#!/usr/bin/env python3
"""任务① 先验注入 —— B臂给【文本里没有的信息】, 而不是原文的有损摘要。

双臂 v1/v2 皆负的机制: 读出是同一文本的有损摘要, 判决器已有原文, 故不增信息。
修正: B臂注入**从其他帖子历史学出的先验**——"本版历史上, 激活哪些欲望/需求的内容
赞更多"。这是外部信息, 不在被判的两篇里。
留一法防泄漏: 判某对时, 先验只从**不含这两篇**的其余帖子学。
判负预注册: B臂95%CI下界 <= A臂点估 ⇒ 先验注入亦无增量。
"""
import os, sys, json, math, collections, statistics as st
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from concurrent.futures import ThreadPoolExecutor
from exp_crossmodel_desire import call_model, DESIRES
from exp_v4_full_validation import extract_json_robust
NEEDS = json.load(open(f"{ROOT}/config/need_taxonomy.json", encoding="utf-8"))["controlled_keys"]
READ = """读出这段内容激活的欲望与需求, 各给分布(和=1, 只列>=0.1)。
欲望9: {D}
需求17: {N}
【内容】
{body}
只输出JSON: {{"desire":{{}},"need":{{}}}}"""
A_T = """你是内容效果预测器。同板块两篇帖子, 发布时间接近。预测哪篇赞更多。只看标题正文。
【A】
{A}
【B】
{B}
只输出JSON: {{"winner":"A"或"B","margin":0到100,"reason":"一句话"}}"""
B_T = """你是内容效果预测器。同板块两篇帖子, 发布时间接近。预测哪篇赞更多。

另给你一份【本版历史先验】: 统计自本板块其他 {np} 篇帖子(不含下面这两篇),
列出激活各欲望/需求的内容的平均赞数分位。这是这两篇文本里没有的外部信息。
{prior}

【A】
{A}
【B】
{B}
只输出JSON: {{"winner":"A"或"B","margin":0到100,"reason":"一句话, 需引用先验"}}"""


def main():
    ev = json.load(open(f"{ROOT}/accuracy/external_validity.json", encoding="utf-8"))
    posts = {p["id"]: p for p in json.load(open(
        f"{ROOT}/accuracy/data/hearingaids_others_20260809.json", encoding="utf-8"))["posts"]}
    pairs = [r for r in ev["rows"] if r["hi"] in posts and r["lo"] in posts]
    body = lambda p: (p["title"] + "\n\n" + (p.get("selftext") or ""))[:2000]
    # 先验语料: 另取 120 篇不在任何配对里的帖
    used = {r["hi"] for r in pairs} | {r["lo"] for r in pairs}
    pool = [p for p in posts.values() if p["id"] not in used
            and 40 <= len((p.get("selftext") or "").split()) <= 400][:120]
    print(f"配对 {len(pairs)} · 先验语料 {len(pool)} 篇(与配对零重叠)", flush=True)

    def read(p):
        c, _ = call_model("M3", READ.format(D=DESIRES, N=NEEDS, body=body(p)), temperature=0.0)
        d = extract_json_robust(c, log_note="t1") or {}
        nz = lambda x, ks: {k: float(v) for k, v in (x or {}).items()
                            if k in ks and isinstance(v, (int, float)) and v >= 0.1}
        return p["id"], p["ups"], nz(d.get("desire"), DESIRES), nz(d.get("need"), NEEDS)
    with ThreadPoolExecutor(max_workers=8) as ex:
        R = [r for r in ex.map(read, pool) if r[2]]
    print(f"先验语料读出 {len(R)}", flush=True)

    # 先验表: 每个欲望/需求 -> 加权平均赞的对数, 转成分位描述
    def build(idx):
        agg = collections.defaultdict(list)
        for _, ups, D, N in R:
            for k, w in (D if idx == 2 else N).items():
                agg[k].append((w, math.log1p(ups)))
        out = {}
        for k, v in agg.items():
            if len(v) >= 4:
                out[k] = sum(w * u for w, u in v) / sum(w for w, _ in v)
        return out
    pd_, pn_ = build(2), build(3)
    rank = lambda d: sorted(d.items(), key=lambda x: -x[1])
    prior_txt = ("欲望(按该欲望被激活时内容的平均赞数由高到低):\n  "
                 + " > ".join(f"{k}({v:.2f})" for k, v in rank(pd_)) +
                 "\n需求(同上):\n  " + " > ".join(f"{k}({v:.2f})" for k, v in rank(pn_)[:10]))
    print("\n先验表:\n" + prior_txt + "\n", flush=True)

    def run(arm, pr, i):
        hi, lo = posts[pr["hi"]], posts[pr["lo"]]
        flip = i % 2 == 1
        a, b = (lo, hi) if flip else (hi, lo)
        p = (A_T.format(A=body(a), B=body(b)) if arm == "A" else
             B_T.format(np=len(R), prior=prior_txt, A=body(a), B=body(b)))
        c, _ = call_model("M3", p, temperature=0.0)
        d = extract_json_robust(c, log_note=f"t1{arm}") or {}
        w = d.get("winner")
        return {"arm": arm, "hi": pr["hi"], "lo": pr["lo"],
                "correct": bool(w) and ((w == "B") if flip else (w == "A")),
                "parsed": bool(w), "reason": (d.get("reason") or "")[:100]}
    jobs = [(x, pr, i) for x in "AB" for i, pr in enumerate(pairs)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(lambda j: run(*j), jobs))
    def stat(a):
        r = [x for x in rows if x["arm"] == a and x["parsed"]]
        n = len(r); acc = sum(x["correct"] for x in r)/n if n else 0
        se = math.sqrt(acc*(1-acc)/n) if n else 0
        return {"n": n, "acc": round(acc, 4), "ci95": [round(acc-1.96*se, 4), round(acc+1.96*se, 4)]}
    SA, SB = stat("A"), stat("B")
    byp = collections.defaultdict(dict)
    for x in rows:
        if x["parsed"]: byp[(x["hi"], x["lo"])][x["arm"]] = x["correct"]
    both = [v for v in byp.values() if len(v) == 2]
    bo = sum(1 for v in both if v["B"] and not v["A"]); ao = sum(1 for v in both if v["A"] and not v["B"])
    p_mc = round(min(1.0, 2*sum(math.comb(bo+ao, i) for i in range(min(bo, ao)+1))/2**(bo+ao)), 4) if bo+ao else None
    res = {"gate": "任务①先验注入", "A臂": SA, "B臂_带先验": SB,
           "增量": round(SB["acc"]-SA["acc"], 4),
           "配对": {"仅B对": bo, "仅A对": ao, "McNemar_p": p_mc},
           "pass": bool(SB["ci95"][0] > SA["acc"]), "先验表": {"欲望": pd_, "需求": pn_},
           "对照": {"v1九结": -0.0334, "v2稳定层": -0.0231}, "rows": rows}
    json.dump(res, open(f"{ROOT}/accuracy/t1_prior.json", "w"), ensure_ascii=False, indent=1)
    print(f"A {SA['acc']:.1%} CI{SA['ci95']} | B {SB['acc']:.1%} CI{SB['ci95']} | 增量 {res['增量']:+.4f}")
    print(f"配对 仅B对{bo}/仅A对{ao} p={p_mc} >>> pass={res['pass']}")


main()
