#!/usr/bin/env python3
"""A_j(0.10) 成本曲线的结论 —— 0 次新增调用, 全部可从既有 draw_ledger 重算。

★ 判据阈值(δ=0.10, A>=0.95)在 commit f2b52ba 冻结, **早于本测量**。
  外部裁决明确要求目标先冻结再测, 否则找到的 draw count 是事后拟合。
"""
import itertools
import json
import math
import os
import statistics
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
from k1_gate import CRIT  # noqa: E402

P = os.path.join(ROOT, "tests", "data", "phase2")
V = json.load(open(os.path.join(P, "k1_cost_curve_verdict.json"), encoding="utf-8"))
SPEC = json.load(open(os.path.join(P, "k1_cost_curve_prereg.json"), encoding="utf-8"))

# ── 1. 0 次新增调用 ────────────────────────────────────────────────────
assert V["new_calls"] == 0, "★ 整条曲线必须是 0 调用算出的"

# ── 2. ★ 目标先冻结, 再测量 —— 用 git 证明, 不是自称 ───────────────────
fz = SPEC["★target_frozen_before_measurement"]
assert fz["criterion"] == {"delta": CRIT["tolerance_delta"],
                           "agreement_min": CRIT["agreement_min"]}
cm = fz["frozen_in_commit"]
assert subprocess.run(["git", "cat-file", "-e", cm], cwd=ROOT,
                      capture_output=True).returncode == 0, f"冻结 commit {cm} 不存在"
src = subprocess.run(["git", "show", f"{cm}:probes/k1_gate.py"], cwd=ROOT,
                     capture_output=True, text=True).stdout
assert '"agreement_min": 0.95' in src and '"tolerance_delta": 0.10' in src, \
    f"★ {cm} 里没有这两个阈值 —— 「先冻结」这句话就是假的"
assert not os.path.exists(os.path.join(P, "k1_cost_curve_verdict.json")) or \
    subprocess.run(["git", "show", f"{cm}:tests/data/phase2/k1_cost_curve_verdict.json"],
                   cwd=ROOT, capture_output=True).returncode != 0, \
    "★ 冻结那个 commit 里不该已经有曲线产物 —— 有就说明先测后冻"

# ── 3. 前缀有效性: 不是近似, 是严格复现 ────────────────────────────────
rows = [json.loads(l) for l in
        open(os.path.join(P, "k1_rootcause_checkpoint.jsonl"), encoding="utf-8") if l.strip()]
reps = [[d for d in r["ledger"] if not d.get("infra") and d.get("knot_vector")]
        for r in rows if r["arm"] == "LIVE" and r.get("ledger")]
assert len(reps) == 10 and all(len(r) == 12 for r in reps)
for r in reps:
    assert all(d["prompt_idx"] == d["draw_id"] % 3 for d in r), \
        "★ 轮转不是 i%3 ⇒ 前缀不再严格复现 n-draw 运行, 整条曲线作废"

# ── 4. 曲线可从原始 ledger 重算 ────────────────────────────────────────
def med_nz(x):
    nz = [y for y in x if y > 0]
    return statistics.median(nz) if nz else None

def A(sub, k, n):
    f = [y for y in (med_nz([d["knot_vector"][k] for d in r[:n]]) for r in sub) if y is not None]
    if len(f) < 2:
        return None
    pr = list(itertools.combinations(f, 2))
    return sum(1 for a, b in pr if abs(a - b) <= CRIT["tolerance_delta"]) / len(pr)

by_n = {row["n"]: row for row in V["curve"]}
KN = sorted(reps[0][0]["knot_vector"])
m_need = math.ceil(CRIT["occurrence_agree_min"] / 8 * len(reps))
for n, row in by_n.items():
    live = {k: A(reps, k, n) for k in KN
            if len([1 for r in reps
                    if med_nz([d["knot_vector"][k] for d in r[:n]]) is not None]) >= m_need}
    assert len(live) == row["eligible"], f"n={n} 合格结数对不上"
    assert abs(min(live.values()) - row["min_A"]) < 1e-3, f"n={n} min A_j 重算对不上"

# ── 5. ★ 落入前登记的哪一支, 必须是前登记里写过的 ──────────────────────
assert V["branch"] in SPEC["★branches"], "★ 落点必须落在前登记写过的分支里"
assert V["branch"] == "B4_noisy"
assert len(SPEC["★branches"]) >= 6, \
    "★ 前登记必须覆盖全部方向(达标/上升/平坦/非单调/下降) —— 上次就是漏了实际落点那一支"
for must in ("B1_reached", "B2_climbing", "B3_flat", "B4_noisy", "B5_declining"):
    assert must in SPEC["★branches"]

# ── 6. 合格集变化的混杂已被分离 ────────────────────────────────────────
fs = V["fixed_eligible_set_sensitivity"]
assert "不是前登记口径" in fs["★label"], "★ 事后分析必须如实标注"
assert fs["still_non_monotone"] is True
assert by_n[2]["eligible"] == 4 and by_n[12]["eligible"] == 6, \
    "★ 合格集确实随 n 变过 —— 这正是要分离它的理由"
seq = [fs["per_n"][str(n)]["suspend"] for n in range(2, 13)]
assert not all(b >= a for a, b in zip(seq, seq[1:])), \
    "★ 固定集下 suspend 应当非单调; 若变单调说明重算口径漂了"

# ── 7. 精度: 不得套二项 SE ─────────────────────────────────────────────
pr = V["precision"]
assert "不得套二项" in pr["method"] and "jackknife" in pr["method"]
assert abs(pr["jackknife_se_mean"] - 0.085) < 0.01
assert pr["curve_max_jitter"] > pr["jackknife_se_mean"], \
    "★ 抖动必须与 SE 同量级或更大, 否则「起伏是噪声」这个结论不成立"
assert "不是标定" in pr["★caveat"]

# ── 8. ★ 能firmly说的和说不出的, 必须分开 ──────────────────────────────
f = V["★what_can_be_said_firmly"]
assert "12 个 draw 明确不够" in f["n12_is_insufficient"]
assert by_n[12]["min_A"] < CRIT["agreement_min"] and by_n[12]["loo_max"] < CRIT["agreement_min"], \
    "★ 连留一最好情况都够不到 0.95, 「n=12 不够」才是稳的"
assert V["n_star"] is None and "说不出 n" in f["no_n_star"], \
    "★ 说不出 n* 就必须写「说不出」, 不许从噪声里拟合一个数"

# ── 9. 建议不花钱 + 理由必须包含「不外推」 ─────────────────────────────
rec = V["★recommendation"]
assert rec["spend"] == "不建议"
assert "不外推" in rec["why"] and "1 个文本" in rec["why"], \
    "★ 不花钱的核心理由是 scope, 不是省钱"
assert "先扩文本再扩 rep" in rec["if_owner_wants_it_anyway"]

print(f"test_cce_k1_cost_curve: OK "
      f"(0 调用 · 阈值冻结早于测量有 git 证据 · 前缀严格复现 · 曲线可重算 · "
      f"落入前登记的 B4_noisy · 合格集混杂已分离且仍非单调 · "
      f"jackknife SE {pr['jackknife_se_mean']} 与抖动 {pr['curve_max_jitter']} 同量级 ⇒ "
      f"起伏是噪声 · n=12 明确不够但说不出 n*)")
