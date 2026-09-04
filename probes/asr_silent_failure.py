#!/usr/bin/env python3
"""历史解析产物里的 ASR **静默失败**。前登记 tests/data/phase2/asr_silent_failure_prereg.json

判据先于扩样冻结。这里只执行。
★ 它是**字幕交叉核验的非退化闸**撞出来的 —— 参照方没坏, 被参照的 ASR 才是坏的。
"""
import glob, json, os, statistics, sys, warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
SPEC = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_silent_failure_prereg.json"),
                      encoding="utf-8"))
SRC = "/Volumes/data/viral-skill-eval/results/video_parse"
AUD = "/Volumes/data/viral-skill-eval/assets/audio_cache"
N_SHORT, N_LONG, VOCAL_GATE = 40, 20, 0.5


def groups():
    short, long_ = [], []
    for f in sorted(glob.glob(f"{SRC}/*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        au = d.get("audio")
        tr = str((au or {}).get("transcript") or "").strip()
        stem = os.path.basename(f)[:-5]
        w = os.path.join(AUD, stem + ".wav")
        if not os.path.exists(w):
            continue
        speech_ok = bool(((d.get("completeness") or {}).get("G1_layers") or {}).get("speech"))
        (short if len(tr) < 20 else long_ if len(tr) >= 200 else []).append(
            (stem, len(tr), w, speech_ok))
    return short[:N_SHORT], long_[:N_LONG]


def main():
    if not (os.path.isdir(SRC) and os.path.isdir(AUD)):
        print(f"★ 无本机产物或音频 —— 不出结论。"); return 2
    warnings.filterwarnings("ignore")
    import cce_audio_separate as SEP
    if not SEP.available():
        print("★ demucs 未装 —— 不出结论。"); return 2
    short, long_ = groups()
    print(f"预注册: {SPEC['block']} | 短转写 {len(short)} 份 + 长转写对照 {len(long_)} 份(排序取前 N, 不挑)")
    print(f"判据: 短转写组 vocals 占比 >= {VOCAL_GATE} 的比例 = **失败率下界**\n" + "-" * 72)

    def scan(rows, label):
        out = []
        for stem, n, w, ok in rows:
            r = SEP.separate(w, max_seconds=30)
            if r["status"] != "ok":
                continue
            v = r["energy_share"]["vocals"]
            out.append({"id": stem[:20], "chars": n, "vocals": round(v, 4), "speech_true": ok})
        print(f"  {label}: {len(out)} 份可测 · vocals 中位 "
              f"{statistics.median(x['vocals'] for x in out):.3f}" if out else f"  {label}: 无")
        return out

    S = scan(short, "短转写(<20字)")
    L = scan(long_, "长转写(>=200字)")
    if len(S) < 20 or len(L) < 8:
        print(f"★ 样本不足(短 {len(S)} / 长 {len(L)}) ⇒ INSUFFICIENT"); return 1

    ms, ml = statistics.median(x["vocals"] for x in S), statistics.median(x["vocals"] for x in L)
    separable = abs(ml - ms) >= 0.2
    fail_lb = sum(x["vocals"] >= VOCAL_GATE for x in S) / len(S)
    mislabeled = sum(x["vocals"] >= VOCAL_GATE and x["speech_true"] for x in S)
    decision = ("SILENT_FAILURE_CONFIRMED" if fail_lb >= 0.30 else
                "MOSTLY_NO_SPEECH" if fail_lb < 0.10 else "MIXED")
    print("-" * 72)
    print(f"短转写组 vocals 中位 {ms:.3f} · 长转写组 {ml:.3f} · 可分(差>=0.2): {separable}")
    print(f"**vocals >= {VOCAL_GATE} 的比例 = {fail_lb:.1%}**(失败率**下界**) ⇒ **{decision}**")
    print(f"其中标着 speech=true 的: **{mislabeled} / {len(S)}** —— 那是**假的 ok**")
    if not separable:
        print("★ 两组分布不可分 ⇒ 分离本身没有判别力, 结论不成立")

    out = {"block": SPEC["block"], "measured_at": "2026-09-04",
           "n_short": len(S), "n_long": len(L),
           "vocals_median": {"short": round(ms, 4), "long": round(ml, 4)},
           "separable": separable,
           "failure_rate_lower_bound": round(fail_lb, 4),
           "★why_lower_bound": ("只数 vocals>=0.5 的。人声占比低但**确有口播**的(远景/小声/被 BGM 压过)"
             "也可能是失败, 但分离分不出来 ⇒ 真实失败率**只会更高**。"),
           "mislabeled_speech_true": mislabeled,
           "decision": decision,
           "★how_it_surfaced": SPEC["how_it_surfaced"],
           "★must_fix_regardless": SPEC["★what_must_be_fixed_regardless"],
           "per_item_short": S, "per_item_long": L}
    json.dump(out, open(os.path.join(ROOT, "tests/data/phase2/asr_silent_failure.json"),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
