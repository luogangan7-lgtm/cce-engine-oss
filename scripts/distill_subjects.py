#!/usr/bin/env python3
"""主体蒸馏 —— 把一个人的 N 条历史压成一张定长卡, 而不是堆原文。

2026-08-09。用户: "构建主体的时候记得把数据进行蒸馏"。
不蒸馏的后果: 一个人 83 条评论直接塞进 prompt = 几万 token, 既贵又噪; 而且卡的大小
随发言数变化, 主体之间不可比、无法批量喂进模拟。

蒸馏后每张卡定长(目标 <1.5KB), 无论此人发过 8 条还是 83 条。四层:
  L1 统计层  条数/跨话题数/时间跨度/得赞/层深/OP率  —— 直接算, 零模型成本
  L2 实体层  提到过的品牌与型号、平台、术语密度   —— 正则抽取, 零模型成本
  L3 心理层  九结分布                             —— 逐条判后聚合(不拼成一段)
  L4 语义层  角色/反复痛点/已试过什么/轨迹        —— 模型蒸馏一次, 输出结构化字段
  证据锚    2~3 条原话引用, 不存全文

用法: distill_subjects.py [--max-users N] [--l3] [--l4]
"""
import os, re, sys, json, argparse, collections, statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

SRC = f"{ROOT}/accuracy/data/hearingaids_regulars_20260809.json"
BRAND = (r"phonak|oticon|resound|widex|signia|starkey|unitron|jabra|sony|eargo|lexie|audien|"
         r"nuheara|bose|kirkland|philips|rexton|beltone|costco|sonova|demant|hearing ?tracker")
SERIES = (r"paradise|lumity|audeo|aud[eé]o|naida|sphere|infinio|nexia|omnia|intent|more\b|real\b|opn|"
          r"xceed|zircon|quattro|linx|vivia|smart ?ic|moment|evoke|allure|silk|pure|motion|insio|"
          r"styletto|edge|genesis|livio|evolv|ks ?\d|9040|9050|7040|i2400|slim ?rt")
PLAT = r"iphone|ios\b|android|pixel|samsung|galaxy|windows|mac\b|ipad"
TERM = (r"\b(rem|real ear|audiogram|compression|wdrc|feedback|occlusion|receiver|ric\b|bte\b|itc\b|cic\b|"
        r"telecoil|t-?coil|le audio|asha|mfi|bluetooth classic|gain|frequency lowering|dome|mold)\b")


def l1(rows):
    ups = [r["ups"] for r in rows]
    ts = [r["t"] for r in rows]
    return {"n": len(rows), "threads": len(({r["p"] for r in rows})),
            "span_days": round((max(ts) - min(ts)) / 86400) if len(ts) > 1 else 0,
            "ups_total": sum(ups), "ups_median": st.median(ups),
            "words_median": int(st.median(len(r["b"].split()) for r in rows))}


def l2(rows):
    txt = " ".join(r["b"] for r in rows).lower()
    brands = sorted(set(re.findall(BRAND, txt)))
    series = sorted(set(re.findall(SERIES, txt)))
    plats = sorted(set(re.findall(PLAT, txt)))
    terms = collections.Counter(m if isinstance(m, str) else m[0] for m in re.findall(TERM, txt))
    return {"brands": brands[:8], "series": series[:8], "platforms": plats[:5],
            "top_terms": [k for k, _ in terms.most_common(6)],
            "term_density": round(sum(terms.values()) / max(len(txt.split()), 1) * 1000, 2)}


def anchors(rows, k=3):
    """证据锚: 取最长的与最高赞的, 各截 160 字"""
    by_ups = sorted(rows, key=lambda r: -r["ups"])[:2]
    by_len = sorted(rows, key=lambda r: -len(r["b"]))[:2]
    seen, out = set(), []
    for r in by_ups + by_len:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        out.append({"ups": r["ups"], "quote": " ".join(r["b"].split())[:160]})
        if len(out) >= k:
            break
    return out


