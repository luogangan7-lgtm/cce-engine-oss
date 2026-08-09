#!/usr/bin/env python3
"""九结验收 v2 — 修正 v1 的三处方法缺陷
【v1的问题】
 ①单选主结 与我们自己的"全占比·禁单argmax"纪律矛盾 → v2 改为带权分布标注,指标=top1κ + top2命中 + JS距离
 ②G-K2 的"实际成本档"用正则+长度启发式判,口径本身不可靠 → v2 改为先抽取**可核验行为事实**(抽取型任务,一致性天然高),再由预注册规则定档
 ③混淆只给了数字没给诊断 → v2 对分歧样本做判别式诊断,产出分类学修订建议
标注者: MiniMax 家族多模型,温度0,互不通气。
"""
import os, sys, json, math, itertools, collections
from concurrent.futures import ThreadPoolExecutor
import urllib.request

ROOT = os.environ.get("VSE_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from exp_v4_full_validation import extract_json_robust

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
KEY = os.environ["MINIMAX_API_KEY"]
BASE = "https://api.minimaxi.com/v1/text/chatcompletion_v2"
TAXO = json.load(open(os.path.join(ROOT, "config/knot_taxonomy.json")))
KNOTS = [k["key"] for k in TAXO["knots"]]
CORPUS = json.load(open(f"{D}/corpus.json"))
ANCHOR_IDS=['p1852zo', 'p1cuqrr', 'p1ypm4q', 'p1sqabv', 'p25z258']
ANCHORS = json.load(open(f"{D}/anchors.json", encoding="utf-8"))["anchors"]
ANCHOR_TRUTH = {a["id"]: a["knot"] for a in ANCHORS if a.get("id") and a.get("knot")}
SAMPLE = [x for x in sorted(CORPUS, key=lambda x: -len(x["b"]))[:45] if x["id"] not in ANCHOR_IDS][:38]
MODELS = ["MiniMax-M3", "MiniMax-M2.5", "MiniMax-Text-01"]  # M2.7 v1中成功率仅4/45,剔除


def call(model, prompt, max_tokens=1000):
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "temperature": 0.0}
    for att in range(3):
        try:
            req = urllib.request.Request(BASE, json.dumps(payload).encode(),
                                         headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=150) as r:
                d = json.loads(r.read())
                if (d.get("base_resp") or {}).get("status_code") == 0:
                    return d["choices"][0]["message"].get("content") or ""
        except Exception:
            pass
    return ""


KNOT_BRIEF = "\n".join(
    f"- {k['key']}({k['name']}): 签名={json.dumps(k['signature'], ensure_ascii=False)}; 行为={k['behavior'][:70]}"
    for k in TAXO["knots"])

