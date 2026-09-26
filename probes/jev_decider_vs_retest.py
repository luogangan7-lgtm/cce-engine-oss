# -*- coding: utf-8 -*-
"""Decider-2B vs TypeSafe Jev vs MiniMax —— 同题同切片无金标对比(预注册 tests/data/jev_decider_vs_retest_prereg.json)。零 API。

输入: 一次 cce-jev-eval 运行的归档(archive/<run_id>/: cce-item..predictions / report) + results/s0_jev_shadow.json(轮1) + results/s0_retest.json(轮2)。
主判据 = 换读者改变率 d(D,J_r)/42(Clopper-Pearson 95%), 两轮 Jev 各算一次; κ 只作伴随量(偏斜分布下 κ 会失真)。
没有金标: 任何一臂都不是真值; 本脚本不产出「谁更准」。产物只有标签计数/统计量/指针, 无原文。
用法: python3 probes/jev_decider_vs_retest.py archive/<run_id>
"""
import collections, hashlib, importlib.util, json, math, pathlib, random, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
PRE = ROOT / "tests/data/jev_decider_vs_retest_prereg.json"
OUT = ROOT / "results/jev_decider_vs_retest.json"
SUITE = ROOT / "experiments/jev/suites/s0-compare-v1.jsonl"
R1, R2 = ROOT / "results/s0_jev_shadow.json", ROOT / "results/s0_retest.json"


def _load(rel, name):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


RT = _load("probes/s0_retest.py", "_rt_cmp")                      # norm / kappa_multi / STRUCT_OK / shadow.READABLE —— 与复测同一实现
CP = _load("probes/real_corpus_pilot_prereg.py", "_cp_cmp").clopper_pearson
FACETS = {f["key"]: f for f in RT.shadow.READABLE}


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()


def cp(k, n):
    lo, hi = CP(k, n); return [round(lo, 4), round(hi, 4)]


def stats_pair(xs, ys, K):
    """一对读数的全部伴随量: po / pe / κ / PABAK / κmax / 多数份额。"""
    n = len(xs); k = RT.kappa_multi(xs, ys)
    po, pe = k["po"], k["pe"]
    px, py = collections.Counter(xs), collections.Counter(ys)
    pmin = sum(min(px[c], py[c]) / n for c in set(xs) | set(ys))
    kmax = None if pe >= 1 else round((pmin - pe) / (1 - pe), 4)
    return {"d": sum(1 for x, y in zip(xs, ys) if x != y), "po": po, "pe": pe, "kappa": k["kappa"],
            "pabak": round((K * po - 1) / (K - 1), 4) if K > 1 else None, "kappa_max": kmax,
            "majority_share_a": round(max(px.values()) / n, 4), "majority_share_b": round(max(py.values()) / n, 4),
            "paradox_flag": pe >= 0.6}


def boot_kappa(xs, ys, B, seed):
    """条目级配对自助: 同一组下标重抽; pe=1 的退化重抽丢弃并计数。"""
    rng = random.Random(seed); n = len(xs); vals, dropped = [], 0
    for _ in range(B):
        idx = [rng.randrange(n) for _ in range(n)]
        k = RT.kappa_multi([xs[i] for i in idx], [ys[i] for i in idx])["kappa"]
        if k is None: dropped += 1
        else: vals.append(k)
    vals.sort()
    if not vals: return {"ci95": None, "dropped": dropped}
    q = lambda p: vals[min(len(vals) - 1, max(0, int(round(p * (len(vals) - 1)))))]
    return {"ci95": [round(q(0.025), 4), round(q(0.975), 4)], "dropped": dropped}


def mcnemar_exact(b, c):
    """精确 McNemar(双侧): 不一致对 b(D 已知 & J 未知) vs c(D 未知 & J 已知)。"""
    n = b + c
    if n == 0: return 1.0
    k = min(b, c); p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return round(min(1.0, 2 * p), 4)


def load_arms():
    """{ptr: {面: 原始标签}} × {J1,J2,M1,M2}; 两轮按 ptr 配对。"""
    r1, r2 = json.loads(R1.read_text(encoding="utf-8")), json.loads(R2.read_text(encoding="utf-8"))
    arms = {}
    for tag, r in (("1", r1), ("2", r2)):
        arms["J" + tag] = {row["ptr"]: row["jev"] for row in r["rows"] if row.get("jev_ok")}
        arms["M" + tag] = {row["ptr"]: row["mm"] for row in r["rows"] if row.get("mm_ok")}
    return arms


