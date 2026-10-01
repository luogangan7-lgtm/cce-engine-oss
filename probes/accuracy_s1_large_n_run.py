#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 tests/data/accuracy_s1_large_n_prereg.json 跑 S1(九结分布 temp=0 重测)的加大条目数复测。

用法:
  .venv/bin/python probes/accuracy_s1_large_n_run.py            # 真跑: 需环境变量 MINIMAX_API_KEY, 硬上限 260 次
  .venv/bin/python probes/accuracy_s1_large_n_run.py --offline  # 零 API 演练: 假回复, 内存账本, 只打印不落盘
  .venv/bin/python probes/accuracy_s1_large_n_run.py --power    # 只打印功效表(零 API), 预注册里的数由它现算
★ 预注册 sha256 钉在 PREREG_SHA256; 不符即拒跑。key 只读环境变量, 不落盘不打印。
★ 加的是**条目数**(独立单位), 每条仍 2 次重测 —— 不是台账里已否决的「加大重复数 n」。
"""
import hashlib, json, math, os, pathlib, random, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
import accuracy_real_provider_run as R1  # noqa: E402  (wilson / _load / _js / 第一轮的 N_ITEMS 与 MODELS)

PREREG = ROOT / "tests/data/accuracy_s1_large_n_prereg.json"
PREREG_SHA256 = "e5b42e60f897979ec9bfa98ad5cfba50c52cdf9b6b4d846d7b8f3942ca03d1b2"
RESULT = ROOT / "tests/data/accuracy_s1_large_n_result.json"
AUTH_ID, CAP = "accuracy_s1_large_n_2026_10_01", 260
MODELS, SKIP = R1.MODELS, R1.N_ITEMS          # 第一轮按 sha256(id) 取了前 30 条 ⇒ 跳过
JS_MAX, BOOT_B, BOOT_SEED = 0.05, 2000, 20261001
P_GRID = (0.70, 0.75, 0.77, 0.80, 0.82, 0.85, 0.87, 0.90)
P_HAT = {"MiniMax-M3": (26, 30), "MiniMax-M2.7": (23, 30)}   # 第一轮观测(tests/data/accuracy_real_provider_result.json)


def select(sample):
    return sorted(sample, key=lambda x: hashlib.sha256(x["id"].encode()).hexdigest())[SKIP:]


def _thresholds(n):
    ks = min(k for k in range(n + 1) if R1.wilson(k, n)[0] >= 0.80)
    ku = max([k for k in range(n + 1) if R1.wilson(k, n)[1] < 0.80] or [-1])
    return ks, ku


def _tails(n, p):
    lp = lambda k: math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * math.log(p) + (n - k) * math.log(1 - p)
    ks, ku = _thresholds(n)
    return sum(math.exp(lp(k)) for k in range(ks, n + 1)), sum(math.exp(lp(k)) for k in range(ku + 1))


def power(n_list=(30, 51)):
    """精确二项功效。STABLE 列只算 top1 部分(还需 JS<=0.05, 无逐条 JS 可建模) ⇒ 是上界。"""
    out = {}
    for n in n_list:
        ks, ku = _thresholds(n)
        row = {}
        for label, p in [("%.2f" % p, p) for p in P_GRID] + [("p_hat_%s=%d/%d" % (m, *kn), kn[0] / kn[1]) for m, kn in P_HAT.items()]:
            s, u = _tails(n, p)
            row[label] = {"P_stable_top1_part_UPPER_BOUND": round(s, 3), "P_unstable": round(u, 3),
                          "P_inconclusive_AT_LEAST": round(1 - s - u, 3)}
        out["n=%d" % n] = {"k_min_for_stable_top1": ks, "k_max_for_unstable": ku, "by_true_p": row}
    need = {}
    for m, (k, n0) in P_HAT.items():
        idx = 0 if m == "MiniMax-M3" else 1      # M3 的 p̂ 在 0.80 之上 ⇒ 看 STABLE 部分; M2.7 在之下 ⇒ 看 UNSTABLE
        need[m] = next((n for n in range(30, 2001, 10) if _tails(n, k / n0)[idx] >= 0.80), None)
    out["n_needed_for_80pct_decisive_at_p_hat"] = need
    return out


def boot_ci(xs, seed=BOOT_SEED, b=BOOT_B):
    if not xs:
        return None, None
    rng = random.Random(seed)
    ms = sorted(sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(b))
    return round(ms[int(0.025 * b)], 4), round(ms[int(0.975 * b) - 1], 4)


def run(offline):
    got = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if got != PREREG_SHA256:
        raise SystemExit("★ 预注册被改过(sha256 %s != 钉住的 %s) —— 拒跑" % (got[:16], PREREG_SHA256[:16]))
    if not offline and os.environ.get("GITHUB_ACTIONS"):
        os.environ.setdefault("CCE_BUDGET_STATE", "/tmp/accuracy_s1_large_n_budget.json")   # 账本随 artifact 上传
    m = R1._load(offline)
    m.BUDGET_ID, m.BUDGET_LIMIT = AUTH_ID, CAP            # call() 每次 POST 前(含重试)按本授权单扣额
    attempts = [0]
    _res = m.reserve

    def counted(*a, **k):
        r = _res(*a, **k)
        attempts[0] += 1
        return r
    m.reserve = counted
    items = select(m.SAMPLE)
    out = {"block": "ACCURACY_S1_LARGE_N_RESULT", "prereg_sha256": got, "offline_dry_run": offline,
           "items": [x["id"] for x in items], "cells": {}}

    def guarded(cell, fn):
        res, fails = [], 0
        for i, it in enumerate(items):
            r = fn(it)
            fails += r is None
            res.append(r)
            if i == 9 and fails >= 5:
                out["cells"][cell + "_stopped"] = "PARSE_FAILURE(前 10 次 %d 次解析失败)" % fails
                return None
        return res

    import cce_request_budget as B
    try:
        for model in MODELS:
            reps = []
            for _ in range(2):
                r = guarded("S1_" + model, lambda it: m.annot_dist((model, it))[1])
                if r is None:
                    break
                reps.append(r)
            if len(reps) < 2:
                out["cells"]["S1_" + model] = {"verdict": "PARSE_FAILURE"}
                continue
            tops = [[max(d, key=d.get) if d else None for d in r] for r in reps]
            agree = sum(1 for a, b in zip(*tops) if a is not None and a == b)
            js = [x for x in (R1._js(a, b, m) for a, b in zip(*reps)) if x is not None]
            lo, hi = R1.wilson(agree, len(items))
            mjs = round(sum(js) / len(js), 4) if js else None
            v = "STABLE" if lo >= 0.80 and mjs is not None and mjs <= JS_MAX else "UNSTABLE" if hi < 0.80 else "INCONCLUSIVE"
            jlo, jhi = boot_ci(js)
            jv = None if jlo is None else "JS_ABOVE" if jlo > JS_MAX else "JS_BELOW" if jhi <= JS_MAX else "JS_UNRESOLVED"
            out["cells"]["S1_" + model] = {"top1_agree": "%d/%d" % (agree, len(items)), "wilson95": [lo, hi],
                                           "mean_JS": mjs, "n_js": len(js), "verdict": v,
                                           "mean_JS_boot95": [jlo, jhi], "JS_readout": jv,
                                           "STABLE_EXCLUDED": v == "INCONCLUSIVE" and jv == "JS_ABOVE"}
    except B.BudgetExceeded as e:
        out["★budget_stop"] = "撞 %d 次硬上限: %s —— 未跑完的格判 INSUFFICIENT" % (CAP, str(e)[:120])
    out["http_attempts"] = attempts[0]
    return out


if __name__ == "__main__":
    if "--power" in sys.argv:
        print(json.dumps(power(), ensure_ascii=False, indent=1))
        sys.exit(0)
    offline = "--offline" in sys.argv
    res = run(offline)
    txt = json.dumps(res, ensure_ascii=False, indent=1) + "\n"
    if offline:
        print(txt)
    else:
        RESULT.write_text(txt, encoding="utf-8")
        print("写入", RESULT.relative_to(ROOT))
        if os.environ.get("GITHUB_ACTIONS"):   # probe.yml 的 artifact 只收 /tmp/*.json
            pathlib.Path("/tmp", RESULT.name).write_text(txt, encoding="utf-8")
