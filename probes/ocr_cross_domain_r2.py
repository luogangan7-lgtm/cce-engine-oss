#!/usr/bin/env python3
"""OCR 跨内容域可搬性 · 第二轮(新样本) —— 预注册 tests/data/phase2/ocr_cross_domain_r2_prereg.json。

第一轮(ocr_cross_domain.py, 4 域 x30, STILL_UNDETERMINED)只用于功效估算, 不进本轮判定。
本轮: 同 4 域, 每域目标 85 张有字帧, 取 stackA_frames 的 00/01/02 三个时刻中**第一轮没看过**的帧;
一条视频可出多帧 ⇒ 区间按**视频聚类**重采样, 创作者稳健性用留一创作者。

用法:
  ocr_cross_domain_r2.py selftest  # 仪器自检(合成图读回 + 版本), 不碰样本
  ocr_cross_domain_r2.py sample    # 打印各域转写顺序(零 OCR) —— 转写前用
  ocr_cross_domain_r2.py freeze    # 真值写完后记录 sha256 → r2_gt_freeze.json(提交后再 run)
  ocr_cross_domain_r2.py run       # 跑 OCR + 判定 → tests/data/phase2/ocr_cross_domain_r2.json

★ 真值不在本仓(含屏幕上的创作者名): 仓内只放 sha/路径/数字。素材或真值缺席 ⇒ 返回 2, 不出结论。
"""
import hashlib, json, os, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
import ocr_cross_domain as R1                      # 复用: meta / 过滤器 / OCR 调用 / 1−CER / judge

VSE, FRAMES = R1.VSE, R1.FRAMES
GT = f"{VSE}/results/ocr_gt_douyin_frames_v2.json"
PRE = os.path.join(ROOT, "tests/data/phase2/ocr_cross_domain_r2_prereg.json")
FREEZE = os.path.join(ROOT, "tests/data/phase2/ocr_cross_domain_r2_gt_freeze.json")
OUT = os.path.join(ROOT, "tests/data/phase2/ocr_cross_domain_r2.json")
N_TARGET, N_MIN, N_BOOT, SEED = 85, 60, 10000, 20261002
FRAME_NAMES = ("00.jpg", "01.jpg", "02.jpg")
VERSIONS = {"rapidocr_onnxruntime": "1.4.4", "onnxruntime": "1.30.0"}
SELFTEST_STRINGS = ("今天教大家做红烧肉", "职场新人必看的三个技巧", "这台车的油耗表现")


def seen_frames(pre):
    """第一轮看过的帧: 第一轮真值里的每一帧 + 第一轮 pilot 的 01.jpg。"""
    r1 = json.load(open(R1.GT, encoding="utf-8"))
    seen = {(it["aweme_id"], os.path.basename(it["frame_path"])) for it in r1["items"]}
    return seen | {(i, "01.jpg") for i in pre["exclusions"]["round1_pilot_aweme_ids"]}


def order(pre, m):
    """每域: 全部视频 x {00,01,02} 去掉第一轮看过的帧, 按 sha256('<aweme_id>/<帧名>') 升序。"""
    seen = seen_frames(pre)
    ids = [i for i in os.listdir(FRAMES) if i in m]
    out = {}
    for kw in pre["domains"]["chosen"]:
        cand = [(i, f) for i in ids if m[i][0] == kw for f in FRAME_NAMES
                if (i, f) not in seen and os.path.exists(f"{FRAMES}/{i}/{f}")]
        out[kw] = sorted(cand, key=lambda x: hashlib.sha256(f"{x[0]}/{x[1]}".encode()).hexdigest())
    return out


def selftest():
    """I0: 合成图读回(仪器读不回已知原文 ⇒ 红) + I2 版本。不碰样本。"""
    import importlib.metadata as md, tempfile
    from ocr_quality_curve import _render
    vers = {p: md.version(p) for p in VERSIONS}
    reads = []
    with tempfile.TemporaryDirectory() as td:
        for k, s in enumerate(SELFTEST_STRINGS):
            p = os.path.join(td, f"st{k}.png")
            _render(s, "zh").save(p)
            st, rows = R1.ocr(p)
            hyp = R1._keep("".join(t for t, _ in rows), R1.CJK)
            reads.append({"ref_chars": len(s), "acc": R1.acc(s, hyp), "status": st})
    return {"I0_readback": all(r["acc"] == 1.0 for r in reads), "I2_versions": vers == VERSIONS,
            "readback": reads, "versions": vers}


