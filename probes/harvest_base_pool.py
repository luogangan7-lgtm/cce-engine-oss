#!/usr/bin/env python3
"""Phase 2 base text 抽样 —— **T-盲的事前分层抽样**（跑前冻结）。

## 为什么是事前分层而不是「先别切 strata」
外部评审此前说「先别硬切 strata」针对的是**事后**分层（看完结果再按类别各配一个阈值）。
这里是**事前**: 长度在任何 CCE measurement 发生前就已知, 用它控制样本覆盖是设计效率,
不是事后挑数据。两者性质不同, 已确认。

## 为什么不按 T 挑
按观测 T 挑 base = selection-on-outcome, 与当初挑「边界对」同性质。
选取只用**测量前可观测**的特征: 来源站点、长度、去重。层内用**冻结 seed** 的伪随机,
seed 写进 artifact —— 比「按 sha1 取前 N」更容易解释 inclusion probability 与 weights。

## 分配规则（硬编码算法, **不硬编码 4/10/10 这个结果**）
每层先保证 3 条 → 剩余名额按各层剩余容量 (N_h - 3) 比例分配 → largest remainder 取整。
既不让只有几条的短文本层被自然比例淹没, 也不做成 8/8/8 那种严重偏离真实 frame 的平衡设计。

## 权重
各层抽样比例不同 ⇒ 恢复原 corpus 长度分布必须用 w_h = N_h / n_h,
**不能**把过采样的小层当成总体占比。artifact 里同时存 unweighted 与 frame-weighted 两套摘要。
"""
import json, random, sys, hashlib
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

# ── 前登记参数（改这里 = 改设计, 必须重新前登记）──────────────────────────
MIN_LEN, MAX_LEN = 150, 2000
STRATA = {"S": (150, 599), "M": (600, 1199), "L": (1200, 2000)}
N_BASE = 24
MIN_PER_STRATUM = 3
SEED = 20260819                      # ★ 冻结 seed, 写进 artifact
# primary eligibility: 同一个 source_family(consumer hearing discussion)。
# ★ dev.to / quora / r/mcp / r/AI_Agents 各只有 1-2 条: 既支持不了 source effect 估计,
#   又会把 scope 从清晰的人群生态变成 mixed heterogeneous sources ⇒ 边界反而更糊。
#   **不删除**, 标 OUT_OF_SCOPE_RESERVED 留给 Phase 2B。
PRIMARY_SITES = ("reddit_r_HearingAids", "reddit_r_hardofhearing", "reddit_r_HearingLoss")


def _site(url):
    p = urlparse(url)
    if "reddit" in p.netloc:
        parts = [x for x in p.path.split("/") if x]
        return "reddit_r_" + (parts[1] if len(parts) > 1 and parts[0] == "r" else "unknown")
    if "hearingtracker" in p.netloc:
        return "hearingtracker_forum"
    return p.netloc


def _stratum(n):
    for k, (lo, hi) in STRATA.items():
        if lo <= n <= hi:
            return k
    return None


def harvest():
    """读**冻结的** frame —— tests/data/phase2/frame_reddit_20260819.json。

    ★ 为什么不再用 run_items 的历史真人文本:
      那批是**为了回帖而挑出来的**(选择机制与内容相关, 非随机), 与本次无过滤的活动流
      是两种不同的选择过程。混成一个 frame 会把一个不可观测的选择机制烧进 sampling frame。
      历史那批留作 RESERVED, 不进 Phase 2 primary。
    """
    d = json.loads((ROOT / "tests" / "data" / "phase2"
                    / "frame_reddit_20260819.json").read_text(encoding="utf-8"))
    rows = []
    for r in d["rows"]:
        r = dict(r)
        r["length_stratum"] = _stratum(r["base_length_chars"])
        r["eligibility"] = ("PRIMARY" if r["source_site"] in PRIMARY_SITES
                            else "OUT_OF_SCOPE_RESERVED")
        rows.append(r)
    rows.sort(key=lambda r: r["base_id"])
    return rows


