#!/usr/bin/env python3
"""K1 在 **outbound_post 的仪器 0e9ca1d4e7a2f180**(k=5)上的判定。
前登记: tests/data/phase2/k1_v2_k5_prereg.json —— 判据与 K1-v2(k=3) **逐字相同**,
文本逐字相同, 只有仪器不同 ⇒ 差异只能归因于仪器。

★ 为什么要做: 生产状态表里唯一的「未测」就是这台仪器没有 K1 判定,
  而**标定不可跨仪器搬** ⇒ outbound_post 结层零可用读数。这不是弱证据, 是没有读数。
★ k=3 的 raw draw **一条都不能复用**。
"""
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
sys.path.insert(0, str(ROOT / "probes"))
import cce_knot_classify as K   # noqa: E402
from k1_gate import judge       # noqa: E402

P = ROOT / "tests" / "data" / "phase2"
CKPT = P / "k1_v2_k5_checkpoint.jsonl"
SPEC = json.loads((P / "k1_v2_k5_prereg.json").read_text(encoding="utf-8"))
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
V1 = json.loads((P / "k1_reliability_prereg.json").read_text(encoding="utf-8"))
CTX = V1["design"]["context"]          # ★ 与 v1 逐字相同, 否则不是同一台仪器的同一件事
KK, S2N, N = SPEC["design"]["K"], SPEC["design"]["stage2_n"], SPEC["design"]["n_per_text"]
WORKERS = int(os.environ.get("K1_WORKERS", "4"))
MAX_CALLS_PER_MIN = 45
_lock = threading.Lock()


def texts():
    import hashlib
    man = json.loads((P / "panel_manifest.json").read_text(encoding="utf-8"))
    arms = {(a["base_id"], a["arm"]): a for a in man["arms"]}
    out = []
    for t in SPEC["design"]["texts"]:
        a = arms[(t["base_id"], "L0")]
        sha = hashlib.sha256(a["text"].encode("utf-8")).hexdigest()
        assert sha == t["text_sha256"], f"★ {t['base_id']} 文本与前登记不符"
        out.append((t["base_id"], a["text"], sha))
    return out


def rows(base_id=None):
    if not CKPT.exists():
        return []
    rs = [json.loads(l) for l in CKPT.read_text(encoding="utf-8").splitlines() if l.strip()]
    rs = [r for r in rs if not r.get("infra_suspected") and r.get("knots")]
    return [r for r in rs if base_id is None or r["base_id"] == base_id]


def layer_rows(rs, layer):
    """把三元组 [key, intensity, weight] 投影成 judge() 要的 [key, value]。"""
    i = {"intensity": 1, "weight": 2}[layer]
    return [{**r, "knots": [[k[0], k[i]] for k in r["knots"]]} for r in rs]


def degeneracy(per_text_rows, layer):
    """★ 非退化检验(预注册 degeneracy_guard): 跨文本极差要真的比文本内抖动大。

    没有它, 一个几乎不动的层会靠「稳定」拿高分 —— 本项目已栽过两次同型。
    """
    i = {"intensity": 1, "weight": 2}[layer]
    per_knot_text_med = defaultdict(dict)     # knot -> base_id -> 该文本中位数
    per_knot_within = defaultdict(list)       # knot -> 各文本内极差
    for bid, rs in per_text_rows.items():
        vals = defaultdict(list)
        for r in rs:
            for k in r["knots"]:
                vals[k[0]].append(k[i])
        for knot, vs in vals.items():
            if len(vs) >= 2:
                per_knot_text_med[knot][bid] = statistics.median(vs)
                per_knot_within[knot].append(max(vs) - min(vs))
    detail, passing = {}, 0
    for knot, meds in per_knot_text_med.items():
        if len(meds) < 2:
            continue
        r_between = max(meds.values()) - min(meds.values())
        r_within = statistics.median(per_knot_within[knot])
        ok = r_between > 2 * r_within
        detail[knot] = {"n_texts": len(meds), "R_between": round(r_between, 4),
                        "R_within_median": round(r_within, 4), "passes": ok}
        passing += ok
    return {"knots_passing": passing, "required": 3,
            "passes": passing >= 3, "detail": detail}


