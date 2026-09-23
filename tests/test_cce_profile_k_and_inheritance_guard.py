#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 决定**哪些读数可以引用**的两处, 必须被观察到。

★★★ 为什么要这条(2026-09-11 消融第四轮点名, 2026-09-12 补):
这两处判决**直接决定生产能不能引用结层读数**, 而两轮消融实测它们 **L4 净新增翻红 = 0** ——
改成任何常数、或整个关掉, **全套测试一条都不红**。

  v3-062  `cce_full_run.py:538`  `"k": 5 if a.mode in {"post","outbound_post"} else 3`
          → `instrument_id(..., k=...)` → **不同的 instrument_hash** → 哪台仪器 → 哪些读数可引用
  v3-071  `cce_k1_status._inherited_verdict_name` + `verdict_path_for` 的继承分支
          → 生产仪器 **本身没有登记 K1 判定**, 它的 top1 **只能**经这条通道自证继承
          → 关掉它, **现行生产唯一可用的结层读数全灭**

## ★★★ 怎么避开「拿同一份东西跟自己比」
昨天补 hard_discriminant 那道闸时实测发现: 期望与实际同源 ⇒ 判据退化成同义反复
(截断/对调都抓不到)。所以本闸**不比对那个常数本身**, 而是比对它的**后果**:
  - 常数在 `cce_full_run.py`
  - 后果的判据来自 `cce_k1_status.VERDICT_BY_INSTRUMENT` + `cce_knot_classify.SCOPE_WIDENINGS`
  **两个不同的源。** 改了常数而后果不变 ⇒ 说明它真的不承重; 后果变了 ⇒ 本闸红。
★ 且每组断言都带**灵敏度自证**(把被测的东西弄坏, 后果必须变) —— 否则一道恒绿的闸
  与「没有闸」在证据上等价, 而它更糟: 它看起来像有覆盖。

