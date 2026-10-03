#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G-K1 v3 分析器(零调用): 读 occasion 结果文件, 按 tests/data/gk1_v3_prereg.json 冻结的规则出判定。

用法: .venv/bin/python probes/accuracy_gk1_v3_analyze.py gk1_v3_occ1_result.json gk1_v3_occ2_result.json ...
      → 打印摘要, 写 tests/data/gk1_v3_result.json
★ 预注册 sha / 新条目 sha / 面板 / 闸协议 与探针同一份常量(probes/accuracy_gk1_v3_run.py); 完整性不符 ⇒ 拒收(报错停)。
★ 有效 occasion 的挑选(替补、重复派发)按预注册 S3/S4 机械执行, 不给人选择余地。
★ 少于 4 个有效 occasion: 只出描述(点估计、G-R1), 不出判定、不出自助界。
"""
import collections, hashlib, itertools, json, math, pathlib, random, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
import accuracy_gk1_v3_run as RUN  # noqa: E402  (只取常量; 不加载 run_gates, 不需要 key)

P5 = list(RUN.MODELS)
P4 = P5[:4]
E = "MiniMax-Text-01"
THR, TOP2_THR, R_NEED = 0.25, 0.80, 4
B_BOOT, SEED = 10000, 20261003
OUT = ROOT / "tests/data/gk1_v3_result.json"
IDS = [x["id"] for x in json.loads(RUN.FRESH.read_text(encoding="utf-8"))]


def js_div(p, q):   # 与 accuracy/run_gates.js_div 同式(不 import: 那个模块 import 时就要 MINIMAX_API_KEY); 守卫测试逐值比对
    keys = set(p) | set(q)
    m = {k: (p.get(k, 0) + q.get(k, 0)) / 2 for k in keys}
    def kl(a, b):
        return sum(a[k] * math.log2(a[k] / b[k]) for k in keys if a.get(k, 0) > 0 and b.get(k, 0) > 0)
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def top1(p):
    return max(p, key=p.get)


def top2(p):
    return sorted(p, key=p.get, reverse=True)[:2]


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


PAIR_FN = {"js": js_div,
           "top1": lambda p, q: float(top1(p) == top1(q)),
           "top2": lambda p, q: float(top1(p) in top2(q) or top1(q) in top2(p))}


# ── 完整性 / 有效性 / 挑选 ──────────────────────────────────────────────────
def check_integrity(r, allow_offline=False):
    rp = r.get("run_params") or {}
    errs = [k for k, ok in (
        ("block", r.get("block") == "GK1_V3_OCCASION_RESULT"),
        ("prereg_sha256", r.get("prereg_sha256") == RUN.PREREG_SHA256),
        ("fresh81_sha256", r.get("fresh81_sha256") == RUN.FRESH_SHA256),
        ("gate_protocol", (rp.get("gate_protocol_version"), rp.get("gate_protocol_hash")) == RUN.GATE_PROTOCOL),
        ("body_chars/unit", rp.get("CCE_BODY_CHARS") == 700 and rp.get("CCE_UNIT_LABEL") == "评论"),
        ("panel", r.get("panel") == P5),
        ("item_ids", r.get("item_ids") == IDS),
        ("occasion", r.get("occasion") in RUN.OCCASIONS),
        ("not_offline", allow_offline or r.get("offline_dry_run") is False)) if not ok]
    if errs:
        raise SystemExit("★ occasion 结果文件完整性不符 %s(occasion=%r) —— 拒收, 不当无效 occasion、不可替补"
                         % (errs, r.get("occasion")))


def invalid_reasons(r):
    """预注册 occasion_validity —— 现算, 不信文件里自报的 occasion_valid。"""
    out = [] if r.get("annotation_complete") is True else ["BUDGET_STOP during annotation"]
    for m in P5:
        c = sum(1 for i in IDS if (r["dists"].get(m) or {}).get(i))
        if c < RUN.MIN_COVERAGE:
            out.append("%s 可解析分布 %d/81 < %d" % (m, c, RUN.MIN_COVERAGE))
    return out


def choose(results, allow_offline=False):
    """预注册 S3/S4: 同编号取最早; 1..4 有效者全用; 5,6 只按编号顺序填补 1..4 中已派发且无效的位置。"""
    for r in results:
        check_integrity(r, allow_offline)
    by = collections.defaultdict(list)
    for r in results:
        by[r["occasion"]].append(r)
    chosen, notes = {}, {"ignored_duplicate": [], "invalid": {}, "unused_not_a_replacement": []}
    for k in sorted(by):
        rs = sorted(by[k], key=lambda r: r["started_at_utc"])
        chosen[k] = rs[0]
        notes["ignored_duplicate"] += [{"occasion": k, "github_run_id": r.get("github_run_id"),
                                        "started_at_utc": r["started_at_utc"]} for r in rs[1:]]
    bad = {k: invalid_reasons(r) for k, r in chosen.items()}
    notes["invalid"] = {k: v for k, v in bad.items() if v}
    used = [k for k in (1, 2, 3, 4) if k in chosen and not bad[k]]
    n_bad = sum(1 for k in (1, 2, 3, 4) if k in chosen and bad[k])
    reps = [k for k in (5, 6) if k in chosen and not bad[k]]
    used += reps[:n_bad]
    notes["unused_not_a_replacement"] = reps[n_bad:]
    return [chosen[k] for k in used], used, notes


# ── 格值 / 交叉自助 ─────────────────────────────────────────────────────────
def cell_matrix(occs, panel, fn):
    """N × R 矩阵: 面板内各对 fn 的平均; 一对都没有 ⇒ None。"""
    mat = []
    for i in IDS:
        row = []
        for r in occs:
            d = r["dists"]
            v = [fn(d[m][i], d[n][i]) for m, n in itertools.combinations(panel, 2) if d[m].get(i) and d[n].get(i)]
            row.append(sum(v) / len(v) if v else None)
        mat.append(row)
    return mat


def point(mat):
    return _mean(v for row in mat for v in row if v is not None)


def draws(n, r):
    """预注册 bootstrap: 先抽 R 个运行(有放回), 再抽 N 个条目(有放回); 同一串用于全部指标与面板。"""
    rng = random.Random(SEED)
    out = []
    for _ in range(B_BOOT):
        rr = rng.choices(range(r), k=r)
        ii = rng.choices(range(n), k=n)
        out.append((tuple(rr.count(j) for j in range(r)), ii))
    return out


def boot(mat, dr):
    """返回 (L, U) = (xs[500], xs[9499]) —— 单侧 95% 下/上界(B=10000)。"""
    cache, xs = {}, []
    for c, ii in dr:
        if c not in cache:
            cache[c] = ([sum(c[j] * v for j, v in enumerate(row) if v is not None) for row in mat],
                        [sum(c[j] for j, v in enumerate(row) if v is not None) for row in mat])
        num, den = cache[c]
        dn = sum(map(den.__getitem__, ii))
        if dn:
            xs.append(sum(map(num.__getitem__, ii)) / dn)
    xs.sort()
    return xs[int(0.05 * len(xs))], xs[int(0.95 * len(xs)) - 1]


def panel_block(occs, panel, dr):
    mats = {k: cell_matrix(occs, panel, fn) for k, fn in PAIR_FN.items()}
    blk = {"members": panel, "mu_D": point(mats["js"]), "top1_agreement": point(mats["top1"]),
           "top2_hit": point(mats["top2"]), "n_cells": sum(v is not None for row in mats["js"] for v in row),
           "per_occasion_mu_D": [_mean(row[j] for row in mats["js"] if row[j] is not None) for j in range(len(occs))],
           "per_pair_mean_JS": {"%s~%s" % (m, n): _mean(js_div(r["dists"][m][i], r["dists"][n][i]) for r in occs for i in IDS
                                                        if r["dists"][m].get(i) and r["dists"][n].get(i))
                                for m, n in itertools.combinations(panel, 2)}}
    if dr is not None:
        L, U = boot(mats["js"], dr)
        js_state = "PASS" if U <= THR else "FAIL" if L > THR else "UNRESOLVED"
        blk.update({"mu_D_L95_one_sided": L, "mu_D_U95_one_sided": U, "JS_three_state": js_state,
                    "top1_LCB95": boot(mats["top1"], dr)[0], "top2_LCB95_descriptive": boot(mats["top2"], dr)[0],
                    "top2_point_ge_0.80": blk["top2_hit"] >= TOP2_THR,
                    "verdict": "FAIL" if blk["top2_hit"] < TOP2_THR else js_state})
    return blk, mats["js"]


# ── G-R1 / Text-01 样本外复核 ────────────────────────────────────────────────
def g_r1(occs):
    out = {}
    for m in P5:
        js, same = [], []
        for a, b in itertools.combinations(occs, 2):
            for i in IDS:
                p, q = a["dists"][m].get(i), b["dists"][m].get(i)
                if p and q:
                    js.append(js_div(p, q))
                    same.append(top1(p) == top1(q))
        out[m] = {"W_m": _mean(js), "top1_retest": _mean(same), "n_item_occasion_pairs": len(js)}
    return out


def onehot_rates(r):
    d = r["dists"]
    return {m: _mean(_mean(float(top1(d[m][i]) != top1(d[o][i])) for i in IDS if d[m].get(i) and d[o].get(i))
                     for o in P5 if o != m) for m in P5}


def consensus(d, i):
    c = collections.Counter(top1(d[o][i]) for o in P4 if d[o].get(i)).most_common()
    return c[0][0] if c and (len(c) == 1 or c[0][1] > c[1][1]) else None


def text01(occs, decide):
    per = [onehot_rates(r) for r in occs]
    cm = collections.Counter()
    for r in occs:
        d = r["dists"]
        for i in IDS:
            k = consensus(d, i)
            if k and d[E].get(i) and top1(d[E][i]) != k:
                cm["%s->%s" % (k, top1(d[E][i]))] += 1
    n_dis = sum(cm.values())
    out = {"T1_onehot_disagreement_per_occasion": per,
           "T2_directed_confusion_pooled": dict(cm.most_common()), "T2_n_disagreements": n_dis,
           "T2_boundary_share": (cm["display->pain_seek"] + cm["display->audit"] + cm["pain_seek->audit"]) / n_dis if n_dis else None}
    if decide:
        mx = [max(v for m, v in p.items() if m != E) for p in per]
        n_rep = sum(p[E] > x + 0.05 for p, x in zip(per, mx))
        n_not = sum(p[E] <= x for p, x in zip(per, mx))
        counts = sorted(cm.values(), reverse=True)
        c1 = bool(counts) and cm["display->pain_seek"] > 0 and cm["display->pain_seek"] == counts[0]
        c2 = bool(counts) and cm["pain_seek->audit"] > 0 and cm["pain_seek->audit"] >= counts[min(2, len(counts) - 1)]
        out.update({"T1_occasions_E_above_max_plus_0.05": n_rep, "T1_occasions_E_not_above_max": n_not,
                    "T1_verdict": "REPLICATED" if n_rep >= 3 else "NOT_REPLICATED" if n_not >= 3 else "MIXED",
                    "T2_c1_display_to_pain_seek_is_top": c1, "T2_c2_pain_seek_to_audit_in_top3": c2,
                    "T2_verdict": "DIRECTION_REPLICATED" if c1 and c2 else "PARTIAL" if c1 or c2 else "NOT_REPLICATED"})
    return out


def analyze(results, allow_offline=False):
    """allow_offline 只给守卫测试用(合成/干跑数据); CLI 不开放。"""
    occs, used, notes = choose(results, allow_offline)
    decide = len(occs) == R_NEED
    dr = draws(len(IDS), len(occs)) if decide else None
    b4, js4 = panel_block(occs, P4, dr) if occs else ({}, None)
    b5, js5 = panel_block(occs, P5, dr) if occs else ({}, None)
    out = {"block": "GK1_V3_ANALYSIS", "prereg_sha256": RUN.PREREG_SHA256, "★zero_api": True,
           "status": "ADJUDICATED" if decide else "DESCRIPTIVE_ONLY_FEWER_THAN_4_VALID_OCCASIONS",
           "occasions_used": used, "occasion_notes": notes,
           "bootstrap": {"B": B_BOOT, "seed": SEED, "scheme": "item x occasion crossed"} if decide else None,
           "G_K1_v3_verdict_P4": b4.get("verdict") if decide else None,
           "P4_primary": b4, "P5_comparison_only": b5,
           "G_R1_descriptive": g_r1(occs) if len(occs) >= 2 else None,
           "text01_out_of_sample": text01(occs, decide) if occs else None,
           "qualification_descriptive": {r["occasion"]: {m: (q or {}).get("state") for m, q in
                                                         (r.get("qualification_descriptive_only") or {}).items()}
                                         for r in occs}}
    if occs:
        diff = [[None if a is None or b is None else b - a for a, b in zip(r4, r5)] for r4, r5 in zip(js4, js5)]
        out["P5_minus_P4"] = {"mean": point(diff)}
        if decide:
            out["P5_minus_P4"]["xs500_xs9499"] = list(boot(diff, dr))
    if decide:
        t, g = out["text01_out_of_sample"], out["G_R1_descriptive"]
        out["prediction_outcomes"] = {
            "Pr1_P4_PASS": b4["verdict"] == "PASS", "Pr2_P5_UNRESOLVED": b5["verdict"] == "UNRESOLVED",
            "Pr3_P5_minus_P4_above_0": out["P5_minus_P4"]["xs500_xs9499"][0] > 0,
            "Pr4_top2_both_ge_0.80": b4["top2_hit"] >= TOP2_THR and b5["top2_hit"] >= TOP2_THR,
            "Pr5_T1_REPLICATED": t["T1_verdict"] == "REPLICATED",
            "Pr6_T2_at_least_PARTIAL": t["T2_verdict"] != "NOT_REPLICATED",
            "Pr7_M3_lowest_W": min(g, key=lambda m: g[m]["W_m"]) == "MiniMax-M3",
            "Pr8_four_planned_occasions_valid": used == [1, 2, 3, 4] and not notes["invalid"]}
    return out


if __name__ == "__main__":
    paths = [pathlib.Path(p) for p in sys.argv[1:]]
    if not paths:
        raise SystemExit("用法: accuracy_gk1_v3_analyze.py <gk1_v3_occ*_result.json> ...")
    res = analyze([json.loads(p.read_text(encoding="utf-8")) for p in paths])
    res["inputs"] = [{"file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("status", "occasions_used", "occasion_notes", "G_K1_v3_verdict_P4")}, ensure_ascii=False, indent=1))
    for k in ("P4_primary", "P5_comparison_only"):
        print(k, {x: res[k].get(x) for x in ("mu_D", "mu_D_L95_one_sided", "mu_D_U95_one_sided", "top2_hit", "verdict")})
    print("写入", OUT.relative_to(ROOT))
