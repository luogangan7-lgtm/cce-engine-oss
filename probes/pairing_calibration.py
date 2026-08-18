#!/usr/bin/env python3
"""s1_pairing 因子对照：改动到底改变了多少 —— 用**校准**判，不用「谁的极差小」判。

背景: 2026-08-18 把仪器边界扩到 s1(n 次 s2 抽样各配一份不同的 s1 draw)之后,
生产读数的 max_range 从约 0.1-0.35 升到 0.48。我给的解释是
「改动前的低极差是把 s1 噪声冻住换来的假象」——**但那只是机理，没有数。**
而且新立的 assert_same_instrument 不允许拿改动前后的 run 直接比(不是同一把尺子),
所以必须在**同一个实验里**把 s1_pairing 当因子跑。

★ 判据不能是「谁的极差小」—— 那会直接奖励低报不确定性。
  用校准比:
      reported  = 仪器在**单个 rep 内**报出的不确定性 (max_range)
      actual    = **rep 之间**实际的变动 (同一结在 R 个 rep 的聚合值之间的极差)
      calib     = reported / actual
  calib ≈ 1 校准好; calib ≪ 1 低报; calib ≫ 1 过报。

★ 判决线跑之前写死(见 VERDICT_LINES)，不许事后挑。

成本: 2 臂 × R 次 × (s1 3 + s2 5) 次调用。R=6 → 96 次。
"""
import json, os, statistics as st, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K  # noqa: E402

TEXT = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
CTX = "reddit r/HearingAids hearing_aid: s1_pairing 校准对照"
R = int(os.environ.get("PAIR_REPS", "6"))
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))

VERDICT_LINES = [
    "OLD 的校准比显著低于 NEW（且 OLD ≪ 1）→ 旧路径低报不确定性，本次改动是对的",
    "两臂校准比相当 → 改动只把数字变大了，没有改善校准，应回滚或另找解释",
    "NEW 校准比 ≫ 1 → 新路径过报，round-robin 引入了本不存在的变动",
]


def one_rep(pairing):
    """跑一次完整 s1 + s2。pairing='new' 走 round-robin, 'old' 强制走 legacy 单 prompt。"""
    s1 = K.stage1(TEXT, CTX, 3)
    if pairing == "old":
        s1 = {k: v for k, v in s1.items() if k != "draws"}   # 抹掉 draws → stage2 退回单 prompt
    s2 = K.stage2(TEXT, s1, TAXO)
    samp = s2["sampling"]
    # 2026-08-18: per_knot 必须落盘。
    # 这是**第三次**我建的探针丢掉了回答自己问题所需的字段
    # (前两次: ab_knot_n 丢 sampling; 本探针初版丢逐 rep 逐结明细)。
    # 没有它, reported 端无法按「两臂共有的核心结」重算 ——
    # 而 OLD 每 rep 4-5 结、NEW 恒 3 结, 不restrict 就是拿不同分母比。
    return {"pairing": s2["s1_pairing"],
            "instrument": s2["instrument"]["instrument_hash"],
            "knots": {k["key"]: k["intensity"] for k in s2["knots"]},
            "per_knot": samp["per_knot"],
            "reported_max_range": samp["max_range"],
            "mode_share": samp["top1_mode_share"],
            "top1": samp["top1_mode"]}


CORE_ONLY = True   # 只用两臂共有的结算判据 —— 稀有结的「极差」是出现值不是稳定性


def score(reps, label, core=None):
    # reported: 每个 rep 内部报出的最大极差, 取均值
    # reported 按 core 结重算, 不用 samp 里那个未 restrict 的 max_range
    if core:
        reported = st.mean(max((r["per_knot"].get(k, {}).get("range", 0.0) for k in core), default=0.0)
                           for r in reps)
    else:
        reported = st.mean(r["reported_max_range"] for r in reps)
    # actual: 同一个结在 R 个 rep 之间的聚合值极差, 取最大
    keys = {k for r in reps for k in r["knots"]}
    between = {k: round(max(r["knots"].get(k, 0.0) for r in reps)
                        - min(r["knots"].get(k, 0.0) for r in reps), 4) for k in keys}
    actual = max(between.values()) if between else 0.0
    tops = [r["top1"] for r in reps]
    return {"label": label, "R": len(reps),
            "reported": round(reported, 4), "actual": actual,
            "calib": round(reported / actual, 3) if actual else None,
            "between_by_knot": dict(sorted(between.items(), key=lambda x: -x[1])),
            "top1_across_reps": tops,
            "instruments": sorted({r["instrument"] for r in reps})}


out = {}
_raw = {}
for label, pairing in (("NEW round-robin", "new"), ("OLD single-prompt", "old")):
    reps = []
    for i in range(R):
        t0 = time.time()
        try:
            reps.append(one_rep(pairing))
            print(f"  {label}  rep{i+1}/{R}  {int(time.time()-t0)}s  "
                  f"reported={reps[-1]['reported_max_range']}  top1={reps[-1]['top1']}", flush=True)
        except Exception as e:
            print(f"  {label}  rep{i+1} 失败 {type(e).__name__}", flush=True)
    _raw[label] = reps
_core = set.intersection(*[{k for r in v for k in r["knots"]} for v in _raw.values()]) if _raw else set()
print(f"\n  两臂共有的核心结: {sorted(_core)}  (稀有结不参与判据)")
for label, reps in _raw.items():
    out[label] = score(reps, label, core=_core if CORE_ONLY else None)

print("\n" + "=" * 74)
print(f"{'臂':<20}{'报告不确定性':>14}{'实际rep间变动':>16}{'校准比':>10}")
for k, v in out.items():
    print(f"  {k:<18}{v['reported']:>14.4f}{v['actual']:>16.4f}{(v['calib'] if v['calib'] is not None else float('nan')):>10.3f}")
n, o = out["NEW round-robin"], out["OLD single-prompt"]
print(f"\n  NEW instrument: {n['instruments']}")
print(f"  OLD instrument: {o['instruments']}   ← 必须不同, 否则因子没生效")
print(f"\n  NEW top1 across reps: {n['top1_across_reps']}")
print(f"  OLD top1 across reps: {o['top1_across_reps']}")
print(f"\n  NEW 逐结 rep 间变动: {n['between_by_knot']}")
print(f"  OLD 逐结 rep 间变动: {o['between_by_knot']}")
print("\n【判决线（跑前写死）】")
for i, l in enumerate(VERDICT_LINES, 1):
    print(f"  {i}. {l}")
Path("/tmp/pairing_calib.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
