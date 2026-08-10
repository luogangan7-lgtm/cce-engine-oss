#!/usr/bin/env python3
"""任务② 生成侧 —— CCE 诊断指导改写, 用【独立已校准的判决器】当裁判。

为什么值得做: 四次预测侧尝试全负(九结-.033 / 稳定层-.023 / 外部先验-.062 / 画像判负),
但 CCE 是"认知因果引擎", 设计目的是解释为什么, 而解释的价值在**指导生成**不在排序。
今天测的全是排序。生成侧已有真实但未受控的正面信号: 站外 10 条投放按 pain_seek
playbook 写 → 5 条楼主亲回 → 2 条可观测行为改变。本测把它做成受控实验。

三臂:
  原版   低赞帖原文(ups 处于低分位, 即"需要改"的对象)
  A 臂   裸 M3 改写("改得更能拿赞"), 不给任何 CCE 结构
  B 臂   先跑 CCE 诊断(九结+欲望+需求+对应 playbook), 再按诊断改写
裁判: 与 external_validity 完全同一个成对 prompt(已知准确率 73~77%), 裁判**不知道**
      哪篇是改写版; 位置一半反位消位置偏; 三组对决 A-vs-原 / B-vs-原 / B-vs-A。
防作弊: 改写字数限制在原文 ±20%, 不许靠加长取胜。

判负预注册: B-vs-A 胜率的 95%CI 下界 <= 0.5 ⇒ CCE 指导改写相对裸改写无增量。
已知 caveat(登记不掩盖): 裁判与改写同为 M3, 存在同模型自偏好风险; 缓解=裁判 prompt
不提改写、两版均以纯文本呈现, 但风险不能完全排除。
"""
import os, sys, json, math, random, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from concurrent.futures import ThreadPoolExecutor
from exp_crossmodel_desire import call_model, DESIRES
from exp_v4_full_validation import extract_json_robust

TAXO = json.load(open(f"{ROOT}/config/knot_taxonomy.json", encoding="utf-8"))
PLAYBOOK = {k["key"]: k.get("playbook", "") for k in TAXO["knots"]}
KBRIEF = "; ".join(f"{k['key']}={k['name']}" for k in TAXO["knots"])
NEEDS = json.load(open(f"{ROOT}/config/need_taxonomy.json", encoding="utf-8"))["controlled_keys"]

DIAG = """你是内容诊断器。对下面这篇 r/HearingAids 帖子做诊断。
九结: {K}
欲望9: {D}
需求17: {N}

【帖子】
{body}

只输出JSON:
{{"knots":{{"结名":权重}},"desire":{{}},"need":{{}},
  "why_weak":"这篇为什么拿不到互动, 一句话, 必须指向具体的结/欲望/需求",
  "fix":"最该改的一处, 一句话可执行"}}"""

REW_A = """把下面这篇 r/HearingAids 帖子改写得更能拿到赞和评论。
保持事实与立场不变, 字数控制在 {lo}~{hi} 词。
只输出改写后的正文, 不要解释, 不要标题以外的任何标注。

【原文】
{body}"""

REW_B = """把下面这篇 r/HearingAids 帖子改写得更能拿到赞和评论。
保持事实与立场不变, 字数控制在 {lo}~{hi} 词。

【诊断】(由认知因果引擎给出)
  激活的结: {knots}
  主欲望: {desire}   主需求: {need}
  弱在哪: {why}
  最该改: {fix}
  对应 playbook: {pb}
按这份诊断改, 特别是执行 playbook 指出的动作。

只输出改写后的正文, 不要解释。

【原文】
{body}"""

JUDGE = """你是内容效果预测器。同一个板块(r/HearingAids)的两篇帖子, 发布时间接近。
预测哪一篇拿到的赞更多。只看标题与正文, 不做任何外部假设。

【A】
{A}

【B】
{B}

只输出JSON: {{"winner":"A"或"B","margin":0到100,"reason":"一句话"}}"""


def gen(p, maxtok=2000):
    c, _ = call_model("M3", p, temperature=0.0)
    return (c or "").strip()


def judge(x, y, flip):
    a, b = (y, x) if flip else (x, y)
    c, _ = call_model("M3", JUDGE.format(A=a[:1800], B=b[:1800]), temperature=0.0)
    d = extract_json_robust(c, log_note="t2j") or {}
    w = d.get("winner")
    if not w: return None
    return (w == "B") if flip else (w == "A")     # True = x 胜


