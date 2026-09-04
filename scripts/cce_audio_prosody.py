#!/usr/bin/env python3
"""韵律与混音指标 —— 只做**已重复验证**的那一段, 拒绝做伪科学的那一段。

## 科学边界(2026-07-22 调研结论, 焊进代码而不是写在注释里)
· **已重复验证**: 韵律(音高/能量/语速) → **唤醒度(arousal)**, CCC≈0.7, 稳健
· **弱**: 效价(valence)**仅靠声学** CCC≈0.5 —— 须借文本/词汇通道 ⇒ 本模块**不产出效价**
· **伪科学**: 音色→性格 / 声音→稳定人格(Big Five) —— 近随机, 且是**性别刻板驱动的
  系统性误判** ⇒ 本模块**在结构上不可能**产出特质/人格字段, 并有断言守着

## 它产出什么
`prosody_timeline`: 逐窗的 f0/能量/语速代理 + 全局摘要(eGeMAPS 风格的廉价可解释基线)
`mix_metrics`: 响度、动态范围、语音带/低频带能量比

## 它**不**产出什么
· 不产出情绪标签 —— 韵律是 **Observation**, 不是情绪推断
· 不产出效价、不产出人格/特质
· `arousal_proxy` 是**代理量不是唤醒度本身**, 且**未在本项目标定过** ——
  下游必须当未验读数, 由 qualified_readout 扣发
"""
from __future__ import annotations

import json
import math
import os
import sys

FORBIDDEN_OUTPUTS = ("valence", "personality", "big_five", "trait", "extraversion",
                     "neuroticism", "性格", "人格", "特质", "效价")


def _load(path, sr=16000):
    import librosa
    y, s = librosa.load(path, sr=sr, mono=True)
    return y, s


def prosody(path: str, win_s: float = 1.0) -> dict:
    """逐窗韵律 + 全局摘要。★ 只出可观测的声学量, 不出情绪/特质。"""
    import librosa
    import numpy as np
    y, sr = _load(path)
    if y.size == 0:
        return {"status": "empty", "why": "音轨为空"}
    hop = int(sr * 0.010)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    f0 = librosa.yin(y, fmin=60, fmax=400, sr=sr, hop_length=hop)
    voiced = np.isfinite(f0) & (rms > np.percentile(rms, 40))
    zcr = librosa.feature.zero_crossing_rate(y, hop_length=hop)[0]
    n = max(1, int(win_s / 0.010))
    tl = []
    for i in range(0, len(rms), n):
        sl = slice(i, i + n)
        v = voiced[sl]
        seg_f0 = f0[sl][v] if v.any() else np.array([])
        tl.append({"t": round(i * 0.010, 2),
                   "rms_db": round(float(20 * math.log10(max(rms[sl].mean(), 1e-9))), 2),
                   "f0_median_hz": (round(float(np.median(seg_f0)), 1) if seg_f0.size else None),
                   "voiced_ratio": round(float(v.mean()), 3),
                   "zcr": round(float(zcr[sl].mean()), 4)})
    vf0 = f0[voiced]
    return {"status": "ok", "window_s": win_s, "timeline": tl,
            "summary": {
                "f0_median_hz": (round(float(np.median(vf0)), 1) if vf0.size else None),
                "f0_iqr_hz": (round(float(np.subtract(*np.percentile(vf0, [75, 25]))), 1)
                              if vf0.size else None),
                "rms_db_mean": round(float(20 * math.log10(max(rms.mean(), 1e-9))), 2),
                "rms_db_iqr": round(float(np.subtract(*np.percentile(
                    20 * np.log10(np.maximum(rms, 1e-9)), [75, 25]))), 2),
                "voiced_ratio": round(float(voiced.mean()), 3),
                "speech_rate_proxy_hz": round(float(zcr.mean() * sr / 2), 1)},
            "★arousal_proxy_only": (
                "韵律→**唤醒度**是已重复验证的通道(CCC≈0.7)。本模块只给声学量本身, "
                "**不给唤醒度分值** —— 那需要标定, 本项目从未做过。"),
            "★refuses": ("**不产出效价**(仅靠声学 CCC≈0.5, 须借文本通道); "
                         "**不产出人格/特质**(音色→性格近随机且是性别刻板驱动的系统性误判)。")}


