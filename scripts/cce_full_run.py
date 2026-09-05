#!/usr/bin/env python3
"""CCE 完整链路唯一入口 · v1
设计原则(2026-08-08 用户裁定"脚本方式agent不会按规矩完整执行"后建):
 1. 无跳步开关: 本文件没有任何 --skip/--only 参数。模式(post/reply)决定链路清单,清单冻结。
 2. 失败即红: 任何环节失败/解析失败/覆盖不足,进程退出码非0,并在 manifest 里显式记 FAIL——
    没有静默绿(本项目 fail-silent 教训第6例之后的制度化防线)。
 3. 留痕: 每次运行产出 manifest.json(每环节: 状态/耗时/产物文件/关键读数),这就是"逐项清单"
    汇报纪律的机器执行版。禁止在没有 manifest 的情况下声称"跑了完整CCE"。
用法:
  python cce_full_run.py --mode reply --text-file X.txt --context "..." --outdir RUNDIR
  python cce_full_run.py --mode post  --text-file X.txt --context "..." --outdir RUNDIR \
      [--audience-file A.txt] [--ref-post REF.txt]
链路清单(冻结):
  reply: s0_context -> s1_readout(K=3) -> s2_knots -> s3_emotion_policy -> s4_guard
  response: s0_context -> s1_readout(K=3) -> s2_knots -> s3_emotion_policy
  outbound_post: s0_context -> s1_readout(K=5) -> s2_knots -> s3_emotion_policy -> s4_guard
  legacy research post:
  post:  s0_context -> s1_readout(K=5) -> s2_knots -> s3_emotion_policy -> s4_guard
         -> s5_audience(K=5, 需--audience-file) -> s6_alignment
         -> s7_ruler(P3双锚) -> s8_pairwise_bet(需--ref-post)
"""
import os, sys, json, time, argparse, subprocess, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import io
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.join(ROOT, "scripts"))

# Windows/n8n 场景没有 shell source,自动加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    env_p = os.path.join(ROOT, ".env")
    if os.path.exists(env_p):
        for line in open(env_p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                if k.startswith("export "):
                    k = k[7:].strip()
                os.environ.setdefault(k, v.strip().strip('"').strip("\'"))

MANIFEST = {}


def stage(name):
    def deco(fn):
        def wrap(ctx):
            t0 = time.time()
            try:
                out = fn(ctx)
                MANIFEST[name] = {"status": "OK", "sec": round(time.time() - t0, 1), **(out or {})}
            except Exception as e:
                MANIFEST[name] = {"status": "FAIL", "sec": round(time.time() - t0, 1),
                                  "error": f"{type(e).__name__}: {e}"[:300]}
                raise
        wrap.stage_name = name
        return wrap
    return deco


CTX_TAXO = json.load(open(os.path.join(ROOT, "config/context_taxonomy.json"), encoding="utf-8"))
CTX_FACETS = CTX_TAXO["facets"]
CTX_UNKNOWN = {"未知", "未提及", "", None}


def run_knot_classify(text_file, context, k, out):
    cmd = [sys.executable, os.path.join(ROOT, "scripts/cce_knot_classify.py"),
           "--text-file", text_file, "--context", context, "--k", str(k), "--out", out]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"knot_classify rc={r.returncode}: {(r.stderr or '')[-200:]}")
    d = json.load(open(out, encoding="utf-8"))
    if d["stage1"]["k_ok"] < k:
        raise RuntimeError(f"K覆盖不足: {d['stage1']['k_ok']}/{k}")
    return d


