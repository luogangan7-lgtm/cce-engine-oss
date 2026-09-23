#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 合同层标签资格(P3 的第 ③ 档)必须 fail-closed, 且**不许进 prompt**。

★★★ 本闸最要紧的两条:
① **默认必须是不升格。** 一个「缺证据时默认给确认」的实现, 比没有这一层更糟 ——
   它会让「已确认存在」这个词失去含义, 而下游读到的仍是那个词。
② **这一层不许进 prompt。** 2026-09-13 gen9 双臂重测实测: 把合同文本塞进生产 s2 prompt
   会让 display 由 1/80 涨到 40/80 且**倒挂**(A 臂 56% > B 臂 41%)。
   ⇒ 用 prompt 去教模型守合同, 是**已被测出会让读数更偏**的路。
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cce_label_qualification as Q  # noqa: E402

TEXT = "Settled on the Oticon. Just holding off till payday to actually order it."
REQ = ["输出新信息增量", "谈论对象是自己已拥有或已经历"]


def test_default_is_not_confirmed():
    """★★★ 没证据 ⇒ 必须是候选。这条是整层的地基。"""
    for ev in (None, []):
        q = Q.qualify("display", TEXT, evidence=ev, required_conjuncts=REQ)
        assert q["state"] == Q.CANDIDATE, "★★★ 无证据却给了确认 —— 这一层就白建了"
        assert not Q.is_citable_as_confirmed(q)
        assert "没有证据" in q["why"], "★ 必须说清这是「没有证据」不是「证据弱」"


def test_a_span_must_be_verbatim_in_the_text():
    """★★★ 附件 B 的可操作化: 指不出原文片段的推断 = 没有证据。"""
    ok = Q.EvidenceSpan("Settled on the Oticon", REQ[0], TEXT)
    assert ok.span in TEXT
    for bad in ("I already own it", "Settled on the Phonak", " ", ""):
        try:
            Q.EvidenceSpan(bad, REQ[0], TEXT)
        except ValueError:
            continue
        raise AssertionError("★★★ 编造的片段 %r 被当成了证据" % bad)
    # 片段必须指向**哪个**条款
    try:
        Q.EvidenceSpan("Settled on the Oticon", "", TEXT)
    except ValueError:
        pass
    else:
        raise AssertionError("★★ 不写支撑哪个条款也放行 —— 证据必须指向条款")


def test_every_conjunct_needs_its_own_span():
    """★★★ 合取项缺一即不成立, 不许用其它条款的证据顶替。"""
    # ★ 2026-09-14 P2 上线后补齐 about/increment_kind —— 本条要测的是**合取项覆盖**,
    #   不该因为缺了 P2 的字段而红在别的地方(那样就测不到它本来要测的东西了)。
    one = [Q.EvidenceSpan("Settled on the Oticon", REQ[0], TEXT,
                          about="Oticon", increment_kind="具体型号")]
    q = Q.qualify("display", TEXT, evidence=one, required_conjuncts=REQ)
    assert q["state"] == Q.CANDIDATE, "★★★ 只支撑了一个合取项就升格了"
    assert REQ[1] in q["why"], "★ 必须点名**哪个**合取项没被支撑"
    # 两条都齐才升格
    two = one + [Q.EvidenceSpan("holding off till payday", REQ[1], TEXT, about="Oticon")]
    q2 = Q.qualify("display", TEXT, evidence=two, required_conjuncts=REQ)
    # ★ 2026-09-14 降格后: 齐了只到 ③′(出处可核·语义未验), **不是**「已确认存在」。
    assert q2["state"] == Q.CITED_UNVERIFIED and Q.has_cited_evidence(q2)
    assert not Q.is_citable_as_confirmed(q2), (
        "★★★★ 一份**语义未被独立验证**的证书拿到了「已确认存在」—— "
        "那正是零调用反例修掉的缺陷(见 test_cce_citation_layer_is_not_semantic)")
    return q2


def test_missing_conjunct_list_also_fails_closed():
    """★★ 连「合同要求哪些必要条件」都没给 ⇒ 同样不许升格。

    缺清单时默认升格, 等于让「忘了写清单」变成一条放行通道。
    """
    ev = [Q.EvidenceSpan("Settled on the Oticon", REQ[0], TEXT)]
    q = Q.qualify("display", TEXT, evidence=ev, required_conjuncts=None)
    assert q["state"] == Q.CANDIDATE
    assert "默认不升格" in q["why"]


