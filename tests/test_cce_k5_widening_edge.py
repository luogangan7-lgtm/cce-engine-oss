#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: k=5 的口径扩大继承边 —— 它解锁 outbound_post 的结层 top-1, 必须被逐条守住。

★★★ 这条边是 2026-09-13 补登记的。为什么它之前不在:
`SCOPE_WIDENINGS` 是 2026-09-06 为了让 `cce_k1_status` 继承 gen4 判定才建的,
当时**只登记了 k=3 那条边**(565470cf26c16d01 → d4cce4c745f3f991), **漏了 k=5 的兄弟**
(0e9ca1d4e7a2f180 → c4419c3e53aa2fa9)。后果: `outbound_post` 结层**零可用读数**,
而 `K1_TOP1_ON_K5` 那 40 条读数**早在 2026-09-04 就采过并判过 TOP1_USABLE**。
⇒ 这是「同一逻辑多份实现, 修了一份漏了其余」的**第四次**(库内前三次有记录)。

## 这条边为什么合法(不是放宽闸)
它用的自证函数就是 k=3 边**已在生产依赖**的那一个 —— `_s1_scope_widening_holds()`,
其内容是 `_stage1_case("<TEXT>","<CONTEXT>") in _stage1_template()`, **与 k 完全无关**。
⇒ **两条边同真同假。** 若 k=5 边不合法, 那么已在生产的 k=3 边同样不合法。
**只登记一条不是谨慎, 是不一致。**

## 结构性证据(本闸现算, 不是断言)
把 `s1_prompt_sha256` 换回旧口径 `eadcdcdac46a5180` 后重算 instrument_hash:
  k=3 → 565470cf26c16d01(登记表里有 K1_VERDICT)
  k=5 → 0e9ca1d4e7a2f180(登记表里有 K1_VERDICT_K5)
两台**都是同一次 gen4→gen6 口径扩大的前代**。重算复用生产自己那一行的序列化, 且**先自证**
能逐位复现两个现值 —— 复现不上就停, 不出结论。

