#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: gen9 的判决必须与**冻结判据现算一致**, 且不得被读成对候选代有利。

★★★ 这一轮最容易被误读的地方:
判决是 `FAIL_ON_NOISE` —— 字面看像「FAIL 被推翻了」。**恰恰相反。**
它的意思是「gen8 点名的那三条的依据不稳」, 而**同一批数据显示候选构造器在更大的面上违反**
恢复的断言(A 臂 56%)。**方向是更不利, 不是更有利。**
⇒ 本闸把这条读法钉死, 免得下一轮有人只看判决词。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRE = json.loads((ROOT / "tests/data/gen9_violation_stability_prereg.json").read_text(encoding="utf-8"))
V = json.loads((ROOT / "results/gen9_verdict.json").read_text(encoding="utf-8"))
A = PRE["arms"]["A_要判的"]["cases"]
B = PRE["arms"]["B_退化对照"]["cases"]
V3 = ["C_已决定_延后执行_0", "C_已决定_延后执行_1", "C_★已决定_未来时间词_0"]


def _per(which):
    p = ROOT / ("results/gen9_violation_stability/per_case.json" if which == "P"
                else "results/gen9c_violation_stability/per_case.json")
    return json.loads(p.read_text(encoding="utf-8"))["per_case"]


def _raw(which):
    p = ROOT / ("results/gen9_violation_stability/raw_draws.jsonl" if which == "P"
                else "results/gen9c_violation_stability/raw_draws.jsonl")
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_the_verdict_is_what_the_frozen_rule_computes_now():
    """★★★ 判决必须由**冻结判据**现算得出, 不许留档一套、代码另一套。"""
    per = _per("C")

    def classify(v):
        if v["stable(>=7/8)"] and v["mode"] == "display":
            return "violation_is_stable"
        if not v["stable(>=7/8)"] and v["saw_display"]:
            return "violation_is_noise"
        if v["stable(>=7/8)"] and v["mode"] != "display":
            return "no_violation"
        return "UNCLASSIFIED"

    three = {c: classify(per[c]) for c in V3}
    modes = [per[c]["mode"] for c in A + B]
    degen = len(set(modes)) >= 2 and modes.count("display") < 10
    if not degen:
        want = "DEGENERATE"
    elif any(x == "violation_is_stable" for x in three.values()):
        want = "FAIL_CONFIRMED"
    elif all(x == "violation_is_noise" for x in three.values()):
        want = "FAIL_ON_NOISE"
    else:
        want = "MIXED"
    assert V["★★★按冻结决策规则的判决"] == want, (
        "★★★ 档案判决 %r 与冻结判据现算 %r 不符" % (V["★★★按冻结决策规则的判决"], want))
    assert V["退化检查"]["通过"] is degen
    return want, three


def test_the_two_arms_used_different_builders():
    """★★ 两臂的**唯一**变量必须是构造器。若两边字数相同, 这轮对照就不成立。"""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import cce_knot_classify as CK
    import cce_stage2_candidate as SC
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    s1 = {"tops": {}, "appraisal": {}}
    prod = CK._build_stage2_prompt(taxo, "SAMPLE", s1)
    cand = SC.build(taxo, "SAMPLE", s1,
                    ("ontology", "discriminant", "negative", "full_behavior", "decision_tree"))
    assert len(prod) != len(cand), "★★★ 两个构造器产出一样长 —— 对照不成立"
    hd = taxo["knots"][0]["hard_discriminant"]
    assert hd not in prod and hd in cand, (
        "★★★ hard_discriminant 的进/不进关系变了 —— 这正是两臂的核心差别, 变了就要重跑")
    return len(prod), len(cand)


def test_the_inversion_is_recorded():
    """★★★ 倒挂必须留在结论里: 候选在**合同说不该 display 的 A 臂**上比 B 臂**更常**给 display。

    这是预注册的 B 臂唯一的目的。没有它, A 臂的数字说明不了任何事。
    """
    def rate(rows, cases):
        r = [x for x in rows if x["case"] in cases and x.get("top1")]
        return sum(1 for x in r if x["top1"] == "display"), len(r)

    ca, na = rate(_raw("C"), A)
    cb, nb = rate(_raw("C"), B)
    assert ca / na > cb / nb, (
        "★ 倒挂不再成立(A %d/%d vs B %d/%d) —— 结论里那句话要重写" % (ca, na, cb, nb))
    assert "倒挂" in json.dumps(V, ensure_ascii=False), "★★ 倒挂这件事从结论里消失了"
    return (ca, na), (cb, nb)


