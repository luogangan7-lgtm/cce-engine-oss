#!/usr/bin/env python3
"""Stage1 等长阳性对照 —— 解锁 KSEP 的 min_effect。

## 为什么必须有它
2026-08-18 run 32130867661 选文本的规则是「长度升序取首/中/末」, 结果 293/1581/4058 字,
长度 ↔ 过闸结数 Spearman ρ=1。**任何分离都可以用长度解释**, 所以 T0-vs-T2 已被否决。
KSEP 的 `min_effect` 现在是 None ⇒ verdict 恒为 UNCALIBRATED ⇒ **PASS 分支结构上不存在**。
只有一次等长对照能给出 min_effect 的第一个经验锚。

## 前登记设计(跑之前写死, 不许事后改)
- T_a = 语料里**天然**最短的那份(293 字, index 0)
- T_b = 其余 11 份各截到 **≤293 字的最大词边界前缀**, 取与 T_a **Jaccard 最低**的那份
  → 选「词面最不像」是**故意给仪器最好的机会**: 这里都分不开, 别处更分不开。
  → 不是挑对结论有利的样本; 选择规则只用词面, 不看九结读数。
- R = 4(**不是 3**): KSEP 要求 R>=4, 否则精确置换 p 下限 1/10=0.1 > alpha=0.05,
  设计上永远无法拒绝零假设 —— 那种跑法是浪费钱, KSEP 会直接抛错。
- 成本 = 2 文本 × 4 rep × (s1 3 + s2 5) = **64 次调用**

⚠️ 两份都在**同一个 run 内**跑。混用历史 run 的 rep 会引入批次效应,
   而批次效应**抬高**分离度 —— 那是假阳性方向, 绝不能省这一步。

## 判决线(前登记)

⚠️ 历史注记(2026-08-18 [3/4], **不改动上述前登记文本** —— 前登记禁止事后修改):
   本探针跑完后, `min_effect` 这个概念被拆成三个互不相容的语义
   (仪器分辨率 / SESOI / 等价边界)。本次产出的 0.06278 现被降级为
   `KSEP.PAIR1_NULL_CALIBRATION_STATISTIC`, 角色 CALIBRATION_ONLY ——
   它是**这一对文本自己的置换零分布水位**, 不是「多大的差异才值得关心」。
   故本探针判决线里「min_effect 可标定 / PASS 分支从此存在」的措辞,
   按今天的理解应读作「拿到了 pair-1 的噪声水位」, 而**不是**「拿到了实践显著性阈值」。
"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K          # noqa: E402
import cce_ksep as KS                  # noqa: E402

R = int(os.environ.get("EQL_REPS", "4"))
MAXLEN = int(os.environ.get("EQL_MAXLEN", "293"))
CTX = "reddit r/HearingAids hearing_aid: 等长阳性对照"
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))

VERDICT_LINES = [
    "p <= 0.05 且 T 明显 > 0 → 仪器在**等长**条件下分得开两份不同内容 ⇒ 读的是内容不是长度。"
    "min_effect 取本次 T 的下界(保守: T 的置换零分布 95 分位), KSEP 的 PASS 分支从此存在, P2 可开",
    "p > 0.05 → 在 293 字尺度上, 仪器对内容**没有可分辨的响应**。"
    "★ 此时不可直接说「仪器盲」—— 阳性对照失败无法区分「仪器无分辨力」与「这两份文本恰好真的像」。"
    "已用 Jaccard 最低对做了最有利的选择, 故更偏向前者, 但仍需第二对才能定论。P2 停",
    "★ 无论哪一支: 两份文本各自的可复现性(结集一致率/occur-n 极差)一并报出, "
    "它是单文本内部性质, 与本对照的成败无关",
    "★ 禁止事后改文本、改 R、改判决线。改了就是新实验, 旧结论作废。",
]


def _prefix(t, maxlen):
    """截到 <=maxlen 的最大词边界前缀。避免半句话造成的伪差异。"""
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
    a = texts[0]
    assert len(a) <= MAXLEN, f"最短文本 {len(a)} 字 > MAXLEN {MAXLEN}"
    cands = [(_jac(a, _prefix(t, MAXLEN)), i, _prefix(t, MAXLEN))
             for i, t in enumerate(texts) if t != a]
    cands.sort()
    j, idx, b = cands[0]
    return a, b, {"a_len": len(a), "b_len": len(b), "b_src_index": idx,
                  "jaccard": round(j, 4),
                  "jaccard_all": [(i, round(x, 4)) for x, i, _ in cands]}


def _rep(text, tag):
    """与 probes/discriminability.py 的 one_rep 逐字段同构 —— 两次实验必须可比。"""
    s1 = K.stage1(text, CTX, 3)
    s2 = K.stage2(text, s1, TAXO)
    return {"instrument": s2["instrument"]["instrument_hash"],
            "knots": {k["key"]: k["intensity"] for k in s2["knots"]},
            "per_knot": s2["sampling"]["per_knot"],
            "top1": s2["sampling"]["top1_mode"]}


if __name__ == "__main__":
    a, b, meta = _pick()
    print("=== Stage1 等长阳性对照 (前登记) ===")
    for v in VERDICT_LINES:
        print("  · " + v)
    print("\n选文本:", json.dumps(meta, ensure_ascii=False))
    print("  T_a:", repr(a[:90]))
    print("  T_b:", repr(b[:90]))
    if os.environ.get("EQL_DRYRUN"):
        print("\n[DRYRUN] 只验选文本, 不发调用。")
        sys.exit(0)

    raw = {}
    for name, txt in (("A", a), ("B", b)):
        raw[name] = [_rep(txt, f"{name}{i}") for i in range(R)]
        print(f"  {name} 完成 {R} rep")
    # 仪器必须全程同一个。换了就不是同一次测量, 两组不可比。
    fp_all = {r["instrument"] for v in raw.values() for r in v}
    assert len(fp_all) == 1, f"仪器指纹不唯一 {fp_all} —— 本次对照作废"
    print(f"\n仪器指纹全程一致: {fp_all.pop()}")

    fps = {n: [json.dumps(r["knots"], sort_keys=True) + f"|{i}" for i, r in enumerate(v)]
           for n, v in raw.items()}
    res = {"meta": meta, "R": R, "raw": raw, "verdict_lines": VERDICT_LINES}
    for n in raw:
        rep = KS.reproducibility([r["knots"] for r in raw[n]], fps[n], name=n)
        res[f"repro_{n}"] = rep
        print(f"\n{n} 可复现性: {rep['verdict']}  结集一致率={rep['set_agreement']:.3f}  翻转={rep['flipping']}")
    sep = KS.separation([r["knots"] for r in raw["A"]], [r["knots"] for r in raw["B"]],
                        fps["A"], fps["B"], nameA="A", nameB="B")
    res["separation"] = sep
    print(f"\n★ 分离: {sep['verdict']}  T={sep['T']:.5f}  p={sep['p']:.4f}  p下限={sep['p_floor']:.4f}")
    print(f"  判决: {'p<=0.05 ⇒ 等长下分得开, min_effect 可标定' if sep['p'] <= 0.05 else 'p>0.05 ⇒ 293 字尺度上无可分辨响应, P2 停'}")
    with open("/tmp/equal_length_control.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("\n写出 /tmp/equal_length_control.json")
