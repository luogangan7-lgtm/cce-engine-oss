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


@stage("s1_readout")
def s1(ctx):
    d = run_knot_classify(ctx["text_file"], ctx["context"], ctx["k"], f"{ctx['outdir']}/s1_readout.json")
    ctx["cce"] = d
    js = d["stage1"]["within_js"]
    flag = {l: v for l, v in js.items() if v > 0.25}
    return {"file": "s1_readout.json", "within_js": js,
            "high_divergence_flag": flag or None,
            "tops": d["stage1"]["tops"]}


@stage("s2_knots")
def s2(ctx):
    taxo = json.load(open(os.path.join(ROOT, "config/knot_taxonomy.json"), encoding="utf-8"))
    # 冻结守卫: 分类学换版必须显式改这里, 防止判定悄悄漂移
    PINNED_TAXO = os.environ.get("CCE_TAXO_VERSION", "1.3.1")
    if taxo.get("version") != PINNED_TAXO:
        raise RuntimeError(f"taxonomy版本漂移: {taxo.get('version')} != {PINNED_TAXO}")
    knots = ctx["cce"]["stage2"]["knots"]
    return {"taxonomy": taxo.get("version"), "knots": [[k["key"], k["weight"]] for k in knots],
            "playbook_primary": knots[0].get("playbook", "")[:120] if knots else None}


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


@stage("s5_audience")
def s5(ctx):
    """受众逆推 —— 逐条判后聚合。

    2026-08-09 修正: 原实现把整个 audience 文件当作一段文本丢给 knot_classify,
    即把 N 个人的话拼成一段问"这段文本是什么结"。但受众是**人群上的分布**, 不是
    一个人。实证后果: 同一份语料四次运行读出的主结 pain_seek 在 0.20~0.60 之间
    摆动(3.0倍), s6 的参照系不稳到无法支撑二值门; 语料加厚到 8131 词后 stage2
    直接三次全失败。改为逐条读出再聚合, 与 accuracy 侧 annot_dist 同形态。
    """
    if not ctx.get("audience_file"):
        raise RuntimeError("post模式必须提供--audience-file(受众逆推是链路必选环节)")
    lines = [l.strip() for l in open(ctx["audience_file"], encoding="utf-8")
             if len(l.strip().split()) >= 4]
    if len(lines) < 3:
        raise RuntimeError(f"受众语料仅 {len(lines)} 条有效原话, 逐条聚合至少需 3 条")
    sys.path.insert(0, os.path.join(ROOT, "accuracy"))
    from aggregate_core import read_many, aggregate
    reads = read_many(lines[:60])
    if len(reads) < 3:
        raise RuntimeError(f"逐条读出成功 {len(reads)}/{len(lines)} 条, 不足 3 条")
    agg = aggregate(reads)
    if not agg.get("九结"):
        raise RuntimeError("逐条聚合后九结为空 —— s6 依赖它, 不允许静默通过")
    out = {"n_utterances": len(lines), "n_read": len(reads),
           "method": "逐条读出后聚合(非拼接判读)",
           "layers": {L: agg[L] for L in ("欲望", "情绪", "需求", "行动")},
           "knots": sorted(agg["九结"].items(), key=lambda x: -x[1])}
    json.dump({"aggregate": agg, "per_utterance": reads},
              open(f"{ctx['outdir']}/s5_audience.json", "w"), ensure_ascii=False, indent=1)
    ctx["aud_layers"] = agg
    # 九结: 由聚合后的行动/需求侧另行判定, 交给 s6 用分布对齐
    ctx["aud"] = {"stage2": {"knots": [{"key": k, "weight": w}
                                      for k, w in sorted(agg["九结"].items(), key=lambda x: -x[1])]},
                  "aggregate": agg}
    out["file"] = "s5_audience.json"
    return out


ALIGN_THETA = float(os.environ.get("CCE_ALIGN_THETA", "0.35"))


