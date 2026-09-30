# -*- coding: utf-8 -*-
"""对齐出口 v5 校对(预注册 tests/data/align_atoms_v5_prereg.json)。

两件事, 都只针对「在用原子」= v4.1 留出集通过的 11 个 + suspend/audit 操作化拆分出的 8 个:
  C 集: 每原子 2 份满足 + 2 份不满足的新构造草稿 × 两种相反问法 × 2 次 = 16 次读数, 全对才过(更多样本)。
  N 集: 20 条**真实**社区回复(化名语料 accuracy/data/hearingaids_regulars_20260809.json), 每条在 9 个结的清单下各用两种问法判一次;
        逐原子算两种问法规范值的一致率(真实文本上没有真值, 但同一段文本换个问法不该换答案)。
MiniMax 经生产同一路径, 本进程开请求作用域, 硬上限 750。产物只放指针与判定, 不落原文。
用法: .venv/bin/python probes/align_atoms_v5.py [--dry-run]
"""
import argparse, collections, hashlib, json, os, pathlib, random, re, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import cce_align_atoms as AT                                   # noqa: E402
import align_atoms_setc_cases as SC                            # noqa: E402
from cce_request_budget import open_scope, scope_status        # noqa: E402
PRE = ROOT / "tests/data/align_atoms_v5_prereg.json"
OUT = ROOT / "results/align_atoms_v5.json"
HELD = ROOT / "results/align_atoms_heldout_v41.json"
REG = ROOT / "accuracy/data/hearingaids_regulars_20260809.json"
CAP, REPS, N_NAT, SEED, AGREE_MIN = 750, 2, 20, 20260930, 0.85
KNOTS = ("pain_seek", "injustice", "belong", "reward", "display", "itch", "suspend", "inertia", "audit")


def natural(start=0):
    users = json.loads(REG.read_text(encoding="utf-8"))["users"]
    pool = []
    for u, cs in users.items():
        for c in cs:
            b = c.get("b") or ""
            if 25 <= len(b.split()) <= 120 and not re.search(r"\bu/\w+|/user/\w+", b):
                pool.append(("regulars:%s:%s" % (u, c.get("id")), b))
    pool.sort(key=lambda x: hashlib.sha256(x[1].encode()).hexdigest())
    random.Random(SEED).shuffle(pool)
    return pool[start:start + N_NAT]


def score(rows):
    per = {}
    for key in SC.CASES:
        knot, i = key.rsplit("#", 1); i = int(i)
        c = [r for r in rows if r["part"] == "C" and r["key"] == key]
        ok = sum(r["canonical"] == ("satisfied" if r["kind"] == "sat" else "unsatisfied") for r in c)
        nat = collections.defaultdict(dict)
        for r in rows:
            if r["part"] == "N" and r["knot"] == knot:
                nat[r["ptr"]][r["framing"]] = (r["atoms"] or {}).get(str(i))
        pairs = [(v.get("a"), v.get("b")) for v in nat.values()]
        agree = sum(1 for a, b in pairs if a is not None and a == b)
        rate = round(agree / len(pairs), 4) if pairs else None
        dist = dict(collections.Counter(a for a, _ in pairs if a))
        passed = len(c) == 8 * REPS and ok == len(c) and rate is not None and rate >= AGREE_MIN
        per[key] = {"setC_correct": ok, "setC_n": len(c), "natural_pairs": len(pairs), "natural_agree": agree, "natural_agree_rate": rate,
                    "natural_A_distribution": dist, "verdict": "CALIBRATED" if passed else "NOT_CALIBRATED",
                    "why_not": None if passed else ("C 集 %d/%d" % (ok, len(c)) if ok != len(c) or len(c) != 8 * REPS else "真实回复两问法一致率 %s < %s" % (rate, AGREE_MIN))}
    return per, {"in_play": len(per), "calibrated": sum(v["verdict"] == "CALIBRATED" for v in per.values())}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    held = json.loads(HELD.read_text(encoding="utf-8"))["per_atom"]
    prior = {k for k, v in held.items() if v["verdict"] == "CALIBRATED"}
    new = {k for k in SC.CASES if k.split("#")[0] in AT.OPERATIONAL}
    assert set(SC.CASES) == prior | new, "C 集覆盖的必须恰是: v4.1 留出通过的 + suspend/audit 拆分条目"
    nat = natural()
    jobs = [("C", key, kind, n, rep, fr, text) for key, d in SC.CASES.items() for kind in ("sat", "unsat")
            for n, text in enumerate(d[kind]) for rep in range(REPS) for fr in ("a", "b")]
    jobs += [("N", knot, ptr, None, 0, fr, text) for ptr, text in nat for knot in KNOTS for fr in ("a", "b")]
    assert len(jobs) <= CAP, len(jobs)
    if a.dry_run:
        def call(prompt, temperature=0.0):
            n = prompt.count("【做】") + prompt.count("【禁】")
            return json.dumps({"atoms": [{"i": i + 1, "state": "不确定", "quote": ""} for i in range(n)]}, ensure_ascii=False)
    else:
        import extractor_counterexample_run_r2 as KR   # noqa: E402
        KR._load_key(); call = None
    open_scope("align_atoms_v5", CAP, os.path.join(tempfile.mkdtemp(), "budget.json"))

    def one(j):
        part, k1, k2, n, rep, fr, text = j
        if part == "C":
            knot, i = k1.rsplit("#", 1)
            r = AT.judge(knot, text, framing=fr, call=call)
            return {"part": "C", "key": k1, "kind": k2, "draft": n, "rep": rep, "framing": fr,
                    "canonical": r[int(i)]["canonical"] if r else "failed", "state": r[int(i)]["state"] if r else None}
        r = AT.judge(k1, text, framing=fr, call=call)
        return {"part": "N", "knot": k1, "ptr": k2, "framing": fr, "atoms": {str(x["i"]): x["canonical"] for x in r} if r else None}
    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = list(ex.map(one, jobs))
    per, summ = score(rows)
    res = {"block": "ALIGN_ATOMS_V5", "judge_version": AT.VERSION, "run_at": "2026-09-30", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "judge_sha256": hashlib.sha256((ROOT / "scripts/cce_align_atoms.py").read_bytes()).hexdigest(),
           "requests": scope_status(), "natural_pointers": [p for p, _ in nat], "summary": summ, "per_atom": per, "raw": rows}
    if not a.dry_run:
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "summary")}, ensure_ascii=False))
    for k, v in per.items(): print(k, v["verdict"], "C %d/%d" % (v["setC_correct"], v["setC_n"]), "nat", v["natural_agree_rate"], v["natural_A_distribution"])


if __name__ == "__main__":
    main()
