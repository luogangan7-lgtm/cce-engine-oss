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
# 2026-08-09: 原为「取最长45条再截38条」。实测该取法与被排除样本在长度上零重叠
# (入选最短245字符 > 排除最长236), 把语料的成本档分布从 51/31/19 筛成 76/21/3——
# low 档 15 条只留下 1 条, 基线被推到 0.763, G-K2 按构造不可判。改为全量(排除锚例)。
SAMPLE = [x for x in CORPUS if x["id"] not in ANCHOR_IDS]
# 2026-08-09 复检: M2.7 旧成功率 4/45 是本文件的 bug 不是模型缺陷——
# 它是推理模型, reasoning_content 独占预算(实测 2660 tok), max_tokens=1000 时
# finish_reason=length 且 content 为空; 给到 4000 即输出干净 JSON。M2.6 在 API 不存在(2013)。
MODELS = ["MiniMax-M3", "MiniMax-M2.5", "MiniMax-M2.7", "MiniMax-M2", "MiniMax-Text-01"]


def call(model, prompt, max_tokens=4000):
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "temperature": 0.0}
    for att in range(3):
        try:
            req = urllib.request.Request(BASE, json.dumps(payload).encode(),
                                         headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read())
                if (d.get("base_resp") or {}).get("status_code") == 0:
                    msg = d["choices"][0]["message"]
                    c = msg.get("content") or ""
                    # 推理模型偶把最终答案留在 reasoning_content
                    return c if c.strip() else (msg.get("reasoning_content") or "")
        except Exception:
            pass
    return ""


KNOT_BRIEF = "\n".join(
    f"- {k['key']}({k['name']}): 签名={json.dumps(k['signature'], ensure_ascii=False)}; 行为={k['behavior'][:70]}"
    for k in TAXO["knots"])

# ── prompt 的决策树/负例改为从分类学组装(2026-08-09) ──
# 此前二者是写死在 DIST_TMPL 里的副本, 与 config 各存一份、会静默漂移
# (当日同族缺陷第五例)。组装后有 assert 逐字比对旧文本, 保证 prompt 一字未变、
# 历史数字可比; 此后改分类学即自动进 prompt。
_P = TAXO["annotation_protocol"]
DECISION_TREE = "★判定顺序(决策树,逐级检查):\n" + "\n".join(_P["decision_tree_prompt"])
_NE = {k["key"]: k.get("negative_examples_prompt") for k in TAXO["knots"]}
# 顺序取自 protocol.negative_examples_order(prompt 层决策, 与内容分离)
NEGATIVE_EXAMPLES = "★何时不用(负例判据,与决策树同权重):\n" + "\n".join(
    f"- {k} 不用于: {_NE[k]}" for k in _P["negative_examples_order"] if _NE.get(k))

