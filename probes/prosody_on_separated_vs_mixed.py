#!/usr/bin/env python3
"""预注册: 源分离到底改不改变韵律读数? —— 判据在测量前冻结。

## 我能测什么、不能测什么
没有 f0 的地面真值 ⇒ **不能**直接说「分离后更准」。
能测的是**因果方向**: 如果 |Δf0| 随**非人声能量占比**上升而上升,
那就是「混音上的 f0 被 BGM 污染」的证据; 如果二者无关, 分离只是换了个数, 不构成改进理由。

## 预注册判据(测量前冻结, 不得事后改)
样本: 本机 N=30 份真实 WAV(按文件名排序取前 30, 不挑)
每份算两次韵律: ① 混音原始 ② demucs 分离出的 vocals 轨(同一 60s 窗)
主判据 —— Spearman ρ(非人声占比, |Δf0| 半音):
  ρ ≥ 0.4 且 p < 0.05        ⇒ SEPARATION_MATTERS      (BGM 越多, f0 差越大 ⇒ 混音 f0 不可信)
  ρ < 0.4 或 p ≥ 0.05        ⇒ SEPARATION_UNJUSTIFIED  (差异与 BGM 无关 ⇒ 只是换了个数)
副判据(防退化, 必须同时报):
  · |Δf0| 的分布(不是均值一个数) —— 全占比原则
  · 非人声占比的分布 —— 若样本全是纯人声(占比方差≈0), 主判据**无判别力**, 记 DEGENERATE 而非通过

## 为什么不用「分离后 f0 方差更小 = 更好」
方差小可能只是把有声段削成了静音。**更稳不等于更对。**
"""
import json, os, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
N = 30
RHO_GATE, P_GATE = 0.40, 0.05
MATERIAL = "/Volumes/data/viral-skill-eval/assets/audio_cache"


def _semitones(a, b):
    if not a or not b or a <= 0 or b <= 0:
        return None
    import math
    return abs(12 * math.log2(a / b))


def main():
    if not os.path.isdir(MATERIAL):
        print(f"★ 无本机素材 {MATERIAL} —— 本探针只在本机成立, 不降级出结论。")
        return 2
    import numpy as np, soundfile as sf
    import cce_audio_prosody as AP, cce_audio_separate as SEP
    if not SEP.available():
        print("★ demucs 未装 —— 不出结论。")
        return 2

    wavs = sorted(f for f in os.listdir(MATERIAL) if f.endswith(".wav"))[:N]

    # ★ 快失败: 先在第一份上验字段路径存在, 再开跑。
    #   今天已因读错字段白跑过两次(图片链读 visual; 这里读 prosody.f0 而非 prosody.summary.f0)。
    #   跑 10 分钟才发现「取到的全是 None」是纯浪费, 且极易被误读成「测量结果为空」。
    _p0 = (AP.analyse(os.path.join(MATERIAL, wavs[0])).get("prosody") or {}).get("summary") or {}
    assert isinstance(_p0.get("f0_median_hz"), (int, float)), \
        f"★ 字段路径不对或首份无 f0: summary 键={list(_p0)}"
    print(f"预注册判据: ρ(非人声占比, |Δf0|半音) ≥ {RHO_GATE} 且 p < {P_GATE} ⇒ SEPARATION_MATTERS")
    print(f"样本: {len(wavs)} 份真实 WAV(排序取前 {N}, 不挑)\n" + "-" * 74)

    nonvocal, dsemi, rows = [], [], []
    for name in wavs:
        p = os.path.join(MATERIAL, name)
        s = SEP.separate(p)
        if s["status"] != "ok":
            rows.append((name, s["status"], s.get("error", ""))); continue
        nv = 1.0 - s["energy_share"]["vocals"]
        f0_mix = (AP.analyse(p) or {}).get("prosody", {}).get("summary", {}).get("f0_median_hz")
        tmp = os.path.join(ROOT, ".tmp_vocals.wav")
        sf.write(tmp, s["vocals"], s["sr"])
        try:
            f0_voc = (AP.analyse(tmp) or {}).get("prosody", {}).get("summary", {}).get("f0_median_hz")
        finally:
            os.path.exists(tmp) and os.remove(tmp)
        d = _semitones(f0_mix, f0_voc)
        if d is None:
            rows.append((name, "f0 缺", f"mix={f0_mix} voc={f0_voc}")); continue
        nonvocal.append(nv); dsemi.append(d)
        rows.append((name, "ok", f"非人声 {nv:.3f} · f0 {f0_mix:.1f}→{f0_voc:.1f} · Δ{d:.2f} 半音"))

    for n, st, d in rows[:12]:
        print(f"  {st:6} {n[:26]:28} {d}")
    if len(rows) > 12:
        print(f"  … 另 {len(rows)-12} 份")

    print("-" * 74)
    if len(nonvocal) < 8:
        print(f"有效样本仅 {len(nonvocal)} 份 ⇒ **INSUFFICIENT**"); return 1

    nv_sd = statistics.pstdev(nonvocal)
    print(f"非人声占比: 中位 {statistics.median(nonvocal):.3f} · 标准差 {nv_sd:.3f} · "
          f"范围 {min(nonvocal):.3f}–{max(nonvocal):.3f}")
    qs = statistics.quantiles(dsemi, n=4)
    print(f"|Δf0| 半音: 中位 {statistics.median(dsemi):.2f} · 四分位 "
          f"{qs[0]:.2f}/{qs[1]:.2f}/{qs[2]:.2f} · 最大 {max(dsemi):.2f}")

    if nv_sd < 0.05:
        print("⇒ **DEGENERATE**: 非人声占比几乎无变异, 主判据没有判别力(不是「通过」)")
        return 1
    from scipy import stats                                     # noqa: PLC0415
    rho, p = stats.spearmanr(nonvocal, dsemi)
    verdict = "SEPARATION_MATTERS" if (rho >= RHO_GATE and p < P_GATE) else "SEPARATION_UNJUSTIFIED"
    print(f"Spearman ρ = {rho:.3f} · p = {p:.4f}  ⇒ **{verdict}**")
    print("★ 这条只说「分离改不改变读数、改变得像不像 BGM 污染」, **不说「分离后更准」**"
          " —— 没有 f0 地面真值就没有准不准。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