def cluster_boot(rows_a, rows_b, rng, key="video"):
    """视频(或创作者)聚类重采样: 每次有放回抽聚类, 带上该聚类在样本里的全部帧; 统计量 = 帧加权均值差。"""
    import numpy as np

    def pack(rows):
        cl = {}
        for r in rows:
            s = cl.setdefault(r[key], [0.0, 0])
            s[0] += r["acc_zh"]; s[1] += 1
        return np.array([v[0] for v in cl.values()]), np.array([v[1] for v in cl.values()])

    (sa, ca), (sb, cb) = pack(rows_a), pack(rows_b)
    ia = rng.integers(0, len(sa), (N_BOOT, len(sa)))
    ib = rng.integers(0, len(sb), (N_BOOT, len(sb)))
    d = np.sort(sa[ia].sum(1) / ca[ia].sum(1) - sb[ib].sum(1) / cb[ib].sum(1))
    return float(d[int(0.05 * N_BOOT)]), float(d[int(0.95 * N_BOOT) - 1])


def pair_verdict(rows_a, rows_b, rng):
    lo, hi = cluster_boot(rows_a, rows_b, rng)
    v = R1.judge(lo, hi)
    loco = []
    for rows, side in ((rows_a, "a"), (rows_b, "b")):
        for c in sorted({r["creator"] for r in rows}):
            keep = [r for r in rows if r["creator"] != c]
            l2, h2 = cluster_boot(keep, rows_b, rng) if side == "a" else cluster_boot(rows_a, keep, rng)
            loco.append({"dropped_side": side, "creator_idx": c, "ci90": [round(l2, 4), round(h2, 4)],
                         "verdict": R1.judge(l2, h2)})
    stable = all(x["verdict"] == v for x in loco)
    cl, ch = cluster_boot(rows_a, rows_b, rng, key="creator")
    mean = lambda rows: sum(r["acc_zh"] for r in rows) / len(rows)
    return {"mean_diff": round(mean(rows_a) - mean(rows_b), 4),
            "ci90": [round(lo, 4), round(hi, 4)], "verdict_raw": v,
            "loco_all_same": stable, "verdict": v if stable else "INCONCLUSIVE", "loco": loco,
            "creator_cluster_ci90_descriptive": [round(cl, 4), round(ch, 4)]}


def overall(vs):
    return ("TRANSFERS_ACROSS_TESTED_DOMAINS" if vs and all(v == "TRANSFERABLE" for v in vs)
            else "DOES_NOT_TRANSFER" if "NOT_TRANSFERABLE" in vs else "STILL_UNDETERMINED")


def measure(flt, ords, by_key, m, cache):
    from PIL import Image, ImageStat
    creator_idx, domains = {}, {}
    for kw, cands in ords.items():
        rows, blanks, excluded, failed = [], [], [], 0
        for i, f in cands:
            if len(rows) >= N_TARGET:
                break
            if (i, f) not in by_key:
                break                                   # 转写到此为止 ⇒ 不越过未标注的帧
            it, p = by_key[(i, f)], f"{FRAMES}/{i}/{f}"
            assert it["sha256"] == R1._sha(p), f"★ 帧 {i}/{f} 与转写时不是同一张图"
            try:
                if ImageStat.Stat(Image.open(p).convert("L")).stddev[0] < 5:
                    excluded.append({"aweme_id": i, "frame": f, "why": "near_black"}); continue
            except OSError as e:
                excluded.append({"aweme_id": i, "frame": f, "why": f"decode:{type(e).__name__}"}); continue
            if p not in cache:
                cache[p] = R1.ocr(p)
            st, raw = cache[p]
            if st == "failed":
                failed += 1; excluded.append({"aweme_id": i, "frame": f, "why": "ocr_failed"}); continue
            kept = flt(raw, m[i][2])
            ref = "".join(it["lines"])
            rz, hz = R1._keep(ref, R1.CJK), R1._keep("".join(kept), R1.CJK)
            cidx = creator_idx.setdefault(m[i][1], len(creator_idx))
            if len(rz) < 2:
                blanks.append({"aweme_id": i, "frame": f, "creator": cidx, "hallucinated": len(hz) >= 2,
                               "hyp_zh_chars": len(hz),
                               "illegible_text_present": "illegible_text_present" in it.get("flags", [])})
                continue
            rl, hl = R1._keep(ref, R1.LAT, True), R1._keep("".join(kept), R1.LAT, True)
            rows.append({"aweme_id": i, "frame": f"stackA_frames/{i}/{f}", "sha256": it["sha256"],
                         "video": i, "creator": cidx, "ref_zh_chars": len(rz), "hyp_zh_chars": len(hz),
                         "acc_zh": R1.acc(rz, hz),
                         "acc_en": R1.acc(rl, hl) if len(rl) >= 3 else None, "ref_en_chars": len(rl),
                         "n_ocr_lines": len(raw), "n_ocr_lines_after_watermark_filter": len(kept),
                         "flags": it.get("flags", [])})
        a = [r["acc_zh"] for r in rows]
        tot = sum(r["ref_zh_chars"] for r in rows)
        n = len(rows)
        domains[kw] = {
            "n_text_frames": n, "n_videos": len({r["video"] for r in rows}),
            "n_blank_controls": len(blanks), "n_instrument_excluded": len(excluded), "n_ocr_failed": failed,
            "n_creators": len({r["creator"] for r in rows}), "n_candidates": len(cands),
            "status": "OK" if n >= N_TARGET else "OK_REDUCED" if n >= N_MIN else "INSUFFICIENT",
            "acc_zh_mean": round(statistics.mean(a), 4) if a else None,
            "acc_zh_median": round(statistics.median(a), 4) if a else None,
            "acc_zh_quartiles": [round(q, 4) for q in statistics.quantiles(a, n=4)] if n > 1 else None,
            "acc_zh_min": min(a) if a else None,
            "acc_zh_micro": round(sum(r["acc_zh"] * r["ref_zh_chars"] for r in rows) / tot, 4) if tot else None,
            "by_frame_position": {f: round(statistics.mean(x), 4) if x else None for f in FRAME_NAMES
                                  for x in [[r["acc_zh"] for r in rows if r["frame"].endswith(f)]]},
            "hallucinated_on_blank": sum(b["hallucinated"] for b in blanks),
            "hallucinated_on_truly_blank": sum(b["hallucinated"] for b in blanks
                                               if not b["illegible_text_present"]),
            "per_frame": rows, "blank_controls": blanks, "excluded": excluded}
    return domains


