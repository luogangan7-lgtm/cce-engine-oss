#!/usr/bin/env python3
"""scope 边界必须是**数据结构**的一部分，不是文档里的一句话。

2026-08-19 外部评审的核心一句：
  「当前窄 corpus 不是缺陷，只要把 generalization boundary 当成数据结构的一部分；
    真正的缺陷会是用一个局部 profile，却给它起一个听起来像全局真理的名字。」

守三件事：
  1. 分辨率状态是**四级**，不是 CALIBRATED/NOT_CALIBRATED 两级 ——
     两级会逼人把局部 profile 叫成 CALIBRATED。
  2. global_resolution() 永远不给数，即使 scoped profile 已经有数。
  3. generator 是 facet：刺激溯源字段齐全，且状态叫 ONTOLOGY_BLINDED_SYNTHETIC 不叫「无偏」。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_ksep as KS  # noqa: E402

# ── 1. 四级状态且顺序不许乱 ─────────────────────────────────────────────────
assert KS.RESOLUTION_STATUS == ("POINT_OBSERVED", "ESTIMATED_SCOPED",
                                "VALIDATED_SCOPED", "CALIBRATED_BROAD")
# gen4 现状只有一个文本一个点
assert KS.SIGNIFICANCE_CONTRACT["measurement"]["status"] == "POINT_OBSERVED"
assert KS.SIGNIFICANCE_CONTRACT["measurement"]["delta_resolution"] is None, \
    "一个文本不构成 profile —— 拿到一个数就填是老毛病"

# ── 2. 全局分辨率的唯一出口：永远 NOT_CALIBRATED ────────────────────────────
g = KS.global_resolution()
assert g["status"] == "NOT_CALIBRATED" and g["delta_resolution"] is None
# ★ 反向：即便 scoped 侧已经有数，全局出口也不许被顶上
saved = KS.SIGNIFICANCE_CONTRACT["measurement"]["delta_resolution"]
KS.SIGNIFICANCE_CONTRACT["measurement"]["delta_resolution"] = 0.0061
try:
    assert KS.global_resolution()["delta_resolution"] is None, \
        "★ scoped median 顶替全局标定 —— 正是 0.06278 当初的死法(对的数放错作用域)"
finally:
    KS.SIGNIFICANCE_CONTRACT["measurement"]["delta_resolution"] = saved

# ── 3. scope 声明明文列出禁止项 ─────────────────────────────────────────────
sc = KS.SCOPE_CLAIM
assert "universal delta_resolution" in sc["forbidden"]
assert "global CCE resolution" in sc["forbidden"]
assert any("universe of generalization" in sc["rationale"] for _ in [0])
# 反向：禁止项里不许出现「其实是允许」的措辞
assert not set(sc["allowed"]) & set(sc["forbidden"])

# ── 4. generator 是 facet，不是透明工具 ────────────────────────────────────
assert set(KS.STIMULUS_PROVENANCE_FIELDS) >= {
    "base_text_id", "arm", "generator_family", "prompt_sha256", "blind_rule_check"}
assert KS.STIMULUS_STATUS == "ONTOLOGY_BLINDED_SYNTHETIC"
assert "UNBIASED" not in KS.STIMULUS_STATUS and "无偏" not in KS.STIMULUS_STATUS, \
    "★ 盲化 ≠ 无偏：生成家族与被测模型仍可能共享语言先验"

print("test_cce_scope_claim: OK (四级状态/全局出口不可顶替/scope 禁止项/generator facet)")
