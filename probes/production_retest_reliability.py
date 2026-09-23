#!/usr/bin/env python3
"""真实生产链路的**完整流程重测** —— 第四本账, 此前是空的。

预注册: tests/data/production_retest_reliability_prereg.json

## ★★★ 三条不许违反的
① **必须完整重跑 s1 和 s2** —— 复用旧 s1 测到的是「条件于固定 s1 的 s2 稳定性」, **不是完整重测**
② **没有事先定义允许的翻转率 ⇒ 不能签发「信度合格」**; 即使 22/22 不翻也只报事实
③ **不许把无合法读数的条目当作稳定**, **不许默默删除后只报漂亮比例**

## 上限
176 次基础 + 最多 22 次**仅用于预定义无效响应**的重试 = **总尝试 198**, 撞上限即停。
"""
import json
import pathlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault")
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as CK  # noqa: E402

PRE = json.loads((ROOT / "tests/data/production_retest_reliability_prereg.json").read_text(encoding="utf-8"))
RUN1 = VAULT / "cce_runs" / "production_suspend_defect"
OUT = VAULT / "cce_runs" / "production_retest"
CAP_ATTEMPTS = 198
MAX_RETRY = 1          # ★ 预注册: 最多 22 次重试 ⇒ 每单元至多 1 次
_lock = threading.Lock()
_att = {"n": 0}


def main():
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    # ★★★ 前提: 必须是**同一台生产仪器**, 否则不构成重测
    r = CK.instrument_id(taxo, k=3, knot_n=CK.KNOT_N, s1_pairing="round_robin_over_3_s1_draws")
    ih = (r[1] if isinstance(r, tuple) else r)["instrument_hash"]
    p1 = json.loads((RUN1 / "run_params.json").read_text(encoding="utf-8"))
    assert ih == p1["instrument_hash"], f"★★★ 仪器变了({p1['instrument_hash']} → {ih}) —— 不构成重测, 停"
    assert CK.KNOT_N == p1["KNOT_N"] and CK.MEASUREMENT_MODEL == p1["MEASUREMENT_MODEL"], "★ 参数不一致"

    items = json.loads((VAULT / "cce_runs/suspend_confirm_items.json").read_text(encoding="utf-8"))
    run1 = {x["id"]: x for x in json.loads((RUN1 / "raw.json").read_text(encoding="utf-8"))}
    assert len(items) == 22 and len(run1) == 22

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "run_params.json").write_text(json.dumps({
        "★这是第二次运行": "与 cce_runs/production_suspend_defect 构成**完整流程重测**",
        "chain": "stage1(k=3)+stage2(KNOT_N=5) —— 整链 11 段里的两段, **不是完整链路**",
        "k": 3, "KNOT_N": CK.KNOT_N, "MEASUREMENT_MODEL": CK.MEASUREMENT_MODEL,
        "instrument_hash": ih,
        "★与第一次逐项比对": "k/KNOT_N/MEASUREMENT_MODEL/instrument_hash **四项全同**(发起前已断言)",
        "★readout": "只取 top-1(DECIDED_KNOT_READOUT_TOP1_ONLY)",
        "★完整重跑": "**s1 与 s2 都重跑**, 未复用旧 s1",
        "cap_attempts": CAP_ATTEMPTS,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    ck = OUT / "raw.json"
    rows = json.loads(ck.read_text(encoding="utf-8")) if ck.exists() else []
    have = {r_["id"] for r_ in rows if r_.get("top1") or r_.get("abstained")}
    todo = [it for it in items if it["id"] not in have]
    print(f"★ 完整流程重测 · {len(items)} 题 · 待跑 {len(todo)} · 每题 8 次 · 尝试上限 {CAP_ATTEMPTS}", flush=True)
    print(f"★ 仪器同一性已断言: instrument_hash = {ih}", flush=True)

    def one(it):
        last = None
        for attempt in range(MAX_RETRY + 1):
            with _lock:
                if _att["n"] + 8 > CAP_ATTEMPTS:
                    print(f"★★ 撞尝试上限 {CAP_ATTEMPTS}, 停。", flush=True)
                    return None
                _att["n"] += 8
            try:
                s1 = CK.stage1(it["b"], "reddit hearing discussion", 3)   # ★ 完整重跑 s1
                s2 = CK.stage2(it["b"], s1, taxo)                          # ★ 完整重跑 s2
            except Exception as e:
                last = f"{type(e).__name__}: {e}"[:200]
                continue
            knots = s2.get("knots") or []
            top1 = knots[0].get("key") if knots and isinstance(knots[0], dict) else None
            ab = bool(s1.get("abstained") or s2.get("measurement_status") == "abstain")
            if top1 or ab:
                prev = run1.get(it["id"], {})
                r_ = {"id": it["id"], "cell": it["cell"],
                      "top1_run2": top1, "top1_run1": prev.get("top1"),
                      "same": (top1 == prev.get("top1")),
                      "abstained": ab,
                      "★k_requested": s1.get("k_requested"), "★k_valid": s1.get("k_valid"),
                      "★k_assert": ("OK" if s1.get("k_valid") == s1.get("k_requested")
                                    else f"★★实得{s1.get('k_valid')}!=请求{s1.get('k_requested')}"),
                      "attempt": attempt + 1,
                      "raw": json.dumps(s2, ensure_ascii=False)[:4000]}
                with _lock:
                    rows.append(r_)
                    ck.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
                    print(f"  {len(rows)}/{len(items)} · {it['cell'][:12]} · "
                          f"run1={prev.get('top1')} run2={top1} "
                          f"{'✅同' if r_['same'] else '★翻转'}", flush=True)
                return r_
        with _lock:
            rows.append({"id": it["id"], "cell": it["cell"], "top1_run2": None,
                         "top1_run1": run1.get(it["id"], {}).get("top1"),
                         "same": None, "abstained": False, "error": last})
            ck.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return None

    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(one, todo))
    ok = [r_ for r_ in rows if r_.get("top1_run2")]
    same = sum(1 for r_ in ok if r_["same"])
    print(f"\n★ 完成 {len(ok)}/{len(items)} 有合法读数 · 一致 {same}/{len(ok)} · 总尝试(估) {_att['n']}")
    print("★★ 提醒: **没有事先定义允许的翻转率 ⇒ 不签发「信度合格」**, 只报事实。")


if __name__ == "__main__":
    main()