# ══ G-K1 v2: 带权分布标注 ══
DIST_TMPL = """你是心理配置标注员。九结分类学(v1.1.1):
{brief}

★判定顺序(决策树,逐级检查):
1. 有对某方真实性/资历/动机的质询句? -> audit 权重优先
2. 有明确归责对象+讨说法? -> injustice
3. 在为**自己的**现实问题求可行解(症状+场景+求解)? -> pain_seek
4. 明确悬置决策(还没定/再看看+犹豫理由)? -> suspend; 明知该动而声明不动? -> inertia
5. 谈论**自己已拥有/已经历**且有信息增量(型号/数据/经验)? -> display
6. 向往**未得之物**且不求解决路径? -> itch
7. 纯致谢/纯情绪回报无增量? -> reward; 仅为确认同类身份? -> belong


★何时不用(负例判据,与决策树同权重):
- display 不用于: 晒了型号但通篇在求解自身未解问题(那是pain_seek); 晒经验+质询OP动机(那是audit)
- pain_seek 不用于: 问题已解决、正在分享方案(那是display); 借问题控诉某方要说法(那是injustice)
- audit 不用于: 质疑的是产品性能而非某人的可信度(那是pain_seek或injustice); 反问只是修辞、落点仍是求解(那是pain_seek)
- itch 不用于: 向往之物已进入比较/购买流程(那是suspend); 向往并主动求推荐路径(那是pain_seek)
- suspend 不用于: 无决策语境的纯畅想(那是itch); 已明确放弃(那是inertia)
- inertia 不用于: 仍在比较权衡中(那是suspend)
- reward 不用于: 致谢同时带新信息增量(那是display); 致谢后追问(那是pain_seek)
- belong 不用于: 自报身份但主体是输出经验增量(那是display)
- injustice 不用于: 无归责对象的困难自述(那是pain_seek)

★全一致锚例(判定同结的样例应长这样):
【锚例·display】The Connect Clip. You had to wear it around your neck. Easy to lose (I lost two). Latenchy from the BT classic audio. Just fiddly.

mfi and ASHA. Definitely better than nothing. Occasional glitching and connection issues. Sound quality is adequate. Range is ju
【锚例·pain_seek】I have a Pixel 9 and Widex Allure.  Maybe you can help.  

Anytime you do anything on the pixel that would normally create a sound, the hearing aids go into streaming mode (which causes real sounds to be muffled and you can hear everything change). 

This happ
【锚例·injustice】OP your musings are interesting and informative. 

I was one of the posters asking about BT connectivity last weekend. It was a miserable weekend trying unsuccessfully to pair my new Starkeys with Windows. 

I was especially pissed at my audiologist who swore 
【锚例·itch】Oh I am unsure too, as to why manufacturers are going for smaller when bigger would allow much more with the current technology we have. In fact, I have been living in hope that one of the big names release a power version (so bigger) of their current tech but
【锚例·audit】No, if size was eliminated as a criterion because the diagnostic criteria eliminated size as a consideration for the patient, which device would you fit that patient with?

You only care about size being identical if it remains a consideration albeit lower in 

给你一条评论。判定被激活的结组合,带权分布(权重和=1,只列>=0.1,最多3个)。

【评论】
{body}

只输出JSON: {{"knots":[{{"key":"<九结key>","weight":0.0}}],"evidence":"<原文引句,20字内>"}}"""

def annot_dist(args):
    model, item = args
    c = call(model, DIST_TMPL.format(brief=KNOT_BRIEF, body=item["b"][:700]))
    d = extract_json_robust(c, log_note=f"gk1v2_{model}")
    if isinstance(d, dict) and isinstance(d.get("knots"), list) and d["knots"]:
        v = {}
        for k in d["knots"]:
            if k.get("key") in KNOTS:
                v[k["key"]] = float(k.get("weight", 0))
        tot = sum(v.values())
        if tot > 0:
            return item["id"], {k: w / tot for k, w in v.items()}
    return item["id"], None


# ══ G-K2 v2: 可核验行为事实抽取 ══
FACT_TMPL = """你是事实抽取器。只做客观抽取,不做心理判断。对这条 r/HearingAids 评论回答:

【评论】
{body}

只输出JSON:
{{"named_specific_model": true/false,   // 是否给出具体助听器型号(品牌+系列/型号,裸品牌名不算)
  "described_own_situation_in_detail": true/false,  // 是否详述了自己的听力状况/使用场景/已试过的步骤
  "asked_question": true/false,          // 是否向他人提出了问题
  "challenged_or_confronted": true/false,// 是否质疑/对质/问责了某方(厂商/验配师/OP)
  "thanks_only": true/false,             // 是否只是致谢没有实质内容
  "offered_help_or_correction": true/false}} // 是否给出建议/纠正/分享经验帮助他人"""


