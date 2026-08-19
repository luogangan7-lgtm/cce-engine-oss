#!/usr/bin/env python3
"""重标定第 2 步: live R=8 采样标定(gen4 首次真投料)。

## 为什么必须真投料
此前的 R 曲线是 conditional bootstrap given 4 observed reps —— 从 4 个点重抽 8 个
只会重复那 4 个点, **生成不了未观测的 run 间变异**, 连下界都不是。
拿到 **8 个真实 rep** 后, 可在其内部取**真子集**(不放回)研究 R=4..8, 这才是升级。

## ★ 三臂, 不是两臂 —— 补一个我原计划里的洞
拿一对真实文本算「拒绝率」, **只有当这对真的不同时它才是 power**;
若它们其实相同, 同一个数就是**型 I 错误**。两者用同一批数据分不开。
故加第三臂 T0b = **T0 再独立跑一次**(同文本, 独立 rep):
  · T0 vs T1  → 拒绝率(疑似 power)
  · T0 vs T0b → **真零假设参照**(同文本, 零效应), 每个 R 上都可比
  · 且 T0/T0b 本身就是「同输入重复测量」= 重标定第 4 步(分辨率)要的数据, 顺带拿到

## 前登记设计
- 文本: T0(293字) 与 T1(1581字) —— gen1 上**唯一未分开**的一对(R=4 时 p=0.0571)。
  ★ 选它是因为**已经分开的一对重抽后必然继续分开, 拒绝率饱和在 1.000, 零信息**
    (这是我自己在 0 调用分析里踩过的坑, 见 scripts/cce_resample_power.py)。
  ⚠️ 它们不等长(293 vs 1581)。gen1 上「长度 per se 不驱动读数」的结论**不转移到 gen4**
    (s1 prompt 变过), 故本次只用它做**功效标定**, 不用它做内容分辨力断言。
- R=8, K=3, n=5(生产值)。成本 3 臂 × 8 rep × (s1 3 + s2 5) = **192 次调用**
- 子集分析取**不放回真子集**, 种子固定, 每个 R 抽 200 对(全枚举在 R=6 会到 36 万量级)

## ★ 判决分区(穷尽互斥, 跑前写死)
"""
import itertools, json, os, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K   # noqa: E402
import cce_ksep as KS           # noqa: E402

R = int(os.environ.get("LR8_REPS", "8"))
KK = int(os.environ.get("LR8_K", "3"))
ALPHA = 0.05
POWER_TARGET = 0.80
CTX = "reddit r/HearingAids hearing_aid: gen4 R 标定"
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))

VERDICT_LINES = [
    "① 零参照(T0 vs T0b)在任一 R 上拒绝率 > alpha+0.05 → TYPE1_VIOLATION, 整轮标定作废"
    "(型 I 都不受控时, 任何 power 数字都不可读)",
    "② 型 I 受控, 且存在最小 R* 使 power(R*)>=0.80 **且** power(R*) 明显高于同 R 的零参照"
    " → RECOMMEND_R = R*",
    "③ 型 I 受控, power 随 R 单调上升但 R=8 仍 <0.80 → INSUFFICIENT_AT_R8(需 R>8 或效应太小)",
    "④ 型 I 受控, 但 power 在所有 R 上都**没有明显高于零参照** → PAIR_MAY_BE_NULL:"
    " 这对文本可能本来就没有差异, **不能用它标定 power**, 需另找已知有效应的一对",
    "⑤ 任一臂合格 rep < 4 → INSUFFICIENT_DATA(投料损耗过大, 子集分析做不了)。"
    "失败与弃权都会压低有效 R —— **名义 R 不等于推断 R**, 三个计数都要上报",
    "★ 以上五支对 (数据是否够, 型I是否受控, R* 是否存在, power 是否高于零参照) 穷尽且互斥。",
    "★ 子集分析用**不放回真子集**, 不是 bootstrap —— 但仍条件于这 8 个真实 rep。",
    "★ 禁止事后改文本、改 R、改判决线。",
]


