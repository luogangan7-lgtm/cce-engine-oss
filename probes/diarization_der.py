#!/usr/bin/env python3
"""说话人分离 DER —— 3D-Speaker(无 token 路径) 在 VoxConverse dev 上。

## 为什么这一项曾被我错记为 BLOCKED
我写的是「pyannote 是受限模型, 需 HF token ⇒ 拿不到凭据」。**两处错**:
① `pyannote.audio` 是 **MIT 开源包**, 受限的是**权重**。包与权重不是一回事。
② 3D-Speaker 的默认路径 `include_overlap=False` **根本不碰** pyannote 权重
   (源码已核: 只有 include_overlap=True 才 require hf_access_token), 走 ModelScope 权重。
⇒ 无账号、无 token、无点击条款即可跑。实测 CPU **0.12x 实时**。

## ★ 四个字段不许压成一个 OPEN
2026-09-04 调研提醒(已核实): 「无账号 / 无 token / 无点击接受条款 / 无许可限制」是**四件事**。
例: sherpa-onnx 的 reverb 权重可匿名直链下载, 但许可是 **non-commercial**;
    NeMo 的 NGC 下载即视为接受 NGC Terms。
本探针只用同时满足四条的路径, 并把四个字段分开登记。

## DER 判据 profile 必须冻结, 且禁止跨 profile 排名
不同论文的 DER 常常不可横比, 危险开关有四个: collar / score_overlap / oracle_vad / oracle_num_speakers。
本探针固定两档,**都报**:
  STRICT : collar=0.00, 计入重叠
  LEGACY : collar=0.25, 不计重叠  ← 多数公开数字用这一档
★ 官方 3D-Speaker 报 VoxConverse DER 11.75%, **但未注明 profile** ⇒ 只能当量级参考, 不能当验收线。
★ 本实现 include_overlap=False ⇒ **结构上不检测重叠语音**, STRICT 档必然吃亏, 这是如实的代价不是缺陷。
"""
import json, os, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOX = "/Volumes/data/cce-eval-corpora/voxconverse"
TOOL = "/Volumes/data/cce-eval-corpora/tools/3D-Speaker"
N = 20
PROFILES = {"STRICT": dict(collar=0.0, skip_overlap=False),
            "LEGACY": dict(collar=0.25, skip_overlap=True)}
OFFICIAL_VOXCONVERSE_DER = 0.1175      # 3D-Speaker 官方报的数, profile 未注明


def load_rttm(path):
    from pyannote.core import Annotation, Segment
    ann = Annotation()
    for line in open(path, encoding="utf-8"):
        p = line.split()
        if len(p) >= 8 and p[0] == "SPEAKER":
            st, dur = float(p[3]), float(p[4])
            ann[Segment(st, st + dur)] = p[7]
    return ann


