#!/usr/bin/env python3
"""K1 首次真实判定的结果, 以及它对生成物闸的下游后果。

§44.9 P4 的验收 gate 是「K1 四项全过」。2026-09-01 首次真实判定: **FAIL**(两项不达标)。
本文件钉住这个结果, 并钉住它的下游: 引用了 K1 未达标层读数的生成物必须被拦
(§44.9 P7 的反向测试点名的那一条 —— 此前无法执行, 因为 K1 从没判定过)。
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "probes"))

from cce_strategy_gate import check_knot_readout_claims  # noqa: E402
from k1_gate import CRIT, judge  # noqa: E402

P = os.path.join(ROOT, "tests", "data", "phase2")
V = json.load(open(os.path.join(P, "k1_reliability_verdict.json"), encoding="utf-8"))
SPEC = json.load(open(os.path.join(P, "k1_reliability_prereg.json"), encoding="utf-8"))
ROWS = [json.loads(l) for l in
        open(os.path.join(P, "k1_reliability_checkpoint.jsonl"), encoding="utf-8") if l.strip()]

# ── 1. 判定可从原始行重算, 不是手写进产物的 ────────────────────────────
usable = [r for r in ROWS if not r.get("infra_suspected") and r.get("knots")]
assert len(usable) == 8 and len(ROWS) == 8, f"n 必须是 8, 实测 {len(usable)}/{len(ROWS)}"
code, rep = judge(usable)
assert rep["verdict"] == V["verdict"] == "FAIL", \
    f"★ 产物里的判决与原始行重算不一致: {V['verdict']} vs {rep['verdict']}"
assert sorted(rep["failed"]) == sorted(V["failed"])
assert code == 1

# ── 2. 前登记与实跑一致: 仪器、文本、n ─────────────────────────────────
assert SPEC["instrument"]["must_equal"] == "565470cf26c16d01" == V["instrument_hash"]
assert V["sha"] == SPEC["design"]["text_sha256"]
assert {r["sha"] for r in usable} == {SPEC["design"]["text_sha256"]}, \
    "同项重跑: 8 次必须是同一个输入指纹"
assert V["n"] == SPEC["design"]["n"] == 8

# ── 3. 四项判据逐条钉住(不是只钉一个总判决) ────────────────────────────
by = {c["name"]: c for c in V["checks"]}
got = {n: c["pass"] for n, c in by.items()}
assert list(got.values()) == [True, False, False, True], \
    f"★ 四项的通过情况变了: {got} —— 变了就说明重算口径漂了"
assert V["ranges"]["reward"] == 0.4 and max(V["ranges"].values()) == 0.4
assert len(set(V["tops"])) == 1 and V["tops"][0] == "pain_seek", "top-1 应当 8/8 一致"
assert CRIT["range_max"] == 0.10 and max(V["ranges"].values()) > CRIT["range_max"]

# ── 4. ★ 分层结论: top-1 稳, 强度不稳 —— 两者不许混为一谈 ──────────────
#    铁律 24: 九结 absolute intensity 与 relative composition 必须分离。
top1_check = [c for c in V["checks"] if "top-1" in c["name"]][0]
range_check = [c for c in V["checks"] if "极差" in c["name"]][0]
assert top1_check["pass"] and not range_check["pass"], \
    "★ 本轮的判定形态就是「首结稳、强度不稳」; 变成同进同退说明重算错了"

# ── 5. 下游: 强度层读数被拦, 首结层放行 ────────────────────────────────
assert check_knot_readout_claims("首结是 [[knot:pain_seek]]。") == [], \
    "★ 反向失败: top-1 一致 8/8, 首结层面的陈述不该被拦"
for bad in ("A 稿 [[knot_intensity:display=0.85]] 高于 B 稿",
            "两稿的 [[knot_delta:reward]] 差 0.2"):
    iss = check_knot_readout_claims(bad)
    assert iss and "K1 未达标" in iss[0], \
        f"★ §44.9 P7 反向失败: 引用了 K1 未达标层的读数却没被拦: {bad}"

# ── 6. 反向: K1 从没判定过时, 强度引用也必须被拦(不许默认放行) ──────────
with tempfile.TemporaryDirectory() as td:
    absent = os.path.join(td, "nope.json")
    iss = check_knot_readout_claims("[[knot_intensity:reward=0.9]]", verdict_path=absent)
    assert iss and "从未判定过" in iss[0], \
        "★ 反向失败: 没有 K1 判定时默认放行了 —— 缺判定不等于判定通过"
    # 反向: 伪造一个 PASS 判定 -> 放行(证明放行确实由判定驱动, 不是恒拦)
    passing = os.path.join(td, "pass.json")
    json.dump({**V, "verdict": "PASS", "failed": []}, open(passing, "w"), ensure_ascii=False)
    assert check_knot_readout_claims("[[knot_intensity:reward=0.9]]",
                                     verdict_path=passing) == [], \
        "★ 闸必须由 K1 判定驱动; 恒拦的闸和恒放的闸一样没有信息量"

# ── 7. 选文规则必须是与稳定性无关的确定性规则, 且范围限制写在产物里 ─────
assert "字典序第一" in V["selection_rule"]
assert "不能在「没有读数」的文本上测读数稳定性" in SPEC["selection_rule"]["why_this_rule"]
assert "只对「稳定合格的真人文本」成立" in V["scope_limit"], \
    "★ 必须写明本次 K1 不覆盖边缘文本 —— 否则会被读成仪器整体过关/不过关"

print(f"test_cce_k1_verdict: OK "
      f"(n=8 同指纹 · 判定 {V['verdict']} 可从原始行重算 · "
      f"四项 通过/不通过 = {sum(got.values())}/4 · "
      f"首结 8/8 稳但单结极差 {max(V['ranges'].values())} 超线 | "
      "强度层引用被拦、首结层放行、缺判定不默认放行 —— 各自见红)")
