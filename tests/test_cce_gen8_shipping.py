#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上线配置那一轮的闸 —— 钉住 FAIL、钉住「不替换生产」、钉住我超了的那 1 次。"""
import json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = json.loads((ROOT / "tests/data/gen8_shipping_result.json").read_text(encoding="utf-8"))
A = json.loads((ROOT / "tests/data/local_contract_assertions_v2.json").read_text(encoding="utf-8"))
P = json.loads((ROOT / "tests/data/gen8_shipping_prereg.json").read_text(encoding="utf-8"))


def test_assertions_v2_were_frozen_before_any_call_and_predicted_the_failure():
    assert "一次调用都没发" in A["★★★冻结时点"]
    assert "很可能 FAIL" in A["★★★预期后果_先写下"], \
        "★ 收紧判据前必须**先写下预期后果**, 否则事后说「早知道」不算数"
    n = A["统计"]["已裁定断言"]
    assert n == 82, f"★ 断言数变了({n}) —— 若是有意修订请同时更新本断言并说明"


def test_verdict_flipped_to_pass_but_production_is_still_not_replaced():
    """★★★ 2026-09-10 离线复核后, 原判 FAIL 已改判 PASS(74 条)。
    本断言随之翻面 —— 但**「不替换生产」这一条不许跟着翻**。"""
    assert R["★★★结论"].startswith("**PASS(本测试范围, 74 条断言)**"), R["★★★结论"]
    assert "原判 FAIL 已按授权的勘误路径改判" in R["★★★结论"]
    # ★★ 第九轮收窄: 结论行必须同时说出「是否合规**仍未决**」, 不许只说改判
    assert "仍未决" in R["★★★结论"], \
        "★★★ 改判说了, 但没说「指控依据被撤销 ≠ 输出已证明正确」—— 这正是第九轮点名要收窄的"
    assert "仍不替换生产" in R["★★★结论"], "★★★ 改判了但刹车没了 —— 这正是我最该被抓的形态"
    f = R["★★★★2026-09-10 离线复核后改判"]
    assert len(f["★★★仍不替换生产(四条)"]) == 4
    assert "这个 PASS 更弱不是更强" in "".join(f.keys())
    # ★ 三条违例的原记录必须仍在, 不许因改判而删除
    assert len(R["★★★三个违例"]) == 3, "★ 改判后把原违例记录删了 —— 勘误要求保留原记录"
    assert "验收通过后" in R["★owner 批准的是什么"] and "不替换" in R["★owner 批准的是什么"]
    # ★ 生产确实没被改
    prod = (ROOT / "scripts/cce_knot_classify.py").read_text(encoding="utf-8")
    assert "cce_stage2_candidate" not in prod, "★ 验收 FAIL 却已把候选接进生产"
    return R["★★★三个违例"]


def test_criterion_was_not_loosened_after_seeing_failure():
    assert "不得改成「多数通过即可」" in R["★★★判据不放宽"]
    assert "不得把这三条改标为「原来有争议」" in R["★★★判据不放宽"]


def test_v2_table_is_credited_with_catching_what_v1_missed():
    assert "当场抓住" in R["★★这正是 v2 断言表被建出来要抓的东西"]
    assert "上一轮的 PASS 确实是判据窄的产物" in R["★★这正是 v2 断言表被建出来要抓的东西"]


def test_downstream_claims_were_downgraded_with_their_premise():
    """★★★ 我刚写下「下游主张必须跟前提一起降级」, 然后差点在同一份文件里漏掉。
    ⇒ 单列成清单并钉住, 不靠记性。"""
    c = R["★★★★下游主张随前提降级的清单"]
    assert len(c["已随之降级的下游主张"]) == 3
    for x in c["已随之降级的下游主张"]:
        assert x["依赖的前提"] and ("降级" in x["现状"] or "撤回" in x["现状"] or "条件性" in x["现状"])
    # ★ 也要钉住**没受影响的**不许被一起降级(过度更正同样是错)
    assert len(c["★未受影响的"]) == 4
    assert any("噪声内" in x for x in c["★未受影响的"])


def test_decision_tree_effect_is_not_claimed():
    d = R["★★★decision_tree 开 vs 关_不得当成效应"]
    assert d["树关(gen7) 的 display 违例"] == 4 and d["树开(gen8) 的 display 违例"] == 3
    assert "落在噪声内" in d["★★不能说树开更好"]
    # ★★★ 那条观察已随前提降级为**条件性**, 断言随之改
    o = d["★一条值得记的观察(不是结论)"]
    assert "随前提一起降级" in o and "条件性观察" in o
    assert "原文保留" in o, "★ 降级要保留原文, 不是删掉"


