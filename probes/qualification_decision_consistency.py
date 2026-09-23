#!/usr/bin/env python3
"""资格考的 **decision consistency** —— 同一份考卷重复施测, 判决稳不稳。

## ★ 这是 v2 唯一能在**不换锚例**的条件下做的确证
v2 的核心主张是「三态比二值稳」。它可以直接测: 同一份 5 题考卷跑 N 次,
比较 **v1 二值判决**(top1 >= 4/5 合格) 与 **v2 三态判决**(Wilson 区间 vs indifference region)
的**重复判决一致性** —— 这正是 AERA/APA/NCME Standards 对有 cut score 的测验所要求的量
(Livingston & Lewis 1995 是估计它的经典方法)。

## ★★ 它测得到什么、测不到什么
· **测得到**: decision consistency(重复施测是否给出相同分类)。
· **测不到**: decision accuracy(观测分类与真实状态的一致程度) —— 那需要知道真实能力,
  而真实能力只能靠**更多独立锚例**估计, 而锚例扩充受阻于「没有第二个模型家族可定真值」。
★ 所以本探针只回答一半, 且必须写明是哪一半。

## 已有的三次(同卷, temp=0)
M3 5/5·5/5·5/5 · M2.5 5/5·5/5·4/5 · **M2.7 3/5·5/5·4/5** · M2 4/5·5/5·5/5 · Text-01 5/5·5/5·5/5
本探针再跑 N 次, 把样本量做到能算一致率。
"""
import json
import os
import pathlib
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault")
sys.path.insert(0, str(ROOT / "accuracy"))
import run_gates as RG  # noqa: E402

N_REPEATS = int(os.environ.get("QC_REPEATS", "10"))
OUT = VAULT / "cce_runs" / "qual_decision_consistency"
PRIOR = {"MiniMax-M3": [5, 5, 5], "MiniMax-M2.5": [5, 5, 4], "MiniMax-M2.7": [3, 5, 4],
         "MiniMax-M2": [4, 5, 5], "MiniMax-Text-01": [5, 5, 5]}   # 2026-09-07 的三次


def one_exam(model):
    """跑一次完整的留一法资格考, 返回答对数。"""
    return RG.qualify(model)["hits"]


