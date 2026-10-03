#!/usr/bin/env python3
"""零调用诊断: 真实端到端(run 36871132945, 2026-10-01) G-K1 为什么没过。

对照对象 = 2026-09-09 闸协议 v2 启用验收(PASS, mean_JS 0.2422)。两次都是同一闸协议、同 81 条、同 5 名
标注者、同截断; 原始逐条分布都已落盘, 所以可以零调用逐对、逐人、逐条拆开看。
  A = 09-09: /Volumes/data/cce-identified-vault/cce_runs/gate_v2_acceptance/raw_annotations.json(识别层, 只读)
  B = 10-01: archive/36871132945/probe-out__tmp__accuracy_main_e2e_real_raw_annotations.json
输出只含数字与化名条目 id(与 accuracy/data/corpus.json 同一套), 不含正文。
用法: .venv/bin/python probes/gk1_fail_diagnosis.py   → tests/data/gk1_fail_diagnosis_2026-10-03.json
"""
import collections, hashlib, itertools, json, math, os, random, statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A_PATH = "/Volumes/data/cce-identified-vault/cce_runs/gate_v2_acceptance/raw_annotations.json"
A_GATES = "/Volumes/data/cce-identified-vault/cce_runs/gate_v2_acceptance/gates_result.json"
B_PATH = os.path.join(ROOT, "archive/36871132945/probe-out__tmp__accuracy_main_e2e_real_raw_annotations.json")
B_GATES = os.path.join(ROOT, "archive/36871132945/probe-out__tmp__accuracy_main_e2e_real_gates_result.json")
OUT = os.path.join(ROOT, "tests/data/gk1_fail_diagnosis_2026-10-03.json")
THR = 0.25
B_BOOT, SEED = 2000, 20261003


def js_div(p, q):   # 与 accuracy/run_gates.js_div 逐字同式(不 import: 那个模块 import 时就要 MINIMAX_API_KEY)
    keys = set(p) | set(q)
    m = {k: (p.get(k, 0) + q.get(k, 0)) / 2 for k in keys}
    def kl(a, b):
        return sum(a[k] * math.log2(a[k] / b[k]) for k in keys if a.get(k, 0) > 0 and b.get(k, 0) > 0)
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def pair_js(d, models, ids):
    """{pair: {item: js}}, 只取两人都有分布的条目(与 run_gates 同口径)。"""
    out = {}
    for a, b in itertools.combinations(models, 2):
        out[f"{a}~{b}"] = {i: js_div(d[a][i], d[b][i]) for i in ids if d[a].get(i) and d[b].get(i)}
    return out


def panel_mean(pj, keep, ids=None):
    vals = []
    for k, per in pj.items():
        if all(m in keep for m in k.split("~")):
            xs = [per[i] for i in (ids if ids is not None else per) if i in per]
            if xs:
                vals.append(sum(xs) / len(xs))
    return sum(vals) / len(vals)


def outlier_rule(pj, models):
    lo = {m: statistics.mean(sum(per.values()) / len(per) for k, per in pj.items() if m in k.split("~"))
          for m in models}
    vals = sorted(lo.values())
    med = statistics.median(vals)
    sd = statistics.stdev(vals)          # run_gates 用 n-1
    return lo, med + 2 * sd


def boot(fn, ids, rng):
    xs = []
    for _ in range(B_BOOT):
        s = [rng.choice(ids) for _ in ids]
        xs.append(fn(s))
    xs.sort()
    return [round(xs[int(0.025 * B_BOOT)], 4), round(xs[int(0.975 * B_BOOT) - 1], 4)], round(sum(x > THR for x in xs) / B_BOOT, 3)