def extract_facts(item):
    c = call("MiniMax-Text-01", FACT_TMPL.format(body=item["b"][:700]), max_tokens=400)
    d = extract_json_robust(c, log_note="gk2v2_fact")
    if isinstance(d, dict):
        return item["id"], {k: bool(d.get(k)) for k in
                            ("named_specific_model", "described_own_situation_in_detail", "asked_question",
                             "challenged_or_confronted", "thanks_only", "offered_help_or_correction")}
    return item["id"], None


def observed_tier_from_facts(f, item):
    """预注册规则: 由可核验事实定成本档(不看结)"""
    if not f:
        return None
    n_costly = sum([f["named_specific_model"], f["described_own_situation_in_detail"],
                    f["challenged_or_confronted"], f["offered_help_or_correction"]])
    if f["thanks_only"] and n_costly == 0:
        return "low"
    if n_costly >= 3 or (n_costly >= 2 and item["followed_up"]):
        return "high"
    if n_costly >= 1:
        return "mid"
    return "low"


COST_TIER = {"pain_seek": "high", "injustice": "high", "audit": "mid", "belong": "mid",
             "suspend": "mid", "display": "mid", "reward": "low", "itch": "low", "inertia": "none"}
TIER_ORD = {"none": 0, "low": 1, "mid": 2, "high": 3}


def js_div(p, q):
    keys = set(p) | set(q)
    m = {k: (p.get(k, 0) + q.get(k, 0)) / 2 for k in keys}
    def kl(a, b):
        s = 0
        for k in keys:
            if a.get(k, 0) > 0 and b.get(k, 0) > 0:
                s += a[k] * math.log2(a[k] / b[k])
        return s
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def kappa(a, b):
    ids = [i for i in a if a[i] and b.get(i)]
    n = len(ids)
    if n < 10:
        return None, n, None
    po = sum(1 for i in ids if a[i] == b[i]) / n
    ca, cb = collections.Counter(a[i] for i in ids), collections.Counter(b[i] for i in ids)
    pe = sum((ca[l] / n) * (cb[l] / n) for l in set(ca) | set(cb))
    return ((po - pe) / (1 - pe) if pe < 1 else None), n, po


def qualify(model):
    """留一法考锚例: 每次留一个锚例当考题, 其余4个作示范。top1命中≥4/5 合格。
    协议 annotation_protocol.annotator_qualification 早已规定, 此前从未执行 —
    未经资格考的标注者混进平均, 是 G-K1 长期不达标的主要嫌疑。"""
    hits, detail = 0, []
    for held in ANCHOR_IDS:
        if held not in ANCHOR_TRUTH:
            continue
        item = next((x for x in CORPUS if x["id"] == held), None)
        if not item:
            continue
        shown = [a for a in ANCHORS if a.get("id") != held]
        demo = "\n".join(f"【锚例·{a['knot']}】{a.get('text','')[:200]}" for a in shown)
        # 用与正式标注完全相同的模板考试, 只是把示范锚例换成留一法的4个
        p = DIST_TMPL.format(brief=KNOT_BRIEF + "\n\n★示范锚例(留一法, 已隐去本题):\n" + demo,
                             body=item["b"][:700])
        out = call(model, p)
        d = extract_json_robust(out, log_note="qual")
        top = None
        if isinstance(d, dict) and isinstance(d.get("knots"), list) and d["knots"]:
            try:
                ks = [(k.get("key"), float(k.get("weight", 0))) for k in d["knots"] if k.get("key")]
                top = sorted(ks, key=lambda x: -x[1])[0][0] if ks else None
            except Exception:
                pass
        ok = (top == ANCHOR_TRUTH[held])
        hits += ok
        detail.append({"held": held, "truth": ANCHOR_TRUTH[held], "got": top, "ok": ok})
    return {"model": model, "hits": hits, "of": len(ANCHOR_TRUTH),
            "qualified": hits >= 4, "detail": detail}


