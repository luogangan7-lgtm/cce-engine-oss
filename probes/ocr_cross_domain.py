#!/usr/bin/env python3
"""OCR 跨**内容域**可搬性 —— 预注册 tests/data/phase2/ocr_cross_domain_prereg.json。

transfer_across_conditions.json 测了语言/密度/难度三条轴, 明说「域这条轴未测」。
本探针只让域变: 抖音视频中点帧(stackA_frames/*/01.jpg), 同分辨率、同 OCR 版本, 4 个关键词域。

用法:
  ocr_cross_domain.py sample   # 打印各域转写顺序(零 OCR) —— 转写前用
  ocr_cross_domain.py freeze   # 真值写完后: 记录真值 sha256 → gt_freeze.json(提交后再 run)
  ocr_cross_domain.py run      # 跑 OCR + 判定 → tests/data/phase2/ocr_cross_domain.json

★ 真值不在本仓(含屏幕上的创作者名/场景文字): 见预注册 annotation.storage。
  素材或真值不在本机 ⇒ 不出结论(返回 2), 不降级。
"""
import glob, hashlib, json, os, random, re, statistics, sys, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "probes"))
VSE = "/Volumes/data/viral-skill-eval"
FRAMES = f"{VSE}/assets/stackA_frames"
GT = f"{VSE}/results/ocr_gt_douyin_frames_v1.json"
PRE = os.path.join(ROOT, "tests/data/phase2/ocr_cross_domain_prereg.json")
FREEZE = os.path.join(ROOT, "tests/data/phase2/ocr_cross_domain_gt_freeze.json")
OUT = os.path.join(ROOT, "tests/data/phase2/ocr_cross_domain.json")
DELTA, N_BOOT, SEED, N_TARGET = 0.10, 10000, 20261001, 30
CJK = re.compile(r"[㐀-䶿一-鿿]")
LAT = re.compile(r"[A-Za-z0-9]")


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def meta():
    """aweme_id -> (kw, sec16, nickname)。域标签 = 采集时的 meta.kw。"""
    m = {}
    for f in glob.glob(f"{VSE}/assets/prereg*_douyin/*.json"):
        if os.path.basename(f).startswith("_"):
            continue
        d = json.load(open(f, encoding="utf-8"))
        for p in d["posts"]:
            m[p["source_video_id"]] = (d["meta"]["kw"], d["meta"]["sec16"], d["meta"]["nickname"])
    return m


def order(pre, m):
    """每域 sha256(aweme_id) 升序, 剔除 pilot。"""
    pilot = set(pre["domains"]["pilot_viewed_and_excluded"]["aweme_ids"])
    ids = [i for i in os.listdir(FRAMES) if i in m and i not in pilot]
    return {kw: sorted((i for i in ids if m[i][0] == kw),
                       key=lambda i: hashlib.sha256(i.encode()).hexdigest())
            for kw in pre["domains"]["chosen"]}


def _keep(s, rx, upper=False):
    s = unicodedata.normalize("NFKC", s)
    s = "".join(rx.findall(s))
    return s.upper() if upper else s


def acc(ref, hyp):
    from ocr_accuracy_real_zh import _cer          # 同式, 不另写
    return round(1.0 - _cer(ref, hyp), 4)


def hyp_lines(path, nickname):
    import cce_image_ingest as II
    vo = II.visual_observation(path)
    st = vo["completeness"]["status"]
    lines = [o["value"] for o in vo["observations"] if o["channel"] == "ocr_text"]
    nick = unicodedata.normalize("NFKC", nickname).replace(" ", "")
    kept = [t for t in lines if "抖音" not in t
            and unicodedata.normalize("NFKC", t).lstrip("Q🔍 ").replace(" ", "") != nick]
    return st, lines, kept


def boot_ci(a, b, rng):
    ds = []
    for _ in range(N_BOOT):
        ra = [a[rng.randrange(len(a))] for _ in a]
        rb = [b[rng.randrange(len(b))] for _ in b]
        ds.append(sum(ra) / len(ra) - sum(rb) / len(rb))
    ds.sort()
    return ds[int(0.05 * N_BOOT)], ds[int(0.95 * N_BOOT) - 1]


def judge(lo, hi):
    if -DELTA < lo and hi < DELTA:
        return "TRANSFERABLE"
    if lo > DELTA or hi < -DELTA:
        return "NOT_TRANSFERABLE"
    return "INCONCLUSIVE"


