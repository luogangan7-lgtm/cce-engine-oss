# -*- coding: utf-8 -*-
"""s1 组内散布闸 · 语料抽样上的扣发率(预注册 tests/data/within_js_corpus_band_prereg.json)。

生产流上的序贯监测(within_js_monitor)只攒到 18 / 11 条, 而且它在 n=60 那次查看**没有任何计数能判带内**(99% 精确区间太宽)。
网页 GPT(2026-09-30): 可以另开一个研究, 从社区语料**概率抽样**固定 n=100, 单次 95% 精确区间整个落在 [5%, 25%] 才算带内(= 11–16/100)。
★ 这是另一个总体(语料样本), 不与生产流合并计数; 生产流那张表照旧挂着。
k=3: 保险库多轮链语料里非楼主的首条顶层评论(每帖至多 2 条)。k=5: 保险库帖子(跳过重标定用过的前 30 帖)。只送正文, 产物只落数字与 sha。
用法: .venv/bin/python probes/within_js_corpus_band.py [--dry-run | --rescore]
"""
import argparse, collections, hashlib, importlib.util, json, os, pathlib, random, re, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import cce_full_run as FR                                   # noqa: E402
from cce_request_budget import open_scope, scope_status     # noqa: E402
def _load(name, rel):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
K5, MON = _load("_k5", "probes/within_js_k5_recalibrate.py"), _load("_mon", "probes/within_js_monitor.py")
PRE = ROOT / "tests/data/within_js_corpus_band_prereg.json"
NUM = ROOT / "results/within_js_corpus_band_numbers.json"
OUT = ROOT / "results/within_js_corpus_band.json"
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault")
N, SEED, BAND, MAX_PER_POST = 100, 20261001, (0.05, 0.25), 2
ARMS = {"k3": {"k": 3, "instrument": "d4cce4c745f3f991"}, "k5": {"k": 5, "instrument": "c4419c3e53aa2fa9"}}
CAP = 2150          # 两臂合计(open_scope 一个进程只开一次); 实测约 8.4 / 10.2 次请求每份读数
LAYERS = MON.LAYERS
_MENTION = re.compile(r"\bu/\w+|/user/\w+")


def sample_k3():
    """[(语境串, 正文)] —— 抽样顺序固定; 前 N 条是样本, 其后是调用失败时的递补。"""
    titles = {p["id"]: p.get("title") or "" for p in json.loads((VAULT / "hearingaids_others_20260809.json").read_text(encoding="utf-8"))["posts"]}
    el = []
    for c in json.loads((VAULT / "hearingaids_chains_20260809.json").read_text(encoding="utf-8"))["chains"]:
        t = c["turns"][0] if c["turns"] else None
        if c["isOP"] or not t or t["dep"] != 0 or not titles.get(c["post"]) or _MENTION.search(t["b"]) or _MENTION.search(titles[c["post"]]):
            continue
        if 25 <= len(t["b"].split()) <= 200:
            el.append((c["post"], t["b"]))
    el.sort(key=lambda x: hashlib.sha256(x[1].encode()).hexdigest()); random.Random(SEED).shuffle(el)
    seen, out = collections.Counter(), []
    for post, b in el:
        if seen[post] < MAX_PER_POST:
            seen[post] += 1
            out.append(("reddit subreddit HearingAids hearing_aids inbound response to post: %s" % titles[post][:160], b))
    return out


def sample_k5():
    K5.N_HOLD = 10 ** 6
    cal, rest = K5.sample()
    return [(K5.CTX, t) for t in rest[10:]]          # rest[:10] = 重标定的留出集


def verdict(k, n):
    lo, hi = MON.clopper_pearson(k, n, 0.05)
    v = "IN_BAND" if lo >= BAND[0] and hi <= BAND[1] else ("OUT_OF_BAND" if hi < BAND[0] or lo > BAND[1] else "STRADDLES")
    return {"exceed": k, "n": n, "rate": round(k / n, 4), "ci95": [lo, hi], "verdict": v}


def build(rows):
    res = {}
    for arm, cfg in ARMS.items():
        rs = [r for r in rows if r["arm"] == arm][:N]; th = FR.within_js_max(cfg["instrument"])
        assert all(r["instrument"] == cfg["instrument"] for r in rs), "仪器变了 —— 阈值不是给这台仪器标的"
        res[arm] = {"n_texts": len(rs), "complete": len(rs) == N, "thresholds": {l: th[l] for l in LAYERS},
                    "per_layer": {l: verdict(sum(r["within_js"].get(l, 0) > th[l] for r in rs), len(rs)) for l in LAYERS} if rs else {}}
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--rescore", action="store_true")
    a = ap.parse_args(argv)
    samples = {"k3": sample_k3(), "k5": sample_k5()}
    if a.dry_run:
        print({k: len(v) for k, v in samples.items()}); return
    if not a.rescore:
        import extractor_counterexample_run_r2 as KR   # noqa: E402
        KR._load_key()
        rows = json.loads(NUM.read_text(encoding="utf-8"))["rows"] if NUM.exists() else []      # 断点续跑: 已有读数不重采
        td = tempfile.mkdtemp(); open_scope("within_js_corpus", CAP, os.path.join(td, "budget.json"))
        for arm, cfg in ARMS.items():
            done = {r["sha16"] for r in rows if r["arm"] == arm}
            for n, (ctx, t) in enumerate(samples[arm]):
                if sum(r["arm"] == arm for r in rows) >= N:
                    break
                sha = hashlib.sha256(t.encode()).hexdigest()[:16]
                if sha in done:
                    continue
                tf = os.path.join(td, "%s_t%d.txt" % (arm, n)); pathlib.Path(tf).write_text(t, encoding="utf-8")
                try:
                    d = FR.run_knot_classify(tf, ctx, cfg["k"], os.path.join(td, "%s_s1_%d.json" % (arm, n)))
                    js = d["stage1"].get("within_js")
                    if js:
                        rows.append({"arm": arm, "order": n, "sha16": sha, "instrument": d["stage2"]["instrument"]["instrument_hash"], "within_js": js})
                    else:
                        print("skip(no within_js)", arm, n, d["stage1"].get("measurement_status"))
                except Exception as e:      # noqa: BLE001
                    print("fail", arm, n, type(e).__name__, str(e)[:100])
                    if "BUDGET" in str(e).upper():
                        break
                NUM.write_text(json.dumps({"source": "语料抽样 s1 读数(只有数字与 sha)", "requests": scope_status(), "rows": rows}, indent=1), encoding="utf-8")
    num = json.loads(NUM.read_text(encoding="utf-8"))
    res = {"block": "WITHIN_JS_CORPUS_BAND", "run_at": "2026-09-30", "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(), "numbers_sha256": hashlib.sha256(NUM.read_bytes()).hexdigest(),
           "requests": num.get("requests"), "result": build(num["rows"])}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "result")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