## 它**没有**解锁什么
`intensity` / `weight` 在两台上**仍然扣发**(K1-v2 判 INSTRUMENT_WIDE_FAIL)。
本边只放行 `top-1`, 与 `k1_top1_k5_verdict.json` 的 `★intensity_weight_unchanged` 一致。
"""
import hashlib
import json
import pathlib
import socket
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import cce_k1_status as K      # noqa: E402
import cce_knot_classify as C  # noqa: E402

TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
OLD_S1 = "eadcdcdac46a5180"          # gen4 口径(238 字 case 外壳)
_INSTRUMENT_FIELDS = ("ontology_version", "s1_prompt_sha256", "s2_prompt_sha256",
                      "model", "endpoint", "sampling_policy")


def _tripwire():
    orig, tripped = socket.socket.connect, []

    def guard(s, a, *x, **k):
        tripped.append(a)
        raise AssertionError("★★★ 本闸发出了真实网络请求: %r" % (a,))
    socket.socket.connect = guard
    return orig, tripped


def _live(k):
    return C.instrument_id(TAXO, k=k, knot_n=C.KNOT_N,
                           s1_pairing="round_robin_over_%d_s1_draws" % k)


def _rehash(spec):
    """★ 逐字复用 cce_knot_classify.instrument_id 里那一行的序列化, 不自己发明。"""
    return hashlib.sha256(json.dumps({k: spec[k] for k in _INSTRUMENT_FIELDS},
                                     ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def test_the_rehash_method_reproduces_both_live_hashes_first():
    """★★★ 先自证判官: 用同一路径必须**逐位复现**两个现值, 复现不上就不许往下走。"""
    for k, want in ((3, "d4cce4c745f3f991"), (5, "c4419c3e53aa2fa9")):
        r = _live(k)
        assert r["instrument_hash"] == want, "★ k=%d 的现仪器变了: %s" % (k, r["instrument_hash"])
        assert _rehash(r["spec"]) == want, (
            "★★★ 重算方法复现不了生产现值(k=%d) —— 本闸的结构性论证**不成立**, 停" % k)


def test_both_edges_are_the_same_caliber_widening():
    """★★★ 结构性证据: k=3 与 k=5 的前代**都在判定登记表里**, 且都由同一次口径扩大得到。"""
    got = {}
    for k in (3, 5):
        sp = dict(_live(k)["spec"])
        sp["s1_prompt_sha256"] = OLD_S1
        got[k] = _rehash(sp)
    assert got[3] == "565470cf26c16d01", "★ k=3 的前代反算不对: %s" % got[3]
    assert got[5] == "0e9ca1d4e7a2f180", "★ k=5 的前代反算不对: %s" % got[5]
    for k, h in got.items():
        assert h in K.VERDICT_BY_INSTRUMENT, (
            "★★ k=%d 的前代 %s 不在 VERDICT_BY_INSTRUMENT 里 —— 没得继承" % (k, h))
    return got


def test_the_k5_edge_is_registered_and_self_proving():
    """★★★ 边必须在册, 且它的 verify() 与 k=3 那条**是同一个函数对象**。"""
    edges = {(w.get("from_instrument"), w.get("to_instrument")): w
             for w in C.SCOPE_WIDENINGS.values()}
    k3 = edges.get(("565470cf26c16d01", "d4cce4c745f3f991"))
    k5 = edges.get(("0e9ca1d4e7a2f180", "c4419c3e53aa2fa9"))
    assert k3, "★ k=3 那条边不见了 —— 生产 top-1 会全面扣发"
    assert k5, ("★★★ k=5 的口径扩大边**不在 SCOPE_WIDENINGS 里** —— outbound_post 结层会退回零可用; "
                "而它与 k=3 那条是同一次扩大, 只登记一条是不一致不是谨慎")
    assert k5["verify"] is k3["verify"], (
        "★★★ 两条边的自证函数**不是同一个** —— 若 k=5 用了另一个(更松的)自证, "
        "那它就不再与 k=3 同真同假, 本闸的合法性论证失效")
    assert k5["verify"]() is True, "★★ k=5 边的自证当下不成立, 继承应当已经失效"
    return len(C.SCOPE_WIDENINGS)


def test_it_unlocks_top1_for_k5_and_nothing_else():
    """★★★ 影响面**恰好**是一项: k=5 的 top-1。其余一律不动。"""
    h3, h5 = _live(3)["instrument_hash"], _live(5)["instrument_hash"]
    ok5, why5 = K.knot_readout_usable("top1", instrument_hash=h5)
    assert ok5, "★★★ k=5 的 top-1 仍不可用: %s" % why5
    assert "8/8" in why5 or "TOP1_USABLE" in why5 or "达标" in why5, (
        "★ 放行理由不是那份 K1 判定: %s" % why5)
    ok3, _ = K.knot_readout_usable("top1", instrument_hash=h3)
    assert ok3, "★ k=3 的 top-1 被连累了"
    for layer in ("intensity", "weight"):
        for k, h in ((3, h3), (5, h5)):
            ok, _ = K.knot_readout_usable(layer, instrument_hash=h)
            assert not ok, ("★★★ %s 在 k=%d 上被**顺手解锁**了 —— 本边只该放行 top-1; "
                            "K1-v2 对两台都判 INSTRUMENT_WIDE_FAIL" % (layer, k))


def test_the_instrument_hashes_did_not_change():
    """★★★ 这**不是换代**: SCOPE_WIDENINGS 不在 _INSTRUMENT_FIELDS 里 ⇒ 既有标定全部仍有效。

    若哪天它进了指纹覆盖面, 本条会红 —— 那时所有既有读数都要重新判可比性。
    """
    assert _live(3)["instrument_hash"] == "d4cce4c745f3f991"
    assert _live(5)["instrument_hash"] == "c4419c3e53aa2fa9"
    scope = _live(3)["hash_scope"]["instrument"]
    assert "SCOPE_WIDENINGS" not in scope and set(scope) == set(_INSTRUMENT_FIELDS), (
        "★★★ 指纹覆盖面变了 %r —— 本边是否构成换代必须重新判" % scope)


def test_the_verdict_file_it_inherits_from_is_the_preregistered_one():
    """★★ 它继承的那份判定必须是**测量前冻结判据**的那一份, 不是事后挑的。"""
    p = pathlib.Path(K.K1_VERDICT_K5)
    assert p.exists(), "★ 继承的判定文件不在: %s" % p
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["instrument_hash"] == "0e9ca1d4e7a2f180"
    assert d["verdict"] == "TOP1_USABLE"
    assert "prereg" in d and (ROOT / d["prereg"]).exists(), "★ 判定没有对应的预注册"
    pre = json.loads((ROOT / d["prereg"]).read_text(encoding="utf-8"))
    assert "frozen_before_measurement" in json.dumps(pre, ensure_ascii=False), \
        "★★ 那份预注册没有「测量前冻结」的自我声明"
    assert d.get("★source", "").find("零新增调用") >= 0 or "复用" in d.get("★source", ""), \
        "★ 该判定的来源声明变了, 请复核"
    return d["checks"]


if __name__ == "__main__":
    orig, tripped = _tripwire()
    try:
        test_the_rehash_method_reproduces_both_live_hashes_first()
        old = test_both_edges_are_the_same_caliber_widening()
        n = test_the_k5_edge_is_registered_and_self_proving()
        test_it_unlocks_top1_for_k5_and_nothing_else()
        test_the_instrument_hashes_did_not_change()
        checks = test_the_verdict_file_it_inherits_from_is_the_preregistered_one()
    finally:
        socket.socket.connect = orig
    assert not tripped, "★★★ 绊线被触发: %r" % tripped
    print("test_cce_k5_widening_edge: OK ("
          f"★★★补登记 k=5 的口径扩大继承边 —— 2026-09-06 建 SCOPE_WIDENINGS 时**只登记了 k=3, 漏了 k=5 兄弟**, "
          "「同一逻辑多份实现修了一份漏其余」的**第四次** | "
          f"★★★结构性证据(现算, 先自证判官能逐位复现两个现值): 换回旧口径 {OLD_S1} 后 "
          f"k=3→{old[3]} · k=5→{old[5]}, **两台都在判定登记表里** ⇒ 同一次扩大 | "
          "★★★两条边的 verify() 是**同一个函数对象**(与 k 无关的子串自证) ⇒ **同真同假**; "
          "若 k=5 用了另一个更松的自证, 本闸当场红 —— 合法性靠的就是这个一致性 | "
          f"★★影响面**恰好一项**: k=5 的 top-1 放行(依据 {checks[1]['value']}); "
          "intensity/weight 在**两台上都仍扣发**, 顺手解锁会红 | "
          "★★★**不是换代**: SCOPE_WIDENINGS 不在指纹覆盖面里 ⇒ instrument_hash 两台皆未变、既有标定全部仍有效; "
          "哪天它进了覆盖面本闸会红 | "
          "★ 继承的判定必须是**测量前冻结判据**的那一份(k1_v2_k5_prereg) | ★ 零 API: 绊线未触发)")
