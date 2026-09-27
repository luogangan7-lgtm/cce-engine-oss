# -*- coding: utf-8 -*-
"""蒸馏第二轮的合同闸(零 API、零模型、零 numpy; 进 cce-jev-contract CI): 预注册照抄冻结规则且钉住全部脚本 sha ·
suite = 验收套件 54 条 + 训练 66 条原样原序 · 许可/策略/锁一致 · 老师预算跨进程累计、撞上限也落产物、拒绝重开、续跑不多发。老师产物写临时目录。"""
import hashlib
import importlib.util
import io
import json
import pathlib
import urllib.error

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/jev_distill2_prereg.json"
S = ROOT / "experiments/jev/suites"
J = ROOT / "experiments/jev"


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _load(rel, name):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def _jsonl(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def test_prereg_copies_the_frozen_rule_and_pins_every_script():
    d, c = json.loads(PRE.read_text(encoding="utf-8")), json.loads((ROOT / "tests/data/jev_candidate_vs_retest_prereg.json").read_text(encoding="utf-8"))
    for k in ("★面", "★输入与题目(冻结)", "★归一化", "★主判据", "★不确定性", "★★★判决规则(测量前冻结)", "★头条检查(预注册)"):
        assert d[k] == c[k], k
    assert {k: d["★确定性(前置)"][k] for k in ("同 run 复跑", "tol_abs_dp")} == {k: c["★确定性(前置)"][k] for k in ("同 run 复跑", "tol_abs_dp")}
    a = d["★脚本(冻结)"]
    for key, path in (("frozen_rule_sha256", "probes/jev_decider_vs_retest.py"), ("analysis2_sha256", "probes/jev_distill2_vs_retest.py"),
                      ("teacher2_sha256", "probes/jev_distill2_teacher.py"), ("teacher1_sha256", "probes/jev_distill_teacher.py"),
                      ("shadow_sha256", "probes/s0_jev_shadow.py"), ("hidden_export_sha256", "experiments/jev/hidden_export.py"),
                      ("cand_wrapper_sha256", "probes/jev_candidate_vs_retest.py")):
        assert _sha(ROOT / path) == a[key], f"{path} changed after freeze — register it"
    from experiments.jev.cli import adapter_hash
    assert adapter_hash() == a["adapter_sha256"], "experiments/jev/*.py changed after freeze — the GitHub legs would carry another adapter"
    assert d["★GitHub(冻结)"]["隐状态块号"] == {"qwen3-4b-2507": [18, 27], "qwen3.5-4b": [16, 24]}
    assert d["★预测(先写, 看数据前)"] and d["★混杂(不可在本轮分离)"] and d["★决策图(预注册)"] and any("挑" in x for x in d["★★★不得据此说"])
    m = json.loads((S / "s0-distill2-v1.manifest.json").read_text(encoding="utf-8"))
    assert m["prereg_sha256"] == _sha(PRE) and m["suite_sha256"] == _sha(S / "s0-distill2-v1.jsonl") and m["policy"] == "cpu_distill2_llm.json"


def test_suite_is_the_exam_suite_then_the_training_suite_verbatim_and_the_permit_pins_it():
    lines = [l for l in (S / "s0-distill2-v1.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    ex = [l for l in (S / "s0-compare-llm-v1.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    tr = [l for l in (S / "s0-distill-train-v1.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert lines == ex + tr and len(lines) == 120
    d = json.loads(PRE.read_text(encoding="utf-8"))
    p = json.loads((J / "permits" / f"{d['★GitHub(冻结)']['permit_id']}.json").read_text(encoding="utf-8"))
    pol = J / "policies" / p["resource_policy"]
    assert p["suite_id"] == "s0-distill2-v1" and p["suite_sha256"] == _sha(S / "s0-distill2-v1.jsonl") and p["resource_policy_sha256"] == _sha(pol)
    assert p["runtime_lock_sha256"] == _sha(J / "locks/runtime-cpu.lock.txt") and p["max_runs"] == p["max_attempts"] == 1
    for m in p["models"]:
        k = m["model_key"]
        assert m["model_source_lock_sha256"] == _sha(J / f"models/{k}/model.source.lock.json") and m["asset_lock_sha256"] == _sha(J / f"models/{k}/model.assets.lock.json")
    policy = json.loads(pol.read_text(encoding="utf-8"))
    assert policy["export_hidden"] == {"depth_fractions": [0.5, 0.75]} and policy["max_rows"] >= d["★GitHub(冻结)"]["rows_per_leg"] == 599
    assert "s0-distill2-v1" in (ROOT / ".github/workflows/cce-jev-llm-eval.yml").read_text(encoding="utf-8")


def test_teacher_preflight_pins_the_request_and_pointer_sets(tmp_path, monkeypatch):
    T = _load("probes/jev_distill2_teacher.py", "_t2a")
    work, ident = T.preflight()
    d = json.loads(PRE.read_text(encoding="utf-8"))["★老师(冻结)"]
    assert [p for p, _ in work] == ["J3"] * 42 + ["R2"] * 66 + ["J4"] * 42 and len(work) == d["planned_calls"] == 150 and ident["prereg_sha256"] == _sha(PRE)
    assert T.SH.API == d["endpoint"] and T.SH.question_sha() == d["question_sha"] and T.CAP_ATTEMPTS == d["cap_attempts"] == 170
    bad = json.loads(PRE.read_text(encoding="utf-8")); bad["★老师(冻结)"]["planned_calls"] = 149
    f = tmp_path / "pre.json"; f.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(T, "PRE", f)
    with pytest.raises(SystemExit, match="planned call count"):
        T.preflight()


class _Resp(io.BytesIO):
    def __init__(self, body, url):
        super().__init__(json.dumps(body, ensure_ascii=False).encode()); self._url = url

    def geturl(self):
        return self._url


class _Opener:
    def __init__(self, T, mode):
        self.T, self.mode, self.calls = T, mode, 0

    def open(self, req, timeout=None):
        self.calls += 1
        if self.mode == "busy":
            raise urllib.error.HTTPError(req.full_url, 429, "busy", {}, None)
        if self.mode == "401":
            raise urllib.error.HTTPError(req.full_url, 401, "no", {}, None)
        if self.mode == "offline":
            raise urllib.error.URLError("offline")
        if self.mode == "blip" and self.calls in (2, 45):
            raise urllib.error.HTTPError(req.full_url, 502, "blip", {}, None)
        ans = {k: {"choice": list(q["criteria"])[0], "probabilities": {list(q["criteria"])[0]: 1.0}} for k, q in self.T.SH.jev_questions().items()}
        return _Resp({"answers": ans}, self.T.SH.API)


def _isolate(T, monkeypatch, tmp_path, mode):
    for n, f in (("OUT", "t.json"), ("PARTIAL", "t_partial.jsonl"), ("LEDGER", "t_ledger.jsonl")):
        monkeypatch.setattr(T, n, tmp_path / f)
    op = _Opener(T, mode)
    monkeypatch.setattr(T.T1, "_OPENER", op)
    monkeypatch.setattr(T.T1.time, "sleep", lambda s: None)
    monkeypatch.setattr(T.SH, "_key", lambda: "k")
    monkeypatch.setattr(T, "provenance", lambda: "h" * 40)
    return op


def test_teacher_cap_is_cumulative_and_a_complete_reading_cannot_be_redone(tmp_path, monkeypatch):
    T = _load("probes/jev_distill2_teacher.py", "_t2b")
    monkeypatch.setattr(T, "BREAK_AFTER", 10 ** 6)                                    # 这里只测累计上限(熔断另有测试)
    op = _isolate(T, monkeypatch, tmp_path, "busy")
    assert T.main([]) == 2
    out = json.loads(T.OUT.read_text(encoding="utf-8"))
    assert out["status"] == "capped" and out["★账本"]["attempts_cumulative"] == 170 == op.calls == len(_jsonl(T.LEDGER))
    with pytest.raises(SystemExit, match="never start over"):
        T.main([])
    assert T.main(["--resume"]) == 2 and op.calls == 170
    T2 = _load("probes/jev_distill2_teacher.py", "_t2c")
    (tmp_path / "ok").mkdir()
    op2 = _isolate(T2, monkeypatch, tmp_path / "ok", "ok")
    assert T2.main([]) == 0
    out = json.loads(T2.OUT.read_text(encoding="utf-8"))
    assert out["status"] == "complete" and op2.calls == 150 and out["counts"] == {"J3": {"n": 42, "ok": 42}, "R2": {"n": 66, "ok": 66}, "J4": {"n": 42, "ok": 42}}
    with pytest.raises(SystemExit, match="already complete"):
        T2.main(["--resume"])


@pytest.mark.parametrize("mode,calls", [("401", 1), ("offline", 3)])
def test_teacher_breaks_the_circuit_instead_of_burning_the_budget(tmp_path, monkeypatch, mode, calls):
    T = _load("probes/jev_distill2_teacher.py", "_t2d" + mode)
    op = _isolate(T, monkeypatch, tmp_path, mode)
    assert T.main([]) == 2
    out = json.loads(T.OUT.read_text(encoding="utf-8"))
    assert out["status"] == "aborted" and op.calls == calls == out["★账本"]["attempts_cumulative"]


def test_a_partial_reading_is_incomplete_and_resume_rereads_only_the_misses(tmp_path, monkeypatch):
    T = _load("probes/jev_distill2_teacher.py", "_t2e")
    op = _isolate(T, monkeypatch, tmp_path, "blip")
    assert T.main([]) == 2
    out = json.loads(T.OUT.read_text(encoding="utf-8"))
    assert out["status"] == "incomplete" and op.calls == 150 and sum(not r["ok"] for r in out["rows"]) == 2
    assert T.main(["--resume"]) == 0
    out = json.loads(T.OUT.read_text(encoding="utf-8"))
    assert out["status"] == "complete" and op.calls == 152 and out["★账本"]["attempts_cumulative"] == 152
