# -*- coding: utf-8 -*-
"""k=5 仪器(outbound_post)的 s1 组内散布闸重标定(预注册 tests/data/within_js_k5_recalibration_prereg.json)。

存档里现行 k=5 仪器只有 2 份读数, 标不了 ⇒ 自己采: 同社区真实帖子(保险库里的 1208 帖, 只送正文给 MiniMax, 产物只落数字与 sha)。
标定集 20 帖各跑 1 次; 留出集 10 帖各跑 2 次。规则与 k=3 那次相同: median + 2×MAD(未缩放), 留出扣发率在 [0.05, 0.25] 才采纳。
MiniMax 经生产同一路径(run_knot_classify, k=5), 本进程开请求作用域, 硬上限 520。
用法: .venv/bin/python probes/within_js_k5_recalibrate.py [--dry-run | --rescore]
"""
import argparse, hashlib, importlib.util, json, os, pathlib, random, re, statistics, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import cce_full_run as FR                                   # noqa: E402
from cce_request_budget import open_scope, scope_status     # noqa: E402
_s = importlib.util.spec_from_file_location("_wr", ROOT / "probes/within_js_recalibrate.py"); wr = importlib.util.module_from_spec(_s); _s.loader.exec_module(wr)
PRE = ROOT / "tests/data/within_js_k5_recalibration_prereg.json"
NUM = ROOT / "results/within_js_k5_numbers.json"
OUT = ROOT / "results/within_js_recalibration_k5.json"
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault/hearingaids_others_20260809.json")
CTX = "reddit subreddit HearingAids hearing_aids outbound post"
CAP, N_CAL, N_HOLD, SEED, INSTRUMENT = 520, 20, 10, 20260930, "c4419c3e53aa2fa9"
LAYERS = wr.LAYERS


def sample():
    posts = json.loads(VAULT.read_text(encoding="utf-8"))["posts"]
    ok = []
    for p in posts:
        t = ((p.get("title") or "") + "\n\n" + (p.get("selftext") or "")).strip()
        n = len(t.split())
        if 80 <= n <= 400 and not re.search(r"\bu/\w+|/user/\w+", t):      # 不送带用户名提及的正文
            ok.append(t)
    ok.sort(key=lambda t: hashlib.sha256(t.encode()).hexdigest())           # 顺序与文件里的排列无关
    random.Random(SEED).shuffle(ok)
    return ok[:N_CAL], ok[N_CAL:N_CAL + N_HOLD]


def calibrate(rows):
    out = {}
    for l in LAYERS:
        v = [r["within_js"][l] for r in rows]
        med = statistics.median(v); mad = statistics.median(abs(x - med) for x in v)
        out[l] = {"median": round(med, 4), "mad": round(mad, 4), "threshold": round(med + 2 * mad, 3), "n": len(v)}
    return out


def build(rows):
    assert {r["instrument"] for r in rows} == {INSTRUMENT}, "采到的不是预注册里那台仪器"
    cal = calibrate([r for r in rows if r["set"] == "cal"])
    hold = wr.evaluate(cal, FR.WITHIN_JS_MAX_DEFAULT, [r for r in rows if r["set"] == "hold"])
    return cal, hold, {l: (cal[l]["threshold"] if hold[l]["adopt"] else FR.WITHIN_JS_MAX_DEFAULT[l]) for l in LAYERS}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--rescore", action="store_true")
    a = ap.parse_args(argv)
    if not a.rescore:
        cal_t, hold_t = sample()
        if a.dry_run:
            print("cal", len(cal_t), "hold", len(hold_t)); return
        import extractor_counterexample_run_r2 as KR   # noqa: E402
        KR._load_key()
        td = tempfile.mkdtemp(); open_scope("within_js_k5", CAP, os.path.join(td, "budget.json"))
        rows = []
        jobs = [("cal", i, t, 0) for i, t in enumerate(cal_t)] + [("hold", i, t, rep) for i, t in enumerate(hold_t) for rep in (0, 1)]
        for n, (st, i, t, rep) in enumerate(jobs):
            tf = os.path.join(td, "t%d.txt" % n); pathlib.Path(tf).write_text(t, encoding="utf-8")
            try:
                d = FR.run_knot_classify(tf, CTX, 5, os.path.join(td, "s1_%d.json" % n))
                s1 = d["stage1"]
                if not s1.get("within_js"):
                    print("skip(no within_js)", st, i, s1.get("measurement_status")); continue
                rows.append({"set": st, "text": i if st == "hold" else 1000 + i, "rep": rep, "sha16": hashlib.sha256(t.encode()).hexdigest()[:16],
                             "instrument": d["stage2"]["instrument"]["instrument_hash"], "within_js": s1["within_js"], "layers": s1["layers"]})
            except Exception as e:      # noqa: BLE001
                print("fail", st, i, rep, type(e).__name__, str(e)[:100])
            NUM.write_text(json.dumps({"source": "同社区真实帖子 s1 k=5(只有数字与 sha)", "requests": scope_status(), "rows": rows}, indent=1), encoding="utf-8")   # 每步落盘
    num = json.loads(NUM.read_text(encoding="utf-8"))
    cal, hold, adopted = build(num["rows"])
    res = {"block": "WITHIN_JS_RECALIBRATION_K5", "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "numbers_sha256": hashlib.sha256(NUM.read_bytes()).hexdigest(), "requests": num.get("requests"),
           "n_cal": sum(r["set"] == "cal" for r in num["rows"]), "n_hold_runs": sum(r["set"] == "hold" for r in num["rows"]),
           "calibration": cal, "holdout": hold, "adopted": adopted, "adopted_for": INSTRUMENT}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "n_cal", "n_hold_runs", "calibration", "holdout", "adopted")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
