"""★★★ suspend 的 2×2 析因挑战 —— 四条预注册预测的判决。零 API, 数字现算。

## 结果
| | MiniMax 五员 | GLM 跨家族 |
|---|---|---|
| **F1** 悬置是必要的 | 95.0% vs 28.3%, Fisher p≈0 ✅ | 100% vs 10%, p=3e-05 ✅ |
| **F2** 问句不改变判定 | 差 **−0.1** ✅ | 差 **0.0** ✅ |
| **F3** 负例不许触发 | ❌ 「已决定,等打折下单」**8/10** | ❌ 「之前没定现在决定了」**2/2** |
| **F4** 跨家族同向 | ✅ | |

## ★★★ 诊断(2026-09-08 **更正**: 原归因错了)
**现象不变**: MiniMax 五员在「已经决定买 A, 等打折下单」上**全票判 suspend, 权重 0.9~1.0**
—— **不是不确定, 是高度确信地判错。**

★★★ **但原来的归因是错的。** 我写「缺陷在 `hard_discriminant` 里『等XX再说』这处措辞歧义」——
实测(零 API, 见 test_the_defect_is_an_omission_in_what_actually_reaches_the_prompt):
· `hard_discriminant` **不进 prompt**(KNOT_BRIEF 只注入 key/name/signature/behavior[:70]);
· **「等XX再说」这五个字在闸的 prompt 里一次都没出现过** —— 模型从没看见它。
⇒ **拿一个模型看不见的短语解释模型的行为, 是一条讲得通但为假的因果。**

★★ 更正后的归因: 进 prompt 的三处**全都没有排除「决定已作出、只是执行延后」** ——
· `signature.time` = 「**未来**(决策悬置)」 ← 「等打折下单」在时间上正是「未来」
· `behavior` 含「**收藏不买**」 ← 与「已决定但还没下单」相容
· 决策树第 4 条「明确悬置决策(还没定/再看看+犹豫理由)」 ← 不含歧义, **但也不排除执行延后**
⇒ 缺陷是**遗漏**, 不是**歧义措辞**。这也正是 V1 修法要补的东西(往负例里加「决定已作出、
   延后的只是执行/购买时点」), 所以**修法的落点没错, 错的是我写的病因。**

★★ 这比「构念坏了」**小得多也具体得多**, 且**直接解释**自然评论上那 5 条为什么不稳:
自然评论里「等XX」很常见, 其中一部分是执行延后 ⇒ 都被吸进 suspend ⇒ 标注者切分不同 ⇒ 内部散。

## ★★★ 我的一条预测被自己的实验推翻
我写过「那次改稿可能根本不是姿态变了, **是句式变了**」。**F2 证伪**: 差只有 −0.1 / 0.0。
⇒ 「降为 modifier」那条后备路线**不能**用「句式驱动」当理由。

## ★ 本闸也钉住: 本轮**没有**处置
修法是**看到 F3 失败之后**想到的 ⇒ 用本轮 34 题确认它就是**用结果选规则**。
判别式**未动**(现算确认)。
"""
import json
import pathlib
from math import comb

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT / "tests/data/suspend_factorial_result.json"
P = ROOT / "tests/data/suspend_factorial_prereg.json"
V2 = ROOT / "tests/data/suspend_disposition_v2_prereg.json"
_j = lambda p: json.loads(p.read_text(encoding="utf-8"))


def _load_run_gates():
    """★★★ 2026-09-11: 原先这里直接 `import run_gates`, 而它 import 时就读
    `os.environ["MINIMAX_API_KEY"]` ⇒ **没有 key 就整条判红**, 闸变成「有没有配 key」的探测器,
    而不是它自称要测的东西。走已建好的离线装置(先设假环境变量再 import), 零网络。"""
    import sys as _s
    _s.path.insert(0, str(ROOT / "probes"))
    import accuracy_offline_harness as H
    with H._Tripwire() as tw:
        m = H.load()
    assert not tw.tripped, f"★★★ 加载闸模块时发生了网络连接: {tw.tripped}"
    return m

def _fisher(a, b, c, d):
    n1, n2, k = a + b, c + d, a + c
    return sum(comb(n1, i) * comb(n2, k - i) for i in range(a, min(n1, k) + 1)) / comb(n1 + n2, k)


def test_f1_passed_so_the_necessary_condition_is_being_used():
    """★★ 第一格「代理线索越权」**被排除** —— 这是本轮最重要的阴性结果。"""
    d = _j(R)
    for fam in ("MiniMax五员", "GLM跨家族"):
        f1 = d[fam]["F1_悬置是必要的"]
        assert f1["verdict"] == "PASS", f"★ {fam} 的 F1 不再通过: {f1}"
        assert f1["fisher_p"] < 0.05
    # ★ 现算 MiniMax 侧的 Fisher
    p = _fisher(57, 3, 17, 43)
    assert p < 1e-6, f"★ 现算 Fisher {p:.2e} 与「p≈0」不符"
    t = d["★★★diagnosis"]["★which_of_the_four_cells"]
    assert "被排除" in t and "不是" in t and "代理线索越权" in t


