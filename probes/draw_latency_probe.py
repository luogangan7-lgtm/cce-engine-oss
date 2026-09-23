# -*- coding: utf-8 -*-
"""第一步(零仪器变更): 量单次 s1 / s2 调用的延迟分布, 按 tests/data/sampling_reduction_prereg.json 冻结的规则算各候选的期望节省。

★ 会发起调用: 10 次 s1 + 10 次 s2 = 20 次 MiniMax(订阅), 硬上限 20, 撞上即停。不改任何仪器文件, 不写 knot 读数。
★ 用生产的 prompt 构造器(与真实 draw 同 prompt), 生产同样的 5 路并发分两波发 —— 量的是生产工况下的延迟, 不是空载延迟。
"""
import hashlib, json, os, pathlib, random, statistics, sys, time
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
PREREG = ROOT / "tests/data/sampling_reduction_prereg.json"; OUT = ROOT / "results/draw_latency.json"
N1 = N2 = 10; CAP = 20; WAVE = 5; B = 4000
TEXT = ("Honestly I'm about ready to give up on these. Paid a fortune, and the left one dies by 4pm every single day. The audiologist says "
        "it's normal. Is it? I'm comparing the new models but I don't want to spend again if it's just going to be the same story.")
CONTEXT = "bench"


def _load_key():
    for line in pathlib.Path("/Volumes/data/viral-skill-eval/.env").read_text(encoding="utf-8").splitlines():
        line = line.strip().removeprefix("export ")
        if line.startswith("MINIMAX_API_KEY="): os.environ["MINIMAX_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")


def emax(samples, n, rng):
    """bootstrap: 有放回抽 n 个取 max, 重复 B 次的均值与 90% 区间。"""
    xs = [max(rng.choice(samples) for _ in range(n)) for _ in range(B)]; xs.sort()
    return {"mean": round(statistics.fmean(xs), 2), "p05": round(xs[int(0.05 * B)], 2), "p95": round(xs[int(0.95 * B) - 1], 2)}


def evaluate(l1, l2, prereg, seed=20260923):
    """由延迟样本 + 预注册规则算判决。纯函数, 闸用它重算。"""
    rng = random.Random(seed); cur = prereg["★当前仪器(冻结, 由闸现算比对)"]
    base = {"s1": emax(l1, cur["s1_k"]["reply"], rng), "s2": emax(l2, cur["s2_n"], rng)}
    base_t = base["s1"]["mean"] + base["s2"]["mean"]
    rule = prereg["★★★第一步(零仪器变更, 先做)"]["★★★判决线(先于数据冻结)"]
    need_sec, need_ratio = 10.0, 0.15
    out = {}
    for name, c in prereg["★★★候选方案(先列全, 禁止事后加)"].items():
        if not name.isalpha() or not isinstance(c, dict) or "s1_k" not in c: continue
        rng = random.Random(seed + ord(name)); e = {"s1": emax(l1, c["s1_k"], rng), "s2": emax(l2, c["s2_n"], rng)}
        t = e["s1"]["mean"] + e["s2"]["mean"]; save = round(base_t - t, 2); ratio = round(save / base_t, 4) if base_t else None
        lo = round(base_t - (e["s1"]["p95"] + e["s2"]["p95"]), 2); hi = round(base_t - (e["s1"]["p05"] + e["s2"]["p05"]), 2)
        go = save >= need_sec and (ratio or 0) >= need_ratio
        out[name] = {"s1_k": c["s1_k"], "s2_n": c["s2_n"], "E[T]": round(t, 2), "期望节省秒": save, "节省比": ratio, "节省 90% 区间(粗)": [lo, hi],
                     "触发第二步": go, "INCONCLUSIVE(区间跨 10 s 门)": lo < need_sec <= hi}
    return {"当前 E[T(3,5)]": round(base_t, 2), "当前分解": base, "候选": out, "★任一候选触发第二步": any(v["触发第二步"] for v in out.values()),
            "★判决线(抄自预注册)": rule["启动第二步的条件(两条同时)"]}


