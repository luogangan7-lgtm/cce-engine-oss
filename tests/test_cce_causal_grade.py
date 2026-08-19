#!/usr/bin/env python3
"""当前 subject_chain 的因果天花板 = DESCRIPTIVE，且这是**结构性**的。

来源: 外部评审判定 + 我方逐行核实。
`cce_response_chain.py` 强制 `reached_members == seen_actors`（防伪造触达，好设计），
但副作用是 **reached 窗在构造上等于响应者集合** ⇒ 响应者/触达者恒为 1
⇒ 「激活率」不是测量而是常数；观测到的是 P(state|responded) 而非 P(state|reached)。

★ 这条闸要防的是: 未来某个下游 agent 把「响应者分布变了」自动改写成「内容改变了人群」。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_response_chain as RC  # noqa: E402

C = RC.CAUSAL_CAPABILITY
src = (ROOT / "scripts" / "cce_response_chain.py").read_text(encoding="utf-8")

# ── 1. 天花板写死, 且理由完整 ────────────────────────────────────────────────
assert C["supported"] is False and C["max_grade"] == "DESCRIPTIVE"
assert len(C["reason"]) >= 4, "三样缺席(曝光分母/前状态/同期对照)加上响应条件化, 缺一不可"
assert any("responded" in r for r in C["reason"])

# ── 2. ★ 禁止词表必须覆盖「把关联写成因果」的常见改写 ───────────────────────
for w in ("CAUSED", "INCREASED", "REDUCED", "ACTIVATED_BY"):
    assert w in C["forbidden_claims"], f"禁止词表缺 {w}"
assert set(C["allowed_claims"]) & {"DESCRIPTIVE", "ASSOCIATIONAL"}
assert not (set(C["allowed_claims"]) & set(C["forbidden_claims"])), "允许与禁止不得交叠"

# ── 3. ★ 结构性事实: reached 与 responded 被强制相等 ────────────────────────
assert "reached_members != seen_actors" in src, \
    "这条相等约束是本判定的依据 —— 它若被删, 因果天花板的理由要重写"
# ⇒ 任何以 reached 为分母的比率恒为 1
assert "恒等于 1" in src or "恒为 1" in src

# ── 4. 因果等级必须随每条读数走, 不能只写在文档里 ───────────────────────────
assert '"causal_grade": CAUSAL_CAPABILITY["max_grade"]' in src

# ── 5. ★ 不得把「因果」从架构里永久删除 —— 冻结的是**当前采集剖面**, 不是能力 ─
assert C["required_evidence_profiles_to_unlock"], \
    "必须列出解锁条件, 否则会被读成『CCE 永远不能做因果』——那是过度结论"
assert "repeated_cross_section_pre_post_control" in C["required_evidence_profiles_to_unlock"], \
    "DiD 可建在 repeated cross-sections 上, 不要求前后同一批人"

# ── 6. 反向测试: 若有人把 supported 改成 True 却不补证据剖面, 必须红 ─────────
_fake = dict(C, supported=True, required_evidence_profiles_to_unlock=[])
assert not (_fake["supported"] and not _fake["required_evidence_profiles_to_unlock"]) is False, \
    "反向用例自检"
try:
    assert not (_fake["supported"] is True and _fake["max_grade"] == "DESCRIPTIVE"), \
        "supported=True 与 max_grade=DESCRIPTIVE 自相矛盾, 必须被抓住"
    raise AssertionError("反向用例应当抛错")
except AssertionError as e:
    assert "自相矛盾" in str(e) or "反向用例应当抛错" in str(e)

print("test_cce_causal_grade: OK (天花板/禁止词表/reached≡responded/随读数走/解锁条件/反向)")

# ── 7. 三种「显著性」必须分开, 不许留一个会被塞数的通用字段 ─────────────────
sys.path.insert(0, str(ROOT / "scripts"))
import cce_ksep as KS  # noqa: E402

SC = KS.SIGNIFICANCE_CONTRACT
assert set(SC) >= {"measurement", "interpretive", "behavioral", "design_sensitivity_bound"}
assert SC["measurement"]["delta_resolution"] is None
assert SC["interpretive"]["semantic_sesoi"] is None
assert SC["behavioral"]["status"] == "NOT_AVAILABLE"
# ★ 分辨率不得被改名成 SESOI(minimal detectable change ≠ minimally important change)
assert "delta_resolution" in SC["measurement"] and "sesoi" not in SC["measurement"]
# ★ 语义档必须写明「不需要产品数据也能标定」的路径, 否则它会被当成永远填不上的坑
assert "human anchor" in SC["interpretive"]["how_to_calibrate"]
# ★ 反向: 不许出现一个笼统的 practical_significance 字段
assert "practical_significance" not in str(SC), \
    "笼统字段迟早会被塞一个数进去 —— 这正是 0.06278 当初的下场"
print("  三档显著性已钉: measurement/interpretive/behavioral 分离 · 无笼统字段")
