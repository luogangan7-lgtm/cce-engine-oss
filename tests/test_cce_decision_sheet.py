#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 交办件 —— 第十一轮之后它不再是「请勾选技术语义菜单」。

★★★ web GPT 第十一轮的主裁定(本文件要挡住的就是它):
「**最主要的引导方向是: 把「哪项规则符合要测的构念」, 悄悄改成了
  「哪项规则能恢复对这些用例的禁判」。**」
「「能恢复几条旧断言」可以是**影响分析**, **不能成为规范选项的主标题** ——
  否则就是**让旧测试期望反过来决定新合同**。」
并: 「对每个真正需要 owner 决定的点, **你应给出自己的推荐及理由**」;
   「你该收回的是**设计和举证的责任**, 不是擅自收回改变构念及合同的权力。」
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHEET = (ROOT / "OWNER_DECISION_SHEET.md").read_text(encoding="utf-8")
LOG_P = ROOT / "OWNER_DECISION_log_2026-09-09_to_11.md"
LOG = LOG_P.read_text(encoding="utf-8")
sys.path.insert(0, str(ROOT / "probes"))
import owner_decision_consequence_matrix as M  # noqa: E402
import p4_reason_coupling_audit as P4  # noqa: E402

SECTIONS = ("## P1 ", "## P2 ", "## P3 ", "## P4 ")


def test_sheet_is_short_and_log_is_kept():
    n = len(SHEET.splitlines())
    assert n <= 120, f"★ 交办件涨到 {n} 行 —— 收敛失效, 该往日志里挪"
    assert LOG_P.exists() and len(LOG.splitlines()) > n, "★ 沿革日志必须留着备查"
    # ★★★ 日志是**备查**, 不是现行件。被撤回的主张必须在日志里**当场标成已撤回** ——
    #   「过期判决表继续被引用」是我登记过的错误族, 原文留着但不标, 读者会当成现行。
    assert "第十一轮更正" in LOG, "★★★ 日志没有第十一轮的撤回块 —— 旧主张仍以现行形态挂着"
    i = LOG.index("suspend 那 12 条要重审")
    assert "已撤回" in LOG[i:], "★★★ 被撤回的 B1 连带在日志里没有撤回标记"
    assert "原文留在原处不删" in LOG, "★ 撤回不等于删除 —— 沿革要可追溯"
    return n


def test_it_is_a_proposal_not_a_menu():
    """★★★ 主裁定的正面要求: 我收回**设计与举证**的责任, 而不是收回 owner 的选择权。"""
    assert "请批准语义提案" in SHEET or "请批准" in SHEET.splitlines()[0] + SHEET.splitlines()[2]
    assert "设计与影响分析由我完成" in SHEET, "★ 没有声明责任已由我承担"
    assert "需要你批准的是**构念范围与损失取舍**" in SHEET
    for s in SECTIONS:
        assert s in SHEET, f"★ 缺 {s}"
        assert "★ 需你批准" in SHEET.split(s)[1].split("\n")[0], f"★ {s} 没标成需批准项"


def test_every_owner_decision_carries_my_recommendation_and_its_reason():
    """★★★ 「你应给出自己的推荐及理由」—— 缺推荐 = 又把推导甩回给他。"""
    for i, s in enumerate(SECTIONS):
        blk = SHEET.split(s)[1].split("\n## ")[0]
        assert "**我的推荐" in blk, f"★★★ {s} 没给我的推荐 —— 这是把推导甩给 owner"
        assert "理由：" in blk, f"★ {s} 的推荐没给理由"
    # 推荐必须连带写出**我依赖的价值取舍**, 否则「推荐」会伪装成客观结论
    assert SHEET.count("我依赖的价值取舍") >= 2, "★ 推荐没写出它依赖的取舍, 会被当成客观结论"


