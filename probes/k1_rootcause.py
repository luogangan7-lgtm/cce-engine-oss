#!/usr/bin/env python3
"""K1 单结极差 0.40 的根因诊断 —— 固定 R, 只看一次。

前登记: tests/data/phase2/k1_rootcause_prereg.json (跑前冻结, 含四个互斥假设与判决线)

★ 本分析全部跑在**闸前** draw_ledger 上, 且它是**诊断不是判据**。
  不得把这里算出的任何量升级成 gate —— 那正是 D_var 被否决的原因。

两臂, 同一条文本, 同一套 prompt 模板:
  LIVE       每 rep 自己跑 stage1(k=3), 再 stage2 n=12
  FROZEN_S1  复用一份跑前冻结的 s1 输出, 只重跑 stage2 n=12
前者的 rep 间方差 = s1 传播 + s2 抽样 + 尺度漂移; 后者去掉了 s1 传播。

★ s2 抽样数 5->12 **就是换仪器**。本批标 gen4-diag-n12, 不得与生产读数合并。
  但 n=5 前缀严格复现生产的 round-robin 分配 ⇒ 前缀可与生产口径对话。
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
import cce_knot_classify as K   # noqa: E402

P = ROOT / "tests" / "data" / "phase2"
CKPT = P / "k1_rootcause_checkpoint.jsonl"
FROZEN_S1 = P / "k1_rootcause_frozen_s1.json"
SPEC = json.loads((P / "k1_rootcause_prereg.json").read_text(encoding="utf-8"))
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
CTX = SPEC["design"]["context"]
N2 = SPEC["design"]["arms"][0]["s2_n"]
R = SPEC["design"]["arms"][0]["R"]
WORKERS = int(os.environ.get("RC_WORKERS", "4"))
MAX_CALLS_PER_MIN = 45
_lock = threading.Lock()


def _text():
    import hashlib
    man = json.loads((P / "panel_manifest.json").read_text(encoding="utf-8"))
    for a in man["arms"]:
        if a["base_id"] == SPEC["design"]["text"]["base_id"] and a["arm"] == "L0":
            sha = hashlib.sha256(a["text"].encode("utf-8")).hexdigest()
            assert sha == SPEC["design"]["text"]["sha256"], "★ 文本与前登记不符"
            return a["text"]
    raise SystemExit("前登记的 base 找不到")


def _s2_with_ledger(text, s1, n):
    """复刻 stage2 的 prompt 构造与轮转, 但把每 draw 的 9 维向量原样交出来。

    ★ 不改 _build_stage2_prompt 一个字符 —— 改了就不是同一台仪器在诊断自己。
    """
    draws = s1["draws"]
    prompts = [K._build_stage2_prompt(TAXO, text, {"tops": d["tops"], "appraisal": d["appraisal"]})
               for d in draws]
    def one(i):
        d = K._stage2_draw(prompts[i % len(prompts)], TAXO, f"rc{i}")
        return i, i % len(prompts), d
    with ThreadPoolExecutor(max_workers=min(4, n)) as ex:
        out = list(ex.map(one, range(n)))
    ledger = []
    for i, pidx, d in out:
        if d is None:
            ledger.append({"draw_id": i, "prompt_idx": pidx, "infra": True, "knot_vector": None})
            continue
        ledger.append({"draw_id": i, "prompt_idx": pidx, "infra": False,
                       "abstained": not d["knots"],
                       "weight_shim_fired": bool(d.get("_weight_shim_fired")),
                       "knot_vector": {k: next((float(x["intensity"]) for x in d["knots"]
                                                if x["key"] == k), 0.0) for k in K.KNOTS_ALL},
                       "top1": (max(d["knots"], key=lambda x: x["intensity"])["key"]
                                if d["knots"] else None)})
    return ledger


def _done():
    if not CKPT.exists():
        return set()
    return {(r["arm"], r["rep"]) for r in
            (json.loads(l) for l in CKPT.read_text(encoding="utf-8").splitlines() if l.strip())
            if r.get("ledger")}


def main() -> int:
    text = _text()
    inst = K.instrument_id(TAXO, k=3, knot_n=N2, s1_pairing="round_robin_over_3_s1_draws")
    assert inst["instrument_hash"] == SPEC["design"]["instrument"]["diagnostic_n12"], \
        f"★ 诊断仪器与前登记不符: {inst['instrument_hash']}"

    # 冻结 s1: 跑前生成一次并落盘; 已存在则复用(重跑时不得重新冻结)
    if not FROZEN_S1.exists():
        if os.environ.get("RC_DRYRUN"):
            print("[DRYRUN] 需要先冻结一份 s1(要 3 次调用), dry-run 跳过。")
        else:
            s1f = K.stage1(text, CTX, 3)
            assert not s1f["abstained"] and s1f["k_valid"] >= 2, "冻结用的 s1 必须过资格"
            FROZEN_S1.write_text(json.dumps(s1f, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"冻结 s1 已生成: k_valid={s1f['k_valid']}, draws={len(s1f['draws'])}")
    frozen = json.loads(FROZEN_S1.read_text(encoding="utf-8")) if FROZEN_S1.exists() else None

    done = _done()
    tasks = [(a, i) for a in ("LIVE", "FROZEN_S1") for i in range(R) if (a, i) not in done]
    calls = sum((3 + N2) if a == "LIVE" else N2 for a, _ in tasks)
    print(f"诊断仪器 {inst['instrument_hash']} (生产是 {SPEC['design']['instrument']['production_n5']})")
    print(f"待跑 {len(tasks)}/{2*R} reps = {calls} 次调用")
    if os.environ.get("RC_DRYRUN"):
        print("[DRYRUN] 不发调用。")
        return 0

    cnt, t0 = Counter(), time.time()
    pace = {"next": time.time()}

    def run(t):
        arm, i = t
        gap = 60.0 / (MAX_CALLS_PER_MIN / ((3 + N2) if arm == "LIVE" else N2))
        with _lock:
            now = time.time()
            w = max(0.0, pace["next"] - now)
            pace["next"] = max(now, pace["next"]) + gap
        if w:
            time.sleep(w)
        try:
            if arm == "LIVE":
                s1 = K.stage1(text, CTX, 3)
                if s1["abstained"] or s1["k_valid"] < 2:
                    rec = {"arm": arm, "rep": i, "ledger": None,
                           "note": "stage1 未过资格", "k_valid": s1["k_valid"]}
                else:
                    rec = {"arm": arm, "rep": i, "k_valid": s1["k_valid"],
                           "s1_tops": s1["tops"],
                           "ledger": _s2_with_ledger(text, s1, N2)}
            else:
                rec = {"arm": arm, "rep": i, "k_valid": frozen["k_valid"],
                       "s1_frozen": True,
                       "ledger": _s2_with_ledger(text, frozen, N2)}
            rec["instrument_hash"] = inst["instrument_hash"]
        except Exception as e:
            rec = {"arm": arm, "rep": i, "ledger": None,
                   "infra_suspected": ("全部失败" in str(e) or "空" in str(e)),
                   "error": type(e).__name__ + ": " + str(e)[:160]}
        with _lock:
            with CKPT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_infra = sum(1 for d in (rec.get("ledger") or []) if d.get("infra"))
            key = "ERR" if not rec.get("ledger") else "ok"
            cnt[key] += 1
            print(f"  [{sum(cnt.values())}/{len(tasks)}] {arm} r{i} -> {key} "
                  f"(draws={len(rec.get('ledger') or [])}, infra={n_infra})")

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(run, tasks))
    print(f"\n采集完成 {sum(cnt.values())} reps, 用时 {time.time()-t0:.0f}s: {dict(cnt)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
