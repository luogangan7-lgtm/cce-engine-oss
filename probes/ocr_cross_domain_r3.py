#!/usr/bin/env python3
"""OCR 跨内容域可搬性 · 第三轮(新域) —— 预注册 tests/data/phase2/ocr_cross_domain_r3_prereg.json。

第一/二轮的 4 域候选帧已近耗尽, 源视频 mp4 大多不在本机 ⇒ 本轮换**三个从未看过的域**(选域规则见预注册,
按 sha256(域名) 定序, 不看帧挑域)。水印过滤换成**有界水印块** keep_v3(只删抖音水印块本身, 块外不删),
并把过滤器保真闸 I6 写进预注册当前置仪器闸(第二轮是事后补的)。

用法:
  ocr_cross_domain_r3.py selftest  # 仪器自检(合成图读回 + 版本), 不碰样本
  ocr_cross_domain_r3.py sample    # 打印各域转写顺序(零 OCR) —— 转写前用
  ocr_cross_domain_r3.py freeze    # 真值写完后记录 sha256 → r3_gt_freeze.json(提交后再 run)
  ocr_cross_domain_r3.py run       # 跑 OCR + 判定 → tests/data/phase2/ocr_cross_domain_r3.json

★ 真值不在本仓(含屏幕上的创作者名): 仓内只放 sha/路径/数字。素材或真值缺席 ⇒ 返回 2, 不出结论。
"""
import hashlib, json, os, re, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
import ocr_cross_domain as R1                      # meta / OCR 调用 / 1−CER / judge
import ocr_cross_domain_r2 as R2                   # 视频聚类区间 / 留一创作者 / measure / selftest

VSE, FRAMES = R1.VSE, R1.FRAMES
GT = f"{VSE}/results/ocr_gt_douyin_frames_v3.json"
PRE = os.path.join(ROOT, "tests/data/phase2/ocr_cross_domain_r3_prereg.json")
FREEZE = os.path.join(ROOT, "tests/data/phase2/ocr_cross_domain_r3_gt_freeze.json")
OUT = os.path.join(ROOT, "tests/data/phase2/ocr_cross_domain_r3.json")
SEED, I6_MAX = 20261003, 0.02
POOL = ("效率工具", "露营装备", "读书分享", "情感成长", "三农生活", "装修避坑")
N_DOMAINS = 3
WM_ID = re.compile(r"音号|号[:：]\s*[A-Za-z0-9_.]{5,}")
WM_ID_SPAN = re.compile(r"^.*?(?:音号[:：]?|号[:：])\s*[A-Za-z0-9_.\-]*")


def choose_domains():
    """未用过且 >=48 条视频、5 名创作者的 6 个域, 按 sha256(域名) 升序取前 3 —— 不看帧挑域。"""
    return sorted(POOL, key=lambda k: hashlib.sha256(k.encode()).hexdigest())[:N_DOMAINS]


def _overlap_x(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2]


def keep_v3(rows, nickname):
    """有界水印块过滤。抖音水印块 = 三行竖排: logo「抖音」/「抖音号: xxx」/「Q昵称」, 只删这三样, 块外不删。
    ① logo: 含「抖音」且核心字 <= 4 的行。
    ② 锚 = 匹配 WM_ID 的行(容 OCR 把「抖」读错, 如「拟音号」): 只删「…音号: <字母数字号>」这一段,
       同一 OCR 框里号码后面的残余文字保留(OCR 会把同一行右侧的正文并进锚框)。
    ③ 锚正下方紧邻 1 行 = 昵称: 与锚框水平区间相交, 竖直间隙 <= 1.5 x 锚框高, 且字高 <= 1.5 x 锚框高
       (昵称与抖音号同字号; 标题字更大, 不会被当昵称删)。
    ④ 锚正上方紧邻 1 行且核心字 <= 4 = 读错的 logo; 更长的行是正文, 不删。
    ⑤ 无锚: 只删以 Q/🔍 开头、去掉后核心字与 meta 昵称互为子串(>=3 字或等于昵称)的行。不带 Q 的不删(宁可漏水印)。
    ★ 第二轮 v2「锚下方整片都算水印」在 t=0 帧(水印在左上)吃掉了真值文字; 本版每一条都有界。"""
    drop, out = set(), {}
    for k, (t, b) in enumerate(rows):
        if "抖音" in t and len(R1._core(t)) <= 4:
            drop.add(k)
    anchors = [k for k, (t, b) in enumerate(rows) if k not in drop and WM_ID.search(t)]
    for a in anchors:
        rest = WM_ID_SPAN.sub("", rows[a][0], count=1)
        out[a] = rest if len(R1._core(rest)) >= 1 else None
        b0 = rows[a][1]
        if not b0:
            continue
        ax, ay, aw, ah = b0
        below = [(b[1] - (ay + ah), k) for k, (t, b) in enumerate(rows)
                 if k != a and b and _overlap_x(b, b0) and b[1] >= ay + ah / 2
                 and b[1] - (ay + ah) <= 1.5 * ah and b[3] <= 1.5 * ah]
        above = [(ay - (b[1] + b[3]), k) for k, (t, b) in enumerate(rows)
                 if k != a and b and _overlap_x(b, b0) and b[1] + b[3] <= ay + ah / 2
                 and ay - (b[1] + b[3]) <= 1.5 * ah]
        if below:
            drop.add(min(below)[1])
        if above and len(R1._core(rows[min(above)[1]][0])) <= 4:
            drop.add(min(above)[1])
    if not anchors:
        nick = R1._core(nickname)
        for k, (t, b) in enumerate(rows):
            if not t.startswith(("Q", "🔍")):
                continue
            c = R1._core(t.lstrip("Q🔍 "))
            if c and nick and (c == nick or (len(c) >= 3 and (c in nick or nick in c))):
                drop.add(k)
    res = []
    for k, (t, b) in enumerate(rows):
        if k in drop:
            continue
        if k in out:
            if out[k] is not None:
                res.append(out[k])
            continue
        res.append(t)
    return res


