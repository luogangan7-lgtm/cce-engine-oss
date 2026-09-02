#!/usr/bin/env python3
"""K1 Reliability 真实判定 —— 固定 n=8, 只看一次。

前登记: tests/data/phase2/k1_reliability_prereg.json (跑前已冻结, 含选文规则)

§23 给 K1 定了四项判据, 三周来只有判据没有真实判定; §44.9 P4 的验收 gate 就是这四项全过。
本脚本采集 8 次同稿重跑, 判定交给 probes/k1_gate.judge() —— 该判定函数的反向测试
在 tests/test_cce_k1_gate.py (含「两份不同内容按同组提交必须拒判」那一条)。

★ 纪律: 固定 n=8、只看一次、不许因为结果不好换文本。
★ INFRA_FAILED(HTTP 200 空 content / 2062) 不是一次读数, 该 rep 重试, 不进 n。
"""
import json
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "probes"))
import cce_knot_classify as K   # noqa: E402
from k1_gate import judge       # noqa: E402

P = ROOT / "tests" / "data" / "phase2"
CKPT = P / "k1_reliability_checkpoint.jsonl"
SPEC = json.loads((P / "k1_reliability_prereg.json").read_text(encoding="utf-8"))
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
CTX = SPEC["design"]["context"]
KK, N = SPEC["design"]["K"], SPEC["design"]["n"]
WORKERS = int(os.environ.get("K1_WORKERS", "4"))
MAX_CALLS_PER_MIN = 45
_lock = threading.Lock()


def _text():
    import hashlib
    man = json.loads((P / "panel_manifest.json").read_text(encoding="utf-8"))
    for a in man["arms"]:
        if a["base_id"] == SPEC["design"]["base_id"] and a["arm"] == "L0":
            sha = hashlib.sha256(a["text"].encode("utf-8")).hexdigest()
            assert sha == SPEC["design"]["text_sha256"], \
                f"★ 文本与前登记不符: {sha[:16]} != {SPEC['design']['text_sha16']}"
            return a["text"], sha
    raise SystemExit("前登记的 base 在面板里找不到")


def _rows():
    if not CKPT.exists():
        return []
    return [r for r in (json.loads(l) for l in CKPT.read_text(encoding="utf-8").splitlines() if l.strip())
            if not r.get("infra_suspected") and r.get("knots")]


def main() -> int:
    inst = K.instrument_id(TAXO, k=KK, knot_n=5, s1_pairing=f"round_robin_over_{KK}_s1_draws")
    assert inst["instrument_hash"] == SPEC["instrument"]["must_equal"] == "565470cf26c16d01", \
        f"★ 仪器不符 {inst['instrument_hash']} —— 读数不可与本批合并"
    text, sha = _text()

    done = {r["rep"] for r in _rows()}
    todo = [i for i in range(N) if i not in done]
    print(f"仪器 {inst['instrument_hash']} · 文本 {SPEC['design']['base_id']} sha16={sha[:16]}")
    print(f"待跑 {len(todo)}/{N} reps = {len(todo) * (KK + SPEC['design']['stage2_n'])} 次调用")
    if os.environ.get("K1_DRYRUN"):
        print("[DRYRUN] 不发调用。")
        return 0

    cnt, t0 = Counter(), time.time()
    pace = {"next": time.time()}
    gap = 60.0 / (MAX_CALLS_PER_MIN / (KK + SPEC["design"]["stage2_n"]))

    def run(i):
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
                rec = {"rep": i, "sha": sha, "cid": f"k1-{i}", "knots": None,
                       "qualified": False, "k_valid": s1["k_valid"],
                       "abstained": s1["abstained"],
                       "note": "stage1 未过资格 —— 本 rep 无读数"}
            else:
                s2 = K.stage2(text, s1, TAXO)
                knots = [[x["key"], x["intensity"]] for x in s2["knots"]]
                rec = {"rep": i, "sha": sha, "cid": f"k1-{i}", "knots": knots,
                       "top1": knots[0][0] if knots else None,
                       "qualified": True, "k_valid": s1["k_valid"],
                       "sampling": {k: s2["sampling"][k] for k in
                                    ("n_requested", "n_ok", "top1_mode", "top1_mode_share",
                                     "top1_unanimous", "top1_stable", "max_range")},
                       "instrument_hash": s2["instrument"]["instrument_hash"]}
        except Exception as e:
            rec = {"rep": i, "sha": sha, "cid": f"k1-{i}", "knots": None,
                   "infra_suspected": ("全部失败" in str(e) or "空" in str(e)),
                   "error": type(e).__name__ + ": " + str(e)[:160]}
        with _lock:
            with CKPT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            key = ("INFRA" if rec.get("infra_suspected") else
                   "NO_READING" if not rec.get("knots") else "ok")
            cnt[key] += 1
            print(f"  [{sum(cnt.values())}/{len(todo)}] rep{i} -> {key} "
                  f"top1={rec.get('top1')} max_range={rec.get('sampling',{}).get('max_range')}")

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(run, todo))
    print(f"\n采集完成 {sum(cnt.values())} reps, 用时 {time.time() - t0:.0f}s: {dict(cnt)}")

    rows = _rows()
    print(f"\n可判读数 {len(rows)}/{N}")
    code, rep = judge(rows)
    if code == 2:
        print(f"⚠️ 不可判: {rep['reason']}")
        return 2
    print(f"\n=== K1 判定 (仪器 {inst['instrument_hash']}) ===")
    for name, ok, val in rep["checks"]:
        print(f"  {'✅' if ok else '❌'} {name:<30} {val}")
    print(f"\n  逐结极差: {dict(sorted(rep['ranges'].items(), key=lambda x: -x[1]))}")
    print(f"  top-1 各次: {rep['tops']}")
    print(f"\n  → {'★ K1 通过 (四项全过)' if not rep['failed'] else 'K1 未通过, 不达标项: ' + ', '.join(rep['failed'])}")
    (P / "k1_reliability_verdict.json").write_text(json.dumps({
        "block": "K1_RELIABILITY_GEN4", "measured_at": "2026-09-01",
        "prereg": "tests/data/phase2/k1_reliability_prereg.json",
        "raw_rows": "tests/data/phase2/k1_reliability_checkpoint.jsonl",
        "instrument_hash": inst["instrument_hash"], "n": rep["n"], "sha": rep["sha"],
        "verdict": rep["verdict"], "failed": rep["failed"],
        "checks": [{"name": c[0], "pass": c[1], "value": c[2]} for c in rep["checks"]],
        "ranges": rep["ranges"], "tops": rep["tops"],
        "selection_rule": SPEC["selection_rule"]["rule"],
        "scope_limit": SPEC["selection_rule"]["scope_limit"],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
