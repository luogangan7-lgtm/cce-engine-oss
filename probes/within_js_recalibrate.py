# -*- coding: utf-8 -*-
"""s1 组内散布闸重标定(预注册 tests/data/within_js_recalibration_prereg.json)。零调用。

标定集 = 预注册里冻结的存档文件(现行 k=3 仪器 d4cce4); 规则与 2026-08-17 相同: median + 2×MAD(未缩放)。
留出集 = S1_CONTEXT_SUFFIX_AB 的 64 次 s1 原始产物(不在存档里)。首次运行时从原始产物目录抽数字落
results/within_js_holdout_numbers.json(只有数字), 之后一律从这份数字文件现算。
用法: .venv/bin/python probes/within_js_recalibrate.py [--extract <s1ab 原始产物目录>]
"""
import argparse, glob, hashlib, json, math, os, pathlib, statistics, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
PRE = ROOT / "tests/data/within_js_recalibration_prereg.json"
NUM = ROOT / "results/within_js_holdout_numbers.json"
OUT = ROOT / "results/within_js_recalibration.json"
LAYERS = ("desire_vec", "need_vec", "emotion_vec", "action_vec")


def js(p, q):
    s1, s2 = math.fsum(p) or 1.0, math.fsum(q) or 1.0
    a = [x / s1 for x in p]; b = [x / s2 for x in q]; m = [(x + y) / 2 for x, y in zip(a, b)]
    kl = lambda u, v: math.fsum(x * math.log2(x / y) for x, y in zip(u, v) if x > 0)
    return 0.5 * kl(a, m) + 0.5 * kl(b, m)


def rank(xs):
    o = sorted(range(len(xs)), key=lambda i: xs[i]); r = [0.0] * len(xs); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and xs[o[j + 1]] == xs[o[i]]: j += 1
        for k in range(i, j + 1): r[o[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(a, b):
    ra, rb = rank(a), rank(b); ma, mb = statistics.fmean(ra), statistics.fmean(rb)
    sa = math.sqrt(math.fsum((x - ma) ** 2 for x in ra)); sb = math.sqrt(math.fsum((y - mb) ** 2 for y in rb))
    return None if sa == 0 or sb == 0 else round(math.fsum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / (sa * sb), 4)


def calibrate(files):
    vals = {l: [json.loads((ROOT / f).read_text(encoding="utf-8"))["stage1"]["within_js"][l] for f in files] for l in LAYERS}
    out = {}
    for l, v in vals.items():
        med = statistics.median(v); mad = statistics.median(abs(x - med) for x in v)
        out[l] = {"median": round(med, 4), "mad": round(mad, 4), "threshold": round(med + 2 * mad, 3), "n": len(v)}
    return out


def extract(d):
    rows = []
    for f in sorted(glob.glob(os.path.join(d, "s1_*_*_*.json"))):
        n, arm, rep = pathlib.Path(f).stem.split("_")[1:]
        s = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        st = s["stage1"]
        rows.append({"text": int(n), "arm": arm, "rep": int(rep), "instrument": s["stage2"]["instrument"]["instrument_hash"],
                     "within_js": st["within_js"], "layers": st["layers"]})
    NUM.write_text(json.dumps({"source": "S1_CONTEXT_SUFFIX_AB 原始 s1 产物(只抽数字)", "rows": rows}, indent=1), encoding="utf-8")


def evaluate(cal, old, rows):
    by = {}
    for r in rows: by.setdefault(r["text"], []).append(r)
    res = {}
    for l in LAYERS:
        w, inst = [], []
        for t, rs in by.items():
            for r in rs:
                others = [o for o in rs if o is not r]
                w.append(r["within_js"][l]); inst.append(statistics.fmean(js(r["layers"][l], o["layers"][l]) for o in others))
        new_t, old_t = cal[l]["threshold"], old[l]
        rate = round(sum(x > new_t for x in w) / len(w), 4); rate_old = round(sum(x > old_t for x in w) / len(w), 4)
        rho = spearman(w, inst)
        res[l] = {"old_threshold": old_t, "new_threshold": new_t, "holdout_exceed_new": rate, "holdout_exceed_old": rate_old,
                  "gate_validity_spearman": rho, "adopt": 0.05 <= rate <= 0.25,
                  "gate_weak": rho is None or rho < 0.2}
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--extract"); a = ap.parse_args(argv)
    if a.extract:
        extract(a.extract)
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    from cce_full_run import WITHIN_JS_MAX_DEFAULT as OLD
    cal = calibrate(pre["calibration_set"]["files"])
    rows = json.loads(NUM.read_text(encoding="utf-8"))["rows"]
    assert {r["instrument"] for r in rows} == {pre["calibration_set"]["instrument_hash"]}, "留出集不是同一台仪器"
    res = {"block": pre["block"], "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "holdout_numbers_sha256": hashlib.sha256(NUM.read_bytes()).hexdigest(),
           "calibration": cal, "holdout": evaluate(cal, OLD, rows),
           "adopted": {l: cal[l]["threshold"] for l in LAYERS}}
    res["adopted"] = {l: (cal[l]["threshold"] if res["holdout"][l]["adopt"] else OLD[l]) for l in LAYERS}
    res["adopted_for"] = pre["calibration_set"]["instrument_hash"]
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("calibration", "holdout", "adopted")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
