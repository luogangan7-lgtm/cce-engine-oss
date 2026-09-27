# -*- coding: utf-8 -*-
"""hf_choice 候选对比的预注册与包装脚本之闸(零 API、零模型)。

守: ① 预注册的判决数值/归一化/主判据/输入与题目/面 与 Decider 预注册逐字相同 ② 冻结脚本与包装脚本 sha 冻结 ③ suite 清单绑预注册 sha,
42 条输入集不变, 与 s0-compare-v1 只差 owner 裁定过的那一个 smoke gold ④ 回放: 把 Decider 的归档预测当作「候选」喂给包装脚本,
必须逐面复现冻结的 Decider 判决(5 面 不同读者, 触发事件 38); 把 Jev 轮 1 标签当作候选必须全部「可替代」 —— 包装层没有改判据。
产物写临时目录, 不写 results/。"""
import hashlib
import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/jev_candidate_vs_retest_prereg.json"
DPRE = ROOT / "tests/data/jev_decider_vs_retest_prereg.json"
S = ROOT / "experiments/jev/suites"


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _load(p, name):
    s = importlib.util.spec_from_file_location(name, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def test_prereg_copies_every_frozen_rule_verbatim():
    c, d = json.loads(PRE.read_text(encoding="utf-8")), json.loads(DPRE.read_text(encoding="utf-8"))
    for k in ("★面", "★输入与题目(冻结)", "★归一化", "★主判据", "★不确定性"):                    # 机器读的 / 定义规则的键: 逐字相同
        assert c[k] == d[k], k
    rc, rd = c["★★★判决规则(测量前冻结)"], d["★★★判决规则(测量前冻结)"]
    assert rc["数值"] == rd["数值"] and all(rc[k] == rd[k] for k in ("测不出", "可替代", "不同读者", "不可判", "D vs MiniMax"))
    assert rc["整体"].startswith(rd["整体"]) and "T=1.0" in rc["前置"] and "T=1.3" not in rc["前置"]      # 前置/混杂是臂相关的, 不许照抄 Decider
    assert not any("English only" in x for x in c["★混杂(不可在本轮分离)"]) and c["★修订记录(测量前)"]
    assert c["★确定性(前置)"]["tol_abs_dp"] == d["★确定性(前置)"]["tol_abs_dp"] and c["★确定性(前置)"]["同 run 复跑"] == d["★确定性(前置)"]["同 run 复跑"]
    assert c["★臂"]["D"]["T"] == 1.0 and c["★臂"]["D"]["prompt_spec"] == "cce.jev.hf_choice.prompt.v1"
    assert c["★★★判决规则(测量前冻结)"]["数值"]["replaceable_max_d"] == 4 and "0 次 TypeSafe/MiniMax" in c["★臂"]["★不新调付费接口"]
    assert set(x for x in d["★★★不得据此说"] if not x.startswith(("D 在 情绪余温", "Decider 总体上"))) <= set(c["★★★不得据此说"])
    assert c["★预测(先写, 看数据前)"] and c["★头条检查(预注册)"]["面"] == "触发事件"


def test_frozen_script_and_wrapper_shas_are_pinned():
    c = json.loads(PRE.read_text(encoding="utf-8"))
    assert _sha(ROOT / "probes/jev_decider_vs_retest.py") == c["★分析脚本(冻结)"]["sha256"]
    assert _sha(ROOT / "probes/jev_candidate_vs_retest.py") == c["★分析脚本(冻结)"]["wrapper_sha256"], \
        "包装脚本改过: 若是看数据后的 bug 修复, 必须在 ★修订记录 登记并在结果里如实报 sha 不等"


def test_suite_binds_the_prereg_and_differs_from_compare_v1_only_by_the_adjudicated_gold():
    m = json.loads((S / "s0-compare-llm-v1.manifest.json").read_text(encoding="utf-8"))
    assert m["prereg_sha256"] == _sha(PRE) and m["suite_sha256"] == _sha(S / "s0-compare-llm-v1.jsonl") and m["policy"] == "cpu_compare_llm.json"
    a = [json.loads(l) for l in (S / "s0-compare-v1.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    b = [json.loads(l) for l in (S / "s0-compare-llm-v1.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert [x["item_id"] for x in a] == [x["item_id"] for x in b]
    diffs = [(x["item_id"], k) for x, y in zip(a, b) for k in set(x) | set(y) if x.get(k) != y.get(k)]
    assert diffs == [("smoke-01-clear-signal", "expected")], diffs
    assert b[[x["item_id"] for x in b].index("smoke-01-clear-signal")]["expected"]["触发事件"] == ["受挫/出故障", "刚花过钱"]


def _run_dir(tmp, preds):
    d = tmp / "run"; d.mkdir(parents=True)
    (d / "predictions.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in preds), encoding="utf-8")
    src = json.loads((ROOT / "experiments/jev/models/qwen3-4b-2507/model.source.lock.json").read_text(encoding="utf-8"))
    bc = src["backend_config"]
    rep = {"execution_status": "SUCCEEDED", "coverage_status": "COMPLETE", "suite_sha256": _sha(S / "s0-compare-llm-v1.jsonl"),
           "suite_manifest": {"prereg_sha256": _sha(PRE)},
           "identities": {"backend_effective": {"temperature": 1.0, "repo_id": src["repo_id"], "revision": src["revision"], "backend": "hf_choice",
                                                "prompt_spec": "cce.jev.hf_choice.prompt.v1", "compute_dtype": "torch.float32", "storage_dtype": "torch.bfloat16",
                                                "threads": 3, "letters": bc["letters"]},
                          "model_key": "qwen3-4b-2507", "source_lock_sha256": _sha(ROOT / "experiments/jev/models/qwen3-4b-2507/model.source.lock.json"),
                          "assets_lock_sha256": "missing", "run": {"GITHUB_RUN_ID": "replay"}, "cgroup_limits": {"cpu_model": "replay"}}}
    (d / "report.json").write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
    return d


@pytest.fixture
def wrapper(tmp_path, monkeypatch):
    W = _load(ROOT / "probes/jev_candidate_vs_retest.py", "_cand_wrap")
    monkeypatch.setattr(W, "out_path", lambda key: tmp_path / f"out_{key}.json")
    return W


def _decider_preds():
    arch = ROOT / "archive/36272175531"
    f = next(p for p in arch.iterdir() if p.name.endswith("predictions.jsonl"))
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_replay_decider_predictions_as_a_candidate_reproduces_the_frozen_verdicts(tmp_path, wrapper):
    frozen = json.loads((ROOT / "results/jev_decider_vs_retest.json").read_text(encoding="utf-8"))
    wrapper.main(["qwen3-4b-2507", str(_run_dir(tmp_path, _decider_preds()))])
    doc = json.loads((tmp_path / "out_qwen3-4b-2507.json").read_text(encoding="utf-8"))
    assert doc["★包装前置错误"] == [] and doc["★前置"]["errors"] == [], (doc["★包装前置错误"], doc["★前置"]["errors"])
    assert doc["verdicts"] == frozen["verdicts"] and all(v == "不同读者" for v in doc["verdicts"].values())
    for k, row in frozen["per_facet"].items():
        assert doc["per_facet"][k]["pairs"]["D~J1"]["d"] == row["pairs"]["D~J1"]["d"], k
    assert doc["★头条检查"]["max_d"] == 38 and doc["★头条检查"]["result"].startswith("不能判可替代")
    assert doc["analysis_script_sha256"] == doc["analysis_script_sha256_at_freeze"] and doc["wrapper_sha256"] == doc["wrapper_sha256_at_freeze"]


def test_replay_a_candidate_that_copies_jev_round1_is_replaceable_everywhere(tmp_path, wrapper):
    X = _load(ROOT / "probes/jev_decider_vs_retest.py", "_frz")
    j1 = X.load_arms()["J1"]
    suite = [json.loads(l) for l in (S / "s0-compare-llm-v1.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    ptr = {it["item_id"]: "%s:%d" % (it["text_ref"]["file"], it["text_ref"]["line_index"]) for it in suite if "text_ref" in it}
    preds = []
    for p in _decider_preds():
        q = dict(p)
        key = p["item_id"][4:] if p["item_id"].startswith("rep-") else p["item_id"]
        lab = X.RT.norm(j1.get(ptr.get(key), {}).get(p["question_id"]), X.FACETS[p["question_id"]]) if key in ptr else p["selected_candidate"]
        lab = lab if lab in p["candidate_ids"] else next(c for c in p["candidate_ids"] if c in ("未知", "未提及"))
        q["selected_candidate"] = lab
        q["probabilities"] = [1.0 if c == lab else 0.0 for c in p["candidate_ids"]]
        preds.append(q)
    wrapper.main(["qwen3-4b-2507", str(_run_dir(tmp_path, preds))])
    doc = json.loads((tmp_path / "out_qwen3-4b-2507.json").read_text(encoding="utf-8"))
    assert all(v == "可替代" for v in doc["verdicts"].values()), doc["verdicts"]
    assert doc["★头条检查"]["max_d"] <= 4


def test_wrapper_refuses_a_report_from_another_model(tmp_path, wrapper):
    d = _run_dir(tmp_path, _decider_preds())
    rep = json.loads((d / "report.json").read_text(encoding="utf-8")); rep["identities"]["backend_effective"]["revision"] = "0" * 40
    (d / "report.json").write_text(json.dumps(rep), encoding="utf-8")
    wrapper.main(["qwen3-4b-2507", str(d)])
    doc = json.loads((tmp_path / "out_qwen3-4b-2507.json").read_text(encoding="utf-8"))
    assert doc["overall"].startswith("前置不成立") and all(v is None for v in doc["verdicts"].values()) and doc["★头条检查"] is None
    assert doc["per_facet"] == {} and doc["★前置"]["同 run 复跑"]["pass"] is False and any("revision" in e for e in doc["★前置"]["errors"])
    for field, val in (("model_key", "qwen3.5-4b"), ("assets_lock_sha256", "0" * 64)):          # 同仓不同键 / 锁被换过 ⇒ 也拒
        rep2 = json.loads((d / "report.json").read_text(encoding="utf-8")); rep2["identities"]["backend_effective"]["revision"] = json.loads(
            (ROOT / "experiments/jev/models/qwen3-4b-2507/model.source.lock.json").read_text(encoding="utf-8"))["revision"]
        rep2["identities"][field] = val
        (d / "report.json").write_text(json.dumps(rep2), encoding="utf-8")
        wrapper.main(["qwen3-4b-2507", str(d)])
        doc = json.loads((tmp_path / "out_qwen3-4b-2507.json").read_text(encoding="utf-8"))
        assert doc["overall"].startswith("前置不成立") and any(field in e for e in doc["★包装前置错误"]), field


# ───────── 端到端(零 torch): hf_choice 计划器 + 假后端 → run_suite.run → 包装脚本 → 冻结前置必须通过 ─────────
def test_hf_choice_rows_from_the_real_planner_pass_the_frozen_preflight(tmp_path, wrapper):
    import sys as _s
    _s.path.insert(0, str(ROOT))
    from experiments.jev import run_suite as RS
    from experiments.jev.contracts import DecisionRow
    from experiments.jev.plan_chat import prepare_chat
    from experiments.jev.tests.test_plan_chat import ChatTok
    key = "qwen3.5-4b"
    src = json.loads((ROOT / f"experiments/jev/models/{key}/model.source.lock.json").read_text(encoding="utf-8"))
    cfg = src["backend_config"]
    pol = json.loads((ROOT / "experiments/jev/policies/cpu_compare_llm.json").read_text(encoding="utf-8"))
    pol = dict(pol, max_row_tokens=8192, max_padded_tokens=8192 * 272)          # 假 tokenizer 按字符切, 行更长

    class FakeBackend:
        def __init__(self, ledger):
            self.ledger, self.forwards_observed = ledger, 0

        def identities(self):
            return {"backend": "hf_choice", "repo_id": src["repo_id"], "revision": src["revision"], "letters": cfg["letters"], "threads": cfg["threads"],
                    "storage_dtype": "torch.bfloat16", "compute_dtype": "torch.float32", "prompt_spec": cfg["prompt_spec"], "temperature": cfg["temperature"]}

        def evaluate(self, plan, up=None):
            out = []
            for r in plan.rows:
                self.ledger.reserve(1, r.padded_len, r.token_len); self.forwards_observed += 1
                w = [1 + int(r.row_sha256[2 * i:2 * i + 2], 16) for i in range(r.nopts)]           # 行哈希定值 ⇒ 复跑逐位一致
                p = [x / sum(w) for x in w]
                out.append(DecisionRow(request_id=plan.request_id, item_id=r.item_id, question_id=r.question_id, question_type=r.question_type,
                                       candidate_ids=list(r.candidate_ids), raw_candidate_logits=[float(x) for x in w], probabilities=p,
                                       selected_candidate=r.candidate_ids[p.index(max(p))],
                                       identities={"row_sha256": r.row_sha256, "kind": r.kind, "level": r.level, "letter_mass": 0.97, "vocab_top1_is_letter": True},
                                       timing={"forward_s": 0.0, "token_len": r.token_len, "padded_len": r.padded_len}))
            return out

    ids = {"backend": "hf_choice", "model_key": key, "model_version": src["model_version"], "run": {"GITHUB_RUN_ID": "e2e"},
           "source_lock_sha256": _sha(ROOT / f"experiments/jev/models/{key}/model.source.lock.json"), "assets_lock_sha256": "missing",
           "cgroup_limits": {"cpu_model": "fake"}}
    out = tmp_path / "reports" / "e2e"
    rep = RS.run("s0-compare-llm-v1", out, pol, cfg, ids, backend_factory=lambda L: FakeBackend(L), tok_factory=ChatTok,
                 upstream_factory=lambda: None, plan_fn=lambda req, tok, up, c, b: prepare_chat(req, tok, c, b))
    assert rep["execution_status"] == "SUCCEEDED" and rep["coverage_status"] == "COMPLETE", rep["failures"]
    assert rep["backend"] == "hf_choice" and rep["budget"]["forwards"] == 269
    wrapper.main([key, str(out)])
    doc = json.loads((tmp_path / f"out_{key}.json").read_text(encoding="utf-8"))
    assert doc["★前置"]["errors"] == [] and doc["★包装前置错误"] == [] and doc["★前置"]["同 run 复跑"]["pass"], (doc["★前置"], doc["★包装前置错误"])
    assert all(v is not None for v in doc["verdicts"].values()) and doc["★字母质量诊断(不进判决)"]["rows"] == 210


def test_headline_threshold_is_replaceable_max_d_plus_one(tmp_path, wrapper, monkeypatch):
    import types
    c = json.loads(PRE.read_text(encoding="utf-8"))
    for d, want in ((5, "不能判可替代"), (4, "头条检查通过")):
        def fake_main(argv, d=d):
            X.OUT.write_text(json.dumps({"★前置": {"errors": [], "同 run 复跑": {"pass": True}}, "overall": "x", "verdicts": {},
                                         "per_facet": {"触发事件": {"pairs": {"D~J1": {"d": d}, "D~J2": {"d": 0}}}}}), encoding="utf-8")
        X = types.SimpleNamespace(main=fake_main, PRE=None, SUITE=None, OUT=None)
        monkeypatch.setattr(wrapper, "load_frozen", lambda pre: X)
        monkeypatch.setattr(wrapper, "identity_errors", lambda key, rep: [])
        wrapper.main(["qwen3-4b-2507", str(_run_dir(tmp_path / str(d), _decider_preds()) if (tmp_path / str(d)).mkdir() is None else "")])
        doc = json.loads((tmp_path / "out_qwen3-4b-2507.json").read_text(encoding="utf-8"))
        assert doc["★头条检查"]["threshold"] == c["★★★判决规则(测量前冻结)"]["数值"]["replaceable_max_d"] + 1 == 5
        assert doc["★头条检查"]["result"].startswith(want), (d, doc["★头条检查"])
