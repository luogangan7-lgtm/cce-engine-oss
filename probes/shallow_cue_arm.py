#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**浅层线索臂** —— 第三条零调用基线。**零模型调用**。

## 它是什么
零基线回答「完全**不读**文本能拿多少」。
本臂回答一个更难的问题: 「只读**表层字符串**、不做任何语义判断, 能拿多少」。

## 为什么必须有它(2026-09-15, 280-agent 零调用评审实跑逼出来的)
r5 草案的评审里, 一个 agent **实跑**出: 一行 `'aid' in span.lower()` 的纯正则填充器,
能让草案的 D1–D7 **七条降级全部沉默**, 并**正好产出那一轮要买的路线结论**
(「B 臂 predicate 22/24 超过零基线 20/24, 阴性放行复现金标上界 ⇒ 模型读懂了判据」)。
★★★ 根因是**我造对照对时的失误**: 24 条 A 支片段里, 只有 ANX 两条 neg 含 "aid",
  其余全是实义动词句 ⇒ **表层正字法线索与目标信号完全共线**。

⇒ **通则**: 「超过零基线」只证明**读了文本**, **不证明读懂了语义**。
  中间还隔着一整层「表层字符串匹配」, 而那一层**不需要任何理解**。

## 规则从哪来(★ 这一点是本文件的全部严谨性)
下面的 RULES **逐字沿用**评审 agent 在**旧版对照文本**上独立写出的那一套 ——
**我没有参与它的构造, 它也不知道我事后会怎么改文本**。
★ 这不是洁癖: 若规则由我在看过答案后写, 它就只是「我能不能造一个打不中的正则」,
  测不出任何东西。**规则必须先于文本修改而固定。**
★★ 因此本文件的 RULES **不许随文本调整**。要加规则, 必须说明它是在**没看新文本**的情况下写的。
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
ANN = ROOT / "tests/data/claim_frame_annotations.json"
PAIRS = ROOT / "tests/data/semantic_minimal_pairs.json"
OUT = ROOT / "results" / "shallow_cue_arm.json"

# ★★★ 逐字冻结: 评审 agent 在旧文本上独立写出的浅层规则。**不许随文本调整**。
RULES = {
    "citation":   ("REPORTED",        "text", r"claimed|claims"),
    "speaker":    ("OTHER",           "span", r"\bhe\b|\bshe\b|wife|brother"),
    "time":       ("FUTURE",          "text", r"\bwill\b"),
    "possession": ("BOTH_NEGATED",    "text", r"never|do not"),
    "predicate":  ("RESTATES_IDENTIFIER", "span", r"aid"),
    "polarity":   ("NEGATED",         "text", r"never|not\b"),
}
# 命中则填上面的取值; 否则填多数类常数(与零基线同)
FALLBACK = {"speaker": "SELF", "polarity": "ASSERTED", "time": "PAST_OR_PRESENT",
            "citation": "DIRECT", "possession": "OWNED", "predicate": "OF_DECLARED_KIND"}
SLOTS = tuple(FALLBACK)


def fill(text, span, is_A):
    """只看字符串。**不做任何语义判断。**"""
    out = {}
    for s in SLOTS:
        val, where, pat = RULES[s]
        hay = text if where == "text" else span
        out[s] = val if re.search(pat, hay, re.I) else FALLBACK[s]
    if not is_A:                       # B 支没标 kind, 金标一律 OWNERSHIP
        out["predicate"] = "OWNERSHIP"
    return out


def items():
    """24 条 item × 2 支 = 48 格。金标来源与 r5 设想一致(pairs 冻结金标 + contract_pairs 自带)。"""
    ann = json.loads(ANN.read_text(encoding="utf-8"))
    d = json.loads(PAIRS.read_text(encoding="utf-8"))
    D = ann["★默认槽位"]
    pr = {p["id"]: p for p in d["pairs"]}
    out = []
    for pid, e in ann["annotations"].items():
        for side in ("pos", "neg"):
            out.append((f"{pid}/{side}", pr[pid][side], e["frames"][side], D, False))
    for p in d["contract_pairs"]:
        for side in ("pos", "neg"):
            out.append((f"{p['id']}/{side}", p[side], p["frames"][side], D, True))
    return out


