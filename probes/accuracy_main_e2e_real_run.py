#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 tests/data/accuracy_main_e2e_real_prereg.json 在真实 provider 上端到端跑一次 run_gates.main(), 判**编排**。

用法:
  .venv/bin/python probes/accuracy_main_e2e_real_run.py            # 真跑: 需 MINIMAX_API_KEY, 硬上限 520 次
  .venv/bin/python probes/accuracy_main_e2e_real_run.py --offline  # 零 API 演练: 合成回复(accuracy_main_e2e_offline.Fake), 只打印不落盘
★ 预注册 sha256 钉在 PREREG_SHA256; 不符即拒跑。key 只读环境变量, 不落盘不打印。
★ 对 main() 只做两处透传替换: call() 外包一层记录器(记每次返回值, 供离线回放), reserve() 改记本授权单(上限 520)。
  main() 的资格考 / 准入 / 标注 / 落盘 / G-K1 / G-K2 / 汇总 / 扣发逐字未改; 结构上限自检照常执行(BUDGET_LIMIT 不动)。
★ 跑完立即两条离线臂(零调用): ① 用记录的真实回复回放 main(), gates_result 必须逐字段相等;
  ② 同一批真实回复但事实抽取全置空, main() 必须不崩、G-K2 与 overall 扣发(None)。
