#!/usr/bin/env python3
"""在**已采集**的 k1_v2 数据上比较各种读数形式的复现性。零 API 调用。

## 这是探索性分析, 不是预注册判定
判定 v2 只预注册了 intensity 与 weight 两层。本脚本回答的是一个**在看到 v2 结果之后**
才提出的问题:「换一种读数形式(粗档 / 秩序)能不能救回来?」

★ 因此它的结论只能用来**关门**, 不能用来开门:
  · 「粗档也不行」是负结论 -> 可以据此不再花钱去试(关门, 低风险)
  · 若某形式看起来行 -> **不得**据此采纳, 必须另立预注册 + 在**新的一批文本**上确认
    (资格池 30 个, v2 用了字典序前 5, 还剩 25 个可作确认集)
本项目已明写: 「不得用同一批输入既调参又验收」。
"""
import itertools
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CKPT = ROOT / "tests" / "data" / "phase2" / "k1_v2_checkpoint.jsonl"
OUT = ROOT / "tests" / "data" / "phase2" / "k1_readout_forms.json"
BANDS = (0.33, 0.66)          # 三档: 低 / 中 / 高
DELTA = 0.10                  # 与 v2 判据同数


def band(v, edges=BANDS):
    return 0 if v < edges[0] else (1 if v < edges[1] else 2)


def spearman(a, b, common):
    ra = {k: i for i, k in enumerate(sorted(common, key=lambda k: -a[k]))}
    rb = {k: i for i, k in enumerate(sorted(common, key=lambda k: -b[k]))}
    n = len(common)
    d2 = sum((ra[k] - rb[k]) ** 2 for k in common)
    return 1 - 6 * d2 / (n * (n * n - 1))


def analyse(path=CKPT):
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("knots")]
    by = defaultdict(list)
    for r in rows:
        by[r["base_id"]].append(r)

    per_text, agg = {}, defaultdict(list)
    for bid, rs in sorted(by.items()):
        acc = defaultdict(list)
        for i, j in itertools.combinations(range(len(rs)), 2):
            a = {k[0]: k[1] for k in rs[i]["knots"]}
            b = {k[0]: k[1] for k in rs[j]["knots"]}
            common = set(a) & set(b)
            if not common:
                continue
            acc["cardinal"].append(sum(abs(a[k] - b[k]) <= DELTA for k in common) / len(common))
            acc["band3"].append(sum(band(a[k]) == band(b[k]) for k in common) / len(common))
            if len(common) >= 3:
                acc["rank_rho"].append(spearman(a, b, common))
            acc["top1"].append(rs[i]["top1"] == rs[j]["top1"])
            acc["top2_set"].append({k[0] for k in rs[i]["knots"][:2]}
                                   == {k[0] for k in rs[j]["knots"][:2]})
        per_text[bid] = {k: round(statistics.mean(v), 4) for k, v in acc.items() if v}
        for k, v in per_text[bid].items():
            agg[k].append(v)

    forms = {k: {"mean": round(statistics.mean(v), 4), "worst_text": round(min(v), 4),
                 "meets_0.95_on_all_texts": min(v) >= 0.95} for k, v in agg.items()}
    return {"kind": "cce.k1.readout_forms.exploratory.v1",
            "★status": "EXPLORATORY_NOT_PREREGISTERED",
            "★usable_for": "关门(排除某读数形式) —— 不得用来采纳任何形式",
            "★to_adopt_any_form": ("须另立预注册, 并在资格池剩余 25 个文本里取新的一批确认; "
                                   "不得用同一批输入既调参又验收"),
            "source": str(CKPT.relative_to(ROOT)), "texts": len(by),
            "reps_per_text": {b: len(v) for b, v in sorted(by.items())},
            "tolerance_delta": DELTA, "bands": list(BANDS),
            "per_text": per_text, "forms": forms}


def main():
    r = analyse()
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{'读数形式':<12}{'均值':>9}{'最差文本':>10}   全文本≥0.95")
    for name, f in r["forms"].items():
        print(f"{name:<12}{f['mean']:>9.3f}{f['worst_text']:>10.3f}   "
              f"{'✅' if f['meets_0.95_on_all_texts'] else '❌'}")
    print(f"\n★ {r['★status']} —— {r['★usable_for']}")
    print(f"→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
