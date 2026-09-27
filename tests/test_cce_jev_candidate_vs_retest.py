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
    for k in ("★面", "★输入与题目(冻结)", "★归一化", "★主判据", "★不确定性", "★★★判决规则(测量前冻结)", "★混杂(不可在本轮分离)"):
        assert c[k] == d[k], k
    assert c["★确定性(前置)"]["tol_abs_dp"] == d["★确定性(前置)"]["tol_abs_dp"] and c["★确定性(前置)"]["同 run 复跑"] == d["★确定性(前置)"]["同 run 复跑"]
    assert c["★臂"]["D"]["T"] == 1.0 and c["★臂"]["D"]["prompt_spec"] == "cce.jev.hf_choice.prompt.v1"
    assert c["★★★判决规则(测量前冻结)"]["数值"]["replaceable_max_d"] == 4 and "0 次 TypeSafe/MiniMax" in c["★臂"]["★不新调付费接口"]
    assert set(d["★★★不得据此说"]) <= set(c["★★★不得据此说"])
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
    d = tmp / "run"; d.mkdir()
    (d / "predictions.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in preds), encoding="utf-8")
    src = json.loads((ROOT / "experiments/jev/models/qwen3-4b-2507/model.source.lock.json").read_text(encoding="utf-8"))
    rep = {"execution_status": "SUCCEEDED", "coverage_status": "COMPLETE", "suite_sha256": _sha(S / "s0-compare-llm-v1.jsonl"),
           "suite_manifest": {"prereg_sha256": _sha(PRE)},
           "identities": {"backend_effective": {"temperature": 1.0, "repo_id": src["repo_id"], "revision": src["revision"], "backend": "hf_choice",
                                                "prompt_spec": "cce.jev.hf_choice.prompt.v1", "compute_dtype": "torch.float32", "storage_dtype": "torch.bfloat16", "threads": 3},
                          "run": {"GITHUB_RUN_ID": "replay"}, "cgroup_limits": {"cpu_model": "replay"}}}
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
