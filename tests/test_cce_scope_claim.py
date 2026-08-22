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
# ★ 2026-08-22 Phase 2 后升到 ESTIMATED_SCOPED(29 个 base 的分布, 不是一个点)
M = KS.SIGNIFICANCE_CONTRACT["measurement"]
assert M["status"] == "ESTIMATED_SCOPED" and M["status"] in KS.RESOLUTION_STATUS
# ★★ 升级了状态但 delta_resolution **仍必须是 None** —— 这是最容易破的一条:
#   拿本批 L0/L0b 的分位数给**同一批** A 臂当阈值 = calibration 与 validation 混用。
assert M["delta_resolution"] is None, \
    "★ 有了 profile 就填一个数 = 拿本批数据给本批发毕业证"
rp = M["resolution_profile"]
assert rp["n_base"] >= 24 and rp["instrument"] == "565470cf26c16d01"
assert rp["spread_ratio"] > 5, "跨度必须记下来 —— 它正是「不存在全局常量」的证据"
# ★ 长度不是驱动因素这条必须显式, 否则日后会有人按长度分层建阈值
assert rp["length_is_not_the_driver"] is True
lo, hi = min(rp["by_length_stratum"].values()), max(rp["by_length_stratum"].values())
assert hi / lo < 1.5, f"层间中位数比 {hi/lo:.2f} —— 若真差很多, 上面那条断言就该改"
# ★ scope 与已知缺口必须随 profile 走, 不许只报好消息
assert M["scope"]["across_domains"] == "NOT_ESTABLISHED"
assert any("coverage gate 未过" in g for g in M["known_gaps"])
assert any("弃权" in g for g in M["known_gaps"])

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
