#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**最佳浅层规则搜索** —— 机械搜遍表层线索。**零模型调用**。

## 为什么要有它
probes/shallow_cue_arm.py 用的是**一套冻结的手写规则**, 它只能告诉你「**那几条**规则能拿多少」。
而造对照集的人(我)只能对称化**自己想得到的**表层特征 —— 2026-09-15 实测演示了这一点:
  · 第一次: 我没想到 `'aid' in span`, 评审 agent 实跑抓到, 它能拿走**全部** ANX 信号;
  · 第二次: 我对称化了 aid, **立刻又出现「neg 全用系动词」**这条新共线。
⇒ **手工猜表层特征是打不完的。**

## 它做什么
在 A 支片段上**穷举**所有单 token(以及 token 的大小写/词形变体)作为候选规则, 对每条规则算:
    净增益 = 命中鉴别格的数量 − 命中多数类格的数量
报出**净增益最大**的那几条, 以及它们各自能把 predicate 推到多少分。

## 怎么用(这是它存在的理由)
**任何模型臂必须超过「最佳浅层规则」**, 而不只是超过零基线、也不只是超过手写的浅层臂。
★ 若最佳浅层规则的净增益已经接近满分, 说明**这批对照集本身测不出语义** —— 要改的是对照集, 不是判据。

★★★ 2026-09-15 扩空间(投料前评审 BLOCKING 抓到):
  原版只搜**单 token**, 报出的最佳是 `'hearing'` 2/6 净 +2, 而 **probes/slot_filling_run_r5.py 直接把这个
  下界当成了主判据的零假设 p0**。评审实跑证明: 扩到**标准闭类词表 ≤3 项合取**后,
  `含系动词 AND 不含介词 AND 不含程度词` 拿 **5/6 · 误伤 0/24 · 净 +5**, 且**通过全部三个前置条件**。
  ⇒ p0 由 1/3 变成 5/6, **门在任何结局下都不可达** —— 正是 r5 第一版被否决的病换了个门回来。

★★★ 停止规则(必须先定, 否则是无限军备竞赛):
  「在 30 个格上对越来越大的规则族做极大化, 最终能打散任何对照集」——
  所以**不是**「扩空间直到 p0 饱和」。本文件的族**先冻结**:
    · 原子只取**标准公开闭类词表**(系动词 / 介词 / 程度词 / 限定词)+ 两个纯正字法项(末词大写 / 词数)
    · **禁止自造词表**, 禁止内容词
    · 合取项数 **≤3**, 含否定
  ⇒ 族规模是**固定且可审的**(现算并随产物一起报)。**先冻族, 再改对照集** —— 反过来就是拟合搜索器。

★★ 边界仍在: 这个族之外(真 n-gram、句法树、词向量)**不在空间内** ⇒ 仍是**下界**,
  只是比单 token 族**高得多**的下界。
