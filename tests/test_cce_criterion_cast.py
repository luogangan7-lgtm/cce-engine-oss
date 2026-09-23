#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scripts/cce_criterion_cast.py 的交叉验证 + 反向测试。零 API。

## 为什么这个文件必须存在
判据铸造器是**用来判别的仪器**。一台没有反向测试的仪器 = 没有仪器 ——
把它改成恒真也没人发红, 那它的每一个输出都不是证据。

## 两类测试
① **与已知闭式解交叉验证**(必须由本仓代码**独立算出**, 不许硬写常数当结果):
   · A >= 0.95  ⟺  q >= 0.9743
   · n=8 纯 50/50 的 E[众数占比] = 0.6367
   · exact binomial 区分 q<=.70 与 q>=.90 @ α=.05,β=.20  ⇒  n=28, PASS 需 modal >= 24/28
   · 单次偏离率 1/16 ⇒ 单臂(零容差 8/8)翻掉概率 ≈ 40%, 8 臂期望达标 ≈ 4.8
② **反向测试**(把算法改坏, 上面的检查必须变红):
   下根 · 用均值替众数 · 正态近似替精确二项 · sf 差一 · 丢掉臂这一层

## ★ 纪律
反向测试走**内存内源码字符串替换**后 exec —— **仓内文件一字不改**,
每个变异都断言「恰好命中一次」(空变异 = 假消融), 且 exec 前后比对 sha256。
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import socket
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAST_PATH = ROOT / "scripts" / "cce_criterion_cast.py"
ARTIFACT = ROOT / "tests" / "data" / "ablation_v3" / "criterion_cast.json"
sys.path.insert(0, str(ROOT / "scripts"))
import cce_criterion_cast as CC  # noqa: E402


# ── 离线绊线: 本文件全程不许有一次新建连接 ──────────────────────────────────
class _Tripwire:
    def __init__(self):
        self._orig = socket.socket.connect
        self.tripped = []

    def __enter__(self):
        tw = self

        def guard(sock, address, *a, **kw):
            tw.tripped.append(address)
            raise AssertionError(f"★★★ 离线隔离被突破: {address}")

        socket.socket.connect = guard
        return self

    def __exit__(self, *exc):
        socket.socket.connect = self._orig
        return False


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _mutate(old: str, new: str) -> types.ModuleType:
    """内存内源码替换后 exec。**恰好命中一次**, 且仓内文件一字不改。"""
    before = _sha(CAST_PATH)
    src = CAST_PATH.read_text(encoding="utf-8")
    assert src.count(old) == 1, f"★ 变异锚点命中 {src.count(old)} 次(需恰好 1) —— 空变异是假消融"
    mod = types.ModuleType("cce_criterion_cast_mutant")
    mod.__file__ = str(CAST_PATH)
    with _Tripwire() as tw:
        exec(compile(src.replace(old, new), str(CAST_PATH), "exec"), mod.__dict__)
    assert tw.tripped == [], "★ 变异体加载期试图联网"
    assert _sha(CAST_PATH) == before, "★★★ R2 违反: 被测文件在消融中被写回"
    mod._MUTATED = True
    return mod


# ══════════════════════════════════════════════════════════════════════════
# ① 与已知闭式解交叉验证
# ══════════════════════════════════════════════════════════════════════════
def test_A095_equivalent_to_q_0974():
    """A = q² + (1−q)² ⇒ A >= 0.95 等价于 q >= 0.974(闭式与数值必须互相印证)。"""
    e = CC.equivalent_q(0.95, 2)
    assert round(e["q_closed_form"], 3) == 0.974, e
    # 独立数值解(二分)必须与闭式一致 —— 两条路算出同一个数才算证据
    assert e["closed_vs_numeric_absdiff"] < 1e-9, e
    # 反代回去必须落回 0.95
    assert abs(e["agreement_at_q"] - 0.95) < 1e-12, e
    # 9 类版本也必须接近(说明这条线与类别数几乎无关)
    assert round(CC.equivalent_q(0.95, 9)["q_closed_form"], 3) == 0.975


def test_modal_bias_n8_pure_5050_is_0_6367():
    """n=8 纯 50/50 的 E[众数占比] = 0.6367 —— 众数是看完数据才挑的, 天然向上偏。"""
    m = CC.modal_bias(8, probs=[0.5, 0.5])
    assert abs(m["E_mode_share"] - 0.63671875) < 1e-12, m
    assert round(m["E_mode_share"], 4) == 0.6367, m
    assert m["E_mode_share"] > 0.5, "★ 若不高于 0.5, 说明没在算众数"
    # 手算对照: E[max(X,8−X)] = 1304/256
    assert abs(m["E_mode_count"] - 1304 / 256) < 1e-12, m
    # 9 结均匀时也必须远高于 1/9
    u9 = CC.modal_bias(8, categories=9)
    assert u9["E_mode_share"] > 2.5 * (1 / 9), u9