def _family_net(pairs_list):
    """★ 冻结族(标准闭类词表 ≤3 合取)在给定一批对上的**最佳净增益**。"""
    import importlib.util
    sp = importlib.util.spec_from_file_location("bs", ROOT / "probes/best_shallow_rule_search.py")
    BS = importlib.util.module_from_spec(sp); sp.loader.exec_module(BS)
    ann = json.loads(ANN.read_text(encoding="utf-8")); D = ann["★默认槽位"]
    d = json.loads(PAIRS.read_text(encoding="utf-8"))
    pr = {p["id"]: p for p in d["pairs"]}
    rows = [(f"{pid}/{s}", pr[pid][s]["A"][0], dict(D, **e["frames"][s]["A"])["predicate"])
            for pid, e in ann["annotations"].items() for s in ("pos", "neg")]
    for p in pairs_list:
        for s in ("pos", "neg"):
            rows.append((p["id"] + "/" + s, p[s]["A"][0], dict(D, **p["frames"][s]["A"])["predicate"]))
    T, MAJ = "RESTATES_IDENTIFIER", "OF_DECLARED_KIND"
    disc = [x for _, x, g in rows if g == T]; bulk = [x for _, x, g in rows if g == MAJ]
    best = max(((sum(1 for x in disc if fn(x)) - sum(1 for x in bulk if fn(x)),
                 sum(1 for x in disc if fn(x)), d_)
                for d_, fn in BS._rules() if any(fn(x) for x in disc)), key=lambda t: (t[0], t[1]))
    return {"最佳净增益": best[0], "命中鉴别格": "%d/%d" % (best[1], len(disc)),
            "规则": best[2], "鉴别格数": len(disc)}


def _baseline_pred_A():
    """★ 零基线在 predicate A 支上的数 —— **现算**。

    ★★★ 这里原本是**手写的** "0/4 / 20/20 / 20/24"; 2026-09-15 第三次扩充把对照集从 24 条加到 32 条后,
      那三个数**当场过期**, 而没有任何东西会提醒我。⇒ 手写的数一定会过期, 一律现算。
    """
    disc = bulk = disc_n = bulk_n = 0
    for iid, src, gold, D, is_anx in items():
        g = dict(D, **gold["A"])["predicate"]
        ok = FALLBACK["predicate"] == g
        if g != FALLBACK["predicate"]:
            disc_n += 1; disc += ok
        else:
            bulk_n += 1; bulk += ok
    return {"鉴别格": "%d/%d" % (disc, disc_n), "多数类格": "%d/%d" % (bulk, bulk_n),
            "A 支合计": "%d/%d" % (disc + bulk, disc_n + bulk_n),
            "★": "常数填充**结构上不可能**答对鉴别格 —— 上面那个鉴别格的数必然是 0。"}


def counterfactual():
    """★★★ **v1(已撤回的 6 对) vs v2(现在的 24 对)** 在**冻结族**上的最佳净增益 —— 现跑, 不手写。

    ★ 这取代了旧版的「改文本前后」对比: v1 已整体撤回, 逐句对比没有意义了;
      真正要留的证据是 **句法共线修掉了多少**。
    """
    d = json.loads(PAIRS.read_text(encoding="utf-8"))
    v1 = [x for x in d if "contract_pairs_v1" in x and "已撤回" in x]
    old = _family_net(d[v1[0]]["pairs"]) if v1 else None
    new = _family_net(d["contract_pairs"])
    return {
        "★★★v1(已撤回的 6 对)": old, "★★★v2(现在的 24 对)": new,
        "★外部锚点_真实证书上的冻结族最佳净增益": 0,
        "★★★怎么读": "v1 的最佳净增益 %s, v2 是 %s, 而**真实证书**上是 **0**。"
            "⇒ 重造把手构对照集的句法共线**压向了真实语料的水平**。"
            % (old["最佳净增益"] if old else "—", new["最佳净增益"]),
        "★★★仍然成立的警告": "**净增益仍不是 0** —— 浅层规则照样「答对」一部分。"
            "⇒ 主判据的零假设必须**用搜出来的 p0**, 不许假定浅层规则无效; "
            "且 p0 要取**留出集**那个(未被迭代过的), 不是最好看的那个。",
        "零基线(常数填充)": _baseline_pred_A(),
    }


def _unused_counterfactual_old():
    return {
        "★★★对比只覆盖 ANX-1/2": "OLD_ANX 里只有 ANX-1/2 的旧文本。**ANX-3..6 是 2026-09-15 第三次扩充时新增的, "
            "它们没有「改之前」** ⇒ 下面两组数的差**只来自 ANX-1/2 那两对**, 其余四对在两组里都用现文本。",
        "改文本前(旧 ANX-1/2)": old, "改文本后(现文本)": new,
        "零基线(常数填充)": _baseline_pred_A(),
        "★★★怎么读": "改 ANX-1/2 的文本**没有**降低浅层臂的鉴别格得分(那条 `'aid' in span` 规则仍命中 neg), "
            "但它让同一条规则**也命中了对应的 pos** ⇒ 多数类格下降。"
            "**净效果: A 支合计 %s → %s; 同批零基线是 %s。**"
            % (old["A 支合计"], new["A 支合计"], _baseline_pred_A()["A 支合计"]),
        "★★★仍然成立的警告": "浅层臂的**鉴别格仍不是 0** —— 它照样「答对」了 ANX 两条。"
            "⇒ **单看鉴别格会把纯正则误读成有鉴别力**。必须看**净增益**(与零基线的差), 不能只看鉴别格。",
    }


