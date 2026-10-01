# -*- coding: utf-8 -*-
"""对齐出口 · 禁令缺席一侧(SATISFIED)的构造稿准入(预注册 tests/data/align_atoms_tri_prereg.json)。

7 条 V3 禁令 × 36 条底稿(V3 确认集里两次面板都判「未违反」的)× 1 句难例违规(F1 改写 / F2 跨两句 / F3 绕开锚词)。
错误 = 植入后面板仍判「未违反」(假满足); 调用失败按假满足计。ADOPTED ⇔ 跑满 36 且 CP 单侧 95% 上界 <= 0.10。
真实请求走 cce_request_budget 作用域(含重试逐次计数, 上限 300); key 只从环境变量 TYPESAFE_API_KEY 取。
"""
import argparse, collections, hashlib, importlib.util, json, os, pathlib, re, sys
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import cce_align_atoms as AT              # noqa: E402
import cce_request_budget as RB           # noqa: E402
def _load(name, rel):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
V5, MON = _load("_v5", "probes/align_atoms_v5.py"), _load("_mon", "probes/within_js_monitor.py")
PRE = ROOT / "tests/data/align_atoms_tri_prereg.json"
V3 = ROOT / "results/align_atoms_v3.json"
OUT, BUDGET_STATE = ROOT / "results/align_atoms_tri.json", ROOT / "results/align_atoms_tri_budget.json"
AUTH, CAP, N, PER_PLANT, MAX_UCB = "align_tri_2026-10-01", 300, 36, 12, 0.10


def prereg():
    return json.loads(PRE.read_text(encoding="utf-8"))


def base_texts():
    return {p: t for s in range(140, 260, 20) for p, t in V5.natural(s)}


def pick_bases(v3, key):
    """V3 原文与逐字重读两次面板都 = 缺席侧的前 N 条(按 base_pointers 顺序)。"""
    knot, i = key.split("#"); absent = "satisfied"
    pan = {(r["ptr"], r["kind"]): ((r["atoms"] or {}).get(i) or {}).get("panel") for r in v3["raw"] if r["knot"] == knot and r["kind"] in ("orig", "restore")}
    return [p for p in v3["base_pointers"] if pan.get((p, "orig")) == absent and pan.get((p, "restore")) == absent][:N]


def plant(text, sent, n):
    if (n // PER_PLANT) % 2 == 0:
        return text + "\n\n" + sent, "append"
    m = re.search(r"[.!?]\s+", text)
    return (text[:m.end()] + sent + " " + text[m.end():], "after_first") if m else (text + "\n\n" + sent, "append")


def jobs(pre, v3, texts):
    out = []
    for key in pre["items"]:
        for n, ptr in enumerate(pick_bases(v3, key)):
            j = n % PER_PLANT; t, pos = plant(texts[ptr], pre["plants"][key][j], n)
            out.append({"key": key, "ptr": ptr, "n": n, "plant": j, "family": "F%d" % (j // 4 + 1), "pos": pos, "text": t})
    return out


def score(rows, items):
    per = {}
    for key in items:
        rs = [r for r in rows if r["key"] == key]
        vals = [r["panel"] or "call_failed" for r in rs]
        err = sum(v in ("satisfied", "call_failed") for v in vals)
        ucb = MON.clopper_pearson(err, len(rs), 0.10)[1] if rs else 1.0
        share = lambda sub: dict(collections.Counter(r["panel"] or "call_failed" for r in sub))
        per[key] = {"n": len(rs), "false_satisfied": err, "false_satisfied_ucb": ucb, "panel_counts": share(rs),
                    "by_family": {f: share([r for r in rs if r["family"] == f]) for f in ("F1", "F2", "F3")},
                    "by_position": {p: share([r for r in rs if r["pos"] == p]) for p in ("append", "after_first")},
                    "single_votes": dict(collections.Counter(v for r in rs for v in (r["votes"] or []))),
                    "verdict": "ADOPTED" if len(rs) == N and ucb <= MAX_UCB else "NOT_ADOPTED"}
    return per, {"items": len(per), "adopted": sum(v["verdict"] == "ADOPTED" for v in per.values())}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    pre, v3 = prereg(), json.loads(V3.read_text(encoding="utf-8"))
    js = jobs(pre, v3, base_texts())
    assert len(js) == N * len(pre["items"]) <= CAP and all(AT.complete_scan(j["text"]) for j in js)
    if a.dry_run:
        os.environ["TYPESAFE_API_KEY"] = "dry"
        post = lambda body, key: ({"answers": {q: {"choice": "unclear", "probabilities": {}} for q in body["questions"]}}, None)
    else:
        assert os.environ.get("TYPESAFE_API_KEY", "").strip(), "TYPESAFE_API_KEY 未设置"
        RB.open_scope(AUTH, CAP, BUDGET_STATE); post = None        # S0._post 每次尝试(含重试)都过 reserve_in_scope

    def one(j):
        knot, i = j["key"].split("#")
        try:
            r, err = AT.judge_jev_v3(knot, j["text"], post=post)
        except RB.BudgetExceeded as e:
            r, err = None, "BUDGET_EXCEEDED"
        x = (r or {}).get(int(i)) or {}
        return {k: j[k] for k in ("key", "ptr", "n", "plant", "family", "pos")} | {"panel": x.get("panel"), "votes": x.get("votes"), "err": err}
    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, js))
    per, summ = score(rows, pre["items"])
    res = {"block": "ALIGN_ATOMS_TRI", "judge": "jev_v3", "run_at": "2026-10-01", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(), "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "questions_sha256": hashlib.sha256(json.dumps({k.split("#")[0]: AT.jev_questions_v3(k.split("#")[0]) for k in pre["items"]}, sort_keys=True).encode()).hexdigest(),
           "requests": (RB.scope_status() or {}).get("used") if not a.dry_run else 0,
           "errors": dict(collections.Counter(r["err"] for r in rows if r["err"])), "summary": summ, "per_atom": per, "raw": rows}
    if not a.dry_run:
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "errors", "summary")}, ensure_ascii=False))
    for k, v in per.items():
        print(k, v["verdict"], "false_satisfied %d/%d ucb %.3f" % (v["false_satisfied"], v["n"], v["false_satisfied_ucb"]), v["by_family"], v["by_position"])


if __name__ == "__main__":
    main()
