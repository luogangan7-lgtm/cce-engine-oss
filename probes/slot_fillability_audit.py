#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**槽位可填性档案** —— 每个槽位「模型能不能自动填」的实测结论。**零模型调用**。

★★★ 它回答的是判据层能不能接进生产的**一半**: 六个槽位里哪些填得出、哪些填不出。

## ★★★ 为什么必须看**相对零基线的净增益**, 不能看准确率
r5 读到 speaker 68/68 · polarity 136/136 · citation 68/68 —— 看起来是满分。
但**同一批上零基线(完全不读文本的常数填充)拿 66/68 与 134/136** ⇒
**那几格的全部增益空间只有 2 格**。
⇒ 「满分」在这里**不等于能力**, 它等于「这批 items 在这个槽位上几乎没有区分度」。
★ 这正是 r4 那条教训(金标倾斜 38:2 ⇒ 不读文本能拿 93.6%)在 r5 上的重演 ——
  区别是这次**算了**。

## 怎么读
对每个槽位算三个数:
  · **零基线**能拿多少(下限, 结构上不读文本)
  · **金标**能拿多少(上限, 按定义满分)
  · **模型**拿多少
然后报 **净增益 = 模型 − 零基线**, 以及 **可得增益 = 金标 − 零基线**。
★★★ **可得增益接近 0 的槽位, 这批数据测不出任何东西** —— 它的准确率不许被引用为能力。
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "results/slot_filling_r5.json"
OUT = ROOT / "results" / "slot_fillability_audit.json"
SLOTS = ("speaker", "polarity", "time", "citation", "possession", "predicate")


def _arm(arms, prefix):
    return [v for a, v in arms.items() if a.startswith(prefix)][0]


def _cell(t, s):
    v = t["逐槽位"].get(s, {}).get("敏感")
    if not v:
        return None
    a, b = v.split("/")
    return int(a), int(b)


def build_result():
    d = json.loads(SRC.read_text(encoding="utf-8"))
    arms = d[[x for x in d if "五臂对照" in x][0]]
    M, Z, G = _arm(arms, "B_"), _arm(arms, "②"), _arm(arms, "①")
    SH, BS = _arm(arms, "③"), _arm(arms, "④")
    rows = {}
    for s in SLOTS:
        m, z, g = _cell(M, s), _cell(Z, s), _cell(G, s)
        if not m:
            continue
        gain, head = m[0] - z[0], g[0] - z[0]
        rows[s] = {
            "模型": "%d/%d" % m, "零基线": "%d/%d" % z, "金标": "%d/%d" % g,
            "手写浅层臂": "%d/%d" % _cell(SH, s), "最佳浅层规则": "%d/%d" % _cell(BS, s),
            "★净增益(模型−零基线)": gain,
            "★可得增益(金标−零基线)": head,
            "★取到了": ("%.0f%%" % (100 * gain / head)) if head else "—",
            "★★★这批数据能不能测出这一格": (
                "**不能** —— 可得增益只有 %d 格, 零基线已经拿 %d/%d。"
                "这一格的准确率**不得引用为能力**。" % (head, z[0], z[1])
                if head <= 2 else
                "**能** —— 可得增益 %d 格。" % head),
        }
    testable = [s for s, v in rows.items() if v["★可得增益(金标−零基线)"] > 2]
    return {
        "block": "SLOT_FILLABILITY_AUDIT",
        "★零调用": "只重算 results/slot_filling_r5.json 里已付费的 68 次读数, **不发起任何新调用**。",
        "★★★它回答什么": "六个槽位里, 模型**能不能自动填**。"
            "★ 判准是**相对零基线的净增益**, 不是准确率。",
        "★★★为什么不能看准确率": "r5 读到 speaker 68/68 · polarity 136/136 · citation 68/68, "
            "而**同一批上零基线拿 66/68 与 134/136** ⇒ 那几格的**全部增益空间只有 2 格**。"
            "⇒ 「满分」在这里等于「**这批 items 在这个槽位上几乎没有区分度**」, 不等于能力。",
        "★★★这批数据只测得出这几个槽位": testable,
        "★★★结论": (
            "**唯一有区分度的槽位是 predicate**(可得增益 %d 格), 而模型只取到 %s。"
            "★ possession 的可得增益是 %d 格, 模型**净增益为负**(%+d) —— 比不读文本还差。"
            "★★ 其余四格(speaker/polarity/time/citation)的可得增益 ≤2, "
            "**这批数据测不出它们**, 它们的满分**不得引用为能力**。"
            % (rows["predicate"]["★可得增益(金标−零基线)"], rows["predicate"]["★取到了"],
               rows["possession"]["★可得增益(金标−零基线)"], rows["possession"]["★净增益(模型−零基线)"])),
        "★★★对「判据层能不能接进生产」的含义":
            "判据层要靠模型自动填槽位, 就得知道**哪几格填得出**。本轮的答案是: "
            "**有区分度的那一格(predicate)填不出**(取到 12%), "
            "**另一格(possession)填出来比不填还差**(净 −6), "
            "剩下四格**这批数据给不出答案**。"
            "⇒ **自动填槽位这条路, 在已测范围内没有可用的证据支持**。"
            "★ 边界: 只测了这 68 条手构 item 与这一个模型, **不得外推**。",
        "逐槽位": rows,
    }


def main():
    r = build_result()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print("槽位可填性档案(**零调用 · 重算 r5 已付费的 68 次**)\n")
    print("  %-11s %-9s %-9s %-9s %-7s %-7s %s"
          % ("槽位", "模型", "零基线", "金标", "净增益", "可得", "取到"))
    for s, v in r["逐槽位"].items():
        print("  %-11s %-9s %-9s %-9s %-7s %-7s %s"
              % (s, v["模型"], v["零基线"], v["金标"],
                 "%+d" % v["★净增益(模型−零基线)"], "%+d" % v["★可得增益(金标−零基线)"], v["★取到了"]))
    print("\n  这批数据测得出的槽位:", r["★★★这批数据只测得出这几个槽位"])
    print("\n  " + r["★★★结论"])
    print("\n→", OUT)


if __name__ == "__main__":
    main()
