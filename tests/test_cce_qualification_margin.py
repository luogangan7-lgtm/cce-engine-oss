#!/usr/bin/env python3
"""资格 margin（ADOPT 闸）—— 2026-08-19 外部评审定值后的守卫。

守三件事：
  1. margin 的**出处**是 ENGINEERING_BUDGET，不是「文献证明 5% 缺失安全」。
     缺失比例本身不决定偏倚可否接受（取决于 missingness mechanism），
     不存在普适的「低于 X% 就没事」阈值。写成文献依据就是伪证。
  2. 闸用**精确单侧 95% 上界**，不是点估计。1/48 = 2.1% 看着 <5%，
     但上界 9.5% —— 用点估计会把一个远不够精确的仪器放进生产。
  3. margin 属于 **qualification policy** 哈希域，不属于 instrument ——
     改它不作废任何已采集的 draw（判据：raw draw 还能不能用）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K  # noqa: E402

M = K.QUALIFICATION_MARGIN

# ── 1. 定值与出处 ────────────────────────────────────────────────────────────
assert M["U_max"] == 0.05 and M["F_max"] == 0.0
assert M["bound"] == "exact_one_sided_95_upper"
assert M["provenance"] == "ENGINEERING_BUDGET", \
    "★ 不许标成文献依据 —— 缺失比例本身不决定偏倚可否接受，没有普适阈值"
assert "LITERATURE" not in M["provenance"]

# ── 2. 精确上界的算术（零事件闭式 + x>0 二分）──────────────────────────────
assert abs(K.binom_upper(0, 48) - 0.06050) < 1e-4      # gen3 的 0/48
assert abs(K.binom_upper(0, 59) - 0.04951) < 1e-4      # 刚好过闸
assert K.binom_upper(0, 58) > 0.05 >= K.binom_upper(0, 59), \
    "n=59 是零事件下过闸的最小 n；58 必须还不够"
assert abs(K.binom_upper(1, 48) - 0.09506) < 1e-4
assert abs(K.binom_upper(2, 72) - 0.08487) < 1e-4      # 历史探索性 2/72 同样不够
assert K.binom_upper(0, 672) < 0.005                   # Phase 2 的 24×7×4 规模

# ── 3. 判决 ─────────────────────────────────────────────────────────────────
v = K.adopt_verdict(n_qualified=48, n_unqualified=0, n_parse_failed=0)
assert v["verdict"] == "ADOPT_PENDING_PRECISION", "0/48 上界 6.05% > 5% ⇒ 不许 ADOPT"
assert v["zero_event_n_needed"] == 59

v = K.adopt_verdict(n_qualified=59, n_unqualified=0, n_parse_failed=0)
assert v["verdict"] == "ADOPT" and v["u_upper95"] <= 0.05

# ★ 反向：点估计会放它过，上界不会。这一条正是加 bound 的理由
v = K.adopt_verdict(n_qualified=47, n_unqualified=1, n_parse_failed=0)
assert v["u_hat"] < 0.05 < v["u_upper95"]
assert v["verdict"] == "ADOPT_PENDING_PRECISION", \
    "★ 点估计 2.1% < 5% 但上界 9.5% —— 用点估计做闸就是把不确定性当成达标"

# F 是范畴性规则：一个都不许
assert K.adopt_verdict(200, 0, 1)["verdict"] == "ROLLBACK"
# 阴性通道自检没过 ⇒ 仪器在错报 schema，任何 U 都不算数
assert K.adopt_verdict(200, 0, 0, channel_live=False)["verdict"] == "ROLLBACK"

# 集中度：总体达标但集中在少数 base ⇒ 不许全局 ADOPT
v = K.adopt_verdict(n_qualified=670, n_unqualified=2, n_parse_failed=0,
                    per_base={"b07": 2})
assert v["verdict"] == "ADOPT_WITH_RESTRICTIONS" and v["concentration_flag"] == ["b07"]
# 同样 2 个 unqualified 但分散在两个 base ⇒ 不触发
v = K.adopt_verdict(670, 2, 0, per_base={"b07": 1, "b11": 1})
assert v["verdict"] == "ADOPT" and v["concentration_flag"] == []

# ── 4. 哈希域：改 margin 只动 qualification policy，不动 instrument ────────
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
BASE = dict(k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")
before = K.instrument_id(TAXO, **BASE)
assert before["spec"]["qualification_policy"]["margin"] is K.QUALIFICATION_MARGIN
K.QUALIFICATION_MARGIN = dict(M, U_max=0.10)
try:
    after = K.instrument_id(TAXO, **BASE)
    assert after["instrument_hash"] == before["instrument_hash"], \
        "★ 改 margin 不该作废仪器标定 —— 已采集的 draw 完全能重算"
    assert after["qualification_policy_hash"] != before["qualification_policy_hash"], \
        "★ 但它必须进资格协议哈希，否则可以静默改闸"
finally:
    K.QUALIFICATION_MARGIN = M

print("test_cce_qualification_margin: OK "
      "(出处/精确上界/59 的最小 n/点估计反向/F 范畴性/集中度/哈希域)")
