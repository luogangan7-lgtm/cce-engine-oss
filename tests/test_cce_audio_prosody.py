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
        AP.analyse(_synth, separate=False)
        raise AssertionError("★ 被禁字段没被拦住 —— 守卫是死的")
    except RuntimeError as e:
        assert "被禁字段" in str(e), e
finally:
    AP.mix_metrics = _orig

# 合成音频上也要能真跑出数(证明不是靠真实素材才成立)
# ★ 2026-09-04: 显式 separate=False —— 默认值是「有 demucs 就分离」(那是对的,
#   混音 f0 已实测不可信), 但测试不该为每次调用付 ~20s 的分离开销。
#   分离那条路由 tests/test_cce_prosody_usable.py 与 probes/prosody_on_separated_vs_mixed.py 覆盖。
_r0 = AP.analyse(_synth, separate=False)
# 不分离时**必须**判不可用 —— 这正是本次要钉住的行为
assert _r0["prosody"]["f0_source"] == "mixed" and _r0["prosody"]["usable"] is False, \
    f"★ 不分离却判可用: {_r0['prosody'].get('★usable_why')}"
assert _r0["prosody"]["status"] == "ok" and _r0["mix_metrics"]["status"] == "ok"
assert abs(_r0["prosody"]["summary"]["f0_median_hz"] - 220) < 25, \
    f"★ 220Hz 正弦的 f0 应≈220, 实测 {_r0['prosody']['summary']['f0_median_hz']}"
os.unlink(_synth)

# ★ 2026-09-04: 真实音频那段现在会连带跑**源分离 + 说话人分离**(默认路径),
#   169s 的原片要 ~40s。真实覆盖必须保留(「要跑不要读」), 但可以只用**前 15 秒** ——
#   被测的是「链路接没接上、状态词有没有混用」, 不是「长音频能不能跑」。
_CLIP = None
if WAVS:
    import soundfile as _sf, tempfile as _tf
    _x, _sr = _sf.read(WAVS[0], dtype="float32")
    _CLIP = _tf.NamedTemporaryFile(suffix=".wav", delete=False).name
    _sf.write(_CLIP, _x[:15 * _sr], _sr)

if _CLIP:
    r = AP.analyse(_CLIP, separate=False)     # 韵律指标本身不需要分离; 分离那条路另有测试
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
    # ★ 这一处**故意走默认路径**(会真跑源分离与说话人分离) —— 台账接没接上只能靠实跑验,
    #   读代码看不出来。15 秒片段让它可负担。
    c = _audio_capabilities(True, ["BGM"], wav=_CLIP)
    assert c["prosody_timeline"]["status"] == "present", c["prosody_timeline"]["status"]
    assert c["prosody_timeline"]["inner_status"] == "ok", "★ 内层状态要另存, 不许覆盖台账状态词"
    assert c["mix_metrics"]["status"] == "present"
    # ★ 2026-09-04 新接入的两项: 台账必须是 present, 且各自的边界声明要跟着进来
    assert c["speaker_turns"]["status"] == "present", c["speaker_turns"]
    assert "不检测重叠语音" in c["speaker_turns"]["★overlap_not_detected"]
    assert "局部标签" in c["speaker_turns"]["★labels_are_local"], \
        "★ speaker_N 不是身份, 这条边界必须跟着读数走"
    assert c["source_separation"]["status"] == "present", c["source_separation"]
    assert abs(sum(c["source_separation"]["energy_share"].values()) - 1.0) < 1e-2
    assert "声学量" in c["source_separation"]["★energy_share_is_acoustic"], \
        "★ 能量占比不得读成说话人数或语义占比"
    pass  # _CLIP 由末尾统一清理(上面 c3/c4 还要用)

# ── 依赖/文件缺席 = missing_parse_failed, **不是** missing_no_capability ──
c2 = _audio_capabilities(True, [], wav="/definitely/not/here.wav")
assert c2["prosody_timeline"]["status"] == "missing_parse_failed", \
    "★ 「这次没跑成」不许写成「压根没这能力」"
# 仍然没有的能力要如实标着。
# ★ 2026-09-04: speaker_turns **已实测接入**(3D-Speaker, 无 token, DER STRICT 0.1004),
#   从这份清单里移出。剩下 speech_timeline 仍是 missing_no_capability。
#   ★ 但「missing_parse_failed(这次没跑成)」与「missing_no_capability(压根没这能力)」
#     的区分没有因此松动 —— 下面用**不存在的文件**验 speaker_turns 走的是前者。
c3 = _audio_capabilities(True, [], wav=_CLIP)
assert c3["speech_timeline"]["status"] == "missing_no_capability", \
    "★ speech_timeline 仍无能力, 要如实标缺"
c4 = _audio_capabilities(True, [], wav="/definitely/not/here.wav")
assert c4["speaker_turns"]["status"] == "missing_parse_failed", \
    "★ 能力已具备时, 文件缺席应记「这次没跑成」而**不是**「压根没这能力」"
assert c4["source_separation"]["status"] == "missing_parse_failed", "同上"

if _CLIP:
    os.unlink(_CLIP)
_where = f"本机真实音频 {len(WAVS)} 份(取前 15 秒跑全链)" if WAVS else "CI(无本机素材, 只跑合成音频)"
print(f"test_cce_audio_prosody: OK ({_where} · 合成 220Hz 正弦 f0 实测≈220 | "
      "韵律只出声学量不出情绪分值 · 混音纯 DSP 频带和≈1 | "
      "★ 效价/人格被**代码抛错**拦住(反向验过) | "
      "四种状态词分开: present / missing_parse_failed / missing_no_capability | "
      "★ speaker_turns 与 source_separation 已实测接入(台账 present, 边界声明随读数走); "
      "文件缺席时记「这次没跑成」而非「压根没这能力」)")
