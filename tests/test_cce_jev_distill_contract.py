# -*- coding: utf-8 -*-
"""蒸馏测试的合同闸(零 API、零模型、零 numpy; 进 cce-jev-contract CI): 预注册照抄冻结规则且钉住四个脚本 sha ·
训练集 = 验收集之外的全部非空行且不重合 · 老师开跑前置 · 老师上限跨进程累计(撞上限也落产物、拒绝重开、续跑不多花) ·
续跑只补没读到的指针 · 不跟随重定向 · 响应逐面校验。老师产物全部写临时目录, 不写 results/。"""
import hashlib
import importlib.util
import io
import json
import pathlib
import urllib.error
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/jev_distill_prereg.json"
S = ROOT / "experiments/jev/suites"


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _load(rel, name):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def _jsonl(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def test_prereg_copies_the_frozen_rule_and_pins_all_scripts():
    d, c = json.loads(PRE.read_text(encoding="utf-8")), json.loads((ROOT / "tests/data/jev_candidate_vs_retest_prereg.json").read_text(encoding="utf-8"))
    for k in ("★面", "★输入与题目(冻结)", "★归一化", "★主判据", "★不确定性", "★★★判决规则(测量前冻结)"):
        assert d[k] == c[k], k
    assert {k: d["★确定性(前置)"][k] for k in ("同 run 复跑", "tol_abs_dp")} == {k: c["★确定性(前置)"][k] for k in ("同 run 复跑", "tol_abs_dp")}
    assert d["★头条检查(预注册)"]["面"] == "触发事件"
    a = d["★分析脚本(冻结)"]
    assert _sha(ROOT / "probes/jev_decider_vs_retest.py") == a["sha256"]
    assert _sha(ROOT / "probes/jev_distill_vs_retest.py") == a["distill_sha256"], "蒸馏分析脚本改过: 看数据后的改动必须登记"
    assert _sha(ROOT / "probes/jev_distill_teacher.py") == a["teacher_sha256"]
    assert _sha(ROOT / "probes/s0_jev_shadow.py") == a["shadow_sha256"]
    assert set(d["★变体(三个都报, 不挑)"]) == {"A", "B", "C"} and len(d["★族(两个都报, 不挑)"]) == 3
    assert d["★预测(先写, 看数据前)"] and d["★混杂(不可在本轮分离)"] and d["★修订记录(测量前)"]
    assert any("挑" in x for x in d["★★★不得据此说"]) and any("蒸馏" in x for x in d["★★★不得据此说"])
    for k in ("qwen3-4b-2507", "qwen3.5-4b"):                   # 零样本基线 == 已提交的零样本结果, 不是手抄
        r = json.loads((ROOT / f"results/jev_candidate_{k}_vs_retest.json").read_text(encoding="utf-8"))["per_facet"]
        assert d["★零样本基线(冻结)"][k] == {f: {j: v["pairs"][f"D~{j}"]["d"] for j in ("J1", "J2")} for f, v in r.items()}
    m = json.loads((S / "s0-distill-train-v1.manifest.json").read_text(encoding="utf-8"))
    assert m["prereg_sha256"] == _sha(PRE) and m["suite_sha256"] == _sha(S / "s0-distill-train-v1.jsonl") and m["policy"] == "cpu_distill_llm.json"


def test_training_set_is_every_line_outside_the_acceptance_set():
    T = _load("probes/jev_distill_teacher.py", "_t1")
    tr = _jsonl(S / "s0-distill-train-v1.jsonl")
    ptrs = T.training_pointers()
    assert [(it["text_ref"]["file"], it["text_ref"]["line_index"], it["text_ref"]["line_sha256"]) for it in tr] == [(p["file"], p["line_index"], p["line_sha256"]) for p in ptrs]
    d = json.loads(PRE.read_text(encoding="utf-8"))["★训练集(冻结)"]
    assert len(tr) == d["n"] == T.N_TRAIN == 66 and T.pointer_set_sha(ptrs) == d["pointer_set_sha256"]
    assert {i for g in d["留一分组(近重复)"] for i in g} <= {it["item_id"] for it in tr}
    acc = [it for it in _jsonl(S / "s0-compare-llm-v1.jsonl") if "text_ref" in it and not it["item_id"].startswith("rep-")]
    assert not {(it["text_ref"]["file"], it["text_ref"]["line_index"]) for it in tr} & {(it["text_ref"]["file"], it["text_ref"]["line_index"]) for it in acc}
    assert not {it["text_ref"]["line_sha256"] for it in tr} & {it["text_ref"]["line_sha256"] for it in acc}
    assert len(T.drift_pointers()) == T.N_DRIFT == 10 and all(p["line_sha256"] in {it["text_ref"]["line_sha256"] for it in acc} for p in T.drift_pointers())


def test_teacher_preflight_pins_request_shape_and_refuses_a_changed_prereg(tmp_path, monkeypatch):
    T = _load("probes/jev_distill_teacher.py", "_t2")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    work, ident = T.preflight()
    assert len(work) == 76 and [s for s, _ in work][:66] == ["train"] * 66 and ident["prereg_sha256"] == _sha(PRE)
    assert T.SH.question_sha() == pre["★老师(冻结)"]["question_sha"] == "e92737943a5431e9" and T.SH.API == pre["★老师(冻结)"]["endpoint"]
    bad = json.loads(PRE.read_text(encoding="utf-8")); bad["★分析脚本(冻结)"]["teacher_sha256"] = "0" * 64
    f = tmp_path / "pre.json"; f.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(T, "PRE", f)
    with pytest.raises(SystemExit, match="teacher script sha"):
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
        assert req.full_url == self.T.SH.API and req.get_header("Authorization") == "Bearer k"
        if self.mode == "busy":
            raise urllib.error.HTTPError(req.full_url, 429, "busy", {}, None)
        return _Resp({"answers": _good_answers(self.T), "usage": {"input_tokens": 10}}, self.T.SH.API)


def _good_answers(T):
    out = {}
    for k, q in T.SH.jev_questions().items():
        c = list(q["criteria"])
        out[k] = {"choice": c[0], "probabilities": {c[0]: 0.7, c[1]: 0.3}}
    return out


def _isolate(T, monkeypatch, tmp_path, mode):
    for n, f in (("OUT", "t.json"), ("PARTIAL", "t_partial.jsonl"), ("LEDGER", "t_ledger.jsonl")):
        monkeypatch.setattr(T, n, tmp_path / f)
    op = _Opener(T, mode)
    monkeypatch.setattr(T, "_OPENER", op)
    monkeypatch.setattr(T.time, "sleep", lambda s: None)
    monkeypatch.setattr(T.SH, "_key", lambda: "k")
    monkeypatch.setattr(T, "provenance", lambda: "h" * 40)
    return op


def test_cap_counts_across_processes_and_the_output_survives_the_cap(tmp_path, monkeypatch):
    T = _load("probes/jev_distill_teacher.py", "_t3")
    op = _isolate(T, monkeypatch, tmp_path, "busy")
    assert T.main([]) == 2
    out = json.loads(T.OUT.read_text(encoding="utf-8"))
    assert out["status"] == "capped" and out["★账本"]["attempts_cumulative"] == T.CAP_ATTEMPTS == op.calls == len(_jsonl(T.LEDGER))
    assert len(out["rows"]) == 76 and not any(r["ok"] for r in out["rows"]) and out["prereg_sha256"] == _sha(PRE)
    with pytest.raises(SystemExit, match="never start over"):   # 重开被拒: 不会再给一份 80
        T.main([])
    assert T.main(["--resume"]) == 2                              # 续跑沿用累计数: 一次都不多发
    assert op.calls == T.CAP_ATTEMPTS == len(_jsonl(T.LEDGER))


def test_resume_reads_only_what_was_not_read_and_a_complete_reading_cannot_be_redone(tmp_path, monkeypatch):
    T = _load("probes/jev_distill_teacher.py", "_t4")
    op = _isolate(T, monkeypatch, tmp_path, "ok")
    real, n = T.body_of, {"i": 0}

    def flaky(p):
        n["i"] += 1
        if n["i"] > 76 + 10:                                      # preflight 取过 76 次; 之后第 11 次时中断
            raise KeyboardInterrupt
        return real(p)
    monkeypatch.setattr(T, "body_of", flaky)
    with pytest.raises(KeyboardInterrupt):
        T.main([])
    assert json.loads(T.OUT.read_text(encoding="utf-8"))["status"] == "aborted" and op.calls == 10
    monkeypatch.setattr(T, "body_of", real)
    assert T.main(["--resume"]) == 0
    out = json.loads(T.OUT.read_text(encoding="utf-8"))
    assert out["status"] == "complete" and op.calls == 76 == out["★账本"]["attempts_cumulative"] and all(r["ok"] for r in out["rows"])
    assert out["counts"] == {"train": {"n": 66, "ok": 66}, "drift": {"n": 10, "ok": 10}}
    with pytest.raises(SystemExit, match="already complete"):
        T.main(["--resume"])
    assert op.calls == 76


def test_budget_cap_stops_inside_the_retry_loop(monkeypatch):
    T = _load("probes/jev_distill_teacher.py", "_t5")
    op = _Opener(T, "busy"); monkeypatch.setattr(T, "_OPENER", op); monkeypatch.setattr(T.time, "sleep", lambda s: None)
    led = {"attempts": T.CAP_ATTEMPTS - 2, "this_run": 0, "tok_in": 0}
    with pytest.raises(RuntimeError, match="BUDGET_EXCEEDED"):   # 429 重试中途撞上限: 两次真实尝试后停, 不多发一次
        T.call("x", "k", led)
    assert led["attempts"] == T.CAP_ATTEMPTS and op.calls == 2
    with pytest.raises(RuntimeError):
        T.call("x", "k", led)
    assert op.calls == 2


def test_redirects_are_refused_and_malformed_answers_are_rejected():
    T = _load("probes/jev_distill_teacher.py", "_t6")
    req = urllib.request.Request(T.SH.API, data=b"{}", method="POST")
    for code in (301, 302, 303, 307, 308):                         # urllib 默认会把 POST 的 301/302/303 跟到新地址(带着头)
        with pytest.raises(urllib.error.HTTPError):
            T._NoRedirect().redirect_request(req, None, code, "moved", {}, "https://elsewhere.example/")
    good = _good_answers(T)
    ch, pr = T.validate(good)
    assert set(ch) == set(pr) == set(T.SH.jev_questions())
    k = next(iter(good))
    c = list(T.SH.jev_questions()[k]["criteria"])
    for bad in ({c[0]: 1.5}, {"not-a-candidate": 1.0}, {c[0]: 0.5}, {c[0]: True}, {c[0]: float("nan")}, {}):
        g = json.loads(json.dumps(good)); g[k]["probabilities"] = bad
        with pytest.raises(ValueError):
            T.validate(g)
    g = json.loads(json.dumps(good)); g[k]["choice"] = "not-a-candidate"
    with pytest.raises(ValueError):
        T.validate(g)
    g = json.loads(json.dumps(good)); del g[k]
    with pytest.raises(ValueError):
        T.validate(g)
