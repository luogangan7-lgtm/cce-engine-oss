# -*- coding: utf-8 -*-
"""s0 五面植入信号 · 分布口径(全占比)复测 —— 预注册 tests/data/s0_planted_profile_prereg.json。

与 S0_PLANTED_SIGNAL_VALIDITY 同材料(前 10 段 × PLANTS × 两说法 + 中性句 + baseline), 只改判法:
存 Jev 每面完整分布; 判 ① 目标面位移 dp = p(植入值) − baseline 同值占比 ② 其余面分布位移(总变差距离 TVD)扣掉中性句的 TVD。
只调 Jev, 硬上限 600。产物只放指针、类别与概率。用法: python3 probes/s0_planted_profile.py [--dry-run]
"""
import argparse, collections, hashlib, importlib.util, json, os, pathlib, statistics, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
_s = importlib.util.spec_from_file_location("_pv", ROOT / "probes/s0_planted_validity.py"); pv = importlib.util.module_from_spec(_s); _s.loader.exec_module(pv)
S0, shadow, FACETS, KEYS = pv.S0, pv.shadow, pv.FACETS, pv.KEYS
PRE = ROOT / "tests/data/s0_planted_profile_prereg.json"
OUT = ROOT / "results/s0_planted_profile.json"
CAP = 600


def tvd(p, q):
    ks = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in ks)


def verdict(dp, net):
    if dp < 0.25: return "UNRESPONSIVE"
    return "RESPONSIVE" if dp >= 0.5 and net <= 0.10 else "WEAK"


def analyse(rows):
    ok = [r for r in rows if r["probs"]]
    base = {r["ptr"]: r["probs"] for r in ok if r["kind"] == "baseline"}
    ok = [r for r in ok if r["ptr"] in base]
    neu = [tvd(r["probs"][k], base[r["ptr"]][k]) for r in ok if r["kind"] == "neutral" for k in KEYS]
    neu_tvd = statistics.fmean(neu) if neu else 0.0
    per = {}
    for f, vals in pv.PLANTS.items():
        pr = [r for r in ok if r["kind"] == "plant" and r["facet"] == f]
        dps = {v: [r["probs"][f].get(v, 0.0) - base[r["ptr"]][f].get(v, 0.0) for r in pr if r["value"] == v] for v in vals}
        dp_v = {v: round(statistics.fmean(x), 4) for v, x in dps.items() if x}
        dp = round(statistics.fmean(dp_v.values()), 4)
        off = {k: round(statistics.fmean(tvd(r["probs"][k], base[r["ptr"]][k]) for r in pr), 4) for k in KEYS if k != f}
        net = round(statistics.fmean(off.values()) - neu_tvd, 4)
        per[f] = {"n": len(pr), "dp_target": dp, "dp_by_value": dp_v, "off_target_tvd_by_facet": off,
                  "net_off_target_tvd": net, "verdict": verdict(dp, net)}
    return round(neu_tvd, 4), per


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    passages = shadow.load_passages()[:pv.N_PASSAGES]
    js = pv.jobs(passages); assert len(js) <= CAP
    ledger, lock = {"req": 0}, threading.Lock()
    if a.dry_run:
        key = "dry"
        def post(body, k):
            return {"answers": {q: {"choice": "未知", "probabilities": {"未知": 1.0}} for q in body["questions"]}}, None
    else:
        key = shadow._key()
        def post(body, k):
            with lock:
                ledger["req"] += 1
                if ledger["req"] > CAP: raise RuntimeError("BUDGET_EXCEEDED")
            return S0._post(body, k, retries=1)
    os.environ["TYPESAFE_API_KEY"] = key          # 仅本进程内, 不打印不落盘
    def one(j):
        kind, ptr, f, v, i, body = j
        read, probs, err = S0.s0_jev_read(body[:2000], FACETS, post=post)
        return {"kind": kind, "ptr": ptr, "facet": f, "value": v, "phrasing": i, "top": read, "probs": probs, "err": err}
    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = list(ex.map(one, js))
    neu, per = analyse(rows)
    res = {"block": "S0_PLANTED_PROFILE", "run_at": "2026-09-29", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "passages": [p for p, _ in passages], "requests": ledger["req"],
           "errors": dict(collections.Counter(r["err"] for r in rows if r["err"])),
           "neutral_tvd": neu, "per_facet": per, "raw": rows}
    if not a.dry_run:
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"requests": ledger["req"], "errors": res["errors"], "neutral_tvd": neu,
                      "per_facet": {k: {kk: v[kk] for kk in ("dp_target", "net_off_target_tvd", "verdict")} for k, v in per.items()}},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