def test_cast_reproduces_n28_c24():
    """exact binomial 区分 q<=.70 与 q>=.90 @ power .80 ⇒ n=28, PASS 需 modal >= 24/28。"""
    c = CC.cast(0.70, 0.90, 0.05, 0.20)
    assert (c["n"], c["c"]) == (28, 24), c
    assert c["alpha_achieved"] <= 0.05 and c["beta_achieved"] <= 0.20, c
    assert c["power_achieved"] >= 0.80, c
    # 最小性: n=27 在同一 α/β 下必须无解
    assert all(CC.binom_cdf(cc - 1, 27, 0.90) > 0.20
               for cc in range(28) if CC.binom_sf(cc, 27, 0.70) <= 0.05), "n=28 不是最小 n"


def test_noise_floor_reproduces_measured_headline():
    """单次偏离率 1/16 ⇒ 单臂翻掉 ≈40%, 8 臂期望达标 ≈4.8。"""
    nf = CC.noise_floor_pass_rate(1 / 16, 8, 8, 8, arms_min=7)
    assert 0.39 < nf["per_arm_flip_prob"] < 0.41, nf
    assert 4.7 < nf["expected_arms_passing"] < 4.9, nf
    assert abs(nf["per_arm_pass_prob"] - (1 - 1 / 16) ** 8) < 1e-12, "零容差单臂 = (1−p)^n"
    lo, hi = nf["arms_passing_95_noise_band"]
    assert lo <= 4 and hi >= 6, f"4/8 与 6/8 必须同落在噪声带内, 实得 {(lo, hi)}"


def test_zero_tolerance_gets_harder_with_more_reps():
    """零容差下 P(全同) = (1−p)^n 随 n **单调下降** —— 加重复只会更难过。"""
    pr = [CC.noise_floor_pass_rate(1 / 16, n, n, 1)["per_arm_pass_prob"] for n in (8, 16, 28)]
    assert pr[0] > pr[1] > pr[2], pr


def test_binomial_primitives_and_exact_interval():
    n, p = 13, 0.37
    assert abs(sum(CC.binom_pmf(k, n, p) for k in range(n + 1)) - 1.0) < 1e-12
    for k in range(n + 1):
        assert abs(CC.binom_cdf(k, n, p) + CC.binom_sf(k + 1, n, p) - 1.0) < 1e-12
    lo, hi = CC.clopper_pearson(0, 10)
    assert lo == 0.0 and abs(hi - (1 - 0.025 ** 0.1)) < 1e-6, (lo, hi)


def test_implied_q_of_zero_tolerance_line():
    """8/8 零容差要有 80% 把握通过, 需 q>=0.9725 —— 与 A>=0.95 的 0.9743 几乎同数。"""
    q80 = CC.implied_q(8, 8, 0.80)
    assert abs(q80 - 0.80 ** (1 / 8)) < 1e-9, q80
    assert abs(q80 - CC.equivalent_q(0.95, 2)["q_closed_form"]) < 0.005


def test_two_level_current_playbook_is_a_false_negative_machine():
    """现行两层判据(单臂 8/8 · 8 臂里 >=7): 真值 q=0.90 时**整条判据 98% 以上判负**。"""
    tl = CC.two_level(8, 8, 8)
    p_fail = CC.binom_cdf(6, 8, tl["per_arm_pass_at_q_good"])
    assert p_fail > 0.95, p_fail
    assert tl["arms_threshold_meeting_both"] is None, "8 臂在该单臂规则下本就不该有可行阈值"


# ══════════════════════════════════════════════════════════════════════════
# 与仓内现行判据的一致性(判据被改 ⇒ 本表作废, 必须变红)
# ══════════════════════════════════════════════════════════════════════════
def test_literal_pins_still_present_in_repo():
    missing = []
    for rel, pins in CC.LITERAL_PINS.items():
        txt = (ROOT / rel).read_text(encoding="utf-8")
        missing += [f"{rel}: {pin}" for pin in pins if pin not in txt]
    assert not missing, f"★ 现行判据字面量已变 ⇒ criterion_cast.json 作废, 必须重铸: {missing}"


