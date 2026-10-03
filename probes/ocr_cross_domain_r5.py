#!/usr/bin/env python3
"""OCR 跨内容域 · 第五轮(过滤器确证 + 跨域) —— 预注册 tests/data/phase2/ocr_cross_domain_r5_prereg.json。

第四轮主过滤器 keep_v3 在新版式上吃字(I6 不过), 事后写的 keep_v3b 只在已看帧上探索过。本轮把 keep_v3b **原样钉死**
(函数源码 sha 写进预注册), 在 r1–r4 都没看过的帧上: 先确证过滤器(H_filter = 逐格 I6 前置仪器闸), 闸过了再判
H_density / H_domain_given_density(判据沿用第四轮)。

帧源(都不联网):
  A. stackA_frames 里 r1–r4 都没看过的帧(密度沿用第四轮冻结的 r4_density.json)
  B. 本机 mp4 的新时刻帧: 时长 d 的 {1,3,5,7}/8 处, 448px, 与 stackA 同参数(scale=448:-2, q:v 4) → VSE/assets/ocr_r5_frames

用法:
  ocr_cross_domain_r5.py extract    # B 源抽帧(零 OCR、零真值)
  ocr_cross_domain_r5.py density    # B 源帧 Vision 密度 → r5_density.json(零 OCR、零真值)
  ocr_cross_domain_r5.py inventory  # 未看帧按 域 x 档 计数(只用机器密度)
  ocr_cross_domain_r5.py seencheck  # 已看帧(r1–r4 真值)上 keep_v3 / keep_v3b 的 I6 与同框前缀自检 —— 仪器自检, 不是证据
  ocr_cross_domain_r5.py power      # 功效估算(只用已看帧)
  ocr_cross_domain_r5.py sample     # 打印各格转写顺序(零 OCR)
  ocr_cross_domain_r5.py freeze     # 真值写完后记录 sha256 → r5_gt_freeze.json(提交后再 run)
  ocr_cross_domain_r5.py run        # 跑 OCR + 闸 + 判定 → tests/data/phase2/ocr_cross_domain_r5.json

★ 真值不在本仓(含屏幕上的创作者名): 仓内只放 sha/路径/数字。素材或真值缺席 ⇒ 返回 2, 不出结论。
"""
import collections, glob, hashlib, inspect, json, os, statistics, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
import ocr_cross_domain as R1                      # meta / OCR 调用 / 1−CER / judge
import ocr_cross_domain_r2 as R2                   # 视频聚类区间 / 留一创作者 / selftest
import ocr_cross_domain_r3 as R3                   # keep_v3(keep_v3b 的内层)
import ocr_cross_domain_r4 as R4                   # 密度仪器 / keep_v3b / 判定(judge_all)

VSE, FRAMES = R1.VSE, R1.FRAMES
NEW = f"{VSE}/assets/ocr_r5_frames"
GT = f"{VSE}/results/ocr_gt_douyin_frames_v5.json"
PH2 = os.path.join(ROOT, "tests/data/phase2")
PRE = os.path.join(PH2, "ocr_cross_domain_r5_prereg.json")
DENS = os.path.join(PH2, "ocr_cross_domain_r5_density.json")
SEEN = os.path.join(PH2, "ocr_cross_domain_r5_seencheck.json")
FREEZE = os.path.join(PH2, "ocr_cross_domain_r5_gt_freeze.json")
OUT = os.path.join(PH2, "ocr_cross_domain_r5.json")
OCR_CACHE = os.path.join(VSE, "results/_ocr_r5_seen_cache.json")   # 已看帧的 OCR 原始框(仓外, 含屏幕文字)
SEED, I6_MAX, TIERS = 20261005, 0.02, R4.TIERS
EIGHTHS = (1, 3, 5, 7)
NEW_NAMES = tuple(f"e{k}.jpg" for k in EIGHTHS)
FILTER_FUNCS = (R4.keep_v3b, R3.keep_v3, R3._overlap_x, R1._core)