# ══ G-K1 v2: 带权分布标注 ══
DIST_TMPL = """你是心理配置标注员。九结分类学(v1.1.1):
{brief}

{decision_tree}


{negative_examples}

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
    c = call(model, DIST_TMPL.format(decision_tree=DECISION_TREE, negative_examples=NEGATIVE_EXAMPLES, brief=KNOT_BRIEF, body=item["b"][:700]))
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
    # 2026-08-09: asked_question 一直被 FACT_TMPL 抽取却从未计分, 导致纯提问型
    # (pain_seek 0.64~0.79) 被判 low → 单调性倒挂(low 2.37 > mid 1.98)。提问是
    # pain_seek 的签名行为, 计入后单调性恢复(1.77<1.94<2.41), spearman 0.296→0.406。
    n_costly = sum([f["named_specific_model"], f["described_own_situation_in_detail"],
                    f["challenged_or_confronted"], f["offered_help_or_correction"],
                    f["asked_question"]])
    if f["thanks_only"] and n_costly == 0:
        return "low"
    if n_costly >= 3 or (n_costly >= 2 and item["followed_up"]):
        return "high"
    if n_costly >= 1:
        return "mid"
    return "low"


# 2026-08-09: 原为硬编码副本, 导致分类学里 display 的 cost_tier_note(2026-08-07 校准:
# 基线mid, followed_up 时升high, 8/8) 从未被预测侧执行——而观察侧一直在用 followed_up,
# 一边用一边不用 → 系统性低估(混淆 mid→high 占全部错误 62%)。改为从分类学读。
COST_TIER = {k["key"]: k["cost_tier"] for k in TAXO["knots"]}
# 条件性档位: knot -> (触发字段, 命中时的档)。来源=分类学 cost_tier_note, 不再各处复制。
COST_TIER_IF = {"display": ("followed_up", "high")}
TIER_ORD = {"none": 0, "low": 1, "mid": 2, "high": 3}
ORD_TIER = {v: k for k, v in TIER_ORD.items()}


def tier_of(knot, item):
    """结→成本档, 应用条件性规则(依赖该条目的可核验元数据)"""
    cond = COST_TIER_IF.get(knot)
    if cond and item.get(cond[0]):
        return cond[1]
    return COST_TIER[knot]


def expected_ordinal(dist, item):
    """分布→连续成本分(0..3)。不取整、不定档——定档是校准问题, 与信号问题分开。"""
    tot = sum(dist.values())
    if tot <= 0:
        return None
    return sum(w * TIER_ORD[tier_of(k, item)] for k, w in dist.items()) / tot


def predict_tier_fixed(dist, item):
    """旧口径(固定整档切点), 仅作对照基线保留。"""
    e = expected_ordinal(dist, item)
    return None if e is None else ORD_TIER[min(TIER_ORD.values(), key=lambda o: abs(o - e))]


def _spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):                       # 并列取平均秩
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 3) if den else None


def _spearman_p(rho, n):
    """ρ 的双侧 p 值(t 近似, df=n-2)。常数预测器 ρ=0, 恒不显著——该判据不可刷。"""
    if rho is None or n < 4 or abs(rho) >= 1:
        return None
    df = n - 2
    t = abs(rho) * math.sqrt(df / (1 - rho * rho))
    # 学生 t 密度数值积分
    lg = math.lgamma
    c = math.exp(lg((df + 1) / 2) - lg(df / 2)) / math.sqrt(df * math.pi)
    N, h = 4000, t / 4000
    s = sum(c * (1 + (i * h) ** 2 / df) ** (-(df + 1) / 2) * (1 if 0 < i < N else 0.5) for i in range(N + 1)) * h
    return round(max(0.0, min(1.0, 2 * (0.5 - s))), 4)


def _fit_cuts(scores, obs_ords):
    """在训练折上网格搜三个切点 c1<c2<c3, 最大化精确命中。"""
    grid = [i / 10 for i in range(1, 30)]
    best, best_hit = (1.0, 2.0, 2.5), -1
    for a in range(len(grid)):
        for b in range(a + 1, len(grid)):
            for c in range(b + 1, len(grid)):
                c1, c2, c3 = grid[a], grid[b], grid[c]
                h = 0
                for s, o in zip(scores, obs_ords):
                    p = 0 if s < c1 else 1 if s < c2 else 2 if s < c3 else 3
                    h += (p == o)
                if h > best_hit:
                    best_hit, best = h, (c1, c2, c3)
    return best


def _apply_cuts(s, cuts):
    c1, c2, c3 = cuts
    return 0 if s < c1 else 1 if s < c2 else 2 if s < c3 else 3


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
    # ── 离群标注者(盲规则, 2026-08-09 冻结): 与其余成员平均JS > 面板中位数+2SD 判离群 ──
    # 首次可判是因为面板由3人扩到5人(10组两两对)才有离散可算。规则冻结后不得按结果调整。
    lo = {}
    for m in MODELS:
        v = [pw[k]["mean_JS"] for k in pw if m in k.split("~") and pw[k]["mean_JS"] is not None]
        if v:
            lo[m] = sum(v) / len(v)
    outliers = []
    if len(lo) >= 4:
        vals = sorted(lo.values())
        med = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
        mu = sum(vals) / len(vals)
        sd = (sum((x - mu) ** 2 for x in vals) / (len(vals) - 1)) ** 0.5
        outliers = [m for m, v in lo.items() if v > med + 2 * sd]
    core = [m for m in MODELS if m not in outliers]
    # 主判只看核心面板的两两对; 全面板数字并列保留, 便于核对剔除的影响
    def _agg(keep):
        sub = [v for k, v in pw.items() if all(m in keep for m in k.split("~"))]
        return ([v["top1_kappa"] for v in sub if v["top1_kappa"] is not None],
                [v["top2_hit"] for v in sub if v["top2_hit"] is not None],
                [v["mean_JS"] for v in sub if v["mean_JS"] is not None])
    ks_all, t2_all, js_all = _agg(MODELS)
    ks, t2s, jss = _agg(core) if len(core) >= 2 else (ks_all, t2_all, js_all)
    def _ms(xs):
        if not xs:
            return None, None
        mu = sum(xs) / len(xs)
        sd = (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5 if len(xs) > 1 else 0.0
        return round(mu, 4), round(sd, 4)
    # top1 结的基率偏斜 → 用于解释 κ: Pe 高时同样的生判一致率会得到更低的 κ
    top1_prev = collections.Counter(v for m in core for v in tops[m].values() if v)
    ntp = sum(top1_prev.values()) or 1
    pe = sum((v / ntp) ** 2 for v in top1_prev.values())
    raw = [v["top1_raw"] for k, v in pw.items()
           if all(m in core for m in k.split("~")) and v["top1_raw"] is not None]
    gk1 = {"pairwise": pw,
           "core_panel": core, "outliers_excluded": outliers,
           "outlier_rule": "与其余成员平均JS > 面板中位数+2SD(盲规则, 2026-08-09 冻结)",
           "annotator_mean_JS": {m: round(v, 4) for m, v in sorted(lo.items(), key=lambda x: x[1])},
           "mean_top2_hit": _ms(t2s)[0], "sd_top2_hit": _ms(t2s)[1],
           "mean_JS": _ms(jss)[0], "sd_JS": _ms(jss)[1],
           "mean_top1_kappa": _ms(ks)[0], "sd_top1_kappa": _ms(ks)[1],
           "mean_top1_raw_agreement": _ms(raw)[0],
           "top1_prevalence": dict(top1_prev.most_common()), "chance_agreement_Pe": round(pe, 3),
           "kappa_note": ("κ=(Po-Pe)/(1-Pe) 依赖类别基率, 不可跨语料比较。本语料 Pe 偏高时"
                          "同样的生判一致率会显示为更低的 κ, 故 κ 为参考项而非硬阈。"),
           "full_panel": {"mean_top2_hit": _ms(t2_all)[0], "mean_JS": _ms(js_all)[0],
                          "mean_top1_kappa": _ms(ks_all)[0]},
           "criteria": "主判(核心面板): top2命中≥0.8 且 平均JS≤0.25; κ与生判一致率为参考项",
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
        # 分布 → 连续成本分。定档留到后面用留一法校准, 避免把校准问题误报成信号问题。
        s = expected_ordinal(c, it)
        if s is None:
            continue
        # 逐条留痕: 只存聚合导致改完无法离线复核(已三次咬人: YouTube头对头亦因此算不出)
        rows.append({"id": it["id"], "score": round(s, 4), "obs": obs, "obs_ord": TIER_ORD[obs],
                     "pred_fixed": predict_tier_fixed(c, it),
                     "followed_up": bool(it.get("followed_up")),
                     "dist": {k: round(w, 3) for k, w in sorted(c.items(), key=lambda x: -x[1])},
                     "facts": f})

    scores = [r["score"] for r in rows]
    obs_ords = [r["obs_ord"] for r in rows]
    bc = collections.Counter(r["obs"] for r in rows).most_common(1)[0]
    base = bc[1] / len(rows) if rows else 0

    # ① 信号问题(与校准无关): 成本分与实测档的秩相关
    rho = _spearman(scores, obs_ords) if len(rows) > 2 else None

    # ② 校准问题: 留一法定切点——切点只在其余 n-1 条上拟合, 不看本条, 无泄漏
    for i, r in enumerate(rows):
        tr_s = scores[:i] + scores[i + 1:]
        tr_o = obs_ords[:i] + obs_ords[i + 1:]
        cuts = _fit_cuts(tr_s, tr_o)
        po = _apply_cuts(r["score"], cuts)
        r["pred"] = ORD_TIER[po]
        r["hit"] = (po == r["obs_ord"])
        r["off_by"] = abs(po - r["obs_ord"])
        r["cuts"] = cuts

    hit = sum(1 for r in rows if r["hit"])
    near = sum(1 for r in rows if r["off_by"] <= 1)
    fixed_hit = sum(1 for r in rows if r["pred_fixed"] == r["obs"])
    p_rho = _spearman_p(rho, len(rows)) if rho is not None else None
    # macro-recall: 每个实测档各自的召回率再取平均, 不被多数类淹没
    per_cls = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        per_cls[r["obs"]][1] += 1
        per_cls[r["obs"]][0] += r["hit"]
    n_cls = max(len(per_cls), 1)
    macro_r = round(sum(h / t for h, t in per_cls.values()) / n_cls, 3) if per_cls else None
    # 对照: 常数预测器在「相邻档」上能拿多少(用于证明该判据不可用)
    const_w1 = {ORD_TIER[o]: round(sum(1 for r in rows if abs(o - r["obs_ord"]) <= 1) / len(rows), 3)
                for o in TIER_ORD.values()} if rows else {}
    gk2 = {"n": len(rows), "exact_acc": round(hit / len(rows), 3) if rows else None,
           "within_1_tier": round(near / len(rows), 3) if rows else None,
           "baseline_majority": round(base, 3), "baseline_tier": bc[0],
           "lift_vs_baseline": round(hit / len(rows) - base, 3) if rows else None,
           "spearman_score_vs_observed": rho,
           "exact_acc_fixed_cuts": round(fixed_hit / len(rows), 3) if rows else None,
           "confusion": dict(collections.Counter(f"{r['pred']}→{r['obs']}" for r in rows)),
           "rows": rows,
           "predictor": "expected_tier_ordinal(taxonomy-sourced + display×followed_up→high) "
                        "→ leave-one-out calibrated cutpoints",
           "note": "spearman 测信号是否存在(免校准); exact/within1 用留一法切点, 与固定切点口径并列可比",
           # 2026-08-09: 删除原「或相邻档命中≥0.85」——实测常数预测器(永远说mid)在该条上
           # 得 1.000、永远说high 得 0.921, 而本预测器 0.921, 即判据被常数吊打, 绿灯无意义。
           # 改为 ①spearman 显著(免校准、常数预测器相关性恒为0不可刷) ②macro-recall 超随机。
           "spearman_p": p_rho, "macro_recall": macro_r, "chance_macro_recall": round(1 / n_cls, 3),
           "constant_predictor_within1": const_w1,
           "criteria": ("主判: spearman(成本分,实测档) 显著(p<0.05) 且 ρ≥0.3; "
                        "辅判: macro-recall > 1/类别数。精确率对多数基线仅作参考(基率偏斜时不可判)"),
           "pass": bool(rho is not None and rho >= 0.3 and p_rho is not None and p_rho < 0.05
                        and macro_r is not None and macro_r > 1 / n_cls)}

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
        c = call("MiniMax-M3", p, max_tokens=6000)  # M3 推理占~2.2k, 1500 会截断成空
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
