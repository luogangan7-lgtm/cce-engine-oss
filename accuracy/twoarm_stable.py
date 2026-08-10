#!/usr/bin/env python3
"""双臂对照 v2 —— 换成【已证稳定的两层】: 欲望 + 需求。

2026-08-09。v1 用九结做 B 臂, 结果 68.3% vs 裸 M3 71.7%, 增量 -0.033, McNemar p=0.58,
判定无增量。事后诊断: 九结(pain_seek/display/audit…)刻画的是"他此刻在做什么", 属
行为/表现层; 而折半信度实测行动层组内/组间比值 1.084、情绪 0.899, **行为层不是稳定属性**,
只有欲望 0.711 与需求 0.776 显著低于组间。拿不稳定的层去预测帖子表现, 加不了分是必然的。

本测把 B 臂换成欲望+需求(稳定层), 其余完全不变(同一批配对、同一 A 臂 prompt)。
A 臂同场重跑作对照 —— 已知它有约 1pp 的运行间波动(70.8% / 71.7% 两次),
故不复用历史值, 必须同场比。

判负预注册: B 臂 95%CI 下界 <= A 臂点估 ⇒ 稳定层亦无增量。
若此测再负, 结论应为: CCE 对"预测互动量"整体无效, 转向它可能有效的任务
(受众画像 / 内容诊断 / 回复生成), 而非继续在预测任务上加层。
"""
import os, sys, json, math, argparse, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from concurrent.futures import ThreadPoolExecutor
from exp_crossmodel_desire import call_model, DESIRES
from exp_v4_full_validation import extract_json_robust

NEEDS = json.load(open(f"{ROOT}/config/need_taxonomy.json", encoding="utf-8"))["controlled_keys"]

READ = """读出这段内容会在读者身上激活的【欲望】与【需求】, 各给分布(和=1, 只列>=0.1)。
欲望9: {D}
需求17: {N}
【内容】
{body}
只输出JSON: {{"desire":{{}},"need":{{}}}}"""

A_TMPL = """你是内容效果预测器。同一个板块(r/HearingAids)的两篇帖子, 发布时间接近。
预测哪一篇拿到的赞更多。只看标题与正文, 不做任何外部假设。

【A】
{A}

【B】
{B}

只输出JSON: {{"winner":"A"或"B","margin":0到100,"reason":"一句话"}}"""

B_TMPL = """你是内容效果预测器。同一个板块(r/HearingAids)的两篇帖子, 发布时间接近。
预测哪一篇拿到的赞更多。

除正文外, 另给出【稳定层读出】——该内容会激活读者的欲望与需求分布。
这两层已被实测证明是读者的稳定属性(折半信度 欲望0.711 / 需求0.776, 显著低于组间),
即它们刻画"什么样的人会被这条内容打中", 而非"此刻的情绪"。

【A】欲望 {DA} · 需求 {NA}
{A}

【B】欲望 {DB} · 需求 {NB}
{B}

只输出JSON: {{"winner":"A"或"B","margin":0到100,"reason":"一句话, 需引用欲望或需求"}}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=f"{ROOT}/accuracy/twoarm_stable.json")
    A = ap.parse_args()
    ev = json.load(open(f"{ROOT}/accuracy/external_validity.json", encoding="utf-8"))
    posts = {p["id"]: p for p in json.load(open(
        f"{ROOT}/accuracy/data/hearingaids_others_20260809.json", encoding="utf-8"))["posts"]}
    pairs = [r for r in ev["rows"] if r["hi"] in posts and r["lo"] in posts]
    body = lambda p: (p["title"] + "\n\n" + (p.get("selftext") or ""))[:2000]
    print(f"配对 {len(pairs)} 组 (与 v1 完全同批)", flush=True)

    ids = sorted({r["hi"] for r in pairs} | {r["lo"] for r in pairs})
    def read(pid):
        c, _ = call_model("M3", READ.format(D=DESIRES, N=NEEDS, body=body(posts[pid])),
                          temperature=0.0)
        d = extract_json_robust(c, log_note="ta2_read") or {}
        nz = lambda x, keys: {k: round(float(v), 2) for k, v in (x or {}).items()
                              if k in keys and isinstance(v, (int, float)) and v >= 0.1}
        return pid, {"D": nz(d.get("desire"), DESIRES), "N": nz(d.get("need"), NEEDS)}
    with ThreadPoolExecutor(max_workers=8) as ex:
        RM = dict(ex.map(read, ids))
    ok = sum(1 for v in RM.values() if v["D"] and v["N"])
    print(f"稳定层读出成功 {ok}/{len(ids)}", flush=True)

    def run(arm, pr, i):
        hi, lo = posts[pr["hi"]], posts[pr["lo"]]
        flip = (i % 2 == 1)
        a, b = (lo, hi) if flip else (hi, lo)
        if arm == "A":
            p = A_TMPL.format(A=body(a), B=body(b))
        else:
            ra, rb = RM.get(a["id"], {}), RM.get(b["id"], {})
            J = lambda x: json.dumps(x, ensure_ascii=False)
            p = B_TMPL.format(DA=J(ra.get("D", {})), NA=J(ra.get("N", {})),
                              DB=J(rb.get("D", {})), NB=J(rb.get("N", {})),
                              A=body(a), B=body(b))
        c, _ = call_model("M3", p, temperature=0.0)
        d = extract_json_robust(c, log_note=f"ta2_{arm}") or {}
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
    byp = collections.defaultdict(dict)
    for x in rows:
        if x["parsed"]: byp[(x["hi"], x["lo"])][x["arm"]] = x["correct"]
    both = [v for v in byp.values() if len(v) == 2]
    bo = sum(1 for v in both if v["B"] and not v["A"])
    ao = sum(1 for v in both if v["A"] and not v["B"])
    p_mc = None
    if bo + ao:
        n_, k_ = bo + ao, min(bo, ao)
        p_mc = round(min(1.0, 2 * sum(math.comb(n_, i) for i in range(k_ + 1)) / 2 ** n_), 4)
    res = {"gate": "双臂对照v2·稳定层(欲望+需求)", "A臂_裸M3": SA, "B臂_欲望需求": SB,
           "增量": round(SB["acc"] - SA["acc"], 4),
           "配对比较": {"仅B对": bo, "仅A对": ao, "两臂同": len(both) - bo - ao, "McNemar_p": p_mc},
           "判据": "B臂95%CI下界 > A臂点估 ⇒ 稳定层有增量",
           "pass": bool(SB["ci95"][0] > SA["acc"]),
           "对照_v1九结": {"A": 0.7167, "B": 0.6833, "增量": -0.0334, "McNemar_p": 0.5847},
           "若再负的结论": "CCE 对预测互动量整体无效, 应转向受众画像/内容诊断/回复生成",
           "rows": rows}
    json.dump(res, open(A.out, "w"), ensure_ascii=False, indent=1)
    print(f"\nA臂 裸M3        {SA['acc']:.1%} CI{SA['ci95']} n={SA['n']}")
    print(f"B臂 欲望+需求   {SB['acc']:.1%} CI{SB['ci95']} n={SB['n']}")
    print(f"增量 {res['增量']:+.4f}  配对 仅B对{bo}/仅A对{ao} McNemar p={p_mc}")
    print(f"对照 v1(九结): A 71.7% B 68.3% 增量 -0.0334")
    print(f">>> 稳定层有增量: {res['pass']}")


if __name__ == "__main__":
    main()
