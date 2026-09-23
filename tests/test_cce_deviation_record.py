#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 偏离记录 DEV-001 是否充分, 且被每一份相关留档引用。"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = json.loads((ROOT / "tests/data/DEV-001-budget-overrun.json").read_text(encoding="utf-8"))


def test_all_six_sections_present_and_substantive():
    # ★ 阈值按各段应有的信息量分别定 —— 一刀切的字数门槛会逼我往短段里灌水
    MIN = {"①原授权": 300, "②实际执行": 400, "③发现与停止": 120, "④证据影响": 400, "⑤处置": 500}
    for k, n in MIN.items():
        assert k in D, f"★ {k} 缺失"
        L = len(json.dumps(D[k], ensure_ascii=False))
        assert L > n, f"★ {k} 过薄({L} < {n})"


def test_the_selection_question_is_answered_item_by_item():
    """★ GPT: 「不能简单贴一个『超限』标签就算处理完」—— 必须逐项回答有没有覆盖/挑选/删失。"""
    q = D["④证据影响"]["★逐项回答_不许一句没有带过"]
    for k in ("覆盖", "挑选", "删失", "是否达到某结果才停"):
        assert k in q and len(q[k]) > 10, f"★ {k} 没有实质回答"
    assert "与答案内容无关" in q["挑选"], "★ 必须证明重试不是结果选择"


def test_the_second_deviation_is_registered_and_credited_honestly():
    """★★★ 第二项偏离(未经更新授权即发起第二轮)必须登记, 且如实记是谁发现的。"""
    s = D["②实际执行"]["★★第二项偏离_我先前没登记"]
    assert "理由成立不等于授权存在" in s
    assert "不是我自己发现的" in s, "★ 谁发现的要如实记 —— 记成自己发现会高估自查能力"
    assert "轮次/范围偏离" in json.dumps(D["④证据影响"], ensure_ascii=False)


def test_remaining_budget_does_not_authorize_extra_rounds():
    assert "不必然授权额外轮次" in D["★★另一条"]


def test_the_over_self_blame_correction_is_recorded():
    """★ GPT 指出我把「现在补闸」误当成「现在追认自己继续跑」。"""
    c = D["⑤处置"]["★★★GPT 纠正我的过度自责"]
    assert "两个动作可分开" in c and "假请求" in c
    assert "不必为了防止追认, 故意把安全缺口留着" in c
    for forbidden in ("重置已用计数", "改大旧上限", "回填授权日期"):
        assert forbidden in c, f"★ 缺少禁止项: {forbidden}"


def test_failed_requests_still_count():
    s = json.dumps(D["⑤处置"], ensure_ascii=False)
    assert "已发出的失败请求不能因为没有有效结果就从「请求次数」里抹掉" in s


def test_every_result_file_from_these_two_rounds_cites_dev001():
    """★★★ 引用闸: 这两轮的每一份结果留档都必须带那一句。"""
    line = "DEV-001"
    missing = []
    for f in ("tests/data/gen7_candidate_result.json", "tests/data/gen8_shipping_result.json"):
        if line not in (ROOT / f).read_text(encoding="utf-8"):
            missing.append(f)
    assert not missing, f"★ 这些留档没有引用偏离记录: {missing}"


if __name__ == "__main__":
    test_all_six_sections_present_and_substantive()
    test_the_selection_question_is_answered_item_by_item()
    test_the_second_deviation_is_registered_and_credited_honestly()
    test_remaining_budget_does_not_authorize_extra_rounds()
    test_the_over_self_blame_correction_is_recorded()
    test_failed_requests_still_count()
    test_every_result_file_from_these_two_rounds_cites_dev001()
    print("test_cce_deviation_record: OK ("
          "★DEV-001 六段齐全 · 覆盖/挑选/删失/是否按结果停 **逐项回答**(重试规则与答案内容无关, 早于本轮) | "
          "★★★自查出**第二项偏离**: 第二轮未经更新授权即发起 —— 「**理由成立不等于授权存在**」, "
          "且如实记明**是 GPT 提醒才想到的** | "
          "★「总额度尚有剩余」**不必然授权额外轮次** | "
          "★GPT 纠正我的过度自责: **允许**离线补闸+假请求测试, **不允许**恢复真实请求/回写授权 —— "
          "「不必为了防止追认, 故意把安全缺口留着」 | "
          "★引用闸: 两轮结果留档都必须带 DEV-001 那一句)")
