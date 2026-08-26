#!/usr/bin/env python3
"""投料前的设计硬门 —— 不过则**禁止产生任何 API job**。

## 为什么存在
2026-08-26 owner 批评:「你这总是调用, 不是错这里就是错那里在这里瞎猜」。属实。
三轮长度相关实验, **每轮都是跑完才发现设计缺陷**, 而其中两处纸面上就能算出来:
  · 第一轮: 填充按 base 成比例加 ⇒ 长度与占比同时变(混杂)
  · 第二轮: total=base+pad 且 share=base/total ⇒ 四个变量只有 **2 个自由度**
外审判定: 这两处「理论上都应该在 **0 次 API 调用阶段被 CI 拒绝**」。
本文件就是那道拒绝。

## 六个 Gate(Gate1/2 是结构性的, 不能被 Gate3 的数值检查替代)
1 代数依赖      声明的 estimand 是否在数学上就不可分辨
2 孤立对比      每个 estimand 是否存在「目标变、所有 nuisance 不变」的计划对比
3 设计矩阵秩    rank / condition number / VIF
4 支撑与正性    各因素在其它因素的不同取值范围内是否都有支持
5 实验单位审计  禁止把同一单位的重复测量当独立 replicate(pseudoreplication)
6 合成结局反测  ★ 用已知真值造 outcome, 看计划中的分析能否还原
"""
import itertools, json, math, sys
from collections import Counter

HARD_COND = 100.0     # 工程阈值(非文献常数): 条件数 >100 硬失败, 30-100 警告
WARN_COND = 30.0
HARD_VIF = 10.0
MIN_SUPPORT_POINTS = 12


def _rank_and_cond(cols):
    """对列做 Gram-Schmidt 求秩 + 幂迭代估条件数。零依赖。"""
    n = len(cols[0])
    basis, rank = [], 0
    for c in cols:
        v = list(c)
        for b in basis:
            d = sum(x * y for x, y in zip(v, b))
            v = [x - d * y for x, y in zip(v, b)]
        nv = math.sqrt(sum(x * x for x in v))
        if nv > 1e-9:
            basis.append([x / nv for x in v])
            rank += 1
    # 条件数: 用 X^T X 的幂迭代取最大/最小特征值
    p = len(cols)
    G = [[sum(cols[i][k] * cols[j][k] for k in range(n)) for j in range(p)] for i in range(p)]
    def power(M, inv=False):
        v = [1.0] * p
        for _ in range(300):
            w = [sum(M[i][j] * v[j] for j in range(p)) for i in range(p)]
            nw = math.sqrt(sum(x * x for x in w)) or 1e-12
            v = [x / nw for x in w]
        return sum(v[i] * sum(M[i][j] * v[j] for j in range(p)) for i in range(p))
    lmax = power(G)
    sh = [[G[i][j] - (lmax + 1e-9) * (i == j) for j in range(p)] for i in range(p)]
    lmin = lmax + power(sh)
    cond = math.sqrt(abs(lmax / lmin)) if abs(lmin) > 1e-12 else float("inf")
    return rank, cond


def gate1_algebraic(variables, estimands, fails):
    """★ 结构性不可分辨: 声明的 derived 变量之间存在代数恒等式时, 自由度会塌陷。

    实例(我的 2x2): total = base + pad 且 share = base/total
    ⇒ base = total*share, pad = total*(1-share) ⇒ 四者只有 2 个自由度。
    """
    prim = set(variables.get("primitive", []))
    der = variables.get("derived", {})           # name -> 依赖的 primitive 列表
    want = [e for e in estimands if e.get("independent", True)]
    dof = len(prim)
    if len(want) > dof:
        fails.append({"gate": 1, "code": "FAIL_STRUCTURAL_NONIDENTIFIABILITY",
                      "detail": f"声明要独立估 {len(want)} 个 estimand "
                                f"({[e['name'] for e in want]}), 但自由变量只有 {dof} 个 "
                                f"({sorted(prim)}); derived={list(der)} 由它们代数决定"})
    return dof


