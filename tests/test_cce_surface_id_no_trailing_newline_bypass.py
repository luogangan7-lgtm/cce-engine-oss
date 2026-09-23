#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: `surface.id` 的模式校验必须是**全匹配**, 不许被尾部换行绕过。

★★★ 为什么要这条(2026-09-12 parser_plane 消融的独立复核查出):
`scripts/cce_platform_adapter.py:56` 现在写的是 `re.fullmatch(pattern, surface_id)` —— **是对的**。
但这条正确性**没有任何闸在看**: 把它换成 `re.match` 或 `re.search`, 全量套件**一条都不红**。

换掉之后会发生什么(实测, 不是推演):
- Python 的 `$` 匹配「串尾 **或** 尾部换行之前」⇒ 对已锚定的 `^...$`,
  `match`/`search` **接受** `'r/HearingAids\\n'`, 而 `fullmatch` 拒绝。
- 后果不是文案差异, 是**生产准入判决翻转**:
  `validate_submission` 由 ok=False(2 errors) 翻成 **ok=True(0 errors)**;
  `build_dispatch` 由 raise ValueError 翻成 **BUILT**, 且出站 context 串里**带着那个换行**
  被喂进测量链路的 prompt。

★ 注意边界: 只有**尾部**换行能绕(`'r/X\\nEVIL'` 三种写法都拒)。所以这不是任意注入,
  但一个换行进 prompt context 已经足够改变喂给模型的那段文本。

## 本闸的范围
它守的是**校验语义**(全匹配), **不是**注册表内容的正确性 —— 那由
`config/platform_adapter_registry_v1.json` 自己和它的既有测试管。
判据来自**语义性质**(逐模式现算「合法 id + \\n 必须被拒」), **不是**抄一份模式表下来比对
—— 期望与实际同源会退化成同义反复(2026-09-11 实测过)。