def main():
    scores = {m: list(PRIOR.get(m, [])) for m in RG.MODELS}
    jobs = [(m, i) for i in range(N_REPEATS) for m in RG.MODELS]
    print(f"重复施测 {N_REPEATS} 次 × {len(RG.MODELS)} 名 = {len(jobs)} 场考试 "
          f"({len(jobs)*len(RG.ANCHOR_IDS)} 次调用)", flush=True)
    with ThreadPoolExecutor(max_workers=5) as ex:
        for (m, i), h in zip(jobs, ex.map(lambda a: one_exam(a[0]), jobs)):
            scores[m].append(h)
            if (i + 1) % 2 == 0 and m == RG.MODELS[-1]:
                print(f"  第 {i+1}/{N_REPEATS} 轮完成", flush=True)

    n_anch = len(RG.ANCHOR_IDS)
    rows = {}
    for m, hs in scores.items():
        v1 = ["PASS" if h >= 4 else "FAIL" for h in hs]
        v2 = [RG.qualification_state(h, n_anch)[0] for h in hs]
        c1, c2 = Counter(v1), Counter(v2)
        # decision consistency = 两次独立施测给出相同分类的概率(在观测分布下)
        pc = lambda c: sum((v / len(hs)) ** 2 for v in c.values())
        # ★★ 「一致性高」可能只是因为**几乎不做判决**。必须同时报**判决覆盖率**:
        #   v1 每次都判(覆盖率恒为 1.0); v2 只在 QUALIFIED/DISQUALIFIED 时才算做了判决。
        cov2 = sum(1 for x in v2 if x != "UNRESOLVED") / len(v2)
        decided2 = [x for x in v2 if x != "UNRESOLVED"]
        rows[m] = {"scores": hs, "n_exams": len(hs),
                   "v1_binary": dict(c1), "v1_consistency": round(pc(c1), 4),
                   "v1_flipped": len(c1) > 1, "v1_coverage": 1.0,
                   "v2_三态": dict(c2), "v2_consistency": round(pc(c2), 4),
                   "v2_flipped": len(c2) > 1, "v2_coverage": round(cov2, 4),
                   "v2_consistency_among_decided": (
                       round(pc(Counter(decided2)), 4) if decided2 else None),
                   "★the_tradeoff": (
                       f"v1 覆盖率 100% 但一致性 {pc(c1):.2f}; "
                       f"v2 覆盖率 {cov2:.0%} —— " +
                       ("**它在这名标注者上一次判决都没做**, 所谓「稳」是空的"
                        if cov2 == 0 else f"做判决时一致性 {pc(Counter(decided2)):.2f}"))}

    res = {
        "block": "QUALIFICATION_DECISION_CONSISTENCY",
        "★what_it_answers": "**decision consistency**(重复施测是否给出相同分类)。",
        "★what_it_does_NOT_answer": (
            "★★ **decision accuracy**(观测分类与真实状态的一致程度) —— 那需要知道真实能力, "
            "而真实能力只能靠**更多独立锚例**估计。锚例扩充受阻于「没有第二个模型家族可定真值」"
            "(2026-09-07 探活: 阿里云 403 · 智谱 429 · Kimi 429 · JustOneAPI 404)。"
            "⇒ 本探针只回答一半, 另一半**结构上做不了**。"),
        "n_anchors": n_anch, "n_exams_per_model": len(next(iter(scores.values()))),
        "★includes_prior_runs": "前 3 次来自 2026-09-07 的 run1/run2/run3, 同卷同 temp。",
        "per_model": rows,
        "★summary": {
            "v1_models_that_flipped": [m for m, r in rows.items() if r["v1_flipped"]],
            "v2_models_that_flipped": [m for m, r in rows.items() if r["v2_flipped"]],
            "v1_mean_consistency": round(sum(r["v1_consistency"] for r in rows.values()) / len(rows), 4),
            "v2_mean_consistency": round(sum(r["v2_consistency"] for r in rows.values()) / len(rows), 4),
            "v1_mean_coverage": 1.0,
            "★v2_mean_coverage": round(sum(r["v2_coverage"] for r in rows.values()) / len(rows), 4),
        },
    }
    res["★reading"] = (
        f"★ v1 二值判决有 **{len(res['★summary']['v1_models_that_flipped'])}/{len(rows)}** 名标注者"
        f"在重复施测间**翻转过**; v2 三态有 **{len(res['★summary']['v2_models_that_flipped'])}/{len(rows)}** 名。\n"
        f"★★★ 但**平凡解释必须先排除**: v2 的判决覆盖率是 "
        f"**{res['★summary']['★v2_mean_coverage']:.0%}**(v1 恒为 100%)。"
        "若覆盖率接近 0, 那 v2 的「稳」是**空的** —— 它不是判得更稳, 是**几乎不判**。\n"
        "★ 而这恰恰**不是缺陷, 是设计意图**: 5 个锚例本来就不足以做判决, "
        "v2 只是**不再假装能判**。真正的问题是「不判」之后怎么办 —— "
        "答案在 v2 预注册里: UNRESOLVED **留在 primary 面板**, 并追加独立锚例。"
        "而追加锚例这一步**当前受阻**(没有第二个模型家族可定真值)。\n"
        "⇒ 诚实的总结: **v2 把一个坏判决换成了一个诚实的空缺, 而空缺的填补还没有路。**")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "raw.json").write_text(json.dumps({"scores": scores}, ensure_ascii=False), encoding="utf-8")
    (ROOT / "tests/data/qualification_decision_consistency.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for m, r in rows.items():
        print(f"  {m:20s} 得分 {r['scores']}  v1={dict(r['v1_binary'])} "
              f"{'★翻转' if r['v1_flipped'] else '稳'}  v2={dict(r['v2_三态'])} "
              f"{'★翻转' if r['v2_flipped'] else '稳'}")
    print(json.dumps(res["★summary"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
