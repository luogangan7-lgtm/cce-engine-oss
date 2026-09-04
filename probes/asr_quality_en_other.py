#!/usr/bin/env python3
"""ASR: LibriSpeech **test-other**(带噪/口音更重) —— 与 test-clean 配对报, 不合并。

调研提醒(已核实): 英文 ASR 主基准应分别报 test-clean 与 test-other,
**不要把两者拼成一个无权重的「English ASR accuracy」**。

抽样与归一化与 GEN2 逐字相同(每说话人取字典序第一条; 换归一化就不可比)。
"""
import json, os, re, statistics, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
from asr_quality_en import norm, wer
OTHER = "/Volumes/data/cce-eval-corpora/LibriSpeech/test-other"


def stratified(corpus):
    by = collections.defaultdict(list)
    for dp, _, fs in os.walk(corpus):
        for f in fs:
            if f.endswith(".trans.txt"):
                for line in open(os.path.join(dp, f), encoding="utf-8"):
                    uid, _, text = line.strip().partition(" ")
                    fl = os.path.join(dp, uid + ".flac")
                    if text and os.path.exists(fl):
                        by[uid.split("-")[0]].append((uid, fl, text))
    return [sorted(v)[0] for _, v in sorted(by.items())]


def main():
    if not os.path.isdir(OTHER):
        print(f"★ 无 test-other 语料 —— 不出结论。"
              "备料: curl -L https://www.openslr.org/resources/12/test-other.tar.gz | tar xz")
        return 2
    rows = stratified(OTHER)
    print(f"LibriSpeech **test-other** · 每说话人一条 · {len(rows)} 个说话人")
    if len(rows) <= 10:
        print("★ 说话人 <= 10 ⇒ NO_ADDED_RESOLUTION"); return 1
    import warnings; warnings.filterwarnings("ignore")
    from funasr import AutoModel
    m = AutoModel(model="iic/SenseVoiceSmall", trust_remote_code=False, disable_update=True)
    wers = []
    for uid, fl, ref in rows:
        try:
            r = m.generate(input=fl, language="en", use_itn=False)
            hyp = norm(re.sub(r"<\|[^|]*\|>", " ", r[0]["text"] if r else ""))
        except Exception:
            continue
        wers.append(wer(norm(ref), hyp))
    if len(wers) < 10:
        print("★ 有效样本不足 ⇒ INSUFFICIENT"); return 1
    qs = statistics.quantiles(wers, n=4)
    clean = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_quality_en_gen2.json"),
                           encoding="utf-8"))["wer"]
    out = {"block": "EXTRACTION_QUALITY_EN_ASR_TEST_OTHER", "measured_at": "2026-09-04",
           "corpus": "LibriSpeech test-other", "sampling": "每说话人第一条(与 GEN2 同)",
           "n_speakers": len(rows), "n": len(wers),
           "wer": {"median": round(statistics.median(wers), 4),
                   "mean": round(sum(wers)/len(wers), 4),
                   "q1": round(qs[0], 4), "q3": round(qs[2], 4), "max": round(max(wers), 4)},
           "test_clean_gen2_for_comparison": clean,
           "★never_merge": ("test-clean 与 test-other **不得**拼成一个无权重的「English ASR accuracy」——"
                            "两者难度不同, 合并等于用一个数掩盖噪声条件下的表现。"),
           "★degeneracy": len(set(round(w, 3) for w in wers)) > 3}
    json.dump(out, open(os.path.join(ROOT, "tests/data/phase2/asr_quality_en_other.json"),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"test-other WER: 中位 {out['wer']['median']} · 均值 {out['wer']['mean']} · 最差 {out['wer']['max']}")
    print(f"test-clean(GEN2): 中位 {clean['median']} · 均值 {clean['mean']}")
    print(f"★ 两者**分别报**, 不合并 —— 难度不同, 合并会掩盖带噪条件下的表现")
    return 0


if __name__ == "__main__":
    sys.exit(main())