L4_TMPL = """你在蒸馏一个真实用户的历史发言, 产出一张定长画像卡。只写发言里有依据的内容,
不许推测、不许补全、不许写"可能/也许"。没依据的字段填 null。

【此人在 r/HearingAids 的发言】共 {n} 条, 跨 {threads} 个话题, 时间跨度 {span} 天
{sample}

只输出JSON:
{{"role": "user|audiologist|HIS|diy_tinkerer|shopper|caregiver|unclear",
  "role_evidence": "支撑该判断的逐字引句, 20字内",
  "recurring_pain": ["反复出现的具体痛点, 最多3条, 每条<=12字"],
  "already_tried": ["他自述试过的做法, 最多3条, 每条<=12字"],
  "stance": "他对厂商/验配师/OTC 的一贯态度, 一句话",
  "arc": "有没有从求助转向给建议之类的轨迹变化, 没有就填 none",
  "what_would_move_him": "什么样的内容最可能让他动作, 一句话, 必须由其历史行为支撑"}}"""


def l3_knots(rows, sample_n=12):
    """九结: 逐条判后聚合。绝不把 N 条拼成一段当一个人判——那正是 s5 的错。"""
    from concurrent.futures import ThreadPoolExecutor
    sys.path.insert(0, os.path.join(ROOT, "accuracy"))
    import run_gates as G
    pick = sorted(rows, key=lambda r: -len(r["b"]))[:sample_n]
    with ThreadPoolExecutor(max_workers=6) as ex:
        out = list(ex.map(G.annot_dist, [("MiniMax-M3", {"id": r["id"], "b": r["b"]}) for r in pick]))
    agg = collections.defaultdict(float)
    got = [d for _, d in out if d]
    for d in got:
        for k, w in d.items():
            agg[k] += w / len(got)
    return {"n_scored": len(got), "knots": {k: round(v, 3) for k, v in
                                            sorted(agg.items(), key=lambda x: -x[1])}}


def l4_semantic(u, rows, sample_n=14):
    from exp_crossmodel_desire import call_model
    from exp_v4_full_validation import extract_json_robust
    pick = sorted(rows, key=lambda r: -len(r["b"]))[:sample_n]
    sample = "\n".join(f"- [{r['ups']:+d}] " + " ".join(r["b"].split())[:220] for r in pick)
    ts = [r["t"] for r in rows]
    p = L4_TMPL.format(n=len(rows), threads=len({r["p"] for r in rows}),
                       span=round((max(ts) - min(ts)) / 86400) if len(ts) > 1 else 0, sample=sample)
    c, _ = call_model("M3", p, temperature=0.0)
    return extract_json_robust(c, log_note="l4_distill") or {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-users", type=int, default=0)
    ap.add_argument("--out", default=f"{ROOT}/subjects/distilled_cards.json")
    ap.add_argument("--l3", action="store_true", help="跑九结(逐条判后聚合)")
    ap.add_argument("--l4", action="store_true", help="跑语义蒸馏")
    A = ap.parse_args()
    users = json.load(open(SRC, encoding="utf-8"))["users"]
    items = sorted(users.items(), key=lambda x: -len(x[1]))
    if A.max_users:
        items = items[:A.max_users]
    cards = {}
    for u, rows in items:
        c = {"l1_stats": l1(rows), "l2_entities": l2(rows), "anchors": anchors(rows)}
        if A.l3:
            c["l3_knots"] = l3_knots(rows)
        if A.l4:
            c["l4_semantic"] = l4_semantic(u, rows)
        cards[u] = c
        print(f"  蒸馏 {u} ({len(rows)}条)", flush=True)
    os.makedirs(os.path.dirname(A.out), exist_ok=True)
    json.dump(cards, open(A.out, "w"), ensure_ascii=False, indent=1)
    sizes = [len(json.dumps(c, ensure_ascii=False)) for c in cards.values()]
    raw = {u: sum(len(r["b"]) for r in users[u]) for u in cards}
    print(f"蒸馏 {len(cards)} 张卡 → {A.out}")
    print(f"卡大小 中位 {int(st.median(sizes))}B 最大 {max(sizes)}B  (目标<1500B)")
    print(f"压缩比 原文中位 {int(st.median(raw.values()))}B → 卡中位 {int(st.median(sizes))}B "
          f"= {st.median(raw.values())/st.median(sizes):.0f}:1\n")
    for u, c in list(cards.items())[:6]:
        s, e = c["l1_stats"], c["l2_entities"]
        print(f"  {u[:20]:20s} {s['n']:3d}条/{s['threads']:2d}话题/{s['span_days']:3d}天 "
              f"赞{s['ups_total']:4d} 中位{s['words_median']:3d}词 | "
              f"{','.join(e['brands'][:3]) or '无品牌'} | 术语{e['term_density']:.1f}‰ "
              f"{','.join(e['top_terms'][:3])}")


if __name__ == "__main__":
    main()
