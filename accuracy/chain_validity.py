#!/usr/bin/env python3
"""地基自检 —— 四层到底是一条因果链, 还是四个互不相干的标注?

2026-08-09。用户: "情感也是欲望衍生出来的"。查配置发现 need_taxonomy.json 里
早已形式化了这条链:
  projection: 「1欲望×N情境=N需求: 同一稳定欲望经不同情境投影出不同需求。
               需求是欲望与情绪之间的中间层。」
  need_emotion_map: 「需求→情绪经 appraisal(goal-congruence) 投影,
               满足/受阻触发不同情绪。」
但 grep 结果: desire_context_need_map 被 0 个文件引用, chain_examples 0,
maxneef_coverage 0, coherence_autocheck 只在 exp_ 实验脚本里。
生产链 cce_knot_classify.py 是四个向量各自独立读出、各自取 top ——
**链条定义了, 从没执行过, 也从没验过。**(当日同族缺陷第六例)

本文件验两跳:
  A 欲望 → 需求   用 desire_context_need_map 从 desire_vec 预测 need_vec
  B 需求 → 情绪   用 need_emotion_map + goal_congruence 从 need_vec 预测 emotion_vec
判据: 映射预测的 JS 显著低于「边际基线」(不看上游, 直接用语料平均分布)。
  过 ⇒ 链条成立, 地基是真的, 而我们白白独立标注了四次
  不过 ⇒ 四层无因果关系, "因果链"名不副实, 地基需要改
"""
import os, sys, json, math, random, argparse, collections, statistics as st
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from concurrent.futures import ThreadPoolExecutor

TAXO = json.load(open(f"{ROOT}/config/need_taxonomy.json", encoding="utf-8"))
NEEDS = TAXO["controlled_keys"]
D2N = TAXO["desire_context_need_map"]["map"]
N2E = {r["need"]: r for r in TAXO["need_emotion_map"]["map"]}
PRIMARY_W, ALT_W = 0.6, 0.2      # 显式权重: primary 0.6, 每个 alt 0.2


def js(p, q):
    ks = set(p) | set(q)
    def H(d):
        return sum(-v * math.log(v, 2) for v in d.values() if v > 0)
    m = {k: (p.get(k, 0) + q.get(k, 0)) / 2 for k in ks}
    return round(H(m) - (H(p) + H(q)) / 2, 4)


def norm(d):
    t = sum(d.values())
    return {k: v / t for k, v in d.items() if v > 0} if t > 0 else {}


def predict_need(desire_dist):
    """欲望分布 → 需求分布(按映射表)。同一欲望有多行(多情境)时合并。"""
    out = collections.defaultdict(float)
    for des, w in desire_dist.items():
        rows = [r for r in D2N if r["desire"].startswith(des)]
        if not rows:
            continue
        for r in rows:
            out[r["primary_need"]] += w * PRIMARY_W / len(rows)
            for a in (r.get("alt_needs") or []):
                out[a] += w * ALT_W / len(rows)
    return norm(out)


def invert_n2e():
    """把 需求→情绪 表反过来: 每个情绪由哪些需求产生。用于测 情绪→需求 方向。"""
    inv = collections.defaultdict(lambda: collections.defaultdict(float))
    for nd, r in N2E.items():
        for pol in ("satisfied_emotions", "blocked_emotions"):
            lst = r.get(pol) or []
            for e in lst:
                inv[e][nd] += 1.0 / len(lst)
    return {e: norm(d) for e, d in inv.items()}


E2N = None


def predict_need_from_emotion(emo_dist):
    """情绪分布 → 需求分布(反转映射)。用户主张的链序: 欲望×情境→情绪→需求。"""
    global E2N
    if E2N is None:
        E2N = invert_n2e()
    out = collections.defaultdict(float)
    for e, w in emo_dist.items():
        for nd, q in (E2N.get(e) or {}).items():
            out[nd] += w * q
    return norm(out)


def predict_emotion(need_dist, congruence):
    """需求分布 + goal_congruence → 情绪分布(按映射表)"""
    out = collections.defaultdict(float)
    neg = str(congruence).strip() in ("负", "negative", "-")
    for nd, w in need_dist.items():
        r = N2E.get(nd)
        if not r:
            continue
        lst = r["blocked_emotions"] if neg else r["satisfied_emotions"]
        if not lst:
            continue
        for e in lst:
            out[e] += w / len(lst)
    return norm(out)