def load_decider(run_dir):
    """归档 run 目录 → ({ptr: {面: 标签}}, {ptr: {面: 概率表}}, 行元数据列表, report)。只取 42 条主条目(非 rep-/非 smoke)。"""
    run_dir = pathlib.Path(run_dir)
    pred_f = next(p for p in run_dir.iterdir() if p.name.endswith("predictions.jsonl"))
    rep_f = next(p for p in run_dir.iterdir() if p.name.endswith("__report.json") or p.name == "report.json")
    preds = [json.loads(l) for l in pred_f.read_text(encoding="utf-8").splitlines() if l.strip()]
    report = json.loads(rep_f.read_text(encoding="utf-8"))
    suite = [json.loads(l) for l in SUITE.read_text(encoding="utf-8").splitlines() if l.strip()]
    ptr_of = {it["item_id"]: "%s:%d" % (it["text_ref"]["file"], it["text_ref"]["line_index"]) for it in suite if "text_ref" in it}
    D, P = {}, {}
    for p in preds:
        iid = p["item_id"]
        if iid not in ptr_of or iid.startswith("rep-"): continue
        ptr = ptr_of[iid]
        D.setdefault(ptr, {})[p["question_id"]] = p["selected_candidate"]
        P.setdefault(ptr, {})[p["question_id"]] = dict(zip(p["candidate_ids"], p["probabilities"]))
    return D, P, preds, report, suite, ptr_of


def determinism(preds, suite, ptr_of, prior_preds, tol, expected_pairs=None):
    """① 同 run 复跑: rep-X 与 X 同一行 sha ⇒ top-1 同且 max|Δp| ≤ tol。② 跨 run: smoke 行与前一 run 同一 row_sha256 ⇒ 同上(描述量)。"""
    by = {(p["item_id"], p["question_id"]): p for p in preds}
    within = {"pairs": 0, "top1_diff": 0, "max_abs_dp": 0.0, "row_sha_mismatch": 0}
    for (iid, q), p in by.items():
        if not iid.startswith("rep-"): continue
        o = by.get((iid[4:], q))
        if o is None: within["missing"] = within.get("missing", 0) + 1; continue
        within["pairs"] += 1
        if p["identities"].get("row_sha256") != o["identities"].get("row_sha256"): within["row_sha_mismatch"] += 1
        within["top1_diff"] += p["selected_candidate"] != o["selected_candidate"]
        within["max_abs_dp"] = max(within["max_abs_dp"], max(abs(a - b) for a, b in zip(p["probabilities"], o["probabilities"])))
    within["expected_pairs"] = expected_pairs
    within["pass"] = (within["pairs"] > 0 and within["top1_diff"] == 0 and within["max_abs_dp"] <= tol and within["row_sha_mismatch"] == 0
                      and not within.get("missing") and (expected_pairs is None or within["pairs"] == expected_pairs))
    cross = {"pairs": 0, "top1_diff": 0, "max_abs_dp": 0.0}
    prior = {p["identities"].get("row_sha256"): p for p in (prior_preds or [])}
    for p in preds:
        o = prior.get(p["identities"].get("row_sha256"))
        if o is None or p["item_id"] in ptr_of: continue
        cross["pairs"] += 1; cross["top1_diff"] += p["selected_candidate"] != o["selected_candidate"]
        cross["max_abs_dp"] = max(cross["max_abs_dp"], max(abs(a - b) for a, b in zip(p["probabilities"], o["probabilities"])))
    cross["bitwise_within_tol"] = cross["pairs"] > 0 and cross["top1_diff"] == 0 and cross["max_abs_dp"] <= tol
    within["max_abs_dp"] = float("%.3g" % within["max_abs_dp"]); cross["max_abs_dp"] = float("%.3g" % cross["max_abs_dp"])
    return within, cross


