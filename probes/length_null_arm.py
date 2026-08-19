#!/usr/bin/env python3
"""Stage2 零假设臂: 长度垫料会不会推动读数？三臂共用基线。

## 为什么这是最高风险的一臂
run 32130867661 的三份文本 字数↔过闸结数 Spearman ρ=1(293→1-2结, 1581→1-2结, 4058→5-6结)。
Stage1(run 32141330271) 已证等长下仪器分得开内容, 但也测出**等长内容效应只有
长度驱动效应的 18.2%** —— 剩下 82% 是什么, 这一臂来定。

**若把 T_a 垫到 T1 的长度就让读数动了 ⇒「T2 结更丰富是因为它内容更丰富」整批作废。**

## 三臂, 不是两臂 —— 把一个假设换成一次实测
「垫料本身无结」是**无法验证的假设**。若垫料带结, 负对照的结论直接废掉。
所以加测 `FILL`(垫料单独):
  · BASE = T_a (293 字)
  · PAD  = T_a + 垫料 (1564 字, T1 是 1581)
  · FILL = 垫料单独 (1270 字)
共用 BASE ⇒ 三臂总价 = 3 × R × 8 = 96 次调用, 与两臂加一次独立验证同价。

## 前登记判决(跑前写死)
"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K   # noqa: E402
import cce_ksep as KS           # noqa: E402

R = int(os.environ.get("NULL_REPS", "4"))
CTX = "reddit r/HearingAids hearing_aid: 长度零假设臂"
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
# [3/4] 常量已降级: 它是 pair-1 自己的置换零分布水位, **不是 SESOI**。
# 传给判据时必须带 margin_is_sesoi=False, 否则会被读成「等价」。
ME = KS.PAIR1_NULL_CALIBRATION_STATISTIC["value"]

VERDICT_LINES = [
    "★主判 BASE vs PAD: p>0.05 或 T<min_effect(%.5f) → 垫料**没有**推动读数 ⇒ "
    "长度本身不是驱动源, T2 结更丰富可继续归因于内容" % ME,
    "★主判 BASE vs PAD: p<=0.05 且 T>=min_effect → **垫料推动了读数** ⇒ "
    "『T2 结更丰富因为内容更丰富』作废, 所有跨长度的九结比较全部不可用",
    "★辅判 FILL 单独: 若 FILL 自己就点火出结, 则 PAD 的位移**不能**归因于长度, "
    "只能归因于『垫料带进了内容』—— 这正是三臂而非两臂的理由",
    "★辅判 FILL: 若 FILL 近乎不点火而 PAD 仍位移 ⇒ 位移由**长度本身**驱动, 这是最坏情况",
    "★ NOT_SEPARATED 不等于『相同』。要主张 BASE 与 PAD 相同必须过等价检验; "
    "本臂只能报『低于当前分辨率(min_effect=%.5f)』" % ME,
    "★ 禁止事后改文本、改垫料、改 R、改判决线。",
]


def _corpus():
    items = json.loads((ROOT / "run_items" / "reddit_20260810.json").read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items") or items.get("run_items") or []
    return sorted({(it["reader"] or "").strip() for it in items
                   if (it.get("reader") or "").strip()}, key=len)


def _rep(text):
    s1 = K.stage1(text, CTX, 3)
    s2 = K.stage2(text, s1, TAXO)
    return {"instrument": s2["instrument"]["instrument_hash"],
            "knots": {k["key"]: k["intensity"] for k in s2["knots"]},
            "per_knot": s2["sampling"]["per_knot"],
            "top1": s2["sampling"]["top1_mode"]}


if __name__ == "__main__":
    texts = _corpus()
    base = texts[0]
    fill = (ROOT / "tests" / "data" / "filler_neutral_20260818.txt").read_text(encoding="utf-8").strip()
    pad = base + "\n" + fill
    arms = {"BASE": base, "PAD": pad, "FILL": fill}
    print("=== Stage2 长度零假设臂 (前登记) ===")
    for v in VERDICT_LINES:
        print("  · " + v)
    print("\n臂长度: " + "  ".join(f"{k}={len(v)}字" for k, v in arms.items())
          + f"   (对照 T1={len(texts[6])}字)")
    if os.environ.get("NULL_DRYRUN"):
        print("\n[DRYRUN] 不发调用。")
        sys.exit(0)

    raw = {k: [_rep(v) for _ in range(R)] for k, v in arms.items()}
    for k in raw:
        print(f"  {k} 完成 {R} rep")
    fp_all = {r["instrument"] for v in raw.values() for r in v}
    assert len(fp_all) == 1, f"仪器指纹不唯一 {fp_all} —— 本臂作废"
    print(f"\n仪器指纹全程一致: {list(fp_all)[0]}")

    fps = {n: [f"{n}{i}" for i in range(R)] for n in raw}
    res = {"arms_len": {k: len(v) for k, v in arms.items()}, "R": R,
           "margin": ME, "margin_is_sesoi": False, "raw": raw, "verdict_lines": VERDICT_LINES}
    for n in raw:
        rep = KS.reproducibility([r["knots"] for r in raw[n]], fps[n], name=n)
        res[f"repro_{n}"] = rep
        print(f"\n{n}: {rep['verdict']}  结集一致率={rep['set_agreement']:.3f}  "
              f"翻转={rep['flipping']}  结={sorted(set().union(*[set(r['knots']) for r in raw[n]]))}")
    for a, b in (("BASE", "PAD"), ("BASE", "FILL"), ("PAD", "FILL")):
        s = KS.separation([r["knots"] for r in raw[a]], [r["knots"] for r in raw[b]],
                          fps[a], fps[b], margin=ME, margin_is_sesoi=False, nameA=a, nameB=b)
        res[f"sep_{a}_{b}"] = s
        print(f"\n★ {a} vs {b}: {s['verdict']}  T={s['T']:.5f}  p={s['p']:.4f}")
    # ⚠️ 2026-08-18 修: 此处原为 `if p > 0.05 or T < ME: 判定没有推动读数`。
    #   那一行把 **p>0.05 当成了「无效应」的证据**, 且在 T=0.10792(高于 min_effect)
    #   时仍打印「低于当前分辨率」。判决一律走 KSEP.verdict3, 探针不自己判。
    v = KS.verdict3([r["knots"] for r in raw["BASE"]], [r["knots"] for r in raw["PAD"]],
                    fps["BASE"], fps["PAD"], margin=ME, margin_is_sesoi=False, nameA="BASE", nameB="PAD")
    res["verdict3_BASE_PAD"] = v
    print("\n=== 主判 ===")
    print({"SEPARATED": "  ★★ 垫料推动了读数 ⇒ 跨长度的九结比较全部不可用",
           "EQUIVALENT": "  垫料没有推动读数(差异小于当前分辨率) ⇒ 长度本身不是驱动源",
           "UNDERPOWERED": "  ★ 欠功效: 既不能说不同, 也不能说相同。**不是阴性结论。**",
           "UNCALIBRATED": "  未标定, 无判决"}[v["verdict"]])
    print(f"    T={v['T']:.5f}  p={v['p']:.4f}  等价上界={v['equiv_upper']}  min_effect={ME}")
    # 负对照的前提检查: 垫料自己带不带结
    fl = sorted(set().union(*[set(r["knots"]) for r in raw["FILL"]]))
    bs = set().union(*[set(r["knots"]) for r in raw["BASE"]])
    pd_ = set().union(*[set(r["knots"]) for r in raw["PAD"]])
    res["filler_knots"] = fl
    if fl:
        print(f"  ⚠️ 垫料**自带结** {fl}; PAD 比 BASE 多出 {sorted(pd_ - bs)}"
              f", 其中 {sorted(set(fl) & (pd_ - bs))} 来自垫料")
        print("     ⇒ 「无结垫料」前提不成立, **本臂无法回答长度问题**。这正是第三臂的用途。")
    with open("/tmp/length_null_arm.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("写出 /tmp/length_null_arm.json")
