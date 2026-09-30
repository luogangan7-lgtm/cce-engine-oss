# -*- coding: utf-8 -*-
"""对齐出口 · Jev 判官校对(预注册 tests/data/align_atoms_jev_prereg.json)。

全部 29 个可判条目(7 个结的原子 + suspend/audit 拆分条目), 用现有三批构造草稿(开发集 A / 留出集 B / C 集 —— 都没用来调过 Jev 题面)
与同一批 20 条真实回复(N 集)。一次 Jev 调用 = 一份草稿 × 它所属结的全部条目 × 两种问法。
判据与 v5 同口径: 该条目名下**全部**构造草稿两种问法都对(至少 4 份草稿), 且真实回复上两问法一致率 >= 0.85。
只调 Jev(约 $0.00005/次), 硬上限 400。产物只放指针与判定。
用法: .venv/bin/python probes/align_atoms_jev.py [--dry-run]
"""
import argparse, collections, hashlib, importlib.util, json, os, pathlib, sys, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import cce_align_atoms as AT          # noqa: E402
import cce_s0_jev as S0               # noqa: E402
import align_atoms_heldout_cases as HB   # noqa: E402
import align_atoms_setc_cases as SC   # noqa: E402
_a = importlib.util.spec_from_file_location("_ac", ROOT / "probes/align_atoms_calibration.py"); AC = importlib.util.module_from_spec(_a); _a.loader.exec_module(AC)
_v = importlib.util.spec_from_file_location("_v5", ROOT / "probes/align_atoms_v5.py"); V5 = importlib.util.module_from_spec(_v); _v.loader.exec_module(V5)
_s = importlib.util.spec_from_file_location("_sh", ROOT / "probes/s0_jev_shadow.py"); shadow = importlib.util.module_from_spec(_s); _s.loader.exec_module(shadow)
PRE = ROOT / "tests/data/align_atoms_jev_prereg.json"
OUT = ROOT / "results/align_atoms_jev.json"
CAP, AGREE_MIN, MIN_DRAFTS = 400, 0.85, 4


def constructed():
    """[(key, kind, set, text)] —— A/B 两集里 suspend/audit 的旧复合原子草稿不用(下标已是拆分后的含义)。"""
    out = []
    for name, cases in (("A", AC.CASES), ("B", HB.CASES)):
        for key, d in cases.items():
            if key.split("#")[0] in AT.OPERATIONAL: continue
            out += [(key, kind, name, d[kind]) for kind in ("sat", "unsat")]
    for key, d in SC.CASES.items():
        out += [(key, kind, "C", t) for kind in ("sat", "unsat") for t in d[kind]]
    return out


def score(rows):
    per = {}
    keys = ["%s#%d" % (k, i) for k in AT.ATOMS_EN for i in range(len(AT.ATOMS_EN[k]))]
    for key in keys:
        knot, i = key.rsplit("#", 1)
        c = [r for r in rows if r["part"] == "C" and r["key"] == key]
        want = lambda r: "satisfied" if r["kind"] == "sat" else "unsatisfied"
        ok = sum((r["a"] == want(r)) + (r["b"] == want(r)) for r in c)
        n = [r for r in rows if r["part"] == "N" and r["knot"] == knot]
        pairs = [((r["atoms"] or {}).get(i, {}).get("a"), (r["atoms"] or {}).get(i, {}).get("b")) for r in n]
        agree = sum(1 for a, b in pairs if a is not None and a == b)
        rate = round(agree / len(pairs), 4) if pairs else None
        passed = len(c) >= MIN_DRAFTS and ok == 2 * len(c) and rate is not None and rate >= AGREE_MIN
        per[key] = {"drafts": len(c), "correct": ok, "of": 2 * len(c), "natural_agree_rate": rate,
                    "natural_A_distribution": dict(collections.Counter(a for a, _ in pairs if a)),
                    "verdict": "CALIBRATED" if passed else "NOT_CALIBRATED"}
    return per, {"atoms": len(per), "calibrated": sum(v["verdict"] == "CALIBRATED" for v in per.values()),
                 "constructed_accuracy": round(sum(v["correct"] for v in per.values()) / max(1, sum(v["of"] for v in per.values())), 4)}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    cons, nat = constructed(), V5.natural()
    jobs = [("C", key, kind, st, text) for key, kind, st, text in cons] + [("N", knot, ptr, None, text) for ptr, text in nat for knot in AT.ATOMS_EN]
    assert len(jobs) <= CAP, len(jobs)
    ledger, lock = {"req": 0}, threading.Lock()
    if a.dry_run:
        os.environ["TYPESAFE_API_KEY"] = "dry"
        def post(body, key):
            return {"answers": {q: {"choice": "unclear", "probabilities": {}} for q in body["questions"]}}, None
    else:
        os.environ["TYPESAFE_API_KEY"] = shadow._key()      # 仅本进程内
        def post(body, key):
            with lock:
                ledger["req"] += 1
                if ledger["req"] > CAP: raise RuntimeError("BUDGET_EXCEEDED")
            return S0._post(body, key, retries=1)

    def one(j):
        part, k1, k2, st, text = j
        knot = k1.rsplit("#", 1)[0] if part == "C" else k1
        r, err = AT.judge_jev(knot, text, post=post)
        if part == "C":
            i = int(k1.rsplit("#", 1)[1])
            return {"part": "C", "key": k1, "kind": k2, "set": st, "a": r[i]["a"] if r else "failed", "b": r[i]["b"] if r else "failed", "err": err}
        return {"part": "N", "knot": knot, "ptr": k2, "atoms": {str(i): {"a": v["a"], "b": v["b"]} for i, v in r.items()} if r else None, "err": err}
    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = list(ex.map(one, jobs))
    per, summ = score(rows)
    res = {"block": "ALIGN_ATOMS_JEV", "judge": "jev", "run_at": "2026-09-30", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "questions_sha256": hashlib.sha256(json.dumps({k: AT.jev_questions(k) for k in AT.ATOMS_EN}, sort_keys=True).encode()).hexdigest(),
           "requests": ledger["req"], "errors": dict(collections.Counter(r["err"] for r in rows if r["err"])),
           "natural_pointers": [p for p, _ in nat], "summary": summ, "per_atom": per, "raw": rows}
    if not a.dry_run:
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "errors", "summary")}, ensure_ascii=False))
    for k, v in per.items(): print(k, v["verdict"], "%d/%d" % (v["correct"], v["of"]), "nat", v["natural_agree_rate"], v["natural_A_distribution"])


if __name__ == "__main__":
    main()
