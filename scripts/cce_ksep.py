#!/usr/bin/env python3
"""KSEP —— 九结读数的两个判据: 可复现性(单文本) 与 可分离性(两文本)。

为什么要有它: 原判据 D = 文本间变动/重跑间变动 在 2026-08-18 实测中退化
(核心结取交集得空集 -> 0/0 -> inf, 而判决线写着 "D>=2 通过")。
中间提案 PSI = (B-W)/(B+W) 也被证伪 —— 它测的是**组内离散度不对称度**, 不是分离度:
两份文本的期望读数逐结完全相同、仅一侧 rep 间抖动更大时 PSI 恒 > 0, 解析上限 1/3。

三条设计原则(全部是被证伪的提案换来的):

1. **判据跑在闸后读数上** —— 那是生产真正发出去的东西。
   闸前算、闸后判是另一个被证伪提案(D_var)的死法: 闸后逐字节相同的两份文本它给 0.9988 PASS。
   闸前 per_knot 只做诊断, 不进判决。

2. **位置检验, 不是离散度比值。** 均值向量的 L1/9 距离 + 精确置换。
   离散度不对称只进置换零分布 —— 正确地**降低功效**, 而不是伪造效应。

3. **PASS 分支结构上不可达, 除非外部标定常数 min_effect 就位。**
   `min_effect=None` 时 verdict 只能是 UNCALIBRATED。那个常数只能由等长阳性对照实测标定,
   现在没有 —— 所以 PASS 分支现在是空的。这是诚实, 不是保守。

★ 元规则(第五次教训): **写完任何守卫, 必须构造一个它应该抓住的输入, 确认它真的触发。**
  测不出失败的检查等于装饰。本模块每条守卫在 tests/test_cce_ksep.py 里都有反向测试。
"""
import itertools
from collections import Counter

KNOTS = ("pain_seek", "injustice", "belong", "reward", "display",
         "itch", "suspend", "inertia", "audit")


def _check(reps, fingerprints, name):
    """退化输入一律抛错。绝不返回一个能被读成通过的数。"""
    if len(reps) != len(fingerprints):
        raise ValueError(f"{name}: readings 与 fingerprints 长度不等")
    if len(reps) < 4:
        raise ValueError(f"{name}: R={len(reps)} < 4, 精确置换的 p 下限过粗")
    dup = [k for k, v in Counter(fingerprints).items() if v > 1]
    if dup:
        # 缓存伪影会让"完美重测"变成假象。查响应指纹, 不查 W 的下限 ——
        # 后者在真实干净仪器上就会触发(实测 T0 的 9 槽平均 rep 间距离 0.0111)。
        raise ValueError(f"{name}: 重复响应指纹 {dup} —— 疑似缓存, 本次重测无效")
    if all(not r for r in reps):
        raise ValueError(f"{name}: 全部读数为空 —— 与管线整体失败不可区分")
    for r in reps:
        for k, v in r.items():
            if k not in KNOTS:
                raise ValueError(f"{name}: 未知结 {k!r}")
            if not (0.0 < v <= 1.0):
                raise ValueError(f"{name}: {k}={v} 越界, 闸后读数应在 (0,1]")


def _vec(r):
    return [r.get(k, 0.0) for k in KNOTS]


def _meanvec(reps):
    return [sum(col) / len(reps) for col in zip(*map(_vec, reps))]


def _T(a, b):
    return sum(abs(x - y) for x, y in zip(_meanvec(a), _meanvec(b))) / len(KNOTS)


def reproducibility(reps, fingerprints, name="text", intensity_tol=0.05):
    """单文本内部性质: 不需要真值、不需要对照、不受长度混杂影响。

    intensity_tol 是本模块仅有的两个旋钮之一(另一个是 min_effect)。
    0.05 约等于实测主导结噪声(0.02-0.04)的 1.5 倍。这是拍的, 明说。
    """
    _check(reps, fingerprints, name)
    R = len(reps)
    sets = [frozenset(r) for r in reps]
    pairs = list(itertools.combinations(range(R), 2))
    agreement = sum(sets[i] == sets[j] for i, j in pairs) / len(pairs)
    flipping = {k: sum(k in s for s in sets) for k in KNOTS
                if 0 < sum(k in s for s in sets) < R}
    ranges = {k: max(r[k] for r in reps) - min(r[k] for r in reps)
              for k in KNOTS if all(k in r for r in reps)}
    worst = max(ranges.values()) if ranges else None
    if flipping:
        verdict = "UNSTABLE_MEMBERSHIP"
    elif worst is None:
        # ★ 可达性证明: flipping 为空 => 每个结要么在所有 rep 出现要么一个都不出现;
        # 若无结在所有 rep 出现 => 所有 rep 皆空 => 已被 _check 的"全部读数为空"拦掉。
        # 因此**本分支不可达**。保留它只是 _check 被改动时的兜底 ——
        # 它没有反向测试, 不算已验证的守卫, 不要把它当作一层保护来引用。
        raise ValueError(f"{name}: 无恒定出现的结, 可复现性无定义(不是通过)")
    elif worst > intensity_tol:
        verdict = "UNSTABLE_INTENSITY"
    else:
        verdict = "REPRODUCIBLE"
    return {"verdict": verdict, "R": R, "set_agreement": agreement,
            "flipping": flipping, "stable_ranges": ranges, "worst_range": worst,
            "intensity_tol": intensity_tol}