def test_it_refuses_bare_strings_as_evidence():
    """★ 裸字符串不算证据 —— 那会绕过「片段必须在原文里」的构造期检查。"""
    try:
        Q.qualify("display", TEXT, evidence=["Settled on the Oticon"], required_conjuncts=REQ)
    except TypeError:
        return
    raise AssertionError("★★★ 裸字符串被当成了证据 —— 构造期的片段核对被绕过了")


def test_this_layer_never_reaches_the_prompt():
    """★★★ 本层**一个字都不许进 prompt** —— 那条路已被 gen9 测出会让读数更偏。"""
    src = (ROOT / "scripts" / "cce_label_qualification.py").read_text(encoding="utf-8")
    for forbidden in ("_build_stage2_prompt", "DISSOLVE_PROMPT", "PROMPT.format", "call_model", "call_parse"):
        assert forbidden not in src, (
            "★★★ 本层碰到了 prompt 路径(%s) —— gen9 实测: 把合同文本塞进生产 prompt 会让 "
            "display 由 1/80 涨到 40/80 且倒挂。这一层的全部价值就在于**不走那条路**" % forbidden)
    # 反向: 产物里必须带着这条理由, 免得下一个人把它搬进 prompt
    q = Q.qualify("display", TEXT)
    blob = json.dumps(q, ensure_ascii=False)
    assert "不**进 prompt" in blob or "不**进 prompt**" in blob or "进 prompt" in blob
    assert "40/80" in blob and "倒挂" in blob, "★★ gen9 那条实测证据必须随产物走"


def test_it_does_not_pretend_to_replace_the_instrument_gate():
    """★★ 仪器层与合同层是**两道**, 不许互相顶替。"""
    q = Q.qualify("display", TEXT)
    blob = json.dumps(q["★它不说明什么"], ensure_ascii=False)
    assert "knot_readout_usable" in blob, "★★ 没写明还要过仪器层那道"
    assert "不**说明 top-1 判得对" in blob or "判得对或判错" in blob


# ══ P2: 同一对象绑定 ═══════════════════════════════════════════════════
def _ev(span, supports, about=None, kind=None):
    return Q.EvidenceSpan(span, supports, TEXT, about=about, increment_kind=kind)


def test_two_conjuncts_on_different_objects_must_not_confirm():
    """★★★ P2 的核心: `∃x[P(x) ∧ Q(x)]` 与 `(∃x P(x)) ∧ (∃y Q(y))` **不等价**。

    「说了个型号」＋「用过别的东西」不能凑成一个 display。
    """
    ev = [_ev("Settled on the Oticon", REQ[0], "Oticon", "具体型号"),
          _ev("holding off till payday", REQ[1], "别的东西")]
    q = Q.qualify("display", TEXT, evidence=ev, required_conjuncts=REQ)
    assert q["state"] == Q.CANDIDATE, "★★★ 两支落在不同对象上却升格了 —— P2 白写了"
    assert "不等价" in q["why"] and "别的东西" in q["why"], "★ 必须点名是哪两个对象"


def test_an_unnamed_object_fails_closed():
    """★★ 指不出对象 ⇒ 无从判断两支是否同一个 x ⇒ 不升格。"""
    ev = [_ev("Settled on the Oticon", REQ[0], None, "具体型号"),
          _ev("holding off till payday", REQ[1], "Oticon")]
    q = Q.qualify("display", TEXT, evidence=ev, required_conjuncts=REQ)
    assert q["state"] == Q.CANDIDATE and "没有指名它是关于哪个对象的" in q["why"]


def test_no_alias_merging_and_it_says_so():
    """★★★ 不做别名归并, 且**把这件事写在产物里**。

    归并需要读文本: 不归并会漏判, 乱归并会误判 ⇒ fail-closed 选漏判。
    ★ 但必须说出来 —— 一个沉默的保守策略会被读成「它判过了」。
    """
    ev = [_ev("Settled on the Oticon", REQ[0], "the Oticon", "具体型号"),
          _ev("holding off till payday", REQ[1], "Oticon")]
    q = Q.qualify("display", TEXT, evidence=ev, required_conjuncts=REQ)
    assert q["state"] == Q.CANDIDATE, "★ 把两个不同字符串当成同一个对象了 —— 那是乱归并"
    assert "不做**别名归并" in q["why"] or "别名归并" in q["why"]
    assert "fail-closed 选漏判" in q["why"], "★★ 保守策略必须写出来, 不许沉默"


