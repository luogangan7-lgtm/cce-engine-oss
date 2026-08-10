#!/usr/bin/env python3
"""任务②的两个对照 —— 判死或洗清那个 100%。

t2 结果: A裸改写胜原版 89.7% / B诊断改写胜原版 100.0%(58/58) / B胜A 91.4%。
58/58 全胜在噪声领域几乎总是假象。三条怀疑:
  ① 满分不可信
  ② 裁判被用在分布外——它的 73~77% 是在【真帖 vs 真帖】上校准的,
     现在judge【真帖 vs LLM改写】, 可能只是在识别"这段被润色过"
  ③ 同模型自偏好(A臂也是 M3 改写、也赢原版 89.7%)

C1 空转对照: 只改措辞不改结构(同义改写, 长度一致, 信息不增不减) vs 原版。
   若裁判仍压倒性偏好空转版 ⇒ 它只是在偏好 LLM 文本, t2 全部结论作废。
C2 会话内校准复核: 真帖 vs 真帖(已知赞数差>=3倍), 同一裁判同一 prompt。
   若真帖对上仍 73~77% 而真帖-vs-改写是 100% ⇒ 坐实分布外。

判据(预注册):
  C1 胜率 >= 0.75 ⇒ 裁判偏好 LLM 文本本身, t2 作废
  C1 胜率 ~0.5    ⇒ 裁判没有文本风格偏好, t2 的 B>A 可信度提高
"""
import os, sys, json, math, random
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from concurrent.futures import ThreadPoolExecutor
from exp_crossmodel_desire import call_model
from exp_v4_full_validation import extract_json_robust

PARA = """把下面这段 r/HearingAids 帖子做**同义改写**: 逐句换措辞, 但
- 不增加任何信息, 不删任何信息
- 不改变结构与段落顺序, 不加钩子, 不加提问, 不加结尾号召
- 字数与原文相差不超过 5%
只输出改写后的正文。

【原文】
{body}"""

JUDGE = """你是内容效果预测器。同一个板块(r/HearingAids)的两篇帖子, 发布时间接近。
预测哪一篇拿到的赞更多。只看标题与正文, 不做任何外部假设。

【A】
{A}

【B】
{B}

只输出JSON: {{"winner":"A"或"B","margin":0到100,"reason":"一句话"}}"""


def judge(x, y, flip):
    a, b = (y, x) if flip else (x, y)
    c, _ = call_model("M3", JUDGE.format(A=a[:1800], B=b[:1800]), temperature=0.0)
    d = extract_json_robust(c, log_note="t2c") or {}
    w = d.get("winner")
    return None if not w else ((w == "B") if flip else (w == "A"))


def main():
    posts = json.load(open(f"{ROOT}/accuracy/data/hearingaids_others_20260809.json",
                           encoding="utf-8"))["posts"]
    rng = random.Random(20260810)

    # ── C1 空转对照 ──
    low = [p for p in posts if p["ups"] <= 2 and 60 <= len(p["selftext"].split()) <= 300]
    rng.shuffle(low); low = low[:45]
    print(f"C1 空转对照: {len(low)} 篇", flush=True)

    def c1(i_p):
        i, p = i_p
        body = (p["title"] + "\n\n" + p["selftext"])[:2200]
        c, _ = call_model("M3", PARA.format(body=body), temperature=0.0)
        para = (c or "").strip()
        if len(para.split()) < 20: return None
        r = judge(para, body, i % 2 == 1)
        return None if r is None else {"id": p["id"], "空转胜原": r,
                                       "w0": len(body.split()), "wp": len(para.split())}
    with ThreadPoolExecutor(max_workers=6) as ex:
        R1 = [r for r in ex.map(c1, list(enumerate(low))) if r]

    # ── C2 会话内校准复核 ──
    ev = json.load(open(f"{ROOT}/accuracy/external_validity.json", encoding="utf-8"))
    P = {p["id"]: p for p in posts}
    pairs = [r for r in ev["rows"] if r["hi"] in P and r["lo"] in P][:40]
    print(f"C2 会话内校准: {len(pairs)} 组真帖配对", flush=True)
    body = lambda p: (p["title"] + "\n\n" + (p.get("selftext") or ""))[:1800]

    def c2(i_pr):
        i, pr = i_pr
        r = judge(body(P[pr["hi"]]), body(P[pr["lo"]]), i % 2 == 1)
        return None if r is None else {"hi": pr["hi"], "correct": r}
    with ThreadPoolExecutor(max_workers=6) as ex:
        R2 = [r for r in ex.map(c2, list(enumerate(pairs))) if r]

    def rate(v):
        n = len(v); a = sum(v) / n if n else 0
        se = math.sqrt(a * (1 - a) / n) if n else 0
        return {"n": n, "率": round(a, 4), "ci95": [round(a - 1.96 * se, 4), round(a + 1.96 * se, 4)]}
    S1 = rate([r["空转胜原"] for r in R1])
    S2 = rate([r["correct"] for r in R2])
    verdict = ("裁判偏好 LLM 文本本身 ⇒ t2 全部结论作废" if S1["率"] >= 0.75 else
               "裁判无明显文本风格偏好 ⇒ t2 的 B>A 可信度提高" if S1["率"] <= 0.6 else
               "介于两者之间 ⇒ t2 结论需打折, 不可直接采信")
    res = {"gate": "任务②对照", "C1_空转胜原版": S1, "C2_会话内真帖校准": S2,
           "字数": {"原": round(sum(r["w0"] for r in R1) / len(R1)),
                   "空转": round(sum(r["wp"] for r in R1) / len(R1))},
           "历史校准参照": {"external_validity": 0.7083, "twoarm_A": 0.7167, "twoarm2_A": 0.7727,
                        "t1_A": 0.7368},
           "t2待检结论": {"A裸改写胜原": 0.897, "B诊断改写胜原": 1.0, "B胜A": 0.914},
           "判据": "C1>=0.75 ⇒ t2作废; C1<=0.6 ⇒ t2可信度提高",
           "verdict": verdict, "rows_c1": R1, "rows_c2": R2}
    json.dump(res, open(f"{ROOT}/accuracy/t2_control.json", "w"), ensure_ascii=False, indent=1)
    print(f"\nC1 空转版胜原版   {S1['率']:.1%} CI{S1['ci95']} n={S1['n']}  (字数 原{res['字数']['原']} 空转{res['字数']['空转']})")
    print(f"C2 真帖对准确率   {S2['率']:.1%} CI{S2['ci95']} n={S2['n']}  (历史 70.8/71.7/77.3/73.7%)")
    print(f"\n>>> {verdict}")


main()
