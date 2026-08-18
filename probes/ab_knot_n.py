#!/usr/bin/env python3
"""重构 A/B：旧链(单次抽样) vs 新链(n=5 聚合)，同一输入、同一环境、各 R 次。

CCE_KNOT_N=1 精确复现改动前的行为(n=1 时中位数即那一次抽样本身)，
所以两臂唯一差异就是采样数 —— 这是能把「重构是否有效」判出来的唯一形态。
此前拿到的 0.65 是在另一份稿子、n=4 下测的, 不能与新链数字直接比(换对象=换仪器)。

判据用 §23 K1 的四项。输出两臂逐项对照。
"""
import json, os, statistics as st, sys, time
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K  # noqa: E402

TEXT = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
CTX = "reddit r/HearingAids hearing_aid: A/B 对照"
R = int(os.environ.get("AB_REPS", "8"))
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))


def one_run(knot_n):
    K.KNOT_N = knot_n
    s1 = K.stage1(TEXT, CTX, 3)
    s2 = K.stage2(TEXT, s1, TAXO)
    # 2026-08-18: 此前只返回 [[key, weight]], 丢掉了 sampling ——
    # 而 occur / top1_stable 正是这个 A/B 唯一能回答自己问题的字段。
    # 对抗评审原话: 「探针丢掉了唯一能回答自己问题的字段」。
    return {"knots": [[k["key"], k["weight"]] for k in s2["knots"]],
            "intensity": s2.get("intensity"),
            "sampling": s2.get("sampling"),
            "support": {k["key"]: k.get("support") for k in s2["knots"]}}


def score(runs, label):
    ser = [json.dumps(r, sort_keys=True) for r in runs]
    pairs = list(combinations(range(len(runs)), 2))
    ident = sum(1 for i, j in pairs if ser[i] == ser[j])
    keys = {k for r in runs for k, _ in r}
    rng = {k: round(max(dict(r).get(k, 0.0) for r in runs) - min(dict(r).get(k, 0.0) for r in runs), 4)
           for k in keys}
    tops = [r[0][0] for r in runs if r]
    agree = max(tops.count(t) for t in set(tops)) if tops else 0
    return {"label": label, "n": len(runs), "identical_pairs": f"{ident}/{len(pairs)}",
            "max_range": max(rng.values()) if rng else 0.0, "ranges": rng,
            "top1_agree": f"{agree}/{len(tops)}", "tops": tops}


out = {}
for label, kn in (("OLD 单次抽样 (CCE_KNOT_N=1)", 1), ("NEW n=5 聚合 (CCE_KNOT_N=5)", 5)):
    runs = []
    for i in range(R):
        t0 = time.time()
        try:
            runs.append(one_run(kn))
            print(f"  {label}  rep{i+1}/{R}  {int(time.time()-t0)}s  {runs[-1]}", flush=True)
        except Exception as e:
            print(f"  {label}  rep{i+1} 失败: {type(e).__name__}", flush=True)
    out[label] = score(runs, label)

print("\n" + "=" * 72)
print(f"{'判据':<26}{'OLD 单抽':>20}{'NEW n=5':>20}")
o, nn = out["OLD 单次抽样 (CCE_KNOT_N=1)"], out["NEW n=5 聚合 (CCE_KNOT_N=5)"]
print(f"{'完全相同读数对':<26}{o['identical_pairs']:>20}{nn['identical_pairs']:>20}")
print(f"{'单结极差(越小越好)':<26}{o['max_range']:>20}{nn['max_range']:>20}")
print(f"{'top-1 一致':<26}{o['top1_agree']:>20}{nn['top1_agree']:>20}")
print(f"\n  OLD tops: {o['tops']}")
print(f"  NEW tops: {nn['tops']}")
print(f"\n  OLD 逐结极差: {dict(sorted(o['ranges'].items(), key=lambda x: -x[1]))}")
print(f"  NEW 逐结极差: {dict(sorted(nn['ranges'].items(), key=lambda x: -x[1]))}")
Path("/tmp/ab_knot_n.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