def seen_frames():
    """第一/二轮看过的帧: 两份真值的每一帧 + 第一轮 pilot 的 01.jpg。"""
    seen = set()
    for g in (R1.GT, R2.GT):
        seen |= {(it["aweme_id"], os.path.basename(it["frame_path"]))
                 for it in json.load(open(g, encoding="utf-8"))["items"]}
    pre2 = json.load(open(R2.PRE, encoding="utf-8"))
    return seen | {(i, "01.jpg") for i in pre2["exclusions"]["round1_pilot_aweme_ids"]}


def order(m):
    """每域: 全部视频 x {00,01,02} 去掉看过的帧, 按 sha256('<aweme_id>/<帧名>') 升序。"""
    seen = seen_frames()
    ids = [i for i in os.listdir(FRAMES) if i in m]
    out = {}
    for kw in choose_domains():
        cand = [(i, f) for i in ids if m[i][0] == kw for f in R2.FRAME_NAMES
                if (i, f) not in seen and os.path.exists(f"{FRAMES}/{i}/{f}")]
        out[kw] = sorted(cand, key=lambda x: hashlib.sha256(f"{x[0]}/{x[1]}".encode()).hexdigest())
    return out


DEVIATIONS = [
    "转写规则澄清(转写中途、任何 OCR 之前): 抖音片尾卡(「来抖音 发现更多创作者」+抖音号/搜索昵称+logo 整屏)按「排除抖音平台水印块」"
    "同一规则记为无字(flags: platform_end_card, 共 13 帧), 已回改此前同类 3 帧。keep_v3 不删片尾卡上的「来抖音 发现更多创作者」"
    "(含「抖音」但核心字 > 4), 故零文字对照的无中生有计数里大部分是片尾卡泄漏 —— 无中生有只作描述, 不是闸, 不影响判定。",
    "非偏离、如实登记: 三农生活候选 147 帧耗尽只有 77 张有字帧(OK_REDUCED), 且只来自 4 名创作者(第 5 名创作者入样的 27 帧全部无字, 只进零文字对照), 留一创作者在该侧只有 4 次。",
]


def judge(domains, rng):
    kws = [k for k in domains if domains[k]["status"] != "INSUFFICIENT"]
    pairs = {f"{kws[x]}|{kws[y]}": R2.pair_verdict(domains[kws[x]]["per_frame"], domains[kws[y]]["per_frame"], rng)
             for x in range(len(kws)) for y in range(x + 1, len(kws))}
    h1 = R2.overall([p["verdict"] for p in pairs.values()])
    if h1 != "DOES_NOT_TRANSFER" and len(kws) < len(domains):
        h1 = "STILL_UNDETERMINED"
    return pairs, h1


def cmd_selftest():
    print(json.dumps(R2.selftest(), ensure_ascii=False, indent=1)); return 0


def cmd_sample():
    m = R1.meta()
    for kw, cands in order(m).items():
        print(f"## {kw} n_candidates={len(cands)} videos={len({i for i, _ in cands})} "
              f"creators={len({m[i][1] for i, _ in cands})}")
        for i, f in cands:
            print(f"{kw}\t{i}\t{f}\t{FRAMES}/{i}/{f}")
    return 0