IMPL_FIX = ("2026-10-01 转写完成后、冻结真值与任何 OCR 之前修正(只看到了逐域有字帧计数, 游戏解说 51 < 60): "
            "预注册提交的代码在任一域 INSUFFICIENT 时整体不算任何对, 连 H2(只涉及另三域)也一并判不了 —— "
            "与预注册文字不符(H2 只由那三对决定; H1 的「>=1 对不可搬 ⇒ DOES_NOT_TRANSFER」先于「其余含 INSUFFICIENT」)。"
            "改为: 只在 status != INSUFFICIENT 的域之间算对; H1 有不可搬对 ⇒ DOES_NOT_TRANSFER, 否则有域 INSUFFICIENT ⇒ "
            "STILL_UNDETERMINED; H2 三域都够才判。δ/区间/留一创作者/阈值均未动。")


def judge_all(domains, pre, rng):
    pairs = {}
    kws = [k for k in domains if domains[k]["status"] != "INSUFFICIENT"]
    for x in range(len(kws)):
        for y in range(x + 1, len(kws)):
            pairs[f"{kws[x]}|{kws[y]}"] = pair_verdict(domains[kws[x]]["per_frame"], domains[kws[y]]["per_frame"], rng)
    vs = [p["verdict"] for p in pairs.values()]
    h1 = overall(vs)
    if h1 != "DOES_NOT_TRANSFER" and len(kws) < len(domains):
        h1 = "STILL_UNDETERMINED"
    sub = set(pre["criterion"]["H2_subset"]["domains"])
    h2 = (overall([p["verdict"] for k, p in pairs.items() if set(k.split("|")) <= sub])
          if sub <= set(kws) else "STILL_UNDETERMINED")
    return pairs, h1, h2


def cmd_selftest():
    print(json.dumps(selftest(), ensure_ascii=False, indent=1)); return 0


def cmd_sample():
    pre, m = json.load(open(PRE, encoding="utf-8")), R1.meta()
    for kw, cands in order(pre, m).items():
        print(f"## {kw} n_candidates={len(cands)} videos={len({i for i, _ in cands})} "
              f"creators={len({m[i][1] for i, _ in cands})}")
        for i, f in cands:
            print(f"{kw}\t{i}\t{f}\t{FRAMES}/{i}/{f}")
    return 0