@stage("reader_baseline")
def reader_baseline(ctx):
    """读者基线(仅 reply 链) —— 用同一把尺量读者那条评论，而不是只量我方草稿。

    2026-08-18: 本段此前在 config/cce_submission_contract_v1.json 里被声明为 outbound_reply
    的第一段, 但**仓库里没有任何实现**, CHAINS["reply"] 也不含它 —— 契约声明了一个任何代码
    都产不出的段, 而聚合层 complete=true 检测不到这种缺失(见 cce_workflow_manifest 的 chain 断言)。
    后果: outbound_reply 与 outbound_post 在实际执行上无差别, 「回复过了 CCE」这句话
    的历史含义仅等于「我方草稿过了 outbound_post 那五段」, 不含任何读者侧测量。

    补上它的理由不是为了让断言变绿 —— 是因为不量读者, reply 这个 profile 就没有存在意义。
    数据一直都在(prepare.py 早已写出 run/reader.txt), 缺的只是这十几行。
    """
    rf = ctx.get("reader_file")
    if not rf or not os.path.exists(rf):
        raise RuntimeError("reply 链必须有 run/reader.txt —— 读者原文缺失时不得静默跳过本段")
    body = open(rf, encoding="utf-8").read().strip()
    if not body:
        raise RuntimeError("run/reader.txt 为空")
    d = run_knot_classify(rf, ctx["context"], ctx["k"], f"{ctx['outdir']}/reader_baseline.json")
    ctx["reader_cce"] = d
    return {"file": "reader_baseline.json", "reader_chars": len(body),
            "tops": d["stage1"]["tops"], "within_js": d["stage1"]["within_js"],
            "knots": [[k["key"], k["weight"]] for k in d["stage2"]["knots"]]}


@stage("s0_context")
def s0(ctx):
    """情境层(第五层) —— 部分可观测, 三态: 已声明 / 读出 / 未知(走先验)。

    2026-08-09/10 实测依据:
      · 情境敏感度(148次受控调用): 逐面翻取值, 情绪位移 .36-.78、行动 .43-.78,
        而需求仅 .06-.13 —— 情境显著改变下游, 不能不建。
      · 九面里【场景类型】位移排第四(.471)却几乎读不出(可读出率 .145) ——
        属"影响大但拿不到", 必须以未知记录并交下游做分布, 不许猜一个填上。
    生产纪律: 我们自己产内容时情境是【已知入参】, 不该让模型猜; 逆向他人内容时才读出。
    故声明优先于读出, 读出优先于未知; 每面记录来源, 并给出填充度。
    """
    decl = {}
    if ctx.get("context_decl"):
        decl = json.loads(open(ctx["context_decl"], encoding="utf-8").read()) \
            if os.path.exists(ctx["context_decl"]) else json.loads(ctx["context_decl"])
    need_read = [f for f in CTX_FACETS
                 if f["key"] not in decl and f.get("readable_from_text") in (True, "partial")]
    read = {}
    if need_read:
        from exp_crossmodel_desire import call_model
        from exp_v4_full_validation import extract_json_robust
        body = open(ctx["text_file"], encoding="utf-8").read()[:2000]
        spec = "\n".join(f"  {f['key']}: {f['values']}" for f in need_read)
        p = (f"逐面读出这段内容体现的读者情境。**读不出来就填\"未知\", 严禁猜**。\n"
             f"{spec}\n\n【内容】\n{body}\n\n只输出JSON: {{\"面名\":\"选中值\"}}")
        c, _ = call_model("M3", p, temperature=0.0)
        read = extract_json_robust(c, log_note="s0_ctx") or {}
    merged, src = {}, {}
    for f in CTX_FACETS:
        k = f["key"]
        if k in decl:
            merged[k], src[k] = decl[k], "已声明"
        elif read.get(k) not in CTX_UNKNOWN and read.get(k) in f["values"]:
            merged[k], src[k] = read[k], "读出"
        else:
            merged[k], src[k] = "未知", "未知(走先验)"
    # 防呆: 声明了却没落到 已声明 => 传参链路断了, 必须抛错而非静默读出覆盖
    miss = [k for k in decl if src.get(k) != "已声明"]
    if miss:
        raise RuntimeError(f"情境声明未生效: {miss} —— 传参链路断了, 拒绝用读出值冒充声明值")
    known = [k for k, v in src.items() if v != "未知(走先验)"]
    fill = round(len(known) / len(CTX_FACETS), 3)
    ctx["ctx_layer"] = {"facets": merged, "source": src, "fill_rate": fill}
    # 情境并入下游语境串, 让 s1/s5 看到
    ctx["context"] = ctx["context"] + " 【情境】" + json.dumps(
        {k: v for k, v in merged.items() if v != "未知"}, ensure_ascii=False)
    json.dump(ctx["ctx_layer"], open(f"{ctx['outdir']}/s0_context.json", "w"),
              ensure_ascii=False, indent=1)
    if fill == 0:
        raise RuntimeError("情境九面全未知且无声明 —— 引擎拒答: 缺必要输入时不硬给结论")
    return {"file": "s0_context.json", "fill_rate": fill,
            "已声明": [k for k, v in src.items() if v == "已声明"],
            "读出": [k for k, v in src.items() if v == "读出"],
            "未知": [k for k, v in src.items() if v == "未知(走先验)"],
            "置信提示": ("填充度低, 下游只出人群级结论, 不出个体级判断"
                       if fill < 0.5 else "填充度足够")}


