#!/usr/bin/env python3
# ⚠️ 名字骗人: 这**不是**实验脚本, 是生产内核。
#    它持有本体常量与 LLM 调用管道, 被 6 个生产文件 + 5 个探针共用。
#    删除 / 改名 / 归档会拆掉引擎 —— 依赖面由 tests/test_cce_module_boundary.py 逐文件钉死。
#    (2026-09-01: 我在整链审计里正是按名字把它误判为"实验脚本占仓库过半"的清理对象。)
"""
v4 因果链原型实验 —— 从「只输出欲望层」升级为输出完整四层因果链联合占比权重

因果链模型：
  欲望(稳定潜变量) →(情境事件) 需求(情境化目标/JTBD)
  →(评价 appraisal: goal-relevance / goal-congruence / coping-potential)
  → 情绪(GoEmotions 离散集) → 行动倾向(Frijda action tendency) → 行为/话语(可观测)

引擎做逆问题：从可观测话语反推整条链各层的占比权重(联合分布)。

前置结论(已证，直接采纳)：
  - 单次自报 MAGNITUDE 不可信、RANK 可信 → 占比权重靠采样 N 次频率，不信单次自报数字
  - 内容模态 4 模型共识好(top 一致 0.8)、对话模态框架错配 → 试点只用内容模态案例

三个测试：
  1. 层间连贯性：人工核查 chain_trace 是否真从「需求×goal-congruence」推出情绪(连贯/断链)
  2. 占比权重共识：M3 vs 千问3.8 对每层权重分布算 JS 散度(不只欲望，比需求/情绪/行动倾向每层)
  3. 权重稳定性：1 案例 M3 跑 N=5 次，每层采样频率是否收敛(欲望层已知稳 vs 新三层未知)

用法：
  python3 exp_v4_causal_chain.py smoke     # 单案例单模型冒烟(看 JSON 结构)
  python3 exp_v4_causal_chain.py           # 全量三测试 + 报告
"""
import os, sys, json, time, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exp_crossmodel_desire import (
    call_model, build_cases, MODELS,
    extract_json_robust, js_divergence, cosine,
)

ROOT = os.environ.get("VSE_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")
CAL = os.path.join(RESULTS, "calibration")
os.makedirs(CAL, exist_ok=True)

# ── 欲望类目：从唯一权威共享类表读，禁止各脚本内嵌（根治分类学脱节）──
# 权威源 md：~/.codex/skills/viral-psychology-excavator/references/desire-taxonomy.md
# 机器可读镜像：config/desire_taxonomy.json（改类目先改 md 再同步该文件）
TAXO_PATH = os.path.join(ROOT, "config", "desire_taxonomy.json")


def load_desire_taxonomy(path=TAXO_PATH):
    with open(path, "r", encoding="utf-8") as f:
        taxo = json.load(f)
    canon = taxo["canonical"]
    assert len(canon) == taxo.get("n", len(canon)) == 9, \
        f"权威类数不是 9：n={taxo.get('n')} len={len(canon)}"
    return taxo, canon


TAXONOMY_SPEC, DESIRES = load_desire_taxonomy()

# 四层输出长，reasoning 模型再留余量：全部抬到 8000
for _mk in MODELS:
    MODELS[_mk]["max_tokens"] = 8000

# ── 固定类目集（让每层像欲望层一样输出定长键分布，才能算 JS 散度）──
# 情绪层：GoEmotions 离散集取常用 13 类。
#   选 GoEmotions 离散集而非 VAD 三维的理由：
#   (a) chain_trace 要「说得出名字的情绪」——离散标签才能在推导链里被行动倾向层显式承接，
#       VAD 的 (valence,arousal,dominance) 连续坐标无法命名一个可被 Frijda 映射的具体情绪；
#   (b) 跨模型 JS 散度需要定长同键分布，离散类目天然满足，VAD 还要再分箱；
#   (c) 13 类覆盖爆款内容需要的趋近/厌恶两极(admiration/joy/desire/pride/love/gratitude/
#       nostalgia/curiosity/relief/approval vs fear/sadness/anger)。
EMOTIONS = [
    "admiration钦佩", "joy喜悦", "gratitude感激", "desire渴望", "nostalgia怀旧",
    "pride自豪", "love爱", "relief宽慰", "approval认同", "curiosity好奇",
    "fear恐惧", "sadness悲伤", "anger愤怒",
]
# 行动倾向层：Frijda action tendency 取 7 类(定长同键)
ACTIONS = [
    "approach趋近", "avoidance回避", "attend关注", "reject拒斥",
    "agonistic对抗", "interrupt中断", "dominate支配",
]

