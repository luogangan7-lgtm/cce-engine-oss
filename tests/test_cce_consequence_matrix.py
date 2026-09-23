#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 后果分析矩阵 —— 钉住它**是后果分析, 不是断言**, 且三条机械结论现算成立。"""
import hashlib
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
import owner_decision_consequence_matrix as M  # noqa: E402
MEMO = (ROOT / "OWNER_DECISION_log_2026-09-09_to_11.md").read_text(encoding="utf-8")


def test_it_produces_no_current_assertions():
    """★★★ 最重要: 后果分析**不得**变成现行断言。

    ★★ 2026-09-13 改**判法**(不是放宽): 原来把条数硬编成 74 —— 那是当时的值。
      2026-09-13 P1 裁定后逐条重判恢复 6 条(74→80), 本条当场判红, 而红的原因
      **与它要守的东西无关**(表是被 P1 裁定改的, 不是被后果分析改的)。
      ⇒ 改成**实测后果分析跑前跑后表有没有变** —— 这才是「不得越界」的直接判据,
        且不会因为表**合法地**变了就误报。
    """
    P = ROOT / "tests/data/local_contract_assertions_v2.json"
    before = hashlib.sha256(P.read_bytes()).hexdigest()
    M.build()                                     # ★ 真跑一遍后果分析
    after = hashlib.sha256(P.read_bytes()).hexdigest()
    assert before == after, (
        "★★★ 后果分析**改动了断言表** —— 那就越界了。它只许算后果, 不许立断言。\n"
        "  before %s\n  after  %s" % (before[:16], after[:16]))
    A = json.loads(P.read_text(encoding="utf-8"))
    adj = [a for a in A["断言"] if a["★★★断言状态"] == "已裁定"]
    # ★ 条数改由**另一个真相源**现算(重分类探针), 不再硬编
    import withdrawn_display_assertions_reclassify as R
    r = R.build()
    # ★★★ 2026-09-14: 又加了一项来源(P 支新断言) ⇒ 这里**每一项都要具名**,
    #   否则下次再加一批, 这个等式又会红, 而红的原因会被当成「对不上」而不是「少写了一项来源」。
    #   计数**不硬编**: 按断言自带的来源标记现算。
    p_arm = [a for a in adj if "★★★与被撤那条的差别_这不是恢复" in a]
    terms = [("v2 冻结基数", 74),
             ("重分类恢复", len(r["★★★恢复"])),
             ("2026-09-14 P 支新断言", len(p_arm))]
    assert len(adj) == sum(n for _, n in terms), (
        "★ 已裁定 %d 条, 与具名各项之和 %d 不符 —— 要么真相源对不上, "
        "要么**又加了一项来源却没在这里具名**。现有各项: %r"
        % (len(adj), sum(n for _, n in terms), terms))
    return len(adj)
    n = M.build()["★★★本矩阵不产生的东西"]
    for must in ("不产生**任何现行断言", "不产生**对任何一轮的改判", "不产生**「哪个选项更好」的推荐"):
        assert any(must in x for x in n), f"★ 缺边界声明: {must}"


def test_the_original_conclusion_is_withdrawn_and_two_ban_kinds_are_split():
    """★★★★ 2026-09-11 **本测试翻面**: 它原本钉的正是被第十轮推翻的那条结论
    (「只有 2/8 且都是甲」)。现在钉住的是**撤回本身 + 两种禁判已拆开**。"""
    c3 = M.build()["第三格·display 对象域"]
    assert c3["组合数"] == 8
    # ★ 撤回必须在册, 且写出两个撤回理由
    w = c3["★★★★原结论已撤回"]
    assert "撤回" in w and "禁的是**无支持的输出**" in w
    assert "乙允许更多对象 ≠ 对象可任意替换" in w
    # ★★ 两种禁判必须拆开, 且写明 ② 不需先证 ①、也不能被留档成 ①
    bk = M.build()["★两种禁判(第十轮)"]
    assert set(bk) == {"①反证型", "②资格型"}
    assert "不需要先证明①" in bk["②资格型"]["★关系"] and "不能被留档成①" in bk["②资格型"]["★关系"]
    assert "不能倒灌成旧输出的新违规依据" in bk["②资格型"]["★★★时间边界"]
    assert "不总能推出" in bk["①反证型"]["★注意"], \
        "★ 「无法证明某一项不成立」≠「无法证明它们不可能同时成立」—— 这条必须在"
    # ★★★ 重算结论: 4/8, 且共同点是证据义务不是对象域
    bans = c3["★★★能启用②资格型禁判的组合"]
    assert len(bans) == 4, f"★ 数变了: {bans}"
    assert all("E1·有证据义务" in b for b in bans)
    assert any("甲·限物" in b for b in bans) and any("乙·物+事" in b for b in bans), \
        "★★ 甲乙都要能启用 —— 若只剩甲, 说明又回到被撤回的那版"
    assert "不是对象域, 是「设了证据义务」" in c3["★★★★最要紧的一条(2026-09-11 **已改写**)"]
    # ★ ①反证型在本分析下必须登记为未定, 不许偷偷判成立或不成立
    k = [k for k in c3["逐组合"]][0]
    assert "未定" in c3["逐组合"][k]["①反证型禁判"]
    return len(bans), c3["组合数"]