def test_options_are_framed_by_textual_scope_not_by_ban_recovery():
    """★★★★ 主裁定: 选项的**主标题**不许是「能恢复几条禁判」。

    影响分析(4/8)仍由探针现算、并留在日志里备查 —— 撤的是它在**规范选项**里的位置,
    不是把分析删掉。删掉分析是另一种不诚实。
    """
    assert M.build()["第三格·display 对象域"]["组合数"] == 8, "★ 影响分析探针本身必须仍可现算"
    assert "4/8" in LOG or "8 个组合" in LOG, "★★ 影响分析被删了 —— 该归档不该销毁"
    for s in SECTIONS:
        head = SHEET.split(s)[1].split("\n")[0]
        blk = SHEET.split(s)[1].split("\n## ")[0]
        for bad in ("禁判", "恢复", "断言数"):
            assert bad not in head, f"★★★★ {s} 的**标题**用「{bad}」做卖点 —— 旧期望反过来定合同"
        assert "8 个组合" not in blk and "4/8" not in blk, f"★★★ {s} 把影响分析当成了选择依据"


def test_the_B1_spillover_claim_is_computed_and_retracted():
    """★★★ GPT 说连带是我的逻辑错, 并要我**自己核对断言耦合**。核了: 受影响 0 条。"""
    r = P4.audit()
    assert r["★★★取消「理由要求」后依据消失的断言"] == [], "★ 探针与交办件的结论不一致"
    assert r["定位到 suspend 条款的断言数"] == 12
    blk = SHEET.split("## P4 ")[1]
    assert "受影响 0 条" in blk and "这项代价不存在" in blk
    # 旧说法只能以**被撤回的引文**形式出现, 不得作为现行主张
    i = blk.index("12 条断言要重审")
    assert "我先前写" in blk[max(0, i - 40):i], "★★★ 旧的连带主张又变回现行主张了"


def test_unresolved_contract_conflict_is_not_handed_to_owner():
    """★★ GPT: D2/D3 的冲突**不能原样交给 owner**。

    上一版的做法是**承诺**先排掉再提交; 现已真排掉(附件 C), 于是本闸升级为:
    冲突的原话要留着(否则读者不知道排的是什么), 且它**只能以已解决的形式**出现。
    """
    blk = SHEET.split("## P3 ")[1].split("\n## ")[0]
    assert "无法同时执行" in blk, "★ 冲突原话没留着"
    assert "已排掉" in blk, "★ 冲突不是已解决形态"
    for promissory in ("再提交你批准", "不把带冲突的组合送给你"):
        assert promissory not in blk, f"★★★ 「{promissory}」—— 又退回承诺态了"


def test_implementation_defect_is_not_excluded_and_three_gens_prove_nothing():
    """★★★ 「这不是实现 bug」是**无依据的排除性论断**, 且与我后文自相矛盾。"""
    assert "我不能排除实现缺陷" in SHEET
    assert "不是互斥命题" in SHEET, "★ 没写明「欠定」与「实现缺陷」可并存"
    assert "三代读数**不能决定该采用哪条规则**" in SHEET
    assert "这不是实现 bug" not in SHEET, "★★★ 排除性论断又回来了"


def test_responsibility_is_split_per_item():
    """★★ GPT 第十一轮要一张**责任表**: 每一项里哪半是我的、哪半是 owner 的。

    没有这张表, 「我承担设计与举证」就只是一句总纲 —— 读者无法逐项核对我有没有真承担。
    """
    assert "## 谁负责哪一半" in SHEET, (
        "★★ 责任表不在 —— 「我承担设计与举证」就只剩一句总纲, 读者无法逐项核对")
    blk = SHEET.split("## 谁负责哪一半")[1].split("\n---")[0]
    for s_ in ("P1", "P2", "P3", "P4"):
        assert f"| {s_} |" in blk, f"★ 责任表缺 {s_}"
    rows = [r for r in blk.splitlines() if r.startswith("| P")]
    for r in rows:
        cells = [c.strip() for c in r.strip("|").split("|")]
        assert len(cells) == 3 and cells[1] and cells[2], f"★ 有一项没写全两边: {r}"
        assert len(cells[2]) <= len(cells[1]) * 2 and len(cells[1]) <= len(cells[2]) * 4, \
            f"★ 责任表两栏详略悬殊, 会读成一边说了算: {r}"
    return len(rows)


