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

2. **均值向量的 L1/9 距离 + 精确置换, 不是离散度比值。**
   离散度不对称只进置换零分布 —— 正确地**降低功效**, 而不是伪造效应。

   ⚠️ [4/4] 表述修正: 此前这里写「位置检验」, 不够准。
   本实现把两组 rep 合并后重贴标签, 严格对应的零假设是
   **label exchangeability / 同分布**, 不是「仅均值(位置)相等」。
   未 studentize 的置换检验在更弱的位置零假设下**不一般保证精确 level-α**。
   算法不必改, 但 inferential target 要写对: 拒绝 H0 意味着
   「两组不可交换」, 而不必然是「均值不同」—— 方差/形状差异同样能致拒。

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
# ★ 2026-08-18 [3/4]: 此前这里只有一个 `MIN_EFFECT_EQUAL_LENGTH_20260818 = 0.06278`,
#   它同时被当成三种**互不相容**的东西用(外部源码审计指出, 我认同):
#       测量分辨率 (instrument resolution)
#     × 实践显著性 (SESOI, smallest effect size of interest)
#     × 等价边界   (equivalence margin)
#   而它的真实身份只是 **pair-1 自己的置换零分布水位**, 不是「多大的心理差异才值得关心」。
#   作为 SESOI: 不成立。作为全局分辨率: 也不成立(两对水位差 2.4 倍, 0.06278 vs 0.14944)。
#
#   ★ 且存在 evaluation leakage: 常量由 run 32141330271 那一对导出后,
#     测试又拿**同一对数据**加该常量断言 SEPARATED。而该对 T=0.07389 vs null_max=0.06278,
#     一旦 p=1/35 成立, T>=0.06278 几乎是构造性的。故 pair-1 标记为 CALIBRATION ONLY。
#
#   现在拆成三个独立参数, 谁也不许冒充谁。
PAIR1_NULL_CALIBRATION_STATISTIC = {
    "value": 0.06278,
    "role": "CALIBRATION_ONLY",
    "what_it_is": "run 32141330271 那一对等长文本自己的置换零分布 95 分位(=该对 null_max)",
    "what_it_is_not": "不是 SESOI, 不是全局仪器分辨率, 不是等价边界",
    "do_not": "不得用它对产生它的那一对数据做 confirmatory 判决(evaluation leakage)",
    # ★ 2026-08-19: stage1 prompt 已改为允许弃权 ⇒ **物理仪器变了**(gen3)。
    #   本统计量测于 gen1(57ec6cf478d3875e), 其 s1 prompt sha = d73764202b732e98。
    #   ⇒ 它对 gen3 **不适用**, 需重新标定。用 cce_knot_classify.calibration_transfers() 判。
    "measured_on_instrument": "57ec6cf478d3875e",
    "measured_on_s1_prompt_sha256": "d73764202b732e98",
    "transfers_to_current": False,
    "why_not": "gen3 改了 s1 prompt(允许声明无可推断主体), 被测对象收到的指令不同。",
}

# 仪器分辨率: 需要**独立的同文本重复校准语料**(同一文本 × 独立重跑 × 多个文本类别),
# 且很可能不是一个全局数字, 而是 instrument_hash × text stratum × sampling policy 的 profile。
# 现在没有 ⇒ 明写 None, 不拿 pair-1 的水位顶替。
DELTA_RESOLUTION = None

# ── 撤回记录(不得删除: 撤回清单机器检查依赖它留痕) ──────────────────────────
#  ~~它来自最有利的一对(Jaccard 最低 = 给仪器最好的机会)~~
#     —— **已被 run 32143785964 证伪并撤回**: Jaccard 更高(0.1013 vs 0.075)的一对
#     T 反而大 3.0 倍(0.22389 vs 0.07389) ⇒ **词面相似度不预测可分离性**。
#  ~~等长内容效应只有长度驱动效应的 18.2%, T0-T2 约 82% 是长度~~
#     —— **已被两次实测推翻并撤回**: (a) 第二对等长 T=0.22389 已是 T0-T2(0.40611) 的 55%,
#     18.2% 是拿**最小**的那个等长效应当上限; (b) run 32147076464 腿B: BASE 与 BASE×5
#     (内容逐字相同, 长度 293→1473)判 T=0.02056、上界 0.04514, 结集完全相同
#     ⇒ **长度 per se 根本不驱动读数**。
# ───────────────────────────────────────────────────────────────────────────

