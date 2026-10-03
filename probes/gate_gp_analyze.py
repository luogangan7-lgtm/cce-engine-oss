#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G-P 分析器(零调用): 读各分片的派发结果文件, 按 tests/data/gate_gp_prereg.json 冻结的规则拼槽、出 (a)(b)(c) 与总判。

用法: .venv/bin/python probes/gate_gp_analyze.py gate_gp_M3_r1_s1_result.json ... gate_gp_M2_r2_s2_result.json
      → 打印摘要, 写 tests/data/gate_gp_result.json
★ 预注册 sha / 条目 sha / 分片条目 / context / k / n / 成员 / 仪器 与探针同一份常量; 完整性不符 ⇒ 拒收(报错停), 不当无效片。
★ 同一 (成员, 运行) 的分片 1 + 分片 2 都有效才拼成 86 条的槽(按条目文件顺序); 缺一片 ⇒ 该槽不成立。
★ (a) 用生产自己的 binom_upper 出精确单侧界; (b)(c) 用 v3/v4 同一份「条目 × 运行」交叉自助(draws / boot)。
★ 分片的挑选、有效性、替补上限按预注册 validity 机械执行。槽不全 ⇒ 对应项 UNRESOLVED(INSUFFICIENT_SLOTS)。
"""
import collections, itertools, json, math, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "scripts"))
import gate_gp_run as RUN                                                     # noqa: E402  常量与仪器现算
from accuracy_gk1_v3_analyze import draws, boot, B_BOOT, SEED, _mean          # noqa: E402  v3/v4 同一份自助
from cce_knot_classify import binom_upper                                     # noqa: E402  生产自己的精确界

THR_A, THR_BC = 0.875, 0.80
MEMBERS, OTHERS, PROD = list(RUN.PANEL), ["M2.5", "M2.7", "M2"], "M3"
SLOTS = [(m, r) for r in RUN.RUNS for m in MEMBERS]
MAX_RESULTS = 18                                                              # 16 片 + 至多 2 次替补
OUT = ROOT / "tests/data/gate_gp_result.json"
IDS = [x["id"] for x in json.loads(RUN.ITEMS.read_text(encoding="utf-8"))]
SHARD_IDS = {s: RUN.shard_items(IDS, s) for s in RUN.SHARDS}


def state(L, U, thr):
    return "PASS" if L >= thr else "FAIL" if U < thr else "UNRESOLVED"


def cp_bounds(x, n):
    """x/n 的单侧 95% 精确下/上界(Clopper–Pearson), 全用生产的 binom_upper。"""
    return 1.0 - binom_upper(n - x, n), binom_upper(x, n)


# ── 完整性 / 有效性 / 挑选 ──────────────────────────────────────────────────
def check_integrity(r, prod_mm, allow_offline=False):
    m, ro, sid = r.get("member"), r.get("readouts") or [], SHARD_IDS.get(r.get("shard"))
    errs = [k for k, ok in (
        ("block", r.get("block") == "GATE_GP_DISPATCH_RESULT"),
        ("prereg_sha256", r.get("prereg_sha256") == RUN.PREREG_SHA256),
        ("items_sha256", r.get("items_sha256") == RUN.ITEMS_SHA256),
        ("shard/item_ids", sid is not None and r.get("item_ids") == sid and [x.get("id") for x in ro] == sid),
        ("member", m in RUN.PANEL and r.get("api_model") == RUN.PANEL.get(m)),
        ("run", r.get("run") in RUN.RUNS),
        ("context/k/n", (r.get("context"), r.get("k"), r.get("knot_n")) == (RUN.CONTEXT, RUN.K_S1, 5)),
        ("instrument", r.get("spec_minus_model_sha") == prod_mm and
         ((r.get("instrument_hash") == RUN.PROD_HASH) == (m == PROD))),
        # s1 弃权的读数由生产记成 s1_pairing="n/a(s1_abstained)", 仪器 hash 本来就不同 ⇒ 只核出了 top-1 的读数
        ("readout_instrument", all(x.get("instrument_hash") == r.get("instrument_hash")
                                   for x in ro if x.get("status") == "OK" and x.get("value") != "NONE")),
        ("production_publication", m != PROD or all(x["published_rule_Q"] == (x["value"] != "NONE")
                                                    for x in ro if x.get("status") == "OK")),
        ("not_offline", allow_offline or r.get("offline_dry_run") is False)) if not ok]
    if errs:
        raise SystemExit("★ 结果文件完整性不符 %s(成员=%r 运行=%r 分片=%r) —— 拒收, 不当无效片、不可替补"
                         % (errs, m, r.get("run"), r.get("shard")))


def invalid_reasons(r):
    """预注册 validity.dispatch_valid_iff(每片)—— 现算, 不信文件自报的 dispatch_valid。"""
    cov = sum(1 for x in r["readouts"] if x.get("status") == "OK")
    return (["BUDGET_STOP"] if r.get("budget_stop") is not False else []) + \
           (["coverage %d/%d < %d" % (cov, len(r["readouts"]), RUN.MIN_COVERAGE)] if cov < RUN.MIN_COVERAGE else [])


def assemble(parts):
    """同一 (成员, 运行) 的两片按条目文件顺序拼成一个槽。"""
    p1, p2 = parts[1], parts[2]
    errs = collections.Counter()
    for p in (p1, p2):
        errs.update(p.get("http_errors_by_model_and_code") or {})
    return {"member": p1["member"], "run": p1["run"], "instrument_hash": p1["instrument_hash"],
            "readouts": p1["readouts"] + p2["readouts"],
            "http_attempts": sum(p.get("http_attempts") or 0 for p in (p1, p2)),
            "http_errors_by_model_and_code": dict(sorted(errs.items())),
            "started_at_utc": min(p1["started_at_utc"], p2["started_at_utc"]),
            "parts": [{"shard": s, "github_run_id": parts[s].get("github_run_id"),
                       "started_at_utc": parts[s]["started_at_utc"]} for s in RUN.SHARDS]}


def choose(results, allow_offline=False):
    """每个 (成员, 运行, 分片) 按 started_at 取最早的有效那份; 两片齐才拼成槽。结果总数 > 18 ⇒ 拒收(超出预算授权)。"""
    if len(results) > MAX_RESULTS:
        raise SystemExit("★ 结果文件 %d 份 > %d(16 片 + 2 次替补)—— 超出预算授权, 拒收" % (len(results), MAX_RESULTS))
    prod_mm = RUN.spec_minus_model_sha(RUN._spec(PROD))
    for r in results:
        check_integrity(r, prod_mm, allow_offline)
    by = collections.defaultdict(list)
    for r in results:
        by[(r["member"], r["run"], r["shard"])].append(r)
    picked, notes = {}, {"invalid": {}, "unused": [], "incomplete_slots": []}
    for key, rs in by.items():
        for r in sorted(rs, key=lambda r: r["started_at_utc"]):
            bad = invalid_reasons(r)
            if bad:
                notes["invalid"].setdefault("%s_r%d_s%d" % key, []).append({"started_at_utc": r["started_at_utc"], "why": bad})
            elif key not in picked:
                picked[key] = r
            else:
                notes["unused"].append({"shard": "%s_r%d_s%d" % key, "started_at_utc": r["started_at_utc"]})
    chosen = {}
    for m, r in SLOTS:
        parts = {s: picked[(m, r, s)] for s in RUN.SHARDS if (m, r, s) in picked}
        if len(parts) == len(RUN.SHARDS):
            chosen[(m, r)] = assemble(parts)
        elif parts:
            notes["incomplete_slots"].append({"slot": "%s_r%d" % (m, r), "valid_shards": sorted(parts)})
    return chosen, notes


# ── 判定 ────────────────────────────────────────────────────────────────────
def values(chosen):
    """{(成员, 运行): {条目: 取值 | None(MISSING)}}; 槽缺 ⇒ 整槽 None。"""
    return {s: ({x["id"]: (x["value"] if x.get("status") == "OK" else None) for x in chosen[s]["readouts"]}
                if s in chosen else {i: None for i in IDS}) for s in SLOTS}


def consensus(vals):
    """留一共识: 非 MISSING 的其他成员 >= 2 名且某取值票数 >= 2。"""
    v = [x for x in vals if x is not None]
    if len(v) < 2:
        return None
    top, c = collections.Counter(v).most_common(1)[0]
    return top if c >= 2 else None


def matrices(V):
    b, c = [], []
    for i in IDS:
        rb, rc = [], []
        for r in RUN.RUNS:
            p, cons = V[(PROD, r)][i], consensus([V[(m, r)][i] for m in OTHERS])
            rb.append(float(p == cons) if p is not None and cons is not None else None)
            pr = [float(V[(m, r)][i] == V[(n, r)][i]) for m, n in itertools.combinations(MEMBERS, 2)
                  if V[(m, r)][i] is not None and V[(n, r)][i] is not None]
            rc.append(sum(pr) / len(pr) if pr else None)
        b.append(rb)
        c.append(rc)
    return b, c


def point(mat):
    return _mean(v for row in mat for v in row if v is not None)


def judge(chosen):
    V = values(chosen)
    have_a = all((PROD, r) in chosen for r in RUN.RUNS)
    have_all = all(s in chosen for s in SLOTS)
    pairs = [(V[(PROD, 1)][i], V[(PROD, 2)][i]) for i in IDS]
    pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
    n, X = len(pairs), sum(x == y for x, y in pairs)
    a = {"estimand": "两次独立生产读数 top1_mode 相同的概率(条目平均)", "threshold": THR_A, "n_pairs": n, "agree": X,
         "point": X / n if n else None}
    if have_a and n:
        L, U = cp_bounds(X, n)
        a.update({"L95_one_sided": L, "U95_one_sided": U, "verdict": state(L, U, THR_A)})
    else:
        a["verdict"] = "UNRESOLVED"
        a["why"] = "INSUFFICIENT_SLOTS" if not have_a else "没有可配对的条目"
    mb, mc = matrices(V)
    b = {"estimand": "生产 top1_mode == 留一面板共识(M2.5/M2.7/M2 多数)| 共识存在", "threshold": THR_BC,
         "point": point(mb), "n_cells": sum(v is not None for row in mb for v in row)}
    c = {"estimand": "四成员两两 top1_mode 相等(同运行同条目)", "threshold": THR_BC,
         "point": point(mc), "n_cells": sum(v is not None for row in mc for v in row)}
    if have_all and b["n_cells"] and c["n_cells"]:
        dr = draws(len(IDS), len(RUN.RUNS))
        for blk, mat in ((b, mb), (c, mc)):
            L, U = boot(mat, dr)
            blk.update({"L95_one_sided": L, "U95_one_sided": U, "verdict": state(L, U, THR_BC)})
    else:
        for blk in (b, c):
            blk.update({"verdict": "UNRESOLVED", "why": "INSUFFICIENT_SLOTS" if not have_all else "没有可用格"})
    b["reported_as"] = "REFERENCE_INCOHERENT" if c["verdict"] == "FAIL" else b["verdict"]
    vs = [a["verdict"], b["verdict"], c["verdict"]]
    overall = "FAIL" if "FAIL" in vs else "PASS" if all(v == "PASS" for v in vs) else "UNRESOLVED"
    return {"a_production_rerun_stability": a, "b_production_vs_panel_consensus": b,
            "c_panel_self_consistency": c, "overall": overall, "descriptive": describe(chosen, V)}


def describe(chosen, V):
    """只出描述, 不进判定。"""
    d = {"per_slot": {}, "member_rerun_agreement": {}, "pair_agreement": {}, "knots0_ne_top1_mode": {}, "rule_U": {}}
    for s, r in chosen.items():
        ro = r["readouts"]
        ok = [x for x in ro if x.get("status") == "OK"]
        d["per_slot"]["%s_r%d" % s] = {
            "coverage": len(ok), "none": sum(x["value"] == "NONE" for x in ok),
            "missing_why": dict(collections.Counter(x.get("why", "").split(":")[0] for x in ro if x.get("status") != "OK")),
            "http_attempts": r.get("http_attempts"), "http_errors": r.get("http_errors_by_model_and_code"),
            "rule_U_available": sum(x.get("published_rule_U") is True for x in ok)}
        keys = [x for x in ok if x["value"] != "NONE"]
        d["knots0_ne_top1_mode"]["%s_r%d" % s] = [sum(x["knots0"] != x["top1_mode"] for x in keys), len(keys)]
    for m in MEMBERS:
        pr = [(V[(m, 1)][i], V[(m, 2)][i]) for i in IDS if V[(m, 1)][i] is not None and V[(m, 2)][i] is not None]
        d["member_rerun_agreement"][m] = [sum(x == y for x, y in pr), len(pr)]
    for m, n in itertools.combinations(MEMBERS, 2):
        pr = [V[(m, r)][i] == V[(n, r)][i] for r in RUN.RUNS for i in IDS
              if V[(m, r)][i] is not None and V[(n, r)][i] is not None]
        d["pair_agreement"]["%s~%s" % (m, n)] = [sum(pr), len(pr)]
    cells = [(V[(PROD, r)][i], consensus([V[(m, r)][i] for m in OTHERS])) for r in RUN.RUNS for i in IDS
             if V[(PROD, r)][i] is not None]
    d["consensus_available"] = [sum(c is not None for _, c in cells), len(cells)]
    d["b_conservative_no_consensus_counts_as_disagree"] = [sum(p == c for p, c in cells if c is not None), len(cells)]
    U = {s: {x["id"]: x.get("rule_U") for x in chosen[s]["readouts"] if x.get("status") == "OK"} for s in chosen}
    if all((PROD, r) in U for r in RUN.RUNS):
        cnt = collections.Counter()
        for i in IDS:
            x, y = U[(PROD, 1)].get(i), U[(PROD, 2)].get(i)
            if x is None or y is None:
                continue
            w = (x == "WITHHELD") + (y == "WITHHELD")
            cnt["both_withheld" if w == 2 else "one_withheld" if w == 1 else "published_same" if x == y else "published_different"] += 1
        d["rule_U"]["production_reruns"] = dict(cnt)
    agree = [U[(PROD, r)][i] == consensus([V[(m, r)][i] for m in OTHERS]) for r in RUN.RUNS if (PROD, r) in U
             for i in IDS if U[(PROD, r)].get(i) not in (None, "WITHHELD")
             and consensus([V[(m, r)][i] for m in OTHERS]) is not None]
    d["rule_U"]["production_published_vs_consensus"] = [sum(agree), len(agree)]
    return d


# ── 功效(只作功效; 预注册 power 段由此现算) ────────────────────────────────
def power_a(n, p, thr=THR_A):
    xf = max((x for x in range(n + 1) if binom_upper(x, n) < thr), default=-1)
    xp = min((x for x in range(n + 1) if 1.0 - binom_upper(n - x, n) >= thr), default=n + 1)
    pmf = [math.comb(n, x) * p ** x * (1 - p) ** (n - x) for x in range(n + 1)]
    pf, pp = sum(pmf[:xf + 1]), sum(pmf[xp:])
    return {"PASS": round(pp, 4), "FAIL": round(pf, 4), "UNRESOLVED": round(1 - pp - pf, 4), "fail_le": xf, "pass_ge": xp}


def design_spec():
    """designs/gate_gp_2026-10-03.json 的内容(守卫测试比对文件 == 本函数)。"""
    return {"★what": "tests/data/gate_gp_prereg.json 的设计门规格(2026-10-03)。G-P: 面板成员(model, 类别 4 水平: M3=生产 / M2.5 / M2.7 / M2)"
                     " × 运行(run, 类别 2 水平) × 同一批 86 条新条目(accuracy/data/gate_gp_fresh86.json; 2026-10-03 owner 调用前修订 40 → 86)。"
                     "每个 (成员, 运行) 拆成 2 个分片派发(各 43 条, 经 GP_MODEL / GP_RUN / GP_SHARD 传入), 分析器拼回; 分片只是运维拆分, 不是因子。"
                     "每行 = 一次生产读数(s1 k=3 + s2 n=5, 名义 8 次 HTTP), 不是一次调用。"
                     "run 效应在生产成员内 = (a) 重跑一致; model 效应 = (c) 面板分歧, (b) 是同一 model 对比的留一形式(不另占自由度)。"
                     "实验单位 = 条目(86); 交叉自助同时重采样条目与运行。",
            "prereg": "tests/data/gate_gp_prereg.json",
            "variables": {"primitive": ["model", "run"], "derived": {}, "categorical": ["model", "run"]},
            "estimands": [{"name": "production_rerun_agreement", "target": "run", "nuisance": ["model"]},
                          {"name": "panel_top1_agreement", "target": "model", "nuisance": ["run"]},
                          {"name": "production_vs_loo_consensus", "target": "model", "nuisance": ["run"], "independent": False}],
            "analysis_formula": {"terms": ["model", "run"]},
            "design": [{"model": mi, "run": ri} for ri in range(len(RUN.RUNS)) for mi in range(len(MEMBERS)) for _ in IDS],
            "n_raw_observations": len(MEMBERS) * len(RUN.RUNS) * len(IDS), "n_experimental_units": len(IDS),
            "claimed_inferential_n": len(IDS), "nominal_http_per_row": RUN.NOMINAL_PER_READOUT,
            "shards_per_member_run": len(RUN.SHARDS), "items_per_shard": RUN.SHARD_SIZE,
            "calls_per_dispatch_planned": RUN.PLANNED, "per_dispatch_hard_cap": RUN.CAP,
            "dispatches_planned": len(MEMBERS) * len(RUN.RUNS) * len(RUN.SHARDS)}


def main(argv):
    allow_offline = "--allow-offline" in argv
    files = [a for a in argv if not a.startswith("--")]
    results = [json.loads(pathlib.Path(f).read_text(encoding="utf-8")) for f in files]
    chosen, notes = choose(results, allow_offline)
    res = judge(chosen)
    res = {"block": "GATE_GP_RESULT", "prereg_sha256": RUN.PREREG_SHA256, "items_sha256": RUN.ITEMS_SHA256,
           "slots_used": {"%s_r%d" % s: r["parts"] for s, r in sorted(chosen.items())},
           "slot_notes": notes, "bootstrap": {"B": B_BOOT, "seed": SEED}, **res}
    print(json.dumps({k: res[k] for k in ("overall", "slots_used")}, ensure_ascii=False, indent=1))
    for k in ("a_production_rerun_stability", "b_production_vs_panel_consensus", "c_panel_self_consistency"):
        print(k, {x: res[k].get(x) for x in ("point", "L95_one_sided", "U95_one_sided", "verdict")})
    if not allow_offline:
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("写入", OUT)
    return res


if __name__ == "__main__":
    main(sys.argv[1:])
