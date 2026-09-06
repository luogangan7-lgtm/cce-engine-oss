"""九结验收闸**自己**的闸 —— 它此前有三处 fail-open, 而注释写着「强制执行」。

## 为什么这条闸到今天才有
`accuracy/` 是**九结验收闸本身**(G-K1 分布一致性 / G-K2 成本档预测), 即判断
「这台仪器准不准」的那道闸。而它 `import` 期就取 `MINIMAX_API_KEY`,
于是两轮消融审计的「零 API」纪律把它**结构性排除**了 ——
**审计从未测过自己的验收标准。**

★ 但那三处缺陷是**纯逻辑**, 不需要 API 就能测。零 API 不是不能测的理由,
  只是没人去看。

## 修掉的三处(2026-09-07)
1. `globals()["MODELS"] = passed or MODELS`
   ★★ 零人合格 ⇒ `passed` 为空 ⇒ **静默回退到全员**, 包括上一行刚被打印成
   「★不合格, 剔除」的那些。**打印说剔除, 代码把他们放了回去。**
   ⇒ 「没人合格」与「全员合格」在输出上**不可区分** —— 本项目命名过的 fail-silent。
2. `if len(passed) < 2: print(...)` 之后**照跑**。
   两两一致性在 <2 名标注者上**数学上无定义**, 硬跑出来的数是假的。
3. `overall_pass = gk1["pass"] and gk2["pass"]` —— **资格考只被报告, 不进判决**
   ⇒ 4/5 不合格照样能 overall_pass=True。

★ 而 `qualify()` 的 docstring 自己写着:「协议早已规定, 此前从未执行 ——
  未经资格考的标注者混进平均, **是 G-K1 长期不达标的主要嫌疑**」,
  上方注释写着「本次起**强制执行**」。**注释不是闸。**
"""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIMAX_API_KEY", "dummy-for-import-only")   # import 期只读 env, 不发请求
sys.path.insert(0, str(ROOT / "accuracy"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_gates as RG  # noqa: E402

SRC = (ROOT / "accuracy" / "run_gates.py").read_text(encoding="utf-8")


def _quals(n_ok, total=5):
    return [{"model": f"m{i}", "qualified": i < n_ok} for i in range(total)]


def test_zero_qualified_does_not_fall_back_to_everyone():
    """★★ 核心: 零人合格必须**扣发**, 不许回退到全员。"""
    a = RG.admit_annotators(_quals(0))
    assert a["admit"] is None, (
        f"★★ 零人合格却放行了 {a['admit']} —— `passed or MODELS` 那个 fail-open 回来了。"
        "「没人合格」与「全员合格」不可区分, 是本项目命名过的 fail-silent"
    )
    assert a["status"] == "INSUFFICIENT_QUALIFIED_ANNOTATORS"
    assert "不产出判决 != 判决通过" in a["reason"]


def test_one_qualified_is_also_withheld():
    """两两一致性在 1 名标注者上**数学上无定义** —— 不能硬跑。"""
    a = RG.admit_annotators(_quals(1))
    assert a["admit"] is None, "★ 只有 1 名合格标注者时仍产出了判决 —— 那个数是假的"


def test_two_or_more_qualified_admits_only_the_qualified():
    a = RG.admit_annotators(_quals(2))
    assert a["status"] == "OK"
    assert a["admit"] == ["m0", "m1"], f"★ 准入名单不对: {a['admit']}"
    assert len(a["admit"]) == 2, "★ 不合格者被放了进来"
    b = RG.admit_annotators(_quals(5))
    assert len(b["admit"]) == 5


def test_source_no_longer_contains_the_fail_open():
    """★ 只查**可执行的赋值**, 不查字符串出现。

    第一版写的是 `"passed or MODELS" not in SRC`, 当场判红 ——
    因为 `admit_annotators` 的 docstring **引用了那行被删掉的代码**作为「修了什么」的说明。
    ⇒ 一个把「文档里提到它」当成「代码里还有它」的断言, 会把**留档**判成**回归**。
      判据要盯**行为**(有没有这条赋值), 不是**字面**。
    """
    import ast
    tree = ast.parse(SRC)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            seg = ast.get_source_segment(SRC, node) or ""
            if "passed or" in seg and "MODELS" in seg:
                bad.append(seg.strip()[:80])
    assert not bad, (
        "★★ `passed or MODELS` 那条赋值又回来了 —— 它让零人合格静默变成全员合格:\n  "
        + "\n  ".join(bad))
    # 文档里可以提它(留档), 但必须同时留下它为什么被删
    assert "静默回退到全员" in SRC, "★ 删了那行, 也要留下**为什么删** —— 否则下一个人会加回去"


def test_overall_pass_includes_qualification():
    """★ 资格考必须**进判决**, 不能只被报告。"""
    assert 'annotator_qualification":\n' not in SRC or True  # 结构性检查在下面
    assert '(globals().get("QUAL_REPORT") or {}).get("status") == "OK"' in SRC, (
        "★★ overall_pass 不再包含资格考 —— 那样 4/5 不合格也能判通过"
    )
    assert '"★pass_components"' in SRC, "★ 判决必须拆开报三项, 否则读不出是哪一项挂了"


def test_withheld_run_returns_a_distinct_exit_code():
    """扣发既不是通过也不是崩溃 —— 必须有自己的退出码。"""
    assert "return 2      # ★ 扣发, 不是失败也不是通过" in SRC, \
        "★ 扣发路径没有独立退出码 ⇒ 调用方分不出「扣发」与「跑挂了」"


def _reverse_checks():
    """反向验证: 把三处 fail-open 放回去, 闸必须判红。"""
    n = 0
    orig = RG.admit_annotators

    # ① 退回 `passed or MODELS`
    def failopen(quals):
        passed = [q["model"] for q in quals if q.get("qualified")]
        allm = [q["model"] for q in quals]
        return {"admit": passed or allm, "status": "OK", "reason": "(旧实现)"}

    RG.admit_annotators = failopen
    try:
        for fn in (test_zero_qualified_does_not_fall_back_to_everyone,
                   test_one_qualified_is_also_withheld):
            try:
                fn()
                raise SystemExit(f"★ 反向验证失败: 退回 fail-open 后 {fn.__name__} 仍绿")
            except AssertionError:
                n += 1
    finally:
        RG.admit_annotators = orig

    # ② 源码里的三条结构断言各自可被破坏
    g = globals()
    saved = g["SRC"]
    for name, mutated, fn in (
        ("恢复 passed or MODELS 赋值", saved + "\nMODELS = passed or MODELS\n",
         test_source_no_longer_contains_the_fail_open),
        ("从 overall_pass 里拿掉资格考",
         saved.replace('(globals().get("QUAL_REPORT") or {}).get("status") == "OK"', "True"),
         test_overall_pass_includes_qualification),
        ("去掉扣发退出码",
         saved.replace("return 2      # ★ 扣发, 不是失败也不是通过", "return 0"),
         test_withheld_run_returns_a_distinct_exit_code),
    ):
        g["SRC"] = mutated
        try:
            fn()
            raise SystemExit(f"★ 反向验证失败: 「{name}」后 {fn.__name__} 仍绿")
        except AssertionError:
            n += 1
        finally:
            g["SRC"] = saved
    return n


if __name__ == "__main__":
    test_zero_qualified_does_not_fall_back_to_everyone()
    test_one_qualified_is_also_withheld()
    test_two_or_more_qualified_admits_only_the_qualified()
    test_source_no_longer_contains_the_fail_open()
    test_overall_pass_includes_qualification()
    test_withheld_run_returns_a_distinct_exit_code()
    n = _reverse_checks()
    print("test_cce_acceptance_gate_failopen: OK ("
          "零人合格→扣发(不回退全员) | 1 人合格→扣发(两两一致性无定义) | "
          ">=2 人→只放合格者 | 源码不含 `passed or MODELS` | "
          "overall_pass 含资格考且拆项报告 | 扣发有独立退出码 2 | "
          f"{n} 条反向验证各自判红)")
