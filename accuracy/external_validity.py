#!/usr/bin/env python3
"""外部效度检验 — 用【别人的】帖子测 CCE 能不能预测真实互动。

2026-08-09。当日全部「欠功效/不可判」结论(噪声地板/多模态/OOS n=20/主体模拟 n=28/
G-K2 基线不可赢)根因同一个: 只用了我们自己 4 篇帖子的 104 条评论。而同版有
1208 篇他人帖子(964 个作者, 赞 0~559)一直在那儿。本文件补这一课。

设计: 成对判决, 免校准。
  - 从同一赞数分箱之外配对(一高一低), 控制帖龄(相差 <= AGE_TOL 天)
  - 输入只有标题+正文, 绝不含任何互动统计(防真值泄漏)
  - 问 CCE: 哪一篇拿到的赞更多
  - 零假设 = 50%。这不需要跨域校准, 所以「跨域分数无意义」这个老问题绕开了。
判负预注册: 命中率的 95% 区间下界 <= 0.5 ⇒ CCE 对他人帖子无预测力, 如实登记。
"""
import os, sys, json, math, random, argparse, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from concurrent.futures import ThreadPoolExecutor
from exp_crossmodel_desire import call_model
from exp_v4_full_validation import extract_json_robust

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGE_TOL_D = 45
SYS = """你是内容效果预测器。同一个板块(r/HearingAids)的两篇帖子, 发布时间接近。
预测哪一篇拿到的赞更多。只看标题与正文, 不做任何外部假设。

【A】
{A}

【B】
{B}

只输出JSON: {{"winner":"A"或"B","margin":0到100,"reason":"一句话"}}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=120)
    ap.add_argument("--ratio", type=float, default=3.0, help="配对要求高/低赞 >= 该倍数且绝对差>=5")
    ap.add_argument("--seed", type=int, default=20260809)
    ap.add_argument("--out", default=f"{ROOT}/accuracy/external_validity.json")
    A = ap.parse_args()
    posts = json.load(open(f"{ROOT}/accuracy/data/hearingaids_others_20260809.json", encoding="utf-8"))["posts"]
    posts = [p for p in posts if len((p.get("selftext") or "").split()) >= 25]
    rng = random.Random(A.seed)
    pairs, tries = [], 0
    while len(pairs) < A.pairs and tries < A.pairs * 400:
        tries += 1
        x, y = rng.sample(posts, 2)
        hi, lo = (x, y) if x["ups"] > y["ups"] else (y, x)
        if hi["ups"] < lo["ups"] * A.ratio or hi["ups"] - lo["ups"] < 5:
            continue
        if abs(hi["created"] - lo["created"]) > AGE_TOL_D * 86400:
            continue
        if (hi["id"], lo["id"]) in {(a["hi"], a["lo"]) for a in pairs}:
            continue
        pairs.append({"hi": hi["id"], "lo": lo["id"], "hi_ups": hi["ups"], "lo_ups": lo["ups"]})
    print(f"配对 {len(pairs)} 组 (赞比>= {A.ratio}x 且绝对差>=5, 帖龄相差<={AGE_TOL_D}天)", flush=True)
    idx = {p["id"]: p for p in posts}

    def body(p):
        return (p["title"] + "\n\n" + (p.get("selftext") or ""))[:2000]

    def one(i_pr):
        i, pr = i_pr
        hi, lo = idx[pr["hi"]], idx[pr["lo"]]
        flip = (i % 2 == 1)                       # 一半反位, 消位置偏
        a, b = (lo, hi) if flip else (hi, lo)
        c, _ = call_model("M3", SYS.format(A=body(a), B=body(b)), temperature=0.0)
        d = extract_json_robust(c, log_note="extval") or {}
        w = d.get("winner")
        pred_hi = (w == "B") if flip else (w == "A")
        return {**pr, "flipped": flip, "winner": w, "margin": d.get("margin"),
                "correct": bool(w) and pred_hi, "parsed": bool(w), "reason": (d.get("reason") or "")[:100]}

    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(one, list(enumerate(pairs))))
    ok = [r for r in rows if r["parsed"]]
    n = len(ok)
    acc = sum(r["correct"] for r in ok) / n if n else 0
    se = math.sqrt(acc * (1 - acc) / n) if n else 0
    lo95, hi95 = acc - 1.96 * se, acc + 1.96 * se
    # 位置偏检查
    pos = collections.Counter(("A" if not r["flipped"] else "B") == r["winner"] for r in ok)
    res = {"n_pairs": len(pairs), "n_parsed": n, "accuracy": round(acc, 4),
           "ci95": [round(lo95, 4), round(hi95, 4)], "null": 0.5,
           "pass": bool(lo95 > 0.5),
           "criteria": "95%区间下界 > 0.5 ⇒ 对他人帖子有预测力",
           "pick_A_rate": round(sum(1 for r in ok if r["winner"] == "A") / n, 3) if n else None,
           "rows": rows}
    json.dump(res, open(A.out, "w"), ensure_ascii=False, indent=1)
    print(f"命中 {acc:.1%}  95%CI [{lo95:.1%}, {hi95:.1%}]  零假设 50%  → {'✅ 有预测力' if lo95>0.5 else '❌ 未过'}", flush=True)
    print(f"选A率 {res['pick_A_rate']} (0.5 为无位置偏), 解析成功 {n}/{len(pairs)}", flush=True)


if __name__ == "__main__":
    main()
