#!/usr/bin/env python3
"""+8 扩展块 —— 必须**预先确定**，且不得被结果污染。

前登记原文两条：
  ① 只允许扩一次；
  ② 这 8 个 base **不能根据前 24 个的 T 来选**，只按原语料选择规则继续取下一批。
本测试守的就是这两条能被机器检验，而不是靠我记得。
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "tests" / "data" / "phase2"
sys.path.insert(0, str(ROOT / "probes"))
import harvest_base_pool as H  # noqa: E402

E = json.loads((P / "base_extension_frozen.json").read_text(encoding="utf-8"))
M = json.loads((P / "base_sample_frozen.json").read_text(encoding="utf-8"))

# ── 1. T-盲：冻结件里不得含任何测量结果 ────────────────────────────────────
blob = json.dumps(E, ensure_ascii=False)
for bad in ('"T"', '"p_perm"', '"verdict"', '"separated"', '"qualified"'):
    assert bad not in blob, f"★ 扩展块冻结件出现 {bad} ⇒ 选样被结果污染"
assert E["rule"]["t_blind"] is True and E["no_extension_measurement_yet"] is True

# ── 2. 与主样本零重叠，且正好 8 个 ─────────────────────────────────────────
main_ids = {c["base_id"] for c in M["chosen"]}
ext_ids = {c["base_id"] for c in E["chosen"]}
assert len(ext_ids) == 8, f"扩展块应正好 8 个, 实得 {len(ext_ids)}"
assert not (ext_ids & main_ids), "★ 扩展 base 与主样本重叠 ⇒ 不是「新的一批」"

# ── 3. 同一个 frame、同一条规则 ────────────────────────────────────────────
assert E["rule"]["same_frame"] == "frame_reddit_20260819.json"
frame_ids = {r["base_id"] for r in H.harvest()}
assert ext_ids <= frame_ids, "★ 扩展 base 必须来自同一个冻结 frame, 不许另抓"

# ── 4. floor 降到 2 的理由必须是**算术约束**，不是「看了结果」──────────────
assert E["rule"]["floor"] == 2
assert 3 * len(H.STRATA) > 8, "主样本 floor=3 在 8 个名额下确实装不下 —— 这是算术, 可核"
assert "装不下" in E["rule"]["floor_note"]
assert sum(E["alloc"].values()) == 8

# ── 5. 可复现 ───────────────────────────────────────────────────────────────
again = H.select_extension(H.harvest(), n=8, exclude=main_ids,
                           seed=E["rule"]["seed"] - 1000, floor=2)
assert [c["base_id"] for c in again["chosen"]] == [c["base_id"] for c in E["chosen"]], \
    "★ 扩展块不可复现 ⇒ 可以一直重选到满意"

# ── 6. 触发条件必须是**事前定好的 coverage gate**，不是事后觉得不够 ─────────
assert "12/24" in E["trigger"] and "20" in E["trigger"]
assert "只允许扩一次" in E["preregistered"]

# ── 7. 三个长度层都有代表（扩展也不许只补好补的那层）──────────────────────
assert set(Counter(c["length_stratum"] for c in E["chosen"])) == {"S", "M", "L"}

print(f"test_cce_extension_block: OK (T-盲/零重叠/同frame/floor理由可核/可复现/"
      f"触发条件事前/三层齐全 {E['alloc']})")
