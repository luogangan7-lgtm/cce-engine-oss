#!/usr/bin/env python3
"""生成侧消融 —— 拆开 F1 的 B 臂, 定九结去留。

F1(run 31360516549) B臂 91.4% 胜 A臂, 但 B臂是【九结+欲望+需求+why_weak+fix+playbook】
打包给的, 拆不出谁的功劳。本测拆成四档:
  A  裸改写(无任何诊断)
  B1 只给 九结 + 对应 playbook
  B2 只给 欲望 + 需求
  B3 只给 why_weak + fix (诊断结论文本, 不给任何分类学)
  B4 全给 (= 原 F1 的 B 臂)

★关键对照是 B3: 若 B3 ≈ B4, 说明起作用的是"做了诊断"这个动作, 而不是九结这套分类学
  —— 那九结在生成侧也可以退役, CCE 的价值就落在"会诊断"而非"有分类学"。
判负预注册:
  B1 不显著优于 A ⇒ 九结在生成侧无独立贡献
  B4 不显著优于 B3 ⇒ 分类学相对纯诊断文本无增量, 九结与欲望需求表均可退役
裁判: 与 external_validity 同一成对 prompt(会话内实测 75.0%), 不知情, 一半反位。
改写长度锁 原文 ±20%, 且**加输出校验**: 超 1.5 倍即丢弃该条(2026-08-10 教训: 11/44
崩坏输出差点反转 C1 结论)。
"""
import os, sys, json, math, random, collections, itertools
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from concurrent.futures import ThreadPoolExecutor
from exp_crossmodel_desire import call_model, DESIRES
from exp_v4_full_validation import extract_json_robust

TAXO = json.load(open(f"{ROOT}/config/knot_taxonomy.json", encoding="utf-8"))
PB = {k["key"]: k.get("playbook", "") for k in TAXO["knots"]}
KB = "; ".join(f"{k['key']}={k['name']}" for k in TAXO["knots"])
NEEDS = json.load(open(f"{ROOT}/config/need_taxonomy.json", encoding="utf-8"))["controlled_keys"]

DIAG_BARE = """你是内容诊断器。对下面这篇 r/HearingAids 帖子做诊断。
不要套用任何既定框架或分类体系, 就凭你对这个板块和读者的理解直接判断。
【帖子】
{body}
只输出JSON: {{"why_weak":"这篇为什么拿不到互动, 一句话, 指向具体机制","fix":"最该改的一处, 一句话可执行"}}"""

DIAG = """你是内容诊断器。对下面这篇 r/HearingAids 帖子做诊断。
九结: {K}
欲望9: {D}
需求17: {N}
【帖子】
{body}
只输出JSON: {{"knots":{{}},"desire":{{}},"need":{{}},
 "why_weak":"这篇为什么拿不到互动, 一句话, 指向具体机制","fix":"最该改的一处, 一句话可执行"}}"""

BASE = """把下面这篇 r/HearingAids 帖子改写得更能拿到赞和评论。
保持事实与立场不变, 字数 {lo}~{hi} 词。只输出改写后的正文, 不要解释。
{extra}
【原文】
{body}"""

JUDGE = """你是内容效果预测器。同一个板块(r/HearingAids)的两篇帖子, 发布时间接近。
预测哪一篇拿到的赞更多。只看标题与正文, 不做任何外部假设。
【A】
{A}
【B】
{B}
只输出JSON: {{"winner":"A"或"B","margin":0到100,"reason":"一句话"}}"""


def gen(p):
    c, _ = call_model("M3", p, temperature=0.0)
    return (c or "").strip()


def judge(x, y, flip):
    a, b = (y, x) if flip else (x, y)
    c, _ = call_model("M3", JUDGE.format(A=a[:1800], B=b[:1800]), temperature=0.0)
    d = extract_json_robust(c, log_note="abl_j") or {}
    w = d.get("winner")
    return None if not w else ((w == "B") if flip else (w == "A"))