def facet_verdict(fk, dD, net, kboot_hi, rules):
    """dD = {J1: d, J2: d}; net = {J1: net gain, J2: ...}。规则全部来自预注册, 不在这里调。"""
    r = rules
    if fk["unmeasurable"]: return "测不出"
    if all(dD[j] <= r["replaceable_max_d"] for j in dD) and all(net[j] > 0 for j in net): return "可替代"
    if all(dD[j] >= r["different_min_d"] for j in dD) and all(h is not None and h < r["different_kappa_hi"] for h in kboot_hi.values()): return "不同读者"
    return "不可判"


def analyse(D, P, arms, pre, determinism_block=None):
    rules = pre["★★★判决规则(测量前冻结)"]["数值"]
    B, seed = pre["★不确定性"]["bootstrap_B"], pre["★不确定性"]["seed"]
    ptrs = sorted(set(D) & set(arms["J1"]) & set(arms["J2"]) & set(arms["M1"]) & set(arms["M2"]))
    out = {"n_items": len(ptrs), "per_facet": {}}
    for k in pre["★面"]["模型读"]:
        f = FACETS[k]; K = len({RT.norm(v, f) for v in f["values"]} | {"未知"})          # 归一化后的类别数(未提及 并入 未知)
        rd = {a: [RT.norm(arms[a][p].get(k), f) for p in ptrs] for a in ("J1", "J2", "M1", "M2")}
        rd["D"] = [RT.norm(D[p].get(k), f) for p in ptrs]
        n = len(ptrs); row = {"labels_counts": {a: dict(sorted(collections.Counter(v).items())) for a, v in rd.items()}}
        pairs = {}
        for a, b in (("D", "J1"), ("D", "J2"), ("J1", "J2"), ("D", "M1"), ("D", "M2"), ("M1", "M2"), ("J1", "M1"), ("J2", "M2")):
            s = stats_pair(rd[a], rd[b], K); s["change_rate_cp95"] = cp(s["d"], n)
            s["kappa_boot"] = boot_kappa(rd[a], rd[b], B, seed) if a == "D" or (a, b) == ("J1", "J2") else None
            pairs[f"{a}~{b}"] = s
        row["pairs"] = pairs
        zero = {}
        for j in ("J1", "J2"):
            c = collections.Counter(rd[j]); d0 = n - max(c.values())
            zero[j] = {"d0_constant_majority": d0, "majority_label": c.most_common(1)[0][0], "majority_count": max(c.values()),
                       "net_gain": d0 - pairs[f"D~{j}"]["d"]}
        row["zero_baseline"] = zero
        unm = any(zero[j]["d0_constant_majority"] <= rules["unmeasurable_max_d0"] or zero[j]["majority_count"] >= rules["unmeasurable_min_majority"] for j in zero)
        row["unmeasurable"] = unm
        unk = {}
        for a in ("D", "J1", "J2", "M1", "M2"):
            u = sum(1 for v in rd[a] if v == "未知"); unk[a] = {"n_unknown": u, "rate_cp95": cp(u, n)}
        for j in ("J1", "J2"):
            b = sum(1 for x, y in zip(rd["D"], rd[j]) if x != "未知" and y == "未知"); c = sum(1 for x, y in zip(rd["D"], rd[j]) if x == "未知" and y != "未知")
            unk[f"D_vs_{j}_mcnemar"] = {"D_known_J_unknown": b, "D_unknown_J_known": c, "p_exact": mcnemar_exact(b, c)}
        row["unknown_selection"] = unk
        if k == "触发事件":                                     # 预注册敏感性: 无明显触发 并入 未知
            m = lambda v: "未知" if v == "无明显触发" else v
            row["sensitivity_无明显触发并入未知"] = {f"D~{j}": sum(1 for x, y in zip(rd["D"], rd[j]) if m(x) != m(y)) for j in ("J1", "J2")}
        desc = {}
        for j in ("J1", "J2", "M1", "M2"):
            mass = [P[p][k].get(arms[j][p].get(k), 0.0) if arms[j][p].get(k) in P[p][k] else 0.0 for p in ptrs]
            top2 = [arms[j][p].get(k) in sorted(P[p][k], key=P[p][k].get, reverse=True)[:2] for p in ptrs]
            desc[j] = {"mean_p_D_on_arm_label": round(sum(mass) / n, 4), "arm_label_in_D_top2": sum(top2)}
        desc["mean_entropy_D_nats"] = round(sum(-sum(v * math.log(v) for v in P[p][k].values() if v > 0) for p in ptrs) / n, 4)
        row["decider_descriptives"] = desc
        if determinism_block is not None and not determinism_block.get("pass", False):
            row["verdict"] = None                                       # 前置不成立: 不出任何面判决
            out["per_facet"][k] = row
            continue
        dD = {j: pairs[f"D~{j}"]["d"] for j in ("J1", "J2")}
        net = {j: zero[j]["net_gain"] for j in ("J1", "J2")}
        hi = {j: (pairs[f"D~{j}"]["kappa_boot"]["ci95"] or [None, None])[1] for j in ("J1", "J2")}
        row["verdict"] = facet_verdict(row, dD, net, hi, rules)
        if row["verdict"] == "可替代" and any(pairs[f"D~{j}"]["kappa"] is not None and pairs[f"D~{j}"]["kappa"] < rules["replaceable_kappa_flag_below"] for j in ("J1", "J2")):
            row["kappa_paradox_flag"] = True
        out["per_facet"][k] = row
    struct = {}
    sk = pre["★面"]["结构判定"]
    for a in ("J1", "J2", "M1", "M2"):
        v = sum(1 for p in ptrs if RT.norm(arms[a][p].get(sk), FACETS[sk]) not in RT.STRUCT_OK); struct[a] = {"violations": v, "cp95": cp(v, len(ptrs))}
    struct["D"] = "n/a —— 合同 v2 不让模型读 情绪余温(结构判定 首轮无余温)"
    out["情绪余温_structural"] = struct
    verdicts = {k: r["verdict"] for k, r in out["per_facet"].items()}
    if determinism_block is not None and not determinism_block.get("pass", False):
        out["verdicts"] = {k: None for k in verdicts}; out["overall"] = "前置不成立(执行错误, 不出判决)"
        return out
    meas = [k for k, v in verdicts.items() if v != "测不出"]
    ok_pre = determinism_block is None or determinism_block.get("pass", False)
    if not ok_pre:
        overall = "前置不成立(执行错误, 不出判决)"
    elif len(meas) < 3:
        overall = "不可判(可测面 < 3)"
    elif any(verdicts[k] == "不同读者" for k in meas):
        overall = "整体不可替代: 不同读者面 = " + "、".join(k for k in meas if verdicts[k] == "不同读者")
    elif all(verdicts[k] == "可替代" for k in meas):
        overall = "5 个可读面上换成 Decider 的读数改变率每面 ≤ ~23%(CP95 上界), 仍需 owner 点头才接生产"
    else:
        overall = "部分: " + "; ".join(f"{k}={v}" for k, v in verdicts.items())
    out["verdicts"] = verdicts; out["overall"] = overall
    return out


