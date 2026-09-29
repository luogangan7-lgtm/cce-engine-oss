# -*- coding: utf-8 -*-
"""情绪余温 指代最小对 · 留出测试(预注册 tests/data/s0_residue_referent_prereg.json)。

同样的情绪, 指向「我们上一条回复」/「别人的回复」/「无关事件」, 嵌入 10 条留出段落; 生产题面(v1)与收窄题面(v2)
同批各读一次。只调 Jev, 硬上限 400。产物只放指针与读数, 不落原文。
用法: python3 probes/s0_residue_referent.py [--dry-run]
"""
import argparse, collections, hashlib, importlib.util, json, pathlib, re, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
_s = importlib.util.spec_from_file_location("_pv", ROOT / "probes/s0_planted_validity.py"); pv = importlib.util.module_from_spec(_s); _s.loader.exec_module(pv)
S0, shadow, FACETS = pv.S0, pv.shadow, pv.FACETS
PRE = ROOT / "tests/data/s0_residue_referent_prereg.json"
OUT = ROOT / "results/s0_residue_referent.json"
CAP = 400
EXPECT = {"OURS_POS": "正向余温", "OURS_NEG": "负向余温"}
PLANTS = {
    "OURS_POS": ["Your suggestion from our last exchange turned out to be exactly what I needed, so thank you.",
                 "Went back and tried what you told me last time and it made a real difference."],
    "OURS_NEG": ["Frankly the advice you gave me last time made things worse.",
                 "I tried what you said in your last message and it just wasted my afternoon."],
    "OTHER_POS": ["A different commenter in another thread gave me a brilliant tip yesterday.",
                  "My neighbour's advice last week was spot on and cheered me up."],
    "OTHER_NEG": ["Some guy on another forum was really rude to me yesterday.",
                  "My brother's advice last month was useless and it annoyed me."],
    "EVENT_POS": ["Had a lovely dinner with my grandkids last night and I'm still smiling.",
                  "Finally slept a full night and I feel great today."],
    "EVENT_NEG": ["The battery door snapped off this morning and it ruined my mood.",
                  "Got a nasty bill in the mail today and I'm furious."],
}


def embed(body, s):
    if "\n\n" in body:
        a, b = body.split("\n\n", 1); return a + "\n\n" + s + "\n\n" + b
    m = re.search(r"[.!?]\s", body)
    return body[:m.end()] + s + " " + body[m.end():] if m else body + "\n\n" + s


def jobs(passages):
    out = [("baseline", p, None, None, body) for p, body in passages]
    out += [("plant", p, c, i, embed(body, s)) for c, ss in PLANTS.items() for i, s in enumerate(ss) for p, body in passages]
    return out


def score(rows):
    fac = {f["key"]: f for f in FACETS}["情绪余温"]
    rd = lambda r: pv.norm(r["read"]["情绪余温"], fac)
    ok = [r for r in rows if r["read"]]
    pl = [r for r in ok if r["kind"] == "plant"]
    rec = {c: round(sum(rd(r) == v for r in pl if r["cls"] == c) / max(1, sum(r["cls"] == c for r in pl)), 4) for c, v in EXPECT.items()}
    neg = [r for r in pl if r["cls"] not in EXPECT]
    fa = round(sum(rd(r) in ("正向余温", "负向余温") for r in neg) / max(1, len(neg)), 4)
    return {"recovery_pos": rec["OURS_POS"], "recovery_neg": rec["OURS_NEG"], "false_attribution": fa, "n_false_pool": len(neg),
            "false_by_class": {c: dict(collections.Counter(rd(r) for r in neg if r["cls"] == c)) for c in PLANTS if c not in EXPECT},
            "baseline_attribution": sum(rd(r) in ("正向余温", "负向余温") for r in ok if r["kind"] == "baseline"),
            "baseline_dist": dict(collections.Counter(rd(r) for r in ok if r["kind"] == "baseline")),
            "verdict": "PASS" if rec["OURS_POS"] >= 0.90 and rec["OURS_NEG"] >= 0.90 and fa <= 0.05 else "FAIL"}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    passages = shadow.load_passages()[10:20]
    js = jobs(passages)
    assert 2 * len(js) <= CAP
    ledger, lock = {"req": 0}, threading.Lock()
    if a.dry_run:
        key = "dry"
        def post(body, k):
            return {"answers": {q: {"choice": "正向余温" if q == "情绪余温" else "未知", "probabilities": {}} for q in body["questions"]}}, None
    else:
        key = shadow._key()
        def post(body, k):
            with lock:
                ledger["req"] += 1
                if ledger["req"] > CAP:
                    raise RuntimeError("BUDGET_EXCEEDED")
            return S0._post(body, k, retries=1)
    import os
    os.environ["TYPESAFE_API_KEY"] = key          # 仅本进程内, 不打印不落盘
    orig = S0.jev_questions
    def v2q(facets):
        q = orig(facets); q["情绪余温"]["instructions"] = pv.EMOTION_V2; return q
    res_arms, raw = {}, []
    for arm, qf in (("v1", orig), ("v2", v2q)):
        S0.jev_questions = qf
        def one(j):
            kind, p, c, i, body = j
            read, _pr, err = S0.s0_jev_read(body[:2000], FACETS, post=lambda b, k=key: post(b, key))
            return {"arm": arm, "kind": kind, "ptr": p, "cls": c, "phrasing": i, "read": read, "err": err}
        with ThreadPoolExecutor(max_workers=4) as ex:
            rows = list(ex.map(one, js))
        res_arms[arm] = score(rows); raw += rows
    S0.jev_questions = orig
    res = {"block": "S0_RESIDUE_REFERENT_HELDOUT", "run_at": "2026-09-29", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "emotion_v2_sha": hashlib.sha256(pv.EMOTION_V2.encode()).hexdigest()[:16],
           "passages": [p for p, _ in passages], "requests": ledger["req"],
           "errors": dict(collections.Counter(r["err"] for r in raw if r["err"])), "arms": res_arms,
           "raw": raw}
    if not a.dry_run:
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "errors", "arms")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
