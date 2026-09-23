"""★★★ 「仅收藏」的退化根因是**两个结共用同一个行为标记且无优先级** —— 不是负例不够。零 API。

## 静态检查(网页版 GPT 要求做的, 结论比「30%→50%」具体得多)
· 「收藏不买」**同时**出现在 **itch** 与 **suspend** 的 behavior 里, **无任何限定**
· 两者 time 高度重叠: 「未来」 vs 「未来(决策悬置)」
· 新负例只说了「什么时候不判 suspend」, **没说「收藏不买本身不构成充分条件」**
⇒ **冲突没被解决, 只是被绕过。**

## 退化的精确形状
C_仅收藏_0: V0 **suspend 3 / itch 2**(分裂) → V1 **suspend 5/5**(全票)
C_仅收藏_1: 三方一致判 reward, 没动
⇒ 退化**集中在一题**, 是**把分裂推成了一致的错误** —— 又一个「一致地错」, 这次是 v2 造的。

## ★★ 本闸不修, 只钉住三件
① 冲突**仍然存在**(两个结共用标记 + 无优先级声明) —— 一旦被解决, 本闸红并要求更新诊断
② **不许**用「再加一条负例」当修法(GPT 明确反对: 用一条负例压住上一条的副作用)
③ 「原四条判据全过」**不能**替这个新发现的缺陷免责
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIMAX_API_KEY", "ZERO_API_TEST_SENTINEL_NOT_A_KEY")
sys.path.insert(0, str(ROOT / "accuracy"))
DOC = ROOT / "tests" / "data" / "only_bookmark_rule_conflict.json"
MARK = "收藏不买"


def _taxo():
    return json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))


def _doc():
    return json.loads(DOC.read_text(encoding="utf-8"))


def test_the_marker_is_still_shared_by_two_knots():
    """★★★ 根因: 同一个行为标记落在两个结上。修好了本闸会红并要求更新诊断。"""
    ks = [k["key"] for k in _taxo()["knots"] if MARK in k["behavior"]]
    assert set(ks) == {"itch", "suspend"}, (
        f"★★ 「{MARK}」现在落在 {ks} 上(原为 itch+suspend) —— "
        "若冲突已被解决, **请更新 tests/data/only_bookmark_rule_conflict.json 的诊断**, "
        "别让一句过时的根因继续挂着")


def test_no_priority_rule_was_added_to_the_prompt():
    """★ 冲突未解决的第二个证据: prompt 里**没有**声明 itch/suspend 在该标记上的优先级。"""
    import run_gates as RG
    fed = RG.KNOT_BRIEF + RG.DECISION_TREE + RG.NEGATIVE_EXAMPLES
    assert MARK in fed, f"★ 「{MARK}」不在 prompt 里了 —— 诊断的前提没了"
    for prio in ("收藏不买本身不构成", "优先级", "先判 itch", "先判 suspend"):
        assert prio not in fed, (
            f"★ prompt 里出现了「{prio}」—— 优先级规则可能已加, 请重跑成对回归并更新诊断")


def test_the_fix_was_not_another_negative_example():
    """★★ GPT 明确反对「用一条负例压住上一条负例的副作用」。钉住我没那么做。"""
    d = json.dumps(_doc(), ensure_ascii=False)
    assert "不再堆负例" in d and "用一条负例压住上一条负例的副作用" in d, "★ 这条自我约束不见了"
    k = [x for x in _taxo()["knots"] if x["key"] == "suspend"][0]
    assert MARK not in k["negative_examples_prompt"], (
        f"★★★ suspend 的负例里出现了「{MARK}」—— 那正是被否决的修法路径(堆负例)。"
        "根因是**规则优先级冲突**, 要改的是分类合同, 不是负例。")


def test_the_four_criteria_do_not_absolve_it():
    """★★★ 「原四条判据全过」不能替这个新发现的缺陷免责。"""
    d = json.dumps(_doc(), ensure_ascii=False)
    assert "预注册控制的是结论形成过程, 不是对新发现缺陷的免责条款" in d, \
        "★★ 这句定性不许删 —— 它是「ALL_PASS 掩盖了一个反向组」的直接对策"
    assert "不回滚≠接受退化" in d or "不回滚, 但不回滚≠接受退化" in d


def test_the_paired_regression_is_registered_with_its_ceiling():
    """★ 成对回归条件已登记, 且写明了它**只能关闭固定用例**, 不能声称语料域已校准。"""
    d = _doc()["★★★处置(照 GPT 的裁定, 不堆负例)"]["③立成对回归条件(本轮只登记, 不改现网)"]
    assert "仅收藏" in d["夹具"] and "决策未定并附理由" in d["夹具"]
    assert "不能" in d["★门槛性质"] and "自然语料域已校准" in d["★门槛性质"], \
        "★★ 必须写明这个工程门槛的天花板, 否则它会被当成域级校准"


def test_the_degradation_shape_is_recorded_not_just_the_percentage():
    """★ 「30%→50%」是个会掩盖形状的数字: 实际是**一题从分裂变全票**。"""
    d = json.dumps(_doc(), ensure_ascii=False)
    assert "suspend 3 / itch 2" in d and "suspend 5/5" in d, "★ 退化的逐题形状不见了"
    assert "一致地错" in d, "★ 「把分裂推成一致的错误」这个定性不许删"
    assert "机理猜测(**未验**)" in d, "★★ 机理必须标为未验 —— 没做拆解实验"


def _reverse_checks():
    n, g = 0, globals()
    saved = g["_taxo"]
    import copy

    # ① 标记不再共用 ⇒ 红(要求更新诊断)
    bad = copy.deepcopy(_taxo())
    for k in bad["knots"]:
        if k["key"] == "itch":
            k["behavior"] = k["behavior"].replace(MARK, "收藏")
    g["_taxo"] = lambda: bad
    try:
        test_the_marker_is_still_shared_by_two_knots()
        raise SystemExit("★ 反向验证失败: 标记不再共用后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_taxo"] = saved

    # ② 有人把标记堆进负例 ⇒ 红
    bad2 = copy.deepcopy(_taxo())
    for k in bad2["knots"]:
        if k["key"] == "suspend":
            k["negative_examples_prompt"] += f"; 仅{MARK}不算"
    g["_taxo"] = lambda: bad2
    try:
        test_the_fix_was_not_another_negative_example()
        raise SystemExit("★ 反向验证失败: 堆负例后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_taxo"] = saved
    return n


if __name__ == "__main__":
    test_the_marker_is_still_shared_by_two_knots()
    test_no_priority_rule_was_added_to_the_prompt()
    test_the_fix_was_not_another_negative_example()
    test_the_four_criteria_do_not_absolve_it()
    test_the_paired_regression_is_registered_with_its_ceiling()
    test_the_degradation_shape_is_recorded_not_just_the_percentage()
    n = _reverse_checks()
    print(f"test_cce_only_bookmark_conflict: OK ("
          f"★★★根因钉住: 「{MARK}」**同时**是 itch 与 suspend 的 behavior 标记, 且 prompt **无优先级声明** | "
          f"退化的**逐题形状**已记(C_仅收藏_0: V0 分裂 3/2 → V1 **全票 5/5**), 不只报「30%→50%」 | "
          f"★★修法**不许是再堆一条负例**(用一条负例压住上一条的副作用) | "
          f"★「原四条全过」**不能替新缺陷免责** | 成对回归已登记且写明天花板 | "
          f"{n} 条反向验证判红)")