def test_increment_must_name_a_contract_enumerated_kind():
    """★★★ 库内教训: **不能把「对象相关的事实」当作「关于对象的信息增量」**。

    ⇒ 增量支必须指名它属于**合同枚举过**的哪一种; 合同没枚举的种类当场拒。
    """
    ev = [_ev("Settled on the Oticon", REQ[0], "Oticon"),          # 没指名种类
          _ev("holding off till payday", REQ[1], "Oticon")]
    q = Q.qualify("display", TEXT, evidence=ev, required_conjuncts=REQ)
    assert q["state"] == Q.CANDIDATE and "没有指名它属于合同枚举的哪一种" in q["why"]
    try:
        _ev("Settled on the Oticon", REQ[0], "Oticon", "我自己发明的种类")
    except ValueError:
        pass
    else:
        raise AssertionError("★★★ 合同没枚举过的增量种类被接受了")


def test_the_enumerated_kinds_match_the_frozen_discriminant():
    """★★★ 那张枚举表必须与**判别式原文现算一致** —— 不许我抄错或抄旧。"""
    import re
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    d = [k for k in taxo["knots"] if k["key"] == "display"][0]["hard_discriminant"]
    m = re.search(r"新信息增量\*\*\((.*?)\)", d)
    assert m, "★ 判别式里找不到增量种类的枚举 —— 原文结构变了, 本模块的枚举表要重核"
    live = tuple(m.group(1).split("/"))
    assert tuple(Q.INCREMENT_KINDS) == live, (
        "★★★ 模块里的枚举 %r 与判别式原文现算 %r 不符 —— 合同改了它必须跟着改"
        % (list(Q.INCREMENT_KINDS), list(live)))
    return live


def test_restating_the_identifier_is_not_an_increment():
    """★ 附件 A: 复述型号名/品类名**不产生增量**。"""
    ev = [_ev("Oticon", REQ[0], "Oticon", "具体型号"),
          _ev("holding off till payday", REQ[1], "Oticon")]
    q = Q.qualify("display", TEXT, evidence=ev, required_conjuncts=REQ)
    assert q["state"] == Q.CANDIDATE and "去掉对象标识之后没剩下内容" in q["why"]


def test_same_object_with_everything_named_does_confirm():
    """★ 灵敏度: 上面全是拒。齐了必须能升格, 否则这层是恒拒的摆设。"""
    ev = [_ev("Settled on the Oticon", REQ[0], "Oticon", "具体型号"),
          _ev("holding off till payday", REQ[1], "Oticon")]
    q = Q.qualify("display", TEXT, evidence=ev, required_conjuncts=REQ)
    assert q["state"] == Q.CITED_UNVERIFIED, "★★★ 条件全齐仍拿不到 ③′ —— 这层是恒拒的摆设"
    assert not Q.is_citable_as_confirmed(q), "★★★ ③′ 不得等同于「已确认存在」"
    assert "落在同一个对象" in q["why"]
    return q


def test_turning_off_the_object_check_must_be_loud():
    """★★ 关掉 P2 要显式传参, **且产物里必须写明本次没查**。"""
    ev = [_ev("Settled on the Oticon", REQ[0], None, "具体型号"),
          _ev("holding off till payday", REQ[1], None)]
    q = Q.qualify("display", TEXT, evidence=ev, required_conjuncts=REQ,
                  require_same_object=False)
    assert q["state"] == Q.CITED_UNVERIFIED
    assert "本次未检查对象绑定" in q["why"], "★★★ 关掉了却不说 —— 那是静默降级"


