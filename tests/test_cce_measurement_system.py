#!/usr/bin/env python3
"""Measurement System 层的离线闸：Instrument Definition + Qualified Readout。

存在理由(2026-08-18): 那组作废的 A/B, 根因是 **prompt 与采样数一起变了而无人察觉** ——
当时没有「仪器」这个一等概念, 两臂看起来只差一个环境变量。
仪器版本化之后, 那种混淆在构造上不可能发生。

以及: 此前每处扣发都是零散加的, 没有一个地方回答「这次运行哪些读数可用」,
于是不确定性只在一条路上生效(reply_loop 曾照旧发 PASS/FAIL)。

★ 本文件必须出现在 .github/workflows/cce-submit.yml 的硬编码测试命令清单里。
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("MINIMAX_API_KEY", "stub-not-used")

import cce_knot_classify as K      # noqa: E402
import cce_full_run as C           # noqa: E402

TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))

# ── 1. Instrument Definition 覆盖六项，缺一不可 ─────────────────────────────
inst = K.instrument_id(TAXO, k=3, knot_n=5)
spec = inst["spec"]
for f in ("ontology_version", "prompt_sha256", "model", "endpoint",
          "sampling_policy", "aggregation_policy"):
    assert f in spec, f"仪器定义缺 {f}"
assert len(inst["instrument_hash"]) == 16, inst

# ── 2. ★ 采样数变了 → 哈希必须变（这正是那次 A/B 的一半混淆）────────────────
a = K.instrument_id(TAXO, k=3, knot_n=1)["instrument_hash"]
b = K.instrument_id(TAXO, k=3, knot_n=5)["instrument_hash"]
assert a != b, "改采样数必须换哈希 —— 否则 n=1 与 n=5 会被当成同一把尺子"

# ── 3. ★ prompt 变了 → 哈希必须变，且**由模板文本自动导出，忘不掉** ─────────
tpl = K._stage2_template(TAXO)
assert "<TEXT>" in tpl and "<TOPS>" in tpl, "模板必须用哨兵占位, 否则哈希会随被测对象变"
import copy
t2 = copy.deepcopy(TAXO)
t2["knots"][0]["signature"] = {"changed": "yes"}      # 分类学内容进 prompt → 模板变
assert K.instrument_id(t2, k=3, knot_n=5)["instrument_hash"] != b, \
    "prompt 模板内容变了必须换哈希"

# 3b. 反向: 被测文本变化**不得**改变哈希（否则每条内容都成了不同仪器）
assert K._stage2_template(TAXO) == tpl, "模板不含被测内容, 应可重复导出"

# ── 4. 本体版本变了 → 哈希必须变；且该字段必须是真值不是常量 ────────────────
t3 = copy.deepcopy(TAXO); t3["version"] = "9.9.9"
i3 = K.instrument_id(t3, k=3, knot_n=5)
assert i3["instrument_hash"] != b
# 2026-08-18 变异测试发现: 把 ontology_version 写死成常量时上面那条仍然过 ——
# 因为版本号同时出现在 prompt 模板里(【九结签名(冻结 vX)】), 哈希经由 prompt_sha256 仍会变。
# 那是等价变异, 不是测试盲区; 但字段本身必须如实记录, 否则仪器定义会说谎。
assert i3["spec"]["ontology_version"] == "9.9.9", \
    f"ontology_version 必须如实记录被测本体的版本, 不能是常量: {i3['spec']['ontology_version']}"
assert spec["ontology_version"] == TAXO["version"], spec

# ── 5. ★ 跨仪器比较必须被拒绝（那次 A/B 作废的可执行形式）────────────────────
r1 = {"instrument": {"instrument_hash": "aaaa000000000000"}}
r2 = {"instrument": {"instrument_hash": "bbbb000000000000"}}
try:
    K.assert_same_instrument([r1, r2]); raise AssertionError("不同仪器必须被拒绝")
except RuntimeError as e:
    assert "不同仪器" in str(e), e
assert K.assert_same_instrument([r1, dict(r1)]) == "aaaa000000000000"
try:
    K.assert_same_instrument([r1, {}]); raise AssertionError("缺 instrument_hash 必须被拒绝")
except RuntimeError as e:
    assert "不带 instrument_hash" in str(e), e

# ── 6. Qualified Readout：usable / withheld 必须互斥且覆盖 ──────────────────
def run_q(tops, tops_withheld, playbook, reason, knots=None):
    C.MANIFEST.clear()
    C.MANIFEST["s1_readout"] = {"tops": tops, "tops_withheld": tops_withheld}
    C.MANIFEST["s2_knots"] = {"playbook_primary": playbook, "playbook_withheld_reason": reason,
                              "knots": knots or [["display", 0.6]], "n": 5,
                              "top1_mode_share": 0.8, "max_range": 0.1}
    C.qualified({"cce": {"stage2": {"instrument": {"instrument_hash": "hhhh000000000000",
                                                   "spec": {"model": "M3"}}}}})
    return C.MANIFEST["qualified_readout"]

q = run_q({"desire": "控制欲", "need": None}, {"need": "need_vec 超噪声底"}, None, "top1 不稳")
assert "s1.tops.desire" in q["usable_keys"], q
assert "s1.tops.need" in q["withheld"], q
assert "s2.playbook_primary" in q["withheld"], q
assert q["withheld"]["s2.playbook_primary"] == "top1 不稳", q
assert set(q["usable_keys"]) & set(q["withheld"]) == set(), "usable 与 withheld 必须互斥"
assert q["instrument_hash"] == "hhhh000000000000", q

# 6b. ★ 反向: 全部通过时 withheld 必须为空 —— 否则闸永远显示有东西被扣, 等于永久红
q2 = run_q({"desire": "控制欲", "need": "N04"}, None, "让位;被当同侪", None)
assert q2["withheld_count"] == 0, q2
assert "s2.playbook_primary" in q2["usable_keys"], q2

# 6c. ★ 反向: 全部被扣时 usable 里不得残留 —— 否则闸永远显示有东西可用, 等于永久绿
q3 = run_q({"desire": None, "need": None}, {"desire": "超噪声底", "need": "超噪声底"}, None, "top1 不稳")
assert not [k for k in q3["usable_keys"] if k.startswith("s1.tops")], q3
assert "s2.playbook_primary" not in q3["usable_keys"], q3

# ── 7. qualified_readout 必须在链路与契约里逐位对齐 ─────────────────────────
contract = json.loads((ROOT / "config" / "cce_submission_contract_v1.json").read_text(encoding="utf-8"))
for mode, prof in (("reply", "outbound_reply"), ("outbound_post", "outbound_post")):
    got = [f.stage_name for f in C.CHAINS[mode]]
    assert got == contract["profiles"][prof]["stages"], (mode, got)
    assert got[-1] == "qualified_readout", "出口闸必须是链路最后一段"

# ── 8. 本文件必须在 CI 的硬编码执行清单里 ───────────────────────────────────
wf = (ROOT / ".github" / "workflows" / "cce-submit.yml").read_text(encoding="utf-8")
assert "python3 tests/test_cce_measurement_system.py" in wf, \
    "本测试未进 cce-submit.yml 的执行清单 —— 那份清单是硬编码的, 不进去就永不执行"

# ── 9. ★ 仪器边界包含 s1：n 次 s2 抽样必须吃到**不同**的 s1 draw ────────────
# 天花板(2026-08-18 发现): 此前 s2 的 prompt 由 s1 聚合 tops + pvs[0] 的 appraisal 拼成**一份**,
# 一个 rep 内 n 次 s2 抽样共享同一份抖过的 prompt
# ⇒ **s2 的聚合器在数学上碰不到 rep 间方差**, 无论 n 多大。
# 修法: k 份 s1 draw 轮转分发给 n 份 s2 draw。

seen = []
def _spy(prompt, taxo, tag):
    seen.append(prompt)
    return {"knots": [{"key": "display", "intensity": 0.6}], "levers_present": [], "notes": ""}

orig = K._stage2_draw
K._stage2_draw = _spy
try:
    s1_multi = {"k_requested": 3, "draws": [
        {"from_temperature": 0.0, "tops": {"desire": "控制欲"}, "appraisal": {"a": 1}},
        {"from_temperature": 0.3, "tops": {"desire": "确认欲"}, "appraisal": {"a": 2}},
        {"from_temperature": 0.6, "tops": {"desire": "归属欲"}, "appraisal": {"a": 3}},
    ]}
    seen.clear()
    out = K.stage2("some text", s1_multi, TAXO)
finally:
    K._stage2_draw = orig

assert len(seen) == K.KNOT_N, f"应发出 {K.KNOT_N} 次抽样, 实际 {len(seen)}"
assert len(set(seen)) == 3,     f"n={K.KNOT_N} 次抽样必须轮转 3 份不同的 s1 prompt, 实际只有 {len(set(seen))} 份不同 —— "     "全相同就说明 s1 方差仍被冻死在 prompt 里, 天花板没修掉"
assert out["s1_pairing"] == "round_robin_over_3_s1_draws", out["s1_pairing"]
# 三份 prompt 各自带着自己那份 s1 读数，不是同一份
for tag in ("控制欲", "确认欲", "归属欲"):
    assert any(tag in p for p in seen), f"prompt 里应出现 {tag}"

# 9a. ★ 配对策略必须进 instrument_hash —— 改了配对就是换了仪器
h_new = K.instrument_id(TAXO, k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")["instrument_hash"]
h_old = K.instrument_id(TAXO, k=3, knot_n=5, s1_pairing="single_s1_aggregate(legacy)")["instrument_hash"]
assert h_new != h_old, "配对策略变了必须换哈希, 否则新旧读数会被当成同一把尺子"

# 9b. 兼容: 老调用方没有 draws 字段时退回单 prompt, 且策略如实标注为 legacy
seen.clear(); K._stage2_draw = _spy
try:
    out2 = K.stage2("some text", {"k_requested": 3, "tops": {"desire": "控制欲"}, "appraisal": {}}, TAXO)
finally:
    K._stage2_draw = orig
assert len(set(seen)) == 1, "无 draws 时应退回单 prompt"
assert out2["s1_pairing"] == "single_s1_aggregate(legacy)", out2["s1_pairing"]
assert out2["instrument"]["spec"]["sampling_policy"]["s1_pairing"] == "single_s1_aggregate(legacy)",     "legacy 路径必须如实标注, 不能伪装成已修"

# ── 10. stage1 必须真的产出 draws（2026-08-18 变异测试找出的盲区）──────────
# 上面第 9 节是手工构造 draws 喂给 stage2 的, 从没断言 stage1 会产出它 ——
# 于是「stage1 不再暴露逐 draw」这个变异跑不红。补上。
_NL = ["desire_vec", "need_vec", "emotion_vec", "action_vec"]
_calls = {"n": 0}
def _fake_parse(mkey, case, T, tag):
    _calls["n"] += 1
    i = _calls["n"]
    pv = {L: [1.0 / (i + j + 1) for j in range(3)] for L in _NL}
    pv["appraisal"] = {"draw": i}
    pv["chain_trace"] = f"trace{i}"
    return "raw", "p", pv, {}, True

_orig_parse, _orig_tl = K.call_parse, K.top_label
K.call_parse = _fake_parse
K.top_label = lambda vec, labels: f"{labels[0]}@{round(vec[0], 3)}"   # 让逐 draw 的 top 可区分
try:
    s1 = K.stage1("text", "ctx", 3)
finally:
    K.call_parse, K.top_label = _orig_parse, _orig_tl

assert "draws" in s1, "stage1 必须暴露逐 draw —— 否则 stage2 无从配对, 天花板照旧"
assert len(s1["draws"]) == s1["k_ok"] == 3, s1["k_ok"]
for dr in s1["draws"]:
    assert {"from_temperature", "tops", "appraisal"} <= set(dr), dr
# ★ 逐 draw 必须**各不相同**, 否则配对形同虚设
assert len({json.dumps(d["appraisal"], sort_keys=True) for d in s1["draws"]}) == 3,     "三份 draw 的 appraisal 必须互不相同, 相同就说明没有真正逐 draw 保留"
assert len({d["from_temperature"] for d in s1["draws"]}) == 3, s1["draws"]
# 聚合项仍在, 且 draws 不替代它们
assert "layers" in s1 and "tops" in s1 and "within_js" in s1

print("test_cce_measurement_system: OK (仪器六项 / 哈希随 prompt·n·本体·配对变 / 跨仪器拒比 / usable×withheld 互斥 / stage1 产出 draws / s2 配对轮转 / 链路对齐 / CI 自防)")
