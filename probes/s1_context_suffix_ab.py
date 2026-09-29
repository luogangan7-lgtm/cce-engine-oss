# -*- coding: utf-8 -*-
"""s1 语境串带不带 s0【情境】后缀 · 对照(预注册 tests/data/s1_context_suffix_ab_prereg.json)。

为什么(生产状态表 s1 行自己写着): 「标定时 s1 的语境串**不含** s0 的【情境】后缀; 生产现在带, 带后缀的全流程重测尚无」。
s1 的组内散布闸(WITHIN_JS_MAX)与 K1 的 top-1 判定都是在**不带后缀**的条件下标定的 ⇒ 后缀若显著挪动分布, 生产读数就在标定条件之外。
做法: 16 条真实文本(post6 的 8 条入站回应 + 冻结集第 20–27 段, 此前任何 s0 测试都没用过), 后缀由真实 s0 读出生成(与生产同一函数);
每条 s1 跑 4 次: 带后缀 ×2 / 不带 ×2(交错), 比较**臂间**分布差与**臂内**重复噪声。全占比: 比的是整条分布(JS), 不是 top-1。
MiniMax 经生产同一出站路径, 本进程开请求作用域, 硬上限 600(撞上即停)。产物只放指针与数字。
用法: .venv/bin/python probes/s1_context_suffix_ab.py [--dry-run]
"""
import argparse, collections, hashlib, importlib.util, json, math, os, pathlib, random, statistics, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import cce_full_run as FR                     # noqa: E402
import cce_s0_jev as S0                       # noqa: E402
from cce_request_budget import open_scope, scope_status   # noqa: E402
_s = importlib.util.spec_from_file_location("_sh", ROOT / "probes/s0_jev_shadow.py"); shadow = importlib.util.module_from_spec(_s); _s.loader.exec_module(shadow)
PRE = ROOT / "tests/data/s1_context_suffix_ab_prereg.json"
OUT = ROOT / "results/s1_context_suffix_ab.json"
SRC = ROOT / "examples/cce_reddit_post6_responses_prior_v1.json"
CAP, LAYERS = 600, ("desire_vec", "need_vec", "emotion_vec", "action_vec")


def js(p, q):
    ks = sorted(set(p) | set(q))
    a = [p.get(k, 0.0) for k in ks]; b = [q.get(k, 0.0) for k in ks]
    sa, sb = math.fsum(a) or 1.0, math.fsum(b) or 1.0
    a = [x / sa for x in a]; b = [x / sb for x in b]; m = [(x + y) / 2 for x, y in zip(a, b)]
    kl = lambda u, v: math.fsum(x * math.log2(x / y) for x, y in zip(u, v) if x > 0)
    return 0.5 * kl(a, m) + 0.5 * kl(b, m)


def texts():
    src = json.loads(SRC.read_text(encoding="utf-8"))
    base = ("reddit subreddit HearingAids hearing_aids inbound response to %s: %s" % (src["content_ref"], src["context"]["summary"]))
    prior = src["responses"][0]["prior_turn"]["text"]
    out = [("post6:" + r["evidence_ref"], r["text"], prior) for r in src["responses"]]
    out += [(p, body, None) for p, body in shadow.load_passages()[20:28]]
    return base, out


def suffix(body, prior):
    """与生产 s0 同一套函数: 五面单读 + (有 prior 时)情绪余温 成对读; 取非未知值拼后缀。"""
    facets = [f for f in FR.CTX_FACETS if f.get("readable_from_text") in (True, "partial")]
    read, _p, err = S0.s0_jev_read(body[:2000], [f for f in facets if f["key"] not in S0.READ_WITHHELD])
    vals = {k: v for k, v in (read or {}).items() if v not in FR.CTX_UNKNOWN}
    if prior:
        c, _pp, e2 = S0.s0_residue_paired(prior, body, facets)
        if c and c not in FR.CTX_UNKNOWN: vals["情绪余温"] = c
    return (" 【情境】" + json.dumps(vals, ensure_ascii=False)) if vals else "", err


