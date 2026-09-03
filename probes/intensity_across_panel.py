#!/usr/bin/env python3
"""用**已付费的历史面板**测强度层一致率 —— 31 个文本, 零 API 调用。

## 为什么补这一支
K1-v2 只用了 5 个文本(新烧 320 次调用)。而 phase2 面板的 L0 臂
**早就有 31 个 base × 4 rep 的结读数, 同一台仪器(565470cf26c16d01, gen4)**。
★ 我做 v2 时没用它 —— 这是漏用, 不是没有。owner 指出后才补。

## 它能做什么, 不能做什么
· **不能**让 K1 通过: 面板每 base 只有 4 rep, 而 K1 判据要求 n>=8。
· **能**回答泛化: 「强度不可复现」在 5 个文本上成立, 在 31 个上还成立吗?
  这是**关门方向**(确认负结论), 与 v2 的 INSTRUMENT_WIDE_FAIL 同向则加强, 反向则要重估。
· 面板只有 intensity, **没有 weight** —— 所以 v2 那 320 次调用并非白烧,
  它是 weight 唯一的数据来源。

## 判据
沿用 K1 的逐对容差一致率 A_j(δ=0.10): 对每对 rep, 在**两边都点火**的结上
算 |Δ|<=δ 的比例; 与 v2 逐字相同, 只是 n 从 8 变 4(对数从 28 变 6)。
"""
import itertools
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "tests" / "data" / "phase2" / "panel_checkpoint.jsonl"
MANIFEST = ROOT / "tests" / "data" / "phase2" / "panel_manifest.json"
OUT = ROOT / "tests" / "data" / "phase2" / "intensity_across_panel.json"
DELTA = 0.10
EXPECT_INSTRUMENT = "565470cf26c16d01"


def run(delta=DELTA):
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    inst = man["measurement_instrument"]["instrument_hash"]
    assert inst == EXPECT_INSTRUMENT, \
        f"★ 面板仪器 {inst} != {EXPECT_INSTRUMENT} —— 标定不可跨仪器搬, 中止"

    rows = [json.loads(l) for l in PANEL.read_text(encoding="utf-8").splitlines() if l.strip()]
    by = defaultdict(list)
    for r in rows:
        if r.get("arm") == "L0" and str(r.get("qualified")) == "True" and r.get("knots"):
            by[r["base_id"]].append(r["knots"])

    per_text, agree, occ = {}, [], []
    for bid, reps in sorted(by.items()):
        if len(reps) < 2:
            continue
        a_vals, o_vals = [], []
        for i, j in itertools.combinations(range(len(reps)), 2):
            A, B = reps[i], reps[j]
            common = set(A) & set(B)
            if common:
                a_vals.append(sum(abs(A[k] - B[k]) <= delta for k in common) / len(common))
            union = set(A) | set(B)
            if union:
                o_vals.append(len(common) / len(union))   # 出现率一致(Jaccard)
        if not a_vals:
            continue
        per_text[bid] = {"n_reps": len(reps), "pairs": len(a_vals),
                         "agreement": round(statistics.mean(a_vals), 4),
                         "occurrence_jaccard": round(statistics.mean(o_vals), 4)}
        agree.append(per_text[bid]["agreement"])
        occ.append(per_text[bid]["occurrence_jaccard"])

    return {"kind": "cce.k1.intensity_across_panel.v1",
            "★status": "EXPLORATORY_n4_below_criterion_n8",
            "★usable_for": "确认「强度不可复现」是否跨文本泛化(关门方向) —— **不能**让 K1 通过",
            "★no_weight_in_panel": "面板只有 intensity; weight 仍只有 K1-v2 那 5 个文本",
            "instrument_hash": inst, "delta": delta,
            "texts": len(per_text), "reps_per_text": 4,
            "agreement": {"mean": round(statistics.mean(agree), 4),
                          "median": round(statistics.median(agree), 4),
                          "min": round(min(agree), 4), "max": round(max(agree), 4),
                          "texts_meeting_0.95": sum(a >= 0.95 for a in agree)},
            "occurrence_jaccard": {"mean": round(statistics.mean(occ), 4),
                                   "min": round(min(occ), 4), "max": round(max(occ), 4)},
            "per_text": per_text}


def main():
    r = run()
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    a = r["agreement"]
    print(f"仪器 {r['instrument_hash']} · {r['texts']} 个文本 × {r['reps_per_text']} rep · δ={r['delta']}")
    print(f"  逐对容差一致率 A: 均值 {a['mean']} · 中位 {a['median']} · [{a['min']}, {a['max']}]")
    print(f"  ★ 达到 0.95 的文本: {a['texts_meeting_0.95']}/{r['texts']}")
    o = r["occurrence_jaccard"]
    print(f"  出现率一致(Jaccard): 均值 {o['mean']} · [{o['min']}, {o['max']}]")
    print(f"\n★ {r['★status']} —— {r['★usable_for']}")
    print(f"→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
