#!/usr/bin/env python3
"""社媒音轨上的 ASR: 有**可证的上界约束**了, 但真准确率仍未测。

## 为什么只能到这一步
本项目素材是社媒音轨(BGM/压缩/重叠/喊话)。**我听不了音频**, 做不了逐字标注;
公开集里也没有本项目域的带标注社媒音轨 ⇒ **真准确率测不了**。
能测的是: 两个**相互独立**的引擎在同一批真实音轨上有多一致。

## 可证的上界(不是手挥)
a、b 是两个转写与(未知)真值的匹配率, p 是两者彼此的一致率。
两者**同时**匹配真值的位置必然也彼此一致 ⇒ 同时匹配 <= p; 由容斥 a+b-1 <= p
⇒ **a + b <= 1 + p**。实测 p=0.475 ⇒ **至少一个 <= 0.738**。

## ★ 第一版是坏的, 靠非退化闸拦下
直接复用了 LibriSpeech 的**英文**归一化(只留 [A-Z0-9' ]), **中文被整个抹掉**
⇒ 一致性全 0.000 零方差。**那是仪器坏了不是结果。**
⇒ 归一化改为**语种感知**(CJK 按字符 / 拉丁按词), 并加非退化闸。
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
D = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_agreement_social.json"),
                   encoding="utf-8"))

# ★ 本测试 import 了 probes/asr_agreement_social —— 那个探针要本机社媒音轨。
#   但**本测试不重跑探针**: 它只用探针里的**纯函数**(norm_units / seq_agreement)做自比基准,
#   以及校验已落盘的产物。⇒ 缺素材时结论不变。
#   本次覆盖: 无本机素材也**照跑**(纯函数 + 产物校验), 唯一跑不了的是**重新采集**那一步。
_MATERIAL = "/Volumes/data/viral-skill-eval/assets/audio_cache"
_COVER = ("本机有素材(但本测试仍不重跑采集)" if os.path.isdir(_MATERIAL)
          else "CI(无本机素材): 结论不变 —— 本测试只用纯函数与已落盘产物, **未重新采集**")

# ── ① 一致性 ≠ 准确率, 这条必须写死 ────────────────────────────────
assert "不是准确率" in D["★this_is_not_accuracy"]
assert "不能" in D["★this_is_not_accuracy"] and "同类模型可能犯同样的错" in D["★this_is_not_accuracy"], \
    "★ 一致高**不能**推出都对 —— 共同模式失败这条要写明"
assert "仍**未测**" in D["★why_no_ground_truth"] or "未测" in D["★why_no_ground_truth"]

# ── ② 上界必须可复算, 不是手挥 ──────────────────────────────────────
b = D["★derivable_bound"]
assert b["inequality"] == "a + b <= 1 + p"
assert abs(b["a_plus_b_max"] - (1 + D["agreement"]["median"])) < 1e-6, "★ 上界与实测不符"
assert abs(b["if_equal_each_max"] - (1 + D["agreement"]["median"]) / 2) < 1e-6
assert "容斥" in b["★derivation"], "★ 推导过程要留下, 不许只给结论"
assert "**不能**推出" in b["★reading"] and "**不能**证明它是好的" in b["★reading"], \
    "★ 既不能说生产引擎是差的那个, 也不能说它是好的那个 —— 两个方向都要写"

# ── ③ ★ 非退化: 第一版就是死在这里 ─────────────────────────────────
assert D["degeneracy_pass"], "★ 一致性取值全同 ⇒ 先查仪器, 不许当结论"
assert "仪器坏了" in D["★unit_by_language"], "★ 第一版坏在哪, 要留在产物里"
assert "CJK 按**字符**比" in D["★unit_by_language"] or "字符" in D["★unit_by_language"]
# 自比基准: 同一输入自己跟自己比必须满分 —— 归一化坏了这条会先红
from asr_agreement_social import norm_units, seq_agreement
for s in ("这个视频我简直是老鼠掉进了米缸", "Hello world this is a test"):
    u, _ = norm_units(s)
    assert u, f"★ 归一化把 {s[:8]!r} 抹成空了"
    assert seq_agreement(u, u) == 1.0, "★ 自比不满分 ⇒ 归一化或距离函数坏了"
assert norm_units("这个视频")[1] == "cjk" and norm_units("hello")[1] == "latin"

# ── ④ 与 LibriSpeech 的对照必须在, 且方向正确 ──────────────────────
c = D["★derivable_bound"]["★contrast_with_librispeech"]
assert "高估" in c, "★ 朗读语音的数高估了本项目素材上的表现 —— 这是本实验的要点"
ls = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_quality_en_gen2.json"),
                    encoding="utf-8"))
assert 1 - ls["wer"]["mean"] > b["if_equal_each_max"], \
    "★ 若 LibriSpeech 的匹配率不高于本上界, 「高估」这个说法就不成立"

print(f"test_cce_asr_agreement_social: OK (社媒音轨 n={D['n']} 全 CJK · "
      f"跨引擎一致 中位 {D['agreement']['median']} 范围 "
      f"{D['agreement']['min']}–{D['agreement']['max']} | "
      f"**可证上界** a+b<=1+p ⇒ 至少一个 <= {b['if_equal_each_max']} | "
      f"对照 LibriSpeech 匹配率 ~{1-ls['wer']['mean']:.3f} ⇒ 朗读语音的数**高估**了本项目素材 | "
      "★ 一致 ≠ 准确; 真准确率仍未测(我听不了音频, 公开集也没有这个域的标注)"
      f"\n  ★ 本次覆盖: {_COVER})")
