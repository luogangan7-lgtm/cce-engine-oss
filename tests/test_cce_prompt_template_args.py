"""每一处 `DIST_TMPL.format(...)` 都必须填满模板的占位符 —— 零 API。

## 为什么
2026-09-07 真跑九结验收时, 第一步就崩:
`KeyError: 'decision_tree'` @ accuracy/run_gates.py:291。
`qualify()`(标注者资格考)只填了 `brief`/`body`, 漏了 `decision_tree`/`negative_examples`,
而正式标注路径(:107)四个都填。

★★ 后果不是「资格考不准」, 是 **qualify() 一次都没跑通过** ——
   而它是 `main()` 的第一步 ⇒ **整个验收闸根本跑不起来**。
★★★ 于是 `annotation_protocol.gate_record` 里那句
   「G-K1 v5 通过(2026-08-07)」只能来自 `qualify()` 被加进来**之前**的版本。
   有人写了资格考、写了「本次起**强制执行**」的注释, 而这段代码**从未执行**。

## 这条闸抓的是一类, 不是一个
任何新增的 prompt 构造路径漏填占位符, 都会在**运行时**才炸,
而验收闸的运行需要 API key ⇒ 平时没人跑 ⇒ **崩溃可以潜伏数月**。
本闸在**静态**层面把它抓住: 解析源码里每一处 `.format(` 调用的关键字参数,
与模板的占位符集合比对。
"""
import ast
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIMAX_API_KEY", "dummy-for-import-only")
sys.path.insert(0, str(ROOT / "accuracy"))
sys.path.insert(0, str(ROOT / "scripts"))

SRC_PATH = ROOT / "accuracy" / "run_gates.py"
SRC = SRC_PATH.read_text(encoding="utf-8")


def _placeholders_of(tmpl_name):
    import run_gates as RG
    return set(re.findall(r"\{(\w+)\}", getattr(RG, tmpl_name)))


def _format_calls(src, tmpl_name):
    """找出源码里每一处 `<tmpl_name>.format(...)`, 返回它填了哪些关键字。"""
    out = []
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "format"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == tmpl_name):
            out.append((node.lineno, {kw.arg for kw in node.keywords if kw.arg}))
    return out


def test_every_dist_tmpl_format_supplies_all_placeholders():
    need = _placeholders_of("DIST_TMPL")
    calls = _format_calls(SRC, "DIST_TMPL")
    assert calls, "★ 一处 DIST_TMPL.format 都没找到 —— 检查解析是否失效"
    missing = [(ln, sorted(need - got)) for ln, got in calls if need - got]
    assert not missing, (
        "★★ 这些 DIST_TMPL.format 漏填占位符, 运行时会 KeyError:\n  "
        + "\n  ".join(f"{SRC_PATH.name}:{ln} 缺 {m}" for ln, m in missing)
        + f"\n模板需要: {sorted(need)}"
    )


def test_qualify_uses_the_same_template_as_production():
    """★ qualify() 的注释写着「用与正式标注**完全相同的模板**」—— 那就必须真的相同。"""
    calls = _format_calls(SRC, "DIST_TMPL")
    argsets = {frozenset(got) for _, got in calls}
    assert len(argsets) == 1, (
        f"★ 不同调用点填的占位符集合不一致: {[sorted(a) for a in argsets]} —— "
        "资格考与正式标注若用不同的 prompt, 考的就不是同一件事"
    )


def test_both_paths_actually_render():
    """静态检查之外再真渲染一次 —— 零 API, 只是字符串格式化。"""
    import run_gates as RG
    need = _placeholders_of("DIST_TMPL")
    kw = {k: f"<{k}>" for k in need}
    s = RG.DIST_TMPL.format(**kw)
    assert len(s) > 100
    # ★ 不能简单查 "{" —— 模板里合法含 `{{"knots": …}}`(输出 JSON 示例),
    #   format 之后它变成单花括号, 那是**正确渲染**的结果, 不是残留占位符。
    #   第一版正是这么写的, 当场判红。⇒ 只查**具名占位符**是否都被替换掉了。
    import re as _re
    left = [m for m in _re.findall(r"\{(\w+)\}", s) if m in need]
    assert not left, f"★ 这些占位符没被替换: {left}"
    for k in need:
        assert f"<{k}>" in s, f"★ 占位符 {k} 的值没出现在渲染结果里"


def _reverse_checks():
    n = 0
    g = globals()
    saved = g["SRC"]
    # ① 注入一处漏填的 format ⇒ 必须红
    g["SRC"] = saved + '\n_ = DIST_TMPL.format(brief="b", body="c")\n'
    try:
        test_every_dist_tmpl_format_supplies_all_placeholders()
        raise SystemExit("★ 反向验证失败: 注入漏填的 format 后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["SRC"] = saved
    # ② 注入一处占位符集合不同的 format ⇒ 一致性断言必须红
    g["SRC"] = saved + '\n_ = DIST_TMPL.format(brief="b", body="c", decision_tree="d")\n'
    try:
        test_qualify_uses_the_same_template_as_production()
        raise SystemExit("★ 反向验证失败: 注入不一致的 format 后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["SRC"] = saved
    return n


if __name__ == "__main__":
    test_every_dist_tmpl_format_supplies_all_placeholders()
    test_qualify_uses_the_same_template_as_production()
    test_both_paths_actually_render()
    n = _reverse_checks()
    calls = _format_calls(SRC, "DIST_TMPL")
    print(f"test_cce_prompt_template_args: OK ({len(calls)} 处 DIST_TMPL.format 全部填满 "
          f"{sorted(_placeholders_of('DIST_TMPL'))} | 资格考与正式标注用同一套占位符 | "
          f"真渲染无残留占位符 | {n} 条反向验证判红)")
