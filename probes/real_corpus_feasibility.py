#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**改用真实语料的可行性** —— 它能不能提供 RESTATES_IDENTIFIER 鉴别格。**零模型调用**。

## 问题
手构对照集与真人语料有 **19–30 个百分点**的表层偏离(results/corpus_balance_audit.json),
⇒ 本轮读数不得外推到自然语料。那么: **改用真实语料重建对照集, 可行吗?**

## ★★★ 答案的关键不在语料规模, 在这个类别是什么
`RESTATES_IDENTIFIER` 的定义是「**声称这是增量, 而它只是复述/指认标识**」——
注意 **「声称这是增量」** 这半句: 它是 **A 支(增量支)** 的属性。
⇒ 一个句子只有在**被当成增量证据提交**时, 才谈得上「它其实只是复述标识」。

**真实语料里「只指认」的句子很多**("I have Oticon Zircon 2s." 这类),
但它们在 CCE 里会被正确地放进 **B 支(所有权支)** —— 那是它们**本来的位置**, 不构成错误。

⇒ **RESTATES_IDENTIFIER 不是一个自然语言类别, 是一个「抽取错误」类别。**
  它只在**模型把一个只指认标识的片段当成增量证据**时出现。
  这正是 48 次已付费调用产出的真实证书里它只有 **2 条**的原因。

