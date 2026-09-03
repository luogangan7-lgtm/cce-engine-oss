#!/usr/bin/env python3
"""playbook_hit 复现性判定的钉子 —— 唯一剩下的对齐出口也不可用。

判定 UNRELIABLE(8 文本 × n=8, 192 次真实调用, 预注册测量前冻结)。

★ 最要紧的不是「4/8 达标」这个数, 是**失败的形状**:
  4 个 PASS 里 3 个中位 0.0、1 个 1.0, 极差全 0 —— **稳在地板或天花板**;
  4 个 FAIL 极差 0.3–0.7, 全落在中间。
  ⇒ 它只在答案明显时稳, **恰恰在阈值判决所在的中间地带不稳**。
★ 非退化闸**过了** ⇒ 这不是「什么都没测」, 是「测到了但在需要它的地方不稳」。
  两者修法完全不同, 不许合并成一句「不稳」。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_k1_status import playbook_hit_usable  # noqa: E402

P = os.path.join(ROOT, "tests", "data", "phase2")
V = json.load(open(os.path.join(P, "playbook_hit_verdict.json"), encoding="utf-8"))
S = json.load(open(os.path.join(P, "playbook_hit_prereg.json"), encoding="utf-8"))
INST = "565470cf26c16d01"

# ── 判定与预注册对得上 ────────────────────────────────────────────────
assert V["instrument_hash"] == INST == S["instrument"]["must_equal"]
assert V["★decision_rule_frozen_at"] == S["prereg_written_at"], "★ 决策规则须测量前冻结"
assert V["decision"] == "UNRELIABLE", V["decision"]
assert V["texts"] == 8 and all(p["n"] == 8 for p in V["per_text"].values()), V["per_text"]

# ── ★ 选文与 K1-v2 错开(不许同批既调参又验收) ─────────────────────────
v2 = json.load(open(os.path.join(P, "k1_v2_multitext_verdict.json"), encoding="utf-8"))
assert not (set(V["per_text"]) & set(v2["layers"]["intensity"]["per_text"])), \
    "★ 与 K1-v2 用了同一批文本 —— 同批既调参又验收"

# ── ★ 核心: 失败集中在中间地带 ────────────────────────────────────────
passes = [p for p in V["per_text"].values() if p["verdict"] == "PASS"]
fails = [p for p in V["per_text"].values() if p["verdict"] == "FAIL"]
assert len(passes) == V["meeting_criterion"] == 4 and len(fails) == 4
assert all(p["range"] == 0.0 for p in passes), \
    "★ PASS 项若不再是极差 0(地板/天花板), 「只在答案明显时稳」这个解读要重写"
assert all(p["median"] in (0.0, 1.0) for p in passes), \
    "★ PASS 项的中位数不在端点 ⇒ 解读要重写"
assert all(p["range"] >= 0.20 for p in fails), \
    "★ FAIL 项极差应明显非零"
assert "中间地带" in V["★pattern"], "★ 失败的形状必须写进产物, 不能只在提交信息里"

# ── ★ 非退化闸过了 —— 这决定了它是哪一种失败 ──────────────────────────
assert V["degeneracy"]["passes"] is True, \
    "★ 若未过非退化, 结论要改成「它什么都没测」, 而不是「测到了但不稳」"
assert V["degeneracy"]["distinct_medians"] >= 3
assert "什么都没测" in V["★not_degenerate"]

# ── 已接进扣发, 且缺仪器标识一律扣发 ──────────────────────────────────
ok, why = playbook_hit_usable(instrument_hash=INST)
assert not ok and "中间地带不稳" in why, why
assert not playbook_hit_usable()[0], "★ 缺 instrument_hash 必须扣发"

# ── 生产路径确实照它扣发 ──────────────────────────────────────────────
src = open(os.path.join(ROOT, "scripts", "reply_loop.py"), encoding="utf-8").read()
assert "playbook_hit_usable(" in src, "★ reply_loop 必须现问, 不许写死"
assert "★measured_2026_09_03" in src, "★ 旧的「未经判定」措辞必须换掉 —— 现在已经判过了"

print(f"test_cce_playbook_hit: OK (8 文本 × n=8 · 达标 {V['meeting_criterion']}/8 ⇒ "
      f"{V['decision']} | PASS 全在端点极差 0 · FAIL 全在中间极差>=0.2 ⇒ "
      "「只在答案明显时稳」 | 非退化过 ⇒ 不是「什么都没测」 | 已接进扣发)")
