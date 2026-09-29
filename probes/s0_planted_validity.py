# -*- coding: utf-8 -*-
"""s0 情境读出的**植入信号效度**测试(预注册 tests/data/s0_planted_validity_prereg.json)。

往真实段落末尾追加一句**明说**某面取值的话(真值由构造给出, 不需要人类金标), 用生产同一个读者
scripts/cce_s0_jev.s0_jev_read 读, 看: ① 植入值读得出来吗(recovery) ② 别的面有没有被连带改掉(net_off_target,
扣掉追加中性句本身带来的变动)。只调 Jev(≈$0.00005/请求), 硬上限 600, 撞上即停。产物只放指针与统计量, 不落原文。

用法: python3 probes/s0_planted_validity.py [--dry-run]
"""
import argparse, collections, hashlib, importlib.util, json, pathlib, sys, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_s0_jev as S0  # noqa: E402

PRE = ROOT / "tests/data/s0_planted_validity_prereg.json"
OUT = ROOT / "results/s0_planted_validity.json"
N_PASSAGES, CAP = 10, 600
_sh = importlib.util.spec_from_file_location("_shadow", ROOT / "probes/s0_jev_shadow.py")
shadow = importlib.util.module_from_spec(_sh); _sh.loader.exec_module(shadow)
FACETS = shadow.READABLE
KEYS = [f["key"] for f in FACETS]

# 每面只植入实质性取值; A 直白 / B 稍口语。句子一经预注册提交即冻结。
PLANTS = {
    "进程位置": {
        "刚意识到问题": ["I only just realized I actually have a hearing problem.", "Honestly it just dawned on me this week that my hearing isn't what it was."],
        "在找方案": ["I'm currently looking for options to deal with it.", "Right now I'm searching around for what I could try."],
        "在比较权衡": ["I'm comparing two specific models and weighing which one to pick.", "I've narrowed it to a couple of options and keep going back and forth."],
        "已决定在执行": ["I've already decided and ordered them; now I'm just going through the fitting.", "Decision's made, I'm in the middle of getting them set up."],
        "回看复盘": ["Looking back now, a year after buying them, here's what I'd do differently.", "In hindsight, after all this time with them, I can see how it went."],
    },
    "触发事件": {
        "受挫/出故障": ["My left one just stopped working yesterday.", "Today they cut out again and I'm fed up."],
        "被否定或质疑": ["My audiologist told me I was wrong about what I need.", "My family keeps telling me I'm imagining the problem."],
        "正在比价": ["I'm comparing prices between two stores right now.", "I'm shopping around to see who has the best price this week."],
        "刚花过钱": ["I just paid for a new pair last week.", "Just spent a lot on them a few days ago."],
        "刚得到好结果": ["I just got great results at my follow-up appointment.", "Yesterday was the first time in years I heard birds clearly."],
    },
    "关系位置": {
        "首次接触": ["This is the first time I've ever heard of this brand.", "Never came across this company before today."],
        "接触过几次": ["I've looked at this brand a few times before.", "I've come across this company a couple of times."],
        "长期关注": ["I've been following this brand for years.", "I've kept an eye on this company for a long time."],
        "已购买": ["I already bought this brand's hearing aids.", "I own a pair from this company already."],
        "有过负面经历": ["I had a bad experience with this brand before.", "This company let me down in the past."],
    },
    "身体状态": {
        "症状正发作": ["My tinnitus is flaring up badly right now.", "Right now the ringing in my ears is really bad."],
        "长期困扰": ["I've struggled with this hearing loss for many years.", "It's been a chronic problem for me for a decade."],
        "已缓解": ["The problem has mostly cleared up now.", "Things have gotten a lot better and the symptoms eased."],
    },
    "资源状态": {
        "预算受限": ["I'm on a tight budget and can't spend much.", "Money is really limited for me right now."],
        "时间受限": ["I barely have any time to deal with appointments.", "I'm swamped at work and can't make time for this."],
        "有决定权": ["It's entirely my decision what to buy.", "I'm the one who decides and pays."],
        "无决定权": ["My daughter makes the decision about what I get.", "It's not up to me, my insurance decides."],
    },
    "情绪余温": {
        "正向余温": ["Thanks again for your last reply, it really helped me.", "Your earlier advice worked out great, so I'm back."],
        "负向余温": ["Your last reply didn't help at all and annoyed me.", "After your previous answer I was pretty frustrated."],
        "中性": ["Following up on your earlier reply.", "Coming back to the thread from before."],
    },
}
NEUTRAL = ["The weather here has been mild this week.", "I usually read these threads in the evening."]