def main():
    posts = json.load(open(f"{ROOT}/accuracy/data/hearingaids_others_20260809.json",
                           encoding="utf-8"))["posts"]
    low = [p for p in posts if p["ups"] <= 2 and 60 <= len(p["selftext"].split()) <= 300]
    random.Random(20260810).shuffle(low); low = low[:45]
    print(f"低赞帖 {len(low)} 篇 · 四档改写 + 五组对决", flush=True)

    def one(i_p):
        i, p = i_p
        body = (p["title"] + "\n\n" + p["selftext"])[:2200]
        w = len(p["selftext"].split()); lo, hi = int(w*.8), int(w*1.2)
        d = extract_json_robust(gen(DIAG.format(K=KB, D=DESIRES, N=NEEDS, body=body)),
                                log_note="abl_d") or {}
        # B5: 诊断阶段完全不给分类学 —— 决定分类学最终去留的对照
        d5 = extract_json_robust(gen(DIAG_BARE.format(body=body)), log_note="abl_d5") or {}
        kn = d.get("knots") or {}
        top = max(kn, key=kn.get) if kn else None
        J = lambda x: json.dumps(x, ensure_ascii=False)
        EX = {
          "A":  "",
          "B1": f"\n【诊断】激活的结: {J(kn)}\n  对应 playbook: {PB.get(top,'')[:160]}\n按 playbook 指出的动作改。",
          "B2": f"\n【诊断】主欲望: {J(d.get('desire') or {})}  主需求: {J(d.get('need') or {})}\n按这两层指出的诉求改。",
          "B3": f"\n【诊断】弱在哪: {d.get('why_weak','')}\n  最该改: {d.get('fix','')}\n按这份诊断改。",
          "B5": f"\n【诊断】弱在哪: {d5.get('why_weak','')}\n  最该改: {d5.get('fix','')}\n按这份诊断改。",
          "B4": (f"\n【诊断】激活的结: {J(kn)}\n  主欲望: {J(d.get('desire') or {})}  主需求: {J(d.get('need') or {})}\n"
                 f"  弱在哪: {d.get('why_weak','')}\n  最该改: {d.get('fix','')}\n  对应 playbook: {PB.get(top,'')[:160]}\n按这份诊断改。"),
        }
        R = {}
        for k, ex in EX.items():
            t = gen(BASE.format(lo=lo, hi=hi, extra=ex, body=body))
            n = len(t.split())
            if n < 20 or n > w*1.5:      # 输出校验: 崩坏或超长即丢
                return None
            R[k] = t
        f = i % 2 == 1
        duels = {"B1vsA": ("B1","A"), "B2vsA": ("B2","A"), "B3vsA": ("B3","A"),
                 "B4vsA": ("B4","A"), "B4vsB3": ("B4","B3"), "B1vsB3": ("B1","B3"),
                 "B5vsA": ("B5","A"), "B3vsB5": ("B3","B5")}
        out = {"id": p["id"], "top_knot": top, "words": {k: len(v.split()) for k, v in R.items()}}
        for name, (x, y) in duels.items():
            out[name] = judge(R[x], R[y], f)
        return out

    with ThreadPoolExecutor(max_workers=5) as ex:
        rows = [r for r in ex.map(one, list(enumerate(low))) if r]
    print(f"完成 {len(rows)}/{len(low)} (含输出校验丢弃)\n", flush=True)

    def rate(k):
        v = [r[k] for r in rows if r.get(k) is not None]
        n = len(v); a = sum(v)/n if n else 0
        se = math.sqrt(a*(1-a)/n) if n else 0
        return {"n": n, "胜率": round(a,4), "ci95": [round(a-1.96*se,4), round(a+1.96*se,4)],
                "显著优于对手": bool(a-1.96*se > 0.5)}
    keys = ["B1vsA","B2vsA","B3vsA","B4vsA","B4vsB3","B1vsB3","B5vsA","B3vsB5"]
    S = {k: rate(k) for k in keys}
    res = {"gate": "生成侧消融·定九结去留", "n": len(rows), "各组": S,
           "预注册": {"九结无独立贡献": "B1vsA 不显著",
                    "分类学相对纯诊断无增量": "B4vsB3 不显著 ⇒ 九结与欲望需求表均可退役"},
           "判定": {
             "九结有独立贡献": S["B1vsA"]["显著优于对手"],
             "稳定层有独立贡献": S["B2vsA"]["显著优于对手"],
             "纯诊断文本有贡献": S["B3vsA"]["显著优于对手"],
             "分类学相对纯诊断有增量": S["B4vsB3"]["显著优于对手"],
             "无框架诊断也有效": S["B5vsA"]["显著优于对手"],
             "★分类学在诊断阶段有增量": S["B3vsB5"]["显著优于对手"]},
           "B5说明": ("B5 = 诊断阶段完全不给任何分类学, 直接问'为什么弱/该怎么改'。"
                    "B3vsB5 是决定分类学最终去留的对决: 不显著 ⇒ 连诊断阶段都不需要分类学, "
                    "CCE 的价值仅是'让模型做结构化诊断'这个动作本身。"),
           "对照_F1": {"B4vsA_原测": 0.914}, "rows": rows}
    json.dump(res, open(f"{ROOT}/accuracy/t2_ablation.json","w"), ensure_ascii=False, indent=1)
    print(f"{'对决':10s} {'胜率':>7s} {'95%CI':>18s} 显著")
    for k in keys:
        s = S[k]
        print(f"{k:10s} {s['胜率']:7.1%} [{s['ci95'][0]:.1%},{s['ci95'][1]:.1%}] {'✅' if s['显著优于对手'] else '❌'} n={s['n']}")
    print(f"\n判定: {json.dumps(res['判定'], ensure_ascii=False)}")


main()