# 2026-08-18: within_js 是这台仪器的自测噪声底 —— K 次采样两两的 JS 散度。
# 它每次都算、每次都写进 manifest, **但此前没有任何 gate 使用它**;
# 唯一的动作是阈值 0.25 的 high_divergence_flag, 而实测 31 条里只触发 2 次 —— 接近永久绿。
# 按本项目铁律, 永久绿与永久红是同一种失效: 读数与被测对象无关, 于是没人再看它。
#
# 阈值改为逐层从实测分布标定(中位数 + 2×MAD, n=31, 2026-08-17/18 全部生产与测试 run):
#   desire 0.076→0.120 · need 0.108→0.161 · emotion 0.108→0.157 · action 0.088→0.125
# ⚠️ 这组阈值是在这 31 条上标定的, 首次样本外检验就是它上线之后的每一次生产运行。
#    不得用同一批数据既标定又验收 —— 若上线后触发率与这里的 6/7/2/2 显著不同, 以样本外为准重标。
#
# 动作不是让 build 红, 而是**扣发该层的 top 标签** —— 与 s2 的 playbook 扣发同一逻辑:
# 一个内部离散超过自身噪声底的层, 它的 top 是在读噪声。这与既有纪律同源
# (「差距落在噪声内的层禁止排名」「情绪层禁单top」「CCE 输出禁止 argmax」)。
WITHIN_JS_MAX = {"desire_vec": 0.120, "need_vec": 0.161,
                 "emotion_vec": 0.157, "action_vec": 0.125}
_LAYER_OF_TOP = {"desire": "desire_vec", "need": "need_vec",
                 "emotion": "emotion_vec", "action": "action_vec"}


@stage("s1_readout")
def s1(ctx):
    d = run_knot_classify(ctx["text_file"], ctx["context"], ctx["k"], f"{ctx['outdir']}/s1_readout.json")
    ctx["cce"] = d
    js = d["stage1"]["within_js"]
    st = d["stage1"]
    if st.get("abstained"):
        # ★ 仪器声明这段输入不构成个人表达 —— 合法弃权, 不是失败。
        return {"file": "s1_readout.json", "measurement_status": "abstain",
                "abstain_reason": st.get("abstain_reason", ""),
                "within_js": None, "tops": {}, "tops_withheld": None,
                "over_noise_floor": None, "high_divergence_flag": None,
                "k": {kk: st.get(kk) for kk in
                      ("k_requested", "k_attempted", "k_valid", "k_abstained")}}
    if not js:
        # ★ 2026-08-19 改: 此前这里 raise。弃权上线后, 「有效 draw 不足」是**合法的
        #   测量结果**, 不是管线故障 —— raise 会把两者重新混在一起(今天修过的同一类病)。
        #   改为 WITHHOLD: 不产出 tops, 但如实报出 k 的三个计数, 让下游知道为什么没有。
        #   ⚠️ 绝不能退回单 draw 继续当合格读数: within_js 数学上需要 >=2 个有效 draw。
        return {"file": "s1_readout.json",
                "measurement_status": "insufficient_replicates",
                "reason": (f"有效 draw {st.get('k_valid')}/{st.get('k_attempted')} "
                           f"(弃权 {st.get('k_abstained')}) < 2, 组内散布无从计算"),
                "within_js": None, "tops": {}, "tops_withheld": "all(insufficient_replicates)",
                "over_noise_floor": None, "high_divergence_flag": None,
                "k": {kk: st.get(kk) for kk in
                      ("k_requested", "k_attempted", "k_valid", "k_abstained")}}
    over = {l: round(v, 4) for l, v in js.items() if v > WITHIN_JS_MAX.get(l, 1.0)}
    tops = dict(d["stage1"]["tops"])
    withheld = {}
    for name, layer in _LAYER_OF_TOP.items():
        if layer in over:
            withheld[name] = f"{layer} within_js={over[layer]} > {WITHIN_JS_MAX[layer]}"
            tops[name] = None
    return {"file": "s1_readout.json", "measurement_status": "qualified",
            "k": {kk: st.get(kk) for kk in
                  ("k_requested", "k_attempted", "k_valid", "k_abstained")},
            "within_js": js,
            "within_js_max": WITHIN_JS_MAX,
            "over_noise_floor": over or None,
            "tops": tops,
            "tops_withheld": withheld or None,
            "high_divergence_flag": {l: v for l, v in js.items() if v > 0.25} or None}


