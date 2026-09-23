"""★★★ 验收闸(G)有**自己的版本** —— 只钉生产仪器抓不到「静默换闸」。零 API。

## 为什么
2026-09-08 实测: 改 `knots[].negative_examples_prompt` 会改**验收闸标注者的 prompt**,
而 `instrument_hash` **一字不变**(它只覆盖生产 s1/s2/model/endpoint/sampling)。
⇒ 在只有一个版本号的世界里, 这类改动是**静默换闸**: 发证的那台仪器变了, 而所有哈希都不动。

## 网页版 GPT-6 Pro 的裁定(2026-09-09)
「P 的实现与有效输入不变; G 的判读程序发生行为性变化。」
「**不能一面把 instrument_generation 叫『整体仪器代号』, 一面利用哈希未覆盖 G 来宣称没换代。**」
⇒ ① instrument_generation 的指称写成**明文**(只指 P) ② G 有独立的 gate_protocol_version/hash
   ③ 换 G 的事件类型是 **GATE_PROTOCOL_CHANGE**, 不得冒充「行为不变的 refactor」

## 本闸钉三件
· 指称明文还在 · 闸协议哈希与清单一致 · 三种失败模式都判红(反向实跑)
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIMAX_API_KEY", "ZERO_API_TEST_SENTINEL_NOT_A_KEY")
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "accuracy"))
MAN = ROOT / "config" / "cce_core_manifest.json"


def _man():
    return json.loads(MAN.read_text(encoding="utf-8"))


def test_the_referent_of_instrument_generation_is_explicit():
    """★★★ 「instrument_generation 只指生产 P」必须是**明文**, 不许退回隐含。"""
    m = _man()
    d = m.get("★★★instrument_generation_denotes")
    assert d, "★★★ 指称声明不见了 —— 退回隐含就等于把「哈希没覆盖 G」当成「G 没变」的借口"
    assert "仅指它" in d or "且仅指它" in d, "★ 必须写明**仅**指生产"
    assert "不" in d and "验收闸" in d, "★ 必须写明它不代表验收闸"


def test_gate_protocol_is_pinned_and_matches_live():
    """★ 闸协议哈希现算与清单一致 —— 不一致就是换了闸没换版本。"""
    import run_gates as RG
    m = _man()
    g = m.get("gate_protocol_expected")
    assert g, "★ 清单缺 gate_protocol_expected"
    assert RG.gate_protocol_hash() == g["hash"], (
        f"★★★ 现算闸协议哈希 {RG.gate_protocol_hash()} != 清单钉的 {g['hash']} —— "
        "闸的材料变了。走 GATE_PROTOCOL_CHANGE, 不要改这条断言。")
    assert RG.GATE_PROTOCOL_VERSION == g["version"]


def test_the_hash_really_covers_the_gate_materials():
    """★★ 灵敏度自证: 哈希必须**真的**随四块材料变 —— 否则是个恒定值假闸。"""
    import run_gates as RG
    base = RG.gate_protocol_hash()
    for name in ("KNOT_BRIEF", "DECISION_TREE", "NEGATIVE_EXAMPLES", "DIST_TMPL"):
        real = getattr(RG, name)
        setattr(RG, name, real + "★探针")
        try:
            assert RG.gate_protocol_hash() != base, (
                f"★★★ 改 {name} 不改变闸协议哈希 —— 那一块**没被覆盖**, 本闸对它是零灵敏度")
        finally:
            setattr(RG, name, real)
    assert RG.gate_protocol_hash() == base, "★ 复原后哈希应回到原值"


def test_changing_negative_examples_moves_the_gate_hash_but_not_instrument_hash():
    """★★★ 这一条是整件事的由来: 改负例 **动闸不动生产**。两个哈希各管一边。"""
    import copy
    import run_gates as RG
    import cce_knot_classify as CK
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    t1 = copy.deepcopy(taxo)
    for k in t1["knots"]:
        if k["key"] == "suspend":
            k["negative_examples_prompt"] += "; ★闸探针"
            break

    def ih(t):
        r = CK.instrument_id(t, k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")
        return (r[1] if isinstance(r, tuple) else r)["instrument_hash"]
    assert ih(taxo) == ih(t1), "★ 负例现在会动 instrument_hash 了 —— 换代路由要重定"

    base = RG.gate_protocol_hash()
    real = RG.NEGATIVE_EXAMPLES
    RG.NEGATIVE_EXAMPLES = real + "; ★闸探针"
    try:
        assert RG.gate_protocol_hash() != base, (
            "★★★ 改负例**不动**闸协议哈希 —— 那这套版本机制没抓到它要抓的那件事")
    finally:
        RG.NEGATIVE_EXAMPLES = real


def _reverse_checks():
    """★ 三种失败模式**实跑**一遍, 不靠读代码断言。"""
    import cce_core_boundary as B
    import run_gates as RG
    n = 0
    assert B.check()[0], "★ 起点必须是绿的"

    real_h, real_v = RG.gate_protocol_hash, RG.GATE_PROTOCOL_VERSION
    # ① 静默换闸: 哈希变、版本不变
    RG.gate_protocol_hash = lambda: "deadbeefdeadbeef"
    try:
        ok, errs, _ = B.check()
        assert not ok and "静默换闸" in " ".join(errs), "★ 反向验证失败: 静默换闸没判红"
        n += 1
        # ② 换代但没留痕
        RG.GATE_PROTOCOL_VERSION = real_v + 1
        ok, errs, _ = B.check()
        assert not ok and "GATE_PROTOCOL_CHANGE" in " ".join(errs), "★ 反向验证失败: 换代无留痕没判红"
        n += 1
    finally:
        RG.gate_protocol_hash = real_h
        RG.GATE_PROTOCOL_VERSION = real_v
    # ③ **无协议变化的跳号** ⇒ 红
    #    ★ 2026-09-09 更正: 原来测的是「材料没变时跳版本」—— **判据写窄了**。
    #      材料没变也可以合法换版(改判据/聚合/资格筛选/缺失重试规则都算协议修订),
    #      该禁的是**没有任何协议变化记录**的跳号。
    RG.GATE_PROTOCOL_VERSION = real_v + 1
    try:
        ok, errs, _ = B.check()
        assert not ok and "无协议变化的跳号" in " ".join(errs), "★ 反向验证失败: 无留痕跳号没判红"
        n += 1
    finally:
        RG.GATE_PROTOCOL_VERSION = real_v
    assert B.check()[0], "★ 复原后必须回到绿"
    return n


if __name__ == "__main__":
    test_the_referent_of_instrument_generation_is_explicit()
    test_gate_protocol_is_pinned_and_matches_live()
    test_the_hash_really_covers_the_gate_materials()
    test_changing_negative_examples_moves_the_gate_hash_but_not_instrument_hash()
    n = _reverse_checks()
    import run_gates as RG
    print(f"test_cce_gate_protocol_version: OK ("
          f"instrument_generation 的指称已是**明文**(只指生产 P) | "
          f"gate_protocol v{RG.GATE_PROTOCOL_VERSION} hash {RG.gate_protocol_hash()} 与清单一致 | "
          f"★★灵敏度自证: 四块材料**每一块**都真的进哈希 | "
          f"★★★改负例 **动闸不动生产**(两个哈希各管一边, 这正是整件事的由来) | "
          f"{n} 条失败模式实跑判红(静默换闸 / 换代无留痕 / **无协议变化的跳号**) | "
          f"★判据已放宽到正确范围: 材料没变**也可以**合法换版(改判据/聚合/资格筛选/缺失规则), "
          f"但须留痕并写明改的是协议哪一部分)")
