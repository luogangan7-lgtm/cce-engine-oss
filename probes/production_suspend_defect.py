#!/usr/bin/env python3
"""真实生产分类器上有没有同一个 suspend 缺陷 —— 走 stage1+stage2, 默认参数。

预注册: tests/data/production_suspend_defect_prereg.json (题目校验和 6627d70e135d0113)

## ★★ 口径(铁律要求, 不许含糊)
跑的是 `cce_knot_classify.stage1 + stage2` —— 整链 11 段里的**两段**。
**不得**说「跑了完整 CCE 链路」。但本轮要测的正是 s2 的结分类, 所以目标对。

## ★ 读数只取 top-1
库内既有裁定 DECIDED_KNOT_READOUT_TOP1_ONLY: 结层 intensity/weight **永久不可用**。

## ★★★ 成本与重试, 发起前冻结
上限 22×8 = **176** 次 + 重试预算 44 = **220 次尝试**, 撞上限即停。
重试只在「没拿到合法输出」时触发, **与答案内容无关**, 每单元最多 2 次。
"""
import json
import os
import pathlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault")
sys.path.insert(0, str(ROOT / "scripts"))
import cce_knot_classify as CK  # noqa: E402

PRE = json.loads((ROOT / "tests/data/production_suspend_defect_prereg.json").read_text(encoding="utf-8"))
OUT = VAULT / "cce_runs" / "production_suspend_defect"
CAP_CALLS = PRE["design"]["cap_calls"]
CAP_ATTEMPTS = 220
MAX_RETRY = 2
_lock = threading.Lock()
_attempts = {"n": 0}


def main():
    import hashlib
    items = json.loads((VAULT / "cce_runs/suspend_confirm_items.json").read_text(encoding="utf-8"))
    chk = hashlib.sha256("".join(sorted(x["id"] for x in items)).encode()).hexdigest()[:16]
    assert chk == PRE["design"]["items"]["checksum"], f"★ 题目校验和不符: {chk}"
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "run_params.json").write_text(json.dumps({
        "chain": "stage1(k=3)+stage2(KNOT_N=5) —— **整链 11 段里的两段, 不是完整链路**",
        "k": 3, "KNOT_N": CK.KNOT_N, "MEASUREMENT_MODEL": CK.MEASUREMENT_MODEL,
        "instrument_hash": CK.instrument_id(taxo, k=3, knot_n=CK.KNOT_N,
                                            s1_pairing="round_robin_over_3_s1_draws")[1]["instrument_hash"]
        if isinstance(CK.instrument_id(taxo, k=3, knot_n=CK.KNOT_N,
                                       s1_pairing="round_robin_over_3_s1_draws"), tuple)
        else CK.instrument_id(taxo, k=3, knot_n=CK.KNOT_N,
                              s1_pairing="round_robin_over_3_s1_draws")["instrument_hash"],
        "★readout": "只取 top-1(DECIDED_KNOT_READOUT_TOP1_ONLY: intensity/weight 永久不可用)",
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    ck = OUT / "raw.json"
    rows = json.loads(ck.read_text(encoding="utf-8")) if ck.exists() else []
    have = {r["id"] for r in rows if r.get("top1") or r.get("abstained")}
    todo = [it for it in items if it["id"] not in have]
    print(f"{len(items)} 题 · 待跑 {len(todo)} · 每题 8 次调用 · 上限 {CAP_CALLS}(尝试上限 {CAP_ATTEMPTS})", flush=True)
    print("★ 口径: stage1+stage2 两段, **不是完整链路**; 读数只取 top-1", flush=True)

    def one(it):
        last = None
        for attempt in range(MAX_RETRY + 1):
            with _lock:
                if _attempts["n"] + 8 > CAP_ATTEMPTS:
                    print(f"★★ 撞尝试上限 {CAP_ATTEMPTS}, 停。", flush=True)
                    return None
                _attempts["n"] += 8
            try:
                s1 = CK.stage1(it["b"], "reddit hearing discussion", 3)
                s2 = CK.stage2(it["b"], s1, taxo)
            except Exception as e:                      # ★ 一条坏读数不许掀翻整轮
                last = f"{type(e).__name__}: {e}"[:200]
                continue
            knots = s2.get("knots") or []
            top1 = knots[0].get("key") if knots and isinstance(knots[0], dict) else None
            ab = bool(s1.get("abstained") or s2.get("measurement_status") == "abstain")
            # ★ 铁律: 数量参数必须硬断言「实得 == 请求」, 不依赖退出码
            k_req, k_valid = s1.get("k_requested"), s1.get("k_valid")
            if top1 or ab:
                r = {"id": it["id"], "cell": it["cell"],
                     "should_be_suspend": it["★should_be_suspend"],
                     "top1": top1, "abstained": ab,
                     "★k_requested": k_req, "★k_valid": k_valid,
                     "★k_assert": ("OK" if k_valid == k_req else
                                   f"★★实得{k_valid}!=请求{k_req} —— 参数被静默降级"),
                     "knots_all": [k.get("key") for k in knots if isinstance(k, dict)],
                     "measurement_status": s2.get("measurement_status"),
                     "attempt": attempt + 1,
                     # ★ 规范字段名就叫 "raw" —— 闸按这个名字找。这里存的是 s2 的**完整原始输出**
                     #   (含 draws / measurement_status / 弃权理由), 足以做确定性重解析。
                     "raw": json.dumps(s2, ensure_ascii=False)[:4000],
                     "raw_s1": json.dumps(s1.get("operational", {}), ensure_ascii=False)[:1500]}
                with _lock:
                    rows.append(r)
                    ck.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
                    print(f"  {len(rows)}/{len(items)} · {it['cell'][:14]} → "
                          f"{top1 or 'ABSTAIN'}{' ★' if top1=='suspend' else ''}", flush=True)
                return r
        with _lock:
            rows.append({"id": it["id"], "cell": it["cell"], "top1": None,
                         "abstained": False, "error": last, "attempt": MAX_RETRY + 1})
            ck.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return None

    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(one, todo))
    ok = sum(1 for r in rows if r.get("top1") or r.get("abstained"))
    print(f"\n★ 完成 {ok}/{len(items)} · 总尝试(估) {_attempts['n']} 次 · 上限 {CAP_ATTEMPTS}")


if __name__ == "__main__":
    main()
