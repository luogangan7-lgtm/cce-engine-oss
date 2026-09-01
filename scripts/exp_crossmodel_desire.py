#!/usr/bin/env python3
# ⚠️ 名字骗人: 这**不是**实验脚本, 是生产内核。
#    它持有本体常量与 LLM 调用管道, 被 6 个生产文件 + 5 个探针共用。
#    删除 / 改名 / 归档会拆掉引擎 —— 依赖面由 tests/test_cce_module_boundary.py 逐文件钉死。
#    (2026-09-01: 我在整链审计里正是按名字把它误判为"实验脚本占仓库过半"的清理对象。)
"""
交叉共识真值锚实验 —— 4 前沿模型独立拆解欲望9类分布
Cross-model desire-distribution consensus experiment.

思想：单模型自报概率不可信（RLHF 破坏校准），但多个独立前沿模型的共识可作真值近似。
模型：M3 / 千问3.8 / GLM-5.2 / Kimi-K3，全 OpenAI 兼容 /chat/completions。
统一拆解协议：完全相同 prompt，输出欲望9类占比分布 JSON。

用法：
  python3 exp_crossmodel_desire.py smoke   # 4 模型连通性冒烟测试
  python3 exp_crossmodel_desire.py         # 全量批次 + 分析 + 报告
"""
import os, sys, json, time, math, re
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calibration_framework import extract_json_robust  # noqa: E402

ROOT = os.environ.get("VSE_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")
CAL = os.path.join(RESULTS, "calibration")
os.makedirs(CAL, exist_ok=True)

# ── 欲望 9 类权威名称（desire-taxonomy.md，2026-07-22 v9）──
DESIRES = ["拥有欲", "成为欲", "摆脱欲", "确认欲", "超越欲", "归属欲", "控制欲", "安全感欲", "向往欲"]

