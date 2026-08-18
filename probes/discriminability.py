#!/usr/bin/env python3
"""★ P1 Reliability 的缺口：仪器分不分得出两份**不同的真实文本**？

背景 (2026-08-18 当晚): 现有的闸全是**单次运行内部**的散布 ——
`within_js` 量 s1 各温度 draw 之间, `top1_mode_share` 量 n 次 s2 抽样之间。
**同一份文本两次独立跑之间的变动, 从来没有被测过, 也没有闸。**
今晚 pairing 探针第一次量到: 核心结 rep 间变动 0.33。

0.33 大不大, 取决于**两份不同文本之间的差**有多大。
如果仪器区分不了真实语料里不同的文本、差距还没它自己重跑的抖动大,
那么 §22 四层结构、九结分布、下游一切分析全是噪声 —— 而这个数从来没人算过。

评审给的次序是「先修 Measurement → **确认 Reliability** → 再收集 Observation」。
这条就是 Reliability, 它没做完, 所以 P2 不能开始。

★ 选文本的规则也写死, 防我自己挑对结论有利的样本:
  从 run_items/reddit_20260810.json (12 条真实语料) 按 `reader` 字段
  **长度升序排序后取 index 0 / 6 / 11** —— 首、中、末。
  不按内容挑, 不预读结点。挑「明显不同」的极端对是**另一个实验**(见判决线分支)。

  ⚠️ 这条规则**自己制造了一个长度混杂**(293 / 1581 / 4058 字)。
  若 D 高但逐结均值随长度单调, 那是在分辨长度不是分辨内容 —— 属**弱分辨**。
  跑前登记, 见 VERDICT_LINES 第 4 条, 不许事后辩解。

★ 判决线跑之前写死 (VERDICT_LINES)。

成本: T 份文本 × R 次 × (s1 3 + s2 5) 次调用。T=3 R=4 → 96 次。
"""
import json, os, re, statistics as st, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K  # noqa: E402

R = int(os.environ.get("DISC_REPS", "4"))
CTX = "reddit r/HearingAids hearing_aid: 可分辨性对照"
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))

VERDICT_LINES = [
    "D <= 1  → 仪器分辨不出真实语料里不同的文本, 差距还没自己重跑的抖动大。下游全是噪声, P2 之前必须停, 并跑极端对照区分「仪器盲」与「语料同质」",
    "1 < D < 2 → 能分辨但信噪比薄。单条读数不可单独使用, 必须配 n 次重复才能出结论",
    "D >= 2  → 分辨力可用, P1 的 Reliability 项通过, 可进 P2",
    "★混杂: 逐结均值若随文本长度单调 → D 主要由长度驱动, 是弱分辨, 上面三条降一档读",
    "★分支(DISC_SELECT=jaccard, 仅在 length 臂 D<=1 时跑): 词面最不像的一对若 D 仍<=1 → **仪器盲**, "
    "九结读数与被测文本无关, §22 四层结构与下游一切分析全部作废重来; 若 D 明显>1 → **语料同质**, "
    "仪器有能力但真实语料区分度低, 结论降为「本语料上不可用」而非「仪器不可用」",
]


SELECT = os.environ.get("DISC_SELECT", "length")   # length | jaccard


