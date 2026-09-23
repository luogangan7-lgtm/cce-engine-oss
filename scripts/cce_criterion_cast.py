#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★★★ 判据铸造器 —— 把「测不准的判据」铸成 **exact-binomial** 判据。零 API, 纯 stdlib。

## 与 scripts/cce_criterion_preflight.py 的分工(不要重复实现)
· preflight 回答「**这条判据裁得动吗**」—— 离散可达性 + 最优单侧 p, 发起前一票否决。
· 本工具回答「**那该用哪条**」—— 给定 (q_bad, q_good, α, β) 用**精确二项**铸出最小 n 与阈值 c,
  并把**现行**判据翻译成它**实际要求的 q**、算出它在实测底噪下的假阳/假阴。
  ⇒ preflight 是拦截器, cast 是铸模。两者共用「离散整数区间」这一个事实, 不共用代码路径。

## 三件必备能力(对应三个已实测的病灶)
① `equivalent_q(A)`  —— A = q² + (1−q)²/(k−1)。**A ≥ 0.95 ⟺ q ≥ 0.9743**(闭式 + 数值双算)。
   ⇒ 「逐对容差一致率 ≥ 0.95」不是一条宽松的工程线, 它在要求**单次重复的一致概率 97.4%**。
② `modal_bias(n, …)` —— 众数占比的期望。**众数是看完数据才挑的 ⇒ 天然向上偏**:
   纯 50/50 在 n=8 时 E[众数占比] = **0.6367**, 不是 0.5。
   ⇒ 一切在 n=8 下报出的「稳定性」都**结构性偏高**, 且众数占比是 **variation ratio 的补数**
     (名义离散度统计量), **不是** reliability coefficient —— 不要当 α/κ 读。
③ `noise_floor_pass_rate(p, n, c, arms)` —— 纯噪声下的**期望达标臂数**与**噪声带**。
   ⇒ 回答「4/8 → 6/8 这个计数之差, 落不落在噪声量级内」。

## ★ 边界(不可越)
本工具**只铸判据、只做影响分析**。它**不**替 owner 上调或下调任何生产判据。
**「噪声大」只说明判据测不准, 不说明结果该往有利方向读。**
判据冻结在先; 两个方向都得认 —— 不许拿噪声把 FAIL 读成 PASS, 也不许拿噪声把 PASS 读成 FAIL。
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import sys
from math import comb, factorial

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "tests" / "data" / "ablation_v3" / "criterion_cast.json"

# ── 实测常量(已在别处测得, 本工具只引用, 不重测) ─────────────────────────────
P_HAT_AA = 0.0048        # 底噪 A/A: n=30 × 8 臂 = 240 次, 20 个原子里 17 个完全确定
P_DISPLAY_FLIP = 1 / 16  # display 两轮 16 次重复中 1 次偏离 ⇒ 单次偏离率
Q_BAD, Q_GOOD = 0.70, 0.90   # 与 accuracy/run_gates.py:427 的 indifference region 同数
ALPHA, BETA = 0.05, 0.20


# ── 精确二项(不用正态近似, 不引 scipy) ──────────────────────────────────────
def binom_pmf(k: int, n: int, p: float) -> float:
    if k < 0 or k > n:
        return 0.0
    return comb(n, k) * p ** k * (1.0 - p) ** (n - k)


def binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k)"""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return math.fsum(binom_pmf(i, n, p) for i in range(k + 1))


def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) —— 注意是**含等号的上尾**, 不是 1-cdf(k)。"""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return math.fsum(binom_pmf(i, n, p) for i in range(k, n + 1))


