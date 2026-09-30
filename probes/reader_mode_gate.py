# -*- coding: utf-8 -*-
"""对齐出口的读者闸: 「5 次抽样全一致」才判, 还是「众数占比 >= 0.8」就判? 预注册 tests/data/reader_mode_gate_prereg.json。

2026-09-30/10-01 连跑 10 次线上 canary, 8 次读者 top-1 是 4/5(众数每次都是同一个结), 对齐出口按现规则整条扣发 —— V3 校出来的 19 个条目大多数时候用不上。
K1 的依据是「同一文本跨次运行 top-1 一致 >= 7/8」, 说的是**跨次**可复现, 不是**次内**全票。归档事后分析(零调用, 留一法, n=5 且同一文本 >= 3 次运行):
众数占比 1.0 的运行与其余运行的众数一致 39/39, 0.8 的 46/49, 0.6 的 12/23。那是看过的数据, 这里在没做过 s2 读数的 24 条真实评论上确认:
每条文本独立读 3 次(生产同一路径 reply_loop.readout, 读者侧), 每次运行与**另外两次**的共识众数比(另两次不一致 ⇒ 无共识, 单列)。
MiniMax, 硬上限 800 次请求, 3 条并行。产物只落结名与占比。用法: .venv/bin/python probes/reader_mode_gate.py [--dry-run | --rescore]
"""
import argparse, collections, hashlib, importlib.util, json, os, pathlib, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import reply_loop as RL                                      # noqa: E402
from cce_request_budget import open_scope, scope_status     # noqa: E402
def _load(name, rel):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
V5, MON = _load("_v5", "probes/align_atoms_v5.py"), _load("_mon", "probes/within_js_monitor.py")
PRE = ROOT / "tests/data/reader_mode_gate_prereg.json"
NUM = ROOT / "results/reader_mode_gate_rows.json"
OUT = ROOT / "results/reader_mode_gate.json"
CAP, N_TEXTS, REPS, WORKERS = 800, 24, 3, 3
SHARE, MIN_POINT, MIN_LCB = 0.8, 0.875, 0.80        # 0.875 = K1 的 7/8
CTX = "reddit subreddit HearingAids hearing_aids outbound reply(对方原文/写作基准侧)"


def texts():
    return (V5.natural(100) + V5.natural(120))[:N_TEXTS]


def build(rows):
    by = collections.defaultdict(list)
    for r in rows: by[r["ptr"]].append(r)
    bins = collections.defaultdict(lambda: {"agree": 0, "disagree": 0, "no_consensus": 0})
    for ptr, rs in by.items():
        if len(rs) != REPS: continue                          # 三次读数不齐的文本不进
        for i, r in enumerate(rs):
            oth = {x["mode"] for j, x in enumerate(rs) if j != i}
            b = bins[str(r["share"])]
            if len(oth) != 1: b["no_consensus"] += 1
            else: b["agree" if r["mode"] in oth else "disagree"] += 1
    def rate(b):
        n = b["agree"] + b["disagree"] + b["no_consensus"]      # 无共识按不一致计(保守)
        return {"agree": b["agree"], "n": n, "rate": round(b["agree"] / n, 4) if n else None, "lcb95": MON.clopper_pearson(b["agree"], n, 0.10)[0] if n else None, **b}
    per = {k: rate(v) for k, v in sorted(bins.items())}
    t = per.get(str(SHARE)) or {"n": 0, "rate": None, "lcb95": None}
    n_runs = sum(v["n"] for v in per.values())
    avail = {"unanimous_only": round((per.get("1.0") or {"n": 0})["n"] / n_runs, 4) if n_runs else None,
             "share_ge_0.8": round(((per.get("1.0") or {"n": 0})["n"] + t["n"]) / n_runs, 4) if n_runs else None}
    if t["n"] < 15: v = "INSUFFICIENT"
    elif t["rate"] >= MIN_POINT and t["lcb95"] >= MIN_LCB: v = "MODE_GATE_OK"
    else: v = "KEEP_UNANIMOUS"
    return {"texts_complete": sum(len(rs) == REPS for rs in by.values()), "runs": n_runs, "by_share": per, "availability": avail, "verdict": v}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--rescore", action="store_true"); a = ap.parse_args(argv)
    tx = texts()
    if a.dry_run:
        print(len(tx), len({p for p, _ in tx})); return
    if not a.rescore:
        import extractor_counterexample_run_r2 as KR   # noqa: E402
        KR._load_key()
        td = tempfile.mkdtemp(); open_scope("reader_mode_gate", CAP, os.path.join(td, "budget.json")); rows = []

        def one(job):
            n, rep, ptr, body = job
            try:
                d = RL.readout(body, CTX, 3, "T%d_%d" % (n, rep), td); s = d["stage2"]["sampling"]
                return {"ptr": ptr, "rep": rep, "mode": s.get("top1_mode"), "share": s.get("top1_mode_share"), "n_ok": s.get("n_ok"), "instrument": d["stage2"]["instrument"]["instrument_hash"]}
            except Exception as e:      # noqa: BLE001
                print("fail", n, rep, type(e).__name__, str(e)[:100]); return None
        jobs = [(n, rep, ptr, body) for n, (ptr, body) in enumerate(tx) for rep in range(REPS)]
        for i in range(0, len(jobs), WORKERS * 2):
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                rows += [r for r in ex.map(one, jobs[i:i + WORKERS * 2]) if r and r["mode"]]
            NUM.write_text(json.dumps({"requests": scope_status(), "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
            if (scope_status() or {}).get("used", 0) >= CAP - 30: break
    num = json.loads(NUM.read_text(encoding="utf-8"))
    res = {"block": "READER_MODE_GATE", "run_at": "2026-10-01", "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(), "rows_sha256": hashlib.sha256(NUM.read_bytes()).hexdigest(),
           "requests": num.get("requests"), "result": build(num["rows"])}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "result")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