@stage("s2_knots")
def s2(ctx):
    taxo = json.load(open(os.path.join(ROOT, "config/knot_taxonomy.json"), encoding="utf-8"))
    # 冻结守卫: 分类学换版必须显式改这里, 防止判定悄悄漂移
    PINNED_TAXO = os.environ.get("CCE_TAXO_VERSION", "1.3.1")
    if taxo.get("version") != PINNED_TAXO:
        raise RuntimeError(f"taxonomy版本漂移: {taxo.get('version')} != {PINNED_TAXO}")
    st2 = ctx["cce"]["stage2"]
    knots = st2["knots"]
    samp = st2.get("sampling") or {}
    # 2026-08-18: playbook_primary 是整条链里唯一直接指挥「怎么写」的字段。
    # 若 n 次抽样连首结是哪个都不一致, 就没有「首结的打法」可发 —— 此处置 None,
    # 让不确定性在做决策的地方生效, 而不是只躺在 manifest 里没人看。
    # 判据是二元的(首结 key 是否全同), 不含任何未校准阈值。
    top1_stable = samp.get("top1_stable")
    return {"taxonomy": taxo.get("version"),
            "knots": [[k["key"], k["weight"]] for k in knots],
            # 四层结构(§22): intensity 不受和为 1 约束; families 给族内组成与 mass;
            # drive_brake 给 §22.4 的四象限。knots 的 weight 仍是全局组成, 仅为下游兼容。
            "intensity": st2.get("intensity"),
            "families": st2.get("families"),
            "drive_brake": st2.get("drive_brake"),
            "n": samp.get("n_ok"), "top1_stable": top1_stable,
            "top1_mode_share": samp.get("top1_mode_share"), "top1_mode": samp.get("top1_mode"),
            "instrument": st2.get("instrument", {}).get("instrument_hash"),
            "top1_draws": samp.get("top1_draws"), "max_range": samp.get("max_range"),
            "per_knot": samp.get("per_knot"),
            "playbook_primary": (knots[0].get("playbook", "")[:120]
                                 if knots and top1_stable is True else None),
            # ★ 2026-09-05 A1/A2: 两类建议被**移出单文本打分**, 但**不能因此从交付里消失**。
            #   移出的理由是判官**结构上看不见**它们(跨轮规则拿不出本文子串; 顺序约束不是
            #   单一子串), 不是这两条建议错了。若只把它们搬进 taxonomy 就不管了,
            #   它们会变成没人读的死规则 —— 一致性闸当场判了红, 判得对。
            #   ⇒ 随 playbook_primary 一同下发, 但**显式标注不参与打分**。
            "playbook_unscored_guidance": (_unscored_guidance(taxo, knots[0]["key"])
                                           if knots and top1_stable is True else None),
            # ★ 2026-09-06: 判据从 `is not False` 收紧为 `is True`。
            #   上游现在会在**可投票 draw < 2** 时返回 None(不可判) ——
            #   而 `is not False` 会把 None 当成通过, 那正是「查不了当查过了」。
            #   ★ 两种扣发理由必须分开: 「测了, 不稳」与「压根测不了」不是一回事。
            "playbook_withheld_reason": (
                None if top1_stable is True else
                (f"top1 一致性**不可判**(可投票 draw < 2, 一个观测点上观察不到一致性): "
                 f"{samp.get('top1_draws')}" if top1_stable is None else
                 f"top1 不稳: {samp.get('top1_draws')}"))}