def score(rows):
    per = {l: [] for l in LAYERS}; flips = collections.Counter()
    by = collections.defaultdict(dict)
    for r in rows:
        if r["layers"]: by[r["ptr"]][(r["arm"], r["rep"])] = r
    used = [p for p, d in by.items() if len(d) == 4]
    for p in used:
        d = by[p]
        for l in LAYERS:
            w = [d[("with", i)]["layers"][l] for i in (0, 1)]; o = [d[("without", i)]["layers"][l] for i in (0, 1)]
            between = statistics.fmean(js(a, b) for a in w for b in o)
            within = statistics.fmean([js(*w), js(*o)])
            per[l].append(between - within)
            tw = [max(x, key=x.get) for x in w]; to = [max(x, key=x.get) for x in o]
            flips[l] += int(tw[0] == tw[1] and to[0] == to[1] and tw[0] != to[0])
    res = {}
    for l, ds in per.items():
        if not ds: res[l] = None; continue
        rng = random.Random(20260929)
        bs = sorted(statistics.fmean(rng.choice(ds) for _ in ds) for _ in range(2000))
        m, lo = statistics.fmean(ds), bs[49]
        res[l] = {"n_texts": len(ds), "mean_excess_js": round(m, 4), "ci95": [round(lo, 4), round(bs[1949], 4)],
                  "stable_top1_flips": flips[l], "verdict": "SHIFTS" if m >= 0.05 and lo > 0 else "NEUTRAL"}
    return {"n_texts_used": len(used), "per_layer": res,
            "overall": "SHIFTS" if any(v and v["verdict"] == "SHIFTS" for v in res.values()) else "NEUTRAL"}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    base, tx = texts()
    if not a.dry_run:
        os.environ["TYPESAFE_API_KEY"] = shadow._key()          # 仅本进程内, 不打印不落盘
        sys.path.insert(0, str(ROOT / "probes")); import extractor_counterexample_run_r2 as KR   # noqa: E402
        KR._load_key()                                        # 读进本进程环境(子进程继承), 不打印
    td = tempfile.mkdtemp()
    open_scope("s1_suffix_ab", CAP, os.path.join(td, "budget.json"))
    rows, sfx = [], {}
    for n, (ptr, body, prior) in enumerate(tx):
        if a.dry_run:
            s, err = " 【情境】{\"进程位置\": \"在找方案\"}", None
        else:
            s, err = suffix(body, prior)
        sfx[ptr] = {"has_suffix": bool(s), "facets": sorted(json.loads(s.split("】", 1)[1]).keys()) if s else [], "err": err}
        if not s:
            continue                                            # 没后缀 ⇒ 两臂相同, 不进对照
        tf = os.path.join(td, "t%d.txt" % n); pathlib.Path(tf).write_text(body, encoding="utf-8")
        for rep in (0, 1):
            for arm, ctx in (("with", base + s), ("without", base)):
                out = os.path.join(td, "s1_%d_%s_%d.json" % (n, arm, rep))
                if a.dry_run:
                    h = int(hashlib.sha256((ptr + arm + str(rep)).encode()).hexdigest(), 16)
                    lay = {l: {"x": 0.5 + (h % 7) / 20, "y": 0.5 - (h % 7) / 20} for l in LAYERS}
                else:
                    try:
                        lay = FR.run_knot_classify(tf, ctx, 3, out)["stage1"].get("layers")
                    except Exception as e:                  # noqa: BLE001
                        lay = None; print("fail", ptr, arm, rep, type(e).__name__, str(e)[:120])
                rows.append({"ptr": ptr, "arm": arm, "rep": rep, "layers": lay})
    res = {"block": "S1_CONTEXT_SUFFIX_AB", "run_at": "2026-09-29", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "python": "%d.%d" % sys.version_info[:2], "requests": scope_status(), "suffix": sfx,
           "result": score(rows), "raw": rows}
    if not a.dry_run:
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "result")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
