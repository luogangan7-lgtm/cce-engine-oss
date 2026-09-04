#!/usr/bin/env python3
"""ASR 受控退化曲线 —— 前登记 tests/data/phase2/asr_degradation_prereg.json

★ 唯一能拿到**真 ground truth** 的路: 参考文本我自己写的, 逐字已知。
★ 代价明确: 合成语音无口音/情绪/口误/远近场 ⇒ 这是**上界**, 真实素材只会更难。
  与 OCR 那条合成上界曲线同构, **不产出**真实素材上的准确率。
"""
import json, os, re, statistics, subprocess, sys, tempfile, time, warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_degradation_prereg.json"),
                      encoding="utf-8"))
# 自撰短句: 助听器/日常场景, 逐字已知。改动它 = 换语料, 属判据变更。
SENTENCES = [
    "这款助听器支持蓝牙直连手机", "验配师帮我调了三个通道的增益",
    "电池能用五天不用天天充电", "在餐厅里噪音大的时候要切换模式",
    "我妈妈今年七十二岁听力下降很久了", "先做一个纯音测听再决定买哪一款",
    "耳背式和耳道式各有各的好处", "保修期是两年可以到店免费清洗",
    "刚戴上的时候会觉得声音有点尖", "适应期一般要两到四周",
    "看电视的时候可以用电视伴侣", "洗澡和游泳一定要摘下来",
]
# ★ 2026-09-04 第一版写死 ["Tingting","Eddy","Flo"] —— **Eddy/Flo 输出为空**。
#   原因: 同名音色跨语种(Eddy 既有英文版也有中文版), `say -v Eddy` 选中了**英文版**,
#   把中文读成了别的东西 ⇒ 无退化 CER = 1.0000, 非退化闸拦下。
#   ⇒ 改为**程序化枚举 zh_CN 音色** + 逐个**读回自检**(合成→ASR 能读回原文才收)。
#   与 OCR 那次字体的修法同构: **先验证仪器能产出可读材料, 再测量**。
VOICES = None                                  # 由 pick_voices() 现算


# ★ 本机 `say` 的 9 个 zh_CN 音色里**只有 1 个**通过读回自检(其余是同名的英文音色),
#   而设计要求音色是有变异的 facet(>= 2) ⇒ 改用 edge-tts(8 个中文神经音色), say 作降级路径。
USE_EDGE = True


def zh_voices():
    if USE_EDGE:
        try:
            import asyncio, edge_tts
            vs = asyncio.run(edge_tts.list_voices())
            return sorted(v["ShortName"] for v in vs if v["Locale"].startswith("zh-CN"))
        except Exception:
            pass
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    return [l.split()[0] for l in out.splitlines() if "zh_CN" in l]
BGM_SNR = [None, 10, 5, 0, -5]
MP3_KBPS = [None, 64, 32, 16]


def norm(s):
    return re.sub(r"[^一-鿿0-9A-Za-z]", "", str(s or ""))


def cer(ref, hyp):
    import difflib
    if not ref:
        return 0.0 if not hyp else 1.0
    sm = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    return max(0.0, min(1.0, 1.0 - sum(b.size for b in sm.get_matching_blocks()) / len(ref)))


def witness(p):
    try:
        import soundfile as sf, numpy as np
        x, sr = sf.read(p, dtype="float32")
        if x.ndim > 1: x = x.mean(axis=1)
        return {"bytes": os.path.getsize(p), "sec": round(len(x)/sr, 2),
                "rms_db": round(20*float(np.log10(max(1e-9, (x**2).mean()**0.5))), 2)}
    except Exception as e:                                        # noqa: BLE001
        return {"error": type(e).__name__}