def filter_sha():
    """被钉死的过滤器 = keep_v3b 及其调用链的函数源码 + 两条正则 + 字符类; 任何一处改动 sha 就变(⇒ 是 r6 不是 r5)。"""
    src = "".join(inspect.getsource(f) for f in FILTER_FUNCS)
    src += R3.WM_ID.pattern + R3.WM_ID_SPAN.pattern + R1.CJK.pattern + R1.LAT.pattern
    return hashlib.sha256(src.encode()).hexdigest()


def metric_sha():
    from ocr_accuracy_real_zh import _cer
    return hashlib.sha256("".join(inspect.getsource(f) for f in (_cer, R1.acc, R1._keep)).encode()).hexdigest()


def fpath(i, f):
    return f"{FRAMES}/{i}/{f}" if f in R2.FRAME_NAMES else f"{NEW}/{i}/{f}"


def flabel(i, f):
    return f"stackA_frames/{i}/{f}" if f in R2.FRAME_NAMES else f"ocr_r5_frames/{i}/{f}"


# ---------- B 源: 本机 mp4 新时刻抽帧 ----------
def mp4s(m):
    """aweme_id → 本机 mp4(有抖音 meta 的; 同 id 多份取排序第一份)。"""
    by = {}
    for p in sorted(glob.glob(f"{VSE}/assets/**/*.mp4", recursive=True)):
        i = os.path.splitext(os.path.basename(p))[0]
        if i in m and os.path.getsize(p) > 10000:
            by.setdefault(i, p)
    return by


def _grab(src, t, dst):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1",
                    "-vf", "scale=448:-2", "-q:v", "4", dst], check=True)


def _extract_one(i, p):
    try:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                   capture_output=True, text=True, check=True).stdout.strip())
        os.makedirs(f"{NEW}/{i}", exist_ok=True)
        ts = {}
        for k, n in zip(EIGHTHS, NEW_NAMES):
            ts[n] = round(dur * k / 8, 3)
            _grab(p, ts[n], f"{NEW}/{i}/{n}")
            if not os.path.exists(f"{NEW}/{i}/{n}") or os.path.getsize(f"{NEW}/{i}/{n}") < 2000:
                return i, {"mp4": os.path.relpath(p, VSE), "error": f"empty_frame:{n}"}
        return i, {"mp4": os.path.relpath(p, VSE), "duration_s": round(dur, 3), "t_s": ts}
    except (subprocess.CalledProcessError, ValueError) as e:
        return i, {"mp4": os.path.relpath(p, VSE), "error": type(e).__name__}


def cmd_extract():
    from concurrent.futures import ThreadPoolExecutor
    m = R1.meta()
    src = mp4s(m)
    with ThreadPoolExecutor(8) as ex:
        res = dict(ex.map(lambda kv: _extract_one(*kv), sorted(src.items())))
    # X0 抽帧确定性: 排序前 20 条视频的全部新时刻重抽一遍到临时目录, sha 必须逐帧相同
    import tempfile
    same, n = 0, 0
    with tempfile.TemporaryDirectory() as td:
        for i in sorted(k for k, v in res.items() if "error" not in v)[:20]:
            for nm, t in res[i]["t_s"].items():
                q = os.path.join(td, f"{i}_{nm}")
                _grab(os.path.join(VSE, res[i]["mp4"]), t, q)
                n += 1; same += R1._sha(q) == R1._sha(f"{NEW}/{i}/{nm}")
    json.dump({"videos": res, "X0_reextract_identical": [same, n]}, open(os.path.join(NEW, "_extract.json"), "w"),
              ensure_ascii=False, indent=0)
    print("videos", len(res), "errors", sum("error" in v for v in res.values()), "X0", same, "/", n); return 0


