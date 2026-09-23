#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 「已决定但尚未取得」这一格的合同空缺 —— 且钉住它**不推翻**违例判定。"""
import json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cce_contract_gap_decided_not_obtained as M  # noqa: E402
TAXO = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))


def test_the_gap_claim_is_withdrawn_not_still_asserted():
    """★★★ 2026-09-10 离线复核后, 「九结全不满足 / 合同没有归宿」这个主张**已撤回**。
    本测试从「钉住空缺成立」翻面为「钉住空缺已撤回」—— 断言方向反了, 这是有意的。"""
    r = M.build()
    w = r["★★★★★2026-09-10 离线复核后_空缺主张**撤回**"]
    assert "撤回" in w and "display 可能正是这一格的归宿" in w
    assert "合同对 display 的对象域欠定" in w, "★ 撤回后要说清**现在还能说什么**"
    assert "那条「display→itch 断掉的路由」也随之降级" in w, \
        "★ 建立在同一前提上的下游主张必须一起降级 —— 这正是我反复漏的那一步"
    # ★ display 一格不得再显示为 FAIL
    assert r["逐结"]["display"]["判"] == "★待复核", "★ display 仍标 FAIL —— 撤回没落到逐结表"
    # ★ 其余八结的推导仍成立(它们依据的是文本内属性或正面反证, 不是证据缺席)
    others = [k for k in r["逐结"] if k != "display"]
    assert all(r["逐结"][k]["判"].startswith("FAIL") for k in others), "★ 其余八结不该被一起撤"
    return len(others)
    for k, v in r["逐结"].items():
        assert len(v["理由"]) > 20, f"★ {k} 没写理由"
    return len(fails)


def test_the_broken_routing_is_quoted_from_the_contract_not_paraphrased():
    """★ 断掉的路由必须是**合同原文**推出的, 不是我概括的。逐字核。"""
    d = [k for k in TAXO["knots"] if k["key"] == "display"][0]["hard_discriminant"]
    i = [k for k in TAXO["knots"] if k["key"] == "itch"][0]["hard_discriminant"]
    assert "期望中未得之物→itch" in d.replace(" ", ""), "★ display 没有转出到 itch 的条文 —— 前提没了"
    assert "不采取行动" in i, "★ itch 没有「不采取行动」这个合取项 —— 前提没了"
    r = M.build()
    assert "转出去了, 但那一头不接" in r["★★★合同内部有一条断掉的路由"]


def test_reward_dead_end_is_two_step_not_one():
    """★ reward 不是一步判死的 —— 前置本身就未定, 且即使满足也被型号条款路由回 display。
    两步都要写出来, 只写一步等于把不确定说成确定。"""
    r = M.build()["逐结"]["reward"]
    assert "未定" in r["理由"] and "即使勉强算满足" in r["理由"]
    assert "回到已经失败的那一格" in r["理由"]


def test_it_does_not_overturn_the_violation_verdict():
    """★★★ 最重要的一条: 发现空缺**不等于**违例不成立。不许拿它给候选脱罪。"""
    r = M.build()
    t = r["★★★这改变了「3 个 display 违例」的性质"]
    assert "违例判定**仍然成立**" in t and "断言没推错" in t
    assert "归因" in t, "★ 必须说清改的是归因不是判定"


def test_abstention_is_noted_as_available_but_not_asserted_as_correct():
    r = M.build()
    a = r["★合同其实允许弃权"]
    assert "合法弃权" in a
    assert "从未告诉模型" in a, "★ 必须点明: 允许弃权 ≠ 告诉了模型该弃权"
    n = " ".join(r["★★不产生的东西"])
    assert "不产生**「这六条正确答案是弃权」" in n, "★ 不许把「可弃权」推成「应弃权」"


def test_it_claims_no_authority_over_ontology_changes():
    n = " ".join(M.build()["★★不产生的东西"])
    assert "增结是重大本体论改动, 归 owner" in n
    assert "历史悬置" in n, "★ 必须划清范围: 已购买的那四条**没有**这个空缺"


def test_it_is_merged_with_the_bookmark_only_memo():
    r = M.build()
    assert "合同在某一格上判不出来" in r["★与「仅收藏」是同一族"], "★ 断言要钉在**值**上, 不是重复键名"
    assert "并入同一份交办件" in r["★与「仅收藏」是同一族"]
    memo = (ROOT / "OWNER_DECISION_log_2026-09-09_to_11.md").read_text(encoding="utf-8")
    assert "已决定但尚未取得" in memo, \
        "★ 交办件还没并入这一格 —— 让 owner 分两次做同型决定是我的问题, 不是他的"


if __name__ == "__main__":
    n = test_the_gap_claim_is_withdrawn_not_still_asserted()
    test_the_broken_routing_is_quoted_from_the_contract_not_paraphrased()
    test_reward_dead_end_is_two_step_not_one()
    test_it_does_not_overturn_the_violation_verdict()
    test_abstention_is_noted_as_available_but_not_asserted_as_correct()
    test_it_claims_no_authority_over_ontology_changes()
    test_it_is_merged_with_the_bookmark_only_memo()
    print("test_cce_contract_gap: OK ("
          "★★★★「合同对这一格没有归宿」这个主张 **2026-09-10 已撤回** —— "
          "复核发现合同**没有**限定 display 的对象域, 「已经历」那一支**否不掉** ⇒ "
          "**display 可能正是这一格的归宿** | "
          f"★现在只能说: 除 display 外的 **{n}/8** 结必要条件不满足(依据的是**文本内属性**或**正面反证**, 不是证据缺席) | "
          "★★那条「display→itch 断掉的路由」**随之降级** —— 它只在「对象域限定为物」这一读法下成立; "
          "**建立在同一前提上的下游主张必须一起降级**, 这是我反复漏的那一步 | "
          "★合同允许弃权但**从未告诉模型**判别式全不满足时该弃权 ⇒ 「可弃权」不推成「应弃权」 | "
          "★与「仅收藏」同族, 已并入同一份交办件)")
