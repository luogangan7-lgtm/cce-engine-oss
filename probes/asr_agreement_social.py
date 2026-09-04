#!/usr/bin/env python3
"""社媒音轨上的 ASR **跨引擎一致性** —— 这不是准确率, 是准确率的**上界约束**。

## 为什么只能做到这一步
本项目的真实素材是社媒视频音轨(BGM/压缩/重叠/喊话), 比 LibriSpeech 难得多。
但**我听不了音频**, 做不了逐字标注; 公开集里也没有本项目这个域的带标注社媒音轨。
⇒ **真准确率测不了**。能测的是: 两个**相互独立**的 ASR 引擎在同一批真实音轨上有多一致。

## 它能约束什么、不能证明什么
· 两引擎**分歧大** ⇒ 至少一个错得多 ⇒ **准确率上界低**。这是有效的负面约束。
· 两引擎**一致** ⇒ **不能**推出「都对」—— 同类模型可能犯同样的错(共同模式失败)。
  ⇒ 一致只给出「上界没被压低」, **不构成准确率证据**。
★ 这与 OCR 那次的 tesseract 交叉检查同形, 但结论方向不同:
  那次是**用第二引擎判我的集成有没有坏**(有 ground truth 的基准上);
  这次**没有 ground truth**, 所以只能给上界约束, 不能给分数。

## 引擎
· A: iic/SenseVoiceSmall (funasr) —— 生产用的那个
· B: faster-whisper small (Apache-2.0, 非受限) —— 独立实现、独立训练数据
"""
import json, os, re, statistics, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
from asr_quality_en import wer as _wer_en

# ★ 2026-09-04: 第一版直接复用了 asr_quality_en.norm() —— 那是 **LibriSpeech 的英文**归一化,
#   只保留 [A-Z0-9' ], **中文会被整个抹掉** ⇒ 两侧皆空 ⇒ 一致性全 0.000、零方差。
#   那是**仪器坏了**, 不是结果。本项目今天已经栽过三次同类(中文渲成豆腐块 / 分词抓整句 / …),
#   靠的是「全 0 且零方差 = 退化」这条本能才没报出去。
#   ⇒ 归一化必须**语种感知**: 中日韩按**字符**比, 拉丁按**词**比。
import re as _re
_CJK = _re.compile(r"[㐀-鿿぀-ヿ가-힯]")


def norm_units(s: str):
    """返回 (单位列表, 语种标签)。CJK 按字符, 拉丁按词 —— 换错单位会把一致性算成 0。"""
    s = (s or "").strip()
    if not s:
        return [], "empty"
    if _CJK.search(s):
        return [c for c in _re.sub(r"[\s\W_]+", "", s) if c.strip()], "cjk"
    t = _re.sub(r"[^A-Za-z0-9' ]+", " ", s.upper())
    return t.split(), "latin"


def seq_agreement(a_units, b_units):
    """对称一致率: 1 − 归一化编辑距离(以较长一侧为分母, 避免偏袒空输出)。"""
    A, B = " ".join(a_units), " ".join(b_units)
    if not A and not B:
        return None
    d = _wer_en(A, B) if len(a_units) >= len(b_units) else _wer_en(B, A)
    return max(0.0, 1.0 - d)
MATERIAL = "/Volumes/data/viral-skill-eval/assets/audio_cache"
N = 20
CLIP_S = 30


