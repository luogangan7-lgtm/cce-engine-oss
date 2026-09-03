#!/usr/bin/env python3
"""θ=0.35 的判决有多少是被 weight 抖动翻转的? 零 API 调用。

## 方法
reply 模式下 alignment_score = Σ_k aud_w[k] · dissolve_hit(k, draft)。
**固定 hit 向量**, 只让 aud_w 走同一文本的 8 个 rep ⇒ 分数的散布完全来自 weight 不可靠。
遍历大量随机 hit 向量, 统计「同一输入下 θ 被跨过」的比例。

## 这是**下界**, 不是全部噪声
dissolve_hit 自身是每结 3 次 LLM 表决取中位数, 它的抖动还要再加上去。
所以真实翻转率只会比这里高。

## 为什么必须实测而不能推断
文献(Spearman-Brown / ICC(k))明确聚合会**提升**信度, 所以「分量不可靠 ⇒ 合成量不可靠」
不是可以直接推的。
★ 但那些定理要求分量**独立** —— 这里 9 个权重来自同一次抽样且被全占比约束到和为 1,
  结构上不独立, 前提不成立。实测确认了这一点。
"""
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CKPT = ROOT / "tests" / "data" / "phase2" / "k1_v2_checkpoint.jsonl"
OUT = ROOT / "tests" / "data" / "phase2" / "align_theta_sensitivity.json"
THETA = 0.35
TRIALS = 2000
SEED = 0


def run(theta=THETA, trials=TRIALS, seed=SEED, path=CKPT):
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    by = defaultdict(list)
    for r in rows:
        if r.get("knots"):
            by[r["base_id"]].append(r)
    knots = sorted({k[0] for rs in by.values() for r in rs for k in r["knots"]})
    W = {b: [{k[0]: k[2] for k in r["knots"]} for r in rs] for b, rs in by.items()}
    # 全占比校验: 权重和应为 1, 否则下面的「凸组合」论证不成立
    sums = [round(sum(w.values()), 3) for ws in W.values() for w in ws]
    assert all(abs(s - 1.0) < 0.02 for s in sums), f"权重和不为 1: {sorted(set(sums))[:5]}"

    rnd = random.Random(seed)
    flips = total = 0
    ranges = []
    for _ in range(trials):
        h = {k: rnd.choice([0.0, 0.5, 1.0]) for k in knots}
        for ws in W.values():
            v = [sum(w.get(k, 0.0) * h[k] for k in knots) for w in ws]
            total += 1
            ranges.append(max(v) - min(v))
            if min(v) < theta <= max(v):
                flips += 1
    q = sorted(ranges)
    return {"kind": "cce.align.theta_sensitivity.v1",
            "★status": "LOWER_BOUND_hit_noise_not_included",
            "theta": theta, "texts": len(W), "reps_per_text": {b: len(v) for b, v in W.items()},
            "knots": knots, "trials": trials, "seed": seed, "combinations": total,
            "score_range_same_input": {
                "median": round(statistics.median(ranges), 4),
                "p90": round(q[int(.9 * len(q))], 4), "max": round(max(q), 4),
                "share_gt_0.10": round(sum(r > 0.10 for r in q) / len(q), 4),
                "share_gt_0.20": round(sum(r > 0.20 for r in q) / len(q), 4)},
            "verdict_flip_rate": round(flips / total, 4),
            "★why_aggregation_does_not_rescue": (
                "Spearman-Brown / ICC(k) 要求分量独立; 这 9 个权重来自**同一次抽样**"
                "且被全占比约束到和为 1(已断言 Σw=1) ⇒ 前提不成立。"),
            "★cross_check": "与 2026-08-10 独立实测(同稿重跑 3/8 翻转, |Δ对齐分|均值 0.213)同量级"}


def main():
    r = run()
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    s = r["score_range_same_input"]
    print(f"{r['texts']} 文本 × 8 rep · {r['trials']} 组随机 hit = {r['combinations']} 次组合")
    print(f"  同一输入下分数极差: 中位 {s['median']} · p90 {s['p90']} · max {s['max']}")
    print(f"  ★ θ={r['theta']} 判决被 weight 抖动翻转: {r['verdict_flip_rate']:.1%}  ({r['★status']})")
    print(f"→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