def mix_metrics(path: str) -> dict:
    """混音指标: 响度 / 动态范围 / 频带能量比。纯 DSP, 无推断。"""
    import librosa
    import numpy as np
    y, sr = _load(path)
    if y.size == 0:
        return {"status": "empty"}
    rms = librosa.feature.rms(y=y)[0]
    db = 20 * np.log10(np.maximum(rms, 1e-9))
    S = np.abs(librosa.stft(y, n_fft=1024))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=1024)
    band = lambda lo, hi: float(S[(freqs >= lo) & (freqs < hi)].sum())
    low, speech, high = band(20, 300), band(300, 3400), band(3400, sr / 2)
    tot = max(low + speech + high, 1e-9)
    return {"status": "ok",
            "loudness_db_mean": round(float(db.mean()), 2),
            "loudness_db_p95": round(float(np.percentile(db, 95)), 2),
            "dynamic_range_db": round(float(np.percentile(db, 95) - np.percentile(db, 5)), 2),
            "band_ratio": {"low_20_300": round(low / tot, 4),
                           "speech_300_3400": round(speech / tot, 4),
                           "high_3400_up": round(high / tot, 4)},
            "★no_inference": "纯 DSP 测量, 不含任何推断; 语音带占比**不等于**「有人说话」"}


# ★ 2026-09-04 实测判决 PROSODY_ON_SEPARATED_VS_MIXED_GEN1(tests/data/phase2/):
#   |Δf0| 随非人声能量占比上升而上升, Spearman ρ=0.618 p=0.0003, 中位差 **12.4 半音(一个八度)**。
#   ⇒ **混音上的 f0 会跟着音乐走**(实例: 非人声 0.996 的片段, 混音 f0 = 79Hz 是贝斯线,
#     人声轨 231Hz 才是说话)。所以韵律读数必须标明**算在哪条轨上**, 且高 BGM 的混音读数不可用。
NONVOCAL_GATE = 0.35        # 超过此占比的**混音**读数判不可用。改它属于判据变更。


def prosody_usable(pros: dict) -> tuple[bool, str]:
    """韵律读数可不可用。★ 默认拒判 —— 说不清算在哪条轨上的, 一律不可用。"""
    if not isinstance(pros, dict) or pros.get("status") != "ok":
        return False, f"韵律未算出(status={(pros or {}).get('status')})"
    src = pros.get("f0_source")
    if src == "vocals":
        return True, "算在分离出的人声轨上"
    if src != "mixed":
        return False, f"未标明算在哪条轨上(f0_source={src!r}) —— 说不清就不可用"
    nv = pros.get("nonvocal_share")
    if nv is None:
        return False, ("算在混音上且**非人声占比未知** —— 无法判断 f0 是不是在跟音乐走"
                       "(实测中位差 12.4 半音)")
    if nv > NONVOCAL_GATE:
        return False, f"算在混音上且非人声占比 {nv:.3f} > {NONVOCAL_GATE}: f0 很可能在跟音乐走"
    return True, f"算在混音上但非人声占比仅 {nv:.3f}, 低于闸"


def analyse(path: str, *, separate: bool | None = None) -> dict:
    """separate=None 表示自动: demucs 可用就分离后再算韵律, 不可用就如实标 mixed。"""
    pros_path, f0_source, nonvocal = path, "mixed", None
    _tmp = None
    if separate is not False:
        try:
            import cce_audio_separate as SEP
            if SEP.available():
                r = SEP.separate(path)
                if r["status"] == "ok":
                    import soundfile as _sf, tempfile as _tf
                    nonvocal = round(1.0 - r["energy_share"]["vocals"], 4)
                    _tmp = _tf.NamedTemporaryFile(suffix=".wav", delete=False).name
                    _sf.write(_tmp, r["vocals"], r["sr"])
                    pros_path, f0_source = _tmp, "vocals"
        except Exception:
            pass                                  # 分离失败 ⇒ 退回 mixed, 并如实标注
    try:
        _pros = prosody(pros_path)
    finally:
        if _tmp and os.path.exists(_tmp):
            os.remove(_tmp)
    _pros["f0_source"] = f0_source
    _pros["nonvocal_share"] = nonvocal
    _ok, _why = prosody_usable(_pros)
    _pros["usable"] = _ok
    _pros["★usable_why"] = _why
    out = {"kind": "cce.audio_prosody.v1", "source": os.path.basename(path),
           "prosody": _pros, "mix_metrics": mix_metrics(path)}
    # ★ 结构性守卫: 任何被禁字段出现即抛 —— 不是靠注释约束, 是靠代码
    blob = json.dumps(out, ensure_ascii=False).lower()
    for k in FORBIDDEN_OUTPUTS:
        if f'"{k}"' in blob or f"'{k}'" in blob:
            raise RuntimeError(f"★ 产出里出现被禁字段 {k!r} —— 效价/人格/特质是已判伪科学或"
                               "声学不可及的, 本模块结构上不得产出")
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("audio")
    ap.add_argument("--out")
    a = ap.parse_args()
    r = analyse(a.audio)
    print(json.dumps({"prosody": r["prosody"].get("summary"),
                      "mix": {k: v for k, v in r["mix_metrics"].items() if not k.startswith("★")}},
                     ensure_ascii=False, indent=1))
    if a.out:
        open(a.out, "w", encoding="utf-8").write(json.dumps(r, ensure_ascii=False, indent=1))