def preflight(pre, report, suite, preds):
    """前置条件(任何一条不成立 = 执行错误, 不出判决): 题目逐面 sha · 实际发出的候选顺序与题目 sha · 切片 · 输入集 · 42×5 行 · 执行成功 · 预注册 sha 在执行提交里。"""
    import importlib
    errs = []
    if report.get("execution_status") != "SUCCEEDED": errs.append(f"execution_status {report.get('execution_status')}")
    if report.get("suite_sha256") != sha(SUITE.read_bytes()): errs.append("报告的 suite sha 与当前 suite 文件不符")
    sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT))
    cq = importlib.import_module("cce_s0_jev").jev_questions(list(FACETS.values()))
    want = pre["★输入与题目(冻结)"]["题目逐面 sha(含候选顺序)"]
    for k, h in want.items():
        if sha(json.dumps(cq[k], ensure_ascii=False)) != h: errs.append(f"题目 {k} sha 与预注册不符")
    items = [it for it in suite if "text_ref" in it and not it["item_id"].startswith("rep-")]
    iset = sha(json.dumps([[it["text_ref"]["file"], it["text_ref"]["line_index"], it["text_ref"]["line_sha256"]] for it in items], ensure_ascii=False))
    if iset != pre["★输入与题目(冻结)"]["输入集 sha"]: errs.append("输入集 sha 与预注册不符")
    if any(it["preparation_id"] != "text_2000.v0" for it in items): errs.append("对比条目切片不是 text_2000.v0")
    from experiments.jev.compile_context import build_request, load_task, load_taxonomy
    from experiments.jev.contracts import JevError
    tax = load_taxonomy(); task = load_task("s0_context.v2", tax)
    qsha = {}
    for it in items:
        try:
            qsha[it["item_id"]] = build_request(it, tax, task)[0].questions_sha256()
        except JevError as e:                                   # 条目本身编不出来 = 前置不成立, 记错误码不崩
            errs.append(f"条目 {it['item_id']} 无法编译: {e.code}")
            qsha[it["item_id"]] = None
    main_ids = set(qsha)
    bad_order = bad_qsha = 0
    for p in preds:
        if p["item_id"] not in main_ids: continue
        bad_order += list(p["candidate_ids"]) != list(cq[p["question_id"]]["criteria"])
        bad_qsha += p.get("questions_sha256") != qsha[p["item_id"]]
    if bad_order: errs.append(f"{bad_order} 行实际发出的候选顺序与生产 jev_questions 不同")
    if bad_qsha: errs.append(f"{bad_qsha} 行的 questions_sha256 与现算不符")
    if (report.get("suite_manifest") or {}).get("prereg_sha256") != sha(PRE.read_bytes()): errs.append("执行提交里的预注册 sha 与当前文件不符(预注册被改过)")
    ok_rows = {(p["item_id"], p["question_id"]) for p in preds if not p["item_id"].startswith("rep-")}
    need = {(it["item_id"], k) for it in items for k in pre["★面"]["模型读"]}
    if need - ok_rows: errs.append(f"对比行缺 {len(need - ok_rows)} 行")
    if report.get("coverage_status") != "COMPLETE": errs.append(f"coverage_status {report.get('coverage_status')}")
    eff = (report.get("identities") or {}).get("backend_effective") or {}
    if eff.get("temperature") != pre["★臂"]["D"]["T"]: errs.append("D 的温度与预注册不符")
    return errs


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    run_dir = pathlib.Path(argv[0]); pre = json.loads(PRE.read_text(encoding="utf-8"))
    D, P, preds, report, suite, ptr_of = load_decider(run_dir)
    prior = pre["★确定性(前置)"]["跨 run 对照"]["run_dir"]
    prior_preds = [json.loads(l) for l in next(p for p in (ROOT / prior).iterdir() if p.name.endswith("predictions.jsonl")).read_text(encoding="utf-8").splitlines() if l.strip()]
    n_rep = sum(1 for it in suite if it["item_id"].startswith("rep-"))
    within, cross = determinism(preds, suite, ptr_of, prior_preds, pre["★确定性(前置)"]["tol_abs_dp"], expected_pairs=n_rep * len(pre["★面"]["模型读"]))
    errs = preflight(pre, report, suite, preds)
    within["pass"] = within["pass"] and not errs
    if within["pass"]:
        res = analyse(D, P, load_arms(), pre, within)
    else:                                                   # 前置不成立: 不算任何面(缺行时也不会崩)
        res = {"n_items": None, "per_facet": {}, "情绪余温_structural": None, "verdicts": {k: None for k in pre["★面"]["模型读"]}, "overall": "前置不成立(执行错误, 不出判决)"}
    doc = {"block": "JEV_DECIDER_VS_RETEST", "prereg_sha256": sha(PRE.read_bytes()), "analysis_script_sha256": sha(pathlib.Path(__file__).read_bytes()),
           "analysis_script_sha256_at_freeze": pre["★分析脚本(冻结)"]["sha256"],
           "run": {"run_id": report.get("identities", {}).get("run", {}).get("GITHUB_RUN_ID"), "execution_commit": report.get("identities", {}).get("cce_execution_commit"),
                   "archive": str(run_dir.resolve().relative_to(ROOT)) if run_dir.resolve().is_relative_to(ROOT) else str(run_dir), "execution_status": report.get("execution_status"),
                   "timing": report.get("timing"), "budget": {k: v for k, v in (report.get("budget") or {}).items() if k != "limits"}},
           "★前置": {"errors": errs, "同 run 复跑": within, "跨 run(smoke 行 vs 前一 run)": cross},
           **res, "★不得据此说": pre["★★★不得据此说"]}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"overall": doc["overall"], "verdicts": doc.get("verdicts"), "preflight_errors": errs, "within": within, "cross": cross}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