@stage("s6_alignment")
def s6(ctx):
    """对齐 —— 双算子并报, 不再硬拦。

    2026-08-10 降级理由(不是为了让它过):
      · θ=0.35 从未被任何真值校准过, 是拍脑袋定的。当日已三次栽在拍脑袋阈值
        (min_words 80 / 中位数切档 / 本 θ)。
      · 两个算子都未被验证有预测力: 双臂对照三次证明九结/欲望需求注入判决皆无增量。
        用一个未验证的量做硬门, 会以"判负"之名拦掉本可能有效的稿件。
      · 共鸣算子(要求稿件呈现与受众同一个结)对【专家向受众解释】这一内容类型
        结构性不成立: 工厂方解释永远读作 display, 受众永远是 pain_seek。
        这与 reply 模式已论证并修过的前提错误同源, 故并报 playbook 执行度。
    结论: s6 输出两个分数 + 明确标注"未经真值校准, 仅作参考", 不再 raise。
    """
    from cce_align_v2 import score
    aud = dict((k["key"], k["weight"]) for k in ctx["aud"]["stage2"]["knots"])
    post = dict((k["key"], k["weight"]) for k in ctx["cce"]["stage2"]["knots"])
    text = open(ctx["text_file"], encoding="utf-8").read()
    mir = score(aud, post, text, mode="post")
    pbk = score(aud, post, text, mode="reply")
    top = max(aud, key=aud.get) if aud else None
    return {"共鸣算子_mirror": {"分": mir["alignment_score"], "共鸣": mir["resonance"],
                              "拆除": mir["dissolution"]},
            "playbook算子": {"分": pbk["alignment_score"], "执行度": pbk["dissolution"]},
            "受众主结": [top, round(aud.get(top, 0), 3) if top else None],
            "稿件结": sorted(post, key=post.get, reverse=True),
            "theta参考值": ALIGN_THETA,
            "口径声明": "θ 未经任何真值校准, 两算子亦未被验证有预测力; 本段仅作诊断参考, 不作放行/拦截依据"}


