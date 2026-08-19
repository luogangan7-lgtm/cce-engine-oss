#!/usr/bin/env python3
"""gen3 收口: 弃权会不会**误伤真人文本**(假阳性方向)。

## 为什么单独跑
run 32223866100 的验收里, 阴性侧四份中性垫料**每个 draw** 都弃权、真人文本零弃权 —— 很干净。
**但阳性侧只有 1 份真人文本。**

过度触发是**更危险**的方向: 它不会报错, 只会让真实读者响应被判「没有主体」而静默消失,
于是 P2 的语料被悄悄缩小, 且缩掉的正是最含糊、最像真实社媒的那部分 ——
与「按信度硬闸删观测会造选择偏倚」是同一个病。

## 前登记设计
- 全部 **12 份**真实语料(run_items/reddit_20260810.json 的唯一 reader 文本), 不挑不排。
- R=2, 只跑 stage1。成本 12 × 2 × 3 = **72 次调用**。
- 阴性对照沿用 filler_numeric 1 份(确认本次运行里弃权通道确实是活的, 防"全不弃权"是因为通道坏了)。

## 前登记判决(跑前写死)
"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K   # noqa: E402

R = int(os.environ.get("AFP_REPS", "2"))
CTX = "reddit r/HearingAids hearing_aid: 弃权假阳性收口"
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))

VERDICT_LINES = [
    "★通过: 12 份真人文本**全部零弃权**, 且阴性对照仍弃权 ⇒ 弃权通道活着且不误伤真实语料",
    "★误伤: 任一真人文本出现弃权 ⇒ 记录是**哪一份**、弃权 draw 数、以及它的长度与体裁。"
    "误伤率 >1/12 即建议回滚 s1 prompt; =1/12 则先看那一份是不是真的缺主体表达(人工判)",
    "★通道死: 阴性对照(数字表)本次**不弃权** ⇒ 本次运行的弃权通道有问题, "
    "真人侧的零弃权**不可读作好消息**, 整轮作废重跑",
    "★ R=2 是筛选: 只答『会不会误伤』, 不答『误伤率是多少』。",
    "★ 禁止事后剔除任何一份文本。",
]


if __name__ == "__main__":
    items = json.loads((ROOT / "run_items" / "reddit_20260810.json").read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items") or items.get("run_items") or []
    texts = sorted({(it["reader"] or "").strip() for it in items
                    if (it.get("reader") or "").strip()}, key=len)
    ctrl = (ROOT / "tests" / "data" / "filler_numeric.txt").read_text(encoding="utf-8").strip()

    print("=== gen3 弃权假阳性收口 (前登记) ===")
    for v in VERDICT_LINES:
        print("  · " + v)
    inst = K.instrument_id(TAXO, k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")
    print(f"\n仪器: {inst['instrument_hash']}  真人文本 {len(texts)} 份 + 阴性对照 1 份, R={R}")
    if os.environ.get("AFP_DRYRUN"):
        print("[DRYRUN] 不发调用。")
        sys.exit(0)

    res = {"instrument": inst["instrument_hash"], "R": R, "verdict_lines": VERDICT_LINES,
           "human": {}, "control": {}}
    hits = []
    for i, t in enumerate(texts):
        reps = [K.stage1(t, CTX, 3) for _ in range(R)]
        na = [s.get("n_abstain", 0) for s in reps]
        res["human"][f"T{i:02d}"] = {"len": len(t), "n_abstain": na,
                                     "abstained": [bool(s.get("abstained")) for s in reps],
                                     "head": t[:60]}
        if any(na):
            hits.append((i, len(t), na, t[:60]))
        print(f"  T{i:02d} {len(t):>5}字  弃权 draw {na}" + ("  ← ★误伤" if any(na) else ""))
    cs = [K.stage1(ctrl, CTX, 3) for _ in range(R)]
    cna = [s.get("n_abstain", 0) for s in cs]
    res["control"] = {"n_abstain": cna, "abstained": [bool(s.get("abstained")) for s in cs]}
    print(f"  阴性对照(数字表)  弃权 draw {cna}")

    print("\n=== 判决 ===")
    if not any(cna):
        v = "★通道死: 阴性对照未弃权 ⇒ 本次运行弃权通道有问题, 真人侧零弃权不可读作好消息, 整轮作废"
    elif not hits:
        v = f"通过: {len(texts)}/{len(texts)} 份真人文本零弃权, 阴性对照仍弃权 ⇒ 不误伤真实语料"
    else:
        v = f"★误伤 {len(hits)}/{len(texts)}: " + "; ".join(
            f"T{i:02d}({ln}字, 弃权{na})" for i, ln, na, _ in hits)
    res["verdict"] = v
    print("  " + v)
    with open("/tmp/abstention_false_positive.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("写出 /tmp/abstention_false_positive.json")
