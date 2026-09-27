# -*- coding: utf-8 -*-
"""蒸馏第二轮的头、坐标导出与分析闸(零 API、零模型; 需 numpy + scipy, 本机跑):
变量替换求解 == 直接原问题求解 · 全零类也收敛且有限 · 留出帖绝不进自己的任何拟合与预处理 · 并列规则 ·
跨度坐标对只依赖内积的岭头无损、复跑行坐标相同 · 合成两腿 + 合成老师端到端走到冻结判决, 置换/植入/学习曲线都产出。产物不写 results/。"""
import copy
import hashlib
import importlib.util
import json
import pathlib

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")
from scipy.optimize import minimize  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/jev_distill2_prereg.json"
S = ROOT / "experiments/jev/suites"


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _load(rel, name):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def _jsonl(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def _primal(H, Z, n_l, dom, Y, w, lam_l, lam_h):
    n, D = Z.shape; K = Y.shape[1]
    lam = np.concatenate([np.full(n_l, lam_l), np.full(D - n_l, lam_h)]); ws = w / w.sum()

    def f(t):
        W = t[:K * D].reshape(K, D); b = t[K * D:K * D + K]; d = t[K * D + K:]
        L = Z @ W.T + b + dom[:, None] * d; lp = L - H._lse(L); G = (np.exp(lp) - Y) * ws[:, None]
        return (-(ws[:, None] * Y * lp).sum() + .5 * (lam * W * W).sum() + .5 * H.LAM_B * (b @ b + d @ d),
                np.concatenate([(G.T @ Z + lam * W).ravel(), G.sum(0) + H.LAM_B * b, (G * dom[:, None]).sum(0) + H.LAM_B * d]))
    r = minimize(f, np.zeros(K * D + 2 * K), jac=True, method="L-BFGS-B", options={"maxiter": 100000, "gtol": 1e-11, "ftol": 1e-16})
    return r.x[:K * D].reshape(K, D), r.x[K * D:K * D + K], r.x[K * D + K:]


def test_substituted_solver_equals_the_primal_problem_and_an_empty_class_stays_finite():
    H = _load("probes/jev_distill2_vs_retest.py", "_d2a")
    rng = np.random.default_rng(0); K, n, D, nl = 5, 30, 50, 8
    Z = rng.normal(size=(n, D)); dom = (rng.random(n) < .5).astype(float); w = rng.random(n) + .5
    Y = rng.dirichlet(np.ones(K), n); Y[:, 4] = 0; Y /= Y.sum(1, keepdims=True)          # 第 5 类在任何一行都没有质量
    for lam_l, lam_h in ((1e-2, 1e-3), (1.0, 10.0), (1e-4, 1e-5)):
        (W, b, d), g = H.fit(Z, nl, dom, Y, w, lam_l, lam_h)
        W2, b2, d2 = _primal(H, Z, nl, dom, Y, w, lam_l, lam_h)
        assert g <= H.GRAD_TOL and np.isfinite(b).all() and np.abs(b).max() < 1e4
        assert np.abs(H.predict((W, b, d), Z, dom) - H.predict((W2, b2, d2), Z, dom)).max() < 5e-6


def test_the_held_out_post_never_enters_its_own_fits_or_preprocessing(monkeypatch):
    H = _load("probes/jev_distill2_vs_retest.py", "_d2b")
    monkeypatch.setattr(H, "LAM_L", (1.0,)); monkeypatch.setattr(H, "LAM_H", (1.0,)); monkeypatch.setattr(H, "W_T", (0.0, 1.0))
    rng = np.random.default_rng(1); K = 4
    F = H.Facet(rng.normal(size=(108, 6)), [rng.normal(size=(108, 9))], rng.dirichlet(np.ones(K), 42), np.eye(K)[rng.integers(0, K, 42)],
                rng.dirichlet(np.ones(K), 66), rng.normal(size=(10, 6)), [rng.normal(size=(10, 9))], list(range(0, 40, 4)), [str(i) for i in range(66)])
    seen, real = [], H.fit_rows
    monkeypatch.setattr(H, "fit_rows", lambda F_, tr, *a, **k: (seen.append(list(tr)), real(F_, tr, *a, **k))[1])
    F.groups_E[16] = F.groups_E[41] = "twin"                                           # 预注册的验收集近重复对
    for i in (0, 13, 16, 41):
        seen.clear()
        r = H.outer_fold(F, i, "P", F.YE, F.YT)
        assert seen and all(j not in tr for tr in seen for j in F.group_of(i)) and len(r["p"]) == K
    folds = H.inner_folds(F, [j for j in range(42) if j != 0])
    assert any(16 in f and 41 in f for f in folds)                                       # 内层同组不拆
    assert H._pick({(1, 1, 0): 0.5, (1, 10, 0): 0.5 + 1e-12, (10, 1, 1): 0.6}) == (1, 10, 0)     # 并列取更大 λ_h


def test_span_coordinates_are_lossless_for_inner_product_heads_and_small():
    X = _load("experiments/jev/hidden_export.py", "_hx")
    rng = np.random.default_rng(2)
    main = [f"m{i}" for i in range(20)]
    rows = []
    for q in ("f1", "f2"):
        for iid in main + ["rep-m3", "smoke"]:
            base = "m3" if iid == "rep-m3" else iid
            v = rng.normal(size=64) if iid != "rep-m3" else None
            rows.append({"item_id": iid, "question_id": q, "row_sha256": base + q, "vectors": {"final": v}})
    for r in rows:                                          # 复跑行 = 基帖同一向量
        if r["item_id"] == "rep-m3":
            r["vectors"]["final"] = next(x for x in rows if x["item_id"] == "m3" and x["question_id"] == r["question_id"])["vectors"]["final"]
    for r in rows:
        r["vectors"] = {k: [float(x) for x in v] for k, v in r["vectors"].items()}
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        meta = X.write_span_coords(rows, main, d)
        got = {(r["item_id"], r["question_id"]): r for r in _jsonl(pathlib.Path(d) / "hidden_coords.jsonl")}
        assert meta["coords_sha256"] == _sha(pathlib.Path(d) / "hidden_coords.jsonl")
    for q in ("f1", "f2"):
        V = np.array([r["vectors"]["final"] for r in rows if r["question_id"] == q and r["item_id"] in main])
        Zs = (V - V.mean(0)) / V.std(0)
        C = np.array([got[(m, q)]["blocks"]["final"]["c"] for m in main])
        assert np.abs(Zs @ Zs.T - C @ C.T).max() < 1e-6                                 # 格拉姆几何不变 ⇒ 岭/逻辑回归的预测不变
        assert got[("rep-m3", q)]["blocks"] == got[("m3", q)]["blocks"] and max(got[(m, q)]["blocks"]["final"]["resid"] for m in main) < 1e-6
    per_row = np.mean([len(json.dumps(v)) for v in got.values()])
    assert per_row * 599 * 3 / 64 * 107 / 20 < 8e6                                      # 按 599 行 × 3 块 × r≈107 外推 < 8 MB


def _fake_run(tmp_path, H, pre):
    """两条腿: 行 = 两份归档的真实行(同 row_sha256、同候选), 字母 logits 与隐状态为随机数; 坐标由真写入器产生。"""
    X = _load("experiments/jev/hidden_export.py", "_hx2")
    rng = np.random.default_rng(3)
    items = _jsonl(S / "s0-distill2-v1.jsonl")
    main = [it["item_id"] for it in items if "text_ref" in it and not it["item_id"].startswith("rep-")]
    run = tmp_path / "99"
    for m in H.MODELS:
        arch = {(r["item_id"], r["question_id"]): r for a in (H.ARCH_EXAM, H.ARCH_TRAIN) for r in _jsonl(a / m / "predictions.jsonl")}
        vec, preds, hid = {}, [], []
        for (iid, q), r in arch.items():
            base = iid[4:] if iid.startswith("rep-") else iid
            if (base, q) not in vec:
                blocks = [f"b{k}" for k in pre["★GitHub(冻结)"]["隐状态块号"][m]] + ["final"]
                vec[(base, q)] = ({k: rng.normal(size=32).tolist() for k in blocks}, rng.normal(size=len(r["candidate_ids"])).tolist())
            v, lg = vec[(base, q)]
            preds.append(dict(r, raw_candidate_logits=lg))
            hid.append({"item_id": iid, "question_id": q, "row_sha256": r["identities"]["row_sha256"], "vectors": copy.deepcopy(v)})
        d = run / m; d.mkdir(parents=True)
        rep0 = json.loads((H.ARCH_EXAM / m / "report.json").read_text(encoding="utf-8"))
        ids = copy.deepcopy(rep0["identities"]); ids["permit_id"] = pre["★GitHub(冻结)"]["permit_id"]; ids["run"]["GITHUB_RUN_ID"] = "99"
        ids["adapter_sha256"] = pre["★脚本(冻结)"]["adapter_sha256"]
        plan = {"n_layers": 36 if m == "qwen3-4b-2507" else 32, "blocks": pre["★GitHub(冻结)"]["隐状态块号"][m]}
        ids["backend_effective"]["hidden_export"] = plan
        (d / "report.json").write_text(json.dumps({"execution_status": "SUCCEEDED", "coverage_status": "COMPLETE", "suite_sha256": _sha(H.SUITE),
                                                   "suite_manifest": {"prereg_sha256": _sha(PRE)}, "identities": ids,
                                                   "hidden_export": {"plan": plan}}), encoding="utf-8")
        with open(d / "predictions.jsonl", "w", encoding="utf-8") as fh:
            for r in preds:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        X.write_span_coords(hid, main, d)
    T = _load("probes/jev_distill2_teacher.py", "_t2x")
    work, ident = T.preflight()
    cand = {r["question_id"]: r["candidate_ids"] for r in _jsonl(H.ARCH_EXAM / H.MODELS[0] / "predictions.jsonl")}
    rows = []
    for p_, p in work:
        ch = {q: c[int(rng.integers(len(c)))] for q, c in cand.items()}
        rows.append(dict(p, **{"pass": p_}, ok=True, err=None, choice=ch, probs={q: {x: (0.8 if x == ch[q] else 0.2 / (len(c) - 1)) for x in c} for q, c in cand.items()}))
    tf = tmp_path / "t2.json"
    tf.write_text(json.dumps({"status": "complete", "question_sha": pre["★老师(冻结)"]["question_sha"], "rows": rows, **ident}, ensure_ascii=False), encoding="utf-8")
    return run, tf


def test_end_to_end_on_synthetic_legs_reaches_the_frozen_verdict_with_all_controls(tmp_path, monkeypatch):
    H = _load("probes/jev_distill2_vs_retest.py", "_d2c")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    for k, v in (("LAM_L", (1.0,)), ("LAM_H", (1.0,)), ("W_T", (0.0, 1.0)), ("PERM_SEEDS", 1), ("LC_SIZES", (20,)), ("LC_SEEDS", 1), ("WORKERS", 1)):
        monkeypatch.setattr(H, k, v)
    run, tf = _fake_run(tmp_path, H, pre)
    monkeypatch.setattr(H, "TEACHER2", tf)
    monkeypatch.setattr(H, "out_path", lambda tag: tmp_path / f"r_{tag}.json")
    monkeypatch.setattr(H, "SUMMARY", tmp_path / "summary.json")
    rc = H.main([str(run)])
    s = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    errs = [e for e in s["★前置错误"] if not e.startswith("analysis script sha")]
    assert rc == 0 and errs == [], s["★前置错误"]
    assert set(s["readers"]) == {"P", "S1", "S2", "S3"} and all(r["nonconverged"] is False for r in s["readers"].values())
    for rd in s["readers"]:
        d = json.loads((tmp_path / f"r_{rd}.json").read_text(encoding="utf-8"))
        assert d["★同 run 复跑"]["pass"] and d["★同 run 复跑"]["pairs"] == 50
    assert set(s["★置换闸"]) == set(pre["★面"]["模型读"]) and set(s["★植入老师功效"]) == set(pre["★面"]["模型读"])
    assert s["★决策图"] and s["★预测核对"]["Q8_permutation_gate_passes"] in (True, False) and "per_facet" in s["★学习曲线(描述)"]
    # 行 sha 与归档不符 ⇒ 前置不成立, 不出判决
    p = run / H.MODELS[0] / "predictions.jsonl"; rows = _jsonl(p); rows[0]["identities"]["row_sha256"] = "0" * 64
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert H.main([str(run)]) == 1
    s = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert s["overall"].startswith("前置不成立") and any("row_sha256" in e for e in s["★前置错误"])
    # 一条腿在 GitHub 上失败 ⇒ 预注册的单腿预案(不是前置不成立)
    p.write_text("".join(json.dumps(dict(r, identities=dict(r["identities"], row_sha256=a["identities"]["row_sha256"])), ensure_ascii=False) + "\n"
                         for r, a in zip(rows, _jsonl(H.ARCH_EXAM / H.MODELS[0] / "predictions.jsonl") + _jsonl(H.ARCH_TRAIN / H.MODELS[0] / "predictions.jsonl"))),
                 encoding="utf-8")
    rp = run / H.MODELS[1] / "report.json"; rj = json.loads(rp.read_text(encoding="utf-8")); rj["execution_status"] = "FAILED"; rp.write_text(json.dumps(rj), encoding="utf-8")
    assert H.main([str(run)]) == 0
    s = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert s["★单腿预案"] and H.MODELS[1] in s["★单腿预案"] and s["readers"]["P"]["nonconverged"] is False


def test_leg_preconditions_catch_a_foreign_adapter_or_a_wrong_layer_plan(tmp_path):
    H = _load("probes/jev_distill2_vs_retest.py", "_d2d")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    run, _tf = _fake_run(tmp_path, H, pre)
    m = H.MODELS[0]
    assert H.leg_errors(m, *H.load_leg(run, m)[:4], H.load_leg(run, m)[4], pre, run) == []
    rp = run / m / "report.json"; good = json.loads(rp.read_text(encoding="utf-8"))
    for mutate, needle in ((lambda r: r["identities"].__setitem__("adapter_sha256", "0" * 64), "adapter"),
                           (lambda r: r["hidden_export"]["plan"].__setitem__("blocks", [3, 5]), "hidden export blocks"),
                           (lambda r: r["identities"]["backend_effective"].__setitem__("threads", 4), "threads")):
        bad = copy.deepcopy(good); mutate(bad); rp.write_text(json.dumps(bad), encoding="utf-8")
        e = H.leg_errors(m, *H.load_leg(run, m)[:4], H.load_leg(run, m)[4], pre, run)
        assert any(needle in x for x in e), (needle, e)
    rp.write_text(json.dumps(good), encoding="utf-8")
