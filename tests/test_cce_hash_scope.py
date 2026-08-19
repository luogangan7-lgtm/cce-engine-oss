#!/usr/bin/env python3
"""仪器哈希 vs 资格协议哈希：判据是「改它之后已采集的 raw draw 还能不能用」。

为什么拆(2026-08-19, 外部评审指出 + 我按可操作判据重划):
  此前 support_rule / intensity_stat / abstention / k_valid 这些**可从 draw ledger 重算**
  的策略也进了 instrument_hash ⇒ 每修一次资格协议就白白作废一次仪器标定,
  而重标定要**真投料**。代价完全不对等。

判据(比「prompt vs schema」更可检验):
  改它 ⇒ 已采集 draw 作废、必须重投料 → instrument
  改它 ⇒ 可从 draw ledger 重算       → qualification policy
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K  # noqa: E402

TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
BASE = dict(k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")


def _id(**kw):
    return K.instrument_id(TAXO, **{**BASE, **kw})


cur = _id()
assert set(cur) >= {"instrument_hash", "qualification_policy_hash", "spec", "hash_scope"}
assert cur["instrument_hash"] != cur["qualification_policy_hash"]

# ── 1. ★ 改**决定 draw 的东西** ⇒ instrument_hash 必须变 ────────────────────
for kw, why in (({"k": 5}, "s1 的 k 是温度阶梯, 改它就是换采样"),
                ({"knot_n": 10}, "s2 的 n 决定抽多少次"),
                ({"s1_pairing": "single_s1_aggregate(legacy)"}, "配对决定哪份 s1 喂哪次 s2")):
    assert _id(**kw)["instrument_hash"] != cur["instrument_hash"], f"{kw} 应换仪器: {why}"

# ── 2. ★★ 改**只影响解读的东西** ⇒ instrument_hash 必须**不变** ─────────────
#    这是本次重划的全部意义: 资格协议变更不得作废仪器标定。
_orig = K.SUPPORT_RULE
try:
    K.SUPPORT_RULE = "occur * 3 > n * 2"      # 一条完全不同的支持度规则
    changed = _id()
finally:
    K.SUPPORT_RULE = _orig
assert changed["instrument_hash"] == cur["instrument_hash"], \
    "★ 改 support_rule 不该换仪器 —— 它可从 draw ledger 重算, 不需要重新投料"
assert changed["qualification_policy_hash"] != cur["qualification_policy_hash"], \
    "★ 但资格协议哈希必须变, 否则等于没记录这次变更"

# ── 3. 作用域声明必须与实际一致(防注释与实现漂移) ───────────────────────────
sc = cur["hash_scope"]
assert "aggregation_policy" in sc["qualification_policy"], "聚合策略归资格侧"
assert "aggregation_policy" not in sc["instrument"], "聚合策略不得再进仪器侧"
for f in ("s1_prompt_sha256", "s2_prompt_sha256", "model", "endpoint", "sampling_policy"):
    assert f in sc["instrument"], f"{f} 必须在仪器侧 —— 改它非重投料不可"
assert "重算" in sc["criterion"] or "raw draw" in sc["criterion"]

# ── 4. spec 形状不得变 —— calibration 的 depends_on 路径依赖它 ──────────────
import cce_ksep as KS  # noqa: E402
for path in KS.PAIR1_NULL_CALIBRATION_STATISTIC["depends_on"]:
    node = cur["spec"]
    for part in path.split("."):
        assert isinstance(node, dict) and part in node, \
            f"★ depends_on 路径 {path} 在 spec 里断了 —— 拆哈希不得改 spec 形状"
        node = node[part]

# ── 5. 资格协议本身必须写下来, 不能只存在于代码分支里 ───────────────────────
qp = cur["spec"]["qualification_policy"]
assert qp["k_valid_min"] == 2 and qp["insufficient_replicates"] == "WITHHOLD"
assert "insufficient_replicates" in qp["statuses"] and "abstain" in qp["statuses"]

print("test_cce_hash_scope: OK (改采样→换仪器 / 改聚合→不换仪器但换协议 / "
      "作用域自洽 / depends_on 路径完好 / 协议已成文)")

# ── 6. ★★ 重划的目的检验: gen3 期的标定必须能搬到 gen4 ─────────────────────
# gen3→gen4 只动了哈希作用域, 物理仪器全同 ⇒ 标定应当可搬。
# 若不可搬, 这次重划就白做了(那正是它要修的病)。
_gen3_cal = {
    "depends_on": ["s1_prompt_sha256", "s2_prompt_sha256", "model", "endpoint",
                   "ontology_version", "sampling_policy.s2_n", "sampling_policy.s1_pairing"],
    "snapshot": {"s1_prompt_sha256": "eadcdcdac46a5180",
                 "s2_prompt_sha256": "b8d0f60d66d10f12",
                 "model": cur["spec"]["model"], "endpoint": cur["spec"]["endpoint"],
                 "ontology_version": cur["spec"]["ontology_version"],
                 "sampling_policy.s2_n": 5,
                 "sampling_policy.s1_pairing": "round_robin_over_3_s1_draws"},
}
t = K.calibration_transfers(_gen3_cal, TAXO, **BASE)
assert t["transfers"] is True, \
    f"★ gen3 期标定必须能搬到 gen4(只重划了哈希作用域, 物理仪器全同): {t}"
# 而 gen1 期的标定仍不可搬(s1 prompt 在 gen3 变过)
import cce_ksep as _KS2  # noqa: E402
assert K.calibration_transfers(_KS2.PAIR1_NULL_CALIBRATION_STATISTIC, TAXO,
                               **BASE)["transfers"] is False
# 谱系必须记着 gen4 与 gen3 物理同一
_g4 = next(g for g in K.INSTRUMENT_LINEAGE if g["gen"] == 4)
assert _g4["s1_prompt_sha256"] == "eadcdcdac46a5180" and "物理仪器与 gen3 完全相同" in _g4["note"]
print("  重划目的已验证: gen3 标定可搬到 gen4 / gen1 标定仍不可搬")
