#!/usr/bin/env python3
"""样本外验证 + 帖级判注 — 用已验收的引擎跑 Reddit 快照。

复用 run_gates 的同一套器械(5标注者九结共识 / 事实抽取 / 观察侧定档 / 成本分),
不重新实现, 避免两处实现漂移。
主判: 在【未进入验收语料】的评论上, spearman(成本分, 实测档) 是否仍显著。
     ——验收是留一法内部校准, 这一步才是真正的样本外。
"""
import os, sys, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_gates as R
from concurrent.futures import ThreadPoolExecutor

D = os.path.dirname(os.path.abspath(__file__))
SNAP = json.load(open(f"{D}/data/reddit_snapshot_20260809.json", encoding="utf-8"))
ONLY = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else None

items = []
for pid, p in SNAP["posts"].items():
    if ONLY and pid not in ONLY:
        continue
    for c in p["comments"]:
        items.append({"id": c["id"], "b": c["body"], "post": pid, "author": c["author"],
                      "ups": c["ups"], "seen": c["seen"], "followed_up": c["replied_to_op"]})
print(f"待判 {len(items)} 条 · 样本外 {sum(1 for i in items if not i['seen'])} 条 · 标注者 {R.MODELS}", flush=True)

jobs = [(m, it) for m in R.MODELS for it in items]
with ThreadPoolExecutor(max_workers=10) as ex:
    ann = list(ex.map(R.annot_dist, jobs))
by = collections.defaultdict(dict)
for (m, it), (iid, dist) in zip(jobs, ann):
    if dist:
        by[iid][m] = dist
with ThreadPoolExecutor(max_workers=8) as ex:
    facts = dict(ex.map(R.extract_facts, items))

rows = []
for it in items:
    vs = list(by[it["id"]].values())
    f = facts.get(it["id"])
    if not vs or not f:
        continue
    agg = collections.defaultdict(float)
    for v in vs:
        for k, w in v.items():
            agg[k] += w / len(vs)
    cons = dict(agg)
    obs = R.observed_tier_from_facts(f, it)
    s = R.expected_ordinal(cons, it)
    if obs is None or s is None:
        continue
    rows.append({**it, "n_annotators": len(vs), "top1": max(cons, key=cons.get),
                 "consensus": {k: round(v, 3) for k, v in sorted(cons.items(), key=lambda x: -x[1]) if v >= 0.05},
                 "score": round(s, 4), "obs": obs, "obs_ord": R.TIER_ORD[obs], "facts": f})


def block(rs, label):
    if len(rs) < 4:
        return {"label": label, "n": len(rs), "note": "样本不足, 不判"}
    rho = R._spearman([r["score"] for r in rs], [r["obs_ord"] for r in rs])
    p = R._spearman_p(rho, len(rs))
    return {"label": label, "n": len(rs), "spearman": rho, "p": p,
            "significant": bool(p is not None and p < 0.05 and rho is not None and rho >= 0.3),
            "obs_tiers": dict(collections.Counter(r["obs"] for r in rs)),
            "top1_knots": dict(collections.Counter(r["top1"] for r in rs).most_common())}


res = {"gate": "OOS 样本外验证", "snapshot": SNAP["_meta"]["snapshot"], "n_rows": len(rows),
       "taxonomy": R.TAXO.get("version"), "annotators": R.MODELS,
       "全部": block(rows, "全部"),
       "样本外(未进验收语料)": block([r for r in rows if not r["seen"]], "样本外"),
       "样本内(已在验收语料)": block([r for r in rows if r["seen"]], "样本内"),
       "分帖": {pid: block([r for r in rows if r["post"] == pid], pid) for pid in SNAP["posts"]},
       "帖级": {pid: {"ups": p["ups"], "upvote_ratio": p["upvote_ratio"],
                     "n_ext_comments": len(p["comments"]), "n_people": p["n_people"],
                     "n_op_replies": p["n_op_replies"],
                     "comments_per_up": round(len(p["comments"]) / max(p["ups"], 1), 3),
                     "replied_to_op": sum(1 for c in p["comments"] if c["replied_to_op"])}
                for pid, p in SNAP["posts"].items()},
       "rows": rows}
json.dump(res, open(f"{D}/oos_result.json", "w"), ensure_ascii=False, indent=1)
for k in ("全部", "样本外(未进验收语料)", "样本内(已在验收语料)"):
    b = res[k]
    print(f"{k:22s} n={b['n']:3d} ρ={b.get('spearman')} p={b.get('p')} 显著={b.get('significant')}", flush=True)
print("→ accuracy/oos_result.json")
