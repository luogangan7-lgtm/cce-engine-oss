# -*- coding: utf-8 -*-
"""对齐出口 V3 · 多题面面板在真实底稿上的准入(预注册 tests/data/align_atoms_v3_prereg.json)。

V2 的单题面判官对同义改写不稳(26 条只过 5 条)。V3: 每个条目 5 个冻结题面, ≥4 票同侧且 0 票相反才给确定值(cce_align_atoms.panel_value)。
每条目在每条底稿上: 原文(面板)· 逐字重读 · 追加中性句 · 审计题面(第 6 个, 与面板不相交, 单独一次调用)· 追加充分见证句 W · 追加难负例句 H。
★ 准入按**分布口径**(owner: 全占比, 不设布尔闸; 网页 GPT 2026-09-30: 下游吃分布时要冻结一个距离容差): 在场占比 p = 五个题面里答在场侧的比例。
  重读漂移   mean |p重读 − p原文|            单侧 95% 上界 <= 0.05
  中性句漂移 mean |p中性 − p原文|            单侧 95% 上界 <= 0.05
  见证响应   mean p(追加 W 后)               单侧 95% 下界 >= 0.90
  难负例     p原文 <= 0.2 的底稿上 mean (p追加H − p原文)  单侧 95% 上界 <= 0.05, 且这样的底稿 >= 20 条
  审计题面   mean |1{审计题面答在场} − p原文|   单侧 95% 上界 <= 0.10
  界按底稿自助(1000 次, 固定种子)。调用失败的读数按最坏值计(漂移 1、见证 0), 不当通过。
同时照报更严的**类别口径**(GPT 的原方案: 基线确定值覆盖率下界 >= 0.80; 确定值在重读/中性句/审计题面下改变或失去确定的占比上界 <= 0.05;
  见证检出下界 >= 0.90; 难负例误触发上界 <= 0.05)—— 只作对照, 不作准入: dev 上 Jev 对同一原文重读就有约 4% 的单票变动, 类别口径把「少一票」记成失败。
植入句沿用 V2(已冻结)。
--stage dev: 20 条用过的底稿, 只查题面有没有毛病。--stage confirm: 116 条此前任何一轮都没用过的底稿, 准入只看它。
"""
import argparse, collections, hashlib, importlib.util, json, math, os, pathlib, random, sys, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import cce_align_atoms as AT              # noqa: E402
import cce_s0_jev as S0                   # noqa: E402
import align_atoms_v2_plants as PL        # noqa: E402
def _load(name, rel):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
V5, shadow, MON = _load("_v5", "probes/align_atoms_v5.py"), _load("_sh", "probes/s0_jev_shadow.py"), _load("_mon", "probes/within_js_monitor.py")
PRE = ROOT / "tests/data/align_atoms_v3_prereg.json"
OUT = {"dev": ROOT / "results/align_atoms_v3_dev.json", "confirm": ROOT / "results/align_atoms_v3.json"}
CAP = {"dev": 1900, "confirm": 10700}
N_CONFIRM, MIN_COVER, MAX_UNSTABLE, MIN_WITNESS, MAX_TRIGGER = 116, 0.80, 0.05, 0.90, 0.05
TOL_DRIFT, MIN_W, TOL_H, TOL_AUDIT, MIN_H_ELIG, BOOT, SEED = 0.05, 0.90, 0.05, 0.10, 20, 1000, 20261001
KEYS = list(PL.PLANTS)


def bases(stage):
    if stage == "dev":
        return V5.natural(0)
    return [x for s in range(140, 260, 20) for x in V5.natural(s)]