def allocate(counts, n_total=N_BASE, floor=MIN_PER_STRATUM):
    """每层先 floor 条 → 剩余名额按剩余容量比例 → largest remainder。"""
    ks = [k for k in STRATA if counts.get(k, 0) > 0]
    alloc = {k: min(floor, counts[k]) for k in ks}
    rest = n_total - sum(alloc.values())
    if rest <= 0:
        return alloc, 0
    cap = {k: counts[k] - alloc[k] for k in ks}
    tot = sum(cap.values())
    if tot == 0:
        return alloc, rest
    exact = {k: rest * cap[k] / tot for k in ks}
    for k in ks:
        alloc[k] += int(exact[k])
    left = rest - sum(int(exact[k]) for k in ks)
    # largest remainder; 平局按层名固定顺序打破(可复现)
    for k in sorted(ks, key=lambda k: (-(exact[k] - int(exact[k])), k))[:left]:
        alloc[k] += 1
    for k in ks:                                   # 不得超过该层容量
        alloc[k] = min(alloc[k], counts[k])
    return alloc, n_total - sum(alloc.values())


def select(rows, seed=SEED, n_total=N_BASE):
    pool = [r for r in rows if r["eligibility"] == "PRIMARY" and r["length_stratum"]]
    counts = Counter(r["length_stratum"] for r in pool)
    alloc, short = allocate(counts, n_total)
    rng = random.Random(seed)
    chosen, weights = [], {}
    for k in STRATA:
        cand = sorted((r for r in pool if r["length_stratum"] == k), key=lambda r: r["base_id"])
        take = alloc.get(k, 0)
        picked = rng.sample(cand, take) if take else []
        chosen += picked
        if take:
            weights[k] = counts[k] / take          # w_h = N_h / n_h
    chosen.sort(key=lambda r: r["base_id"])
    remaining = [r for r in pool if r not in chosen]
    return {"chosen": chosen, "alloc": dict(alloc), "stratum_counts": dict(counts),
            "sampling_weights": weights, "unfilled_slots": short,
            "remaining_primary": len(remaining)}


if __name__ == "__main__":
    rows = harvest()
    prim = [r for r in rows if r["eligibility"] == "PRIMARY"]
    print(f"eligible(去重, {MIN_LEN}-{MAX_LEN} chars) n={len(rows)}  "
          f"PRIMARY={len(prim)}  OUT_OF_SCOPE_RESERVED={len(rows)-len(prim)}")
    print("  按站点:", dict(Counter(r["source_site"] for r in rows)))
    sel = select(rows)
    print(f"  分层容量 {sel['stratum_counts']} → 分配 {sel['alloc']}"
          f"  未填满 {sel['unfilled_slots']}")
    print("  抽样权重 w_h=N_h/n_h:", {k: round(v, 3) for k, v in sel["sampling_weights"].items()})
    print(f"  ★ 扩展块(+8)可用余量: {sel['remaining_primary']} 条"
          f" —— {'够' if sel['remaining_primary'] >= 8 else '**不够, 必须先按同规则补抓**'}")
    if "--freeze" in sys.argv:
        out = ROOT / "tests" / "data" / "phase2" / "base_sample_frozen.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "sampling_design": {"type": "preregistered_length_stratified",
                                "strata": {k: list(v) for k, v in STRATA.items()},
                                "allocation_rule": "minimum_3_then_proportional_remaining_capacity",
                                "selection_within_stratum": "frozen_seed_random",
                                "seed": SEED, "outcome_blind": True,
                                "primary_sites": list(PRIMARY_SITES),
                                "eligible_chars": [MIN_LEN, MAX_LEN]},
            "stratum_counts": sel["stratum_counts"], "alloc": sel["alloc"],
            "sampling_weights": sel["sampling_weights"],
            "unfilled_slots": sel["unfilled_slots"],
            "remaining_primary_for_extension": sel["remaining_primary"],
            "chosen": sel["chosen"],
            "reserved": [r for r in rows if r["eligibility"] == "OUT_OF_SCOPE_RESERVED"],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  已冻结 →", out.relative_to(ROOT))
