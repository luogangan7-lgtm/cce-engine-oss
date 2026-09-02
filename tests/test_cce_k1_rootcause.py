#!/usr/bin/env python3
"""K1 极差 0.40 的根因诊断结论, 以及它对判据本身的含义。

★ 这是**诊断不是判据**。全部跑在闸前 draw_ledger 上。
  不得把这里的任何量升级成 gate —— D_var 正是因「闸前算、闸后判」被否决的。
"""
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "tests", "data", "phase2")
V = json.load(open(os.path.join(P, "k1_rootcause_verdict.json"), encoding="utf-8"))
SPEC = json.load(open(os.path.join(P, "k1_rootcause_prereg.json"), encoding="utf-8"))
ROWS = [json.loads(l) for l in
        open(os.path.join(P, "k1_rootcause_checkpoint.jsonl"), encoding="utf-8") if l.strip()]


def arm(a):
    out = []
    for r in ROWS:
        if r["arm"] != a or not r.get("ledger"):
            continue
        g = [d for d in r["ledger"] if not d.get("infra") and d.get("knot_vector")]
        if g:
            out.append(g)
    return out


def med_nz(v):
    nz = [x for x in v if x > 0]
    return statistics.median(nz) if nz else 0.0


def rg(x):
    return round(max(x) - min(x), 4)


LIVE, FROZ = arm("LIVE"), arm("FROZEN_S1")

# ── 1. 采集规模与前登记一致 ────────────────────────────────────────────
assert len(LIVE) == len(FROZ) == 10 and V["reps"] == {"LIVE": 10, "FROZEN_S1": 10}
assert all(len(r) == 12 for r in LIVE + FROZ), "每 rep 必须 12 个可用 draw"
assert V["calls"] == 270 == SPEC["design"]["total_calls"]
assert V["instrument_diagnostic"] != V["instrument_production"], \
    "★ s2_n 5->12 就是换仪器, 两个哈希必须不同"

# ── 2. ★ 决定性分解可从原始行重算 ──────────────────────────────────────
KN = sorted(LIVE[0][0]["knot_vector"])
always = [k for k in KN if all(any(d["knot_vector"][k] > 0 for d in r) for r in LIVE)]
rare = [k for k in KN if k not in always]
assert set(always) == set(V["decisive_split"]["always_firing"]["knots"])
assert set(rare) == set(V["decisive_split"]["rarely_firing"]["knots"]) == {"reward", "inertia", "itch"}
assert len(always) == 6 and len(rare) == 3


def cv(k, reps):
    a = [med_nz([d["knot_vector"][k] for d in r]) for r in reps]
    m = statistics.fmean(a)
    return rg(a) / m if m else 0.0


cv_a = statistics.median([cv(k, LIVE) for k in always])
cv_r = statistics.median([cv(k, LIVE) for k in rare])
assert cv_r / cv_a > 10, \
    f"★ 核心发现: 不稳定集中在稀有结, 变异系数应差一个数量级, 实测 {cv_r/cv_a:.1f} 倍"
# 产物里的 cv 是逐结 round(...,3) 后再取中位数, 重算是未舍入的 —— 容差按舍入量级
assert abs(cv_a - V["decisive_split"]["always_firing"]["cv_median"]) < 1e-3

# ── 3. H1 的**分层**结论: 全局拒绝, 限常火结成立 ───────────────────────
ratios = []
for k in always:
    r5 = rg([med_nz([d["knot_vector"][k] for d in r[:5]]) for r in LIVE])
    r12 = rg([med_nz([d["knot_vector"][k] for d in r]) for r in LIVE])
    if r5:
        ratios.append(r12 / r5)
med_ratio = statistics.median(ratios)
assert V["hypotheses"]["H1_sampling_noise"]["global"]["verdict"] == "REJECTED"
assert V["hypotheses"]["H1_sampling_noise"]["global"]["ratio"] > 1.0, \
    "★ 全局上加大 n 让极差**变大** —— 这是拒绝 H1 的依据, 方向不能反"