def main():
    prereg = json.loads(PREREG.read_text(encoding="utf-8")); psha = hashlib.sha256(PREREG.read_bytes()).hexdigest()[:16]
    _load_key()
    from cce_knot_classify import _stage1_case, _build_stage2_prompt, MEASUREMENT_MODEL
    from cce_structural_gate import structural_gate
    from exp_v4_full_validation import call_parse, extract_json_robust
    from exp_crossmodel_desire import call_model
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    text = structural_gate(TEXT)["subject_text"]; case = _stage1_case(text, CONTEXT); temps = [0.0, 0.3, 0.6]
    ledger = {"calls": 0}; rows = []

    def s1_call(i):
        ledger["calls"] += 1
        if ledger["calls"] > CAP: raise RuntimeError("BUDGET_EXCEEDED")
        T = temps[i % 3]; t0 = time.time(); c, p, pv, m, ok = call_parse(MEASUREMENT_MODEL, case, T, "latency_s1"); dt = round(time.time() - t0, 2)
        return {"stage": "s1", "i": i, "T": T, "sec": dt, "ok": bool(ok), "chars": len(c or "")}, pv

    # ★ s2 prompt 里的 s1 摘要(tops/appraisal)取一份**生产归档的 stage1**(与生产同形); 文本仍是本探针合成句。量的是延迟不是读数。
    import glob
    s1_prod = json.loads(pathlib.Path(sorted(glob.glob(str(ROOT / "archive/*/*s1_readout.json")))[-1]).read_text(encoding="utf-8"))["stage1"]
    prompt2 = _build_stage2_prompt(taxo, text, s1_prod)
    PARTIAL = ROOT / "results/draw_latency_partial.jsonl"
    if PARTIAL.exists(): PARTIAL.unlink()
    def persist(r):
        with PARTIAL.open("a", encoding="utf-8") as fh: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    for w in range(0, N1, WAVE):
        with ThreadPoolExecutor(max_workers=WAVE) as ex:
            for r, pv in ex.map(s1_call, range(w, min(w + WAVE, N1))):
                rows.append(r); persist(r); print("  s1 #%d T=%.1f %.1fs ok=%s" % (r["i"], r["T"], r["sec"], r["ok"]))

    def s2_call(j):
        ledger["calls"] += 1
        if ledger["calls"] > CAP: raise RuntimeError("BUDGET_EXCEEDED")
        t0 = time.time()
        try: c, _ = call_model(MEASUREMENT_MODEL, prompt2, temperature=0.0); d = extract_json_robust(c, log_note="latency_s2"); ok = isinstance(d, dict) and isinstance(d.get("knots"), list)
        except Exception: c, ok = "", False
        return {"stage": "s2", "i": j, "T": 0.0, "sec": round(time.time() - t0, 2), "ok": bool(ok), "chars": len(c or "")}

    for w in range(0, N2, WAVE):
        with ThreadPoolExecutor(max_workers=WAVE) as ex:
            for r in ex.map(s2_call, range(w, min(w + WAVE, N2))): rows.append(r); persist(r); print("  s2 #%d %.1fs ok=%s" % (r["i"], r["sec"], r["ok"]))
    l1 = [r["sec"] for r in rows if r["stage"] == "s1"]; l2 = [r["sec"] for r in rows if r["stage"] == "s2"]
    ev = evaluate(l1, l2, prereg)
    res = {"block": "DRAW_LATENCY_STEP1", "date": "2026-09-23", "★预注册 sha(测量前冻结)": psha, "★性质": "延迟分布测量, 不是优化结果; 零仪器变更",
           "★调用账": {**ledger, "★作废": "首次执行 10 次 s1 后在 s2 prompt 构造处报错(KeyError tops), 未落盘, 那 10 次不进本产物; 修后重跑, 本产物 20 次全新"}, "★工况": {"并发": WAVE, "s1 prompt chars": len(case), "s2 prompt chars": len(prompt2), "model": MEASUREMENT_MODEL},
           "样本": {"s1 sec": l1, "s2 sec": l2, "s1 中位/最大": [statistics.median(l1), max(l1)], "s2 中位/最大": [statistics.median(l2), max(l2)], "失败": sum(1 for r in rows if not r["ok"])},
           "★★★评估(按预注册规则现算)": ev, "rows": rows,
           "★★★结论": ("H1: 有候选过线 ⇒ 第二步可启动(见候选表)" if ev["★任一候选触发第二步"] else "H0: 没有候选同时过 10 s 与 15% ⇒ STOP —— 时间在单次调用延迟, 不在抽样次数; K/n 减少不值得换仪器")}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(ev, ensure_ascii=False, indent=1)); print(res["★★★结论"]); print("→", OUT); return 0


if __name__ == "__main__": sys.exit(main())