def main():
    if not os.path.isdir(MATERIAL):
        print(f"★ 无本机社媒音轨 {MATERIAL} —— 不出结论。"); return 2
    import warnings; warnings.filterwarnings("ignore")
    import soundfile as sf, tempfile
    wavs = sorted(f for f in os.listdir(MATERIAL) if f.endswith(".wav"))[:N]
    print(f"社媒音轨 {len(wavs)} 份 · 每份取前 {CLIP_S}s · 两引擎独立转写")
    print("★ 这是**一致性**不是准确率 —— 没有 ground truth, 只能给上界约束\n" + "-" * 70)

    from funasr import AutoModel
    from faster_whisper import WhisperModel
    a = AutoModel(model="iic/SenseVoiceSmall", trust_remote_code=False, disable_update=True)
    b = WhisperModel("small", device="cpu", compute_type="int8")

    rows, agrees = [], []
    langs = collections.Counter()
    with tempfile.TemporaryDirectory() as td:
        for name in wavs:
            p = os.path.join(MATERIAL, name)
            try:
                x, sr = sf.read(p, dtype="float32")
                if x.ndim > 1: x = x.mean(axis=1)
                clip = os.path.join(td, name)
                sf.write(clip, x[:CLIP_S * sr], sr)
                ra = a.generate(input=clip, language="auto", use_itn=False)
                ta_raw = re.sub(r"<\|[^|]*\|>", " ", ra[0]["text"] if ra else "")
                segs, info = b.transcribe(clip, beam_size=1)
                tb_raw = " ".join(s.text for s in segs)
                ua, la = norm_units(ta_raw)
                ub, lb = norm_units(tb_raw)
            except Exception as e:                                # noqa: BLE001
                rows.append((name, "失败", str(e)[:50])); continue
            if la != lb and "empty" not in (la, lb):
                rows.append((name, "语种不一致", f"A={la} B={lb} —— 两引擎连语种都没判一致, 单列不并入")); continue
            agr = seq_agreement(ua, ub)
            if agr is None:
                rows.append((name, "两侧皆空", "")); continue
            agrees.append(agr)
            langs[la if la != "empty" else lb] += 1
            rows.append((name, f"{agr:.3f}", f"A {len(ua)} / B {len(ub)} 个{'字' if la=='cjk' else '词'}"))

    for n_, v, d_ in rows[:8]:
        print(f"  {n_[:26]:28} 一致 {v:>6}  {d_}")
    if len(rows) > 8: print(f"  … 另 {len(rows)-8} 份")
    print("-" * 70)
    if len(agrees) < 8:
        print(f"★ 有效仅 {len(agrees)} 份 ⇒ INSUFFICIENT"); return 1
    q = statistics.quantiles(agrees, n=4)
    med = statistics.median(agrees)
    out = {"block": "ASR_CROSS_ENGINE_AGREEMENT_SOCIAL", "measured_at": "2026-09-04",
           "material": "本机社媒音轨(抖音/YouTube 音频缓存), 每份前 30s",
           "n": len(agrees), "engine_a": "iic/SenseVoiceSmall (生产用)",
           "engine_b": "faster-whisper small (Apache-2.0, 独立实现与训练数据)",
           "agreement": {"median": round(med, 4), "mean": round(sum(agrees)/len(agrees), 4),
                         "q1": round(q[0], 4), "q3": round(q[2], 4),
                         "min": round(min(agrees), 4), "max": round(max(agrees), 4)},
           "★this_is_not_accuracy": ("没有 ground truth ⇒ 这是**一致性**不是准确率。"
             "两引擎分歧大 ⇒ 至少一个错得多 ⇒ **准确率上界低**(有效负面约束); "
             "两引擎一致 ⇒ **不能**推出「都对」, 同类模型可能犯同样的错。"),
           "★compare_librispeech": ("对照: 同一个 SenseVoice 在 LibriSpeech test-clean 上 WER 2.34%、"
             "test-other 11.61%(**有** ground truth)。社媒音轨上的这个一致性数**不能**与它们并列。"),
           "★unit_by_language": ("CJK 按**字符**比, 拉丁按**词**比。第一版复用了英文归一化, "
             "中文被整个抹掉 ⇒ 一致性全 0.000 零方差 —— 那是**仪器坏了**不是结果, "
             "靠「全同值=退化」这条本能才没报出去。"),
           "languages": dict(langs),
           "degeneracy_pass": len(set(round(x, 3) for x in agrees)) > 3,
           "★why_no_ground_truth": ("我听不了音频, 做不了逐字标注; 公开集里没有本项目域的带标注社媒音轨。"
             "⇒ 真准确率仍**未测**, 这条不改变那个状态。")}
    json.dump(out, open(os.path.join(ROOT, "tests/data/phase2/asr_agreement_social.json"),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if len(set(round(x, 3) for x in agrees)) <= 3:
        print(f"★ 一致性取值仅 {len(set(round(x,3) for x in agrees))} 种 ⇒ **DEGENERATE** —— "
              "先查仪器(归一化单位/语种), 不许当结论报出去"); return 1
    print(f"语种分布: {dict(langs)}")
    print(f"跨引擎一致性: 中位 {med:.3f} · 四分位 {q[0]:.3f}/{q[2]:.3f} · 范围 {min(agrees):.3f}–{max(agrees):.3f}")
    print("★ 这**不是**准确率。真准确率仍未测 —— 缺带逐字标注的社媒音轨素材。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