def cmd_freeze():
    if not os.path.exists(GT):
        print(f"★ 真值不在本机 {GT}"); return 2
    json.dump({"block": "OCR_CROSS_DOMAIN_R2_GT_FREEZE", "frozen_at": "2026-10-01", "gt_path": GT,
               "gt_sha256": R1._sha(GT),
               "★order": "本文件提交时 OCR 尚未在第二轮样本上运行; run 会校验真值 sha 等于此值。"},
              open(FREEZE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("frozen", R1._sha(GT)); return 0


def cmd_run():
    import numpy as np
    if not (os.path.exists(GT) and os.path.isdir(FRAMES)):
        print("★ 真值或素材不在本机 —— 不出结论。"); return 2
    pre, m, fz = json.load(open(PRE, encoding="utf-8")), R1.meta(), json.load(open(FREEZE, encoding="utf-8"))
    st = selftest()
    gate = {"I0_readback": st["I0_readback"], "I2_versions": st["I2_versions"],
            "I3_gt_frozen": R1._sha(GT) == fz["gt_sha256"]}
    gt = json.load(open(GT, encoding="utf-8"))
    by_key = {(it["aweme_id"], os.path.basename(it["frame_path"])): it for it in gt["items"]}
    gate["I5_no_round1_frame"] = not (set(by_key) & seen_frames(pre))
    ords = order(pre, m)
    cache, determinism = {}, []
    for kw, cands in ords.items():                       # I1: 每域前 3 帧连跑两次
        for i, f in [x for x in cands if x in by_key][:3]:
            p = f"{FRAMES}/{i}/{f}"
            cache[p] = R1.ocr(p)
            determinism.append({"domain": kw, "aweme_id": i, "frame": f, "same": R1.ocr(p) == cache[p]})
    gate["I1_determinism"] = bool(determinism) and all(d["same"] for d in determinism)
    results = {name: measure(flt, ords, by_key, m, cache)
               for name, flt in (("v2_anchor", R1.keep_v2), ("v1_prereg_r1", R1.keep_v1))}
    d2 = results["v2_anchor"]
    gate["I4_variance"] = all(d["acc_zh_mean"] is not None and 0 < d["acc_zh_mean"] < 1
                              and len({r["acc_zh"] for r in d["per_frame"]}) > 1 for d in d2.values())
    gate["fail_rate_ok"] = all(d["n_ocr_failed"] <= 0.10 * max(1, d["n_text_frames"] + d["n_blank_controls"])
                               for d in d2.values())
    gate_ok = all(gate.values())
    out = {}
    for name, domains in results.items():
        pairs, ov, h2 = {}, "INSTRUMENT_GATE_FAILED", "INSTRUMENT_GATE_FAILED"
        if gate_ok:
            pairs, ov, h2 = judge_all(domains, pre, np.random.default_rng(SEED))
        out[name] = {"role": "primary" if name == "v2_anchor" else "descriptive_only",
                     "domains": domains, "pairs": pairs, "overall": ov, "H2_subset": h2}
    res = {"block": "OCR_CROSS_DOMAIN_R2", "measured_at": "2026-10-01",
           "prereg": "tests/data/phase2/ocr_cross_domain_r2_prereg.json",
           "annotator": "Claude_single_non_human", "gt_path": GT, "gt_sha256": R1._sha(GT),
           "engine_versions": st["versions"], "instrument_gate": gate, "selftest_readback": st["readback"],
           "determinism_checks": determinism,
           "overall": out["v2_anchor"]["overall"], "H2_subset": out["v2_anchor"]["H2_subset"],
           "by_filter": out,
           "★round1_not_pooled": "第一轮数据只用于功效估算, 不并入本轮判定。",
           "★implementation_fix_before_ocr": IMPL_FIX,
           "★no_transcriptions_in_repo": "本文件只有路径/sha/数字; 转写在仓外真值文件。"}
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    o = out["v2_anchor"]
    print(json.dumps({"gate": gate, "overall": res["overall"], "H2_subset": res["H2_subset"],
                      "v1_overall_descriptive": out["v1_prereg_r1"]["overall"],
                      "domains": {k: {x: v[x] for x in ("status", "n_text_frames", "n_videos", "n_creators",
                                                        "n_blank_controls", "acc_zh_mean", "acc_zh_median",
                                                        "acc_zh_micro", "by_frame_position",
                                                        "hallucinated_on_blank", "hallucinated_on_truly_blank")}
                                  for k, v in o["domains"].items()},
                      "pairs": {k: {x: v[x] for x in ("mean_diff", "ci90", "verdict_raw", "loco_all_same",
                                                      "verdict", "creator_cluster_ci90_descriptive")}
                                for k, v in o["pairs"].items()}}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    rc = {"selftest": cmd_selftest, "sample": cmd_sample, "freeze": cmd_freeze,
          "run": cmd_run}[sys.argv[1] if len(sys.argv) > 1 else "run"]()
    sys.stdout.flush()
    os._exit(rc)  # onnxruntime 在解释器退出析构时 abort, 产物已落盘
