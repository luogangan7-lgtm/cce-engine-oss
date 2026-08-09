#!/usr/bin/env python3
"""五层顺序组合校准 —— 不假设链序, 把中间三层的排列全试一遍, 用样本外预测力选。

2026-08-09。用户三条指示合并实现:
  1) 4层变5层 —— 加入情境(config/context_taxonomy.json, 9面, 允许显式未知)
  2) 不同顺序组合进行校准 —— 欲望固定在头(稳定), 行动固定在尾(产出),
     中间 {情境,情绪,需求} 的 6 种排列全部拟合, 比谁对【行动】的样本外预测最好
  3) 槽填充度 —— 情境按面读出且允许"未知", 填充度=已知面数/9, 免费得到
     可证伪预言: 预测精度随填充度单调上升。不成立则情境层该砍。

数据: 域外他人帖的多轮对话链(827链/3025轮), 一次读出五层, 之后全部为零成本算术。
留一法拟合条件矩阵, 无泄漏。终端指标 = 对行动分布的 JS, 对照边际基线。
"""
import os, sys, json, math, random, argparse, itertools, collections, statistics as st
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from concurrent.futures import ThreadPoolExecutor
from exp_crossmodel_desire import call_model, DESIRES
from exp_v4_causal_chain import EMOTIONS, ACTIONS
from exp_v4_full_validation import extract_json_robust

CTX = json.load(open(f"{ROOT}/config/context_taxonomy.json", encoding="utf-8"))
FACETS = CTX["facets"]
NEEDS = json.load(open(f"{ROOT}/config/need_taxonomy.json", encoding="utf-8"))["controlled_keys"]

TMPL = """你是心理配置读取器。对下面这段真实发言, 读出五层。全部用分布(权重和=1), 不许只给一个标签。

【欲望 9 类】{D}
【情绪 13 类】{E}
【需求 17 类】{N}
【行动 7 类】{A}
【情境 9 面】逐面选一个值; **读不出来就填"未知"或"未提及", 严禁猜**:
{C}

【发言】(该作者在此串的第 {idx} 轮, 之前他说过 {prev} 轮)
{body}

只输出JSON:
{{"desire":{{"类名":权重}},"emotion":{{"类名":权重}},"need":{{"类名":权重}},
  "action":{{"类名":权重}},"context":{{"面名":"选中的值"}}}}"""


def norm(d):
    d = {k: float(v) for k, v in (d or {}).items() if isinstance(v, (int, float)) and v > 0}
    t = sum(d.values())
    return {k: v / t for k, v in d.items()} if t else {}


def js(p, q):
    H = lambda d: sum(-v * math.log(v, 2) for v in d.values() if v > 0)
    m = {k: (p.get(k, 0) + q.get(k, 0)) / 2 for k in set(p) | set(q)}
    return H(m) - (H(p) + H(q)) / 2


def fit(rows, xk, yk):
    M = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in rows:
        for x, wx in r[xk].items():
            for y, wy in r[yk].items():
                M[x][y] += wx * wy
    return {x: norm(dict(d)) for x, d in M.items()}