def cmd_density():
    ext = json.load(open(os.path.join(NEW, "_extract.json"), encoding="utf-8"))
    keys = [f"{i}/{n}" for i, v in sorted(ext["videos"].items()) if "error" not in v for n in NEW_NAMES]
    runs = [R4._vision([f"{NEW}/{k}" for k in keys]) for _ in range(2)]        # D2: 两次独立运行逐帧比
    frames, errors, flips = {}, [], 0
    for k, r, r2 in zip(keys, *runs):
        if "error" in r or "error" in r2:
            errors.append({"frame": k, "why": r.get("error") or r2.get("error")}); continue
        d, d2 = R4.density(r["boxes"]), R4.density(r2["boxes"])
        flips += d != d2
        frames[k] = list(d)
    json.dump({"block": "OCR_CROSS_DOMAIN_R5_DENSITY", "computed_at": "2026-10-03",
               "instrument": "同第四轮: macOS Vision VNRecognizeTextRequest rev3 accurate zh-Hans+en-US, 只取框几何与每框非空白字符数",
               "swift_source_sha256": R1._sha(R4.SWIFT), "os": __import__("platform").mac_ver()[0],
               "scope": "只含 B 源(本机 mp4 新时刻)帧; A 源(stackA 未看帧)沿用第四轮冻结的 ocr_cross_domain_r4_density.json",
               "extraction": {"rule": "时长 d 的 {1,3,5,7}/8 处各 1 帧, ffmpeg -ss t -frames:v 1 -vf scale=448:-2 -q:v 4(同 stackA 参数)",
                              "ffmpeg": subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.split("\n")[0],
                              "X0_reextract_identical": ext["X0_reextract_identical"],
                              "videos": ext["videos"]},
               "frame_sha256": {k: R1._sha(f"{NEW}/{k}") for k in frames},
               "D2_two_runs_differ": flips,
               "★independence": "不调用被测 OCR(RapidOCR), 不读真值; 识别出的文字不落盘。",
               "fields": "frame -> [D 去水印后估计字数, 去水印后框数, 水印块框数]",
               "n_frames": len(frames), "errors": errors, "frames": frames},
              open(DENS, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("density", len(frames), "errors", len(errors), "D2 flips", flips); return 0


# ---------- 候选 / 盘点 ----------
def seen_frames():
    """r1–r4 看过的帧: 四份真值的每一帧 + 第一轮 pilot 的 01.jpg。"""
    g4 = json.load(open(R4.GT, encoding="utf-8"))
    return R4.seen_frames() | {(it["aweme_id"], os.path.basename(it["frame_path"])) for it in g4["items"]}


def all_density():
    """(aweme_id, 帧名) → D。A 源 = 第四轮冻结文件; B 源 = 本轮冻结文件。"""
    out = {}
    for k, v in json.load(open(R4.DENS, encoding="utf-8"))["frames"].items():
        i, f = k.split("/"); out[(i, f)] = v[0]
    for k, v in json.load(open(DENS, encoding="utf-8"))["frames"].items():
        i, f = k.split("/"); out[(i, f)] = v[0]
    return out


def candidates(m, dens, edges, seen):
    """(域, 档) → 未看过的候选帧(A+B 源), 按 sha256('<aweme_id>/<帧名>') 升序。"""
    out = {}
    for (i, f), d in dens.items():
        if i in m and (i, f) not in seen:
            out.setdefault((m[i][0], R4.tier(d, edges)), []).append((i, f))
    return {c: sorted(v, key=lambda x: hashlib.sha256(f"{x[0]}/{x[1]}".encode()).hexdigest()) for c, v in out.items()}


def inventory(m, cc):
    inv = {}
    for (d, t), v in sorted(cc.items()):
        for src, sel in (("A_stackA", [x for x in v if x[1] in R2.FRAME_NAMES]),
                         ("B_new_moment", [x for x in v if x[1] not in R2.FRAME_NAMES]), ("all", v)):
            inv.setdefault(d, {}).setdefault(t, {})[src] = [len(sel), len({i for i, _ in sel}),
                                                            len({m[i][1] for i, _ in sel})]
    return inv


def cmd_inventory():
    m = R1.meta()
    cc = candidates(m, all_density(), [30], seen_frames())
    inv = inventory(m, cc)
    for d, x in sorted(inv.items(), key=lambda kv: -kv[1].get("DENSE", {}).get("all", [0])[0]):
        print(d, " | ".join(f"{t} " + " ".join(f"{s}={x[t][s]}" for s in x[t]) for t in TIERS if t in x))
    print(json.dumps(inv, ensure_ascii=False)); return 0


# ---------- 已看帧自检(仪器, 不是证据) ----------
def _seen_items():
    out = []
    for rnd, g in ((1, R1.GT), (2, R2.GT), (3, R3.GT), (4, R4.GT)):
        for it in json.load(open(g, encoding="utf-8"))["items"]:
            out.append((rnd, it))
    return out


def _ocr_cached(paths):
    cache = json.load(open(OCR_CACHE, encoding="utf-8")) if os.path.exists(OCR_CACHE) else {}
    todo = [p for p in paths if p not in cache]
    for k, p in enumerate(todo):
        st, rows = R1.ocr(p)
        cache[p] = [st, [[t, b] for t, b in rows]]
        if k % 50 == 49:
            json.dump(cache, open(OCR_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(cache, open(OCR_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return {p: (cache[p][0], [(t, tuple(b) if b else None) for t, b in cache[p][1]]) for p in paths}


def prefix_boxes(rows):
    """同框前缀: 锚框(WM_ID)里「音号」之前还有 >=1 个核心字 —— 第四轮 I6 不过的版式。"""
    n = 0
    for t, _ in rows:
        mm = R3.WM_ID.search(t)
        if mm:
            k = max(0, mm.start() - (1 if t[mm.start():mm.start() + 2] == "音号" else 0))
            n += len(R1._core(t[:k])) >= 1
    return n


def cmd_seencheck():
    m = R1.meta()
    dens = {tuple(k.split("/")): v[0] for k, v in json.load(open(R4.DENS, encoding="utf-8"))["frames"].items()}
    items = _seen_items()
    ocr = _ocr_cached(sorted({it["frame_path"] for _, it in items}))
    flt = {"no_filter": lambda rows, _n: [t for t, _ in rows], "keep_v3": R3.keep_v3, "keep_v3b": R4.keep_v3b}
    per, frames = collections.defaultdict(list), []
    for rnd, it in items:
        st, raw = ocr[it["frame_path"]]
        ref = R1._keep("".join(it["lines"]), R1.CJK)
        if st == "failed" or len(ref) < 2:
            continue
        i, f = it["aweme_id"], os.path.basename(it["frame_path"])
        acc = {k: R1.acc(ref, R1._keep("".join(fn(raw, m[i][2])), R1.CJK)) for k, fn in flt.items()}
        row = {"round": rnd, "domain": m[i][0], "tier": R4.tier(dens[(i, f)], [30]), "video": i, "creator": m[i][1],
               "acc": acc, "prefix_boxes": prefix_boxes(raw)}
        frames.append(row)
        per[(rnd, m[i][0], row["tier"])].append(row)
    cells = {}
    for (rnd, d, t), rows in sorted(per.items()):
        loss = lambda k: [r["acc"]["no_filter"] - r["acc"][k] for r in rows]
        cells[f"r{rnd}|{d}|{t}"] = {
            "n": len(rows), "I6_keep_v3": round(statistics.mean(loss("keep_v3")), 4),
            "I6_keep_v3b": round(statistics.mean(loss("keep_v3b")), 4),
            "max_frame_loss_keep_v3b": round(max(loss("keep_v3b")), 4),
            "n_frames_loss_gt_0.10_keep_v3b": sum(x > 0.10 for x in loss("keep_v3b")),
            "n_frames_with_prefix_box": sum(r["prefix_boxes"] > 0 for r in rows)}
    pre = [r for r in frames if r["prefix_boxes"]]
    summary = {
        "block": "OCR_CROSS_DOMAIN_R5_SEENCHECK", "computed_at": "2026-10-03",
        "role": "仪器自检 —— 只在 r1–r4 **已看过**的帧上(真值已冻结)看 keep_v3b 的行为, 不是 H_filter 的证据(r4 帧是 keep_v3b 的设计集)",
        "filter_source_sha256": filter_sha(), "n_text_frames": len(frames),
        "I6_max_over_cells": {"keep_v3": max(c["I6_keep_v3"] for c in cells.values()),
                              "keep_v3b": max(c["I6_keep_v3b"] for c in cells.values())},
        "cells_over_I6_max": {"keep_v3": sorted(k for k, c in cells.items() if c["I6_keep_v3"] > I6_MAX),
                              "keep_v3b": sorted(k for k, c in cells.items() if c["I6_keep_v3b"] > I6_MAX)},
        "same_box_prefix_frames": {
            "n": len(pre),
            "mean_loss_keep_v3": round(statistics.mean(r["acc"]["no_filter"] - r["acc"]["keep_v3"] for r in pre), 4) if pre else None,
            "mean_loss_keep_v3b": round(statistics.mean(r["acc"]["no_filter"] - r["acc"]["keep_v3b"] for r in pre), 4) if pre else None,
            "by_round": dict(collections.Counter(f"r{r['round']}" for r in pre))},
        "frames_loss_gt_0.10_keep_v3b": len([r for r in frames if r["acc"]["no_filter"] - r["acc"]["keep_v3b"] > 0.10]),
        "cells": cells}
    json.dump(summary, open(SEEN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(frames, open(os.path.join(VSE, "results/_ocr_r5_seen_frames.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(json.dumps({k: v for k, v in summary.items() if k != "cells"}, ensure_ascii=False, indent=1)); return 0


# ---------- 功效(只用已看帧) ----------
def cmd_power():
    """零假设总体 = r1–r4 已看帧中非游戏域的逐帧 keep_v3b 读数(按档分), 按视频聚类抽到本轮预计 n, 区间 2000 次重采样,
    200 次模拟; 不含留一创作者(只会更难判)。另: 已看帧逐帧过滤损失按格 n 重采样 ⇒ 单格 I6 > 0.02 的概率。"""
    import numpy as np
    pre = json.load(open(PRE, encoding="utf-8"))
    fr = [r for r in json.load(open(os.path.join(VSE, "results/_ocr_r5_seen_frames.json"), encoding="utf-8"))
          if r["domain"] != "游戏解说"]
    exp_n = pre["power_from_seen_frames"]["expected_n_per_cell"]
    rng = np.random.default_rng(SEED)
    R2.N_BOOT = 2000
    by_t = {t: collections.defaultdict(list) for t in TIERS}
    for r in fr:
        by_t[r["tier"]][r["video"]].append(r["acc"]["keep_v3b"])

    def draw(t, n):
        vids = list(by_t[t]); rows = []
        while len(rows) < n:
            v = vids[rng.integers(len(vids))]
            rows += [{"video": f"{v}#{len(rows)}", "creator": 0, "acc_zh": a} for a in by_t[t][v]]
        return rows[:n]

    def p_transfer(t, na, nb, sims=200):
        k = sum(R1.judge(*R2.cluster_boot(draw(t, na), draw(t, nb), rng)) == "TRANSFERABLE" for _ in range(sims))
        return [k, sims, round(k / sims, 2)]

    out = {}
    for t in TIERS:
        cs = [c for c in exp_n if c.endswith("|" + t)]
        for x in range(len(cs)):
            for y in range(x + 1, len(cs)):
                out[f"{t}: {exp_n[cs[x]]} v {exp_n[cs[y]]}"] = p_transfer(t, exp_n[cs[x]], exp_n[cs[y]])
    ns = sum(v for c, v in exp_n.items() if c.endswith("|SPARSE")), sum(v for c, v in exp_n.items() if c.endswith("|DENSE"))
    vs = collections.Counter(R1.judge(*R2.cluster_boot(draw("SPARSE", ns[0]), draw("DENSE", ns[1]), rng)) for _ in range(200))
    out[f"cross_tier {ns[0]} v {ns[1]}"] = dict(vs)
    loss = np.array([r["acc"]["no_filter"] - r["acc"]["keep_v3b"] for r in fr])
    i6 = {n: round(float((loss[rng.integers(0, len(loss), (20000, n))].mean(1) > I6_MAX).mean()), 4) for n in (20, 30, 45)}
    print(json.dumps({"pair_TRANSFERABLE_prob": out, "P_cell_I6_over_0.02_by_n": i6,
                      "seen_loss_frames": [int((loss > 0).sum()), len(loss)]}, ensure_ascii=False, indent=1)); return 0


# ---------- 选域 / 抽样 ----------
def plan(pre=None):
    pre = pre or json.load(open(PRE, encoding="utf-8"))
    m = R1.meta()
    cc = candidates(m, all_density(), pre["density"]["tier_edges"], seen_frames())
    chosen, eligible = R4.choose_domains(cc, pre["domains"]["selection_rule"])
    return m, {f"{d}|{t}": cc.get((d, t), []) for d in chosen for t in TIERS}, chosen, eligible


def cmd_sample():
    m, cl, chosen, eligible = plan()
    print("eligible", eligible, "chosen", chosen)
    for c, cands in cl.items():
        print(f"## {c} n_candidates={len(cands)} videos={len({i for i, _ in cands})} "
              f"creators={len({m[i][1] for i, _ in cands})}")
        for i, f in cands:
            print(f"{c}\t{i}\t{f}\t{fpath(i, f)}")
    return 0


def cmd_freeze():
    if not os.path.exists(GT):
        print(f"★ 真值不在本机 {GT}"); return 2
    json.dump({"block": "OCR_CROSS_DOMAIN_R5_GT_FREEZE", "frozen_at": "2026-10-03", "gt_path": GT,
               "gt_sha256": R1._sha(GT),
               "★order": "本文件提交时 OCR 尚未在第五轮样本上运行; run 会校验真值 sha 等于此值。"},
              open(FREEZE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("frozen", R1._sha(GT)); return 0


# ---------- 测量 ----------
def measure(flt, cl, by_key, m, cache, n_target, n_min):
    """同 R2.measure(停止规则/有字判定/无中生有), 只把帧路径换成 A/B 两源, 并逐帧记同框前缀框数。"""
    from PIL import Image, ImageStat
    creator_idx, cells, sv = {}, {}, {i for i, _ in seen_frames()}
    for c, cands in cl.items():
        rows, blanks, excluded, failed = [], [], [], 0
        for i, f in cands:
            if len(rows) >= n_target or (i, f) not in by_key:
                break                                   # 够数 / 转写到此为止 ⇒ 不越过未标注的帧
            it, p = by_key[(i, f)], fpath(i, f)
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
                               "illegible_text_present": "illegible_text_present" in it.get("flags", [])})
                continue
            rows.append({"aweme_id": i, "frame": flabel(i, f), "sha256": it["sha256"], "video": i, "creator": cidx,
                         "source": "A" if f in R2.FRAME_NAMES else "B", "ref_zh_chars": len(rz),
                         "hyp_zh_chars": len(hz), "acc_zh": R1.acc(rz, hz), "n_ocr_lines": len(raw),
                         "n_ocr_lines_after_watermark_filter": len(kept), "n_anchor_prefix_boxes": prefix_boxes(raw),
                         "video_seen_r1_r4": i in sv, "flags": it.get("flags", [])})
        a, n = [r["acc_zh"] for r in rows], len(rows)
        cells[c] = {
            "n_text_frames": n, "n_videos": len({r["video"] for r in rows}),
            "n_creators": len({r["creator"] for r in rows}), "n_candidates": len(cands),
            "n_blank_controls": len(blanks), "n_instrument_excluded": len(excluded), "n_ocr_failed": failed,
            "n_source_B": sum(r["source"] == "B" for r in rows),
            "n_video_seen_r1_r4": sum(r["video_seen_r1_r4"] for r in rows),
            "status": "OK" if n >= n_target else "OK_REDUCED" if n >= n_min else "INSUFFICIENT",
            "acc_zh_mean": round(statistics.mean(a), 4) if a else None,
            "acc_zh_median": round(statistics.median(a), 4) if a else None,
            "acc_zh_quartiles": [round(q, 4) for q in statistics.quantiles(a, n=4)] if n > 1 else None,
            "acc_zh_min": min(a) if a else None,
            "hallucinated_on_blank": sum(b["hallucinated"] for b in blanks),
            "hallucinated_on_truly_blank": sum(b["hallucinated"] for b in blanks if not b["illegible_text_present"]),
            "per_frame": rows, "blank_controls": blanks, "excluded": excluded}
    return cells


def cmd_run():
    import numpy as np
    if not (os.path.exists(GT) and os.path.isdir(FRAMES) and os.path.isdir(NEW)):
        print("★ 真值或素材不在本机 —— 不出结论。"); return 2
    pre, fz = json.load(open(PRE, encoding="utf-8")), json.load(open(FREEZE, encoding="utf-8"))
    m, cl, chosen, _ = plan(pre)
    st, ds = R2.selftest(), R4.density_selftest()
    dB = json.load(open(DENS, encoding="utf-8"))
    gate = {"I0_readback": st["I0_readback"], "I2_versions": st["I2_versions"],
            "I3_gt_frozen": R1._sha(GT) == fz["gt_sha256"],
            "F0_filter_source_pinned": filter_sha() == pre["filter"]["source_sha256"],
            "M0_metric_source_pinned": metric_sha() == pre["metric"]["source_sha256"],
            "D0_density_monotone": ds["D0_monotone"], "D1_density_watermark_excluded": ds["D1_watermark_excluded"],
            "D2_density_deterministic": ds["D2_deterministic"],
            "D3_density_files_frozen": R1._sha(R4.DENS) == pre["density"]["r4_density_file_sha256"]
            and R1._sha(DENS) == pre["density"]["r5_density_file_sha256"],
            "D4_domains_as_preregistered": chosen == pre["domains"]["chosen"]}
    gt = json.load(open(GT, encoding="utf-8"))
    by_key = {(it["aweme_id"], os.path.basename(it["frame_path"])): it for it in gt["items"]}
    gate["I5_no_seen_frame"] = not (set(by_key) & seen_frames())
    gate["X1_new_frames_unchanged"] = all(R1._sha(fpath(i, f)) == dB["frame_sha256"][f"{i}/{f}"]
                                          for i, f in by_key if f not in R2.FRAME_NAMES)
    cache, determinism = {}, []
    for c, cands in cl.items():                          # I1: 每格首帧连跑两次
        for i, f in [x for x in cands if x in by_key][:1]:
            p = fpath(i, f)
            cache[p] = R1.ocr(p)
            determinism.append({"cell": c, "aweme_id": i, "frame": f, "same": R1.ocr(p) == cache[p]})
    gate["I1_determinism"] = bool(determinism) and all(d["same"] for d in determinism)
    nt, nm = pre["sampling"]["n_target_per_cell"], pre["sampling"]["n_min_per_cell"]
    main = measure(R4.keep_v3b, cl, by_key, m, cache, nt, nm)
    up = measure(lambda rows, _n: [t for t, _ in rows], cl, by_key, m, cache, nt, nm)
    gate["fail_rate_ok"] = all(d["n_ocr_failed"] <= 0.10 * max(1, d["n_text_frames"] + d["n_blank_controls"])
                               for d in main.values())
    upf = {c: {r["frame"]: r["acc_zh"] for r in d["per_frame"]} for c, d in up.items()}
    loss = {c: [round(upf[c][r["frame"]] - r["acc_zh"], 4) for r in d["per_frame"]] for c, d in main.items()}
    i6 = {c: round(statistics.mean(v), 4) for c, v in loss.items() if v}           # 逐 (域,档) 格, 含 INSUFFICIENT 格
    probe = [x for c in cl.values() for x in c[:1]]               # D5: 每格首帧现算密度 = 冻结值
    now = R4._vision([fpath(i, f) for i, f in probe])
    frozen = all_density()
    gate["D5_density_recomputed_equal"] = all("boxes" in r and R4.density(r["boxes"])[0] == frozen[(i, f)]
                                              for (i, f), r in zip(probe, now))
    gate["I4_variance"] = all(len({r["acc_zh"] for t in TIERS for r in main[f"{d}|{t}"]["per_frame"]}) > 1
                              for d in chosen)
    base_ok = all(gate.values())
    i6_ok = bool(i6) and all(v <= I6_MAX for v in i6.values())
    h_filter = ("INSTRUMENT_GATE_FAILED" if not base_ok else
                "CONFIRMED_ON_UNSEEN_FRAMES" if i6_ok else "FAILED_ON_UNSEEN_FRAMES")
    gate["I6_filter_preserves_text"] = i6_ok
    gate_ok = base_ok and i6_ok
    verdicts = R4.judge_all(main, chosen, np.random.default_rng(SEED)) if gate_ok else {
        "H_density": "INSTRUMENT_GATE_FAILED", "H_domain_given_density": "INSTRUMENT_GATE_FAILED"}
    worst = sorted(({"cell": c, "frame": r["frame"], "loss": l, "n_anchor_prefix_boxes": r["n_anchor_prefix_boxes"]}
                    for c, d in main.items() for r, l in zip(d["per_frame"], loss[c]) if l > 0.10),
                   key=lambda x: -x["loss"])
    pref = [(r, l) for c, d in main.items() for r, l in zip(d["per_frame"], loss[c]) if r["n_anchor_prefix_boxes"]]
    res = {"block": "OCR_CROSS_DOMAIN_R5", "measured_at": "2026-10-03",
           "prereg": "tests/data/phase2/ocr_cross_domain_r5_prereg.json",
           "annotator": "Claude_single_non_human", "gt_path": GT, "gt_sha256": R1._sha(GT),
           "engine_versions": st["versions"], "filter": "keep_v3b", "filter_source_sha256": filter_sha(),
           "instrument_gate": gate, "selftest_readback": st["readback"], "density_selftest": ds,
           "determinism_checks": determinism,
           "I6_mean_acc_loss_vs_no_filter": i6, "I6_max": I6_MAX, "H_filter": h_filter,
           "filter_frame_level_descriptive": {
               "frames_loss_gt_0.10": worst,
               "same_box_prefix_frames": {"n": len(pref), "mean_loss": round(statistics.mean(l for _, l in pref), 4)
                                          if pref else None, "max_loss": max((l for _, l in pref), default=None)}},
           "domains_chosen": chosen, "tier_edges": pre["density"]["tier_edges"],
           "H_density": verdicts["H_density"], "H_domain_given_density": verdicts["H_domain_given_density"],
           "verdicts": verdicts,
           "cells_reaching_30": sorted(c for c, d in main.items() if d["n_text_frames"] >= 30),
           "cells": {"keep_v3b": {"role": "primary_preregistered", "cells": main},
                     "no_filter_upper_bound": {"role": "I6_reference_only", "cells": up}},
           "★deviations_registered": DEVIATIONS,
           "★prior_rounds_not_pooled": "r1–r4 数据只用于功效估算与已看帧自检, 不并入本轮判定。",
           "★no_transcriptions_in_repo": "本文件只有路径/sha/数字; 转写在仓外真值文件。"}
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    show = lambda p: [p["mean_diff"], p["ci90"], p["verdict_raw"], p["loco_all_same"], p["verdict"]]
    print(json.dumps({"gate": gate, "I6": i6, "H_filter": h_filter, "H_density": res["H_density"],
                      "H_domain_given_density": res["H_domain_given_density"], "worst_frames": worst[:10],
                      "cells": {c: [d["status"], d["n_text_frames"], d["n_videos"], d["n_creators"], d["acc_zh_mean"],
                                    f"B {d['n_source_B']} blank {d['n_blank_controls']} hall {d['hallucinated_on_blank']}"]
                                for c, d in main.items()},
                      **({k: ({kk: show(vv) for kk, vv in verdicts[k].items()} if k != "cross_tier_sparse_vs_dense"
                              else show(verdicts[k]) if verdicts[k] else None)
                          for k in ("within_tier_pairs", "cross_tier_sparse_vs_dense", "stratified_domain_pairs",
                                    "unstratified_domain_pairs_descriptive")} if gate_ok else {}),
                      **({"per_tier_verdict": verdicts["per_tier_verdict"]} if gate_ok else {})},
                     ensure_ascii=False, indent=1))
    return 0


DEVIATIONS = []


if __name__ == "__main__":
    rc = {"extract": cmd_extract, "density": cmd_density, "inventory": cmd_inventory, "seencheck": cmd_seencheck,
          "power": cmd_power, "sample": cmd_sample, "freeze": cmd_freeze, "run": cmd_run}[sys.argv[1]]()
    sys.stdout.flush()
    os._exit(rc)