h1r = V["hypotheses"]["H1_sampling_noise"]["restricted_to_always_firing"]
assert h1r["verdict"] == "SUPPORTED" and abs(h1r["ratio_median"] - med_ratio) < 1e-3
assert abs(med_ratio - 0.645) < 0.15, \
    f"★ 常火结上 n 效应应贴近纯抽样噪声预期 0.645, 实测 {med_ratio:.3f}"

# ── 4. H2 的自我更正必须留在产物里 ─────────────────────────────────────
h2 = V["hypotheses"]["H2_estimator_defect"]
assert h2["verdict"] == "REJECTED_AFTER_CORRECTION"
assert "恒定估计量" in h2["why"] and "尺度无关量" in h2["why"], \
    "★ 前登记 C2 的两个洞必须写明: 可被退化估计量满足 + 极差不是尺度无关量"
assert "不是原口径的结论" in h2["★self_correction"]

# 反向: 退化估计量确实能骗过原口径 —— 证明那个洞是真的
def median_all(v):
    return statistics.median(v)
deg = rg([median_all([d["knot_vector"]["reward"] for d in r]) for r in LIVE])
base = rg([med_nz([d["knot_vector"]["reward"] for d in r]) for r in LIVE])
assert deg == 0.0 and base > 0.3, \
    "★ median(含0) 把 reward 序列压成恒 0 ⇒ 原 C2 判决线确实可被退化估计量满足"

# ── 5. H3 明确反向 ─────────────────────────────────────────────────────
h3 = V["hypotheses"]["H3_s1_propagation"]
assert h3["verdict"] == "REJECTED" and h3["ratio_all"] > 1.0, \
    "★ 冻结 s1 后极差更大 —— 方向必须是「更差」, 不是「略好但没过线」"

# ── 6. H4 只在常火结上被排除, 不许说成全面排除 ─────────────────────────
h4 = V["hypotheses"]["H4_no_anchor"]
assert h4["verdict"] == "REJECTED_FOR_ALWAYS_FIRING_KNOTS"
assert "不覆盖稀有结" in h4["why"], "★ H4 的排除范围必须写明, 否则会被读成「尺度没问题」"

# ── 7. ★ 诊断不得推翻 K1 的 FAIL ───────────────────────────────────────
nf = V["★does_not_flip_k1"]
assert nf["verdict"] == "K1 仍然 FAIL"
worst = max(rg([v for r, v in zip(LIVE, [med_nz([d["knot_vector"][k] for d in r]) for r in LIVE])
                if any(d["knot_vector"][k] > 0 for d in r)]) for k in always)
assert worst > 0.10, \
    f"★ 剔除出现率成分后最大纯强度极差仍须 > 0.10(否则 K1 的 FAIL 就是判据假阳性), 实测 {worst}"
assert "两点外推" in nf["n_extrapolation"] and "不得当作承诺" in nf["n_extrapolation"]
# ★ n>=75 的口径已作废 —— 它是从被删掉的 R<=0.10 推出来的
assert "那个口径已作废" in nf["★n75_relabelled_2026_09_02"]
assert "量级级成本诊断" in nf["★n75_relabelled_2026_09_02"]
assert "已于 2026-09-02 冻结" in nf["new_cost_curve_protocol"], \
    "★ 新成本曲线的目标必须先冻结再测, 否则找到的 draw count 是事后拟合"
assert "诊断的**事实**全部仍然成立" in V["★superseded_criterion_note"]

# ── 8. 与已确立结论对齐, 不是另起一个根因 ──────────────────────────────
assert "support 闸二值化" in V["root_cause"] and "同一个根因" in V["root_cause"], \
    "★ 必须写明与 2026-08-18 已确立的 P1a 根因是同一个, 否则是在重复发现"
