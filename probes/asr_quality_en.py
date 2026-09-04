#!/usr/bin/env python3
"""英文 ASR 抽取质量(WER) —— 前登记 tests/data/phase2/extraction_quality_en_prereg.json

判据、抽样、归一化在测量前冻结, 见该文件与 git。这里只执行。
★ 判据不是我拍的合格线, 是「与公开报告值是否同量级」—— 那测的是**我的集成有没有坏**。
"""
import json, os, re, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
CORPUS = "/Volumes/data/cce-eval-corpora/LibriSpeech/test-clean"
SPEC = json.load(open(os.path.join(ROOT, "tests/data/phase2/extraction_quality_en_prereg.json"),
                      encoding="utf-8"))
N = 100


def norm(s: str) -> str:
    """LibriSpeech 约定: 全大写 · 去标点 · 折空白。转写侧同规则。"""
    s = (s or "").upper()
    s = re.sub(r"[^A-Z0-9' ]+", " ", s)
    return " ".join(s.split())


def wer(ref: str, hyp: str) -> float:
    r, h = ref.split(), hyp.split()
    if not r:
        return 0.0 if not h else 1.0
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)] / len(r)


def utterances():
    out = []
    for dp, _, fs in os.walk(CORPUS):
        for f in fs:
            if f.endswith(".trans.txt"):
                for line in open(os.path.join(dp, f), encoding="utf-8"):
                    uid, _, text = line.strip().partition(" ")
                    flac = os.path.join(dp, uid + ".flac")
                    if text and os.path.exists(flac):
                        out.append((uid, flac, text))
    return sorted(out)[:N]          # 字典序取前 N, **不挑**


def main():
    if not os.path.isdir(CORPUS):
        print(f"★ 无语料 {CORPUS} —— 本探针只在备好语料的机器上成立, **不出结论**。"
              "备料: curl -L https://www.openslr.org/resources/12/test-clean.tar.gz | tar xz")
        return 2
    rows = utterances()
    print(f"预注册: {SPEC['block']} | 语料 LibriSpeech test-clean | "
          f"取前 {len(rows)} 条(字典序, 不挑)")
    print("模型: iic/SenseVoiceSmall via funasr —— 与 cce_video_parse 调用逐字相同\n" + "-" * 72)

    import warnings; warnings.filterwarnings("ignore")
    from funasr import AutoModel
    m = AutoModel(model="iic/SenseVoiceSmall", trust_remote_code=False, disable_update=True)

    wers, bad, samples = [], 0, []
    for i, (uid, flac, ref) in enumerate(rows):
        try:
            r = m.generate(input=flac, language="en", use_itn=False)
            hyp_raw = r[0]["text"] if r else ""
        except Exception as e:                                   # noqa: BLE001
            bad += 1; continue
        # SenseVoice 会带 <|en|><|EMO|> 之类的标签, 去掉后再归一化
        hyp = norm(re.sub(r"<\|[^|]*\|>", " ", hyp_raw))
        w = wer(norm(ref), hyp)
        wers.append(w)
        if i < 3:
            samples.append((uid, norm(ref)[:60], hyp[:60], round(w, 3)))

    for uid, r_, h_, w in samples:
        print(f"  {uid}\n     参考: {r_}\n     识别: {h_}\n     WER {w}")

    print("-" * 72)
    if len(wers) < 90:
        print(f"★ 有效条目仅 {len(wers)} < 90 ⇒ INSUFFICIENT"); return 1
    qs = statistics.quantiles(wers, n=4)
    med = statistics.median(wers)
    agg = sum(wers) / len(wers)
    varied = len(set(round(w, 3) for w in wers)) > 3
    print(f"逐条 WER: 中位 {med:.4f} · 四分位 {qs[0]:.4f}/{qs[1]:.4f}/{qs[2]:.4f} · "
          f"最差 {max(wers):.4f} · 均值 {agg:.4f}")
    print(f"非退化(逐条有变异): {'过' if varied else '**不过** —— 全同值说明测量坏了'}")
    out = {"block": SPEC["block"] + ":ASR", "measured_at": "2026-09-04",
           "corpus": "LibriSpeech test-clean", "n": len(wers), "failed": bad,
           "model": "iic/SenseVoiceSmall (funasr)",
           "wer": {"median": round(med, 4), "mean": round(agg, 4),
                   "q1": round(qs[0], 4), "q3": round(qs[2], 4), "max": round(max(wers), 4)},
           "degeneracy_pass": varied,
           "★normalization": "LibriSpeech 约定: 大写/去标点/折空白; 识别侧先剥 <|...|> 标签",
           "★criterion": "与公开报告值同量级 ⇒ 集成没坏; 差一倍以上 ⇒ 是我的集成有缺陷"}
    json.dump(out, open(os.path.join(ROOT, "tests/data/phase2/asr_quality_en.json"),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n★ 下一步(判据要求): 现查 SenseVoiceSmall 官方报告的 test-clean WER 并记录出处, "
          f"与实测 {med:.4f} 比对量级。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