def test_the_original_item_is_unchanged_across_three_generations():
    t = R["★★★引发一切的那道题"]["C_仅收藏_0"]
    assert t["旧代"] == t["候选(树关)"] == t["上线(树开)"] == "suspend"
    assert "一动没动" in R["★★★引发一切的那道题"]["★"]


def test_budget_overrun_is_reported_not_hidden():
    """★★★ 我超了自己定的当日上限 1 次。必须**主动记**, 且必须点明机制缺口。"""
    b = R["★★★我超了自己定的账_必须先说"]
    assert "353" in b["实际"] and "超 1 次" in b["实际"]
    assert "没写进代码" in b["★为什么会超"], "★ 必须点明: 跨轮上限只在文档里"
    assert "第 5 次" in b["★★这是同型错误"]
    assert "立即停止" in b["★处置"]


def test_headline_denies_what_it_cannot_claim():
    s = R["★★★本轮实际证明了什么"]
    for must in ("不证明**候选比旧代差", "不证明**决策树无用", "不证明**这三条的正确标签"):
        assert must in s, f"★ 缺少否认: {must}"


def test_owner_memo_exists_and_claims_no_evidence_authority():
    m = (ROOT / "OWNER_DECISION_log_2026-09-09_to_11.md").read_text(encoding="utf-8")
    assert "不能**用你的签字补出候选缺失的验证证据" in m
    # ★ 第八轮把这条改精确了 —— 钉住**新措辞**, 且它比旧的更强
    assert "不是**规范正确性或标签真值的证据**" in m or "不是**规范正确性或标签真值的证据" in m, \
        "★ 必须挡住「三代一致 ⇒ 现状正确」这条诱人的错推"
    assert "不能当成三个独立的语义裁决" in m, "★ 三代一致不是三次独立裁决"
    # ★★ A/B/C 不是互斥三选一 —— 交办件已改为分层, 断言随之改
    assert "这不是三选一，是三个正交的层" in m, "★ 交办件还是三选一结构 —— 第八轮已判它不互斥"
    for layer in ("第一层 · 理由要求怎么定", "第二层 · 允许使用哪些证据", "第三层 · 证据不足时怎么处理"):
        assert layer in m, f"★ 交办件缺分层: {layer}"
    for opt in ("**A**", "**B1**", "**B2**", "**D · 固定上下文**", "**C · 弃权**"):
        assert opt in m, f"★ 交办件缺选项 {opt}"
    # ★ 标题不得预判为「无理由」
    assert "「收藏 + 未来准备状态」表达，是否满足 suspend 的理由要求？" in m, \
        "★ 待决问题的表述又变回预判了"


if __name__ == "__main__":
    test_assertions_v2_were_frozen_before_any_call_and_predicted_the_failure()
    test_verdict_flipped_to_pass_but_production_is_still_not_replaced()
    test_criterion_was_not_loosened_after_seeing_failure()
    test_v2_table_is_credited_with_catching_what_v1_missed()
    test_downstream_claims_were_downgraded_with_their_premise()
    test_decision_tree_effect_is_not_claimed()
    test_the_original_item_is_unchanged_across_three_generations()
    test_budget_overrun_is_reported_not_hidden()
    test_headline_denies_what_it_cannot_claim()
    test_owner_memo_exists_and_claims_no_evidence_authority()
    print("test_cce_gen8_shipping: OK ("
          "★★★★原判 FAIL(3 违例/82 条) —— **2026-09-10 离线复核后改判 PASS(0 违例/74 条)**: "
          "8 条 display 断言经复核**不可由冻结合同推出**已撤销, 那 3 个违例全落在这 8 条上 | "
          "★★★但**仍不替换生产**, 四条刹车: DEV-001 偏离 · **表从 82 缩到 74 ⇒ 证据更弱不是更强** · "
          "撤销项变成**新的 owner 待决项** · 旧缺陷不因候选 PASS 而结案 | "
          f"★三条同形: display 判在「已决定但**尚未拿到机器**」的文本上 | "
          "★★v1 那 12 条**看不见**这三条, v2 逐结查判别式后当场抓住 ⇒ 上轮 PASS 是判据窄的产物, **已证实** | "
          "★★★★「把规则送进 prompt ≠ 模型会遵守」这条**随前提一起降级为条件性** —— "
          "它依赖「模型违反了规则」, 而该前提已随 display 断言撤销; "
          "**三条下游主张已单列成清单**(另两条: 合同无归宿=已撤回 · display→itch 断路=已降级), "
          "同时钉住**四条未受影响的不许被过度更正** | "
          "★树开 3 vs 树关 4 **落在噪声内**(逐题翻转率 3/22), 不得当效应 | "
          "★★★C_仅收藏_0 三代**全是 suspend, 一动没动** | "
          "★我超了当日上限 **1 次**(353/352), 机制缺口=**跨轮上限只在文档里不在代码里**, 同型第 5 次)")
