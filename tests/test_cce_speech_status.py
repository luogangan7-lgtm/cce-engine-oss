#!/usr/bin/env python3
"""语音层完备性: `speech=true` 曾把两种完全不同的情况压成一个 true。

## 实测发现的缺陷(ASR_SILENT_FAILURE_IN_HISTORICAL_ARTIFACTS_GEN1, n=40 预注册)
历史产物 275 份里 **138 份转写不足 20 字**, 其中至少 **22.5%** 人声能量占比 >= 0.5
(即**确有口播**), 却照样标 speech=true ⇒ **9/40 是假的 ok**。
全集外推 ≈ **31 份**静默失败被标为完备。而 media_ingest 链正是从这些产物跑出 17726 条 observation 的。

## 怎么撞上的
不是我去找它。**字幕交叉核验的非退化闸**触发(召回中位 0.0098 落在预注册的 (0.05,0.95) 之外),
按规则「先查仪器」, 查下去才发现: 参照方没坏, **被参照的 ASR 才是坏的**。

## ★ 一个自己打脸的细节
最初 6 份抽查的短转写组人声中位 **0.472**, 看着像「一半全坏」;
预注册的 40 份给出 **0.178**。**抽查用来发现问题, 不能用来估比例。**
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_video_parse import (_speech_status, TRANSCRIPT_MIN_CHARS_PER_SEC,
                             TRANSCRIPT_RATE_PROVENANCE)

V = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_silent_failure.json"),
                   encoding="utf-8"))

# ── ① 五态必须各自可达且互不混 ──────────────────────────────────────
cases = {
    "missing_no_capability": ({"present": False}, None),
    "present":               ({"present": True, "transcript": "这是一段正常长度的转写"}, 10),
    "absent_verified":       ({"present": True, "transcript": "嗯。", "★vocals_share": 0.05}, 60),
    "missing_parse_failed":  ({"present": True, "transcript": "嗯。", "★vocals_share": 0.96}, 60),
    "not_available":         ({"present": True, "transcript": "嗯。"}, 60),
}
for want, (a, d) in cases.items():
    got = _speech_status(a, d)["status"]
    assert got == want, f"★ {want} 不可达: 实得 {got}"

# ★ 最关键的一条: 「查不了」不许写成「查过没有」
nv = _speech_status({"present": True, "transcript": "嗯。"}, 60)
assert nv["status"] == "not_available" and "查不了不等于查过没有" in nv["why"], nv

# ── ② 界必须是**按时长**的, 且原始量随状态带出 ─────────────────────
short_ok = _speech_status({"present": True, "transcript": "你好呀"}, 3)     # 3 秒 3 字
long_bad = _speech_status({"present": True, "transcript": "你好呀", "★vocals_share": 0.9}, 178)
assert short_ok["status"] == "present", "★ 3 秒 3 字是正常的 —— 绝对字数阈值会误杀"
assert long_bad["status"] == "missing_parse_failed", "★ 178 秒 3 字且人声高, 必须判失败"
for r in (short_ok, long_bad):
    for k in ("chars", "duration_s", "chars_per_sec", "★rate_gate", "★rate_gate_provenance"):
        assert k in r, f"★ 原始量 {k} 必须随状态带出, 下游要能自行重判"
assert TRANSCRIPT_RATE_PROVENANCE == "ENGINEERING_BUDGET", \
    "★ 这个界是工程预算不是标定阈值, 出处必须如实标"

# ── ③ 判决与产物一致, 且 MIXED 的两半都要报 ────────────────────────
assert V["decision"] == "MIXED", V["decision"]
assert V["separable"], "★ 两组人声分布不可分 ⇒ 结论不成立"
assert 0.10 <= V["failure_rate_lower_bound"] < 0.30, \
    f"★ 判决与数值不符: {V['failure_rate_lower_bound']} 不在 MIXED 区间"
assert "两种成因都有" in V["★both_causes_present"] and "不许只报一种" in V["★both_causes_present"]
assert "只会更高" in V["★why_lower_bound"], "★ 只数 vocals>=0.5 的 ⇒ 真实失败率只会更高"
assert V["mislabeled_speech_true"] > 0, "★ 假 ok 的数量是这条缺陷的核心证据"

# ── ④ 抽查不能估比例, 这条教训要留着 ────────────────────────────────
assert "不能用来估比例" in V["★spot_check_was_misleading"], \
    "★ 6 份抽查给 0.472 而 40 份给 0.178 —— 这个自打脸要留在产物里"

# ── ⑤ 兼容别名 speech 仍在, 但语义已缩小 ────────────────────────────
import inspect
src = inspect.getsource(sys.modules["cce_video_parse"])
assert "'speech': audio.get('present', False),   # 兼容别名: 只表示**音轨在不在**" in src, \
    "★ speech 保留为兼容别名, 但必须写明它只表示音轨在不在"

print(f"test_cce_speech_status: OK (五态各自可达且互不混 | 「查不了」不许写成「查过没有」 | "
      f"界按**字/秒**(3秒3字=present, 178秒3字+人声高=failed), 出处 {TRANSCRIPT_RATE_PROVENANCE}, "
      "原始量随状态带出 | "
      f"实测 {V['decision']}: 失败率下界 {V['failure_rate_lower_bound']:.1%}, "
      f"假 ok {V['mislabeled_speech_true']}/{V['n_short']} | "
      "★ 6 份抽查 0.472 vs 40 份 0.178 —— 抽查不能估比例)")
