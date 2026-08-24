#!/usr/bin/env python3
"""资格闸精度扩展 —— 固定 n，只看一次。

## 为什么要这一轮
真人原文 U = 9/256 = 3.5%，看着达标；但**精确单侧 95% 上界 6.05% > U_max 5%**
⇒ ADOPT_PENDING_PRECISION。点估计会误判通过，上界才是真相。

## 为什么是 55（这里取 56）
x=9 时 n=311 → upper95 = 0.049955（过）；n=310 → 0.050114（不过）。
现状 n=256 ⇒ 至少再收 55 个。7 base × 2 臂 × R=4 = 56 reps ⇒ n=312。

## ★ 纪律：固定 n、只看一次
固定-n Clopper–Pearson **不是**为 optional stopping 设计的。
不许边跑边看上界、一过 5% 就停 —— 那样报出来的 95% 不是 95%。
若新增样本里再出事件，按 escalation 表（10→336 / 11→361 / 12→386）重算，**不自动续采**。
"""
import json, os, sys, threading, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as K   # noqa: E402

P = ROOT / "tests" / "data" / "phase2"
CKPT = P / "qualification_extension_checkpoint.jsonl"
CTX = "reddit hearing discussion: 多 base 标定面板"   # ★ 与主面板逐字相同
TAXO = json.loads((ROOT / "config" / "knot_taxonomy.json").read_text(encoding="utf-8"))
KK, R, WORKERS = 3, 4, 6
MAX_CALLS_PER_MIN = 45
_lock = threading.Lock()


def _done():
    if not CKPT.exists():
        return set()
    return {(r["base_id"], r["arm"], r["rep"]) for r in
            (json.loads(l) for l in CKPT.read_text(encoding="utf-8").splitlines() if l.strip())}


def main():
    spec = json.loads((P / "qualification_extension_frozen.json").read_text(encoding="utf-8"))
    inst = K.instrument_id(TAXO, k=KK, knot_n=5, s1_pairing=f"round_robin_over_{KK}_s1_draws")
    assert inst["instrument_hash"] == "565470cf26c16d01", \
        f"★ 仪器不符 {inst['instrument_hash']} —— U 不可跨仪器合并"
    tasks = [(b, a, i) for b in spec["chosen"] for a in ("L0", "L0b") for i in range(R)
             if (b["base_id"], a, i) not in _done()]
    # 顺序与臂无关(同主面板教训: 顺序按因子排会把时间衰减做成臂效应)
    import random
    random.Random(spec["design"]["seed"]).shuffle(tasks)
    print(f"仪器 {inst['instrument_hash']} · 待跑 {len(tasks)} reps = {len(tasks)*8} 次调用")
    if os.environ.get("QE_DRYRUN"):
        return
    n, t0, cnt = len(tasks), time.time(), Counter()
    pace = {"next": time.time()}
    gap = 60.0 / (MAX_CALLS_PER_MIN / (KK + 5))

    def run(t):
        b, arm, i = t
        with _lock:
            now = time.time()
            w = max(0.0, pace["next"] - now)
            pace["next"] = max(now, pace["next"]) + gap
        if w:
            time.sleep(w)
        try:
            s1 = K.stage1(b["text"], CTX, KK)
            for nm in ("k_valid", "abstained", "measurement_status", "operational"):
                if nm not in s1:
                    raise KeyError(f"stage1 缺 {nm}")
            q = not (s1["abstained"] or s1["k_valid"] < 2)
            rec = {"base_id": b["base_id"], "arm": arm, "rep": i, "qualified": q,
                   "k_valid": s1["k_valid"], "abstained": s1["abstained"],
                   "length_stratum": b["length_stratum"], "op": s1["operational"]}
        except Exception as e:
            rec = {"base_id": b["base_id"], "arm": arm, "rep": i, "qualified": False,
                   "k_valid": None, "abstained": None,
                   "stage_failed": "stage1" if "stage1" in str(e) else "unknown",
                   "infra_suspected": "全部失败" in str(e),
                   "length_stratum": b["length_stratum"], "op": {"error": str(e)[:160]}}
        with _lock:
            with CKPT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            cnt["d"] += 1
            cnt["q" if rec["qualified"] else "u"] += 1
            if cnt["d"] % 10 == 0 or cnt["d"] == n:
                el = time.time() - t0
                print(f"  [{cnt['d']}/{n}] qualified={cnt['q']} unqualified={cnt['u']} "
                      f"{cnt['d']*8/el*60:.0f} calls/min", flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(run, tasks))
    print(f"\n落盘 {len(_done())} reps → {CKPT.relative_to(ROOT)}")
    print("★ 现在才允许看一次结果。不要因为数字不好就再采。")


if __name__ == "__main__":
    main()
