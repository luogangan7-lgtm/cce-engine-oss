#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 tests/data/accuracy_real_provider_prereg.json 跑真实 provider 的重测稳定性与锚例排除检验。

用法:
  .venv/bin/python probes/accuracy_real_provider_run.py            # 真跑: 需环境变量 MINIMAX_API_KEY, 硬上限 200 次
  .venv/bin/python probes/accuracy_real_provider_run.py --offline  # 零 API 演练: 假回复, 内存账本, 只打印不落盘
★ 预注册 sha256 钉在 PREREG_SHA256; 不符即拒跑。key 只读环境变量, 不落盘不打印。
"""
import hashlib, json, math, os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PREREG = ROOT / "tests/data/accuracy_real_provider_prereg.json"
PREREG_SHA256 = "d08ec84b8b92365e16a366eee70d22dc0296c6057733b75b002055cabae9ddad"
RESULT = ROOT / "tests/data/accuracy_real_provider_result.json"
AUTH_ID, CAP = "accuracy_real_provider_2026_10_01", 200
MODELS, FACT_MODEL, N_ITEMS = ("MiniMax-M3", "MiniMax-M2.7"), "MiniMax-Text-01", 30


def wilson(k, n, z=1.96):
    if not n:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 4), round(c + h, 4)


def _load(offline):
    if offline:
        sys.path.insert(0, str(ROOT / "probes"))
        import accuracy_offline_harness as AH
        kn = ["pain_seek", "injustice", "belong", "reward", "display", "itch", "suspend", "inertia", "audit"]

        def fake(model, prompt):
            h = int(hashlib.sha256((model + prompt).encode()).hexdigest(), 16)
            if "你是事实抽取器" in prompt:
                return json.dumps({k: bool((h >> i) & 1) for i, k in enumerate(
                    ("named_specific_model", "described_own_situation_in_detail", "asked_question",
                     "challenged_or_confronted", "thanks_only", "offered_help_or_correction"))})
            return json.dumps({"knots": [{"key": kn[h % 9], "weight": 0.6}, {"key": kn[(h // 9) % 9], "weight": 0.4}]})
        return AH.load(responses=fake)
    if not os.environ.get("MINIMAX_API_KEY"):
        print(json.dumps({"status": "BLOCKED_NO_KEY", "real_calls": 0}, ensure_ascii=False))
        sys.exit(3)
    sys.path.insert(0, str(ROOT / "accuracy"))
    import run_gates as m          # noqa: E402  (import 期读 key; 只在环境里)
    return m


def _js(p, q, m):
    return m.js_div(p, q) if p and q else None


def run(offline):
    got = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if got != PREREG_SHA256:
        raise SystemExit("★ 预注册被改过(sha256 %s != 钉住的 %s) —— 拒跑" % (got[:16], PREREG_SHA256[:16]))
    m = _load(offline)
    m.BUDGET_ID, m.BUDGET_LIMIT = AUTH_ID, CAP            # call() 每次 POST 前(含重试)按本授权单扣额
    items = sorted(m.SAMPLE, key=lambda x: hashlib.sha256(x["id"].encode()).hexdigest())[:N_ITEMS]
    out = {"block": "ACCURACY_REAL_PROVIDER_RESULT", "prereg_sha256": got, "offline_dry_run": offline,
           "items": [x["id"] for x in items], "cells": {}}

    def guarded(cell, jobs, fn):
        """逐个跑; 前 10 次里解析失败 >= 5 ⇒ 停该格。撞预算 ⇒ 向上抛, 全局停。"""
        res, fails = [], 0
        for i, j in enumerate(jobs):
            r = fn(j)
            fails += r is None
            res.append(r)
            if i == 9 and fails >= 5:
                out["cells"][cell + "_stopped"] = "PARSE_FAILURE(前 10 次 %d 次解析失败)" % fails
                return None
        return res

    import cce_request_budget as B
    try:
        for model in MODELS:                                   # S1
            reps = []
            for _ in range(2):
                r = guarded("S1_" + model, items, lambda it: m.annot_dist((model, it))[1])
                if r is None:
                    break
                reps.append(r)
            if len(reps) < 2:
                out["cells"]["S1_" + model] = {"verdict": "PARSE_FAILURE"}
                continue
            tops = [[max(d, key=d.get) if d else None for d in r] for r in reps]
            agree = sum(1 for a, b in zip(*tops) if a is not None and a == b)
            js = [x for x in (_js(a, b, m) for a, b in zip(*reps)) if x is not None]
            lo, hi = wilson(agree, len(items))
            mjs = round(sum(js) / len(js), 4) if js else None
            v = "STABLE" if lo >= 0.80 and mjs is not None and mjs <= 0.05 else "UNSTABLE" if hi < 0.80 else "INCONCLUSIVE"
            out["cells"]["S1_" + model] = {"top1_agree": "%d/%d" % (agree, len(items)), "wilson95": [lo, hi],
                                           "mean_JS": mjs, "n_js": len(js), "verdict": v}
        for model in MODELS:                                   # S2
            q = m.qualify(model)
            lo, hi = wilson(q["hits"], q["of"])
            out["cells"]["S2_" + model] = {"hits": "%d/%d" % (q["hits"], q["of"]), "wilson95": [lo, hi],
                                           "verdict": "DISQUALIFIED" if hi <= 0.70 else "NOT_DISQUALIFIED"}
        reps = []                                              # S3
        for _ in range(2):
            r = guarded("S3", items, lambda it: m.extract_facts(it)[1])
            if r is None:
                break
            reps.append(r)
        if len(reps) == 2:
            tiers = [[m.observed_tier_from_facts(f, it) for f, it in zip(r, items)] for r in reps]
            agree = sum(1 for a, b in zip(*tiers) if a is not None and a == b)
            lo, hi = wilson(agree, len(items))
            per = {k: sum(1 for a, b in zip(*reps) if a and b and a[k] == b[k]) for k in (reps[0][0] or {}).keys()} if reps[0][0] else {}
            out["cells"]["S3"] = {"tier_agree": "%d/%d" % (agree, len(items)), "wilson95": [lo, hi], "per_fact_agree": per,
                                  "verdict": "STABLE" if lo >= 0.80 else "UNSTABLE" if hi < 0.80 else "INCONCLUSIVE"}
        else:
            out["cells"]["S3"] = {"verdict": "PARSE_FAILURE"}
    except B.BudgetExceeded as e:
        out["★budget_stop"] = "撞 %d 次硬上限: %s —— 未跑完的格判 INSUFFICIENT" % (CAP, str(e)[:120])
    return out


if __name__ == "__main__":
    offline = "--offline" in sys.argv
    res = run(offline)
    txt = json.dumps(res, ensure_ascii=False, indent=1) + "\n"
    if offline:
        print(txt)
    else:
        RESULT.write_text(txt, encoding="utf-8")
        print("写入", RESULT.relative_to(ROOT))