# ══ 接线: 两道都必须过 ═════════════════════════════════════════════════
def test_both_gates_are_required_and_not_merged():
    """★★★ 合同层建好后全仓**零个调用方** —— 一层没人调的闸与没有它等价, 且更糟(看起来像有覆盖)。

    ⇒ 做成**一个**入口, 下游只能整体用, 不能只挑一道。
    """
    good = [_ev("Settled on the Oticon", REQ[0], "Oticon", "具体型号"),
            _ev("holding off till payday", REQ[1], "Oticon")]
    PROD = "d4cce4c745f3f991"
    r = Q.citable_as_confirmed("display", TEXT, PROD, evidence=good, required_conjuncts=REQ)
    # ★★★ 2026-09-14 降格后: 即使两道都「过」, citable 仍为 False ——
    #   因为合同层现在最高只到 ③′(语义未独立验证), ④ 的识别器尚未实现。
    #   **这是有意的**: 在语义被独立验证之前, 没有东西有资格被叫作「已确认存在」。
    assert r["instrument_gate"]["pass"], "★ 仪器那道应当过"
    assert r["contract_gate"]["state"] == Q.CITED_UNVERIFIED, "★ 合同那道应当到 ③′"
    assert not r["citable"], (
        "★★★★ 两道都「过」就放行了「已确认存在」—— 但合同层**只验了出处与结构**, "
        "语义未独立验证(否定辖域/归属/时态/引用层级/类型成员资格五类都没验)")
    # 合同不过 ⇒ 整体不可引用, 但仪器那道仍如实报 pass(不合并)
    r2 = Q.citable_as_confirmed("display", TEXT, PROD, evidence=None, required_conjuncts=REQ)
    assert not r2["citable"] and r2["instrument_gate"]["pass"] and not r2["contract_gate"]["pass"]
    assert r2["contract_gate"]["state"] == Q.CANDIDATE, "★ 无证据应当落 ③(候选)"
    # 仪器不过 ⇒ 整体不可引用, 合同那道仍如实报 pass
    r3 = Q.citable_as_confirmed("display", TEXT, "0" * 16, evidence=good, required_conjuncts=REQ)
    assert not r3["citable"] and not r3["instrument_gate"]["pass"]
    assert r3["contract_gate"]["state"] == Q.CITED_UNVERIFIED
    # ★ 两道的理由不许被合并成一句
    assert r3["instrument_gate"]["why"] != r3["contract_gate"]["why"]
    assert "不许互相顶替" in json.dumps(r3, ensure_ascii=False)
    return r, r2, r3


if __name__ == "__main__":
    test_default_is_not_confirmed()
    test_a_span_must_be_verbatim_in_the_text()
    q2 = test_every_conjunct_needs_its_own_span()
    test_missing_conjunct_list_also_fails_closed()
    test_it_refuses_bare_strings_as_evidence()
    test_this_layer_never_reaches_the_prompt()
    test_it_does_not_pretend_to_replace_the_instrument_gate()
    test_two_conjuncts_on_different_objects_must_not_confirm()
    test_an_unnamed_object_fails_closed()
    test_no_alias_merging_and_it_says_so()
    test_increment_must_name_a_contract_enumerated_kind()
    kinds = test_the_enumerated_kinds_match_the_frozen_discriminant()
    test_restating_the_identifier_is_not_an_increment()
    test_same_object_with_everything_named_does_confirm()
    test_turning_off_the_object_check_must_be_loud()
    test_both_gates_are_required_and_not_merged()
    print("test_cce_label_qualification: OK ("
          "★★★落地 P3 的第 ③ 档「未确认候选」—— 附件 C 把混用的四件事拆开后, "
          "「输出端必须给确定标签」与「禁止无支持的确定标签」**不再矛盾**: "
          "top-1 照发, 缺支持时**不升格**而落进候选 | "
          "★★★**fail-closed**: 无证据 / 无合取项清单 / 裸字符串 / 合取项缺一 —— **四种都不升格**; "
          "默认给确认的实现**比没有这一层更糟**(会让「已确认存在」这个词失去含义) | "
          "★★★证据 = **原文里逐字可指的片段** + 它支撑哪个条款, 构造期当场核 —— "
          "编造片段直接抛(附件 B: 指不出片段的推断**不是弱证据, 是没有证据**) | "
          "★★★★**这一层一个字都不进 prompt**: gen9 双臂重测(1291 次真实调用)实测, "
          "把合同文本塞进生产 s2 prompt 会让 display 由 **1/80 涨到 40/80** 且**倒挂**"
          "(不该给的 A 臂 56% > 可以给的 B 臂 41%) ⇒ **用 prompt 教模型守合同是已被测出会让读数更偏的路**; "
          "本层只在读数产出**之后**工作, 不改 instrument_hash、不换代、不碰冻结件 | "
          "★ 与仪器层是**两道**(还要过 knot_readout_usable), 不许互相顶替 | "
          f"★★★★**P2 落地**: `∃x[P(x)∧Q(x)]` 与 `(∃x P)∧(∃y Q)` 不等价 —— "
          "每条片段必须**指名它关于哪个对象**, 两支落不同对象/指不出对象 ⇒ 不升格; "
          "**不做别名归并**(「the Oticon」与「Oticon」在这里是两个对象), 且**把这个保守选择写进产物** —— "
          "沉默的保守策略会被读成「它判过了」 | "
          f"★★★增量支额外两条(库内教训: **对象相关的事实 ≠ 关于对象的信息增量**): "
          f"① 必须指名属于**合同枚举**的哪一种{list(kinds)}(枚举表与判别式原文**现算一致**, 合同改了它必须跟着改); "
          "② 片段**去掉对象标识后仍要有内容** —— 复述型号名不产生增量(附件 A) | "
          "★灵敏度: 条件全齐**必须**升格, 否则这层是恒拒的摆设; 关掉 P2 要显式传参**且产物里写明本次没查** | "
          "★★★★**接线**: 合同层建好后全仓**零个调用方** —— 一层没人调的闸与没有它等价, 且更糟(看起来像有覆盖)。"
          "⇒ `citable_as_confirmed()` 做成**唯一入口**, 仪器层与合同层**两道都过才 True**, "
          "且两道的理由**分别给出不合并** —— 把任一道单独拿去放行, 就是把两个不同的问题当成了一个 | "
          "★★★★**2026-09-14 降格**: 零调用反例证明这一层**允许形式合法、语义错误的证书通过** —— "
          "原文「I have **never** owned or tried the Oticon」, Q 支引用「owned or tried the Oticon」"
          "(片段真实·对象正确·落在否定辖域内), 旧实现判 CONFIRMED_PRESENT。"
          "⇒ 改名 **CITED_SEMANTICS_UNVERIFIED**(出处可核对·语义未独立验证); "
          "④ 只留给**尚未实现**的确定性识别器 ⇒ `is_citable_as_confirmed()` **现阶段恒为 False**, "
          "模型与人工的引用**都只能到 ③′**。"
          "★**不加否定词正则**: 逐字核对验不了的至少五类(否定辖域/归属/时态/引用层级/类型成员资格), "
          "补一类会留着其余四类**却制造「已关住」的错觉** —— 那正是要消除的误解本身)")


