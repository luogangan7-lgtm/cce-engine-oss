#!/usr/bin/env python3
"""情境敏感度 —— 同一条内容 × 逐面翻取值, 量下游位移。

2026-08-09。用户: "不同情景跑出来的肯定是不一样的"。既然必然不同, 该测的就不是
"有没有影响", 是"每一面影响多大"。判据也随之改:
    不是「这面重不重要」, 是「重要 × 能不能知道」
      影响大+能知道 -> 必须声明(不声明=把已知信息扔了)
      影响大+不能知道 -> 必须建成分布做分流(单点必错)
      影响小 -> 可省

受控设计: 内容不变、默认情境不变, 每次只翻一个面的取值, 量 情绪/需求/行动 三层的
JS 位移。再算该面各取值之间的两两距离——取值间距离小的应合并, 决定该分几路。
这测的正是【生产时的用法】(生产时情境是声明的, 不是猜的)。
"""
import os, sys, json, math, argparse, itertools, collections, statistics as st
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from concurrent.futures import ThreadPoolExecutor
from exp_crossmodel_desire import call_model, DESIRES
from exp_v4_causal_chain import EMOTIONS, ACTIONS
from exp_v4_full_validation import extract_json_robust

CTX = json.load(open(f"{ROOT}/config/context_taxonomy.json", encoding="utf-8"))
FACETS = {f["key"]: f for f in CTX["facets"]}
NEEDS = json.load(open(f"{ROOT}/config/need_taxonomy.json", encoding="utf-8"))["controlled_keys"]
DEFAULT = {"进程位置": "在找方案", "触发事件": "无明显触发", "关系位置": "首次接触",
           "身体状态": "长期困扰", "资源状态": "未提及", "社会在场": "匿名",
           "场景类型": "未知", "信息环境": "推荐流", "情绪余温": "首轮无余温"}

TMPL = """你是心理配置预测器。给定一段【内容】和读者当前所处的【情境】,
预测这段内容会在这个情境下的读者身上激活出什么。全部给分布(权重和=1), 不许只给单个标签。

【情境】(这是已知条件, 不要质疑也不要改写)
{ctx}

【内容】
{body}

【情绪 13 类】{E}
【需求 17 类】{N}
【行动 7 类】{A}

只输出JSON: {{"emotion":{{"类名":权重}},"need":{{"类名":权重}},"action":{{"类名":权重}}}}"""


def norm(d):
    d = {k: float(v) for k, v in (d or {}).items() if isinstance(v, (int, float)) and v > 0}
    t = sum(d.values())
    return {k: v / t for k, v in d.items()} if t else {}


def js(p, q):
    H = lambda d: sum(-v * math.log(v, 2) for v in d.values() if v > 0)
    m = {k: (p.get(k, 0) + q.get(k, 0)) / 2 for k in set(p) | set(q)}
    return H(m) - (H(p) + H(q)) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=f"{ROOT}/accuracy/context_sensitivity.json")
    A = ap.parse_args()
    CONTENTS = {
        "A座位": "Can't hear the person across the table? Your hearing aid's mic faces forward. It's turning down whatever's behind you. Put the kitchen behind you, not your friend.",
        "B蓝牙": "Your aids won't do calls on Android? There are four kinds of Bluetooth on that spec sheet. Only one carries your voice out. Ask which before you buy.",
        "C壳体": "Why are your tiny aids dead by dinner? A shell one size up holds double the battery. That's the whole trade. They just don't print it.",
        "D对比": "OTC and prescription aids often share the same receivers and chip families. You're not paying for better parts. You're paying for someone measuring the fit in your ear.",
    }
    jobs = []
    for cname, body in CONTENTS.items():
        jobs.append((cname, "BASE", "BASE", dict(DEFAULT)))
        for fk, f in FACETS.items():
            for v in f["values"]:
                if v == DEFAULT[fk]:
                    continue
                cfg = dict(DEFAULT); cfg[fk] = v
                jobs.append((cname, fk, v, cfg))
    print(f"内容 {len(CONTENTS)} × 情境配置 → 共 {len(jobs)} 次调用", flush=True)

    def one(j):
        cname, fk, v, cfg = j
        ctx = "\n".join(f"  {k}: {x}" for k, x in cfg.items())
        p = TMPL.format(ctx=ctx, body=CONTENTS[cname], E=EMOTIONS, N=NEEDS, A=ACTIONS)
        c, _ = call_model("M3", p, temperature=0.0)
        d = extract_json_robust(c, log_note="ctx_sens")
        if not isinstance(d, dict): return None
        return {"content": cname, "facet": fk, "value": v,
                "情绪": norm(d.get("emotion")), "需求": norm(d.get("need")), "行动": norm(d.get("action"))}

    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = [r for r in ex.map(one, jobs) if r and r["情绪"] and r["行动"]]
    print(f"成功 {len(rows)}/{len(jobs)}\n", flush=True)

    base = {r["content"]: r for r in rows if r["facet"] == "BASE"}
    LY = ["情绪", "需求", "行动"]
    sens = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        if r["facet"] == "BASE" or r["content"] not in base: continue
        for L in LY:
            sens[r["facet"]][L].append(js(base[r["content"]][L], r[L]))

    rep = []
    for fk in FACETS:
        if fk not in sens: continue
        row = {"面": fk, "可读出": str(FACETS[fk]["readable_from_text"])}
        for L in LY:
            v = sens[fk][L]
            row[L] = round(st.mean(v), 4) if v else None
        row["平均位移"] = round(st.mean([row[L] for L in LY if row[L] is not None]), 4)
        # 取值间两两距离 -> 该分几路
        pairs = []
        for cname in CONTENTS:
            vs = [r for r in rows if r["content"] == cname and r["facet"] == fk]
            for a, b in itertools.combinations(vs, 2):
                pairs.append((f"{a['value']}|{b['value']}", js(a["行动"], b["行动"])))
        agg = collections.defaultdict(list)
        for k, d in pairs: agg[k].append(d)
        pm = sorted(((k, round(st.mean(v), 4)) for k, v in agg.items()), key=lambda x: -x[1])
        row["取值间最远"] = pm[:2]; row["取值间最近"] = pm[-2:]
        rep.append(row)
    rep.sort(key=lambda r: -(r["平均位移"] or 0))

    print(f"{'面':8s} {'可读出':8s} {'情绪':>7s} {'需求':>7s} {'行动':>7s} {'平均':>7s}")
    for r in rep:
        print(f"{r['面']:8s} {r['可读出']:8s} {r['情绪']:7.4f} {r['需求']:7.4f} "
              f"{r['行动']:7.4f} {r['平均位移']:7.4f}")

    def bucket(r):
        big = r["平均位移"] >= (st.median([x["平均位移"] for x in rep]))
        known = str(r["可读出"]) in ("True", "partial")
        return ("必须声明" if (big and known) else "必须建分布做分流" if big else
                "可省(影响小)" if known else "可忽略")
    print(f"\n{'面':8s} 判定")
    for r in rep: print(f"{r['面']:8s} {bucket(r)}")

    res = {"gate": "情境敏感度", "n_calls": len(rows), "默认情境": DEFAULT,
           "逐面": rep, "判定": {r["面"]: bucket(r) for r in rep},
           "判据": "影响大×能知道→必须声明; 影响大×不能知道→必须建分布分流; 影响小→可省",
           "rows": rows}
    json.dump(res, open(A.out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