def test_four_blocked_inferences_numbered_one_to_four():
    """★ 先前写「三条」却列了四条且编号重复。"""
    blk = SHEET.split("## 四条要挡住的错推")[1].split("\n## ")[0]
    nums = re.findall(r"^(\d+)\. ", blk, re.M)
    assert nums == ["1", "2", "3", "4"], f"★ 错推编号错乱: {nums}"
    assert "你的签字不能补出验证证据" in blk


def test_not_deciding_is_legitimate_and_stated_without_pressure():
    """★★★ GPT: 原「你可以不决定」是**施压框架** ——
    「永久」越界 · 「以后每份报告」外扩 · 详略不均使「不决定」读起来像欠债。"""
    blk = SHEET.split("## 可以暂不修订")[1]
    for w in ("永久", "以后每份报告"):
        assert w not in blk, f"★★★ 施压措辞「{w}」还在"
    assert "这些用例上已有的明确约束仍有效" in blk, "★ 不决定的后果被夸大成全面失效"
    for n in ("22", "12", "10"):
        assert n in blk, f"★ 披露口径缺 {n}"


def test_overrun_names_the_exact_resource_dimension():
    """★ 「超支过 1 次」含糊 —— 必须说清是**哪一维**超了、哪一维没超。"""
    tail = SHEET.split("## 批准之后会发生什么")[1]
    assert "请求次数超限一次（353/352），金额未超" in tail, "★ 超支维度仍含糊"
    assert "DEV-001" in tail
    assert "合同批准不构成运行授权" in tail, "★ 批准被当成了运行授权"


def test_options_within_one_decision_are_described_symmetrically():
    """★★★ 2026-09-11 我自审出的引导: 同一决定内两个选项详略不得悬殊。"""
    assert "| 选项 | 它把哪种文本现象纳入／排除 |" in SHEET, (
        "★★★★ 选项表的**比较轴**必须是「哪种文本现象被纳入或排除」—— "
        "这正是 GPT 第十一轮要我换回去的那根轴")
    rows = re.findall(r"^\| \*\*(只含物|含事)\*\*(.*?) \| (.*?) \|$", SHEET, re.M)
    assert len(rows) == 2, f"★ P1 的两个选项没抓到: {[r[0] for r in rows]}"
    lens = {n: len(a + b) for n, a, b in rows}
    lo, hi = min(lens.values()), max(lens.values())
    assert hi <= lo * 2, f"★★★ P1 两选项详略悬殊({lens}) —— 这是引导, 不是省略"
    return lens


ANNEX_P = ROOT / "OWNER_DECISION_ANNEX_definitions.md"


def test_my_own_debts_are_discharged_not_just_labelled():
    """★★★ GPT 点的几处「定义未给全」是**我的欠账**。

    上一版把它们标成「正在补」就交了出去 —— 那仍然是把推导留给 owner
    (「你该减少的是 owner 要替你完成的推导」)。⇒ 本闸要求它们**已兑现**, 不只是被认领。
    """
    assert ANNEX_P.exists(), "★★★ 三项定义的附件不存在 —— 欠账只被贴了标签, 没被还"
    ann = ANNEX_P.read_text(encoding="utf-8")
    assert "这三项是我欠的推导，不是你的待办" in ann
    for must in ("信息增量", "文本正面证据", "确定标签"):
        assert must in ann, f"★ 附件缺「{must}」这一项"
    # 每项都必须给**提案 + 代价**, 否则又变成「请你挑」
    # ★ 2026-09-11 变异测试逮到本闸自己的虚胖: 原先数「我的提案」, 而**导语里也有一处**
    #   ⇒ 删掉一项真提案仍能凑够数。改数**带冒号的提案句**, 并钉死**恰好三条**。
    props = ann.count("我的提案：")
    assert props == 3, f"★★★ 带提案的定义只有 {props} 条(应为 3) —— 有定义把选择推回给 owner 了"
    assert ann.count("**代价**") >= 3, "★ 有提案没写代价 —— 只说好处就是在带"
    assert "它们是我的责任，不是你的" in SHEET
    assert "已补" in SHEET and "ANNEX" in SHEET, "★ 交办件没有指向附件"
    assert "正在补" not in SHEET, "★★★ 欠账又退回「正在补」状态了"
    # 兑现不等于越权: 构念范围仍归 owner
    assert "它们**不**决定 P1／P2／P4 的构念范围 —— 那仍然归你" in ann, \
        "★★★ 补定义不得顺手把构念范围也定了"
    return len(ann.splitlines())