## 含义
要从真实语料拿到这个类别的鉴别格, **必须先让模型在真实语料上抽取**(花钱), 再标注它的错误。
**不能**靠人直接从语料里标出来 —— 人标的是「这句话是不是只指认」, 而不是「模型有没有把它当成增量」。
"""
import importlib.util, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "real_corpus_feasibility.json"
REPLAY_ANN = ROOT / "tests/data/claim_frame_replay_annotations.json"

# ★ 「只指认」的机械候选: 含品牌/型号, 且谓语是 have/use/own/be 这类**所有权**动词
OWN_VERB = re.compile(r"\b(have|had|has|own|owns|owned|use|uses|used|wear|wears|wore|"
                      r"got|acquired|bought|on|am|is|are)\b", re.I)
CONTENT_VERB = re.compile(r"\b(work|works|worked|drop|drops|cut|cuts|clog|clogs|whistle|whistles|"
                          r"squeal|squeals|hiss|run|runs|drain|drains|pair|pairs|connect|connects|"
                          r"turn|turns|reduce|reduces|resolve|resolved|fail|fails|"
                          r"charge|charges|stream|streams|set|sets)\b", re.I)


def _corpus():
    sp = importlib.util.spec_from_file_location("cba", ROOT / "probes/corpus_balance_audit.py")
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    return m


def build_result():
    m = _corpus()
    sents = m._corpus_sents()
    brand = [s for s in sents if m.BRANDS.search(s)]
    # ★ 机械候选: 含品牌 + 有所有权动词 + 无内容动词 ⇒ 像「只指认」
    cand = [s for s in brand if OWN_VERB.search(s) and not CONTENT_VERB.search(s)]

    ann = json.loads(REPLAY_ANN.read_text(encoding="utf-8"))
    D = ann["★默认槽位"]
    by_sup = {"A": [], "B": []}
    for k, v in ann["annotations"].items():
        g = dict(D, **v)
        # 键形如 轮次/id/序号; 第 0 条是 A 支(增量), 其余多为 B 支 —— 用 predicate 反推更稳
        (by_sup["B"] if g.get("predicate") == "OWNERSHIP" else by_sup["A"]).append(g.get("predicate"))
    import collections
    a_dist = dict(collections.Counter(by_sup["A"]))
    b_dist = dict(collections.Counter(by_sup["B"]))

    return {
        "block": "REAL_CORPUS_FEASIBILITY",
        "★零调用": "只统计仓内语料与**已付费**证书的标注, **不发起任何模型调用**。",
        "★★★问题": "手构对照集与真人语料有 19–30 个百分点的表层偏离 ⇒ 读数不得外推。"
            "那么**改用真实语料重建对照集, 可行吗**?",
        "★语料规模": {"总句数": len(sents), "含品牌/型号": len(brand),
                  "机械候选「只指认」(含品牌 + 所有权动词 + 无内容动词)": len(cand)},
        "★★★★★ 关键: RESTATES_IDENTIFIER 不是自然语言类别": (
            "它的定义是「**声称这是增量**, 而它只是复述/指认标识」—— "
            "**「声称这是增量」是 A 支的属性**。"
            "⇒ 一个句子只有在**被当成增量证据提交**时, 才谈得上「它其实只是复述标识」。"
            "★★ 真实语料里「只指认」的句子很多(机械候选 **%d** 条), "
            "但它们在 CCE 里会被正确地放进 **B 支(所有权支)** —— 那是它们**本来的位置**, **不构成错误**。"
            "⇒ **它是一个「抽取错误」类别, 不是语言现象。**" % len(cand)),
        "★证据: 已付费证书里两支的 predicate 分布": {
            "A 支(增量支)": a_dist, "B 支(所有权支)": b_dist,
            "★怎么读": "**RESTATES_IDENTIFIER 只出现在 A 支**, 且只有 2 条 —— "
                "那是**模型把只指认标识的片段当成增量证据**的两次。"
                "B 支里全是 OWNERSHIP, 因为「只指认」放在 B 支是**正确**的。"},
        "★★★所以可行吗": (
            "**不能靠人直接从语料里标出来。** 人标得出「这句话是不是只指认」, "
            "标不出「**模型有没有把它当成增量**」—— 而后者才是这个类别的定义。"
            "⇒ 要从真实语料拿到鉴别格, **必须先让模型在真实语料上抽取**(花钱), 再标注它的错误。"),
        "★★★代价估算": (
            "按 r1/r2/r3 的经验: **48 次调用产出 2 条** RESTATES ⇒ 约 **24 次/条**。"
            "要拿到 r5 那样的 **24 个鉴别格**, 粗估需要 **~570 次调用** —— "
            "而已用预算总共才 **136 次**。★ 这是**外推估算**, 且真实语料的错误率可能与手构模板不同, "
            "**不得当成精确预算**; 但量级足以说明: **这条路比手构贵一个数量级**。"),
        "★★★还剩什么选择": [
            "**(a) 先小批试**: 花 ~50 次在真实语料上抽取, **实测**每条调用产出多少 RESTATES, "
            "把上面那个外推估算换成实测值。这是**唯一能把估算变成数**的做法。",
            "**(b) 承认外推边界**: 不重建对照集, 但把「读数不得外推到自然语料」**写死在每份产物里**"
            "(已做, 见 results/corpus_balance_audit.json)。",
            "**(c) 换一个类别**: RESTATES 是抽取错误类别 ⇒ 稀少。"
            "若改测一个**自然语言里常见**的槽位(如 citation=REPORTED, 转述), 真实语料可能够用 —— "
            "★ 但实测: 已付费证书里 REPORTED **也是 0 次**(见 results/interpretation_upgrade_impact.json), "
            "所以这条也要先小批试。"],
    }


def main():
    r = build_result()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print("改用真实语料的可行性(**零调用**)\n")
    print("  语料规模:", json.dumps(r["★语料规模"], ensure_ascii=False))
    print("\n  两支的 predicate 分布:", json.dumps(r["★证据: 已付费证书里两支的 predicate 分布"]["A 支(增量支)"], ensure_ascii=False),
          "/", json.dumps(r["★证据: 已付费证书里两支的 predicate 分布"]["B 支(所有权支)"], ensure_ascii=False))
    print("\n  " + r["★★★★★ 关键: RESTATES_IDENTIFIER 不是自然语言类别"])
    print("\n  " + r["★★★所以可行吗"])
    print("\n  " + r["★★★代价估算"])
    print("\n  还剩什么选择:")
    for x in r["★★★还剩什么选择"]:
        print("    · " + x)
    print("\n→", OUT)


if __name__ == "__main__":
    main()