# 正/负向情绪划分(用于连贯性自动初筛：goal-congruence 正应配正向情绪 top)
POS_EMO = {"admiration钦佩", "joy喜悦", "gratitude感激", "desire渴望", "nostalgia怀旧",
           "pride自豪", "love爱", "relief宽慰", "approval认同"}
NEG_EMO = {"fear恐惧", "sadness悲伤", "anger愤怒"}
# curiosity好奇 视为中性(趋近但非正负价)

def build_taxonomy_text(spec):
    """从共享类表动态拼「欲望N类定义」提示段，类名/定义全部来自 config，禁止内嵌。"""
    defs = spec["definitions"]
    lines = [f"欲望{spec['n']}类定义(触发视角：看完这条内容观众想要什么)："]
    for i, name in enumerate(spec["canonical"], 1):
        lines.append(f"{i}. {name}：{defs[name]}")
    lines.append(
        "划界：「求链接/想买」=拥有欲；「想住进去/想过这种生活」=向往欲；"
        "「我属于这群人」=归属欲；「想成为那种人」=成为欲。"
    )
    return "\n".join(lines)


TAXONOMY = build_taxonomy_text(TAXONOMY_SPEC)


def build_v4_prompt(case_input):
    emo_keys = "、".join(EMOTIONS)
    act_keys = "、".join(ACTIONS)
    emo_json = ",".join(f'"{e}":0.0' for e in EMOTIONS)
    act_json = ",".join(f'"{a}":0.0' for a in ACTIONS)
    des_json = ",".join(f'"{d}":0.0' for d in DESIRES)
    return f"""你是爆款内容心理拆解专家。你要对以下内容做「因果链逆问题」拆解：从可观测的话语/评论，反推观众心理的完整因果链，输出每一层的占比权重(联合分布)。

因果链结构(必须按此顺序推导，后一层要能从前一层导出，不能各层各拍)：
  欲望(稳定潜变量) →(情境事件) 需求(情境化目标) →(评价) 情绪 → 行动倾向 → 行为/话语(可观测)

{TAXONOMY}

【需求层定义】JTBD/ODI 风格：情境化的「要达成的结果/任务」，单元是「结果是什么」不是「怎么做」。need≠want：缺失会导致功能失调的才是 need。由某个欲望在某个具体情境下衍生。

【评价层(appraisal)——欲望与情绪之间的桥】三个维度：
  - goal_relevance(目标相关度 0-1)：这个情境对观众目标有多相关 → 决定情绪强度
  - goal_congruence(目标一致性 正/负)：情境是促进(正)还是阻碍(负)目标 → 决定情绪正负价
  - coping_potential(应对潜能 高/中/低)：观众觉得自己能多大程度应对/获得 → 决定应对方式(趋近还是回避)

【情绪层】GoEmotions 离散集 13 类：{emo_keys}

【行动倾向层】Frijda action tendency 7 类：{act_keys}

【待拆解内容】
{case_input}

【输出要求】严格输出一个 JSON(可放 ```json 代码块内)，不要输出任何解释文字。结构如下：
{{
  "desire_layer": {{
    "distribution": {{{des_json}}},
    "note": "一句话说明为什么这几类欲望被激活"
  }},
  "need_layer": [
    {{"need": "JTBD式结果描述(结果是什么，不是怎么做)", "weight": 0.0, "derived_from": "由<哪个欲望>经<什么情境事件>衍生"}}
  ],
  "appraisal": {{
    "goal_relevance": 0.0,
    "goal_congruence": "正 或 负",
    "coping_potential": "高 或 中 或 低",
    "note": "一句话说明评价如何决定了下面情绪的正负与强度"
  }},
  "emotion_layer": {{
    "distribution": {{{emo_json}}},
    "note": "一句话说明情绪如何从 需求×goal-congruence 推出"
  }},
  "action_tendency_layer": {{
    "distribution": {{{act_json}}}
  }},
  "chain_trace": "欲望X →(情境Y)→ 需求Z →(评价:goal-congruence正/负, coping高/低)→ 情绪W → 行动倾向V 的完整推导句(用具体名字填 X/Y/Z/W/V，必须一句话连贯读通)",
  "evidence": {{
    "desire": "支撑主欲望的逐字引用",
    "need": "支撑主需求的逐字引用",
    "emotion": "支撑主情绪的逐字引用",
    "action": "支撑主行动倾向的逐字引用"
  }}
}}
硬约束：
- desire_layer/emotion_layer/action_tendency_layer 的 distribution 必须且只能含上面列出的固定键，每层权重之和=1(可为0)；
- need_layer 是列表，各 need 的 weight 之和=1；
- chain_trace 必须显式写出从欲望到行动倾向的完整推导，且推出的情绪要真能从「需求×goal-congruence」导出，禁止情绪凭空出现；
- evidence 用内容/评论里的原话。"""


