#!/usr/bin/env python3
"""ASR GEN2: 说话人分层 —— 前登记 tests/data/phase2/asr_quality_en_gen2_prereg.json

GEN1 严格执行了「字典序前 100」, 但后果是只覆盖 2 个说话人。
★ 不改 GEN1 的规则(看到结果后改预注册是禁止的); GEN2 是**另一个**实验, 两个结果都报。
"""
import json, os, re, statistics, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
from asr_quality_en import CORPUS, norm, wer                       # 归一化与 GEN1 **逐字相同**

SPEC = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_quality_en_gen2_prereg.json"),
                      encoding="utf-8"))
G1 = json.load(open(os.path.join(ROOT, "tests/data/phase2/asr_quality_en.json"), encoding="utf-8"))


def stratified():
    """每个说话人取其字典序**第一条** —— 覆盖全部说话人。"""
    by = collections.defaultdict(list)
    for dp, _, fs in os.walk(CORPUS):
        for f in fs:
            if f.endswith(".trans.txt"):
                for line in open(os.path.join(dp, f), encoding="utf-8"):
                    uid, _, text = line.strip().partition(" ")
                    flac = os.path.join(dp, uid + ".flac")
                    if text and os.path.exists(flac):
                        by[uid.split("-")[0]].append((uid, flac, text))
    return [sorted(v)[0] for _, v in sorted(by.items())]


def main():
    if not os.path.isdir(CORPUS):
        print(f"★ 无语料 {CORPUS} —— 不出结论。"); return 2
    rows = stratified()
    print(f"预注册: {SPEC['block']} | 每个说话人取字典序第一条 | 共 {len(rows)} 个说话人")
    if len(rows) <= 10:
        print(f"★ 说话人仅 {len(rows)} <= 10 ⇒ **NO_ADDED_RESOLUTION** —— "
              "GEN2 相对 GEN1 没增加任何东西, 不记作「确认了 GEN1」"); return 1
    print("-" * 72)
    import warnings; warnings.filterwarnings("ignore")
    from funasr import AutoModel
    m = AutoModel(model="iic/SenseVoiceSmall", trust_remote_code=False, disable_update=True)

    per, wers = [], []
    for uid, flac, ref in rows:
        try:
            r = m.generate(input=flac, language="en", use_itn=False)
            hyp = norm(re.sub(r"<\|[^|]*\|>", " ", r[0]["text"] if r else ""))
        except Exception:
            continue
        w = wer(norm(ref), hyp)
        wers.append(w); per.append({"speaker": uid.split("-")[0], "utt": uid, "wer": round(w, 4)})
    if len(wers) < 10:
        print(f"★ 有效仅 {len(wers)} ⇒ INSUFFICIENT"); return 1

    qs = statistics.quantiles(wers, n=4)
    med = statistics.median(wers)
    g1 = G1["wer"]
    inside = g1["q1"] <= med <= g1["q3"]
    varied = len(set(round(w, 3) for w in wers)) > 3
    print(f"GEN2 逐条 WER: 中位 {med:.4f} · 四分位 {qs[0]:.4f}/{qs[2]:.4f} · "
          f"最差 {max(wers):.4f} · 均值 {sum(wers)/len(wers):.4f}")
    print(f"GEN1(2 个说话人)   : 中位 {g1['median']} · 四分位 {g1['q1']}/{g1['q3']} · 均值 {g1['mean']}")
    print(f"非退化: 说话人 {len(rows)} > 10 ✓ · 逐条有变异 {'✓' if varied else '**✗**'}")
    verdict = ("GEN1_CONSISTENT" if inside else "GEN1_WAS_OPTIMISTIC"
               if med > g1["q3"] else "GEN1_WAS_PESSIMISTIC")
    print(f"GEN2 中位落在 GEN1 四分位区间内: {inside} ⇒ **{verdict}**")

    out = {"block": SPEC["block"], "measured_at": "2026-09-04",
           "corpus": "LibriSpeech test-clean", "sampling": "每说话人第一条, 覆盖全部说话人",
           "n_speakers": len(rows), "n": len(wers),
           "wer": {"median": round(med, 4), "mean": round(sum(wers)/len(wers), 4),
                   "q1": round(qs[0], 4), "q3": round(qs[2], 4), "max": round(max(wers), 4)},
           "gen1_for_comparison": g1, "degeneracy_pass": varied and len(rows) > 10,
           "decision": verdict,
           "★both_reported": "GEN1 与 GEN2 抽样规则不同, **两个结果都报, 不合并成一个数**",
           "★normalization_identical_to_gen1": "换归一化就不可比, 故逐字复用 GEN1 的 norm()",
           "per_speaker": per}
    json.dump(out, open(os.path.join(ROOT, "tests/data/phase2/asr_quality_en_gen2.json"),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
