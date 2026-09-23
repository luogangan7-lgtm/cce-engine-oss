#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把**冻结族最佳浅层规则**放到 r1/r2/r3 已付费的**真实证书**上。**零模型调用**。

## 为什么要有这份东西(2026-09-15 投料前评审逼出来的)
r5-v2 的主判据零假设 p0 用的是「最佳浅层规则的命中率」。投料前评审实跑发现:
把搜索空间从**单 token** 扩到**标准闭类词表 ≤3 项合取**(族规模 378)之后,
`含系动词 AND 不含介词 AND 不含程度词` 在 6 个鉴别格上拿 **5/6 · 误伤 0/24 · 净 +5**。
⇒ p0 由 1/3 变成 5/6, **门在任何 n 下都不可达**。

★★★ 但这引出一个**比 r5 本身更要紧的问题**:
  **那条规则在真实证书上也这么强吗?**
  · 若也强 ⇒ 「复述标识 vs 使用细节」这条合同区分在自然语言里**有一个强的表层代理**,
    那么判据层**可能根本不需要模型** —— 路线要改。
  · 若很弱 ⇒ 它是**手构对照集的伪影**, 说明那 6 对 ANX 造得句法与目标信号共线, **对照集必须重造**。
  **两种答案都改变下一步, 而且都零调用。**

★ 边界: 真实证书的 predicate 标注是**我做的**(38 条, tests/data/claim_frame_replay_annotations.json),
  且这批里 RESTATES_IDENTIFIER 只有很少几条 —— 分母极小, **不得按百分比引用**。