## 零 API
纯本地计算。装 socket 绊线并断言未触发。
"""
import json
import pathlib
import re
import socket
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cce_platform_adapter as PA  # noqa: E402

SRC = (ROOT / "scripts" / "cce_platform_adapter.py").read_text(encoding="utf-8")


class NetworkTripwire(AssertionError):
    pass


class _Tripwire:
    """★ 作用域如实声明: 覆盖本进程内经 socket.socket.connect **新建**的连接;
    不覆盖已建立连接 · 不走 socket 的传输 · 子进程 · C 扩展自带网络栈。"""
    def __enter__(self):
        self._o, self.tripped = socket.socket.connect, []
        tw = self

        def guard(sock, address, *a, **kw):
            tw.tripped.append(address)
            raise NetworkTripwire("★★★ 离线隔离被突破: %r" % (address,))

        socket.socket.connect = guard
        return self

    def __exit__(self, *e):
        socket.socket.connect = self._o
        return False


def _legal_ids():
    """为每条 space_pattern 造一个**它自己接受**的 id。

    ★ 造法只用模式里的字面片段 + 满足量词的填充, 不抄任何现成 id ——
      造出来后**当场用该模式验一遍**, 造不出来的如实跳过并计数(不假装覆盖)。
    """
    reg = PA.registry()["adapters"]
    out, skipped = [], []
    FILL = {"[A-Za-z0-9_]": "a", "[A-Za-z0-9_-]": "a", "[A-Za-z0-9]": "a",
            "[A-Za-z0-9._:-]": "a", "[A-Za-z0-9_.]": "a", "[A-Za-z0-9.-]": "a"}
    for plat, spec in reg.items():
        for kind, pat in (spec.get("space_patterns") or {}).items():
            body = pat[1:-1] if pat.startswith("^") and pat.endswith("$") else None
            if body is None:
                skipped.append((plat, kind, "模式未同时锚定 ^ 与 $"))
                continue
            cand = None
            m = re.match(r"^(?P<lit>[^\[\]{}()+*?]*)(?P<cls>\[[^\]]+\])"
                         r"(?:\{(?P<lo>\d+)(?:,\d+)?\}|(?P<plus>\+))$", body)
            if m:
                fill = FILL.get(m.group("cls"), "a")
                n = int(m.group("lo")) if m.group("lo") else 3
                cand = m.group("lit") + fill * n
            if cand and re.fullmatch(pat, cand):
                out.append((plat, kind, pat, cand))
            else:
                skipped.append((plat, kind, "造不出合法 id(模式形状超出本构造器)"))
    return out, skipped


def test_the_validator_uses_whole_string_matching():
    """★★ 源码面: 这一行必须是 fullmatch。

    (源码断言只是第一道; 真正的判据是下面那条**语义**断言 —— 换成等价的手写全匹配
     也应当过, 所以这条给的是**定位信息**, 不是全部证据。)
    """
    assert "re.fullmatch(pattern, surface_id)" in SRC, (
        "★★★ surface.id 的模式校验不再是 re.fullmatch —— 若换成 re.match/re.search, "
        "尾部换行可绕过准入校验(见本文件头)。若你是**故意**改成别的等价全匹配写法, "
        "下面那条语义断言仍会通过, 请改这条断言的措辞而不是删掉它。")


def test_a_trailing_newline_is_rejected_for_every_registered_pattern():
    """★★★ 语义面(本闸的核心): 对**每一条**注册模式, 「合法 id + 尾部换行」必须被拒。

    这条不看实现写法, 只看行为 —— 换成手写全匹配也能过, 换成 match/search 立刻红。
    """
    with _Tripwire() as tw:
        ok_cases, skipped = _legal_ids()
        assert ok_cases, "★ 一条合法 id 都造不出来 —— 本闸退化成空过, 请检查造法"
        bad = []
        for plat, kind, pat, cand in ok_cases:
            good = PA.validate_platform_context(
                plat, {"id": PA.registry()["adapters"][plat]["adapter_id"],
                       "version": PA.registry()["adapters"][plat]["adapter_version"]},
                {"kind": kind, "id": cand, "observed_at": "2026-09-12T00:00:00+00:00"})
            if not good["ok"]:
                continue  # 这条造出来的 id 过不了别的校验, 不用它做对照
            evil = PA.validate_platform_context(
                plat, {"id": PA.registry()["adapters"][plat]["adapter_id"],
                       "version": PA.registry()["adapters"][plat]["adapter_version"]},
                {"kind": kind, "id": cand + "\n", "observed_at": "2026-09-12T00:00:00+00:00"})
            if evil["ok"]:
                bad.append("%s/%s 模式 %r: %r 被拒而 %r **被放行**" % (plat, kind, pat, cand, cand + "\n"))
        assert not bad, (
            "★★★ 尾部换行绕过了 surface.id 准入校验 —— 生产准入判决翻转, 且换行会进入"
            "喂给测量链路的 prompt context:\n  " + "\n  ".join(bad))
    assert not tw.tripped, "★★★ 本闸发出了真实网络请求: %r" % (tw.tripped,)
    return len(ok_cases), len(skipped)


def test_the_gate_is_not_inert():
    """★★★ 灵敏度自证: 把全匹配换成 `re.match`, 上面那条**必须**判红。

    否则它就是一条恒绿的摆设 —— 而恒绿的闸比没有闸更糟, 它看起来像有覆盖。
    (只在**内存里**换掉模块的 re, 仓里文件一字不动。)
    """
    class _ReMatchOnly:
        """把 fullmatch 悄悄降级成 match —— 正是本闸要挡住的那次改动。"""
        def __getattr__(self, n):
            return getattr(re, n)

        def fullmatch(self, pattern, string, *a, **k):
            return re.match(pattern, string, *a, **k)

    orig = PA.re
    try:
        PA.re = _ReMatchOnly()
        try:
            test_a_trailing_newline_is_rejected_for_every_registered_pattern()
        except AssertionError as e:
            assert "被放行" in str(e), "★ 降级后判红了, 但红的不是这条判据: %s" % str(e)[:160]
            return True
        # ★★★ 2026-09-12 自查修正: 第一版这里直接判「本闸是摆设」——**诬告**。
        #   实测: 若生产改成等价的手写全匹配(如 `re.match(pattern + r"\Z", s)`),
        #   这条臂**够不着**它, 于是「降级后仍绿」的真正含义是「我这条臂不再适用」,
        #   不是「闸测不到」。两者处置完全不同, 混成一句就是把装置失效说成结论。
        raise AssertionError(
            "★★★ 本闸的灵敏度自证**不再适用**: 把 `re.fullmatch` 降级成 `re.match` 之后, "
            "语义判据仍然全绿 ⇒ 当前实现已**不依赖 re.fullmatch** 来保证全匹配"
            "(例如改成了 `pattern + r'\\Z'` 这类等价写法)。\n"
            "  这**不等于**本闸测不到尾部换行绕过 —— 它只说明这条降级臂够不着现在的实现。\n"
            "  ⇒ 请补一条**能真正削弱当前锚定机制**的降级臂, 否则本闸的非惰性**未被证明**。"
            "(不许删掉这条检查了事: 一道恒绿的闸比没有闸更糟, 它看起来像有覆盖。)")
    finally:
        PA.re = orig


def test_the_registry_patterns_are_still_anchored():
    """★ 前提: 本闸的语义论证建立在「模式两端都锚定」上。

    出现未锚定的模式 ⇒ 它的绕过面比尾部换行大得多(任意前后缀), 那是另一个问题,
    必须先被看见 —— 所以在这里红出来, 而不是让本闸静默少覆盖一条。
    """
    unanchored = []
    for plat, spec in PA.registry()["adapters"].items():
        for kind, pat in (spec.get("space_patterns") or {}).items():
            if not (isinstance(pat, str) and pat.startswith("^") and pat.endswith("$")):
                unanchored.append("%s/%s = %r" % (plat, kind, pat))
    assert not unanchored, (
        "★★★ 这些 space_pattern 没有两端锚定 —— 任意前后缀都能绕, 比尾部换行严重:\n  "
        + "\n  ".join(unanchored))
    n = sum(len(s.get("space_patterns") or {}) for s in PA.registry()["adapters"].values())
    return n


if __name__ == "__main__":
    test_the_validator_uses_whole_string_matching()
    covered, skipped = test_a_trailing_newline_is_rejected_for_every_registered_pattern()
    test_the_gate_is_not_inert()
    total = test_the_registry_patterns_are_still_anchored()
    print("test_cce_surface_id_no_trailing_newline_bypass: OK ("
          f"★★★补上 parser_plane 消融复核查出的**验收缺口**: 生产用的 `re.fullmatch` 是对的, "
          "但把它换成 `re.match`/`re.search` **全量套件一条都不红** —— 而换掉之后 "
          "`validate_submission` 由 ok=False(2 errors) 翻成 **ok=True**, `build_dispatch` 由 raise 翻成 **BUILT**, "
          "且**一个换行被带进喂给测量链路的 prompt context** | "
          f"★★★判据是**语义**不是写法: 逐条现算「合法 id + \\n 必须被拒」, 覆盖 {covered}/{total} 条注册模式"
          f"(另 {skipped} 条造不出合法 id, **如实计数不假装覆盖**); 换成手写全匹配也能过, 换成 match 立刻红 | "
          "★★★**灵敏度自证**: 内存内把 fullmatch 降级成 match, 本闸必须判红 —— 恒绿的闸比没有闸更糟 | "
          f"★前提被钉住: {total} 条模式必须两端锚定(出现未锚定的 ⇒ 绕过面比尾部换行大得多, 先红出来) | "
          "★ 零 API: socket 绊线未触发)")
