#!/usr/bin/env python3
"""主体模拟 — 让每个真实主体去看文案, 预测会不会触达、会不会有动作, 再拿真实行为验。

2026-08-09。此前把受众当成一团分布(s5 把 N 个人的话拼成一段判结), 概念上就错了:
受众是一群各有因果链的人。本文件按人建模、按人预测、按人校验。

  A 主体卡  = 该人真实发言逆推的九结/四层/成本分 + 该人真实行为频率(报型号/提问/回OP/…)
  B 刺激    = 一段文案
  预测      = 这个主体看到 B 会不会动; 若动, 做哪种动作
  校验      = 该主体对该帖的真实行为(评论过没有, 做了什么)

判负条件预注册: 命中率 <= 多数基线 ⇒ 主体模拟无增益, 如实登记。
"""
import os, sys, json, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concurrent.futures import ThreadPoolExecutor
from exp_crossmodel_desire import call_model
from exp_v4_full_validation import extract_json_robust

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOTS = {"auto-sticky", "AutoModerator", "Hearingaids-bot"}
ACTIONS = ["named_specific_model", "asked_question", "described_own_situation_in_detail",
           "challenged_or_confronted", "offered_help_or_correction", "thanks_only"]

TMPL = """你在模拟一个真实的人, 判断他看到一段内容后会不会有动作。

【这个人是谁 — 全部来自他自己发过的话与做过的事, 不是画像标签】
过往发言 {n_comments} 条, 参与过 {n_posts} 个帖子
心理配置(九结分布, 由他本人的话逆推): {knots}
成本档倾向: {cost}  (连续成本分均值 {score}, 0=不动 3=高投入)
真实行为频率(他过去每条发言里出现的比例):
{behavior}
他过去回复楼主 {replied_to_op} 次, 累计得赞 {ups}

【他会看到的内容】
{post}

只判这一个人, 不判"一般受众"。他的行为频率是硬约束: 一个从不报型号的人不会突然报型号。

只输出JSON:
{{"will_engage": true/false,
  "engage_prob": 0到1,
  "predicted_actions": ["从 named_specific_model/asked_question/described_own_situation_in_detail/challenged_or_confronted/offered_help_or_correction/thanks_only 里选, 可多选, 不动则空数组"],
  "reason": "一句话, 必须引用他的某个具体特征"}}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-posts", type=int, default=2, help="只模拟跨帖主体(负例污染最小)")
    ap.add_argument("--out", default=f"{ROOT}/subjects/simulation.json")
    A = ap.parse_args()
    snap = json.load(open(f"{ROOT}/accuracy/data/reddit_snapshot_20260809.json", encoding="utf-8"))
    cards = json.load(open(f"{ROOT}/subjects/subject_cards.json", encoding="utf-8"))
    subs = {w: c for w, c in cards.items() if c["n_posts"] >= A.min_posts and w not in BOTS}
    posts = {pid: p for pid, p in snap["posts"].items()}
    truth = {}
    for pid, p in posts.items():
        for c in p["comments"]:
            truth.setdefault((c["author"], pid), []).append(c)
    print(f"主体 {len(subs)} × 帖 {len(posts)} = {len(subs)*len(posts)} 格", flush=True)

    jobs = [(w, pid) for w in subs for pid in posts]

    def one(job):
        w, pid = job
        c = subs[w]
        beh = "\n".join(f"  {k}: {v:.0%}" for k, v in c["behavior_rate"].items())
        body = (posts[pid]["title"] + "\n\n" + (posts[pid].get("selftext") or ""))[:2500]
        p = TMPL.format(n_comments=c["n_comments"], n_posts=c["n_posts"],
                        knots=json.dumps(c["knots"], ensure_ascii=False),
                        cost=json.dumps(c["cost_tier_dist"], ensure_ascii=False),
                        score=c["cost_score_mean"], behavior=beh,
                        replied_to_op=c["replied_to_op"], ups=c["ups_total"], post=body)
        content, _ = call_model("M3", p, temperature=0.0)
        d = extract_json_robust(content, log_note="subj_sim") or {}
        act = truth.get((w, pid), [])
        real_actions = sorted({a for cc in act for a in ACTIONS
                               if (cc.get("facts") or {}).get(a)}) if act else []
        return {"subject": w, "post": pid,
                "pred_engage": bool(d.get("will_engage")), "prob": d.get("engage_prob"),
                "pred_actions": d.get("predicted_actions") or [], "reason": d.get("reason", "")[:120],
                "real_engage": bool(act), "real_n": len(act), "real_actions": real_actions}

    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(one, jobs))

    tp = sum(1 for r in rows if r["pred_engage"] and r["real_engage"])
    tn = sum(1 for r in rows if not r["pred_engage"] and not r["real_engage"])
    n = len(rows)
    base = max(sum(1 for r in rows if r["real_engage"]), sum(1 for r in rows if not r["real_engage"])) / n
    acc = (tp + tn) / n
    res = {"n": n, "accuracy": round(acc, 3), "majority_baseline": round(base, 3),
           "lift": round(acc - base, 3),
           "confusion": dict(collections.Counter(f"{'预动' if r['pred_engage'] else '预不动'}→"
                                                 f"{'实动' if r['real_engage'] else '实不动'}" for r in rows)),
           "criteria": "命中率 > 多数基线 ⇒ 主体模拟有增益; 否则如实登记为无增益",
           "pass": acc > base, "rows": rows}
    json.dump(res, open(A.out, "w"), ensure_ascii=False, indent=1)
    print(f"命中 {acc:.1%} vs 基线 {base:.1%} → 增益 {acc-base:+.3f}  {'✅' if acc>base else '❌'}", flush=True)
    print(json.dumps(res["confusion"], ensure_ascii=False))


if __name__ == "__main__":
    main()
