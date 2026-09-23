#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 引文层**不得**自称语义验证过 —— 零调用反例钉死这件事。

★★★ 来历(2026-09-14, 网页版 GPT-6 Pro 裁定, 本仓零调用复现):
我建了一个 fail-closed 资格层, 要求证据是「原文里逐字可指的片段 + 对象 + 增量种类」,
并把通过者标成 `CONFIRMED_PRESENT`(已确认存在)。GPT 指出**那个名字超出了这层验过的东西**,
并给了一个零模型调用就能验的反例:

    原文: I have never owned or tried the Oticon, and I still want one.
    证书: Q 支引用 "owned or tried the Oticon"
          —— **片段真实存在、对象正确**, 但它在 "never ..." 的**否定辖域**内, 是 Q 的**反面**。

旧实现判 CONFIRMED_PRESENT。⇒ **逐字核对只验了出处与结构, 没有验「这段话是否支持该必要条件」。**

★ 这一步测的是**验证器**, 不是抽取器。它能以**零模型调用**消除
  「逐字检查已经把语义风险关住」这个误解。
★★ 它能得出的: **这个验证器允许形式合法、语义错误的证书通过。**
   它**不能**得出: 模型已经犯过这个错, 或发生率是多少。

★★★ 为什么**不加否定词正则**: 逐字核对验不了的至少有五类 ——
  否定辖域 / 归属 / 时态 / 引用层级 / 类型成员资格。
  补一类会留着其余四类, **却制造「已处理」的错觉** —— 那正是这次要消除的误解本身。
  正确的处置是**降格命名**: 这一层只能承诺「出处可核对, 语义未独立验证」。
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cce_label_qualification as Q  # noqa: E402

# ★ 反例逐字固定在这里 —— 它是本闸的全部依据, 不许被改软
NEG_TEXT = "I have never owned or tried the Oticon, and I still want one."
REQ = ["输出新信息增量", "谈论对象是自己已拥有或已经历"]


def _neg_cert():
    return [Q.EvidenceSpan("still want one", REQ[0], NEG_TEXT,
                           about="Oticon", increment_kind="结构化经验"),
            Q.EvidenceSpan("owned or tried the Oticon", REQ[1], NEG_TEXT, about="Oticon")]


def test_the_counterexample_spans_really_are_in_the_text():
    """★ 先自证反例本身成立: 两个片段都**真在原文里**, 且 Q 支确实落在否定辖域内。"""
    for e in _neg_cert():
        assert e.span in NEG_TEXT
    i = NEG_TEXT.index("owned or tried the Oticon")
    assert "never" in NEG_TEXT[:i], "★★★ 反例失效: Q 支引用不在 'never' 之后了"


def test_zero_call_the_verifier_lets_a_semantically_wrong_cert_through():
    """★★★ 核心: 这份**语义上是反面**的证书, 仍然拿到了「有引文」这一档。

    这不是缺陷报告, 是**范围声明** —— 它就是这一层能做到的上限。
    """
    q = Q.qualify("display", NEG_TEXT, evidence=_neg_cert(), required_conjuncts=REQ)
    assert q["state"] == Q.CITED_UNVERIFIED, (
        "★ 反例的状态变了(%s) —— 若它变成 CANDIDATE, 说明有人加了针对否定的补丁: "
        "**那会留着其余四类却制造已处理的错觉**, 请改回降格命名的方案" % q["state"])
    assert Q.has_cited_evidence(q) is True
    assert Q.is_citable_as_confirmed(q) is False, (
        "★★★★ 一份**语义上是反面**的证书拿到了「已确认存在」—— 这正是 2026-09-14 修掉的那个缺陷")


def test_nothing_can_reach_the_confirmed_tier_yet():
    """★★★ ④ 的识别器**尚未实现** ⇒ 现阶段 is_citable_as_confirmed 恒为 False。"""
    good = [Q.EvidenceSpan("Settled on the Oticon", REQ[0],
                           "Settled on the Oticon. Just holding off till payday to actually order it.",
                           about="Oticon", increment_kind="具体型号"),
            Q.EvidenceSpan("holding off till payday", REQ[1],
                           "Settled on the Oticon. Just holding off till payday to actually order it.",
                           about="Oticon")]
    T2 = "Settled on the Oticon. Just holding off till payday to actually order it."
    for prov in ("model", "human"):
        q = Q.qualify("display", T2, evidence=good, required_conjuncts=REQ, provenance=prov)
        assert q["state"] == Q.CITED_UNVERIFIED, (
            "★★★ provenance=%r 竟然拿到了 %s —— 模型与人工的引用**都只证明出处**, "
            "不得单独拥有确认权" % (prov, q["state"]))
        assert not Q.is_citable_as_confirmed(q)
    try:
        Q.qualify("display", T2, evidence=good, required_conjuncts=REQ, provenance="rule")
    except NotImplementedError:
        pass
    else:
        raise AssertionError(
            "★★★★ provenance='rule' 放行了 —— 那个**确定性识别器尚未实现**, "
            "这个参数不许被当成绕过确认边界的后门")