def cmd_freeze():
    if not os.path.exists(GT):
        print(f"★ 真值不在本机 {GT}"); return 2
    json.dump({"block": "OCR_CROSS_DOMAIN_R3_GT_FREEZE", "frozen_at": "2026-10-01", "gt_path": GT,
               "gt_sha256": R1._sha(GT),
               "★order": "本文件提交时 OCR 尚未在第三轮样本上运行; run 会校验真值 sha 等于此值。"},
              open(FREEZE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("frozen", R1._sha(GT)); return 0


def cmd_run():
    import numpy as np
    if not (os.path.exists(GT) and os.path.isdir(FRAMES)):
        print("★ 真值或素材不在本机 —— 不出结论。"); return 2
    m, fz = R1.meta(), json.load(open(FREEZE, encoding="utf-8"))
    st = R2.selftest()
    gate = {"I0_readback": st["I0_readback"], "I2_versions": st["I2_versions"],
            "I3_gt_frozen": R1._sha(GT) == fz["gt_sha256"]}
    gt = json.load(open(GT, encoding="utf-8"))
    by_key = {(it["aweme_id"], os.path.basename(it["frame_path"])): it for it in gt["items"]}
    gate["I5_no_seen_frame"] = not (set(by_key) & seen_frames())
    ords = order(m)
    cache, determinism = {}, []
    for kw, cands in ords.items():                       # I1: 每域前 3 帧连跑两次
        for i, f in [x for x in cands if x in by_key][:3]:
            p = f"{FRAMES}/{i}/{f}"
            cache[p] = R1.ocr(p)
            determinism.append({"domain": kw, "aweme_id": i, "frame": f, "same": R1.ocr(p) == cache[p]})
    gate["I1_determinism"] = bool(determinism) and all(d["same"] for d in determinism)
    results = {name: R2.measure(flt, ords, by_key, m, cache)
               for name, flt in (("v3_bounded", keep_v3),
                                 ("no_filter_upper_bound", lambda rows, _n: [t for t, _ in rows]))}
    d3 = results["v3_bounded"]
    gate["I4_variance"] = all(d["acc_zh_mean"] is not None and 0 < d["acc_zh_mean"] < 1
                              and len({r["acc_zh"] for r in d["per_frame"]}) > 1 for d in d3.values())
    gate["fail_rate_ok"] = all(d["n_ocr_failed"] <= 0.10 * max(1, d["n_text_frames"] + d["n_blank_controls"])
                               for d in d3.values())
    up = {k: {r["frame"]: r["acc_zh"] for r in d["per_frame"]} for k, d in results["no_filter_upper_bound"].items()}
    i6 = {k: round(statistics.mean(up[k][r["frame"]] - r["acc_zh"] for r in d["per_frame"]), 4)
          for k, d in d3.items() if d["per_frame"]}
    gate["I6_filter_preserves_text"] = len(i6) == len(d3) and all(v <= I6_MAX for v in i6.values())
    gate_ok = all(gate.values())
    pairs, h1 = judge(d3, np.random.default_rng(SEED)) if gate_ok else ({}, "INSTRUMENT_GATE_FAILED")
    res = {"block": "OCR_CROSS_DOMAIN_R3", "measured_at": "2026-10-01",
           "prereg": "tests/data/phase2/ocr_cross_domain_r3_prereg.json",
           "annotator": "Claude_single_non_human", "gt_path": GT, "gt_sha256": R1._sha(GT),
           "engine_versions": st["versions"], "instrument_gate": gate, "selftest_readback": st["readback"],
           "determinism_checks": determinism, "I6_mean_acc_loss_vs_no_filter": i6, "I6_max": I6_MAX,
           "domains_chosen": choose_domains(),
           "overall": h1, "H2_new_nongame_domains": h1 if gate_ok else "INSTRUMENT_GATE_FAILED",
           "H3_game_vs_others": "NOT_TESTABLE_THIS_ROUND",
           "pairs": pairs,
           "by_filter": {"v3_bounded": {"role": "primary_preregistered", "domains": d3},
                         "no_filter_upper_bound": {"role": "I6_reference_only(不过滤, 水印字可能虚增召回)",
                                                   "domains": results["no_filter_upper_bound"]}},
           "★deviations_registered": DEVIATIONS,
           "★prior_rounds_not_pooled": "第一/二轮数据只用于功效估算与过滤器开发, 不并入本轮判定。",
           "★no_transcriptions_in_repo": "本文件只有路径/sha/数字; 转写在仓外真值文件。"}
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"gate": gate, "overall": h1, "I6": i6,
                      "domains": {k: [v["status"], v["n_text_frames"], v["n_videos"], v["n_creators"],
                                      v["acc_zh_mean"], v["acc_zh_micro"], v["by_frame_position"],
                                      f"hall {v['hallucinated_on_blank']}/{v['n_blank_controls']}"]
                                  for k, v in d3.items()},
                      "pairs": {k: [v["mean_diff"], v["ci90"], v["verdict_raw"], v["loco_all_same"], v["verdict"],
                                    v["creator_cluster_ci90_descriptive"]] for k, v in pairs.items()}},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    rc = {"selftest": cmd_selftest, "sample": cmd_sample, "freeze": cmd_freeze,
          "run": cmd_run}[sys.argv[1] if len(sys.argv) > 1 else "run"]()
    sys.stdout.flush()
    os._exit(rc)  # onnxruntime 在解释器退出析构时 abort, 产物已落盘
