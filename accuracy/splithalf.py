#!/usr/bin/env python3
"""折半信度 —— 聚合之后, 主体的四层读出能不能稳定地代表这个人?

判据: 同一个人两半的 JS(组内) 显著小于 不同人之间的 JS(组间)。
  过 ⇒ 聚合读出能捕获个体差异, 该层是主体属性, 可跨平台迁移
  不过 ⇒ 该层不是人的属性, 只是此刻文本的属性
预注册: 欲望应当组内最小(它按定义最稳)。若欲望都不过, 说明读出仍不可用于主体建模。
"""
import os, sys, json, random, statistics as st, itertools
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "accuracy"))
from aggregate_core import read_many, aggregate, js

U = json.load(open(f"{ROOT}/accuracy/data/hearingaids_regulars_20260809.json",
                   encoding="utf-8"))["users"]
rng = random.Random(20260809)
people = {w: [c["b"] for c in v if len(c["b"].split()) >= 12] for w, v in U.items()}
people = {w: v for w, v in people.items() if len(v) >= 8}
print(f"常驻者 {len(people)} 人, 每人取 8 条(>=12词), 折半 4+4", flush=True)

halves = {}
for w, txts in people.items():
    s = txts[:]; rng.shuffle(s); s = s[:8]
    A, B = s[:4], s[4:]
    halves[w] = (aggregate(read_many(A)), aggregate(read_many(B)))
    print(f"  {w} 读出完成", flush=True)
halves = {w: v for w, v in halves.items() if v[0] and v[1]}
print(f"\n有效 {len(halves)} 人\n")

out = {}
for L in ("欲望", "情绪", "需求", "行动"):
    within = [js(a[L], b[L]) for a, b in halves.values()]
    between = [js(x[0][L], y[1][L]) for x, y in itertools.permutations(halves.values(), 2)]
    wi, be = st.mean(within), st.mean(between)
    se = st.pstdev(within) / (len(within) ** .5)
    out[L] = {"组内": round(wi, 4), "组间": round(be, 4), "比值": round(wi / be, 3),
              "组内95CI": [round(wi - 1.96 * se, 4), round(wi + 1.96 * se, 4)],
              "显著低于组间": bool(wi + 1.96 * se < be)}
print(f"{'层':6s} {'组内(同人两半)':>14s} {'组间':>9s} {'比值':>7s} 显著")
for L, v in out.items():
    print(f"{L:6s} {v['组内']:14.4f} {v['组间']:9.4f} {v['比值']:7.3f} {'✅' if v['显著低于组间'] else '❌'}")
res = {"gate": "折半信度·聚合读出", "n_people": len(halves), "每人条数": 8, "折半": "4+4",
       "逐层": out,
       "判据": "组内显著低于组间 ⇒ 该层是主体属性, 可跨平台迁移",
       "预注册": "欲望应组内最小; 若欲望不过, 聚合读出仍不可用于主体建模",
       "对照_单条读出": {"欲望比值": 0.95, "情绪": 0.93, "需求": 0.91, "行动": 0.94,
                      "note": "2026-08-09 单条读出实测, 全部接近1即几乎无个体信息"}}
json.dump(res, open(f"{ROOT}/accuracy/splithalf.json", "w"), ensure_ascii=False, indent=1)
print(f"\n对照单条读出(全部≈0.95, 几乎无个体信息): 聚合后欲望比值 {out['欲望']['比值']}")
