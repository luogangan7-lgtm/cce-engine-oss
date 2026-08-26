#!/usr/bin/env python3
"""结构闸守卫。靶子尽量用**真实语料**(tests/data/phase2/frame_reddit_20260819.json),
不用我编的例子 —— 自造例子只能证明代码按我想的跑, 证明不了它在真数据上做对了事。

守的四件事:
  ① 判据方向: 只摘「可证为非作者原话」的段, 证不出的一律保留(误判方向必须是漏摘)
  ② 锚文本不许吞: 实测反例 f062a35fb9d2, 曾把作者自己的话连同 URL 一起摘掉
  ③ 不换仪器: 结构闸不得改动 stage1 prompt 模板, 否则 gen4 标定当场作废
  ④ 制备身份: 读数必须带 preparation_id, 且跨制备比较必须被拦
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_structural_gate import (RAW_PREPARATION_ID, VERDICT_ABSTAIN,  # noqa: E402
                                 VERDICT_MEASURE, assert_same_preparation,
                                 preparation_id, segment, structural_gate)

FRAME = json.loads((ROOT / "tests" / "data" / "phase2"
                    / "frame_reddit_20260819.json").read_text(encoding="utf-8"))
BY_ID = {r["base_id"]: r["text"] for r in FRAME["rows"]}

# ── ① 判据方向: 保留是默认, 摘除要有可证的理由 ─────────────────────────────
PROVABLE = {"code_fence", "inside_code_fence", "blockquote", "link_only_line"}
for bid, text in BY_ID.items():
    for sp in segment(text):
        if sp["kind"] == "NONPERSONAL":
            assert sp["reason"] in PROVABLE, \
                f"★ {bid} 摘除理由 {sp['reason']!r} 不在可证清单里 —— 摘除必须证得出"

# ── ② 锚文本不许吞(真实反例) ───────────────────────────────────────────────
# `[Look, I know the camera angle is simply weird, but this arm is SHORT!](url)`
# 锚文本是作者原话。曾被整条当作 link_only 摘掉。
r = structural_gate(BY_ID["f062a35fb9d2"])
assert r["chars_dropped"] == 0, \
    f"★ 作者原话被当成链接摘掉了(摘了 {r['chars_dropped']} 字)"
assert "camera angle" in r["subject_text"], "★ 锚文本必须留在被测文本里"

# 反向: 锚文本本身就是 URL 时, 整行确实没有作者的话 ⇒ 必须摘
r = structural_gate(BY_ID["c8b0ceb706f6"])
assert r["chars_dropped"] > 0, "★ 锚文本即 URL 的链接行必须被摘 —— 否则这条规则空转"
assert "I only had moderate" in r["subject_text"]

# 引用段必须被摘(真实例: 4 段 &gt; HTML 转义引用)
r = structural_gate(BY_ID["3fb58419ad8f"])
quoted = [s for s in r["spans"] if s["reason"] == "blockquote"]
assert len(quoted) == 4, f"★ HTML 转义的 &gt; 引用必须识别, 实得 {len(quoted)}"
assert "Q4 2026" not in r["subject_text"], "★ 被引用的条款不得进入被测文本"

# ── 全文可证非人称 ⇒ 零调用弃权 ────────────────────────────────────────────
# ⚠️ 如实记录: 本语料 367 条里**没有**这样的实例(锚文本保留后 3fb58419ad8f 也不再触发)。
#    所以这一支只能用构造样本守住 —— 并在此写明它未被真实数据触发过。
only_quoted = "&gt; someone else said this\n&gt; and this\n\n```\ncode()\n```"
r = structural_gate(only_quoted)
assert r["verdict"] == VERDICT_ABSTAIN, "★ 全篇可证非作者原话 ⇒ 必须弃权"
assert r["subject_text"] is None, \
    "★ 弃权时 subject_text 必须是 None 而非空串 —— 空串会被下游当成「短文本」照常投料"

n_abstain = sum(1 for t in BY_ID.values()
                if structural_gate(t)["verdict"] == VERDICT_ABSTAIN)
assert n_abstain == 0, \
    (f"★ 本语料零调用弃权数已从 0 变成 {n_abstain}。这不一定是错, 但**必须重新如实报数**: "
     "此前对外说法是「弃权分支在真实语料上无实例」。")
n_touched = sum(1 for t in BY_ID.values() if structural_gate(t)["chars_dropped"])
assert n_touched == 13, \
    f"★ 混合型条数从 13 变成 {n_touched} —— 规则改动改变了真实语料上的行为, 需重新报数"

# ── ③ 结构闸不得换仪器 ────────────────────────────────────────────────────
import cce_knot_classify as KC  # noqa: E402
assert KC._stage1_template() == KC._stage1_case("<TEXT>", "<CONTEXT>"), "模板取哈希的方式变了"
assert "eadcdcdac46a5180" == __import__("hashlib").sha256(
    KC._stage1_template().encode("utf-8")).hexdigest()[:16], \
    ("★ stage1 prompt 模板被改动了。结构闸只做样品制备, 一个字都不许碰模板 —— "
     "碰了 s1_prompt_sha256 就变, 仪器换代, gen4 那 311 样本的资格标定当场作废。")

# ── ④ 制备身份必须随读数走, 且跨制备比较必须被拦 ──────────────────────────
assert preparation_id().startswith("prep_") and preparation_id() != RAW_PREPARATION_ID
try:
    assert_same_preparation([{"preparation_id": preparation_id()},
                             {"preparation_id": RAW_PREPARATION_ID}])
    raise AssertionError("★ 跨制备比较必须被拒绝 —— 摘过引用的文本与原文不是同一个样品")
except RuntimeError as e:
    assert "制备" in str(e)
assert assert_same_preparation([{}, {}]) == RAW_PREPARATION_ID, \
    "★ 不带 preparation_id 的历史读数必须归入 raw 档, 不能默默算作已过闸"

# stage1 的零调用弃权分支必须与 LLM 弃权同形(否则下游 k_valid<2 的 WITHHOLD 会漏判)
src = (ROOT / "scripts" / "cce_knot_classify.py").read_text(encoding="utf-8")
assert 'gate["verdict"] == SG_ABSTAIN' in src, "★ stage1 必须在任何调用前先过结构闸"
head = src[src.index("def stage1("):src.index('case = _stage1_case(text, context)')]
assert "call_parse" not in head, "★ 结构闸必须在第一次 call_parse 之前"
for key in ("k_valid", "k_abstained", "measurement_status", "preparation_id"):
    assert key in head, f"★ 零调用弃权分支缺 {key}, 下游会静默兜底"

print(f"test_cce_structural_gate: OK (摘除全部可证/锚文本保留/真实语料混合型 {n_touched} 条·"
      f"弃权 {n_abstain} 条/仪器未换/制备可拦)")