def pair_verdict(rows_a, rows_b, rng):
    a = [r["acc_zh"] for r in rows_a]
    b = [r["acc_zh"] for r in rows_b]
    lo, hi = boot_ci(a, b, rng)
    v = judge(lo, hi)
    loco = []
    for rows, other, side in ((rows_a, b, "a"), (rows_b, a, "b")):
        for c in sorted({r["creator"] for r in rows}):
            keep = [r["acc_zh"] for r in rows if r["creator"] != c]
            l2, h2 = boot_ci(keep, other, rng) if side == "a" else boot_ci(other, keep, rng)
            loco.append({"dropped_side": side, "creator_idx": c, "ci90": [round(l2, 4), round(h2, 4)],
                         "verdict": judge(l2, h2)})
    stable = all(x["verdict"] == v for x in loco)
    return {"mean_diff": round(sum(a) / len(a) - sum(b) / len(b), 4),
            "ci90": [round(lo, 4), round(hi, 4)], "verdict_raw": v,
            "loco_all_same": stable, "verdict": v if stable else "INCONCLUSIVE", "loco": loco}


def cmd_sample():
    pre, m = json.load(open(PRE, encoding="utf-8")), meta()
    for kw, ids in order(pre, m).items():
        print(f"## {kw} n_videos={len(ids)} creators={len({m[i][1] for i in ids})}")
        for i in ids:
            print(f"{kw}\t{i}\t{FRAMES}/{i}/01.jpg")
    return 0