# ═══════════════════════════════════════════════════════════════
# 模型配置（密钥全走环境变量，禁止字面量落文件/日志）
# ═══════════════════════════════════════════════════════════════
MODELS = {
    "M3": {
        "model": "MiniMax-M3",
        "base": "https://api.minimaxi.com/v1/text/chatcompletion_v2",
        "key_env": "MINIMAX_API_KEY",
        "append_path": False,      # base 已是完整 chatcompletion 端点
        "max_tokens": 12000,       # 8000→12000 (2026-07-23): 消除罕见 finish_reason=length 截断
    },
    "Qwen3.8": {
        "model": "qwen3.8-max-preview",
        "base": os.environ.get("ALIYUN_API_BASE", ""),
        "key_env": "ALIYUN_API_KEY",
        "append_path": True,       # base + /chat/completions
        "max_tokens": 6000,
    },
    "GLM5.2": {
        "model": "glm-5.2",
        "base": os.environ.get("ALIYUN_API_BASE", ""),  # 智谱走阿里云 endpoint+key 直调
        "key_env": "ALIYUN_API_KEY",
        "append_path": True,
        "max_tokens": 6000,
    },
    "KimiK3": {
        "model": "kimi-k3",
        "base": "https://api.moonshot.cn/v1",
        "key_env": "KIMI_API_KEY",
        "append_path": True,
        "max_tokens": 6000,
        "force_temp": 1.0,   # kimi-k3 只允许 temperature=1
        # ⚠️ 2026-08-01 实测 429 account suspended(欠费)。owner 2026-08-19 确认只用
        #    阿里云与 MiniMax 两个订阅 ⇒ 本条**不进任何现役流程**, 保留仅为历史可读。
        "unavailable": "owner 未订阅(2026-08-19)",
    },
    # 阿里云 Token Plan 共享 Credits 下的同族备选(千问家族)。
    # ★ 2026-08-20: qwen3.7-max 被选作 **gen5 测量仪器** —— 理由是它**既不是 G1 也不是 G2**,
    #   避免「自己写的自己读」。已知残留限度: 订阅里没有非 qwen/非 GLM 的第三家族,
    #   故 G1(qwen3.8) 生成的那 12 个 base 与仪器**同属 qwen 家族**(版本不同)。
    #   好在 generator 是随机分配的 ⇒ 该重叠**本身可测**(G1 组 vs G2 组读数差异会暴露它)。
    "Qwen3.7max": {
        "model": "qwen3.7-max",
        "base": os.environ.get("ALIYUN_API_BASE", ""),
        "key_env": "ALIYUN_API_KEY",
        "append_path": True,
        "max_tokens": 6000,
    },
    # ★ 2026-08-24 阿里云订阅到期后接入。DeepSeek 的价值**不是**替代 G1/G2 ——
    #   它只有一个家族, 撑不起「两个生成器」这个 facet。
    #   它补的是一个更好的位置: **真正独立的第三方盲验者**
    #   (≠G1 千问 · ≠G2 GLM · ≠测量模型 MiniMax-M3), 比 Phase 2 用的
    #   CROSS_FAMILY_NO_THIRD_PARTY(验证者恰是另一个生成器)更强。
    "DeepSeek": {
        "model": "deepseek-chat",
        "base": os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"),
        "key_env": "DEEPSEEK_API_KEY",
        "append_path": True,
        "max_tokens": 6000,
    },
    # ★ 2026-08-25 智谱直连接入(阿里云那条 glm-5.2 通路随订阅到期失效)。
    #   ★ glm-4.5-air / glm-4.6v 是**推理模型**: 思考 token 计入 completion,
    #     max_tokens 给小了会得到「静默的空 content」(实测 max_tokens=10 时 content='' 但耗 20 token)。
    #     与库里 M3 那条教训同款 —— 故 max_tokens 给足。
    "GLM47": {
        "model": "glm-4.7",
        "base": os.environ.get("ZHIPU_API_BASE", "https://open.bigmodel.cn/api/paas/v4"),
        "key_env": "ZHIPU_API_KEY", "append_path": True, "max_tokens": 8000,
    },
    "GLM45air": {
        "model": "glm-4.5-air",
        "base": os.environ.get("ZHIPU_API_BASE", "https://open.bigmodel.cn/api/paas/v4"),
        "key_env": "ZHIPU_API_KEY", "append_path": True, "max_tokens": 8000,
    },
    "Qwen3.7plus": {
        "model": "qwen3.7-plus",
        "base": os.environ.get("ALIYUN_API_BASE", ""),
        "key_env": "ALIYUN_API_KEY",
        "append_path": True,
        "max_tokens": 6000,
    },
}


def call_model(mkey, prompt, temperature=0.0, timeout=300, max_retries=3):
    """通用 OpenAI 兼容调用。返回 (content, meta)。meta 含 usage/elapsed/n_calls/error。"""
    cfg = MODELS[mkey]
    api_key = os.environ.get(cfg["key_env"], "")
    if not api_key:
        return "", {"error": f"missing env {cfg['key_env']}", "n_calls": 0, "elapsed": 0}
    url = cfg["base"] + ("/chat/completions" if cfg["append_path"] else "")
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": cfg["max_tokens"],
        "temperature": cfg.get("force_temp", temperature),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_err = None
    t0 = time.time()
    for attempt in range(max_retries):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            # MiniMax 风控: 输入触发敏感审查时 choices=null + input_sensitive=true。
            # 确定性拦截, 重试纯浪费 —— 快速失败并带类型化错误(2026-07-23 修, 原来在这里炸 TypeError 后盲重试 3 次)
            if data.get("input_sensitive") or data.get("output_sensitive"):
                return "", {"error": f"SENSITIVE_BLOCKED input_type={data.get('input_sensitive_type')}",
                            "sensitive": True, "n_calls": attempt + 1,
                            "elapsed": round(time.time() - t0, 1)}
            choices = data.get("choices") or [{}]     # choices 可能为 null, .get 默认值不生效
            choice = choices[0] if choices else {}
            msg = choice.get("message", {}) or {}
            content = msg.get("content", "") or ""
            # 部分 reasoning 模型把最终答案留在 content，思考在 reasoning_content
            if not content.strip() and msg.get("reasoning_content"):
                content = msg.get("reasoning_content", "")
            return content, {
                "usage": data.get("usage", {}),
                "finish_reason": choice.get("finish_reason", ""),
                "elapsed": round(time.time() - t0, 1),
                "n_calls": attempt + 1,
                "error": None,
            }
        except Exception as e:
            body = ""
            try:
                body = r.text[:300]  # noqa
            except Exception:
                pass
            last_err = f"{type(e).__name__}: {e} | {body}"
            time.sleep(4)
    return "", {"error": last_err, "n_calls": max_retries, "elapsed": round(time.time() - t0, 1)}