def test_the_P3_conflict_is_resolved_by_distinguishing_top1_from_confirmation():
    """★★★ 我报过的「无法同时执行」是**建立在概念混用上的假冲突** —— 必须真排掉, 不是移交。"""
    ann = ANNEX_P.read_text(encoding="utf-8")
    assert "证据义务只约束 ④" in ann and "top1 读数" in ann
    assert "不必让你在二者之间挑一个" in SHEET
    assert "无法同时执行" in SHEET, "★ 冲突的原话要留着, 否则读者不知道排掉的是什么"
    i = SHEET.index("无法同时执行")
    assert "已排掉" in SHEET[max(0, i - 120):i], "★★★ 冲突又变回未解决的现行主张了"


if __name__ == "__main__":
    n = test_sheet_is_short_and_log_is_kept()
    test_it_is_a_proposal_not_a_menu()
    test_every_owner_decision_carries_my_recommendation_and_its_reason()
    test_options_are_framed_by_textual_scope_not_by_ban_recovery()
    test_the_B1_spillover_claim_is_computed_and_retracted()
    test_unresolved_contract_conflict_is_not_handed_to_owner()
    test_implementation_defect_is_not_excluded_and_three_gens_prove_nothing()
    nr = test_responsibility_is_split_per_item()
    test_four_blocked_inferences_numbered_one_to_four()
    test_not_deciding_is_legitimate_and_stated_without_pressure()
    test_overrun_names_the_exact_resource_dimension()
    lens = test_options_within_one_decision_are_described_symmetrically()
    na = test_my_own_debts_are_discharged_not_just_labelled()
    test_the_P3_conflict_is_resolved_by_distinguishing_top1_from_confirmation()
    print("test_cce_decision_sheet: OK ("
          f"★★★★**主裁定已落成闸**: 选项的**标题**不许出现「禁判/恢复/断言数」—— "
          "GPT 第十一轮说我「把『哪项规则符合要测的构念』悄悄改成了『哪项规则能恢复对这些用例的禁判』」, "
          "那是**让旧测试期望反过来决定新合同**; 影响分析(4/8)仍现算、仍归档在日志, **撤的是它在规范选项里的位置** | "
          f"★★★**B1 连带已核实撤回**: 不是「12 条要重审」而是**受影响 0 条** —— "
          "12 条 suspend 断言的失败合取项**无一例外**是「决策被明确悬置」, 与「理由」无关(探针现算) | "
          "★★★每个待批项都带**我的推荐 + 理由 + 我依赖的价值取舍**(推荐不许伪装成客观结论) | "
          "★★D2/D3 的冲突**已真排掉**(不是承诺排掉), 原话留档以便读者知道排的是什么 | "
          "★★★「这不是实现 bug」这个**无依据排除性论断已删**, 改为「不能排除实现缺陷」且与欠定**不互斥** | "
          "★「三条错推」实为四条(编号已正) · 超支维度写准(**请求次数 353/352 超, 金额未超**) · "
          "**合同批准不构成运行授权** | "
          f"★★★施压框架已拆: 「永久」「以后每份报告」删除, 改为披露口径(22/12/10)且**已有约束仍有效** | "
          f"★★★**三项定义欠账已兑现**(附件 {na} 行, 每项都带我的提案+代价): 信息增量=**对象相对** · 正面证据=**自述+能指名原文片段的推断**(不含文本外上下文) · 「确定标签」拆成四件事、**证据义务只管「已确认存在」** | "
          "★★★由此**排掉了我自己报的那个冲突**: 「输出端必须给确定标签」与「禁止无支持的确定标签」并不矛盾 —— top1 照常给、缺支持时不升格为确认而落进候选, **不必让 owner 在二者间挑一个** | "
          f"★★**责任表**逐项分开我的与 owner 的({nr} 项, 两栏都不得空、不得详略悬殊) | "
          f"★对称性闸保留({lens}) | 交办件 {n} 行, 409 行日志备查)")