def test_the_five_unverified_classes_are_named_in_the_output():
    """★★ 五类没验的东西必须**逐条写在产物里** —— 只说「语义未验」太含糊, 读者会以为只差一点点。"""
    q = Q.qualify("display", NEG_TEXT, evidence=_neg_cert(), required_conjuncts=REQ)
    blob = json.dumps(q.get("★这一层没验什么"), ensure_ascii=False)
    for k in ("否定辖域", "归属", "时态", "引用层级", "类型成员资格"):
        assert k in blob, "★★★ 没验的那五类里缺: %s" % k
    assert "不加针对某一类的补丁" in blob, "★★ 「不补单类」这条自我约束被删了"


def test_no_negation_regex_was_sneaked_in():
    """★★★ 反向: 源码里不许出现针对否定词的特判 —— 那是补症状。"""
    src = (ROOT / "scripts/cce_label_qualification.py").read_text(encoding="utf-8")
    body = src.split('"""', 2)[-1]          # 跳过模块 docstring 里对反例的叙述
    for pat in ('"never"', "'never'", '"not "', "r\"\\bnever\\b\""):
        assert pat not in body, (
            "★★★ 代码里出现了针对否定词的特判(%s) —— 它只修一类, 留着归属/时态/引用层级/"
            "类型成员资格四类, 却制造「语义风险已关住」的错觉。**这正是本闸要挡的那个动作。**" % pat)


def test_the_scope_claim_is_exact():
    """★★★ 这一步能得出什么、不能得出什么, 必须写准 —— 多说一句就是越界。"""
    doc = (ROOT / "tests/test_cce_citation_layer_is_not_semantic.py").read_text(encoding="utf-8")
    assert "这个验证器允许形式合法、语义错误的证书通过" in doc
    assert "不能" in doc and "模型已经犯过这个错" in doc, (
        "★★★ 必须写明它**不**说明模型犯过这个错或发生率 —— 那需要另一个实验")


if __name__ == "__main__":
    test_the_counterexample_spans_really_are_in_the_text()
    test_zero_call_the_verifier_lets_a_semantically_wrong_cert_through()
    test_nothing_can_reach_the_confirmed_tier_yet()
    test_the_five_unverified_classes_are_named_in_the_output()
    test_no_negation_regex_was_sneaked_in()
    test_the_scope_claim_is_exact()
    print("test_cce_citation_layer_is_not_semantic: OK ("
          "★★★★**零调用反例**(webgpt 给形状, 本仓复现): 原文「I have **never** owned or tried the Oticon」, "
          "Q 支引用「owned or tried the Oticon」—— **片段真实存在、对象正确**, 却落在否定辖域内, 是 Q 的**反面**; "
          "**旧实现判 CONFIRMED_PRESENT** | "
          "★★★ 结论口径**精确**: 它证明「**这个验证器允许形式合法、语义错误的证书通过**」, "
          "**不**证明模型犯过这个错、更不给发生率 —— 这一步测的是**验证器**不是抽取器 | "
          "★★★★修法是**降格命名**不是打补丁: CONFIRMED_PRESENT → **CITED_SEMANTICS_UNVERIFIED**"
          "(出处可核对·语义未独立验证); ④ 只留给**确定性识别器**, 而它**尚未实现** ⇒ "
          "`is_citable_as_confirmed()` **现阶段恒为 False**; 模型与人工的引用**都只能到 ③′**, "
          "provenance='rule' 直接抛 NotImplementedError, 不许当后门 | "
          "★★★**明令不许加否定词正则**(反向验过): 逐字核对验不了的至少五类 —— "
          "否定辖域/归属/时态/引用层级/类型成员资格; 补一类会留着其余四类, "
          "**却制造「语义风险已关住」的错觉 —— 那正是这次要消除的误解本身**)")