# ═══════════════════════════════════════════════════════════════
# 案例集构建（≥8 多模态；4 模型看到完全相同的输入文本，均为客观内容描述，无欲望标签）
# ═══════════════════════════════════════════════════════════════
def _load(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return json.load(f)


def _comments_block(items, key, n=8, likekey=None):
    out = []
    for c in items[:n]:
        t = c.get(key, "")
        if likekey and c.get(likekey) is not None:
            out.append(f"  · {t}（{c[likekey]}赞）")
        else:
            out.append(f"  · {t}")
    return "\n".join(out)


def build_cases():
    cases = {}

    # ── 图文 4 例（title_copy 是画面内文字，visual_sig 是客观场景描述）──
    it_map = {
        "IT_ad_goods": ("平价好物种草广告", "夏日篮子开箱：浅蓝编织篮+暖肤人像+高饱和综艺立体字"),
        "IT_life_kitchen": ("生活方式图文", "草莓漂浮在白色农舍水槽里+鎏金阳光+复古乡村质地，无人厨房场景"),
        "IT_life_roomtour": ("生活方式图文", "粉系欧式 room tour，花艺装饰的居家空间"),
        "IT_kn_health": ("健康科普图文", "蓝粉撞色医嘱型封面：白大褂+听诊器+微笑医生+大标题"),
    }
    for cid, (ctype, vsig) in it_map.items():
        raw = _load(f"assets/image-text/{cid.split('_',1)[1]}.json")
        st = raw.get("stats", {})
        cmts = _comments_block(raw.get("comments", []), "text", 8, "likes")
        cases[cid] = {
            "modality": "图文", "type": ctype,
            "input": f"""【内容类型】{ctype}（抖音图文/单图帖）
【作者】{raw.get('author','')}
【画面内文案】{raw.get('title_copy','')}
【客观视觉】{vsig}
【互动数据】赞{st.get('digg_count')} 评论{st.get('comment_count')} 转发{st.get('share_count')} 收藏{st.get('collect_count')}
【热门评论】
{cmts}""",
        }

    # ── 评论 2 例（视频+评论区，纯文本）──
    cm_map = {"CM_food": ("美食探店", "douyin-food.json"), "CM_knowledge": ("知识科普", "douyin-knowledge.json")}
    for cid, (ctype, fn) in cm_map.items():
        raw = _load(f"assets/comments/{fn}")
        st = raw.get("stats", {})
        cmts = _comments_block(raw.get("comments", []), "text", 10, "digg_count")
        cases[cid] = {
            "modality": "评论", "type": ctype,
            "input": f"""【内容类型】{ctype}（抖音视频，仅提供文案+评论区）
【作者】{raw.get('author','')}
【视频文案】{raw.get('desc','')}
【互动数据】赞{st.get('digg_count')} 评论{st.get('comment_count')} 转发{st.get('share_count')} 收藏{st.get('collect_count')}
【热门评论】
{cmts}""",
        }

    # ── 对话 2 例（Soul 私聊转写）──
    dl_map = {"DLG_dashewan": "case1_soul_dashewan.json", "DLG_tangguo": "case2_soul_tangguo.json"}
    for cid, fn in dl_map.items():
        raw = _load(f"assets/dialogue/{fn}")
        msgs = raw.get("messages", [])
        lines = []
        for m in msgs[:40]:
            c = m.get("content", "")
            q = m.get("quote", {})
            qs = f"[引用:{q.get('content','')[:30]}] " if q else ""
            lines.append(f"  {m.get('sender','?')}: {qs}{c}")
        cases[cid] = {
            "modality": "对话", "type": "陌生人社交私聊",
            "input": f"""【内容类型】陌生人社交私聊转写（{raw.get('source_platform','')}）
【关系阶段】{raw.get('relationship_type','')}
【背景】{raw.get('context_note','')}
【对话转写（前40条）】
""" + "\n".join(lines),
        }

    # ── 视频 2 例（用已有客观场景描述，不重跑 vision）──
    cases["VID_mc_xiongchu"] = {
        "modality": "视频", "type": "MC建造/长视频",
        "input": """【内容类型】抖音超长视频（34:56）
【作者】creator_17
【标题】一辈子的存档-在MC还原熊出没地图
【客观内容】在《我的世界》中1:1复刻《熊出没》整张地图：光头强小屋、白熊山、吉吉毛毛山洞、各角色住所；航拍巡游+加速建造蒙太奇，结尾封存存档
【互动数据】赞180.4万 转发33.9万 评论33.8万
【热门评论】
  · 肝：活爹
  · 肝上长了个人
  · 光头强的一辈子
  · 创造都不一定做的出来呀
  · 玩mc的就是没轻没重
  · 这才是童年
  · 300小时太猛了
  · 细节拉满""",
    }
    cases["VID_perfect_mv"] = {
        "modality": "视频", "type": "音乐MV",
        "input": """【内容类型】音乐MV（4:42，YouTube）
【作者】Ed Sheeran
【标题】Ed Sheeran - Perfect (Official Music Video)
【客观内容】电影级实拍情侣叙事MV：阿尔卑斯雪山、木屋、篝火、圣诞彩灯 bokeh、雪地漫步的两人故事，暖金/蓝调电影感
【互动数据】36亿播放
【热门评论】
  · singing this at our wedding
  · 57 years together and still in love
  · single and still crying
  · 0% nudity 1000% talent
  · makes me believe in love
  · July 2026 anyone?""",
    }

    return cases


# ═══════════════════════════════════════════════════════════════
# 统一拆解 PROMPT（4 模型完全一致）
# ═══════════════════════════════════════════════════════════════
TAXONOMY = """欲望9类定义（触发视角：看完这条内容观众想要什么）：
1. 拥有欲：想拥有这个产品/这种生活/这种状态（指向可占有的具体物）
2. 成为欲：想成为视频里那种人（更好看/更有钱/更自由/更被爱）
3. 摆脱欲：想摆脱当前的痛苦状态
4. 确认欲：想确认自己的选择/观点/身份是对的（被认同感）
5. 超越欲：想超越平凡/超越他人/超越过去的自己
6. 归属欲：想找到同类/想属于某个群体（社会身份认同，指向群体成员资格）
7. 控制欲：想掌控自己的生活/财务/健康/关系
8. 安全感欲：想消除不确定性/风险/恐惧
9. 向往欲（投射欲）：想进入/住进/成为内容展示的那个画面——对未拥有的生活方式/空间/状态的想象性代入（指向不可直接购买的整体图景，氛围向内容优先检查此类）

划界要点：「求链接/想买」=拥有欲；「想住进去/想过这种生活」=向往欲；「我属于这群人」=归属欲；「想成为那种人」=成为欲。"""


def build_prompt(case_input):
    return f"""你是爆款内容心理拆解专家。请判断以下内容在单次观看中激发观众的「欲望9类」占比分布。

{TAXONOMY}

【待拆解内容】
{case_input}

【输出要求】严格输出一个 JSON（可放在 ```json 代码块内），结构如下，不要输出任何解释文字：
{{
  "desire_distribution": {{"拥有欲":0.0,"成为欲":0.0,"摆脱欲":0.0,"确认欲":0.0,"超越欲":0.0,"归属欲":0.0,"控制欲":0.0,"安全感欲":0.0,"向往欲":0.0}},
  "top_desire": "占比最高的那一类的名字",
  "confidence": 0.0,
  "evidence": {{"占比最高的类名":"来自内容或评论的逐字引用"}}
}}
要求：desire_distribution 必须且只能包含上述9个键，9个权重加起来等于1（可为0）；confidence 是你对本次判断的置信度(0-1)；evidence 用内容里的原话。"""


# ═══════════════════════════════════════════════════════════════
# 分布归一 + 指标
# ═══════════════════════════════════════════════════════════════
def normalize_dist(raw):
    """把模型输出的 desire_distribution 对齐到 9 类固定顺序并归一化。返回 list[9] 或 None。"""
    if not isinstance(raw, dict):
        return None
    dd = raw.get("desire_distribution")
    if not isinstance(dd, dict):
        return None
    vec = []
    for d in DESIRES:
        v = dd.get(d, 0)
        # 容错：键可能带修饰或子型，做包含匹配
        if d not in dd:
            for k, vv in dd.items():
                if d in str(k) or str(k) in d:
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


def js_divergence(p, q):
    """Jensen-Shannon divergence（以2为底，∈[0,1]）。"""
    m = [(a + b) / 2 for a, b in zip(p, q)]

    def kl(a, b):
        s = 0.0
        for ai, bi in zip(a, b):
            if ai > 0 and bi > 0:
                s += ai * math.log2(ai / bi)
        return s
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def cosine(p, q):
    dot = sum(a * b for a, b in zip(p, q))
    np_ = math.sqrt(sum(a * a for a in p))
    nq = math.sqrt(sum(b * b for b in q))
    return dot / (np_ * nq) if np_ and nq else 0.0


def top_k(vec, k=2):
    idx = sorted(range(len(vec)), key=lambda i: vec[i], reverse=True)[:k]
    return [DESIRES[i] for i in idx]


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════
def run_smoke():
    print("=== SMOKE TEST (4 models) ===")
    p = "只回一个JSON：{\"ok\":1}"
    for mk in MODELS:
        c, meta = call_model(mk, p, timeout=120, max_retries=1)
        ok = "OK" if c.strip() else "FAIL"
        print(f"  {mk:9s} {ok:4s} | {meta.get('elapsed')}s | err={meta.get('error')} | head={c.strip()[:80]!r}")


def run_full():
    cases = build_cases()
    print(f"=== FULL BATCH: {len(cases)} cases × {len(MODELS)} models ===")
    per = {}          # case -> model -> {vec, raw, confidence, meta}
    model_stats = {mk: {"calls": 0, "elapsed": 0.0, "fail": 0, "prompt_tok": 0, "completion_tok": 0} for mk in MODELS}

    for cid, cinfo in cases.items():
        prompt = build_prompt(cinfo["input"])
        per[cid] = {}
        print(f"\n[{cid}] {cinfo['modality']}/{cinfo['type']}")
        for mk in MODELS:
            content, meta = call_model(mk, prompt)
            model_stats[mk]["calls"] += meta.get("n_calls", 0)
            model_stats[mk]["elapsed"] += meta.get("elapsed", 0) or 0
            u = meta.get("usage", {}) or {}
            model_stats[mk]["prompt_tok"] += u.get("prompt_tokens", 0) or 0
            model_stats[mk]["completion_tok"] += u.get("completion_tokens", 0) or 0
            parsed = extract_json_robust(content, log_note=f"crossmodel {cid} {mk}")
            vec = normalize_dist(parsed) if parsed else None
            rec = {
                "model": MODELS[mk]["model"], "case": cid,
                "raw_content": content, "parsed": parsed,
                "vec": vec, "top_desire": (parsed or {}).get("top_desire") if parsed else None,
                "confidence": (parsed or {}).get("confidence") if parsed else None,
                "meta": meta,
            }
            with open(os.path.join(RESULTS, f"crossmodel_{cid}_{mk}.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
            per[cid][mk] = rec
            if vec is None:
                model_stats[mk]["fail"] += 1
            status = "ok" if vec else f"PARSE/CALL FAIL ({meta.get('error') or 'no json'})"
            tv = top_k(vec, 1)[0] if vec else "?"
            conf = rec["confidence"]
            print(f"    {mk:9s} {meta.get('elapsed')}s top={tv} conf={conf} {status}")

    analysis = analyze(cases, per, model_stats)
    with open(os.path.join(RESULTS, "crossmodel_ALL.json"), "w", encoding="utf-8") as f:
        json.dump({"per_case": per, "analysis": analysis, "model_stats": model_stats},
                  f, ensure_ascii=False, indent=2)
    write_report(cases, per, analysis, model_stats)
    print("\n=== DONE ===")
    print(json.dumps(analysis["headline"], ensure_ascii=False, indent=2))


def analyze(cases, per, model_stats):
    mkeys = list(MODELS.keys())
    pairs = [(a, b) for i, a in enumerate(mkeys) for b in mkeys[i + 1:]]
    case_metrics = {}
    all_js = []
    top_agree_cases = 0
    strong_anchor = 0
    split_cases = 0
    disagreement_mass = [0.0] * len(DESIRES)  # 各欲望类的跨模型标准差累积（分歧热点）

    for cid in cases:
        recs = per[cid]
        vecs = {mk: recs[mk]["vec"] for mk in mkeys if recs[mk]["vec"]}
        tops = {mk: recs[mk]["top_desire"] for mk in mkeys if recs[mk]["vec"]}
        # 用归一 vec 的 argmax 作为 top（比模型自报字段更可靠，字段可能带修饰）
        tops_argmax = {mk: top_k(vecs[mk], 1)[0] for mk in vecs}
        pair_js = {}
        pair_cos = {}
        for a, b in pairs:
            if a in vecs and b in vecs:
                j = js_divergence(vecs[a], vecs[b])
                pair_js[f"{a}~{b}"] = round(j, 4)
                pair_cos[f"{a}~{b}"] = round(cosine(vecs[a], vecs[b]), 4)
                all_js.append(j)
        # top 众数投票
        from collections import Counter
        vote = Counter(tops_argmax.values())
        mode_top, mode_n = (vote.most_common(1)[0] if vote else (None, 0))
        n_models = len(vecs)
        # Top2 Jaccard 平均
        jacs = []
        for a, b in pairs:
            if a in vecs and b in vecs:
                sa, sb = set(top_k(vecs[a], 2)), set(top_k(vecs[b], 2))
                jacs.append(len(sa & sb) / len(sa | sb))
        # 分歧热点：各类跨模型标准差
        per_class_std = []
        for ci in range(len(DESIRES)):
            vals = [vecs[mk][ci] for mk in vecs]
            if len(vals) >= 2:
                mu = sum(vals) / len(vals)
                sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / len(vals))
            else:
                sd = 0.0
            per_class_std.append(sd)
            disagreement_mass[ci] += sd

        anchor = "strong" if (n_models >= 3 and mode_n >= 3) else \
                 ("split" if (n_models >= 2 and mode_n <= max(2, n_models - 2) and mode_n == max(vote.values()) and len([v for v in vote.values() if v == mode_n]) > 1) else "weak")
        if mode_n >= 3 and n_models >= 3:
            strong_anchor += 1
        if n_models >= 4 and len(vote) >= 2 and sorted(vote.values(), reverse=True)[:2] == [2, 2]:
            anchor = "split"
            split_cases += 1
        if n_models >= 2 and len(set(tops_argmax.values())) == 1:
            top_agree_cases += 1

        case_metrics[cid] = {
            "modality": cases[cid]["modality"], "type": cases[cid]["type"],
            "n_models_ok": n_models,
            "tops_argmax": tops_argmax,
            "mode_top": mode_top, "mode_votes": f"{mode_n}/{n_models}",
            "pair_js": pair_js, "pair_cos": pair_cos,
            "mean_js": round(sum(pair_js.values()) / len(pair_js), 4) if pair_js else None,
            "mean_top2_jaccard": round(sum(jacs) / len(jacs), 3) if jacs else None,
            "per_class_std": {DESIRES[i]: round(per_class_std[i], 3) for i in range(len(DESIRES))},
            "anchor": anchor,
        }

    # overconfidence：每模型 平均自报confidence vs 它与众数一致的比率
    model_conf = {}
    for mk in mkeys:
        confs, agree = [], []
        for cid in cases:
            r = per[cid][mk]
            if r["vec"] is None:
                continue
            mode_top = case_metrics[cid]["mode_top"]
            my_top = top_k(r["vec"], 1)[0]
            if isinstance(r["confidence"], (int, float)):
                confs.append(float(r["confidence"]))
            agree.append(1 if my_top == mode_top else 0)
        avg_conf = round(sum(confs) / len(confs), 3) if confs else None
        agree_rate = round(sum(agree) / len(agree), 3) if agree else None
        gap = round(avg_conf - agree_rate, 3) if (avg_conf is not None and agree_rate is not None) else None
        model_conf[mk] = {"avg_confidence": avg_conf, "consensus_agree_rate": agree_rate, "overconfidence_gap": gap}

    # 哪个单模型最接近共识：与众数top一致率最高 + 与其他模型平均JS最低
    model_to_consensus = {}
    for mk in mkeys:
        js_to_others = []
        for cid in cases:
            r = per[cid][mk]
            if r["vec"] is None:
                continue
            others = [per[cid][o]["vec"] for o in mkeys if o != mk and per[cid][o]["vec"]]
            if others:
                mean_vec = [sum(v[i] for v in others) / len(others) for i in range(len(DESIRES))]
                js_to_others.append(js_divergence(r["vec"], mean_vec))
        model_to_consensus[mk] = round(sum(js_to_others) / len(js_to_others), 4) if js_to_others else None

    n_cases = len(cases)
    disagreement_rank = sorted(range(len(DESIRES)), key=lambda i: disagreement_mass[i], reverse=True)
    headline = {
        "n_cases": n_cases, "n_models": len(mkeys),
        "mean_pairwise_JS": round(sum(all_js) / len(all_js), 4) if all_js else None,
        "top_agree_rate_all4": round(top_agree_cases / n_cases, 3),
        "strong_anchor_cases": strong_anchor,
        "split_cases": split_cases,
        "closest_single_model_to_consensus": min(
            (k for k in model_to_consensus if model_to_consensus[k] is not None),
            key=lambda k: model_to_consensus[k], default=None),
    }
    return {
        "headline": headline,
        "case_metrics": case_metrics,
        "model_confidence": model_conf,
        "model_to_consensus_meanJS": model_to_consensus,
        "disagreement_hotspots": {DESIRES[i]: round(disagreement_mass[i], 3) for i in disagreement_rank},
    }


def write_report(cases, per, analysis, model_stats):
    h = analysis["headline"]
    cm = analysis["case_metrics"]
    L = []
    L.append("# 交叉共识真值锚实验 —— 4 模型欲望9类分布交叉对比\n")
    L.append(f"> 模型：M3 / 千问3.8(qwen3.8-max-preview) / GLM-5.2 / Kimi-K3 · 案例 {h['n_cases']} 个多模态 · 统一拆解协议（完全相同 prompt）\n")
    L.append("## 0. 核心数字（headline）\n")
    L.append(f"- **平均两两 JS 散度**：`{h['mean_pairwise_JS']}`（0=完全一致，1=完全分歧）")
    L.append(f"- **4 模型 top 欲望全一致率**：`{h['top_agree_rate_all4']}`")
    L.append(f"- **强真值锚案例（≥3/4 众数一致）**：{h['strong_anchor_cases']}/{h['n_cases']}")
    L.append(f"- **2:2 分裂案例（本身模糊）**：{h['split_cases']}/{h['n_cases']}")
    L.append(f"- **单模型最接近共识**：`{h['closest_single_model_to_consensus']}`\n")

    L.append("## 1. 一致度矩阵（每案例）\n")
    L.append("| 案例 | 模态 | ok模型 | 众数top | 票数 | 平均JS | 平均Top2-Jaccard | 锚定 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for cid, m in cm.items():
        L.append(f"| {cid} | {m['modality']} | {m['n_models_ok']} | {m['mode_top']} | {m['mode_votes']} | {m['mean_js']} | {m['mean_top2_jaccard']} | {m['anchor']} |")
    L.append("")
    L.append("### 各案例 4 模型 top 欲望明细\n")
    L.append("| 案例 | " + " | ".join(MODELS.keys()) + " |")
    L.append("|---|" + "---|" * len(MODELS))
    for cid, m in cm.items():
        row = [cid] + [m["tops_argmax"].get(mk, "—") for mk in MODELS]
        L.append("| " + " | ".join(row) + " |")
    L.append("")

    L.append("## 2. 自报置信度 vs 实际一致性（overconfidence 对比）\n")
    L.append("| 模型 | 平均自报confidence | 与众数top一致率 | overconfidence gap |")
    L.append("|---|---|---|---|")
    mc = analysis["model_confidence"]
    for mk in MODELS:
        d = mc[mk]
        L.append(f"| {mk} | {d['avg_confidence']} | {d['consensus_agree_rate']} | {d['overconfidence_gap']} |")
    L.append("\n> gap>0 = 自报置信度高于实际与共识一致率 = 过度自信；gap<0 = 保守/校准良好。\n")
    L.append("### 单模型到共识的平均 JS（越小越贴近共识，可作生产主模型候选）\n")
    L.append("| 模型 | 到其余模型均值分布的平均JS |")
    L.append("|---|---|")
    for mk, v in analysis["model_to_consensus_meanJS"].items():
        L.append(f"| {mk} | {v} |")
    L.append("")

    L.append("## 3. 分类学分歧热点（各欲望类跨模型标准差累积，越大越是撞车区）\n")
    L.append("| 欲望类 | 分歧累积(Σstd) |")
    L.append("|---|---|")
    for d, v in analysis["disagreement_hotspots"].items():
        L.append(f"| {d} | {v} |")
    L.append("")

    L.append("## 4. 模型调用成本对比\n")
    L.append("| 模型 | 总调用数 | 总耗时(s) | 解析失败 | prompt_tok | completion_tok |")
    L.append("|---|---|---|---|---|---|")
    for mk in MODELS:
        s = model_stats[mk]
        L.append(f"| {mk} | {s['calls']} | {round(s['elapsed'],1)} | {s['fail']} | {s['prompt_tok']} | {s['completion_tok']} |")
    L.append("")

    L.append("## 5. 给 v4 表示法的建议\n")
    L.append("（结论段由分析脚本生成数据，人工/主线据下方数据判断。见 headline 与各表。）\n")

    with open(os.path.join(CAL, "exp_crossmodel.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"报告写入 {os.path.join(CAL, 'exp_crossmodel.md')}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    if mode == "smoke":
        run_smoke()
    else:
        run_full()