def synth(text, voice, out, retries=3):
    if voice.startswith("zh-CN-"):
        mp3 = out + ".src.mp3"
        # ★ edge-tts 走网络, 偶发失败。重试; 仍失败则由调用方**计数跳过**, **不得静默丢弃**。
        last = None
        for _ in range(retries):
            r = subprocess.run(["edge-tts", "--voice", voice, "--text", text,
                                "--write-media", mp3], capture_output=True)
            if r.returncode == 0 and os.path.exists(mp3) and os.path.getsize(mp3) > 1000:
                break
            last = r.stderr.decode()[:120]
            time.sleep(1.5)
        else:
            raise RuntimeError(f"edge-tts 连续 {retries} 次失败: {last}")
        subprocess.run(["ffmpeg", "-y", "-i", mp3, "-ar", "16000", "-ac", "1", out],
                       check=True, capture_output=True)
        os.remove(mp3)
        return out
    aiff = out + ".aiff"
    subprocess.run(["say", "-v", voice, "-o", aiff, text], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-i", aiff, "-ar", "16000", "-ac", "1", out],
                   check=True, capture_output=True)
    os.remove(aiff)
    return out


def degrade(src, axis, level, out, noise):
    import soundfile as sf, numpy as np
    x, sr = sf.read(src, dtype="float32")
    if x.ndim > 1: x = x.mean(axis=1)
    if axis == "bgm_snr_db" and level is not None:
        n = noise[:len(x)] if len(noise) >= len(x) else np.tile(noise, len(x)//len(noise)+1)[:len(x)]
        ps, pn = (x**2).mean(), (n**2).mean() or 1e-9
        x = x + n * float((ps / (pn * 10**(level/10)))**0.5)
        x = x / max(1.0, float(abs(x).max()))
    wav = out + ".wav"
    sf.write(wav, x, sr)
    mp3_bytes = None
    if axis == "mp3_kbps" and level is not None:
        mp3 = out + ".mp3"
        subprocess.run(["ffmpeg", "-y", "-i", wav, "-b:a", f"{level}k", mp3],
                       check=True, capture_output=True)
        # ★ 见证必须记**中间 mp3** 的字节 —— 往返回 WAV 后字节数几乎不变,
        #   拿它当见证等于没有见证。我第一版就指错了对象。
        mp3_bytes = os.path.getsize(mp3)
        subprocess.run(["ffmpeg", "-y", "-i", mp3, "-ar", "16000", "-ac", "1", wav],
                       check=True, capture_output=True)
        os.remove(mp3)
    return wav, mp3_bytes


def main():
    for tool in ("say", "ffmpeg"):
        if subprocess.run(["which", tool], capture_output=True).returncode:
            print(f"★ 缺 {tool} —— 不出结论。"); return 2
    warnings.filterwarnings("ignore")
    import numpy as np
    from funasr import AutoModel
    m = AutoModel(model="iic/SenseVoiceSmall", trust_remote_code=False, disable_update=True)
    rng = np.random.default_rng(20260904)
    noise = rng.normal(0, 1, 16000 * 30).astype("float32")   # 冻结种子的粉噪代理

    def asr(p):
        try:
            r = m.generate(input=p, language="zh", use_itn=False)
            return norm(re.sub(r"<\|[^|]*\|>", " ", r[0]["text"] if r else ""))
        except Exception:
            return ""

    # ★ 音色读回自检: 只收能把中文读回来的音色
    probe_txt = SENTENCES[0]
    voices = []
    with tempfile.TemporaryDirectory() as vtd:
        for v in zh_voices():
            try:
                p = synth(probe_txt, v, os.path.join(vtd, f"v_{v}.wav"))
                if cer(norm(probe_txt), asr(p)) <= 0.15:
                    voices.append(v)
            except Exception:
                continue
    print(f"zh_CN 音色 {len(zh_voices())} 个 · **读回自检通过 {len(voices)} 个**: {voices}")
    if len(voices) < 2:
        print("★ 可用音色 < 2 ⇒ 无法把「音色」当作有变异的 facet, 不出曲线。"); return 1
    print(f"预注册: {SPEC['block']} | {len(SENTENCES)} 句 × {len(voices)} 音色")
    result = {}
    with tempfile.TemporaryDirectory() as td:
        base, skipped = {}, []
        for si, s in enumerate(SENTENCES):
            for v in voices:
                try:
                    base[(si, v)] = synth(s, v, os.path.join(td, f"s{si}_{v}.wav"))
                except Exception as e:                            # noqa: BLE001
                    skipped.append({"sentence": si, "voice": v, "why": str(e)[:80]})
        n_planned = len(SENTENCES) * len(voices)
        print(f"合成 {len(base)}/{n_planned} 条 · **跳过 {len(skipped)} 条**(如实计数, 不静默丢弃)")
        if len(base) < n_planned * 0.8:
            print(f"★ 合成成功率 {len(base)/n_planned:.0%} < 80% ⇒ 样本已被网络失败选择性削减, 不出曲线。")
            return 1
        # ★ 退化闸①: 无退化时 CER 必须近 0
        clean = [cer(norm(SENTENCES[si]), asr(p)) for (si, v), p in list(base.items())]
        c0 = statistics.median(clean)
        print(f"无退化 CER 中位 **{c0:.4f}**(闸: 须 < 0.15)")
        if c0 >= 0.15:
            print("★ 无退化就错这么多 ⇒ **合成或归一化坏了**, 不是 ASR 差。先查仪器, 不出曲线。")
            return 1

        for axis, levels in (("bgm_snr_db", BGM_SNR), ("mp3_kbps", MP3_KBPS)):
            curve = []
            for lv in levels:
                cers, w = [], None
                for (si, v), src in base.items():
                    p, mb = degrade(src, axis, lv, os.path.join(td, f"d{si}_{v}"), noise)
                    cers.append(cer(norm(SENTENCES[si]), asr(p)))
                    if w is None:
                        w = witness(p)
                        w["mp3_bytes"] = mb        # ★ 中间 mp3 的字节, 压缩的真见证
                curve.append({"level": lv, "cer_median": round(statistics.median(cers), 4),
                              "cer_q3": round(statistics.quantiles(cers, n=4)[2], 4),
                              "cer_max": round(max(cers), 4), "witness": w})
            rise = curve[-1]["cer_median"] - curve[0]["cer_median"]
            # ★ 「无分辨力」必须有见证证明**处理确实施加了**, 否则与「仪器坏了」分不开
            wit = [c["witness"] for c in curve]
            if axis == "mp3_kbps":
                mbs = [w.get("mp3_bytes") for w in wit if w.get("mp3_bytes")]
                applied = len(mbs) >= 2 and max(mbs) / min(mbs) >= 1.5
                wproof = f"中间 mp3 字节 {min(mbs)}–{max(mbs)}(比 {max(mbs)/min(mbs):.1f}x)" if mbs else "无"
            else:
                rms = [w.get("rms_db") for w in wit if w.get("rms_db") is not None]
                applied = len(rms) >= 2 and (max(rms) - min(rms)) >= 1.0
                wproof = f"rms {min(rms)}–{max(rms)} dB" if rms else "无"
            result[axis] = {"curve": curve, "rise": round(rise, 4),
                            "resolution": "OK" if rise >= 0.10 else "NO_RESOLUTION",
                            "★degradation_applied": applied, "★witness_proof": wproof,
                            "★if_not_applied": ("见证显示处理**没真的施加** ⇒ 「无分辨力」不成立, "
                                                "是仪器问题" if not applied else "见证证明处理确实施加了")}
            pts = " ".join(f"{c['level']}:{c['cer_median']:.2f}" for c in curve)
            print(f"  {axis:14} {pts}   上升 {rise:+.3f} "
                  f"{'' if rise>=0.10 else '⇒ NO_RESOLUTION(这条轴没分辨力)'}")

    out = {"block": SPEC["block"], "measured_at": "2026-09-04",
           "n_sentences": len(SENTENCES), "voices": voices,
           "★voice_self_check": "只收**读回自检**通过的 zh_CN 音色 —— 第一版写死的 Eddy/Flo 是英文版同名音色, 输出为空",
           "clean_cer_median": round(c0, 4), "axes": result,
           "n_synth_ok": len(base), "n_synth_skipped": len(skipped), "skipped": skipped,
           "★is_upper_bound": SPEC["★what_it_gives_and_costs"]["costs"],
           "★not_claimed": SPEC["★what_it_gives_and_costs"]["★not_claimed"],
           "★witness_per_level": "每档记 bytes/sec/rms_db —— 「无分辨力」要能与「仪器坏了」区分"}
    json.dump(out, open(os.path.join(ROOT, "tests/data/phase2/asr_degradation_curve.json"),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"★ {out['★not_claimed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
