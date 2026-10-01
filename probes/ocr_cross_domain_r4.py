#!/usr/bin/env python3
"""OCR 跨内容域可搬性 · 第四轮(按文字密度分层) —— 预注册 tests/data/phase2/ocr_cross_domain_r4_prereg.json。

前三轮的共同线索: 损失集中在文字密集的帧 ⇒ 域差可能经文字密度传导。本轮先按一个**与被测 OCR 和真值都无关**
的密度量把帧分档(macOS Vision 文字框, probes/text_density_vision.swift), 档界写死在预注册里, 再在档内比域。

用法:
  ocr_cross_domain_r4.py density   # 全部 stackA 帧跑 Vision 密度(零被测 OCR、零真值) → r4_density.json
  ocr_cross_domain_r4.py selftest  # 仪器自检: RapidOCR 读回/版本 + 密度仪器合成单调/水印排除/确定性
  ocr_cross_domain_r4.py sample    # 打印各 (域, 档) 转写顺序(零 OCR) —— 转写前用
  ocr_cross_domain_r4.py freeze    # 真值写完后记录 sha256 → r4_gt_freeze.json(提交后再 run)
  ocr_cross_domain_r4.py run       # 跑 OCR + 判定 → tests/data/phase2/ocr_cross_domain_r4.json

★ 真值不在本仓(含屏幕上的创作者名): 仓内只放 sha/路径/数字。素材或真值缺席 ⇒ 返回 2, 不出结论。
"""
import hashlib, json, os, platform, statistics, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
import ocr_cross_domain as R1                      # meta / OCR 调用 / 1−CER / judge
import ocr_cross_domain_r2 as R2                   # 视频聚类区间 / 留一创作者 / measure / selftest
import ocr_cross_domain_r3 as R3                   # 有界水印过滤 keep_v3 / 前两轮看过的帧

VSE, FRAMES = R1.VSE, R1.FRAMES
GT = f"{VSE}/results/ocr_gt_douyin_frames_v4.json"
PH2 = os.path.join(ROOT, "tests/data/phase2")
PRE = os.path.join(PH2, "ocr_cross_domain_r4_prereg.json")
DENS = os.path.join(PH2, "ocr_cross_domain_r4_density.json")
FREEZE = os.path.join(PH2, "ocr_cross_domain_r4_gt_freeze.json")
OUT = os.path.join(PH2, "ocr_cross_domain_r4.json")
SWIFT = os.path.join(ROOT, "probes/text_density_vision.swift")
SEED, I6_MAX, N_BOOT = 20261004, 0.02, R2.N_BOOT
TIERS = ("SPARSE", "DENSE")


# ---------- 密度仪器(与被测 OCR / 真值无关) ----------
def _ov(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2]


def density(boxes):
    """Vision 框 [x,y,w,h,n,wm] → 去掉抖音水印块后的估计字数 D = Σn。
    水印块 = wm 框(串含「抖音」/「音号」) + 每个 wm 框正下方紧邻且同字号的 1 个框(昵称; 规则同 keep_v3 ③)。"""
    wm = {k for k, b in enumerate(boxes) if b[5]}
    for a in [k for k in wm]:
        A = boxes[a]
        below = [(b[1] - (A[1] + A[3]), k) for k, b in enumerate(boxes) if k not in wm and _ov(b, A)
                 and b[1] >= A[1] + A[3] / 2 and b[1] - (A[1] + A[3]) <= 1.5 * A[3] and b[3] <= 1.5 * A[3]]
        if below:
            wm.add(min(below)[1])
    return sum(b[4] for k, b in enumerate(boxes) if k not in wm), len(boxes) - len(wm), len(wm)


def tier(d, edges):
    """edges = [e1]: D < e1 ⇒ SPARSE; D >= e1 ⇒ DENSE(档界在预注册里写死)。"""
    return TIERS[sum(d >= e for e in edges)]


