#!/usr/bin/env python3
"""gen3 验收 gate: 给了弃权权限, 模型**到底用不用**？

## 为什么必须实测
2026-08-19 把 stage1 prompt 改成允许返回 `no_inferable_subject: true`。
但**给了权限 ≠ 会用**。若模型照旧为一张数字表构造一个人, 这次改动就是**惰性的** ——
仪器换代、当日标定作废, 却什么也没换来。那本身是必须知道的结论。

## 前登记设计
- 阴性侧(应当弃权): 四份中性垫料 —— filler_numeric(纯数字表) / filler_legal(法律样板) /
  filler_procedural(操作步骤) / filler_neutral_20260818(说明文)。
  gen1 上它们**全部**点火出九结, 且距均匀分布的 JS 与真人文本相当(比值 0.99)。
- 阳性侧(不应弃权): 语料里天然最短的真人文本(车祸后无法忍受耳内异物, 293 字)。
- R=2, 只跑 stage1(弃权发生在 s1)。成本 5 × 2 × 3 = **30 次调用**。
  R=2 是**筛选**不是测量: 只答「用不用这个出口」, 不答「弃权率是多少」。

## 前登记判决(跑前写死)
"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K   # noqa: E402

R = int(os.environ.get("AU_REPS", "2"))
CTX = "reddit r/HearingAids hearing_aid: 弃权采用率验收"
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))

VERDICT_LINES = [
    "★通过: 四份中性垫料**至少三份**出现弃权(任一 rep), 且真人文本**零弃权** "
    "⇒ 弃权出口真的被用上, gen3 有了「空读数」这一档",
    "★惰性: 四份中性垫料**全部零弃权** ⇒ 给权限不足以让模型弃权。"
    "本次换代**没换来东西**, 当日标定白作废。此时应回滚 s1 prompt 或改用外部 Eligibility Gate",
    "★过度触发: 真人文本出现弃权 ⇒ 比改动前更坏(把真实语料判成没有主体), 必须回滚",
    "★部分: 中性垫料一到两份弃权 ⇒ 出口可用但不可靠, 记录为「弱采用」, 不足以支撑生产使用",
    "★ R=2 是筛选不是测量: 不得据此报「弃权率」。",
    "★ 禁止事后改文本、改 R、改判决线。",
]


def _texts():
    items = json.loads((ROOT / "run_items" / "reddit_20260810.json").read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items") or items.get("run_items") or []
    human = sorted({(it["reader"] or "").strip() for it in items
                    if (it.get("reader") or "").strip()}, key=len)[0]
    out = {"HUMAN_base(应当不弃权)": human}
    for c in ("filler_numeric", "filler_legal", "filler_procedural",
              "filler_neutral_20260818"):
        out[c + "(应当弃权)"] = (ROOT / "tests" / "data" / f"{c}.txt").read_text(encoding="utf-8").strip()
    return out


if __name__ == "__main__":
    texts = _texts()
    print("=== gen3 弃权采用率验收 (前登记) ===")
    for v in VERDICT_LINES:
        print("  · " + v)
    inst = K.instrument_id(TAXO, k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")
    print(f"\n当前仪器: {inst['instrument_hash']}  s1_prompt_sha={inst['spec']['s1_prompt_sha256']}")
    print("谱系: " + " → ".join(f"gen{g['gen']} {g['hash'] or '(本代)'}"
                                for g in K.INSTRUMENT_LINEAGE))
    if os.environ.get("AU_DRYRUN"):
        print("\n[DRYRUN] 不发调用。")
        sys.exit(0)

    res = {"instrument": inst["instrument_hash"], "R": R, "verdict_lines": VERDICT_LINES,
           "s1_prompt_sha256": inst["spec"]["s1_prompt_sha256"], "by_text": {}}
    for name, t in texts.items():
        reps = []
        for i in range(R):
            s1 = K.stage1(t, CTX, 3)
            reps.append({"abstained": bool(s1.get("abstained")),
                         "n_abstain": s1.get("n_abstain", 0),
                         "k_ok": s1.get("k_ok"),
                         "reason": s1.get("abstain_reason", ""),
                         "tops": s1.get("tops", {})})
        any_abs = any(r["abstained"] or r["n_abstain"] > 0 for r in reps)
        res["by_text"][name] = {"reps": reps, "any_abstention": any_abs}
        print(f"  {name:34s} 任一 rep 出现弃权: {any_abs}  "
              f"(逐 rep 弃权 draw 数 {[r['n_abstain'] for r in reps]})")

    fillers = [v["any_abstention"] for k, v in res["by_text"].items() if "应当弃权" in k]
    human = res["by_text"]["HUMAN_base(应当不弃权)"]["any_abstention"]
    n_ok = sum(fillers)
    print("\n=== 判决 ===")
    if human:
        verdict = "过度触发: 真人文本被判无主体 ⇒ 必须回滚"
    elif n_ok >= 3:
        verdict = f"通过: {n_ok}/4 份中性垫料弃权, 真人零弃权 ⇒ gen3 有了空读数这一档"
    elif n_ok == 0:
        verdict = "★惰性: 0/4 弃权 ⇒ 给权限不足以让模型弃权, 本次换代没换来东西"
    else:
        verdict = f"部分: {n_ok}/4 弃权 ⇒ 弱采用, 不足以支撑生产使用"
    res["verdict"] = verdict
    print("  " + verdict)
    with open("/tmp/abstention_uptake.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("写出 /tmp/abstention_uptake.json")