def _corpus():
    items = json.loads((ROOT / "run_items" / "reddit_20260810.json").read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items") or items.get("run_items") or []
    texts = sorted({(it["reader"] or "").strip() for it in items if (it.get("reader") or "").strip()}, key=len)
    assert len(texts) >= 3, f"语料只有 {len(texts)} 份唯一 reader 文本, 不足以做可分辨性"
    return texts


def pick_texts():
    """两条写死的选样规则, 都不由我按内容挑。

    length  (默认): 长度升序取首/中/末。**操作相关**的那个数 ——
            仪器分不分得出「我实际喂给它的那些东西」。带长度混杂, 已登记。

    jaccard (分支): 取词集 Jaccard 相似度**最低**的一对(纯机械, 无内容判断)。
            **能力上界**的那个数 —— 连真实语料里词面最不像的两份都分不出,
            那就是仪器盲, 而不是语料同质。
            ★ 这条分支在 length 臂出数**之前**写入(见 git 历史), 不是照结果补的。
    """
    texts = _corpus()
    if SELECT == "jaccard":
        def toks(t):
            return set(re.findall(r"[a-z']{3,}", t.lower()))
        tk = [toks(t) for t in texts]
        best, pair = 2.0, (0, 1)
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                u = tk[i] | tk[j]
                sim = len(tk[i] & tk[j]) / len(u) if u else 1.0
                if sim < best:
                    best, pair = sim, (i, j)
        print(f"  [jaccard] 最不相似的一对 sim={best:.4f}")
        return [(f"T{n}", texts[j]) for n, j in enumerate(pair)]
    idx = [0, len(texts) // 2, len(texts) - 1]
    return [(f"T{i}", texts[j]) for i, j in enumerate(idx)]   # 已按长度升序, T0<T1<T2


def one_rep(text):
    s1 = K.stage1(text, CTX, 3)
    s2 = K.stage2(text, s1, TAXO)
    return {"instrument": s2["instrument"]["instrument_hash"],
            "knots": {k["key"]: k["intensity"] for k in s2["knots"]},
            "per_knot": s2["sampling"]["per_knot"],
            "reported": s2["sampling"]["max_range"],
            "top1": s2["sampling"]["top1_mode"]}


def rng(vals):
    return round(max(vals) - min(vals), 4) if len(vals) > 1 else 0.0


def main():
    texts = pick_texts()
    print(f"\n选中 {len(texts)} 份真实语料 (长度升序 首/中/末, 规则写死不按内容挑):")
    for name, t in texts:
        print(f"  {name}  {len(t):>4}字  {t[:60].replace(chr(10),' ')}…")

    data = {}
    for name, text in texts:
        reps = []
        for i in range(R):
            t0 = time.time()
            reps.append(one_rep(text))
            print(f"  {name} rep{i+1}/{R}  {time.time()-t0:.0f}s  top1={reps[-1]['top1']}"
                  f"  结={sorted(reps[-1]['knots'])}")
        data[name] = reps

    # 核心结: 在**每一个 (文本, rep) 格子**里都出现的结。
    # 不用并集补零 —— 那正是此前踩过的隐藏阈值坑(缺席记 0 会把极差灌成假信号)。
    cells = [r["knots"] for reps in data.values() for r in reps]
    core = sorted(set.intersection(*[set(c) for c in cells])) if cells else []

    print(f"\n核心结(每个格子都出现): {core}")
    if not core:
        print("  ⚠️ 核心结为空 —— 这本身就是发现: 连出现哪些结都不稳定")

    # between-run: 每份文本内部, 逐结 rep 间极差, 取该文本的最大值; 再对文本取均值
    within = {}
    for name, reps in data.items():
        within[name] = max((rng([r["knots"][k] for r in reps]) for k in core), default=0.0)
    between_run = round(st.mean(within.values()), 4) if within else 0.0

    # between-text: 逐结取各文本的 rep 均值, 再看文本之间的极差, 取最大结
    means = {name: {k: st.mean(r["knots"][k] for r in reps) for k in core}
             for name, reps in data.items()}
    between_text = round(max((rng([means[n][k] for n in means]) for k in core), default=0.0), 4)

    D = round(between_text / between_run, 3) if between_run else float("inf")

    print("\n" + "=" * 74)
    print(f"  文本间变动 (信号)      {between_text}")
    print(f"  重跑间变动 (噪声)      {between_run}    逐文本: "
          + " ".join(f"{n}={v}" for n, v in within.items()))
    print(f"  ★ 可分辨性 D = 信号/噪声 = {D}")
    print(f"\n  逐结 文本间差: " + json.dumps(
        {k: rng([means[n][k] for n in means]) for k in core}, ensure_ascii=False))
    print(f"  各文本 top1: " + json.dumps({n: [r["top1"] for r in reps] for n, reps in data.items()},
                                          ensure_ascii=False))
    # 结集差异本身也是分辨力 —— 只看核心结会低估 D, 单独报出来
    ksets = {n: sorted(set().union(*[set(r["knots"]) for r in reps])) for n, reps in data.items()}
    print(f"  各文本触发的结集: " + json.dumps(ksets, ensure_ascii=False))
    print(f"  (结集若因文本而异, 那也是分辨力, 但没算进 D —— D 是**下界**)")

    # 长度混杂检查: T0<T1<T2 已按长度排好, 逐结均值若同序或反序 = 随长度单调
    order = list(means)
    mono = [k for k in core
            if [means[n][k] for n in order] == sorted(means[n][k] for n in order)
            or [means[n][k] for n in order] == sorted((means[n][k] for n in order), reverse=True)]
    print(f"\n  ★长度混杂: {len(mono)}/{len(core)} 个核心结的均值随长度单调 {mono}")
    if core and len(mono) == len(core):
        print("     ⚠️ 全部单调 —— D 可能主要由长度驱动, 属弱分辨, 判决线降一档读")

    insts = sorted({r["instrument"] for reps in data.values() for r in reps})
    print(f"\n  仪器: {insts}   ← 必须只有 1 把, 否则跨文本比较无效")
    assert len(insts) == 1, f"❌ 涉及 {len(insts)} 把不同仪器, 本次比较无效"

    print("\n【判决线(跑前写死)】")
    for i, line in enumerate(VERDICT_LINES, 1):
        print(f"  {i}. {line}")

    Path("/tmp/discriminability.json").write_text(json.dumps(
        {"R": R, "core": core, "between_text": between_text, "between_run": between_run,
         "D": D, "within_by_text": within, "means": means, "ksets": ksets,
         "raw": {n: [{"knots": r["knots"], "per_knot": r["per_knot"], "top1": r["top1"]} for r in reps]
                 for n, reps in data.items()}},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n  原始逐 rep 逐结明细 → /tmp/discriminability.json")


if __name__ == "__main__":
    main()
