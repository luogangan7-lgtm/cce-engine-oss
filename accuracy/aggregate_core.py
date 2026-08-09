#!/usr/bin/env python3
"""正确的聚合读出 —— 逐条判后聚合, 绝不把 N 条拼成一段。

2026-08-09 实证: 用单条发言读"人的欲望基线"读不出来——同一个人前后两轮的欲望读出
差异(组内 JS 0.2721) 与陌生人之间(组间 0.2856) 几乎一样, 比值 0.95。
原因: prompt 问的是"这段发言的五层", 读的是文本不是人。
故 s5(受众逆推) 与主体基线读出必须走同一条正确路径: 逐条读 -> 聚合。
"""
import os, sys, json, math, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from concurrent.futures import ThreadPoolExecutor
from exp_crossmodel_desire import call_model, DESIRES
from exp_v4_causal_chain import EMOTIONS, ACTIONS
from exp_v4_full_validation import extract_json_robust

NEEDS = json.load(open(f"{ROOT}/config/need_taxonomy.json", encoding="utf-8"))["controlled_keys"]
_KT = json.load(open(f"{ROOT}/config/knot_taxonomy.json", encoding="utf-8"))
KNOTS = [k["key"] for k in _KT["knots"]]
KNOT_BRIEF = "; ".join(f"{k['key']}={k['name']}" for k in _KT["knots"])
TMPL = """读出这段发言体现的四层配置, 全部给分布(权重和=1), 只列权重>=0.08 的。
【欲望9】{D}
【情绪13】{E}
【需求17】{N}
【行动7】{A}
【九结9】{K}
【发言】
{body}
只输出JSON: {{"desire":{{}},"emotion":{{}},"need":{{}},"action":{{}},"knot":{{}}}}"""


def norm(d):
    d = {k: float(v) for k, v in (d or {}).items() if isinstance(v, (int, float)) and v > 0}
    t = sum(d.values())
    return {k: v / t for k, v in d.items()} if t else {}


def js(p, q):
    H = lambda x: sum(-v * math.log(v, 2) for v in x.values() if v > 0)
    m = {k: (p.get(k, 0) + q.get(k, 0)) / 2 for k in set(p) | set(q)}
    return H(m) - (H(p) + H(q)) / 2


def read_one(text):
    p = TMPL.format(D=DESIRES, E=EMOTIONS, N=NEEDS, A=ACTIONS, K=KNOT_BRIEF, body=text[:1200])
    c, _ = call_model("M3", p, temperature=0.0)
    d = extract_json_robust(c, log_note="agg_core")
    if not isinstance(d, dict): return None
    o = {"欲望": norm(d.get("desire")), "情绪": norm(d.get("emotion")),
         "需求": norm(d.get("need")), "行动": norm(d.get("action")),
         "九结": norm({k: v for k, v in (d.get("knot") or {}).items() if k in KNOTS})}
    return o if all(o[L] for L in ("欲望", "情绪", "需求", "行动")) else None


def read_many(texts, workers=8):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return [r for r in ex.map(read_one, texts) if r]


def aggregate(reads):
    """逐条读出 -> 聚合成一个主体/人群的分布。这是 s5 该走的路。"""
    if not reads: return None
    out = {}
    for L in ("欲望", "情绪", "需求", "行动", "九结"):
        agg = collections.defaultdict(float)
        for r in reads:
            for k, v in r[L].items(): agg[k] += v / len(reads)
        out[L] = norm(dict(agg))
    out["_n"] = len(reads)
    return out
