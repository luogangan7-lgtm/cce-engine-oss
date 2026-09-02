#!/usr/bin/env python3
"""制备桥接重跑 —— 固定 n=16, 只看一次。

前登记: tests/data/phase2/preparation_rerun_prereg.json (跑前已冻结)

gen4 的资格标定是在 raw 制备下做的。结构闸改的是**送进仪器的文本** ⇒ 样品制备变更。
39 个 base 里 37 个过闸后逐字节不变(EXACT_INPUT_IDENTITY, 历史 draw 直接复用),
2 个被改动 ⇒ 对应的 16 rep 不可迁移, 必须重跑。

仪器 565470cf26c16d01 与资格协议 b41ef5217a77d311 **一个字节不动**;
唯一变的是 text = structural_gate(raw)["subject_text"]。
context 字符串与主面板/扩展块逐字相同 —— 否则 context 成为混杂因子。

★ 纪律: 固定 n、只看一次。不许边跑边看上界、一过 U_max 就停。
★ INFRA_FAILED(HTTP 200 空 content / 2062) 不计入 U, 该 rep 重试。
"""
import json
import os
import random
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K            # noqa: E402
from cce_structural_gate import structural_gate, preparation_id  # noqa: E402

P = ROOT / "tests" / "data" / "phase2"
CKPT = P / "preparation_rerun_checkpoint.jsonl"
SPEC = json.loads((P / "preparation_rerun_prereg.json").read_text(encoding="utf-8"))
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
CTX = SPEC["design"]["context"]
KK, R = SPEC["design"]["K"], SPEC["design"]["R"]
WORKERS = int(os.environ.get("PR_WORKERS", "4"))
MAX_CALLS_PER_MIN = 45
_lock = threading.Lock()


def _texts():
    seen = {}
    def walk(n):
        if isinstance(n, dict):
            if "base_id" in n and "text" in n:
                seen.setdefault(n["base_id"], n["text"])
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(json.loads((P / "panel_manifest.json").read_text(encoding="utf-8")))
    for row in json.loads((P / "qualification_extension_frozen.json").read_text(encoding="utf-8"))["chosen"]:
        seen.setdefault(row["base_id"], row["text"])
    return seen


def _done():
    if not CKPT.exists():
        return set()
    return {(r["base_id"], r["arm"], r["rep"]) for r in
            (json.loads(l) for l in CKPT.read_text(encoding="utf-8").splitlines() if l.strip())
            if not r.get("infra_suspected")}


def main() -> int:
    inst = K.instrument_id(TAXO, k=KK, knot_n=5,
                           s1_pairing=f"round_robin_over_{KK}_s1_draws",
                           preparation_id=preparation_id())
    assert inst["instrument_hash"] == "565470cf26c16d01", \
        f"★ 仪器不符 {inst['instrument_hash']} —— U 不可跨仪器合并"
    assert inst["qualification_policy_hash"] == SPEC["instrument"]["qualification_policy_hash"]
    assert inst["measurement_procedure_id"] == SPEC["instrument"]["measurement_procedure_id"], \
        "★ measurement_procedure_id 与前登记不符 —— 制备变了却没重新登记"

    seen = _texts()
    prepared = {}
    for b in SPEC["design"]["bases"]:
        g = structural_gate(seen[b])
        assert g["verdict"] == "MEASURE", f"{b} 过闸后弃权, 与前登记不符"
        import hashlib
        got = hashlib.sha256(g["subject_text"].encode("utf-8")).hexdigest()[:16]
        want = SPEC["prepared_inputs"][b]["prepared_sha256"]
        assert got == want, f"★ {b} 制备产物与前登记不符: {got} != {want}"
        prepared[b] = g["subject_text"]

    done = _done()
    tasks = [(b, a, i) for b in SPEC["design"]["bases"]
             for a in SPEC["design"]["arms"] for i in range(R)
             if (b, a, i) not in done]
    # 顺序与臂无关: 顺序按因子排会把时间衰减做成臂效应(主面板实测过的坑)
    random.Random(20260901).shuffle(tasks)
    print(f"仪器 {inst['instrument_hash']} · 制备 {inst['preparation_id']} · "
          f"程序 {inst['measurement_procedure_id']}")
    print(f"待跑 {len(tasks)}/16 reps = {len(tasks) * KK} 次调用 (已完成 {len(done)})")
    if os.environ.get("PR_DRYRUN"):
        print("[DRYRUN] 不发调用。")
        return 0

    cnt, t0 = Counter(), time.time()
    pace = {"next": time.time()}
    gap = 60.0 / (MAX_CALLS_PER_MIN / KK)

    def run(t):
        b, arm, i = t
        with _lock:
            now = time.time()
            w = max(0.0, pace["next"] - now)
            pace["next"] = max(now, pace["next"]) + gap
        if w:
            time.sleep(w)
        try:
            s1 = K.stage1(prepared[b], CTX, KK)
            for nm in ("k_valid", "abstained", "measurement_status", "operational"):
                if nm not in s1:
                    raise KeyError(f"stage1 缺 {nm} —— 禁止兜底")
            q = not (s1["abstained"] or s1["k_valid"] < 2)
            rec = {"base_id": b, "arm": arm, "rep": i, "qualified": q,
                   "k_valid": s1["k_valid"], "abstained": s1["abstained"],
                   "measurement_status": s1["measurement_status"],
                   "op": s1["operational"], "preparation_id": inst["preparation_id"],
                   "measurement_procedure_id": inst["measurement_procedure_id"]}
        except Exception as e:
            rec = {"base_id": b, "arm": arm, "rep": i, "qualified": None,
                   "k_valid": None, "abstained": None,
                   "stage_failed": "stage1",
                   "infra_suspected": ("全部失败" in str(e) or "空" in str(e)),
                   "error": type(e).__name__ + ": " + str(e)[:160]}
        with _lock:
            with CKPT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            key = ("INFRA" if rec.get("infra_suspected") else
                   "ERR" if rec["qualified"] is None else
                   "qualified" if rec["qualified"] else "UNQUALIFIED")
            cnt[key] += 1
            n_done = sum(cnt.values())
            print(f"  [{n_done}/{len(tasks)}] {b} {arm} r{i} -> {key} "
                  f"(k_valid={rec.get('k_valid')}, abstained={rec.get('abstained')})")

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(run, tasks))
    print(f"\n完成 {sum(cnt.values())} reps, 用时 {time.time() - t0:.0f}s: {dict(cnt)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