# ═══════════════════════════════════════════════════════════════
# 解析：把某层 distribution 对齐固定键并归一
# ═══════════════════════════════════════════════════════════════
def norm_layer(dist, keys):
    if not isinstance(dist, dict):
        return None
    vec = []
    for k in keys:
        v = dist.get(k, None)
        if v is None:  # 容错：模型可能只写中文或只写英文半边
            for kk, vv in dist.items():
                s = str(kk)
                if s in k or k in s or any(part and part in s for part in [k[:6], k[-4:]]):
                    v = vv
                    break
        try:
            v = float(v)
        except Exception:
            v = 0.0
        vec.append(max(0.0, v))
    s = sum(vec)
    if s <= 0:
        return None
    return [x / s for x in vec]


def parse_v4(parsed):
    """从解析后的 JSON 抽出四层向量 + appraisal + chain_trace。返回 dict 或 None(结构不全)。"""
    if not isinstance(parsed, dict):
        return None
    d = norm_layer((parsed.get("desire_layer") or {}).get("distribution"), DESIRES)
    e = norm_layer((parsed.get("emotion_layer") or {}).get("distribution"), EMOTIONS)
    a = norm_layer((parsed.get("action_tendency_layer") or {}).get("distribution"), ACTIONS)
    needs = parsed.get("need_layer") or []
    app = parsed.get("appraisal") or {}
    return {
        "desire_vec": d, "emotion_vec": e, "action_vec": a,
        "needs": needs if isinstance(needs, list) else [],
        "appraisal": app,
        "chain_trace": parsed.get("chain_trace", ""),
        "evidence": parsed.get("evidence", {}),
        "desire_note": (parsed.get("desire_layer") or {}).get("note", ""),
        "emotion_note": (parsed.get("emotion_layer") or {}).get("note", ""),
    }


def top_label(vec, keys):
    if not vec:
        return None
    i = max(range(len(vec)), key=lambda j: vec[j])
    return keys[i]


def coherence_autocheck(pv):
    """连贯性自动初筛(供人工复核参考，不替代人工判定)：
    - top 情绪的正负价 是否与 goal_congruence 符号一致
    - chain_trace 是否真的把 需求 与 情绪 串上(非空且含箭头)
    返回 flags 列表(空=无自动可疑点)。"""
    flags = []
    top_emo = top_label(pv["emotion_vec"], EMOTIONS)
    cong = str(pv["appraisal"].get("goal_congruence", ""))
    if top_emo:
        is_pos = top_emo in POS_EMO
        is_neg = top_emo in NEG_EMO
        if "正" in cong and is_neg:
            flags.append(f"congruence正 但 top情绪={top_emo}(负向)")
        if "负" in cong and is_pos:
            flags.append(f"congruence负 但 top情绪={top_emo}(正向)")
    ct = pv["chain_trace"] or ""
    if "→" not in ct and "->" not in ct:
        flags.append("chain_trace 无箭头/未成链")
    if len(ct) < 20:
        flags.append("chain_trace 过短")
    # 情绪是否与需求脱节：emotion_note 是否提到需求/情境(弱信号)
    return flags


