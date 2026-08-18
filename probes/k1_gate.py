#!/usr/bin/env python3
"""K1 Reliability 闸（重构文档 §23）—— 同项重跑稳定性，四项判据。

为什么不放进 CI: 它要跑 n≥8 次完整链路(每次含 reader_baseline + s1 + s2 共约 16 次模型调用),
单次约 6 分钟、128 次调用。这是**研究闸**, 按需跑, 不是每 PR 跑。
CI 里跑的是它的离线孪生 tests/test_cce_knot_stability.py(聚合语义 + 变异测试)。

用法:
  python3 probes/k1_gate.py <artifacts_dir>     # 目录下含多个 cce-item-*/manifest.json
判据(§23 K1):
  n ≥ 8 · 完全相同的读数对 ≥ 6/8 · 单结权重极差 ≤ 0.10 · top-1 结一致率 ≥ 7/8
退出码: 0 = 四项全过; 1 = 有不达标项; 2 = 输入不足(不可判, 既不判过也不判负)
"""
import json
import sys
from itertools import combinations
from pathlib import Path

CRIT = {"n_min": 8, "identical_pairs_min": 6, "range_max": 0.10, "top1_agree_min": 7}


def load(d: Path):
    out = []
    for f in sorted(d.rglob("manifest.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        s2 = (m.get("stages") or {}).get("s2_knots")
        if not s2:
            continue
        out.append({"cid": (m.get("submission") or {}).get("content_id"),
                    "sha": m.get("text_sha256"),
                    "knots": s2.get("knots"), "intensity": s2.get("intensity"),
                    "top1": (s2.get("knots") or [[None]])[0][0]})
    return out


def main() -> int:
    rows = load(Path(sys.argv[1]))
    if len(rows) < CRIT["n_min"]:
        print(f"⚠️ 不可判: n={len(rows)} < {CRIT['n_min']}")
        return 2
    shas = {r["sha"] for r in rows}
    if len(shas) != 1:
        print(f"❌ 输入指纹不唯一({len(shas)} 种) —— 这不是同项重跑, 测量作废")
        return 2

    n = len(rows)
    ser = [json.dumps(r["knots"], sort_keys=True) for r in rows]
    pairs = list(combinations(range(n), 2))
    identical = sum(1 for i, j in pairs if ser[i] == ser[j])
    # 归一到 /8 的口径(§23 表格按 8 次表述), 用比例换算避免 n≠8 时口径漂移
    ident_scaled = identical / len(pairs) * (CRIT["n_min"] * (CRIT["n_min"] - 1) / 2)

    keys = {k for r in rows for k, _ in (r["knots"] or [])}
    ranges = {}
    for k in keys:
        v = [dict(r["knots"]).get(k, 0.0) for r in rows]
        ranges[k] = round(max(v) - min(v), 4)
    max_range = max(ranges.values()) if ranges else 0.0

    tops = [r["top1"] for r in rows]
    top1_agree = max(tops.count(t) for t in set(tops))
    top1_scaled = top1_agree / n * CRIT["n_min"]

    checks = [
        ("n ≥ 8", n >= CRIT["n_min"], f"{n}"),
        (f"完全相同读数对 ≥ {CRIT['identical_pairs_min']}/28",
         identical >= CRIT["identical_pairs_min"] / 28 * len(pairs),
         f"{identical}/{len(pairs)} (折算 {ident_scaled:.1f}/28)"),
        (f"单结极差 ≤ {CRIT['range_max']}", max_range <= CRIT["range_max"],
         f"{max_range}  最大项 {max(ranges, key=ranges.get) if ranges else '-'}"),
        (f"top-1 一致 ≥ {CRIT['top1_agree_min']}/8", top1_scaled >= CRIT["top1_agree_min"],
         f"{top1_agree}/{n} (折算 {top1_scaled:.1f}/8)"),
    ]
    print(f"K1 Reliability · n={n} · 输入指纹唯一 ✅\n")
    for name, ok, val in checks:
        print(f"  {'✅' if ok else '❌'} {name:<28} {val}")
    print(f"\n  逐结极差: {dict(sorted(ranges.items(), key=lambda x: -x[1]))}")
    print(f"  top-1 各次: {tops}")
    failed = [c[0] for c in checks if not c[1]]
    print(f"\n  → {'K1 通过' if not failed else 'K1 未通过, 不达标项: ' + ', '.join(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
