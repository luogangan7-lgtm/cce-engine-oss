#!/usr/bin/env python3
"""对齐分必须随读数层可用性扣发 —— 这是 K1 裁定必然带出的下游后果。

## 为什么这条测试存在
2026-09-03 裁定「结层只发 top-1」之后追下游, 发现**唯一能产 complete=true 的入口**
(cce-submit.yml) 仍在调 reply_loop, 而它用 x["weight"] 算对齐分。

## 为什么不能推断「分量不可靠 ⇒ 合成量不可靠」
文献(Spearman-Brown / ICC(k))明确: 聚合会**提升**信度。所以必须实测, 不能假设。
实测(零调用, 5 文本 × 8 rep, 固定 hit 向量以隔离 weight 的贡献):
    同一输入下分数极差 中位 0.135 · p90 0.288 · max 0.488
    ★ θ=0.35 的判决 **18.4%** 被 weight 抖动翻转 —— 且这是**下界**
与 2026-08-10 的独立实测(同稿重跑 3/8 翻转, |Δ|均值 0.213)相符。

★ 聚合定理在这里**结构上不适用**: Spearman-Brown 要求分量独立, 而 9 个权重
  来自同一次抽样且被全占比约束到和为 1。
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_k1_status import knot_readout_usable  # noqa: E402

SRC = open(os.path.join(ROOT, "scripts", "reply_loop.py"), encoding="utf-8").read()
INST = "565470cf26c16d01"

# ── 前提: weight 确实不可用(可用了这条测试就该重写而不是沿用) ──────────
ok, why = knot_readout_usable("weight", instrument_hash=INST)
assert not ok, "★ weight 变成可用了 —— 扣发逻辑与本测试都要重估, 不许沿用"

# ── reply_loop 必须**现问**可用性, 不许写死结论 ────────────────────────
assert "knot_readout_usable(\"weight\"" in SRC, \
    "★ 必须现问 knot_readout_usable —— 写死「不可用」会在它将来可用时变成永久错误"
tree = ast.parse(SRC)
assert any(isinstance(n, ast.ImportFrom) and n.module == "cce_k1_status"
           for n in ast.walk(tree)), "必须从 cce_k1_status 取可用性, 不得自行判断"

# ── 不可用时 knot_ok 必须置 None(不可判), 不许发 True/False ────────────
assert "if not _w_ok:\n        knot_ok = None" in SRC, \
    "★ 读数层不可用时必须判「不可判」—— 给 PASS 或 FAIL 都是把噪声当结论"

# ── 旧守卫守错了对象这件事必须写在代码里 ──────────────────────────────
assert "守错了对象" in SRC, \
    "★ 旧 top1_stable 守卫守的是**稳的**那层, 这个教训要留在原地, 不能只写在提交信息里"

# ── 必须留下只用可用层的出口, 否则 with_alignment 变成永远「不可判」────
assert "top1_align" in SRC and "reader_top1" in SRC, "★ 缺 top-1 唯一可用层的对齐出口"
assert "★still_noisy" in SRC, \
    "★ top-1 对齐的 playbook_hit 自身未经预注册判定, 必须写明, 不许当已验收的量"

# ── 二值门必须仍然是摘掉的状态 ────────────────────────────────────────
WF = open(os.path.join(ROOT, ".github", "workflows", "cce-submit.yml"), encoding="utf-8").read()
body = "\n".join(l for l in WF.splitlines() if not l.lstrip().startswith("#"))
assert "reply_alignment.json" in body, "对齐步骤应仍在(只是不判决)"
assert "jq -e '.verdict.PASS" not in body, \
    "★ 二值门不得复活 —— 该算子同稿重跑就会翻转, 布尔化即把噪声当结论"

print("test_cce_reply_alignment_withheld: OK "
      "(weight 不可用 -> knot_ok=None 不可判 | 现问可用性不写死 | "
      "留了 top-1 唯一可用层的出口且标注其自身未验 | 二值门仍是摘掉状态)")
