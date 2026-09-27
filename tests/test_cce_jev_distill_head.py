# -*- coding: utf-8 -*-
"""蒸馏测试的头与分析闸(零 API、零模型; 需 numpy + scipy, 本机跑): 头确定性且学得会 · 近重复同组留出 ·
端到端(合成老师 + 合成训练特征 + 真考场归档)两族都走到冻结判决 · 老师漂移行碰不到头 · 可比性/溯源前置真会拦。
产物不写 results/。"""
import copy
import hashlib
import importlib.util
import json
import pathlib
import random

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/jev_distill_prereg.json"
S = ROOT / "experiments/jev/suites"
EVAL = ROOT / "archive/36316049972"


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _load(rel, name):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def _jsonl(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def test_head_is_deterministic_and_learns_separable_data():
    H = _load("probes/jev_distill_vs_retest.py", "_h1")
    rng = random.Random(0)
    X = np.array([[rng.gauss(3 * (i % 3 == j), 0.3) for j in range(3)] for i in range(30)])
    Y = np.array([[1.0 if i % 3 == j else 0.0 for j in range(3)] for i in range(30)])
    h1, h2 = H.train_head(X, Y), H.train_head(X, Y)
    assert (h1["W"] == h2["W"]).all() and (h1["b"] == h2["b"]).all() and h1["lambda"] in H.LAMBDAS
    P = H.predict(h1, X)
    assert abs(P.sum(axis=1) - 1).max() < 1e-12 and (P.argmax(axis=1) == Y.argmax(axis=1)).all()
    assert (H.logsoftmax([1.0, 2.0, 3.0]) == H.logsoftmax([11.0, 12.0, 13.0])).all()   # 整行平移不改特征


def test_near_duplicates_are_left_out_together(monkeypatch):
    H = _load("probes/jev_distill_vs_retest.py", "_h2")
    sizes, real = [], H.fit
    monkeypatch.setattr(H, "fit", lambda X, Y, lam: (sizes.append(len(X)), real(X, Y, lam))[1])
    monkeypatch.setattr(H, "LAMBDAS", (1.0,))
    X = np.arange(12.0).reshape(6, 2); Y = np.eye(2)[[0, 1, 0, 1, 0, 1]]
    H.train_head(X, Y, ["g", "g", "a", "b", "c", "d"])
    assert sizes == [4, 5, 5, 5, 5, 6]                               # 5 组留一 + 全量; 同组两行一起留出


def _fixture(tmp_path, H, pre, drift_probs=None):
    tr = _jsonl(S / "s0-distill-train-v1.jsonl")
    ev = {m: _jsonl(EVAL / m / "predictions.jsonl") for m in H.VARIANTS["C"]}
    cand = {r["question_id"]: r["candidate_ids"] for r in ev["qwen3-4b-2507"]}
    qsha = next(r["questions_sha256"] for r in ev["qwen3-4b-2507"] if r["item_id"].startswith("redd"))
    rng = random.Random(1)
    rows = []
    for it in tr:
        ch = {q: rng.choice(c) for q, c in cand.items()}
        rows.append(dict(it["text_ref"], split="train", ok=True, err=None, choice=ch,
                         probs={q: {x: (0.7 if x == ch[q] else 0.3 / (len(c) - 1)) for x in c} for q, c in cand.items()}))
    T = _load("probes/jev_distill_teacher.py", "_h_t")
    for p in T.drift_pointers():
        rows.append(dict(p, split="drift", ok=True, err=None, choice={q: c[0] for q, c in cand.items()},
                         probs=drift_probs or {q: {c[0]: 1.0} for q, c in cand.items()}))
    teacher = {"status": "complete", "question_sha": pre["★老师(冻结)"]["question_sha"], "model": pre["★老师(冻结)"]["model"],
               "prereg_sha256": _sha(PRE), "teacher_script_sha256": pre["★分析脚本(冻结)"]["teacher_sha256"],
               "training_pointer_set_sha256": pre["★训练集(冻结)"]["pointer_set_sha256"], "rows": rows}
    tf = tmp_path / "teacher.json"; tf.write_text(json.dumps(teacher, ensure_ascii=False), encoding="utf-8")
    train_dir = tmp_path / "train"
    for m in H.VARIANTS["C"]:
        d = train_dir / m; d.mkdir(parents=True)
        rep = json.loads((EVAL / m / "report.json").read_text(encoding="utf-8"))
        rep = {"execution_status": "SUCCEEDED", "coverage_status": "COMPLETE", "suite_sha256": _sha(S / "s0-distill-train-v1.jsonl"),
               "suite_manifest": {"prereg_sha256": _sha(PRE)}, "identities": copy.deepcopy(rep["identities"])}
        rep["identities"]["run"]["GITHUB_RUN_ID"] = "1"; rep["identities"]["backend_effective"]["load_s"] = 9.9
        (d / "report.json").write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
        with open(d / "predictions.jsonl", "w", encoding="utf-8") as fh:
            for it in tr:
                for q, c in cand.items():
                    fh.write(json.dumps({"item_id": it["item_id"], "question_id": q, "candidate_ids": c, "questions_sha256": qsha,
                                         "raw_candidate_logits": [rng.gauss(0, 3) for _ in c], "identities": {"row_sha256": "x"}}, ensure_ascii=False) + "\n")
    return tf, train_dir


def test_end_to_end_both_families_reach_the_frozen_verdict_and_the_gates_bite(tmp_path, monkeypatch):
    H = _load("probes/jev_distill_vs_retest.py", "_h3")
    monkeypatch.setattr(H, "LAMBDAS", (0.1,))
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    X_ = H.load_frozen(pre)
    tf, train_dir = _fixture(tmp_path, H, pre)
    monkeypatch.setattr(H, "TEACHER", tf)
    for fam, var in (("T", "C"), ("X", "A")):
        doc = H.analyse_reader(fam, var, train_dir, EVAL, pre, X_)
        assert doc["★前置错误"] == [] and doc["★同 run 复跑"]["pass"] and doc["★同 run 复跑"]["pairs"] == 50, (fam, doc["★前置错误"])
        assert all(v is not None for v in doc["verdicts"].values()) and doc["★头条检查"]["threshold"] == 5
        assert set(doc["★功效前置(自老师)"]) == set(pre["★面"]["模型读"]) and all("★功效标记" in v for v in doc["per_facet"].values())
        units = [u for h in doc["★头"].values() for u in h["units"]]
        assert all(u["n_train"] == (66 if fam == "T" else 36) for u in units) and len(units) == 5 * (1 if fam == "T" else 7)
        if fam == "T":
            heads_t = doc["★头"]
    # 老师漂移行碰不到头: 把 drift 行改成任意分布, T 族的头逐位不变
    (tmp_path / "d2").mkdir()
    tf2, _ = _fixture(tmp_path / "d2", H, pre, drift_probs={q: {"未知": 1.0} for q in pre["★面"]["模型读"]})
    monkeypatch.setattr(H, "TEACHER", tf2)
    assert H.analyse_reader("T", "C", train_dir, EVAL, pre, X_)["★头"] == heads_t
    # 溯源: 老师读数不是在当前预注册下取得的 ⇒ 前置不成立
    t = json.loads(tf.read_text(encoding="utf-8")); t["prereg_sha256"] = "0" * 64; tf.write_text(json.dumps(t), encoding="utf-8")
    monkeypatch.setattr(H, "TEACHER", tf)
    doc = H.analyse_reader("T", "A", train_dir, EVAL, pre, X_)
    assert doc["overall"].startswith("前置不成立") and any("预注册" in e for e in doc["★前置错误"])
    # 可比性: 训练 run 的有效配置与考场不同 ⇒ 前置不成立
    t["prereg_sha256"] = _sha(PRE); tf.write_text(json.dumps(t), encoding="utf-8")
    rp = train_dir / "qwen3-4b-2507" / "report.json"; r = json.loads(rp.read_text(encoding="utf-8"))
    r["identities"]["backend_effective"]["threads"] = 4; rp.write_text(json.dumps(r), encoding="utf-8")
    doc = H.analyse_reader("T", "A", train_dir, EVAL, pre, X_)
    assert doc["overall"].startswith("前置不成立") and any("backend_effective.threads" in e for e in doc["★前置错误"])


def test_main_writes_all_six_readers_and_the_summary(tmp_path, monkeypatch):
    H = _load("probes/jev_distill_vs_retest.py", "_h4")
    monkeypatch.setattr(H, "LAMBDAS", (0.1,))
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    tf, train_dir = _fixture(tmp_path, H, pre)
    monkeypatch.setattr(H, "TEACHER", tf)
    monkeypatch.setattr(H, "out_path", lambda tag: tmp_path / f"r_{tag}.json")
    monkeypatch.setattr(H, "SUMMARY", tmp_path / "summary.json")
    H.main([str(train_dir), str(EVAL)])
    s = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert set(s["readers"]) == {f + v for f in "TX" for v in "ABC"} and all(r["errors"] == [] for r in s["readers"].values()), s["readers"]
    assert all((tmp_path / f"r_{t}.json").is_file() for t in s["readers"])
    assert set(s["★预测核对"]) == set(s["readers"]) and all(v is not None for v in s["★预测核对"].values())
    d = s["★老师漂移(描述, 不进判决)"]
    assert d["n"] == 10 and d["flag"] is not None and set(d) >= {"d_vs_J1", "d_vs_J2", "J1_vs_J2_same_items", "missing_in_J"}
