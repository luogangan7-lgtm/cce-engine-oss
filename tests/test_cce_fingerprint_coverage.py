"""指纹必须覆盖**真正发给模型的那份 prompt**。

## 这条闸为什么存在
2026-09-05 全系统消融审计查出一个 P0:
`s1_prompt_sha256` 哈希的是 `_stage1_case(...)` = **238 字的 case 外壳**,
而实际送进模型的是 `build_prompt(case)` = **4403 字**, 里面装着
13 类 EMOTIONS · 7 类 ACTIONS · 17 个 NEED_KEYS · 47KB NEED_TAXO ·
DESIRE_TAXO · appraisal 五维规范 · 输出 JSON schema。
⇒ **覆盖率 5.4%, 漏掉的 94.6% 恰好是本体载荷。**

实测反证(当时):
· 砍掉 5 类情绪 / 砍掉 12 个 need code / 清空 need 分类学 —— 真实 prompt 变了,
  `instrument_hash` **一字不变**。
· 反向: 改一个 k=3 时**永不取用**的温度档, `instrument_hash` **却会变**。
⇒ **标签空间是反的**: 最能改变读数的东西在指纹外, 死常量在指纹内。

## 三层讽刺(都已修, 记在这里防重演)
1. `INSTRUMENT_LINEAGE` gen2 的 note 白纸黑字写着「把 s1 prompt 纳入指纹」——
   **它从来没有纳入**。那次改的是外壳的哈希。假声明被 gen3/gen4 一路继承。
2. `cce_knot_classify.py` 顶部的注释写着「此前 prompt_sha256 只哈希了 _stage2_template
   ⇒ 静默换仪器 …… 现在 s1 与 s2 各出一份, 两边都忘不掉」——
   **同一个洞只是往上挪了一层调用栈**, 从来没被堵上。
3. `tests/test_cce_structural_gate.py` 里有一条断言**主动锁死**这个 bug
   (断言进指纹的就是那个外壳), 报错文案是「模板取哈希的方式变了」——
   **谁去修它, 它就判谁红**。已反转。

## ★ 已知的、本闸**不**覆盖的另一半缺陷
指纹**过度覆盖**: `_S1_BASE_TEMPS` 整条阶梯进指纹, 但 k=3 时只取前 3 档 ——
改第 6/7 档(永不取用)会造成**假换代**。这是独立缺陷, 未修, 见 §已知缺陷。
"""
import copy
import hashlib
import importlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import cce_knot_classify as KC          # noqa: E402
import exp_v4_full_validation as V      # noqa: E402

TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
KW = dict(k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")


def _hash():
    return KC.instrument_id(TAXO, **KW)["instrument_hash"]


def test_fingerprinted_string_is_the_string_sent():
    """★ 核心不变式: 进指纹的字符串, 必须**就是**发给模型的那一份。

    不是「包含」, 不是「大致相同」—— 是同一个函数产出的同一个字符串。
    另抄一份构造 prompt 的代码, 正是 gen1→gen4 那个洞的成因。
    """
    sent = V.build_prompt(KC._stage1_case("<TEXT>", "<CONTEXT>"))
    fingerprinted = KC._stage1_template()
    assert fingerprinted == sent, (
        f"★ 指纹取的字符串({len(fingerprinted)} 字) != 发给模型的 prompt({len(sent)} 字)。"
        "这就是那个 P0 的形状: 指纹漏掉本体载荷 ⇒ 改分类学不换仪器 ⇒ **静默换仪器**。"
    )


def test_coverage_is_not_a_token_wrapper():
    """外壳单独进指纹是不够的 —— 那正是旧的错法(238 / 4403 = 5.4%)。"""
    shell = KC._stage1_case("<TEXT>", "<CONTEXT>")
    full = KC._stage1_template()
    assert shell in full, "★ case 外壳不在指纹字符串里 —— 指纹取的不是真实 prompt"
    assert len(full) > 10 * len(shell), (
        f"★ 指纹字符串 {len(full)} 字, 外壳 {len(shell)} 字 —— "
        "比值太小, 像是又退回只哈希外壳了"
    )


ONTOLOGY_MUTATIONS = [
    ("砍掉 5 类 EMOTIONS", "EMOTIONS", lambda v: v[:8]),
    ("砍掉 12 个 NEED_KEYS", "NEED_KEYS", lambda v: v[:5]),
    ("清空 NEED_TAXO", "NEED_TAXO", lambda v: ""),
    ("清空 DESIRE_TAXO", "DESIRE_TAXO", lambda v: ""),
    ("砍掉 ACTIONS", "ACTIONS", lambda v: v[:2] if isinstance(v, list) else v),
]


def test_changing_the_ontology_changes_the_instrument():
    """★★ 本体载荷是这台仪器最承重的部分 —— 动它必须换代。

    旧口径下这些改动**一个都不会**改变 instrument_hash。
    """
    base = _hash()
    checked = 0
    for name, attr, mut in ONTOLOGY_MUTATIONS:
        if not hasattr(V, attr):
            continue
        saved = getattr(V, attr)
        try:
            new_val = mut(saved)
            if new_val == saved:
                continue
            setattr(V, attr, new_val)
            got = _hash()
            assert got != base, (
                f"★★ {name} 后 instrument_hash 仍是 {got} —— "
                "本体载荷没进指纹, 那个 P0 回来了"
            )
            checked += 1
        finally:
            setattr(V, attr, saved)
    assert checked >= 3, f"★ 只验到 {checked} 个本体常量, 太少 —— 检查 V 的属性名是否改了"
    assert _hash() == base, "★ 还原后指纹对不上 —— 测试自己把状态弄脏了"


def test_lineage_records_the_scope_widening_with_live_proof():
    """gen6 的「口径扩大」豁免必须**运行时自证**, 不能像 gen2 那样靠一句声称。"""
    gens = {g["gen"]: g for g in KC.INSTRUMENT_LINEAGE}
    assert 6 in gens, "★ gen6 未登记进谱系"
    assert gens[6]["s1_prompt_sha256"] == hashlib.sha256(
        KC._stage1_template().encode()).hexdigest()[:16], \
        "★ 谱系记的 s1_prompt_sha256 与现算不符"

    key = ("s1_prompt_sha256", gens[4]["s1_prompt_sha256"], gens[6]["s1_prompt_sha256"])
    assert key in KC.SCOPE_WIDENINGS, f"★ gen4→gen6 的口径扩大未具名登记: {key}"
    assert KC.SCOPE_WIDENINGS[key]["verify"](), \
        "★ 口径扩大的自证不成立 —— 旧口径覆盖的字符串不再是新口径的子串"


def test_scope_widening_is_not_a_general_escape_hatch():
    """★ 豁免必须逐条具名。一个没登记过的字段变化, 必须照旧判不可搬。"""
    cal = {"depends_on": ["model"], "snapshot": {"model": "SOMETHING-ELSE"}}
    r = KC.calibration_transfers(cal, TAXO, **KW)
    assert r["transfers"] is False, "★ 未登记的字段变化竟然被放行了 —— 豁免成了万能通道"
    assert "scope_widening_exemption" not in r


def _reverse_checks():
    """反向验证: 把洞放回去, 每条闸都必须判红。"""
    n = 0
    saved = KC._stage1_template

    # ① 退回只哈希外壳(旧 bug 原样) ⇒ 前三条闸都必须红
    KC._stage1_template = lambda context="<CONTEXT>", text="<TEXT>": KC._stage1_case(text, context)
    try:
        for fn in (test_fingerprinted_string_is_the_string_sent,
                   test_coverage_is_not_a_token_wrapper,
                   test_changing_the_ontology_changes_the_instrument):
            try:
                fn()
                raise SystemExit(f"★ 反向验证失败: 退回只哈希外壳后 {fn.__name__} 仍绿")
            except AssertionError:
                n += 1
    finally:
        KC._stage1_template = saved

    # ② 豁免自证被破坏 ⇒ 谱系闸必须红
    key = ("s1_prompt_sha256", "eadcdcdac46a5180", "61fe230f5c588c1f")
    entry = KC.SCOPE_WIDENINGS[key]
    orig = entry["verify"]
    entry["verify"] = lambda: False
    try:
        test_lineage_records_the_scope_widening_with_live_proof()
        raise SystemExit("★ 反向验证失败: 自证返回 False 后谱系闸仍绿")
    except AssertionError:
        n += 1
    finally:
        entry["verify"] = orig

    assert KC._stage1_template is saved
    return n


if __name__ == "__main__":
    test_fingerprinted_string_is_the_string_sent()
    test_coverage_is_not_a_token_wrapper()
    test_changing_the_ontology_changes_the_instrument()
    test_lineage_records_the_scope_widening_with_live_proof()
    test_scope_widening_is_not_a_general_escape_hatch()
    n = _reverse_checks()
    shell = len(KC._stage1_case("<TEXT>", "<CONTEXT>"))
    full = len(KC._stage1_template())
    print(f"test_cce_fingerprint_coverage: OK ("
          f"指纹字符串 == 发给模型的 prompt({full} 字, 旧口径只有 {shell} 字 = "
          f"{100*shell/full:.1f}%) | 本体载荷改动逐个都换代 | "
          f"gen6 口径扩大已具名登记且运行时自证 | 豁免不是万能通道 | "
          f"{n} 条反向验证: 退回旧错法与破坏自证 各自判红)")
