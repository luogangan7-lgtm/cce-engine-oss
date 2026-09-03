#!/usr/bin/env python3
"""K1-v2 多文本判定的钉子。

判决 INSTRUMENT_WIDE_FAIL —— 两件事被这批数据定死:
  ① 强度层不可复现是**仪器属性**, 不是那一篇文本的偶然(5/5 文本同样失败, 失败项也相同)
  ② **weight 救不了它**: 同批同判据下 weight 也是 0/5。
     上轮派生层探针在单文本上看到 weight(0.9111–1.0) 稳于 intensity(0.7333–1.0),
     那是单文本观察, 过不了预注册判据 —— 这条必须钉住, 否则下一个人还会照它换层。
  ③ 两层都**过**非退化检验 ⇒ 失败不是「这个层什么都没测」, 是「测到了但复现不了」。
     这两种失败的修法完全不同, 不许合并成一句「不稳」。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_k1_status import weight_usable, intensity_usable  # noqa: E402

P = os.path.join(ROOT, "tests", "data", "phase2")
V = json.load(open(os.path.join(P, "k1_v2_multitext_verdict.json"), encoding="utf-8"))
S = json.load(open(os.path.join(P, "k1_v2_multitext_prereg.json"), encoding="utf-8"))
INST = "565470cf26c16d01"

# ── 判定与预注册对得上 ────────────────────────────────────────────────
assert V["instrument_hash"] == INST == S["instrument"]["must_equal"]
assert V["decision"] == "INSTRUMENT_WIDE_FAIL", V["decision"]
assert V["★decision_rule_frozen_at"] == S["prereg_written_at"], \
    "★ 决策规则必须是测量前冻结的那一版"

# ── 5 文本 × n=8, 一个都没少 ──────────────────────────────────────────
for layer in ("intensity", "weight"):
    L = V["layers"][layer]
    assert L["of"] == 5 and len(L["per_text"]) == 5, L
    for bid, r in L["per_text"].items():
        assert r["n"] == 8, f"{layer}/{bid} n={r['n']} != 8 —— 少 rep 的判定不算数"

# ── ① 仪器属性: 5/5 全败, 且失败项相同 ────────────────────────────────
it = V["layers"]["intensity"]
assert it["passed_texts"] == 0, it["passed_texts"]
fails = {tuple(sorted(r["failed"])) for r in it["per_text"].values()}
assert len(fails) == 1, f"★ 各文本失败项不同 ⇒ 不能叫仪器属性: {fails}"

# ── ② weight 救不了: 同批同判据 0/5 ───────────────────────────────────
wt = V["layers"]["weight"]
assert wt["passed_texts"] == 0, "★ weight 若真的过了, 换层结论要重写"
ok, why = weight_usable(instrument_hash=INST)
assert not ok and "单文本观察" in why, why
ok_i, _ = intensity_usable(instrument_hash=INST)
assert not ok_i, "★ intensity 仍不可用"

# ── 缺仪器标识一律扣发(两层同规则) ────────────────────────────────────
assert not weight_usable()[0] and "缺仪器标识" in weight_usable()[1]

# ── ③ 失败**不是**退化 —— 两层都能把文本分开 ─────────────────────────
for layer in ("intensity", "weight"):
    d = V["layers"][layer]["degeneracy"]
    assert d["passes"], f"★ {layer} 未过非退化检验 ⇒ 结论要改成「这个层什么都没测」"
    assert d["knots_passing"] >= d["required"], d

print(f"test_cce_k1_v2: OK (5 文本 × n=8 | intensity {it['passed_texts']}/5 · "
      f"weight {wt['passed_texts']}/5, 两层均**过**非退化 ⇒ "
      f"是「测到了但复现不了」不是「什么都没测」 | 判定 {V['decision']} | "
      "weight 已接进路由, 单文本观察不能用来换层)")