def test_f2_refuted_my_own_prediction():
    """★★★ 我猜「是句式变了」—— 被自己的实验推翻, 必须留档。"""
    d = _j(R)
    for fam, lim in (("MiniMax五员", 0.20), ("GLM跨家族", 0.20)):
        f2 = d[fam]["F2_问句不该改变判定"]
        assert f2["verdict"] == "PASS", f"★ {fam} 的 F2 不再通过"
        assert abs(f2["P_Q - P_noQ"]) <= lim
    t = d["★★★diagnosis"]["★★★a_prediction_of_mine_was_refuted"]
    assert "证伪" in t and "不是句式" in t, "★★★ 「我的预测被推翻」这条不见了"
    # ★ 且它必须影响后续路线
    v = _j(V2)["★★★what_the_factorial_round_found_2026-09-08"]["★one_prediction_of_mine_was_refuted"]
    assert "不能" in v and "句式驱动" in v, "★ 「modifier 路线不能用句式驱动当理由」这条不见了"


def test_f3_failed_and_both_families_failed_differently():
    """★★ 两个家族都在「决定已作出」上失败, 但失败模式不同。"""
    d = _j(R)
    mm = d["MiniMax五员"]["F3_负例不许触发"]
    gl = d["GLM跨家族"]["F3_负例不许触发"]
    assert "FAIL" in mm["verdict"] and "已决定_延后执行" in mm["verdict"]
    assert "FAIL" in gl["verdict"] and "历史悬置_现已决定" in gl["verdict"]
    assert mm["per_group"]["已决定_延后执行"]["rate"] >= 0.7, "★ MiniMax 那 80% 变了"
    assert gl["per_group"]["历史悬置_现已决定"]["rate"] >= 0.9, "★ GLM 那 100% 变了"
    t = d["★★★diagnosis"]["★★★the_exact_defect"]["★glm_fails_differently"]
    assert "失败模式不同" in t and "执行延后" in t and "历史悬置短语" in t


def test_the_defect_is_an_omission_in_what_actually_reaches_the_prompt():
    """★★★ 2026-09-08 更正: 原判据断言「判别式里有『等XX再说』」—— **归因错了**。

    `hard_discriminant` 不进 prompt。本条改为现算两件事:
    ① 「等XX再说」**确实没进** prompt ⇒ 它不可能是病因;
    ② 进 prompt 的三处**确实都没有**排除「决定已作出、执行延后」⇒ 缺陷是**遗漏**。
    """
    RG = _load_run_gates()
    fed = RG.KNOT_BRIEF + RG.DECISION_TREE + RG.NEGATIVE_EXAMPLES + RG.DIST_TMPL
    assert "等XX再说" not in fed, (
        "★★ 「等XX再说」现在进 prompt 了 —— 若是有意接入, 原归因可能重新成立, "
        "请重新判定病因, 别让这条更正继续挂着")
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    k = [x for x in taxo["knots"] if x["key"] == "suspend"][0]
    assert "等XX再说" in k["hard_discriminant"], "★ 判别式原文变了, 请复核本条更正"
    # 进 prompt 的三处都在(它们是缺陷的载体, 修法没动它们)
    assert k["signature"]["time"] == "未来(决策悬置)" and "未来(决策悬置)" in fed
    assert "收藏不买" in k["behavior"] and "收藏不买" in fed
    # ★★★ 2026-09-09 更新: 本闸原来断言「prompt 里**没有**排除执行延后的字样」——
    #   那是在钉住**缺陷仍在**。GATE_PROTOCOL_CHANGE v1→v2 已经把它补上了,
    #   于是这条断言判红并写着「请更新本闸与诊断」。**闸判得对, 现在照做。**
    #   ⇒ 断言反转: 补丁必须**在 prompt 里**, 且**只在负例块里**(载体三处一字未动)。
    for marker in ("购买时点", "决定已作出", "决策对象上的决定尚未作出"):
        assert marker in fed, (
            f"★★★ 修法的关键词「{marker}」不在闸 prompt 里 —— "
            "要么修法被回滚了, 要么组装链路断了。两种都要立刻查。")
    _RG = RG
    assert "购买时点" in _RG.NEGATIVE_EXAMPLES, "★ 补丁必须落在**负例块**"
    assert "购买时点" not in _RG.KNOT_BRIEF and "购买时点" not in _RG.DECISION_TREE, (
        "★★ 补丁不该出现在 KNOT_BRIEF 或决策树里 —— 修法只改一个字段, "
        "出现在别处说明改动比声称的大")
    assert _RG.GATE_PROTOCOL_VERSION >= 2, "★ 补丁在 prompt 里但闸协议版本没换代 —— 静默换闸"

def test_this_is_smaller_than_construct_failure():
    """★★ 结论必须写明: 这比「构念坏了」小得多也具体得多。"""
    t = _j(R)["★★★diagnosis"]["★★what_this_changes"]
    assert "比「构念坏了」" in t and "小得多" in t
    assert "直接解释" in t and "执行延后" in t, "★ 「它解释了自然评论为何不稳」这条不见了"


