#!/usr/bin/env python3
"""Phase 2 base 抽样 —— **事前**分层、T-盲、可复现。

三条要守的:
  1. **T-盲**: 冻结件里不得出现任何测量结果字段。按观测 T 挑 base = selection-on-outcome,
     与当初挑「边界对」同性质。
  2. **可复现**: 冻结 seed + 稳定排序 ⇒ 同一 frame 必须选出同一批 base_id。
     不可复现的「随机」= 事后可以重抽到满意为止。
  3. **权重不能丢**: 各层抽样比例不同(w_h 从 10.25 到 18.0), 直接把过采样的 L 层
     当成总体占比就会高估长文本的分量。恢复 frame 分布必须用 w_h = N_h/n_h。

★ frame 本身的选择机制也要守: run_items 里的历史真人文本是**为了回帖而挑的**
  (选择机制与内容相关), 不能与无过滤的活动流混成一个 frame。
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "probes"))
import harvest_base_pool as H  # noqa: E402

FROZEN = json.loads((ROOT / "tests" / "data" / "phase2"
                     / "base_sample_frozen.json").read_text(encoding="utf-8"))
FRAME = json.loads((ROOT / "tests" / "data" / "phase2"
                    / "frame_reddit_20260819.json").read_text(encoding="utf-8"))

# ── 1. T-盲：冻结件里不许有任何测量结果 ────────────────────────────────────
blob = json.dumps(FROZEN, ensure_ascii=False)
for forbidden in ('"T"', '"p_perm"', '"verdict"', '"separated"', '"t_same"',
                  '"within_js"', '"null_max"'):
    assert forbidden not in blob, f"★ 冻结件出现测量结果字段 {forbidden} ⇒ 选样已被结果污染"
assert FROZEN["sampling_design"]["outcome_blind"] is True

# ── 2. 可复现：同 frame + 同 seed ⇒ 同一批 base_id ─────────────────────────
rows = H.harvest()
again = H.select(rows, seed=FROZEN["sampling_design"]["seed"])
assert [c["base_id"] for c in again["chosen"]] == [c["base_id"] for c in FROZEN["chosen"]], \
    "★ 选样不可复现 ⇒ 事后可以一直重抽到满意为止"
# 反向：换 seed 必须选出不同的一批（否则 seed 是摆设，抽样并未真的随机）
diff = H.select(rows, seed=FROZEN["sampling_design"]["seed"] + 1)
assert [c["base_id"] for c in diff["chosen"]] != [c["base_id"] for c in FROZEN["chosen"]]

# ── 3. 分配规则：每层先 3，总数正好 N_BASE，且不超层容量 ───────────────────
alloc, counts = FROZEN["alloc"], FROZEN["stratum_counts"]
assert sum(alloc.values()) == H.N_BASE == 24
for k, n in alloc.items():
    assert n >= min(H.MIN_PER_STRATUM, counts[k]), f"{k} 层低于保底 3 条"
    assert n <= counts[k], f"{k} 层分配超过容量"
# 长文本层被**有意**上抽：4 条 > 按自然比例应得的 41/367*24 ≈ 2.7
assert alloc["L"] > counts["L"] / sum(counts.values()) * 24, \
    "保底 3 条的意义正是不让只有 41 条的长文本层被自然比例淹没"

# ── 4. 权重：w_h = N_h / n_h，且各层确实不同（所以不能忽略）────────────────
for k, w in FROZEN["sampling_weights"].items():
    assert abs(w - counts[k] / alloc[k]) < 1e-9
assert max(FROZEN["sampling_weights"].values()) / min(FROZEN["sampling_weights"].values()) > 1.5, \
    "★ 各层抽样比例差 1.5 倍以上 ⇒ 报告 median 时必须同时给 frame-weighted 版本"

# ── 5. frame 的选择机制必须写明，且扩展块可执行 ────────────────────────────
assert "为了回帖而挑" in FRAME["harvest"]["why_not_run_items"], \
    "frame 的选择机制不写明 ⇒ 一个不可观测的选择偏倚被烧进 sampling frame"
assert FROZEN["remaining_primary_for_extension"] >= 8, \
    "★ 前登记的 +8 扩展块必须**事前**就可执行, 否则触发时只能临时改规则"
# 三个子版都在，且没有一个占压倒多数（site 可作为 facet 估计）
sites = Counter(r["source_site"] for r in FRAME["rows"])
assert len(sites) == 3 and max(sites.values()) / sum(sites.values()) < 0.5

print("test_cce_phase2_sampling: OK "
      f"(T-盲/可复现+换seed反向/保底3条/权重{'×'.join(str(round(v,1)) for v in FROZEN['sampling_weights'].values())}"
      f"/扩展余量{FROZEN['remaining_primary_for_extension']})")
