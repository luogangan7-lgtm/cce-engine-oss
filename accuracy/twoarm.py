#!/usr/bin/env python3
"""双臂对照 —— 九结到底加不加分? 这是整个项目的立身问题。

2026-08-09 外部效度拿到 70.8%(CI 62.7-79.0, n=120), 但那次**只调了裸 M3 成对 prompt,
完全没走 s1-s8 九结链路**, 证明的是"M3 能排序帖子", 不是"九结有预测力"。
本文件补这一课: 同一批配对, 两臂只差九结信息。

  A 臂  裸 M3 成对判决(与 external_validity 同 prompt) —— 已知基线 70.8%
  B 臂  先对两篇各跑九结分布读出, 把读出结果连同正文一起给判决器
判负预注册: B 臂命中率的 95%CI 下界 <= A 臂点估 ⇒ 九结无增量, 如实登记。
配对复用 external_validity.json 的同一批, 保证可比。
"""
import os, sys, json, math, argparse, collections, statistics as st
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from concurrent.futures import ThreadPoolExecutor
from exp_crossmodel_desire import call_model
from exp_v4_full_validation import extract_json_robust

TAXO = json.load(open(f"{ROOT}/config/knot_taxonomy.json", encoding="utf-8"))
KNOTS = [k["key"] for k in TAXO["knots"]]
BRIEF = "\n".join(f"- {k['key']}({k['name']}): {k['behavior'][:60]}" for k in TAXO["knots"])

KNOT_TMPL = """判定这段内容会激活读者的哪些结, 带权分布(和=1, 只列>=0.1, 最多3个)。
九结: {brief}
【内容】
{body}
只输出JSON: {{"knots":[{{"key":"","weight":0.0}}]}}"""

A_TMPL = """你是内容效果预测器。同一个板块(r/HearingAids)的两篇帖子, 发布时间接近。
预测哪一篇拿到的赞更多。只看标题与正文, 不做任何外部假设。

【A】
{A}

【B】
{B}

只输出JSON: {{"winner":"A"或"B","margin":0到100,"reason":"一句话"}}"""

