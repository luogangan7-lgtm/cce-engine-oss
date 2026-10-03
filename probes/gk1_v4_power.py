#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G-K1 v4 设计与功效估算(零调用)。★ v3 数据只用于功效估算, 不用于定阈值、不进 v4 判定。

读 v3 四个有效 occasion(3/4/5/6, archive/ 下的原始结果文件, sha 钉在 tests/data/gk1_v3_result.json 的 inputs),
只取 P4 四人, 回答: k 次采样平均能把面板分歧 D(k) 与各模型自身噪声 W(k) 压到多少, 以及在预算内哪个 (k, N, R)
在「真实分歧 = D(k)」情形下有合理判出概率。

  D(k)  = k 个 occasion 的分布逐格平均后再算 P4 面板 μ_D; 对 {3,4,5,6} 的全部 k 元子集取平均(k=1..4 都是真实独立样本的平均)
  W(k)  = 同一模型同一条目两份**不相交**的 k 平均之间的 JS(k=1: 6 个 occasion 对; k=2: 3 个完美配对)
  方差分量 = 格值 d_ir 的两因素随机效应矩估计(条目 σ²_I · occasion σ²_O · 残差 σ²_E);
          k=1 用 81×4, k=2 用 3 个完美配对各 81×2(不相交 ⇒ 真独立)再平均; k≥3 无不相交样本, 按 1/k 外推(标明外推)
  功效  = 按方差分量造合成 d_ir 矩阵(正态), 跑与分析器同式的「条目 × occasion」交叉自助, 数 PASS/UNRESOLVED/FAIL
