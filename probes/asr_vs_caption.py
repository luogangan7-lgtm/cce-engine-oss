#!/usr/bin/env python3
"""ASR vs 烧录字幕 —— **模态独立**的交叉核验。前登记 tests/data/phase2/asr_vs_caption_prereg.json

★ 字幕**不是真值**。四种系统性偏倚(改写/缩短 · 加标点 · 漏语气词 · OCR 自身误差)已写在预注册里。
  它只给**约束**, 不给准确率, 不改变「社媒音轨真准确率未测」这个状态。
"""
import glob, json, os, statistics, sys, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
from asr_agreement_social import norm_units          # 归一化与那条实验**逐字相同**
SRC = "/Volumes/data/viral-skill-eval/results/video_parse"
SPEC = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_vs_caption_prereg.json"),
                      encoding="utf-8"))


def lcs_len(a, b):
    """有序最长公共子序列长度 —— 召回的分子。"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, 1):
            cur[j] = prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1])
        prev = cur
    return prev[-1]


def caption_text(ocr):
    """逐帧字幕**按相邻去重**再拼接 —— 同一句会在连续多帧重复出现。"""
    if not isinstance(ocr, dict):
        return ""
    out, last = [], None
    for _t, v in sorted(ocr.items(), key=lambda kv: float(kv[0]) if _num(kv[0]) else 0.0):
        for x in (v if isinstance(v, list) else [v]):
            s = str(x).strip()
            if s and s != last:
                out.append(s); last = s
    return " ".join(out)


def _num(s):
    try:
        float(s); return True
    except Exception:
        return False


def main():
    if not os.path.isdir(SRC):
        print(f"★ 无本机解析产物 {SRC} —— 不出结论。"); return 2
    rows, rec_cap, rec_asr = [], [], []
    for f in sorted(glob.glob(f"{SRC}/*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        au = d.get("audio")
        tr = au.get("transcript") if isinstance(au, dict) else ""
        cap = caption_text(d.get("ocr"))
        if not (tr and cap):
            continue
        uc, lc = norm_units(cap)
        ua, la = norm_units(str(tr))
        if not uc or not ua or lc != la:
            continue
        m = lcs_len(uc, ua)
        r_cap = m / len(uc)          # 字幕的字有多少出现在 ASR 里(以字幕为参考)
        r_asr = m / len(ua)          # 反方向
        rec_cap.append(r_cap); rec_asr.append(r_asr)
        rows.append((os.path.basename(f)[:24], len(uc), len(ua), round(r_cap, 3), round(r_asr, 3)))

    print(f"预注册: {SPEC['block']} | 既有产物, **零新增调用**")
    print(f"可比样本 {len(rows)} 份\n" + "-" * 74)
    for n, nc, na, rc, ra in rows[:8]:
        print(f"  {n:26} 字幕 {nc:5} 字 / ASR {na:5} 字  字幕召回 {rc:.3f}  ASR召回 {ra:.3f}")
    if len(rows) > 8:
        print(f"  … 另 {len(rows)-8} 份")
    print("-" * 74)
    if len(rec_cap) < 30:
        print(f"★ 有效仅 {len(rec_cap)} < 30 ⇒ INSUFFICIENT"); return 1

    # ★ 自比基准 —— 归一化或 LCS 一坏, 这条先红
    _u, _ = norm_units("你们敢信这个东西又是蓝牙耳机")
    assert lcs_len(_u, _u) == len(_u), "★ 自比不满分 ⇒ 归一化或 LCS 坏了"

    med = statistics.median(rec_cap)
    q = statistics.quantiles(rec_cap, n=4)
    varied = len(set(round(x, 3) for x in rec_cap)) > 3
    if not varied or not (0.05 < med < 0.95):
        print(f"★ 中位 {med:.3f} 落在 (0.05,0.95) 之外或取值无变异 ⇒ **先查仪器**, 不当结论")
        if not varied:
            return 1
    # ★ 2026-09-04 调研后更正推论(判据本身未追改, 见预注册的 ★AMENDED 段):
    #   字幕差异**既不是**真 WER 的上界**也不是**下界 —— ASR 逐字正确而字幕被压缩会**高估**错误,
    #   字幕写错而 ASR 错得一样会**低估**错误。⇒ 判决词一律降级为「弱一致」, 不作方向性约束。
    decision = ("WEAK_AGREEMENT_LOW" if med < 0.6 else
                "WEAK_AGREEMENT_HIGH" if med > 0.9 else "WEAK_AGREEMENT_MID")
    print(f"字幕召回(以字幕为参考): 中位 {med:.4f} · 四分位 {q[0]:.4f}/{q[2]:.4f} · "
          f"范围 {min(rec_cap):.4f}–{max(rec_cap):.4f}")
    print(f"ASR 召回(反方向)      : 中位 {statistics.median(rec_asr):.4f}")
    print(f"非退化: 取值 {len(set(round(x,3) for x in rec_cap))} 种 · 中位在区间内 {0.05<med<0.95}")
    print(f"⇒ **{decision}**")

    out = {"block": SPEC["block"], "measured_at": "2026-09-04",
           "n": len(rec_cap), "★zero_new_calls": True,
           "caption_recall": {"median": round(med, 4), "q1": round(q[0], 4), "q3": round(q[2], 4),
                              "min": round(min(rec_cap), 4), "max": round(max(rec_cap), 4)},
           "asr_recall": {"median": round(statistics.median(rec_asr), 4)},
           "degeneracy_pass": varied and 0.05 < med < 0.95,
           "decision": decision,
           "★modality_independent": ("OCR 败于花字/遮挡/低对比, ASR 败于噪声/口音/BGM —— "
             "**失效模式不重叠** ⇒ 比两个 ASR 的一致更有约束力"),
           "★caption_is_not_ground_truth": SPEC["★this_is_not_ground_truth"],
           "★what_this_does_not_establish": SPEC["★what_this_does_not_establish"],
           "★decision_rule_frozen_at": SPEC["prereg_written_at"]}
    json.dump(out, open(os.path.join(ROOT, "tests/data/phase2/asr_vs_caption.json"),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"★ {out['★what_this_does_not_establish']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