# ★ 探索臂(非预注册, 不作采纳依据): 情绪余温 题面收窄。主测试发现 Jev 会从非互动事件(设备故障→负向余温、
#   症状缓解→正向余温)推断「上一轮互动留下的感觉」。本臂只改这一道题的说明, 看溢出是否下降、正/负是否仍读得出。
EMOTION_V2 = ("Read only the feeling the writer expresses toward OUR previous message or reply in this thread. "
              "Feelings about products, devices, symptoms, prices or other people do NOT count. "
              "If the text does not react to a previous message from us, choose 首轮无余温 if it reads as a first contact, otherwise 未知; never guess.")
V2_FACETS = ("触发事件", "身体状态", "情绪余温")


def norm(v, facet):
    return "未知" if (v in shadow.UNKNOWN or v not in facet["values"]) else v


def jobs(passages):
    out = [("baseline", p, None, None, None, body) for p, body in passages]
    out += [("neutral", p, None, None, i, body + "\n\n" + s) for p, body in passages for i, s in enumerate(NEUTRAL)]
    out += [("plant", p, f, v, i, body + "\n\n" + s)
            for f, vals in PLANTS.items() for v, ss in vals.items() for i, s in enumerate(ss) for p, body in passages]
    return out


def verdict(recovery, net):
    if recovery < 0.50:
        return "UNRESPONSIVE"
    if recovery >= 0.80 and net <= 0.10:
        return "RESPONSIVE"
    return "WEAK"


def analyse(rows):
    fac = {f["key"]: f for f in FACETS}
    base = {r["ptr"]: r["read"] for r in rows if r["kind"] == "baseline" and r["read"]}
    ok = [r for r in rows if r["read"] and r["ptr"] in base]
    neu = [r for r in ok if r["kind"] == "neutral"]
    neu_ch = sum(norm(r["read"][k], fac[k]) != norm(base[r["ptr"]][k], fac[k]) for r in neu for k in KEYS) / max(1, len(neu) * len(KEYS))
    per = {}
    for f, vals in PLANTS.items():
        pr = [r for r in ok if r["kind"] == "plant" and r["facet"] == f]
        by_v = {v: [r for r in pr if r["value"] == v] for v in vals}
        rec_v = {v: round(sum(norm(r["read"][f], fac[f]) == v for r in rs) / len(rs), 4) if rs else None for v, rs in by_v.items()}
        rec = round(sum(x for x in rec_v.values() if x is not None) / max(1, sum(x is not None for x in rec_v.values())), 4)
        others = [k for k in KEYS if k != f]
        off = sum(norm(r["read"][k], fac[k]) != norm(base[r["ptr"]][k], fac[k]) for r in pr for k in others) / max(1, len(pr) * len(others))
        net = round(off - neu_ch, 4)
        confus = collections.Counter("%s→%s" % (r["value"], norm(r["read"][f], fac[f])) for r in pr if norm(r["read"][f], fac[f]) != r["value"])
        per[f] = {"n": len(pr), "recovery": rec, "recovery_by_value": rec_v, "off_target_change": round(off, 4),
                  "net_off_target": net, "verdict": verdict(rec, net), "misreads_top5": dict(confus.most_common(5))}
    return round(neu_ch, 4), per


