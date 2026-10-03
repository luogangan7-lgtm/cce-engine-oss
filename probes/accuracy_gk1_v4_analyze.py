#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G-K1 v4 分析器(零调用): 读 occasion 结果文件, 按 tests/data/gk1_v4_prereg.json 冻结的规则出判定。

用法: .venv/bin/python probes/accuracy_gk1_v4_analyze.py gk1_v4_occ1_result.json gk1_v4_occ2_result.json ...
      → 打印摘要, 写 tests/data/gk1_v4_result.json
★ 预注册 sha / 条目 sha / 面板 / k / 闸协议 与探针同一份常量; 完整性不符 ⇒ 拒收(报错停)。
★ k=3 平均只在 occasion 内做, 之后才进「条目 × occasion」交叉自助(抽样与界的实现与 v3 同一份代码)。
★ 有效 occasion 的挑选(替补、重复派发)按预注册 S3/S4 机械执行。少于 4 个有效 occasion: 只出描述。
"""
import collections, hashlib, itertools, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
import accuracy_gk1_v4_run as RUN  # noqa: E402  (只取常量; 不加载 run_gates, 不需要 key)
from accuracy_gk1_v3_analyze import js_div, top1, _mean, PAIR_FN, point, draws, boot, B_BOOT, SEED  # noqa: E402

P4 = list(RUN.MODELS)
THR, TOP2_THR, R_NEED, K = 0.25, 0.80, 4, RUN.K
OUT = ROOT / "tests/data/gk1_v4_result.json"
IDS = [x["id"] for x in json.loads(RUN.ITEMS.read_text(encoding="utf-8"))]


def kavg(samples):
    """occasion 内可解析采样分布的逐类算术平均; 全失败 ⇒ None。"""
    ds = [d for d in samples if d]
    if not ds:
        return None
    return {k: sum(d.get(k, 0.0) for d in ds) / len(ds) for k in set().union(*ds)}


def view(r, sample=None):
    """一个 occasion 的读数: sample=None ⇒ k 平均(主判); sample=s ⇒ 只取第 s 次采样(描述)。"""
    return {m: {i: kavg(r["dists"][m][i]) if sample is None else r["dists"][m][i][sample] for i in IDS} for m in P4}


# ── 完整性 / 有效性 / 挑选 ──────────────────────────────────────────────────
def _k_shape_ok(r):
    try:
        return r.get("k") == K and all(len(r["dists"][m][i]) == K for m in P4 for i in IDS)
    except (KeyError, TypeError):
        return False


def check_integrity(r, allow_offline=False):
    rp = r.get("run_params") or {}
    errs = [k for k, ok in (
        ("block", r.get("block") == "GK1_V4_OCCASION_RESULT"),
        ("prereg_sha256", r.get("prereg_sha256") == RUN.PREREG_SHA256),
        ("items_sha256", r.get("items_sha256") == RUN.ITEMS_SHA256),
        ("gate_protocol", (rp.get("gate_protocol_version"), rp.get("gate_protocol_hash")) == RUN.GATE_PROTOCOL),
        ("body_chars/unit", rp.get("CCE_BODY_CHARS") == 700 and rp.get("CCE_UNIT_LABEL") == "评论"),
        ("panel", r.get("panel") == P4),
        ("k", _k_shape_ok(r)),
        ("item_ids", r.get("item_ids") == IDS),
        ("occasion", r.get("occasion") in RUN.OCCASIONS),
        ("not_offline", allow_offline or r.get("offline_dry_run") is False)) if not ok]
    if errs:
        raise SystemExit("★ occasion 结果文件完整性不符 %s(occasion=%r) —— 拒收, 不当无效 occasion、不可替补"
                         % (errs, r.get("occasion")))


def invalid_reasons(r):
    """预注册 occasion_validity —— 现算, 不信文件里自报的 occasion_valid。"""
    out = [] if r.get("annotation_complete") is True else ["BUDGET_STOP during annotation"]
    for m in P4:
        c = sum(1 for i in IDS for d in r["dists"][m][i] if d)
        if c < RUN.MIN_SAMPLES:
            out.append("%s 可解析采样 %d/%d < %d" % (m, c, len(IDS) * K, RUN.MIN_SAMPLES))
    return out


def choose(results, allow_offline=False):
    """预注册 S3/S4: 同编号取最早; 1..4 有效者全用; 5 只填补 1..4 中已派发且无效的位置(最多 1 个)。"""
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
    reps = [k for k in (5,) if k in chosen and not bad[k]]
    used += reps[:n_bad]
    notes["unused_not_a_replacement"] = reps[n_bad:]
    return [chosen[k] for k in used], used, notes


# ── 格值 / 面板 ─────────────────────────────────────────────────────────────
def cell_matrix(views, fn):
    """N × R 矩阵: P4 各对 fn 的平均; 一对都没有 ⇒ None。views = 每个 occasion 一份 {m: {i: 读数}}。"""
    mat = []
    for i in IDS:
        row = []
        for v in views:
            x = [fn(v[m][i], v[n][i]) for m, n in itertools.combinations(P4, 2) if v[m][i] and v[n][i]]
            row.append(sum(x) / len(x) if x else None)
        mat.append(row)
    return mat


def panel_block(views, dr):
    mats = {k: cell_matrix(views, fn) for k, fn in PAIR_FN.items()}
    blk = {"members": P4, "k": K, "mu_D": point(mats["js"]), "top1_agreement": point(mats["top1"]),
           "top2_hit": point(mats["top2"]), "n_cells": sum(v is not None for row in mats["js"] for v in row),
           "per_occasion_mu_D": [_mean(row[j] for row in mats["js"] if row[j] is not None) for j in range(len(views))],
           "per_pair_mean_JS": {"%s~%s" % (m, n): _mean(js_div(v[m][i], v[n][i]) for v in views for i in IDS
                                                        if v[m][i] and v[n][i])
                                for m, n in itertools.combinations(P4, 2)}}
    if dr is not None:
        L, U = boot(mats["js"], dr)
        js_state = "PASS" if U <= THR else "FAIL" if L > THR else "UNRESOLVED"
        blk.update({"mu_D_L95_one_sided": L, "mu_D_U95_one_sided": U, "JS_three_state": js_state,
                    "top1_LCB95": boot(mats["top1"], dr)[0], "top2_LCB95_descriptive": boot(mats["top2"], dr)[0],
                    "top2_point_ge_0.80": blk["top2_hit"] >= TOP2_THR,
                    "verdict": "FAIL" if blk["top2_hit"] < TOP2_THR else js_state})
    return blk


def d1_block(occs, dr):
    """描述: 只取第 1 次采样(v3 式单次调用读数)。"""
    mat = cell_matrix([view(r, 0) for r in occs], js_div)
    out = {"mu_D": point(mat)}
    if dr is not None:
        out["L95_U95_one_sided"] = list(boot(mat, dr))
    return out


# ── G-R1(描述) ─────────────────────────────────────────────────────────────
def g_r1(occs):
    views = [view(r) for r in occs]
    out = {}
    for m in P4:
        jk, same, within, between = [], [], [], []
        for a, b in itertools.combinations(views, 2):
            for i in IDS:
                p, q = a[m][i], b[m][i]
                if p and q:
                    jk.append(js_div(p, q))
                    same.append(top1(p) == top1(q))
        for r in occs:
            for i in IDS:
                ss = r["dists"][m][i]
                within += [js_div(p, q) for p, q in itertools.combinations(ss, 2) if p and q]
        for a, b in itertools.combinations(occs, 2):
            for i in IDS:
                between += [js_div(p, q) for p, q in zip(a["dists"][m][i], b["dists"][m][i]) if p and q]
        w, bt = _mean(within), _mean(between)
        out[m] = {"W_m_k_between": _mean(jk), "top1_retest_k": _mean(same), "n_item_occasion_pairs": len(jk),
                  "W_within_single": w, "W_between_single": bt,
                  "within_over_between": w / bt if w is not None and bt else None}
    return out


def analyze(results, allow_offline=False):
    """allow_offline 只给守卫测试用(合成/干跑数据); CLI 不开放。"""
    occs, used, notes = choose(results, allow_offline)
    decide = len(occs) == R_NEED
    dr = draws(len(IDS), len(occs)) if decide else None
    b4 = panel_block([view(r) for r in occs], dr) if occs else {}
    out = {"block": "GK1_V4_ANALYSIS", "prereg_sha256": RUN.PREREG_SHA256, "★zero_api": True,
           "status": "ADJUDICATED" if decide else "DESCRIPTIVE_ONLY_FEWER_THAN_4_VALID_OCCASIONS",
           "occasions_used": used, "occasion_notes": notes,
           "bootstrap": {"B": B_BOOT, "seed": SEED, "scheme": "item x occasion crossed; k-average inside occasion"} if decide else None,
           "G_K1_v4_verdict": b4.get("verdict") if decide else None,
           "P4_k3": b4, "D1_single_sample_descriptive": d1_block(occs, dr) if occs else None,
           "partial_cells": {r["occasion"]: {m: sum(1 for i in IDS if 0 < sum(1 for d in r["dists"][m][i] if d) < K)
                                             for m in P4} for r in occs},
           "G_R1_descriptive": g_r1(occs) if len(occs) >= 2 else None}
    if out["G_R1_descriptive"]:
        out["k_average_effective"] = all((g["within_over_between"] or 0) >= 0.75 for g in out["G_R1_descriptive"].values())
    if decide:
        g, d1 = out["G_R1_descriptive"], out["D1_single_sample_descriptive"]["mu_D"]
        out["prediction_outcomes"] = {
            "Pr1_PASS": b4["verdict"] == "PASS",
            "Pr2_mu_D_k3_in_0.13_0.20": 0.13 <= b4["mu_D"] <= 0.20,
            "Pr3_D1_in_0.22_0.29_and_gap_gt_0.05": 0.22 <= d1 <= 0.29 and d1 - b4["mu_D"] > 0.05,
            "Pr4_top2_ge_0.80": b4["top2_hit"] >= TOP2_THR,
            "Pr5_within_over_between_ge_0.75_all": out["k_average_effective"],
            "Pr6_M3_lowest_W_k": min(g, key=lambda m: g[m]["W_m_k_between"]) == "MiniMax-M3",
            "Pr7_four_planned_occasions_valid": used == [1, 2, 3, 4] and not notes["invalid"]}
    return out


if __name__ == "__main__":
    paths = [pathlib.Path(p) for p in sys.argv[1:]]
    if not paths:
        raise SystemExit("用法: accuracy_gk1_v4_analyze.py <gk1_v4_occ*_result.json> ...")
    res = analyze([json.loads(p.read_text(encoding="utf-8")) for p in paths])
    res["inputs"] = [{"file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("status", "occasions_used", "occasion_notes", "G_K1_v4_verdict")}, ensure_ascii=False, indent=1))
    print("P4_k3", {x: res["P4_k3"].get(x) for x in ("mu_D", "mu_D_L95_one_sided", "mu_D_U95_one_sided", "top2_hit", "verdict")})
    print("D1_single_sample", res["D1_single_sample_descriptive"])
    print("写入", OUT.relative_to(ROOT))
