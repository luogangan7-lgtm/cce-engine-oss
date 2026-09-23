"""★★★ 被登记为「描述性/纯文档」的字段, 不许悄悄地在驱动仪器。零 API。

## 发现
`consistency_check.DESCRIPTIVE` 里有两个字段**真的进 prompt**:
· `knots[].name` → BOTH(闸与生产都注入)
· `knots[].typical_codes` → PROD_ONLY(且进 `s2_prompt_sha256` ⇒ 改它会换 instrument_hash)

## ★ 它**当前**不造成误红, 风险在反方向
DESCRIPTIVE 的作用是免掉「必须有代码消费者」这条检查。这两个字段确实有消费者。
★★ 但**若有人把 typical_codes 从生产 prompt 里拿掉**, 它就变成死字段, 而一致性闸
**永远不会发现** —— 因为它被登记成「描述性的, 不用查」。
⇒ 一个驱动仪器的字段贴着「描述性」标签, 等于开了一条**无人看守的退化通道**。

## ★★ 这是同一个形状的第四次
① gate_record 与 status 互相矛盾并存数月 ② TOPLEVEL_DOC_ONLY 被引用计数当成消费者
③ internal_examples 七个例子六个不在语料 ④ **本条**。
形状每次都一样: **名单里的东西没人再看它一眼。**

## 本闸做什么
**不动 DESCRIPTIVE 名单**(挪出去会得到一条语义不对的绿)。只做两件:
钉住交集**恰为这两个**; 并钉住这两个**仍然**在 prompt 里(退化通道一旦被走, 立刻红)。
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER = ROOT / "tests" / "data" / "taxonomy_field_reach_ledger.json"
DOC = ROOT / "tests" / "data" / "descriptive_exemption_vs_reach.json"
KNOWN = {"knots[].name": "BOTH", "knots[].typical_codes": "PROD_ONLY"}


def _lists():
    src = (ROOT / "scripts" / "consistency_check.py").read_text(encoding="utf-8")
    ns = {}
    exec(re.search(r"^DESCRIPTIVE = \{.*?\}", src, re.S | re.M).group(), ns)
    exec(re.search(r"^TOPLEVEL_DOC_ONLY = \{.*?\n\}", src, re.S | re.M).group(), ns)
    return ns["DESCRIPTIVE"], set(ns["TOPLEVEL_DOC_ONLY"])


def _reach():
    return json.loads(LEDGER.read_text(encoding="utf-8"))["per_field"]


def _intersect():
    desc, top = _lists()
    led = _reach()
    hit = {}
    for f in sorted(set(desc) | top):
        for key in (f"knots[].{f}", f):
            r = led.get(key)
            if r and r != "NEITHER":
                hit[key] = r
    return hit


def test_the_intersection_is_exactly_the_two_known_fields():
    """★★★ 新增任何「被登记成描述性却进 prompt」的字段 ⇒ 红。"""
    got = _intersect()
    assert got == KNOWN, (
        f"★★★ 「描述性/纯文档」名单与 prompt 到达台账的交集变了。\n"
        f"  现算: {got}\n  已登记: {KNOWN}\n"
        "★ 新增的项意味着又有一个**驱动仪器**的字段被贴上了「不用查」的标签 —— "
        "这是本仓第四次遇到的形状。要么把它接进真正的检查, 要么在 "
        "tests/data/descriptive_exemption_vs_reach.json 里具名登记并写明为什么安全。\n"
        "★ 减少的项也要红: 说明退化通道被走了(见下一条断言)。")


def test_the_two_fields_still_actually_reach_the_prompt():
    """★★ 退化通道的守卫: 这两个字段一旦不再进 prompt, 就变成了无人看守的死字段。"""
    led = _reach()
    for f, want in KNOWN.items():
        assert led.get(f) == want, (
            f"★★★ {f} 从 {want} 变成了 {led.get(f)} —— "
            "它还在 DESCRIPTIVE 名单里, 于是**一致性闸不会发现它死了**。"
            "这正是本闸要防的那条退化通道。")


def test_the_decision_not_to_touch_the_list_is_recorded():
    """★ 「不动名单、只加交叉闸」这个决定必须留档, 否则下一个人会去改名单。"""
    d = json.dumps(json.loads(DOC.read_text(encoding="utf-8")), ensure_ascii=False)
    assert "不改 DESCRIPTIVE 名单" in d and "语义不对的绿" in d, "★ 「不动名单」的理由不见了"
    assert "第四次" in d, "★ 「这是同族第四次」这句不许删 —— 计数本身是证据"


def _reverse_checks():
    n, g = 0, globals()
    saved = g["_reach"]

    # ① 又一个描述性字段进了 prompt ⇒ 红
    bad = dict(_reach()); bad["knots[].evidence_level"] = "BOTH"
    g["_reach"] = lambda: bad
    try:
        test_the_intersection_is_exactly_the_two_known_fields()
        raise SystemExit("★ 反向验证失败: 新增描述性字段进 prompt 后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_reach"] = saved

    # ② 退化通道被走(typical_codes 不再进 prompt) ⇒ 红
    bad2 = dict(_reach()); bad2["knots[].typical_codes"] = "NEITHER"
    g["_reach"] = lambda: bad2
    try:
        test_the_two_fields_still_actually_reach_the_prompt()
        raise SystemExit("★ 反向验证失败: typical_codes 退化成死字段后仍绿")
    except AssertionError:
        n += 1
    finally:
        g["_reach"] = saved
    return n


if __name__ == "__main__":
    test_the_intersection_is_exactly_the_two_known_fields()
    test_the_two_fields_still_actually_reach_the_prompt()
    test_the_decision_not_to_touch_the_list_is_recorded()
    n = _reverse_checks()
    desc, top = _lists()
    print(f"test_cce_descriptive_exemption_vs_reach: OK ("
          f"扫 DESCRIPTIVE {len(desc)} 项 + TOPLEVEL_DOC_ONLY {len(top)} 项 | "
          f"★★★ 交集恰为 {sorted(KNOWN)} —— 两个**贴着「描述性」标签却在驱动仪器**的字段 | "
          f"退化通道已上守卫(它们不再进 prompt 就判红) | "
          f"★ 判定为**不动名单, 只加交叉闸**(挪出去会得到语义不对的绿) | "
          f"{n} 条反向验证判红)")