def mean_pairwise_js(vecs):
    """一组分布向量两两 JS 均值(层内跨运行/跨模型的发散度)。"""
    valid = [v for v in vecs if v]
    if len(valid) < 2:
        return None
    js = []
    for i in range(len(valid)):
        for j in range(i + 1, len(valid)):
            js.append(js_divergence(valid[i], valid[j]))
    return round(sum(js) / len(js), 4)


def per_class_freq(vecs, keys):
    """N 次运行的逐类均值(采样频率)与标准差。返回 {key:(mean,std)}。"""
    valid = [v for v in vecs if v]
    out = {}
    n = len(valid)
    for ci, k in enumerate(keys):
        vals = [v[ci] for v in valid]
        mu = sum(vals) / n if n else 0.0
        sd = math.sqrt(sum((x - mu) ** 2 for x in vals) / n) if n else 0.0
        out[k] = (round(mu, 3), round(sd, 3))
    return out


def top_consistency(vecs, keys):
    """N 次运行 top label 的一致率(众数票数/N)。"""
    valid = [v for v in vecs if v]
    if not valid:
        return None, None
    from collections import Counter
    tops = [top_label(v, keys) for v in valid]
    c = Counter(tops)
    mode, n = c.most_common(1)[0]
    return mode, round(n / len(valid), 3)


# ═══════════════════════════════════════════════════════════════
# 试点案例：4 个内容模态(与 crossmodel 实验相同输入文本)
#   IT_ad_goods(拥有欲) / IT_life_kitchen(向往欲) / IT_kn_health(安全感) / VID_mc_xiongchu(视频)
# ═══════════════════════════════════════════════════════════════
PILOT_CASES = ["IT_ad_goods", "IT_life_kitchen", "IT_kn_health", "VID_mc_xiongchu"]
STABILITY_CASE = "IT_life_kitchen"   # 新三层最可能不稳的向往欲/氛围向案例，压力测试
STABILITY_N = 5


def call_and_parse(mk, case_input, temperature, log_note):
    content, meta = call_model(mk, build_v4_prompt(case_input), temperature=temperature)
    parsed = extract_json_robust(content, log_note=log_note)
    pv = parse_v4(parsed) if parsed else None
    ok = pv is not None and pv["desire_vec"] and pv["emotion_vec"] and pv["action_vec"]
    return content, parsed, pv, meta, ok


def run_smoke():
    cases = build_cases()
    ci = cases[PILOT_CASES[0]]
    content, parsed, pv, meta, ok = call_and_parse("M3", ci["input"], 0.0, "v4smoke")
    print("elapsed", meta.get("elapsed"), "err", meta.get("error"), "ok", ok)
    if pv:
        print("desire top:", top_label(pv["desire_vec"], DESIRES))
        print("emotion top:", top_label(pv["emotion_vec"], EMOTIONS))
        print("action top:", top_label(pv["action_vec"], ACTIONS))
        print("needs:", len(pv["needs"]))
        print("appraisal:", pv["appraisal"])
        print("chain_trace:", pv["chain_trace"][:300])
        print("autocheck flags:", coherence_autocheck(pv))
    else:
        print("PARSE FAIL. head:", (content or "")[:500])


