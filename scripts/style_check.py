#!/usr/bin/env python3
"""文风闸 — 用目标版块的真人语料当基准, 量一段拟发文案有多像 AI 写的。

2026-08-09 建立。用户指出我写的回复"很像 AI 写的", 点名 "One boundary." 这类句子。
实测(基准 = r/HearingAids 版内 104 条真人外部评论):
  缩写占比  真人 83.6%(199缩写/39展开)  我的稿 0%   ← 不是风格偏好, 是指纹
  "One boundary." / "Why it stops." / "The symptom." 在真人语料出现 0 次

为什么必须独立于 CCE: CCE 只管心理触达, 完全不管文风。同一稿可以既过 CCE 又满身 AI 味。
(已实证二者正交: 去标签重测对齐分不降反升 0.85→0.895, 说明 CCE 根本没在看这些标签。)

为什么必须对着语料量而不是靠人判: 作者判不准自己写的东西, 当天已证。

用法: style_check.py <draft.txt> [--corpus accuracy/data/reddit_snapshot_20260809.json]
退出码非 0 = 有 ERROR。
"""
import os, re, sys, json, argparse, statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACTION = r"\b\w+['’](t|s|re|ve|ll|d|m)\b"
EXPANDED = (r"\b(cannot|can not|do not|does not|did not|is not|are not|was not|it is|that is|there is|"
            r"you will|I will|we will|they will|they are|we are|I am|would not|will not|could not|"
            r"should not|has not|have not|let us)\b")
# 大纲标签当句子 —— 用显式词表而非长度启发式。
# 校准(2026-08-09): 真人也写短段首句(104条里 6.2% 的段落, 如 "Nice post" / "Thanks" /
# "The Connect Clip"), 按长度一刀切会误伤。真正的差别是「内容」vs「关于话语的标签」:
# 真人写的是反应和指代, AI 写的是"这段要干什么"的目录条目。故改为词表, 并在语料上验零误报。
LABEL_LEXICON = [
    r"One boundary", r"One caveat", r"A caveat", r"One catch", r"The catch",
    r"Why it (?:works|stops|matters|happens|fails)", r"What (?:it|this) means",
    r"The (?:symptom|reason|mechanism|upshot|short answer|long answer|takeaway|point)",
    # "Bottom line" 已剔除: u/user_82 实际这么写过, 语料不支持禁它
    r"To be clear", r"In short", r"Put simply", r"Simply put",
    r"(?:Two|Three|Four|Five) (?:tests|things|reasons|options|steps|ways)",
    r"First (?:thing|off)", r"The fix", r"The problem", r"Here is (?:why|how|the)",
]
LABEL_SENTENCE = r"(?m)(?:^|\n)\s*((?:" + "|".join(LABEL_LEXICON) + r")[^.!?\n]{0,30})[.:]\s"


def profile(text):
    c = len(re.findall(CONTRACTION, text))
    e = len(re.findall(EXPANDED, text, re.I))
    sents = [len(s.split()) for s in re.split(r"[.!?]+[\s\n]", text) if len(s.split()) > 1]
    paras = [len(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]
    return {"contraction_rate": round(c / (c + e), 4) if (c + e) else None,
            "n_contraction": c, "n_expanded": e,
            "sent_median": st.median(sents) if sents else None,
            "sent_sd": round(st.pstdev(sents), 2) if len(sents) > 1 else None,
            "para_sd": round(st.pstdev(paras), 2) if len(paras) > 1 else None,
            "label_sentences": [m.group(1) for m in re.finditer(LABEL_SENTENCE, text)],
            "em_dash": text.count("—") + text.count("–")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft")
    ap.add_argument("--corpus", default=os.path.join(ROOT, "accuracy/data/reddit_snapshot_20260809.json"))
    A = ap.parse_args()
    snap = json.load(open(A.corpus, encoding="utf-8"))
    human = [c["body"] for p in snap["posts"].values() for c in p["comments"]]
    base = profile("\n\n".join(human))
    draft = open(A.draft, encoding="utf-8").read()
    d = profile(draft)

    print(f"文风闸 · 基准 = {len(human)} 条真人评论\n")
    print(f"{'指标':22s} {'真人基准':>10s} {'本稿':>10s}")
    print(f"{'缩写占比':22s} {base['contraction_rate']:10.1%} {(d['contraction_rate'] or 0):10.1%}")
    print(f"{'句长中位':22s} {base['sent_median']:10.0f} {(d['sent_median'] or 0):10.0f}")
    print(f"{'句长标准差':21s} {base['sent_sd']:10.1f} {(d['sent_sd'] or 0):10.1f}")
    print(f"{'大纲标签句':21s} {len(base['label_sentences']):10d} {len(d['label_sentences']):10d}"
          f"   ← 词表在真人语料上的误报数应为 0")
    print(f"{'破折号':23s} {base['em_dash']:10d} {d['em_dash']:10d}")

    err, warn = [], []
    lo = base["contraction_rate"] * 0.6
    if d["contraction_rate"] is None:
        warn.append("本稿无缩写也无展开形, 判不了")
    elif d["contraction_rate"] < lo:
        err.append(f"缩写占比 {d['contraction_rate']:.0%} < 真人基准的六成({lo:.0%})。"
                   f"改用 can't / don't / it's / you'll / I'd。零缩写是最强的 AI 指纹。")
    if d["label_sentences"]:
        err.append(f"大纲标签当句子 {len(d['label_sentences'])} 处: {d['label_sentences']}。"
                   f"真人语料出现 {len(base['label_sentences'])} 次。要说边界就直接说那句话, 不许起小标题。")
    if d["em_dash"]:
        err.append(f"破折号 {d['em_dash']} 处(纪律: 0)")
    if d["sent_sd"] is not None and d["sent_sd"] < base["sent_sd"] * 0.5:
        warn.append(f"句长过于齐整(sd {d['sent_sd']} vs 真人 {base['sent_sd']}), 长短句掺着写")

    print()
    for w in warn:
        print(f"  WARN  {w}")
    for e in err:
        print(f"  ERROR {e}")
    print(f"\n{'FAIL' if err else 'PASS'} · {len(err)} error / {len(warn)} warn")
    sys.exit(1 if err else 0)


if __name__ == "__main__":
    main()