def _rep(text):
    """三种状态, 不是两种: qualified / abstained / **failed**。

    ★ 2026-08-19 run 32240552713 教训: T0 臂 8/8 跑完后, T0b 的某个 rep 三档全失败
      (原始件内容为空 ⇒ **API 调用本身失败**, 不是 prompt 破坏解析),
      stage1 按设计抛错, 于是**整轮 192 调用作废**, 已花掉的六十多次也白花。

    ⚠️ 修法**不是**加重试: 每档内部已重试 3 次(9 次连续失败已是突发故障),
       而 rep 级重试会**条件化于成功, 把真实失败率藏起来** —— 与「抽到够两个为止」同病。
       正确做法: 失败是第三种状态, 如实记录并继续, 让 R_failed 可见。
    """
    try:
        s1 = K.stage1(text, CTX, KK)
    except RuntimeError as e:
        return {"qualified": False, "failed": True, "k_valid": None,
                "error": str(e)[:120], "knots": None}
    for need in ("k_valid", "k_attempted", "measurement_status", "abstained"):
        if need not in s1:
            raise KeyError(f"stage1 缺 {need} —— 禁止兜底")
    if s1["abstained"] or s1["k_valid"] < 2:
        return {"qualified": False, "failed": False, "k_valid": s1["k_valid"],
                "abstained": s1["abstained"], "knots": None}
    try:
        s2 = K.stage2(text, s1, TAXO)
    except RuntimeError as e:
        return {"qualified": False, "failed": True, "k_valid": s1["k_valid"],
                "error": "stage2: " + str(e)[:110], "knots": None}
    return {"qualified": True, "failed": False, "k_valid": s1["k_valid"],
            "instrument": s2["instrument"]["instrument_hash"],
            "qualification_policy": s2["instrument"].get("qualification_policy_hash"),
            "knots": {x["key"]: x["intensity"] for x in s2["knots"]},
            "measurement_status": s2.get("measurement_status")}


def _reject_rate(A, B, r, n_draw=200, seed=20260819):
    """不放回真子集。⚠️ r 等于臂长时只有 C(n,n)=1 个子集 ——
    此时「率」退化成单次检验(0 或 1), 不是率。输出里带 n_subsets 让它可见。"""
    rng = random.Random(seed + r)
    subs_a = list(itertools.combinations(range(len(A)), r))
    subs_b = list(itertools.combinations(range(len(B)), r))
    if len(subs_a) * len(subs_b) == 1:
        n_draw = 1
    hits = tot = 0
    for _ in range(n_draw):
        # (原稿这里写了 `if hasattr(rng,"choice") else None` —— 正是我刚禁掉的防御性默认, 已清)
        a = [A[i] for i in rng.choice(subs_a)]
        b = [B[i] for i in rng.choice(subs_b)]
        fa = [f"a{i}" for i in range(r)]
        fb = [f"b{i}" for i in range(r)]
        try:
            s = KS.separation(a, b, fa, fb, alpha=ALPHA)
        except ValueError:
            continue
        hits += (s["p"] <= ALPHA)
        tot += 1
    return (hits / tot if tot else None), {"n_eval": tot,
                                           "n_subsets": len(subs_a) * len(subs_b)}


