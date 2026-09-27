# -*- coding: utf-8 -*-
"""Decider-2B 弃权原因 2×2 探针(候选顺序 × 候选语言)。预注册 tests/data/jev_decider_probe_prereg.json。零 API。

格子: 0 = 原序中文(复用 run 36272175531, archive/36272175531) · a = 反序中文 · b = 原序英文 · c = 反序英文(后三者 = 本次运行)。
同 42 条、同 line[:2000]、同 5 面、一题一行; 英文选择按合同 v3 译表一一映射回中文再比较。无金标: 不产出「谁更准」。
用法: python3 probes/jev_decider_probe.py archive/<probe_run_id>
"""
import collections, hashlib, importlib.util, json, math, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
PRE = ROOT / "tests/data/jev_decider_probe_prereg.json"
OUT = ROOT / "results/jev_decider_probe.json"
SUITE = ROOT / "experiments/jev/suites/s0-probe-v1.jsonl"
CELL0_SUITE = ROOT / "experiments/jev/suites/s0-compare-v1.jsonl"


def _load(rel, name):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


CMP = _load("probes/jev_decider_vs_retest.py", "_cmp_probe")      # 冻结的对比脚本: stats_pair / facet_verdict / cp / mcnemar / load_arms
RT, FACETS = CMP.RT, CMP.FACETS
CELLS = {"a": "rev-zh", "b": "orig-en", "c": "rev-en"}


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()


def _lse(xs):
    m = max(xs); return m + math.log(sum(math.exp(x - m) for x in xs))


def unk_logodds(row, unk_id):
    """z = l_unk − logsumexp(l_others), 用原始 logits(与温度无关)。"""
    ids, lg = row["candidate_ids"], row["raw_candidate_logits"]
    i = ids.index(unk_id)
    return lg[i] - _lse([l for j, l in enumerate(lg) if j != i])


def sign_test(xs):
    """精确双侧符号检验(零差不计)。"""
    pos, neg = sum(1 for x in xs if x > 0), sum(1 for x in xs if x < 0)
    return CMP.mcnemar_exact(pos, neg), pos, neg


def holm(pvals):
    """{key: p} → {key: 是否拒绝} (Holm, α=0.05)。"""
    order = sorted(pvals, key=pvals.get); m = len(order); rej = {}; stop = False
    for i, k in enumerate(order):
        if not stop and pvals[k] <= 0.05 / (m - i): rej[k] = True
        else: stop = True; rej[k] = False
    return rej


def _preds(run_dir):
    run_dir = pathlib.Path(run_dir)
    return [json.loads(l) for l in next(p for p in run_dir.iterdir() if p.name.endswith("predictions.jsonl")).read_text(encoding="utf-8").splitlines() if l.strip()], \
        json.loads(next(p for p in run_dir.iterdir() if p.name == "report.json").read_text(encoding="utf-8"))


def load_cells(probe_dir, cell0_dir, task):
    """→ {cell: {ptr: {facet: row(带 label_zh)}}}, 锚点行, 本次报告。"""
    from experiments.jev.compile_context import to_zh
    suite = [json.loads(l) for l in SUITE.read_text(encoding="utf-8").splitlines() if l.strip()]
    ptr_of = {it["item_id"]: "%s:%d" % (it["text_ref"]["file"], it["text_ref"]["line_index"]) for it in suite}
    cell0_suite = [json.loads(l) for l in CELL0_SUITE.read_text(encoding="utf-8").splitlines() if l.strip()]
    ptr0 = {it["item_id"]: "%s:%d" % (it["text_ref"]["file"], it["text_ref"]["line_index"]) for it in cell0_suite if "text_ref" in it and not it["item_id"].startswith("rep-")}
    preds, report = _preds(probe_dir)
    p0, _ = _preds(cell0_dir)
    cells = {k: {} for k in ("0", "a", "b", "c")}
    for p in p0:
        if p["item_id"] in ptr0:
            cells["0"].setdefault(ptr0[p["item_id"]], {})[p["question_id"]] = dict(p, label_zh=p["selected_candidate"])
    anchors = []
    for p in preds:
        prefix = p["item_id"].split(":", 1)[0]
        if prefix == "anchor": anchors.append(p); continue
        cell = next(k for k, v in CELLS.items() if v == prefix)
        cells[cell].setdefault(ptr_of[p["item_id"]], {})[p["question_id"]] = dict(p, label_zh=to_zh(task, p["question_id"], p["selected_candidate"]))
    return cells, anchors, p0, report, suite


