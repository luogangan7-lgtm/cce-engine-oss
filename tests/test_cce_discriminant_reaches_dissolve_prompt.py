#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: `hard_discriminant` **真正进生产的那一处**必须被观察到。

★★★ 为什么要这条(2026-09-11 消融第四轮查出, 2026-09-12 补):
仓内有 **21 条测试在断言 `hard_discriminant` 不进 stage2 prompt** —— 那是**另一台**仪器
(`cce_knot_classify` 的生产分类器 P)。而它**真正进的那一处**是:

    config/knot_taxonomy.json
      → scripts/cce_align_v2.py:22  DISCR = {k["key"]: k.get("hard_discriminant", "")}   ← import 期自读磁盘
      → :87  DISSOLVE_PROMPT.format(knot=…, discr=DISCR.get(knot, ""), …)   在 dissolve_hit() 里
      → :128 score() 的 dissolution 项  → θ 判决
      → scripts/reply_batch.py:22 / scripts/reply_loop.py:20  `from cce_align_v2 import score`
      → **生产回复链路**

这一处**零测试覆盖**: 删掉该字段, `DISCR.get(knot, "")` 的默认值让 `discr` **静默变成空串**,
prompt 照样成形、模型照样被调用、分数照样产出, **全仓一条测试都不会红**。
(`tests/test_cce_support_publication.py` 虽然提到 dissolve_hit, 但它把整个函数**替换掉**了
 ⇒ 结构上看不见任何消融。)

★ 与那 21 条**不矛盾**: 它们说的是「不进 P 的 stage2 prompt」, 这条说的是「必须进 align 的 DISSOLVE prompt」。
  两台仪器、两个消费者, 混成一条判决正是第四轮翻案的根因。

## 本闸的观测面
**不重新拼 prompt** —— 那是「探针仿造请求」的老毛病(本仓修过一次)。
做法是**截住 `_call`**, 让**真实的 `dissolve_hit` / `score`** 跑完整条路径, 再看**实际发出去的那段文本**。

## ★★★ 本闸的范围, 以及**它抓不到什么**(2026-09-12 反向验证实测得出)
本闸拿**同一份 taxonomy** 与 prompt 比对 ⇒ 它测的是**到达性(plumbing)**, **不是内容正确性**。
实测八条变异:
  ✅ 删字段 · ✅ 置空串 · ✅ 摘掉 `{discr}` 槽 · ✅ dissolve_hit 不再传 discr ·
  ✅ 生产改走别的算子 · ✅ 空操作对照不产生伪阳性
  ❌ **截断一半** · ❌ **两个结的判别式对调** —— 这两条本闸**抓不到**,
     因为文件一改, 比对的两边**一起变**, 判据退化成同义反复。
⇒ 内容漂移由**另一道闸**管: `config/knot_taxonomy.json` 被 `config/cce_core_manifest.json:core_files`
  以 sha256 钉住(现值 56a1c1977bf8d18c), `scripts/cce_core_boundary.py` 逐文件比对。
  已实算: 截断后 sha → 31677b24e5fdf15e · 对调后 → 3b704904caa8eb7c, **两者都 ≠ 钉住值 ⇒ 必红**。
★ 所以本闸**依赖那个钉**。`test_the_content_pin_this_gate_relies_on_is_still_in_place` 把这个依赖
  显式钉住 —— 哪天有人把 taxonomy 从 core_files 里拿掉, 内容就**没人管了**, 本闸会先红说出来,
  而不是继续绿着假装覆盖完整。

