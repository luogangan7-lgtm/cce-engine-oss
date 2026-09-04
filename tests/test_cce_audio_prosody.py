#!/usr/bin/env python3
"""韵律与混音指标 —— 以及**拒绝做伪科学那一段**的结构性守卫。

## 科学边界(2026-07-22 调研, 焊进代码而不是写在注释里)
· **已重复验证**: 韵律(音高/能量/语速) → 唤醒度, CCC≈0.7, 稳健
· **弱**: 效价仅靠声学 CCC≈0.5, 须借文本通道 ⇒ **不产出效价**
· **伪科学**: 音色→性格 / 声音→稳定人格 —— 近随机, 且是**性别刻板驱动的系统性误判**
  ⇒ **在结构上不可能产出**, 由 analyse() 里的守卫抛错, 不是靠自觉

## 三种「没有」必须分开
present(真做了) / empty_verified(跑了但空) / missing_parse_failed(这次没跑成)
/ missing_no_capability(压根没这能力)
★ 依赖缺席是 **missing_parse_failed**, 不是 missing_no_capability —— 后者是「没这能力」。
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cce_audio_prosody as AP                      # noqa: E402
from cce_video_parse import _audio_capabilities     # noqa: E402

WAVS = sorted(glob.glob("/Volumes/data/viral-skill-eval/assets/audio_cache/*.wav"))

# ── ★ 结构性守卫: 被禁字段必须由代码抛错, 不是靠注释 ──────────────────
assert set(AP.FORBIDDEN_OUTPUTS) >= {"valence", "personality", "trait", "效价", "人格"}, \
    AP.FORBIDDEN_OUTPUTS
_src = open(os.path.join(ROOT, "scripts", "cce_audio_prosody.py"), encoding="utf-8").read()
assert "raise RuntimeError" in _src and "结构上不得产出" in _src, \
    "★ 禁项必须由代码抛错拦住 —— 写在注释里等于没拦"
assert "性别刻板驱动" in _src, "★ 为什么禁人格推断, 理由要留在原地"

# 反向: 真塞一个被禁字段进去, 守卫必须响
# ★ 2026-09-04 CI 实跑修: 原来这里在无 wav 时回退到 __file__, CI 上就把 .py 喂给了 librosa
#   ⇒ LibsndfileError。**测试不许依赖本机素材** —— 现场合成一个极小 wav, 到哪儿都能跑。
def _tiny_wav():
    import numpy as np, soundfile as sf, tempfile
    sr = 16000
    t = np.linspace(0, 0.5, sr // 2, endpoint=False)
    y = 0.2 * np.sin(2 * np.pi * 220 * t)          # 220Hz 正弦, 确定性
    fd, path = tempfile.mkstemp(suffix=".wav"); os.close(fd)
    sf.write(path, y, sr)
    return path

_synth = _tiny_wav()
_orig = AP.mix_metrics
try:
    AP.mix_metrics = lambda p: {"status": "ok", "valence": 0.7}
    try:
        AP.analyse(_synth)
        raise AssertionError("★ 被禁字段没被拦住 —— 守卫是死的")
    except RuntimeError as e:
        assert "被禁字段" in str(e), e
finally:
    AP.mix_metrics = _orig

# 合成音频上也要能真跑出数(证明不是靠真实素材才成立)
_r0 = AP.analyse(_synth)
assert _r0["prosody"]["status"] == "ok" and _r0["mix_metrics"]["status"] == "ok"
assert abs(_r0["prosody"]["summary"]["f0_median_hz"] - 220) < 25, \
    f"★ 220Hz 正弦的 f0 应≈220, 实测 {_r0['prosody']['summary']['f0_median_hz']}"
os.unlink(_synth)

if WAVS:
    r = AP.analyse(WAVS[0])
    # ── 韵律: 只给声学量, 不给情绪分值 ────────────────────────────────
    p = r["prosody"]
    assert p["status"] == "ok" and p["summary"]["f0_median_hz"] > 0
    for k in ("f0_median_hz", "f0_iqr_hz", "rms_db_mean", "voiced_ratio", "speech_rate_proxy_hz"):
        assert k in p["summary"], k
    assert "不给唤醒度分值" in p["★arousal_proxy_only"], \
        "★ 必须写明只给声学量、不给唤醒度分值(那需要标定, 本项目没做过)"
    assert "不产出效价" in p["★refuses"] and "人格" in p["★refuses"]
    assert not any("emotion" in k or "arousal_score" in k for k in p["summary"]), \
        "★ 摘要里出现了情绪/唤醒分值 —— 那是推断不是观察"

    # ── 混音: 纯 DSP, 频带占比之和≈1 ──────────────────────────────────
    m = r["mix_metrics"]
    assert m["status"] == "ok" and m["dynamic_range_db"] > 0
    assert abs(sum(m["band_ratio"].values()) - 1.0) < 1e-3, m["band_ratio"]
    assert "有人说话" in m["★no_inference"] and "不等于" in m["★no_inference"], \
        "★ 语音带占比不是「有人说话」, 这条要写明"

    # ── 台账: 状态词不许两套混用 ──────────────────────────────────────
    c = _audio_capabilities(True, ["BGM"], wav=WAVS[0])
    assert c["prosody_timeline"]["status"] == "present", c["prosody_timeline"]["status"]
    assert c["prosody_timeline"]["inner_status"] == "ok", "★ 内层状态要另存, 不许覆盖台账状态词"
    assert c["mix_metrics"]["status"] == "present"

# ── 依赖/文件缺席 = missing_parse_failed, **不是** missing_no_capability ──
c2 = _audio_capabilities(True, [], wav="/definitely/not/here.wav")
assert c2["prosody_timeline"]["status"] == "missing_parse_failed", \
    "★ 「这次没跑成」不许写成「压根没这能力」"
# 仍然没有的能力要如实标着
c3 = _audio_capabilities(True, [], wav=WAVS[0] if WAVS else None)
for k in ("speech_timeline", "speaker_turns"):
    assert c3[k]["status"] == "missing_no_capability", \
        f"★ {k} 需 pyannote, 未装就得如实标缺"

_where = f"本机真实音频 {len(WAVS)} 份" if WAVS else "CI(无本机素材, 只跑合成音频)"
print(f"test_cce_audio_prosody: OK ({_where} · 合成 220Hz 正弦 f0 实测≈220 | "
      "韵律只出声学量不出情绪分值 · 混音纯 DSP 频带和≈1 | "
      "★ 效价/人格被**代码抛错**拦住(反向验过) | "
      "四种状态词分开: present / missing_parse_failed / missing_no_capability)")
