#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: P1–P4 是**owner 授权我代定**的, 这件事不许被悄悄抹掉; 且它写的代价必须与现算一致。

★★★ 为什么这条最要紧:
这四项本来归 owner。2026-09-13 他说「P1–P4 仍归你, 也做了吧」⇒ 由我代定。
**下游读到这些规则时必须知道推理与取舍是我做的**, 不是 owner 的判断 ——
否则过几轮之后, 「我推荐的」会被读成「owner 定的」, 而那是**把自己的判断洗成授权**,
比判错严重得多(判错可以改, 洗成授权之后没人会再去改)。
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = (ROOT / "P1_P4_DECIDED_2026-09-13.md").read_text(encoding="utf-8")
sys.path.insert(0, str(ROOT / "probes"))
import withdrawn_display_assertions_reclassify as R  # noqa: E402


def test_the_delegation_is_stated_and_revocable():
    """★★★ 代定这件事必须写在**最前面**, 且必须写明 owner 可以随时推翻。"""
    head = DOC.split("---")[0]
    assert "owner" in head and "代定" in head, "★★★ 没写这是代定 —— 会被读成 owner 自己的判断"
    assert "推理与取舍是我做的" in head, "★★ 没写清是谁在推理"
    assert "以他为准" in head and "作废重来" in head, (
        "★★★ 没写明 owner 可随时推翻 —— 代定必须是可撤的, 否则就是夺权")
    # 「他授权的是『你来定』, 不是『你定的就是我想的』」这一层不许丢
    assert "不是「你定的就是我想的」" in head, "★★ 授权范围的限定被抹掉了"


def test_all_four_are_decided_with_their_tradeoff():
    for p in ("**P1**", "**P2**", "**P3**", "**P4**"):
        assert p in DOC, "★ 缺 %s" % p
    assert DOC.count("我依赖的价值取舍") >= 1
    for t in ("宁可让一类文本落进未决", "误报比漏判更伤"):
        assert t in DOC, "★ 取舍没写出来: %s" % t


def test_the_stated_cost_matches_what_the_probe_computes_now():
    """★★★ 「gen8 改回 FAIL」这句必须与探针**现算**一致 —— 不许留档说一套代码算另一套。"""
    r = R.build()
    restore, keep = r["★★★恢复"], r["★维持撤销"]
    assert len(restore) == 6 and len(keep) == 2, (
        "★★★ 重分类结果变了(恢复 %d / 维持 %d) —— 文档里的 74→80 与 FAIL 都要重算"
        % (len(restore), len(keep)))
    imp = r["★★★对 gen8 判决的影响"]
    assert isinstance(imp, dict), "★ gen8 影响算不出来: %r" % imp
    assert len(imp["★★★其中落在恢复集里的"]) == 3, "★ 落在恢复集里的违例数变了"
    assert "改回 FAIL" in imp["结论"]
    assert "74 → 80" in DOC and "改回 FAIL" in DOC, "★ 文档里的数与探针不一致"
    # 每条恢复项都必须能**指名原文片段**, 且片段逐字在原文里(探针自己会断言, 这里再钉一次)
    for row in r["逐条"]:
        if row["处置"] == "恢复":
            assert row["原文片段"] and row["原文片段"] in row["文本"], (
                "★★★ %s 的片段指不出或不在原文里 —— 那它就该落 (丁)" % row["用例"])
        else:
            assert row["原文片段"] is None, "★ 维持撤销的条目不该带片段"
    return len(restore), len(keep)


def test_the_cost_is_owned_not_blamed_outward():
    """★★ 代价必须写成**这个决定自己的代价**, 不许写成外部坏消息。"""
    assert "这是 **P1 自己的代价，不是外部坏消息**" in DOC or "自己的代价" in DOC, \
        "★★ 代价被写成了外来的"
    assert "选「含事」就不会有这个后果" in DOC, "★ 没写清另一个选项不会有这个代价 —— 那是在藏取舍"


def test_it_does_not_smuggle_in_an_authorization():
    """★★★ 合同裁定 ≠ 替换生产 ≠ 运行授权。三件事不许混。"""
    blk = DOC.split("## 这些裁定**没有**授权什么")[1]
    for must in ("不构成替换生产的依据", "不构成运行授权", "不倒灌"):
        assert must in blk, "★★★ 缺一条否定: %s" % must
    assert "DEV-001" in blk, "★ 偏离记录没随裁定同行"


def test_it_did_not_pick_the_rule_by_how_many_assertions_it_restores():
    """★★★ 第十一轮那条主裁定: 判据是**构念**, 不是「能恢复几条断言」。

    代定之后这条更危险 —— 没人在外面盯着了, 所以必须自己钉住。
    """
    assert "判据是构念，不是它能恢复几条断言" in DOC, (
        "★★★ 没有声明判据是构念 —— 代定的人最容易照着结果选规则")
    assert "P1 也不是为了让它 FAIL 而选的" in DOC
    # 裁定表里不许出现「恢复几条」作为理由
    tbl = DOC.split("## 裁定")[1].split("---")[0]
    for bad in ("恢复", "违例", "FAIL"):
        assert bad not in tbl, "★★★ 裁定表里用「%s」当理由 —— 那是让结果反过来定规则" % bad


if __name__ == "__main__":
    test_the_delegation_is_stated_and_revocable()
    test_all_four_are_decided_with_their_tradeoff()
    n_r, n_k = test_the_stated_cost_matches_what_the_probe_computes_now()
    test_the_cost_is_owned_not_blamed_outward()
    test_it_does_not_smuggle_in_an_authorization()
    test_it_did_not_pick_the_rule_by_how_many_assertions_it_restores()
    print("test_cce_p1_p4_decided: OK ("
          "★★★**代定这件事被钉在最前面且可撤**: owner 授权的是「你来定」**不是**「你定的就是我想的」, "
          "他说不是这个意思 ⇒ 整体作废重来 —— 不钉住这条, 几轮之后「我推荐的」会被读成「owner 定的」, "
          "**那是把自己的判断洗成授权**, 比判错严重(判错能改, 洗成授权之后没人会再去改) | "
          f"★★★代价与探针**现算一致**: 8 条被一刀切撤销的 display 断言重分类 ⇒ **恢复 {n_r} 条(乙·文本内正面反证, "
          f"每条都能指名片段且代码逐字核过) / 维持撤销 {n_k} 条(丁·指不出片段)**; 断言表 74→80; "
          "**gen8 三个违例 3/3 依据恢复 ⇒ 改回 FAIL** | "
          "★★代价写成**这个决定自己的代价**(选「含事」就不会有), 不是外来坏消息 | "
          "★★★三件事不许混: 合同裁定 ≠ 替换生产 ≠ 运行授权(且 DEV-001 随行) | "
          "★★★判据是**构念**不是「能恢复几条断言」—— 裁定表里连「恢复/违例/FAIL」都不许出现, "
          "**代定之后没人在外面盯着, 这条只能自己钉**)")
