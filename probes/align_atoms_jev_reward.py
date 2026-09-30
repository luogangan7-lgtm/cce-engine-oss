# -*- coding: utf-8 -*-
"""reward 结 · 重做后的 Jev 校对(预注册 tests/data/align_atoms_jev_reward_prereg.json)。

reward#0「短收」= 机械规则(句数 <= 2 且词数 <= 40), 不问模型; reward#1 / #2 = 改写后的题面。
构造草稿: 三批已有草稿里 reward 的全部(#0、#1 各 4 份, #2 8 份)。真实回复: **新的 20 条**(V5.natural(start=20), 此前任何一轮都没用过)
作判定; 原来那 20 条(已看过结果)只作开发集回归报告。只调 Jev, 硬上限 80。
用法: .venv/bin/python probes/align_atoms_jev_reward.py [--dry-run]
"""
import argparse, collections, hashlib, importlib.util, json, os, pathlib, sys, threading

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import cce_align_atoms as AT          # noqa: E402
import cce_s0_jev as S0               # noqa: E402
_j = importlib.util.spec_from_file_location("_aj", ROOT / "probes/align_atoms_jev.py"); AJ = importlib.util.module_from_spec(_j); _j.loader.exec_module(AJ)
PRE = ROOT / "tests/data/align_atoms_jev_reward_prereg.json"
OUT = ROOT / "results/align_atoms_jev_reward.json"
CAP, AGREE_MIN, MIN_DRAFTS, KNOT = 80, 0.85, 4, "reward"


def score(rows):
    per = {}
    for i in range(len(AT.ATOMS_EN[KNOT])):
        key = "%s#%d" % (KNOT, i); mech = (KNOT, i) in AT.MECHANICAL
        c = [r for r in rows if r["part"] == "C" and r["key"] == key]
        want = lambda r: "satisfied" if r["kind"] == "sat" else "unsatisfied"
        ok = sum((r["a"] == want(r)) + (r["b"] == want(r)) for r in c)
        def agree(part):
            pairs = [((r["atoms"] or {}).get(str(i), {}).get("a"), (r["atoms"] or {}).get(str(i), {}).get("b")) for r in rows if r["part"] == part]
            return (round(sum(1 for a, b in pairs if a is not None and a == b) / len(pairs), 4) if pairs else None,
                    dict(collections.Counter(a for a, _ in pairs if a)))
        r2, d2 = agree("N2"); r1, _ = agree("N1")
        passed = len(c) >= MIN_DRAFTS and ok == 2 * len(c) and r2 is not None and r2 >= AGREE_MIN
        per[key] = {"mechanical": mech, "drafts": len(c), "correct": ok, "of": 2 * len(c), "natural_agree_rate": r2,
                    "natural_A_distribution": d2, "dev_natural_agree_rate": r1, "verdict": "CALIBRATED" if passed else "NOT_CALIBRATED"}
    return per, {"atoms": len(per), "calibrated": sum(v["verdict"] == "CALIBRATED" for v in per.values())}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    cons = [x for x in AJ.constructed() if x[0].startswith(KNOT + "#")]
    n1, n2 = AJ.V5.natural(0), AJ.V5.natural(20)
    assert not {p for p, _ in n1} & {p for p, _ in n2}
    jobs = [("C", key, kind, text) for key, kind, _st, text in cons] + [("N2", p, None, t) for p, t in n2] + [("N1", p, None, t) for p, t in n1]
    assert len(jobs) <= CAP, len(jobs)
    ledger, lock = {"req": 0}, threading.Lock()
    if a.dry_run:
        os.environ["TYPESAFE_API_KEY"] = "dry"
        post = lambda body, key: ({"answers": {q: {"choice": "unclear", "probabilities": {}} for q in body["questions"]}}, None)
    else:
        os.environ["TYPESAFE_API_KEY"] = AJ.shadow._key()
        def post(body, key):
            with lock:
                ledger["req"] += 1
                if ledger["req"] > CAP: raise RuntimeError("BUDGET_EXCEEDED")
            return S0._post(body, key, retries=1)
    rows = []
    for part, k1, k2, text in jobs:
        r, err = AT.judge_jev(KNOT, text, post=post)
        if part == "C":
            i = int(k1.rsplit("#", 1)[1])
            rows.append({"part": "C", "key": k1, "kind": k2, "a": r[i]["a"] if r else "failed", "b": r[i]["b"] if r else "failed", "err": err})
        else:
            rows.append({"part": part, "ptr": k1, "atoms": {str(i): {"a": v["a"], "b": v["b"]} for i, v in r.items()} if r else None, "err": err})
    per, summ = score(rows)
    res = {"block": "ALIGN_ATOMS_JEV_REWARD", "judge": "jev", "run_at": "2026-09-30", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "questions_sha256": hashlib.sha256(json.dumps(AT.jev_questions(KNOT), sort_keys=True).encode()).hexdigest(),
           "short_rule": {"max_sentences": AT.SHORT_MAX_SENTENCES, "max_words": AT.SHORT_MAX_WORDS},
           "requests": ledger["req"], "errors": dict(collections.Counter(r["err"] for r in rows if r["err"])),
           "heldout_natural_pointers": [p for p, _ in n2], "summary": summ, "per_atom": per, "raw": rows}
    if not a.dry_run:
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "errors", "summary")}, ensure_ascii=False))
    for k, v in per.items(): print(k, v["verdict"], "%d/%d" % (v["correct"], v["of"]), "N2", v["natural_agree_rate"], v["natural_A_distribution"], "dev", v["dev_natural_agree_rate"])


if __name__ == "__main__":
    main()