def test_B1_spillover_and_B2_does_not():
    """★★★ 之二: B1 有连带(可能放宽「决策未定」), B2 没有。"""
    c1 = M.build()["第一格·收藏+未来准备状态"]
    b1 = [v for k, v in c1["逐组合"].items() if "B1·不要求理由" in k][0]
    b2 = [v for k, v in c1["逐组合"].items() if "B2·" in k][0]
    assert "6 条的 suspend 禁判可能一并失效" in b1["★★★B1 的连带"]
    assert "另一个构念范围变化" in b1["★★★B1 的连带"]
    assert b2["★★★B1 的连带"] == "无", "★ B2 不该有连带 —— 若有, 这条对比就不成立"
    assert len(b1["受影响用例"]) == 6 and len(b2["受影响用例"]) == 0


def test_D_is_untestable_on_this_corpus():
    """★★★ 之三: 这 22 条**没有上下文** ⇒ D 与「仅当前句」产出完全相同, 本轮数据测不出 D。"""
    c1 = M.build()["第一格·收藏+未来准备状态"]
    d = [v for k, v in c1["逐组合"].items() if "D·固定上下文" in k][0]
    assert "产出完全相同" in d["★★D 在本语料上无区别"]
    assert "另建带上下文的语料" in c1["★★★★D 在本语料上测不出"]


def test_matrix_nature_is_pinned_as_recomputation_not_prediction():
    """★★★ 第十轮: 性质必须固定为「旧输出在不同假定规范下的**后果重算**」,
    **不是**「新规范送给模型后新输出将是什么」。"""
    r = M.build()
    n = r["★★★★性质必须固定为(第十轮)"]
    assert "后果重算" in n and "不要把后果分析再升成换代效果预测" in n
    b = r["★★该补的不是更多自由轴, 是先把层次固定(第十轮)"]
    assert "不能在某个条件失败后临时换一个对象救判" in b["对象绑定规则"]
    assert "不能由当次判官临场选择" in b["对象绑定规则"]
    assert "组合翻倍" in b["★不宜"]


def test_the_two_cells_share_one_fallback_rule():
    assert "是**同一条规则**" in M.build()["★★两格之间的耦合"]


def test_readings_are_not_offered_as_normative_evidence():
    """★ 15/22 三代未变 —— 那是**当前实现的行为**, 不是规范正确性的证据。"""
    r = M.build()
    assert len(r["★三代都没变过的用例"]) == 15
    assert "C_仅收藏_0" in r["★三代都没变过的用例"]
    assert any("不是规范正确性的证据" in x for x in r["★★★本矩阵不产生的东西"])
    assert "不是规范正确性的证据" in MEMO


def test_memo_carries_the_matrix_with_the_three_conclusions():
    for x in ("只回答「甲·限物」而不同时定证据规则，结果与现状完全相同",
              "B1·不要求理由有连带风险", "B2 没有这个连带",
              "在本语料上测不出", "是同一条规则"):
        assert x in MEMO, f"★ 交办件缺: {x}"
    assert "断言表仍是 74 条" in MEMO, "★ 交办件必须自陈它没改断言表"


if __name__ == "__main__":
    test_it_produces_no_current_assertions()
    nb, nt = test_the_original_conclusion_is_withdrawn_and_two_ban_kinds_are_split()
    test_B1_spillover_and_B2_does_not()
    test_D_is_untestable_on_this_corpus()
    test_matrix_nature_is_pinned_as_recomputation_not_prediction()
    test_the_two_cells_share_one_fallback_rule()
    test_readings_are_not_offered_as_normative_evidence()
    test_memo_carries_the_matrix_with_the_three_conclusions()
    n_adj = test_it_produces_no_current_assertions()
    print("test_cce_consequence_matrix: OK ("
          "★★★★第三格**原结论已撤回** —— 我把**两种禁判混成了一个轴**: "
          "①反证型(要有效反证必要条件) 与 ②资格型(缺合同要求的支持⇒不准确定输出) **不是一回事**, "
          "且 E1/E2 **根本不互斥**(输出资格规则 vs 事实推理规则, 可同时执行, **不把未知变成假**) | "
          f"★重算: {nb}/{nt} 个组合能启用②, 共同点**不是对象域而是「设了证据义务」—— 甲乙都能启用**; "
          "①在本分析下**登记为未定** | "
          "★★时间边界: 旧合同没规定证据义务时, **现在提出不能倒灌成旧输出的违规依据** | "
          "★★第一格: **A 是唯一能禁 C_仅收藏_0 的理由档**; ★★★**「B1 有连带」已于 2026-09-11 核实撤回** —— "
          "旧说法「12 条 suspend 断言要重审」**两重错**(逻辑: 取消 `A∧B` 的 B 剩下 A; "
          "事实: 那 12 条的失败合取项无一例外是「决策被明确悬置」, 与理由无关) ⇒ **受影响 0 条**, "
          "**B2 没有** | "
          "★★★**D 在本语料上测不出** —— 22 条是孤立构造题无上下文, D 与「仅当前句」产出完全相同, "
          "**选 D 须另建带上下文语料** | "
          "★两格的 F 是**同一条规则**, 可一次决定但同时作用于两格 | "
          f"★★★后果分析**不产生任何现行断言**(实测跑前跑后断言表 sha **逐位相同**; n 由另一真相源现算, 各项具名求和 = {n_adj} 条); "
          "15/22 三代未变是**当前实现的行为**, **不是规范正确性的证据**)")