B_TMPL = """你是内容效果预测器。同一个板块(r/HearingAids)的两篇帖子, 发布时间接近。
预测哪一篇拿到的赞更多。

除正文外, 另给出【九结读出】——该内容会激活读者哪些心理结的带权分布。
九结含义: {brief}
推动族(pain_seek/injustice/belong/reward/display/itch)驱动行动; 阻挡族(suspend/inertia/audit)抑制行动。

【A】九结: {KA}
{A}

【B】九结: {KB}
{B}

只输出JSON: {{"winner":"A"或"B","margin":0到100,"reason":"一句话, 需引用九结"}}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=f"{ROOT}/accuracy/twoarm.json")
    A = ap.parse_args()
    ev = json.load(open(f"{ROOT}/accuracy/external_validity.json", encoding="utf-8"))
    posts = {p["id"]: p for p in json.load(open(
        f"{ROOT}/accuracy/data/hearingaids_others_20260809.json", encoding="utf-8"))["posts"]}
    pairs = [r for r in ev["rows"] if r["hi"] in posts and r["lo"] in posts]
    print(f"复用 external_validity 的 {len(pairs)} 组配对 (A臂已知 {ev['accuracy']:.1%})", flush=True)
    body = lambda p: (p["title"] + "\n\n" + (p.get("selftext") or ""))[:2000]

    ids = sorted({r["hi"] for r in pairs} | {r["lo"] for r in pairs})
    def knot(pid):
        c, _ = call_model("M3", KNOT_TMPL.format(brief=BRIEF, body=body(posts[pid])), temperature=0.0)
        d = extract_json_robust(c, log_note="twoarm_knot") or {}
        ks = {k["key"]: float(k.get("weight", 0)) for k in (d.get("knots") or [])
              if k.get("key") in KNOTS}
        t = sum(ks.values())
        return pid, ({k: round(v / t, 2) for k, v in ks.items()} if t else {})
    with ThreadPoolExecutor(max_workers=8) as ex:
        KM = dict(ex.map(knot, ids))
    ok = sum(1 for v in KM.values() if v)
    print(f"九结读出成功 {ok}/{len(ids)}", flush=True)

    def run(arm, pr, i):
        hi, lo = posts[pr["hi"]], posts[pr["lo"]]
        flip = (i % 2 == 1)
        a, b = (lo, hi) if flip else (hi, lo)
        if arm == "A":
            p = A_TMPL.format(A=body(a), B=body(b))
        else:
            p = B_TMPL.format(brief=BRIEF, KA=json.dumps(KM.get(a["id"], {}), ensure_ascii=False),
                              KB=json.dumps(KM.get(b["id"], {}), ensure_ascii=False),
                              A=body(a), B=body(b))
        c, _ = call_model("M3", p, temperature=0.0)
        d = extract_json_robust(c, log_note=f"twoarm_{arm}") or {}
        w = d.get("winner")
        pred_hi = (w == "B") if flip else (w == "A")
        return {"arm": arm, "hi": pr["hi"], "lo": pr["lo"], "winner": w,
                "correct": bool(w) and pred_hi, "parsed": bool(w),
                "reason": (d.get("reason") or "")[:110]}

    jobs = [("A", pr, i) for i, pr in enumerate(pairs)] + [("B", pr, i) for i, pr in enumerate(pairs)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(lambda j: run(*j), jobs))

    def stat(arm):
        r = [x for x in rows if x["arm"] == arm and x["parsed"]]
        n = len(r); acc = sum(x["correct"] for x in r) / n if n else 0
        se = math.sqrt(acc * (1 - acc) / n) if n else 0
        return {"n": n, "acc": round(acc, 4),
                "ci95": [round(acc - 1.96 * se, 4), round(acc + 1.96 * se, 4)]}
    SA, SB = stat("A"), stat("B")
    # 配对差(同一组配对上 B 对 A 错 / A 对 B 错)
    byp = collections.defaultdict(dict)
    for x in rows:
        if x["parsed"]: byp[(x["hi"], x["lo"])][x["arm"]] = x["correct"]
    both = [v for v in byp.values() if "A" in v and "B" in v]
    b_only = sum(1 for v in both if v["B"] and not v["A"])
    a_only = sum(1 for v in both if v["A"] and not v["B"])
    p_mc = None
    if b_only + a_only > 0:                        # McNemar 精确二项(双侧)
        n_, k_ = b_only + a_only, min(b_only, a_only)
        p_mc = round(min(1.0, 2 * sum(math.comb(n_, i) for i in range(k_ + 1)) / 2 ** n_), 4)
    res = {"gate": "双臂对照·九结是否加分", "A臂_裸M3": SA, "B臂_带九结": SB,
           "增量": round(SB["acc"] - SA["acc"], 4),
           "配对比较": {"仅B对": b_only, "仅A对": a_only, "两臂同": len(both) - b_only - a_only,
                      "McNemar_p": p_mc},
           "判据": "B臂95%CI下界 > A臂点估 ⇒ 九结有增量",
           "pass": bool(SB["ci95"][0] > SA["acc"]),
           "历史参照": {"external_validity_A臂": ev["accuracy"]}, "rows": rows}
    json.dump(res, open(A.out, "w"), ensure_ascii=False, indent=1)
    print(f"\nA臂 裸M3   {SA['acc']:.1%} CI{SA['ci95']}  n={SA['n']}")
    print(f"B臂 带九结 {SB['acc']:.1%} CI{SB['ci95']}  n={SB['n']}")
    print(f"增量 {res['增量']:+.4f}   配对: 仅B对 {b_only} / 仅A对 {a_only} / McNemar p={p_mc}")
    print(f">>> 九结有增量: {res['pass']}")


if __name__ == "__main__":
    main()
