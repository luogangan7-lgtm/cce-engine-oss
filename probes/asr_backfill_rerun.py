#!/usr/bin/env python3
"""回填: 历史 ASR 失败是「那一轮坏了」还是「模型对这类素材本就不行」?
前登记 tests/data/phase2/asr_backfill_prereg.json

两者修法完全不同 —— 前者重跑即可, 后者要换模型或加前处理。
"""
import glob, json, os, statistics, sys, warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
SPEC = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_backfill_prereg.json"),
                      encoding="utf-8"))
SRC = "/Volumes/data/viral-skill-eval/results/video_parse"
AUD = "/Volumes/data/viral-skill-eval/assets/audio_cache"
RATE_GATE, VOCAL_GATE = 0.15, 0.5
N_CONTROL = 12


def rate(tr, dur):
    return (len(str(tr or "").strip()) / dur) if dur else None


def collect():
    short, ctrl = [], []
    for f in sorted(glob.glob(f"{SRC}/*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        au = d.get("audio"); dur = d.get("duration") or 0
        tr = str((au or {}).get("transcript") or "").strip()
        r = rate(tr, dur)
        stem = os.path.basename(f)[:-5]
        w = os.path.join(AUD, stem + ".wav")
        if r is None or not os.path.exists(w):
            continue
        (short if r < RATE_GATE else ctrl).append((stem, len(tr), dur, r, w))
    return short, ctrl[:N_CONTROL]


def main():
    if not (os.path.isdir(SRC) and os.path.isdir(AUD)):
        print("★ 无本机产物或音频 —— 不出结论。"); return 2
    warnings.filterwarnings("ignore")
    import cce_audio_separate as SEP
    from funasr import AutoModel
    if not SEP.available():
        print("★ demucs 未装 —— 不出结论。"); return 2
    m = AutoModel(model="iic/SenseVoiceSmall", trust_remote_code=False, disable_update=True)

    def asr(path):
        import re
        try:
            r = m.generate(input=path, language="auto", use_itn=False)
            return re.sub(r"<\|[^|]*\|>", " ", r[0]["text"] if r else "").strip()
        except Exception:
            return None

    short, ctrl = collect()
    print(f"预注册: {SPEC['block']} | 短转写 {len(short)} 份(全取, 不挑) + 对照 {len(ctrl)} 份")
    print("-" * 74)

    # ★ 退化闸①: 对照组重跑必须仍是长转写 —— 否则是**我的重跑环境**坏了
    ctrl_ok = 0
    for stem, n, dur, r, w in ctrl:
        t = asr(w)
        if t is not None and rate(t, dur) and rate(t, dur) >= RATE_GATE:
            ctrl_ok += 1
    print(f"对照组(历史长转写)重跑后仍达标: **{ctrl_ok}/{len(ctrl)}**")
    if len(ctrl) and ctrl_ok / len(ctrl) < 0.7:
        print("★ 对照组重跑也垮了 ⇒ **我的重跑环境坏了**, 不是历史产物的问题。不出结论。")
        return 1

    rows, high = [], []
    for stem, n, dur, r, w in short:
        s = SEP.separate(w, max_seconds=30)
        vs = s["energy_share"]["vocals"] if s["status"] == "ok" else None
        t = asr(w)
        r2 = rate(t, dur) if t is not None else None
        rec = {"id": stem[:22], "old_chars": n, "dur": round(dur, 1),
               "old_rate": round(r, 4), "vocals": round(vs, 4) if vs is not None else None,
               "new_chars": len(t) if t is not None else None,
               "new_rate": round(r2, 4) if r2 is not None else None,
               "recovered": bool(r2 is not None and r2 >= RATE_GATE)}
        rows.append(rec)
        if vs is not None and vs >= VOCAL_GATE:
            high.append(rec)

    if len(high) < 8:
        print(f"★ 高人声(>= {VOCAL_GATE})的仅 {len(high)} 份 ⇒ INSUFFICIENT"); return 1
    rec_rate = sum(x["recovered"] for x in high) / len(high)
    vm = statistics.median(x["vocals"] for x in rows if x["vocals"] is not None)
    decision = ("HISTORICAL_RUN_WAS_BROKEN" if rec_rate >= 0.5 else
                "ASR_CANNOT_HANDLE_THIS_MATERIAL" if (1 - rec_rate) >= 0.5 else "MIXED")
    print(f"短转写 {len(rows)} 份 · 其中高人声(>= {VOCAL_GATE}) **{len(high)}** 份")
    print(f"vocals 中位 {vm:.3f}(上一实验 0.178, 一致性检查)")
    print(f"高人声那批**重跑后恢复**的比例 = **{rec_rate:.1%}** ⇒ **{decision}**")
    for x in high[:6]:
        print(f"  {x['id']:24} 人声 {x['vocals']:.3f} · 旧 {x['old_chars']:4}字 → 新 {x['new_chars']:5}字 "
              f"· 恢复={x['recovered']}")

    out = {"block": SPEC["block"], "measured_at": "2026-09-04",
           "n_short": len(rows), "n_high_vocals": len(high),
           "control_reran_ok": f"{ctrl_ok}/{len(ctrl)}",
           "vocals_median": round(vm, 4),
           "recovery_rate_high_vocals": round(rec_rate, 4),
           "decision": decision,
           "★what_it_answers": "只答「历史那轮坏没坏」, **不产出 ASR 准确率**(仍无逐字标注)",
           "★control_gate": ("对照组(历史长转写)重跑后仍达标 —— 否则说明是**我的重跑环境**坏了, "
                             "而不是历史产物的问题。这条闸先于主判据。"),
           "per_item": rows}
    json.dump(out, open(os.path.join(ROOT, "tests/data/phase2/asr_backfill_rerun.json"),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
