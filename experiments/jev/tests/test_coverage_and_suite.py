# -*- coding: utf-8 -*-
"""覆盖闸 + run_suite 端到端(假后端): 空/缺/重复输出 ⇒ COVERAGE_MISMATCH 且分母不漏 · 失败也写报告 · 假后端恒选首项 ⇒ 语义闸变红 ·
正确答案假后端 ⇒ PASSED · 坏概率 ⇒ OUTPUT_INVALID · 报告无原文。"""
import json
from pathlib import Path

import pytest

from experiments.jev import run_suite as RS
from experiments.jev.contracts import JevError
from experiments.jev.report import coverage, text_leaks
from experiments.jev.tests.fakes import FakeBackend, FakeTokenizer, fake_upstream

CFG = {"temperature": 1.3, "version": "v10", "isolated_levels": True, "max_options": 255, "schema_first": False, "neutralize_none": False}
POLICY = json.loads((Path(RS.HERE) / "policies" / "cpu_smoke.json").read_text(encoding="utf-8"))
IDS = {"model_version": "v10", "cce_execution_commit": "test"}


def _run(tmp_path, backend_factory, **kw):
    return RS.run("s0-smoke-v1", tmp_path / "reports" / "r1", POLICY, CFG, IDS, backend_factory, FakeTokenizer, fake_upstream, **kw)


def test_coverage_gate_families():
    exp = [{"item_id": "i", "question_id": q, "status": "NOT_RUN"} for q in ("a", "b")]
    assert coverage(exp, [{"item_id": "i", "question_id": "a", "status": "OK"}, {"item_id": "i", "question_id": "b", "status": "FAILED"}])["by_status"] == {"FAILED": 1, "OK": 1}
    for results in ([], [{"item_id": "i", "question_id": "a", "status": "OK"}],
                    [{"item_id": "i", "question_id": "a", "status": "OK"}] * 2 + [{"item_id": "i", "question_id": "b", "status": "OK"}],
                    [{"item_id": "i", "question_id": "a", "status": "OK"}, {"item_id": "i", "question_id": "b", "status": "OK"}, {"item_id": "i", "question_id": "zz", "status": "OK"}],
                    [{"item_id": "i", "question_id": "a", "status": "OK"}, {"item_id": "i", "question_id": "b", "status": "WHATEVER"}]):
        with pytest.raises(JevError) as e:
            coverage(exp, results)
        assert e.value.code == "COVERAGE_MISMATCH"


def test_suite_sha_is_checked_and_expected_set_fixed_before_inference(tmp_path):
    items, m = RS.load_suite("s0-smoke-v1")
    assert len(items) == 2 and m["suite_sha256"]
    bad = tmp_path / "suites"; bad.mkdir()
    (bad / "s0-smoke-v1.jsonl").write_text("{}\n"); (bad / "s0-smoke-v1.manifest.json").write_text(json.dumps(m))
    with pytest.raises(JevError):
        RS.load_suite("s0-smoke-v1", bad)
    with pytest.raises(JevError):
        RS.load_suite("../etc", bad)


def _correct_answers():
    items, _ = RS.load_suite("s0-smoke-v1")
    return {(it["item_id"], q): acc[0] for it in items for q, acc in it["expected"].items()}


def test_correct_fake_backend_passes_and_report_is_public_safe(tmp_path):
    rep = _run(tmp_path, lambda L: FakeBackend(L, answers=_correct_answers()))
    assert rep["execution_status"] == "SUCCEEDED" and rep["coverage_status"] == "COMPLETE" and rep["semantic_acceptance"] == "PASSED"
    assert rep["production_eligible"] is False and rep["failures"] == []
    by = rep["coverage"]["by_status"]
    assert by["DECLARED"] == 1 and by["UNOBSERVABLE"] == 6 and by["OK"] + by.get("SEMANTIC_UNKNOWN", 0) == 11 and rep["coverage"]["expected"] == 18
    out = tmp_path / "reports" / "r1"
    for f in ("report.json", "summary.md", "predictions.jsonl", "expected_items.json", "execution_receipt.json", "resource_ledger.jsonl", "manifest.sha256", "s0_candidates.jsonl"):
        assert (out / f).is_file(), f
    blob = " ".join(((out / "report.json").read_text(encoding="utf-8") + (out / "predictions.jsonl").read_text(encoding="utf-8")).split())
    items, _ = RS.load_suite("s0-smoke-v1")
    hits = text_leaks(blob, [it["text"] for it in items], window=8)
    assert hits == 0, f"{hits} item text(s) found in report"   # 计数, 不复述原文
    exp = json.loads((out / "expected_items.json").read_text(encoding="utf-8"))
    assert exp["fixed_before_inference"] and len(exp["rows"]) == 18
    assert rep["budget"]["forwards"] == 11 == rep["budget"]["rows"]


def test_first_option_fake_backend_turns_semantic_gate_red_but_execution_succeeds(tmp_path):
    rep = _run(tmp_path, lambda L: FakeBackend(L))
    assert rep["execution_status"] == "SUCCEEDED" and rep["coverage_status"] == "COMPLETE"
    assert rep["semantic_acceptance"] == "FAILED" and any(f["code"] == "SEMANTIC_CHECK_FAILED" for f in rep["failures"])
    assert rep["production_eligible"] is False