def test_the_production_arm_is_not_oversold():
    """★★★ 生产臂 A 0/48 **不等于**「生产判得对」—— B 臂 1/32 说明它在这族文本上几乎从不给 display。

    没有这句限定, 0/48 会被读成一个它支持不了的结论。
    """
    def rate(rows, cases):
        r = [x for x in rows if x["case"] in cases and x.get("top1")]
        return sum(1 for x in r if x["top1"] == "display"), len(r)

    pa, na = rate(_raw("P"), A)
    pb, nb = rate(_raw("P"), B)
    assert pa == 0, "★ 生产臂 A 出现了 display(%d/%d) —— 结论要重写" % (pa, na)
    assert pb / nb < 0.1, "★ 生产臂 B 的 display 率升高了(%d/%d) —— 那句限定要重算" % (pb, nb)
    blob = json.dumps(V, ensure_ascii=False)
    assert "同样相容" in blob, "★★★ 「0/48 与两种解释同样相容」这句限定被删了"
    return (pa, na), (pb, nb)


def test_the_verdict_cannot_be_read_as_good_news():
    """★★★ `FAIL_ON_NOISE` 字面像「FAIL 被推翻」。挡住这个读法。"""
    blob = json.dumps(V["★★★不得据此说"], ensure_ascii=False)
    # ★ 锚在**值**上而不是我记忆里的措辞: 实际文本带加粗标记(**不得**说…)。
    #   本仓踩过好几次「断言锚错」—— 这次是锚少了两个星号, 修断言不是改数据。
    for must in ("说「候选代 FAIL 被推翻」", "方向是更不利", "把「违例落在噪声里」读成「候选代通过」"):
        assert must in blob, "★★★ 挡板缺: %s" % must


def test_a_stable_violation_outside_the_named_three_is_reported():
    """★★ 有一条**稳定**违例, 但不在 gen8 点名的三条里 —— 这条比判决词本身更重要。"""
    per = _per("C")
    extra = [c for c in A if c not in V3
             and per[c]["stable(>=7/8)"] and per[c]["mode"] == "display"]
    assert extra, "★ 稳定违例集合变了, 结论里那一段要重算"
    assert "C_★已决定_未来时间词_1" in extra
    assert "gen8 抓到那三条**带有抽样偶然性**" in json.dumps(V, ensure_ascii=False)
    return extra


if __name__ == "__main__":
    want, three = test_the_verdict_is_what_the_frozen_rule_computes_now()
    lp, lc = test_the_two_arms_used_different_builders()
    (ca, na), (cb, nb) = test_the_inversion_is_recorded()
    (pa, npa), (pb, npb) = test_the_production_arm_is_not_oversold()
    test_the_verdict_cannot_be_read_as_good_news()
    extra = test_a_stable_violation_outside_the_named_three_is_reported()
    print("test_cce_gen9_verdict: OK ("
          f"★★★判决 **{want}** 由冻结判据**现算**得出(判据看完数据一字未改) —— 原 gen8 三违例全部落 violation_is_noise | "
          f"★★两臂唯一变量是构造器: 生产 {lp} 字(hard_discriminant **不进**) vs 候选 {lc} 字(**进**) | "
          f"★★★**倒挂**(预注册 B 臂唯一目的, 抓到了): 候选在**合同说不该 display 的 A 臂 {ca}/{na}** 上"
          f"比在 **display 合理可能的 B 臂 {cb}/{nb}** 上**更常**给 display | "
          f"★★★生产臂 A **{pa}/{npa}** —— 但 B 臂 {pb}/{npb} 说明它在这族文本上几乎从不给 display, "
          "所以 0/48 与「有判别力」和「对这批语料就是不输出 display」**同样相容**, 不得当成「判得对」 | "
          f"★★有一条**稳定**违例落在 gen8 点名的三条**之外**({extra[0]}) ⇒ 候选构造器对恢复的断言是"
          "**普遍违反且不稳定**, gen8 抓到那三条**带抽样偶然性** | "
          "★★★挡住误读: `FAIL_ON_NOISE` **不是**「候选代 FAIL 被推翻」—— 同一批数据显示它在更大面上违反, "
          "**方向是更不利不是更有利**)")
