#!/usr/bin/env python3
"""地基自检·全组合 —— 把四层拆成单跳, 所有有向组合对比校验, 让数据拼出链序。

2026-08-09。用户给的链序 欲望×情境→情绪→需求→行动→评价 与配置方向相反
(配置是 需求→appraisal→情绪, Lazarus 派)。两派本有分歧, 不该由我选边;
用户进一步指示"拆分组合, 进行对比校验"——故不比整链, 比单跳。

设计
  一次读出(唯一花钱处) → 四层分布 + appraisal
  然后 12 个有向单跳全部对比校验, 纯算术, 零额外成本:
    {欲望,需求,情绪,行动} 的所有有序对 X→Y
  每跳两种预测器:
    ① 理论映射   仅 欲望→需求 / 需求→情绪 有表(来自 need_taxonomy.json)
    ② 数据条件   从训练折估 P(Y|X) 的双线性矩阵, 留一法, 无泄漏
  基线: Y 的边际分布(完全不看 X)
  指标: 改善 = 基线JS - 预测JS, 带 95%CI
最后按"改善"给 12 跳排名, 看数据把链拼成什么顺序。

诚实声明: 互信息对称、静态文本无时序, 故这是**方向锐度**证据, 不是因果证明。
"""
import os, sys, json, math, random, argparse, collections, statistics as st
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from concurrent.futures import ThreadPoolExecutor

TAXO = json.load(open(f"{ROOT}/config/need_taxonomy.json", encoding="utf-8"))
NEEDS = TAXO["controlled_keys"]
D2N = TAXO["desire_context_need_map"]["map"]
N2E = {r["need"]: r for r in TAXO["need_emotion_map"]["map"]}


def norm(d):
    t = sum(d.values())
    return {k: v / t for k, v in d.items() if v > 0} if t > 0 else {}


def js(p, q):
    ks = set(p) | set(q)
    H = lambda d: sum(-v * math.log(v, 2) for v in d.values() if v > 0)
    m = {k: (p.get(k, 0) + q.get(k, 0)) / 2 for k in ks}
    return H(m) - (H(p) + H(q)) / 2


def theory_d2n(dd):
    out = collections.defaultdict(float)
    for des, w in dd.items():
        rows = [r for r in D2N if r["desire"].startswith(des)]
        for r in rows:
            out[r["primary_need"]] += w * 0.6 / len(rows)
            for a in (r.get("alt_needs") or []):
                out[a] += w * 0.2 / len(rows)
    return norm(out)


def theory_n2e(nd, cong):
    neg = str(cong).strip() in ("负", "negative", "-")
    out = collections.defaultdict(float)
    for n, w in nd.items():
        r = N2E.get(n)
        if not r: continue
        lst = r["blocked_emotions"] if neg else r["satisfied_emotions"]
        for e in lst or []:
            out[e] += w / len(lst)
    return norm(out)


def fit_cond(rows, xk, yk):
    """从训练折估 P(Y|X): M[x][y] ∝ Σ x_i·y_j, 按 x 行归一"""
    M = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in rows:
        for x, wx in r[xk].items():
            for y, wy in r[yk].items():
                M[x][y] += wx * wy
    return {x: norm(d) for x, d in M.items()}


def apply_cond(M, xd):
    out = collections.defaultdict(float)
    for x, w in xd.items():
        for y, q in (M.get(x) or {}).items():
            out[y] += w * q
    return norm(out)