assert "既不是通解也不是错处方" in V["fix"]["partially_right"]

# ── 9. 诊断不是判据 —— 这条必须留在产物里 ──────────────────────────────
assert "不得把这里算出的任何量升级成 gate" in V["★not_a_gate"]
assert "D_var" in V["★not_a_gate"], "★ 必须点名 D_var 被否决的先例"
assert "不外推" in V["★scope"] and SPEC["design"]["experimental_unit"]["n_texts"] == 1

# ── 10. 进机制注册表, 且必须是 TESTED 不是 ESTABLISHED ────────────────
REG = json.load(open(os.path.join(ROOT, "config", "mechanism_registry.json"), encoding="utf-8"))
mech = {m["id"]: m for m in REG["mechanisms"]}.get("k1_range_is_occurrence_not_intensity")
assert mech, "★ 根因结论没进注册表 —— 那它只是一份没人查得到的实验产物"
assert mech["status"] == "TESTED" and mech["replications"] == [], \
    "★ 1 个文本、零复现 ⇒ 只能是 TESTED。标 ESTABLISHED 就是超出证据"
assert "1 个文本" in mech["note"] and "同一个根因" in mech["note"]
assert "不推翻" in mech["note"], "★ 必须写明它不推翻 K1 的 FAIL"
assert "不得升级为判据" in mech["downstream_enforcement"] and "D_var" in mech["downstream_enforcement"]
for ref in mech["evidence_refs"] + [mech["prereg_ref"]]:
    assert os.path.exists(os.path.join(ROOT, ref)), f"证据 {ref} 不存在"

# ── 11. ★ 出现率判据的跨批交叉检验 ────────────────────────────────────
#    2026-09-02 给 K1 补的第五项(出现率一致 >= 7/8)只在 K1 那一批上验过。
#    这里拿本轮两个独立臂再验: 若阈值是为某一批调的, 换批就会指向不同的结。
sys.path.insert(0, os.path.join(ROOT, "probes"))
from k1_gate import CRIT  # noqa: E402

def occ_agree(reps, k):
    fired = sum(1 for r in reps if any(d["knot_vector"][k] > 0 for d in r))
    return max(fired, len(reps) - fired) / len(reps) * 8, fired

for label, reps in (("LIVE", LIVE), ("FROZEN_S1", FROZ)):
    bad = sorted(k for k in KN
                 if occ_agree(reps, k)[1] > 0
                 and occ_agree(reps, k)[0] < CRIT["occurrence_agree_min"])
    assert set(bad) <= set(rare), \
        f"★ {label} 上出现率判据指向了常火结 {set(bad) - set(rare)} —— 判据在乱抓"
    assert "inertia" in bad, f"★ {label} 上 inertia 应当不达标"
# K1 那批(n=5 draw, 8 rep)最差也是 inertia —— 三批独立数据同一结论
K1V = json.load(open(os.path.join(P, "k1_reliability_verdict.json"), encoding="utf-8"))
assert min(K1V["occurrence"], key=lambda k: K1V["occurrence"][k]["agree"]) == "inertia", \
    "★ 三批独立数据必须指向同一组结, 否则阈值就是为某一批调的"

print(f"test_cce_k1_rootcause: OK "
      f"(20 rep x 12 draw 可重算 | 常火 {len(always)} 结 CV {cv_a:.2f} vs 稀有 {len(rare)} 结 "
      f"CV {cv_r:.2f} = {cv_r/cv_a:.0f} 倍 | H1 全局拒绝但限常火结成立 "
      f"({med_ratio:.3f} vs 理论 0.645) | H2/H3 拒绝 · H4 仅在常火结被排除 | "
      f"纯强度极差 {worst} 仍 > 0.10 ⇒ 不推翻 K1 的 FAIL | "
      "已登记为 TESTED 机制, 不得当判据 | "
      "出现率判据经三批独立数据交叉检验, 均指向 inertia)")
