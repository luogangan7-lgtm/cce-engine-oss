#!/usr/bin/env python3
"""任务③ 主体画像 -> 预测该主体未来行为。对照基线: 历史频率查表。

折半信度已证聚合读出携带个体信息(欲望0.711/需求0.776)。本测问下一步:
这份画像能不能预测这个人**接下来**会做什么?
  前半段发言 -> 建画像 -> 预测后半段的行为类型
  基线 = 该人前半段的行为频率直接查表(2026-08-09 实测 精确75%/召回69%)
判负预注册: 画像法精确率与召回率均未超过查表基线 ⇒ 画像对行为预测无增量。
"""
import os, sys, json, math, random, collections, statistics as st
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "accuracy"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from concurrent.futures import ThreadPoolExecutor
from aggregate_core import read_many, aggregate
from exp_crossmodel_desire import call_model
from exp_v4_full_validation import extract_json_robust

ACTS = ["named_specific_model", "asked_question", "described_own_situation_in_detail",
        "challenged_or_confronted", "offered_help_or_correction", "thanks_only"]
FACT = """事实抽取器。只做客观抽取, 不做心理判断。这条评论:
{body}
只输出JSON: {{"named_specific_model":true/false,"asked_question":true/false,
"described_own_situation_in_detail":true/false,"challenged_or_confronted":true/false,
"offered_help_or_correction":true/false,"thanks_only":true/false}}"""
PRED = """根据一个人的【心理画像】(由他过去发言逐条读出后聚合而得), 预测他下一条发言会有哪些行为。
画像:
  欲望 {D}
  需求 {N}
  情绪 {E}
  行动 {A}
可选行为: {acts}
只输出JSON: {{"predicted":["行为名..."]}}"""


def facts(t):
    c, _ = call_model("M3", FACT.format(body=t[:900]), temperature=0.0)
    d = extract_json_robust(c, log_note="t3f")
    return {k: bool((d or {}).get(k)) for k in ACTS} if isinstance(d, dict) else None


U = json.load(open(f"{ROOT}/accuracy/data/hearingaids_regulars_20260809.json",
                   encoding="utf-8"))["users"]
rng = random.Random(20260810)
people = {w: [c["b"] for c in v if len(c["b"].split()) >= 12] for w, v in U.items()}
people = {w: v for w, v in people.items() if len(v) >= 8}
print(f"{len(people)} 人, 每人前4条建画像 / 后4条作真值", flush=True)

rows = []
for w, txts in people.items():
    s = txts[:]; rng.shuffle(s); s = s[:8]
    first, later = s[:4], s[4:]
    prof = aggregate(read_many(first))
    if not prof: continue
    with ThreadPoolExecutor(max_workers=6) as ex:
        f_first = [x for x in ex.map(facts, first) if x]
        f_later = [x for x in ex.map(facts, later) if x]
    if not f_first or not f_later: continue
    truth = {a for a in ACTS if any(f[a] for f in f_later)}
    lookup = {a for a in ACTS if sum(f[a] for f in f_first) / len(f_first) >= 0.5}
    J = lambda d: json.dumps({k: round(v, 2) for k, v in list(d.items())[:5]}, ensure_ascii=False)
    c, _ = call_model("M3", PRED.format(D=J(prof["欲望"]), N=J(prof["需求"]), E=J(prof["情绪"]),
                                        A=J(prof["行动"]), acts=ACTS), temperature=0.0)
    d = extract_json_robust(c, log_note="t3p") or {}
    pred = {a for a in (d.get("predicted") or []) if a in ACTS}
    rows.append({"who": w, "truth": sorted(truth), "画像预测": sorted(pred), "查表基线": sorted(lookup)})
    print(f"  {w}: 真值{len(truth)} 画像{len(pred)} 查表{len(lookup)}", flush=True)

def prf(key):
    tp = sum(len(set(r[key]) & set(r["truth"])) for r in rows)
    fp = sum(len(set(r[key]) - set(r["truth"])) for r in rows)
    fn = sum(len(set(r["truth"]) - set(r[key])) for r in rows)
    p = tp/(tp+fp) if tp+fp else 0; rc = tp/(tp+fn) if tp+fn else 0
    return {"精确": round(p, 3), "召回": round(rc, 3),
            "F1": round(2*p*rc/(p+rc), 3) if p+rc else 0}
A, B = prf("画像预测"), prf("查表基线")
res = {"gate": "任务③画像->未来行为", "n_people": len(rows), "画像法": A, "查表基线": B,
       "pass": bool(A["精确"] > B["精确"] and A["召回"] > B["召回"]),
       "判负预注册": "精确与召回均未超查表基线 ⇒ 画像对行为预测无增量",
       "历史参照": {"主体模拟时的查表基线": {"精确": 0.75, "召回": 0.69}}, "rows": rows}
json.dump(res, open(f"{ROOT}/accuracy/t3_profile.json", "w"), ensure_ascii=False, indent=1)
print(f"\n画像法   精确{A['精确']} 召回{A['召回']} F1{A['F1']}")
print(f"查表基线 精确{B['精确']} 召回{B['召回']} F1{B['F1']}")
print(f">>> 画像有增量: {res['pass']}")
