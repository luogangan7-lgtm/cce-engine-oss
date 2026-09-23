#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""候选 stage2 构造器的闸。

★ 它**不替换生产** —— 有一条断言专门钉住这一点: 生产路径不得引用本模块。
"""
import json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cce_stage2_candidate as V          # noqa: E402
import cce_rule_delivery_completeness as M  # noqa: E402

TAXO = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
S1 = {"tops": {}, "appraisal": {}}


def test_candidate_is_not_wired_into_production():
    """★★★ 最重要的一条: 候选就是候选, 生产必须一字未动。"""
    prod = (ROOT / "scripts/cce_knot_classify.py").read_text(encoding="utf-8")
    assert "cce_stage2_candidate" not in prod, \
        "★ 生产脚本引用了候选构造器 —— 那就不是候选了, 是已经换代"
    import cce_knot_classify as C
    cur = C._build_stage2_prompt(TAXO, "X", S1)
    assert "hard_discriminant" not in cur and "★判别式" not in cur, \
        "★ 生产 prompt 里出现了判别式 —— 生产已被改动, 与「不替换生产」矛盾"


def test_candidate_closes_the_delivery_gap():
    p = V.build(TAXO, "PROBE", S1)
    bad = []
    for k in TAXO["knots"]:
        for f in M.REQUIRED_PER_KNOT:
            if M._delivered(k[f], p) != "FULL":
                bad.append((k["key"], f))
    for f in M.REQUIRED_GLOBAL:
        if M._delivered(TAXO[f], p) != "FULL":
            bad.append(("(全局)", f))
    assert not bad, f"★ 候选仍未完整送达: {bad}"
    return 9 * len(M.REQUIRED_PER_KNOT) + len(M.REQUIRED_GLOBAL)


def test_reverse_turning_a_component_off_reopens_the_gap():
    """反向: 关掉组件必须让缺口重新出现, 否则组件开关是摆设。"""
    p = V.build(TAXO, "PROBE", S1, ("ontology", "negative", "full_behavior"))
    n = sum(1 for k in TAXO["knots"] if M._delivered(k["hard_discriminant"], p) != "FULL")
    assert n == 9, f"★ 关掉 discriminant 后仍有 {9-n} 个结的判别式在 —— 开关无效"


def test_budget_blocks_and_never_trims():
    """★ 超预算**显式阻断**, 不得静默裁尾 —— 裁尾正是本次要修的缺陷形态。"""
    try:
        V.build(TAXO, "PROBE", S1, budget=100)
    except V.PromptBudgetExceeded as e:
        assert "不裁尾" in str(e)
        return
    raise AssertionError("★ 超预算没有阻断 —— 闸失效")


def test_behavior_is_labelled_as_illustration_not_criterion():
    """★ 只是把 behavior 送全不够 —— 必须**当场标注它是例示**, 且判别式优先。"""
    p = V.build(TAXO, "PROBE", S1)
    assert "仅例示, 不是判定条件" in p
    assert "判别式不成立 ⇒ **不得**判该结" in p
    assert "**不能**单独支撑该结" in p
    # ★ 合取项那条来自 GPT 第六轮的更正: 同一子串可支持两项, 但每项都要真被支持
    assert "每一项都必须真的被支持" in p


def test_decision_tree_is_off_by_default_with_a_stated_cost():
    """★★★ 决策树默认关闭, 且**理由必须写出来** —— 它会让闸对生产的判决部分变成同义反复。"""
    p = V.build(TAXO, "PROBE", S1)
    tree0 = TAXO["annotation_protocol"]["decision_tree_prompt"][0]
    assert tree0 not in p, "★ 决策树默认进了候选 —— 独立性代价被静默吞掉"
    assert "同义反复" in V.INDEPENDENCE_COST and "默认关闭" in V.INDEPENDENCE_COST
    # 开了就必须真的进
    p2 = V.build(TAXO, "PROBE", S1, ("ontology", "discriminant", "negative", "full_behavior", "decision_tree"))
    assert tree0 in p2, "★ 开了决策树却没进 prompt"


def test_unknown_component_is_rejected():
    """★ 组件表是规范端的, 不许临时加一个名字就往里塞东西。"""
    try:
        V.build(TAXO, "PROBE", S1, ("ontology", "临时加的"))
    except ValueError as e:
        assert "不许临时加" in str(e)
        return
    raise AssertionError("★ 未知组件被接受 —— 规范端约束失效")


def test_the_changelog_false_claim_is_recorded():
    """★ 冻结配置的 changelog 把闸的 prompt 写成了「生产 prompt」, 已 git 核实为不实。
    它直接影响「补送算实现纠错还是判据修订」, 必须留档。"""
    d = json.loads((ROOT / "tests/data/changelog_false_delivery_claim.json").read_text(encoding="utf-8"))
    assert "返回空" in d["★★★证据"]["git -S 全历史搜索"]
    assert "没有碰 scripts/cce_knot_classify.py" in d["★★★证据"]["那次提交改了什么"]
    assert len(d["★★这是同族第三例"]) == 3
    imp = d["★★★它对「补送算实现纠错还是判据修订」的影响"]
    assert "不能" in imp["★★实际是假的"]
    key = [k for k in imp if "不自动等于判据修订" in k]
    assert key, "★ 不许从「changelog 是假的」直接跳到「所以是判据修订」—— 留档里必须有这条保留"
    assert "web GPT 第七轮" in imp[key[0]], "★ 该结论仍在外部裁定中, 必须标明未决"
    return d


if __name__ == "__main__":
    test_candidate_is_not_wired_into_production()
    n = test_candidate_closes_the_delivery_gap()
    test_reverse_turning_a_component_off_reopens_the_gap()
    test_budget_blocks_and_never_trims()
    test_behavior_is_labelled_as_illustration_not_criterion()
    test_decision_tree_is_off_by_default_with_a_stated_cost()
    test_unknown_component_is_rejected()
    test_the_changelog_false_claim_is_recorded()
    print("test_cce_stage2_candidate: OK ("
          f"★★★候选**不替换生产**(有断言钉住: 生产脚本不得引用本模块, 且生产 prompt 里不得出现判别式) | "
          f"★候选把必需集合送达补到 {n}/{n} FULL | "
          "★behavior 送全**并当场标注是例示**+判别式优先+合取项逐项独立满足 | "
          "★★决策树**默认关闭**: 它是验收闸 G 的判定顺序, 送进 P 会让「G 与 P 一致」部分变成**同义反复** —— "
          "这个代价归 owner 权衡, 不由我打包 | "
          "★超预算**显式阻断不裁尾** | "
          "★冻结 changelog 的「生产 prompt」是**不实陈述**(git 全历史核实), 同族第三例 | "
          "3 条反向验证判红)")
