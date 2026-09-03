#!/usr/bin/env python3
"""本体层铁律 1/2/4/25 的闸 —— 每条都由**实际注入一次违例**驱动, 不是补装饰。

2026-09-03 逐条注入的实测结果:
  铁律 1  observation() 空 evidence_ref + 空 provenance 照样产出 assertion="observed"  ⇒ 有洞, 已补
  铁律 2  单个 observation 送进 assemble 产出 events=[] —— 行为本来就对, 但**没有测试钉住** ⇒ 本文件钉
  铁律 3  assemble 原样透传调用方自带的 events ⇒ 状态断言可冒充事件                      ⇒ 有洞, 已补
          ★ 前两版闸都造窄了: ① assertion=="derived" 当判别器 -> 拦红真实的 evt:shot-cut;
            ② 补 event_type -> 又拦红 evt:reinforcement(inferred 也是合同里的合法值)。
            事件**形状**本来就由 cce_contract.validate_case 管, 不该重造。
            合同没管的只有「事件带状态层字段」, 铁律 3 只补这一条。
            **闸开太宽和开太窄一样是缺陷。**
  铁律 4  admit('outcome', {'deal':1, 'knots':{...}}) 曾放行 —— 带一个 owned key 就能夹带状态 ⇒ 有洞, 已补
  铁律 25 coverage_scope="" 曾放行 —— 覆盖率没有框 ⇒ 有洞, 已补
  铁律 8  已由 distribution 账的 creates_identified_subjects 拦下(指名那条规则) ⇒ 本来就有闸

★ 注入时必须断言**是哪条规则拦的**。本项目当天已六次栽在「抛了异常 != 我说的那条规则生效」。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cce_event_assemble as EA          # noqa: E402
import cce_foundation_adapter as FA      # noqa: E402
import cce_population as PP              # noqa: E402
from cce_ledger import admit, LedgerAdmissionError, STATE_KEYS  # noqa: E402


def raises_with(fn, must):
    try:
        fn()
    except Exception as e:
        assert must in str(e), f"拦了但理由不对: 需含 {must!r}, 实际 {str(e)[:110]}"
        return
    raise AssertionError(f"★ 未拦: 期望含 {must!r} 的错误")


# ── 铁律 1: Raw != Observation ────────────────────────────────────────
raises_with(lambda: FA.observation("r1", "text", "", {"m": "x"}), "Raw != Observation")
raises_with(lambda: FA.observation("r1", "text", "f.txt", {}), "观察必须说得出来路")
ok = FA.observation("r1", "text", "f.txt", {"method": "read"})
assert ok["assertion"] == "observed" and ok["evidence_refs"] == ["f.txt"]

# ── 铁律 2: Observation != Event ──────────────────────────────────────
#    单个 observation **不得**自动变成 event。行为本来就对, 这里把它钉死。
case = {"observations": [FA.observation("o1", "text", "f.txt", {"method": "read"}, text="hi")],
        "content_id": "c1"}
ev = EA.assemble(case)
assert ev["events"] == [], \
    "★ 一条 observation 被提升成了 event —— 观察不是事件, 事件要交集/共现才成立"
assert ev["observations"], "observation 本身必须原样留着, 不能被吃掉"

# ── 铁律 3: Event != State ────────────────────────────────────────────
#    ★ 实测 assemble 会**原样透传**调用方自带的 events ⇒ 一条贴着 assertion="observed"
#      的状态断言能直接冒充事件活下来。这同时说明上面那条铁律 2 的钉子
#      **只在不自带 events 时成立** —— 两个方向都要堵。
raises_with(lambda: EA.assemble({"observations": case["observations"], "content_id": "c",
                                 "events": [{"id": "e1", "assertion": "derived",
                                             "event_type": "x", "knots": {"a": 1}}]}), "铁律 3")
raises_with(lambda: EA.assemble({"observations": case["observations"], "content_id": "c",
                                 "events": [{"id": "e1", "assertion": "observed",
                                             "event_type": "x", "state": {"a": 1}}]}), "铁律 3")
# ★ 正向不得误伤: observed 与 inferred 都是合同里的合法 assertion。
#   我第一版闸把两者各拦红过一次 —— 事件的**形状**由 cce_contract 管, 这里只管状态字段。
for _a in ("observed", "derived", "inferred"):
    _ok = EA.assemble({"observations": case["observations"], "content_id": "c",
                       "events": [{"id": f"evt:x:{_a}", "assertion": _a,
                                   "event_type": "shot_cut_observed"}]})
    assert len(_ok["events"]) == 1, f"★ 合法的 {_a} 事件被误伤"
# 形状不合法的事件由合同层拦(分层, 不重造)
from cce_contract import VALID_ASSERTIONS  # noqa: E402
assert {"observed", "derived", "inferred"} <= set(VALID_ASSERTIONS), VALID_ASSERTIONS

# ── 铁律 4: State != Behavior ─────────────────────────────────────────
#    ★ 光靠「outcome 必须含 owned key」拦不住 —— 带一个 deal 就能夹带。
raises_with(lambda: admit("outcome", {"deal": 1, "knots": {"a": .8},
                                      "acknowledges_first_entry": True}), "铁律 4")
raises_with(lambda: admit("distribution", {"impressions": 1, "intensity": .9,
            "provenance": {"method": "manual_backend_read", "backend_ref": "x"},
            "acknowledges_first_entry": True}), "铁律 4")
assert STATE_KEYS >= {"knots", "intensity", "weight", "mass", "quadrant"}
# 正向不得误伤
assert admit("content", {"knots": {"a": .8}, "instrument_hash": "h"})["admitted"]
assert admit("outcome", {"deal": 1, "acknowledges_first_entry": True})["admitted"]

# ── 铁律 8: Individual != Broadcast Target(本来就有闸, 钉住防回退) ─────
raises_with(lambda: admit("distribution", {"impressions": 50000,
            "creates_identified_subjects": True,
            "provenance": {"method": "manual_backend_read", "backend_ref": "x"},
            "acknowledges_first_entry": True}), "缺抽样框")

# ── 铁律 25: Coverage 是某个已声明框的分数 ────────────────────────────
M = [{"actor_ref": f"user_{i}", "distribution": {"a": 0.5, "b": 0.5}} for i in range(3)]
raises_with(lambda: PP.build_population_subject(M, ""), "铁律 25")
raises_with(lambda: PP.build_population_subject(M, "   "), "铁律 25")
r = PP.build_population_subject(M, "r/X 2026-08 活跃发帖者")
cov = r["mode_coverage"]
assert cov["denominator"] == "known_member_count", cov
assert cov["not_denominator"], "★ 必须写明分母**不是**什么 —— 否则会被读成占目标人群的比例"

print("test_cce_ontology_iron_laws: OK "
      "(1 Raw!=Observation · 2 Observation!=Event · 3 Event!=State · 4 State!=Behavior · "
      "8 Individual!=Broadcast · 25 Coverage 有框 | "
      "每条都断言是**哪条规则**拦的, 不接受「抛了异常」当通过)")