def _unscored_guidance(taxo, knot_key):
    """随 playbook 一同下发、但**刻意不进单文本打分**的建议。

    ★ 为什么要单独一格而不是并进 playbook: 这两类条目判官**结构上看不见** ——
      cross_turn_strategy 说的是跨多轮该做什么, 本文里根本没有第二轮;
      composition_note 是两个动作之间的**顺序**, 拿不出单一逐字子串。
      把它们留在打分清单里, 只会让判官在看不见的东西上瞎猜(实测: audit 因此
      常年卡在中位 0.50)。移出打分是对的, **移出交付是错的** —— 写稿的人仍然要照做。
    """
    for k in taxo.get("knots", []):
        if k.get("key") != knot_key:
            continue
        out = {}
        if k.get("cross_turn_strategy"):
            out["cross_turn"] = k["cross_turn_strategy"]
        if k.get("composition_note"):
            out["composition"] = k["composition_note"]
        return out or None
    return None

@stage("s3_emotion_policy")
def s3(ctx):
    # 纪律: 情绪层禁单模型top(模型间JS=0.164)。单模型运行时只报分布。
    from exp_v4_causal_chain import EMOTIONS
    vec = ctx["cce"]["stage1"]["layers"]["emotion_vec"]
    dist = sorted(zip(EMOTIONS, vec), key=lambda x: -x[1])[:4]
    return {"policy": "distribution_only(单模型运行)",
            "emotion_distribution": [[l, round(p, 3)] for l, p in dist]}


@stage("s4_guard")
def s4(ctx):
    cmd = [sys.executable, os.path.join(ROOT, "scripts/cce_outbound_guard.py"),
           ctx["text_file"], f"--profile={ctx['guard_profile']}", "--intl"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT, timeout=300)
    d = json.loads(r.stdout)
    if not (d.get("clean") and d.get("clean_strict")):
        raise RuntimeError(f"guard未过: clean={d.get('clean')} strict={d.get('clean_strict')}")
    dash = open(ctx["text_file"], encoding="utf-8").read().count("—") + open(ctx["text_file"], encoding="utf-8").read().count("–")
    if dash:
        raise RuntimeError(f"破折号{dash}处(纪律: 0)")
    return {"clean": True, "strict": True, "em_dash": 0}


# ── s5_audience / s6_alignment / s7_ruler / s8_pairwise_bet 已删(2026-09-01) ──
# 四段随旧九环节链于 2026-08-13 退役, 不在任何生产 profile 里。留着的唯一作用
# 是让人误以为它们还是现行标准(实际复发三次)。cce_align_v2 保留 —— reply_loop
# 仍在用它做诊断性对齐分(workflow:154), 那条口径是「不作放行/拦截依据」。

# ── P3 Multimodal 生产链(2026-09-03) ──────────────────────────────────
# 输入不是原始视频, 是**解析产物**(cce_video_parse 的 JSON)。理由:
#   解析要 ffmpeg/OCR/ASR + 真实媒体文件, 不该塞进 CI; 而测量链要的是精确输入哈希 +
#   可回放。产物走既有 --text-file 管道 ⇒ text_sha256 天然就是「精确输入哈希」。
# ★ 只做**视频解析产物**这一档。2026-08-15 已否决「静态图片与视频帧各建一套视觉合同」,
#   且 standalone_image_ingest 仍 missing —— 不得声称图片全链可用。
# 链止于 Foundation 层(observations + events)。测量是 P0–P2 的事, 走既有 profile,
# 在这里重跑一遍就是重复测量。
@stage("media_validate")
def media_validate(ctx):
    """校验它确实是解析产物, 不是随便一个 JSON。★ 形状不合就红, 不猜。"""
    raw = open(ctx["text_file"], encoding="utf-8").read()
    try:
        parsed = json.loads(raw)
    except Exception as e:
        raise ValueError(f"media_ingest 的输入必须是解析产物 JSON: {e}")
    if not isinstance(parsed, dict):
        raise ValueError(f"解析产物顶层应为对象, 实际 {type(parsed).__name__}")
    dur = float(parsed.get("duration") or 0.0)
    if dur <= 0:
        raise ValueError("解析产物缺正的 duration —— 不是有效产物")
    ctx["parsed"] = parsed
    present = [k for k in ("audio", "ocr", "frames", "visual") if parsed.get(k)]
    return {"duration_sec": round(dur, 1), "channels_present": present,
            "artifact_sha256": hashlib.sha256(raw.encode()).hexdigest()[:16],
            "★scope": "只校验形状与完整性; **抽取质量(ASR/OCR 准确率)未测**, 见 registry"}


