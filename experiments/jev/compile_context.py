# -*- coding: utf-8 -*-
"""s0_context 业务适配: 从 config/context_taxonomy.json 编译 Choice 问题。

逐面: 合法声明 → DECLARED(不发模型行) · 未声明且可读(True/partial) → MODEL_CANDIDATE · 未声明且不可读 → UNOBSERVABLE(记 unknown, 不调模型)
     · 声明 key/value 不合法 → INPUT_INVALID(不调模型猜测修复)。
题目文本与生产 scripts/cce_s0_jev.jev_questions **逐字相同**(闸核), 否则 Jev 重测证据不再适用于候选。
原文与情境只作数据; 新候选默认用**完整文本**(preparation_id=full_text.v1), 超长由 plan_work 拒绝, 不切片。
"""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import DecisionRequest, JevError, Question, sha256

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_PATH = ROOT / "config" / "context_taxonomy.json"
UNKNOWN_SET = {"未知", "未提及", "", None}   # 与 cce_s0_jev.UNKNOWN 相同
PREPARATION_ID = "full_text.v1"


def load_taxonomy(path=TAXONOMY_PATH) -> dict:
    t = json.loads(Path(path).read_text(encoding="utf-8"))
    for k in ("facets", "unknown_token", "schema_version"):
        if k not in t:
            raise JevError("INPUT_INVALID", f"taxonomy missing {k}")
    return t


def question_for(facet: dict) -> Question:
    """与 scripts/cce_s0_jev.jev_questions 的单面输出逐字相同(tests/test_compile_context.py 核)。"""
    opts = {v: "%s: %s" % (facet["desc"], v) for v in facet["values"]}
    if not (set(facet["values"]) & UNKNOWN_SET):
        opts["未知"] = "the text does not show this facet; do not guess"
    instructions = ("Read this facet of the reader's situation from the text. Facet: %s (%s). "
                    "If the text does not show it, choose 未知; never guess." % (facet["key"], facet["desc"]))
    return Question(question_id=facet["key"], type="choice", instructions=instructions, criteria=tuple(opts.items())).validate()


def unknown_candidate(q: Question) -> str:
    """unknown 在候选中必须有**唯一**表示(未知 或 未提及, 二选一存在)。"""
    u = [c for c in q.candidate_ids() if c in UNKNOWN_SET]
    if len(u) != 1:
        raise JevError("INPUT_INVALID", f"{q.question_id}: unknown candidates {u}")
    return u[0]


def compile_s0(text: str, declared: dict | None, taxonomy: dict):
    """→ (questions: list[Question], provenance: {facet: {provenance, value|None, readable}})。"""
    if not isinstance(text, str) or not text.strip():
        raise JevError("INPUT_INVALID", "empty text")
    facets = {f["key"]: f for f in taxonomy["facets"]}
    declared = declared or {}
    if not isinstance(declared, dict):
        raise JevError("INPUT_INVALID", "declared must be a mapping")
    for k, v in declared.items():
        if k not in facets:
            raise JevError("INPUT_INVALID", f"declared facet {k!r} not in taxonomy")
        if v not in facets[k]["values"]:
            raise JevError("INPUT_INVALID", f"declared {k}={v!r} not a taxonomy value")
    qs, prov = [], {}
    for f in taxonomy["facets"]:
        key, readable = f["key"], f["readable_from_text"]
        if key in declared:
            prov[key] = {"provenance": "DECLARED", "value": declared[key], "readable": readable}
        elif readable in (True, "partial"):
            q = question_for(f)
            unknown_candidate(q)
            qs.append(q)
            prov[key] = {"provenance": "MODEL_CANDIDATE", "value": None, "readable": readable}
        else:
            prov[key] = {"provenance": "UNOBSERVABLE", "value": taxonomy["unknown_token"], "readable": readable}
    return qs, prov


def build_request(item: dict, taxonomy: dict, preparation_id: str = PREPARATION_ID):
    """suite item {item_id, text, declared?} → (DecisionRequest, provenance)。state = 完整文本(str)。"""
    text = item.get("text")
    qs, prov = compile_s0(text, item.get("declared"), taxonomy)
    req = DecisionRequest(request_id=f"{item['item_id']}:s0", item_id=item["item_id"], state=text, questions=qs,
                          source_refs=[str(item.get("source", item["item_id"]))], original_input_sha256=sha256(text),
                          preparation_id=preparation_id)
    return req.validate(), prov
