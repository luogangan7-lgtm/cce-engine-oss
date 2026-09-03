#!/usr/bin/env python3
"""强度层失败的跨文本泛化 —— 用**已付费的历史面板**, 31 个文本, 零调用。

## 这条测试为一次「漏用数据」而设
K1-v2 只用了 5 个文本(新烧 320 次调用)。而 phase2 面板的 L0 臂**早就有
31 个 base × 4 rep 的结读数, 同一台仪器**(565470cf26c16d01, gen4)。
★ 是 owner 指出「应该有历史数据可以测」我才去查的 —— 数据一直在, 是我没用。
**通用教训: 设计新实验之前, 先把已有数据翻一遍。**

## 它证明什么 / 不证明什么
· **不能**让 K1 通过: 面板每 base 只有 4 rep, 判据要求 n>=8
· **能**确认泛化: 失败在 5 个文本上成立, 在 31 个上仍成立 ⇒ INSTRUMENT_WIDE_FAIL 加强
· 面板**只有 intensity 没有 weight** ⇒ v2 那 320 次调用不是白烧, 它是 weight 唯一来源
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
from intensity_across_panel import run  # noqa: E402

r = run()

# ── 同一台仪器, 否则不可比 ────────────────────────────────────────────
V2 = json.load(open(os.path.join(ROOT, "tests/data/phase2/k1_v2_multitext_verdict.json"),
                    encoding="utf-8"))
assert r["instrument_hash"] == V2["instrument_hash"], \
    "★ 面板与 v2 不是同一台仪器 —— 标定不可跨仪器搬, 结论不可合并"

# ── 样本确实比 v2 宽 ──────────────────────────────────────────────────
assert r["texts"] >= 30, f"★ 面板应覆盖 30+ 文本, 实测 {r['texts']}"
assert r["texts"] > V2["layers"]["intensity"]["of"], "★ 这一支的意义就是样本更宽"

# ── ★ 核心: 失败跨 31 个文本泛化 ──────────────────────────────────────
a = r["agreement"]
assert a["texts_meeting_0.95"] <= 2, (
    f"★ 31 个文本里有 {a['texts_meeting_0.95']} 个达到 0.95 —— "
    "若普遍达标, INSTRUMENT_WIDE_FAIL 就要重估而不是沿用")
assert a["mean"] < 0.80, f"★ 均值 {a['mean']} 偏高, 与 v2 不同向, 需重估"
# 与 v2 同向(v2 五文本上 cardinal 均值 0.712)
assert abs(a["mean"] - 0.712) < 0.15, \
    f"★ 面板均值 {a['mean']} 与 v2 的 0.712 差太远 —— 两批数据不一致, 必须查清再引用"

# ── 定位必须写死: 它不能让 K1 通过 ────────────────────────────────────
assert r["★status"].startswith("EXPLORATORY"), r["★status"]
assert "不能" in r["★usable_for"] and "关门" in r["★usable_for"]
assert "没有 weight" in r["★no_weight_in_panel"] or "只有 intensity" in r["★no_weight_in_panel"], \
    "★ 必须写明面板无 weight —— 否则会有人以为 v2 那 320 次调用是多余的"

print(f"test_cce_intensity_across_panel: OK "
      f"({r['texts']} 文本 × 4 rep, 同仪器 · A 均值 {a['mean']} · "
      f"达 0.95 仅 {a['texts_meeting_0.95']}/{r['texts']} ⇒ "
      f"INSTRUMENT_WIDE_FAIL 在 6 倍样本上被证实, 零调用 | "
      "面板无 weight, v2 的 320 次调用仍是 weight 唯一来源)")
