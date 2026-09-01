#!/usr/bin/env python3
# ⚠️ 名字骗人: 这**不是**实验脚本, 是生产内核。
#    它持有本体常量与 LLM 调用管道, 被 6 个生产文件 + 5 个探针共用。
#    删除 / 改名 / 归档会拆掉引擎 —— 依赖面由 tests/test_cce_module_boundary.py 逐文件钉死。
#    (2026-09-01: 我在整链审计里正是按名字把它误判为"实验脚本占仓库过半"的清理对象。)
"""
v4 因果链 —— 生产级硬化校验（four-layer causal chain full validation）

目标：把四层因果链从「方向性成立」硬化到「已证/待迭代」判决。
  全 4 模型(M3 / 千问3.8 / GLM-5.2 / Kimi-K3) × 16 案例(多模态) × 含≥5 负向 congruence。

相对原型(exp_v4_causal_chain.py)的三处硬化：
  1. 需求层用受控 17 类词表(config/need_taxonomy.json controlled_keys) → 首次可算需求层跨模型 JS 散度；
  2. 评价桥 goal_congruence 由单标量拆多维(congruence_direction 促进/威胁 + need_status 已满足/未满足) →
     可区分「内容有帮助(促进+已满足→正情绪)」vs「自查触发威胁(威胁+未满足→fear)」；
  3. 案例集补 ≥5 负向 congruence(健康死亡威胁 / 情感绝望 / 地震恐惧 / 失恋怀旧 / 焦虑倾诉) → 首验负向分支。

四层受控词表全部从 config/常量读：
  desire 9(config/desire_taxonomy.json) · need 17(config/need_taxonomy.json) ·
  emotion 13 / action 7(沿用 exp_v4_causal_chain.py 常量)。

四项校验：
  1. 各层跨 4 模型一致度：每层两两 JS 均值 + top 众数一致率(desire/need/emotion/action)。
  2. 层间连贯率：chain_trace 能否 情绪←需求×congruence、需求←欲望×情境；负向 congruence 情绪是否转负。
  3. 稳定性：3 案例(1 正 congruence + 1 负 congruence + 1 对话)× N=5(M3)，每层采样频率收敛；行动层重点。
  4. congruence 正负分叉：同/近需求在正负 congruence 下是否分叉出相反情绪。

用法：
  python3 exp_v4_full_validation.py smoke   # M3 单案例四层结构冒烟
  python3 exp_v4_full_validation.py         # 全量四校验 + 报告 + 增量落盘
"""
import os, sys, json, time, math
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exp_crossmodel_desire import (
    call_model, build_cases, MODELS,
    extract_json_robust, js_divergence, cosine,
)
from exp_v4_causal_chain import EMOTIONS, ACTIONS, POS_EMO, NEG_EMO

ROOT = os.environ.get("VSE_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")
CAL = os.path.join(RESULTS, "calibration")
os.makedirs(CAL, exist_ok=True)

# ── 四层受控词表：全部从权威 config 读，禁止内嵌 ──
with open(os.path.join(ROOT, "config", "desire_taxonomy.json"), encoding="utf-8") as f:
    _DT = json.load(f)
    DESIRES = _DT["canonical"]
    DESIRE_DEFS = _DT["definitions"]
    assert len(DESIRES) == 9

with open(os.path.join(ROOT, "config", "need_taxonomy.json"), encoding="utf-8") as f:
    _NT = json.load(f)
    NEED_KEYS = _NT["controlled_keys"]                 # 17 类 code
    NEED_TYPES = {n["code"]: n for n in _NT["need_types"]}
    NEED_EMOTION_MAP = {m["need"]: m for m in _NT["need_emotion_map"]["map"]}
    assert len(NEED_KEYS) == 17

# 四层输出较长(17 类需求 + 三分布 + chain_trace)，全模型抬到 8000 留余量
for _mk in MODELS:
    MODELS[_mk]["max_tokens"] = 8000

STAB_MODELS = ["M3", "Qwen3.8", "GLM5.2", "KimiK3"]