def main():
    rttm_dir = os.path.join(VOX, "voxconverse-master", "dev")
    wav_dir = os.path.join(VOX, "audio")
    for cand in (os.path.join(VOX, "audio"), os.path.join(VOX, "dev"), VOX):
        if os.path.isdir(cand) and any(f.endswith(".wav") for f in os.listdir(cand)):
            wav_dir = cand; break
    if not (os.path.isdir(rttm_dir) and os.path.isdir(wav_dir)):
        print(f"★ 无语料(rttm={rttm_dir} wav={wav_dir}) —— 只在备好语料的机器上成立, **不出结论**。")
        return 2
    sys.path.insert(0, TOOL)
    import warnings; warnings.filterwarnings("ignore")
    from speakerlab.bin.infer_diarization import Diarization3Dspeaker
    from pyannote.core import Annotation, Segment
    from pyannote.metrics.diarization import DiarizationErrorRate
    import soundfile as sf

    names = sorted(f[:-5] for f in os.listdir(rttm_dir) if f.endswith(".rttm"))
    names = [n for n in names if os.path.exists(os.path.join(wav_dir, n + ".wav"))][:N]
    if len(names) < 5:
        print(f"★ 可用录音仅 {len(names)} < 5 ⇒ INSUFFICIENT"); return 1

    print(f"3D-Speaker · include_overlap=False · hf_access_token=None(**无 token 路径**)")
    print(f"VoxConverse dev 取排序前 {len(names)} 段(不挑)\n" + "-" * 72)
    pipe = Diarization3Dspeaker(device="cpu", include_overlap=False, hf_access_token=None)
    scorers = {k: DiarizationErrorRate(**v) for k, v in PROFILES.items()}
    rtfs, per = [], []
    for n in names:
        w = os.path.join(wav_dir, n + ".wav")
        ref = load_rttm(os.path.join(rttm_dir, n + ".rttm"))
        info = sf.info(w); dur = info.frames / info.samplerate
        t0 = time.time(); segs = pipe(w); dt = time.time() - t0
        rtfs.append(dt / dur)
        hyp = Annotation()
        for st, ed, spk in segs:
            hyp[Segment(float(st), float(ed))] = str(spk)
        row = {"id": n, "sec": round(dur, 1), "rtf": round(dt / dur, 3),
               "ref_spk": len(ref.labels()), "hyp_spk": len(hyp.labels())}
        for k, s in scorers.items():
            row[k] = round(s(ref, hyp), 4)
        per.append(row)
        print(f"  {n:14} {dur:6.0f}s  RTF {row['rtf']:.2f}  说话人 参考{row['ref_spk']}/预测{row['hyp_spk']}  "
              f"STRICT {row['STRICT']:.3f}  LEGACY {row['LEGACY']:.3f}")

    print("-" * 72)
    agg = {k: abs(s) for k, s in scorers.items()}       # pyannote 的 abs() 给累计 DER
    out = {"block": "DIARIZATION_DER_GEN1", "measured_at": "2026-09-04",
           "implementation": "3D-Speaker (modelscope) CAM++ · include_overlap=False",
           "corpus": "VoxConverse dev", "n": len(names),
           "★access_fields_kept_separate": {
               "account_required": False, "token_required": False,
               "click_through_terms_required": False,
               "license_restriction": "无(ModelScope 权重, Apache-2.0 代码)"},
           "★why_four_fields": ("「无账号/无token/无点击条款/无许可限制」是四件事, 压成一个 OPEN 会出错: "
                                "sherpa-onnx 的 reverb 权重可匿名直链但**非商用**; "
                                "NeMo 的 NGC 下载即视为接受条款。"),
           "der_profiles": {k: {"params": PROFILES[k], "aggregate": round(agg[k], 4),
                                "median_per_file": round(statistics.median(r[k] for r in per), 4)}
                            for k in PROFILES},
           "★no_cross_profile_ranking": "两档参数不同, **禁止**拿一档的数去和另一档比。",
           "rtf_cpu": {"median": round(statistics.median(rtfs), 3),
                       "max": round(max(rtfs), 3),
                       "★measured_locally": "官方无同口径 CPU RTF, 此数由本机实测铸值"},
           "official_reference": {"value": OFFICIAL_VOXCONVERSE_DER,
                                  "★profile_unknown": "官方未注明 collar/overlap 口径 ⇒ 只作量级参考, **不作验收线**"},
           "★structural_limit": "include_overlap=False ⇒ **结构上不检测重叠语音**; STRICT 档必然吃亏, 是如实代价不是缺陷",
           "per_file": per}
    for k in PROFILES:
        print(f"{k:7} DER 累计 {agg[k]:.4f} · 逐段中位 {out['der_profiles'][k]['median_per_file']:.4f}  "
              f"(collar={PROFILES[k]['collar']}, 跳过重叠={PROFILES[k]['skip_overlap']})")
    print(f"CPU RTF 中位 {statistics.median(rtfs):.3f} · 最差 {max(rtfs):.3f}")
    print(f"★ 官方报 VoxConverse DER {OFFICIAL_VOXCONVERSE_DER} 但**未注明 profile** ⇒ 只作量级参考")
    json.dump(out, open(os.path.join(ROOT, "tests/data/phase2/diarization_der.json"),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