def anchor_check(anchors, p0, tol):
    by = {p["identities"].get("row_sha256"): p for p in p0}
    out = {"rows": len(anchors), "matched": 0, "top1_diff": 0, "max_abs_dp": 0.0}
    for a in anchors:
        o = by.get(a["identities"].get("row_sha256"))
        if o is None: continue
        out["matched"] += 1; out["top1_diff"] += a["selected_candidate"] != o["selected_candidate"]
        out["max_abs_dp"] = max(out["max_abs_dp"], max(abs(x - y) for x, y in zip(a["probabilities"], o["probabilities"])))
    out["pass"] = out["rows"] > 0 and out["matched"] == out["rows"] and out["top1_diff"] == 0 and out["max_abs_dp"] <= tol
    out["max_abs_dp"] = float("%.3g" % out["max_abs_dp"])
    return out


def preflight(pre, report, suite, cells, task):
    from experiments.jev.compile_context import build_request, load_taxonomy
    errs = []
    if report.get("execution_status") != "SUCCEEDED": errs.append(f"execution_status {report.get('execution_status')}")
    if report.get("coverage_status") != "COMPLETE": errs.append(f"coverage_status {report.get('coverage_status')}")
    if report.get("suite_sha256") != sha(SUITE.read_bytes()): errs.append("报告 suite sha 与当前 suite 不符")
    if (report.get("suite_manifest") or {}).get("prereg_sha256") != sha(PRE.read_bytes()): errs.append("执行提交里的预注册 sha 与当前文件不符")
    if sha(json.dumps(task["translation_en"], ensure_ascii=False, sort_keys=True)) != pre["★冻结"]["译表 sha"]: errs.append("译表 sha 与预注册不符")
    eff = (report.get("identities") or {}).get("backend_effective") or {}
    if eff.get("temperature") != pre["★臂"]["T"]: errs.append("温度与预注册不符")
    tax = load_taxonomy()
    want, qsha = {}, {}
    for it in suite:
        prefix = it["item_id"].split(":", 1)[0]
        if prefix == "anchor": continue
        cell = next(k for k, v in CELLS.items() if v == prefix)
        ptr = "%s:%d" % (it["text_ref"]["file"], it["text_ref"]["line_index"])
        try:
            req = build_request(it, tax, task)[0]
        except Exception as e:  # noqa: BLE001
            errs.append(f"条目 {it['item_id']} 无法编译: {type(e).__name__}"); continue
        want[(cell, ptr)] = {q.question_id: q.candidate_ids() for q in req.questions}; qsha[(cell, ptr)] = req.questions_sha256()
    bad_order = bad_qsha = 0
    for c in ("a", "b", "c"):
        for ptr, facets in cells[c].items():
            for k, row in facets.items():
                w = want.get((c, ptr), {}).get(k)
                bad_order += w is None or list(row["candidate_ids"]) != w
                bad_qsha += row.get("questions_sha256") != qsha.get((c, ptr))
    if bad_order: errs.append(f"{bad_order} 行实际发出的候选与变体编译结果不符")
    if bad_qsha: errs.append(f"{bad_qsha} 行的 questions_sha256 与现算不符")
    for c in ("0", "a", "b", "c"):
        n = sum(len(v) for v in cells[c].values())
        if len(cells[c]) != 42 or n != 42 * len(pre["★面"]): errs.append(f"格子 {c} 行数 {n}(条目 {len(cells[c])})")
    return errs


