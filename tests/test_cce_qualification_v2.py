"""资格考 v2 —— 三态判决, UNRESOLVED **不视同 FAIL**。零 API, 纯函数。

## v1 为什么被废
同一份 5 题考卷、temp=0.0、代码逐字相同, 跑**三次**: M2.7 得 **3/5、5/5、4/5**。
· 实测 **n=5 时任何 cutoff 都做不到 α、β 同时 <5%**(最好的全对判据是 α=0.168 / β=0.226)
  ⇒ **5 题在任何阈值下都不可能做出可靠的二元判决**, 不是调阈值能修的。
· 而那次剔除**损害了指标**: 剔 M2.7 的 4 人面板自助失败率 **23.1%**, 保留它的 5 人 **7.0%**。
· ★★★ 且我的 bootstrap **本身是低估的**: 只重采样条目, 没传播「谁进面板」的随机性。
  传播后 **14.8%**, 且**跑一次得到 5 人面板的概率只有 46%**。

## ★★ 三条最容易被悄悄改回去的性质, 本闸逐条钉住
① **UNRESOLVED 留在 primary 面板里** —— 「若 UNRESOLVED 就排除, 那只是把 FAIL 改名」。
② **判据是不对称的**: DISQUALIFIED 便宜(n=5 时 k<=1 即可), QUALIFIED 昂贵(需 n>=35 全对)。
   ⇒ 资格考**只用于 DISQUALIFY, 不用于 CERTIFY**。v1 恰恰反过来, 那是它乱剔人的根因。
③ **不用点阈值, 用 indifference region**。「Wilson 下界 > 0.80」在小 n 上结构性地要求全对:
   **n=16 之前连全对都不能 PASS**(14/14 下界 0.7847), 16~20 必须全对, 30 题才允许错 1 题。
   ★ 更正: 我第一版写「即使 n=60 也要全对」是**代码 bug**(从 n 往下数取第一个满足的);
     实际 n=60 答对 55 即可。GPT 的原论点没变, 变的是我多加的推论。

★ 本规则据 development 证据设计, **待新数据确证**; 本闸只校验实现与冻结的判据一致。
"""
import json
import os
import pathlib
import sys
from math import comb

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIMAX_API_KEY", "dummy-for-import-only")
sys.path.insert(0, str(ROOT / "accuracy"))
import run_gates as RG  # noqa: E402

PREREG = json.loads((ROOT / "tests/data/annotator_qualification_v2_prereg.json").read_text(encoding="utf-8"))
Q = lambda ms: RG.admit_annotators([{"model": m, "hits": k, "of": n} for m, k, n in ms])


def test_unresolved_stays_in_the_primary_panel():
    """★★★ 最核心: UNRESOLVED **不排除**。改成排除 = 把 FAIL 改名。"""
    a = Q([("a", 5, 5), ("b", 5, 5), ("c", 4, 5)])
    assert a["status"] == "OK"
    assert set(a["admit"]) == {"a", "b", "c"}, f"★★★ UNRESOLVED 被排除了: {a['admit']}"
    assert all(v["state"] == "UNRESOLVED" for v in a["★states"].values())
    assert a["qualified_only"] == [], "★ n=5 不可能有人 QUALIFIED(需 n>=35 全对)"
    assert "不视同 FAIL" in a["reason"]


def test_only_disqualified_is_excluded():
    a = Q([("good", 5, 5), ("mid", 4, 5), ("bad", 0, 5), ("bad2", 1, 5)])
    assert set(a["admit"]) == {"good", "mid"}, f"★ 排除的不是恰好 DISQUALIFIED 那批: {a['admit']}"
    assert set(a["★disqualified"]) == {"bad", "bad2"}


def test_the_bands_are_asymmetric_and_that_is_deliberate():
    """★★ DISQUALIFY 便宜、CERTIFY 昂贵 —— 现算, 不信任落盘。"""
    dq = [k for k in range(6) if RG.qualification_state(k, 5)[0] == "DISQUALIFIED"]
    assert dq == [0, 1], f"★ n=5 的 DISQUALIFIED 带变了: {dq}"
    assert RG.qualification_state(5, 5)[0] == "UNRESOLVED", "★ n=5 全对不该是 QUALIFIED"
    n_cert = next(n for n in range(3, 200) if RG.qualification_state(n, n)[0] == "QUALIFIED")
    assert n_cert >= 30, f"★ 全对时最早能 CERTIFY 的 n = {n_cert}, 应远大于 5"
    assert n_cert == 35, f"★ 现算 {n_cert} != 预注册记的 35 —— 若 p_H 改了请同步"


def test_a_point_threshold_demands_near_perfection_at_small_n():
    """★★ 「Wilson 下界 > 0.80」在小 n 上结构性要求全对 —— 不用点阈值的**可执行**理由。

    ★ 本函数第一版断言「所有 n 都要全对」, **被自己判红** —— 那是我的 bug
      (从 n 往下数取第一个满足的, 永远返回 n)。现在断言的是真实形状。
    """
    need = lambda n, thr: min((k for k in range(n + 1) if RG._wilson(k, n)[0] > thr), default=None)
    assert need(14, 0.80) is None and need(15, 0.80) is None, \
        "★ n=14/15 居然能 PASS 了 —— 那「>=14 与该判据自相矛盾」这条要重写"
    assert need(16, 0.80) == 16 and need(20, 0.80) == 20, "★ 16/20 不再要求全对"
    assert need(30, 0.80) == 29, f"★ n=30 现算需 {need(30,0.80)}, 预期 29(可错 1)"
    assert need(60, 0.80) == 55, f"★ n=60 现算需 {need(60,0.80)}, 预期 55(可错 5)"
    # ★ v2 用的 p_H=0.90 更贵 —— CERTIFY 昂贵那条的量化依据
    assert need(20, 0.90) is None and need(40, 0.90) == 40, "★ p_H=0.90 的成本形状变了"


