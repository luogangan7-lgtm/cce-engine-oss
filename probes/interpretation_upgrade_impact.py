#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**升合同的后果对比** —— 把两条依赖解释的规则分别/一起升为合同明文, 读数各差多少。**零模型调用**。

## 对象
scripts/cce_claim_frame.py 的 _p() 里有**两条**走 BY_INTERPRETATION(依赖解释, 可被推翻)的规则:
  · **(i) citation == REPORTED** —— 合同未定义「输出」是否含**转述**
  · **(ii) predicate == NOT_OF_DECLARED_KIND** —— 合同只**列出**五类增量、未定义**各自成立条件**
附件 A(只复述标识 ⇒ 不产生增量)已于 2026-09-14 升为合同。现在问这两条要不要也升。

## ★★★ 「升」在行为上到底改变什么
两档的差别**只有一个**: 规则在不在 `if use_interpretation:` 门内。
  · 升之前 —— **只用合同明文**那一档**不执行**它 ⇒ 拦不住对应的阴性
  · 升之后 —— 两档都执行 ⇒ **只用合同明文**档也拦得住
⇒ 所以对比就是看**「只用合同明文」档的读数变化**; 「明文+解释」档**逐字不变**(升前它本来就执行)。
★ 这一点是**可预测的**, 但**算出来才知道差多少格**, 以及**对照会不会被误拦**。

## ★★★ 这份东西不做裁定
★ 这条纪律的正文**只写在产物里**(build_result 的「★★★这份东西不做裁定」键), docstring 不复述 ——
  2026-09-17 变异实测: 同一句话写在两处, 改了其中一处**没有任何闸会红**。
