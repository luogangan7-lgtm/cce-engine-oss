#!/usr/bin/env python3
"""从真实评论构建【主体卡】—— 受众不是一团分布, 是一群各有因果链的人。

2026-08-09。此前 s5 把 N 个人的话拼成一段当"一个人"判结, 这在概念上就是错的:
受众是人群上的分布, 不是一个人。本文件按人聚合, 每人一张卡, 且每张卡都带
**该主体的真实行为记录**, 使"这个主体看了会不会动"成为可证伪的预测而非空想。

每张卡:
  心理侧  九结分布 / 四层分布 / 成本分(连续)
  行为侧  报型号率 提问率 回OP率 给建议率 质询率 详述率 / 实测成本档分布 / 得赞
  暴露侧  发言条数 跨帖数 参与过哪几帖   ← 用于区分"没看到"与"看到了没动"
"""
import os, json, glob, collections, statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
snap = json.load(open(f"{ROOT}/accuracy/data/reddit_snapshot_20260809.json", encoding="utf-8"))
oos_f = sorted(glob.glob(f"{ROOT}/oos*/**/oos_result.json", recursive=True))
rows = {r["id"]: r for r in json.load(open(oos_f[-1], encoding="utf-8"))["rows"]} if oos_f else {}

FACTS = ("named_specific_model", "asked_question", "described_own_situation_in_detail",
         "challenged_or_confronted", "offered_help_or_correction", "thanks_only")

by = collections.defaultdict(lambda: {"c": [], "posts": set()})
for pid, p in snap["posts"].items():
    for c in p["comments"]:
        by[c["author"]]["c"].append({**c, "post": pid})
        by[c["author"]]["posts"].add(pid)

cards = {}
for who, v in by.items():
    seen = [c for c in v["c"] if c["id"] in rows]
    knots, layers_src = collections.Counter(), []
    fact_n = collections.Counter()
    tiers, scores = [], []
    for c in seen:
        r = rows[c["id"]]
        for k, w in r["consensus"].items():
            knots[k] += w
        for f in FACTS:
            fact_n[f] += bool((r.get("facts") or {}).get(f))
        tiers.append(r["obs"]); scores.append(r["score"])
    tot = sum(knots.values()) or 1
    n = len(seen) or 1
    cards[who] = {
        "n_comments": len(v["c"]), "n_readout": len(seen),
        "posts": sorted(v["posts"]), "n_posts": len(v["posts"]),
        "knots": {k: round(w / tot, 3) for k, w in knots.most_common()},
        "cost_tier_dist": dict(collections.Counter(tiers)),
        "cost_score_mean": round(st.mean(scores), 3) if scores else None,
        "behavior_rate": {f: round(fact_n[f] / n, 2) for f in FACTS},
        "replied_to_op": sum(1 for c in v["c"] if c["replied_to_op"]),
        "ups_total": sum(c["ups"] for c in v["c"]),
    }
json.dump(cards, open(f"{ROOT}/subjects/subject_cards.json", "w"), ensure_ascii=False, indent=1)

multi = {w: c for w, c in cards.items() if c["n_posts"] >= 2}
print(f"主体卡 {len(cards)} 张 → subjects/subject_cards.json")
print(f"其中跨帖主体 {len(multi)} 人 —— 这批可区分「没看到」与「看到了没动」, 是校验用的干净测试床\n")
print(f"{'主体':22s} {'条':>3s} {'帖':>3s} {'成本分':>6s}  主结          报型号 提问 回OP")
for w, c in sorted(cards.items(), key=lambda x: -x[1]["n_comments"])[:12]:
    k = ", ".join(f"{a} {b:.0%}" for a, b in list(c["knots"].items())[:2])
    b = c["behavior_rate"]
    print(f"{w[:22]:22s} {c['n_comments']:3d} {c['n_posts']:3d} "
          f"{str(c['cost_score_mean']):>6s}  {k:26s} {b['named_specific_model']:4.0%} "
          f"{b['asked_question']:4.0%} {c['replied_to_op']:3d}")