@pytest.mark.parametrize("bad,code", [("nan", "OUTPUT_INVALID"), ("short", "OUTPUT_INVALID"), ("duplicate", "COVERAGE_MISMATCH"), ("drop", "COVERAGE_MISMATCH")])
def test_bad_backend_outputs_are_typed_failures_with_report_written(tmp_path, bad, code):
    rep = _run(tmp_path, lambda L: FakeBackend(L, answers=_correct_answers(), bad=bad))
    assert rep["execution_status"] == "FAILED" and rep["failures"][0]["code"] == code, rep["failures"]
    assert (tmp_path / "reports" / "r1" / "report.json").is_file() and rep["semantic_acceptance"] == "NOT_ESTABLISHED"
    # 失败项仍在分母: 结果表覆盖全部 18 个预期键
    keys = {(r["item_id"], r["question_id"]) for r in rep["results"]}
    assert len(keys) == 18


def test_budget_exhaustion_is_typed_and_ledger_kept(tmp_path):
    pol = {**POLICY, "max_forwards": 3}
    rep = RS.run("s0-smoke-v1", tmp_path / "reports" / "r2", pol, CFG, IDS, lambda L: FakeBackend(L, answers=_correct_answers()), FakeTokenizer, fake_upstream)
    assert rep["execution_status"] == "FAILED" and rep["failures"][0]["code"] == "BUDGET_EXCEEDED" and rep["budget"]["forwards"] == 3


def test_out_dir_outside_reports_is_refused(tmp_path):
    with pytest.raises(JevError) as e:
        RS.run("s0-smoke-v1", tmp_path / "results" / "x", POLICY, CFG, IDS, lambda L: FakeBackend(L), FakeTokenizer, fake_upstream)
    assert e.value.code == "OUTPUT_INVALID"


COMPARE = json.loads((Path(RS.HERE) / "policies" / "cpu_compare.json").read_text(encoding="utf-8"))
# 假 tokenizer 按字符切(真 tokenizer ≈4 字符/token), 只在这里放宽单行上限, 其余上限与冻结策略相同
COMPARE_FAKE_TOK = {**COMPARE, "max_row_tokens": 4096, "max_padded_tokens": 4096 * 272}


def test_compare_suite_end_to_end_with_fake_backend(tmp_path):
    rep = RS.run("s0-compare-v1", tmp_path / "reports" / "c1", COMPARE_FAKE_TOK, CFG, IDS, lambda L: FakeBackend(L), FakeTokenizer, fake_upstream)
    assert rep["execution_status"] == "SUCCEEDED" and rep["coverage_status"] == "COMPLETE", rep["failures"]
    by = rep["coverage"]["by_status"]
    assert by["STRUCTURAL_COLD_READ"] == 54 and by["UNOBSERVABLE"] == 162 and by["DECLARED"] == 1 and rep["coverage"]["expected"] == 486
    assert rep["budget"]["forwards"] == 269 == rep["budget"]["rows"]
    sem = rep["semantic"]
    assert sum(s["asserted"] for s in sem) == 9 and sum(not s["asserted"] for s in sem) == 260     # 只有 2 条 smoke 有 gold
    assert all(r["value"] == "首轮无余温" for r in rep["results"] if r.get("provenance") == "STRUCTURAL_COLD_READ")
    assert not any(r.get("question_id") == "情绪余温" and "probabilities" in r for r in rep["results"])  # 情绪余温 不是模型行
    assert rep["suite_manifest"]["task"] == "s0_context.v2" and rep["suite_manifest"]["prereg_sha256"]
    blob = " ".join("".join(p.read_text(encoding="utf-8") for p in (tmp_path / "reports" / "c1").iterdir() if p.is_file()).split())
    items, _ = RS.load_suite("s0-compare-v1")
    hits = text_leaks(blob, RS.suite_texts(items))
    assert hits == 0, f"{hits} input text(s) found in report files"


def test_policy_and_suite_must_match(tmp_path):
    rep = RS.run("s0-compare-v1", tmp_path / "reports" / "x1", POLICY, CFG, IDS, lambda L: FakeBackend(L), FakeTokenizer, fake_upstream)
    assert rep["execution_status"] == "FAILED" and rep["failures"][0]["code"] == "PERMIT_NOT_APPROVED"   # smoke 策略不许跑 v2 对比 suite
    rep = RS.run("s0-smoke-v1", tmp_path / "reports" / "x2", COMPARE, CFG, IDS, lambda L: FakeBackend(L), FakeTokenizer, fake_upstream)
    assert rep["execution_status"] == "FAILED" and rep["failures"][0]["code"] == "PERMIT_NOT_APPROVED"   # 对比策略不覆盖 smoke suite


def test_unhandled_exception_message_is_withheld(tmp_path):
    class Boom:
        def __init__(self, L): pass
        def identities(self): return {}
        def evaluate(self, plan, up): raise RuntimeError("SECRET-INPUT-TEXT-SHOULD-NOT-APPEAR")
    rep = _run(tmp_path, lambda L: Boom(L))
    blob = json.dumps(rep, ensure_ascii=False) + "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "reports" / "r1").iterdir() if p.is_file())
    assert rep["failures"][0]["code"] == "UNHANDLED_EXCEPTION" and rep["failures"][0]["type"] == "RuntimeError"
    assert blob.count("SECRET-INPUT-TEXT") == 0
