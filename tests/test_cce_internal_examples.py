"""分类学的 `internal_examples` 必须指向**语料里真实存在**的作者 —— 零 API。

## ★★★ 为什么这条闸今天才有
`internal_examples` 在 `scripts/consistency_check.py` 的 **DESCRIPTIVE 豁免名单**里,
**从不被任何东西核对**。实测结果:

| 结 | 例子 | 问题 |
|---|---|---|
| **audit** | user_87#c2, user_65 | **两个都不在语料里 ⇒ 可核对的正例 0 条** |
| **belong** | user_154, user_73 | user_154 不在语料; **user_73 是锚例作者** ⇒ 唯一可核对的正例**就是考题** |
| reward | user_87#c1 | 格式都不一样(带 #c1) |
| display | user_28 | 与锚例作者撞车 |
| pain_seek/injustice/suspend | 各 1 个 | 不在语料里 |

★★ 这是今天第**三**次遇到同一个形状: **豁免名单里的字段无人核对, 于是它可以任意腐坏。**
   前两次: ① `annotation_protocol.gate_record` 与 `status` 互相矛盾并存数月
          ② `TOPLEVEL_DOC_ONLY` 登记表被消融的引用计数当成消费者, 14 个死字段被虚增成 INCONCLUSIVE

## ★ 这条闸不做什么
**不判红当前状态。** 修好它需要领域判断(哪个作者才真的例示 belong), 那不是机械替换。
本闸只做两件: **把现状逐字钉住**, 和**防止它继续变坏**。
★ 一旦有人修好了(缺失数减少), 断言会红并要求更新基线 —— 这是有意的: 改善也要留痕。

## ★★ 对 belong 那条结论的影响
belong 的 codebook 里**从来没有一个干净的、可核对的正例**。
⇒ 「belong 在评论上共识 argmax 0/81」这件事, 有一部分可能来自**它的定义本身就没有被样例锚定**,
   而不是来自语料。这是 belong 处置问题的**第五条通道**(前四条见
   tests/data/belong_disposition_rule_prereg.json)。
"""
import collections
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("MINIMAX_API_KEY", "dummy-for-import-only")
sys.path.insert(0, str(ROOT / "accuracy"))

TAXO = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
CORPUS = json.loads((ROOT / "accuracy/data/corpus.json").read_text(encoding="utf-8"))
AUTHORS = collections.Counter(c["a"] for c in CORPUS)

# ★ 2026-09-07 实测基线。**逐字钉住**, 不是豁免。
BASELINE_MISSING = {
    "pain_seek": ["user_66"], "injustice": ["user_89"], "belong": ["user_154"],
    "reward": ["user_87#c1"], "suspend": ["user_26"], "audit": ["user_87#c2", "user_65"],
}
BASELINE_ANCHOR_COLLISION = {"belong": ["user_73"], "display": ["user_28"]}


def _anchor_authors():
    import run_gates as RG
    return {c["a"] for c in CORPUS if c["id"] in RG.ANCHOR_IDS}


def _audit():
    anch = _anchor_authors()
    miss, coll, usable = {}, {}, {}
    for k in TAXO["knots"]:
        ex = k.get("internal_examples") or []
        m = [a for a in ex if a not in AUTHORS]
        c = [a for a in ex if a in anch]
        if m:
            miss[k["key"]] = m
        if c:
            coll[k["key"]] = c
        usable[k["key"]] = sum(AUTHORS.get(a, 0) for a in ex if a not in anch)
    return miss, coll, usable


def test_the_breakage_has_not_grown():
    """★ 现状钉死。变坏 ⇒ 红; 变好 ⇒ 也红(要求更新基线, 改善必须留痕)。"""
    miss, coll, _ = _audit()
    assert miss == BASELINE_MISSING, (
        f"★★ internal_examples 的「不在语料里」集合变了。\n  现在: {miss}\n  基线: {BASELINE_MISSING}\n"
        "  ★ 若是**修好了**, 请更新 BASELINE_MISSING 并在此写明修了哪几条; "
        "若是**变坏了**, 那就是又往里塞了指向不存在作者的例子。")
    assert coll == BASELINE_ANCHOR_COLLISION, (
        f"★★ 与锚例作者撞车的集合变了。\n  现在: {coll}\n  基线: {BASELINE_ANCHOR_COLLISION}")


def test_audit_has_zero_usable_examples():
    """★★★ audit 的两个例子都不在语料里 —— 它的 codebook 没有任何可核对的正例。"""
    _, _, usable = _audit()
    assert usable["audit"] == 0, (
        f"★ audit 现在有 {usable['audit']} 条可核对正例了(基线 0) —— 修好了就更新本断言")


def test_belong_has_no_clean_example():
    """★★★ belong 唯一可核对的正例**就是资格考的考题** —— 这是它处置问题的第五条通道。"""
    miss, coll, usable = _audit()
    assert "user_154" in miss.get("belong", []), "★ belong 的缺失例变了"
    assert "user_73" in coll.get("belong", []), "★ belong 与锚例撞车这件事变了"
    assert usable["belong"] == 0, (
        f"★ belong 现在有 {usable['belong']} 条**非锚例**的可核对正例了(基线 0) —— "
        "那 tests/data/belong_disposition_rule_prereg.json 里「没有干净正例」的说法要改")


def test_it_is_still_exempt_from_the_consistency_check():
    """★ 记住它为什么能坏这么久: 它在豁免名单里。"""
    cc = (ROOT / "scripts/consistency_check.py").read_text(encoding="utf-8")
    assert "internal_examples" in cc, "★ 它连豁免名单都不在了? 那 C1 应该在报它是死规则"
    assert "DESCRIPTIVE" in cc
    # ★ 豁免不等于不该有闸 —— 本文件就是那个闸。这条断言防的是「以为豁免了就没人管」。
    assert (ROOT / "tests/test_cce_internal_examples.py").exists()


def _reverse_checks():
    n = 0
    g = globals()
    saved = g["AUTHORS"]
    g["AUTHORS"] = collections.Counter({**saved, "user_154": 1})   # 假装修好了 belong
    try:
        test_belong_has_no_clean_example()
        raise SystemExit("★ 反向验证失败: 补上 user_154 后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["AUTHORS"] = saved
    g["AUTHORS"] = collections.Counter({k: v for k, v in saved.items() if k != "user_28"})
    try:
        test_the_breakage_has_not_grown()
        raise SystemExit("★ 反向验证失败: 让 user_28 消失后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["AUTHORS"] = saved
    return n


if __name__ == "__main__":
    test_the_breakage_has_not_grown()
    test_audit_has_zero_usable_examples()
    test_belong_has_no_clean_example()
    test_it_is_still_exempt_from_the_consistency_check()
    n = _reverse_checks()
    miss, coll, usable = _audit()
    print(f"test_cce_internal_examples: OK ("
          f"★**{len(miss)}/9 个结的例子指向语料里不存在的作者** | "
          f"★★audit 可核对正例 **0** 条 · belong **0** 条(唯一那条是锚例作者) | "
          f"{len(coll)} 个结与锚例作者撞车 | 现状逐字钉住, 变好变坏都会红 | "
          f"★ 它在 consistency_check 的 DESCRIPTIVE 豁免名单里 —— **今天第三次遇到"
          f"「豁免名单里的字段无人核对」** | {n} 条反向验证判红)")
