"""★★★ 四个结论**不能再由一个 PASS 串起来** —— 一致性 / 局部规则符合性 / 完整生产重测信度 / 认证资格。零 API。

网页版 GPT-6 Pro 2026-09-09 的收尾句, 本仓接受为常设约束。
本闸逐本核对「有什么」与「**没有什么**」都在, 且四本**不许被合并成一句**。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "tests" / "data" / "four_claims_separate.json"


def _d():
    return json.loads(DOC.read_text(encoding="utf-8"))


def test_all_four_books_exist_and_each_says_what_it_lacks():
    """★ 四本账都在, 且**每一本都写了「没有什么」** —— 只写「有什么」就会被串成一句。"""
    books = _d()["★★四本账, 逐本记清「有什么」与「没有什么」"]
    assert len(books) == 4, f"★★ 四本账变成 {len(books)} 本 —— 合并就是本闸要防的那件事"
    for name, b in books.items():
        assert b.get("有") is not None, f"★ {name} 缺「有」"
        lack = [k for k in b if k.startswith("★没有") or k.startswith("★★★为什么")]
        assert lack, f"★★ {name} **没写「没有什么」** —— 只报有什么就是在为串账做准备"


def test_the_production_retest_book_states_exactly_what_it_has():
    """★★★ 第四本: 有什么就说什么, **且天花板不许被抹**。

    ★ 2026-09-09 本条**出过一次假绿**: 原断言查子串「空的」, 而补进去的新文本里有一句
      「★ 此前是**空的**」—— 于是**事实已经变了, 闸却仍然通过**。
      ⇒ 子串断言在「历史陈述与现状陈述共存」的文本上是不可靠的。改为**结构化断言**。
    """
    b = _d()["★★四本账, 逐本记清「有什么」与「没有什么」"]["④完整生产重测信度"]
    has, lack = b["有"], b["★没有"]
    if "首条局部证据" in has:
        # 已买到首条证据 —— 那就必须同时钉住它的四条天花板
        for must in ("q = 19/22", "不签发", "不是", "自然部署域", "29 条"):
            assert must in has or must in lack, f"★★ 第四本缺天花板「{must}」"
        assert "信度合格" in lack, "★★★ 必须写明**不是**「信度合格」"
        assert "已暴露" in lack, "★★ 必须写明是**已暴露、作者构造**题上的重测"
    else:
        assert has.strip().startswith("**空的"), (
            "★★★ 第四本既不是「空的」也没有「首条局部证据」—— 它被别的读数填进去了? **那是串账**")
    why = b["★★★为什么前三本填不上它"]
    assert "一次生产测量的组成部分" in why and "不可互换" in why


def test_arm_b_is_not_called_production_reliability():
    """★★ arm B 的 JS 是**替代面板**的一致性, 不是生产的信度。这条区分不许糊。"""
    b = _d()["★★四本账, 逐本记清「有什么」与「没有什么」"]["②材料替代面板的一致性(arm B)"]
    assert "不是真实生产分类器的信度" in b["★没有"]


def test_the_local_rule_claim_is_bounded():
    """★ 「1/8 ⇒ 没缺陷」过强 · 「更准」= suspend 假阳性更少, 不是九分类准确率。"""
    b = _d()["★★四本账, 逐本记清「有什么」与「没有什么」"]["③局部规则符合性(今天这一条边界)"]
    assert "0.471" in b["★没有"], "★ 1/8 的精确上限不见了"
    assert "不是九分类准确率" in b["★没有"], "★★ 「更准」的限定不见了"
    assert "v2 0/8" in b["有"] and "v2 1/16" in b["有"], (
        "★★★ 三方同口径表里必须有**当前 v2** —— 只拿旧闸 V0 比就是拿退役仪器代表现行版本")


def test_c_does_not_mean_division_of_labour():
    """★★★ (c) **不是**「闸负责一致、生产负责正确」。这条误读必须被明文挡住。"""
    d = _d()["★★★认证资格(第五本, 也是最要紧的一本)"]
    assert "错误的参考判读没有因为更一致而获得保留资格" in d["★(c) 的正确含义"]
    assert "不产生生产分类器的认证效力" in d["现状"]


def test_the_zero_call_step_changed_the_decision_and_that_is_recorded():
    """★★★ 零调用补表**改变了下一步该不该买** —— 这件事本身必须留档。

    补表前: 「生产更准(3/16 vs 6/16)」⇒ 路线 (a) 值得测。
    补表后: **当前 v2 已是 1/16 与 0/8, 比生产还好** ⇒ 换成生产材料更可能变差。
    ⇒ 我**没有**发起那 220 次。★ 但 (a) 只是优先级下降, **没有被证伪**
      (现有证据只覆盖这一条边界的 16 道构造题, 且题是我出的)。
    """
    d = _d()["★★★零调用补表已经改变了下一步的判断_2026-09-09"]
    assert "它确实改变了判断" in d["★★补完之后发生了什么"]
    n = d["★★★因此我不发起那 220 次"]
    assert "没有被证伪" in n["★★但这不等于 (a) 被否掉"], (
        "★★ 必须写明 (a) 只是优先级下降 —— 否则「不买」会被读成「已排除」")
    assert "自然语料" in n["★★但这不等于 (a) 被否掉"],         "★ 必须写明若要测应在**自然语料**上测, 不是在我出的 22 道边界题上"
    assert "owner 拍板" in n["★★★我不替 owner 决定要不要买"]
    assert "删掉闸独有材料" in d["★还需要注意的一处"] and "不等于" in d["★还需要注意的一处"],         "★★ 「删块 ≠ 换成生产材料」这条区分不许糊 —— 生产还有闸没有的三个字段"


def _reverse_checks():
    n, g = 0, globals()
    saved = g["_d"]
    import copy
    bad = copy.deepcopy(_d())
    bad["★★四本账, 逐本记清「有什么」与「没有什么」"]["④完整生产重测信度"]["有"] = "已由 arm B 提供"
    g["_d"] = lambda: bad
    try:
        test_the_production_retest_book_states_exactly_what_it_has()
        raise SystemExit("★ 反向验证失败: 用 arm B 填第四本后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_d"] = saved

    bad2 = copy.deepcopy(_d())
    del bad2["★★四本账, 逐本记清「有什么」与「没有什么」"]["④完整生产重测信度"]
    g["_d"] = lambda: bad2
    try:
        test_all_four_books_exist_and_each_says_what_it_lacks()
        raise SystemExit("★ 反向验证失败: 四本变三本后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_d"] = saved
    return n


if __name__ == "__main__":
    test_all_four_books_exist_and_each_says_what_it_lacks()
    test_the_production_retest_book_states_exactly_what_it_has()
    test_arm_b_is_not_called_production_reliability()
    test_the_local_rule_claim_is_bounded()
    test_c_does_not_mean_division_of_labour()
    test_the_zero_call_step_changed_the_decision_and_that_is_recorded()
    n = _reverse_checks()
    print(f"test_cce_four_claims_separate: OK ("
          f"★★★四本账各自独立且**每本都写了「没有什么」** | "
          f"④完整生产重测信度**已有首条局部证据**(q=19/22), 且四条天花板逐条钉住"
          f"(不签发信度合格 · 非自然域总体信度 · 已暴露题 · 自然域需 29/59 条) | "
          f"★本条**出过一次假绿**(子串「空的」被「此前是空的」这句满足), 已改为结构化断言 | "
          f"②arm B 不得被叫成生产信度 | ③1/8 的上限 0.471 与「不是九分类准确率」都在 | "
          f"★三方同口径表含**当前 v2**(0/8 · 1/16), 不拿退役的 V0 代表现行版本 | "
          f"★★(c) **不是**「闸负责一致、生产负责正确」 | "
          f"★★★零调用补表**改变了下一步该不该买**(v2 已比生产好 ⇒ 未发起那 220 次), "
          f"且写明 (a) 只是优先级下降**未被证伪** | {n} 条反向验证判红)")
