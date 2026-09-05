#!/usr/bin/env python3
"""判官底噪 A/A —— 零改动重复 n=30, 估的是参数不是判结论。

前登记: tests/data/phase2/judge_noise_floor_prereg.json

## 为什么这个必须先跑
库内 2026-08-09 已立的规则: 「版本间差异全在噪声地板以内…三轮分类学迭代实质是在
噪声上调参。**迭代前必须先量噪声地板。**」
★ 而 GEN1(原子分解) 与 GEN2(A1/A2) 两轮迭代**都没先量**。后果当场出现: GEN2 里一个
playbook 一字未改的臂从 PASS 翻成 FAIL —— 没有底噪就分不出那是信号还是噪声。

## 它不做什么
**不出 playbook 判决。** 这是仪器表征。把噪声测量读成结果, 正是本项目要防的那类错。
"""
import json
import os
import statistics
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "probes"))

# ★ 复用**测量**, 不复用判决: read_once / atoms_of 与 GEN2 逐字同一套调用,
#   否则这次量到的底噪不是那次测量的底噪。
import playbook_atoms_reliability as R      # noqa: E402

P = ROOT / "tests" / "data" / "phase2"

# ★ 按代隔离。GEN=1 是 v1 提问形式下的底噪 A/A(已跑);
#   GEN=3 是 v2(禁令改问「违反了吗」)下的同一批测量 —— 唯一变量是提问形式。
GEN = os.environ.get("CCE_NOISE_GEN", "1")
if GEN == "1":
    SPEC = json.loads((P / "judge_noise_floor_prereg.json").read_text(encoding="utf-8"))
    CKPT = P / "judge_noise_floor_checkpoint.jsonl"
    OUT = P / "judge_noise_floor.json"
    FORM = "v1"
else:
    SPEC = json.loads((P / f"playbook_atoms_gen{GEN}_prereg.json").read_text(encoding="utf-8"))
    CKPT = P / f"playbook_atoms_gen{GEN}_noise_checkpoint.jsonl"
    OUT = P / f"playbook_atoms_gen{GEN}_noise.json"
    FORM = "v2"
N = SPEC["design"]["n_per_text"]
_lock = threading.Lock()

FLOOR, CEIL = 0.0, 1.0


def _band(mode_val: float) -> str:
    """众数落在地板 / 天花板 / 中段 —— P_A 就是问这三档的稳定性是否不同。"""
    if abs(mode_val - FLOOR) < 1e-9:
        return "floor"
    if abs(mode_val - CEIL) < 1e-9:
        return "ceiling"
    return "middle"