def ci(vals):
    n = len(vals)
    if n < 4: return None, None, None
    mu = st.mean(vals); se = st.pstdev(vals) / math.sqrt(n)
    return round(mu, 4), round(mu - 1.96 * se, 4), round(mu + 1.96 * se, 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=70)
    ap.add_argument("--seed", type=int, default=20260809)
    ap.add_argument("--out", default=f"{ROOT}/accuracy/chain_ablation.json")
    A = ap.parse_args()
    posts = json.load(open(f"{ROOT}/accuracy/data/hearingaids_others_20260809.json",
                           encoding="utf-8"))["posts"]
    posts = [p for p in posts if 40 <= len((p.get("selftext") or "").split()) <= 400]
    random.Random(A.seed).shuffle(posts)
    sample = posts[:A.n]
    wd = f"{ROOT}/accuracy/_chain"; os.makedirs(wd, exist_ok=True)
    print(f"样本 {len(sample)} 条(域外他人帖正文)", flush=True)
    import subprocess
    from exp_crossmodel_desire import DESIRES
    from exp_v4_causal_chain import EMOTIONS, ACTIONS

    def one(i_p):
        i, p = i_p
        tf = f"{wd}/a{i}.txt"; out = f"{wd}/a{i}.json"
        open(tf, "w", encoding="utf-8").write((p["title"] + "\n\n" + p["selftext"])[:2500])
        r = subprocess.run([sys.executable, f"{ROOT}/scripts/cce_knot_classify.py",
                            "--text-file", tf, "--context", "r/HearingAids 他人帖正文(地基自检)",
                            "--k", "2", "--out", out], capture_output=True, text=True,
                           cwd=ROOT, timeout=900)
        if r.returncode != 0: return None
        d = json.load(open(out, encoding="utf-8")); L = d["stage1"]["layers"]
        return {"id": p["id"],
                "cong": (d["stage1"].get("appraisal") or {}).get("goal_congruence", ""),
                "欲望": norm(dict(zip(DESIRES, L["desire_vec"]))),
                "需求": norm(dict(zip(NEEDS, L["need_vec"]))),
                "情绪": norm(dict(zip(EMOTIONS, L["emotion_vec"]))),
                "行动": norm(dict(zip(ACTIONS, L["action_vec"])))}

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = [r for r in ex.map(one, list(enumerate(sample))) if r]
    print(f"读出成功 {len(rows)} —— 以下全部为零成本算术\n", flush=True)

    LAYERS = ["欲望", "需求", "情绪", "行动"]
    marg = {L: norm({k: v for r in rows for k, v in r[L].items()}) for L in LAYERS}

    results = []
    for X in LAYERS:
        for Y in LAYERS:
            if X == Y: continue
            gains, tgains = [], []
            for i, r in enumerate(rows):                      # 留一法
                tr = rows[:i] + rows[i + 1:]
                base = js(marg[Y], r[Y])
                gains.append(base - js(apply_cond(fit_cond(tr, X, Y), r[X]), r[Y]))
                th = None
                if X == "欲望" and Y == "需求": th = theory_d2n(r["欲望"])
                if X == "需求" and Y == "情绪": th = theory_n2e(r["需求"], r["cong"])
                if th: tgains.append(base - js(th, r[Y]))
            mu, lo, hi = ci(gains)
            tmu, tlo, thi = ci(tgains) if tgains else (None, None, None)
            results.append({"hop": f"{X}→{Y}", "X": X, "Y": Y,
                            "数据条件_改善": mu, "CI": [lo, hi], "显著": bool(lo and lo > 0),
                            "理论映射_改善": tmu, "理论CI": [tlo, thi] if tmu is not None else None})
    results.sort(key=lambda r: -(r["数据条件_改善"] or -9))

    print(f"{'跳':11s} {'数据改善':>8s} {'95%CI':>18s} {'显著':>4s}   理论映射改善")
    for r in results:
        t = f"{r['理论映射_改善']:+.4f}" if r["理论映射_改善"] is not None else "—"
        print(f"{r['hop']:11s} {r['数据条件_改善']:+8.4f} [{r['CI'][0]:+.3f},{r['CI'][1]:+.3f}] "
              f"{'✅' if r['显著'] else '❌':>4s}   {t}")

    sig = [r for r in results if r["显著"]]
    W = {(r["X"], r["Y"]): r["数据条件_改善"] for r in sig}

    # 用户主张: 这几层是【流动闭环】不是线性链。故不贪心拼线, 改为:
    #   ① 输出完整有向图边权  ② 枚举所有有向回路并给回路强度  ③ 对照三种候选环序
    def cycles():
        out = []
        for k in (2, 3, 4):
            import itertools
            for perm in itertools.permutations(LAYERS, k):
                if perm[0] != min(perm): continue          # 去掉旋转重复
                edges = [(perm[i], perm[(i + 1) % k]) for i in range(k)]
                if all(e in W for e in edges):
                    out.append({"环": " → ".join(perm) + f" → {perm[0]}",
                                "长度": k,
                                "最弱边": round(min(W[e] for e in edges), 4),
                                "边权和": round(sum(W[e] for e in edges), 4),
                                "边": {f"{a}→{b}": round(W[(a, b)], 4) for a, b in edges}})
        return sorted(out, key=lambda c: -c["最弱边"])       # 按瓶颈边排序: 环的强度取决于最弱一环

    cyc = cycles()
    CAND = {"用户主张(情绪先于需求)": [("欲望", "情绪"), ("情绪", "需求"), ("需求", "行动")],
            "配置现有(需求先于情绪)": [("欲望", "需求"), ("需求", "情绪"), ("情绪", "行动")]}
    cand_eval = {}
    for name, path in CAND.items():
        ws = [W.get(e) for e in path]
        cand_eval[name] = {"逐边": {f"{a}→{b}": (round(W[(a, b)], 4) if (a, b) in W else "不显著")
                                    for a, b in path},
                           "全边显著": all(w is not None for w in ws),
                           "最弱边": round(min([w for w in ws if w is not None]), 4) if any(ws) else None}
    json.dump(res, open(A.out, "w"), ensure_ascii=False, indent=1)
    print(f"\n══ 闭环枚举(按瓶颈边排序, 环的强度取决于最弱一环) ══")
    for c in cyc[:6]:
        print(f"  {c['环']:38s} 最弱边{c['最弱边']:+.4f} 和{c['边权和']:+.4f}")
    print(f"\n══ 两种候选环序逐边对比 ══")
    for name, v in cand_eval.items():
        print(f"  {name}: 全边显著={v['全边显著']} 最弱边={v['最弱边']}")
        for e, w in v["逐边"].items(): print(f"      {e}: {w}")


if __name__ == "__main__":
    main()