def test_run_gates_indifference_region_is_live_not_transcribed():
    """★ R1: 经离线装置加载 accuracy/run_gates.py, 绊线必须在加载期装上且**未被触发**。"""
    sys.path.insert(0, str(ROOT / "probes"))
    import accuracy_offline_harness as H  # noqa: E402
    mod = H.load()
    assert mod._OFFLINE_TRIPWIRE.tripped == [], mod._OFFLINE_TRIPWIRE.tripped
    assert (mod.QUAL_P_LOW, mod.QUAL_P_HIGH) == (CC.Q_BAD, CC.Q_GOOD), \
        "★ 本表用的 indifference region 必须与 run_gates 现行的同数"


def test_artifact_is_regenerable_and_current(tmp_path):
    assert ARTIFACT.exists(), "产物未生成"
    fresh = CC.build(tmp_path / "criterion_cast.json")
    saved = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert saved["cast_recommended"] == fresh["cast_recommended"]
    assert len(saved["criteria_table"]) == len(CC.CRITERIA) >= 10
    assert saved["sources_sha256"] == fresh["sources_sha256"], "★ 被测源已变, 产物过期"
    # 边界声明必须在产物里, 一字不许丢
    assert "不说明结果该往有利方向读" in saved["★边界(不可越)"]
    # R3: 产物里不许出现仓外识别层路径
    assert "cce-identified-vault" not in json.dumps(saved, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════════════
# ② 反向测试 —— 把算法改坏, 上面的检查必须变红
# ══════════════════════════════════════════════════════════════════════════
def test_reverse_equivalent_q_lower_root():
    """取下根(镜像解) ⇒ A>=0.95 的 0.974 交叉验证必须变红。"""
    m = _mutate("q_closed = (1.0 + math.sqrt(disc)) / k",
                "q_closed = (1.0 - math.sqrt(disc)) / k")
    assert round(m.equivalent_q(0.95, 2)["q_closed_form"], 3) != 0.974


def test_reverse_modal_bias_mean_instead_of_max():
    """用均值替众数 ⇒ n=8 的 0.6367 必须变红(会退化成 1/k = 0.5)。"""
    m = _mutate("        m = max(c)\n", "        m = sum(c) / len(c)\n")
    got = m.modal_bias(8, probs=[0.5, 0.5])["E_mode_share"]
    assert abs(got - 0.63671875) > 1e-6, got
    assert abs(got - 0.5) < 1e-12, "改坏后应退化到 1/k —— 证明原实现确实在算众数"


def test_reverse_cast_normal_approximation():
    """把精确二项换成正态近似 ⇒ (n, c) 不再是 (28, 24), 或实际 α 越界。"""
    m = _mutate(
        "            if binom_sf(cc, n, q_bad) <= alpha:",
        "            if 1.0 - 0.5 * (1.0 + math.erf(((cc - 0.5 - n * q_bad) /"
        " max(1e-12, math.sqrt(n * q_bad * (1 - q_bad)))) / math.sqrt(2))) <= alpha:")
    got = m.cast(0.70, 0.90, 0.05, 0.20)
    bad = (got["n"], got["c"]) != (28, 24) or CC.binom_sf(got["c"], got["n"], 0.70) > 0.05
    assert bad, f"正态近似竟给出同一答案且 α 未越界: {got}"


def test_reverse_binom_sf_off_by_one():
    """sf 差一(把含等号的上尾写成严格大于) ⇒ 铸出的 n/c 必须偏掉。"""
    m = _mutate("    return math.fsum(binom_pmf(i, n, p) for i in range(k, n + 1))",
                "    return math.fsum(binom_pmf(i, n, p) for i in range(k + 1, n + 1))")
    got = m.cast(0.70, 0.90, 0.05, 0.20)
    assert (got["n"], got["c"]) != (28, 24), got


def test_reverse_noise_floor_drops_the_arms_layer():
    """丢掉「臂」这一层 ⇒ 期望达标臂数 ≈4.8 的交叉验证必须变红。"""
    m = _mutate('           "expected_arms_passing": arms * per_arm,',
                '           "expected_arms_passing": per_arm,')
    got = m.noise_floor_pass_rate(1 / 16, 8, 8, 8, arms_min=7)["expected_arms_passing"]
    assert not (4.7 < got < 4.9), got


def test_reverse_modal_bias_ignores_composition_weights():
    """丢掉多项式系数(把每个组合当等概率) ⇒ 期望必须偏掉且不再是概率分布。"""
    m = _mutate("        pr = w\n", "        pr = 1\n")
    got = m.modal_bias(8, probs=[0.5, 0.5])["E_mode_share"]
    assert abs(got - 0.63671875) > 1e-6, got


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
