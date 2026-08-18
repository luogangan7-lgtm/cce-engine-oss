#!/usr/bin/env python3
"""第二对等长文本 —— 把 min_effect 从「一个锚」变成阈值。

## 为什么
`MIN_EFFECT_EQUAL_LENGTH_20260818 = 0.06278` 来自 run 32141330271, 它有三条限度,
其中第 2 条是致命的: **那一对是 Jaccard 最低(0.075)的, 即最有利的一对。**
它给的是「最好情况下的可分离量级」, 推不出典型文本对可分。

## 前登记选择规则(与 Stage1 **故意不同**)
Stage1 取 Jaccard **最低**(最有利)。本次取 **中位数**(典型)。
- 候选: 语料 12 份各截到 ≤293 字的最大词边界前缀
- **排除 Stage1 用过的 index 0 与 index 10** —— 复用会让两次实验不独立
- 在剩下 10 份的 C(10,2)=45 对里, 取 Jaccard **中位数**那一对
- 平局取字典序最小的 (i, j), 保证可复现

R=4(KSEP 要求), 成本 2 × 4 × 8 = **64 次调用**。两份同一 run 内跑(批次效应抬高分离度)。

## 前登记判决
"""
import itertools, json, os, statistics as st, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K   # noqa: E402
import cce_ksep as KS           # noqa: E402

R = int(os.environ.get("PAIR2_REPS", "4"))
MAXLEN = int(os.environ.get("PAIR2_MAXLEN", "293"))
CTX = "reddit r/HearingAids hearing_aid: 第二对等长对照"
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
ME = KS.MIN_EFFECT_EQUAL_LENGTH_20260818
EXCLUDE = (0, 10)   # Stage1 用过

VERDICT_LINES = [
    "p<=0.05 且 T>=min_effect(%.5f) → **典型**文本对也分得开 ⇒ min_effect 可由锚升为阈值, "
    "取两次的较小者作保守阈值" % ME,
    "p<=0.05 但 T<min_effect → 分得开但效应比最有利那对小 ⇒ min_effect **必须下调**到本次水平, "
    "否则阈值会漏掉真实的典型差异",
    "p>0.05 → 典型文本对**分不开**。★ 结论不是『仪器坏』, 而是"
    "『仪器的分辨力只够区分词面差异最大的一对』—— 下游任何基于典型文本对九结差异的断言全部不可用",
    "★ 本次与 Stage1 的差别只在选择规则(最低 vs 中位), 文本池、截断法、R、判据全同 —— "
    "这是设计, 不是事后挑样本",
    "★ 禁止事后改规则。",
]


def _prefix(t, maxlen):
    if len(t) <= maxlen:
        return t
    cut = t[:maxlen]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > maxlen * 0.6 else cut).rstrip()


def _jac(a, b):
    A, B = set(a.lower().split()), set(b.lower().split())
    return len(A & B) / len(A | B) if A | B else 1.0


def _pick():
    items = json.loads((ROOT / "run_items" / "reddit_20260810.json").read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items") or items.get("run_items") or []
    texts = sorted({(it["reader"] or "").strip() for it in items
                    if (it.get("reader") or "").strip()}, key=len)
    cand = {i: _prefix(t, MAXLEN) for i, t in enumerate(texts) if i not in EXCLUDE}
    pairs = sorted(((round(_jac(cand[i], cand[j]), 6), i, j)
                    for i, j in itertools.combinations(sorted(cand), 2)))
    med = st.median([p[0] for p in pairs])
    # 取 Jaccard 最接近中位数者; 平局取字典序最小 (i,j) —— pairs 已排序, 天然稳定
    best = min(pairs, key=lambda p: (abs(p[0] - med), p[1], p[2]))
    j, i1, i2 = best
    return cand[i1], cand[i2], {"i1": i1, "i2": i2, "jaccard": j,
                                "jaccard_median_of_45": med, "n_pairs": len(pairs),
                                "len1": len(cand[i1]), "len2": len(cand[i2]),
                                "stage1_jaccard": 0.075, "excluded": list(EXCLUDE)}


def _rep(text):
    s1 = K.stage1(text, CTX, 3)
    s2 = K.stage2(text, s1, TAXO)
    return {"instrument": s2["instrument"]["instrument_hash"],
            "knots": {k["key"]: k["intensity"] for k in s2["knots"]},
            "per_knot": s2["sampling"]["per_knot"],
            "top1": s2["sampling"]["top1_mode"]}


if __name__ == "__main__":
    a, b, meta = _pick()
    print("=== 第二对等长对照 (前登记: Jaccard 中位数 = 典型对) ===")
    for v in VERDICT_LINES:
        print("  · " + v)
    print("\n选文本:", json.dumps(meta, ensure_ascii=False))
    print("  A:", repr(a[:80]))
    print("  B:", repr(b[:80]))
    if os.environ.get("PAIR2_DRYRUN"):
        print("\n[DRYRUN] 不发调用。")
        sys.exit(0)

    raw = {"A": [_rep(a) for _ in range(R)], "B": [_rep(b) for _ in range(R)]}
    fp_all = {r["instrument"] for v in raw.values() for r in v}
    assert len(fp_all) == 1, f"仪器指纹不唯一 {fp_all} —— 本次作废"
    print(f"\n仪器指纹全程一致: {list(fp_all)[0]}")
    fps = {n: [f"{n}{i}" for i in range(R)] for n in raw}
    res = {"meta": meta, "R": R, "min_effect_prior": ME, "raw": raw,
           "verdict_lines": VERDICT_LINES}
    for n in raw:
        rep = KS.reproducibility([r["knots"] for r in raw[n]], fps[n], name=n)
        res[f"repro_{n}"] = rep
        print(f"\n{n}: {rep['verdict']}  结集一致率={rep['set_agreement']:.3f}  翻转={rep['flipping']}")
    s = KS.separation([r["knots"] for r in raw["A"]], [r["knots"] for r in raw["B"]],
                      fps["A"], fps["B"], min_effect=ME)
    res["separation"] = s
    print(f"\n★ 分离: {s['verdict']}  T={s['T']:.5f}  p={s['p']:.4f}  (Stage1 最有利对 T=0.07389)")
    print("\n=== 判决 ===")
    if s["p"] > 0.05:
        print("  典型文本对**分不开** ⇒ 分辨力只够区分词面差异最大的一对")
    elif s["T"] < ME:
        print(f"  分得开但 T={s['T']:.5f} < min_effect={ME} ⇒ **min_effect 必须下调**")
    else:
        print(f"  典型对也分得开 ⇒ min_effect 可升为阈值, 保守取 min({ME}, {s['T']:.5f})")
    with open("/tmp/second_pair_typical.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("写出 /tmp/second_pair_typical.json")