# ─────────────────────────────────────────────────────────────────────────────
# min_effect 的**第一个经验锚**。2026-08-18, oss run 32141330271,
# probes/equal_length_control.py, 64 次调用, 仪器 57ec6cf478d3875e。
#
# 设计: T_a=语料天然最短(293字) vs T_b=index10 截至词边界(289字), Jaccard 0.075(最不像的一对)。
# 结果: 观测 T=0.07389, **排名 35/35(置换零分布里最大)**, p=1/35=0.0286。
#       等长条件下仪器分得开 ⇒ **它读的是内容, 不是长度。**
# 取值: 前登记规则「零分布 95 分位」→ 0.06278。
#
# ⚠️ 这个常量的三条限度, 引用它之前必须一起读:
#  1. **一对文本, R=4, 35 种构型** —— 这是**一个**经验锚, 不是一个估计良好的常数。
#     第二对独立文本跑出来之前, 别把它当作稳定阈值。
#  2. **它来自最有利的一对**(Jaccard 最低 0.075; 其余对在 0.088–0.156)。
#     即「最好情况下的可分离量级」, 不代表典型文本对。
#  3. **等长内容效应 0.07389 只有长度驱动效应(T0-vs-T2 = 0.40611)的 18.2%。**
#     ⇒ 此前 T0-vs-T2 的"分离"约 82% 是长度。任何未控长度的分离结论都要按这个比例打折。
MIN_EFFECT_EQUAL_LENGTH_20260818 = 0.06278


def separation(A, B, fpA, fpB, min_effect=None, alpha=0.05, nameA="A", nameB="B"):
    """两文本可分离性。精确置换, 位置检验。

    ⚠️ NOT_SEPARATED **不等于**"两份文本相同" —— 要主张相同必须过等价检验
    (T 的置信上界 < min_effect), 而那需要 min_effect, 即需要阳性对照。
    """
    _check(A, fpA, nameA)
    _check(B, fpB, nameB)
    if len(A) != len(B):
        raise ValueError("两组 R 不等, 精确置换无定义")
    R, pool = len(A), list(A) + list(B)
    idx = range(2 * R)
    seen, splits = set(), []
    for combo in itertools.combinations(idx, R):
        # 每种二分只数一次(标签互换是同一个分割)
        key = frozenset(combo) if 0 in combo else frozenset(set(idx) - set(combo))
        if key in seen:
            continue
        seen.add(key)
        splits.append(_T([pool[i] for i in combo],
                         [pool[i] for i in idx if i not in combo]))
    p_floor = 1 / len(splits)
    if p_floor > alpha:
        raise ValueError(f"R={R} 时 p_floor={p_floor:.4f} > alpha={alpha}: "
                         "本设计永远不可能拒绝零假设, 跑它没有意义")
    obs = _T(A, B)
    # 观测标签本身在枚举里, 所以 #{>=obs} >= 1 恒成立, 不再额外 +1
    p = sum(s >= obs - 1e-12 for s in splits) / len(splits)
    if min_effect is None:
        verdict = "UNCALIBRATED"      # PASS 分支结构上不存在
    elif p > alpha:
        verdict = "NOT_SEPARATED"     # 注意: 不等于"相同"
    elif obs < min_effect:
        verdict = "BELOW_MDE"
    else:
        verdict = "SEPARATED"
    return {"verdict": verdict, "T": obs, "p": p, "p_floor": p_floor,
            "n_splits": len(splits), "min_effect": min_effect, "alpha": alpha}

def equivalence(A, B, fpA, fpB, min_effect, alpha=0.05, nameA="A", nameB="B"):
    """等价检验: 能不能主张两组**相同**(而不只是「没分开」)。

    ★ 存在理由: `separation` 的 NOT_SEPARATED **不等于相同** —— 它是
      「没有证据说不同」, 不是「有证据说相同」。二者混用是经典的
      「不显著即无差异」谬误。要主张相同, 必须证明 T 的**上界**低于 min_effect。

    做法: 组内对 rep 做**穷举自助**(R=4 → 每组 4^4=256 种重抽, 两组 65536 对),
      取 T 的 (1-alpha) 分位作上界。穷举而非随机 ⇒ 完全确定、可复现、无随机种子。

    ⚠️ 诚实边界: R=4 的自助分布只由 4 个点撑起, **很粗**。
      结论是指示性的, 不是精确置信区间。R 越小越保守地读它。
      本函数不会在 min_effect=None 时给任何肯定判决。
    """
    _check(A, fpA, nameA)
    _check(B, fpB, nameB)
    if min_effect is None:
        return {"verdict": "UNCALIBRATED", "T": _T(A, B), "upper": None,
                "min_effect": None, "alpha": alpha}
    RA, RB = len(A), len(B)
    ma = [_meanvec([A[i] for i in c]) for c in itertools.product(range(RA), repeat=RA)]
    mb = [_meanvec([B[i] for i in c]) for c in itertools.product(range(RB), repeat=RB)]
    ts = sorted(sum(abs(x - y) for x, y in zip(u, v)) / len(KNOTS)
                for u in ma for v in mb)
    upper = ts[min(len(ts) - 1, int(round((1 - alpha) * (len(ts) - 1))))]
    return {"verdict": "EQUIVALENT" if upper < min_effect else "NOT_EQUIVALENT",
            "T": _T(A, B), "upper": round(upper, 5), "n_boot": len(ts),
            "min_effect": min_effect, "alpha": alpha,
            "note": ("EQUIVALENT = T 的自助上界低于 min_effect, 可主张「差异小于当前分辨率」; "
                     "NOT_EQUIVALENT ≠ 不同, 只是**还不能主张相同**")}