"""
import collections, itertools, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ANN = ROOT / "tests/data/claim_frame_annotations.json"
PAIRS = ROOT / "tests/data/semantic_minimal_pairs.json"
OUT = ROOT / "results" / "best_shallow_rule_search.json"
MAJORITY = "OF_DECLARED_KIND"          # 零基线在 predicate 上填的常数


# ────────── 冻结的规则族: 标准公开闭类词表 × ≤3 项合取 ──────────
# ★★★ 这些词表取自常见英语语法教材的闭类清单, **不是我为这批数据挑的**。禁止增删以迁就读数。
COPULA = {"is", "are", "am", "was", "were", "be", "been", "being"}
PREP = {"about", "above", "across", "after", "against", "along", "among", "around", "at",
        "before", "behind", "below", "beneath", "beside", "between", "beyond", "by", "down",
        "during", "except", "for", "from", "in", "inside", "into", "near", "of", "off", "on",
        "onto", "out", "outside", "over", "past", "since", "through", "throughout", "to",
        "toward", "towards", "under", "until", "up", "upon", "with", "within", "without"}
DEG = {"too", "very", "quite", "so", "really", "rather", "fairly", "pretty", "extremely",
       "somewhat", "hardly", "barely"}
DET = {"a", "an", "the", "this", "that", "these", "those", "my", "your", "his", "her",
       "its", "our", "their"}
MAX_CONJ = 3


def _t(s):
    return [x.lower() for x in re.findall(r"[A-Za-z']+", s)]


ATOMS = {
    "含系动词":            lambda s: bool(set(_t(s)) & COPULA),
    "含介词":              lambda s: bool(set(_t(s)) & PREP),
    "含程度词":            lambda s: bool(set(_t(s)) & DEG),
    "末词前是限定词":       lambda s: len(_t(s)) >= 2 and _t(s)[-2] in DET,
    "末词首字母大写":       lambda s: bool(re.findall(r"[A-Za-z']+", s))
                                      and re.findall(r"[A-Za-z']+", s)[-1][0].isupper(),
    "词数<=5":            lambda s: len(_t(s)) <= 5,
    "词数<=6":            lambda s: len(_t(s)) <= 6,
}


def _rules():
    """冻结族的全部规则。返回 [(描述, 判定函数)]。"""
    names = list(ATOMS)
    out = []
    for k in range(1, MAX_CONJ + 1):
        for combo in itertools.combinations(names, k):
            for pols in itertools.product((True, False), repeat=k):
                desc = " AND ".join(("" if p else "不") + n for n, p in zip(combo, pols))
                fns = [(ATOMS[n], p) for n, p in zip(combo, pols)]
                out.append((desc, lambda s, f=fns: all(fn(s) == p for fn, p in f)))
    return out


def search_family(rows, target):
    """在**冻结族**上穷举。返回按净增益排序的候选 + 族规模。"""
    disc = [s for _, s, g in rows if g == target]
    bulk = [s for _, s, g in rows if g == MAJORITY]
    cand = []
    for desc, fn in _rules():
        hd = sum(1 for s in disc if fn(s))
        hb = sum(1 for s in bulk if fn(s))
        if hd:
            cand.append({"规则": desc, "命中鉴别格": "%d/%d" % (hd, len(disc)),
                         "误伤多数类格": "%d/%d" % (hb, len(bulk)), "净增益": hd - hb,
                         "_hd": hd, "_hb": hb})
    cand.sort(key=lambda c: (-c["净增益"], -c["_hd"]))
    return cand, len(disc), len(bulk)


def cells():
    """全部 A 支的 (id, span, 金标 predicate)。predicate 只在 A 支有分母。"""
    ann = json.loads(ANN.read_text(encoding="utf-8"))
    d = json.loads(PAIRS.read_text(encoding="utf-8"))
    D = ann["★默认槽位"]
    pr = {p["id"]: p for p in d["pairs"]}
    out = []
    for pid, e in ann["annotations"].items():
        for side in ("pos", "neg"):
            out.append((f"{pid}/{side}", pr[pid][side]["A"][0],
                        dict(D, **e["frames"][side]["A"])["predicate"]))
    for p in d["contract_pairs"]:
        for side in ("pos", "neg"):
            out.append((f"{p['id']}/{side}", p[side]["A"][0],
                        dict(D, **p["frames"][side]["A"])["predicate"]))
    return out


def search(rows, target):
    """穷举单 token 规则: 「span 含 token ⇒ 填 target」。返回按净增益排序的候选。"""
    disc = [(i, s) for i, s, g in rows if g == target]        # 该取值的鉴别格
    bulk = [(i, s) for i, s, g in rows if g == MAJORITY]      # 零基线免费答对的格
    toks = set()
    for _, s, _ in rows:
        toks |= {t.lower() for t in re.findall(r"[A-Za-z']+", s)}
    cand = []
    for t in sorted(toks):
        hit_d = sum(1 for _, s in disc if t in s.lower())
        hit_b = sum(1 for _, s in bulk if t in s.lower())
        if hit_d:
            cand.append({"token": t, "命中鉴别格": "%d/%d" % (hit_d, len(disc)),
                         "误伤多数类格": "%d/%d" % (hit_b, len(bulk)),
                         "净增益": hit_d - hit_b,
                         "_predicate总分": (len(bulk) - hit_b) + hit_d})
    cand.sort(key=lambda c: (-c["净增益"], -int(c["命中鉴别格"].split("/")[0]), c["token"]))
    return cand, len(disc), len(bulk)


def build_result():
    rows = cells()
    res = {
        "block": "BEST_SHALLOW_RULE_SEARCH",
        "★零调用": "本搜索**不发起任何模型调用**, 也**不做任何语义判断** —— 只做 token 匹配。",
        "★★★它回答什么": "「**在这批对照集上, 最强的单 token 浅层规则能拿多少**」。"
            "★ 手写的浅层臂只能测**我想得到的**规则; 本搜索**机械搜遍** token 这一族。",
        "★★★怎么用": "**任何模型臂必须超过最佳浅层规则**, 而不只是超过零基线、也不只是超过手写浅层臂。"
            "★ 若最佳浅层规则已接近满分, 说明**这批对照集本身测不出语义** —— 要改的是对照集, 不是判据。",
        "★★★边界_这是下界不是上界": "搜索空间只有**单 token 规则**。n-gram、位置、长度、标点等更复杂的浅层规则"
            "**不在空间内** ⇒ 结论只能读成「**至少存在**这么强的浅层规则」, **不能**读成「不存在更强的」。",
        "★零基线参照": "常数填 %s。它在鉴别格上**按构造 0 分**, 在多数类格上满分。" % MAJORITY,
    }
    res["★★★冻结规则族"] = {
        "原子": list(ATOMS), "最大合取项数": MAX_CONJ, "族规模": len(_rules()),
        "★词表来源": "常见英语语法教材的**标准闭类清单**(系动词/介词/程度词/限定词) + 两个纯正字法项。"
            "**不是为这批数据挑的**, 禁止增删以迁就读数。",
        "★★★为什么必须先冻族": "在 30 个格上对**越来越大**的规则族做极大化, 最终能打散任何对照集 ⇒ "
            "「扩空间直到 p0 饱和」**不是停止规则**。**先冻族, 再改对照集**; 反过来就是拟合搜索器。"}
    for target in ("RESTATES_IDENTIFIER", "NOT_OF_DECLARED_KIND"):
        cand, nd, nb = search(rows, target)
        fam, _, _ = search_family(rows, target)
        top = cand[:5]
        res["★★★目标取值 %s" % target] = {
            "鉴别格数": nd, "多数类格数": nb,
            "零基线在此": "0/%d" % nd,
            "最佳净增益": (top[0]["净增益"] if top else 0),
            "最佳规则能把 predicate 推到": ("%d/%d" % (top[0]["_predicate总分"], nd + nb)) if top else "—",
            "前 5 条候选": [{k: v for k, v in c.items() if not k.startswith("_")} for c in top],
            "★怎么读": "净增益 = 命中鉴别格 − 误伤多数类格。**净增益 ≤ 0 表示该 token 规则不比零基线好**。",
            "★★★冻结族最佳(这才是 p0 该用的数)": {
                "规则": (fam[0]["规则"] if fam else "—"),
                "命中鉴别格": (fam[0]["命中鉴别格"] if fam else "0/%d" % nd),
                "误伤多数类格": (fam[0]["误伤多数类格"] if fam else "0/%d" % nb),
                "净增益": (fam[0]["净增益"] if fam else 0),
                "前 6 条": [{k: v for k, v in c.items() if not k.startswith("_")} for c in fam[:6]]},
            "★★★单token族与冻结族的差": "单 token 最佳净 %+d vs 冻结族最佳净 %+d。"
                "**主判据的 p0 必须用后者** —— 用前者等于把一个**下界**当成 null。"
                % ((top[0]["净增益"] if top else 0), (fam[0]["净增益"] if fam else 0)),
        }
    return res


def main():
    res = build_result()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("最佳浅层规则搜索(**零调用 · 穷举单 token · 无语义**)\n")
    for k, v in res.items():
        if not k.startswith("★★★目标取值"):
            continue
        print("  %s  鉴别格 %d · 多数类格 %d" % (k.replace("★★★目标取值 ", ""), v["鉴别格数"], v["多数类格数"]))
        print("    最佳净增益 %d · 能把 predicate 推到 %s (零基线 %d/%d)"
              % (v["最佳净增益"], v["最佳规则能把 predicate 推到"], v["多数类格数"], v["鉴别格数"] + v["多数类格数"]))
        for c in v["前 5 条候选"]:
            print("      %-14s 鉴别 %-6s 误伤 %-7s 净 %+d"
                  % (repr(c["token"]), c["命中鉴别格"], c["误伤多数类格"], c["净增益"]))
        print()
    print("→", OUT)


if __name__ == "__main__":
    main()
