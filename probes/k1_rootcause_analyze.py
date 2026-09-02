#!/usr/bin/env python3
"""K1 根因诊断的分析 —— 0 次调用, 全部跑在闸前 draw_ledger 上。

判决线在 tests/data/phase2/k1_rootcause_prereg.json 里, **跑前已冻结**;
本脚本只是执行它, 不新增任何阈值。

★ 诊断不是判据。不得把这里的任何量升级成 gate(D_var 就是这么被否决的)。
"""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "tests" / "data" / "phase2"
SPEC = json.loads((P / "k1_rootcause_prereg.json").read_text(encoding="utf-8"))
DR = SPEC["decision_rule"]
PRIMARY = DR["primary_knot"].split()[0]


# ── 四个估计量。生产用的是 median_nz。 ────────────────────────────────
def median_nz(v):
    nz = [x for x in v if x > 0]
    return statistics.median(nz) if nz else 0.0


def mean_nz(v):
    nz = [x for x in v if x > 0]
    return statistics.fmean(nz) if nz else 0.0


def mean_all(v):
    return statistics.fmean(v) if v else 0.0


def median_all(v):
    return statistics.median(v) if v else 0.0


ESTIMATORS = {"median_nz(生产)": median_nz, "mean_nz": mean_nz,
              "mean_all(含0)": mean_all, "median_all(含0)": median_all}