def analyse(cells, arms, pre, task):
    from experiments.jev.compile_context import to_zh
    R = pre["★★★判决规则(测量前冻结)"]["数值"]; rules_cmp = json.loads(CMP.PRE.read_text(encoding="utf-8"))["★★★判决规则(测量前冻结)"]["数值"]
    ptrs = sorted(set(cells["0"]) & set(cells["a"]) & set(cells["b"]) & set(cells["c"]) & set(arms["J1"]))
    n = len(ptrs); out = {"n_items": n, "per_facet": {}}
    primary_p = {}
    for k in pre["★面"]:
        f = FACETS[k]; K = len({RT.norm(v, f) for v in f["values"]} | {"未知"})
        lab = {c: [RT.norm(cells[c][p][k]["label_zh"], f) for p in ptrs] for c in cells}
        J = {j: [RT.norm(arms[j][p].get(k), f) for p in ptrs] for j in ("J1", "J2")}
        row = {"labels_counts": {c: dict(sorted(collections.Counter(v).items())) for c, v in lab.items()}}
        U = {c: sum(1 for v in lab[c] if v == "未知") for c in lab}
        UJ = {j: sum(1 for v in J[j] if v == "未知") for j in J}
        row["unknown_count"] = {**U, **{f"J_{j}": UJ[j] for j in UJ}}
        if k == "触发事件":
            me = lambda v: v in ("未知", "无明显触发")
            row["merged_empty_count"] = {c: sum(1 for v in lab[c] if me(v)) for c in lab} | {f"J_{j}": sum(1 for v in J[j] if me(v)) for j in J}
        ind = (lambda v: v in ("未知", "无明显触发")) if k == "触发事件" else (lambda v: v == "未知")
        E0 = sum(ind(v) for v in lab["0"]) - sum(ind(v) for v in J["J1"])
        effects = {}
        for fac, c in (("position", "a"), ("language", "b")):
            b_ = sum(1 for x, y in zip(lab["0"], lab[c]) if ind(x) and not ind(y)); c_ = sum(1 for x, y in zip(lab["0"], lab[c]) if not ind(x) and ind(y))
            Ec = sum(ind(v) for v in lab[c]) - sum(ind(v) for v in J["J1"])
            effects[fac] = {"left_unknown": b_, "entered_unknown": c_, "p_exact": CMP.mcnemar_exact(b_, c_), "excess_cell0": E0, "excess_cell": Ec}
            if k in pre["★主要检验族"]["面"]: primary_p[(k, fac)] = effects[fac]["p_exact"]
        row["effects"] = effects
        row["order_sensitivity"] = {"zh d(0,a)": sum(x != y for x, y in zip(lab["0"], lab["a"])), "en d(b,c)": sum(x != y for x, y in zip(lab["b"], lab["c"])),
                                    "language d(0,b)": sum(x != y for x, y in zip(lab["0"], lab["b"]))}
        row["order_sensitivity"]["cp95"] = {kk: CMP.cp(v, n) for kk, v in list(row["order_sensitivity"].items())}
        cls = lambda d: "顺序不敏感" if d <= R["order_insensitive_max_d"] else "顺序敏感" if d >= R["order_sensitive_min_d"] else "有顺序影响但大小未定"
        row["order_sensitivity"]["class"] = {"zh": cls(row["order_sensitivity"]["zh d(0,a)"]), "en": cls(row["order_sensitivity"]["en d(b,c)"])}
        z = {}
        for c in cells:
            zs = []
            for p in ptrs:
                r = cells[c][p][k]; ids = r["candidate_ids"]
                uid = next(i for i in ids if to_zh(task, k, i) in ("未知", "未提及"))
                zs.append(unk_logodds(r, uid))
            z[c] = zs
        I = [(z["c"][i] - z["b"][i]) - (z["a"][i] - z["0"][i]) for i in range(n)]
        p_i, pos, neg = sign_test(I)
        dU_en = sum(ind(v) for v in lab["c"]) - sum(ind(v) for v in lab["b"]); dU_zh = sum(ind(v) for v in lab["a"]) - sum(ind(v) for v in lab["0"])
        row["interaction"] = {"sign_test_p": p_i, "pos": pos, "neg": neg, "dU_en": dU_en, "dU_zh": dU_zh,
                              "claimed": p_i < R["interaction_p"] and abs(dU_en - dU_zh) >= R["interaction_min_dU"]}
        row["mean_unknown_logodds"] = {c: round(sum(z[c]) / n, 3) for c in z}
        agree = {}
        for c in cells:
            for j in ("J1", "J2"):
                agree[f"{c}~{j}"] = sum(x == y for x, y in zip(lab[c], J[j]))
        row["agreement_with_jev"] = agree
        ver = {}
        for c in cells:
            dD = {j: sum(x != y for x, y in zip(lab[c], J[j])) for j in ("J1", "J2")}
            zero = {j: (n - max(collections.Counter(J[j]).values())) - dD[j] for j in ("J1", "J2")}
            hi = {}
            for j in ("J1", "J2"):
                kb = CMP.boot_kappa(lab[c], J[j], pre["★不确定性"]["bootstrap_B"], pre["★不确定性"]["seed"])["ci95"]; hi[j] = kb[1] if kb else None
            unm = any((n - max(collections.Counter(J[j]).values())) <= rules_cmp["unmeasurable_max_d0"] or max(collections.Counter(J[j]).values()) >= rules_cmp["unmeasurable_min_majority"] for j in ("J1", "J2"))
            ver[c] = {"d": dD, "net": zero, "verdict": CMP.facet_verdict({"unmeasurable": unm}, dD, zero, hi, rules_cmp), "exploratory": c != "0"}
        row["replaceability_per_cell"] = ver
        out["per_facet"][k] = row
    rej = holm({f"{k}|{fac}": p for (k, fac), p in primary_p.items()})
    for (k, fac) in primary_p:
        e = out["per_facet"][k]["effects"][fac]
        e["holm_reject"] = rej[f"{k}|{fac}"]
        if e["holm_reject"] and e["excess_cell"] <= e["excess_cell0"] / 2:
            e["attribution"] = "该因素可以解释多数过量弃权"
        elif e["p_exact"] > 0.05 and abs((e["excess_cell"] - e["excess_cell0"])) <= R["no_effect_max_dU"]:
            e["attribution"] = "该因素在可测尺度上不是原因"
        else:
            e["attribution"] = "有影响但大小未定或不足一半"
    out["holm_family"] = {f"{k}|{fac}": {"p": p, "reject": rej[f"{k}|{fac}"]} for (k, fac), p in primary_p.items()}
    return out


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    from experiments.jev.compile_context import load_task, load_taxonomy
    pre = json.loads(PRE.read_text(encoding="utf-8")); task = load_task("s0_context.v3", load_taxonomy())
    probe_dir = pathlib.Path(argv[0]); cell0_dir = ROOT / pre["★臂"]["格子 0 归档"]
    cells, anchors, p0, report, suite = load_cells(probe_dir, cell0_dir, task)
    anc = anchor_check(anchors, p0, pre["★确定性(前置)"]["tol_abs_dp"])
    errs = preflight(pre, report, suite, cells, task)
    ok = anc["pass"] and not errs
    res = analyse(cells, CMP.load_arms(), pre, task) if ok else {"n_items": None, "per_facet": {}, "holm_family": {}}
    doc = {"block": "JEV_DECIDER_PROBE_2X2", "prereg_sha256": sha(PRE.read_bytes()), "analysis_script_sha256": sha(pathlib.Path(__file__).read_bytes()),
           "analysis_script_sha256_at_freeze": pre["★分析脚本(冻结)"]["sha256"],
           "run": {"run_id": (report.get("identities") or {}).get("run", {}).get("GITHUB_RUN_ID"), "execution_commit": (report.get("identities") or {}).get("cce_execution_commit"),
                   "archive": str(probe_dir.resolve().relative_to(ROOT)) if probe_dir.resolve().is_relative_to(ROOT) else str(probe_dir),
                   "timing": report.get("timing"), "budget": {k: v for k, v in (report.get("budget") or {}).items() if k != "limits"}},
           "★前置": {"errors": errs, "锚点(跨 run)": anc, "pass": ok},
           **res, "★不得据此说": pre["★★★不得据此说"]}
    if not ok: doc["overall"] = "前置不成立(执行错误, 不出结论)"
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"preflight": doc["★前置"], "holm_family": doc.get("holm_family")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