def _vision(paths):
    with tempfile.TemporaryDirectory() as td:
        exe = os.path.join(td, "tdv")
        subprocess.run(["swiftc", "-O", SWIFT, "-o", exe], check=True)
        go = lambda ch: [json.loads(l) for l in subprocess.run([exe] + ch, capture_output=True, text=True,
                                                                check=True).stdout.splitlines()]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(6) as ex:
            res = {r["path"]: r for part in ex.map(go, [paths[k:k + 100] for k in range(0, len(paths), 100)])
                   for r in part}
        # 并发下 Vision 偶发整批 perform 失败(实测一次 903/2694, 单跑同帧正常) ⇒ 失败帧串行重跑, 至多 3 遍
        for _ in range(3):
            bad = [p for p, r in res.items() if "error" in r]
            if not bad:
                break
            res.update({r["path"]: r for r in go(bad)})
        return [res[p] for p in paths]


def cmd_density():
    paths = sorted(f"{FRAMES}/{i}/{f}" for i in os.listdir(FRAMES) for f in R2.FRAME_NAMES
                   if os.path.exists(f"{FRAMES}/{i}/{f}"))
    frames, errors = {}, []
    for r in _vision(paths):
        key = r["path"].split("stackA_frames/")[1]
        if "error" in r:
            errors.append({"frame": key, "why": r["error"]}); continue
        d, nb, nwm = density(r["boxes"])
        frames[key] = [d, nb, nwm]
    json.dump({"block": "OCR_CROSS_DOMAIN_R4_DENSITY", "computed_at": "2026-10-01",
               "instrument": "macOS Vision VNRecognizeTextRequest rev3 accurate zh-Hans+en-US, 只取框几何与每框非空白字符数",
               "os": platform.mac_ver()[0], "swift_source_sha256": R1._sha(SWIFT),
               "fields": "frame -> [D 去水印后估计字数, 去水印后框数, 水印块框数]",
               "★independence": "不调用被测 OCR(RapidOCR), 不读真值; 识别出的文字不落盘。",
               "n_frames": len(frames), "errors": errors, "frames": frames},
              open(DENS, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("density", len(frames), "errors", len(errors)); return 0


def density_selftest():
    """D0 合成单调: 0/8/40/120 字小号文本 → D 严格递增, 空白图 D=0;
    D1 水印排除: 加一个「抖音号: …」+ 昵称块, D 不变; D2 确定性: 同图两次逐字节相同。"""
    from PIL import Image, ImageDraw
    from ocr_quality_curve import _font
    f = _font("zh")
    base = "今天分享一个提高效率的小方法大家可以试试看"
    with tempfile.TemporaryDirectory() as td:
        paths = []
        for k, n in enumerate((0, 8, 40, 120)):
            im = Image.new("RGB", (448, 796), (255, 255, 255))
            dr = ImageDraw.Draw(im)
            s = (base * 10)[:n]
            for row in range(0, n, 16):
                dr.text((20, 120 + row // 16 * 34), s[row:row + 16], fill=(0, 0, 0), font=f.font_variant(size=24))
            p = os.path.join(td, f"d{k}.png"); im.save(p); paths.append(p)
        im = Image.open(paths[2]).copy(); dr = ImageDraw.Draw(im)
        dr.text((10, 20), "抖音", fill=(0, 0, 0), font=f.font_variant(size=26))
        dr.text((10, 56), "抖音号: demo0000001", fill=(0, 0, 0), font=f.font_variant(size=18))
        dr.text((10, 82), "示例昵称", fill=(0, 0, 0), font=f.font_variant(size=18))
        pw = os.path.join(td, "wm.png"); im.save(pw)
        r = _vision(paths + [pw, paths[3]])
    ds = [density(x["boxes"])[0] if "boxes" in x else None for x in r]
    return {"D0_monotone": ds[0] == 0 and None not in ds[:4] and ds[0] < ds[1] < ds[2] < ds[3],
            "D1_watermark_excluded": ds[4] == ds[2], "D2_deterministic": r[3] == r[5],
            "synthetic_D": {"chars_0_8_40_120": ds[:4], "40+watermark": ds[4]}}


# ---------- 选域 / 抽样 ----------
def seen_frames():
    """前三轮看过的帧: 三份真值的每一帧 + 第一轮 pilot 的 01.jpg。"""
    seen = R3.seen_frames()
    g3 = json.load(open(R3.GT, encoding="utf-8"))
    return seen | {(it["aweme_id"], os.path.basename(it["frame_path"])) for it in g3["items"]}


def cells(m, dens, edges, seen):
    """(域, 档) → 未看过的候选帧, 按 sha256('<aweme_id>/<帧名>') 升序。"""
    out = {}
    for i in os.listdir(FRAMES):
        if i not in m:
            continue
        for f in R2.FRAME_NAMES:
            k = f"{i}/{f}"
            if (i, f) in seen or k not in dens:
                continue
            out.setdefault((m[i][0], tier(dens[k][0], edges)), []).append((i, f))
    return {c: sorted(v, key=lambda x: hashlib.sha256(f"{x[0]}/{x[1]}".encode()).hexdigest())
            for c, v in out.items()}


def choose_domains(cc, rule):
    """合格 = 每档未看候选 >= rule['min_candidates'][档]; 合格域按 DENSE 候选数降序(同数按 sha256(域名) 升序)
    取前 rule['n_domains'] 个 —— 只看候选计数(机器密度), 不看帧、不看 OCR、不看真值。"""
    doms = {d for d, _ in cc}
    ok = [d for d in doms if all(len(cc.get((d, t), [])) >= rule["min_candidates"][t] for t in TIERS)]
    key = lambda k: (-len(cc.get((k, "DENSE"), [])), hashlib.sha256(k.encode()).hexdigest())
    return sorted(ok, key=key)[:rule["n_domains"]], sorted(ok, key=key)


def plan(pre=None):
    pre = pre or json.load(open(PRE, encoding="utf-8"))
    dens = json.load(open(DENS, encoding="utf-8"))["frames"]
    m = R1.meta()
    cc = cells(m, dens, pre["density"]["tier_edges"], seen_frames())
    chosen, _ = choose_domains(cc, pre["domains"]["selection_rule"])
    return m, {f"{d}|{t}": cc.get((d, t), []) for d in chosen for t in TIERS}, chosen


# ---------- 统计 ----------
def strat_boot(cells_a, cells_b, rng):
    """档均衡均值差: 每域 = 各档均值的等权平均; 每 (域,档) 格内对视频有放回重采样, 格间独立。
    ponytail: 同一视频跨档出现时格间独立重采样忽略了这点相关(只会让区间更宽/更保守)。"""
    import numpy as np

    def packs(cs):
        out = []
        for rows in cs:
            cl = {}
            for r in rows:
                s = cl.setdefault(r["video"], [0.0, 0]); s[0] += r["acc_zh"]; s[1] += 1
            out.append((np.array([v[0] for v in cl.values()]), np.array([v[1] for v in cl.values()])))
        return out

    def draw(ps):
        tot = 0
        for s, c in ps:
            ix = rng.integers(0, len(s), (N_BOOT, len(s)))
            tot = tot + s[ix].sum(1) / c[ix].sum(1)
        return tot / len(ps)

    d = np.sort(draw(packs(cells_a)) - draw(packs(cells_b)))
    return float(d[int(0.05 * N_BOOT)]), float(d[int(0.95 * N_BOOT) - 1])


def strat_pair(ca, cb, rng):
    """ca/cb: 同序的档 → 逐帧行。点估计 + 区间 + 留一创作者(从一侧所有档剔除该创作者)。"""
    bal = lambda cs: sum(sum(r["acc_zh"] for r in rows) / len(rows) for rows in cs) / len(cs)
    lo, hi = strat_boot(ca, cb, rng)
    v = R1.judge(lo, hi)
    loco = []
    for side, cs in (("a", ca), ("b", cb)):
        for c in sorted({r["creator"] for rows in cs for r in rows}):
            kept = [[r for r in rows if r["creator"] != c] for rows in cs]
            if any(not rows for rows in kept):
                loco.append({"dropped_side": side, "creator_idx": c, "verdict": "SKIPPED_EMPTY_CELL"}); continue
            l2, h2 = strat_boot(kept, cb, rng) if side == "a" else strat_boot(ca, kept, rng)
            loco.append({"dropped_side": side, "creator_idx": c, "ci90": [round(l2, 4), round(h2, 4)],
                         "verdict": R1.judge(l2, h2)})
    stable = all(x["verdict"] in (v, "SKIPPED_EMPTY_CELL") for x in loco)
    return {"mean_diff": round(bal(ca) - bal(cb), 4), "ci90": [round(lo, 4), round(hi, 4)], "verdict_raw": v,
            "loco_all_same": stable, "verdict": v if stable else "INCONCLUSIVE", "loco": loco}


def judge_all(cellres, chosen, rng):
    ok = lambda d, t: cellres[f"{d}|{t}"]["status"] != "INSUFFICIENT"
    rows = lambda d, t: cellres[f"{d}|{t}"]["per_frame"]
    within = {}
    for t in TIERS:
        ds = [d for d in chosen if ok(d, t)]
        for x in range(len(ds)):
            for y in range(x + 1, len(ds)):
                within[f"{t}:{ds[x]}|{ds[y]}"] = R2.pair_verdict(rows(ds[x], t), rows(ds[y], t), rng)
    lo_t, hi_t = TIERS[0], TIERS[-1]
    pool = lambda t: [r for d in chosen if ok(d, t) for r in rows(d, t)]
    cross = R2.pair_verdict(pool(lo_t), pool(hi_t), rng) if pool(lo_t) and pool(hi_t) else None
    strat = {}
    for x in range(len(chosen)):
        for y in range(x + 1, len(chosen)):
            a, b = chosen[x], chosen[y]
            ts = [t for t in TIERS if ok(a, t) and ok(b, t)]
            if ts:
                strat[f"{a}|{b}"] = dict(strat_pair([rows(a, t) for t in ts], [rows(b, t) for t in ts], rng),
                                         tiers_used=ts)
    unstrat = {}
    for x in range(len(chosen)):
        for y in range(x + 1, len(chosen)):
            a, b = chosen[x], chosen[y]
            ra = [r for t in TIERS if ok(a, t) for r in rows(a, t)]
            rb = [r for t in TIERS if ok(b, t) for r in rows(b, t)]
            p = R2.pair_verdict(ra, rb, rng)
            unstrat[f"{a}|{b}"] = {k: p[k] for k in ("mean_diff", "ci90", "verdict_raw", "loco_all_same", "verdict")}
    wv = [p["verdict"] for p in within.values()]
    full = all(sum(ok(d, t) for d in chosen) >= 2 for t in TIERS)
    if "NOT_TRANSFERABLE" in wv or (cross and cross["verdict"] == "TRANSFERABLE"):
        h_den = "REJECTED"
    elif full and wv and set(wv) == {"TRANSFERABLE"} and cross and cross["verdict"] == "NOT_TRANSFERABLE":
        h_den = "SUPPORTED"
    else:
        h_den = "STILL_UNDETERMINED"
    per_tier = {}
    for t in TIERS:
        v = [p["verdict"] for k, p in within.items() if k.startswith(t + ":")]
        per_tier[t] = ("DOES_NOT_TRANSFER_WITHIN_TIER" if "NOT_TRANSFERABLE" in v else
                       "TRANSFERS_WITHIN_TIER" if v and set(v) == {"TRANSFERABLE"}
                       and sum(ok(d, t) for d in chosen) == len(chosen) else "STILL_UNDETERMINED")
    sv = [p["verdict"] for p in strat.values()]
    all_tiers = all(len(p["tiers_used"]) == len(TIERS) for p in strat.values())
    h_dom = ("RESIDUAL_DOMAIN_EFFECT" if "NOT_TRANSFERABLE" in sv else
             "NO_RESIDUAL_DOMAIN_EFFECT_WITHIN_DELTA" if sv and set(sv) == {"TRANSFERABLE"} and all_tiers
             and len(strat) == len(chosen) * (len(chosen) - 1) // 2 else "STILL_UNDETERMINED")
    return {"within_tier_pairs": within, "cross_tier_sparse_vs_dense": cross,
            "stratified_domain_pairs": strat, "unstratified_domain_pairs_descriptive": unstrat,
            "per_tier_verdict": per_tier, "H_density": h_den, "H_domain_given_density": h_dom}


# ---------- 命令 ----------
def cmd_selftest():
    print(json.dumps({"ocr": R2.selftest(), "density": density_selftest()}, ensure_ascii=False, indent=1)); return 0


def cmd_sample():
    m, cl, chosen = plan()
    print("chosen", chosen)
    for c, cands in cl.items():
        print(f"## {c} n_candidates={len(cands)} videos={len({i for i, _ in cands})} "
              f"creators={len({m[i][1] for i, _ in cands})}")
        for i, f in cands:
            print(f"{c}\t{i}\t{f}\t{FRAMES}/{i}/{f}")
    return 0


def cmd_freeze():
    if not os.path.exists(GT):
        print(f"★ 真值不在本机 {GT}"); return 2
    json.dump({"block": "OCR_CROSS_DOMAIN_R4_GT_FREEZE", "frozen_at": "2026-10-01", "gt_path": GT,
               "gt_sha256": R1._sha(GT),
               "★order": "本文件提交时 OCR 尚未在第四轮样本上运行; run 会校验真值 sha 等于此值。"},
              open(FREEZE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("frozen", R1._sha(GT)); return 0


def cmd_run():
    import numpy as np
    if not (os.path.exists(GT) and os.path.isdir(FRAMES)):
        print("★ 真值或素材不在本机 —— 不出结论。"); return 2
    pre, fz = json.load(open(PRE, encoding="utf-8")), json.load(open(FREEZE, encoding="utf-8"))
    m, cl, chosen = plan(pre)
    st, ds = R2.selftest(), density_selftest()
    gate = {"I0_readback": st["I0_readback"], "I2_versions": st["I2_versions"],
            "I3_gt_frozen": R1._sha(GT) == fz["gt_sha256"],
            "D0_density_monotone": ds["D0_monotone"], "D1_density_watermark_excluded": ds["D1_watermark_excluded"],
            "D2_density_deterministic": ds["D2_deterministic"],
            "D3_density_file_frozen": R1._sha(DENS) == pre["density"]["density_file_sha256"],
            "D4_domains_as_preregistered": chosen == pre["domains"]["chosen"]}
    gt = json.load(open(GT, encoding="utf-8"))
    by_key = {(it["aweme_id"], os.path.basename(it["frame_path"])): it for it in gt["items"]}
    gate["I5_no_seen_frame"] = not (set(by_key) & seen_frames())
    cache, determinism = {}, []
    for c, cands in cl.items():                          # I1: 每格前 1 帧连跑两次
        for i, f in [x for x in cands if x in by_key][:1]:
            p = f"{FRAMES}/{i}/{f}"
            cache[p] = R1.ocr(p)
            determinism.append({"cell": c, "aweme_id": i, "frame": f, "same": R1.ocr(p) == cache[p]})
    gate["I1_determinism"] = bool(determinism) and all(d["same"] for d in determinism)
    R2.N_TARGET, R2.N_MIN = pre["sampling"]["n_target_per_cell"], pre["sampling"]["n_min_per_cell"]
    results = {name: R2.measure(flt, cl, by_key, m, cache)
               for name, flt in (("v3_bounded", R3.keep_v3),
                                 ("no_filter_upper_bound", lambda rows, _n: [t for t, _ in rows]))}
    d3 = results["v3_bounded"]
    gate["fail_rate_ok"] = all(d["n_ocr_failed"] <= 0.10 * max(1, d["n_text_frames"] + d["n_blank_controls"])
                               for d in d3.values())
    up = {k: {r["frame"]: r["acc_zh"] for r in d["per_frame"]} for k, d in results["no_filter_upper_bound"].items()}
    i6 = {c: round(statistics.mean(up[c][r["frame"]] - r["acc_zh"] for r in d["per_frame"]), 4)
          for c, d in d3.items() if d["per_frame"]}                # 逐 (域,档) 格; 空格不算
    gate["I6_filter_preserves_text"] = bool(i6) and all(v <= I6_MAX for v in i6.values())
    probe = [x for c in cl.values() for x in c[:1]]               # D5: 每格首帧现算密度 = 冻结值
    dens_now = _vision([f"{FRAMES}/{i}/{f}" for i, f in probe])
    frozen = json.load(open(DENS, encoding="utf-8"))["frames"]
    gate["D5_density_recomputed_equal"] = all("boxes" in r and list(density(r["boxes"])) == frozen[f"{i}/{f}"]
                                              for (i, f), r in zip(probe, dens_now))
    gate["I4_variance"] = all(len({r["acc_zh"] for t in TIERS for r in d3[f"{d}|{t}"]["per_frame"]}) > 1
                              for d in chosen)
    gate_ok = all(gate.values())
    verdicts = judge_all(d3, chosen, np.random.default_rng(SEED)) if gate_ok else {
        "H_density": "INSTRUMENT_GATE_FAILED", "H_domain_given_density": "INSTRUMENT_GATE_FAILED"}
    explo = None
    if not gate_ok:                                               # 只描述, 不判定(预注册: 不许事后换过滤器补判)
        ex = R2.measure(keep_v3b, cl, by_key, m, cache)
        i6b = {c: round(statistics.mean(up[c][r["frame"]] - r["acc_zh"] for r in d["per_frame"]), 4)
               for c, d in ex.items() if d["per_frame"]}
        base_ok = all(v for k, v in gate.items() if k != "I6_filter_preserves_text")
        ok_b = base_ok and all(v <= I6_MAX for v in i6b.values())
        explo = {"role": "EXPLORATORY_POST_HOC —— 主过滤器 I6 不过之后才写的 keep_v3b, **不作判定、不改注册表状态**",
                 "root_cause": I6_ROOT_CAUSE, "I6_under_keep_v3b": i6b, "I6_would_pass": ok_b,
                 "acc_zh_mean": {c: d["acc_zh_mean"] for c, d in ex.items()},
                 "n_text_frames": {c: d["n_text_frames"] for c, d in ex.items()},
                 "verdict_shaped_readout": judge_all(ex, chosen, np.random.default_rng(SEED)) if ok_b else None}
    cell_density = {c: {"D_median": statistics.median(dens_of(r) for r in d["per_frame"]) if d["per_frame"] else None}
                    for c, d in d3.items()}
    res = {"block": "OCR_CROSS_DOMAIN_R4", "measured_at": "2026-10-01",
           "prereg": "tests/data/phase2/ocr_cross_domain_r4_prereg.json",
           "annotator": "Claude_single_non_human", "gt_path": GT, "gt_sha256": R1._sha(GT),
           "engine_versions": st["versions"], "instrument_gate": gate, "selftest_readback": st["readback"],
           "density_selftest": ds, "determinism_checks": determinism,
           "I6_mean_acc_loss_vs_no_filter": i6, "I6_max": I6_MAX,
           "domains_chosen": chosen, "tier_edges": pre["density"]["tier_edges"],
           "H_density": verdicts["H_density"], "H_domain_given_density": verdicts["H_domain_given_density"],
           "verdicts": verdicts, "cell_density": cell_density,
           "cells": {"v3_bounded": {"role": "primary_preregistered", "cells": d3},
                     "no_filter_upper_bound": {"role": "I6_reference_only", "cells": results["no_filter_upper_bound"]}},
           "exploratory_post_hoc": explo,
           "★deviations_registered": DEVIATIONS,
           "★prior_rounds_not_pooled": "第一到三轮数据只用于功效估算与档界先验, 不并入本轮判定。",
           "★no_transcriptions_in_repo": "本文件只有路径/sha/数字; 转写在仓外真值文件。"}
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    show = lambda p: [p["mean_diff"], p["ci90"], p["verdict_raw"], p["loco_all_same"], p["verdict"]]
    print(json.dumps({"gate": gate, "I6": i6, "H_density": res["H_density"],
                      "H_domain_given_density": res["H_domain_given_density"],
                      "cells": {c: [d["status"], d["n_text_frames"], d["n_videos"], d["n_creators"], d["acc_zh_mean"],
                                    f"blank {d['n_blank_controls']} hall {d['hallucinated_on_blank']}"]
                                for c, d in d3.items()},
                      **({k: ({kk: show(vv) for kk, vv in verdicts[k].items()} if k != "cross_tier_sparse_vs_dense"
                              else show(verdicts[k]) if verdicts[k] else None)
                          for k in ("within_tier_pairs", "cross_tier_sparse_vs_dense", "stratified_domain_pairs",
                                    "unstratified_domain_pairs_descriptive")} if gate_ok else {})},
                     ensure_ascii=False, indent=1))
    return 0


def keep_v3b(rows, nickname):
    """★ 事后(I6 不过之后)的探索用过滤器, 不是本轮仪器: keep_v3 ② 用「行首 … 音号: 号码」整段删除,
    OCR 把锚左侧同一行的正文并进锚框时会连正文一起删。v3b 先把锚框里「音号」前一字之前的前缀拆成独立行(无框, 不参与
    ③④ 的几何判断)再交给 keep_v3, 其余规则不变。"""
    out = []
    for t, b in rows:
        mm = R3.WM_ID.search(t)
        k = None if not mm else max(0, mm.start() - (1 if t[mm.start():mm.start() + 2] == "音号" else 0))
        if k and len(R1._core(t[:k])) >= 1:
            out += [(t[:k], None), (t[k:], b)]
        else:
            out.append((t, b))
    return R3.keep_v3(out, nickname)


I6_ROOT_CAUSE = ("户外跑步|SPARSE 损失 0.0435 来自 2 帧(单帧损失 0.556 / 0.75): 底部一行免责声明与「抖音号: …」在同一水平线上, "
                 "RapidOCR 把两者并成一个框(核心字 27), keep_v3 ② 的「行首到号码」整段删除连同前面的正文一起删掉。"
                 "第三轮只验证了「号码之后的残余」保留, 没验证「号码之前的前缀」—— 同一条教训再次出现: 仪器在新版式上没先自检。"
                 "另 户外跑步|DENSE 1 帧(t=0)锚正下方紧邻的大字标题被 ③ 当昵称删(字高约 1.2x 锚高 < 1.5x 阈值), 该格 I6 0.0091 未超限。")


_DENS_CACHE = {}


def dens_of(row):
    if not _DENS_CACHE:
        _DENS_CACHE.update(json.load(open(DENS, encoding="utf-8"))["frames"])
    return _DENS_CACHE[row["frame"].split("stackA_frames/")[1]][0]


DEVIATIONS = [
    "转写规则澄清(转写中途、任何被测 OCR 之前): 满屏平铺重复的背景品牌字样只录一次并记 partial(召回型指标, OCR 多读不罚)。",
    "非偏离、如实登记(冻结真值前已知, 只看了有字帧计数): 户外跑步 SPARSE 68 候选耗尽只有 30 张有字帧(OK_REDUCED); "
    "DENSE 三格候选 47/22/20, 户外跑步 22、智能家居 20 均耗尽(OK_REDUCED, 智能家居恰好等于下限 20); DENSE 候选无一帧真值无字。",
]


if __name__ == "__main__":
    rc = {"density": cmd_density, "selftest": cmd_selftest, "sample": cmd_sample, "freeze": cmd_freeze,
          "run": cmd_run}[sys.argv[1] if len(sys.argv) > 1 else "run"]()
    sys.stdout.flush()
    os._exit(rc)  # onnxruntime 在解释器退出析构时 abort, 产物已落盘
