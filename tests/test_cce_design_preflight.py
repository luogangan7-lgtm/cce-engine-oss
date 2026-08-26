#!/usr/bin/env python3
"""投料前设计硬门的守卫 —— 用**我自己已经犯过的两个错**当测试用例。

一道从来没被看见拦下过任何东西的检查, 和没有这道检查是一回事(本项目反复
栽在这一类缺陷上)。所以这里不测「函数能跑」, 只测三件事:

  ① 第一轮设计(填充按比例加)          必须 FAIL, 且命中 g3 秩亏 + g6 合成还原失败
  ② 第二轮 2x2(total=base+pad 等)     必须 FAIL, 且命中 g1 结构不可分辨
  ③ 一个正交的干净设计                必须 PASS —— 否则这道门只是无差别挡路

②③ 合起来才有意义: 只有 ① ② 会红, 无法区分「门有判别力」和「门永远说 FAIL」。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from design_preflight import preflight  # noqa: E402

V = {"primitive": ["base_chars", "pad_chars"],
     "derived": {"total_chars": ["base_chars", "pad_chars"],
                 "share": ["base_chars", "pad_chars"]}}
TERMS = {"terms": ["base_chars", "pad_chars"]}
codes = lambda r: {f["code"] for f in r["fails"]}


# ── ① 第一轮: base 固定, 只加 pad ⇒ base_chars 列恒定 ⇒ 秩亏 ────────────────
r1 = preflight({
    "variables": V,
    "estimands": [{"name": "total_length_effect", "target": "total_chars",
                   "nuisance": ["share"]}],
    "analysis_formula": TERMS,
    "design": [{"base_chars": 750, "pad_chars": p, "total_chars": 750 + p,
                "share": round(750 / (750 + p), 3)} for p in (0, 375, 750, 1500)],
    "n_raw_observations": 240, "n_experimental_units": 12,
    "claimed_inferential_n": 240})
assert not r1["pass"], "★ 第一轮设计必须被拦下 —— 它当时跑完才发现混杂"
assert "FAIL_RANK_DEFICIENT" in codes(r1), "★ base 在设计里不变, 秩亏必须被抓到"
assert "NOT_IDENTIFIABLE_BY_DESIGN" in codes(r1), "★ 不存在孤立对比"
assert "FAIL_SYNTHETIC_SIGN" in codes(r1), \
    "★ gate6: 连「只有 base 有效应」这个已知答案都还原不出, 该分析不能上真数据"

# ── ② 第二轮 2x2: total=base+pad 且 share=base/total ⇒ 4 变量仅 2 自由度 ────
r2 = preflight({
    "variables": V,
    "estimands": [{"name": "total_effect", "target": "total_chars", "nuisance": ["share"]},
                  {"name": "share_effect", "target": "share", "nuisance": ["total_chars"]},
                  {"name": "base_effect", "target": "base_chars", "nuisance": ["pad_chars"]},
                  {"name": "pad_effect", "target": "pad_chars", "nuisance": ["base_chars"]}],
    "analysis_formula": TERMS,
    "design": [{"base_chars": 1004, "pad_chars": 452, "total_chars": 1456, "share": 0.69},
               {"base_chars": 459, "pad_chars": 997, "total_chars": 1456, "share": 0.32},
               {"base_chars": 1841, "pad_chars": 1130, "total_chars": 2971, "share": 0.62},
               {"base_chars": 928, "pad_chars": 2047, "total_chars": 2975, "share": 0.31}],
    "n_raw_observations": 192, "n_experimental_units": 24,
    "claimed_inferential_n": 192})
assert not r2["pass"], "★ 2x2 必须被拦下"
assert "FAIL_STRUCTURAL_NONIDENTIFIABILITY" in codes(r2), \
    "★ 声明 4 个 estimand 但只有 2 个自由度 —— 这是纸面上就能算出来的"
assert r2["report"]["free_dof"] == 2
assert "FAIL_PSEUDOREPLICATION" in codes(r2), "★ 声明 n=192 但独立单位只有 24"

# ── ③ 反向: 正交干净设计必须放行(否则这门只是无差别挡路) ────────────────────
good = [{"base_chars": b, "pad_chars": p, "total_chars": b + p,
         "share": round(b / (b + p), 3)}
        for b in (400, 700, 1000, 1400, 1800, 2200) for p in (0, 400, 900, 1600)]
r3 = preflight({
    "variables": V,
    "estimands": [{"name": "base_effect", "target": "base_chars", "nuisance": ["pad_chars"]},
                  {"name": "pad_effect", "target": "pad_chars", "nuisance": ["base_chars"]}],
    "analysis_formula": TERMS, "design": good,
    "n_raw_observations": len(good) * 4, "n_experimental_units": len(good),
    "claimed_inferential_n": len(good)})
assert r3["pass"], f"★ 干净设计被误拦, 这门没有判别力: {codes(r3)}"

# ── ④ 条件数必须按列归一化: 否则纯量纲差异会被误判成共线性(修复回归) ────────
assert r3["report"]["condition_number"] < 30, \
    ("★ 正交设计的条件数应接近 1 量级; 若又回到 1e3 说明忘了列归一化, "
     f"当前 {r3['report']['condition_number']}")

# ── ⑤ 只改 n 的谎报, 应当**只**触发 gate5, 不牵连其它门 ─────────────────────
r4 = preflight({
    "variables": V,
    "estimands": [{"name": "base_effect", "target": "base_chars", "nuisance": ["pad_chars"]},
                  {"name": "pad_effect", "target": "pad_chars", "nuisance": ["base_chars"]}],
    "analysis_formula": TERMS, "design": good,
    "n_raw_observations": len(good) * 4, "n_experimental_units": len(good),
    "claimed_inferential_n": len(good) * 4})
assert codes(r4) == {"FAIL_PSEUDOREPLICATION"}, \
    f"★ 各门必须彼此独立可归因, 实际触发 {codes(r4)}"

print("test_cce_design_preflight: OK (第一轮秩亏+合成失败/2x2结构不可分辨/"
      f"干净设计放行 cond={r3['report']['condition_number']:.2f}/门可归因)")
