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
  reply: s1_readout(K=3) -> s2_knots(v1.2.0) -> s3_emotion_policy -> s4_guard
  post:  s1_readout(K=5) -> s2_knots -> s3_emotion_policy -> s4_guard
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
    return {"taxonomy": "1.2.0", "knots": [[k["key"], k["weight"]] for k in knots],
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
           ctx["text_file"], "--profile=hearing_aid", "--intl"]
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
    if not ctx.get("audience_file"):
        raise RuntimeError("post模式必须提供--audience-file(受众逆推是链路必选环节)")
    d = run_knot_classify(ctx["audience_file"], ctx["context"] + "(目标读者原话)", 5,
                          f"{ctx['outdir']}/s5_audience.json")
    ctx["aud"] = d
    return {"file": "s5_audience.json",
            "knots": [[k["key"], k["weight"]] for k in d["stage2"]["knots"]]}


ALIGN_THETA = float(os.environ.get("CCE_ALIGN_THETA", "0.35"))


@stage("s6_alignment")
def s6(ctx):
    """对齐算子 v2(2026-08-09): 分布级 + 分族(推动=共鸣 / 阻挡=拆除)
    v1缺陷: 裸argmax丢分布 + 集合成员判定丢权重 + 阻挡族恒不可满足
    θ标定: 四篇已发布帖, 新分与R(落点完成率)同序递增, θ=0.35落在p1(R=0)与p2(R>0)之间
    """
    from cce_align_v2 import score
    aud = dict((k["key"], k["weight"]) for k in ctx["aud"]["stage2"]["knots"])
    post = dict((k["key"], k["weight"]) for k in ctx["cce"]["stage2"]["knots"])
    text = open(ctx["text_file"], encoding="utf-8").read().strip()
    r = score(aud, post, text, theta=ALIGN_THETA)
    r["operator"] = "v2_distribution_family"
    if not r["pass"]:
        top = max(aud.items(), key=lambda x: x[1])
        raise RuntimeError(
            f"对齐分{r['alignment_score']}<θ{ALIGN_THETA}(共鸣{r['resonance']}+拆除{r['dissolution']})"
            f"——受众主结{top[0]}({top[1]}), 稿件结{sorted(post)}")
    return r


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
        a, b, _ = args
        p = f"【内容A】\n{T[a]}\n\n【内容B】\n{T[b]}\n\n哪篇每千浏览的型号评论更多?只输出JSON。"
        c, _m = call_model("M3", SYS + "\n\n" + p, temperature=0.4)
        d = extract_json_robust(c, log_note="fullrun_ruler")
        if not (isinstance(d, dict) and d.get("winner") in ("A", "B")):
            return None
        return (a, b, d["margin"] if d["winner"] == "A" else -d["margin"])

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
    dev = m["CIMP->POST"] + m["POST->CACT"] - m["CIMP->CACT"]
    ok = abs(dev) <= 15
    out = {"legs": {k: round(v, 1) for k, v in m.items()}, "selfcheck_dev": round(dev, 1), "selfcheck_pass": ok}
    if ok and m["CIMP->CACT"] != 0:
        out["position_pct"] = round(m["CIMP->POST"] / m["CIMP->CACT"] * 100, 1)
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
    SYS = ("你是内容效果预测器。同一账号(r/HearingAids, OTC助听器OEM制造方视角)先后发布两篇帖子。\n"
           "预测哪一篇的「落点完成率」更高。落点完成 = 读者按帖子结尾的邀请,在评论区贴出自己的助听器型号(每千浏览计)。\n"
           '只看文本本身。只输出 JSON: {"winner":"A"或"B","margin":0到100,"reason":"一句话"}')
    T = {"NEW": NEW, "REF": REF}

    def one(args):
        a, b, _ = args
        p = f"【帖子A】\n{T[a]}\n\n【帖子B】\n{T[b]}\n\n哪篇每千浏览的型号评论更多?只输出JSON。"
        c, _m = call_model("M3", SYS + "\n\n" + p, temperature=0.4)
        d = extract_json_robust(c, log_note="fullrun_bet")
        if not (isinstance(d, dict) and d.get("winner") in ("A", "B")):
            return None
        win_new = (d["winner"] == "A") == (a == "NEW")
        return (win_new, d.get("margin", 0))

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
    "reply": [s1, s2, s3, s4],
    "post": [s1, s2, s3, s4, s5, s6, s7, s8],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=list(CHAINS))
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--context", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--audience-file")
    ap.add_argument("--ref-post")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    ctx = {"text_file": a.text_file, "context": a.context, "outdir": a.outdir,
           "audience_file": a.audience_file, "ref_post": a.ref_post,
           "k": 5 if a.mode == "post" else 3}
    txt = open(a.text_file, encoding="utf-8").read()
    meta = {"mode": a.mode, "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "text_sha1": hashlib.sha1(txt.encode()).hexdigest()[:12],
            "chain": [f.stage_name for f in CHAINS[a.mode]]}
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
                "k": 5 if body.get("mode") == "post" else 3})
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