# ═══════════════════════════════════════════════════════════════
# 案例集：16 案例，5 模态，≥6 负向 congruence（全部取自真实 assets 内容）
#   expect: 预期 congruence 方向(pos=促进/满足, neg=威胁/受阻)，供分叉验证
# ═══════════════════════════════════════════════════════════════
def _load(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return json.load(f)


def _cmts(items, key, n=8, likekey=None):
    out = []
    for c in items[:n]:
        t = c.get(key, "")
        if likekey and c.get(likekey) is not None:
            out.append(f"  · {t}（{c[likekey]}赞）")
        else:
            out.append(f"  · {t}")
    return "\n".join(out)


def build_full_cases():
    """返回 {cid: {modality,type,expect,input}}。expect∈{'pos','neg'}。"""
    base = build_cases()   # 复用 crossmodel 的 10 案例输入构造
    cases = {}

    def take(cid, modality, mtype, expect):
        cases[cid] = {"modality": modality, "type": mtype, "expect": expect,
                      "input": base[cid]["input"]}

    # ── 正向 congruence（内容有帮助/愉悦/满足）──
    take("IT_ad_goods",     "图文", "平价好物种草", "pos")   # 拥有欲/N07
    take("IT_life_kitchen", "图文", "唯美生活方式", "pos")   # 向往欲/N14
    take("IT_life_roomtour","图文", "室内一镜到底", "pos")   # 向往欲/N14
    take("CM_food",         "评论", "美食探店",     "pos")   # 向往/归属
    take("CM_knowledge",    "评论", "文化科普",     "pos")   # 好奇/N04
    take("VID_mc_xiongchu", "视频", "MC建造长视频", "pos")   # 怀旧/N17
    take("VID_perfect_mv",  "视频", "爱情MV",       "pos")   # 爱/N12

    # ── 补充正向（图文 ad_kitchen / kn_names，一句话 trivia）──
    ak = _load("assets/image-text/ad_kitchen.json"); akst = ak.get("stats", {})
    cases["IT_ad_kitchen"] = {"modality": "图文", "type": "厨房好物种草", "expect": "pos",
        "input": f"""【内容类型】厨房好物种草（抖音图文）
【作者】{ak.get('author','')}
【画面内文案】{ak.get('title_copy','')}
【客观视觉】开放式厨房 + 8 件懒人收纳神器逐一展示
【互动数据】赞{akst.get('digg_count')} 评论{akst.get('comment_count')} 收藏{akst.get('collect_count')}
【热门评论】
{_cmts(ak.get('comments',[]), 'text', 6, 'likes')}"""}

    kn = _load("assets/image-text/kn_names.json"); knst = kn.get("stats", {})
    cases["IT_kn_names"] = {"modality": "图文", "type": "冷知识科普", "expect": "pos",
        "input": f"""【内容类型】冷知识科普（抖音图文）
【作者】{kn.get('author','')}
【画面内文案】{kn.get('title_copy','')}
【客观视觉】一组日常物件配上「原来它们都有名字」的科普图卡
【互动数据】赞{knst.get('digg_count')} 评论{knst.get('comment_count')} 收藏{knst.get('collect_count')}
【热门评论】
{_cmts(kn.get('comments',[]), 'text', 6, 'likes')}"""}

    cases["SENT_names_trivia"] = {"modality": "一句话", "type": "科普金句", "expect": "pos",
        "input": "【单条文案】原来这些东西还有名字 #涨知识 #冷知识 #科普"}

    # ── 负向 congruence（需求受阻/威胁/冲突/恐惧）──
    # 1) 健康死亡威胁（图文）：心梗脑梗，评论区自查焦虑
    hk = _load("assets/image-text/kn_health.json"); hkst = hk.get("stats", {})
    cases["IT_kn_health"] = {"modality": "图文", "type": "健康风险科普", "expect": "neg",
        "input": f"""【内容类型】健康风险科普（抖音图文）
【作者】{hk.get('author','')}
【画面内文案】{hk.get('title_copy','')}
【客观视觉】白底大标题「要想不得心梗脑梗，一定要知道的生命9要素」，列举各项指标红线
【互动数据】赞{hkst.get('digg_count')} 评论{hkst.get('comment_count')} 收藏{hkst.get('collect_count')}
【热门评论】
{_cmts(hk.get('comments',[]), 'text', 6, 'likes')}"""}

    # 2) 情感绝望（对话）：tangguo 首夜深聊，人生无望/没人要
    take("DLG_tangguo", "对话", "陌生人深夜倾诉", "neg")

    # 3) 地震恐惧 + flirt deflect（对话）：dashewan
    take("DLG_dashewan", "对话", "陌生人破冰(地震)", "neg")

    # 4) 健康威胁一句话（一句话）
    cases["SENT_health_scare"] = {"modality": "一句话", "type": "健康威胁金句", "expect": "neg",
        "input": "【单条文案】要想不得心梗脑梗，一定要知道的生命「9」要素 #心肌梗死 #健康科普"}

    # 5) 情感绝望一句话（一句话）：取自 tangguo 真实原话
    cases["SENT_despair"] = {"modality": "一句话", "type": "情感倾诉金句", "expect": "neg",
        "input": "【单条深夜倾诉】各种各样的问题很累，我想慢下来，逃离人海城市。我三年都没脱单了，追的不喜欢，喜欢的配不上，我好像真的没人要，人生无望吧。"}

    # 6) 失恋怀旧（评论）：music-cover 无声卡翻唱，失恋主题评论
    mc = _load("assets/comments/douyin-music-cover.json"); mcst = mc.get("stats", {})
    cases["CM_music_breakup"] = {"modality": "评论", "type": "翻唱/失恋主题", "expect": "neg",
        "input": f"""【内容类型】无声卡翻唱（抖音音乐视频，仅文案+评论区）
【作者】{mc.get('author','')}
【视频文案】{mc.get('desc','')}
【互动数据】赞{mcst.get('digg_count')} 评论{mcst.get('comment_count')} 收藏{mcst.get('collect_count')}
【热门评论】
{_cmts(mc.get('comments',[]), 'text', 7, 'digg_count')}"""}

    return cases


# ═══════════════════════════════════════════════════════════════
# PROMPT：四层联合分布 + 多维评价桥 + 受控 17 类需求
# ═══════════════════════════════════════════════════════════════
def _desire_taxo_text():
    lines = ["欲望9类定义（触发视角：看完这条内容观众想要什么）："]
    for i, name in enumerate(DESIRES, 1):
        lines.append(f"{i}. {name}：{DESIRE_DEFS[name]}")
    return "\n".join(lines)


def _need_taxo_text():
    lines = ["需求受控17类（JTBD/ODI 结果导向，code + 名称 + 一句定义；标注时选 code 并给情境槽）："]
    for code in NEED_KEYS:
        n = NEED_TYPES[code]
        lines.append(f"- {code}（{n['name_cn']}）：{n['definition'][:48]}")
    return "\n".join(lines)


DESIRE_TAXO = _desire_taxo_text()
NEED_TAXO = _need_taxo_text()


def build_prompt(case_input):
    emo_keys = "、".join(EMOTIONS)
    act_keys = "、".join(ACTIONS)
    emo_json = ",".join(f'"{e}":0.0' for e in EMOTIONS)
    act_json = ",".join(f'"{a}":0.0' for a in ACTIONS)
    des_json = ",".join(f'"{d}":0.0' for d in DESIRES)
    need_codes = "、".join(NEED_KEYS)
    return f"""你是爆款内容心理拆解专家。对以下内容做「因果链逆问题」拆解：从可观测话语/评论，反推观众心理完整因果链，输出每一层占比权重(联合分布)。

因果链结构(必须按此顺序推导，后一层要能从前一层导出，不能各层各拍)：
  欲望(稳定潜变量) →(情境事件) 需求(情境化目标) →(评价) 情绪 → 行动倾向 → 行为/话语(可观测)

{DESIRE_TAXO}

{NEED_TAXO}

【评价层(appraisal)——欲望与情绪之间的桥，本轮拆成多维】
  - goal_relevance(目标相关度 0-1)：情境对观众目标有多相关 → 决定情绪强度
  - congruence_direction(内容对需求是「促进」还是「威胁」)：内容帮观众趋近目标=促进；内容揭示威胁/让需求受阻=威胁；无关=中性
  - need_status(该需求当前「已满足」还是「未满足」)：内容当场满足了需求(有帮助/愉悦)=已满足；只勾起或揭示威胁却没解决=未满足
  - goal_congruence(正/负)：由上两维派生——促进且已满足=正；威胁或未满足(焦虑悬置)=负
  - coping_potential(应对潜能 高/中/低)：观众觉得自己能多大程度应对/获得 → 决定趋近还是回避
  关键区分：「内容有帮助」=促进+已满足→正情绪；「自查后发现威胁却没解法」=威胁+未满足→fear恐惧等负情绪。

【情绪层】GoEmotions 离散集 13 类：{emo_keys}
【行动倾向层】Frijda action tendency 7 类：{act_keys}

【待拆解内容】
{case_input}

【输出要求】严格输出一个 JSON(可放 ```json 代码块内)，不要输出任何解释文字。结构：
{{
  "desire_layer": {{"distribution": {{{des_json}}}, "note": "为何这几类欲望被激活"}},
  "need_layer": [
    {{"code": "从上面17类里选(如 N07_占有资源)", "context_slot": "半自由文本:触发情境", "weight": 0.0, "derived_from": "由<哪个欲望>经<什么情境事件>衍生"}}
  ],
  "appraisal": {{
    "goal_relevance": 0.0,
    "congruence_direction": "促进 或 威胁 或 中性",
    "need_status": "已满足 或 未满足",
    "goal_congruence": "正 或 负",
    "coping_potential": "高 或 中 或 低",
    "note": "评价如何决定下面情绪的正负与强度"
  }},
  "emotion_layer": {{"distribution": {{{emo_json}}}, "note": "情绪如何从 需求×congruence 推出"}},
  "action_tendency_layer": {{"distribution": {{{act_json}}}}},
  "chain_trace": "欲望X →(情境Y)→ 需求Z(写code) →(评价:direction/need_status/congruence正负,coping)→ 情绪W → 行动倾向V 的完整一句话推导(用具体名字填 X/Y/Z/W/V，必须连贯读通)",
  "evidence": {{"desire":"逐字引用","need":"逐字引用","emotion":"逐字引用","action":"逐字引用"}}
}}
硬约束：
- desire_layer/emotion_layer/action_tendency_layer 的 distribution 必须且只能含上面列出的固定键，每层权重之和=1(可为0)；
- need_layer 是列表，code 必须取自受控17类({need_codes})，各 need 的 weight 之和=1；
- chain_trace 必须显式从欲望到行动倾向连贯，情绪要真能从「需求×goal_congruence」导出，禁止情绪凭空出现；
- evidence 用内容/评论里的原话。"""


# ═══════════════════════════════════════════════════════════════
# 解析
# ═══════════════════════════════════════════════════════════════
def norm_layer(dist, keys):
    if not isinstance(dist, dict):
        return None
    vec = []
    for k in keys:
        v = dist.get(k, None)
        if v is None:
            for kk, vv in dist.items():
                s = str(kk)
                if s in k or k in s or any(p and p in s for p in [k[:6], k[-4:]]):
                    v = vv; break
        try:
            v = float(v)
        except Exception:
            v = 0.0
        vec.append(max(0.0, v))
    s = sum(vec)
    return [x / s for x in vec] if s > 0 else None


def need_to_vec(need_list):
    """把 need_layer 列表映射到 17 维受控向量(按 code 前缀匹配求和归一)。返回 (vec, slots)。"""
    if not isinstance(need_list, list):
        return None, []
    agg = {k: 0.0 for k in NEED_KEYS}
    slots = []
    for item in need_list:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", ""))
        w = item.get("weight", 0)
        try:
            w = float(w)
        except Exception:
            w = 0.0
        matched = None
        for k in NEED_KEYS:
            kc = k.split("_")[0]            # N01
            if code == k or code.startswith(kc) or kc in code:
                matched = k; break
        if matched is None:                # 尝试用中文名匹配
            for k in NEED_KEYS:
                if NEED_TYPES[k]["name_cn"][:3] in code:
                    matched = k; break
        if matched:
            agg[matched] += max(0.0, w)
            slots.append({"code": matched, "slot": item.get("context_slot", ""), "w": w})
    vec = [agg[k] for k in NEED_KEYS]
    s = sum(vec)
    return ([x / s for x in vec] if s > 0 else None), slots


def parse_v4(parsed):
    if not isinstance(parsed, dict):
        return None
    d = norm_layer((parsed.get("desire_layer") or {}).get("distribution"), DESIRES)
    e = norm_layer((parsed.get("emotion_layer") or {}).get("distribution"), EMOTIONS)
    a = norm_layer((parsed.get("action_tendency_layer") or {}).get("distribution"), ACTIONS)
    nvec, nslots = need_to_vec(parsed.get("need_layer") or [])
    app = parsed.get("appraisal") or {}
    return {
        "desire_vec": d, "emotion_vec": e, "action_vec": a, "need_vec": nvec,
        "need_slots": nslots, "appraisal": app,
        "chain_trace": parsed.get("chain_trace", ""), "evidence": parsed.get("evidence", {}),
    }


def top_label(vec, keys):
    if not vec:
        return None
    return keys[max(range(len(vec)), key=lambda j: vec[j])]


def call_parse(mk, case_input, temperature, note):
    """单次调用+解析，任何异常都吞成 ok=False，绝不外抛(防单点崩整批)。"""
    try:
        content, meta = call_model(mk, build_prompt(case_input), temperature=temperature)
    except Exception as e:
        return "", None, None, {"error": f"EXC {type(e).__name__}: {e}", "n_calls": 1, "elapsed": 0}, False
    try:
        parsed = extract_json_robust(content, log_note=note)
        pv = parse_v4(parsed) if parsed else None
    except Exception as e:
        return content, None, None, {**(meta or {}), "error": f"PARSE_EXC {type(e).__name__}: {e}"}, False
    ok = bool(pv is not None and pv["desire_vec"] and pv["emotion_vec"] and pv["action_vec"] and pv["need_vec"])
    return content, parsed, pv, meta, ok


def load_existing_ok(path):
    """幂等续跑：若结果文件已存在且 ok=True，返回该 rec，否则 None（须重跑）。"""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        if rec.get("ok") and rec.get("pv"):
            return rec
    except Exception:
        return None
    return None


# ═══════════════════════════════════════════════════════════════
# 指标
# ═══════════════════════════════════════════════════════════════
def mean_pairwise_js(vecs):
    valid = [v for v in vecs if v]
    if len(valid) < 2:
        return None
    js = [js_divergence(valid[i], valid[j]) for i in range(len(valid)) for j in range(i + 1, len(valid))]
    return round(sum(js) / len(js), 4)


def top_consistency(vecs, keys):
    valid = [v for v in vecs if v]
    if not valid:
        return None, None
    tops = [top_label(v, keys) for v in valid]
    c = Counter(tops)
    mode, n = c.most_common(1)[0]
    return mode, round(n / len(valid), 3)


def per_class_freq(vecs, keys):
    valid = [v for v in vecs if v]
    out, n = {}, len(valid)
    for ci, k in enumerate(keys):
        vals = [v[ci] for v in valid]
        mu = sum(vals) / n if n else 0.0
        sd = math.sqrt(sum((x - mu) ** 2 for x in vals) / n) if n else 0.0
        out[k] = (round(mu, 3), round(sd, 3))
    return out


def emo_valence(top_emo):
    if top_emo in POS_EMO:
        return "pos"
    if top_emo in NEG_EMO:
        return "neg"
    return "neutral"   # curiosity/desire 视中性(desire渴望在向往欲下是愉悦性longing)


def coherence_check(pv, expect):
    """层间连贯 + 负向分支自动核查。返回 flags(空=通过)。"""
    flags = []
    ct = pv["chain_trace"] or ""
    if "→" not in ct and "->" not in ct:
        flags.append("chain_trace无箭头")
    if len(ct) < 20:
        flags.append("chain_trace过短")
    top_emo = top_label(pv["emotion_vec"], EMOTIONS)
    cong = str(pv["appraisal"].get("goal_congruence", ""))
    val = emo_valence(top_emo)
    if "正" in cong and val == "neg":
        flags.append(f"cong正但top情绪{top_emo}(负)")
    if "负" in cong and val == "pos":
        flags.append(f"cong负但top情绪{top_emo}(正)")
    # 层间：需求 top 的来源欲望是否与 desire top 一致(用 need_taxonomy upstream_desires 核查)
    need_top = top_label(pv["need_vec"], NEED_KEYS)
    des_top = top_label(pv["desire_vec"], DESIRES)
    if need_top and des_top:
        ups = [u["desire"] for u in NEED_TYPES[need_top].get("upstream_desires", [])]
        ups = [u.replace("(被爱面向)", "").replace("(被爱面向)", "") for u in ups]
        if not any(des_top in u or u in des_top for u in ups):
            flags.append(f"需求{need_top}上游≠欲望top{des_top}")
    # 需求→情绪：top 情绪是否在该需求 satisfied/blocked 情绪集内
    if need_top and top_emo and need_top in NEED_EMOTION_MAP:
        m = NEED_EMOTION_MAP[need_top]
        allowed = set(m["satisfied_emotions"]) | set(m["blocked_emotions"])
        if top_emo not in allowed:
            flags.append(f"top情绪{top_emo}不在需求{need_top}情绪集")
    return flags


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════
def run_smoke():
    cases = build_full_cases()
    cid = "IT_kn_health"
    ci = cases[cid]
    content, parsed, pv, meta, ok = call_parse("M3", ci["input"], 0.0, "v4full smoke")
    print(f"[{cid}] elapsed={meta.get('elapsed')} err={meta.get('error')} ok={ok}")
    if pv:
        print("desire top:", top_label(pv["desire_vec"], DESIRES))
        print("need top:", top_label(pv["need_vec"], NEED_KEYS), "| slots:", [s["code"] for s in pv["need_slots"]])
        print("emotion top:", top_label(pv["emotion_vec"], EMOTIONS))
        print("action top:", top_label(pv["action_vec"], ACTIONS))
        print("appraisal:", json.dumps(pv["appraisal"], ensure_ascii=False))
        print("chain_trace:", pv["chain_trace"][:260])
        print("coherence flags:", coherence_check(pv, ci["expect"]))
    else:
        print("PARSE FAIL head:", (content or "")[:400])


STAB_CASES = [("IT_life_kitchen", "pos"), ("IT_kn_health", "neg"), ("DLG_tangguo", "dialogue-neg")]
STAB_N = 5


def _acc(stats, mk, meta):
    stats[mk]["calls"] += meta.get("n_calls", 0)
    stats[mk]["elapsed"] += meta.get("elapsed", 0) or 0
    u = meta.get("usage", {}) or {}
    stats[mk]["ptok"] += u.get("prompt_tokens", 0) or 0
    stats[mk]["ctok"] += u.get("completion_tokens", 0) or 0


def run_full():
    cases = build_full_cases()
    mkeys = list(MODELS.keys())
    print(f"=== v4 FULL VALIDATION: {len(cases)} cases × {len(mkeys)} models "
          f"(neg={sum(1 for c in cases.values() if c['expect']=='neg')}) ===")
    stats = {mk: {"calls": 0, "elapsed": 0.0, "fail": 0, "ptok": 0, "ctok": 0, "consec_fail": 0, "skipped": False}
             for mk in mkeys}
    per = {}   # cid -> mk -> rec

    ck = 0
    for cid, ci in cases.items():
        per[cid] = {}
        print(f"\n[{cid}] {ci['modality']}/{ci['type']} expect={ci['expect']}")
        for mk in mkeys:
            fpath = os.path.join(RESULTS, f"v4full_{cid}_{mk}.json")
            existing = load_existing_ok(fpath)
            if existing is not None:      # 幂等续跑：已有 ok 结果，直接复用不重调
                per[cid][mk] = existing
                stats[mk]["consec_fail"] = 0
                print(f"    {mk:9s} RESUME(已有ok, skip)")
                continue
            if stats[mk]["skipped"]:
                per[cid][mk] = {"ok": False, "skipped": True, "pv": None}
                print(f"    {mk:9s} SKIPPED(连续3次失败)")
                continue
            content, parsed, pv, meta, ok = call_parse(mk, ci["input"], 0.0, f"v4full {cid} {mk}")
            _acc(stats, mk, meta)
            rec = {"case": cid, "model": mk, "expect": ci["expect"], "ok": ok,
                   "raw": content, "parsed": parsed, "pv": pv, "meta": meta}
            with open(os.path.join(RESULTS, f"v4full_{cid}_{mk}.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
            per[cid][mk] = rec
            if not ok:
                stats[mk]["fail"] += 1
                stats[mk]["consec_fail"] += 1
                print(f"    {mk:9s} {meta.get('elapsed')}s FAIL ({meta.get('error') or 'parse'}) consec={stats[mk]['consec_fail']}")
                if stats[mk]["consec_fail"] >= 3:
                    stats[mk]["skipped"] = True
                    print(f"    !! {mk} 连续3次失败 → 后续跳过并标注")
                continue
            stats[mk]["consec_fail"] = 0
            flags = coherence_check(pv, ci["expect"])
            print(f"    {mk:9s} {meta.get('elapsed')}s des={top_label(pv['desire_vec'],DESIRES)} "
                  f"need={top_label(pv['need_vec'],NEED_KEYS)} emo={top_label(pv['emotion_vec'],EMOTIONS)} "
                  f"act={top_label(pv['action_vec'],ACTIONS)} cong={pv['appraisal'].get('goal_congruence')} "
                  f"dir={pv['appraisal'].get('congruence_direction')} flags={len(flags)}")
        ck += 1
        if ck % 2 == 0:   # 增量落盘：每2案例
            _dump_incremental(cases, per, stats, mkeys)
            print(f"  💾 增量落盘 @ {ck} 案例")

    _dump_incremental(cases, per, stats, mkeys)

    # ── 校验1：各层跨模型一致度 ──
    layer_consensus = analyze_layer_consensus(cases, per, mkeys)
    # ── 校验2：层间连贯率 + 负向分支 ──
    coherence = analyze_coherence(cases, per, mkeys)
    # ── 校验4：congruence 正负分叉 ──
    fork = analyze_congruence_fork(cases, per, mkeys)
    # ── 校验3：稳定性(全模型 3 案例 × N=5) ──
    stability = run_stability(cases, stats, mkeys)

    out = {
        "cases": {cid: {k: ci[k] for k in ("modality", "type", "expect")} for cid, ci in cases.items()},
        "layer_consensus": layer_consensus, "coherence": coherence,
        "congruence_fork": fork, "stability": stability,
        "model_stats": {mk: {k: v for k, v in stats[mk].items() if k != "consec_fail"} for mk in mkeys},
    }
    with open(os.path.join(RESULTS, "v4full_ALL.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    write_report(cases, per, out)
    print("\n=== DONE ===")
    print("layer_consensus:", json.dumps(layer_consensus["layer_summary"], ensure_ascii=False))
    print("neg_branch:", json.dumps(coherence["neg_branch"], ensure_ascii=False))
    print("model_stats:", json.dumps(out["model_stats"], ensure_ascii=False))


def _dump_incremental(cases, per, stats, mkeys):
    slim = {}
    for cid in per:
        slim[cid] = {}
        for mk in per[cid]:
            r = per[cid][mk]
            pv = r.get("pv")
            slim[cid][mk] = {
                "ok": r.get("ok"), "skipped": r.get("skipped", False),
                "desire_top": top_label(pv["desire_vec"], DESIRES) if pv else None,
                "need_top": top_label(pv["need_vec"], NEED_KEYS) if pv else None,
                "emotion_top": top_label(pv["emotion_vec"], EMOTIONS) if pv else None,
                "action_top": top_label(pv["action_vec"], ACTIONS) if pv else None,
                "appraisal": pv["appraisal"] if pv else None,
                "chain_trace": pv["chain_trace"] if pv else None,
            }
    with open(os.path.join(RESULTS, "v4full_progress.json"), "w", encoding="utf-8") as f:
        json.dump({"per_case_slim": slim,
                   "model_stats": {mk: {k: v for k, v in stats[mk].items() if k != "consec_fail"} for mk in mkeys}},
                  f, ensure_ascii=False, indent=2)


def analyze_layer_consensus(cases, per, mkeys):
    layers = [("desire", "desire_vec", DESIRES), ("need", "need_vec", NEED_KEYS),
              ("emotion", "emotion_vec", EMOTIONS), ("action", "action_vec", ACTIONS)]
    per_case = {}
    layer_js = {ln: [] for ln, _, _ in layers}
    layer_topagree = {ln: [] for ln, _, _ in layers}   # 每案例 top 众数一致率(众数票/ok模型数)
    for cid in cases:
        recs = per[cid]
        oks = {mk: recs[mk]["pv"] for mk in mkeys if recs[mk].get("ok")}
        row = {"n_ok": len(oks)}
        for ln, key, keys in layers:
            vecs = [oks[mk][key] for mk in oks if oks[mk][key]]
            j = mean_pairwise_js(vecs)
            mode, cons = top_consistency(vecs, keys)
            row[ln] = {"mean_js": j, "top_mode": mode, "top_consistency": cons}
            if j is not None:
                layer_js[ln].append(j)
            if cons is not None:
                layer_topagree[ln].append(cons)
        per_case[cid] = row
    layer_summary = {}
    for ln, _, _ in layers:
        js = layer_js[ln]; ta = layer_topagree[ln]
        layer_summary[ln] = {
            "mean_pairwise_JS": round(sum(js) / len(js), 4) if js else None,
            "mean_top_consistency": round(sum(ta) / len(ta), 3) if ta else None,
            "n_cases": len(js),
        }
    return {"per_case": per_case, "layer_summary": layer_summary}


def analyze_coherence(cases, per, mkeys):
    per_rec, flag_counter = {}, Counter()
    n_total, n_clean = 0, 0
    # 负向分支：expect=neg 案例中，模型判 cong负 且 top情绪∈NEG 的比例
    neg_cong_hits, neg_emo_hits, neg_total = 0, 0, 0
    pos_cong_hits, pos_total = 0, 0
    for cid in cases:
        expect = cases[cid]["expect"]
        for mk in mkeys:
            r = per[cid].get(mk)
            if not r or not r.get("ok"):
                continue
            pv = r["pv"]
            flags = coherence_check(pv, expect)
            per_rec[f"{cid}_{mk}"] = {"expect": expect, "flags": flags,
                                      "cong": pv["appraisal"].get("goal_congruence"),
                                      "dir": pv["appraisal"].get("congruence_direction"),
                                      "need_status": pv["appraisal"].get("need_status"),
                                      "emo_top": top_label(pv["emotion_vec"], EMOTIONS)}
            n_total += 1
            if not flags:
                n_clean += 1
            for fl in flags:
                flag_counter[fl.split("(")[0].split("≠")[0][:14]] += 1
            cong = str(pv["appraisal"].get("goal_congruence", ""))
            val = emo_valence(top_label(pv["emotion_vec"], EMOTIONS))
            if expect == "neg":
                neg_total += 1
                if "负" in cong:
                    neg_cong_hits += 1
                if val == "neg":
                    neg_emo_hits += 1
            else:
                pos_total += 1
                if "正" in cong:
                    pos_cong_hits += 1
    return {
        "per_rec": per_rec,
        "chain_coherence_rate": round(n_clean / n_total, 3) if n_total else None,
        "n_records": n_total, "n_clean": n_clean,
        "flag_hotspots": dict(flag_counter.most_common()),
        "neg_branch": {
            "neg_records": neg_total,
            "neg_congruence_hit_rate": round(neg_cong_hits / neg_total, 3) if neg_total else None,
            "neg_top_emotion_negative_rate": round(neg_emo_hits / neg_total, 3) if neg_total else None,
            "pos_records": pos_total,
            "pos_congruence_hit_rate": round(pos_cong_hits / pos_total, 3) if pos_total else None,
        },
    }


def analyze_congruence_fork(cases, per, mkeys):
    """同/近需求在正/负 congruence 下是否分叉出相反情绪：按 need_top 分组，比对正负案例 top 情绪价。"""
    rows = []
    by_need = {}
    for cid in cases:
        expect = cases[cid]["expect"]
        for mk in mkeys:
            r = per[cid].get(mk)
            if not r or not r.get("ok"):
                continue
            pv = r["pv"]
            nt = top_label(pv["need_vec"], NEED_KEYS)
            et = top_label(pv["emotion_vec"], EMOTIONS)
            by_need.setdefault(nt, {"pos": [], "neg": []})
            by_need[nt][expect if expect in ("pos", "neg") else "neg"].append(emo_valence(et))
    for nt, d in by_need.items():
        if d["pos"] and d["neg"]:
            pos_pos = sum(1 for v in d["pos"] if v == "pos") / len(d["pos"])
            neg_neg = sum(1 for v in d["neg"] if v == "neg") / len(d["neg"])
            rows.append({"need": nt, "n_pos": len(d["pos"]), "n_neg": len(d["neg"]),
                         "pos_case_posEmo_rate": round(pos_pos, 2),
                         "neg_case_negEmo_rate": round(neg_neg, 2),
                         "forked": pos_pos >= 0.5 and neg_neg >= 0.5})
    # 全局分叉：正案例 top 情绪价 vs 负案例 top 情绪价
    return {"by_need": rows}


def run_stability(cases, stats, mkeys):
    print(f"\n=== STABILITY: {len(STAB_CASES)} cases × N={STAB_N} × {len(STAB_MODELS)} models ===")
    layers = [("desire", "desire_vec", DESIRES), ("need", "need_vec", NEED_KEYS),
              ("emotion", "emotion_vec", EMOTIONS), ("action", "action_vec", ACTIONS)]
    result = {}
    for cid, tag in STAB_CASES:
        if cid not in cases:
            continue
        ci = cases[cid]
        result[cid] = {"tag": tag, "by_model": {}}
        print(f"\n[stab {cid}] ({tag})")
        for mk in STAB_MODELS:
            if stats[mk]["skipped"]:
                result[cid]["by_model"][mk] = {"skipped": True}
                continue
            pvs = []
            for r in range(STAB_N):
                spath = os.path.join(RESULTS, f"v4full_stab_{cid}_{mk}_run{r+1}.json")
                ex = load_existing_ok(spath)
                if ex is not None:            # 幂等续跑
                    pvs.append(ex["pv"]); continue
                content, parsed, pv, meta, ok = call_parse(mk, ci["input"], 0.7, f"v4stab {cid} {mk} r{r+1}")
                _acc(stats, mk, meta)
                rec = {"run": r + 1, "ok": ok, "raw": content, "parsed": parsed, "pv": pv, "meta": meta}
                with open(spath, "w", encoding="utf-8") as f:
                    json.dump(rec, f, ensure_ascii=False, indent=2)
                if ok:
                    pvs.append(pv)
                else:
                    stats[mk]["fail"] += 1
            ld = {}
            for ln, key, keys in layers:
                vecs = [pv[key] for pv in pvs if pv[key]]
                mode, cons = top_consistency(vecs, keys)
                ld[ln] = {"mean_pairwise_JS": mean_pairwise_js(vecs),
                          "top_mode": mode, "top_consistency": cons, "n": len(vecs)}
            result[cid]["by_model"][mk] = {"n_ok": len(pvs), "layers": ld}
            print(f"  {mk:9s} n_ok={len(pvs)}/{STAB_N} " +
                  " ".join(f"{ln}:JS={ld[ln]['mean_pairwise_JS']},top={ld[ln]['top_consistency']}"
                           for ln, _, _ in layers))
    return result


def write_report(cases, per, out):
    lc = out["layer_consensus"]; co = out["coherence"]; fk = out["congruence_fork"]; st = out["stability"]
    ms = out["model_stats"]; mkeys = list(MODELS.keys())
    L = []
    L.append("# v4 因果链 —— 生产级硬化校验报告\n")
    L.append(f"> 全 4 模型(M3 / 千问3.8 / GLM-5.2 / Kimi-K3) × {len(cases)} 案例(5 模态) × "
             f"{sum(1 for c in cases.values() if c['expect']=='neg')} 负向 congruence · 四层受控词表(欲望9/需求17/情绪13/行动7)\n")

    L.append("## 0. 四层可信度判决表\n")
    L.append("| 层 | 跨模型平均JS(↓好) | 跨模型top众数一致率(↑好) | 稳定性(见§3) | 判决 |")
    L.append("|---|---|---|---|---|")
    verdicts = {}
    for ln in ["desire", "need", "emotion", "action"]:
        s = lc["layer_summary"][ln]
        js, ta = s["mean_pairwise_JS"], s["mean_top_consistency"]
        # 判决启发：top一致≥0.7且JS≤0.25→已证；top≥0.55→方向性成立(待迭代)；否则待迭代
        if ta is not None and ta >= 0.7 and (js is not None and js <= 0.30):
            v = "已证(可进生产量化)"
        elif ta is not None and ta >= 0.55:
            v = "方向性成立/待迭代"
        else:
            v = "待迭代"
        verdicts[ln] = v
        L.append(f"| {ln} | {js} | {ta} | 见下 | **{v}** |")
    L.append("")

    L.append("## 1. 各层跨模型一致度（校验1）\n")
    L.append("| 案例 | 模态 | expect | okN | desireJS/top | needJS/top | emoJS/top | actJS/top |")
    L.append("|---|---|---|---|---|---|---|---|")
    for cid in cases:
        r = lc["per_case"][cid]
        def cell(ln):
            x = r[ln]; return f"{x['mean_js']}/{x['top_consistency']}"
        L.append(f"| {cid} | {cases[cid]['modality']} | {cases[cid]['expect']} | {r['n_ok']} | "
                 f"{cell('desire')} | {cell('need')} | {cell('emotion')} | {cell('action')} |")
    L.append("")
    L.append("**层级汇总（层越细 top 是否越不可信？需求层首次量化）**\n")
    L.append("| 层 | 类目数 | 平均两两JS | 平均top众数一致率 | 参与案例 |")
    L.append("|---|---|---|---|---|")
    ncls = {"desire": 9, "need": 17, "emotion": 13, "action": 7}
    for ln in ["desire", "need", "emotion", "action"]:
        s = lc["layer_summary"][ln]
        L.append(f"| {ln} | {ncls[ln]} | {s['mean_pairwise_JS']} | {s['mean_top_consistency']} | {s['n_cases']} |")
    L.append("")

    L.append("## 2. 层间连贯率 + 负向分支（校验2）\n")
    L.append(f"- **chain 连贯清洁率**（无任何连贯 flag 的记录比例）：`{co['chain_coherence_rate']}`（{co['n_clean']}/{co['n_records']}）")
    nb = co["neg_branch"]
    L.append(f"- **负向分支**：{nb['neg_records']} 条负向记录中，判 congruence=负 比例 `{nb['neg_congruence_hit_rate']}`，"
             f"top 情绪转负(fear/sadness/anger) 比例 `{nb['neg_top_emotion_negative_rate']}`")
    L.append(f"- **正向对照**：{nb['pos_records']} 条正向记录中，判 congruence=正 比例 `{nb['pos_congruence_hit_rate']}`")
    L.append(f"- **连贯 flag 热点**：{json.dumps(co['flag_hotspots'], ensure_ascii=False)}\n")

    L.append("## 3. 稳定性（校验3，N=5，temp=0.7；行动层重点）\n")
    for cid, sd in st.items():
        L.append(f"### {cid}（{sd['tag']}）\n")
        L.append("| 模型 | okN | desire top一致/JS | need top一致/JS | emotion top一致/JS | action top一致/JS |")
        L.append("|---|---|---|---|---|---|")
        for mk in STAB_MODELS:
            bm = sd["by_model"].get(mk, {})
            if bm.get("skipped"):
                L.append(f"| {mk} | SKIP | - | - | - | - |"); continue
            lay = bm.get("layers", {})
            def c(ln):
                x = lay.get(ln, {}); return f"{x.get('top_consistency')}/{x.get('mean_pairwise_JS')}"
            L.append(f"| {mk} | {bm.get('n_ok')} | {c('desire')} | {c('need')} | {c('emotion')} | {c('action')} |")
        L.append("")

    L.append("## 4. congruence 正负分叉（校验4）\n")
    L.append("> 同一需求 top 分组下，正向案例 top 情绪是否为正、负向案例 top 情绪是否为负（分叉=需求层核心假设成立）。\n")
    L.append("| 需求top | 正案例数 | 负案例数 | 正案例→正情绪率 | 负案例→负情绪率 | 分叉成立 |")
    L.append("|---|---|---|---|---|---|")
    for row in fk["by_need"]:
        L.append(f"| {row['need']} | {row['n_pos']} | {row['n_neg']} | {row['pos_case_posEmo_rate']} | "
                 f"{row['neg_case_negEmo_rate']} | {'✅' if row['forked'] else '❌'} |")
    L.append("")

    L.append("## 5. 模型调用成本 / 失败\n")
    L.append("| 模型 | 总调用 | 总耗时(s) | 解析失败 | 是否跳过 | prompt_tok | completion_tok |")
    L.append("|---|---|---|---|---|---|---|")
    for mk in mkeys:
        s = ms[mk]
        L.append(f"| {mk} | {s['calls']} | {round(s['elapsed'],1)} | {s['fail']} | {s.get('skipped')} | {s['ptok']} | {s['ctok']} |")
    L.append("")

    L.append("## 6. 对 v4 定稿的判决与建议\n")
    L.append("（数据驱动，人工据上表复核）\n")
    for ln in ["desire", "need", "emotion", "action"]:
        L.append(f"- **{ln} 层**：{verdicts[ln]}")
    L.append("")

    path = os.path.join(CAL, "exp_v4_full_validation.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"报告写入 {path}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(line_buffering=True)   # 行缓冲，防被 kill 时日志全丢
    except Exception:
        pass
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    if mode == "smoke":
        run_smoke()
    else:
        run_full()
