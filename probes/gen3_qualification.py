#!/usr/bin/env python3
"""Gen3 Qualification Experiment —— 取代那条被判失效的二元判决线。

## 为什么重来
上一条前登记是「真人文本误伤率 >1/12 即建议回滚」。它被 4/12 触发了。
但该 endpoint 是**错误设定**(endpoint misspecification), 不是结果不合心意:
  · 它把 abstain 1/3、2/3、3/3 压成同一个 Yes, 而三者后果完全不同
  · k_valid=1 时 within_js 结构性不可计算 —— 关键验证步骤在某些结果下不可执行
故: 原规则 **TRIGGERED** 的事实**永久保留**; 其**推断权限**停止; 本轮结论 INDETERMINATE;
    恢复 confirmatory 地位**必须用新数据** —— 就是本探针。
   (纪律: 错规则不能被改写成对规则, 但也不该继续拥有决策权。)

## 探索性输入(来自旧数据, **不作判决**, 只用于定 R)
run 32224198135 的 24 个 rep 观测: U=P(k_valid<2)=0.083 · F=P(k_valid=0)=0.000 · burden=0.111。
⇒ 对 ~0.08 的率, R=2(24 观测)精度不够; 本次取 **R=4**(48 观测)。

## 前登记设计
- 语料: 全部 12 份真实文本, **不挑不排不分层**(分层阈值极易变成事后挑数据)
- 阴性对照: filler_numeric, 同 R
- K=3(**生产值**), R=4 ⇒ 成本 (12+1) × 4 × 3 = **156 次调用**
- 每 rep 记录 k_attempted / k_valid / k_abstained, 且**弃权的 draw 全部保留**
- ★ **禁止「抽到够两个为止」** —— 那会条件化于模型愿意给读数, 隐藏真实弃权倾向

## 终点(跑前写死)
主安全终点  U = unqualified_measurement_rate = P(k_valid < 2 | 真人文本)
次级       F = full_false_abstention_rate   = P(k_valid = 0 | 真人文本)
次级       B = partial_abstention_burden    = mean((K - k_valid)/K | 真人文本)
阴性侧对称  Nf = P(k_valid = 0 | 中性垫料)   Nd = 逐 draw 弃权率(中性垫料)
新维度     R_requested vs R_qualified(k_valid>=2 的 rep 数) —— 名义 R 不等于推断 R

## ★ 判决分区(穷尽且互斥; 每个阈值都不依赖从本语料倒推)
"""
import json, os, statistics as st, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K   # noqa: E402

R = int(os.environ.get("GQ_REPS", "4"))
KK = int(os.environ.get("GQ_K", "3"))
CTX = "reddit r/HearingAids hearing_aid: gen3 资格实验"
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))

VERDICT_LINES = [
    "① 阴性对照未弃权(Nd=0) → INDETERMINATE(channel_dead): 通道死, 真人侧任何结果都不可读, 整轮作废",
    "② F > 0(任一真人文本 k_valid=0) → **ROLLBACK**。理由不需要任何产品侧标定: "
    "把一个真实的人从语料里静默删掉, 对观测型仪器是范畴性不可接受",
    "③ F = 0 且 U = 0 → **ADOPT_PENDING_MARGIN**。注意**不是 ADOPT** —— "
    "ADOPT 需要一个已标定的『可接受损失 margin』, 而它现在不存在, 故 ADOPT 分支**结构上不可达**",
    "④ F = 0 且 U > 0 → **ADOPT_WITH_RESTRICTIONS**。限制两条: "
    "(a) k_valid<2 的 rep 一律 WITHHOLD(已实现); (b) 生产须把 K 提到使 U=0, 所需 K 由本次逐 draw 弃权率估",
    "★ 以上四支对 (Nd, F, U) 的取值空间**穷尽且互斥**。不存在『其他』。",
    "★ margin **不许从本次 12 份倒推**。ADOPT 留空是诚实, 不是保守。",
    "★ 禁止事后改语料、改 R、改 K、改判决线。禁止剔除任何一份文本。",
]


def _zero_event_n(target, alpha=0.05):
    """零事件下要把单侧 95% 上界压到 target 所需的最小 n。

    闭式: 0/n 的上界是 1 - alpha**(1/n) <= target  ⇒  n >= log(alpha)/log(1-target)。
    ★ 存在的理由: 报「U=0」时必须同时能回答「那要多少次才够说它接近零」——
      否则「没看见」会被读成「不会发生」。
    """
    import math
    return math.ceil(math.log(alpha) / math.log(1 - target))


def _rep(text):
    s1 = K.stage1(text, CTX, KK)
    # ★ 2026-08-19: 初版这里写的是 s1.get("k_valid", s1.get("k_ok")) —— **兜底害死了一整轮**。
    #   stage1 的弃权分支当时没有 k_valid 键, 兜底取到 k_ok=3(它自己也把弃权算成了成功),
    #   于是「全体弃权」被记成 k_valid=3, 通道自检读出 Nd=0, 156 次调用整轮作废。
    #   ⇒ **对自己的 schema 禁止用 .get(key, default)**: 它把 schema 漂移变成自信的错数。
    #      缺键就该当场炸。
    for _need in ("k_attempted", "k_valid", "k_abstained", "measurement_status",
                  "abstained", "draws"):
        if _need not in s1:
            raise KeyError(f"stage1 返回体缺 {_need} —— 禁止兜底, 缺键即失败")
    return {"k_attempted": s1["k_attempted"],
            "k_valid": s1["k_valid"],
            "k_abstained": s1["k_abstained"],
            "abstained": bool(s1["abstained"]),
            "measurement_status": s1["measurement_status"],
            "draws": [{"t": d["from_temperature"], "abstained": d["abstained"]}
                      for d in s1["draws"]]}


