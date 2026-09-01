#!/usr/bin/env python3
"""制备桥接: 三层拦截 + 标定迁移。每条都带反向测试。"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cce_knot_classify as kc  # noqa: E402
from cce_preparation_bridge import (  # noqa: E402
    BRIDGE_PURPOSE, COMPARABLE, EXACT_INPUT_IDENTITY, NOT_COMPARABLE,
    NONTRANSFERABLE_PREPARATION_CHANGED, PREPARATION_EFFECT_ESTIMATE,
    PreparationMismatchError, bridge_calibration_frame, classify_transfer,
    comparability, manifest_preparation_verdict, measurement_procedure_id,
    require_comparability_declared,
)
from cce_structural_gate import preparation_id, structural_gate  # noqa: E402

TAXO = json.load(open(os.path.join(ROOT, "config", "knot_taxonomy.json"), encoding="utf-8"))

# ── 1. 联合身份: 换制备必须换 measurement_procedure_id ──────────────────
raw = kc.instrument_id(TAXO, k=3, knot_n=9, s1_pairing="paired")
new = kc.instrument_id(TAXO, k=3, knot_n=9, s1_pairing="paired", preparation_id=preparation_id())
assert raw["instrument_hash"] == new["instrument_hash"], "换制备不该换仪器"
assert raw["qualification_policy_hash"] == new["qualification_policy_hash"]
assert raw["measurement_procedure_id"] != new["measurement_procedure_id"], \
    ("★ 这正是补它的理由: 两个旧哈希都相同, 只有 measurement_procedure_id 能分辨 "
     "「同一把尺子量了不同的样品」。")

# 反向: 缺任一分量不得凑出一个 id
for bad in (("", "p", "q"), ("i", "", "q"), ("i", "p", ""), (None, "p", "q")):
    try:
        measurement_procedure_id(*bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"反向失败: 缺分量 {bad} 却凑出了 measurement_procedure_id")

# ── 2. 第 1 层: 比较函数抛 typed 异常, 不是裸 RuntimeError ──────────────
A = {"preparation_id": "prep_a", "instrument": {"instrument_hash": "i1", "qualification_policy_hash": "q1"}}
B = {"preparation_id": "prep_b", "instrument": {"instrument_hash": "i1", "qualification_policy_hash": "q1"}}
assert comparability([A, dict(A)])["status"] == COMPARABLE
try:
    comparability([A, B])
except PreparationMismatchError as exc:
    assert exc.preparations == ["prep_a", "prep_b"]
else:
    raise AssertionError("反向失败: 制备不一致却没有抛 PreparationMismatchError")
assert issubclass(PreparationMismatchError, RuntimeError), "保持向后兼容: 旧 except RuntimeError 仍能接住"

# 显式声明 bridge 目的 -> 允许, 但产出物换了种类
bridged = comparability([A, B], comparison_purpose=BRIDGE_PURPOSE)
assert bridged["status"] == NOT_COMPARABLE
assert bridged["allowed_operation"] == ["preparation_bridge_only"]
assert bridged["output_kind"] == PREPARATION_EFFECT_ESTIMATE, \
    "bridge 模式必须产出制备效应估计, 不是普通 delta"

# ── 3. 第 2 层: 结果 schema 缺 comparability.status 即非法 ──────────────
require_comparability_declared({"comparability": {"status": COMPARABLE}})
for bad in ({}, {"comparability": {}}, {"comparability": {"status": "OK"}}):
    try:
        require_comparability_declared(bad)
    except PreparationMismatchError:
        pass
    else:
        raise AssertionError(f"反向失败: 结果缺/错 comparability.status 却被放行: {bad}")

# ── 4. 第 3 层: 即使 catch 掉异常, manifest 也拿不到合法 production 产物 ─
try:
    comparability([A, B])
except PreparationMismatchError:
    pass          # ← 下游把异常吃掉了
v = manifest_preparation_verdict(["prep_a", "prep_b"])
assert v["complete"] is False and v["production_verified"] is False, \
    "★ 反向失败: 吃掉异常之后居然还能拿到 complete=true 的 production artifact"
assert v["errors"], "第 3 层必须留下可读的 error"
vb = manifest_preparation_verdict(["prep_a", "prep_b"], bridge_mode=True)
assert vb["complete"] is True and vb["production_verified"] is False, \
    "bridge run 可以完成, 但不是 production-verified"
assert manifest_preparation_verdict(["prep_a", "prep_a"])["complete"] is True

# manifest.build 真的接了第 3 层(不只是模块里有个函数)
import cce_workflow_manifest as wm  # noqa: E402
src = open(wm.__file__, encoding="utf-8").read()
assert "manifest_preparation_verdict(" in src and "prep_verdict[\"complete\"]" in src, \
    "反向失败: manifest.build 没有真的把第 3 层接进 complete 的计算"

# ── 5. 标定迁移: 判据是逐字节, 不是「制备版本号变没变」 ─────────────────
assert classify_transfer("abc", "abc")["status"] == EXACT_INPUT_IDENTITY
assert classify_transfer("abc", "ab")["status"] == NONTRANSFERABLE_PREPARATION_CHANGED
assert classify_transfer("abc", None)["status"] == NONTRANSFERABLE_PREPARATION_CHANGED, \
    "制备后弃权也是不可迁移 —— 没有有效样本可比"

# ── 6. 钉住 gen4 的真实桥接数 ──────────────────────────────────────────
P = os.path.join(ROOT, "tests", "data", "phase2")
art = json.load(open(os.path.join(P, "preparation_bridge_gen4.json"), encoding="utf-8"))

seen = {}
def _walk(node):
    if isinstance(node, dict):
        if "base_id" in node and "text" in node:
            seen.setdefault(node["base_id"], node["text"])
        for x in node.values(): _walk(x)
    elif isinstance(node, list):
        for x in node: _walk(x)
_walk(json.load(open(os.path.join(P, "panel_manifest.json"), encoding="utf-8")))
for row in json.load(open(os.path.join(P, "qualification_extension_frozen.json"), encoding="utf-8"))["chosen"]:
    seen.setdefault(row["base_id"], row["text"])
live = bridge_calibration_frame(
    [{"item_id": b, "raw_text": t, "prepared_text": structural_gate(t)["subject_text"]}
     for b, t in sorted(seen.items())])

assert live["frame_size"] == art["base_level"]["frame_bases"] == 39
assert live["exact_input_identity"] == art["base_level"]["exact_input_identity"] == 37
assert live["nontransferable"] == art["base_level"]["nontransferable"] == 2
assert sorted(live["rerun_item_ids"]) == art["base_level"]["rerun_bases"]

rl = art["rep_level"]
assert rl["frame_n"] == 312 and rl["old_U_total"] == 9, "frame 重建必须复现历史记录的 U=9/312"
assert rl["reuse_reps"] == 296 and rl["rerun_reps"] == 16
assert rl["reuse_U"] == 1 and rl["rerun_U_old"] == 8, \
    "★ 旧 9 个 U 里 8 个落在被改动的 base 上 —— 两组事件率极不相同, 总体率不可搬"

# ── 7. 反向: 不许拿旧上界冒充新制备的上界 ──────────────────────────────
pi = art["partial_identification"]
assert art["new_frame_status"] == "PENDING_RERUN"
assert pi["lower"]["upper95"] < pi["U_max"] < pi["upper"]["upper95"], \
    "反向失败: 区间没跨越判决线, 那就不该标 PENDING"
assert art["old_frame_for_reference"]["upper95"] == 0.04980
assert "upper95" not in art.get("new_frame", {}), \
    "★ 反向失败: 在重跑之前就给出了新制备下的点估计上界 —— 那是拿旧数冒充新数"

print(f"test_cce_preparation_bridge: OK "
      f"(三层拦截各自见红 | 39 base 中 2 条需重跑 -> 16/312 rep | "
      f"新 U 区间 [{pi['lower']['upper95']}, {pi['upper']['upper95']}] 跨越 U_max={pi['U_max']}, "
      f"判为 PENDING_RERUN)")
