#!/usr/bin/env python3
"""ASR 受控退化曲线: **唯一能拿到真 ground truth** 的路, 且它把真实素材定位到了曲线上。

## 为什么这条能给真值
参考文本是我自撰的 12 句, **逐字已知**, 无标注误差。代价是 domain gap ——
合成语音无口音/情绪/口误/远近场 ⇒ 这是**上界**, 与 OCR 那条合成曲线同构。

## ★ 三次仪器故障, 三次被非退化闸拦下
① 第一版写死 ["Tingting","Eddy","Flo"] —— **Eddy/Flo 是同名的英文音色**, 中文输出为空
   ⇒ 无退化 CER = 1.0000, 闸拦下。改为**程序化枚举 + 读回自检**。
② 本机 say 的 9 个 zh_CN 音色只有 1 个通过自检, 而设计要求音色是有变异的 facet(>=2)
   ⇒ 改用 edge-tts(8 个中文神经音色, 7 个通过自检)。
③ **MP3 轴的见证测错了对象** —— 我在 MP3 往返后又转回 WAV, 记的是 WAV 字节(112172 vs 112206,
   几乎无差), **根本没证明压缩施加了**。改为记**中间 mp3** 的字节。
★ 第 ③ 条尤其要记: 见证本身也会指错对象, 那时「无分辨力」依然与「仪器坏了」分不开。
"""
import json, math, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_degradation_curve.json"),
                   encoding="utf-8"))

# ── ① 仪器闸: 无退化必须近乎无错, 否则量的是合成不是 ASR ────────────
assert D["clean_cer_median"] < 0.15, \
    f"★ 无退化 CER {D['clean_cer_median']} —— 合成或归一化坏了, 不是 ASR 差"
assert len(D["voices"]) >= 2, "★ 音色必须是有变异的 facet, 否则「音色好不好认」会被当成「ASR 好不好」"
assert "读回自检" in D["★voice_self_check"], "★ 音色必须逐个读回自检 —— 同名英文音色会静默产出空"
assert D["n_synth_skipped"] == 0 or D["n_synth_ok"] >= 0.8 * (D["n_synth_ok"] + D["n_synth_skipped"]), \
    "★ 合成失败必须计数; 失败率过高说明样本被网络选择性削减"

# ── ② 每条轴的见证必须证明**处理确实施加了** ────────────────────────
for ax, v in D["axes"].items():
    assert v["★degradation_applied"], \
        f"★ {ax}: 见证显示处理没真的施加 ⇒ 「{v['resolution']}」不成立, 是仪器问题"
    assert v["★witness_proof"] and v["★witness_proof"] != "无", f"★ {ax} 缺见证"
# MP3 的见证必须是**中间压缩文件**的字节, 不是往返后的 WAV
mp3w = D["axes"]["mp3_kbps"]["★witness_proof"]
assert "中间 mp3" in mp3w, "★ 见证必须记中间 mp3 —— 往返回 WAV 后字节几乎不变, 那不是见证"
lo, hi = [int(x) for x in mp3w.split("字节 ")[1].split("(")[0].split("–")]
assert hi / lo >= 1.5, f"★ 中间 mp3 字节只差 {hi/lo:.1f}x ⇒ 压缩没真的施加"

# ── ③ 至少一条轴要有分辨力, 否则是设计失败不是「稳健」 ──────────────
assert any(v["resolution"] == "OK" for v in D["axes"].values()), \
    "★ 所有轴都无分辨力 ⇒ 设计失败, 不是「ASR 稳健」"
bgm = D["axes"]["bgm_snr_db"]["curve"]
assert bgm[0]["cer_median"] < bgm[-1]["cer_median"], "★ CER 必须随噪声上升"

# ── ④ 真实素材在曲线上的位置, 且必须标明是**下界** ──────────────────
W = D["★where_real_material_sits"]
sep = json.load(open(os.path.join(ROOT, "tests/data/phase2/prosody_separation_verdict.json"),
                     encoding="utf-8"))
nv = sep["nonvocal_share"]["median"]
assert abs(W["real_nonvocal_share_median"] - nv) < 1e-9, "★ 占比必须从产物现读, 不手抄"
assert abs(W["equivalent_snr_db"] - 10 * math.log10((1 - nv) / nv)) < 0.05, "★ SNR 换算不符"
assert "下界" in W["★this_is_a_lower_bound"], "★ 必须标明真实只会更差"
for reason in ("高斯噪声", "TTS 语音比真人干净"):
    assert reason in W["★this_is_a_lower_bound"], f"★ 缺 domain gap 理由: {reason}"

# ── ⑤ 压缩那条工程含义 ──────────────────────────────────────────────
assert "压缩不是问题" in W["★mp3_finding"] and "降噪" in W["★mp3_finding"], \
    "★ 「该花力气的是降噪不是保码率」这个可行动结论要留着"
assert "★not_claimed" in D and "未测" in D["★not_claimed"]

print(f"test_cce_asr_degradation: OK ({D['n_synth_ok']}/{D['n_synth_ok']+D['n_synth_skipped']} 合成 · "
      f"{len(D['voices'])} 音色(读回自检过) · 无退化 CER {D['clean_cer_median']} | "
      f"噪声轴有分辨力(SNR 0dB 起塌到 {bgm[3]['cer_median']}) · MP3 至 16kbps **无分辨力**但见证证明压缩施加了 | "
      f"★ 真实素材等效 SNR **{W['equivalent_snr_db']} dB** —— 恰好落在曲线开始塌的那一点 | "
      "该数是**下界**(高斯噪声≠音乐, TTS≠真人))")
