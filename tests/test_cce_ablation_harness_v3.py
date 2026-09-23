#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""消融装置 v3 的**反向闸** —— 把装置弄坏, 必须判红。

## 为什么是反向测试而不是正向测试
正向断言「阳性对照通过」是**恒绿风险最高**的写法: 判据一旦退化成重言(第一轮的 L3),
它照样全绿。前三轮的系统性失败全部长这个形状。
⇒ 这里每一条都**先把量具打断一根**, 然后断言「断了之后确实看得见」。
看不见 = 这条闸是空的, 它保护不了任何东西。

## 六条反向
① 绊线不抛 ⇒ 离线隔离是装饰(网络会真的出去)
② file_integrity 不比对 ⇒ R2「仓内文件一字不改」无从验证
③ 重放 stub 用共享迭代器 ⇒ draw 与序号错配(M3-①, 已实际制造过 95 处伪差异)
④ 判据换成 L3 instrument_hash ⇒ 死常量被判成承重(M2, 第一轮 20/20 全判承重的根因)
⑤ 扫描面砍掉 accuracy/ ⇒ 真实消费者被判成零引用(M3-②)
⑥ 变异锚点打空 ⇒ 空臂假装跑过消融
"""
import json
import os
import pathlib
import socket
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
import ablation_harness_v3 as H          # noqa: E402

_RED = []


def _must_raise(what, fn, *a, **k):
    """跑一遍**弄坏的**装置, 断言它真的红了。红了才记一笔。"""
    try:
        fn(*a, **k)
    except Exception as e:
        _RED.append((what, f"{type(e).__name__}: {str(e)[:110]}"))
        return e
    raise AssertionError(f"★ 反向测试没见红: {what} —— 装置被弄坏了却照样绿, 这条闸是空的")


# ── ① 绊线: 弄坏 = 不抛异常 ───────────────────────────────────────────────
def test_reverse_tripwire_must_fire_on_connect():
    with H.Tripwire() as tw:
        assert tw.armed, "★ 绊线没装上"
        s = socket.socket()
        _must_raise("绊线: 新建连接必须抛", s.connect, ("127.0.0.1", 9))
        s.close()
        assert tw.tripped, "★ 绊线抛了却没记账 —— 产物里会看不到它被触发过"
    # 弄坏的对照: guard 换成 no-op(不连也不抛) ⇒ 同一个断言不再见红
    class _Broken(H.Tripwire):
        def __enter__(self):
            self._orig = socket.socket.connect
            socket.socket.connect = lambda *a, **k: None   # 不抛 = 装饰
            return self
    with _Broken() as bt:
        s = socket.socket()
        s.connect(("127.0.0.1", 9))       # 不抛 ⇒ 说明「不抛」这件事是可观察的
        s.close()
        assert not bt.tripped, "★ 坏装置不该记到触发"
    # 作用域声明必须**明写不覆盖什么**, 否则证据会被读成「全进程网络已关闭」
    for word in ("不覆盖", "子进程", "C 扩展", "已建立"):
        assert word in H.Tripwire().scope, f"★ 绊线作用域没写清 {word}"


# ── ② file_integrity: 弄坏 = 真去改文件 ───────────────────────────────────
def test_reverse_file_integrity_must_catch_a_write(tmpdir=None):
    import tempfile
    d = tempfile.mkdtemp(prefix="ablv3_fi_")
    p = os.path.join(d, "frozen.txt")
    open(p, "w").write("original")

    def _break():
        with H.file_integrity([p]):
            open(p, "w").write("TAMPERED")
    _must_raise("file_integrity: 文件被改必须抛", _break)

    # 正向: 不改就不该抛(否则这条闸恒红, 一样没用)
    open(p, "w").write("original")
    with H.file_integrity([p]) as rec:
        pass
    assert rec["identical"] and rec["before"] and rec["after"], "★ 两组哈希没落进产物"


# ── ③ 重放 stub: 弄坏 = 共享迭代器(M3-①) ──────────────────────────────────
def test_reverse_shared_iterator_mispairs_draws():
    draws = {f"d{i}": {"knots": [{"key": "belong", "intensity": 0.1 * i}]} for i in range(5)}
    good = H.replay_draws(draws)
    # ThreadPoolExecutor 下调用顺序是**不保证**的; 用乱序调用把竞态的后果确定化
    order = ["d2", "d0", "d4", "d1", "d3"]
    for tag in order:
        got = good(None, None, tag)["knots"][0]["intensity"]
        assert got == draws[tag]["knots"][0]["intensity"], f"★ 按 tag 索引竟然错配 {tag}"

    it = iter(list(draws.values()))          # ← 上一轮实际写法, 也是缺陷本体
    bad = lambda prompt, taxo, tag: next(it)
    mispaired = [tag for tag in order
                 if bad(None, None, tag)["knots"][0]["intensity"]
                 != draws[tag]["knots"][0]["intensity"]]
    assert mispaired, "★ 共享迭代器竟然没错配 —— 换个乱序, 否则这条闸验不到缺陷"
    _RED.append(("共享迭代器错配", f"{len(mispaired)}/{len(order)} 个 tag 拿到别人的 draw"))

    # 未登记 tag 必须炸, 不许静默返回 None(会被聚合层吞成「本次抽样失败」)
    _must_raise("重放 stub: 未知 tag 必须抛", good, None, None, "d999")


# ── ④ 判据非重言: 弄坏 = 换成 L3 instrument_hash(M2) ─────────────────────
def test_reverse_L3_would_call_a_dead_constant_load_bearing():
    r = _PC
    dead = r["arms"]["dead_absurd"]
    assert dead["L1_changed"] is False and dead["L2_changed"] is False, \
        "★ 死常量在 L1/L2 上就变了 —— 要么工况漂了(k 已 >5), 要么装置错了"
    assert dead["L3_changed_TAUTOLOGY_NOT_EVIDENCE"] is True, (
        "★ 改一个**永不取用**的死常量, instrument_hash 竟然没变 —— "
        "那 M2 的重言论断在本仓不成立, 整套判据要重新验收")
    _RED.append(("L3 重言", "同一死常量: L1/L2 不变 而 L3 变 ⇒ 用 L3 判必然误判成承重"))
    assert r["gates"]["L3_is_tautology_confirmed"] is True


# ── ⑤ 扫描面: 弄坏 = 砍掉 accuracy/(M3-②) ────────────────────────────────
def test_reverse_narrow_scan_surface_loses_a_real_consumer():
    sym = "negative_examples_prompt"          # 真实消费者在 accuracy/run_gates.py
    full_coarse, full_strict = H.scan_refs(sym)
    assert full_coarse > 0, f"★ 全扫描面都找不到 {sym} —— 扫描器坏了"
    assert full_strict <= full_coarse, "★ 严计不可能大于粗计"

    saved = H.SCAN_DIRS
    try:
        H.SCAN_DIRS = ("accuracy",)
        acc_only, _ = H.scan_refs(sym)
        H.SCAN_DIRS = ("scripts", "probes")   # ← 上一轮的扫描面
        narrow, _ = H.scan_refs(sym)
    finally:
        H.SCAN_DIRS = saved
    assert acc_only > 0, (
        f"★ accuracy/ 里找不到 {sym} —— 扫描面没真的走进 accuracy/, M3-② 的盲区还在")
    assert narrow < full_coarse, "★ 砍掉 accuracy/ 后计数没掉 —— 这条闸验不到盲区"
    _RED.append(("扫描面盲区",
                 f"{sym}: 全面 coarse={full_coarse} · 只看 accuracy/={acc_only} · "
                 f"上一轮扫描面(scripts+probes)={narrow} ⇒ 会漏掉 {full_coarse - narrow} 处"))
    # M4: 必须报两个数
    assert isinstance(full_coarse, int) and isinstance(full_strict, int)


# ── ⑥ 变异锚点: 弄坏 = 锚点打空(空臂) ─────────────────────────────────────
def test_reverse_empty_mutation_arm_must_be_rejected():
    _must_raise("变异锚点打空必须抛",
                H.replace_once("__NOT_IN_ANY_SOURCE__", "x"), "def f(): pass")
    # 正向: 真锚点必须恰好命中一次
    m = H.replace_once("a = 1", "a = 2")
    assert m("a = 1\n") == "a = 2\n"


# ── 判官自己必须验收通过, 且工况与产物同行(M7) ────────────────────────────
def test_positive_control_passed_and_carries_its_operating_point():
    r = _PC
    assert r["passed"] is True, f"★ 判官未验收通过, 卡在: {r['failed_gates']}"
    op = r["operating_point"]
    for key in ("market", "profile", "k_distribution", "corpus_sha256",
                "n_archive_files", "decided_at", "drift_rule", "M8_structural_bias"):
        assert key in op, f"★ 工况缺 {key} —— 没有工况的判决没有意义"
    # ★ 工况在测试时被**重新实测**: 语料一变, 产物里的判决当场失效
    live = H.operating_point(H.corpus())
    assert live["corpus_sha256"] == op["corpus_sha256"], (
        "★ 存量语料已漂移 ⇒ _positive_control.json 里的判决当场失效, 必须重跑 "
        f"(产物 {op['corpus_sha256'][:12]} vs 现测 {live['corpus_sha256'][:12]})")
    assert live["k_distribution"] == op["k_distribution"], "★ k 分布漂移 ⇒ 判决失效"
    assert r["file_integrity"]["identical"] is True, "★ R2: 仓内被测文件被改动"
    assert r["checks"]["tripwire_tripped"] == [], "★ R1: 绊线被触发过"
    assert "UNREACHABLE" in r["judge_verdict_on_dead_constant"], (
        "★ 死常量应判 UNREACHABLE(k≥6 即复活), 不是 NO_CONSUMER —— 见 M8 结构性偏倚")


_PC = H.positive_control()


def test_market_in_operating_point_is_scanned_not_asserted():
    """★★★ CE-21(a): 装置里那句「仓内无 market 字段(已实扫)」**是假的**, 且是 CE-2 的源头 ——
    凡直接把 operating_point() 落进产物的 agent 都会再抄一遍。被指出两轮未改, 2026-09-12 修。

    本闸要求它**真扫**, 且**不许**回落到任何预写结论。
    """
    import ablation_harness_v3 as H
    m = H._market_facts()
    assert isinstance(m, dict), "★ market 工况又变回一个写死的串了"
    assert "★口径" in m, "★ 没写扫描口径 —— 没有口径的数字不是证据"
    assert isinstance(m.get("总命中"), int) and m["总命中"] > 0, (
        "★★★ market 实扫命中 %r —— 若真是 0, 请**连同口径一起**说明; "
        "而四轮消融各自独立重扫分别得 33/44/56/61, 没有一个是 0" % m.get("总命中"))
    blob = __import__("json").dumps(m, ensure_ascii=False)
    assert "仓内无 market 字段" not in blob or "曾经是假的" in blob, (
        "★★★ 那句假话又以现行主张的形式回来了")
    # 扫不动时必须说扫不动, 不许给一个数
    import unittest.mock as _m
    with _m.patch.object(H.pathlib.Path, "rglob", side_effect=OSError("boom")):
        bad = H._market_facts()
    assert "总命中" not in bad and "实扫失败" in str(bad.get("★口径", "")), (
        "★★★ 扫不动时仍给出了结论 —— 「没查」被写成了「查过没有」: %r" % bad)
    return m["总命中"], m["逐目录"]

if __name__ == "__main__":
    _mk = test_market_in_operating_point_is_scanned_not_asserted()
    for name, fn in sorted((n, f) for n, f in globals().items() if n.startswith("test_")):
        fn()
    print("test_cce_ablation_harness_v3: OK")
    print(f"  阳性对照 passed={_PC['passed']} · 语料 {_PC['operating_point']['n_archive_files']} 份 "
          f"· k 分布 {_PC['operating_point']['k_distribution']} "
          f"· sha {_PC['operating_point']['corpus_sha256'][:12]}")
    print(f"  ★ 实际见红 {len(_RED)} 处:")
    for what, how in _RED:
        print(f"    · {what} → {how}")
