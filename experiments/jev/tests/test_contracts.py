# -*- coding: utf-8 -*-
"""合同层: 坏输出逐族拒绝 · 候选顺序进哈希 · 题目/输入哈希分开。"""
import math

import pytest

from experiments.jev.contracts import DecisionRequest, DecisionRow, JevError, Question, canonical, sha256, validate_row

Q = Question("q", "choice", "pick", (("a", "A"), ("b", "B"), ("c", None))).validate()


def row(**over):
    base = dict(request_id="r", item_id="i", question_id="q", question_type="choice", candidate_ids=["a", "b", "c"],
                raw_candidate_logits="unavailable", probabilities=[0.7, 0.2, 0.1], selected_candidate="a")
    base.update(over)
    return DecisionRow(**base)


def test_good_row_passes():
    validate_row(row(), Q)
    validate_row(row(raw_candidate_logits=[1.0, -0.5, -2.0]), Q)


@pytest.mark.parametrize("bad", [
    dict(probabilities=[float("nan"), 0.5, 0.5]), dict(probabilities=[float("inf"), 0.0, 0.0]), dict(probabilities=[-0.1, 0.6, 0.5]),
    dict(probabilities=[0.5, 0.5]), dict(probabilities=[0.6, 0.3, 0.3]), dict(candidate_ids=["a", "a", "c"]), dict(candidate_ids=["a", "c", "b"]),
    dict(candidate_ids=["a", "b", "zzz"]), dict(selected_candidate="zzz"), dict(question_type="score"),
    dict(raw_candidate_logits=[1.0, 2.0]), dict(raw_candidate_logits=[1.0, float("nan"), 0.0]), dict(raw_candidate_logits=[-math.inf, 1.0, 2.0]),
    dict(semantic_status="MAYBE"),
])
def test_bad_rows_rejected(bad):
    with pytest.raises(JevError) as e:
        validate_row(row(**bad), Q)
    assert e.value.code == "OUTPUT_INVALID"


def test_question_validation():
    with pytest.raises(JevError):
        Question("q", "choice", "x", (("a", None),)).validate()          # <2 candidates
    with pytest.raises(JevError):
        Question("q", "choice", "", (("a", None), ("b", None))).validate()   # empty instructions
    with pytest.raises(JevError):
        Question("q", "choice", "x", (("a", None), ("a", None))).validate()  # duplicate
    with pytest.raises(JevError):
        Question("q", "noul", "x", (("yes", None), ("no", None))).validate()
    with pytest.raises(JevError):
        Question("q", "score", "x", tuple((i, str(i)) for i in range(11))).validate()
    assert Question("q", "score", "x", ((0, "none"), (1, "some"))).validate().wire()["criteria"] == ["none", "some"]


def test_candidate_order_is_part_of_the_hash_and_wire_format():
    q1 = Question("q", "choice", "x", (("a", "A"), ("b", "B"))).validate()
    q2 = Question("q", "choice", "x", (("b", "B"), ("a", "A"))).validate()
    assert list(q1.wire()["criteria"]) == ["a", "b"] and list(q2.wire()["criteria"]) == ["b", "a"]
    r1 = DecisionRequest("r", "i", "text", [q1]).validate(); r2 = DecisionRequest("r", "i", "text", [q2]).validate()
    assert r1.questions_sha256() != r2.questions_sha256()
    # 键排序不重排候选: canonical 只排 dict 键
    assert canonical({"z": [3, 1, 2], "a": 1}) == '{"a":1,"z":[3,1,2]}'


def test_questions_hash_separate_from_input_hash():
    q = Question("q", "choice", "x", (("a", None), ("b", None))).validate()
    a = DecisionRequest("r", "i", "text one", [q]).validate(); b = DecisionRequest("r", "i", "text two", [q]).validate()
    assert a.questions_sha256() == b.questions_sha256() and a.input_sha256() != b.input_sha256()
    assert len(sha256("x")) == 64


def test_request_rejects_bad_shapes():
    q = Question("q", "choice", "x", (("a", None), ("b", None))).validate()
    for bad in (dict(state=""), dict(state=42), dict(questions=[]), dict(questions=[q, q]), dict(item_id="bad id!"), dict(contract_version="v0")):
        kw = dict(request_id="r", item_id="i", state="t", questions=[q]); kw.update(bad)
        with pytest.raises(JevError) as e:
            DecisionRequest(**kw).validate()
        assert e.value.code == "INPUT_INVALID"


def test_error_codes_are_typed():
    with pytest.raises(ValueError):
        JevError("NOT_A_CODE")
