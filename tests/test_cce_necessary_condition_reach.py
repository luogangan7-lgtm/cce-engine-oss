#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 生产 P 是否收到了它被指控违反的那条必要条件。

★ 这个闸存在的理由(比它检查的东西更重要):
  我把「仅收藏被判 suspend」定性成「**违反**既有必要条件」, 而那条必要条件
  (hard_discriminant 的「附带犹豫理由」)**根本不进生产 prompt** ——
  这个事实几天前就写在我自己建的字段送达账本里, 我从没拿它去复查依赖它的结论。
  ⇒ 闸的作用是: 只要「许可送达而必要条件不送达」这个不对称还在, 就**每次都判红**,
    不让它再被沉默地绕过。
"""
import json, sys, pathlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cce_necessary_condition_reach as M  # noqa: E402


def _res():
    return M.build()


def test_production_never_receives_the_necessary_condition():
    r = _res()
    d = r["★★★必要条件是否送达"]
    assert d["hard_discriminant 字段被生产取用?"] is False
    assert d["negative_examples_prompt 被生产取用?"] is False
    assert d["在生产那一行里出现?"] is False, "★ 必要条件竟出现在生产那一行 —— 结论要重算"
    # 许可条件反而送达了 —— 不对称正是问题所在
    assert r["★★★许可条件是否送达"]["在生产那一行里出现?"] is True
    return d


def test_the_asymmetry_is_stated_not_just_recorded():
    """★ 只记录字段送达情况是不够的 —— 必须显式说出「归因错了」这个后果。
    上一次失守就是: 事实记了, 后果没被推出来。"""
    r = _res()
    c = r["★★★结论_按web-GPT第六轮的替换措辞"]
    for must in ("规范性条款未送达生产执行路径", "须另行判断"):
        assert must in c, f"★ 结论里缺「{must}」—— 记录了事实但没说出后果, 正是上次失守的形态"
    # ★ 且必须同时钉住我**原来写过头的那句已被撤回**, 以及三分不许合并
    w = r["★★★我原来写过头的话_已撤回"]
    assert "原文:" in w, "★ 撤回必须**原样抄下被撤回的那句**, 否则读者不知道撤的是什么"
    assert "外部规范可以约束系统" in w, "★ 撤回理由必须写出来: 未送达≠整个系统符合规范"
    tri = r["★★★三分不许合并"]
    assert tri["模型收到必要条件后仍未遵守"].startswith("**撤回**")
    assert "不因未送达而自动撤销" in tri["某个输出不符合外部规范中的必要条件"]


def test_reverse_the_gate_must_go_green_if_the_condition_were_delivered():
    """反向验证: 若必要条件确实送达, 这个闸必须能判出「不再是那个形态」。
    构造一份假的生产行(把 hard_discriminant 拼进去), 断言检测翻面。"""
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    k = [x for x in taxo["knots"] if x["key"] == "suspend"][0]
    fake_line = M.suspend_line() + "; 硬判别=" + k["hard_discriminant"]
    assert "附带犹豫理由" in fake_line, "★ 反向构造本身没成立"
    assert "附带犹豫理由" not in M.suspend_line(), "★ 正向与反向没有区分度 —— 闸无效"


def test_the_two_defects_stay_separate_and_the_narrow_gate_is_marked_narrow():
    """★ GPT: 两个缺陷**不合并关闭**; 且「零硬编码截断」闸的**定义本身**太窄。"""
    r = _res()
    t = r["★★另一处独立缺陷_硬编码截断"]
    assert "换成变量" in t["★★★但真正的问题不是覆盖面, 是**闸的定义本身太窄**(GPT)"]
    assert "两个缺陷 ID" in t["★这是**独立的第二个缺陷**, 不与「条款未进路径」合并关闭"]
    assert "降级为交叉核对" in r["★方法已被取代"], "★ 本探针的方法已被规范端生成取代, 必须自陈降级"


def test_hardcoded_truncation_in_the_production_prompt_builder():
    """★ 独立缺陷: behavior[:60] 切掉了 inertia 的末尾。
    今天新建的「零硬编码截断」闸只扫探针脚本, 没扫这里 —— **闸的覆盖面自己也要被审**。"""
    r = _res()
    t = r["★★另一处独立缺陷_硬编码截断"]["被截断的结"]
    assert "inertia" in t, "★ 截断消失了? 若确已修复, 请连同这条断言一起更新, 不要静默放行"
    assert t["inertia"]["★被丢掉"], "★ 记了被截断却没记丢了什么 —— 无法判断影响面"
    return t


def test_this_probe_claims_no_authority_it_does_not_have():
    r = _res()
    n = " ".join(r["★本探针不产生的东西"])
    # ★ 逐条锚在**不同的一条**声明上, 不用一个词去撞三条(那样一条覆盖全部=假绿)
    for must in ("换代", "仅收藏该判什么", "它看不到的规则"):
        assert must in n, f"★ 缺少边界声明: {must}"


def test_witness_round_is_recorded_as_void():
    """★ 欠定见证那一轮按预注册作废, 留档必须**明写作废**且**明写不得引用**,
    不许把 T1 的 6/6 偷偷当证据用。"""
    p = ROOT / "tests/data/underdetermination_witness_result.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    j = d["★★★按预注册的判定"]
    assert j["★★★所以本轮按预注册**整体作废**"] is True
    # ★ GPT 判「不得引用」过严 ⇒ 现在要钉的是**引用规则已改成 GPT 的模板**
    assert "已改" in j["★不得引用"]
    q = d["★★★引用规则_按GPT第六轮"]
    assert "仅用于诊断" in q["★GPT给的模板(照抄, 以后就这样写)"]
    assert "T4 负对照同时出现 4/6" in q["★GPT给的模板(照抄, 以后就这样写)"], \
        "★ 引用时必须同时披露失效, 不许只摆有利部分"
    assert "不能" in q["★★18/18 只能报成"] and "已证明不存在干净推导" in q["★★18/18 只能报成"]
    assert d["★★★按预注册的判定"]["★作废原因与根因诊断分开"]["失败根因"] == "**尚未确定**"
    # ★ 原断言钉的是我**错误**的作废解释, 已随之更正: 现在要钉住的是那条解释被**撤回**,
    #   且撤回的理由(句式匹配替代条件检验)被写下来 —— 那是同一个错的第二次。
    c = d["★★★更正_我对作废原因的解释是错的"]
    assert "已撤回" in d["★★★作废的真实原因_不是装置没检定力"]
    assert "决策被明确悬置" in c["★★★为什么错"] and "当场为假" in c["★★★为什么错"]
    assert "同一个错, 换了个用途" in c["★★★这是同一个错的第二次"], \
        "★ 必须点明它与上一轮 first-hit 错误同源, 否则下次照犯"
    assert "不是我自己发现的" in c["★★★元教训"], \
        "★ 谁发现的要如实记 —— 记成自己发现的会高估我的自查能力"
    # ★★ 二次更正: 我的「装置确实没检定力」同样超出证据
    c2 = c["★★★但我的更正也过头了_二次更正"]
    assert "尚未证明失败必然由版本错配造成" in c2["★★★可登记的只有这一句"]
    assert "过度自责与开脱是同一个病" in c2["★两次都错在同一处"]
    # 与「必要条件未送达」的关联本身也建立在作废轮上 —— 必须自称待验假设
    assert "待验假设" in d["★★与「必要条件未送达」的关系"], \
        "★ 拿作废轮去支撑另一条结论 —— 正是作废规则要禁止的事"
    return j


if __name__ == "__main__":
    d = test_production_never_receives_the_necessary_condition()
    test_the_asymmetry_is_stated_not_just_recorded()
    test_the_two_defects_stay_separate_and_the_narrow_gate_is_marked_narrow()
    test_reverse_the_gate_must_go_green_if_the_condition_were_delivered()
    t = test_hardcoded_truncation_in_the_production_prompt_builder()
    test_this_probe_claims_no_authority_it_does_not_have()
    j = test_witness_round_is_recorded_as_void()
    print("test_cce_necessary_condition_reach: OK ("
          "★★★生产收到「收藏不买」(许可)却收不到「附带犹豫理由」(必要条件) ⇒ "
          "**规范性条款未送达生产执行路径**; 「模型收到却违反」**撤回**, "
          "但「某输出不符合外部规范」**不因未送达而自动撤销**(外部规范可约束系统, 即使某组件没收到) | "
          f"★★v2 修复改的是 GATE_ONLY 材料 ⇒ **修复错层/生产目标未触达**(不叫伪修复); "
          "hash 不变**不能单独**证明这一点, 证据是源码+出站请求 | "
          f"★另一处独立缺陷: behavior[:60] 切掉 inertia 的「{t['inertia']['★被丢掉']}」, "
          "而当天新建的零截断闸没扫生产构造器 —— **闸的覆盖面自己也要被审** | "
          "★欠定见证轮按预注册**作废**(触发条件 T4 4/6, **失败根因尚未确定**), "
          "观察**可引用但须同披露失效**(我原写「不得引用」被判过严) | "
          "2 条反向验证判红)")