"""
import importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
ANN = ROOT / "tests/data/claim_frame_replay_annotations.json"
OUT = ROOT / "results" / "shallow_rule_on_real_certs.json"
SRC = [("r1", "results/extractor_counterexample.json"),
       ("r2", "results/extractor_counterexample_r2.json"),
       ("r3", "results/repeat_measure_r3.json")]


def _bs():
    sp = importlib.util.spec_from_file_location("bs", ROOT / "probes/best_shallow_rule_search.py")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def _ev(m):
    if "evidence" in m:
        return [(e.get("span"), e.get("supports")) for e in (m.get("evidence") or [])]
    inc, own = (m.get("increment") or {}), (m.get("ownership") or {})
    return [(inc.get("span"), "A"), (own.get("span"), "B")]


def cells():
    """真实证书里**每一条 A 支证据**的 (key, span, 金标 predicate)。"""
    ann = json.loads(ANN.read_text(encoding="utf-8"))
    D = ann["★默认槽位"]
    out = []
    for rnd, path in SRC:
        p = ROOT / path
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for row in (d.get("rows") or []):
            rid = row.get("id")
            m = row.get("模型原样") or row.get("cert") or row.get("certificate") or row
            try:
                evs = _ev(m)
            except Exception:
                continue
            for i, (span, sup) in enumerate(evs):
                key = "%s/%s/%d" % (rnd, rid, i)
                g = ann["annotations"].get(key)
                if not g or sup != "A" or not span:
                    continue
                out.append((key, span, dict(D, **g).get("predicate")))
    return out


def _forms():
    """★★★ 把真实证书里两类片段的**实际形态**并排列出来 —— 重造对照集的模板。"""
    rows = cells()
    T, MAJ = "RESTATES_IDENTIFIER", "OF_DECLARED_KIND"
    BS = _bs()
    def feat(s):
        return {"含系动词": BS.ATOMS["含系动词"](s), "含介词": BS.ATOMS["含介词"](s),
                "词数": len(BS._t(s))}
    return {
        "真实的 %s(模型实际产出的复述形态)" % T:
            [{"key": k, "span": s, **feat(s)} for k, s, g in rows if g == T],
        "真实的 %s(样例)" % MAJ:
            [{"key": k, "span": s, **feat(s)} for k, s, g in rows if g == MAJ][:5],
        "★★★我造的 ANX 是什么形态":
            [{"id": p["id"], "neg span": p["neg"]["A"][0], **feat(p["neg"]["A"][0])}
             for p in json.loads((ROOT / "tests/data/semantic_minimal_pairs.json")
                                 .read_text(encoding="utf-8"))["contract_pairs"]],
        "★★★★★ 结论(这是本轮最要紧的一条)":
            "**真实的「复述标识」不是「X is Y」这种教科书式定义句。** 模型实际产出的是"
            "「**泛泛提及 / 只指认对象, 但不给关于它的任何陈述**」"
            "(r1/NEGP-1 \"wearing hearing aids for a good while now\"; "
            "r3/MIS-4 \"What I actually wear is an old pair from before all this\")。"
            "★ 两种形态**都符合附件 A 的条款**, 但**真实分布里是后者**。"
            "★★ 而我造的 6 对 ANX **全部**是前者 ⇒ 那套对照集测的其实是"
            "「**定义句 vs 描述句**」这个**句法区分**, 不是合同条款。"
            "⇒ 这正解释了为什么同一条闭类规则在手构集上净 +5、在真实证书上净 **0**。"
            "★★★ **重造对照集必须照真实形态**: neg 要含介词、句式要多样、"
            "要有「泛泛提及」而不只是「说出品类名」。",
    }


def build_result():
    BS = _bs()
    rows = cells()
    T, MAJ = "RESTATES_IDENTIFIER", "OF_DECLARED_KIND"
    disc = [(k, s) for k, s, g in rows if g == T]
    bulk = [(k, s) for k, s, g in rows if g == MAJ]
    fam = BS._rules()
    # ★ 冻结族里, 在**最小对照上**最好的那条规则(名字由 results 现读, 不手写)
    best_desc = json.loads((ROOT / "results/best_shallow_rule_search.json").read_text(
        encoding="utf-8"))["★★★目标取值 RESTATES_IDENTIFIER"]["★★★冻结族最佳(这才是 p0 该用的数)"]["规则"]
    fn = dict(fam).get(best_desc)
    res = {
        "block": "SHALLOW_RULE_ON_REAL_CERTS",
        "★零调用": "本测量**不发起任何模型调用**。证书来自 r1/r2/r3 **已付费的 48 次**, 边际成本为零。",
        "★★★它回答什么": "在**最小对照上**拿 5/6 的那条浅层规则, 放到**真实模型产出的证书**上还剩多少。"
            "★ 若也强 ⇒ 这条合同区分有**强的表层代理**, 判据层可能不需要模型; "
            "若很弱 ⇒ 它是**手构对照集的伪影**, 对照集必须重造。",
        "★真实证书里的分布": {"A 支带标注的证据条数": len(rows),
                       "金标 = %s" % T: len(disc), "金标 = %s" % MAJ: len(bulk)},
        "★★★分母极小_不得按百分比引用": "**不得按百分比引用**。真实证书里 %s 只有 **%d 条**。"
            "★ 这不是抽样不足, 是**那批测量本来就没有针对它设计** —— "
            "r1/r2/r3 的 items 里一条 ANX 都没有。" % (T, len(disc)),
    }
    if fn is None:
        res["★★★无法复用那条规则"] = "在冻结族里找不到 %r" % best_desc
        return res
    hd = [k for k, s in disc if fn(s)]
    hb = [k for k, s in bulk if fn(s)]
    res["★★★那条规则在真实证书上"] = {
        "规则": best_desc,
        "命中 %s" % T: "%d/%d" % (len(hd), len(disc)),
        "误伤 %s" % MAJ: "%d/%d" % (len(hb), len(bulk)),
        "净增益": len(hd) - len(hb),
        "命中的": hd, "误伤的": hb[:8],
        "★对比": "同一条规则在**手构最小对照**上是 5/6 · 误伤 0/24 · 净 +5。",
    }
    # ★ 顺带: 在真实证书上重新搜一遍冻结族, 看那里的最佳是什么
    cand = []
    for desc, f in fam:
        a = sum(1 for _, s in disc if f(s))
        b = sum(1 for _, s in bulk if f(s))
        if a:
            cand.append({"规则": desc, "命中": "%d/%d" % (a, len(disc)),
                         "误伤": "%d/%d" % (b, len(bulk)), "净增益": a - b})
    cand.sort(key=lambda c: (-c["净增益"], c["规则"]))
    res["★真实证书上重搜冻结族的最佳"] = cand[:5] if cand else "无候选"
    res["★★★两类片段的真实形态(重造对照集的模板)"] = _forms()
    return res


def main():
    r = build_result()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print("冻结族最佳规则 · 真实证书复核(**零调用**)\n")
    print("  ", json.dumps(r["★真实证书里的分布"], ensure_ascii=False))
    k = "★★★那条规则在真实证书上"
    if k in r:
        v = r[k]
        print("\n  规则: %s" % v["规则"])
        for kk, vv in v.items():
            if kk not in ("规则", "命中的", "误伤的"):
                print("    %-28s %s" % (kk, vv))
    print("\n  真实证书上重搜的最佳:")
    for c in (r.get("★真实证书上重搜冻结族的最佳") or [])[:5]:
        print("    净%+d  命中%-6s 误伤%-7s %s" % (c["净增益"], c["命中"], c["误伤"], c["规则"]))
    print("\n→", OUT)


if __name__ == "__main__":
    main()
