#!/usr/bin/env python3
"""用冻结数据估「R 取多少」—— 0 次 API 调用。

★★ 两条硬边界, 引用任何数字前必须一起读:

1. **这不是经验 power 曲线, 是 conditional bootstrap approximation given the observed reps。**
   从 4 个已观测 rep 有放回重抽 8 个, 只会重复那 4 个点, **永远生成不了尚未观测到的
   run 间变异**。若那 4 次恰好漏掉尾部, 它**反而偏乐观** —— 所以它连「下界」都不是。
   (这条措辞是外部评审纠正我的: 我原先说「bootstrap 给出的下界」, 不对。)

2. **数据产自 gen1(57ec6cf478d3875e), 而当前仪器是 gen3** —— s1 prompt 已变,
   噪声结构可能整体不同。用它规划 gen3 的投料是一个**明写的假设**, 不是结论。

那它还有什么用? 两件:
  · 型 I 错误自检: 把**同一个文本**的 rep 随机劈成两半, 看精确置换检验有多常误报分离。
    这不依赖「未观测变异」—— 零假设本来就成立, 是当前实现的自检。
  · 给出**乐观上界**: 若连乐观估计都说 R=6 不够, 那 R=6 一定不够。反向不成立。
"""
import itertools, json, random, statistics as st, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_ksep as K  # noqa: E402


def _p_perm(A, B, alpha=0.05):
    """对任意等长两组算精确置换 p。R 大时构型数爆炸, 故 R>7 改抽样近似并标注。"""
    R = len(A)
    pool = list(A) + list(B)
    idx = range(2 * R)
    obs = K._T(A, B)
    combos = itertools.combinations(idx, R)
    if K_math_comb(2 * R, R) // 2 > 20000:
        rng = random.Random(20260819 + R)
        seen = 0, 
        cnt = tot = 0
        for _ in range(20000):
            c = tuple(rng.sample(list(idx), R))
            t = K._T([pool[i] for i in c], [pool[i] for i in idx if i not in c])
            cnt += (t >= obs - 1e-12); tot += 1
        return cnt / tot, obs, True
    seen, splits = set(), []
    for c in combos:
        key = frozenset(c) if 0 in c else frozenset(set(idx) - set(c))
        if key in seen:
            continue
        seen.add(key)
        splits.append(K._T([pool[i] for i in c], [pool[i] for i in idx if i not in c]))
    return sum(s >= obs - 1e-12 for s in splits) / len(splits), obs, False


def K_math_comb(n, r):
    from math import comb
    return comb(n, r)


def curve(reps_a, reps_b, Rs=(4, 5, 6, 7), B=400, seed=20260819):
    """H1: 两个不同文本; H0: 同一文本劈两半(零假设成立, 任何分离都是误报)。"""
    rng = random.Random(seed)
    out = {}
    for R in Rs:
        h1 = h0 = 0
        approx = False
        for _ in range(B):
            a = [rng.choice(reps_a) for _ in range(R)]
            b = [rng.choice(reps_b) for _ in range(R)]
            p, _, ap = _p_perm(a, b); approx |= ap
            h1 += (p <= 0.05)
            # H0: 两组都从 A 抽
            a0 = [rng.choice(reps_a) for _ in range(R)]
            b0 = [rng.choice(reps_a) for _ in range(R)]
            p0, _, _ = _p_perm(a0, b0)
            h0 += (p0 <= 0.05)
        out[R] = {"p_floor": 1 / (K_math_comb(2 * R, R) // 2),
                  "H1_reject_rate": round(h1 / B, 3),
                  "H0_false_separation": round(h0 / B, 3),
                  "permutation": "approx(20k 抽样)" if approx else "exact",
                  "B": B}
    return out


if __name__ == "__main__":
    print(__doc__)
    # ★ 已分开的一对重抽后必然继续分开 ⇒ H1 列饱和在 1.000, **等于没信息**。
    #   真正有信息的是**没分开的那一对**: 对它, 加 R 到底救不救得回来?
    cases = [
        ("★T0 vs T1 (R=4 时 p=0.0571, **未分开**)", "discriminability_20260818.json", "T0", "T1"),
        ("等长对1 A vs B (R=4 已分开, 对照)", "equal_length_20260818.json", "A", "B"),
        ("等长对2 A vs B (R=4 已分开, 对照)", "second_pair_20260818.json", "A", "B"),
    ]
    for name, fn, ka, kb in cases:
        d = json.loads((ROOT / "tests" / "data" / fn).read_text(encoding="utf-8"))
        raw = d["raw"]
        A = [r["knots"] for r in raw[ka]]
        B = [r["knots"] for r in raw[kb]]
        print(f"\n=== {name} (源数据 R={len(A)}, 仪器 gen1) ===")
        print(f"{'R':>3} {'p下限':>8} {'H1 拒绝率':>10} {'H0 误报分离':>12}  置换")
        for R, v in curve(A, B).items():
            print(f"{R:>3} {v['p_floor']:>8.4f} {v['H1_reject_rate']:>10.3f} "
                  f"{v['H0_false_separation']:>12.3f}  {v['permutation']}")
    print("\n★ H0 列是**自检**(零假设成立, 不依赖未观测变异): 它应当 <= alpha=0.05。")
    print("★ H1 列是**乐观上界**: 连它都不够就一定不够; 它够**不代表**真投料也够。")
    print("★★ 已分开的两对 H1 恒为 1.000 —— **饱和, 无信息**。只有未分开的 T0/T1 那行可读。")