用法: .venv/bin/python probes/gk1_v4_power.py   → 写 tests/data/gk1_v4_power.json
"""
import hashlib, itertools, json, math, pathlib, sys
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
from accuracy_gk1_v3_analyze import js_div   # noqa: E402  (与 run_gates.js_div 同式, v3 守卫逐值比对过)

OUT = ROOT / "tests/data/gk1_v4_power.json"
V3_FILES = {3: "archive/37092420336/probe-out__tmp__gk1_v3_occ3_result.json",
            4: "archive/37094215372/probe-out__tmp__gk1_v3_occ4_result.json",
            5: "archive/37095859396/probe-out__tmp__gk1_v3_occ5_result.json",
            6: "archive/37097348068/probe-out__tmp__gk1_v3_occ6_result.json"}
P4 = ["MiniMax-M3", "MiniMax-M2.5", "MiniMax-M2.7", "MiniMax-M2"]
THR, SEED, SIMS, B_SIM = 0.25, 20261004, 400, 2000
CANDIDATES = [  # (k, N, R): 每 occasion 计划调用 = 4 × N × k
    (1, 81, 4), (2, 81, 4), (2, 64, 4), (3, 54, 4), (4, 40, 4), (2, 108, 3)]
CHOSEN = (3, 54, 4)
STUDY_CAP, DISPATCH_CAP, SLACK = 3500, 900, 0.08   # 研究总上限 / 单次派发上限 / 重试余量(v3 新运维设置下 4 次 0 重试)


def budget(k, n, r, models=4):
    """每 occasion 一次派发; 上限 = 计划 + 8% 余量; 研究上限 = (R + 1 个替补) × 单次上限。"""
    plan = models * n * k
    cap = plan + math.ceil(SLACK * plan)
    return {"models": models, "per_dispatch_planned": plan, "per_dispatch_cap": cap, "study_planned": plan * r,
            "study_ceiling_with_1_replacement": cap * (r + 1),
            "fits": cap <= DISPATCH_CAP and cap * (r + 1) <= STUDY_CAP}


def avg(ds):
    ds = [d for d in ds if d]
    if not ds:
        return None
    keys = set().union(*ds)
    return {k: sum(d.get(k, 0.0) for d in ds) / len(ds) for k in keys}


def load_v3():
    pinned = {x["file"]: x["sha256"] for x in json.loads((ROOT / "tests/data/gk1_v3_result.json").read_text())["inputs"]}
    occ = {}
    for k, rel in V3_FILES.items():
        p = ROOT / rel
        want = pinned["gk1_v3_occ%d_result.json" % k]
        if hashlib.sha256(p.read_bytes()).hexdigest() != want:
            raise SystemExit("★ v3 occasion %d 原始文件与 gk1_v3_result.json 记录的 sha 不符 —— 拒算" % k)
        occ[k] = json.loads(p.read_text(encoding="utf-8"))
    ids = occ[3]["item_ids"]
    assert all(o["item_ids"] == ids for o in occ.values())
    return occ, ids


def panel_cells(dists_by_model, ids):
    """dists_by_model[m][i] -> 每条目的 P4 面板 d_i(两两 JS 平均; 只计两人都有分布的对)。"""
    out = []
    for i in ids:
        v = [js_div(dists_by_model[a][i], dists_by_model[b][i]) for a, b in itertools.combinations(P4, 2)
             if dists_by_model[a][i] and dists_by_model[b][i]]
        out.append(sum(v) / len(v) if v else None)
    return out


def kavg(occ, subset, ids):
    return {m: {i: avg([occ[s]["dists"][m].get(i) for s in subset]) for i in ids} for m in P4}


def var_components(mat):
    """N × R 完整矩阵的两因素随机效应矩估计(无重复)。"""
    a = np.array(mat, dtype=float)
    n, r = a.shape
    g, rm, cm = a.mean(), a.mean(1), a.mean(0)
    ms_r = r * ((rm - g) ** 2).sum() / (n - 1)
    ms_c = n * ((cm - g) ** 2).sum() / (r - 1)
    ms_e = ((a - rm[:, None] - cm[None, :] + g) ** 2).sum() / ((n - 1) * (r - 1))
    return {"item": max(0.0, (ms_r - ms_e) / r), "occasion": max(0.0, (ms_c - ms_e) / n), "resid": ms_e}


def crossed_bounds(mat, rng, B):
    """与分析器同式的交叉自助(先抽 occasion 再抽条目), 返回 (L, U) = 第 5% / 95% 分位。"""
    n, r = mat.shape
    rr = rng.integers(0, r, size=(B, r))
    cnt = np.stack([(rr == j).sum(1) for j in range(r)], 1)            # B × R
    ii = rng.integers(0, n, size=(B, n))
    rowsum = mat @ cnt.T                                                 # N × B
    xs = np.sort(np.take_along_axis(rowsum.T, ii, 1).sum(1) / (n * r))
    return xs[int(0.05 * B)], xs[int(0.95 * B) - 1]


def simulate(mu, vc, n, r, rng, sims=SIMS, B=B_SIM):
    out = {"PASS": 0, "UNRESOLVED": 0, "FAIL": 0}
    us = []
    for _ in range(sims):
        mat = (mu + rng.normal(0, math.sqrt(vc["item"]), (n, 1)) + rng.normal(0, math.sqrt(vc["occasion"]), (1, r))
               + rng.normal(0, math.sqrt(vc["resid"]), (n, r)))
        L, U = crossed_bounds(mat, rng, B)
        out["PASS" if U <= THR else "FAIL" if L > THR else "UNRESOLVED"] += 1
        us.append(U - mat.mean())
    return {k: v / sims for k, v in out.items()} | {"mean_U_minus_muhat": float(np.mean(us))}


def main():
    occ, ids = load_v3()
    O = sorted(occ)
    # D(k): 全部 k 元子集
    D, top2 = {}, {}
    for k in range(1, 5):
        vals = []
        for S in itertools.combinations(O, k):
            c = [x for x in panel_cells(kavg(occ, S, ids), ids) if x is not None]
            vals.append(sum(c) / len(c))
        D[k] = sum(vals) / len(vals)
    # W(k): 不相交 k 平均
    W = {1: {}, 2: {}}
    pairs1 = [((a,), (b,)) for a, b in itertools.combinations(O, 2)]
    pairs2 = [((O[0], O[1]), (O[2], O[3])), ((O[0], O[2]), (O[1], O[3])), ((O[0], O[3]), (O[1], O[2]))]
    for k, prs in ((1, pairs1), (2, pairs2)):
        for m in P4:
            v = []
            for S, T in prs:
                for i in ids:
                    p, q = avg([occ[s]["dists"][m].get(i) for s in S]), avg([occ[s]["dists"][m].get(i) for s in T])
                    if p and q:
                        v.append(js_div(p, q))
            W[k][m] = sum(v) / len(v)
    Wbar = {k: sum(W[k].values()) / 4 for k in W}
    # 方差分量
    m1 = [list(col) for col in zip(*[panel_cells(kavg(occ, (s,), ids), ids) for s in O])]
    vc1 = var_components(m1)
    vc2s = []
    for S, T in pairs2:
        m2 = [list(col) for col in zip(panel_cells(kavg(occ, S, ids), ids), panel_cells(kavg(occ, T, ids), ids))]
        vc2s.append(var_components(m2))
    vc2 = {f: sum(v[f] for v in vc2s) / 3 for f in vc1}
    vc = {1: vc1, 2: vc2}
    for k in (3, 4):   # ★ 外推: 残差按 1/k(以 k=2 为锚), 条目与 occasion 分量取 k=2 的值(不再缩, 偏保守)
        vc[k] = {"item": vc2["item"], "occasion": vc2["occasion"], "resid": vc2["resid"] * 2 / k, "★extrapolated": True}
    # 1/k 模型拟合 D(k) = X + c/k (最小二乘, k=1..4)
    ks = np.array([1, 2, 3, 4.0])
    A = np.stack([np.ones(4), 1 / ks], 1)
    X, c = np.linalg.lstsq(A, np.array([D[k] for k in range(1, 5)]), rcond=None)[0]
    rng = np.random.default_rng(SEED)
    # 校准: 用 k=1 方差分量模拟 v3 自身设计(N=81, R=4), 看模拟的 U − μ̂ 是否接近 v3 实测 0.2923 − 0.2548 = 0.0375
    v3_res = json.loads((ROOT / "tests/data/gk1_v3_result.json").read_text())["P4_primary"]
    calib = simulate(D[1], vc1, 81, 4, rng)
    cand = []
    for k, n, r in CANDIDATES:
        row = {"k": k, "N": n, "R": r, "budget_P4": budget(k, n, r), "mu_assumed_D_k": D[k],
               "at_mu_D_k": simulate(D[k], vc[k], n, r, rng)}
        if k >= 2:   # ★ 情形: 同一 occasion 内 k 次采样两两相关 ρ ⇒ 等效独立次数 k/(1+(k−1)ρ); μ 按拟合曲线 X + c/k_eff
            row["within_occasion_dependence"] = {
                "rho=%.2f" % rho: {"mu": float(X + c * (1 + (k - 1) * rho) / k),
                                   **simulate(float(X + c * (1 + (k - 1) * rho) / k), vc[k], n, r, rng, sims=300)}
                for rho in (0.25, 0.5)}
        cand.append(row)
    p5_cost = budget(CHOSEN[0], CHOSEN[1], CHOSEN[2], models=5)
    # 选定设计在一串 μ 上的判出曲线(含 0.25 附近: 判不出是该区间的本性)
    chosen = CHOSEN
    curve = {"%.2f" % mu: simulate(mu, vc[chosen[0]], chosen[1], chosen[2], rng, sims=300)
             for mu in (0.17, 0.19, 0.20, 0.21, 0.22, 0.23, 0.24, 0.26, 0.28, 0.30)}
    out = {"block": "GK1_V4_POWER", "★zero_api": True,
           "★v3_data_use": "只用于功效估算(k、N、R 的选择与预期判出概率)。不用于定阈值(0.25 是 2026-08-07 冻结的既有常数)、不进 v4 判定; v4 用全新条目。",
           "v3_inputs": V3_FILES, "panel": P4,
           "D_k_empirical": {str(k): D[k] for k in D},
           "D_k_fit_X_plus_c_over_k": {"X_k_to_inf": float(X), "c": float(c),
                                       "fitted": {str(k): float(X + c / k) for k in range(1, 5)},
                                       "note": "X 是 k→∞ 外推(模型假设: 运行噪声对平方型距离按 1/k 衰减); 只描述, 不进判定"},
           "W_k_self": {"1": W[1], "2": W[2], "mean_1": Wbar[1], "mean_2": Wbar[2],
                        "ratio_2_over_1": Wbar[2] / Wbar[1],
                        "note": "W(2)/W(1) = %.3f > 1/2 ⇒ JS 不按 1/k 衰减; v3 只有 4 个样本, k>=3 的不相交 W 测不到 —— 不外推" % (Wbar[2] / Wbar[1])},
           "variance_components": {str(k): v for k, v in vc.items()},
           "calibration_k1_v3_design": {"simulated": calib,
                                        "v3_observed_U_minus_mu": v3_res["mu_D_U95_one_sided"] - v3_res["mu_D"],
                                        "v3_observed_verdict": v3_res["verdict"]},
           "candidates": cand, "chosen": {"k": chosen[0], "N": chosen[1], "R": chosen[2], "budget": budget(*chosen)},
           "text01_arm_cost_at_chosen": p5_cost,
           "chosen_power_curve_by_true_mu": curve,
           "sim": {"seed": SEED, "sims": SIMS, "B": B_SIM, "model": "d_ir = μ + a_i + b_r + e_ir, 正态, 方差分量见上"}}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"D_k": out["D_k_empirical"], "W": {"1": Wbar[1], "2": Wbar[2]}, "vc": out["variance_components"],
                      "calib": out["calibration_k1_v3_design"],
                      "cand": [(r["k"], r["N"], r["R"], r["budget_P4"], round(r["mu_assumed_D_k"], 4), r["at_mu_D_k"],
                                r.get("within_occasion_dependence")) for r in cand], "p5": p5_cost,
                      "curve": curve}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