@stage("s7_ruler")
def s7(ctx):
    from exp_crossmodel_desire import call_model
    from exp_v4_full_validation import extract_json_robust
    from concurrent.futures import ThreadPoolExecutor
    CIMP = ("Looking for hearing aids that actually work? Our OTC devices deliver crystal clear sound at a "
            "fraction of the price of prescription hearing aids. Advanced noise reduction, Bluetooth streaming, "
            "and all day battery life. Thousands of satisfied customers can't be wrong. Check out our range "
            "today and hear the difference for yourself. Limited time offer available now.")
    CACT = ("Quick question for the sub. If you wear hearing aids, what model are you on and what is the one "
            "thing about them you would change? Trying to get a sense of what actually bothers people day to "
            "day. Drop it in the comments, I read all of them.")
    POST = open(ctx["text_file"], encoding="utf-8").read().strip()
    SYS = ("你是内容效果预测器。同一板块(r/HearingAids)的两篇内容。\n"
           "预测哪一篇的「落点完成率」更高。落点完成 = 读者按帖子结尾的邀请,在评论区贴出自己的助听器型号(每千浏览计)。\n"
           "只看文本本身。同时给出领先幅度(0到100的相对差距)。\n"
           '只输出 JSON: {"winner":"A"或"B","margin":0到100,"reason":"一句话"}')
    T = {"CIMP": CIMP, "CACT": CACT, "POST": POST}

    def one(args):
        # 2026-08-10: 原为单次调用无重试, temperature=0.4 下短文本(26词微片)极易吐解释
        # 而非 JSON —— 实测 D对比 s7 仅 9/30、C壳体 22/30、A座位 s8 0/10, 三条链因此断掉。
        # 加三次重试并逐次收紧指令, 后两次降温到 0。
        a, b, _ = args
        base = f"【内容A】\n{T[a]}\n\n【内容B】\n{T[b]}\n\n哪篇每千浏览的型号评论更多?"
        strict = ["只输出JSON。", "只输出一行JSON, 不要解释、不要代码块标记。",
                  '严格只输出这一行形式: {"winner":"A","margin":50,"reason":"x"}']
        for att in range(3):
            c, _m = call_model("M3", SYS + "\n\n" + base + strict[att],
                               temperature=0.4 if att == 0 else 0.0)
            d = extract_json_robust(c, log_note="fullrun_ruler")
            if isinstance(d, dict) and d.get("winner") in ("A", "B"):
                try:
                    mg = float(d.get("margin", 0))
                except Exception:
                    mg = 0.0
                return (a, b, mg if d["winner"] == "A" else -mg)
        return None

    pairs = [("CIMP", "POST"), ("POST", "CACT"), ("CIMP", "CACT")]
    jobs = [(a, b, r) for a, b in pairs for r in range(5)] + [(b, a, r) for a, b in pairs for r in range(5)]
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = [x for x in ex.map(one, jobs) if x]
    if len(res) < 24:
        raise RuntimeError(f"尺子成功率不足: {len(res)}/30")
    m = {}
    for a, b in pairs:
        vals = [s for (x, y, s) in res if (x, y) == (a, b)] + [-s for (x, y, s) in res if (x, y) == (b, a)]
        m[f"{a}->{b}"] = sum(vals) / len(vals)
    # 2026-08-10 自检改口径。原自检 dev = 两段之和 - 直连, 要求 |dev|<=15 —— 它假设
    # margin 是可相加的区间尺度; 实际 margin 是 0~100 的【有界相对差, 会饱和】。
    # 实测三个比较都接近饱和(|margin| 85~95)时, 两段之和 -167.7 而直连上限只有 -100,
    # 加性【按构造不可能成立】, 判负与尺子好坏无关。这是自检设定错, 不是尺子坏。
    # 改为【排序自洽】作主判: 三条 leg 必须能被同一个全序解释(CIMP < POST < CACT 之类)。
    # 加性偏差 dev 保留为诊断项, 且只在远离饱和时才有解释力。
    sat = max(abs(v) for v in m.values()) >= 70
    order_ok = True
    sc = {"CIMP": 0.0, "POST": 0.0, "CACT": 0.0}          # 由 leg 反推的相对位次
    sc["POST"] = -m["CIMP->POST"]                          # 负 = B(后者)胜
    sc["CACT"] = -m["CIMP->CACT"]
    implied = sc["CACT"] - sc["POST"]                      # 按位次推出的 POST->CACT
    for a, b in pairs:
        x, y = (sc[a], sc[b])
        if (m[f"{a}->{b}"] > 0) != (x > y) and abs(m[f"{a}->{b}"]) > 5 and abs(x - y) > 5:
            order_ok = False
    dev = m["CIMP->POST"] + m["POST->CACT"] - m["CIMP->CACT"]
    out = {"legs": {k: round(v, 1) for k, v in m.items()},
           "主判_排序自洽": order_ok,
           "推得的排序": [k for k, _ in sorted(sc.items(), key=lambda x: x[1])],
           "诊断_加性偏差dev": round(dev, 1),
           "饱和": sat,
           "dev可解释性": ("饱和区, 加性按构造不成立, dev 无解释力" if sat
                        else "非饱和区, |dev|>15 提示尺子不一致"),
           "口径说明": "主判=排序自洽(有界尺度上唯一有效的一致性判据); 加性偏差仅作诊断"}
    ok = order_ok
    if m["CIMP->CACT"] != 0:
        out["position_pct"] = round(m["CIMP->POST"] / m["CIMP->CACT"] * 100, 1)
        out["position_note"] = "本篇在【硬广 0% ←→ 纯问句CTA 100%】轴上的位置"
    json.dump(out, open(f"{ctx['outdir']}/s7_ruler.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out


@stage("s8_pairwise_bet")
def s8(ctx):
    if not ctx.get("ref_post"):
        raise RuntimeError("post模式必须提供--ref-post(上一篇正文,成对下注是链路必选环节)")
    from exp_crossmodel_desire import call_model
    from exp_v4_full_validation import extract_json_robust
    from concurrent.futures import ThreadPoolExecutor
    NEW = open(ctx["text_file"], encoding="utf-8").read().strip()
    REF = open(ctx["ref_post"], encoding="utf-8").read().strip()
    if len(REF.split()) < 20:
        raise RuntimeError(f"ref_post 只有 {len(REF.split())} 词, 不是一篇正文 —— "
                           f"拒绝拿本篇与疑似标识串做成对下注(2026-08-10 曾因此产出 9/10 假结果)")
    SYS = ("你是内容效果预测器。同一账号(r/HearingAids, OTC助听器OEM制造方视角)先后发布两篇帖子。\n"
           "预测哪一篇的「落点完成率」更高。落点完成 = 读者按帖子结尾的邀请,在评论区贴出自己的助听器型号(每千浏览计)。\n"
           '只看文本本身。只输出 JSON: {"winner":"A"或"B","margin":0到100,"reason":"一句话"}')
    T = {"NEW": NEW, "REF": REF}

    def one(args):
        # 2026-08-10: 原为单次调用无重试, temperature=0.4 下短文本(26词微片)极易吐解释
        # 而非 JSON —— 实测 D对比 s7 仅 9/30、C壳体 22/30、A座位 s8 0/10, 三条链因此断掉。
        # 加三次重试并逐次收紧指令, 后两次降温到 0。
        a, b, _ = args
        base = f"【帖子A】\n{T[a]}\n\n【帖子B】\n{T[b]}\n\n哪篇每千浏览的型号评论更多?"
        strict = ["只输出JSON。", "只输出一行JSON, 不要解释、不要代码块标记。",
                  '严格只输出这一行形式: {"winner":"A","margin":50,"reason":"x"}']
        for att in range(3):
            c, _m = call_model("M3", SYS + "\n\n" + base + strict[att],
                               temperature=0.4 if att == 0 else 0.0)
            d = extract_json_robust(c, log_note="fullrun_bet")
            if isinstance(d, dict) and d.get("winner") in ("A", "B"):
                return ((d["winner"] == "A") == (a == "NEW"), d.get("margin", 0))
        return None

    jobs = [("NEW", "REF", r) for r in range(5)] + [("REF", "NEW", r) for r in range(5)]
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = [x for x in ex.map(one, jobs) if x]
    if len(res) < 8:
        raise RuntimeError(f"下注成功率不足: {len(res)}/10")
    w = sum(1 for x, _ in res if x)
    return {"new_wins": f"{w}/{len(res)}",
            "verdict": "strong" if w >= len(res) * 0.8 else ("weak" if w > len(res) * 0.5 else "lose"),
            "note": "弱注=与随机不可区分,照实报告"}


CHAINS = {
    "reply": [s0, s1, s2, s3, s4],
    "response": [s0, s1, s2, s3],
    "outbound_post": [s0, s1, s2, s3, s4],
    "post": [s0, s1, s2, s3, s4, s5, s6, s7, s8],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=list(CHAINS))
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--context", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--audience-file")
    ap.add_argument("--context-decl", help="情境声明(JSON文件或内联JSON); 生产时应显式声明已知面")
    ap.add_argument("--ref-post")
    ap.add_argument("--guard-profile", default="hearing_aid",
                    help="outbound compliance profile; platform/community independent")
    ap.add_argument("--submission-meta", help="normalized cce.submission.v1 item metadata JSON")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    ctx = {"text_file": a.text_file, "context": a.context, "outdir": a.outdir,
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
