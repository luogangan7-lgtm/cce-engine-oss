#!/usr/bin/env python3
"""Designed Perturbation Ladder —— Phase 1 单文本 pilot（gen4）。

## 为什么不再找「边界文本对」
按观测 T 筛边界对 = selection-on-outcome；即便 R=8 独立重采(sample splitting 可救推断),
仍有 **regression to the mean / winner's curse** —— pilot 上 T=0.018 可能只是噪声,
重测大概率发现它根本不是边界对。⇒ 把**扰动强度变成设计变量**, 而不是被挑出来的观测量。

## ★ Axis A 不能用「调 rubric 自己的触发词」
外部评审建议的 A 轴是「更强/更弱 reward、audit」。但我库里 2026-08-18 已否决过这条:
  **「剂量臂用 rubric 自己的触发词写插入句 = 拿仪器对它自己的定义做检验。
    一台自洽但什么都没测的仪器会全过。」**
故 A 轴改用**去词化扰动**: 改变心理姿态, 但只描述**处境与动作**, 不命名感受/评价/动机。
这条**可机器验证**(见 tests/data/ladder/PSYCH_VOCAB.txt), 且反向自检能抓住违例。
  ⚠️ 限制: 该词表是我方作者冻结的, 测的是我的词表不是 rubric。
     (「不含 rubric 词汇」那种检查在这里**必然通过** —— rubric 判别式是中文而语料是英文,
      是个观察不到失败的空检查, 已弃用。)

## 六臂(R=4 各, K=3, 每 rep 8 调用 ⇒ 192 次)
  L0   原文
  L0b  原文独立重跑            —— **零参照**
  A1   去词化·轻度姿态改变      —— 求助 → 追问依据
  A3   去词化·中度姿态改变      —— 求助 → 已解决并在告知他人
  B1   表层改写(同义+句序)      —— 姿态不变, **应当不动**
  B2   仅格式/标点/断行         —— 姿态不变, **应当不动**

## ★ 判决分区(穷尽互斥, 跑前写死)
"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K   # noqa: E402
import cce_ksep as KS           # noqa: E402

R = int(os.environ.get("PL_REPS", "4"))
KK = int(os.environ.get("PL_K", "3"))
ALPHA = 0.05
CTX = "reddit r/HearingAids hearing_aid: 扰动阶梯 pilot"
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
LAD = ROOT / "tests" / "data" / "ladder"

VERDICT_LINES = [
    "① 零参照 L0 vs L0b **分开** → TYPE1_VIOLATION, 整轮作废(型 I 都不受控时其余不可读)",
    "② B 轴(B1 或 B2)**分开** → SURFACE_SENSITIVE: 姿态未变而读数变了 ⇒ "
    "仪器在读表层形式, 「好比较器」这个定性要下调, 且 B 轴优先于 A 轴报告",
    "③ 型 I 与 B 轴都干净, 但 A3 **不分开** → SEMANTIC_BLIND: 去词化的姿态改变读不出 ⇒ "
    "此前『它在读内容』很可能是在读词汇。这是**真证伪**, 不是功效不足(A3 是中度改变)",
    "④ 型 I 与 B 轴干净, A3 分开 → LADDER_USABLE, 可进 Phase 2(多 base text 建 power surface)。"
    "★ 此时**不得**顺带宣称 T(A1)<T(A3) 的单调性 —— 那是 Phase 2 要检验的, 不是本轮结论",
    "★ 以上四支对 (型I, B轴, A3) 的取值穷尽且互斥。",
    "★ 只叫 Designed Perturbation Ladder。**禁止**叫 Known Effect-Size Ladder ——"
    "扰动等级是**设计变量**, 它与 T 的单调关系是待检验对象, 不是前提。",
    "★ 禁止事后改文本、改 R、改判决线。变体文本已冻结在 tests/data/ladder/。",
]


def _rep(text):
    s1 = K.stage1(text, CTX, KK)
    for n in ("k_valid", "abstained", "measurement_status", "operational"):
        if n not in s1:
            raise KeyError(f"stage1 缺 {n} —— 禁止兜底")
    if s1["abstained"] or s1["k_valid"] < 2:
        return {"qualified": False, "failed": False, "k_valid": s1["k_valid"],
                "abstained": s1["abstained"], "op": s1["operational"], "knots": None}
    s2 = K.stage2(text, s1, TAXO)
    return {"qualified": True, "failed": False, "k_valid": s1["k_valid"],
            "abstained": False, "op": s1["operational"],
            "knots": {x["key"]: x["intensity"] for x in s2["knots"]}}


if __name__ == "__main__":
    arms = {"L0": "L0_base", "L0b": "L0_base", "A1": "A1_delex_mild",
            "A3": "A3_delex_moderate", "B1": "B1_surface_rewrite", "B2": "B2_format_only"}
    texts = {a: (LAD / f"{fn}.txt").read_text(encoding="utf-8").strip()
             for a, fn in arms.items()}

    print("=== Designed Perturbation Ladder · Phase 1 (前登记) ===")
    for v in VERDICT_LINES:
        print("  · " + v)
    inst = K.instrument_id(TAXO, k=KK, knot_n=5, s1_pairing=f"round_robin_over_{KK}_s1_draws")
    print(f"\n仪器 {inst['instrument_hash']}  资格协议 {inst['qualification_policy_hash']}")
    print("臂: " + "  ".join(f"{a}({len(t)}字)" for a, t in texts.items())
          + f"   R={R} ⇒ {len(arms)*R*(KK+5)} 次调用")
    if os.environ.get("PL_DRYRUN"):
        print("[DRYRUN] 不发调用。")
        sys.exit(0)

    raw = {}
    for a, t in texts.items():
        raw[a] = [_rep(t) for _ in range(R)]
        q = sum(1 for r in raw[a] if r["qualified"])
        fo = [r["op"]["first_attempt_success_rate"] for r in raw[a]]
        print(f"  {a}: qualified={q}/{R}  首次成功率={fo}")

    Q = {a: [r["knots"] for r in v if r["qualified"]] for a, v in raw.items()}
    res = {"instrument": inst["instrument_hash"], "R_requested": R, "K": KK,
           "verdict_lines": VERDICT_LINES, "raw": raw,
           "R_qualified": {a: len(v) for a, v in Q.items()}}
    if min(res["R_qualified"].values()) < 4:
        res["verdict"] = f"INSUFFICIENT_DATA: {res['R_qualified']}"
        print("\n=== 判决 ===\n  " + res["verdict"])
    else:
        cmp = {}
        for b in ("L0b", "A1", "A3", "B1", "B2"):
            s = KS.separation(Q["L0"], Q[b], [f"x{i}" for i in range(len(Q["L0"]))],
                              [f"y{i}" for i in range(len(Q[b]))], alpha=ALPHA)
            cmp[b] = {"T": round(s["T"], 5), "p": round(s["p"], 5),
                      "separated": s["verdict"] == "SEPARATED"}
            print(f"  L0 vs {b:4s}: T={cmp[b]['T']:.5f}  p={cmp[b]['p']:.5f}  "
                  f"{'SEPARATED' if cmp[b]['separated'] else 'not separated'}")
        res["comparisons"] = cmp
        if cmp["L0b"]["separated"]:
            v = "TYPE1_VIOLATION: 零参照分开, 整轮作废"
        elif cmp["B1"]["separated"] or cmp["B2"]["separated"]:
            v = ("SURFACE_SENSITIVE: 姿态未变而读数变了 ⇒ 仪器在读表层形式, "
                 "「好比较器」定性需下调")
        elif not cmp["A3"]["separated"]:
            v = ("SEMANTIC_BLIND: 去词化的中度姿态改变读不出 ⇒ "
                 "此前『它在读内容』很可能是在读词汇。**这是真证伪**")
        else:
            v = "LADDER_USABLE: 可进 Phase 2(多 base text 建 power surface)"
        res["verdict"] = v
        print("\n=== 判决 ===\n  " + v)
    with open("/tmp/perturbation_ladder.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("写出 /tmp/perturbation_ladder.json")