def main() -> int:
    inst = K.instrument_id(TAXO, k=KK, knot_n=5, s1_pairing=f"round_robin_over_{KK}_s1_draws")
    assert inst["instrument_hash"] == SPEC["instrument"]["must_equal"], \
        f"★ 仪器不符 {inst['instrument_hash']} —— 读数不可与本批合并"
    TS = texts()
    todo = [(bid, txt, sha, i) for bid, txt, sha in TS for i in range(N)
            if i not in {r["rep"] for r in rows(bid)}]
    print(f"仪器 {inst['instrument_hash']} · {len(TS)} 文本 × n={N}")
    print(f"待跑 {len(todo)} reps = {len(todo) * (KK + S2N)} 次调用")
    if os.environ.get("K1_DRYRUN"):
        print("[DRYRUN] 不发调用。")
        return 0

    cnt, t0 = Counter(), time.time()
    pace = {"next": time.time()}
    gap = 60.0 / (MAX_CALLS_PER_MIN / (KK + S2N))

    def run(job):
        bid, text, sha, i = job
        with _lock:
            now = time.time()
            w = max(0.0, pace["next"] - now)
            pace["next"] = max(now, pace["next"]) + gap
        if w:
            time.sleep(w)
        try:
            s1 = K.stage1(text, CTX, KK)
            for nm in ("k_valid", "abstained", "measurement_status", "operational"):
                if nm not in s1:
                    raise KeyError(f"stage1 缺 {nm} —— 禁止兜底")
            if s1["abstained"] or s1["k_valid"] < 2:
                rec = {"base_id": bid, "rep": i, "sha": sha, "knots": None, "qualified": False,
                       "k_valid": s1["k_valid"], "abstained": s1["abstained"],
                       "note": "stage1 未过资格 —— 本 rep 无读数"}
            else:
                s2 = K.stage2(text, s1, TAXO)
                # ★ 同时记 intensity 与 weight —— v1 只记了 intensity, 结果 weight 无从判
                knots = [[x["key"], x["intensity"], x["weight"]] for x in s2["knots"]]
                rec = {"base_id": bid, "rep": i, "sha": sha, "knots": knots,
                       "top1": knots[0][0] if knots else None, "qualified": True,
                       "k_valid": s1["k_valid"],
                       "instrument_hash": s2["instrument"]["instrument_hash"]}
        except Exception as e:
            rec = {"base_id": bid, "rep": i, "sha": sha, "knots": None,
                   "infra_suspected": ("全部失败" in str(e) or "空" in str(e)),
                   "error": type(e).__name__ + ": " + str(e)[:160]}
        with _lock:
            with CKPT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            key = ("INFRA" if rec.get("infra_suspected") else
                   "NO_READING" if not rec.get("knots") else "ok")
            cnt[key] += 1
            print(f"  [{sum(cnt.values())}/{len(todo)}] {bid[:8]} rep{i} -> {key} top1={rec.get('top1')}")

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(run, todo))
    print(f"\n采集完成 {sum(cnt.values())} reps, 用时 {time.time() - t0:.0f}s: {dict(cnt)}")
    return report(TS, inst)


def report(TS, inst) -> int:
    per_text = {bid: rows(bid) for bid, _, _ in TS}
    result = {"block": SPEC["block"], "measured_at": time.strftime("%Y-%m-%d"),
              "instrument_hash": inst["instrument_hash"],
              "prereg": "tests/data/phase2/k1_v2_k5_prereg.json",
              "per_text": {}, "layers": {}}
    for layer in SPEC["criterion"]["layers_judged"]:
        passed, per = 0, {}
        for bid, rs in per_text.items():
            code, rep = judge(layer_rows(rs, layer))
            ok = (code == 0)
            passed += ok
            per[bid] = {"n": len(rs), "verdict": "PASS" if ok else ("UNJUDGEABLE" if code == 2 else "FAIL"),
                        "failed": rep.get("failed"), "agreement": rep.get("agreement")}
        deg = degeneracy(per_text, layer)
        result["layers"][layer] = {"passed_texts": passed, "of": len(TS),
                                   "per_text": per, "degeneracy": deg}
    it, wt = result["layers"]["intensity"], result["layers"]["weight"]
    T = len(TS)
    if wt["passed_texts"] >= T - 1 and it["passed_texts"] <= 1:
        d = "LAYER_SWITCH_SUPPORTED" if wt["degeneracy"]["passes"] else "LAYER_SWITCH_REJECTED"
    elif it["passed_texts"] >= T - 1:
        d = "FALSIFIED_V1"          # v1 的 FAIL 不可复现
    elif it["passed_texts"] >= 2 and (T - it["passed_texts"]) >= 2:
        d = "TEXT_SPECIFIC"
    elif it["passed_texts"] <= T - 4:
        d = "INSTRUMENT_WIDE_FAIL"
    else:
        d = "INCONCLUSIVE"
    result["decision"] = d
    result["★decision_rule_frozen_at"] = SPEC["prereg_written_at"]
    out = P / "k1_v2_k5_verdict.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n" + "=" * 62)
    for layer in ("intensity", "weight"):
        L = result["layers"][layer]
        print(f"{layer:<10} 过 {L['passed_texts']}/{L['of']} 文本 · "
              f"非退化 {'过' if L['degeneracy']['passes'] else '不过'} "
              f"({L['degeneracy']['knots_passing']}/{L['degeneracy']['required']} 结可分文本)")
        for bid, v in L["per_text"].items():
            print(f"    {bid[:8]} n={v['n']:<2} {v['verdict']:<12} {(v['failed'] or [])[:2]}")
    print(f"\n判定(预注册规则): **{d}**")
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
