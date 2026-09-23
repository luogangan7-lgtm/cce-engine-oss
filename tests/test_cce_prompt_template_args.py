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


def _all_templates():
    """★★ 2026-09-07: 原来只查 DIST_TMPL 一个 —— **这条闸有和它要抓的 bug 一样的盲点**。

    当天给模板加 `{unit}` 占位符时, `FACT_TMPL.format(body=...)` 漏填 ⇒ 会 KeyError,
    而本闸**绿着**。⇒ 改为**枚举模块里所有 `*_TMPL`**, 不许再手写名单。
    """
    import run_gates as RG
    return sorted(n for n in dir(RG)
                  if n.endswith("_TMPL") and isinstance(getattr(RG, n), str))


def test_every_template_format_supplies_all_placeholders():
    names = _all_templates()
    assert len(names) >= 2, f"★ 只找到 {names} —— 模板枚举失效了"
    bad = []
    for nm in names:
        need = _placeholders_of(nm)
        for ln, got in _format_calls(SRC, nm):
            if need - got:
                bad.append(f"{SRC_PATH.name}:{ln} {nm}.format 缺 {sorted(need - got)} (需 {sorted(need)})")
    assert not bad, "★★ 这些 .format 漏填占位符, 运行时会 KeyError:\n  " + "\n  ".join(bad)


def test_every_template_actually_renders():
    """★ 每个模板都真渲染一次, 不只 DIST_TMPL。零 API。"""
    import run_gates as RG
    import re as _re
    for nm in _all_templates():
        need = _placeholders_of(nm)
        s = getattr(RG, nm).format(**{k: f"<{k}>" for k in need})
        left = [m for m in _re.findall(r"\{(\w+)\}", s) if m in need]
        assert not left, f"★ {nm} 渲染后仍有占位符: {left}"


def test_unit_label_is_a_measured_variable_not_a_hardcode():
    """★★★ 「给你一条评论」这句话曾经是**硬编**的 —— 而它对 belong 有方向明确的影响。"""
    import run_gates as RG
    assert "unit" in _placeholders_of("DIST_TMPL"), (
        "★★★ DIST_TMPL 里的单元标签又被写死了。它不能硬编: prompt 说「给你一条**评论**」, "
        "而 KNOT_BRIEF 同时说 display=「**评论区**最高质量UGC主力」、belong=「自我暴露式**发帖**」"
        "⇒ 标一条评论时 belong 拿 0 **几乎是被 prompt 指示出来的**。"
        "它必须是**被测变量**(CCE_UNIT_LABEL), 才能把这个效应量出来")
    assert RG.UNIT_LABEL == os.environ.get("CCE_UNIT_LABEL", "评论"), "★ 默认值变了"
    a = RG.DIST_TMPL.format(unit="评论", brief="b", decision_tree="d",
                            negative_examples="n", body="x")
    b = RG.DIST_TMPL.format(unit="帖子", brief="b", decision_tree="d",
                            negative_examples="n", body="x")
    assert a != b and "帖子" in b and "评论" not in b.replace("评论区", ""), \
        "★ 换单元标签后 prompt 没有真的变"


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
        test_every_template_format_supplies_all_placeholders()
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
    test_every_template_format_supplies_all_placeholders()
    test_every_template_actually_renders()
    test_unit_label_is_a_measured_variable_not_a_hardcode()
    test_qualify_uses_the_same_template_as_production()
    test_both_paths_actually_render()
    n = _reverse_checks()
    calls = _format_calls(SRC, "DIST_TMPL")
    print(f"test_cce_prompt_template_args: OK (★**全部 {len(_all_templates())} 个模板**"
          f"{_all_templates()} 的 .format 都填满(此前只查 DIST_TMPL, 与它要抓的 bug 同盲点) | "
          f"资格考与正式标注用同一套占位符 | 每个模板都真渲染 | "
          f"★单元标签是**被测变量**不是硬编 | {n} 条反向验证判红)")