## 零 API
装 socket 绊线并断言未触发。`_call` 被换成确定性回放, **一次真实请求都不发**。
"""
import json
import os
import pathlib
import socket
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
HD = {k["key"]: k.get("hard_discriminant", "") for k in TAXO["knots"]}
BLOCKING = [k["key"] for k in TAXO["knots"] if k.get("family") == "阻挡"]

TEXT = "PROBE_TEXT_DO_NOT_SEND —— 这是离线闸的探针文本, 不应出现在任何真实请求里。"
CANNED = '{"hit": 0.6, "evidence": "PROBE"}'


class NetworkTripwire(AssertionError):
    """★ 任何**新建 socket 连接**都是失败, 不是警告。"""


class _Tripwire:
    """★ 作用域如实声明(写成代码里的字符串, 不是注释):
    覆盖 —— 本进程内经 `socket.socket.connect` **新建**的连接。
    **不覆盖** —— 已建立的连接 · 不走 socket 的传输 · 子进程 · C 扩展自带网络栈。
    """
    scope = ("覆盖: 本进程内经 socket.socket.connect 新建的连接。"
             "不覆盖: 已建立连接 · 不走 socket 的传输 · 子进程 · C 扩展自带网络栈。")

    def __enter__(self):
        self._orig = socket.socket.connect
        self.tripped = []
        tw = self

        def guard(sock, address, *a, **kw):
            tw.tripped.append(address)
            raise NetworkTripwire("★★★ 离线隔离被突破: 试图连接 %r" % (address,))

        socket.socket.connect = guard
        return self

    def __exit__(self, *exc):
        socket.socket.connect = self._orig
        return False


def _capture(A):
    """把 `_call` 换成确定性回放并记录**实际发出的 prompt**。返回 (还原函数, 记录列表)。"""
    seen, lock, orig = [], threading.Lock(), A._call

    def fake(prompt, model="MiniMax-Text-01", temperature=0.0):
        with lock:
            seen.append(prompt)
        return CANNED

    A._call = fake
    return (lambda: setattr(A, "_call", orig)), seen


def _import_align():
    import importlib
    import cce_align_v2 as A
    return importlib.reload(A)


# ── ① 每个结的判别式必须逐字进 DISSOLVE prompt ────────────────────────
def test_every_discriminant_reaches_the_dissolve_prompt_verbatim():
    """★★★ 核心: 对**每一个**结, 它自己的 hard_discriminant 必须**逐字**出现在
    真实 dissolve_hit 发出的 prompt 里。空串、被别的结的判别式顶替、被截断, 都判红。"""
    A = _import_align()
    with _Tripwire() as tw:
        restore, seen = _capture(A)
        try:
            for knot in HD:
                seen.clear()
                A.dissolve_hit(knot, TEXT)
                assert seen, "★ %s: dissolve_hit 没有发出任何 prompt" % knot
                p = seen[0]
                hd = HD[knot]
                assert hd, "★★★ %s 的 hard_discriminant 在分类学里就是空的" % knot
                assert hd in p, (
                    "★★★ %s 的 hard_discriminant **没有逐字进 DISSOLVE prompt** ——\n"
                    "  这正是 DISCR.get(knot, \"\") 的静默默认值会造成的形状: prompt 照样成形, 分数照样产出。\n"
                    "  期望片段: %r\n  实际 prompt(前 300 字): %r" % (knot, hd[:60], p[:300]))
                # 不许被别的结的判别式顶替
                wrong = [o for o, v in HD.items() if o != knot and v and v in p]
                assert not wrong, "★★ %s 的 prompt 里混进了别的结的判别式: %r" % (knot, wrong)
                assert TEXT in p, "★ 待判文本没进 prompt —— 这条路不是真实路径"
        finally:
            restore()
    assert not tw.tripped, "★★★ 本闸发出了真实网络请求: %r" % (tw.tripped,)
    return len(HD)


# ── ② 生产入口(score)而不只是 helper ────────────────────────────────
def test_it_reaches_the_prompt_through_the_production_entry_point():
    """★★ 只测 dissolve_hit 不够 —— 生产调的是 `score`。

    reply 模式下**全部九结**都走 dissolve_hit(:128 的 else 分支);
    post 模式下只有阻挡族走。两种都测, 免得改了分族逻辑没人发现。
    """
    A = _import_align()
    aud = {k: 1.0 / len(HD) for k in HD}
    post = {k: 0.5 for k in HD}
    out = {}
    with _Tripwire() as tw:
        restore, seen = _capture(A)
        try:
            for mode, expect in (("reply", set(HD)), ("post", set(BLOCKING))):
                seen.clear()
                A.score(aud, post, TEXT, detect=True, mode=mode)
                blob = "\n".join(seen)
                got = {k for k, v in HD.items() if v and v in blob}
                assert got == expect, (
                    "★★ mode=%s 下进 prompt 的判别式集合与预期不符\n  缺: %r\n  多: %r\n"
                    "  (reply 模式应当全部九结; post 模式只有阻挡族 %r)"
                    % (mode, sorted(expect - got), sorted(got - expect), BLOCKING))
                out[mode] = len(got)
        finally:
            restore()
    assert not tw.tripped, "★★★ 本闸发出了真实网络请求: %r" % (tw.tripped,)
    return out


# ── ③ 生产确实引入了这条路 ──────────────────────────────────────────
def test_the_production_callers_still_import_this_path():
    """★ 判决面的前提: reply_batch / reply_loop 确实用 score。
    哪天它们改走别的算子, 上面两条就变成在测一条没人走的路 —— 那时本条会先红。"""
    for f in ("reply_batch.py", "reply_loop.py"):
        src = (ROOT / "scripts" / f).read_text(encoding="utf-8")
        assert "from cce_align_v2 import score" in src, (
            "★★ scripts/%s 不再从 cce_align_v2 引入 score —— "
            "本闸测的那条路可能已经不是生产路径了, 请重新确认消费者" % f)


# ── ④ 把静默默认值本身钉出来 ────────────────────────────────────────
def test_the_silent_default_is_pinned_as_a_known_hazard():
    """★★★ `DISCR.get(knot, "")` 的默认值**就是**让这处零覆盖得以静默的机制。

    本条不要求改生产行为(那会改变 reply 链路), 只要求:
    ① 这个静默路径**确实存在**(如实钉住, 不假装没有);
    ② **当前没有任何结落进它**。
    哪天有结落进去, ① 仍成立而 ② 判红。
    """
    A = _import_align()
    # ① 未知 key 静默得到空串, 且 prompt 照样成形 —— 不抛、不告警
    assert A.DISCR.get("__no_such_knot__", "") == ""
    p = A.DISSOLVE_PROMPT.format(knot="__no_such_knot__", discr=A.DISCR.get("__no_such_knot__", ""),
                                 playbook="", text=TEXT)
    assert "判据(受众处于该状态的表现):" in p, "★ 模板结构变了, 本条的前提要重核"
    # ② 当前九结无一落进该默认值
    empty = [k for k in HD if not A.DISCR.get(k, "")]
    assert not empty, "★★★ 这些结落进了静默默认值(判别式为空却照发 prompt): %r" % empty
    assert set(A.DISCR) >= set(HD), "★ DISCR 与分类学的结集合不一致"
    return len(A.DISCR)


# ── ⑤ 模板里那个槽不许被摘掉 ────────────────────────────────────────
def test_the_discr_slot_is_still_in_the_template():
    """★ 摘掉 `{discr}` 槽 ⇒ 字段永远到不了模型, 而 format 不会报错(多余 kwarg 被忽略)。"""
    A = _import_align()
    assert "{discr}" in A.DISSOLVE_PROMPT, (
        "★★★ DISSOLVE_PROMPT 里没有 {discr} 槽 —— hard_discriminant 结构上到不了模型, "
        "而 str.format 对多余关键字**不报错**, 所以这件事不会以异常的形式出现")


# ── ⑥ 本闸依赖的那个内容钉必须还在 ──────────────────────────────────
def test_the_content_pin_this_gate_relies_on_is_still_in_place():
    """★★★ 本闸只管**到达性**, 管不了内容(截断/对调它抓不到, 已实测)。

    内容由 `cce_core_boundary` 的 sha256 钉管。**那个钉是本闸范围声明的前提** ——
    钉没了, 判别式的内容就**一个闸都没有**, 而本闸仍会绿。
    ⇒ 把依赖显式钉住: 钉不在, 或钉与现况不符, 本条先红。
    """
    import hashlib
    man = json.loads((ROOT / "config" / "cce_core_manifest.json").read_text(encoding="utf-8"))
    rel = "config/knot_taxonomy.json"
    pinned = (man.get("core_files") or {}).get(rel)
    assert pinned, (
        "★★★ %s 不在 core_files 里 —— 本闸只测到达性, 内容漂移(截断/对调)原本由那个 sha 钉管, "
        "钉没了就**没有任何闸在看判别式的内容**了" % rel)
    live = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()[:len(pinned)]
    assert live == pinned, (
        "★★ %s 与 core_files 的钉不符(钉 %s / 现 %s) —— "
        "本闸的「内容另有人管」这句话当下不成立" % (rel, pinned, live))
    return pinned


if __name__ == "__main__":
    n = test_every_discriminant_reaches_the_dissolve_prompt_verbatim()
    modes = test_it_reaches_the_prompt_through_the_production_entry_point()
    test_the_production_callers_still_import_this_path()
    ndiscr = test_the_silent_default_is_pinned_as_a_known_hazard()
    test_the_discr_slot_is_still_in_the_template()
    pin = test_the_content_pin_this_gate_relies_on_is_still_in_place()
    print("test_cce_discriminant_reaches_dissolve_prompt: OK ("
          f"★★★补上 2026-09-11 消融第四轮查出的**零覆盖**: 仓内 21 条测试在断言 "
          "hard_discriminant **不进** stage2 prompt(那是生产分类器 P), 而它**真正进的那一处** —— "
          "cce_align_v2:22 DISCR → :87 DISSOLVE_PROMPT 的 discr 槽 → :128 score → "
          "reply_batch/reply_loop 的**生产回复链路** —— 一条测试都没有 | "
          f"★★★{n}/9 个结的判别式现在被要求**逐字**出现在**真实 dissolve_hit 发出的 prompt** 里"
          "(截 `_call` 看实际发文, **不重拼 prompt** —— 仿造请求是本仓修过的老毛病), "
          "且不许被别的结的判别式顶替 | "
          f"★★经**生产入口 score** 而不只是 helper: reply 模式 {modes['reply']}/9 结全走、"
          f"post 模式仅阻挡族 {modes['post']}/{len(BLOCKING)} —— 分族逻辑被改会先红 | "
          f"★★★把**静默机制本身**钉出来: `DISCR.get(knot, \"\")` 的默认值让缺字段变成空串、"
          f"prompt 照样成形、分数照样产出({ndiscr} 个键现无一落进它; 落进去就红) | "
          "★ {discr} 槽被摘掉也要红 —— str.format 对多余 kwarg **不报错**, 这事不会以异常形式出现 | "
          f"★★★**范围如实声明**: 八条变异实测 —— 删字段/置空/摘槽/不传参/改算子/空操作对照 **6 条按预期**, "
          f"而**截断**与**对调**本闸**抓不到**(拿同一份文件跟自己比, 两边一起变 ⇒ 同义反复); "
          f"内容漂移由 cce_core_boundary 的 sha 钉管(现 {pin}, 截断后 31677b24… 对调后 3b704904… 均 ≠ 钉 ⇒ 必红), "
          f"**这个依赖已被显式钉住** —— 钉没了本闸先红, 不假装覆盖完整 | "
          "★ 零 API: socket 绊线未触发, `_call` 走确定性回放)")