def main():
    posts = json.load(open(f"{ROOT}/accuracy/data/hearingaids_others_20260809.json",
                           encoding="utf-8"))["posts"]
    low = [p for p in posts if p["ups"] <= 2 and 60 <= len(p["selftext"].split()) <= 300]
    random.Random(20260810).shuffle(low)
    low = low[:60]
    print(f"低赞帖 {len(low)} 篇(ups<=2, 60~300词) —— 即'需要改'的对象", flush=True)

    def one(i_p):
        i, p = i_p
        body = (p["title"] + "\n\n" + p["selftext"])[:2200]
        w = len(p["selftext"].split()); lo, hi = int(w * .8), int(w * 1.2)
        d = extract_json_robust(gen(DIAG.format(K=KBRIEF, D=DESIRES, N=NEEDS, body=body)),
                                log_note="t2d") or {}
        kn = d.get("knots") or {}
        top = max(kn, key=kn.get) if kn else None
        ra = gen(REW_A.format(lo=lo, hi=hi, body=body))
        rb = gen(REW_B.format(lo=lo, hi=hi, body=body,
                              knots=json.dumps(kn, ensure_ascii=False),
                              desire=json.dumps(d.get("desire") or {}, ensure_ascii=False),
                              need=json.dumps(d.get("need") or {}, ensure_ascii=False),
                              why=d.get("why_weak", ""), fix=d.get("fix", ""),
                              pb=PLAYBOOK.get(top, "")[:160]))
        if len(ra.split()) < 20 or len(rb.split()) < 20:
            return None
        f = i % 2 == 1
        return {"id": p["id"], "ups": p["ups"], "top_knot": top,
                "why": d.get("why_weak", "")[:90], "fix": d.get("fix", "")[:90],
                "wA": len(ra.split()), "wB": len(rb.split()), "w0": w,
                "A胜原": judge(ra, body, f), "B胜原": judge(rb, body, f),
                "B胜A": judge(rb, ra, f)}

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = [r for r in ex.map(one, list(enumerate(low))) if r]
    print(f"完成 {len(rows)}\n", flush=True)

    def rate(k):
        v = [r[k] for r in rows if r[k] is not None]
        n = len(v); acc = sum(v) / n if n else 0
        se = math.sqrt(acc * (1 - acc) / n) if n else 0
        return {"n": n, "胜率": round(acc, 4),
                "ci95": [round(acc - 1.96 * se, 4), round(acc + 1.96 * se, 4)]}
    RA, RB, RBA = rate("A胜原"), rate("B胜原"), rate("B胜A")
    res = {"gate": "任务②生成侧·诊断指导改写",
           "A臂_裸改写_胜原版": RA, "B臂_CCE诊断改写_胜原版": RB,
           "主判_B胜A": RBA,
           "字数": {"原": round(sum(r["w0"] for r in rows) / len(rows)),
                   "A": round(sum(r["wA"] for r in rows) / len(rows)),
                   "B": round(sum(r["wB"] for r in rows) / len(rows))},
           "判据": "B胜A 的95%CI下界 > 0.5 ⇒ CCE 指导改写相对裸改写有增量",
           "pass": bool(RBA["ci95"][0] > 0.5),
           "caveat": "裁判与改写同为 M3, 存在同模型自偏好风险; 缓解=裁判不知情+纯文本呈现, 未完全排除",
           "诊断主结分布": dict(collections.Counter(r["top_knot"] for r in rows)),
           "rows": rows}
    json.dump(res, open(f"{ROOT}/accuracy/t2_rewrite.json", "w"), ensure_ascii=False, indent=1)
    print(f"A臂 裸改写 胜原版      {RA['胜率']:.1%} CI{RA['ci95']} n={RA['n']}")
    print(f"B臂 CCE诊断改写 胜原版 {RB['胜率']:.1%} CI{RB['ci95']} n={RB['n']}")
    print(f"主判 B 胜 A            {RBA['胜率']:.1%} CI{RBA['ci95']} n={RBA['n']}")
    print(f"字数 原{res['字数']['原']} A{res['字数']['A']} B{res['字数']['B']}")
    print(f">>> CCE 指导改写有增量: {res['pass']}")
    print(f"\n诊断主结分布: {res['诊断主结分布']}")
    for r in rows[:3]:
        print(f"  [{r['id']}] 弱在: {r['why']}")
        print(f"           最该改: {r['fix']}")


main()
