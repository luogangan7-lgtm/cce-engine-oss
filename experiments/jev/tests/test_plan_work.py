# -*- coding: utf-8 -*-
"""题行计划: 截断/重排即拒 · 超长 INPUT_TOO_LONG(不裁) · 行哈希与 padding 核算 · 声明面不产生行。"""
import pytest

from experiments.jev import compile_context as C
from experiments.jev.contracts import ExecutionBudget, JevError
from experiments.jev.plan_work import ceil64, prepare, rows_json
from experiments.jev.tests.fakes import FakeTokenizer, fake_upstream

TAX = C.load_taxonomy()
CFG = {"temperature": 1.3, "version": "v10", "isolated_levels": True, "max_options": 255, "schema_first": False, "neutralize_none": False}
BUD = ExecutionBudget(max_forwards=16, max_rows=16, max_padded_tokens=32768, max_row_tokens=2048, deadline_s=100)
TEXT = "上周刚买的助听器今天突然没声了。"


def test_rows_one_per_model_question_with_hash_and_padding():
    req, _ = C.build_request({"item_id": "i1", "text": TEXT, "declared": {"关系位置": "已购买"}}, TAX)
    p = prepare(req, FakeTokenizer(), fake_upstream(), CFG, BUD)
    assert len(p.rows) == 5 and {r.question_id for r in p.rows} == {q.question_id for q in req.questions}
    for r in p.rows:
        assert r.padded_len == ceil64(r.token_len) and r.token_len <= r.padded_len and len(r.row_sha256) == 64
        assert r.ids[:p.state_tokens] == FakeTokenizer().encode("Context:\n" + TEXT) and r.nopts == len(r.candidate_ids)
    assert "ids" not in rows_json(p)[0] and rows_json(p)[0]["row_sha256"] == p.rows[0].row_sha256


def test_renderer_truncation_is_detected():
    req, _ = C.build_request({"item_id": "i1", "text": TEXT}, TAX)
    with pytest.raises(JevError) as e:
        prepare(req, FakeTokenizer(), fake_upstream(truncate_to=5), CFG, BUD)
    assert e.value.code == "INPUT_INVALID" and "truncated" in e.value.detail


def test_renderer_reordering_is_detected():
    req, _ = C.build_request({"item_id": "i1", "text": TEXT}, TAX)
    with pytest.raises(JevError) as e:
        prepare(req, FakeTokenizer(), fake_upstream(reorder=True), CFG, BUD)
    assert e.value.code == "INPUT_INVALID" and "order" in e.value.detail


def test_too_long_is_refused_not_truncated():
    req, _ = C.build_request({"item_id": "i1", "text": TEXT * 300}, TAX)
    with pytest.raises(JevError) as e:
        prepare(req, FakeTokenizer(), fake_upstream(), CFG, BUD)
    assert e.value.code == "INPUT_TOO_LONG"


def test_neutralize_none_config_is_unsupported():
    req, _ = C.build_request({"item_id": "i1", "text": TEXT}, TAX)
    with pytest.raises(JevError) as e:
        prepare(req, FakeTokenizer(), fake_upstream(), {**CFG, "neutralize_none": True}, BUD)
    assert e.value.code == "RUNTIME_UNSUPPORTED"


def test_same_input_same_hashes_different_text_different_input_hash():
    a, _ = C.build_request({"item_id": "i1", "text": TEXT}, TAX); b, _ = C.build_request({"item_id": "i1", "text": TEXT + "。"}, TAX)
    pa, pb = prepare(a, FakeTokenizer(), fake_upstream(), CFG, BUD), prepare(b, FakeTokenizer(), fake_upstream(), CFG, BUD)
    assert pa.questions_sha256 == pb.questions_sha256 and pa.input_sha256 != pb.input_sha256
    assert [r.row_sha256 for r in pa.rows] != [r.row_sha256 for r in pb.rows]
    assert prepare(a, FakeTokenizer(), fake_upstream(), CFG, BUD).rows[0].row_sha256 == pa.rows[0].row_sha256