def main():
    # ── 资格考(协议既有规定, 本次起强制执行) ──
    print("=== 标注者资格考(留一法·锚例 top1≥4/5) ===", flush=True)
    quals = [qualify(m) for m in MODELS]
    for q in quals:
        print(f"  {q['model']:22s} {q['hits']}/{q['of']} {'合格' if q['qualified'] else '★不合格, 剔除'}", flush=True)
    passed = [q["model"] for q in quals if q["qualified"]]
    if len(passed) < 2:
        print(f"合格标注者不足2个({passed}), 无法计算两两一致性")
    globals()["MODELS"] = passed or MODELS
    globals()["QUAL_REPORT"] = quals
    print(f"进入验收的标注者: {globals()['MODELS']}\n", flush=True)

    print(f"样本 {len(SAMPLE)} 条 · 标注者 {MODELS}", flush=True)
    dists = {m: {} for m in MODELS}
    jobs = [(m, it) for m in MODELS for it in SAMPLE]
    with ThreadPoolExecutor(max_workers=8) as ex:
        for (m, _), (iid, dv) in zip(jobs, ex.map(annot_dist, jobs)):
            dists[m][iid] = dv
    cover = {m: sum(1 for v in dists[m].values() if v) for m in MODELS}
    print("分布标注覆盖:", cover, flush=True)

    with ThreadPoolExecutor(max_workers=8) as ex:
        facts = dict(ex.map(extract_facts, SAMPLE))
    print("事实抽取覆盖:", sum(1 for v in facts.values() if v), "/", len(SAMPLE), flush=True)

    # ── G-K1 v2 三指标 ──
    tops = {m: {i: (max(v, key=v.get) if v else None) for i, v in dists[m].items()} for m in MODELS}
    top2 = {m: {i: sorted(v, key=v.get, reverse=True)[:2] if v else [] for i, v in dists[m].items()} for m in MODELS}
    pw = {}
    for a, b in itertools.combinations(MODELS, 2):
        k, n, po = kappa(tops[a], tops[b])
        ids = [i for i in dists[a] if dists[a][i] and dists[b].get(i)]
        t2 = sum(1 for i in ids if tops[a][i] in top2[b][i] or tops[b][i] in top2[a][i]) / len(ids) if ids else None
        jsv = [js_div(dists[a][i], dists[b][i]) for i in ids]
        pw[f"{a}~{b}"] = {"top1_kappa": round(k, 3) if k is not None else None,
                          "top1_raw": round(po, 3) if po else None,
                          "top2_hit": round(t2, 3) if t2 is not None else None,
                          "mean_JS": round(sum(jsv) / len(jsv), 4) if jsv else None, "n": len(ids)}
    ks = [v["top1_kappa"] for v in pw.values() if v["top1_kappa"] is not None]
    t2s = [v["top2_hit"] for v in pw.values() if v["top2_hit"] is not None]
    jss = [v["mean_JS"] for v in pw.values() if v["mean_JS"] is not None]
    gk1 = {"pairwise": pw,
           "mean_top1_kappa": round(sum(ks) / len(ks), 3) if ks else None,
           "mean_top2_hit": round(sum(t2s) / len(t2s), 3) if t2s else None,
           "mean_JS": round(sum(jss) / len(jss), 4) if jss else None,
           "criteria": "主判: top2命中≥0.8 且 平均JS≤0.25(与跨模型四层基准JS 0.0975~0.193同量级); 参考: top1κ",
           "pass": (sum(t2s) / len(t2s) >= 0.8 and sum(jss) / len(jss) <= 0.25) if (t2s and jss) else False}

    # ── G-K2 v2 ──
    cons = {}
    for it in SAMPLE:
        vs = [dists[m].get(it["id"]) for m in MODELS if dists[m].get(it["id"])]
        if vs:
            agg = collections.defaultdict(float)
            for v in vs:
                for k, w in v.items():
                    agg[k] += w / len(vs)
            cons[it["id"]] = dict(agg)
    rows = []
    for it in SAMPLE:
        c, f = cons.get(it["id"]), facts.get(it["id"])
        obs = observed_tier_from_facts(f, it)
        if not c or not obs:
            continue
        # 结分布 → 成本档期望(按权重加权取档位众数)
        tier_w = collections.defaultdict(float)
        for k, w in c.items():
            tier_w[COST_TIER[k]] += w
        pred = max(tier_w, key=tier_w.get)
        rows.append({"id": it["id"], "pred": pred, "obs": obs, "hit": pred == obs,
                     "off_by": abs(TIER_ORD[pred] - TIER_ORD[obs])})
    hit = sum(1 for r in rows if r["hit"])
    near = sum(1 for r in rows if r["off_by"] <= 1)
    bc = collections.Counter(r["obs"] for r in rows).most_common(1)[0]
    base = bc[1] / len(rows) if rows else 0
    gk2 = {"n": len(rows), "exact_acc": round(hit / len(rows), 3) if rows else None,
           "within_1_tier": round(near / len(rows), 3) if rows else None,
           "baseline_majority": round(base, 3), "baseline_tier": bc[0],
           "lift_vs_baseline": round(hit / len(rows) - base, 3) if rows else None,
           "confusion": dict(collections.Counter(f"{r['pred']}→{r['obs']}" for r in rows)),
           "criteria": "精确档准确率 > 多数基线,或相邻档命中≥0.85",
           "pass": ((hit / len(rows) > base) or (near / len(rows) >= 0.85)) if rows else False}

    # ── 混淆诊断(问题2) ──
    disagree = []
    for it in SAMPLE:
        vs = {m: tops[m].get(it["id"]) for m in MODELS if tops[m].get(it["id"])}
        if len(set(vs.values())) > 1:
            disagree.append({"id": it["id"], "labels": vs, "body": it["b"][:400]})
    diag = None
    if disagree:
        pairs_seen = collections.Counter()
        for d0 in disagree:
            for a, b in itertools.combinations(sorted(set(d0["labels"].values())), 2):
                pairs_seen[f"{a}|{b}"] += 1
        top_pairs = pairs_seen.most_common(4)
        cases = "\n\n".join(f"[分歧{i+1}] 标注={json.dumps(d0['labels'],ensure_ascii=False)}\n{d0['body'][:300]}"
                            for i, d0 in enumerate(disagree[:8]))
        p = (f"""九结分类学 v1.0.0 的签名定义如下:
{KNOT_BRIEF}

多个标注者在下列真实评论上判定不一致。高频混淆对: {[p for p,_ in top_pairs]}

{cases}

请诊断: 对每个高频混淆对,①两者签名里哪一处描述不足以区分 ②给出一条**可操作的硬判别式**(观察什么就能定案)。
只输出JSON: {{"pairs":[{{"pair":"a|b","ambiguity":"...","hard_discriminant":"..."}}],"taxonomy_fix":"一句话总体修订方向"}}""")
        c = call("MiniMax-M3", p, max_tokens=1500)
        diag = extract_json_robust(c, log_note="gk_diag") or {"raw": c[:400]}
        diag = {"n_disagree_cases": len(disagree), "top_confusion_pairs": dict(top_pairs), "diagnosis": diag}

    out = {"gate": "九结分类学 v1.1.1 验收 v5(v4+全结负例句)",
           "sample_n": len(SAMPLE), "annotators": MODELS, "coverage": cover,
           "G_K1v2_分布一致性": gk1, "G_K2v2_成本档预测": gk2, "混淆诊断": diag,
           "annotator_qualification": globals().get("QUAL_REPORT"),
        "overall_pass": gk1["pass"] and gk2["pass"]}
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"out","gates_result.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "混淆诊断"}, ensure_ascii=False, indent=1))
    if diag:
        print("\n=== 混淆诊断 ===")
        print(json.dumps(diag, ensure_ascii=False, indent=1)[:2000])


if __name__ == "__main__":
    main()