def jobs(bs):
    out = []
    for n, (ptr, text) in enumerate(bs):
        for knot in AT.ATOMS_EN:
            out.append((ptr, knot, "orig", None, text, AT.PANEL_V3))
            out.append((ptr, knot, "restore", None, text, AT.PANEL_V3))
            out.append((ptr, knot, "neutral", None, text + "\n\n" + PL.NEUTRAL[n % 2], AT.PANEL_V3))
            out.append((ptr, knot, "audit", None, text, (AT.AUDIT_V3,)))
        for key in KEYS:
            knot = key.split("#")[0]
            out.append((ptr, knot, "W", key, text + "\n\n" + PL.PLANTS[key]["W"][n % 2], AT.PANEL_V3))
            out.append((ptr, knot, "H", key, text + "\n\n" + PL.PLANTS[key]["H"][n % 2], AT.PANEL_V3))
    return out


def lower(k, n): return MON.clopper_pearson(k, n, 0.10)[0] if n else 0.0      # 单侧 95%
def upper(k, n): return MON.clopper_pearson(k, n, 0.10)[1] if n else 1.0


def bound(xs, upper_side):
    """(均值, 单侧 95% 界) —— 按底稿自助。"""
    if not xs: return None, None
    rng = random.Random(SEED); n = len(xs)
    ms = sorted(math.fsum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(BOOT))
    return round(math.fsum(xs) / n, 4), round(ms[int(0.95 * BOOT) - 1] if upper_side else ms[int(0.05 * BOOT)], 4)


