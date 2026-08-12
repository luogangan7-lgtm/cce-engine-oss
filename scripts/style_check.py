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
    words = text.split()
    sl = [len(x.split()) for x in re.split(r"(?<=[.!?])\s+", text) if x.split()]
    return {"n_sent": len(sl),
            "short_frac": round(sum(1 for x in sl if x <= 5) / len(sl), 3) if sl else 0.0,
            "len_ratio": round(max(sl) / min(sl), 2) if sl and min(sl) else 0.0,
            "first_person": round(len(re.findall(r"\b(i|my|me|mine|i'm|i've|i'd|i'll)\b", text, re.I))
                                  / len(words) * 100, 2) if words else 0.0,
            "contraction_rate": round(c / (c + e), 4) if (c + e) else None,
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
    # 2026-08-11 曾给机翻稿豁免破折号, 理由是「来源是 DeepL 的标点转换不是 LLM 指纹」+
    # 「真人用翻译工具后不会回头改标点, 清洗本身才不自然」。**2026-08-12 实测推翻。**
    # 真人语料 75 条(≥25词): 用过破折号的 1/75 = 1%, 每千词密度 中位 0.00 / 均值 0.06 / 最大 4.50。
    # 同日我方线上 7 条: 每千词 17.00 —— 是语料里最爱用破折号那人的 3.8 倍, 均值的 280 倍, 且 7 条无一例外。
    # 略高于真人时「不清洗更自然」成立; 高到全场最高值的 3.8 倍就不是自然, 是账号级指纹。
    # 归因正确不等于结果可接受: 读者看到的就是 em dash, 不管它来自 DeepL 还是 LLM。豁免作废。
    # 修法也不是改英文(违反「机翻稿不做文体后编辑」), 是中文起草时就别用破折号 —— DeepL 原样转。
    ap.add_argument("--translated", action="store_true",
                    help="稿件为非英文起草后机器翻译。不再豁免破折号(2026-08-12 实测推翻), "
                         "仅用于在报错里给出正确修法: 回改中文源稿而非后编辑英文")
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
        # 用密度判而非绝对数: 真人 75 条里最爱用的那个是 4.50/千词, 中位 0.00。
        # 一条 160 词的评论按 4.50 只允许 0.72 处 —— 所以对评论长度来说 0 就是对的,
        # 但把阈值写成密度而不是硬 0, 是为了长文(帖子/博客)不被误伤。
        rate = d["em_dash"] / max(1, len(draft.split())) * 1000
        fix = ("回改中文源稿去掉破折号再重翻(DeepL 原样转), 不要后编辑英文"
               if A.translated else "改成句号或逗号")
        if rate > 4.5:
            err.append(f"破折号 {d['em_dash']} 处 = {rate:.1f}/千词, 超过真人语料最大值 4.5"
                       f"(75 条里只有 1 条用过, 中位 0.00)。{fix}。")
        else:
            warn.append(f"破折号 {d['em_dash']} 处 = {rate:.1f}/千词, 未超真人最大值但真人中位是 0.00")
    if d["sent_sd"] is not None and d["sent_sd"] < base["sent_sd"] * 0.5:
        warn.append(f"句长过于齐整(sd {d['sent_sd']} vs 真人 {base['sent_sd']}), 长短句掺着写")

    # ── 自然人节奏(2026-08-12 建立) ──────────────────────────────────────
    # 起因: hearingtracker #175/#177 被三名读者公开判定为 AI 写的(#178 user_110 /
    # #179 user_119 / #180 user_109)。那两条是英文直写, 不是机翻 —— 证明问题在结构不在语言。
    # 基准取自同一份 104 条真人语料中 ≥25 词的 75 条(中位数):
    #   句数 5 · 短句(≤5词)占比 14% · 长短比 7.25 · 第一人称密度 6.25%
    # 实测我方 24 条稿: 句数 11.4 / 短句 5% / 第一人称 0.77% —— 第一人称差 8 倍, 是最大指纹。
    # 阈值取真人中位的一半, 宁松勿紧: 这是拟人下限不是风格指标。
    if d["first_person"] < 3.0:
        err.append(f"第一人称密度 {d['first_person']}% < 3%(真人 6.25%)。"
                   f"AI 写「这个原因是X」, 人写「我见过的是X」。把客观陈述改成经验陈述。")
    if d["short_frac"] < 0.08:
        err.append(f"短句(≤5词)占比 {d['short_frac']:.0%} < 8%(真人 14%)。"
                   f"整段没有一个短促的断句 = 最容易辨认的机器节奏。至少插一个。")
    if d["n_sent"] > 10:
        warn.append(f"句数 {d['n_sent']} > 10(真人中位 5)。真人评论比你以为的短得多。")
    # 上限保护: 只设下限的闸可以靠写成电报体刷过, 那是另一种不自然。
    # 真人句长中位 14, 短句占比 14%; 取 2.5 倍与 1/2.5 为软边界, 越界只 WARN。
    if d["short_frac"] > 0.45:
        warn.append(f"短句占比 {d['short_frac']:.0%} > 45%(真人 14%)。过度短促=电报体, 是另一种不自然。")
    if d["sent_median"] and d["sent_median"] < 7:
        warn.append(f"句长中位 {d['sent_median']:.0f} < 7(真人 13-14)。除非是认错/情绪场景, 否则太碎。")
    if d["len_ratio"] and d["len_ratio"] < 4.0:
        warn.append(f"长短句比 {d['len_ratio']} < 4(真人 7.25)。句子长度太齐。")

    print(f"{'句数':23s} {5:10d} {d['n_sent']:10d}")
    print(f"{'短句(≤5词)占比':17s} {0.14:10.0%} {d['short_frac']:10.0%}")
    print(f"{'长短句比':21s} {7.25:10.2f} {d['len_ratio']:10.2f}")
    print(f"{'第一人称密度':19s} {6.25:9.2f}% {d['first_person']:9.2f}%")

    print()
    for w in warn:
        print(f"  WARN  {w}")
    for e in err:
        print(f"  ERROR {e}")
    print(f"\n{'FAIL' if err else 'PASS'} · {len(err)} error / {len(warn)} warn")
    sys.exit(1 if err else 0)


if __name__ == "__main__":
    main()
