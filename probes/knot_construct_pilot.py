# -*- coding: utf-8 -*-
"""九结 · 多题项构念小试验(心理测量口径) —— 预注册 tests/data/knot_construct_pilot_prereg.json。

owner 2026-09-29: 人格/九型/情绪量表不靠逐人金标, 靠多题聚合、在人群层面验证构念。这里先做 3 个结(本语料里有自然变异的
display / pain_seek / reward), 每结 3–4 个内容不同的题项, 由 Jev 逐题读「支持 / 反对 / 不足以判断」, 题项分数 = P(支持)。
验证(无个体金标): ① 结内题项互相关 > 跨结题项互相关(区分) ② 结内合成分与**另一种方法**(三个 MiniMax 模型已有的九结分布,
accuracy/data/warm_reference.json)同结占比的秩相关, 且高于与另两结占比的秩相关(MTMM 对角线) ③ 两轮重测。
只调 Jev(38 条 × 2 轮 = 76 次, 硬上限 120)。产物只放指针与数字。用法: python3 probes/knot_construct_pilot.py [--dry-run]
"""
import argparse, collections, hashlib, importlib.util, itertools, json, os, pathlib, statistics, threading, sys
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import cce_s0_jev as S0  # noqa: E402
_s = importlib.util.spec_from_file_location("_sh", ROOT / "probes/s0_jev_shadow.py"); shadow = importlib.util.module_from_spec(_s); _s.loader.exec_module(shadow)
PRE = ROOT / "tests/data/knot_construct_pilot_prereg.json"
OUT = ROOT / "results/knot_construct_pilot.json"
WARM = ROOT / "accuracy/data/warm_reference.json"; CORPUS = ROOT / "accuracy/data/corpus.json"
CAP, REPS = 120, 2
ITEMS = {
    "display": {"D1": "The writer shares their own expertise, experience or accomplishment for others to see.",
                "D2": "The writer positions themself as a knowledgeable peer or contributor rather than someone asking for help.",
                "D3": "The writer offers a correction, tip or experience mainly to add to the discussion.",
                "D4": "The writer would likely want their contribution acknowledged by others."},
    "pain_seek": {"P1": "The writer describes a problem they currently have that is not yet solved.",
                  "P2": "The writer is asking for or looking for a solution, mechanism or next step.",
                  "P3": "The writer expresses frustration or discomfort with an ongoing situation.",
                  "P4": "The writer would benefit from a concrete, actionable next step."},
    "reward": {"R1": "The writer's own need appears already resolved or satisfied.",
               "R2": "The writer is mainly expressing thanks or satisfaction.",
               "R3": "The writer signals that the conversation or search is closed for them."},
}
CRIT = {"支持": "the text supports this statement", "反对": "the text contradicts this statement",
        "不足以判断": "the text does not give enough evidence either way; do not guess"}


def questions():
    return {iid: {"type": "choice", "instructions": "Judge this statement about the writer from the text only. Statement: " + s, "criteria": CRIT}
            for k in ITEMS for iid, s in ITEMS[k].items()}


def texts():
    w = json.loads(WARM.read_text(encoding="utf-8")); c = {x["id"]: x["b"] for x in json.loads(CORPUS.read_text(encoding="utf-8"))}
    ids = [i for i in w["sample_ids"] if i in c]
    ref = {i: {k: statistics.fmean((w["dists"][m].get(i) or {}).get(k, 0.0) for m in w["dists"] if w["dists"][m].get(i)) for k in ITEMS}
           for i in ids if any(w["dists"][m].get(i) for m in w["dists"])}
    return [(i, c[i]) for i in ids if i in ref], ref


def rank(xs):
    o = sorted(range(len(xs)), key=lambda i: xs[i]); r = [0.0] * len(xs); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and xs[o[j + 1]] == xs[o[i]]: j += 1
        for k in range(i, j + 1): r[o[k]] = (i + j) / 2
        i = j + 1
    return r


def pearson(a, b):
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    sa = sum((x - ma) ** 2 for x in a) ** .5; sb = sum((y - mb) ** 2 for y in b) ** .5
    return None if sa == 0 or sb == 0 else round(sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb), 4)


def spearman(a, b): return pearson(rank(a), rank(b))