def apply(M, xd):
    o = collections.defaultdict(float)
    for x, w in xd.items():
        for y, q in (M.get(x) or {}).items():
            o[y] += w * q
    return norm(dict(o))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=220)
    ap.add_argument("--seed", type=int, default=20260809)
    ap.add_argument("--out", default=f"{ROOT}/accuracy/order_calibration.json")
    A = ap.parse_args()
    ch = json.load(open(f"{ROOT}/accuracy/data/hearingaids_chains_20260809.json",
                        encoding="utf-8"))["chains"]
    turns = [{"who": c["who"], "post": c["post"], "idx": i + 1, "prev": i,
              "b": t["b"], "ups": t["ups"]}
             for c in ch for i, t in enumerate(c["turns"]) if len(t["b"].split()) >= 15]
    random.Random(A.seed).shuffle(turns)
    turns = turns[:A.n]
    facet_txt = "\n".join(f"  {f['key']}: {f['values']}" for f in FACETS)
    print(f"样本 {len(turns)} 轮(域外多轮对话)", flush=True)

    def one(t):
        p = TMPL.format(D=DESIRES, E=EMOTIONS, N=NEEDS, A=ACTIONS, C=facet_txt,
                        idx=t["idx"], prev=t["prev"], body=t["b"][:1400])
        c, _ = call_model("M3", p, temperature=0.0)
        d = extract_json_robust(c, log_note="order_cal")
        if not isinstance(d, dict):
            return None
        cx = d.get("context") or {}
        known = [f["key"] for f in FACETS
                 if str(cx.get(f["key"], "未知")) not in ("未知", "未提及", "", "None")]
        return {**t,
                "欲望": norm(d.get("desire")), "情绪": norm(d.get("emotion")),
                "需求": norm(d.get("need")), "行动": norm(d.get("action")),
                "情境": norm({f"{k}={v}": 1.0 for k, v in cx.items()}),
                "fill": round(len(known) / len(FACETS), 3), "known": known}

    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = [r for r in ex.map(one, turns) if r and all(r[L] for L in
                ("欲望", "情绪", "需求", "行动", "情境"))]
    print(f"读出成功 {len(rows)} —— 以下零成本\n", flush=True)

    marg_A = norm({k: v for r in rows for k, v in r["行动"].items()})
    MID = ["情境", "情绪", "需求"]
    out = []
    for perm in itertools.permutations(MID):
        path = ["欲望"] + list(perm) + ["行动"]
        gains = []
        for i, r in enumerate(rows):
            tr = rows[:i] + rows[i + 1:]
            cur = r["欲望"]
            for a, b in zip(path, path[1:]):
                cur = apply(fit(tr, a, b), cur)
                if not cur:
                    break
            if cur:
                gains.append(js(marg_A, r["行动"]) - js(cur, r["行动"]))
        n = len(gains); mu = st.mean(gains) if n else 0
        se = st.pstdev(gains) / math.sqrt(n) if n > 1 else 0
        out.append({"链序": " → ".join(path), "n": n, "改善": round(mu, 4),
                    "95%CI": [round(mu - 1.96 * se, 4), round(mu + 1.96 * se, 4)],
                    "显著": bool(mu - 1.96 * se > 0)})
    out.sort(key=lambda x: -x["改善"])

    print(f"{'链序':46s} {'改善':>8s} {'95%CI':>18s} 显著")
    for o in out:
        print(f"{o['链序']:46s} {o['改善']:+8.4f} [{o['95%CI'][0]:+.3f},{o['95%CI'][1]:+.3f}] "
              f"{'✅' if o['显著'] else '❌'}")

    # 槽填充度 → 精度 是否单调上升(用最优链序)
    best = out[0]["链序"].split(" → ")
    per = []
    for i, r in enumerate(rows):
        tr = rows[:i] + rows[i + 1:]
        cur = r["欲望"]
        for a, b in zip(best, best[1:]):
            cur = apply(fit(tr, a, b), cur)
        if cur:
            per.append((r["fill"], js(marg_A, r["行动"]) - js(cur, r["行动"])))
    bins = [(0, .22), (.22, .34), (.34, .45), (.45, 1.01)]
    fillrep = []
    for lo, hi in bins:
        g = [x for f, x in per if lo <= f < hi]
        if len(g) >= 5:
            fillrep.append({"填充度区间": f"{lo:.2f}-{hi:.2f}", "n": len(g),
                            "平均改善": round(st.mean(g), 4)})
    def sp(a, b):
        rk = lambda v: [sorted(v).index(x) + 1 for x in v]
        x, y = rk([p[0] for p in per]), rk([p[1] for p in per])
        n = len(x); mx, my = sum(x)/n, sum(y)/n
        nu = sum((p-mx)*(q-my) for p, q in zip(x, y))
        de = (sum((p-mx)**2 for p in x)*sum((q-my)**2 for q in y))**.5
        return round(nu/de, 3) if de else None
    rho = sp(None, None) if len(per) > 3 else None

    facet_hit = collections.Counter(k for r in rows for k in r["known"])
    res = {"gate": "五层顺序组合校准", "n": len(rows),
           "链序对比": out, "最优链序": out[0]["链序"],
           "用户主张": "欲望 → 情境 → 情绪 → 需求 → 行动",
           "配置现有": "欲望 → 情境 → 需求 → 情绪 → 行动",
           "填充度分箱": fillrep,
           "填充度×改善_spearman": rho,
           "可证伪预言": "精度随填充度单调上升; rho<=0 ⇒ 情境层无用, 该砍",
           "各面可读出率": {k: round(v / len(rows), 3) for k, v in facet_hit.most_common()},
           "平均填充度": round(st.mean([r["fill"] for r in rows]), 3),
           "rows": rows}
    json.dump(res, open(A.out, "w"), ensure_ascii=False, indent=1)
    print(f"\n最优链序: {res['最优链序']}")
    print(f"用户主张: {res['用户主张']}")
    print(f"\n填充度×改善 spearman = {rho}  (预言: >0 且显著)")
    for f in fillrep: print(f"  填充度 {f['填充度区间']} n={f['n']:3d} 平均改善 {f['平均改善']:+.4f}")
    print(f"\n平均填充度 {res['平均填充度']} · 各面可读出率 {res['各面可读出率']}")


if __name__ == "__main__":
    main()
