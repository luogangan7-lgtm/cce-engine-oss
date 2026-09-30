# -*- coding: utf-8 -*-
"""对齐出口 Jev 判官 · 真实回复一致率的扩样复核(预注册 tests/data/align_atoms_jev_n3_prereg.json)。

前两轮每个条目的「两问法一致率」只有 20 条真实回复, 0.85 线上下只差 1 条(16/20 vs 17/20): reward#2 以 0.80 落选,
injustice#0 / display#0 / audit#2 以 0.85 擦线入选 —— 两个方向都可能是运气。题面一字不改, 再取 40 条没用过的真实回复(N3),
每个条目按**合并 60 条**(它原来那 20 条 + 新 40 条)重判; 构造草稿那一半沿用已有结果。对称: 过线的进, 不过线的出。
只调 Jev, 硬上限 400。用法: .venv/bin/python probes/align_atoms_jev_n3.py [--dry-run]
"""
import argparse, collections, hashlib, importlib.util, json, os, pathlib, sys, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import cce_align_atoms as AT          # noqa: E402
import cce_s0_jev as S0               # noqa: E402
_j = importlib.util.spec_from_file_location("_aj", ROOT / "probes/align_atoms_jev.py"); AJ = importlib.util.module_from_spec(_j); _j.loader.exec_module(AJ)
PRE = ROOT / "tests/data/align_atoms_jev_n3_prereg.json"
OUT = ROOT / "results/align_atoms_jev_final.json"
BASE, REWARD = ROOT / "results/align_atoms_jev.json", ROOT / "results/align_atoms_jev_reward.json"
CAP, AGREE_MIN = 400, 0.85


def prior():
    """每个条目: 构造草稿是否全对 + 它原来那 20 条真实回复上的 (一致数, 总数)。reward 取重做后的结果(判定用的是 N2)。"""
    b = json.loads(BASE.read_text(encoding="utf-8")); r = json.loads(REWARD.read_text(encoding="utf-8"))
    out = {}
    for key, v in b["per_atom"].items():
        if key.startswith("reward#"): continue
        out[key] = {"constructed_ok": v["drafts"] >= 4 and v["correct"] == v["of"], "agree": round(v["natural_agree_rate"] * 20), "n": 20}
    for key, v in r["per_atom"].items():
        out[key] = {"constructed_ok": v["drafts"] >= 4 and v["correct"] == v["of"], "agree": round(v["natural_agree_rate"] * 20), "n": 20}
    return out


def score(rows):
    pr, per = prior(), {}
    for key, p in pr.items():
        knot, i = key.rsplit("#", 1)
        pairs = [((r["atoms"] or {}).get(i, {}).get("a"), (r["atoms"] or {}).get(i, {}).get("b")) for r in rows if r["knot"] == knot]
        a3 = sum(1 for a, b in pairs if a is not None and a == b)
        tot_a, tot_n = p["agree"] + a3, p["n"] + len(pairs)
        rate = round(tot_a / tot_n, 4)
        per[key] = {"constructed_ok": p["constructed_ok"], "first20_agree": p["agree"], "n3_agree": a3, "n3_n": len(pairs),
                    "combined_agree_rate": rate, "n3_A_distribution": dict(collections.Counter(a for a, _ in pairs if a)),
                    "verdict": "CALIBRATED" if p["constructed_ok"] and len(pairs) == 40 and rate >= AGREE_MIN else "NOT_CALIBRATED"}
    return per, {"atoms": len(per), "calibrated": sum(v["verdict"] == "CALIBRATED" for v in per.values())}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    n3 = AJ.V5.natural(40) + AJ.V5.natural(60)
    used = {p for s in (0, 20) for p, _ in AJ.V5.natural(s)}
    assert len(n3) == 40 and not used & {p for p, _ in n3}
    jobs = [(knot, ptr, text) for ptr, text in n3 for knot in AT.ATOMS_EN]
    assert len(jobs) <= CAP
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

    def one(j):
        knot, ptr, text = j
        r, err = AT.judge_jev(knot, text, post=post)
        return {"knot": knot, "ptr": ptr, "atoms": {str(i): {"a": v["a"], "b": v["b"]} for i, v in r.items()} if r else None, "err": err}
    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = list(ex.map(one, jobs))
    per, summ = score(rows)
    res = {"block": "ALIGN_ATOMS_JEV_N3", "judge": "jev", "run_at": "2026-09-30", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "questions_sha256": hashlib.sha256(json.dumps({k: AT.jev_questions(k) for k in AT.ATOMS_EN}, sort_keys=True).encode()).hexdigest(),
           "requests": ledger["req"], "errors": dict(collections.Counter(r["err"] for r in rows if r["err"])),
           "n3_pointers": [p for p, _ in n3], "summary": summ, "per_atom": per, "raw": rows}
    if not a.dry_run:
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "errors", "summary")}, ensure_ascii=False))
    for k, v in per.items(): print(k, v["verdict"], "构造全对" if v["constructed_ok"] else "构造有错", "%d+%d/60=%s" % (v["first20_agree"], v["n3_agree"], v["combined_agree_rate"]))


if __name__ == "__main__":
    main()
