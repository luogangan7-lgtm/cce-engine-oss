#!/usr/bin/env python3
"""长度问题第二次尝试: 筛出真正无结的垫料 + 一条**不需要任何假设**的长度对照。

## 上一次为什么没答上(run 32143780680)
垫料(音叉说明文)自己就稳定点火 display+reward(一致率 1.000), PAD 多出的正是它们
⇒「无结垫料」前提不成立, 那一臂无法回答长度问题。

## 本次两条腿, 一条治标一条治本

### 腿 A: 筛选(SCREEN, R=2) —— 三个不同文体的候选垫料
音叉文是**说明文**, 猜测是「有人在展示知识+给出有用信息」被读成 display/reward。
故候选刻意避开说明文体: 数字表 / 法律样板 / 中性操作步骤。
**R=2 是筛选不是测量** —— 只回答「它点不点火」, 不回答「它的读数是什么」。
任一 rep 点火即淘汰。省下的功效留给胜出者。

### 腿 B: 自身重复(REPEAT, R=4) —— ★ 不需要「无结」假设
BASE 重复 5 遍。**内容逐字相同**, 只有长度变了(293 → ~1470, 对照 T1=1581)。
这条腿绕开了整个「垫料带不带结」的问题, 因为没有引入任何新内容。

⚠️ 它自己的限度, 跑前写死: 重复文本不自然, 模型可能对**重复本身**起反应。
   这使判读**不对称**:
   · EQUIVALENT → **强证据**说长度本身不驱动读数(连不自然的重复都没推动它)
   · SEPARATED  → **歧义**, 分不清是长度还是「重复很怪」
   · UNDERPOWERED → 判不出来
   所以腿 B 的信息量集中在阴性方向 —— 这正是零假设臂该有的样子。

## 成本
筛选 3 × R=2 × 8 = 48; BASE R=4 = 32; REPEAT R=4 = 32; 胜出垫料 PAD R=4 = 32(有胜出者才跑)
= 112–144 次调用。**公开仓 Actions 分钟免费, 真实成本是 MiniMax 按次计费。**

## 判决一律走 KSEP.verdict3(), 探针不自己判(上一轮就栽在自写 if p>0.05)。
"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K   # noqa: E402
import cce_ksep as KS           # noqa: E402

R_SCREEN = int(os.environ.get("FS_SCREEN_REPS", "2"))
R_FULL = int(os.environ.get("FS_REPS", "4"))
REPEAT_N = int(os.environ.get("FS_REPEAT_N", "5"))
CTX = "reddit r/HearingAids hearing_aid: 垫料筛选与长度对照"
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
ME = KS.MIN_EFFECT_EQUAL_LENGTH_20260818
CANDS = ["filler_numeric", "filler_legal", "filler_procedural"]

VERDICT_LINES = [
    "★腿A 筛选: 候选在 R=2 内点火任何结即淘汰。全部淘汰 → 记录「本仓找不到无结垫料」, "
    "该结论本身有价值(说明九结对任意文本都会响应, 即缺少「空读数」这一档)",
    "★腿B 主判 BASE vs REPEAT(内容逐字相同, 仅长度变):",
    "   EQUIVALENT   → 强证据: 长度本身不驱动读数 ⇒ 跨长度九结比较可用, T2 更丰富可归因于内容",
    "   SEPARATED    → 歧义: 分不清长度 vs「重复很怪」。**不可直接判定长度驱动**, 需第三次设计",
    "   UNDERPOWERED → 判不出来, **不是阴性**",
    "★ 若有胜出垫料, additionally 跑 BASE vs PAD_best 作交叉验证; 两条腿结论不一致时以腿B为准"
    "(它不含未验证假设)",
    "★ 禁止事后改候选、改 R、改判决线。",
]


def _corpus():
    items = json.loads((ROOT / "run_items" / "reddit_20260810.json").read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items") or items.get("run_items") or []
    return sorted({(it["reader"] or "").strip() for it in items
                   if (it.get("reader") or "").strip()}, key=len)


def _rep(text):
    s1 = K.stage1(text, CTX, 3)
    s2 = K.stage2(text, s1, TAXO)
    return {"instrument": s2["instrument"]["instrument_hash"],
            "knots": {k["key"]: k["intensity"] for k in s2["knots"]},
            "per_knot": s2["sampling"]["per_knot"]}


if __name__ == "__main__":
    base = _corpus()[0]
    repeat = "\n\n".join([base] * REPEAT_N)
    fillers = {c: (ROOT / "tests" / "data" / f"{c}.txt").read_text(encoding="utf-8").strip()
               for c in CANDS}
    print("=== 垫料筛选 + 自身重复长度对照 (前登记) ===")
    for v in VERDICT_LINES:
        print("  · " + v)
    print(f"\nBASE={len(base)}字  REPEAT(×{REPEAT_N})={len(repeat)}字  (对照 T1=1581字)")
    for c, t in fillers.items():
        print(f"  候选 {c}: {len(t)}字")
    if os.environ.get("FS_DRYRUN"):
        print("\n[DRYRUN] 不发调用。")
        sys.exit(0)

    res = {"verdict_lines": VERDICT_LINES, "min_effect": ME,
           "lens": {"BASE": len(base), "REPEAT": len(repeat),
                    **{c: len(t) for c, t in fillers.items()}}}

    # ── 腿 A: 筛选 ──────────────────────────────────────────────────────────
    screen = {}
    for c, t in fillers.items():
        reps = [_rep(t) for _ in range(R_SCREEN)]
        fired = sorted(set().union(*[set(r["knots"]) for r in reps]))
        screen[c] = {"reps": reps, "fired": fired, "clean": not fired}
        print(f"  筛选 {c}: 点火 {fired or '无 ← 干净'}")
    res["screen"] = {c: {"fired": v["fired"], "clean": v["clean"]} for c, v in screen.items()}
    winners = [c for c, v in screen.items() if v["clean"]]
    print(f"\n★ 筛选结果: {'胜出 ' + winners[0] if winners else '**全部淘汰** —— 本仓找不到无结垫料'}")

    # ── 腿 B: 自身重复 ──────────────────────────────────────────────────────
    raw = {"BASE": [_rep(base) for _ in range(R_FULL)],
           "REPEAT": [_rep(repeat) for _ in range(R_FULL)]}
    if winners:
        raw["PAD_best"] = [_rep(base + "\n" + fillers[winners[0]]) for _ in range(R_FULL)]
    fp = {n: [f"{n}{i}" for i in range(len(v))] for n, v in raw.items()}
    ins = {r["instrument"] for v in raw.values() for r in v} | \
          {r["instrument"] for v in screen.values() for r in v["reps"]}
    assert len(ins) == 1, f"仪器指纹不唯一 {ins} —— 本次作废"
    print(f"\n仪器指纹全程一致: {list(ins)[0]}")

    for n in raw:
        rp = KS.reproducibility([r["knots"] for r in raw[n]], fp[n], name=n)
        res[f"repro_{n}"] = rp
        print(f"\n{n}: {rp['verdict']}  结集一致率={rp['set_agreement']:.3f}  "
              f"结={sorted(set().union(*[set(r['knots']) for r in raw[n]]))}")

    v = KS.verdict3([r["knots"] for r in raw["BASE"]], [r["knots"] for r in raw["REPEAT"]],
                    fp["BASE"], fp["REPEAT"], min_effect=ME, nameA="BASE", nameB="REPEAT")
    res["verdict3_BASE_REPEAT"] = v
    print("\n=== ★ 腿B 主判 (内容逐字相同, 仅长度变) ===")
    print({"EQUIVALENT": "  强证据: 长度本身不驱动读数 ⇒ 跨长度九结比较可用",
           "SEPARATED": "  ★歧义: 分不清长度 vs「重复很怪」—— **不可直接判定长度驱动**",
           "UNDERPOWERED": "  ★欠功效: 既不能说不同也不能说相同。**不是阴性结论。**",
           "UNCALIBRATED": "  未标定"}[v["verdict"]])
    print(f"    T={v['T']:.5f}  p={v['p']:.4f}  等价上界={v['equiv_upper']}  null_max={v['null_max']}")
    if winners:
        v2 = KS.verdict3([r["knots"] for r in raw["BASE"]], [r["knots"] for r in raw["PAD_best"]],
                         fp["BASE"], fp["PAD_best"], min_effect=ME)
        res["verdict3_BASE_PADbest"] = v2
        print(f"\n  交叉验证 BASE vs PAD_best({winners[0]}): {v2['verdict']}  "
              f"T={v2['T']:.5f} p={v2['p']:.4f}")
    with open("/tmp/filler_screen_and_repeat.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("\n写出 /tmp/filler_screen_and_repeat.json")
