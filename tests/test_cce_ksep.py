#!/usr/bin/env python3
"""KSEP 判据的闸。

★ 本文件的组织原则(第五次教训): **每一条守卫都配一个反向测试** ——
构造一个它应该抓住的输入, 确认它真的抛错/给出否定判决。
测不出失败的检查等于装饰。前四次失效全是"边界条件下返回了对作者有利的值"。

★ CI 遍历 tests/test_*.py 执行, 本文件末尾断言那个遍历机制还在。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_ksep as K  # noqa: E402

FP = ["a", "b", "c", "d"]


def _raises(fn, needle):
    try:
        fn()
    except ValueError as exc:
        assert needle in str(exc), f"抛错了但理由不对: {exc}"
        return True
    raise AssertionError(f"应当抛错却没有抛 (期望包含 {needle!r})")


# ── 1. 每条守卫的反向测试: 它必须真的红 ──────────────────────────────────────
_raises(lambda: K.reproducibility([{"audit": .5}] * 3, FP[:3]), "R=3 < 4")
_raises(lambda: K.reproducibility([{"audit": .5}] * 4, FP[:3]), "长度不等")
_raises(lambda: K.reproducibility([{"audit": .5}] * 4, ["x"] * 4), "重复响应指纹")
_raises(lambda: K.reproducibility([{}] * 4, FP), "全部读数为空")
_raises(lambda: K.reproducibility([{"nope": .5}] * 4, FP), "未知结")
_raises(lambda: K.reproducibility([{"audit": 1.5}] * 4, FP), "越界")
_raises(lambda: K.reproducibility([{"audit": 0.0}] * 4, FP), "越界")
# ★ "无恒定出现的结 -> 无定义" 那条分支**不可达**, 反向测试就是这么发现的:
#   flipping 为空 => 每个结要么全出现要么全不出现; 若无结全出现 => 所有 rep 皆空
#   => 已被"全部读数为空"拦掉。所以它没有反向测试, 也不算已验证的守卫。
#   这里改为钉住那条**真正生效**的前置守卫, 以及构造出来的输入实际走到哪一格。
r = K.reproducibility([{"audit": .5}, {"audit": .5}, {"belong": .5}, {"belong": .5}], FP)
assert r["verdict"] == "UNSTABLE_MEMBERSHIP", "两结各占一半 -> 走的是翻转分支, 不是无定义分支"
assert r["flipping"] == {"audit": 2, "belong": 2} and r["set_agreement"] == 1 / 3

# ── 2. 可复现性的三种判决都能被触发 ─────────────────────────────────────────
r = K.reproducibility([{"audit": .5}] * 4, FP)
assert r["verdict"] == "REPRODUCIBLE" and r["set_agreement"] == 1.0

r = K.reproducibility([{"audit": .5}, {"audit": .5, "belong": .3},
                       {"audit": .5}, {"audit": .5}], FP)
assert r["verdict"] == "UNSTABLE_MEMBERSHIP", "结集翻转必须判 UNSTABLE_MEMBERSHIP"
assert r["flipping"] == {"belong": 1}
assert r["set_agreement"] == 0.5, r["set_agreement"]

r = K.reproducibility([{"audit": .40}, {"audit": .45},
                       {"audit": .55}, {"audit": .35}], FP)
assert r["verdict"] == "UNSTABLE_INTENSITY", "极差 0.20 > tol 0.05 必须判不稳"
assert abs(r["worst_range"] - 0.20) < 1e-9

# ── 3. ★ PASS 分支在没有 min_effect 时结构上不可达 ──────────────────────────
A = [{"audit": .9}, {"audit": .9}, {"audit": .9}, {"audit": .88}]
B = [{"belong": .9}, {"belong": .9}, {"belong": .9}, {"belong": .88}]
s = K.separation(A, B, FP, ["e", "f", "g", "h"])
assert s["verdict"] == "UNCALIBRATED", \
    "没有阳性对照标定的 min_effect 时, 只能是 UNCALIBRATED —— PASS 分支必须不存在"
assert s["min_effect"] is None
# 给了 min_effect 才可能 SEPARATED
s2 = K.separation(A, B, FP, ["e", "f", "g", "h"], min_effect=0.01)
assert s2["verdict"] == "SEPARATED", s2

# ── 4. ★ PSI 的致命反例: 期望读数逐结相同、仅一侧抖动大 ─────────────────────
# PSI = (B-W)/(B+W) 在这里恒 > 0 (解析上限 1/3), 会伪造出"分离"。
# KSEP 用位置检验, 必须给 T≈0 / 不拒绝。
steady = [{"audit": .5}] * 4
jittery = [{"audit": .3}, {"audit": .7}, {"audit": .3}, {"audit": .7}]
s = K.separation(steady, jittery, FP, ["e", "f", "g", "h"], min_effect=0.001)
assert s["T"] < 1e-9, f"离散度不对称不得产生位置效应, 实得 T={s['T']}"
assert s["verdict"] in ("NOT_SEPARATED", "BELOW_MDE"), s

# ── 5. R 太小时 p 下限过粗 -> 抛错, 而不是给一个永远不显著的 p ───────────────
# R=4: C(8,4)/2 = 35 -> p_floor = 1/35 = 0.0286 <= 0.05, 可用
assert K.separation(A, B, FP, ["e", "f", "g", "h"])["n_splits"] == 35
_raises(lambda: K.separation(A[:3], B[:3], FP[:3], ["e", "f", "g"]), "R=3 < 4")

# ── 6. 完全相同的两组 -> T=0, p=1.0, 绝不能读成分离 ──────────────────────────
s = K.separation(A, [dict(x) for x in A], FP, ["e", "f", "g", "h"], min_effect=0.001)
assert s["T"] == 0.0 and s["p"] == 1.0 and s["verdict"] == "NOT_SEPARATED"

# ── 7. 真实数据复现(2026-08-18 run 32130867661) ──────────────────────────────
import json  # noqa: E402
FIX = ROOT / "tests" / "data" / "discriminability_20260818.json"
if FIX.exists():
    raw = json.loads(FIX.read_text(encoding="utf-8"))["raw"]
    reps = {t: [r["knots"] for r in v] for t, v in raw.items()}
    fps = {t: [f"{t}-{i}" for i in range(len(v))] for t, v in reps.items()}
    exp = {"T0": (0.5, {"suspend": 1}), "T1": (0.5, {"suspend": 3}),
           "T2": (1 / 3, {"pain_seek": 2})}
    for t, (agree, flip) in exp.items():
        r = K.reproducibility(reps[t], fps[t], name=t)
        assert r["verdict"] == "UNSTABLE_MEMBERSHIP", f"{t}: {r['verdict']}"
        assert abs(r["set_agreement"] - agree) < 1e-9, (t, r["set_agreement"])
        assert r["flipping"] == flip, (t, r["flipping"])
    s = K.separation(reps["T0"], reps["T1"], fps["T0"], fps["T1"])
    assert abs(s["T"] - 0.02208) < 5e-5 and abs(s["p"] - 2 / 35) < 1e-9, s
    s = K.separation(reps["T0"], reps["T2"], fps["T0"], fps["T2"])
    assert abs(s["p"] - 1 / 35) < 1e-9, s

# ── 8. CI 自防 ──────────────────────────────────────────────────────────────
wf = (ROOT / ".github" / "workflows" / "cce-submit.yml").read_text(encoding="utf-8")
assert "for t in tests/test_*.py" in wf, \
    "CI 必须遍历 tests/test_*.py —— 退回硬编码清单会让新增测试永不执行"
assert re.search(r'test "\$n" -ge \d+', wf), \
    "遍历必须配数量下限自守 —— 否则路径写错会静默跑零个测试而 CI 全绿"

print("test_cce_ksep: OK (守卫反向测试 8 条 / PASS分支不可达 / PSI反例 / 真实数据复现)")

# ── 9. min_effect 的经验锚 (oss run 32141330271, 等长阳性对照) ───────────────
assert K.MIN_EFFECT_EQUAL_LENGTH_20260818 == 0.06278
EQL = ROOT / "tests" / "data" / "equal_length_20260818.json"
if EQL.exists():
    d = json.loads(EQL.read_text(encoding="utf-8"))
    A4 = [r["knots"] for r in d["raw"]["A"]]
    B4 = [r["knots"] for r in d["raw"]["B"]]
    fa = [f"A{i}" for i in range(4)]
    fb = [f"B{i}" for i in range(4)]
    s = K.separation(A4, B4, fa, fb, min_effect=K.MIN_EFFECT_EQUAL_LENGTH_20260818)
    assert abs(s["T"] - 0.07389) < 5e-5, s
    assert abs(s["p"] - 1 / 35) < 1e-9, "观测必须是零分布里最大的那个"
    assert s["verdict"] == "SEPARATED", s
    assert d["meta"]["a_len"] == 293 and d["meta"]["b_len"] == 289, "等长前提"
    assert d["meta"]["jaccard"] == min(x[1] for x in d["meta"]["jaccard_all"]), \
        "必须是 Jaccard 最低的一对 —— 选择规则只用词面, 不看九结读数"
    # ★ 标定后回判旧数据: T0-vs-T1 落在 min_effect 之下
    raw0 = json.loads(FIX.read_text(encoding="utf-8"))["raw"]
    r01 = K.separation([r["knots"] for r in raw0["T0"]], [r["knots"] for r in raw0["T1"]],
                       [f"a{i}" for i in range(4)], [f"b{i}" for i in range(4)],
                       min_effect=K.MIN_EFFECT_EQUAL_LENGTH_20260818)
    assert r01["verdict"] == "NOT_SEPARATED", f"T0-T1 p=0.0571>alpha, 应判不分离: {r01}"
    r02 = K.separation([r["knots"] for r in raw0["T0"]], [r["knots"] for r in raw0["T2"]],
                       [f"a{i}" for i in range(4)], [f"c{i}" for i in range(4)],
                       min_effect=K.MIN_EFFECT_EQUAL_LENGTH_20260818)
    assert r02["verdict"] == "SEPARATED" and r02["T"] > 0.4
    # ★ 但它 82% 是长度 —— 这条注记必须在代码里, 不能只在文档里
    assert "82%" in K.__doc__ or "82" in open(ROOT / "scripts" / "cce_ksep.py",
                                              encoding="utf-8").read()
    print("  min_effect 锚点已钉: 等长 SEPARATED / T0-T1 NOT_SEPARATED / T0-T2 含长度混杂")

# ── 10. equivalence(): NOT_SEPARATED 不等于「相同」 ─────────────────────────
ME = K.MIN_EFFECT_EQUAL_LENGTH_20260818
F4 = ["p", "q", "r", "s"]

# 10a. 没有 min_effect ⇒ 不给任何肯定判决(与 separation 同一纪律)
assert K.equivalence(A, B, FP, ["e", "f", "g", "h"], min_effect=None)["verdict"] == "UNCALIBRATED"

# 10b. 组内恒定且两组逐字节相同 ⇒ 上界必须恰为 0
#      (不能用 A: 它第 4 个 rep 是 0.88, 自助会产生非零上界 —— 我最初就写错了这条前提)
CONST = [{"audit": .5}] * 4
same = K.equivalence(CONST, [dict(x) for x in CONST], F4, ["e", "f", "g", "h"], min_effect=ME)
assert same["upper"] == 0.0 and same["verdict"] == "EQUIVALENT", same
assert same["n_boot"] == 4 ** 4 * 4 ** 4, f"必须穷举自助(确定性), 实得 {same['n_boot']}"
# 组内**有**抖动时上界必须 >0 —— 否则说明自助根本没在重抽
jit = K.equivalence(A, [dict(x) for x in A], FP, ["e", "f", "g", "h"], min_effect=ME)
assert jit["T"] == 0.0 and jit["upper"] > 0.0, f"组内抖动必须反映在上界里: {jit}"

# 10c. 差异巨大 ⇒ NOT_EQUIVALENT
big = K.equivalence(A, B, FP, ["e", "f", "g", "h"], min_effect=ME)
assert big["verdict"] == "NOT_EQUIVALENT" and big["upper"] > ME

# 10d. ★★ 核心反向测试: 均值相同但组内抖动巨大
#      → separation 判 NOT_SEPARATED(T≈0), 但**不能**因此说「相同」。
#      若 equivalence 在这里也判 EQUIVALENT, 它就没起到任何作用。
jitA = [{"audit": .1}, {"audit": .9}, {"audit": .1}, {"audit": .9}]
jitB = [{"audit": .9}, {"audit": .1}, {"audit": .9}, {"audit": .1}]
fj = ["j1", "j2", "j3", "j4"]
sj = K.separation(jitA, jitB, fj, ["k1", "k2", "k3", "k4"], min_effect=ME)
ej = K.equivalence(jitA, jitB, fj, ["k1", "k2", "k3", "k4"], min_effect=ME)
assert sj["T"] < 1e-9 and sj["verdict"] in ("NOT_SEPARATED", "BELOW_MDE"), sj
assert ej["verdict"] == "NOT_EQUIVALENT", \
    f"均值相同但抖动巨大时**不得**主张相同, 否则本函数没起作用: {ej}"
assert ej["upper"] > ME, ej

# 10e. 真实数据: T0-T1 分不开, 且上界低于分辨率 ⇒ 可主张「差异低于当前分辨率」
if FIX.exists():
    _r = {t: [x["knots"] for x in v] for t, v in json.loads(FIX.read_text(encoding="utf-8"))["raw"].items()}
    _f = {t: [f"{t}{i}" for i in range(4)] for t in _r}
    e01 = K.equivalence(_r["T0"], _r["T1"], _f["T0"], _f["T1"], min_effect=ME)
    assert e01["verdict"] == "EQUIVALENT" and e01["upper"] < ME, e01
    assert abs(e01["upper"] - 0.03542) < 1e-4, e01
    e02 = K.equivalence(_r["T0"], _r["T2"], _f["T0"], _f["T2"], min_effect=ME)
    assert e02["verdict"] == "NOT_EQUIVALENT"
    print("  equivalence 已钉: 同一 ⇒ 上界0 / 抖动大 ⇒ 拒绝主张相同 / T0-T1 差异低于分辨率")