def clopper_pearson(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """精确(Clopper-Pearson)区间 —— 用二分反解 exact tail, 不引 scipy.betaincinv。"""
    a = (1.0 - conf) / 2.0
    lo = 0.0 if k == 0 else _bisect(lambda q: binom_sf(k, n, q) - a, 0.0, 1.0)
    hi = 1.0 if k == n else _bisect(lambda q: binom_cdf(k, n, q) - a, 0.0, 1.0)
    return round(lo, 6), round(hi, 6)


def _bisect(f, lo: float, hi: float, tol: float = 1e-12, it: int = 200) -> float:
    flo = f(lo)
    for _ in range(it):
        mid = (lo + hi) / 2.0
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2.0


# ── ① 旧判据 → 它实际要求的 q ────────────────────────────────────────────────
def equivalent_q(A: float, categories: int = 2) -> dict:
    """「两次独立重复的一致率 >= A」实际要求的 q(主类别概率)。

    模型: 一个主类别概率 q, 其余 (k−1) 类均分 (1−q)。
      A(q) = q² + (1−q)²/(k−1)
    闭式: k·q² − 2q + (1 − A(k−1)) = 0  ⇒  q = [1 + √(1 − k + A·k·(k−1))] / k
    ★ 取**上根**(q > 1/k 的那支)。下根对应「主类别反而是少数」的镜像解, 无实际意义。
    """
    if categories < 2:
        raise ValueError("categories must be >= 2")
    k = categories
    disc = 1.0 - k + A * k * (k - 1)
    if disc < 0:
        return {"A": A, "categories": k, "attainable": False,
                "★": f"A={A} 低于该族的最小可达一致率 1/{k} ⇒ 无解"}
    q_closed = (1.0 + math.sqrt(disc)) / k

    def f(q):
        return q * q + (1.0 - q) ** 2 / (k - 1) - A

    q_num = _bisect(f, 1.0 / k, 1.0)
    return {"A": A, "categories": k, "attainable": True,
            "q_closed_form": q_closed, "q_numeric_bisection": q_num,
            "closed_vs_numeric_absdiff": abs(q_closed - q_num),
            "agreement_at_q": q_closed ** 2 + (1 - q_closed) ** 2 / (k - 1),
            "★读法": f"「一致率 >= {A}」实际等价于要求单次重复的主类别概率 q >= {q_closed:.4f}"}


# ── ② 众数占比的向上偏 ───────────────────────────────────────────────────────
def _compositions(n: int, k: int):
    if k == 1:
        yield (n,)
        return
    for i in range(n + 1):
        for rest in _compositions(n - i, k - 1):
            yield (i,) + rest


def modal_bias(n: int, probs=None, q: float = None, categories: int = 2,
               max_states: int = 2_000_000) -> dict:
    """众数占比在给定 n 下的**精确期望** —— 量化「看完数据才挑众数」的向上偏。

    ★ 众数占比 = variation ratio 的补数, 是**名义离散度**统计量, 不是 reliability coefficient。
    ★ 它对 argmax 后验挑选敏感 ⇒ 即使真分布完全均匀, 期望也 > 1/k。
    """
    if probs is None:
        if q is None:
            probs = [1.0 / categories] * categories
        else:
            k = categories
            probs = [q] + [(1.0 - q) / (k - 1)] * (k - 1)
    k = len(probs)
    if comb(n + k - 1, k - 1) > max_states:
        raise ValueError(f"状态数 {comb(n + k - 1, k - 1)} 超过 max_states —— 拒绝近似, 请缩小 n/k")
    fn = factorial(n)
    e_count = 0.0
    p_all_same = 0.0
    for c in _compositions(n, k):
        w = fn
        for x in c:
            w //= factorial(x)
        pr = w
        prob = float(pr)
        for x, p in zip(c, probs):
            prob *= p ** x
        m = max(c)
        e_count += prob * m
        if m == n:
            p_all_same += prob
    return {"n": n, "categories": k, "probs": [round(p, 6) for p in probs],
            "E_mode_count": e_count, "E_mode_share": e_count / n,
            "naive_floor_1_over_k": 1.0 / k,
            "upward_bias_vs_1_over_k": e_count / n - 1.0 / k,
            "P_all_same": p_all_same,
            "★读法": (f"n={n}、{k} 类时众数占比的期望是 {e_count / n:.4f}, "
                      f"而不是 {1.0 / k:.4f} —— 高出 {e_count / n - 1.0 / k:.4f} 全部来自"
                      f"「众数是看完数据才挑的」")}


# ── ③ 纯噪声下的达标臂数 ─────────────────────────────────────────────────────
def _modal_count_given_deviations(n: int, d: int, mode: str) -> int:
    """d 次偏离时的众数计数。
    scatter : 偏离各自散到不同类别 ⇒ 众数 = max(n−d, 1)   —— 9 结分类学的现实形态
    collapse: 偏离全落到同一个替代类别 ⇒ 众数 = max(n−d, d) —— 二值读数的最坏/最宽形态
    """
    if mode == "scatter":
        return max(n - d, 1)
    if mode == "collapse":
        return max(n - d, d)
    raise ValueError(mode)


def noise_floor_pass_rate(p: float, n: int, c: int, arms: int,
                          arms_min: int = None, mode: str = "scatter") -> dict:
    """纯噪声(单次偏离率 p)下: 单臂达标概率 · 期望达标臂数 · 达标臂数的 95% 噪声带。

    ★ 这是回答「4/8 → 6/8 这些计数之差落不落在噪声量级内」的那把尺子。
    ★ 它**不**说明该把阈值调到哪 —— 见模块 docstring 的边界。
    """
    per_arm = math.fsum(binom_pmf(d, n, p) for d in range(n + 1)
                        if _modal_count_given_deviations(n, d, mode) >= c)
    pmf = [binom_pmf(a, arms, per_arm) for a in range(arms + 1)]
    cum = 0.0
    lo = hi = None
    for a, pr in enumerate(pmf):
        cum += pr
        if lo is None and cum >= 0.025:
            lo = a
        if hi is None and cum >= 0.975:
            hi = a
    out = {"p_single_rep_deviation": p, "n": n, "c": c, "arms": arms, "mode": mode,
           "per_arm_pass_prob": per_arm,
           "per_arm_flip_prob": 1.0 - per_arm,
           "expected_arms_passing": arms * per_arm,
           "arms_passing_95_noise_band": [lo, hi],
           "pmf_arms_passing": [round(x, 6) for x in pmf]}
    if arms_min is not None:
        out["arms_min"] = arms_min
        out["P_criterion_passes_under_noise"] = binom_sf(arms_min, arms, per_arm)
    return out


# ── ④ 铸模: exact-binomial 最小 n 与阈值 c ───────────────────────────────────
def cast(q_bad: float = Q_BAD, q_good: float = Q_GOOD,
         alpha: float = ALPHA, beta: float = BETA, n_max: int = 600) -> dict:
    """给定 (q_bad, q_good, α, β), 精确二项求最小 n 与 PASS 阈值 c, 并报**实际达到**的 α/β。

    判据形状: X ~ Bin(n, q) 为「与众数/真值一致的重复数」, PASS ⟺ X >= c。
    · Type I  : P(X >= c | q = q_bad)  <= α
    · Type II : P(X <  c | q = q_good) <= β
    c 取满足 α 约束的**最小** c ⇒ 在该 n 下 β 最小(单调), 即 UMP 形式。
    """
    for n in range(1, n_max + 1):
        c = None
        for cc in range(0, n + 2):
            if binom_sf(cc, n, q_bad) <= alpha:
                c = cc
                break
        if c is None or c > n:
            continue
        b = binom_cdf(c - 1, n, q_good)
        if b <= beta:
            a = binom_sf(c, n, q_bad)
            return {"q_bad": q_bad, "q_good": q_good,
                    "alpha_target": alpha, "beta_target": beta,
                    "n": n, "c": c, "rule": f"PASS ⟺ modal >= {c}/{n}",
                    "alpha_achieved": a, "beta_achieved": b, "power_achieved": 1.0 - b,
                    "method": "exact binomial (no normal approximation)"}
    return {"q_bad": q_bad, "q_good": q_good, "alpha_target": alpha, "beta_target": beta,
            "n": None, "★": f"n_max={n_max} 内无解"}


def implied_q(n: int, c: int, power: float) -> float:
    """现行「modal >= c/n」判据: 要有 `power` 的把握通过, 实际需要的 q。

    ★ 用 scatter 模型 ⇒ 与众数一致的重复数就是 X ~ Bin(n, q), P(PASS) = P(X >= c)。
      这是判据**最有利**的读法; 真实众数占比还会被 argmax 后验挑选抬高(见 modal_bias)。
    """
    return _bisect(lambda q: binom_sf(c, n, q) - power, 0.0, 1.0)


def operating_chars(n: int, c: int, q_bad: float = Q_BAD, q_good: float = Q_GOOD) -> dict:
    """现行判据的操作特性: 在 q_bad / q_good / 实测底噪三点上的通过概率。"""
    return {"n": n, "c": c,
            "q_needed_for_50pct_pass": implied_q(n, c, 0.50),
            "q_needed_for_80pct_pass": implied_q(n, c, 0.80),
            "P_pass_at_q_bad": binom_sf(c, n, q_bad),
            "P_pass_at_q_good": binom_sf(c, n, q_good),
            "P_fail_at_q_good": binom_cdf(c - 1, n, q_good),
            "P_fail_at_AA_noise_floor": binom_cdf(c - 1, n, 1.0 - P_HAT_AA),
            "P_fail_at_display_flip_rate": binom_cdf(c - 1, n, 1.0 - P_DISPLAY_FLIP)}



def two_level(n: int, c: int, arms: int, q_bad: float = Q_BAD, q_good: float = Q_GOOD,
              alpha: float = ALPHA, beta: float = BETA) -> dict:
    """两层判据(「arms 个臂里 >= t 个达标」, 单臂 = 「modal >= c/n」)的 exact-binomial 铸模。

    ★ 两层都必须精确: 单臂通过概率在 q_bad/q_good 下各是一个数, 臂数再走一次二项。
      现行做法是**只**给第二层拍一个 7/8, 第一层的操作特性从未算过 —— 这就是测不准的来源。
    """
    pb = binom_sf(c, n, q_bad)
    pg = binom_sf(c, n, q_good)
    t_alpha = next((t for t in range(0, arms + 2) if binom_sf(t, arms, pb) <= alpha), None)
    rows = [{"t": t, "P_pass_at_q_bad": binom_sf(t, arms, pb),
             "P_pass_at_q_good": binom_sf(t, arms, pg)} for t in range(1, arms + 1)]
    ok = None
    if t_alpha is not None and t_alpha <= arms and binom_cdf(t_alpha - 1, arms, pg) <= beta:
        ok = t_alpha
    return {"per_arm_rule": f"modal >= {c}/{n}", "arms": arms,
            "per_arm_pass_at_q_bad": pb, "per_arm_pass_at_q_good": pg,
            "arms_threshold_meeting_alpha": t_alpha,
            "arms_threshold_meeting_both": ok,
            "★": (f"arms >= {ok}/{arms}" if ok is not None else
                  f"**{arms} 个臂不够** —— 在 α={alpha}, β={beta} 下无可行的臂数阈值; "
                  f"要么加臂, 要么把单臂 n 从 {n} 抬到 cast 给的 n"),
            "operating_curve": rows}


# ── 现行判据清单(全部 grep 自仓内; locus 为写入时的行号, 字面量由测试钉住) ──
CRITERIA = [
    dict(key="playbook_atomic_0.95_n8",
         text="playbook 原子判据: 8 个臂里 >=7 个达标; **单臂达标 = n=8 次重复全部同值**(0.95 线)",
         locus="tests/data/phase2/playbook_mode_prereg.json (criterion) + probes/k1_gate.py:75",
         shape="modal", n=8, c=8, arms=8, arms_min=7),
    dict(key="playbook_mode_share_7of8",
         text="playbook v2 预注册: 单文本 mode_share >= 0.875(7/8) @ n=8, 且 8 个文本里 >=7 个达标",
         locus="tests/data/phase2/playbook_mode_prereg.json:criterion.mode_share_min=0.875",
         shape="modal", n=8, c=7, arms=8, arms_min=7),
    dict(key="k1_pairwise_agreement_0.95",
         text="K1 ③: 稳定出现的结, 逐对容差一致率 A(0.10) >= 0.95 @ n=8",
         locus="probes/k1_gate.py:75 (CRIT['agreement_min']=0.95)",
         shape="pairwise_A", A=0.95, n=8, categories=(2, 9)),
    dict(key="k1_top1_agree_7of8",
         text="K1 ④: top-1 结一致率 >= 7/8 @ n=8",
         locus="probes/k1_gate.py:77 (CRIT['top1_agree_min']=7)",
         shape="modal", n=8, c=7, arms=1, arms_min=None),
    dict(key="k1_occurrence_agree_7of8",
         text="K1 ②: 每个结的出现率一致率 >= 7/8 @ n=8",
         locus="probes/k1_gate.py:84 (CRIT['occurrence_agree_min']=7)",
         shape="modal", n=8, c=7, arms=9, arms_min=9),
    dict(key="gk1_top2_hit_0.80",
         text="G-K1 主判之一: 核心面板两两对的 **平均 top2 命中 >= 0.80**",
         locus="accuracy/run_gates.py:658",
         shape="proportion", thr=0.80, n_items=73, n_pairs=6, observed=0.9042),
    dict(key="gk1_mean_JS_0.25",
         text="G-K1 主判之二: 核心面板两两对的 **平均 JS <= 0.25**",
         locus="accuracy/run_gates.py:658",
         shape="continuous", thr=0.25, observed=0.2321),
    dict(key="annotator_qual_v1_4of5",
         text="标注者资格考 v1: hits >= 4 / 5 判 qualified",
         locus="accuracy/run_gates.py:422",
         shape="modal", n=5, c=4, arms=1, arms_min=None),
    dict(key="annotator_qual_v2_wilson",
         text="标注者资格考 v2 三态: Wilson 95% 下界 >= 0.90 判 QUALIFIED; 上界 <= 0.70 判 DISQUALIFIED",
         locus="accuracy/run_gates.py:427 (QUAL_P_LOW, QUAL_P_HIGH = 0.70, 0.90)",
         shape="wilson", n=5, p_low=0.70, p_high=0.90),
    dict(key="gk2_rho_0.30",
         text="G-K2: Spearman rho >= 0.30 且 p < 0.05(已冻结不可判)",
         locus="accuracy/run_gates.py:751",
         shape="inferential"),
    dict(key="t2_control_c1_0.75",
         text="t2 空转对照 C1: 空转版胜率 >= 0.75 ⇒ t2 全部结论作废; <= 0.6 ⇒ 可信度提高",
         locus="accuracy/t2_control.py:98",
         shape="proportion_runtime_n", thr=0.75),
    dict(key="reply_need_reach_0.5",
         text="回帖闸: need 层触达率 >= 0.5",
         locus="scripts/reply_loop.py:144 · scripts/reply_batch.py:73",
         shape="continuous_boolgate", thr=0.5),
    dict(key="v4_layer_reproducible",
         text="v4 层可复现: top 一致 >= 0.7 且 mean JS <= 0.30 判「可复现」",
         locus="scripts/exp_v4_full_validation.py:741",
         shape="continuous_boolgate", thr=0.70),
]

# 字面量钉子: 测试据此断言仓内判据**一字未改**(改了 → 本表作废, 必须重铸)
LITERAL_PINS = {
    "probes/k1_gate.py": ['"agreement_min": 0.95', '"top1_agree_min": 7', '"occurrence_agree_min": 7'],
    "accuracy/run_gates.py": ["sum(t2s) / len(t2s) >= 0.8 and sum(jss) / len(jss) <= 0.25",
                              '"qualified": hits >= 4',
                              "QUAL_P_LOW, QUAL_P_HIGH = 0.70, 0.90",
                              "rho >= 0.3"],
    "accuracy/t2_control.py": ['S1["率"] >= 0.75'],
    "scripts/reply_loop.py": ['(layers["need_vec"]["触达率"] or 0) >= 0.5'],
    "scripts/exp_v4_full_validation.py": ["ta >= 0.7 and (js is not None and js <= 0.30)"],
    "tests/data/phase2/playbook_mode_prereg.json": ['"mode_share_min": 0.875',
                                                    '"texts_meeting_min": 7'],
}


def _row(spec: dict, suggested: dict) -> dict:
    """把一条现行判据过一遍: 实际要求的 q → 实测底噪下的假阳/假阴 → 建议的 exact-binomial 版本。"""
    r = {"key": spec["key"], "criterion_text": spec["text"], "locus": spec["locus"],
         "shape": spec["shape"]}
    s = spec["shape"]
    if s == "modal":
        n, c = spec["n"], spec["c"]
        oc = operating_chars(n, c)
        r["operating_chars"] = oc
        r["implied_q"] = (f"要 50% 把握通过需 q>={oc['q_needed_for_50pct_pass']:.4f}; "
                          f"要 80% 把握通过需 q>={oc['q_needed_for_80pct_pass']:.4f} "
                          f"(朴素读法 c/n={c/n:.3f} 严重低估)")
        nf_d = noise_floor_pass_rate(P_DISPLAY_FLIP, n, c, spec["arms"], spec.get("arms_min"))
        nf_a = noise_floor_pass_rate(P_HAT_AA, n, c, spec["arms"], spec.get("arms_min"))
        r["noise_floor"] = {"display_flip_1_16": nf_d, "AA_p_hat_0.0048": nf_a}
        tl = two_level(n, c, spec["arms"]) if spec.get("arms_min") else None
        if tl:
            r["two_level_cast"] = tl
            am = spec["arms_min"]
            r["two_level_current"] = {
                "current_rule": f"arms >= {am}/{spec['arms']}, 单臂 modal >= {c}/{n}",
                "P_whole_criterion_PASS_at_q_bad": binom_sf(am, spec["arms"], tl["per_arm_pass_at_q_bad"]),
                "P_whole_criterion_FAIL_at_q_good": binom_cdf(am - 1, spec["arms"], tl["per_arm_pass_at_q_good"])}
        r["false_pos_at_noise_floor"] = (
            f"P(单臂 PASS | q=0.70)={oc['P_pass_at_q_bad']:.4f}"
            + (f"; P(整条判据 PASS | 每臂 q=0.70)="
               f"{r['two_level_current']['P_whole_criterion_PASS_at_q_bad']:.4f}"
               f"; P(整条判据 PASS | 纯噪声单次偏离率 1/16)="
               f"{nf_d['P_criterion_passes_under_noise']:.4f}" if tl else ""))
        r["false_neg"] = (
            f"P(单臂 FAIL | q=0.90)={oc['P_fail_at_q_good']:.4f}; "
            f"P(单臂 FAIL | 实测 A/A 底噪 q=0.9952)={oc['P_fail_at_AA_noise_floor']:.4f}; "
            f"P(单臂 FAIL | display 单次偏离 1/16)={oc['P_fail_at_display_flip_rate']:.4f}"
            + (f"; P(整条判据 FAIL | 每臂 q=0.90)="
               f"{r['two_level_current']['P_whole_criterion_FAIL_at_q_good']:.4f}" if tl else ""))
        r["noise_band_on_arm_count"] = (
            f"单次偏离率 1/16 下, {spec['arms']} 个臂的达标数期望 "
            f"{nf_d['expected_arms_passing']:.2f}, 95% 噪声带 "
            f"{nf_d['arms_passing_95_noise_band']} ⇒ 该带内的计数之差**不可解读**")
        r["suggested_exact_binomial"] = (
            f"单臂 {suggested['rule']} (α_achieved={suggested['alpha_achieved']:.4f}, "
            f"β_achieved={suggested['beta_achieved']:.4f}, 区分 q<=0.70 与 q>=0.90)"
            + (f"; 两层: 在现行单臂规则 modal>={c}/{n} 下 {tl['★']}" if tl else ""))
    elif s == "pairwise_A":
        eq = {k: equivalent_q(spec["A"], k) for k in spec["categories"]}
        r["equivalent_q"] = eq
        r["implied_q"] = ("; ".join(f"k={k}: q>={v['q_closed_form']:.4f}" for k, v in eq.items())
                          + " —— 与 n=8 零容差线要求的 q 几乎同数, 不是一条宽松的工程线")
        oc = operating_chars(spec["n"], spec["n"])   # A>=0.95 @ n=8 离散后 = 8/8 全同
        r["operating_chars"] = oc
        nf_d = noise_floor_pass_rate(P_DISPLAY_FLIP, spec["n"], spec["n"], 1)
        r["noise_floor"] = {"display_flip_1_16": nf_d}
        r["false_pos_at_noise_floor"] = f"P(PASS | q=0.70)={oc['P_pass_at_q_bad']:.6f}"
        r["false_neg"] = (f"P(FAIL | q=0.90)={oc['P_fail_at_q_good']:.4f}; "
                          f"P(FAIL | display 单次偏离 1/16)={oc['P_fail_at_display_flip_rate']:.4f}")
        r["suggested_exact_binomial"] = (
            f"{suggested['rule']} —— 若坚持 0.95 的一致率语义, 请改写成对 q 的直陈"
            f"(q>={eq[2]['q_closed_form']:.4f}), 否则读者会把它当宽松线")
    elif s == "proportion":
        n_i, thr = spec["n_items"], spec["thr"]
        c = math.ceil(thr * n_i - 1e-12)
        oc = operating_chars(n_i, c)
        r["operating_chars"] = oc
        r["implied_q"] = (f"单对 n≈{n_i}: 阈值 {thr} 离散后 = {c}/{n_i}; "
                          f"要 80% 把握通过需 q>={oc['q_needed_for_80pct_pass']:.4f}")
        r["false_pos_at_noise_floor"] = (
            f"单对 P(PASS | q=0.70)={oc['P_pass_at_q_bad']:.6f} "
            f"(≈0 ⇒ 对「单对」而言这条线其实很有力)")
        r["false_neg"] = (f"单对 P(FAIL | q=0.90)={oc['P_fail_at_q_good']:.4f}; "
                          f"实测 {spec['observed']} ⇒ 余量 {spec['observed'] - thr:+.4f}")
        r["suggested_exact_binomial"] = (
            f"单对: {cast(Q_BAD, Q_GOOD, ALPHA, BETA)['rule']} 即可; "
            f"但**聚合层不可照搬** —— {spec['n_pairs']} 个对共享标注者与题目, "
            f"不是 {spec['n_pairs']}×{n_i} 个独立伯努利。聚合判据需 cluster bootstrap 或"
            f"按**标注者**重抽的置换检验, 有效 n 远小于 {spec['n_pairs'] * n_i}")
        r["★caveat"] = "非独立: 6 个两两对由 4 名标注者生成, 且逐题共享。exact binomial 只对**单对**成立。"
    elif s == "continuous":
        r["implied_q"] = "不适用 —— JS 是连续量, 没有「每次重复的成败」这个二项事件"
        r["false_pos_at_noise_floor"] = (
            "无二项解。**已有实测**: 自助重抽下越 0.25 线的概率 v1=7.3% → v2=35.5%, "
            "点估计余量 0.031→0.0078 ⇒ PASS 不是二值事实")
        r["false_neg"] = "无二项解; 同上, 由自助区间给出(v2 的 95%CI [0.1999, 0.2846] 已横跨 0.25)"
        r["suggested_exact_binomial"] = (
            "★ **不要铸成二项** —— 正确升级是把判据写成区间判据: "
            "「cluster bootstrap 95%CI **上界** <= 0.25」而不是「点估计 <= 0.25」。"
            "把现有的越线概率并列报告制度化。")
        r["★caveat"] = "在噪声连续量上设布尔闸, 与库内『全占比原则』直接冲突。"
    elif s == "wilson":
        n = spec["n"]
        r["implied_q"] = (f"n={n} 时 Wilson 下界 >= {spec['p_high']} 需全对且 n>=35 ⇒ "
                          f"CERTIFY 在 n=5 上**不可达**; DISQUALIFY 只需 k<=1")
        cp5 = {k: clopper_pearson(k, n) for k in range(n + 1)}
        r["clopper_pearson_n5"] = {str(k): v for k, v in cp5.items()}
        r["false_pos_at_noise_floor"] = "按设计不可能 CERTIFY ⇒ 假阳为 0; 代价全在 UNRESOLVED"
        r["false_neg"] = (f"P(DISQUALIFIED | q=0.90) = P(k<=1) = "
                          f"{binom_cdf(1, n, spec['p_high']):.6f} —— 很小, 方向正确")
        r["suggested_exact_binomial"] = (
            "★ 这一条**已经是对的形状**(三态 + 区间), 只建议把 Wilson 换成 Clopper-Pearson"
            f"(精确, 小 n 下不越界); 若要 CERTIFY 可达, 按 cast 需 n={suggested['n']}, "
            f"c={suggested['c']}")
    elif s == "inferential":
        r["implied_q"] = "不适用 —— 相关系数判据, 已自带 p 值"
        r["false_pos_at_noise_floor"] = "已由 p<0.05 控制(名义); 但 rho>=0.30 这一半是**效应量线**, 无检定力声明"
        r["false_neg"] = "未算 —— 需先声明 rho 的 indifference region(现无)"
        r["suggested_exact_binomial"] = ("不适用。建议补的是**检定力声明**: 给定 n 与目标 rho, "
                                         "报 1−β; 现状是「显著即通过」而没说它能测多小的效应")
    elif s == "proportion_runtime_n":
        r["implied_q"] = f"阈值 {spec['thr']}; n 由运行时 low 篇数决定 ⇒ **判据的操作特性随样本漂移**"
        r["false_pos_at_noise_floor"] = "无法计算 —— n 不在判据里, 这本身就是缺陷"
        r["false_neg"] = "同上"
        r["suggested_exact_binomial"] = (
            f"把 n 写进判据。若目标是区分 q<=0.6(无偏好) 与 q>=0.75(有偏好), "
            f"按 cast: {cast(0.60, 0.75, ALPHA, BETA)['rule']}")
    elif s == "continuous_boolgate":
        r["implied_q"] = "不适用 —— 连续量上的布尔闸"
        r["false_pos_at_noise_floor"] = "未测量 —— 该量的重测噪声从未估计过"
        r["false_neg"] = "未测量"
        r["suggested_exact_binomial"] = (
            "★ 先估这个连续量自己的重测噪声(A/A), 再决定它配不配有阈值。"
            "在没有噪声估计的连续量上设布尔闸 = 库内『全占比原则』点名的错误写法")
    return r


class _Tripwire:
    """★ R1 零 API: 加载期即装, 任何**新建 socket 连接**都是失败, 不是警告。
    作用域如实写: 只覆盖本进程内经 socket.socket.connect 新建的连接。"""

    def __enter__(self):
        import socket
        self._socket, self._orig, self.tripped = socket, socket.socket.connect, []
        tw = self

        def guard(sock, address, *a, **kw):
            tw.tripped.append(str(address))
            raise AssertionError(f"★★★ 离线隔离被突破: {address}")

        socket.socket.connect = guard
        return self

    def __exit__(self, *exc):
        self._socket.socket.connect = self._orig
        return False


def build(out_path: pathlib.Path = DEFAULT_OUT) -> dict:
    with _Tripwire() as _tw:
        doc = _build_inner(out_path, _tw)
    assert _tw.tripped == [], f"★★★ 离线隔离被突破: {_tw.tripped}"
    return doc


def _build_inner(out_path: pathlib.Path, tw) -> dict:
    suggested = cast(Q_BAD, Q_GOOD, ALPHA, BETA)
    rows = [_row(spec, suggested) for spec in CRITERIA]
    src_sha = {}
    for rel in sorted(LITERAL_PINS):
        p = ROOT / rel
        src_sha[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    doc = {
        "block": "CRITERION_CAST_V1",
        "generated_by": "scripts/cce_criterion_cast.py",
        "★边界(不可越)": (
            "本产物**只铸判据、只做影响分析**。**不**替 owner 上调或下调任何生产判据。"
            "★★★ **「噪声大」只说明判据测不准, 不说明结果该往有利方向读。** "
            "判据冻结在先, 两个方向都得认: 不许拿噪声把 FAIL 读成 PASS, 也不许拿噪声把 PASS 读成 FAIL。"),
        "★本产物不含任何仓外识别层路径": True,
        "★仓内被测文件一字未改": "见 sources_sha256; 消融只做内存内源码替换, 从不写回",
        "measured_inputs": {
            "p_hat_AA_240trials": P_HAT_AA,
            "p_display_single_rep_flip": P_DISPLAY_FLIP,
            "indifference_region": [Q_BAD, Q_GOOD],
            "alpha": ALPHA, "beta": BETA,
            "★这些数不是本轮测的": "引用自既有实测, 本工具零 API, 未重测"},
        "closed_form_checks": {
            "A>=0.95 ⟺ q>=?": equivalent_q(0.95, 2),
            "A>=0.95 ⟺ q>=? (9 结)": equivalent_q(0.95, 9),
            "modal_bias n=8 pure 50/50": modal_bias(8, probs=[0.5, 0.5]),
            "modal_bias n=8 uniform over 9 knots": modal_bias(8, categories=9),
            "modal_bias n=28 pure 50/50": modal_bias(28, probs=[0.5, 0.5]),
            "zero_tolerance_8of8_q_for_80pct": implied_q(8, 8, 0.80)},
        "cast_recommended": suggested,
        "cast_grid": {f"alpha={a},beta={b}": cast(Q_BAD, Q_GOOD, a, b)
                      for a, b in ((0.05, 0.20), (0.05, 0.10), (0.01, 0.20), (0.10, 0.20))},
        "noise_floor_headline": {
            "★单次偏离率 1/16 ⇒ 单臂(8/8 零容差)翻掉的概率":
                noise_floor_pass_rate(P_DISPLAY_FLIP, 8, 8, 8, 7)["per_arm_flip_prob"],
            "★纯噪声期望达标臂数(8 臂)":
                noise_floor_pass_rate(P_DISPLAY_FLIP, 8, 8, 8, 7)["expected_arms_passing"],
            "★达标臂数的 95% 噪声带":
                noise_floor_pass_rate(P_DISPLAY_FLIP, 8, 8, 8, 7)["arms_passing_95_noise_band"],
            "★读法": ("4/8 与 6/8 之差完全落在这条带内 ⇒ **这两个计数在当前判据下不可区分**。"
                      "这只是说判据测不准, **不是**说 6/8 该被读成通过。")},
        "criteria_table": rows,
        "★零API证据": {
            "绊线": "socket.socket.connect 在生成期即被替换为抛错的 guard",
            "绊线是否被触发": tw.tripped,
            "★作用域(如实写, 不夸大)": ("只覆盖本进程内**经 socket.socket.connect 新建**的连接。"
                                         "不覆盖: 已建立连接 · 不走 socket 的传输 · 子进程 · C 扩展自带网络栈。"),
            "★本工具不 import 任何被测生产模块": "纯 stdlib 数学; 判据字面量由 LITERAL_PINS 在测试里钉住"},
        "★反向测试": {
            "位置": "tests/test_cce_criterion_cast.py",
            "机制": "内存内源码字符串替换后 exec, 每个变异断言恰好命中一次, exec 前后比对 sha256",
            "已证见红(6/6)": [
                "equivalent_q 取下根 ⇒ A>=0.95 的 0.974 交叉验证变红",
                "modal_bias 用均值替众数 ⇒ n=8 的 0.6367 退化到 0.5, 变红",
                "cast 改正态近似 ⇒ 铸出 (n,c)=(29,25) 而非 (28,24), 变红",
                "binom_sf 差一(含等号上尾写成严格大于) ⇒ 铸出 (1,1), 变红",
                "noise_floor 丢掉臂这一层 ⇒ 期望达标臂数 4.8 变红",
                "modal_bias 丢掉多项式系数 ⇒ 期望 0.0273, 变红"]},
        "★与已知值的交叉验证": {
            "A>=0.95 ⟺ q>=0.974": {"已知": 0.974,
                                    "本工具独立算出": round(equivalent_q(0.95, 2)["q_closed_form"], 6)},
            "n=8 纯 50/50 的 E[众数占比]=0.6367": {"已知": 0.6367,
                                                   "本工具独立算出": round(modal_bias(8, probs=[0.5, 0.5])["E_mode_share"], 6)},
            "exact binomial @ q .70/.90, α.05 β.20 ⇒ n=28, modal>=24": {
                "已知": "n=28, c=24",
                "本工具独立算出": f"n={suggested['n']}, c={suggested['c']}"},
            "单次偏离 1/16 ⇒ 单臂翻掉 ≈40%": {
                "已知": "约 40%",
                "本工具独立算出": round(noise_floor_pass_rate(P_DISPLAY_FLIP, 8, 8, 8)["per_arm_flip_prob"], 4)},
            "纯噪声期望达标臂数 ≈4.8/8": {
                "已知": 4.8,
                "本工具独立算出": round(noise_floor_pass_rate(P_DISPLAY_FLIP, 8, 8, 8)["expected_arms_passing"], 3)}},
        "sources_sha256": src_sha,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


def main() -> int:
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    doc = build(out)
    s = doc["cast_recommended"]
    print("=" * 78)
    print("判据铸造器 —— exact binomial (零 API)")
    print("=" * 78)
    e = doc["closed_form_checks"]["A>=0.95 ⟺ q>=?"]
    print(f"  A>=0.95  ⟺ q >= {e['q_closed_form']:.6f}  (闭式 vs 数值差 {e['closed_vs_numeric_absdiff']:.2e})")
    m = doc["closed_form_checks"]["modal_bias n=8 pure 50/50"]
    print(f"  n=8 纯 50/50 的 E[众数占比] = {m['E_mode_share']:.6f}  (向上偏 +{m['upward_bias_vs_1_over_k']:.4f})")
    print(f"  铸出: {s['rule']}  α={s['alpha_achieved']:.4f} β={s['beta_achieved']:.4f}")
    h = doc["noise_floor_headline"]
    print(f"  纯噪声(1/16): 单臂翻掉 {h['★单次偏离率 1/16 ⇒ 单臂(8/8 零容差)翻掉的概率']:.4f} · "
          f"期望达标 {h['★纯噪声期望达标臂数(8 臂)']:.3f}/8 · 95% 带 {h['★达标臂数的 95% 噪声带']}")
    print("-" * 78)
    for r in doc["criteria_table"]:
        print(f"  [{r['key']}] {r['locus']}")
        print(f"     实际要求: {r['implied_q']}")
        print(f"     假阳    : {r['false_pos_at_noise_floor']}")
        print(f"     假阴    : {r['false_neg']}")
        print(f"     建议    : {r['suggested_exact_binomial']}")
    print("-" * 78)
    print(doc["★边界(不可越)"])
    print(f"写出: {DEFAULT_OUT if len(sys.argv) <= 1 else out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