def cmd_freeze():
    if not os.path.exists(GT):
        print(f"★ 真值不在本机 {GT}"); return 2
    json.dump({"block": "OCR_CROSS_DOMAIN_GT_FREEZE", "frozen_at": "2026-10-01",
               "gt_path": GT, "gt_sha256": _sha(GT),
               "★order": "本文件提交时 OCR 尚未在样本上运行; run 会校验真值 sha 等于此值。"},
              open(FREEZE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("frozen", _sha(GT)); return 0


def cmd_run():
    import importlib.metadata as md
    from PIL import Image, ImageStat
    if not (os.path.exists(GT) and os.path.isdir(FRAMES)):
        print("★ 真值或素材不在本机 —— 不出结论。"); return 2
    pre, m, fz = json.load(open(PRE, encoding="utf-8")), meta(), json.load(open(FREEZE, encoding="utf-8"))
    gate = {}
    gate["I3_gt_frozen"] = _sha(GT) == fz["gt_sha256"]
    vers = {p: md.version(p) for p in ("rapidocr_onnxruntime", "onnxruntime")}
    gate["I2_versions"] = vers == {"rapidocr_onnxruntime": "1.4.4", "onnxruntime": "1.30.0"}
    gt = json.load(open(GT, encoding="utf-8"))
    by_id = {it["aweme_id"]: it for it in gt["items"]}
    ords = order(pre, m)
    creator_idx = {}
    domains, determinism = {}, []
    for kw, ids in ords.items():
        rows, blanks, excluded, failed, n_text = [], [], [], 0, 0
        for i in ids:
            if n_text >= N_TARGET:
                break
            if i not in by_id:
                break                                   # 转写到此为止 ⇒ 不越过未标注的帧
            it, p = by_id[i], f"{FRAMES}/{i}/01.jpg"
            assert it["sha256"] == _sha(p), f"★ 帧 {i} 与转写时不是同一张图"
            try:
                im = Image.open(p).convert("L")
                if ImageStat.Stat(im).stddev[0] < 5:
                    excluded.append({"aweme_id": i, "why": "near_black"}); continue
            except OSError as e:
                excluded.append({"aweme_id": i, "why": f"decode:{type(e).__name__}"}); continue
            st, raw, kept = hyp_lines(p, m[i][2])
            if st == "failed":
                failed += 1; excluded.append({"aweme_id": i, "why": "ocr_failed"}); continue
            if len(determinism) < 3 * len(ords) and sum(1 for d in determinism if d["domain"] == kw) < 3:
                st2, raw2, _ = hyp_lines(p, m[i][2])
                determinism.append({"domain": kw, "aweme_id": i, "same": raw2 == raw})
            ref = "".join(it["lines"])
            rz, hz = _keep(ref, CJK), _keep("".join(kept), CJK)
            cidx = creator_idx.setdefault(m[i][1], len(creator_idx))
            if len(rz) < 2:
                blanks.append({"aweme_id": i, "creator": cidx, "hallucinated": len(hz) >= 2,
                               "hyp_zh_chars": len(hz),
                               # 冻结前补的分报(非预注册): 图上有字但小到不可辨 ⇒ 读出不一定是无中生有
                               "illegible_text_present": "illegible_text_present" in it.get("flags", [])})
                continue
            n_text += 1
            rl, hl = _keep(ref, LAT, True), _keep("".join(kept), LAT, True)
            rows.append({"aweme_id": i, "frame": f"stackA_frames/{i}/01.jpg", "sha256": it["sha256"],
                         "creator": cidx, "ref_zh_chars": len(rz), "hyp_zh_chars": len(hz),
                         "acc_zh": acc(rz, hz),
                         "acc_en": acc(rl, hl) if len(rl) >= 3 else None, "ref_en_chars": len(rl),
                         "n_ocr_lines": len(raw), "n_ocr_lines_after_watermark_filter": len(kept),
                         "flags": it.get("flags", [])})
        a = [r["acc_zh"] for r in rows]
        tot = sum(r["ref_zh_chars"] for r in rows)
        micro = (sum(r["acc_zh"] * r["ref_zh_chars"] for r in rows) / tot) if tot else None
        en = [r["acc_en"] for r in rows if r["acc_en"] is not None]
        domains[kw] = {
            "n_text_frames": len(rows), "n_blank_controls": len(blanks),
            "n_instrument_excluded": len(excluded), "n_ocr_failed": failed,
            "n_creators": len({r["creator"] for r in rows}),
            "status": "OK" if len(rows) >= N_TARGET else "INSUFFICIENT",
            "acc_zh_mean": round(statistics.mean(a), 4) if a else None,
            "acc_zh_median": round(statistics.median(a), 4) if a else None,
            "acc_zh_quartiles": [round(q, 4) for q in statistics.quantiles(a, n=4)] if len(a) > 1 else None,
            "acc_zh_min": min(a) if a else None,
            "acc_zh_micro": round(micro, 4) if micro is not None else None,
            "cer_zh_mean": round(1 - statistics.mean(a), 4) if a else None,
            "en_descriptive": {"n_frames_ref_en_ge3": len(en),
                               "acc_en_median": round(statistics.median(en), 4) if en else None},
            "hallucinated_on_blank": sum(b["hallucinated"] for b in blanks),
            "hallucinated_on_truly_blank": sum(b["hallucinated"] for b in blanks
                                               if not b["illegible_text_present"]),
            "per_frame": rows, "blank_controls": blanks, "excluded": excluded}
    gate["I1_determinism"] = bool(determinism) and all(d["same"] for d in determinism)
    gate["I4_variance"] = all(d["acc_zh_mean"] is not None and 0 < d["acc_zh_mean"] < 1
                              and len({r["acc_zh"] for r in d["per_frame"]}) > 1 for d in domains.values())
    gate["fail_rate_ok"] = all(d["n_ocr_failed"] <= 0.10 * max(1, d["n_text_frames"] + d["n_blank_controls"])
                               for d in domains.values())
    gate_ok = all(gate.values())
    pairs, overall = {}, "INSTRUMENT_GATE_FAILED"
    if gate_ok:
        rng = random.Random(SEED)
        kws = list(domains)
        if all(domains[k]["status"] == "OK" for k in kws):
            for x in range(len(kws)):
                for y in range(x + 1, len(kws)):
                    pairs[f"{kws[x]}|{kws[y]}"] = pair_verdict(
                        domains[kws[x]]["per_frame"], domains[kws[y]]["per_frame"], rng)
            vs = [p["verdict"] for p in pairs.values()]
            overall = ("TRANSFERS_ACROSS_TESTED_DOMAINS" if all(v == "TRANSFERABLE" for v in vs)
                       else "DOES_NOT_TRANSFER" if "NOT_TRANSFERABLE" in vs else "STILL_UNDETERMINED")
        else:
            overall = "STILL_UNDETERMINED"
    means = [d["cer_zh_mean"] for d in domains.values() if d["cer_zh_mean"]]
    res = {"block": "OCR_CROSS_DOMAIN_GEN1", "measured_at": "2026-10-01",
           "prereg": "tests/data/phase2/ocr_cross_domain_prereg.json",
           "annotator": "Claude_single_non_human",
           "gt_path": GT, "gt_sha256": _sha(GT), "engine_versions": vers,
           "instrument_gate": gate, "determinism_checks": determinism,
           "domains": domains, "pairs": pairs, "overall": overall,
           "max_over_min_domain_cer_ratio": round(max(means) / min(means), 2) if len(means) > 1 else None,
           "★no_transcriptions_in_repo": "本文件只有路径/sha/数字; 转写在仓外真值文件。"}
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"gate": gate, "overall": overall,
                      "domains": {k: {x: v[x] for x in ("status", "n_text_frames", "n_blank_controls",
                                                        "acc_zh_mean", "acc_zh_median", "acc_zh_micro",
                                                        "hallucinated_on_blank")} for k, v in domains.items()},
                      "pairs": {k: {x: v[x] for x in ("mean_diff", "ci90", "verdict_raw", "loco_all_same", "verdict")}
                                for k, v in pairs.items()}}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit({"sample": cmd_sample, "freeze": cmd_freeze, "run": cmd_run}[sys.argv[1] if len(sys.argv) > 1 else "run"]())