def test_no_disposition_and_the_fix_is_frozen_not_applied():
    """★★★ 修法是看到结果后想到的 ⇒ **不许用本轮题确认**。

    ★ 2026-09-09 注: 修法后来**确实实施了**(GATE_PROTOCOL_CHANGE v1→v2), 但那是靠
      **另一批 22 道全新题**确证的。本条断言的是**析因那一轮**的纪律 —— 历史陈述, 仍成立,
      **不因后来实施而失效**。抹掉它等于抹掉「当时没有拿本轮题去确认」这个事实。
    """
    d = _j(R)["★★★diagnosis"]["★★still_no_disposition"]
    assert "本轮仍不改判别式" in d and "SYNTHETIC_DIAGNOSTIC" in d
    v = _j(V2)["★★★what_the_factorial_round_found_2026-09-08"]
    assert "不在本轮实施" in v["★★★the_fix_to_be_frozen_next_round"]
    assert "用结果选规则" in v["★★★why_it_cannot_be_confirmed_by_this_round"]
    assert "未参与本轮" in v["★★★why_it_cannot_be_confirmed_by_this_round"]


def test_the_prereg_was_frozen_first():
    """★ 题集校验和与四条预测必须在预注册里, 且标为合成诊断集。"""
    p = _j(P)
    assert p["design"]["sha256"] == "8a25dc3cb6db472d", "★ 题集校验和变了"
    for f in ("F1_悬置命题是必要的", "F2_问句形式不该改变判定", "F3_负例不许触发", "F4_跨家族同向"):
        assert f in p["★★★falsifiable_predictions"], f"★ 预测 {f} 不见了"
    assert "SYNTHETIC_DIAGNOSTIC" in json.dumps(p, ensure_ascii=False)
    assert "不并入自然语料" in json.dumps(p, ensure_ascii=False)


def _reverse_checks():
    n, g = 0, globals()
    import copy
    saved = g["_j"]
    d = saved(R)
    bad = copy.deepcopy(d)
    bad["★★★diagnosis"]["★★★a_prediction_of_mine_was_refuted"] = "句式是驱动因素。"
    g["_j"] = lambda p: bad if p == R else saved(p)
    try:
        test_f2_refuted_my_own_prediction()
        raise SystemExit("★ 反向验证失败: 把被推翻的预测改回来后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    bad2 = copy.deepcopy(d)
    bad2["MiniMax五员"]["F3_负例不许触发"]["verdict"] = "PASS"
    g["_j"] = lambda p: bad2 if p == R else saved(p)
    try:
        test_f3_failed_and_both_families_failed_differently()
        raise SystemExit("★ 反向验证失败: 把 F3 改成 PASS 后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    bad3 = copy.deepcopy(d)
    bad3["★★★diagnosis"]["★★still_no_disposition"] = "已修判别式。"
    g["_j"] = lambda p: bad3 if p == R else saved(p)
    try:
        test_no_disposition_and_the_fix_is_frozen_not_applied()
        raise SystemExit("★ 反向验证失败: 声称已修后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_j"] = saved
    return n


if __name__ == "__main__":
    test_f1_passed_so_the_necessary_condition_is_being_used()
    test_f2_refuted_my_own_prediction()
    test_f3_failed_and_both_families_failed_differently()
    test_the_defect_is_an_omission_in_what_actually_reaches_the_prompt()
    test_this_is_smaller_than_construct_failure()
    test_no_disposition_and_the_fix_is_frozen_not_applied()
    test_the_prereg_was_frozen_first()
    n = _reverse_checks()
    d = _j(R)
    print(f"test_cce_suspend_factorial: OK ("
          f"★F1 ✅**代理线索越权被排除**(95.0% vs 28.3%, Fisher 现算 <1e-6) | "
          f"★★★F2 ✅**推翻我自己的预测**(问句 vs 陈述句差只有 −0.1/0.0, 不是句式驱动) | "
          f"★★F3 ❌ 两家族**失败模式不同**: MiniMax 被**执行延后**骗 8/10, GLM 被**历史悬置短语**骗 2/2 | "
          f"F4 ✅ 同向 | "
          f"★★★缺陷**更正**: 不是判别式的措辞歧义(「等XX再说」现算确认**根本不进 prompt**), "
          f"而是进 prompt 的三处**都遗漏了**排除「决定已作出·执行延后」"
          f"(★ 该遗漏已由 GATE_PROTOCOL_CHANGE v1→v2 补在**负例块**, 载体三处一字未动) | "
          f"⇒ 比「构念坏了」**小得多也具体得多** | "
          f"★**析因那一轮**修法已冻结未实施(看到结果后想到的, 不许用本轮题确认); "
          f"后由**另一批 22 道全新题**确证, 再经 GATE_PROTOCOL_CHANGE v1→v2 实施 | "
          f"{n} 条反向验证判红)")