def test_n5_can_never_separate_at_5pct():
    """★★ 5 题在**任何** cutoff 下都做不到 α、β 同时 <5% —— 现算。"""
    P_ge = lambda k, n, p: sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))
    ok = [t for t in range(6) if P_ge(t, 5, 0.70) < 0.05 and (1 - P_ge(t, 5, 0.95)) < 0.05]
    assert not ok, f"★ n=5 居然有可行 cutoff {ok} —— 那 v1 的问题要重新表述"
    best = min((max(P_ge(t, 5, 0.70), 1 - P_ge(t, 5, 0.95)), t) for t in range(1, 6))
    assert best[0] > 0.15, f"★ n=5 最好也有 {best[0]:.3f} 的误判率(cutoff>={best[1]})"


def test_insufficient_still_withholds_not_falls_back():
    """★ 第一次修的 fail-open **必须仍然有效**。"""
    for ms in ([("a", 0, 5)] * 1 + [("b", 0, 5), ("c", 0, 5)],
               [("a", 5, 5)] + [("b", 0, 5), ("c", 0, 5), ("d", 1, 5)]):
        a = Q([(m + str(i), k, n) for i, (m, k, n) in enumerate(ms)])
        assert a["admit"] is None and a["status"] == "INSUFFICIENT_QUALIFIED_ANNOTATORS"
        assert "不产出判决 != 判决通过" in a["reason"]
    # ★★ 不能用字符串查 —— docstring 里**引用**了被删掉的那行代码作为说明。
    #   今天第二次栽在这上面(第一次是 test_cce_acceptance_gate_failopen)。改用 AST 查真实赋值。
    import ast as _ast
    src = (ROOT / "accuracy/run_gates.py").read_text(encoding="utf-8")
    bad = [n for n in _ast.walk(_ast.parse(src))
           if isinstance(n, _ast.BoolOp) and isinstance(n.op, _ast.Or)
           and any(isinstance(v, _ast.Name) and v.id == "MODELS" for v in n.values)]
    assert not bad, f"★ fail-open 回来了: 源码里出现了 `... or MODELS`(行 {[n.lineno for n in bad]})"


def test_prereg_says_it_awaits_confirmation():
    """★ 规则据 development 证据设计, **不得**拿当天那 81 条当确证。"""
    t = json.dumps(PREREG, ensure_ascii=False)
    assert "待新数据确证" in PREREG["★status"] or "待确证验证" in PREREG["★status"]
    assert "不重跑验收" in t, "★ 「不在 development data 上确证」这条声明不见了"
    assert "伪重复" in t, "★ 三次同卷不是 15 个独立题这条不见了"
    assert "46" in t and "14.8" in t, "★ 面板 46% / 传播后 14.8% 这两个数不见了"


def _reverse_checks():
    n = 0
    real = RG.admit_annotators
    RG.admit_annotators = lambda q: {  # 把 UNRESOLVED 也排除掉
        **real(q), "admit": [m for m, v in real(q)["★states"].items() if v["state"] == "QUALIFIED"]}
    try:
        test_unresolved_stays_in_the_primary_panel()
        raise SystemExit("★ 反向验证失败: 排除 UNRESOLVED 后仍绿")
    except (AssertionError, TypeError):
        n += 1
    finally:
        RG.admit_annotators = real
    real_w = RG.qualification_state
    RG.qualification_state = lambda k, of: ("QUALIFIED" if k / max(of, 1) >= 0.8 else "DISQUALIFIED", (0, 1))
    try:
        test_the_bands_are_asymmetric_and_that_is_deliberate()
        raise SystemExit("★ 反向验证失败: 换回二值点阈值后仍绿")
    except AssertionError:
        n += 1
    finally:
        RG.qualification_state = real_w
    return n


if __name__ == "__main__":
    test_unresolved_stays_in_the_primary_panel()
    test_only_disqualified_is_excluded()
    test_the_bands_are_asymmetric_and_that_is_deliberate()
    test_a_point_threshold_demands_near_perfection_at_small_n()
    test_n5_can_never_separate_at_5pct()
    test_insufficient_still_withholds_not_falls_back()
    test_prereg_says_it_awaits_confirmation()
    n = _reverse_checks()
    n_cert = next(x for x in range(3, 200) if RG.qualification_state(x, x)[0] == "QUALIFIED")
    print(f"test_cce_qualification_v2: OK ("
          f"★★★**UNRESOLVED 留在 primary 面板**(排除它=把 FAIL 改名) | "
          f"只有 DISQUALIFIED 与协议违规才排除 | "
          f"★判据**不对称**: n=5 时 DISQUALIFY 只需 k<=1, 而 CERTIFY 需 n>={n_cert} 全对 "
          f"⇒ 资格考只用于排除, 不用于认证 | "
          f"★「Wilson 下界>0.80」在 n<16 时连全对都不能 PASS ⇒ 点阈值把「证据不足」与「不合格」混成一档 | "
          f"★n=5 任何 cutoff 都做不到 α、β 同时<5% | "
          f"第一次修的 fail-open 仍有效 | 规则**待新数据确证** | {n} 条反向验证判红)")
