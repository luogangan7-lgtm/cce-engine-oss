#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产规则送达完整性闸的测试 —— 按 web GPT 第六轮给的四条机械条件逐条验。

★ 关键: 必需集合**从规范端生成**。这条不是风格问题 ——
  从构造器反推的话, **被遗漏的字段会一起从检查清单里消失**。
  实证: 换成规范端生成后, 立刻查出旧探针**结构上不可能查到**的两条
  (definition_of_knot / identity_criterion 两台仪器都没收到)。
"""
import json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cce_rule_delivery_completeness as M  # noqa: E402


def test_required_set_comes_from_the_spec_not_the_builder():
    """① 必需集合从规范端生成。反向: 若集合为空, 一切都会「通过」⇒ 必须判红。"""
    req = set(M.REQUIRED_PER_KNOT) | set(M.REQUIRED_GLOBAL)
    assert req, "★ 必需集合为空 —— all([]) 式空过, 正是 GPT 点名要防的"
    assert "hard_discriminant" in M.REQUIRED_PER_KNOT
    # 每条都要写**为什么必需**, 不许只列键名
    for d in (M.REQUIRED_PER_KNOT, M.REQUIRED_GLOBAL):
        for k, why in d.items():
            assert why and len(why) > 6, f"★ {k} 没写为什么必需"
    # ★ 反向: 构造器实际读取的键集合 **不等于** 必需集合 —— 这正是漏检发生的地方
    src = (ROOT / "scripts/cce_knot_classify.py").read_text(encoding="utf-8")
    assert "hard_discriminant" not in src, \
        "★ 若生产已开始读 hard_discriminant, 本测试的前提变了, 请重算而不是改断言"


def test_it_checks_the_final_outbound_request_not_an_imitation():
    """② 检查最终生产请求 —— 用真实构造器拼出的文本, 不是探针仿造的 prompt。"""
    prod = M.production_stage2_request()
    assert isinstance(prod, str) and len(prod) > 500
    assert "PROBE_TEXT_DO_NOT_SEND" in prod, "★ 探针文本没进请求 ⇒ 拼的不是真实请求路径"
    assert "收藏不买" in prod, "★ 行为例示不在最终请求里 —— 前提变了, 重算"


def test_content_completeness_distinguishes_missing_from_partial():
    """③ 逐条校验**完整值**: 完全没送达 与 送了一半(静默损失) 必须分开。"""
    r = M.build()
    partial = r["★★静默损失(送了一半)"]
    assert any(x["对象"] == "inertia" for x in partial), \
        "★ inertia.behavior 的截断没被判成 PARTIAL —— 内容完整性检查失效"
    hit = [x for x in partial if x["对象"] == "inertia"][0]
    assert "丢失" in hit["→生产"] and "开口即高质量个案" in hit["→生产"], \
        "★ 只说被截断不说**丢了什么** —— 无法判断影响面"
    assert hit["→验收闸"] == "FULL", "★ 两台仪器的损失不对称, 这个不对称本身要记下来"
    return hit


def test_the_spec_side_set_found_what_the_builder_side_method_could_not():
    """★★★ 规范端生成的价值证据: 查出旧方法结构上查不到的两条。"""
    r = M.build()
    miss_p = {(x["对象"], x["必需条款"]) for x in r["★★★未完整送达生产"]}
    miss_g = {(x["对象"], x["必需条款"]) for x in r["★★★未完整送达验收闸"]}
    for f in ("definition_of_knot", "identity_criterion"):
        assert ("(全局)", f) in miss_p and ("(全局)", f) in miss_g, \
            f"★ {f} 应两台都缺 —— 若已补上, 请重算而不是改断言"
    # 九结的 hard_discriminant 两台都缺
    n_hd_p = sum(1 for o, f in miss_p if f == "hard_discriminant")
    n_hd_g = sum(1 for o, f in miss_g if f == "hard_discriminant")
    assert n_hd_p == 9 and n_hd_g == 9, f"★ 期望九结全缺, 实得 生产{n_hd_p}/闸{n_hd_g}"
    return n_hd_p, len(miss_p), len(miss_g)


def test_two_instruments_are_not_folded_into_one():
    """★ GPT 点名: 不许把「生产路径未收到」写成「谁都收不到」。"""
    r = M.build()
    txt = r["★★★两台仪器要分开说_不许折叠成「谁都收不到」"]
    assert "压缩版" in txt and "生产连压缩版都没有" in txt
    assert "两台的缺口不一样大" in txt


def test_i_recorded_that_i_gave_gpt_a_false_premise():
    r = M.build()
    t = r["★我给 web GPT 的前提里有一处是错的"]
    assert "不成立" in t and "第三个" in t, \
        "★ 我在提问里说闸看完整合同含 hard_discriminant —— 实测不成立, 必须如实记"


def test_the_gate_claims_no_behavioral_authority():
    r = M.build()
    n = " ".join(r["★本闸不产生的东西"])
    assert "正确理解并遵守" in n and "必需集合已经完整" in n


if __name__ == "__main__":
    test_required_set_comes_from_the_spec_not_the_builder()
    test_it_checks_the_final_outbound_request_not_an_imitation()
    hit = test_content_completeness_distinguishes_missing_from_partial()
    n_hd, np_, ng = test_the_spec_side_set_found_what_the_builder_side_method_could_not()
    test_two_instruments_are_not_folded_into_one()
    test_i_recorded_that_i_gave_gpt_a_false_premise()
    test_the_gate_claims_no_behavioral_authority()
    print("test_cce_rule_delivery_completeness: OK ("
          "★★★必需集合**从规范端生成**(不从构造器反推, 否则被遗漏的字段会一起从清单消失) | "
          f"★★hard_discriminant **九结全缺, 生产与验收闸两台都缺** | "
          "★★★规范端方法立刻查出旧方法**结构上查不到**的两条: "
          "definition_of_knot 与 identity_criterion **两台都没收到**(「什么算一个结」的本体论定义) | "
          f"★静默损失 1 处且**不对称**: inertia.behavior 生产丢「{'开口即高质量个案'}」、闸 FULL | "
          f"★合计 生产缺 {np_} 项 / 闸缺 {ng} 项 | "
          "★我给 GPT 的前提有一处是假的(说闸看完整合同), 已如实记 | 4 条反向验证判红)")