@stage("foundation_adapt")
def foundation_adapt(ctx):
    """解析产物 → Foundation observations。"""
    from pathlib import Path as _P
    import cce_foundation_adapter as _FA
    case = _FA.adapt(ctx["parsed"], _P(ctx["text_file"]))
    ctx["case"] = case
    obs = case.get("observations") or []
    with open(os.path.join(ctx["outdir"], "observations.json"), "w", encoding="utf-8") as fh:
        json.dump(case, fh, ensure_ascii=False, indent=1)
    from collections import Counter as _C
    return {"observations": len(obs), "kinds": dict(_C(o.get("kind") for o in obs)),
            "content_id": case.get("content_id")}


@stage("event_assemble")
def event_assemble(ctx):
    """observations → events, 且必须过 Foundation 合同。"""
    import cce_event_assemble as _EA
    from cce_contract import validate_case as _vc
    ev = _EA.assemble(ctx["case"])
    v = _vc(ev)
    if not v["ok"]:
        raise ValueError("组装结果不合合同: " + "; ".join(v["errors"][:3]))
    ctx["events_case"] = ev
    with open(os.path.join(ctx["outdir"], "events.json"), "w", encoding="utf-8") as fh:
        json.dump(ev, fh, ensure_ascii=False, indent=1)
    from collections import Counter as _C
    types = dict(_C(e.get("event_type") for e in ev.get("events") or []))
    return {"events": len(ev.get("events") or []), "event_types": types,
            "contract_ok": True, "counts": v.get("counts")}


