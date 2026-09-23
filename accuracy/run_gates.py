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
# ★★ 2026-09-07: 语料与输出目录可被环境变量覆盖 —— 为**重复性**(同语料二次运行)
#   与**外部效度**(换语料)两个实验而加。默认值与此前逐字相同, 不改变既有行为。
#   ★ CCE_OUT_DIR 允许指向仓外(识别层保险库), 因为外部效度语料含真实 reddit handle:
#     **原始产物落保险库, 只有去识别的聚合量进公开仓**。
CORPUS = json.load(open(os.environ.get("CCE_CORPUS", f"{D}/corpus.json"), encoding="utf-8"))
# ★★ 2026-09-07: 锚例考卷**必须独立于被测语料**。
#   实测缺陷: 换 CCE_CORPUS 跑外部效度时, qualify() 仍从 CORPUS 里按 id 找锚例 ⇒ 一个都找不到
#   ⇒ 全员 hits=0 ⇒ **0/5 合格 ⇒ 整轮扣发**。
#   ★ 闸做对了事(扣发而不是假通过), 但根因是**锚例与被测语料耦合**:
#     资格考问的是「这个标注者懂不懂这套分类学」, 与「今天要标什么语料」无关。
#   ⇒ 锚例固定读自有 anchors.json 的那份 corpus, 不受 CCE_CORPUS 影响。
ANCHOR_CORPUS = json.load(open(f"{D}/corpus.json", encoding="utf-8"))
_OUT_DIR = os.environ.get(
    "CCE_OUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
SKIP_GK2 = os.environ.get("CCE_SKIP_GK2") == "1"   # 外部语料无 followed_up/replied_by_op
# ★★ 正文截断长度。默认 700 = 此前逐字硬编的值, **不改变既有行为**。
#   ★ 更正: 我第一版注释写「它对验收语料从未触发过(最长 683 字符, 0 条超 700)」——
#     **那是编的**。实测验收语料最长 **900** 字符, **15/86(17%)** 超过 700 ⇒ 它**触发过**。
#     ⇒ 700 确实是仪器的一部分, 换语料时改它**不是无害的**, 必须记为工况变更。
#   ★★ 真正的理由是**截断率差了一倍多**: 验收 17%(15/86) vs 外部帖子 **38%(461/1208)**,
#     且实测 **16.2% 的 belong 标志词落在 700 字符之后**("only me?" 常在结尾) ——
#     照 700 跑外部语料, 会**系统性漏检 belong**, 方向恰好偏向「找不到 ⇒ 判它死」。
#   ★ 所以 Run B **两种截断都跑**(700 与 2000), 把截断当成一个**被测变量**而不是一个默认值 ——
#     否则「belong=0」与「截断吃掉了它」永远分不开。
#   ⇒ 产物里必须记下实际用了多少。
BODY_CHARS = int(os.environ.get("CCE_BODY_CHARS", "700"))
# ★★★ 2026-09-07: **标注 prompt 逐字告诉模型「给你一条评论」, 输入槽标签也是【{unit}】。**
#   而 KNOT_BRIEF 里(逐字来自 taxonomy 的 behavior 字段)同时告诉它:
#     · display = 「…**评论区**最高质量UGC主力」
#     · belong  = 「自我暴露式**发帖**+『only me?』」
#   ⇒ 在这个 prompt 下, 标注一条评论时 belong 拿 0/78 共识 argmax
#     **几乎是被 prompt 指示出来的**, 不是仪器的独立判断。
#   ★ 这不是「单元错配的可能机制」, 是 prompt 里一条**显式的、方向明确的指示**。
#   ⇒ 把单元标签做成**被测变量**: 同一批帖子跑两臂(评论 / 帖子), 直接测这个词的效应。
#   默认「评论」= 此前硬编值, **不改变既有行为**。
UNIT_LABEL = os.environ.get("CCE_UNIT_LABEL", "评论")


# ★★★ 2026-09-08: 这两个参数**进 prompt**(body 截断长度、prompt 里说「给你一条评论/帖子」),
#   而它们是**环境变量** —— 换掉就换了刺激, 却一个文件都不动。
#   实测缺陷: run_a_repeat / run_c_confirm 两次运行的产物里**都没有记录它们** ⇒
#   事后无法核实「那次跑的是 700 还是别的」, 于是**任何与它对照的新臂都只能假设可比, 不能验证**。
#   ★ 与 manifest 里已记的同族洞(MEASUREMENT_MODEL 是环境变量, 只钉文件 sha 抓不到)一模一样,
#     那个洞修了, 这个没修 —— **修了一个实例, 没修那一类**。
#   ⇒ 每次运行必须把它们写进产物。由 tests/test_cce_run_params_recorded.py 守住。
RUN_PARAMS = {
    "CCE_BODY_CHARS": BODY_CHARS,
    "CCE_UNIT_LABEL": UNIT_LABEL,
    "CCE_CORPUS": os.environ.get("CCE_CORPUS", "<default corpus.json>"),
    "CCE_SKIP_GK2": SKIP_GK2,
    "run_gates_MODELS": None,          # 由 main()/stamp_params 填 run_gates 自己的面板
    "annotators_actually_used": None,  # ★ 探针若另加标注者(跨家族 GLM 等)必须自报, 否则章不完整
    "gate_protocol_version": None,     # 由 main()/stamp_params 填(定义在下方, 此处占位)
    "gate_protocol_hash": None,
    "★why_recorded": ("这些参数**进 prompt 或决定跑哪几道闸**, 且全是环境变量。"
                      "不记 ⇒ 事后无法核实两次运行是否可比。"),
}


def stamp_params(out_dir, extra=None):
    """★ 把「进 prompt 的环境参数」盖在任意一次运行的输出目录旁。

    探针复用 run_gates 的 BODY_CHARS / UNIT_LABEL 构造 prompt, 于是**继承了同一个缺陷**:
    产物不记参数 ⇒ 事后无法核实两次跑是否可比。一行调用堵住。
    """
    import datetime
    d = dict(RUN_PARAMS)
    d["gate_protocol_version"] = GATE_PROTOCOL_VERSION
    d["gate_protocol_hash"] = gate_protocol_hash()
    # ★ 这是 **run_gates 的**面板。探针若另加标注者(如跨家族 GLM), 必须自己传
    #   extra={"annotators_actually_used": [...]} —— 实测漏过一次(suspend V0/V1 的章少了 glm-4.5-flash)。
    d["run_gates_MODELS"] = list(MODELS)
    d["annotators_actually_used"] = None   # 由调用方覆盖; 留 None 表示与 run_gates_MODELS 相同
    d["stamped_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if extra:
        d.update(extra)
    q = os.path.join(str(out_dir), "run_params.json")
    os.makedirs(str(out_dir), exist_ok=True)
    with open(q, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    return q
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


# ══ ★★★ 验收闸的**独立版本** (2026-09-09) ═══════════════════════════════════
#  网页版 GPT-6 Pro 裁定: 改 negative_examples 这类改动**不是生产换代** ——
#  P 的实现与有效输入不变, 变的是 **G(验收者)怎样判**。
#  ⇒ 「P 不递增 instrument_generation」是对的, **但 G 必须有自己的版本**,
#    否则就成了「一面把 instrument_generation 叫整体仪器代号,
#    一面利用哈希未覆盖 G 来宣称没换代」。
#  ★ instrument_generation **只指称 P** —— 这层关系此前是**隐含**的, 现在写成明文。
# v1 → v2 (2026-09-09, GATE_PROTOCOL_CHANGE): suspend 的负例新增「决定已作出、延后的只是
#   执行/购买时点」这一条排除。**生产 instrument_hash 一字未变** —— 见 manifest 的 refactor_log。
#   ★ v2 与 v1 的 G-K1 读数**可比不可合**。
GATE_PROTOCOL_VERSION = 2


def gate_protocol_hash():
    """现算**进闸 prompt 的全部材料**的哈希。改任何一块 ⇒ 哈希变 ⇒ 必须换 G 的版本。"""
    import hashlib as _h
    mat = KNOT_BRIEF + "\x00" + DECISION_TREE + "\x00" + NEGATIVE_EXAMPLES + "\x00" + DIST_TMPL
    return _h.sha256(mat.encode()).hexdigest()[:16]


GATE_PROTOCOL = {
    "version": GATE_PROTOCOL_VERSION,
    "★covers": "KNOT_BRIEF + DECISION_TREE + NEGATIVE_EXAMPLES + DIST_TMPL —— 即**标注者实际看到的全部材料**",
    "★does_not_cover": "生产 s1/s2 prompt(那由 instrument_hash 管)、模型与端点(由 sampling/endpoint 管)",
    "★★why_separate": "闸与生产是**两台仪器**。用一个版本号同时代表两者, 会让改了一台却宣称没换代。",
}

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

给你一条{unit}。判定被激活的结组合,带权分布(权重和=1,只列>=0.1,最多3个)。

【{unit}】
{body}

只输出JSON: {{"knots":[{{"key":"<九结key>","weight":0.0}}],"evidence":"<原文引句,20字内>"}}"""

def annot_dist(args):
    model, item = args
    c = call(model, DIST_TMPL.format(unit=UNIT_LABEL, decision_tree=DECISION_TREE, negative_examples=NEGATIVE_EXAMPLES, brief=KNOT_BRIEF, body=item["b"][:BODY_CHARS]))
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

【{unit}】
{body}

只输出JSON:
{{"named_specific_model": true/false,   // 是否给出具体助听器型号(品牌+系列/型号,裸品牌名不算)
  "described_own_situation_in_detail": true/false,  // 是否详述了自己的听力状况/使用场景/已试过的步骤
  "asked_question": true/false,          // 是否向他人提出了问题
  "challenged_or_confronted": true/false,// 是否质疑/对质/问责了某方(厂商/验配师/OP)
  "thanks_only": true/false,             // 是否只是致谢没有实质内容
  "offered_help_or_correction": true/false}} // 是否给出建议/纠正/分享经验帮助他人"""


def extract_facts(item):
    c = call("MiniMax-Text-01", FACT_TMPL.format(unit=UNIT_LABEL, body=item["b"][:BODY_CHARS]), max_tokens=400)
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
        item = next((x for x in ANCHOR_CORPUS if x["id"] == held), None)
        if not item:
            continue
        shown = [a for a in ANCHORS if a.get("id") != held]
        demo = "\n".join(f"【锚例·{a['knot']}】{a.get('text','')[:200]}" for a in shown)
        # 用与正式标注完全相同的模板考试, 只是把示范锚例换成留一法的4个
        # ★★ 2026-09-07 修: 此前只填了 brief/body, 漏了 decision_tree 与 negative_examples
        #   ⇒ `DIST_TMPL.format(unit=UNIT_LABEL, ...)` 抛 KeyError('decision_tree') ⇒ **qualify() 一次都没跑通过**。
        #   而它是 main() 的第一步 ⇒ **整个验收闸根本跑不起来**。
        #   ⇒ `gate_record` 里那句「G-K1 v5 通过(2026-08-07)」只能来自 qualify() 被加进来**之前**
        #     的版本 —— 有人写了资格考、写了「本次起强制执行」的注释, 而这段代码从未执行。
        #   ★ 本函数自己的注释写着「用与正式标注**完全相同的模板**考试」—— 现在它才真的相同。
        p = DIST_TMPL.format(unit=UNIT_LABEL, decision_tree=DECISION_TREE,
                             negative_examples=NEGATIVE_EXAMPLES,
                             brief=KNOT_BRIEF + "\n\n★示范锚例(留一法, 已隐去本题):\n" + demo,
                             body=item["b"][:BODY_CHARS])
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


# ★★ v2 资格考的 indifference region(2026-09-07 冻结于
#    tests/data/annotator_qualification_v2_prereg.json, **待新数据确证**)
QUAL_P_LOW, QUAL_P_HIGH = 0.70, 0.90


def _wilson(k, n, z=1.96):
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def qualification_state(hits, of):
    """三态判决 —— 单调, 不会一题之差翻转。见 v2 预注册。

    · QUALIFIED    : Wilson 95% **下界 >= p_H**  (可信地够好)
    · DISQUALIFIED : Wilson 95% **上界 <= p_L**  (可信地不够好)
    · UNRESOLVED   : 其余 —— **追加独立锚例, 绝不视同 FAIL**

    ★★ 判决带是**不对称**的, 而这是对的: 实测 n=5 时 DISQUALIFIED 只需 k<=1,
      而 QUALIFIED 需 **n>=35 且全对**。⇒ **排除一个明显坏的便宜, 证明一个够好昂贵。**
      所以资格考**只用于 DISQUALIFY, 不用于 CERTIFY** —— v1 恰恰反过来, 那是它乱剔人的根因。
    """
    # ★★★ of == 0 ⇒ **考试根本没跑**, 不是「证据不足」。
    #   若把它归入 UNRESOLVED, 而 UNRESOLVED 又留在 primary 面板里,
    #   就等于「**跳过资格考 ⇒ 所有人默认通过**」—— 那正是 v1 那个 fail-open 换了个壳。
    #   ⇒ 单列一档, 由 admit_annotators 扣发整轮。
    if not of:
        return "NOT_EXAMINED", (0.0, 1.0)
    lo, hi = _wilson(hits, of)
    if lo >= QUAL_P_HIGH:
        return "QUALIFIED", (round(lo, 4), round(hi, 4))
    if hi <= QUAL_P_LOW:
        return "DISQUALIFIED", (round(lo, 4), round(hi, 4))
    return "UNRESOLVED", (round(lo, 4), round(hi, 4))


def admit_annotators(quals):
    """谁进验收 —— **纯函数, 无 API, 可离线测**。

    ## ★★★ v1 的两次修法, 都不够

    **第一次(2026-09-07 早)** 修的是 fail-open。原实现:
        if len(passed) < 2: print(...)          # 只打印, 然后照跑
        globals()["MODELS"] = passed or MODELS  # ★ 零人合格 ⇒ **静默回退到全员**
    `passed or MODELS` 让「零人合格」与「全员合格」在输出上**不可区分** —— 而上一行刚把他们
    逐个打印成「★不合格, 剔除」。打印说剔除, 代码把他们放了回去。
    ⇒ 这正是本项目命名过的 fail-silent: **缺判定不等于判定通过**。
    而函数上方的注释写着「本次起**强制执行**」—— **注释不是闸**。
    改成合格者 <2 就扣发。**那条修法仍然有效, 保留。**

    ★★★ 而 v2 第一版**当场又造了一个同族的**: 把 `of == 0`(考试没跑)归入 UNRESOLVED,
      而 UNRESOLVED 又留在 primary 面板里 ⇒ **「跳过资格考 ⇒ 所有人默认通过」**。
      它比第一个更危险, 因为在输出上完全看不见。已单列 NOT_EXAMINED 并扣发整轮。

    **第二次(2026-09-07 晚, 本次)** 修的是**判据本身**:
    同一份 5 题考卷、temp=0、代码逐字相同, 跑三次 M2.7 得 **3/5、5/5、4/5**。
    ★ 实测 **n=5 时任何 cutoff 都做不到 α、β 同时 <5%**(最好的全对判据是 α=0.168/β=0.226)
      ⇒ **5 题在任何阈值下都不可能做出可靠的二元判决**, 不是调阈值能修的。
    ★★ 而那次剔除**损害了指标**: 剔 M2.7 的 4 人面板自助失败率 **23.1%**, 保留它的 5 人 **7.0%**。
    ★★★ 且我的 bootstrap **本身是低估的** —— 它只重采样条目, 没传播「谁进面板」的随机性。
      传播后是 **14.8%**, 且**跑一次得到 5 人面板的概率只有 46%**。

    ## v2 的三条改动
    ① **三态**(QUALIFIED / UNRESOLVED / DISQUALIFIED), 由 indifference region 两端定, 单调。
    ② **UNRESOLVED 保留, 不排除** —— 「若 UNRESOLVED 就排除, 那只是把 FAIL 改名」。
    ③ **只有 DISQUALIFIED 与明确协议违规才排除**。primary 含所有无协议违规者;
       qualified-only 另作 sensitivity。

    ★ 本规则**据 development 证据设计, 待新数据确证** —— 不得用当天那 81 条当确证证据。
    """
    states = {}
    for q in quals:
        st, ci = qualification_state(q.get("hits", 0), q.get("of", 0) or 0)
        states[q["model"]] = {"hits": q.get("hits"), "of": q.get("of"),
                              "wilson95": list(ci), "state": st}
    # ★★ 有任何一名 NOT_EXAMINED ⇒ **扣发整轮**。理由见 qualification_state:
    #   「跳过考试 ⇒ 默认通过」比「考砸了 ⇒ 剔除」更危险, 因为它在输出上看不见。
    ne = [m for m, v in states.items() if v["state"] == "NOT_EXAMINED"]
    if ne:
        return {"admit": None, "status": "QUALIFICATION_NOT_RUN", "★states": states,
                "qualified_only": [],
                "reason": (f"{len(ne)}/{len(quals)} 名标注者**没有考试数据**({ne}) —— "
                           "资格考没跑。★ 不得归入 UNRESOLVED 后放行: 那等于"
                           "「跳过考试 ⇒ 默认通过」, 是 v1 那个 fail-open 换壳。"
                           "★ 不产出判决 != 判决通过。")}
    # ★ 只有 DISQUALIFIED 出局。UNRESOLVED 留在 primary 面板里。
    admitted = [m for m, v in states.items() if v["state"] != "DISQUALIFIED"]
    qualified_only = [m for m, v in states.items() if v["state"] == "QUALIFIED"]
    dis = [m for m, v in states.items() if v["state"] == "DISQUALIFIED"]
    unres = [m for m, v in states.items() if v["state"] == "UNRESOLVED"]
    if len(admitted) < 2:
        return {"admit": None, "status": "INSUFFICIENT_QUALIFIED_ANNOTATORS",
                "★states": states, "qualified_only": qualified_only,
                "reason": (f"仅 {len(admitted)}/{len(quals)} 名标注者未被 DISQUALIFY({admitted or '无'}) —— "
                           "两两一致性需要 >=2 名, 少于此**数学上无定义**。"
                           "★ 不回退到全员: 那会让「没人合格」与「全员合格」不可区分。"
                           "★ 不产出判决 != 判决通过。")}
    return {"admit": admitted, "status": "OK", "★states": states,
            "qualified_only": qualified_only,
            "★primary_includes_UNRESOLVED": unres,
            "★disqualified": dis,
            "reason": (f"primary 面板 {len(admitted)}/{len(quals)} 名(含 {len(unres)} 名 UNRESOLVED, "
                       f"剔除 {len(dis)} 名 DISQUALIFIED)。"
                       f"★ UNRESOLVED **不视同 FAIL** —— 那只是把 FAIL 改名。"
                       f"★ qualified-only({len(qualified_only)} 名)另作 sensitivity, "
                       f"**不是 primary**。判据见 tests/data/annotator_qualification_v2_prereg.json")}


def main():
    # ── 资格考(协议既有规定; 2026-09-07 起**真的**强制执行) ──
    print("=== 标注者资格考(留一法·锚例 top1≥4/5) ===", flush=True)
    quals = [qualify(m) for m in MODELS]
    for q in quals:
        print(f"  {q['model']:22s} {q['hits']}/{q['of']} {'合格' if q['qualified'] else '★不合格, 剔除'}", flush=True)
    adm = admit_annotators(quals)
    globals()["QUAL_REPORT"] = {"per_model": quals, **adm}
    if adm["admit"] is None:
        # ★ 扣发路径也要带参数: 「哪一批语料、哪个截断下没人合格」本身就是要复核的事实
        RUN_PARAMS["run_gates_MODELS"] = RUN_PARAMS["annotators_actually_used"] = list(MODELS)
        RUN_PARAMS["gate_protocol_version"] = GATE_PROTOCOL_VERSION
        RUN_PARAMS["gate_protocol_hash"] = gate_protocol_hash()
        out = {"gate": "九结分类学验收", "overall_pass": None, "run_params": RUN_PARAMS,
               "★withheld": adm["reason"], "annotator_qualification": globals()["QUAL_REPORT"]}
        os.makedirs(_OUT_DIR, exist_ok=True)
        json.dump(out, open(os.path.join(_OUT_DIR, "gates_result.json"), "w"),
                  ensure_ascii=False, indent=1)
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 2      # ★ 扣发, 不是失败也不是通过
    globals()["MODELS"] = adm["admit"]
    print(f"进入验收的标注者: {globals()['MODELS']}\n", flush=True)

    print(f"样本 {len(SAMPLE)} 条 · 标注者 {MODELS}", flush=True)
    dists = {m: {} for m in MODELS}
    jobs = [(m, it) for m in MODELS for it in SAMPLE]
    with ThreadPoolExecutor(max_workers=8) as ex:
        for (m, _), (iid, dv) in zip(jobs, ex.map(annot_dist, jobs)):
            dists[m][iid] = dv
    cover = {m: sum(1 for v in dists[m].values() if v) for m in MODELS}
    print("分布标注覆盖:", cover, flush=True)
    # ★★ 2026-09-07: 原始逐条标注**必须落盘**。
    #   此前只落聚合数 ⇒ 2026-09-07 那次 430+ 次调用的原始数据**全部丢掉**,
    #   而下一个问题(误差棒/自助重采样/逐条复核/G-K3 实证版)全都要它 ——
    #   于是「想知道 JS 的置信区间」就得**再花 430 次调用**, 而一行 json.dump 本可避免。
    #   ★ 这与本项目反复栽的「只存聚合值, 回答不了『是哪一条在动』」同族:
    #     聚合是**判决**要的, 逐条是**复核**要的, 两者不可互相替代。
    _raw = os.path.join(_OUT_DIR, "raw_annotations.json")
    os.makedirs(os.path.dirname(_raw), exist_ok=True)
    RUN_PARAMS["run_gates_MODELS"] = RUN_PARAMS["annotators_actually_used"] = list(MODELS)
    RUN_PARAMS["gate_protocol_version"] = GATE_PROTOCOL_VERSION
    RUN_PARAMS["gate_protocol_hash"] = gate_protocol_hash()
    json.dump({"★what": "逐条原始标注分布, 供自助重采样/逐条复核/重跑对照; 聚合数在 gates_result.json",
               "run_params": RUN_PARAMS,
               "annotators": MODELS, "sample_ids": [x["id"] for x in SAMPLE],
               "coverage": cover, "dists": dists},
              open(_raw, "w"), ensure_ascii=False)
    print(f"原始标注已落盘: {_raw}", flush=True)

    if SKIP_GK2:
        # ★ 外部效度语料是**帖子**, 没有 followed_up / replied_by_op / u 这些互动字段,
        #   且 G-K2 早已被正式定性为**不可判**并冻结 N>=150 复测 ⇒ 本轮**不跑、不猜、不补**。
        facts = {}
        print("★ CCE_SKIP_GK2=1: 跳过 G-K2 事实抽取(外部语料无互动字段, 且 G-K2 已冻结)", flush=True)
    else:
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

    # ★★★ 2026-09-07: SKIP_GK2 时必须跳过**整个 G-K2 块**, 不只事实抽取。
    #   实测崩法: facts={} ⇒ observed_tier_from_facts 每条返 None ⇒ rows=[] ⇒
    #   下游按空列表算 ⇒ **IndexError**, 而那已经是 405 次标注调用**之后**。
    #   ★ 那次没丢数据, 只因为逐条原始标注的落盘被挪到了 G-K2 **之前** —— 同日刚修的那条。
    #     若还是老代码, 405 次调用的原始数据会跟着崩溃一起蒸发。
    if SKIP_GK2:
        gk2 = {"n": 0, "pass": None,
               "★withheld": "CCE_SKIP_GK2=1 —— 外部语料无 followed_up/replied_by_op 等互动字段, "
                            "且 G-K2 已于 2026-08-07 正式定性为不可判并冻结 N>=150 复测。"
                            "★ 不跑、不猜、不补; 扣发 != 不通过。",
               "rows": []}
        rows, diag = [], None
    else:
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
           "run_params": RUN_PARAMS,
           "sample_n": len(SAMPLE), "annotators": MODELS, "coverage": cover,
           "G_K1v2_分布一致性": gk1, "G_K2v2_成本档预测": gk2, "混淆诊断": diag,
           "annotator_qualification": globals().get("QUAL_REPORT"),
           # ★ 2026-09-07: 资格考此前**只被报告, 不进判决** —— 于是 4/5 不合格也能 overall_pass=True。
           #   现在它是判决的一部分。三项缺一即不通过。
           # ★ SKIP_GK2 下 **不发 overall_pass** —— 缺一道闸就宣称整体通过, 正是本仓修过的 fail-open。
           "overall_pass": (None if SKIP_GK2 else
                            bool(gk1["pass"] and gk2["pass"]
                                 and (globals().get("QUAL_REPORT") or {}).get("status") == "OK")),
           "★overall_withheld_because": ("G-K2 本轮未跑(外部语料无互动字段且 G-K2 已冻结) ⇒ "
                                          "整体判决**扣发**, 只报 G-K1 与类实现台账") if SKIP_GK2 else None,
           "★pass_components": {"G_K1": gk1["pass"], "G_K2": gk2["pass"],
                                "annotator_qualification":
                                    (globals().get("QUAL_REPORT") or {}).get("status")}}
    os.makedirs(_OUT_DIR, exist_ok=True)
    json.dump(out, open(os.path.join(_OUT_DIR, "gates_result.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "混淆诊断"}, ensure_ascii=False, indent=1))
    if diag:
        print("\n=== 混淆诊断 ===")
        print(json.dumps(diag, ensure_ascii=False, indent=1)[:2000])


if __name__ == "__main__":
    main()