def gate2_isolated_contrast(design, estimands, fails):
    """每个 primary estimand 必须存在一个**孤立对比**: 目标变、所有 nuisance 不变。

    实例(我的第一轮): 目标是 total_length, 但 pad↑ 时 total↑ 且 share↓ 同时发生
    ⇒ 不存在孤立对比 ⇒ NOT_IDENTIFIABLE_BY_DESIGN。
    """
    for e in estimands:
        tgt, nui = e["target"], e.get("nuisance", [])
        found = False
        for a, b in itertools.combinations(design, 2):
            if a[tgt] != b[tgt] and all(abs(a[k] - b[k]) < 1e-9 for k in nui):
                found = True
                break
        if not found:
            fails.append({"gate": 2, "code": "NOT_IDENTIFIABLE_BY_DESIGN",
                          "detail": f"estimand «{e['name']}»: 找不到「{tgt} 变而 {nui} 全不变」"
                                    f"的计划对比 —— 投料后靠回归救不回来"})


def gate3_rank(design, formula_terms, fails, warns):
    cols = [[1.0] * len(design)] + [[float(d[t]) for d in design] for t in formula_terms]
    # Belsley 条件指数按**列归一化**后计算: 否则单纯的量纲差异(base~1e3 vs 截距 1)
    # 会被误读成共线性。归一化不改变秩, 只剥掉尺度。
    scaled = []
    for c in cols:
        n = sum(v * v for v in c) ** 0.5
        if n == 0.0:          # 恒零列 = 该因素在设计里根本没变化
            scaled.append(c)
        else:
            scaled.append([v / n for v in c])
    rank, cond = _rank_and_cond(scaled)
    if rank < len(cols):
        fails.append({"gate": 3, "code": "FAIL_RANK_DEFICIENT",
                      "detail": f"设计矩阵秩 {rank} < 列数 {len(cols)} ⇒ 效应彼此 alias, 无法分别估"})
    if cond > HARD_COND:
        fails.append({"gate": 3, "code": "FAIL_ILL_CONDITIONED",
                      "detail": f"条件数 {cond:.1f} > {HARD_COND}"})
    elif cond > WARN_COND:
        warns.append(f"[gate3] 条件数 {cond:.1f} 在 {WARN_COND}-{HARD_COND} 之间")
    return rank, cond


