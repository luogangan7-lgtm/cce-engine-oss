# -*- coding: utf-8 -*-
"""对齐出口 · 【做】条目缺席一侧(VIOLATED = 没做)的构造稿准入(预注册 tests/data/align_atoms_tri_do_prereg.json)。

11 条 V3【做】条目, 按结分 7 组 × 34 条底稿(V3 确认集两次面板都判「没做」的)× 每条目 1 句「做了但说法绕」的植入句
(F1 改写 / F2 跨两句 / F3 绕开锚词); 同结两条目共用一次调用(联合植入, 见预注册 ★joint_planting)。
错误 = 植入后面板仍判「没做」(假违反); 调用失败按假违反计。ADOPTED ⇔ 跑满 34 且 CP 单侧 95% 上界 <= 0.10。
真实请求走 cce_request_budget 作用域(含重试逐次计数, 上限 250); key 只从环境变量 TYPESAFE_API_KEY 取。
选底稿 / 植入位置 / 判官 / 计分口径复用禁令轮 probes/align_atoms_tri.py, 只换缺席侧与联合植入。
"""
import argparse, collections, hashlib, importlib.util, json, os, pathlib, sys
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import cce_align_atoms as AT              # noqa: E402
import cce_request_budget as RB           # noqa: E402
_s = importlib.util.spec_from_file_location("_tri_base", ROOT / "probes/align_atoms_tri.py"); TRI = importlib.util.module_from_spec(_s); _s.loader.exec_module(TRI)
PRE = ROOT / "tests/data/align_atoms_tri_do_prereg.json"
OUT, BUDGET_STATE = ROOT / "results/align_atoms_tri_do.json", ROOT / "results/align_atoms_tri_do_budget.json"
AUTH, CAP, N, PER_PLANT, MAX_UCB = "align_tri_do_2026-10-01", 250, 34, 12, 0.10
ABSENT = "unsatisfied"      # 【做】的缺席侧: 面板判「没做」


def prereg():
    return json.loads(PRE.read_text(encoding="utf-8"))


def pick_bases(v3, knot, keys):
    """V3 原文与逐字重读两次面板, 该结所列条目全 = 「没做」的前 N 条(按 base_pointers 顺序)。"""
    idx = [k.split("#")[1] for k in keys]
    pan = {(r["ptr"], r["kind"]): r["atoms"] or {} for r in v3["raw"] if r["knot"] == knot and r["kind"] in ("orig", "restore")}
    return [p for p in v3["base_pointers"]
            if all(((pan.get((p, kd)) or {}).get(i) or {}).get("panel") == ABSENT for kd in ("orig", "restore") for i in idx)][:N]


def jobs(pre, v3, texts):
    out = []
    for knot, keys in pre["knots"].items():
        for n, ptr in enumerate(pick_bases(v3, knot, keys)):
            t, plants = texts[ptr], []
            for k, key in enumerate(keys):            # k = 1 取相反位置: n + PER_PLANT 翻转 (n // 12) % 2
                j = n % PER_PLANT; t, pos = TRI.plant(t, pre["plants"][key][j], n + k * PER_PLANT)
                plants.append({"key": key, "plant": j, "family": "F%d" % (j // 4 + 1), "pos": pos})
            out.append({"knot": knot, "ptr": ptr, "n": n, "plants": plants, "text": t})
    return out


def score(rows, items):
    per = {}
    for key in items:
        rs = [r for r in rows if r["key"] == key]
        err = sum((r["panel"] or "call_failed") in (ABSENT, "call_failed") for r in rs)
        ucb = TRI.MON.clopper_pearson(err, len(rs), 0.10)[1] if rs else 1.0
        share = lambda sub: dict(collections.Counter(r["panel"] or "call_failed" for r in sub))
        per[key] = {"n": len(rs), "false_violated": err, "false_violated_ucb": ucb, "panel_counts": share(rs),
                    "by_family": {f: share([r for r in rs if r["family"] == f]) for f in ("F1", "F2", "F3")},
                    "by_position": {p: share([r for r in rs if r["pos"] == p]) for p in ("append", "after_first")},
                    "single_votes": dict(collections.Counter(v for r in rs for v in (r["votes"] or []))),
                    "verdict": "ADOPTED" if len(rs) == N and ucb <= MAX_UCB else "NOT_ADOPTED"}
    return per, {"items": len(per), "adopted": sum(v["verdict"] == "ADOPTED" for v in per.values())}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    pre, v3 = prereg(), json.loads(TRI.V3.read_text(encoding="utf-8"))
    assert sorted(k for ks in pre["knots"].values() for k in ks) == sorted(pre["items"])
    js = jobs(pre, v3, TRI.base_texts())
    assert len(js) == N * len(pre["knots"]) <= CAP and all(AT.complete_scan(j["text"]) for j in js)
    if a.dry_run:
        os.environ["TYPESAFE_API_KEY"] = "dry"
        post = lambda body, key: ({"answers": {q: {"choice": "unclear", "probabilities": {}} for q in body["questions"]}}, None)
    else:
        assert os.environ.get("TYPESAFE_API_KEY", "").strip(), "TYPESAFE_API_KEY 未设置"
        RB.open_scope(AUTH, CAP, BUDGET_STATE); post = None        # S0._post 每次尝试(含重试)都过 reserve_in_scope

    def one(j):
        try:
            r, err = AT.judge_jev_v3(j["knot"], j["text"], post=post)
        except RB.BudgetExceeded:
            r, err = None, "BUDGET_EXCEEDED"
        out = []
        for p in j["plants"]:
            x = (r or {}).get(int(p["key"].split("#")[1])) or {}
            out.append({"ptr": j["ptr"], "n": j["n"], **p, "panel": x.get("panel"), "votes": x.get("votes"), "err": err})
        return out
    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = [x for rs in ex.map(one, js) for x in rs]
    per, summ = score(rows, pre["items"])
    res = {"block": "ALIGN_ATOMS_TRI_DO", "judge": "jev_v3", "run_at": "2026-10-01", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(), "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "questions_sha256": hashlib.sha256(json.dumps({k: AT.jev_questions_v3(k) for k in pre["knots"]}, sort_keys=True).encode()).hexdigest(),
           "calls_planned": len(js), "requests": (RB.scope_status() or {}).get("used") if not a.dry_run else 0,
           "errors": dict(collections.Counter(r["err"] for r in rows if r["err"])), "summary": summ, "per_atom": per, "raw": rows}
    if not a.dry_run:
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("calls_planned", "requests", "errors", "summary")}, ensure_ascii=False))
    for k, v in per.items():
        print(k, v["verdict"], "false_violated %d/%d ucb %.3f" % (v["false_violated"], v["n"], v["false_violated_ucb"]), v["by_family"], v["by_position"])


if __name__ == "__main__":
    main()
