#!/usr/bin/env python3
"""VLM 视觉层: 为什么**刻意不照现状接**进图片链。

## 结论
`cce_video_parse` 的 `visual` 字段产出的是**自由散文**(scene/persons/actions/objects
各一段中文), 正是 2026-08-15 否决的「用提示词中的七字段当图像 Schema ——
无法机器校验、定位区域、保留模型/置信/来源」。**接进来等于复现一个已被否决的设计。**

## 支持证据(零调用, 方向性)
301 帧双模型(M3 + Qwen3.8): 自由散文 Jaccard 0.151 vs 受约束 on_screen_text 0.388
—— 受约束高 2.58 倍。
★ 只作方向参考, **不作判据**: 跨模型一致 != 重测信度, 且跨模型共识闸 2026-08-18 已否决。

## ★ 顺带钉住一次「测量本身坏了」的教训
第一版中文分词抓出 8–11 字整句短语, Jaccard≈0.008 —— 那是分词造的, 不是模型的分歧。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
from visual_prose_vs_constrained import bigrams, run  # noqa: E402

CAPS = {c["id"]: c for c in json.load(
    open(os.path.join(ROOT, "config/cce_capability_registry_v1.json"), encoding="utf-8")
)["capabilities"]}

# ── ★ 分词必须真的在分词(上一版就是坏在这里) ──────────────────────────
g = bigrams("金属竖条栏杆围栏")
assert g and max(len(x) for x in g) == 2, f"★ 中文必须切成二元组, 实际 {sorted(g)[:3]}"
assert "金属" in g and "属竖" in g, g
assert bigrams("hello world") >= {"hello", "world"}
assert bigrams(None) == set()

# ── 结论方向必须成立 ──────────────────────────────────────────────────
r = run()
assert r["prose"]["n"] > 500 and r["constrained"]["n"] > 0, r
assert r["ratio_constrained_over_prose"] > 1.5, \
    f"★ 受约束若不再明显优于散文, 「散文做不成 Schema」的论证要另找依据: {r}"
assert r["★status"].startswith("EXPLORATORY")
assert "不得" in r["★usable_for"] and "已否决" in r["★why_not_a_gate"], \
    "★ 必须写明它不作判据, 且跨模型共识闸已被否决"
assert "分词造出来的" in r["★tokenizer_bug_fixed"], \
    "★ 「测量本身坏过」这件事要留在产物里"

# ── 能力登记: 必须写明是**刻意不接**, 不是忘了做 ──────────────────────
cap = CAPS["standalone_image_ingest"]
_m = " ".join(cap["missing"])
assert "刻意不照现状接" in _m, "★ 要写明是刻意, 否则下一个人会当欠账去补"
assert "已被否决的设计" in _m and "受约束标签" in _m, \
    "★ 否决依据与「要做需要什么」都得写出来"
assert "2.58" in cap["★vlm_evidence"] or "受约束高" in cap["★vlm_evidence"]

print(f"test_cce_visual_prose_gap: OK (分词真在切二元组(上一版坏过) | "
      f"散文 {r['prose']['mean']} vs 受约束 {r['constrained']['mean']} = "
      f"{r['ratio_constrained_over_prose']}x | "
      "登记为**刻意不接**并写明否决依据与新仪器要求)")