def gate4_support(design, formula_terms, fails, warns):
    pts = {tuple(round(d[t], 6) for t in formula_terms) for d in design}
    if len(pts) < MIN_SUPPORT_POINTS:
        fails.append({"gate": 4, "code": "FAIL_INSUFFICIENT_SUPPORT",
                      "detail": f"唯一设计点仅 {len(pts)} < {MIN_SUPPORT_POINTS} ⇒ "
                                f"系数几乎由少数角点决定, 属局部平面拟合"})
    # 正性: 每个因素在另一因素的高/低半区都要有取值
    for i, t in enumerate(formula_terms):
        for j, o in enumerate(formula_terms):
            if i == j:
                continue
            med = sorted(d[o] for d in design)[len(design) // 2]
            lo = {d[t] for d in design if d[o] <= med}
            hi = {d[t] for d in design if d[o] > med}
            if not lo or not hi or len(lo) < 2 or len(hi) < 2:
                warns.append(f"[gate4] {t} 在 {o} 的高/低半区支持不足 "
                             f"(低区 {len(lo)} 个取值, 高区 {len(hi)} 个)")
    return len(pts)


def gate5_unit_audit(n_raw, n_units, claimed_n, fails):
    """★ 禁止把同一实验单位的重复测量当独立 replicate(pseudoreplication)。"""
    if claimed_n > n_units:
        fails.append({"gate": 5, "code": "FAIL_PSEUDOREPLICATION",
                      "detail": f"推断 n 声明为 {claimed_n}, 但独立实验单位只有 {n_units} 个"
                                f"(原始观测 {n_raw})。同一单位的重复测量不是新的独立单位; "
                                f"标准误会被低估 ⇒ 必须按 cluster 处理或把 n 降到 {n_units}"})


def gate6_synthetic(design, formula_terms, fit_fn, fails, seedworlds=None):
    """★ 外审最推荐写进 CI 的一条: 用**已知真值**造 outcome, 看计划中的分析能否还原。

    连已知答案都还原不出的分析, 不该用来分析真实数据。
    """
    worlds = seedworlds or [
        ("only_" + formula_terms[0], {formula_terms[0]: -2.0}),
        ("only_" + formula_terms[1], {formula_terms[1]: +2.0}),
    ]
    for name, truth in worlds:
        zs = {t: [d[t] for d in design] for t in formula_terms}
        mu = {t: sum(v) / len(v) for t, v in zs.items()}
        sd = {t: (sum((x - mu[t]) ** 2 for x in v) / len(v)) ** .5 or 1.0 for t, v in zs.items()}
        y = []
        for d in design:
            z = sum(truth.get(t, 0.0) * (d[t] - mu[t]) / sd[t] for t in formula_terms)
            y.append(1.0 / (1 + math.exp(-max(-30, min(30, z)))))
        est = fit_fn(design, formula_terms, y)
        for t in formula_terms:
            want, got = truth.get(t, 0.0), est.get(t, 0.0)
            if want == 0.0 and abs(got) > 0.5:
                fails.append({"gate": 6, "code": "FAIL_SYNTHETIC_FALSE_POSITIVE",
                              "detail": f"世界«{name}»里 {t} 真值为 0, 计划分析却估出 {got:+.2f}"})
            if want != 0.0 and (got == 0 or want * got < 0):
                fails.append({"gate": 6, "code": "FAIL_SYNTHETIC_SIGN",
                              "detail": f"世界«{name}»里 {t} 真值 {want:+.1f}, 计划分析估出 {got:+.2f}"})


def logistic_fit(design, terms, y):
    """计划中的分析: 标准化 logistic。作为 gate6 的被测对象。"""
    zs = {t: [d[t] for d in design] for t in terms}
    mu = {t: sum(v) / len(v) for t, v in zs.items()}
    sd = {t: (sum((x - mu[t]) ** 2 for x in v) / len(v)) ** .5 or 1.0 for t, v in zs.items()}
    X = [[(d[t] - mu[t]) / sd[t] for t in terms] for d in design]
    w = [0.0] * (len(terms) + 1)
    for _ in range(6000):
        g = [0.0] * len(w)
        for i, xi in enumerate(X):
            z = w[0] + sum(w[j + 1] * xi[j] for j in range(len(terms)))
            p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            e = p - y[i]
            g[0] += e
            for j in range(len(terms)):
                g[j + 1] += e * xi[j]
        for j in range(len(w)):
            w[j] -= 0.5 * g[j] / len(X)
    return {t: w[i + 1] for i, t in enumerate(terms)}


def preflight(spec):
    fails, warns = [], []
    design, V, E = spec["design"], spec["variables"], spec["estimands"]
    terms = spec["analysis_formula"]["terms"]
    dof = gate1_algebraic(V, E, fails)
    gate2_isolated_contrast(design, E, fails)
    rank, cond = gate3_rank(design, terms, fails, warns)
    pts = gate4_support(design, terms, fails, warns)
    gate5_unit_audit(spec["n_raw_observations"], spec["n_experimental_units"],
                     spec["claimed_inferential_n"], fails)
    gate6_synthetic(design, terms, logistic_fit, fails)
    return {"pass": not fails, "fails": fails, "warns": warns,
            "report": {"free_dof": dof, "design_matrix_rank": rank,
                       "condition_number": round(cond, 2), "unique_support_points": pts,
                       "n_raw": spec["n_raw_observations"],
                       "n_units": spec["n_experimental_units"],
                       "claimed_n": spec["claimed_inferential_n"]}}


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    r = preflight(spec)
    print(json.dumps(r["report"], ensure_ascii=False, indent=1))
    for w in r["warns"]:
        print("  WARN ", w)
    for f in r["fails"]:
        print(f"  FAIL  [gate{f['gate']}] {f['code']}: {f['detail']}")
    print(("PASS —— 允许产生 API job" if r["pass"] else
           "★ FAIL —— **禁止产生任何 API job**"))
    sys.exit(0 if r["pass"] else 1)