@stage("qualified_readout")
def qualified(ctx):
    """Measurement System 的出口闸(2026-08-18 新增)。

    此前每一处扣发都是零散加的: s1 超噪声底扣发该层 top、s2 首结不稳扣发 playbook。
    问题不在于它们不对, 而在于**没有一个地方回答「这次运行到底哪些读数可用」** ——
    于是下游各自决定看不看, 结果就是不确定性只在一条路上生效(reply_loop 曾照旧发 PASS/FAIL)。

    本段不调模型, 只把前面各段的扣发决定收敛成一个具名对象:
        usable   —— 允许进入下游 / Population Field 的读数
        withheld —— 被扣发的, 连同扣发理由
    纪律: **只有 usable 里的东西允许被引用。** 不在 usable 里的, 不是「弱证据」, 是没有读数。

    并带上 instrument_hash —— 跨读数比较之前必须先比它(见 cce_knot_classify.assert_same_instrument)。
    """
    s1m, s2m = MANIFEST.get("s1_readout", {}), MANIFEST.get("s2_knots", {})
    usable, withheld = {}, {}
    # ── P3: 媒体链的读数也必须在这里表态, 不能绕过出口闸 ────────────────
    fa, ea = MANIFEST.get("foundation_adapt", {}), MANIFEST.get("event_assemble", {})
    if fa.get("status") == "OK":
        usable["p3.observations"] = {"n": fa.get("observations"), "kinds": fa.get("kinds")}
    if ea.get("status") == "OK":
        usable["p3.events"] = {"n": ea.get("events"), "types": ea.get("event_types")}
    if fa.get("status") == "OK" or ea.get("status") == "OK":
        # ★ 抽出来了 != 抽得准。质量未测这件事必须占一个具名的扣发位,
        #   否则下游会把 observation 里的文字当已验收的读数用。
        withheld["p3.extraction_quality"] = (
            "ASR/OCR 抽取**准确率未测**(语言相关, 英文上从未评过) —— "
            "observation 里的文字可作证据引用, 但不得当作已验收的转写")
        withheld["p3.cross_domain_calibration"] = (
            "分辨率/阈值 across_domains=NOT_ESTABLISHED —— 禁止跨域搬")
    for name, val in (s1m.get("tops") or {}).items():
        (usable if val is not None else withheld)[f"s1.tops.{name}"] = (
            val if val is not None else (s1m.get("tops_withheld") or {}).get(name, "超噪声底"))
    if s2m.get("playbook_primary"):
        usable["s2.playbook_primary"] = s2m["playbook_primary"]
    else:
        withheld["s2.playbook_primary"] = s2m.get("playbook_withheld_reason") or "未产出"
    # ★ 2026-09-02: 原来这里写「分布类读数**始终可用**, 但必须带 n 与不确定性一起引用」,
    #   把 intensity 无条件放进 usable。那是一句**散文 caveat** —— 而本项目已确立
    #   散文式 caveat 在这个项目已被证伪(13 条 Notion 读数都标了「不可单独使用」,
    #   照样被当读数引用)。且它与出站闸自相矛盾: 出站闸按 K1 判定硬拦
    #   [[knot_intensity:]], 这里却宣布同一份读数可引用。
    #   改为由 K1 判定驱动的**路由**, 单一真相源见 scripts/cce_k1_status.py。
    if s2m.get("knots"):
        from cce_k1_status import layer_status, knot_readout_usable
        # ★ 必须把**本次运行**的仪器传进去: K1 判定是在某一台仪器上做的,
        #   标定不可跨仪器搬(gen2→gen3 已确立)。缺它一律扣发。
        _inst = (ctx.get("cce") or {}).get("stage2", {}).get("instrument") or {}
        st = layer_status(instrument_hash=_inst.get("instrument_hash"))
        base = {"n": s2m.get("n"), "top1_mode_share": s2m.get("top1_mode_share"),
                "top1_mode": s2m.get("top1_mode"), "max_range": s2m.get("max_range")}
        if st["top1"]["usable"]:
            usable["s2.distribution.top1"] = base
        else:
            withheld["s2.distribution.top1"] = st["top1"]["reason"]
        if st["intensity"]["usable"]:
            usable["s2.distribution.intensity"] = {
                "knots": s2m["knots"], "intensity": s2m.get("intensity"), **base}
        else:
            # intensity 与**建在 intensity 上的一切**一起扣发:
            #   knots[].weight = intensity/Σ · families.mass = max(intensity)
            #   families.composition = intensity/Σ · drive_brake = 两个 mass 的象限
            # ★ 2026-09-03 更正: weight 已**不是**「未单独判定」了 —— K1-v2 在 5 个文本上
            #   按预注册判据判过, 结果 0/5。把已判红的东西报成「未测」是把 red 降级成
            #   NOT_MEASURED, 而本项目的三态纪律要求这两者分开(not started is not green,
            #   judged-and-failed 也不是 not started)。理由改为**现问**, 判定变了自动跟上。
            withheld["s2.distribution.intensity"] = st["intensity"]["reason"]
            _w_ok, _w_why = knot_readout_usable(
                "weight", instrument_hash=_inst.get("instrument_hash"))
            withheld["s2.distribution.knot_weight"] = (
                f"{_w_why}(weight = intensity/Σ, 建在 intensity 上)")
            withheld["s2.families"] = (
                "mass = max(intensity), composition = intensity/Σ —— 二者都建在已判红的 "
                "intensity 上; 且 mass 自身在探索性实测里比 intensity **更差**(0.6222–0.7333), "
                "未经预注册判定 ⇒ 扣发")
            withheld["s2.drive_brake"] = (
                "由两个 mass 的象限决定, 未单独判定 ⇒ 扣发")
    inst = (ctx.get("cce") or {}).get("stage2", {}).get("instrument") or {}
    return {"instrument_hash": inst.get("instrument_hash"),
            "instrument_spec": inst.get("spec"),
            "usable_keys": sorted(usable), "withheld": withheld,
            "usable_count": len(usable), "withheld_count": len(withheld),
            "rule": "只有 usable 里的读数允许进入下游/Population Field; "
                    "withheld 不是弱证据, 是没有读数。跨读数比较前必须先比 instrument_hash。"}