## 零 API
`instrument_id` / `knot_readout_usable` 全程本地计算(已实测零网络)。本闸装 socket 绊线并断言未触发。
"""
import contextlib
import json
import pathlib
import socket
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import cce_k1_status as K      # noqa: E402
import cce_knot_classify as C  # noqa: E402

TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))

# ★ 生产的真实调用形状(不是我重拼的): cce_knot_classify.py:770
#   instrument_id(taxo, k=s1["k_requested"], knot_n=KNOT_N,
#                 s1_pairing=f"round_robin_over_{len(s1_draws)}_s1_draws", ...)
def _hash_for_k(k):
    return C.instrument_id(TAXO, k=k, knot_n=C.KNOT_N,
                           s1_pairing="round_robin_over_%d_s1_draws" % k)["instrument_hash"]


def _k_expr_from_production():
    """★★★ 2026-09-12 自查修正: 第一版我把映射语义**抄进了测试**
    (`K_OF = lambda mode: 5 if mode in {...} else 3`) —— 那样改 `cce_full_run.py`
    本闸**根本看不见**, 正是昨天那个「拿同一份东西跟自己比」的陷阱换了个马甲。

    ⇒ 改成**从生产源码里取出那个表达式并求值它本身**。表达式变了, 这里求出的 k 就变,
      后果随之变, 与下面 EXPECTED 那张**被决定过的**表对不上 ⇒ 红。
    """
    import ast
    src = (ROOT / "scripts" / "cce_full_run.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    # ★ 只认**赋给 ctx 的那个字典**里的 "k" —— 仓里别处也有带 "k" 键的字典,
    #   第一版我拿 ast.walk 取了「最后一个」, 结果取到了无关的那个(实测 NameError)。
    hits = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "ctx" for t in n.targets)):
            continue
        if not isinstance(n.value, ast.Dict):
            continue
        for kk, vv in zip(n.value.keys, n.value.values):
            if isinstance(kk, ast.Constant) and kk.value == "k":
                hits.append(vv)
    assert len(hits) == 1, (
        "★★ ctx 字典里的 \"k\" 表达式命中 %d 处(应为 1) —— 映射结构变了, 请重核" % len(hits))
    node = hits[0]
    assert node is not None, (
        "★★★ 在 cce_full_run.py 里找不到 ctx 的 \"k\" 表达式 —— "
        "profile→k 的映射换地方了, 本闸测的可能已不是生产路径, 请重核")
    code = compile(ast.Expression(ast.fix_missing_locations(node)), "<cce_full_run:k>", "eval")

    class _A:  # 只提供表达式用到的 a.mode
        def __init__(self, mode): self.mode = mode

    def k_of(mode):
        try:
            return eval(code, {"__builtins__": {}}, {"a": _A(mode)})  # noqa: S307
        except Exception as e:
            # ★ 别让它裸崩: 裸 NameError 不告诉读者出了什么事(反向验证时实测到过)
            raise AssertionError(
                "★★★ 生产的 profile→k 表达式 %r 在本闸里求不动(%s: %s) —— "
                "它多半已经依赖 cce_full_run 里别的名字。本闸**故意只求值那一个表达式**"
                "(不整体 import, 免得把 argparse/副作用一起拖进来), "
                "所以映射一旦挪窝或改用函数, 这里必须重新对接, 不能放着不管。"
                % (ast.unparse(node), type(e).__name__, e)) from None
    return k_of, ast.unparse(node)


K_OF, K_EXPR = _k_expr_from_production()

# ★★ **必须逐个决定**的 profile 全集(来自 cce_full_run.CHAINS)。
#   新增 profile 而没人决定它的读数状态 ⇒ 本闸红(见 test_every_profile_has_a_decided_readout_status)。
EXPECTED = {
    "reply":         {"k": 3, "top1_usable": True},
    "response":      {"k": 3, "top1_usable": True},
    "media_ingest":  {"k": 3, "top1_usable": True},
    # ★★★ 2026-09-13 由 False 改 True —— **不是把闸改宽, 是被测事实变了**:
    #   owner 点头后登记了 k=5 的口径扩大继承边(SCOPE_WIDENING_EDGE_REGISTERED),
    #   c4419c3e53aa2fa9 现在能继承 K1_TOP1_ON_K5(2026-09-04 采集, 判据测量前冻结, 8/8)。
    #   ★ 本闸**就是为了让这种改变必须被人手动确认**才存在的 —— 它当场判了红, 这是它工作了。
    #   变更留档: config/cce_core_manifest.json 的 refactor_log(2026-09-13) 与
    #            tests/test_cce_k5_widening_edge.py。
    "outbound_post": {"k": 5, "top1_usable": True},
}


class NetworkTripwire(AssertionError):
    pass


@contextlib.contextmanager
def _tripwire():
    """★ 作用域如实声明: 覆盖本进程内经 socket.socket.connect **新建**的连接;
    **不覆盖**已建立连接 · 不走 socket 的传输 · 子进程 · C 扩展自带网络栈。"""
    orig, tripped = socket.socket.connect, []

    def guard(sock, address, *a, **kw):
        tripped.append(address)
        raise NetworkTripwire("★★★ 离线隔离被突破: %r" % (address,))

    socket.socket.connect = guard
    try:
        yield tripped
    finally:
        socket.socket.connect = orig


def _chains_profiles():
    import ast
    t = ast.parse((ROOT / "scripts" / "cce_full_run.py").read_text(encoding="utf-8"))
    for n in ast.walk(t):
        if isinstance(n, ast.Assign) and any(getattr(x, "id", "") == "CHAINS" for x in n.targets):
            return [k.value for k in n.value.keys]
    raise AssertionError("★ 在 cce_full_run.py 里找不到 CHAINS —— profile 全集的来源变了, 请重核")


# ══ v3-062 · profile → k 映射 ═══════════════════════════════════════
def test_every_profile_has_a_decided_readout_status():
    """★★ 每个生产 profile 的结层读数状态都必须**被决定过**。

    新增一个 profile 而没人决定它能不能引用结层读数 ⇒ 红。
    (它不是「默认可以」也不是「默认不可以」—— 那是 owner/标定的事, 不许靠默认值定。)
    """
    live = set(_chains_profiles())
    decided = set(EXPECTED)
    assert live <= decided, (
        "★★★ 这些 profile 在 cce_full_run.CHAINS 里但没人决定它们的结层读数状态: %r\n"
        "  —— 不许靠默认值定: 新 profile 的 k 会决定它落在哪台仪器上, "
        "而那台仪器有没有 K1 判定是**标定问题**, 不是代码问题。" % sorted(live - decided))
    return sorted(live)


def test_the_k_mapping_actually_selects_between_two_different_instruments():
    """★★★ 映射的**后果**: k=3 与 k=5 是**两台不同的仪器**, 且可用读数不同。

    判据来自 `cce_k1_status`(登记表 + 继承), **不是**来自那个常数本身。
    """
    with _tripwire() as tw:
        h3, h5 = _hash_for_k(3), _hash_for_k(5)
        assert h3 != h5, "★★★ k 不再改变 instrument_hash —— 这条映射的整个前提没了"
        for mode, exp in EXPECTED.items():
            h = _hash_for_k(K_OF(mode))
            ok, why = K.knot_readout_usable("top1", instrument_hash=h)
            assert ok is exp["top1_usable"], (
                "★★★ %s(k=%d, 仪器 %s) 的 top1 可用性与登记不符: 期望 %s 实得 %s\n  理由: %s"
                % (mode, exp["k"], h, exp["top1_usable"], ok, why))
        # ★★★ 2026-09-13: 原来这里钉的是「k=5 的 **top-1** 必须扣发, 且理由必须是**未测**」。
        #   登记 k=5 继承边之后 top-1 已放行 ⇒ 那条断言的**对象没了**。
        #   ★ 但它守的**三态纪律**(未测 / 已测不达标 / 可用, 三者修法不同, 方向不许反)
        #     一条都不能丢 —— 改钉到**仍然扣发的那两层**上。
        ok5, why5 = K.knot_readout_usable("top1", instrument_hash=h5)
        assert ok5, "★★★ k=5 的 top-1 又扣发了 —— 继承边是不是被撤了? 见 test_cce_k5_widening_edge"
        assert ("8/8" in why5) or ("达标" in why5), (
            "★★ k=5 的 top-1 放行理由不是那份 K1 判定(%s) —— 放行依据换了就必须重新确认" % why5)
        for layer in ("intensity", "weight"):
            okl, whyl = K.knot_readout_usable(layer, instrument_hash=h5)
            assert not okl, "★★★ %s 在 k=5 上被顺手解锁了" % layer
            # 三态: 这两层是**已测不达标**(K1-v2 判过并失败), 不是「未测」—— 方向同样不许反
            assert ("判定" in whyl) or ("不可用" in whyl), (
                "★★ %s 的扣发理由变了(%s) —— 若它从「已测不达标」变成「未测」, "
                "那是把 judged-and-failed 说成 not-started, 方向反了" % (layer, whyl))
    assert not tw, "★★★ 本闸发出了真实网络请求: %r" % (tw,)
    return h3, h5


def test_the_k_mapping_is_not_inert():
    """★★★ 灵敏度自证: 把映射压成常数, 可用集**必须改变**。

    若压成常数后可用集不变 ⇒ 这条映射对读数可用性无影响, 上面那条断言就是恒真的摆设。
    (消融实测它 L4 净新增 0 —— 本条就是补上那个 0。)
    """
    # ★★★ 2026-09-13 换观测面, 并把**为什么换**写在这里(换而不记 = 悄悄放宽):
    #   登记 k=5 继承边之后, **两台仪器的 top-1 都可用** ⇒ 「top-1 可用性」这个观测面
    #   **对 k 不再有判别力**(压成任何常数, 可用集都不变)。
    #   ★ 这不是缺陷, 是本次变更的**直接后果**, 而且是件该被知道的事: 从今天起
    #     「哪个 profile 能引用结层 top-1」**不再由 k 决定** —— 以前 outbound_post 因为
    #     落在未登记仪器上而零可用, 现在不会了。
    #   ⇒ 灵敏度自证改钉**映射仍然控制的那个面**: 它决定 profile 落在**哪台仪器**上,
    #     而仪器身份决定哪份标定适用。这个面压成常数一定会变。
    base_inst = {m: _hash_for_k(K_OF(m)) for m in EXPECTED}
    assert len(set(base_inst.values())) >= 2, (
        "★★★ 全部 profile 现在落在**同一台仪器**上 —— 这条映射对仪器身份也没有影响了, "
        "本闸测的是空气; 请重新确认 profile→k 还有没有意义")
    for const in (3, 5):
        flat = {m: _hash_for_k(const) for m in EXPECTED}
        assert flat != base_inst, (
            "★★★ 把 k 压成常数 %d 后**仪器归属**与现状完全相同(%r) —— 映射无影响" % (const, flat))
    # ★ 同时把「top-1 现在两台都可用」这件事钉住: 哪天它又变回只有一台, 必须有人确认
    now = {m: K.knot_readout_usable("top1", instrument_hash=_hash_for_k(K_OF(m)))[0]
           for m in EXPECTED}
    assert all(now.values()), (
        "★★ 有 profile 的结层 top-1 又变成不可用了(%r) —— 若是继承边被撤/判定失效, "
        "那是**读数面缩小**, 必须有人确认而不是默默接受" % now)
    return base_inst


# ══ v3-071 · 口径扩大继承通道 ═══════════════════════════════════════
def test_production_top1_hangs_entirely_on_the_inheritance_channel():
    """★★★ 生产仪器**自己没有**登记的 K1 判定 —— 它的 top1 **只能**经继承通道拿到。

    这不是一句描述, 是本闸后面三条「关掉它」断言的前提: 若哪天它被直接登记了,
    继承通道就不再承重, 那三条会变成测空气 ⇒ 本条会先红。
    """
    h3 = _hash_for_k(3)
    assert h3 not in K.VERDICT_BY_INSTRUMENT, (
        "★★ 生产仪器 %s 现在**直接登记**在 VERDICT_BY_INSTRUMENT 里了 —— "
        "继承通道不再是它 top1 的唯一来源, 下面三条关断断言的前提已变, 请重核" % h3)
    assert K._inherited_verdict_name(h3) == "K1_VERDICT", "★ 继承来源变了, 请重核"
    assert K.verdict_path_for(h3), "★ 生产仪器拿不到判定文件 —— top1 应当已被扣发"
    ok, _ = K.knot_readout_usable("top1", instrument_hash=h3)
    assert ok, "★★★ 生产 top1 现在不可用了 —— 这是现行唯一可用的结层读数, 出了大事"
    return h3


def _kill_arms():
    """三种关掉继承通道的方式, 每种都必须让生产 top1 变成不可用。"""
    key = next(iter(C.SCOPE_WIDENINGS))
    w = C.SCOPE_WIDENINGS[key]
    return [
        ("verify() 恒 False(自证不成立)",
         lambda: C.SCOPE_WIDENINGS.__setitem__(key, {**w, "verify": lambda: False})),
        ("整条口径扩大登记被删",
         lambda: C.SCOPE_WIDENINGS.pop(key)),
        ("前代仪器自己没有判定(from_instrument 未登记)",
         lambda: C.SCOPE_WIDENINGS.__setitem__(key, {**w, "from_instrument": "0" * 16})),
    ]


def test_killing_the_channel_actually_kills_production_top1():
    """★★★ 灵敏度自证(本闸的核心): 三种关断方式, 每种都必须让生产 top1 **立刻不可用**。

    消融实测这条通道 L4 净新增翻红 **0** —— 关掉它现行唯一可用的结层读数全灭,
    而整个测试套件一条都不红。本条就是补上那个 0。
    """
    h3 = _hash_for_k(3)
    saved = dict(C.SCOPE_WIDENINGS)
    results = []
    try:
        for name, kill in _kill_arms():
            C.SCOPE_WIDENINGS.clear()
            C.SCOPE_WIDENINGS.update(saved)
            kill()
            ok, why = K.knot_readout_usable("top1", instrument_hash=h3)
            assert not ok, (
                "★★★ 「%s」之后生产 top1 **仍然可用** —— 说明它并不真的挂在这条通道上, "
                "或者有别的路径在兜底(那条路径也需要闸)。理由: %s" % (name, why))
            results.append(name)
    finally:
        C.SCOPE_WIDENINGS.clear()
        C.SCOPE_WIDENINGS.update(saved)
    # 还原后必须恢复可用 —— 否则是本闸自己把仓弄坏了
    ok, why = K.knot_readout_usable("top1", instrument_hash=h3)
    assert ok, "★★★ 本闸还原失败, 生产 top1 没有恢复可用: %s" % why
    return results


def test_the_channel_is_a_self_proof_not_a_bare_mapping():
    """★★ 继承**不是**裸加映射: 它要求具名登记 + `verify()` 当场自证。

    键里带着**新旧两个口径哈希**, verify() 去核「旧口径的串仍是新口径的子串」。
    若哪天它退化成一张裸映射表(没有 verify), 自证就没了 —— 那时 `w["verify"]()`
    会 KeyError, 本条红。
    """
    assert C.SCOPE_WIDENINGS, "★ 口径扩大登记表空了"
    for key, w in C.SCOPE_WIDENINGS.items():
        assert callable(w.get("verify")), "★★ %r 没有 verify() —— 继承退化成裸映射了" % (key,)
        assert w["verify"]() is True, "★★ %r 的自证当下不成立, 继承应当已经失效" % (key,)
        # ★★★ 2026-09-12 反向验证逮到的漏: 只查「可调用且返回 True」**分不出橡皮图章** ——
        #   把 verify 换成 `lambda: True` 照样过, 而那正是危险方向(任何仪器都能继承)。
        #   ⇒ 补**对自证本身的灵敏度检验**: 把它声称在核的东西弄坏, verify() 必须翻成 False。
        #   这条 widening 核的是「旧口径哈希的串仍是新口径 s1 模板的子串」⇒ 弄坏模板即可。
        orig_tpl = C._stage1_template
        try:
            C._stage1_template = lambda *a, **k: "TEMPLATE_DESTROYED_BY_GATE"
            still = None
            try:
                still = bool(w["verify"]())
            except Exception:
                still = False          # 抛异常 = 自证不成立, 与返回 False 等价
            assert still is False, (
                "★★★ %r 的 verify() 在**它声称在核的东西被弄坏之后仍然返回 True** —— "
                "那它不是自证, 是橡皮图章。继承通道就等于裸加映射: 任何仪器都能继承前代判定。" % (key,))
        finally:
            C._stage1_template = orig_tpl
        assert w["verify"]() is True, "★ 灵敏度检验后没有还原 —— 本闸把仓弄坏了"
        assert w.get("from_instrument") and w.get("to_instrument"), "★ 登记缺 from/to"
        assert w["from_instrument"] in K.VERDICT_BY_INSTRUMENT, (
            "★★ %r 的前代仪器 %s 自己都没有判定 —— 没得继承" % (key, w["from_instrument"]))
    return len(C.SCOPE_WIDENINGS)


if __name__ == "__main__":
    profs = test_every_profile_has_a_decided_readout_status()
    h3, h5 = test_the_k_mapping_actually_selects_between_two_different_instruments()
    base_inst = test_the_k_mapping_is_not_inert()
    test_production_top1_hangs_entirely_on_the_inheritance_channel()
    arms = test_killing_the_channel_actually_kills_production_top1()
    nw = test_the_channel_is_a_self_proof_not_a_bare_mapping()
    print("test_cce_profile_k_and_inheritance_guard: OK ("
          f"★★★补上消融第四轮点名的**两处 L4 净新增翻红 = 0**(改成任何常数/整个关掉, 全套一条不红) | "
          f"★★v3-062 profile→k: {len(profs)} 个 profile 逐个**被决定过**读数状态(新增 profile 不许靠默认值定); "
          f"k=3 → {h3} **可用**(经继承) · k=5 → {h5} **2026-09-13 起也可用**(同一次口径扩大的兄弟边补登记); "
          "★ 原来钉在 k=5 top-1 扣发上的**三态纪律**(未测/已测不达标/可用, 方向不许反)"
          "**一条没丢, 改钉到仍然扣发的 intensity/weight 两层上** | "
          f"★★★**灵敏度自证换了观测面(并记下为什么)**: 登记 k=5 边后两台的 top-1 都可用 ⇒ "
          "「top-1 可用性」对 k **不再有判别力** —— 这不是缺陷, 是本次变更的直接后果, "
          "且是件该被知道的事(**从今天起「哪个 profile 能引用结层 top-1」不再由 k 决定**)。"
          "改钉映射仍然控制的面: **仪器归属**(压成常数必变), 并另钉「两台 top-1 现在都可用」, "
          "哪天缩回去必须有人确认 | "
          f"★★v3-071 继承通道: 生产仪器**本身没有登记 K1 判定**, top1 **只能**经这条自证继承; "
          f"**三种关断方式({len(arms)}/3)每种都必须让它立刻不可用** —— {arms} | "
          f"★★★继承**不是橡皮图章**: {nw} 条登记的 verify() 都要过**对自证本身的灵敏度检验**""(弄坏它声称在核的 s1 模板 ⇒ 必须翻 False) —— 反向验证逮到过: 只查「可调用且返回 True」""分不出 `lambda: True`, 而那正是危险方向 | "
          "★★★判据来自**另一个源**(VERDICT_BY_INSTRUMENT + SCOPE_WIDENINGS), 不比对常数本身 —— "
          "昨天那道闸实测过: 期望与实际同源就退化成同义反复 | "
          "★ 零 API: socket 绊线未触发, 全程本地计算)")