# SESOI: 「CCE contrast 小到什么程度, 我们愿意当作实际无意义」。
# 只能来自真实下游结果 / 决策成本 / 机制实验 / 预注册的业务意义。
# 现在没有 ⇒ 明写 None。**填 None 比硬塞 0.06278 科学。**
SESOI = None


def separation(A, B, fpA, fpB, alpha=0.05, sesoi=None, nameA="A", nameB="B"):
    """两文本可分离性。精确置换检验。

    零假设是**两组 rep 可交换(同分布)**, 不是「仅均值/位置相等」——
    故拒绝 H0 意味着「两组不可交换」, 方差/形状差异同样能致拒, 不必然是均值不同。

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
    # ★ 统计证据与实践显著性**正交**, 不再合成一个 verdict。
    #   verdict 只回答统计问题; 实践问题在 practical 块里单独回答。
    verdict = "NOT_SEPARATED" if p > alpha else "SEPARATED"
    if sesoi is None:
        practical = {"status": "NOT_CALIBRATED", "sesoi": None,
                     "note": "没有 SESOI 就没有实践显著性判决。不要拿零分布水位顶替。"}
    else:
        practical = {"status": "MEANINGFUL" if obs >= sesoi else "BELOW_SESOI",
                     "sesoi": sesoi}
    # 报出本次比较**自己的**零分布水位。理由(2026-08-18 实测):
    #   两对等长文本的零分布 95 分位分别是 0.06278 与 0.14944, 差 2.4 倍 ——
    #   零分布水位由文本自身的组内变异决定, **不存在一个全局适用的 min_effect**。
    # ★ 并且 R=4 时 p<=0.05 需要 #{>=obs}==1, 即 obs 严格大于其余 34 个构型
    #   ⇒ **p<=0.05 已经蕴含 obs > 本次零分布最大值**, min_effect 在 R=4 上
    #   只在「整个零分布都被压在 min_effect 之下」时才起作用。它不是死分支, 但比看上去弱得多。
    _nul = [x for x in splits if x < obs - 1e-12]
    return {"verdict": verdict, "T": obs, "p": p, "p_floor": p_floor,
            "n_splits": len(splits), "practical": practical, "alpha": alpha,
            "null_max": round(max(_nul), 5) if _nul else None,
            "null_median": round(sorted(_nul)[len(_nul) // 2], 5) if _nul else None}

def equivalence(A, B, fpA, fpB, margin, margin_is_sesoi=False, alpha=0.05,
                nameA="A", nameB="B"):
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
    # ★ margin_is_sesoi=False 时**不允许**说「等价」——
    #   拿 pair-1 的置换噪声水位当等价边界, 说的不是「差异实际无意义」,
    #   只是「差异低于那一对文本的噪声水位」。两者不可混读。
    if margin is None:
        return {"verdict": "UNCALIBRATED", "T": _T(A, B), "upper": None,
                "margin": None, "margin_is_sesoi": False, "alpha": alpha}
    RA, RB = len(A), len(B)
    ma = [_meanvec([A[i] for i in c]) for c in itertools.product(range(RA), repeat=RA)]
    mb = [_meanvec([B[i] for i in c]) for c in itertools.product(range(RB), repeat=RB)]
    ts = sorted(sum(abs(x - y) for x, y in zip(u, v)) / len(KNOTS)
                for u in ma for v in mb)
    upper = ts[min(len(ts) - 1, int(round((1 - alpha) * (len(ts) - 1))))]
    below = upper < margin
    if margin_is_sesoi:
        verdict = "EQUIVALENT" if below else "NOT_EQUIVALENT"
        note = ("EQUIVALENT = T 的自助上界低于**已标定的 SESOI**, 可主张「差异实际无意义」; "
                "NOT_EQUIVALENT ≠ 不同, 只是还不能主张相同")
    else:
        verdict = "BELOW_CALIBRATION_MARGIN" if below else "ABOVE_CALIBRATION_MARGIN"
        note = ("margin 不是已标定的 SESOI, 只是一个校准统计量 ⇒ **不得读成「等价」**。"
                "只能说「T 的自助上界低于该 margin」。要主张等价必须先独立标定 SESOI。")
    return {"verdict": verdict, "T": _T(A, B), "upper": round(upper, 5), "n_boot": len(ts),
            "margin": margin, "margin_is_sesoi": margin_is_sesoi, "alpha": alpha,
            "note": note,
            "caveat": ("R 小时自助分布只由 R 个点撑起 —— 严格说这是 "
                       "conditional bootstrap approximation given these observed reps, "
                       "**不保证是下界**; 若这几次恰好漏掉尾部, 它反而偏乐观。")}


def verdict3(A, B, fpA, fpB, margin=None, margin_is_sesoi=False, alpha=0.05,
             nameA="A", nameB="B"):
    """三分判决 —— 唯一允许被探针引用的结论出口。

    ★ 存在理由(2026-08-18, run 32143780680 实地翻车):
      length_null_arm 探针自己写了 `if p > 0.05 or T < min_effect: 判定没有效应`。
      那一行**把 p>0.05 当成了「无效应」的证据**, 并且在 T=0.10792(高于 min_effect
      0.06278)时仍打印「低于当前分辨率」。实际同一对数据 equivalence 判 NOT_EQUIVALENT
      ⇒ 正确结论是**欠功效**, 既不能说不同也不能说相同。

      每个探针各判一次 = 每个探针各错一次。判决收进这里, 只错一处、只修一处。

    三种出口, 没有第四种:
      SEPARATED    分离检验拒绝零假设 ⇒ 有证据说**不同**
      EQUIVALENT   T 的自助上界低于 min_effect ⇒ 有证据说**差异小于当前分辨率**
      UNDERPOWERED 两者都不成立 ⇒ **既不能说不同, 也不能说相同**。不是「没有差异」。
    """
    sep = separation(A, B, fpA, fpB, alpha=alpha,
                     sesoi=(margin if margin_is_sesoi else None), nameA=nameA, nameB=nameB)
    eq = equivalence(A, B, fpA, fpB, margin=margin, margin_is_sesoi=margin_is_sesoi,
                     alpha=alpha, nameA=nameA, nameB=nameB)
    if sep["verdict"] == "SEPARATED":
        v = "SEPARATED"
    elif margin is None:
        v = "UNCALIBRATED"
    elif eq["verdict"] == "EQUIVALENT":
        v = "EQUIVALENT"                    # 只有 margin 是真 SESOI 时才可能到这
    elif eq["verdict"] == "BELOW_CALIBRATION_MARGIN":
        v = "BELOW_CALIBRATION_MARGIN"      # ★ 不是「等价」, 只是低于一个未标定的 margin
    else:
        v = "UNDERPOWERED"
    return {"verdict": v, "T": sep["T"], "p": sep["p"],
            "equiv_upper": eq.get("upper"), "null_max": sep.get("null_max"),
            "margin": margin, "margin_is_sesoi": margin_is_sesoi,
            "practical": sep["practical"], "separation": sep, "equivalence": eq,
            "note": ("UNDERPOWERED 不是「没有差异」, 是「这个 R 下判不出来」; "
                     "BELOW_CALIBRATION_MARGIN 不是「等价」, 是「低于一个尚未标定为 SESOI 的 margin」。"
                     "两者都禁止读成阴性结论。")}