CHAINS = {
    # 2026-08-18: reply 链补入 reader_baseline —— 契约一直声明它, 实现一直不存在。
    # 顺序与 config/cce_submission_contract_v1.json 的 profiles.outbound_reply.stages 逐位相等,
    # 由 tests/test_cce_submission.py 与 cce_workflow_manifest 的 chain 断言双向钉死。
    "reply": [reader_baseline, s0, s1, s2, s3, s4, qualified],
    "response": [s0, s1, s2, s3],
    "outbound_post": [s0, s1, s2, s3, s4, qualified],
    # 2026-09-03 P3 进生产: 输入是解析产物, 链止于 Foundation 层(测量走既有 profile)。
    "media_ingest": [media_validate, foundation_adapt, event_assemble, qualified],
    # 2026-09-01: 删 "post"(旧九环节 s0-s8)。2026-08-13 退役, 契约从无此档,
    # 而它一直可从 .github/prepare.py 选中 —— 「拿退役组件当现行标准」复发三次的根因。
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=list(CHAINS))
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--context", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--audience-file")
    ap.add_argument("--reader-file", help="reply 链的读者原文(run/reader.txt); reader_baseline 段必需")
    ap.add_argument("--context-decl", help="情境声明(JSON文件或内联JSON); 生产时应显式声明已知面")
    ap.add_argument("--ref-post")
    ap.add_argument("--guard-profile", default="hearing_aid",
                    help="outbound compliance profile; platform/community independent")
    ap.add_argument("--submission-meta", help="normalized cce.submission.v1 schema 1.1.0 item metadata JSON")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    ctx = {"text_file": a.text_file, "context": a.context, "outdir": a.outdir,
           "reader_file": a.reader_file,
           "audience_file": a.audience_file, "ref_post": a.ref_post,
           "context_decl": a.context_decl, "guard_profile": a.guard_profile,
           "k": 5 if a.mode in {"post", "outbound_post"} else 3}
    txt = open(a.text_file, encoding="utf-8").read()
    meta = {"mode": a.mode, "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "text_sha1": hashlib.sha1(txt.encode()).hexdigest()[:12],
            "text_sha256": "sha256:" + hashlib.sha256(txt.encode()).hexdigest(),
            "chain": [f.stage_name for f in CHAINS[a.mode]]}
    if a.submission_meta:
        submission_meta = json.load(open(a.submission_meta, encoding="utf-8"))
        expected = submission_meta.get("text_sha256")
        if expected and expected != meta["text_sha256"]:
            raise SystemExit("submission metadata text_sha256 does not match exact input")
        meta["submission"] = submission_meta
    failed = None
    for fn in CHAINS[a.mode]:
        try:
            fn(ctx)
        except Exception:
            failed = fn.stage_name
            break
    meta["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    meta["stages"] = MANIFEST
    meta["complete"] = failed is None
    meta["failed_at"] = failed
    json.dump(meta, open(f"{a.outdir}/manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    sys.exit(0 if failed is None else 1)



# ── 单环节模式(供 n8n 逐节点编排;链路完整性由工作流定义保证) ──
def _ctx_path(outdir):
    return os.path.join(outdir, "_ctx.json")


def load_ctx(outdir):
    p = _ctx_path(outdir)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def save_ctx(outdir, ctx):
    json.dump(ctx, open(_ctx_path(outdir), "w", encoding="utf-8"), ensure_ascii=False)


def load_manifest(outdir):
    p = os.path.join(outdir, "manifest.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"stages": {}}


def run_single_stage(name, ctx):
    """跑一个环节,累加进 manifest。返回 (ok, stage_result)"""
    fn = {f.stage_name: f for chain in CHAINS.values() for f in chain}.get(name)
    if not fn:
        raise RuntimeError(f"未知环节: {name}")
    outdir = ctx["outdir"]
    mani = load_manifest(outdir)
    global MANIFEST
    MANIFEST = mani.setdefault("stages", {})
    ok = True
    try:
        fn(ctx)
    except Exception:
        ok = False
    mani["stages"] = MANIFEST
    mani["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    json.dump(mani, open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    save_ctx(outdir, {k: v for k, v in ctx.items() if k not in ("cce", "aud")})
    return ok, MANIFEST.get(name)


def build_ctx(outdir, body):
    """从 run_dir 与请求体重建 ctx;cce/aud 从上游落盘文件恢复"""
    ctx = load_ctx(outdir)
    ctx.update({"outdir": outdir,
                "text_file": os.path.join(outdir, "input.txt"),
                "context": body.get("context", ""),
                "guard_profile": body.get("guard_profile", "hearing_aid"),
                "k": 5 if body.get("mode") in {"post", "outbound_post"} else 3})
    if body.get("audience"):
        ctx["audience_file"] = os.path.join(outdir, "audience.txt")
    if body.get("ref"):
        ctx["ref_post"] = os.path.join(outdir, "ref.txt")
    for key, fname in (("cce", "s1_readout.json"), ("aud", "s5_audience.json")):
        fp = os.path.join(outdir, fname)
        if os.path.exists(fp):
            ctx[key] = json.load(open(fp, encoding="utf-8"))
    return ctx


def main_single():
    pass


if __name__ == "__main__":
    main()
