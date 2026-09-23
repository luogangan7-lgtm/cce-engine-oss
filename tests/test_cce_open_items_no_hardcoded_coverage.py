#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 「还差什么」那张表里的覆盖率**必须现算**, 不许硬编。

★★★ 为什么要这条(2026-09-11 实际发生):
`cce_open_items.py:320` 把「只覆盖 17.3%」**写死在字符串里**, 且指向 ablation_verdicts_v2.json。
v3 落地后真实数已是文件级 12.89% / 行级 27.95%, 而这张表**永远不会自己更新**。
—— 「过期判决表继续被引用」是本仓登记过的错误族, 这次它出现在**报告「还差什么」的那张表自己**身上,
   而那张表正是我用来回答 owner「可以使用了吗」的东西。**报告层的过期比被报告项的过期更危险。**
"""
import json, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "scripts" / "cce_open_items.py").read_text(encoding="utf-8")
V3 = ROOT / "tests" / "data" / "ablation_verdicts_v3.json"


def _run():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "cce_open_items.py")],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, "★ cce_open_items.py 跑不起来:\n%s" % r.stderr[-800:]
    return r.stdout


def test_no_literal_coverage_percentage_in_source():
    """★★★ 源码里不许出现写死的覆盖率百分比。

    判据只针对**覆盖率语境**的百分比(附近出现「覆盖」二字), 不误伤其它百分比
    (如「12.5%」那种实验读数) —— 会误报的闸不上。
    """
    import ast
    tree = ast.parse(SRC)
    # ★ 用 AST 排除 docstring —— 第一版判据按字符距离取上下文, **误伤了解释这段历史的 docstring 本身**
    #   (它当然会同时出现「覆盖」与「17.3%」)。会误报的闸不上, 所以改成只看**真会进输出的字符串**。
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d = ast.get_docstring(node, clean=False)
            if d:
                docstrings.add(d)
    bad = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        v = node.value
        if v in docstrings:
            continue
        for m in re.finditer(r"\d+\.\d+%", v):
            ctx = v[max(0, m.start() - 60):m.end() + 20]
            if "覆盖" not in ctx:
                continue
            # ★ 旧数字**只能以被撤回的引文形式**出现(与决策单闸同一形状):
            #   必须同时 ① 被「」括住 ② 附近有撤回标记。缺一就是现行主张。
            quoted = "「" in v[max(0, m.start() - 14):m.start()] and "」" in v[m.end():m.end() + 14]
            retracted = any(w in ctx for w in ("原写死", "原先", "先前", "已撤回", "不再硬编", "旧硬编"))
            if quoted and retracted:
                continue
            bad.append((m.group(), "L%s " % node.lineno + " ".join(ctx.split())[:80]))
    assert not bad, ("★★★ 覆盖率百分比被写死在源码里 —— 判决表一更新它就过期:\n  "
                     + "\n  ".join("%s ← %s" % b for b in bad))


def test_the_printed_number_equals_what_the_verdict_table_says_now():
    """★★ 打印出来的数必须与判决表**当下**的 ★coverage 逐位相同。"""
    assert V3.exists(), "★ 判决表不在 —— 覆盖率无从现算"
    cov = json.loads(V3.read_text(encoding="utf-8"))["★coverage"]
    out = _run()
    for label, val in (("file_level_pct", cov["file_level_pct"]),
                       ("line_level_pct", cov["line_level_pct_GENEROUS_UPPER_BOUND"])):
        assert str(val) in out, "★ 清单里找不到判决表现在的 %s=%s" % (label, val)
    # 旧数字**只能以被撤回的引文形式**出现在输出里 —— 同决策单闸的形状
    for m in re.finditer(r"17\.3%", out):
        ctx = out[max(0, m.start() - 70):m.end() + 30]
        assert "「" in ctx and any(w in ctx for w in ("原写死", "原先", "不再硬编")), (
            "★★★ 旧硬编数字 17.3% 以**现行主张**的形式回来了: %s" % " ".join(ctx.split())[:120])
    return cov["file_level_pct"], cov["line_level_pct_GENEROUS_UPPER_BOUND"]


def test_it_says_unknown_rather_than_falling_back_to_an_old_number():
    """★★★ 判决表读不到时必须说「未知」, **不许回落到任何旧数字** ——
    回落就是把过期数字伪装成现状, 比直接报错糟得多。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    import cce_open_items as OI
    import importlib
    importlib.reload(OI)
    real = OI.ROOT
    try:
        OI.ROOT = str(ROOT / "tests" / "data" / "__no_such_dir__")
        src, cov = OI._ablation_coverage_now()
        assert src is None, "★ 判决表不存在却报出了来源 %r" % src
        assert "未知" in cov, "★ 读不到时没有说「未知」: %r" % cov
        assert not re.search(r"\d+\.\d+%", cov), "★★★ 读不到判决表却仍给出了一个百分比 —— 那是回落到旧数字: %r" % cov
    finally:
        OI.ROOT = real
    return cov


if __name__ == "__main__":
    test_no_literal_coverage_percentage_in_source()
    f, l = test_the_printed_number_equals_what_the_verdict_table_says_now()
    fb = test_it_says_unknown_rather_than_falling_back_to_an_old_number()
    print("test_cce_open_items_no_hardcoded_coverage: OK ("
          f"★★★覆盖率已改为**现算**: 文件级 {f}% · 行级慷慨上界 {l}% —— "
          "原先「只覆盖 17.3%」是**写死在字符串里**且指向 v2, v3 落地后它永远不会自己更新 | "
          "★★「过期判决表继续被引用」这次出现在**报告『还差什么』的那张表自己**身上, "
          "而那正是我用来回答 owner「可以使用了吗」的东西 —— **报告层的过期比被报告项的过期更危险** | "
          f"★★★判决表读不到时它说「{fb[:22]}…」而**不回落到任何旧数字** | "
          "★ 百分比判据只针对**覆盖率语境**(附近含「覆盖」), 不误伤其它读数百分比 —— 会误报的闸不上)")