def main():
    A, B = json.load(open(A_PATH)), json.load(open(B_PATH))
    GA, GB = json.load(open(A_GATES)), json.load(open(B_GATES))
    models = A["annotators"]
    assert models == B["annotators"] and A["sample_ids"] == B["sample_ids"], "两次运行面板/条目不同 ⇒ 不可比, 停"
    ids = A["sample_ids"]
    da, db = A["dists"], B["dists"]
    pa, pb = pair_js(da, models, ids), pair_js(db, models, ids)

    # ① 仪器自检: 重算必须复现两份 gates_result 的落盘值, 否则下面的拆解没有意义
    rep = {"A_recomputed": round(panel_mean(pa, models), 4), "A_stored": GA["G_K1v2_分布一致性"]["mean_JS"],
           "B_recomputed": round(panel_mean(pb, models), 4), "B_stored": GB["G_K1v2_分布一致性"]["mean_JS"]}
    assert rep["A_recomputed"] == rep["A_stored"] and rep["B_recomputed"] == rep["B_stored"], rep

    comparable = {k: (A["run_params"].get(k), B["run_params"].get(k))
                  for k in ("gate_protocol_version", "gate_protocol_hash", "CCE_BODY_CHARS", "CCE_UNIT_LABEL",
                            "CCE_CORPUS", "annotators_actually_used")}

    # ② 逐对 / 逐人
    pairs = {k: {"A_0909": round(sum(pa[k].values()) / len(pa[k]), 4),
                 "B_1001": round(sum(pb[k].values()) / len(pb[k]), 4)} for k in pa}
    for k, v in pairs.items():
        v["delta"] = round(v["B_1001"] - v["A_0909"], 4)
    loA, cutA = outlier_rule(pa, models)
    loB, cutB = outlier_rule(pb, models)
    per_annot = {m: {"A_mean_JS_vs_others": round(loA[m], 4), "B_mean_JS_vs_others": round(loB[m], 4),
                     "delta": round(loB[m] - loA[m], 4)} for m in models}
    t01 = "MiniMax-Text-01"
    delta_total = sum(v["delta"] for v in pairs.values()) / len(pairs)
    delta_t01 = sum(v["delta"] for k, v in pairs.items() if t01 in k) / len(pairs)

    # ③ 同一模型跨运行的自身分布漂移(同条目, 09-09 vs 10-01) —— 运行间噪声有多大
    self_drift = {}
    for m in models:
        xs = [js_div(da[m][i], db[m][i]) for i in ids if da[m].get(i) and db[m].get(i)]
        top_same = sum(max(da[m][i], key=da[m][i].get) == max(db[m][i], key=db[m][i].get)
                       for i in ids if da[m].get(i) and db[m].get(i))
        self_drift[m] = {"mean_JS_run_vs_run": round(sum(xs) / len(xs), 4), "top1_same": f"{top_same}/{len(xs)}"}

    # ④ 留一标注者
    loo = {m: {"A": round(panel_mean(pa, [x for x in models if x != m]), 4),
               "B": round(panel_mean(pb, [x for x in models if x != m]), 4)} for m in models}

    # ⑤ 条目聚类自助: 各自 CI、越线频率、配对差
    rng = random.Random(SEED)
    ciA, pA = boot(lambda s: panel_mean(pa, models, s), ids, rng)
    ciB, pB = boot(lambda s: panel_mean(pb, models, s), ids, rng)
    diffs = []
    for _ in range(B_BOOT):
        s = [rng.choice(ids) for _ in ids]
        diffs.append(panel_mean(pb, models, s) - panel_mean(pa, models, s))
    diffs.sort()
    ci_diff = [round(diffs[int(0.025 * B_BOOT)], 4), round(diffs[int(0.975 * B_BOOT) - 1], 4)]

    # ⑥ 条目层: 增量集中在哪些条目 / 哪类结(按两次运行面板众数 top1)
    def item_mean(pj, i):
        xs = [per[i] for per in pj.values() if i in per]
        return sum(xs) / len(xs)
    def modal(d, i):
        c = collections.Counter(max(d[m][i], key=d[m][i].get) for m in models if d[m].get(i))
        return c.most_common(1)[0][0]
    item_delta = sorted(((round(item_mean(pb, i) - item_mean(pa, i), 4), i, modal(da, i), modal(db, i)) for i in ids),
                        reverse=True)
    by_knot = collections.defaultdict(list)
    for dlt, i, ka, kb in item_delta:
        by_knot[ka].append(dlt)
    total_shift = sum(d for d, *_ in item_delta)
    top10_share = sum(d for d, *_ in item_delta[:10]) / total_shift if total_shift else None
    modal_changed = sum(1 for _, _, ka, kb in item_delta if ka != kb)

    # ⑪ E(Text-01) 分歧根因: 网页 GPT 建议的零调用诊断(tests/data/webgpt_consultation_2026-10-03_gk1.json §3)
    E = t01
    peers = [m for m in models if m != E]
    top = lambda p: max(p, key=p.get)
    H = lambda p: -sum(v * math.log2(v) for v in p.values() if v > 0)

    def onehot_loo(d):   # one-hot 后 JS = top1 不一致率; 每人与其余人的平均不一致率
        return {m: round(statistics.mean(
            statistics.mean(float(top(d[m][i]) != top(d[o][i])) for i in ids if d[m].get(i) and d[o].get(i))
            for o in models if o != m), 4) for m in models}

    def sharpen(p, a):
        z = {k: v ** a for k, v in p.items() if v > 0}
        s = sum(z.values())
        return {k: v / s for k, v in z.items()}

    def fit_alpha(d):    # 全局一个 α: 让 E 的平均熵 = 四名同伴平均熵的中位数
        target = statistics.median(statistics.mean(H(d[m][i]) for i in ids if d[m].get(i)) for m in peers)
        lo, hi = 1.0, 6.0
        for _ in range(50):
            mid = (lo + hi) / 2
            h = statistics.mean(H(sharpen(d[E][i], mid)) for i in ids if d[E].get(i))
            lo, hi = (mid, hi) if h > target else (lo, mid)
        return (lo + hi) / 2

    def e_vs_peers(d, a=1.0):
        return statistics.mean(statistics.mean(js_div(sharpen(d[E][i], a), d[o][i]) for i in ids
                                               if d[E].get(i) and d[o].get(i)) for o in peers)

    def consensus(d, i):   # 四名同伴多数 top1(称 peer consensus, 不当金标); 并列返回 None
        c = collections.Counter(top(d[o][i]) for o in peers if d[o].get(i)).most_common()
        return c[0][0] if c and (len(c) == 1 or c[0][1] > c[1][1]) else None

    def confusion(d):
        cm, top2_in, n_dis = collections.Counter(), 0, 0
        for i in ids:
            k = consensus(d, i)
            if k is None or not d[E].get(i):
                continue
            e1 = top(d[E][i])
            if e1 != k:
                n_dis += 1
                cm[f"{k}->{e1}"] += 1
                if k in sorted(d[E][i], key=d[E][i].get, reverse=True)[:2]:
                    top2_in += 1
        return cm, top2_in, n_dis

    aA, aB = fit_alpha(da), fit_alpha(db)
    cmA, t2A, ndA = confusion(da)
    cmB, t2B, ndB = confusion(db)
    disputed = [i for i in ids if consensus(da, i) and da[E].get(i) and top(da[E][i]) != consensus(da, i)]
    stab = collections.Counter()
    for i in disputed:
        kb, eb = consensus(db, i), (top(db[E][i]) if db[E].get(i) else None)
        if kb == consensus(da, i) and eb == top(da[E][i]):
            stab["E 与同伴都没变(稳定分歧)"] += 1
        elif kb == consensus(da, i) and eb == kb:
            stab["E 第二次改回同伴的类"] += 1
        elif kb == consensus(da, i):
            stab["E 换了另一个异类"] += 1
        else:
            stab["同伴共识自己变了/并列"] += 1

    def outlier_trigger_prob(pj, rng):
        hits = 0
        for _ in range(B_BOOT):
            s = [rng.choice(ids) for _ in ids]
            lo = {m: statistics.mean(statistics.mean(per[i] for i in s if i in per)
                                     for k, per in pj.items() if m in k.split("~")) for m in models}
            v = sorted(lo.values())
            hits += lo[E] > statistics.median(v) + 2 * statistics.stdev(v)
        return round(hits / B_BOOT, 3)

    cause = {
        "onehot_top1_disagreement_vs_others": {"A": onehot_loo(da), "B": onehot_loo(db)},
        "global_sharpening_crossfit": {
            "alpha_fit_on_A": round(aA, 3), "alpha_fit_on_B": round(aB, 3),
            "E_vs_peers_raw": {"A": round(e_vs_peers(da), 4), "B": round(e_vs_peers(db), 4)},
            "E_vs_peers_B_with_alpha_from_A": round(e_vs_peers(db, aA), 4),
            "E_vs_peers_A_with_alpha_from_B": round(e_vs_peers(da, aB), 4)},
        "peer_consensus_to_E_top1_confusion": {"A": dict(cmA.most_common()), "B": dict(cmB.most_common())},
        "consensus_in_E_top2_among_disagreements": {"A": f"{t2A}/{ndA}", "B": f"{t2B}/{ndB}"},
        "disputed_items_in_A_followed_into_B": {"n": len(disputed), **dict(stab)},
        "outlier_rule_bootstrap_trigger_prob_E": {"A": outlier_trigger_prob(pa, random.Random(SEED + 1)),
                                                  "B": outlier_trigger_prob(pb, random.Random(SEED + 2))},
    }

    out = {
        "block": "GK1_FAIL_DIAGNOSIS", "date": "2026-10-03", "★zero_api": True,
        "⑪cause_of_E_divergence": cause,
        "inputs": {"A_0909_v2_acceptance": {"path": A_PATH, "sha256": sha(A_PATH)},
                   "B_1001_real_e2e": {"path": os.path.relpath(B_PATH, ROOT), "sha256": sha(B_PATH)}},
        "①instrument_check_recompute_equals_stored": rep,
        "②comparability_run_params(A, B)": comparable,
        "③headline": {"A_mean_JS": rep["A_stored"], "B_mean_JS": rep["B_stored"], "threshold": THR,
                      "delta_mean_JS": round(delta_total, 4),
                      "delta_from_Text01_pairs": round(delta_t01, 4),
                      "Text01_share_of_delta": round(delta_t01 / delta_total, 3) if delta_total else None},
        "④pairs": pairs,
        "⑤per_annotator": per_annot,
        "⑥outlier_rule_median_plus_2SD": {"A_cut": round(cutA, 4), "B_cut": round(cutB, 4),
                                          "B_Text01": round(loB[t01], 4),
                                          "B_Text01_margin_below_cut": round(cutB - loB[t01], 4),
                                          "excluded_A": [m for m in models if loA[m] > cutA],
                                          "excluded_B": [m for m in models if loB[m] > cutB]},
        "⑦same_model_run_to_run_drift": self_drift,
        "⑧leave_one_annotator_out_mean_JS": loo,
        "⑨item_cluster_bootstrap": {"B": B_BOOT, "seed": SEED,
                                    "A_CI95": ciA, "A_frac_over_0.25": pA,
                                    "B_CI95": ciB, "B_frac_over_0.25": pB,
                                    "paired_diff_B_minus_A_CI95": ci_diff},
        "⑩items": {"n": len(ids), "items_with_higher_JS": sum(1 for d, *_ in item_delta if d > 0),
                   "top10_items_share_of_total_shift": round(top10_share, 3) if top10_share else None,
                   "panel_modal_top1_changed_items": modal_changed,
                   "mean_delta_by_A_modal_knot": {k: {"n": len(v), "mean_delta": round(sum(v) / len(v), 4)}
                                                  for k, v in sorted(by_knot.items(), key=lambda x: -len(x[1]))},
                   "top10": [{"id": i, "delta": d, "modal_A": ka, "modal_B": kb} for d, i, ka, kb in item_delta[:10]]},
    }
    open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("③headline", "⑥outlier_rule_median_plus_2SD", "⑨item_cluster_bootstrap")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