"""
import importlib.util, json, pathlib, shutil, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
CF_SRC = ROOT / "scripts/cce_claim_frame.py"
ANN = ROOT / "tests/data/claim_frame_annotations.json"
PAIRS = ROOT / "tests/data/semantic_minimal_pairs.json"
OUT = ROOT / "results" / "interpretation_upgrade_impact.json"

# ★ 把规则移出 `if use_interpretation:` 门 = 升为合同明文。锚点逐字取自源码。
RULE_REPORTED = '''        if f.citation == "REPORTED":
            return (REFUTES,
                    "该陈述是**转述他人主张**, 说话人并未「输出」它。"
                    "★ 合同**未定义**「输出」是否含转述 ⇒ **本条依赖解释**, 可被推翻",
                    BY_INTERPRETATION)
'''
RULE_NOTKIND = '''        if f.predicate == "NOT_OF_DECLARED_KIND":
            return (REFUTES,
                    "谓词**不属于**所声明的那一类增量。"
                    "★ 合同只**列出**五类、**未定义**各自成立条件 ⇒ **本条依赖解释**, 可被推翻",
                    BY_INTERPRETATION)
'''


def _variant(upgrade):
    """生成一个把 upgrade 里的规则升为合同明文的源码(镜像, **不动仓**)。"""
    import textwrap
    s = CF_SRC.read_text(encoding="utf-8")
    moved = ""
    for name, blk in (("REPORTED", RULE_REPORTED), ("NOT_OF_DECLARED_KIND", RULE_NOTKIND)):
        if name not in upgrade:
            continue
        assert blk in s, "★ 锚点失配: %s" % name
        s = s.replace(blk, "", 1)
        # ★ 整块 dedent 后按函数体缩进(4)重新缩进 —— 逐行手改缩进太脆
        moved += textwrap.indent(textwrap.dedent(blk), "    ").replace(
            "BY_INTERPRETATION)", "BY_CONTRACT)  # ★ 本对比里被升为合同")
    if moved:
        # ★ 两条都移走时 `if use_interpretation:` 块会空 ⇒ 补一句 pass, 否则语法错
        s = s.replace("    if use_interpretation:",
                      moved + "    if use_interpretation:\n        pass", 1)
    return s


def _load(src, name):
    d = tempfile.mkdtemp()
    p = pathlib.Path(d) / ("%s.py" % name)
    p.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _minimal_rows(CF):
    ann = json.loads(ANN.read_text(encoding="utf-8")); D = ann["★默认槽位"]
    d = json.loads(PAIRS.read_text(encoding="utf-8"))
    pr = {p["id"]: p for p in d["pairs"]}
    out = []
    for pid, e in ann["annotations"].items():
        for side in ("pos", "neg"):
            out.append((f"{pid}/{side}", side == "neg", pr[pid][side], e["frames"][side], D))
    for p in d["contract_pairs"]:
        for side in ("pos", "neg"):
            out.append((f"{p['id']}/{side}", side == "neg", p[side], p["frames"][side], D))
    return out


def _score(CF, rows):
    res = {}
    for tier, ui in (("只用合同明文", False), ("明文+解释", True)):
        nb = nn = po = pn = 0
        for _id, is_neg, src, ann, D in rows:
            fr = []
            for key, conj in (("A", CF.CONJ_P), ("B", CF.CONJ_Q)):
                kw = dict(D, **ann[key])
                fr.append(CF.ClaimFrame(src[key][0], conj, object=src[key][1],
                                        predicate=kw["predicate"], speaker=kw["speaker"],
                                        polarity=kw["polarity"], time=kw["time"],
                                        citation=kw["citation"], possession=kw["possession"],
                                        increment_kind=(src[key][2] if key == "A" else None)))
            allow = CF.allow_label(fr, use_interpretation=ui)["allow"]
            if is_neg:
                nn += 1; nb += (not allow)
            else:
                pn += 1; po += allow
        res[tier] = {"阴性拦住": "%d/%d" % (nb, nn), "对照通过": "%d/%d" % (po, pn)}
    return res


def _replay(CF_src, name):
    """真实证书: 用**已验证的** claim_frame_replay.py, 只把它 import 的判据层换成变体。"""
    import cce_claim_frame as _orig
    m = _load(CF_src, name)
    sys.modules["cce_claim_frame"] = m
    try:
        sp = importlib.util.spec_from_file_location("cfr_%s" % name, ROOT / "probes/claim_frame_replay.py")
        r = importlib.util.module_from_spec(sp); sp.loader.exec_module(r)
        rows, _ = r.build_rows()
    finally:
        sys.modules["cce_claim_frame"] = _orig
    neg = [x for x in rows if x["★是阴性吗"]]; pos = [x for x in rows if not x["★是阴性吗"]]
    return {t: {"阴性拦住": "%d/%d" % (sum(1 for x in neg if not x[t]["allow"]), len(neg)),
                "对照通过": "%d/%d" % (sum(1 for x in pos if x[t]["allow"]), len(pos))}
            for t in ("只用合同明文", "明文+解释")}


OPTIONS = [("① 现状(两条都不升)", ()),
           ("② 只升 NOT_OF_DECLARED_KIND(五类成立条件)", ("NOT_OF_DECLARED_KIND",)),
           ("③ 只升 REPORTED(转述算不算输出)", ("REPORTED",)),
           ("④ 两条都升", ("REPORTED", "NOT_OF_DECLARED_KIND"))]


def _exercised():
    """★★★ 这两条规则在**真实证书**上有没有对象 —— 「无差别」到底是无关还是没测到。"""
    import collections
    ann = json.loads((ROOT / "tests/data/claim_frame_replay_annotations.json").read_text(encoding="utf-8"))
    D = ann["★默认槽位"]
    c = collections.Counter(); pr = collections.Counter()
    for v in ann["annotations"].values():
        g = dict(D, **v)
        c[g.get("citation")] += 1; pr[g.get("predicate")] += 1
    n_rep, n_nok = c.get("REPORTED", 0), pr.get("NOT_OF_DECLARED_KIND", 0)
    return {
        "真实证书的标注条数": sum(c.values()),
        "citation 取值分布": dict(c), "predicate 取值分布": dict(pr),
        "citation == REPORTED 出现次数": n_rep,
        "predicate == NOT_OF_DECLARED_KIND 出现次数": n_nok,
        "★★★所以真实证书上「无差别」是什么意思": (
            "**不是「这两条规则无关」, 是「它们一次都没被 exercise」**。"
            "48 次已付费调用产出的真实证书里, REPORTED 出现 **%d** 次、"
            "NOT_OF_DECLARED_KIND 出现 **%d** 次 ⇒ 两条规则**根本没有对象**。"
            "★ 与 r4 的 ONE_NEGATED 零覆盖、r2 的「资格层一次都没被 exercise」是**同型**。" % (n_rep, n_nok)),
        "★★★对「升不升」的含义": (
            "升它们, **在现有真实数据上买不到任何可验证的东西**。"
            "收益只在**手构对照**上看得见(明文档阴性 +2/+2/+4), 而手构对照与真人语料有 "
            "**19–30 个百分点**的表层偏离(results/corpus_balance_audit.json) ⇒ **那个收益不能外推**。"
            "⇒ 决策的性质不是「升了有没有好处」, 而是 **「升了的好处目前测不出来」**。"),
    }


def build_result():
    res = {
        "block": "INTERPRETATION_UPGRADE_IMPACT",
        "★零调用": "只重算手构对照与**已付费**的真实证书, **不发起任何模型调用**。",
        "★★★这份东西不做裁定": "**升不升是 owner 的决定, 不是读数能定的** —— "
            "附件 A 那次已经写死这条纪律(「裁定依据是 owner 的决定, 不是读数」)。"
            "本文件只把**四个选项的后果**摆出来。",
        "★★★「升」在行为上改变什么": "两档的差别**只有一个**: 规则在不在 `if use_interpretation:` 门内。"
            "⇒ 升了之后**只用合同明文**那一档也执行它; **「明文+解释」档逐字不变**(升前它本来就执行)。"
            "★ 这一点可预测, 但**算出来才知道差多少格, 以及对照会不会被误拦**。",
        "★对比是在镜像上做的": "变体源码写进临时目录再 import, **仓内 scripts/cce_claim_frame.py 一个字节没动**。",
    }
    for lbl, up in OPTIONS:
        m = _load(_variant(up), "cf_%d" % abs(hash(lbl)))
        res[lbl] = {"手构最小对照(34 对 × 2 版)": _score(m, _minimal_rows(m)),
                    "真实证书(r1/r2/r3 已付费的 48 次)": _replay(_variant(up), "v%d" % abs(hash(lbl)))}
    res["★★★这两条规则在真实证书上被 exercise 了吗"] = _exercised()
    base = res["① 现状(两条都不升)"]
    res["★★★逐项与现状的差(只看「只用合同明文」档)"] = {
        lbl: {k: {"现状": base[k]["只用合同明文"], "该选项": res[lbl][k]["只用合同明文"]}
              for k in ("手构最小对照(34 对 × 2 版)", "真实证书(r1/r2/r3 已付费的 48 次)")}
        for lbl, _ in OPTIONS[1:]}
    res["★★★「明文+解释」档必须逐字不变"] = {
        lbl: all(res[lbl][k]["明文+解释"] == base[k]["明文+解释"]
                 for k in ("手构最小对照(34 对 × 2 版)", "真实证书(r1/r2/r3 已付费的 48 次)"))
        for lbl, _ in OPTIONS}
    return res


def main():
    r = build_result()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print("升合同的后果对比(**零调用 · 镜像变体 · 仓内判据层未动**)\n")
    for lbl, _ in OPTIONS:
        print("  %s" % lbl)
        for k in ("手构最小对照(34 对 × 2 版)", "真实证书(r1/r2/r3 已付费的 48 次)"):
            d = r[lbl][k]["只用合同明文"]
            e = r[lbl][k]["明文+解释"]
            print("    %-34s 明文档: 阴性 %-7s 对照 %-7s | 明文+解释: 阴性 %-7s 对照 %s"
                  % (k[:34], d["阴性拦住"], d["对照通过"], e["阴性拦住"], e["对照通过"]))
    print("\n  「明文+解释」档是否逐字不变:", json.dumps(r["★★★「明文+解释」档必须逐字不变"], ensure_ascii=False))
    e = r["★★★这两条规则在真实证书上被 exercise 了吗"]
    print("\n  " + e["★★★所以真实证书上「无差别」是什么意思"])
    print("\n  " + e["★★★对「升不升」的含义"])
    print("\n→", OUT)


if __name__ == "__main__":
    main()
