# -*- coding: utf-8 -*-
"""对齐出口 V2 · 真实底稿上的受控变形测试(预注册 tests/data/align_atoms_v2_prereg.json)。

每条真实回复(底稿)× 每个条目, 一个测试块(网页 GPT 2026-09-30 的方案, CheckList 的 MFT / INV / DIR):
  原文(A + A′)· 逐字再读一次(恢复/重复性)· 追加中性句 · 追加充分见证句 W · 追加难负例句 H
只看问法 A 的规范值(A′ 只用来查原文上的相反确定答案)。一个底稿上只要出现任一预注册失败, 该(底稿, 条目)记 1 次失败事件:
  F_W 见证没被检出(unclear 也算)    F_H 难负例把读数推到在场一侧    F_N 中性句把读数推到在场一侧或翻到对侧
  F_R 同一原文两次读数给出相反确定值   F_P 原文上 A 与 A′ 给出相反确定值
--stage dev: 8 条已用过的回复, 只为查植入句本身有没有毛病(可据此改一次植入句, 改完冻结)。
--stage confirm: 60 条此前任何一轮都没用过的回复, 准入只看它。
只调 Jev(约 $0.00005/次); dev 上限 700, confirm 上限 5200。产物只放指针与判定。
"""
import argparse, collections, hashlib, importlib.util, json, os, pathlib, sys, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import cce_align_atoms as AT              # noqa: E402
import cce_s0_jev as S0                   # noqa: E402
import align_atoms_v2_plants as PL        # noqa: E402
_v = importlib.util.spec_from_file_location("_v5", ROOT / "probes/align_atoms_v5.py"); V5 = importlib.util.module_from_spec(_v); _v.loader.exec_module(V5)
_s = importlib.util.spec_from_file_location("_sh", ROOT / "probes/s0_jev_shadow.py"); shadow = importlib.util.module_from_spec(_s); _s.loader.exec_module(shadow)
PRE = ROOT / "tests/data/align_atoms_v2_prereg.json"
OUT = {"dev": ROOT / "results/align_atoms_v2_dev.json", "confirm": ROOT / "results/align_atoms_v2.json"}
CAP = {"dev": 700, "confirm": 5200}
MAX_FAIL, MIN_COVER, N_CONFIRM = 1, 0.70, 60
KEYS = list(PL.PLANTS)


def bases(stage):
    if stage == "dev":
        return V5.natural(0)[:8]
    return V5.natural(80) + V5.natural(100) + V5.natural(120)


def jobs(bs):
    out = []
    for n, (ptr, text) in enumerate(bs):
        for knot in AT.ATOMS_EN:
            out.append((ptr, n, knot, "orig", None, text))
            out.append((ptr, n, knot, "restore", None, text))
            out.append((ptr, n, knot, "neutral", None, text + "\n\n" + PL.NEUTRAL[n % 2]))
        for key in KEYS:
            knot = key.split("#")[0]
            out.append((ptr, n, knot, "W", key, text + "\n\n" + PL.PLANTS[key]["W"][n % 2]))
            out.append((ptr, n, knot, "H", key, text + "\n\n" + PL.PLANTS[key]["H"][n % 2]))
    return out


def score(rows, n_expected):
    by = collections.defaultdict(dict)
    for r in rows:
        by[(r["ptr"], r["knot"])][(r["kind"], r["key"])] = r["atoms"]
    ptrs = sorted({r["ptr"] for r in rows})
    per = {}
    for key in KEYS:
        knot, i = key.split("#"); neg = AT.atoms_of(knot)[int(i)][1]; wv = AT.witness_value(neg); opp = "satisfied" if wv == "unsatisfied" else "unsatisfied"
        fails, types, cover, base_dist, incomplete = 0, collections.Counter(), 0, collections.Counter(), 0
        for p in ptrs:
            d = by[(p, knot)]
            get = lambda kind, k=None: ((d.get((kind, k)) or {}).get(i) or {})
            o, rs, nt, w, h = get("orig"), get("restore"), get("neutral"), get("W", key), get("H", key)
            if not all(x.get("a") for x in (o, rs, nt, w, h)):
                incomplete += 1; fails += 1; types["INCOMPLETE"] += 1; continue          # 调用失败: 不当通过
            b = o["a"]; base_dist[b] += 1; cover += b != "uncertain"
            f = []
            if w["a"] != wv: f.append("F_W")
            if b != wv and h["a"] == wv: f.append("F_H")
            if (b != wv and nt["a"] == wv) or (b == wv and nt["a"] == opp): f.append("F_N")
            if {b, rs["a"]} == {"satisfied", "unsatisfied"}: f.append("F_R")
            if {b, o.get("p")} == {"satisfied", "unsatisfied"}: f.append("F_P")
            for x in f: types[x] += 1
            fails += bool(f)
        n = len(ptrs)
        ok = n == n_expected and fails <= MAX_FAIL and (cover / n if n else 0) >= MIN_COVER
        per[key] = {"bases": n, "failing_bases": fails, "failure_types": dict(types), "coverage": round(cover / n, 4) if n else None,
                    "witness_detect_rate": round(1 - types["F_W"] / max(1, n - incomplete), 4), "baseline_distribution": dict(base_dist),
                    "verdict": "VALIDATED" if ok else "NOT_VALIDATED"}
    return per, {"items": len(per), "validated": sum(v["verdict"] == "VALIDATED" for v in per.values())}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", choices=["dev", "confirm"], required=True); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    bs = bases(a.stage)
    if a.stage == "confirm":
        used = {p for s in (0, 20, 40, 60) for p, _ in V5.natural(s)}
        assert len(bs) == N_CONFIRM and not used & {p for p, _ in bs}, "确认集必须是没用过的 60 条"
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
            return S0._post(body, key, retries=2)

    def one(j):
        ptr, n, knot, kind, key, text = j
        r, err = AT.judge_jev_v2(knot, text, post=post)
        return {"ptr": ptr, "knot": knot, "kind": kind, "key": key,
                "atoms": {str(i): {"a": v["a"], "p": v["p"]} for i, v in r.items()} if r else None, "err": err}
    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, js))
    per, summ = score(rows, len(bs))
    res = {"block": "ALIGN_ATOMS_V2_" + a.stage.upper(), "judge": "jev", "stage": a.stage, "run_at": "2026-09-30", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest() if PRE.exists() else None,
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "plants_sha256": hashlib.sha256((ROOT / "probes/align_atoms_v2_plants.py").read_bytes()).hexdigest(),
           "questions_sha256": hashlib.sha256(json.dumps({k: AT.jev_questions_v2(k) for k in AT.ATOMS_EN}, sort_keys=True).encode()).hexdigest(),
           "requests": ledger["req"], "errors": dict(collections.Counter(r["err"] for r in rows if r["err"])),
           "base_pointers": [p for p, _ in bs], "summary": summ, "per_atom": per, "raw": rows}
    if not a.dry_run:
        OUT[a.stage].write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "errors", "summary")}, ensure_ascii=False))
    for k, v in per.items(): print(k, v["verdict"], "fail %d/%d" % (v["failing_bases"], v["bases"]), v["failure_types"], "cover", v["coverage"])


if __name__ == "__main__":
    main()
