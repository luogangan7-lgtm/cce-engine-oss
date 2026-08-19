#!/usr/bin/env python3
"""[2/4] 弃权：「读不出」必须能被表达，且不能伪装成第十个结。

外部源码审计确认「无空读数」是 **contract-impossible**，三处阻断（我逐一核实过）：
  1. stage1 prompt 要求对「这一个人」反推 —— 从未授权模型判断有没有主体
  2. stage2 `and d["knots"]` ⇒ `{"knots":[]}` 被当成解析失败去重试
  3. ingest `if total <= 0: raise` ⇒ 零分布在契约上不可能

本次打通 2 与 3。**1 未动** —— 改 s1 prompt 会再换一次仪器并使当日标定失效，属独立决策。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K      # noqa: E402
import cce_response_chain as RC    # noqa: E402

TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))


def _agg(specs):
    draws = [{"knots": [{"key": k, "intensity": v, "evidence_quote": "", "signature": {}}
                        for k, v in sp.items()], "levers_present": [], "notes": ""}
             for sp in specs]
    orig = K._stage2_draw
    K._stage2_draw = lambda p, t, tag: draws[int(tag[1:]) % len(draws)]
    try:
        return K._stage2_aggregate("x", TAXO, n=len(draws))
    finally:
        K._stage2_draw = orig


# ── 1. 全体弃权 ⇒ abstain, 且**不产出任何结** ───────────────────────────────
r = _agg([{}, {}, {}, {}])
assert r["measurement_status"] == "abstain", r["measurement_status"]
assert r["knots"] == [] and r["intensity"] == {}, "弃权时不得产出任何结"
assert "4/4" in r["abstain_reason"]
# ★ 弃权**不是**第十个结: 九结里不许出现 no_signal 之类的键
assert not any("signal" in k.lower() or "abstain" in k.lower() for k in K.KNOTS_ALL)
assert all(v == 0.0 for row in r["draw_ledger"] for v in row["knot_vector"].values())
assert all(row["abstained"] is True for row in r["draw_ledger"])

# ── 2. ★ 部分弃权不得抬高众数占比(分母必须是全部 draw) ──────────────────────
r = _agg([{"audit": .5}, {}, {"audit": .5}, {"audit": .5}])
assert r["measurement_status"] == "qualified" and r["n_abstain"] == 1
assert r["sampling"]["top1_mode_share"] == 0.75, \
    f"弃权若不计入分母会得 3/3=1.0(假的稳), 实得 {r['sampling']['top1_mode_share']}"
assert [x["abstained"] for x in r["draw_ledger"]] == [False, True, False, False]

# ── 3. 反向测试: 把分母改回 len(tops), 这条必须能抓住 ───────────────────────
_tops = [x for x in r["draw_ledger"] if not x["abstained"]]
assert len(_tops) == 3 and 3 / 3 != r["sampling"]["top1_mode_share"], \
    "反向用例必须证明两种分母给出不同的数, 否则本断言测不到东西"

# ── 4. 正常路径不受影响 ─────────────────────────────────────────────────────
r = _agg([{"audit": .5}] * 4)
assert r["measurement_status"] == "qualified" and r["n_abstain"] == 0
assert r["sampling"]["top1_mode_share"] == 1.0

# ── 5. ingest: 零分布是弃权, 不是 raise ─────────────────────────────────────
src = (ROOT / "scripts" / "cce_response_chain.py").read_text(encoding="utf-8")
assert 'raise ValueError(f"{row[\'evidence_ref\']} empty' not in src, \
    "零分布不得再 raise —— 那让「读不出」与「管线坏了」不可区分"
assert '"measurement_status"' in src and '"abstained_layers"' in src

# ── 6. ★★ 仪器指纹: s1 prompt 现在必须进指纹(此前不进 = 静默换仪器) ─────────
spec = K.instrument_id(TAXO, k=3, knot_n=5,
                       s1_pairing="round_robin_over_3_s1_draws")["spec"]
assert "s1_prompt_sha256" in spec and "s2_prompt_sha256" in spec
assert spec["s1_prompt_sha256"] == K.LEGACY_INSTRUMENT_20260818["s1_prompt_sha256"], \
    "★ s1 prompt 变了 —— 当日六个 run 的换代桥接就此断开, 不得再与新数据比较"
assert spec["s2_prompt_sha256"] == K.LEGACY_INSTRUMENT_20260818["s2_prompt_sha256"]
assert spec["aggregation_policy"]["abstention"] == K.ABSTENTION_POLICY

# 反向: 改一个字的 s1 prompt 必须换哈希(这正是此前做不到的)
import hashlib  # noqa: E402
_now = hashlib.sha256(K._stage1_template().encode()).hexdigest()[:16]
_alt = hashlib.sha256((K._stage1_template() + "。").encode()).hexdigest()[:16]
assert _now != _alt, "★ s1 prompt 改一个字必须换指纹 —— 否则又是静默换仪器"

# ── 7. 换代桥接必须诚实: 六个 run 全在册, 且旧哈希写死 ───────────────────────
lg = K.LEGACY_INSTRUMENT_20260818
assert lg["old_hash"] == "57ec6cf478d3875e" and len(lg["runs"]) == 6
assert "32150369795" in lg["runs"]

# ── 8. s1 prompt **未**被改动 —— 本次只通 2/3 两处, 不许悄悄动第 1 处 ────────
assert "反推其心理因果链四层占比分布" in src or True  # s1 在另一文件
k_src = (ROOT / "scripts" / "cce_knot_classify.py").read_text(encoding="utf-8")
assert "请对『写下这段内容的这一个人』反推" in k_src, \
    "s1 prompt 本次不得改动 —— 改它会再换一次仪器并使当日标定失效, 属独立决策"
assert "ABSTENTION_S1_NOTE" in k_src, "必须显式记下第 1 处未通及其理由"

print("test_cce_abstention: OK (全体/部分弃权 · 分母不被抬高 · ingest 不再 raise · "
      "s1 进指纹 · 换代桥接 · s1 prompt 未动)")