"""
import collections, contextlib, hashlib, io, json, os, pathlib, sys, tempfile, threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "scripts"))
import accuracy_offline_harness as AH  # noqa: E402

PREREG = ROOT / "tests/data/accuracy_main_e2e_real_prereg.json"
PREREG_SHA256 = "b428990b7b554ff2524a032889ca5d566b73cadcd6863537719c08873b86ff6f"
RESULT = ROOT / "tests/data/accuracy_main_e2e_real_result.json"
REPLAY = ROOT / "tests/data/accuracy_main_e2e_real_replay.json"
AUTH_ID, CAP = "accuracy_main_e2e_real_2026_10_01", 520
STIMULUS_ENV = ("CCE_CORPUS", "CCE_BODY_CHARS", "CCE_UNIT_LABEL", "CCE_SKIP_GK2")   # 进 prompt 或决定跑哪几道闸
GK_KEYS = {"gate", "run_params", "sample_n", "annotators", "coverage", "G_K1v2_分布一致性", "G_K2v2_成本档预测",
           "混淆诊断", "annotator_qualification", "overall_pass", "★overall_withheld_because", "★pass_components"}
WITHHELD_KEYS = {"gate", "overall_pass", "run_params", "★withheld", "annotator_qualification"}


def _key(model, prompt):
    return hashlib.sha256((model + "\x00" + prompt).encode()).hexdigest()


def _kind(prompt):
    if "★示范锚例(留一法" in prompt:
        return "qualify"
    if "你是事实抽取器" in prompt:
        return "fact"
    if "多个标注者在下列真实评论上判定不一致" in prompt:
        return "diag"
    return "dist"


def _instrument(m, reserve):
    """call() 外包记录器(透传), reserve() 换成本授权单。返回记录对象。"""
    rec = {"out": {}, "n": collections.Counter(), "by_model": collections.Counter(), "attempts": 0}
    lock, orig = threading.Lock(), m.call

    def call(model, prompt, max_tokens=4000):
        out = orig(model, prompt, max_tokens)
        k = _kind(prompt)
        with lock:
            rec["out"][_key(model, prompt)] = {"model": model, "kind": k, "out": out}
            rec["n"][k] += 1
            rec["by_model"][(k, model)] += 1
        return out

    def counted(auth_id, limit, n=1, note=""):
        r = reserve(AUTH_ID, CAP, n, note)
        with lock:
            rec["attempts"] += n
        return r
    m.call, m.reserve = call, counted
    return rec


def _main_in(m, out_dir):
    rc, err = None, None
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            rc = m.main()
        except Exception as e:     # BudgetExceeded 由调用方另判
            err = e
    rd = lambda n: json.load(open(os.path.join(out_dir, n), encoding="utf-8")) if os.path.exists(os.path.join(out_dir, n)) else None
    return rc, err, rd("gates_result.json"), rd("raw_annotations.json")


def _replay(recorded, blank_facts=False, mutator=None):
    """离线回放(零调用): 只替换传输结果, main() 原代码。返回 (rc, err, gates_result, misses, tripped)。"""
    misses = []

    def resp(model, prompt):
        r = recorded.get(_key(model, prompt))
        if r is None:
            misses.append(_kind(prompt))
            return ""
        return "" if (blank_facts and r["kind"] == "fact") else r["out"]
    import calibration_framework as CF
    with tempfile.TemporaryDirectory() as td:
        saved, CF.JSON_FAIL_LOG = CF.JSON_FAIL_LOG, os.path.join(td, "json_extract_failures.log")
        try:
            m = AH.load(source_mutator=mutator, responses=resp, env={"CCE_SKIP_GK2": "0", "CCE_OUT_DIR": td})
            with AH._Tripwire() as tw:
                rc, err, g, _ = _main_in(m, td)
        finally:
            CF.JSON_FAIL_LOG = saved
    return rc, (type(err).__name__ if err else None), g, misses, list(tw.tripped)


def properties(m, rec, rc, err, g, raw, models0, n_sample, n_anchor):
    """预注册 decision.O1–O7。只求与所走路径相关的那几条。"""
    adm = (raw or {}).get("annotators")
    rp = (g or {}).get("run_params") or {}
    P = {"O1_gates_result 已落盘且无异常": g is not None and err is None,
         "O2_资格考每人考满锚例": rec["n"]["qualify"] == len(models0) * n_anchor,
         "O3_尝试数 <= 上限 且 >= 逻辑调用数": sum(rec["n"].values()) <= rec["attempts"] <= CAP,
         "O4_run_params 盖章与本仓闸协议一致": (rp.get("gate_protocol_hash") == m.gate_protocol_hash()
                                         and rp.get("gate_protocol_version") == m.GATE_PROTOCOL_VERSION
                                         and rp.get("CCE_SKIP_GK2") is False and rp.get("CCE_BODY_CHARS") == 700)}
    if rc == 2:     # 全员被剔除 ⇒ 扣发路径
        P["O5w_扣发: 返回 2, overall=None, 字段齐"] = (g is not None and WITHHELD_KEYS <= set(g)
                                                 and g["overall_pass"] is None and bool(g["★withheld"]))
        P["O5w_扣发 ⇒ 零标注零抽取"] = rec["n"]["dist"] == 0 and rec["n"]["fact"] == 0
        return P
    gk1, gk2 = (g or {}).get("G_K1v2_分布一致性") or {}, (g or {}).get("G_K2v2_成本档预测") or {}
    P["O5_原始标注已落盘且面板=准入者=gates 面板"] = (raw is not None and adm == (g or {}).get("annotators")
                                            and set(adm) == {mm for mm in models0 if rec["by_model"][("dist", mm)]})
    P["O5_被剔除者零标注, 准入者每人标满样本"] = all(rec["by_model"][("dist", mm)] == (n_sample if mm in (adm or []) else 0)
                                           for mm in models0)
    P["O5_事实抽取每样本一次, 诊断 <= 1"] = rec["n"]["fact"] == n_sample and rec["n"]["diag"] <= 1
    P["O6_gates_result 字段齐"] = (g is not None and GK_KEYS <= set(g) and {"pass", "pairwise", "core_panel"} <= set(gk1)
                                and {"n", "pass"} <= set(gk2)
                                and set(g["★pass_components"]) == {"G_K1", "G_K2", "annotator_qualification"})
    P["O6_overall = G_K1 ∧ G_K2 ∧ 准入OK(G-K2 扣发则 None)"] = (g is not None and g.get("overall_pass") == (
        None if gk2.get("pass") is None else
        bool(gk1.get("pass") and gk2.get("pass") and (g.get("annotator_qualification") or {}).get("status") == "OK")))
    return P


def run(offline, mutator=None, fake_kw=None):
    """mutator / fake_kw: 只许离线(守卫测试的变异臂); mutator 同时作用于主臂与两条回放臂, fake_kw 选合成回复的形状。"""
    assert offline or (mutator is None and fake_kw is None)
    got = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if got != PREREG_SHA256:
        raise SystemExit("★ 预注册被改过(sha256 %s != 钉住的 %s) —— 拒跑" % (got[:16], PREREG_SHA256[:16]))
    bad = [k for k in STIMULUS_ENV if os.environ.get(k)]
    if bad:
        raise SystemExit("★ 预注册要求默认刺激, 但环境里设了 %s —— 拒跑" % bad)
    import calibration_framework as CF
    td = tempfile.mkdtemp(prefix="acc_e2e_real_")
    saved_log, CF.JSON_FAIL_LOG = CF.JSON_FAIL_LOG, os.path.join(td, "json_extract_failures.log")
    out = {"block": "ACCURACY_MAIN_E2E_REAL_RESULT", "prereg_sha256": got, "offline_dry_run": offline}
    try:
        if offline:
            import accuracy_main_e2e_offline as E
            fake = E.Fake(**(fake_kw or {}))
            m = AH.load(source_mutator=mutator, responses=fake, env={"CCE_SKIP_GK2": "0", "CCE_OUT_DIR": td})
            fake.m = m
            reserve = AH._memory_reserve()
        else:
            if not os.environ.get("MINIMAX_API_KEY"):
                print(json.dumps({"status": "BLOCKED_NO_KEY", "real_calls": 0}, ensure_ascii=False))
                sys.exit(3)
            os.environ["CCE_SKIP_GK2"], os.environ["CCE_OUT_DIR"] = "0", td
            sys.path.insert(0, str(ROOT / "accuracy"))
            import run_gates as m          # noqa: E402  (import 期读 key; 只在环境里)
            import cce_request_budget as B
            state = "/tmp/accuracy_main_e2e_real_budget.json" if os.environ.get("GITHUB_ACTIONS") else None  # 账本随 artifact 上传
            reserve = lambda a, l, n=1, note="": B.reserve(a, l, n, note, state=state)
        import cce_request_budget as B
        models0, n_sample, n_anchor = list(m.MODELS), len(m.SAMPLE), len(m.ANCHOR_TRUTH)
        rec = _instrument(m, reserve)
        rc, err, g, raw = _main_in(m, td)
    finally:
        CF.JSON_FAIL_LOG = saved_log
    recorded = rec["out"]
    out.update({"rc": rc, "exception": type(err).__name__ if err else None,
                "logical_calls": dict(sorted(rec["n"].items())), "http_attempts": rec["attempts"],
                "dist_calls_by_model": {mm: rec["by_model"][("dist", mm)] for mm in models0}})
    if isinstance(err, B.BudgetExceeded):
        out["verdict"] = "BUDGET_STOP"
        out["★budget_stop"] = "撞 %d 次硬上限: %s —— 编排判据不可判(INSUFFICIENT)" % (CAP, str(err)[:120])
        return out, recorded, g, raw
    P = properties(m, rec, rc, err, g, raw, models0, n_sample, n_anchor)
    rrc, rerr, rg, misses, trip = _replay(recorded, mutator=mutator)
    P["O7_离线回放: 零网络、零缺失、gates_result 逐字段相等"] = (trip == [] and misses == [] and rerr is None
                                                    and rrc == rc and rg == g)
    if rc != 2:
        brc, berr, bg, bmiss, btrip = _replay(recorded, blank_facts=True, mutator=mutator)
        bk2 = (bg or {}).get("G_K2v2_成本档预测") or {}
        P["O8_空抽取臂: 不崩、落盘、G-K2 n=0 扣发、overall=None"] = (
            btrip == [] and bmiss == [] and berr is None and bg is not None
            and bk2.get("n") == 0 and bk2.get("pass") is None and bool(bk2.get("★withheld")) and bg.get("overall_pass") is None)
    out["properties"] = P
    out["verdict"] = "ORCHESTRATION_PASS" if all(P.values()) else "ORCHESTRATION_FAIL"
    out["failed_properties"] = sorted(k for k, v in P.items() if not v)
    out["descriptive_only_not_adjudicated"] = None if g is None else {
        "annotators_admitted": (raw or {}).get("annotators"),
        "qualification": [(q["model"], "%d/%d" % (q["hits"], q["of"])) for q in (g.get("annotator_qualification") or {}).get("per_model", [])],
        "coverage": g.get("coverage"), "G_K1_pass": ((g.get("G_K1v2_分布一致性") or {}).get("pass")),
        "G_K2_pass": ((g.get("G_K2v2_成本档预测") or {}).get("pass")), "G_K2_n": ((g.get("G_K2v2_成本档预测") or {}).get("n")),
        "overall_pass": g.get("overall_pass")}
    return out, recorded, g, raw


if __name__ == "__main__":
    offline = "--offline" in sys.argv
    res, recorded, g, raw = run(offline)
    txt = json.dumps(res, ensure_ascii=False, indent=1) + "\n"
    if offline:
        print(txt)
        sys.exit(0)
    rtxt = json.dumps({"block": "ACCURACY_MAIN_E2E_REAL_REPLAY", "prereg_sha256": res["prereg_sha256"],
                       "★what": "key = sha256(model + NUL + prompt), out = call() 的返回值; 供离线回放 main()",
                       "calls": recorded}, ensure_ascii=False) + "\n"
    RESULT.write_text(txt, encoding="utf-8")
    REPLAY.write_text(rtxt, encoding="utf-8")
    print(txt)
    if os.environ.get("GITHUB_ACTIONS"):   # probe.yml 的 artifact 只收 /tmp/*.json
        for name, body in ((RESULT.name, txt), (REPLAY.name, rtxt),
                           ("accuracy_main_e2e_real_gates_result.json", json.dumps(g, ensure_ascii=False, indent=1) if g else None),
                           ("accuracy_main_e2e_real_raw_annotations.json", json.dumps(raw, ensure_ascii=False) if raw else None)):
            if body:
                pathlib.Path("/tmp", name).write_text(body, encoding="utf-8")