def run_full():
    cases = build_cases()
    stats = {mk: {"calls": 0, "elapsed": 0.0, "fail": 0, "ptok": 0, "ctok": 0} for mk in ["M3", "Qwen3.8"]}
    per = {}   # case -> model -> pv record

    # ── 测试1&2：4 案例 × (M3, Qwen3.8) 单次 temp=0 ──
    print("=== TEST 1&2: 4 cases × 2 models (single-shot temp=0) ===")
    for cid in PILOT_CASES:
        per[cid] = {}
        ci = cases[cid]
        print(f"\n[{cid}] {ci['modality']}/{ci['type']}")
        for mk in ["M3", "Qwen3.8"]:
            content, parsed, pv, meta, ok = call_and_parse(mk, ci["input"], 0.0, f"v4 {cid} {mk}")
            stats[mk]["calls"] += meta.get("n_calls", 0)
            stats[mk]["elapsed"] += meta.get("elapsed", 0) or 0
            u = meta.get("usage", {}) or {}
            stats[mk]["ptok"] += u.get("prompt_tokens", 0) or 0
            stats[mk]["ctok"] += u.get("completion_tokens", 0) or 0
            rec = {"case": cid, "model": mk, "ok": ok, "raw": content, "parsed": parsed,
                   "pv": pv, "meta": meta}
            with open(os.path.join(RESULTS, f"v4chain_{cid}_{mk}.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
            per[cid][mk] = rec
            if not ok:
                stats[mk]["fail"] += 1
                print(f"    {mk:9s} {meta.get('elapsed')}s FAIL ({meta.get('error') or 'parse'})")
                continue
            flags = coherence_autocheck(pv)
            print(f"    {mk:9s} {meta.get('elapsed')}s "
                  f"des={top_label(pv['desire_vec'],DESIRES)} "
                  f"emo={top_label(pv['emotion_vec'],EMOTIONS)} "
                  f"act={top_label(pv['action_vec'],ACTIONS)} "
                  f"cong={pv['appraisal'].get('goal_congruence')} "
                  f"flags={flags}")

    # ── 测试2 分析：逐层跨模型 JS ──
    print("\n=== TEST 2: per-layer cross-model JS (M3 vs Qwen3.8) ===")
    layer_js = {"desire": [], "emotion": [], "action": []}
    per_case_layer_js = {}
    for cid in PILOT_CASES:
        m3, qw = per[cid]["M3"], per[cid]["Qwen3.8"]
        if not (m3["ok"] and qw["ok"]):
            per_case_layer_js[cid] = {"note": "缺一模型解析失败"}
            continue
        row = {}
        for lname, key in [("desire", "desire_vec"), ("emotion", "emotion_vec"), ("action", "action_vec")]:
            j = round(js_divergence(m3["pv"][key], qw["pv"][key]), 4)
            row[lname] = j
            layer_js[lname].append(j)
        # 需求层：无固定类目，比数量 + top欲望来源是否一致
        row["need_count_M3"] = len(m3["pv"]["needs"])
        row["need_count_Qwen"] = len(qw["pv"]["needs"])
        row["congruence_M3"] = m3["pv"]["appraisal"].get("goal_congruence")
        row["congruence_Qwen"] = qw["pv"]["appraisal"].get("goal_congruence")
        row["desire_top_M3"] = top_label(m3["pv"]["desire_vec"], DESIRES)
        row["desire_top_Qwen"] = top_label(qw["pv"]["desire_vec"], DESIRES)
        row["emotion_top_M3"] = top_label(m3["pv"]["emotion_vec"], EMOTIONS)
        row["emotion_top_Qwen"] = top_label(qw["pv"]["emotion_vec"], EMOTIONS)
        row["action_top_M3"] = top_label(m3["pv"]["action_vec"], ACTIONS)
        row["action_top_Qwen"] = top_label(qw["pv"]["action_vec"], ACTIONS)
        per_case_layer_js[cid] = row
        print(f"  {cid}: desireJS={row['desire']} emoJS={row['emotion']} actJS={row['action']} "
              f"| cong {row['congruence_M3']}/{row['congruence_Qwen']}")
    layer_js_mean = {k: (round(sum(v) / len(v), 4) if v else None) for k, v in layer_js.items()}

    # ── 测试3：稳定性 M3 × N ──
    print(f"\n=== TEST 3: stability M3 ×{STABILITY_N} on {STABILITY_CASE} (temp=0.7) ===")
    ci = cases[STABILITY_CASE]
    stab = []
    for r in range(STABILITY_N):
        content, parsed, pv, meta, ok = call_and_parse("M3", ci["input"], 0.7, f"v4stab {STABILITY_CASE} run{r+1}")
        stats["M3"]["calls"] += meta.get("n_calls", 0)
        stats["M3"]["elapsed"] += meta.get("elapsed", 0) or 0
        u = meta.get("usage", {}) or {}
        stats["M3"]["ptok"] += u.get("prompt_tokens", 0) or 0
        stats["M3"]["ctok"] += u.get("completion_tokens", 0) or 0
        rec = {"run": r + 1, "ok": ok, "raw": content, "parsed": parsed, "pv": pv, "meta": meta}
        with open(os.path.join(RESULTS, f"v4chain_stab_{STABILITY_CASE}_run{r+1}.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        stab.append(rec)
        if not ok:
            stats["M3"]["fail"] += 1
            print(f"  run{r+1} FAIL")
            continue
        print(f"  run{r+1} {meta.get('elapsed')}s des={top_label(pv['desire_vec'],DESIRES)} "
              f"emo={top_label(pv['emotion_vec'],EMOTIONS)} act={top_label(pv['action_vec'],ACTIONS)}")

    stab_ok = [s["pv"] for s in stab if s["ok"]]
    stab_layer = {}
    for lname, key, keys in [("desire", "desire_vec", DESIRES),
                             ("emotion", "emotion_vec", EMOTIONS),
                             ("action", "action_vec", ACTIONS)]:
        vecs = [pv[key] for pv in stab_ok if pv[key]]
        mode, cons = top_consistency(vecs, keys)
        stab_layer[lname] = {
            "mean_pairwise_JS": mean_pairwise_js(vecs),
            "top_mode": mode, "top_consistency": cons,
            "freq": per_class_freq(vecs, keys),
        }
        print(f"  [{lname}] pairwiseJS={stab_layer[lname]['mean_pairwise_JS']} "
              f"topMode={mode} topConsistency={cons}")

    # ── 汇总落盘 ──
    out = {
        "pilot_cases": PILOT_CASES,
        "emotions_set": EMOTIONS, "actions_set": ACTIONS,
        "test2_per_case_layer_js": per_case_layer_js,
        "test2_layer_js_mean": layer_js_mean,
        "test3_stability_case": STABILITY_CASE, "test3_N": STABILITY_N,
        "test3_stability_layer": stab_layer,
        "model_stats": stats,
        "coherence_autocheck": {
            cid: (coherence_autocheck(per[cid][mk]["pv"]) if per[cid][mk]["ok"] else ["PARSE FAIL"])
            for cid in PILOT_CASES for mk in ["M3", "Qwen3.8"]
            if False  # replaced below
        },
    }
    # per (model,case) autocheck flat
    out["coherence_autocheck"] = {
        f"{cid}_{mk}": (coherence_autocheck(per[cid][mk]["pv"]) if per[cid][mk]["ok"] else ["PARSE FAIL"])
        for cid in PILOT_CASES for mk in ["M3", "Qwen3.8"]
    }
    # chain_trace 收集(供人工连贯性判定)
    out["chain_traces"] = {
        f"{cid}_{mk}": (per[cid][mk]["pv"]["chain_trace"] if per[cid][mk]["ok"] else None)
        for cid in PILOT_CASES for mk in ["M3", "Qwen3.8"]
    }
    with open(os.path.join(RESULTS, "v4chain_ALL.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("\n=== SUMMARY ===")
    print("layer_js_mean(M3 vs Qwen):", json.dumps(layer_js_mean, ensure_ascii=False))
    print("stability(M3 x5):", json.dumps(
        {k: {"pairwiseJS": v["mean_pairwise_JS"], "topConsistency": v["top_consistency"]}
         for k, v in stab_layer.items()}, ensure_ascii=False))
    print("model_stats:", json.dumps(stats, ensure_ascii=False))
    print("\nSaved: results/v4chain_ALL.json + per-case/per-run json")
    return out


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    if mode == "smoke":
        run_smoke()
    else:
        run_full()