if __name__ == "__main__":
    items = json.loads((ROOT / "run_items" / "reddit_20260810.json").read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items") or items.get("run_items") or []
    texts = sorted({(it["reader"] or "").strip() for it in items
                    if (it.get("reader") or "").strip()}, key=len)
    ctrl = (ROOT / "tests" / "data" / "filler_numeric.txt").read_text(encoding="utf-8").strip()

    print("=== Gen3 Qualification Experiment (前登记) ===")
    for v in VERDICT_LINES:
        print("  · " + v)
    inst = K.instrument_id(TAXO, k=KK, knot_n=5, s1_pairing=f"round_robin_over_{KK}_s1_draws")
    print(f"\n仪器 {inst['instrument_hash']}  K={KK}(生产值)  R={R}  "
          f"真人 {len(texts)} 份 + 阴性 1 份 ⇒ {(len(texts)+1)*R*KK} 次调用")
    if os.environ.get("GQ_DRYRUN"):
        print("[DRYRUN] 不发调用。")
        sys.exit(0)

    res = {"instrument": inst["instrument_hash"], "K": KK, "R_requested": R,
           "verdict_lines": VERDICT_LINES, "human": {}, "control": {}}
    for i, t in enumerate(texts):
        reps = [_rep(t) for _ in range(R)]
        res["human"][f"T{i:02d}"] = {"len": len(t), "reps": reps}
        print(f"  T{i:02d} {len(t):>5}字  k_valid={[r['k_valid'] for r in reps]}")
    res["control"] = {"reps": [_rep(ctrl) for _ in range(R)]}
    print(f"  阴性对照  k_valid={[r['k_valid'] for r in res['control']['reps']]}")

    kv = [r["k_valid"] for v in res["human"].values() for r in v["reps"]]
    U = sum(1 for k in kv if k < 2) / len(kv)
    F = sum(1 for k in kv if k == 0) / len(kv)
    B = st.mean((KK - k) / KK for k in kv)
    cd = [d["abstained"] for r in res["control"]["reps"] for d in r["draws"]]
    Nd = sum(1 for x in cd if x) / len(cd) if cd else 0.0
    Nf = sum(1 for r in res["control"]["reps"] if r["k_valid"] == 0) / R
    Rq = sum(1 for k in kv if k >= 2)
    res.update({"U": round(U, 4), "F": round(F, 4), "B": round(B, 4),
                "Nd": round(Nd, 4), "Nf": round(Nf, 4),
                "R_qualified_rep_observations": Rq, "R_total_rep_observations": len(kv)})
    print(f"\n主终点 U=P(k_valid<2)={U:.4f}  次级 F=P(k_valid=0)={F:.4f}  B={B:.4f}")
    print(f"阴性 Nd(逐draw弃权率)={Nd:.4f}  Nf={Nf:.4f}")
    print(f"R_qualified/R_total(rep 观测) = {Rq}/{len(kv)}  ← 名义 R 不等于推断 R")

    if Nd == 0:
        verdict = "INDETERMINATE(channel_dead): 阴性对照未弃权, 整轮作废"
    elif F > 0:
        verdict = f"ROLLBACK: F={F:.4f}>0, 有真实文本被整条删掉"
    elif U == 0:
        # ★★ 2026-09-06: 此前只报点估计 U=0。**零事件不等于零发生率** ——
        #   0/n 的精确单侧 95% 上界是 1 - 0.05**(1/n); n=20 时仍有 **0.139**, n=42 时 0.069。
        #   ⇒ 「U=0」单独说出来会被读成「不会发生」, 而数据只支持「在 n 次里没看见」。
        #   ★ 生产侧早有 binom_upper(Clopper-Pearson 精确上界)与 adopt_verdict
        #     (**唯一**允许把仪器升到 ADOPT 的入口), 而此处手搓的平行判决绕过了它们 ——
        #     同一逻辑两份实现, 被用的偏偏是没有上界的那份。
        _u_hi = K.binom_upper(sum(1 for k in kv if k < 2), len(kv))
        res["U_upper95"] = round(_u_hi, 4)
        res["zero_event_n_needed"] = _zero_event_n(0.05)
        verdict = (f"ADOPT_PENDING_MARGIN: F=0 且 U=0(**点估计**), "
                   f"但 95% 上界 **U<={_u_hi:.4f}** —— 零事件只说明「n={len(kv)} 次里没看见」, "
                   f"不说明发生率为零。要把上界压到 0.05 需 n>={res['zero_event_n_needed']}。"
                   f"ADOPT 仍需已标定 margin, 现不存在。")
    else:
        q = st.mean(sum(1 for d in r["draws"] if d["abstained"]) / max(1, len(r["draws"]))
                    for v in res["human"].values() for r in v["reps"])
        need = next((k for k in range(KK, 13)
                     if sum(__import__("math").comb(k, j) * q ** (k - j) * (1 - q) ** j
                            for j in range(0, 2)) < 0.001), None)
        res["per_draw_abstention_rate"] = round(q, 4)
        res["K_needed_estimate"] = need
        verdict = (f"ADOPT_WITH_RESTRICTIONS: U={U:.4f}>0, F=0。逐 draw 弃权率 q={q:.4f}, "
                   f"估计需把 K 提到 {need} 才使 P(k_valid<2)<0.001")
    res["verdict"] = verdict
    print("\n=== 判决 ===\n  " + verdict)
    with open("/tmp/gen3_qualification.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("写出 /tmp/gen3_qualification.json")