def test_p2的强度取决于调用方肯不肯分别指名():
    """★★★ 2026-09-14 零调用自检抓到的**协议层**漏洞, 不是本模块的 bug, 是它的**使用条件**。

    `require_same_object` 比对的是调用方填进两条 EvidenceSpan 的 `about`。
    如果采集协议只向产出方要**一个**对象字段, 再由调用方贴到两支上,
    那么 P2 **结构上不可能失败** —— 验证器还在, 但它在核一个恒真的命题。

    这是 N2(期望与实际同源) 在协议层的样子: 不看模块看不见, 因为模块本身是对的。
    """
    import cce_label_qualification as LQ
    txt = ("My brother's Phonak Audeo Sphere gets 16 hours on a charge. "
           "I wear something far simpler myself.")
    inc = "gets 16 hours on a charge"
    own = "I wear something far simpler myself"

    # ① 分别指名 ⇒ P2 拦住
    q = LQ.qualify("display", txt, required_conjuncts=["输出新信息增量", "谈论对象是自己已拥有或已经历的"],
                   evidence=[LQ.EvidenceSpan(inc, "输出新信息增量", txt,
                                             about="Phonak Audeo Sphere", increment_kind="数据"),
                             LQ.EvidenceSpan(own, "谈论对象是自己已拥有或已经历的", txt,
                                             about="something far simpler")])
    assert q["state"] == LQ.CANDIDATE, "★ 两支明明不同对象, P2 没拦住"

    # ② 同一个 about 贴到两支 ⇒ 放行。**这不是模块的错**, 是协议喂了假输入。
    q2 = LQ.qualify("display", txt, required_conjuncts=["输出新信息增量", "谈论对象是自己已拥有或已经历的"],
                    evidence=[LQ.EvidenceSpan(inc, "输出新信息增量", txt,
                                              about="Phonak Audeo Sphere", increment_kind="数据"),
                              LQ.EvidenceSpan(own, "谈论对象是自己已拥有或已经历的", txt,
                                              about="Phonak Audeo Sphere")])
    assert q2["state"] == LQ.CITED_UNVERIFIED, (
        "★ 若这里也被拦住, 说明模块**自己**在识别对象 —— 它明写了不做那件事, "
        "那就是文档与行为不符, 同样要查。")

    # ★ 结论落成一条**对调用方的要求**, 而不是模块的修补:
    #   凡是要靠 P2 的地方, 采集协议必须向产出方**分别**要两个 about。
    #   probes/extractor_counterexample_run.py 的 PROMPT 已按此改过(2026-09-14)。
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "probes/extractor_counterexample_run.py")
    if src.exists():
        body = src.read_text(encoding="utf-8")
        assert body.count('"about"') >= 2, (
            "★ 该 probe 的采集协议又退回成只要一个对象字段了 —— P2 会重新变成摆设")