def main() -> int:
    if not os.environ.get("MINIMAX_API_KEY"):
        print("★ 无 MINIMAX_API_KEY —— 不出结论, 不降级。"
              "(2026-08-18 实事故: 无 key 时返回 0.0 使断言退化成 0==0)")
        return 2
    ih = os.environ.get("CCE_INSTRUMENT_HASH", "565470cf26c16d01")
    assert ih == SPEC["instrument"]["must_equal"], f"★ 仪器不符: {ih}"

    # ★ 与 GEN2 **共用同一个**选结函数 —— 各写一份就会漂, 漂了就是量了别的臂的噪声。
    todo = R.texts_and_knots(SPEC["design"]["texts"])

    done = {}
    if CKPT.exists():
        for l in CKPT.read_text(encoding="utf-8").splitlines():
            if l.strip():
                r = json.loads(l)
                done[(r["base_id"], r["rep"])] = r

    print(f"前登记: {SPEC['block']} | 提问形式 **{FORM}** | {len(todo)} 文本 × {N} 重复 "
          f"= {len(todo) * N} 次调用")
    print("原子数:", {k: len(R.atoms_of(k)) for k in sorted({k for _, k, _ in todo})})
    print("-" * 78)

    jobs = [(b, k, tx, r) for (b, k, tx) in todo for r in range(N) if (b, r) not in done]

    def run(job):
        b, k, tx, r = job
        for attempt in range(4):
            v = R.read_once(k, tx, [0.0, 0.3, 0.6, 0.9][attempt], form=FORM)
            if v:
                rec = {"base_id": b, "knot": k, "rep": r, **v, "ok": True}
                with _lock:
                    with open(CKPT, "a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                return rec
        return None

    if jobs:
        with ThreadPoolExecutor(max_workers=6) as ex:
            for rec in ex.map(run, jobs):
                if rec:
                    done[(rec["base_id"], rec["rep"])] = rec

    per, by_band = {}, defaultdict(list)
    n_asked = len(todo) * N
    n_got = sum(1 for (b, _, _) in todo for r in range(N) if (b, r) in done)

    for b, k, _ in todo:
        recs = [done[(b, r)] for r in range(N) if (b, r) in done]
        vals = [x["atoms_hit"] for x in recs]
        if not vals:
            per[b] = {"n": 0, "knot": k, "status": "NO_DATA"}
            continue
        c = Counter(round(v, 4) for v in vals)
        mode_val, mode_n = c.most_common(1)[0]
        share = mode_n / len(vals)
        band = _band(mode_val)
        by_band[band].append(share)

        # ★ 逐原子: 这是本轮第一次能回答「是哪个原子在动」
        atoms = defaultdict(lambda: {"executed": 0, "n": 0, "unsupported": 0, "text": "",
                                     "is_prohibition": None})
        for x in recs:
            for a in x.get("per_atom", []):
                slot = atoms[a["i"]]
                slot["executed"] += a["executed"]
                slot["unsupported"] += 1 if a["unsupported"] else 0
                slot["n"] += 1
                slot["text"] = a["text"]
                slot["is_prohibition"] = a["is_prohibition"]
        per_atom = {}
        for i, s in sorted(atoms.items()):
            rate = s["executed"] / s["n"] if s["n"] else None
            per_atom[str(i)] = {
                "text": s["text"], "is_prohibition": s["is_prohibition"],
                "executed_rate": round(rate, 4) if rate is not None else None,
                # ★ 每原子自身的稳定性: 离 0 或 1 越远越不稳, 0.5 就是抛硬币
                "instability": round(2 * min(rate, 1 - rate), 4) if rate is not None else None,
                "unsupported_rate": round(s["unsupported"] / s["n"], 4) if s["n"] else None,
                "n": s["n"]}

        per[b] = {"n": len(vals), "knot": k, "mode_value": mode_val,
                  "mode_share": round(share, 4), "band": band,
                  "distribution": {str(v): n for v, n in sorted(c.items())},
                  "per_atom": per_atom}

    for b, v in per.items():
        if v.get("status") == "NO_DATA":
            print(f"  {b}  无数据 [{v['knot']}]")
            continue
        print(f"  {b}  n={v['n']:2d}  众数 {v['mode_value']:.3f} ({v['band']:7s}) "
              f"占比 {v['mode_share']:.3f}  分布 {v['distribution']}  [{v['knot']}]")

    # ── 预注册的三条预测 ──────────────────────────────────────────────
    band_summary = {b: {"n_arms": len(s), "min_share": round(min(s), 4),
                        "max_share": round(max(s), 4),
                        "median_share": round(statistics.median(s), 4)}
                    for b, s in sorted(by_band.items())}
    stable = [s for b in ("floor", "ceiling") for s in by_band.get(b, [])]
    middle = by_band.get("middle", [])
    p_a = (all(s >= 0.95 for s in stable) and all(s < 0.95 for s in middle)) if middle else None

    audit = next((v for v in per.values() if v.get("knot") == "audit"), {})
    p_b = audit.get("mode_share", 1.0) < 0.70
    disp = per.get("344d81fc035f", {})
    p_c = disp.get("mode_share", 0.0) >= 0.95

    # ── 非退化闸 ─────────────────────────────────────────────────────
    shares = [v["mode_share"] for v in per.values() if "mode_share" in v]
    all_perfect = shares and all(abs(s - 1.0) < 1e-9 for s in shares)
    constant = len({v["mode_value"] for v in per.values() if "mode_value" in v}) <= 1
    loss = 1 - (n_got / n_asked) if n_asked else 1.0
    guards = {
        "① 全部众数占比 1.000(与 audit 在 n=8 的 0.429 不相容)": not all_perfect,
        "② 取值非恒定": not constant,
        "③ 读数丢失率 <= 10%": loss <= 0.10,
    }

    print("-" * 78)
    print("各档众数占比:", json.dumps(band_summary, ensure_ascii=False))
    for name, ok in guards.items():
        print(f"非退化 {name} ⇒ {'过' if ok else '★不过'}")
    print(f"读数 {n_got}/{n_asked} (丢失 {loss:.1%})")
    print("-" * 78)
    print(f"P_A 地板/天花板稳(>=0.95) 且 中段不稳(<0.95) ⇒ {p_a}")
    print(f"P_B audit 众数占比 < 0.70 ⇒ {p_b}  (实测 {audit.get('mode_share')})")
    print(f"P_C display 众数占比 >= 0.95 ⇒ {p_c}  (实测 {disp.get('mode_share')})")

    degenerate = not all(guards.values())
    OUT.write_text(json.dumps({
        "block": SPEC["block"],
        "measured_at": __import__("datetime").date.today().isoformat(),
        "instrument_hash": ih, "n_per_text": N,
        "reads": {"asked": n_asked, "got": n_got, "loss_rate": round(loss, 4)},
        "per_text": per, "by_band": band_summary,
        "predictions": {"P_A_bands": p_a, "P_B_audit_unstable": p_b,
                        "P_C_display_was_noise": p_c},
        "degeneracy_guards": guards,
        "status": "DEGENERATE_CHECK_INSTRUMENT" if degenerate else "CHARACTERISED",
        "★produces_no_playbook_verdict": "本轮是**仪器表征**, 不改变 GEN2 的「6/8 < 7 ⇒ 不采纳」。",
        "★prior_was_calibration_only": "先验 p̂ = 1/96 由 GEN1/GEN2 的 6 个未改臂导出, "
                                       "**只作校准**; 本轮是独立重复, 才是确认性测量。",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n⇒ {'DEGENERATE — 先查仪器' if degenerate else 'CHARACTERISED'}   写入 {OUT.name}")
    print("★ 本轮**不出 playbook 判决**。GEN2 的 6/8 < 7 不采纳, 不因这轮改变。")
    return 1 if degenerate else 0


if __name__ == "__main__":
    sys.exit(main())