if __name__ == "__main__":
    items = json.loads((ROOT / "run_items" / "reddit_20260810.json").read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items") or items.get("run_items") or []
    texts = sorted({(it["reader"] or "").strip() for it in items
                    if (it.get("reader") or "").strip()}, key=len)
    T0, T1 = texts[0], texts[6]

    print("=== gen4 live R=8 采样标定 (前登记) ===")
    for v in VERDICT_LINES:
        print("  · " + v)
    inst = K.instrument_id(TAXO, k=KK, knot_n=5, s1_pairing=f"round_robin_over_{KK}_s1_draws")
    print(f"\n仪器 {inst['instrument_hash']}  资格协议 {inst['qualification_policy_hash']}")
    print(f"三臂: T0({len(T0)}字) / T0b(T0 独立重跑, 零参照) / T1({len(T1)}字)  "
          f"R={R} K={KK} ⇒ {3*R*(KK+5)} 次调用")
    if os.environ.get("LR8_DRYRUN"):
        print("[DRYRUN] 不发调用。")
        sys.exit(0)

    arms = {"T0": T0, "T0b": T0, "T1": T1}
    raw = {}
    for name, t in arms.items():
        raw[name] = [_rep(t) for _ in range(R)]
        q = sum(1 for r in raw[name] if r["qualified"])
        fl = sum(1 for r in raw[name] if r.get("failed"))
        ab = sum(1 for r in raw[name] if r.get("abstained"))
        print(f"  {name}: R_qualified={q}/{R}  失败={fl}  弃权={ab}  "
              f"k_valid={[r['k_valid'] for r in raw[name]]}")

    res = {"instrument": inst["instrument_hash"],
           "qualification_policy": inst["qualification_policy_hash"],
           "R_requested": R, "K": KK, "raw": raw, "verdict_lines": VERDICT_LINES,
           "alpha": ALPHA, "power_target": POWER_TARGET}
    Q = {n: [r["knots"] for r in v if r["qualified"]] for n, v in raw.items()}
    res["R_qualified"] = {n: len(v) for n, v in Q.items()}
    res["R_failed"] = {n: sum(1 for r in v if r.get("failed")) for n, v in raw.items()}
    res["R_abstained"] = {n: sum(1 for r in v if r.get("abstained")) for n, v in raw.items()}
    # ★ 名义 R 不等于推断 R —— 失败与弃权都会压低它, 必须让下游看见
    print(f"\nR_requested={R}  R_qualified={res['R_qualified']}  "
          f"R_failed={res['R_failed']}  R_abstained={res['R_abstained']}")
    if min(res["R_qualified"].values()) < 4:
        res["verdict"] = (f"INSUFFICIENT_DATA: 某臂合格 rep 不足 4 "
                          f"({res['R_qualified']}), 无法做 R>=4 的子集分析")
        print("\n=== 判决 ===\n  " + res["verdict"])
        with open("/tmp/live_r8_calibration.json", "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        sys.exit(0)

    print(f"\n{'R':>3} {'power(T0-T1)':>14} {'null(T0-T0b)':>14}  差")
    curve = {}
    for r in range(4, R + 1):
        if min(len(Q["T0"]), len(Q["T1"]), len(Q["T0b"])) < r:
            continue
        pw, mp = _reject_rate(Q["T0"], Q["T1"], r)
        nl, mn = _reject_rate(Q["T0"], Q["T0b"], r)
        curve[r] = {"power": pw, "null": nl, "meta_power": mp, "meta_null": mn,
                    "gap": None if pw is None or nl is None else round(pw - nl, 3)}
        tag = "  ← 仅 1 个子集, 是单次检验不是率" if mp["n_subsets"] == 1 else ""
        print(f"{r:>3} {pw:>14.3f} {nl:>14.3f}  {curve[r]['gap']:+.3f}{tag}")
    res["curve"] = curve

    bad = [r for r, v in curve.items() if v["null"] is not None and v["null"] > ALPHA + 0.05]
    above = {r: v for r, v in curve.items() if v["gap"] is not None and v["gap"] > 0.20}
    ok = sorted(r for r, v in curve.items()
                if v["power"] is not None and v["power"] >= POWER_TARGET and r in above)
    if bad:
        verdict = f"TYPE1_VIOLATION: R={bad} 的零参照拒绝率超 alpha+0.05, 整轮标定作废"
    elif not above:
        verdict = "PAIR_MAY_BE_NULL: power 在所有 R 上都未明显高于零参照 ⇒ 这对文本可能本无差异, 不能用它标定 power"
    elif ok:
        verdict = f"RECOMMEND_R = {ok[0]}"
    else:
        verdict = f"INSUFFICIENT_AT_R8: R=8 时 power={curve.get(R,{}).get('power')} < {POWER_TARGET}"
    res["verdict"] = verdict
    print("\n=== 判决 ===\n  " + verdict)
    with open("/tmp/live_r8_calibration.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("写出 /tmp/live_r8_calibration.json")