def alpha(cols):
    k = len(cols); tot = [sum(v) for v in zip(*cols)]
    vt = statistics.pvariance(tot)
    return None if vt == 0 else round(k / (k - 1) * (1 - sum(statistics.pvariance(c) for c in cols) / vt), 4)


def analyse(rows, ref):
    ids = sorted({r["ptr"] for r in rows if r["probs"] and r["rep"] == 0} & {r["ptr"] for r in rows if r["probs"] and r["rep"] == 1})
    sc = {(r["ptr"], r["rep"]): {q: p.get("支持", 0.0) for q, p in r["probs"].items()} for r in rows if r["probs"]}
    item = {q: [statistics.fmean(sc[(i, rep)][q] for rep in range(REPS)) for i in ids] for k in ITEMS for q in ITEMS[k]}
    out = {"n_texts": len(ids), "per_knot": {}}
    comp = {k: [statistics.fmean(item[q][n] for q in ITEMS[k]) for n in range(len(ids))] for k in ITEMS}
    for k in ITEMS:
        within = [pearson(item[a], item[b]) for a, b in itertools.combinations(ITEMS[k], 2)]
        cross = [pearson(item[a], item[b]) for a in ITEMS[k] for j in ITEMS if j != k for b in ITEMS[j]]
        w_ = statistics.fmean(x for x in within if x is not None); c_ = statistics.fmean(x for x in cross if x is not None)
        rho = {j: spearman(comp[k], [ref[i][j] for i in ids]) for j in ITEMS}
        retest = pearson([statistics.fmean(sc[(i, 0)][q] for q in ITEMS[k]) for i in ids], [statistics.fmean(sc[(i, 1)][q] for q in ITEMS[k]) for i in ids])
        distinct = (w_ - c_) >= 0.2
        converges = rho[k] is not None and rho[k] >= 0.4 and all(rho[k] > (rho[j] if rho[j] is not None else -1) for j in ITEMS if j != k)
        out["per_knot"][k] = {"alpha": alpha([item[q] for q in ITEMS[k]]), "mean_r_within": round(w_, 4), "mean_r_cross": round(c_, 4),
                              "rho_vs_minimax_share": rho, "retest_r": retest, "item_mean_support": {q: round(statistics.fmean(item[q]), 4) for q in ITEMS[k]},
                              "distinct": distinct, "converges": converges,
                              "verdict": "SUPPORTED" if distinct and converges else ("PARTIAL" if distinct or converges else "NOT_SUPPORTED")}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    tx, ref = texts(); js = [(i, body, rep) for i, body in tx for rep in range(REPS)]; assert len(js) <= CAP
    ledger, lock = {"req": 0}, threading.Lock()
    if a.dry_run:
        key = "dry"
        def post(body, k):
            h = int(hashlib.sha256(body["state"].encode()).hexdigest(), 16)
            return {"answers": {q: {"choice": "支持", "probabilities": {"支持": ((h >> n) % 7) / 7, "不足以判断": 0.1}} for n, q in enumerate(body["questions"])}}, None
    else:
        key = shadow._key()
        def post(body, k):
            with lock:
                ledger["req"] += 1
                if ledger["req"] > CAP: raise RuntimeError("BUDGET_EXCEEDED")
            return S0._post(body, k, retries=1)
    qs = questions()
    def one(j):
        i, body, rep = j
        resp, err = post({"model": S0.MODEL, "state": body[:2000], "questions": qs}, key)
        probs = None
        if resp and not err:
            try: probs = {q: resp["answers"][q]["probabilities"] for q in qs}
            except (KeyError, TypeError) as e: err = "BAD_SHAPE:%s" % type(e).__name__
        return {"ptr": "accuracy/data/corpus.json#" + i, "id": i, "rep": rep, "probs": probs, "err": err}
    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = list(ex.map(one, js))
    for r in rows: r["ptr"] = r.pop("id")
    res = {"block": "KNOT_CONSTRUCT_PILOT", "run_at": "2026-09-29", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "requests": ledger["req"], "errors": dict(collections.Counter(r["err"] for r in rows if r["err"])),
           "result": analyse(rows, ref), "raw": rows}
    if not a.dry_run:
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "errors", "result")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
