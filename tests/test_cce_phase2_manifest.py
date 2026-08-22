#!/usr/bin/env python3
"""面板清单 —— 刺激集进入测量之前的最后一道闸。

守四件事：
  1. 测量仪器必须是 gen4 MiniMax-M3 —— 换模型 = 换仪器 = gen5, gen4 标定全废。
  2. 生成器与盲验者**都不得**是测量模型（用测量模型筛刺激 ⇒ 留下的都是它认为变了的 ⇒ 循环）。
  3. primary / sensitivity 两套集合必须都在，且分歧规则写死 ——
     否则事后可以挑一套好看的报。
  4. 协议修订必须**带时间戳 + 原因 + outcome_dependent 声明**，且证据文件真的存在。
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "tests" / "data" / "phase2"
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "scripts"))
import phase2_generate_stimuli as G  # noqa: E402
from exp_crossmodel_desire import MODELS  # noqa: E402

M = json.loads((P / "panel_manifest.json").read_text(encoding="utf-8"))

# ── 1. 仪器身份 ─────────────────────────────────────────────────────────────
MI = M["measurement_instrument"]
assert MI["instrument_hash"] == "565470cf26c16d01" and MI["gen"] == 4
# ★ 换过代就必须留痕: 「用过 gen5、为什么放弃、那批数据在哪」不能只活在对话里
rv = MI["reverted_from"]
assert rv["instrument_hash"] == "eb487df50f5aec31" and "周配额" in rv["why"]
assert "不与 gen4 数据混用" in rv["why"], "★ 两台仪器的数据不得混, 这条必须写死"
assert (P / "panel_gen5_partial_294_quota_exhausted.jsonl").exists(), "★ gen5 部分数据必须留档"

# ── 2. 测量模型不得参与刺激构造 ─────────────────────────────────────────────
meas = MODELS[G.MEASUREMENT_MODEL]["model"]
touched = {MODELS[k]["model"] for k in
           set(G.GENERATORS.values()) | set(G.VERIFIER_OF.values())}
assert meas not in touched, \
    "★★ 测量模型参与了刺激生成/筛选 ⇒ 按它自己的判断筛刺激, 可分辨性被系统性抬高"

# ── 3. 两套分析集合 + 分歧规则 ──────────────────────────────────────────────
arms = M["arms"]
prim = [a for a in arms if a["in_primary"]]
assert len(prim) < len(arms), "★ primary 与 sensitivity 完全相同 ⇒ 盲验没起任何作用"
assert "INDETERMINATE" in M["analysis_sets"]["on_disagreement"], \
    "★ 两套结果分歧时的处理不写死 ⇒ 事后可以挑好看的那套报"
for a in arms:
    assert a["in_primary"] == (a["blind_rule_check"] in ("FOLLOWS", "NOT_APPLICABLE"))
# 零参照两臂是 base 原文本身, 不经生成器 ⇒ 不受刺激作者污染
for a in arms:
    if a["arm"] in ("L0", "L0b"):
        assert a["generator_family"] is None and a["blind_rule_check"] == "NOT_APPLICABLE"
# 每个 base 都必须有完整的零参照对(resolution 不依赖任何生成内容)
n_base = len({a["base_id"] for a in arms})
c = Counter(a["arm"] for a in arms)
# 不写死 24: 扩展块触发后是 24+8。守的是**不变量** —— 每个 base 都必须有零参照对,
# 因为 resolution 完全不依赖生成内容, 任何 base 缺 L0/L0b 都是采集漏了。
assert c["L0"] == c["L0b"] == n_base, "★ 有 base 缺零参照臂 ⇒ 该 base 的分辨率无法计算"
ext = M.get("extension_block")
assert n_base == 24 + (ext["n_bases"] if ext else 0), f"base 数 {n_base} 与扩展块登记不符"
if ext:
    assert ext["same_instrument"].startswith("gen4"), "★ 扩展块必须与主面板同一台仪器"
    assert "预先确定" in ext["preregistered"]

# ── 4. 协议修订留痕 ─────────────────────────────────────────────────────────
am = M["protocol_amendments"]
assert len(am) >= 2
for a in am:
    assert a["outcome_dependent"] is False and a["at"] and a["trigger"] and a["why_not"]
    assert "block" in a, "★ 修订必须冻结成完整 block, 否则就是「不够就再加一点」"
assert (P / "stimuli_pre_amendment_maxregen3.json").exists(), "★ 修订前结果必须留档, 不许覆盖"
assert (P / "blind_verify_pre_amend2.jsonl").exists()

# ── 5. 规模自洽 ─────────────────────────────────────────────────────────────
assert M["planned_calls"] == len(arms) * M["R"] * M["calls_per_rep"]

print(f"test_cce_phase2_manifest: OK ({len(arms)} 臂 / primary {len(prim)} / "
      f"{M['planned_calls']} 次调用 / {len(am)} 条修订留痕)")
