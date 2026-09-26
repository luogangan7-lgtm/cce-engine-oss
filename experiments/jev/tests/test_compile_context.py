# -*- coding: utf-8 -*-
"""s0 编译: 声明不被覆盖且不生成模型行 · 不可读面保持未知不猜 · 非法声明失败 · 完整题目/候选进预定输入 · 与生产题目逐字相同。"""
import importlib.util
import json
from pathlib import Path

import pytest

from experiments.jev import compile_context as C
from experiments.jev.contracts import JevError

ROOT = Path(__file__).resolve().parents[3]
TAX = C.load_taxonomy()
TEXT = "上周刚买的助听器今天突然没声了，充了一晚上电还是开不了机。"


def _prod_jev_questions():
    spec = importlib.util.spec_from_file_location("_s0jev", ROOT / "scripts" / "cce_s0_jev.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.jev_questions


def test_questions_verbatim_equal_to_production_jev_questions():
    prod = _prod_jev_questions()(TAX["facets"])
    for f in TAX["facets"]:
        q = C.question_for(f)
        assert q.wire() == prod[f["key"]], f["key"]
        assert list(q.wire()["criteria"]) == list(prod[f["key"]]["criteria"]), "candidate order"


def test_declared_value_is_kept_and_no_model_row_is_generated():
    qs, prov = C.compile_s0(TEXT, {"关系位置": "已购买", "进程位置": "在找方案"}, TAX)
    assert prov["关系位置"] == {"provenance": "DECLARED", "value": "已购买", "readable": "partial"}
    assert prov["进程位置"]["provenance"] == "DECLARED" and prov["进程位置"]["value"] == "在找方案"
    assert {q.question_id for q in qs}.isdisjoint({"关系位置", "进程位置"})


def test_unreadable_facets_stay_unknown_without_model():
    qs, prov = C.compile_s0(TEXT, None, TAX)
    for f in TAX["facets"]:
        if f["readable_from_text"] is False:
            assert prov[f["key"]] == {"provenance": "UNOBSERVABLE", "value": TAX["unknown_token"], "readable": False}
            assert f["key"] not in {q.question_id for q in qs}
        else:
            assert prov[f["key"]]["provenance"] == "MODEL_CANDIDATE" and f["key"] in {q.question_id for q in qs}
    assert len(qs) == sum(1 for f in TAX["facets"] if f["readable_from_text"] in (True, "partial")) == 6


@pytest.mark.parametrize("declared", [{"不存在的面": "x"}, {"关系位置": "不是取值"}, {"社会在场": "匿名 "}, "not a dict"])
def test_invalid_declaration_fails_without_guessing(declared):
    with pytest.raises(JevError) as e:
        C.compile_s0(TEXT, declared, TAX)
    assert e.value.code == "INPUT_INVALID"


def test_empty_text_fails():
    for t in ("", "   ", None):
        with pytest.raises(JevError):
            C.compile_s0(t, None, TAX)


def test_compiler_completeness_full_question_and_candidates_in_prepared_input():
    qs, _ = C.compile_s0(TEXT, None, TAX)
    facets = {f["key"]: f for f in TAX["facets"]}
    for q in qs:
        f = facets[q.question_id]
        assert f["key"] in q.instructions and f["desc"] in q.instructions        # 题意不只活在 ID 里
        ids = q.candidate_ids()
        assert ids[:len(f["values"])] == list(f["values"])                      # 候选原序
        assert C.unknown_candidate(q) in ids and sum(c in C.UNKNOWN_SET for c in ids) == 1   # unknown 唯一
        for cid, desc in q.criteria:
            assert cid == "未知" or desc == f"{f['desc']}: {cid}"


def test_build_request_uses_full_text_and_fixed_expected_set():
    long_text = TEXT * 200      # > 2000 chars: 生产切片行为不进候选
    req, prov = C.build_request({"item_id": "it-1", "text": long_text}, TAX)
    assert req.state == long_text and len(req.state) > 2000 and req.preparation_id == "full_text.v1"
    assert req.expected_keys() and len(req.expected_keys()) == len(req.questions) == 6
    assert req.original_input_sha256 == C.sha256(long_text)


V2 = C.load_task("s0_context.v2", TAX)
PR = json.loads((ROOT / "tests/data/real_corpus_pilot_prereg.json").read_text(encoding="utf-8"))
FROZEN = [PR[k] for k in PR if "冻结输入集" in k][0]["items"]


def _ref(it):
    line = (ROOT / it["file"]).read_text(encoding="utf-8").split("\n")[it["line_index"]]
    return {"file": it["file"], "line_index": it["line_index"], "line_sha256": it["sha256"], "body_sha256": C.sha256(line[:2000])}


def test_v2_emotion_residue_is_structural_and_other_questions_verbatim():
    qs, prov = C.compile_s0(TEXT, None, TAX, V2)
    assert "情绪余温" not in {q.question_id for q in qs} and len(qs) == 5
    assert prov["情绪余温"] == {"provenance": "STRUCTURAL_COLD_READ", "value": "首轮无余温", "readable": "partial"}
    prod = _prod_jev_questions()(TAX["facets"])
    for q in qs:
        assert q.wire() == prod[q.question_id] and list(q.wire()["criteria"]) == list(prod[q.question_id]["criteria"]), q.question_id
    qs, prov = C.compile_s0(TEXT, {"情绪余温": "负向余温"}, TAX, V2)                   # 调用方给了上一轮 ⇒ 声明优先
    assert prov["情绪余温"]["provenance"] == "DECLARED" and prov["情绪余温"]["value"] == "负向余温"
    v1q, v1p = C.compile_s0(TEXT, None, TAX)                                            # task=None ⇔ v1 行为不变
    assert len(v1q) == 6 and v1p["情绪余温"]["provenance"] == "MODEL_CANDIDATE"


def test_task_contract_validation():
    import copy
    for bad_id in ("s0_context.v9", "../x", "", "s0_context"):
        try:
            C.load_task(bad_id, TAX); raise AssertionError(bad_id)
        except JevError as e:
            assert e.code == "INPUT_INVALID"
    assert V2["structural_facets"]["情绪余温"]["value"] in [f for f in TAX["facets"] if f["key"] == "情绪余温"][0]["values"]


def test_text_ref_resolves_like_the_retest_and_rejects_bad_refs():
    it = next(i for i in FROZEN if i["n_chars"] > 2000)                                 # 唯一超长条: 必须截到 2000
    body = C.resolve_text_ref(_ref(it))
    assert len(body) == 2000 and C.sha256(body) == _ref(it)["body_sha256"]
    good = _ref(FROZEN[0])
    bads = [dict(good, body_sha256="0" * 64), dict(good, line_sha256="0" * 64), dict(good, line_index=10 ** 6), dict(good, line_index=-1),
            dict(good, line_index=True), dict(good, file="../config/context_taxonomy.json"), dict(good, file="config/context_taxonomy.json"),
            dict(good, file="/etc/passwd"), dict(good, file="corpus/missing.txt"), {k: v for k, v in good.items() if k != "body_sha256"},
            dict(good, extra=1)]
    texts = [C.resolve_text_ref(_ref(i)) for i in FROZEN[:5]]
    for b in bads:
        try:
            C.resolve_text_ref(b); raise AssertionError("bad ref accepted")
        except JevError as e:
            assert e.code == "INPUT_INVALID"
            leaked = sum(1 for t in texts if t[:20] in e.detail)
            assert leaked == 0, "error detail echoes input text"


def test_item_text_exactly_one_source_and_preparation_binding():
    ref = _ref(FROZEN[0])
    for bad in ({"item_id": "a", "text": "x", "text_ref": ref, "preparation_id": "text_2000.v0"}, {"item_id": "a"},
                {"item_id": "a", "text_ref": ref}, {"item_id": "a", "text_ref": ref, "preparation_id": "full_text.v1"},
                {"item_id": "a", "text": "hello", "preparation_id": "text_2000.v0"}):
        try:
            C.item_text(bad); raise AssertionError(bad.keys())
        except JevError as e:
            assert e.code == "INPUT_INVALID"
    req, prov = C.build_request({"item_id": "reddit_x.txt:0", "text_ref": ref, "preparation_id": "text_2000.v0", "expected": {}}, TAX, V2)
    assert req.preparation_id == "text_2000.v0" and req.original_input_sha256 == ref["line_sha256"] and req.source_refs == ["%s:%d" % (ref["file"], ref["line_index"])]



def test_task_with_bad_structural_facet_is_refused(tmp_path, monkeypatch):
    bad = dict(V2); bad["structural_facets"] = {"情绪余温": {"value": "首轮无余温", "provenance": "MODEL_CANDIDATE"}}
    (tmp_path / "s0_context.v2.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(C, "TASKS", tmp_path)
    for spec in ({"value": "首轮无余温", "provenance": "MODEL_CANDIDATE"}, {"value": "不存在", "provenance": "STRUCTURAL_COLD_READ"}):
        bad["structural_facets"]["情绪余温"] = spec
        (tmp_path / "s0_context.v2.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        try:
            C.load_task("s0_context.v2", TAX); raise AssertionError(spec)
        except JevError as e:
            assert e.code == "INPUT_INVALID"