def score(rows, n_expected):
    by = collections.defaultdict(dict)
    for r in rows:
        by[(r["ptr"], r["knot"])][(r["kind"], r["key"])] = r["atoms"] or {}
    ptrs = sorted({r["ptr"] for r in rows}); n = len(ptrs)
    per = {}
    for key in KEYS:
        knot, i = key.split("#"); wv = AT.witness_value(AT.atoms_of(knot)[int(i)][1])
        m = v = w_ok = elig = trig = 0; types = collections.Counter(); votes = collections.Counter()
        rd, nd, ws, hs, ad = [], [], [], [], []
        for p in ptrs:
            d = by[(p, knot)]
            g = lambda kind, k=None: ((d.get((kind, k)) or {}).get(i) or {})
            sh = lambda kind, k=None: (lambda vs: vs.count(wv) / len(vs) if vs else None)(g(kind, k).get("votes"))
            pb = sh("orig")
            if pb is None:                                   # 基线读数失败: 每项按最坏值
                rd.append(1.0); nd.append(1.0); ws.append(0.0); ad.append(1.0)
            else:
                rd.append(abs(sh("restore") - pb) if sh("restore") is not None else 1.0)
                nd.append(abs(sh("neutral") - pb) if sh("neutral") is not None else 1.0)
                ws.append(sh("W", key) or 0.0)
                av = g("audit").get("votes")
                ad.append(abs((1.0 if av[0] == wv else 0.0) - pb) if av else 1.0)
                if pb <= 0.2:
                    hs.append((sh("H", key) - pb) if sh("H", key) is not None else 1.0)
            b = g("orig").get("panel", "uncertain")
            votes.update(g("orig").get("votes") or [])
            if b != "uncertain":
                m += 1
                f = []
                if g("restore").get("panel", "uncertain") != b: f.append("RESTORE")
                if g("neutral").get("panel", "uncertain") != b: f.append("NEUTRAL")
                if (g("audit").get("votes") or ["uncertain"])[0] != b: f.append("AUDIT")
                types.update(f); v += bool(f)
            w_ok += g("W", key).get("panel", "uncertain") == wv
            if b != wv:
                elig += 1; trig += g("H", key).get("panel", "uncertain") == wv
        strict = {"coverage": lower(m, n) >= MIN_COVER, "stability": m > 0 and upper(v, m) <= MAX_UNSTABLE,
                  "witness": lower(w_ok, n) >= MIN_WITNESS, "hard_negative": elig > 0 and upper(trig, elig) <= MAX_TRIGGER}
        dist = {"reread_drift": bound(rd, True), "neutral_drift": bound(nd, True), "witness_share": bound(ws, False),
                "hard_negative_shift": bound(hs, True), "hard_negative_n": len(hs), "audit_gap": bound(ad, True)}
        c = {"reread": dist["reread_drift"][1] <= TOL_DRIFT, "neutral": dist["neutral_drift"][1] <= TOL_DRIFT, "witness": dist["witness_share"][1] >= MIN_W,
             "hard_negative": len(hs) >= MIN_H_ELIG and dist["hard_negative_shift"][1] <= TOL_H, "audit": dist["audit_gap"][1] <= TOL_AUDIT}
        per[key] = {"bases": n, "distribution": dist, "strict_tier": {"criteria": strict, "pass": all(strict.values())}, "baseline_definite": m, "coverage_lcb": lower(m, n), "unstable": v, "unstable_ucb": upper(v, m), "unstable_types": dict(types),
                    "witness_detected": w_ok, "witness_lcb": lower(w_ok, n), "hard_negative_eligible": elig, "hard_negative_triggered": trig,
                    "trigger_ucb": upper(trig, elig), "baseline_votes": dict(votes), "criteria": c,
                    "verdict": "VALIDATED" if n == n_expected and all(c.values()) else "NOT_VALIDATED"}
    return per, {"items": len(per), "validated": sum(x["verdict"] == "VALIDATED" for x in per.values()), "strict_tier_pass": sum(x["strict_tier"]["pass"] for x in per.values())}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", choices=["dev", "confirm"], required=True); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    bs = bases(a.stage)
    if a.stage == "confirm":
        used = {p for s in range(0, 140, 20) for p, _ in V5.natural(s)}
        assert len(bs) == N_CONFIRM and len({p for p, _ in bs}) == N_CONFIRM and not used & {p for p, _ in bs}, "确认集必须是没用过的 116 条"
    js = jobs(bs); assert len(js) <= CAP[a.stage], len(js)
    ledger, lock = {"req": 0}, threading.Lock()
    if a.dry_run:
        os.environ["TYPESAFE_API_KEY"] = "dry"
        post = lambda body, key: ({"answers": {q: {"choice": "unclear", "probabilities": {}} for q in body["questions"]}}, None)
    else:
        os.environ["TYPESAFE_API_KEY"] = shadow._key()      # 仅本进程内
        def post(body, key):
            with lock:
                ledger["req"] += 1
                if ledger["req"] > CAP[a.stage]: raise RuntimeError("BUDGET_EXCEEDED")
            return S0._post(body, key, retries=3)

    def one(j):
        ptr, knot, kind, key, text, forms = j
        r, err = AT.judge_jev_v3(knot, text, post=post, forms=forms)
        return {"ptr": ptr, "knot": knot, "kind": kind, "key": key, "atoms": {str(i): x for i, x in r.items()} if r else None, "err": err}
    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, js))
    per, summ = score(rows, len(bs))
    res = {"block": "ALIGN_ATOMS_V3_" + a.stage.upper(), "judge": "jev", "stage": a.stage, "run_at": "2026-09-30", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest() if PRE.exists() else None,
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "plants_sha256": hashlib.sha256((ROOT / "probes/align_atoms_v2_plants.py").read_bytes()).hexdigest(),
           "questions_sha256": hashlib.sha256(json.dumps({k: AT.jev_questions_v3(k, AT.PANEL_V3 + (AT.AUDIT_V3,)) for k in AT.ATOMS_EN}, sort_keys=True).encode()).hexdigest(),
           "requests": ledger["req"], "errors": dict(collections.Counter(r["err"] for r in rows if r["err"])),
           "base_pointers": [p for p, _ in bs], "summary": summ, "per_atom": per, "raw": rows}
    if not a.dry_run:
        OUT[a.stage].write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "errors", "summary")}, ensure_ascii=False))
    for k, x in per.items():
        dd = x["distribution"]
        print(k, x["verdict"], {c: v for c, v in x["criteria"].items() if not v} or "", "reread", dd["reread_drift"], "neutral", dd["neutral_drift"], "W", dd["witness_share"],
              "H", dd["hard_negative_shift"], dd["hard_negative_n"], "audit", dd["audit_gap"], "| strict", x["strict_tier"]["pass"], "cover %d unstable %d" % (x["baseline_definite"], x["unstable"]))


if __name__ == "__main__":
    main()