def readout(text, ctx, outdir, tag):
    import subprocess
    tf = f"{outdir}/{tag}.txt"
    open(tf, "w", encoding="utf-8").write(text)
    out = f"{outdir}/{tag}.json"
    r = subprocess.run([sys.executable, f"{ROOT}/scripts/cce_knot_classify.py",
                        "--text-file", tf, "--context", ctx, "--k", "2", "--out", out],
                       capture_output=True, text=True, cwd=ROOT, timeout=900)
    if r.returncode != 0:
        return None
    return json.load(open(out, encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20260809)
    ap.add_argument("--out", default=f"{ROOT}/accuracy/chain_validity.json")
    A = ap.parse_args()
    posts = json.load(open(f"{ROOT}/accuracy/data/hearingaids_others_20260809.json",
                           encoding="utf-8"))["posts"]
    posts = [p for p in posts if 40 <= len((p.get("selftext") or "").split()) <= 400]
    random.Random(A.seed).shuffle(posts)
    sample = posts[:A.n]
    wd = f"{ROOT}/accuracy/_chain"; os.makedirs(wd, exist_ok=True)
    print(f"样本 {len(sample)} 条(他人帖正文, 域外)", flush=True)

    def one(i_p):
        i, p = i_p
        d = readout((p["title"] + "\n\n" + p["selftext"])[:2500],
                    "r/HearingAids 他人帖正文(地基自检)", wd, f"c{i}")
        if not d:
            return None
        L = d["stage1"]["layers"]
        from exp_crossmodel_desire import DESIRES
        from exp_v4_causal_chain import EMOTIONS
        act_d = norm({k: v for k, v in zip(DESIRES, L["desire_vec"])})
        act_n = norm({k: v for k, v in zip(NEEDS, L["need_vec"])})
        act_e = norm({k: v for k, v in zip(EMOTIONS, L["emotion_vec"])})
        cong = (d["stage1"].get("appraisal") or {}).get("goal_congruence", "")
        return {"id": p["id"], "cong": cong, "act_d": act_d, "act_n": act_n, "act_e": act_e,
                "pred_n": predict_need(act_d), "pred_e": predict_emotion(act_n, cong),
                "pred_n_from_e": predict_need_from_emotion(act_e)}

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = [r for r in ex.map(one, list(enumerate(sample))) if r]
    print(f"读出成功 {len(rows)}", flush=True)

    marg_n, marg_e = collections.defaultdict(float), collections.defaultdict(float)
    for r in rows:
        for k, v in r["act_n"].items(): marg_n[k] += v / len(rows)
        for k, v in r["act_e"].items(): marg_e[k] += v / len(rows)
    marg_n, marg_e = norm(marg_n), norm(marg_e)

    a_map = [js(r["pred_n"], r["act_n"]) for r in rows if r["pred_n"]]
    a_base = [js(marg_n, r["act_n"]) for r in rows if r["pred_n"]]
    b_map = [js(r["pred_e"], r["act_e"]) for r in rows if r["pred_e"]]
    b_base = [js(marg_e, r["act_e"]) for r in rows if r["pred_e"]]

    def block(mp, bs, name):
        d = [b - m for m, b in zip(mp, bs)]          # 正 = 映射比基线好
        n = len(d); mu = st.mean(d) if n else 0
        sd = st.pstdev(d) if n > 1 else 0
        se = sd / math.sqrt(n) if n else 0
        return {"跳": name, "n": n, "映射JS": round(st.mean(mp), 4) if n else None,
                "边际基线JS": round(st.mean(bs), 4) if n else None,
                "改善": round(mu, 4), "95%CI": [round(mu - 1.96 * se, 4), round(mu + 1.96 * se, 4)],
                "映射更优的条数": f"{sum(1 for x in d if x > 0)}/{n}",
                "显著": bool(n > 3 and mu - 1.96 * se > 0)}

    c_map = [js(r["pred_n_from_e"], r["act_n"]) for r in rows if r["pred_n_from_e"]]
    c_base = [js(marg_n, r["act_n"]) for r in rows if r["pred_n_from_e"]]
    A_ = block(a_map, a_base, "A 欲望→需求")
    B_ = block(b_map, b_base, "B 需求→情绪(配置方向)")
    C_ = block(c_map, c_base, "C 情绪→需求(用户方向)")
    res = {"gate": "地基自检·四层因果链", "n": len(rows),
           "congruence分布": dict(collections.Counter(r["cong"] for r in rows)),
           "A": A_, "B": B_, "C": C_,
           "判据": "映射预测JS显著低于边际基线 ⇒ 该跳成立",
           "方向对比": {
               "note": ("B 与 C 用同一张表的正反两向。谁相对各自基线改善更大, 谁那一向更锐。"
                        "这是方向性证据而非因果证明——互信息本身对称, 静态文本也拿不到时序。"),
               "配置方向(需求→情绪)改善": B_["改善"], "用户方向(情绪→需求)改善": C_["改善"],
               "更锐的方向": ("用户方向 情绪→需求" if C_["改善"] > B_["改善"] else "配置方向 需求→情绪")},
           "chain_holds": bool(A_["显著"] and (B_["显著"] or C_["显著"])), "rows": rows}
    json.dump(res, open(A.out, "w"), ensure_ascii=False, indent=1)
    for x in (A_, B_, C_):
        print(f"{x['跳']}: 映射JS {x['映射JS']} vs 基线 {x['边际基线JS']} "
              f"改善 {x['改善']:+} CI{x['95%CI']} {x['映射更优的条数']} → {'✅' if x['显著'] else '❌'}", flush=True)
    print(f"\n更锐的方向: {res['方向对比']['更锐的方向']}", flush=True)
    print(f"链条成立: {res['chain_holds']}", flush=True)


if __name__ == "__main__":
    main()
