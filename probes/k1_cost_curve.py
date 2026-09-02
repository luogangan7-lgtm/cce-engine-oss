#!/usr/bin/env python3
"""A_j(0.10) 随 stage2 draw 数的成本曲线 —— 0 次新增调用。

前登记: tests/data/phase2/k1_cost_curve_prereg.json (含五个分支, 跑前冻结)
★ 判据阈值(δ=0.10, A>=0.95)在 commit f2b52ba 冻结, **早于本测量** —— git 时间可证。

数据来自 k1_rootcause 的 LIVE 臂(10 rep x 12 draw)。s2 抽样按 i%3 轮转 3 份 s1 prompt,
故取前 n 个 draw **严格复现**一次 n-draw 运行的分配, 不是近似。
"""
import itertools
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "probes"))
from k1_gate import CRIT  # noqa: E402

P = ROOT / "tests" / "data" / "phase2"
SPEC = json.loads((P / "k1_cost_curve_prereg.json").read_text(encoding="utf-8"))
DELTA, AMIN = CRIT["tolerance_delta"], CRIT["agreement_min"]


def live_reps():
    rows = [json.loads(l) for l in
            (P / "k1_rootcause_checkpoint.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    out = []
    for r in rows:
        if r["arm"] != "LIVE" or not r.get("ledger"):
            continue
        g = [d for d in r["ledger"] if not d.get("infra") and d.get("knot_vector")]
        assert all(d["prompt_idx"] == d["draw_id"] % 3 for d in g), \
            "★ 轮转不是 i%3, 前缀不再严格复现 n-draw 运行"
        out.append(g)
    return out


def med_nz(v):
    nz = [x for x in v if x > 0]
    return statistics.median(nz) if nz else None


def agreement_at(reps, n_draw, knots):
    """返回 {结: A_j}，只含在这个 n 下**稳定出现**的结。合格集随 n 重新判定。"""
    n_rep = len(reps)
    m_need = math.ceil(CRIT["occurrence_agree_min"] / 8 * n_rep)
    out = {}
    for k in knots:
        vals = [med_nz([d["knot_vector"][k] for d in r[:n_draw]]) for r in reps]
        fired = [v for v in vals if v is not None]
        if len(fired) < m_need:
            continue                      # 出现率不稳或稳定缺席 —— 不是 draw 数的问题
        pairs = list(itertools.combinations(fired, 2))
        out[k] = sum(1 for a, b in pairs if abs(a - b) <= DELTA) / len(pairs)
    return out


def main() -> int:
    reps = live_reps()
    knots = sorted(reps[0][0]["knot_vector"])
    max_n = min(len(r) for r in reps)
    print("=" * 76)
    print("A_j(0.10) 成本曲线 —— 0 次新增调用")
    print("=" * 76)
    print(f"{len(reps)} rep x {max_n} draw · 目标 min_j A_j >= {AMIN} (冻结于 f2b52ba, 早于本测量)")
    print(f"合格集**随 n 重新判定**: 稳定出现要求 m_j >= "
          f"{math.ceil(CRIT['occurrence_agree_min'] / 8 * len(reps))}/{len(reps)}\n")

    curve, rows_out = [], []
    print(f"  {'n':>3} {'合格结数':>7} {'min A_j':>9} {'最差项':>11} {'留一 min':>9} {'留一 max':>9}")
    for n in range(2, max_n + 1):
        a = agreement_at(reps, n, knots)
        if not a:
            print(f"  {n:>3} {'0':>7}   —— 无稳定出现的结")
            continue
        worst_k = min(a, key=a.get)
        worst = a[worst_k]
        loo = []
        for i in range(len(reps)):
            sub = [r for j, r in enumerate(reps) if j != i]
            b = agreement_at(sub, n, knots)
            if b:
                loo.append(min(b.values()))
        curve.append((n, worst))
        rows_out.append({"n": n, "eligible": len(a), "min_A": round(worst, 4),
                         "worst_knot": worst_k, "per_knot": {k: round(v, 4) for k, v in a.items()},
                         "loo_min": round(min(loo), 4) if loo else None,
                         "loo_max": round(max(loo), 4) if loo else None})
        print(f"  {n:>3} {len(a):>7} {worst:>9.3f} {worst_k:>11} "
              f"{(min(loo) if loo else 0):>9.3f} {(max(loo) if loo else 0):>9.3f}")

    reached = [n for n, w in curve if w >= AMIN]
    ws = [w for _, w in curve]
    mono = all(b >= a - 1e-9 for a, b in zip(ws, ws[1:]))
    print()
    if reached:
        branch, note = "B1_reached", f"n* = {reached[0]} —— 0 次新增调用即可收工"
    elif mono and ws[-1] > ws[0]:
        branch, note = "B2_climbing", f"单调上升 {ws[0]:.3f} -> {ws[-1]:.3f}, 但 n={max_n} 仍未达 {AMIN}"
    elif ws[-1] < ws[0] - 0.05:
        branch, note = "B5_declining", f"下降 {ws[0]:.3f} -> {ws[-1]:.3f} —— 与理论矛盾, 必须先解释机制"
    elif max(ws) - min(ws) < 0.05:
        branch, note = "B3_flat", f"平坦(跨度 {max(ws)-min(ws):.3f}) —— 与「零均值抽样噪声」矛盾, 必须重查"
    else:
        branch, note = "B4_noisy", f"非单调(跨度 {max(ws)-min(ws):.3f}) —— 可能是 A_j 估计误差, 需更多 rep"
    print(f"★ 落入前登记分支: {branch}")
    print(f"  {note}")
    print(f"  {SPEC['★branches'][branch]}")

    (P / "k1_cost_curve_verdict.json").write_text(json.dumps({
        "block": "K1_AGREEMENT_COST_CURVE", "measured_at": "2026-09-02",
        "prereg": "tests/data/phase2/k1_cost_curve_prereg.json",
        "new_calls": 0, "reps": len(reps), "max_draws": max_n,
        "delta": DELTA, "agreement_min": AMIN,
        "curve": rows_out, "branch": branch, "note": note,
        "n_star": reached[0] if reached else None,
        "monotone": mono,
        "scope": SPEC["scope"]["limit"],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n产物: tests/data/phase2/k1_cost_curve_verdict.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
