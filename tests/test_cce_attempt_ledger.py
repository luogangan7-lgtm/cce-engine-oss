#!/usr/bin/env python3
"""attempt ledger：重试不是污染，「失败被重试成功后从记录里消失」才是。

外部评审判定（我原本判得过严，说"一律不重试"）：
  · **measurement estimand**：在 API 能返回可解析结果的条件下，仪器性质如何 —— 对
    明确的基础设施错误做固定重试**是正当的**
  · **operational estimand**：一次真实调用最终成功的概率 —— **第一次失败必须保留**
两本账混在一起，会让 infra 抖动伪装成仪器不稳。

★ 我方现状：`one()` **本来就每档重试 3 次，只是从未记录** ⇒ first_attempt_success 至今未知。
  缺的不是重试能力，是 ledger。本次**只记录、不改重试行为**（改重试策略会影响拿到哪些 draw）。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K  # noqa: E402


def _run(seq):
    """seq: 每次调用返回 (content, parsed, ok)"""
    it = iter(seq)
    orig = K.call_parse

    def fake(mk, case, T, note):
        c, p, ok = next(it)
        pv = None
        if ok:
            pv = {"desire_vec": [1.0] + [0] * 8, "need_vec": [1.0] + [0] * 16,
                  "emotion_vec": [1.0] + [0] * 12, "action_vec": [1.0] + [0] * 6,
                  "need_slots": {}, "appraisal": {}, "chain_trace": "", "evidence": {}}
        return c, p, pv, ({"error": "E"} if not ok and c else {"error": "HTTP 503"}), ok

    K.call_parse = fake
    try:
        return K.stage1("x", "ctx", 3)
    finally:
        K.call_parse = orig


OK = ("ok", {}, True)
INFRA = ("", None, False)                       # 空 body ⇒ 传输故障
PARSE = ("{半个 JSON", None, False)              # 有内容但解析不过 ⇒ 仪器行为
ABST = ("ok", {"no_inferable_subject": True}, False)

# ── 1. 三种失败类别必须被分开 ───────────────────────────────────────────────
op = _run([INFRA, OK, OK, OK])["operational"]
assert op["n_infra_failed"] == 1 and op["n_parse_failed"] == 0
op = _run([PARSE, OK, OK, OK])["operational"]
assert op["n_parse_failed"] == 1 and op["n_infra_failed"] == 0, \
    "★ 有内容但解析失败是**仪器行为**, 不得归成基础设施 —— 否则重试它就是条件化于好读数"

# ── 2. ★ 第一次失败不得从记录里消失(这是全部意义) ───────────────────────────
s = _run([INFRA, OK, OK, OK])
assert s["k_valid"] == 3, "重试后三档都拿到了读数"
assert s["operational"]["first_attempt_success"] == 2, \
    "★ 首档第一次失败必须留痕 —— 重试成功后 first_attempt_success 仍须是 2/3"
assert s["operational"]["first_attempt_success_rate"] == round(2 / 3, 4)
assert s["operational"]["attempts"][0]["status"] == "INFRA_FAILED"
assert s["operational"]["attempts"][0]["error_class"]

# ── 3. 弃权算 measurement 侧, 不算 operational 失败 ─────────────────────────
op = _run([ABST, ABST, ABST])["operational"]
assert op["n_infra_failed"] == 0 and op["n_parse_failed"] == 0
assert op["first_attempt_success"] == 3, "弃权是合法读数结果, 首次即成功(operational 意义上)"

# ── 4. ★ 两分支键集一致 —— 弃权分支也必须带 operational ─────────────────────
ab = _run([ABST, ABST, ABST])
assert "operational" in ab and ab["measurement_status"] == "abstain"

# ── 5. ★ 反向: 若有人把 PARSE_FAILED 并进 INFRA, 这条要红 ───────────────────
src = (ROOT / "scripts" / "cce_knot_classify.py").read_text(encoding="utf-8")
assert '"PARSE_FAILED"' in src and '"INFRA_FAILED"' in src, "两类必须分开命名"
assert "仪器行为" in src, "必须写明 PARSE_FAILED 属仪器行为"
# 且必须诚实标注当前尚未按错误类别分流
assert "not** classified by error type yet" in src or "不是按错误类别" in src or \
    "尚未" in src or "先记录" in src, "当前实现对 PARSE_FAILED 也重试, 必须如实标注"

print("test_cce_attempt_ledger: OK (三类分开 / 首次失败留痕 / 弃权不算 operational 失败 / "
      "两分支同构 / 未分流已如实标注)")
