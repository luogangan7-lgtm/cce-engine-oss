#!/usr/bin/env python3
"""英文 ASR 抽取质量: GEN1(字典序前 100) 与 GEN2(说话人分层) —— **两个都报, 不合并**。

## GEN1 的抽样局限是事后发现的, 处理方式很重要
预注册写「按 id 字典序取前 100, 不挑」, 我**严格执行了** —— 但后果是只覆盖 **2 个说话人**。
★ **不改 GEN1 的规则**(看到结果后改预注册是明令禁止的)。GEN1 原样保留 + 标注局限;
  GEN2 是**另一个**实验, 抽样规则不同, 归一化与 GEN1 逐字相同(换归一化就不可比)。

## 最差的几条已逐条查看过
全是**真实识别错误**(专有名词 STEPHANOS DEDALOS→SSTEPHANOS DELO; 英式拼写 COLOURS→COLORSS;
IN A CHORD→ACCORD), **不是**数字/缩写格式造成的假象 —— 归一化没有虚增 WER。
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G1 = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_quality_en.json"), encoding="utf-8"))
G2 = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_quality_en_gen2.json"), encoding="utf-8"))
P2 = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_quality_en_gen2_prereg.json"),
                    encoding="utf-8"))

# ── ① GEN1 的局限必须写在产物里, 且不许改它的抽样规则 ────────────────
assert "严格执行了" in G1["★sampling_limitation_found_after_measurement"]
assert "不改 GEN1 的抽样规则" in G1["★sampling_limitation_found_after_measurement"], \
    "★ 看到结果后改预注册是禁止的 —— 这条纪律要留在产物里"
assert G1["speakers"]["n"] == 2, "★ GEN1 只覆盖 2 个说话人这个事实要钉住"
assert "不是" in G1["★worst_cases_are_real_errors_not_normalization_artifacts"], \
    "★ 最差条目查过了没有、是不是归一化假象, 要写明"

# ── ② GEN2 的非退化闸: 说话人必须真的多起来 ─────────────────────────
assert G2["n_speakers"] > 10, \
    f"★ GEN2 只有 {G2['n_speakers']} 个说话人 ⇒ 相对 GEN1 没增加分辨力, 不得记作「确认了 GEN1」"
assert G2["degeneracy_pass"], "★ GEN2 非退化闸未过"
assert "NO_ADDED_RESOLUTION" in P2["★degeneracy_guard"], \
    "★ 「没增加分辨力」这个判决要在预注册里就写好"

# ── ③ 两个都报, 不合并 ──────────────────────────────────────────────
assert "不合并成一个数" in G2["★both_reported"], "★ 抽样规则不同的两个结果不许合并"
assert G2["★normalization_identical_to_gen1"], "★ 归一化必须与 GEN1 逐字相同, 否则不可比"
assert G2["gen1_for_comparison"]["median"] == G1["wer"]["median"], "★ 对照的是同一份 GEN1"

# ── ④ 判决必须由数据得出, 不是我写的字 ──────────────────────────────
inside = G1["wer"]["q1"] <= G2["wer"]["median"] <= G1["wer"]["q3"]
expect = "GEN1_CONSISTENT" if inside else ("GEN1_WAS_OPTIMISTIC"
         if G2["wer"]["median"] > G1["wer"]["q3"] else "GEN1_WAS_PESSIMISTIC")
assert G2["decision"] == expect, f"★ 判决与数据不符: 记 {G2['decision']} 应为 {expect}"

# ── ⑤ 只测了朗读语音, 不许外推 ──────────────────────────────────────
assert "自发语音" in P2["★what_this_does_not_establish"], \
    "★ LibriSpeech 是朗读语音; 自发/带噪场景未测, 这条边界要留着"

print(f"test_cce_asr_quality_en: OK (GEN1 前100条/**2 个说话人** 均值 {G1['wer']['mean']} · "
      f"GEN2 分层/**{G2['n_speakers']} 个说话人** 均值 {G2['wer']['mean']} ⇒ {G2['decision']} | "
      "GEN1 的抽样局限事后发现, **不改其规则**而另立 GEN2 | 两个都报不合并 | "
      "最差条目逐条查过: 真实识别错误而非归一化假象 | 仅朗读语音, 自发/带噪未测)")
