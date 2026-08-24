#!/usr/bin/env python3
"""Phase 2 的分端点状态与仪器定性 —— 守住「不许把话说回去」。

2026-08-22 外部评审把我拟的定性判为**仍然说过头**：
  我写「在处境层面是好比较器，在词面层面不是」，但 B1 已证明
  **处境与说话人状态被独立盲评认为没变**（124 次判断 P(DIFFERENT)=0.000），
  而 CCE 仍有 7/26 判分开 ⇒ 「在处境层面是好比较器」这半句站不住。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "tests" / "data" / "phase2"
sys.path.insert(0, str(ROOT / "scripts"))
import cce_ksep as KS  # noqa: E402

C = KS.INSTRUMENT_CHARACTERIZATION
S = json.loads((P / "phase2_status.json").read_text(encoding="utf-8"))

# ── 1. 定性不得退回「好比较器」这类说法 ────────────────────────────────────
blob = json.dumps(C, ensure_ascii=False)
assert "好比较器" not in blob, "★ 定性退回「好比较器」—— B1 已证否该说法"
assert C["semantic_form_invariance"] == "FAILED"
assert C["wording_method_effect"] == "DETECTED"
assert "cross-group DIF" in C["psychometric_frame"], \
    "★ 术语必须归位: 这是 alternate-form/wording-method invariance, 不是跨组 DIF"

# ── 2. 解释边界必须是**机器可读的禁止项**，不是散文 ────────────────────────
I = C["interpretation"]
assert I["separated_means"] == "CCE representation differs"
assert "subject situation differs" in I["does_not_mean"]
assert "psychological construct differs" in I["does_not_mean"]
assert I["T_does_not_mean"] == "语义差异的大小"   # 非单调直接打掉的那条
assert any("T 越大" in f for f in C["forbidden_uses"])
assert any("自由文本" in f for f in C["forbidden_uses"])

# ── 3. 度量不许被顺手换掉 ───────────────────────────────────────────────────
MB = KS.METRIC_BAKEOFF
assert MB["status"].startswith("RESEARCH_TRACK")
assert "sep_l1_v1" in MB["production_metric"]
assert MB["same_batch_selection_forbidden"] is True, \
    "★ 在 Phase 2 上选中度量再用 Phase 2 验证 = 同批选择+验证"
assert set(MB["must_recalibrate_if_changed"]) >= {"null", "type1", "resolution"}

# ── 4. 分端点状态：整轮不作废，但 ladder 终点必须判 INCONCLUSIVE ────────────
assert S["phase2"]["overall_status"] == "PARTIALLY_CONCLUSIVE"
assert S["joint_ladder"]["status"] == "INCONCLUSIVE_COVERAGE"
assert S["joint_ladder"]["complete_bases"] < S["joint_ladder"]["prereg_required"]
assert "不得" in S["joint_ladder"]["note"]
assert S["B1_invariance"]["status"] == "FAILED"
assert S["B2_invariance"]["status"] == "COMPATIBLE"
assert S["A3_sensitivity"]["status"] == "CONDITIONAL_ON_QUALIFICATION"

# ── 5. ★ 两条 headline 必须在**无假设最坏界**下也成立 ──────────────────────
lo, hi = S["B1_invariance"]["manski"]
assert lo > 0.05, f"★ B1 下界 {lo} 不高于不变性期望 ⇒ 结论就依赖缺失机制假设了"
lo3, _ = S["A3_sensitivity"]["manski"]
assert lo3 > 0.5, "★ A3 下界不够高 ⇒ 灵敏度结论会依赖缺失机制假设"
# 反向: 弃权不得被填成数值
assert "不是「测出来为零」" in S["T_distribution"]["forbidden"]

# ── 6. 资格闸扩展必须是**固定 n、只看一次** ────────────────────────────────
Q = S["qualification_extension"]
# ── 7. 扩展跑完后的结果与纪律 ──────────────────────────────────────────────
if "result" in Q:
    Rr = Q["result"]
    assert Rr["combined"]["n"] >= Q["total_target"], "★ 没跑够 n 就不许看结果"
    assert Rr["combined"]["upper95"] <= 0.05, "精度闸: 上界必须 <= U_max"
    # ★ 精度达标≠可以全量 ADOPT: 集中度旗标仍然拦着
    assert Rr["verdict"] == "ADOPT_WITH_RESTRICTIONS"
    assert "CONCENTRATION_FLAG" in Rr["why_not_full_adopt"]
    # ★★ 事后剔除只能当诊断: 看到结果再决定剔谁 = selection-on-outcome
    ph = Rr["post_hoc_diagnostic"]
    assert ph["excluding_flagged_base"]["verdict"] == "ADOPT"
    assert "selection-on-outcome" in ph["★caveat"], \
        "★ 事后诊断必须自带「不得当正式判决」的警告, 否则下游会把它读成结论"
    assert Rr["verdict"] != ph["excluding_flagged_base"]["verdict"], \
        "★ 正式判决不得等于事后剔除后的判决"
    # 前向修法必须是**新开前登记**, 不是回头改本轮 frame
    fwd = Rr["correct_forward_action"]
    assert "新开前登记" in fwd and "不许回头改" in fwd
    # 旗标 base 的成因要写明, 否则「受限」会被读成不明原因
    assert Rr["flagged_base_diagnosis"]["failure_types"]
assert Q["fixed_n"] is True and Q["additional_n"] == 55 and Q["total_target"] == 311
assert "anytime-valid" in Q["no_optional_stopping"], \
    "★ 用固定-n Clopper-Pearson 做滚动监控是错的, 这条必须写明"
# 算术自核: x=9 时 n=311 过闸而 310 不过
import math  # noqa: E402


def upper(x, n, alpha=0.05):
    def tail(p):
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(x + 1))
    lo_, hi_ = 0.0, 1.0
    for _ in range(200):
        m = (lo_ + hi_) / 2
        if tail(m) > alpha:
            lo_ = m
        else:
            hi_ = m
    return (lo_ + hi_) / 2


assert upper(9, 311) <= 0.05 < upper(9, 310), "★ 55 这个数必须能算出来, 不能只是抄来的"

# ── 8. 换验证者只能是**事后敏感性分析**, 不得重定 primary ──────────────────
if "verifier_sensitivity_analysis" in S:
    V = S["verifier_sensitivity_analysis"]
    assert V["status"] == "POST_HOC_SENSITIVITY_ONLY"
    assert "事后改判据" in V["★not_primary"], \
        "★ 看到结果后换验证者重定 primary = 事后改判据, 这条警告必须在件里"
    # 正式件必须仍是前登记的那个验证者
    assert "CROSS_FAMILY" in V["artifacts"]["preregistered_primary"]
    assert (P / "blind_verify_deepseek_posthoc.json").exists()
    bv = json.loads((P / "blind_verify_frozen.json").read_text(encoding="utf-8"))
    assert bv["mode"] == "CROSS_FAMILY_NO_THIRD_PARTY", \
        "★ 正式件被换成了事后跑的那个验证者 —— primary 已被污染"
    # ★★ 最关键: 判官换了, 但 B1 在两个判官下都干净 ⇒ headline 不是刺激污染造成的
    tj = V["same_stimuli_two_judges"]
    assert tj["deepseek_third_party"]["rate"] > tj["cross_family"]["rate"] * 5, \
        "两个判官的严格度差异是本节存在的前提"
    assert "B1" in V["finding_2"]["evidence"] and "0/31" in V["finding_2"]["evidence"]
    assert "不可直接互比" in V["finding_1"]["implication"]

print("test_cce_phase2_status: OK (定性不退回/解释禁止项/度量不换/分端点状态/"
      "无假设界下仍成立/扩展固定n且算术自核)")