def build_result():
    """★ 计算 + 构造产物。**闸靠它现算比对全部键** —— 抽出来就是为了让「改源码不重跑」也被抓到。"""
    rows, per = [], {s: {"hit": 0, "n": 0} for s in SLOTS}
    pred_disc = {"hit": 0, "n": 0}     # ★ 只算金标 ≠ 零基线常数的那几格(鉴别格)
    pred_bulk = {"hit": 0, "n": 0}     # ★ 金标 == 零基线常数的格(过度触发代价)
    for iid, src, gold, D, is_anx in items():
        r = {"id": iid, "is_ANX": is_anx, "支": {}}
        for key, is_A in (("A", True), ("B", False)):
            g = dict(D, **gold[key])
            got = fill(src["text"], src[key][0], is_A)
            cell = {}
            for s in SLOTS:
                ok = got[s] == g[s]
                cell[s] = {"金标": g[s], "浅层": got[s], "对": ok}
                per[s]["n"] += 1
                per[s]["hit"] += ok
                if s == "predicate" and is_A:
                    (pred_disc if g[s] != FALLBACK[s] else pred_bulk)["n"] += 1
                    (pred_disc if g[s] != FALLBACK[s] else pred_bulk)["hit"] += ok
            r["支"][key] = cell
        rows.append(r)

    res = {
        "block": "SHALLOW_CUE_ARM",
        "★零调用": "本臂**不发起任何模型调用**, 也**不做任何语义判断** —— 只做正则匹配。",
        "★★★它回答什么": "「**只读表层字符串**能拿多少」。零基线回答「完全不读文本能拿多少」; "
            "两者之间隔着一整层**不需要任何理解**的字符串匹配。"
            "⇒ **任何臂只有超过本臂, 才谈得上读懂了语义**; 只超过零基线, 只证明它读了文本。",
        "★★★规则的来源(本文件的全部严谨性)":
            "RULES **逐字沿用 2026-09-15 那次 280-agent 评审里, 某个 agent 在旧版对照文本上独立写出的**那一套。"
            "**我没有参与它的构造, 它也不知道我事后会怎么改文本。** "
            "★ 若规则由我在看过答案后写, 它测的就只是「我能不能造一个打不中的正则」。"
            "**规则必须先于文本修改而固定** —— 所以本文件的 RULES **不许随文本调整**。",
        "★★★逐槽位": {s: "%d/%d" % (v["hit"], v["n"]) for s, v in per.items()},
        "★predicate 聚合数不许直接读": "上面的 predicate 合计含 **B 支 24 格**, 而 B 支没标 kind ⇒ "
            "本臂按协议直接填 OWNERSHIP, **结构上必然全对**。那 24 格是**协议白送的**, 不是能力。"
            "⇒ 只读下面按 A 支拆开的两个数。",
        "★predicate 只看 A 支": "%d/%d" % (pred_disc["hit"] + pred_bulk["hit"],
                                          pred_disc["n"] + pred_bulk["n"]),
        "★★★predicate 必须拆开报": {
            "鉴别格(金标 ≠ 零基线常数)": "%d/%d" % (pred_disc["hit"], pred_disc["n"]),
            "多数类格(金标 == 零基线常数)": "%d/%d" % (pred_bulk["hit"], pred_bulk["n"]),
            "★为什么拆": "合在一起时, **20 个多数类格会把 4 个鉴别格稀释掉** —— "
                "一个在鉴别格上全错、在多数类格上全对的填充器, 聚合数与零基线**完全相同**。"
                "⇒ 聚合的 predicate 准确率**读不出鉴别力**。",
            "★零基线在鉴别格上按构造是 0/4": "常数填充**结构上不可能**答对非多数类的格。"},
        "★★★消共线前后(现跑_不手写)": counterfactual(),
        "★★★从这个对比学到的通则": "消掉正字法共线的机制**不是把线索删掉**(「只复述标识」天然是系动词+品类名, 删不掉), "
            "而是**让同一条线索同时打中 pos 和 neg**, 使它的**净增益归零**。"
            "★ 这也是 pos 对照存在的更深理由: 它不只防退化, 还**中和表层线索**。",
        "★★★这不是模型的读数": "本臂是**手构的字符串匹配器**, 不经任何模型。"
            "它是**基线**, 不是被测对象。",
        "rows": rows,
    }
    return res


def main():
    res = build_result()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("浅层线索臂(**零调用 · 纯正则 · 无语义**)\n")
    for k, v in res["★★★逐槽位"].items():
        print("  %-11s %s" % (k, v))
    d = res["★★★predicate 必须拆开报"]
    print("\n  ★ predicate 鉴别格   %s  (零基线现算 %s)"
          % (d["鉴别格(金标 ≠ 零基线常数)"], _baseline_pred_A()["鉴别格"]))
    print("  ★ predicate 多数类格 %s" % d["多数类格(金标 == 零基线常数)"])
    print("\n→", OUT)


if __name__ == "__main__":
    main()
