#!/usr/bin/env python3
"""arm A(闸字段集) vs arm B(生产字段集) 的判决 —— 判据在看到读数之前写完。零 API。"""
import itertools
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault")
sys.path.insert(0, str(ROOT / "accuracy"))
PRE = json.loads((ROOT / "tests/data/gate_vs_production_fieldset_prereg.json").read_text(encoding="utf-8"))


def js(p, q):
    import math
    ks = set(p) | set(q)
    m = {k: (p.get(k, 0) + q.get(k, 0)) / 2 for k in ks}

    def kl(a):
        return sum(a.get(k, 0) * math.log2(a[k] / m[k]) for k in ks if a.get(k, 0) > 0)
    return (kl(p) + kl(q)) / 2


def metrics(dists, models, ids):
    """全面板 10 对的 mean_JS 与 mean_top2 —— 与 run_gates 同式。"""
    tops = {m: {i: (max(v, key=v.get) if v else None) for i, v in dists[m].items()} for m in models}
    t2 = {m: {i: sorted(v, key=v.get, reverse=True)[:2] if v else [] for i, v in dists[m].items()}
          for m in models}
    J, T = [], []
    for a, b in itertools.combinations(models, 2):
        sel = [i for i in ids if dists[a].get(i) and dists[b].get(i)]
        if not sel:
            continue
        J.append(sum(js(dists[a][i], dists[b][i]) for i in sel) / len(sel))
        T.append(sum(1 for i in sel if tops[a][i] in t2[b][i] or tops[b][i] in t2[a][i]) / len(sel))
    return (sum(J) / len(J) if J else None), (sum(T) / len(T) if T else None), len(J)


def main():
    A = json.loads((VAULT / "cce_runs/run_a_repeat/raw_annotations.json").read_text(encoding="utf-8"))
    models = A["annotators"]
    da = A["dists"]
    rb = json.loads((VAULT / "cce_runs/fieldset_arm_b/raw.json").read_text(encoding="utf-8"))
    db = {m: {} for m in models}
    for r in rb:
        if r["dist"]:
            db[r["model"]][r["id"]] = r["dist"]
    # ★ 只用**两臂都有读数**的条目 —— 否则差值里混进覆盖率差异
    ids = [i for i in A["sample_ids"]
           if all(da[m].get(i) for m in models) and all(db[m].get(i) for m in models)]

    # ★★ 预注册要求的缺失报告(在有结果之前写死, 见 prereg 的 missing_readings_rule)
    all_ids = A["sample_ids"]
    dropped = [i for i in all_ids if i not in set(ids)]
    cov = {"armA": {m: sum(1 for i in all_ids if da[m].get(i)) for m in models},
           "armB": {m: sum(1 for i in all_ids if db[m].get(i)) for m in models}}
    missA = sum(len(all_ids) - v for v in cov["armA"].values())
    missB = sum(len(all_ids) - v for v in cov["armB"].values())
    tot = len(all_ids) * len(models)
    from math import comb

    def _fisher_upper(a, b, c, d_):
        n1, n2, k = a + b, c + d_, a + c
        return sum(comb(n1, i) * comb(n2, k - i)
                   for i in range(a, min(n1, k) + 1)) / comb(n1 + n2, k)
    p_imb = _fisher_upper(missB, tot - missB, missA, tot - missA)
    drop_frac = len(dropped) / len(all_ids)
    trigger = drop_frac > 0.05 or p_imb < 0.10

    ja, ta, npair = metrics(da, models, ids)
    jb, tb, _ = metrics(db, models, ids)

    rnd = random.Random(20260908)
    diffs, tdiffs = [], []
    for _ in range(10000):
        s = [ids[rnd.randrange(len(ids))] for _ in ids]
        x = metrics(da, models, s)[0]
        y = metrics(db, models, s)[0]
        if x is not None and y is not None:
            diffs.append(y - x)
        u, v = metrics(da, models, s)[1], metrics(db, models, s)[1]
        if u is not None and v is not None:
            tdiffs.append(v - u)
    diffs.sort(); tdiffs.sort()
    lo, hi = diffs[int(.025 * len(diffs))], diffs[int(.975 * len(diffs))]
    d = jb - ja

    if lo <= 0 <= hi:
        verdict = "D4_影响不显著" if abs(d) <= 0.02 else "★不显著但点估计不小 —— 报为**未定**, 不许说「无差异」"
    elif d > 0.02:
        verdict = "★★D2_闸是乐观代理 —— G-K1 高估了生产字段集下的一致性"
    elif d < -0.02:
        verdict = "★★★D3_闸是悲观代理 —— 生产字段集反而更一致(**我赌错了**)"
    else:
        verdict = "★CI 不含 0 但差值 <=0.02 —— 统计显著、实质微小"

    out = {
        "block": "GATE_VS_PRODUCTION_FIELDSET_RESULT",
        "★prereg": "tests/data/gate_vs_production_fieldset_prereg.json",
        "n_items_both_arms": len(ids), "n_pairs": npair, "models": models,
        "★★缺失报告": {
            "逐模型覆盖": cov,
            "剔掉条目数": len(dropped), "剔掉比例": round(drop_frac, 4), "剔掉的id": dropped,
            "两臂缺失": f"armA {missA}/{tot} · armB {missB}/{tot}",
            "★两臂失衡单侧Fisher(armB更多)": round(p_imb, 5),
            "★★预注册触发条件(剔>5% 或 失衡p<0.10)": (
                "**已触发 ⇒ 必须补齐缺失读数后重判, 本结果不得直接下结论**" if trigger
                else "未触发 ⇒ 完备条目分析可用"),
        },
        "armA_闸字段集": {"mean_JS": round(ja, 4), "mean_top2": round(ta, 4)},
        "armB_生产字段集": {"mean_JS": round(jb, 4), "mean_top2": round(tb, 4)},
        "★diff_JS_B_minus_A": {"点估计": round(d, 4), "配对自助95%CI": [round(lo, 4), round(hi, 4)],
                               "B": 10000},
        "★diff_top2_B_minus_A": {"点估计": round(tb - ta, 4),
                                 "配对自助95%CI": [round(tdiffs[int(.025*len(tdiffs))], 4),
                                                   round(tdiffs[int(.975*len(tdiffs))], 4)],
                                 "★注": "top2 在混淆方向上结构性盲 ⇒ 参考项, 不作判决"},
        "★★★verdict": (verdict if not trigger else
                       f"**扣发** —— 缺失触发了预注册的补齐条件, 先补齐再判。(完备条目下本会是: {verdict})"),
        "★my_bet": {"赌的是": "arm B 更差(JS 更高)", "信心": "低",
                    "★结果": "**赌对**" if d > 0 else "**赌错**" if d < 0 else "持平"},
        "★★scope": PRE["★★★what_this_still_cannot_say"],
    }
    p = ROOT / "tests/data/gate_vs_production_fieldset_result.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "★★scope"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