def load():
    rows = [json.loads(l) for l in (P / "k1_rootcause_checkpoint.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()]
    out = {"LIVE": [], "FROZEN_S1": []}
    for r in rows:
        led = r.get("ledger")
        if not led:
            continue
        good = [d for d in led if not d.get("infra") and d.get("knot_vector") is not None]
        if good:
            out[r["arm"]].append({"rep": r["rep"], "draws": good})
    return out


def series(reps, knot, est, n=None):
    """每个 rep 一个聚合值。n 给定则只取前 n 个 draw —— 严格复现该 n 的轮转分配。"""
    vals = []
    for r in reps:
        ds = r["draws"][:n] if n else r["draws"]
        vals.append(est([d["knot_vector"][knot] for d in ds]))
    return vals


def rng(xs):
    return round(max(xs) - min(xs), 4) if xs else 0.0


def main() -> int:
    data = load()
    n_live, n_froz = len(data["LIVE"]), len(data["FROZEN_S1"])
    n2 = SPEC["design"]["arms"][0]["s2_n"]
    print("=" * 74)
    print("K1 单结极差的根因诊断 —— 闸前 draw_ledger, 0 次新增调用")
    print("=" * 74)
    print(f"LIVE {n_live} rep · FROZEN_S1 {n_froz} rep · 每 rep {n2} draw · 主判据结 = {PRIMARY}")
    print(f"实验单元 = 1 个文本 ({SPEC['design']['text']['base_id']}) —— 结论不外推到其他文本\n")

    live, froz = data["LIVE"], data["FROZEN_S1"]
    R12 = rng(series(live, PRIMARY, median_nz))
    R5 = rng(series(live, PRIMARY, median_nz, n=5))
    print(f"── C1 n 效应 (LIVE, median_nz) ──")
    print(f"   n=5  前缀 R_between = {R5}   ← 严格复现生产的轮转分配")
    print(f"   n={n2} 全量 R_between = {R12}")
    c1_ratio = round(R12 / R5, 3) if R5 else float("inf")
    c1 = c1_ratio <= 0.75
    print(f"   比值 {c1_ratio}  vs 判决线 <= 0.75  ⇒ H1(抽样噪声) {'有支持 ✅' if c1 else '不支持 ❌'}")
    if R5:
        print(f"   (纯零均值抽样噪声的预期比值 ≈ sqrt(5/{n2}) = {round((5/n2)**.5,3)})")

    print(f"\n── C2 估计量效应 (LIVE, n={n2}) ──")
    base = R12
    est_r = {}
    for name, f in ESTIMATORS.items():
        est_r[name] = rng(series(live, PRIMARY, f))
        print(f"   {name:<18} R_between = {est_r[name]}")
    # ★ 2026-09-01 事后加的退化守卫 —— **前登记时漏了这条, 如实标注为事后修正**。
    #   C2 原判决线「最优替代估计量的 R_between <= 0.65 x 基准」可被一个**恒定**估计量满足:
    #   它把整条序列压成常数, 极差按构造为 0。那不是改进, 是把信号删掉。
    #   库里的元教训正是「统计量退化 -> 返回有利数」, 我这次又踩了一次。
    #   守卫: 替代估计量必须在**该结实际点火的 rep 上**仍保留非零变异, 否则判为 DEGENERATE。
    def _degenerate(f, knot):
        vals = series(live, knot, f)
        fired = [v for r, v in zip(live, vals)
                 if any(d["knot_vector"][knot] > 0 for d in r["draws"])]
        return (not fired) or (max(fired) == min(fired) == 0.0) or (rng(vals) == 0.0)

    alts = {k: v for k, v in est_r.items()
            if not k.startswith("median_nz") and not _degenerate(ESTIMATORS[k], PRIMARY)}
    degenerate = [k for k in est_r if not k.startswith("median_nz")
                  and _degenerate(ESTIMATORS[k], PRIMARY)]
    if degenerate:
        print(f"   ⚠️ 退化估计量(极差按构造为 0, 不算改进): {degenerate}")
    best_name = min(alts, key=alts.get) if alts else None
    c2_ratio = round(alts[best_name] / base, 3) if best_name and base else float("inf")
    if best_name is None:
        print("   所有替代估计量都退化 ⇒ C2 无有效候选")
    c2 = c2_ratio <= 0.65
    print(f"   最优替代 {best_name} 比值 {c2_ratio} vs 判决线 <= 0.65 ⇒ "
          f"H2(估计量缺陷) {'有支持 ✅' if c2 else '不支持 ❌'}")

    print(f"\n── C3 s1 传播效应 (n={n2}, median_nz) ──")
    Rf = rng(series(froz, PRIMARY, median_nz))
    print(f"   LIVE      R_between = {R12}")
    print(f"   FROZEN_S1 R_between = {Rf}")
    c3_ratio = round(Rf / R12, 3) if R12 else float("inf")
    c3 = c3_ratio <= 0.65
    print(f"   比值 {c3_ratio}  vs 判决线 <= 0.65  ⇒ H3(s1 传播) {'有支持 ✅' if c3 else '不支持 ❌'}")

    knots = sorted(live[0]["draws"][0]["knot_vector"])
    print(f"\n── occur 与 rep 间极差 (LIVE, n={n2}, median_nz) ──")
    print(f"   {'结':<12} {'occur中位':>9} {'R_between':>10} {'sigma_within':>13} {'sigma_between':>14} {'过散比':>8}")
    occ_r = []
    var_rows = {}
    for k in knots:
        occs, withins, aggs = [], [], []
        for r in live:
            v = [d["knot_vector"][k] for d in r["draws"]]
            nz = [x for x in v if x > 0]
            occs.append(len(nz))
            if len(nz) >= 2:
                withins.append(statistics.pvariance(nz))
            aggs.append(median_nz(v))
        if max(occs) == 0:
            continue                      # 全程未点火的结: 信度未被测量, 不参与
        med_occ = statistics.median(occs)
        Rk = rng(aggs)
        sw = (statistics.fmean(withins) ** 0.5) if withins else 0.0
        sb = statistics.pstdev(aggs) if len(aggs) > 1 else 0.0
        # 过散比: 观测到的 rep 间方差 / 「纯抽样噪声」预期的 rep 间方差(sigma2_within / 有效n)
        n_eff = max(1.0, med_occ)
        expected_sb2 = (sw ** 2) / n_eff if sw else 0.0
        od = round((sb ** 2) / expected_sb2, 2) if expected_sb2 > 0 else None
        print(f"   {k:<12} {med_occ:>9.1f} {Rk:>10.3f} {sw:>13.3f} {sb:>14.3f} "
              f"{(str(od) if od is not None else '—'):>8}")
        occ_r.append((med_occ, Rk))
        var_rows[k] = {"median_occur": med_occ, "R_between": Rk,
                       "sigma_within": round(sw, 4), "sigma_between": round(sb, 4),
                       "overdispersion": od}
    if len(occ_r) >= 3:
        xs = [a for a, _ in occ_r]; ys = [b for _, b in occ_r]
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        num = sum((a-mx)*(b-my) for a, b in occ_r)
        den = (sum((a-mx)**2 for a in xs) * sum((b-my)**2 for b in ys)) ** 0.5
        r_pearson = round(num/den, 3) if den else None
        print(f"\n   occur 中位数 与 R_between 的相关: r = {r_pearson}  "
              f"(H2 预测强负相关)")
    else:
        r_pearson = None

    print(f"\n── ★ 决定性分解: 极差里有多少是「出现/缺席」造成的 ──")
    print(f"   把每个结的 rep 间极差拆成两块:")
    print(f"     R_all   = 全部 {n_live} 个 rep 的极差 (缺席 rep 记 0.0 —— 生产口径)")
    print(f"     R_fired = **只在该结真的点火的 rep 上**算极差 (纯强度变异)")
    print(f"   {'结':<12} {'点火rep':>8} {'R_all':>8} {'R_fired':>9} {'出现率驱动占比':>14}")
    split = {}
    for k in knots:
        aggs, fired_vals = [], []
        for r in live:
            v = [d["knot_vector"][k] for d in r["draws"]]
            a = median_nz(v)
            aggs.append(a)
            if any(x > 0 for x in v):
                fired_vals.append(a)
        if not fired_vals:
            continue
        Rall, Rf2 = rng(aggs), rng(fired_vals)
        share = round(1 - Rf2 / Rall, 3) if Rall > 0 else None
        print(f"   {k:<12} {len(fired_vals):>8} {Rall:>8.3f} {Rf2:>9.3f} "
              f"{(f'{share:.0%}' if share is not None else '—'):>14}")
        split[k] = {"reps_fired": len(fired_vals), "R_all": Rall, "R_fired": Rf2,
                    "occurrence_driven_share": share}
    shares = [v["occurrence_driven_share"] for v in split.values()
              if v["occurrence_driven_share"] is not None]
    med_share = round(statistics.median(shares), 3) if shares else None
    print(f"\n   出现率驱动占比中位数 = {med_share}")
    print(f"   主判据结 {PRIMARY}: R_all={split.get(PRIMARY,{}).get('R_all')} -> "
          f"R_fired={split.get(PRIMARY,{}).get('R_fired')}")

    ods = [v["overdispersion"] for v in var_rows.values() if v["overdispersion"] is not None]
    med_od = round(statistics.median(ods), 2) if ods else None
    print(f"\n── 方差分解小结 ──")
    print(f"   过散比中位数 = {med_od}   (=1 表示 rep 间变动**恰好**是抽样噪声所能解释的量;")
    print(f"                            >>1 表示存在抽样噪声解释不了的 rep 级成分)")

    c4 = not (c1 or c2 or c3)
    print("\n" + "=" * 74)
    print("判决 (判决线跑前已冻结, 本脚本只执行不新增)")
    print("=" * 74)
    for name, ok, note in (
        ("H1 抽样噪声 —— 加大 n 能解决", c1, f"n 效应比值 {c1_ratio} (线 <=0.75)"),
        ("H2 估计量缺陷 —— median(非零) 的分母是随机的", c2, f"最优替代 {best_name} 比值 {c2_ratio} (线 <=0.65)"),
        ("H3 s1 传播 —— 上游抽样带进来的", c3, f"冻结 s1 比值 {c3_ratio} (线 <=0.65)"),
    ):
        print(f"  {'✅ 有支持' if ok else '❌ 不支持'}  {name}")
        print(f"              {note}")
    print(f"  {'★ 剩余解释' if c4 else '  (未触发)'}  H4 评分尺度无锚点")
    if c4:
        print("              前三个假设的预测全部落空 ⇒ H4 是剩余解释。")
        print("              注意: 这是**其他三个被证伪**, 不是 H4 被直接证实。")

    verdict = {
      "block": "K1_ROOT_CAUSE_VARIANCE_STRUCTURE", "measured_at": "2026-09-01",
      "prereg": "tests/data/phase2/k1_rootcause_prereg.json",
      "raw_rows": "tests/data/phase2/k1_rootcause_checkpoint.jsonl",
      "instrument_diagnostic": SPEC["design"]["instrument"]["diagnostic_n12"],
      "instrument_production": SPEC["design"]["instrument"]["production_n5"],
      "n_reps": {"LIVE": n_live, "FROZEN_S1": n_froz}, "s2_n": n2,
      "primary_knot": PRIMARY,
      "C1_n_effect": {"R_n5": R5, "R_n12": R12, "ratio": c1_ratio,
                      "threshold": 0.75, "supported": c1,
                      "pure_noise_expectation": round((5/n2)**0.5, 3)},
      "C2_estimator_effect": {"by_estimator": est_r, "best_alt": best_name,
                              "ratio": c2_ratio, "threshold": 0.65, "supported": c2},
      "C3_s1_effect": {"R_live": R12, "R_frozen": Rf, "ratio": c3_ratio,
                       "threshold": 0.65, "supported": c3},
      "C4_residual_H4_no_anchor": c4,
      "per_knot": var_rows,
      "occurrence_vs_intensity_split": split,
      "occurrence_driven_share_median": med_share,
      "degenerate_estimators": degenerate,
      "★c2_guard_was_post_hoc": ("退化守卫是**事后**加的 —— 前登记的 C2 判决线可被恒定估计量满足。"
                                 "如实标注: C2 的结论按加了守卫之后的口径给, 不是原前登记口径。"),
      "occur_range_correlation": r_pearson,
      "overdispersion_median": med_od,
      "★not_a_gate": SPEC["★_what_this_is_not"]["not_a_gate"],
      "★scope": SPEC["design"]["experimental_unit"]["★scope"],
    }
    (P / "k1_rootcause_verdict.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n产物: tests/data/phase2/k1_rootcause_verdict.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
