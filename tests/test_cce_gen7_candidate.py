#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""候选代那一轮的闸 —— 钉住判决**及其边界**, 尤其是「PASS 主要来自判据窄」这条。"""
import json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = json.loads((ROOT / "tests/data/gen7_candidate_result.json").read_text(encoding="utf-8"))
P = json.loads((ROOT / "tests/data/gen7_candidate_prereg.json").read_text(encoding="utf-8"))
A = json.loads((ROOT / "tests/data/local_contract_assertions.json").read_text(encoding="utf-8"))


def test_prereg_and_assertions_were_frozen_before_any_call():
    assert P["★★★status"].startswith("**READY**")
    assert "一次调用都没发" in A["★★★冻结时点"], A["★★★冻结时点"]
    assert P["③★★★判据_显式留空"]["★已由 web GPT 第七轮裁定, 不再留空"] is True


def test_verdict_states_only_what_it_can():
    j = R["★★★冻结判据下的判决"]
    assert j["已确认违例"] == 0 and j["判决"].startswith("**PASS(本测试范围)**")
    assert "未观察到" in j["★★★只能这样说"]
    for forbidden in ("总体违例率为零", "九结都可靠", "可以替换生产"):
        assert forbidden in j["★★★不得据此说"], f"★ 缺少禁语: {forbidden}"


def test_the_pass_is_immediately_qualified_as_a_narrow_criterion_artifact():
    """★★★ 最重要的一条: PASS 后面必须**紧跟**它主要来自判据窄这句, 不许单独摆 PASS。"""
    k = R["★★★★但这个 PASS 主要是判据覆盖面窄的产物_必须先说这句"]
    assert "全部" in k["★我的断言表只禁了一个标签"] and "没有检查新标签是否满足它自己的判别式" in k["★我的断言表只禁了一个标签"]
    g = k["★★★候选产生了一个可由合同推出、而我没列的问题"]
    assert len(g["适用" if "适用" in g else "★这四条的文本"]) == 4 or len(g["★这四条的文本"]) == 4
    assert "尚未拥有或经历该产品" in g["★★★核实"]
    assert "我的判据没查它" in g["★★★所以"]
    return g


def test_the_new_assertion_does_not_retroactively_change_the_verdict():
    """★ 事后枚举出的断言**不得回溯改判** —— 无论方向。"""
    k = R["★★★★但这个 PASS 主要是判据覆盖面窄的产物_必须先说这句"]
    assert "不得" in k["★★这条**不改变**本轮判决"] and "无论方向" in k["★★这条**不改变**本轮判决"]
    for a in R["★★下一轮才可用的新断言(现在冻结, **不回溯适用**)"]:
        if "★状态" in a:
            assert "仅对下一轮生效" in a["★状态"]


def test_improvement_is_not_claimed_over_noise():
    """★ 「1 → 0」不得写成缺陷已修复 —— 已知同代逐题翻转率 3/22。"""
    d = R["★逐题变化(诊断用, **不是效应归因**)"]
    assert d["★旧代在已裁定断言上的违例数"] == 1
    assert "3/22" in d["★★而且旧代的逐题读数**本身不稳定**"]
    assert "不足以支持" in d["★★所以「1 → 0」这个改善**落在噪声量级内**"]
    assert "不能自动写成联合改动的因果效应" in d["★★★不得写成因果效应(GPT 第七轮原话)"]


def test_the_original_disputed_item_is_reported_as_unchanged():
    """★★★ 引发一切的那道题仍是 suspend —— 不许被 PASS 盖过去。"""
    o = R["★★★那个引发一切的题_没有变"]["C_仅收藏_0"]
    assert o["旧"] == "suspend" and o["候选"] == "suspend"
    assert "一点没动" in R["★★★那个引发一切的题_没有变"]["★"]


def test_fourth_instance_of_the_same_gate_failure_is_named():
    k = R["★★★★但这个 PASS 主要是判据覆盖面窄的产物_必须先说这句"]
    s = k["★★★这是同型错误的第四次"]
    assert s.count("①") and s.count("②") and s.count("③") and s.count("④"), "★ 四次要逐条列出, 不能只说「又犯了」"


def test_budget_was_respected_and_only_one_round():
    b = R["★真实计费请求"]
    assert b["实际"] <= b["上限"], "★ 撞上限未停"
    assert "一轮" in b["轮数"] and "旧代未重跑" in b["轮数"]


def test_headline_sentence_denies_the_three_things():
    s = R["★★★本轮实际证明了什么_一句话"]
    for must in ("没有**证明缺陷已修复", "没有**证明候选优于现行", "没有**证明可以替换生产"):
        assert must in s, f"★ 一句话结论里缺: {must}"


if __name__ == "__main__":
    test_prereg_and_assertions_were_frozen_before_any_call()
    test_verdict_states_only_what_it_can()
    g = test_the_pass_is_immediately_qualified_as_a_narrow_criterion_artifact()
    test_the_new_assertion_does_not_retroactively_change_the_verdict()
    test_improvement_is_not_claimed_over_noise()
    test_the_original_disputed_item_is_reported_as_unchanged()
    test_fourth_instance_of_the_same_gate_failure_is_named()
    test_budget_was_respected_and_only_one_round()
    test_headline_sentence_denies_the_three_things()
    print("test_cce_gen7_candidate: OK ("
          "★候选代一轮 176 次请求(上限 220)· 12 条**事先裁定**的禁判断言**零违例** ⇒ PASS(本测试范围) | "
          "★★★但这个 PASS 主要是**判据覆盖面窄**的产物: 我的断言**全部**只禁 suspend, "
          "**没查新标签是否满足它自己的判别式** —— 候选把 4 条移到 display, "
          "而这 4 条说话人**尚未拥有该产品**, display 的必要条件不成立 | "
          "★该断言是**看到结果后**才枚举的 ⇒ **不回溯改判**, 只对下一轮生效 | "
          "★「旧代 1 违例 → 候选 0」**落在噪声内**(同代逐题翻转率 3/22, 且只跑一轮) | "
          "★★★引发一切的 C_仅收藏_0 **仍是 suspend, 一点没动** | "
          "★同型闸错误今天第 **4** 次, 已逐条列出)")
