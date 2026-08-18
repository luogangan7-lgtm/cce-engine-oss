#!/usr/bin/env python3
"""P2 开工前的两个前置问题 —— 同一批 60 次调用回答。

Observation 层(`cce_response_chain.py`)喂的是 **stage1 四层**(desire/need/emotion/action),
九结(stage2)按 L191 明确**不进聚合**。所以 2026-08-18 关于九结「无空读数」的发现
**不能外推到这一层** —— 必须单独测。

## 问题一: stage1 有没有「空读数」这一档？
四层各自被强制归一化(和为 1) ⇒ 任何文本都会得到一个分布。
问题是: 对**无人称、无诉求**的文本(数字表/法律样板), 它给出的是接近均匀的分布(=「我读不出」),
还是一个自信的、有明确峰值的分布(=「这张数字表想要 X」)？
  · 接近均匀 → stage1 有可用的零点, 绝对读数携带信息
  · 远离均匀 → 与九结同病, **P2 的指标必须是差分的**

## ★ 问题二: `confidence` 量错了东西吗？
`_measurement()` 里 `confidence = 1 - mean(within_js)`, 即 **同一次运行内 k 档温度之间**的散布。
本轮(2026-08-18)已反复证明: **组内散布不等于跨次可复现性**。
本探针每个文本跑 R=4 次独立 rep, 于是可以直接比:
    within_js(同一 run 内, 即 confidence 的来源)  vs  across_run_js(rep 之间)
  · across >> within → `confidence` **系统性高估可靠性**, 下游读它就是被误导
  · 两者相当 → `confidence` 是可用的代理

成本: 5 文本 × R=4 × k=3 = **60 次调用**(只跑 stage1, 不跑 stage2)。

## 前登记判决
"""
import json, os, statistics as st, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K   # noqa: E402
from exp_v4_full_validation import DESIRES, NEED_KEYS, js_divergence  # noqa: E402
from exp_v4_causal_chain import EMOTIONS, ACTIONS  # noqa: E402

R = int(os.environ.get("P2B_REPS", "4"))
KK = int(os.environ.get("P2B_K", "3"))
CTX = "reddit r/HearingAids hearing_aid: P2 基线"
LAYERS = {"desire_vec": DESIRES, "need_vec": NEED_KEYS,
          "emotion_vec": EMOTIONS, "action_vec": ACTIONS}

VERDICT_LINES = [
    "★问题一: 无人称文本(数字表/法律样板)的层分布 JS(·‖均匀)。"
    "若与真人文本相当或更高 → stage1 **没有**空读数这一档 ⇒ P2 指标必须差分化",
    "★问题一: 若无人称文本明显更接近均匀 → stage1 有零点, 绝对读数可用(但仍需报不确定度)",
    "★问题二: across_run_js 与 within_js 的比值。>1.5 → confidence 系统性高估可靠性, "
    "**必须在 Observation 层显式标注跨次信度未测**",
    "★问题二: 比值 ≈1 → confidence 是可用代理, 维持现状",
    "★ 本探针只跑 stage1。九结结论不得据此外推, 反之亦然。",
    "★ 禁止事后改文本、改 R、改判决线。",
]


def _texts():
    items = json.loads((ROOT / "run_items" / "reddit_20260810.json").read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items") or items.get("run_items") or []
    base = sorted({(it["reader"] or "").strip() for it in items
                   if (it.get("reader") or "").strip()}, key=len)[0]
    out = {"HUMAN_base": base}
    for c in ("filler_numeric", "filler_legal", "filler_procedural", "filler_neutral_20260818"):
        out[c] = (ROOT / "tests" / "data" / f"{c}.txt").read_text(encoding="utf-8").strip()
    return out


def _uniform_js(vec):
    v = [max(0.0, x) for x in vec]
    s = sum(v) or 1.0
    v = [x / s for x in v]
    return js_divergence(v, [1.0 / len(v)] * len(v))


if __name__ == "__main__":
    texts = _texts()
    print("=== P2 前置基线 (前登记) ===")
    for v in VERDICT_LINES:
        print("  · " + v)
    print("\n文本: " + "  ".join(f"{k}={len(v)}字" for k, v in texts.items()))
    if os.environ.get("P2B_DRYRUN"):
        print("\n[DRYRUN] 不发调用。")
        sys.exit(0)

    raw = {}
    for name, t in texts.items():
        reps = []
        for i in range(R):
            s1 = K.stage1(t, CTX, KK)
            reps.append({"layers": s1["layers"], "within_js": s1.get("within_js") or {}})
        raw[name] = reps
        print(f"  {name} 完成 {R} rep")

    res = {"R": R, "k": KK, "raw": raw, "verdict_lines": VERDICT_LINES,
           "lens": {k: len(v) for k, v in texts.items()}}

    print("\n=== 问题一: 各层距均匀分布的 JS (越大=越自信地断言) ===")
    q1 = {}
    for name, reps in raw.items():
        per = {}
        for vk in LAYERS:
            per[vk] = round(st.mean(_uniform_js(r["layers"][vk]) for r in reps), 4)
        q1[name] = per
        print(f"  {name:26s} " + "  ".join(f"{vk.split('_')[0]}={per[vk]:.4f}" for vk in LAYERS))
    res["js_from_uniform"] = q1
    hum = st.mean(q1["HUMAN_base"].values())
    fil = st.mean(st.mean(v.values()) for k, v in q1.items() if k != "HUMAN_base")
    print(f"\n  真人文本均值={hum:.4f}   无人称文本均值={fil:.4f}   比值={fil/hum:.2f}")

    print("\n=== ★ 问题二: within_js(confidence 的来源) vs across_run_js ===")
    q2 = {}
    for name, reps in raw.items():
        row = {}
        for vk in LAYERS:
            wi = [r["within_js"].get(vk) for r in reps if isinstance(r["within_js"].get(vk), (int, float))]
            ac = [js_divergence(reps[i]["layers"][vk], reps[j]["layers"][vk])
                  for i in range(len(reps)) for j in range(i + 1, len(reps))]
            row[vk] = {"within": round(st.mean(wi), 4) if wi else None,
                       "across": round(st.mean(ac), 4),
                       "ratio": round(st.mean(ac) / st.mean(wi), 2) if wi and st.mean(wi) > 0 else None}
        q2[name] = row
        print(f"  {name:26s} " + "  ".join(
            f"{vk.split('_')[0]} w={row[vk]['within']} a={row[vk]['across']} ×{row[vk]['ratio']}"
            for vk in LAYERS))
    res["within_vs_across"] = q2
    ratios = [c["ratio"] for r in q2.values() for c in r.values() if c["ratio"]]
    med = st.median(ratios)
    print(f"\n  ★ across/within 比值中位数 = {med:.2f}  (n={len(ratios)} 个 文本×层 格)")
    print("  判决: " + ("confidence **系统性高估可靠性** ⇒ Observation 层必须显式标注跨次信度未测"
                       if med > 1.5 else "confidence 是可用代理, 维持现状"))
    res["ratio_median"] = med
    with open("/tmp/p2_stage1_baseline.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("\n写出 /tmp/p2_stage1_baseline.json")
