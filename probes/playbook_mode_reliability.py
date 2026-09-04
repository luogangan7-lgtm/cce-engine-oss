#!/usr/bin/env python3
"""top-1 playbook_hit 的复现性判定。前登记: tests/data/phase2/playbook_mode_prereg.json

★ 纪律:
  · 判据与选文测量前已冻结, 不许因结果不好换
  · 检测失败(0.0/'检测失败')**不算一次读数**, 重试, 不进 n
  · **非退化闸**: 恒为 0 的 hit 会给出完美一致率 —— 2026-08-18 出过这个实事故
"""
import itertools
import json
import os
import statistics
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K            # noqa: E402
from cce_align_v2 import dissolve_hit    # noqa: E402

P = ROOT / "tests" / "data" / "phase2"
SPEC = json.loads((P / "playbook_mode_prereg.json").read_text(encoding="utf-8"))
CKPT = P / "playbook_mode_checkpoint.jsonl"
PANEL = P / "panel_checkpoint.jsonl"
MAN = json.loads((P / "panel_manifest.json").read_text(encoding="utf-8"))
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
N = SPEC["design"]["n_per_text"]
C = SPEC["criterion"]
_lock = threading.Lock()


def targets():
    """每个文本取它自己的 top-1 结 —— 由**已冻结的面板读数**确定, 不重测。"""
    arms = {(a["base_id"], a["arm"]): a for a in MAN["arms"]}
    rows = [json.loads(l) for l in PANEL.read_text(encoding="utf-8").splitlines() if l.strip()]
    knots = defaultdict(list)
    for r in rows:
        if r.get("arm") == "L0" and str(r.get("qualified")) == "True" and r.get("knots"):
            knots[r["base_id"]].append(r["knots"])
    out = []
    for t in SPEC["design"]["texts"]:
        bid = t["base_id"]
        reps = knots.get(bid) or []
        assert reps, f"面板里没有 {bid} 的 L0 读数"
        tally = Counter()
        for kk in reps:
            tally[max(kk, key=kk.get)] += 1
        out.append((bid, tally.most_common(1)[0][0], arms[(bid, "L0")]["text"]))
    return out


def rows():
    if not CKPT.exists():
        return []
    return [json.loads(l) for l in CKPT.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    inst = K.instrument_id(TAXO, k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")
    assert inst["instrument_hash"] == SPEC["instrument"]["must_equal"], "★ 仪器不符"
    T = targets()
    done = {(r["base_id"], r["rep"]) for r in rows() if r.get("ok")}
    todo = [(b, k, t, i) for b, k, t in T for i in range(N) if (b, i) not in done]
    print(f"仪器 {inst['instrument_hash']} · {len(T)} 文本 × n={N}")
    print("  top-1 结:", {b[:8]: k for b, k, _ in T})
    print(f"  待跑 {len(todo)} rep = {len(todo)*3} 次调用")
    if os.environ.get("PM_DRYRUN"):
        print("[DRYRUN] 不发调用。"); return 0

    cnt = Counter()
    def run(job):
        bid, knot, text, i = job
        try:
            hit, ev = dissolve_hit(knot, text)
            ok = ev != "检测失败"
            rec = {"base_id": bid, "knot": knot, "rep": i, "hit": hit,
                   "evidence": str(ev)[:60], "ok": ok}
        except Exception as e:
            rec = {"base_id": bid, "knot": knot, "rep": i, "ok": False,
                   "error": type(e).__name__ + ": " + str(e)[:120]}
        with _lock:
            CKPT.open("a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
            cnt["ok" if rec.get("ok") else "FAIL"] += 1
            print(f"  [{sum(cnt.values())}/{len(todo)}] {bid[:8]} rep{i} {knot} -> "
                  f"{rec.get('hit') if rec.get('ok') else 'FAIL'}")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(run, todo))
    print(f"\n采集完成 {sum(cnt.values())}, 用时 {time.time()-t0:.0f}s: {dict(cnt)}")
    return report(T, inst)


def report(T, inst) -> int:
    from collections import Counter
    by = defaultdict(list)
    for r in rows():
        if r.get("ok"):
            by[r["base_id"]].append(r["hit"])
    C = SPEC["criterion"]
    per, meeting, modes = {}, 0, []
    for bid, _, _ in T:
        v = by.get(bid, [])
        if len(v) < C["n_min"]:
            per[bid] = {"n": len(v), "verdict": "UNJUDGEABLE(n 不足)"}
            continue
        cnt = Counter(v)
        mode, k = cnt.most_common(1)[0]
        share = k / len(v)
        ok = share >= C["mode_share_min"]
        meeting += ok
        modes.append(mode)
        per[bid] = {"n": len(v), "mode": mode, "mode_share": round(share, 4),
                    "outliers": len(v) - k, "verdict": "PASS" if ok else "FAIL"}
    g = SPEC["★degeneracy_guard"]
    distinct = len(set(modes))
    top_mode_texts = max(Counter(modes).values()) if modes else 0
    deg_ok = distinct >= 2 and top_mode_texts <= 7
    need = C["texts_meeting_min"]
    if meeting >= need and deg_ok:
        d = "USABLE"
    elif meeting >= need:
        d = "DEGENERATE"
    elif meeting <= len(T) // 2 + 1:
        d = "STILL_UNRELIABLE"
    else:
        d = "INCONCLUSIVE"
    res = {"block": SPEC["block"], "measured_at": time.strftime("%Y-%m-%d"),
           "instrument_hash": inst["instrument_hash"], "texts": len(T),
           "meeting_criterion": meeting, "required": need, "per_text": per,
           "degeneracy": {"distinct_modes": distinct, "modes": sorted(set(modes)),
                          "texts_sharing_top_mode": top_mode_texts,
                          "passes": deg_ok, "rule": g["rule"]},
           "decision": d, "★decision_rule_frozen_at": SPEC["prereg_written_at"]}
    (P / "playbook_mode_verdict.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("=" * 62)
    for bid, v in per.items():
        print(f"  {bid[:8]} n={v['n']:<2} {v['verdict']:<12} "
              f"众数={v.get('mode')} 占比={v.get('mode_share')} 离群={v.get('outliers')}")
    print(f"\n达标 {meeting}/{len(T)}(需 {need}) · 非退化 {'过' if deg_ok else '不过'}"
          f"(不同众数 {distinct} 个 {sorted(set(modes))}, 最多 {top_mode_texts}/8 共用同一众数)")
    print(f"判定(预注册规则): **{d}**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