def analyse_v2(rows):
    """探索臂读数: ① 触发事件/身体状态植入 ⇒ 情绪余温 从 baseline 被改掉的比例(溢出) ② 情绪余温 植入的召回。"""
    fac = {f["key"]: f for f in FACETS}
    base = {r["ptr"]: r["read"] for r in rows if r["kind"] == "baseline" and r["read"]}
    ok = [r for r in rows if r["read"] and r["ptr"] in base]
    out = {}
    for f in ("触发事件", "身体状态"):
        pr = [r for r in ok if r["kind"] == "plant" and r["facet"] == f]
        spill = [r for r in pr if norm(r["read"]["情绪余温"], fac["情绪余温"]) != norm(base[r["ptr"]]["情绪余温"], fac["情绪余温"])]
        out[f + " ⇒ 情绪余温 溢出"] = {"n": len(pr), "changed": len(spill), "rate": round(len(spill) / max(1, len(pr)), 4),
                                    "to": dict(collections.Counter(norm(r["read"]["情绪余温"], fac["情绪余温"]) for r in spill))}
        out[f + " 召回"] = round(sum(norm(r["read"][f], fac[f]) == r["value"] for r in pr) / max(1, len(pr)), 4)
    pe = [r for r in ok if r["kind"] == "plant" and r["facet"] == "情绪余温"]
    out["情绪余温 召回(按值)"] = {v: round(sum(norm(r["read"]["情绪余温"], fac["情绪余温"]) == v for r in pe if r["value"] == v)
                                       / max(1, sum(r["value"] == v for r in pe)), 4) for v in PLANTS["情绪余温"]}
    out["baseline 情绪余温 分布"] = dict(collections.Counter(norm(base[p]["情绪余温"], fac["情绪余温"]) for p in base))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--variant", choices=["main", "emotion_v2"], default="main"); a = ap.parse_args(argv)
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    passages = shadow.load_passages()[:N_PASSAGES]
    js = jobs(passages)
    out_path = OUT
    if a.variant == "emotion_v2":
        js = [j for j in js if j[0] == "baseline" or (j[0] == "plant" and j[2] in V2_FACETS)]
        out_path = ROOT / "results/s0_planted_validity_emotion_v2.json"
        _orig_q = S0.jev_questions
        def _qs(facets):
            q = _orig_q(facets)
            if "情绪余温" in q:
                q["情绪余温"]["instructions"] = EMOTION_V2
            return q
        S0.jev_questions = _qs
    assert len(js) <= CAP, (len(js), CAP)
    ledger, lock = {"req": 0}, threading.Lock()
    if a.dry_run:
        def post(body, key):
            return {"answers": {k: {"choice": FACETS[i]["values"][0], "probabilities": {}} for i, k in enumerate(body["questions"])}}, None
        key = "dry"
    else:
        key = shadow._key()
        def post(body, k):
            with lock:
                ledger["req"] += 1
                if ledger["req"] > CAP:
                    raise RuntimeError("BUDGET_EXCEEDED")
            return S0._post(body, k, retries=1)

    import os
    os.environ["TYPESAFE_API_KEY"] = key          # 仅本进程内, 不打印不落盘
    def one(j):
        kind, ptr, f, v, i, body = j
        read, _probs, err = S0.s0_jev_read(body[:2000], FACETS, post=post)
        return {"kind": kind, "ptr": ptr, "facet": f, "value": v, "phrasing": i, "read": read, "err": err}
    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = list(ex.map(one, js))
    errs = collections.Counter(r["err"] for r in rows if r["err"])
    neu_ch, per = analyse(rows) if a.variant == "main" else (None, analyse_v2(rows))
    res = {"block": "S0_PLANTED_SIGNAL_VALIDITY" + ("" if a.variant == "main" else "_EXPLORATORY_EMOTION_V2"),
           "variant": a.variant, "run_at": "2026-09-29", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "jev_question_sha": shadow.question_sha(), "passages": [p for p, _ in passages],
           "requests": ledger["req"], "jobs": len(js), "errors": dict(errs),
           "neutral_change": neu_ch, "per_facet": per,
           "★predictions": ({"P1": {k: per[k]["verdict"] for k in ("进程位置", "触发事件", "资源状态")},
                             "P2_情绪余温": per["情绪余温"]["verdict"], "P3_neutral_change<=0.05": neu_ch <= 0.05}
                            if a.variant == "main" else "探索臂: 不设预注册判决, 只报溢出与召回"),
           "★what_it_cannot_claim": pre["★what_it_cannot_claim"],
           "raw": [{k: r[k] for k in ("kind", "ptr", "facet", "value", "phrasing", "read", "err")} for r in rows]}
    if not a.dry_run:
        out_path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"requests": ledger["req"], "errors": dict(errs), "neutral_change": neu_ch,
                      "per_facet": per if a.variant != "main" else
                      {k: {kk: v[kk] for kk in ("recovery", "net_off_target", "verdict")} for k, v in per.items()}},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
