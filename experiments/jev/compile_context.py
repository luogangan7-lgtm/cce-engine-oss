# -*- coding: utf-8 -*-
"""s0_context 业务适配: 从 config/context_taxonomy.json 编译 Choice 问题。

逐面: 合法声明 → DECLARED(不发模型行) · 未声明且可读(True/partial) → MODEL_CANDIDATE · 未声明且不可读 → UNOBSERVABLE(记 unknown, 不调模型)
     · 声明 key/value 不合法 → INPUT_INVALID(不调模型猜测修复)。
题目文本与生产 scripts/cce_s0_jev.jev_questions **逐字相同**(闸核), 否则 Jev 重测证据不再适用于候选。
原文与情境只作数据; 新候选默认用**完整文本**(preparation_id=full_text.v1), 超长由 plan_work 拒绝, 不切片。

★ 任务合同 v2(tasks/s0_context.v2.json, owner 2026-09-27「做吧」): structural_facets 里的面不出模型题 —— 未声明 ⇒ 合同写定的值,
  provenance STRUCTURAL_COLD_READ(情绪余温 是闭环接口: 调用方没给上一轮 ⇒ 首轮)。task=None 时行为与 v1 逐字相同。
★ text_ref(按指针取语料): 与 probes/s0_jev_shadow.load_passages 逐字节同一取法 —— read_text(utf-8).split("\n")[i], 整行 sha 核,
  再 [:2000](text_2000.v0), 切片 sha 核。任何不符只报指针/sha 前缀, 绝不把原文放进错误信息。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .contracts import DecisionRequest, JevError, Question, sha256

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_PATH = ROOT / "config" / "context_taxonomy.json"
UNKNOWN_SET = {"未知", "未提及", "", None}   # 与 cce_s0_jev.UNKNOWN 相同
PREPARATION_ID = "full_text.v1"
LEGACY_SLICE = 2000                          # text_2000.v0 = line[:2000], 与 2026-09-23 复测 BODY_CHARS 相同
TASKS = Path(__file__).resolve().parent / "tasks"
CORPUS_FILE_RE = re.compile(r"^corpus/[A-Za-z0-9._-]+\.txt$")
_LINES: dict = {}


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


def load_task(task_id: str, taxonomy: dict) -> dict:
    """读任务合同; structural_facets 的值必须是该面的合法取值(否则合同坏了, 不猜)。"""
    if not re.match(r"^s0_context\.v[0-9]+$", task_id or ""):
        raise JevError("INPUT_INVALID", f"task_id {task_id!r}")
    p = TASKS / f"{task_id}.json"
    if not p.is_file():
        raise JevError("INPUT_INVALID", f"task {task_id} not registered")
    task = json.loads(p.read_text(encoding="utf-8"))
    if task.get("task_id") != task_id:
        raise JevError("INPUT_INVALID", f"task file {task_id} carries task_id {task.get('task_id')!r}")
    facets = {f["key"]: f for f in taxonomy["facets"]}
    for k, spec in (task.get("structural_facets") or {}).items():
        if k not in facets or spec.get("value") not in facets[k]["values"] or spec.get("provenance") != "STRUCTURAL_COLD_READ":
            raise JevError("INPUT_INVALID", f"task {task_id}: bad structural facet {k!r}")
    return task


def resolve_text_ref(ref: dict, root: Path = ROOT) -> str:
    """{file, line_index, line_sha256, body_sha256} → line[:2000]。取法与 probes/s0_jev_shadow.load_passages 相同。"""
    if not isinstance(ref, dict) or set(ref) != {"file", "line_index", "line_sha256", "body_sha256"}:
        raise JevError("INPUT_INVALID", "text_ref must be {file, line_index, line_sha256, body_sha256}")
    f, i = ref["file"], ref["line_index"]
    if not isinstance(f, str) or not CORPUS_FILE_RE.match(f):
        raise JevError("INPUT_INVALID", "text_ref.file must match corpus/<name>.txt")
    path = (Path(root) / f).resolve()
    if path.parent != (Path(root) / "corpus").resolve() or not path.is_file():
        raise JevError("INPUT_INVALID", f"text_ref.file {f} not a file under corpus/")
    if not isinstance(i, int) or isinstance(i, bool) or i < 0:
        raise JevError("INPUT_INVALID", f"text_ref.line_index for {f} must be a non-negative int")
    key = str(path)
    if key not in _LINES:
        _LINES[key] = path.read_text(encoding="utf-8").split("\n")
    lines = _LINES[key]
    if i >= len(lines):
        raise JevError("INPUT_INVALID", f"{f}:{i} beyond {len(lines)} lines")
    line = lines[i]
    if sha256(line) != ref["line_sha256"]:
        raise JevError("INPUT_INVALID", f"{f}:{i} line sha256 {sha256(line)[:12]} != ref {str(ref['line_sha256'])[:12]}")
    body = line[:LEGACY_SLICE]
    if sha256(body) != ref["body_sha256"]:
        raise JevError("INPUT_INVALID", f"{f}:{i} body sha256 {sha256(body)[:12]} != ref {str(ref['body_sha256'])[:12]}")
    return body


def item_text(item: dict) -> tuple:
    """suite item → (text, preparation_id, original_sha256, source_ref)。inline 文本 = full_text.v1; text_ref = text_2000.v0。"""
    has_text, has_ref = "text" in item, "text_ref" in item
    if has_text == has_ref:
        raise JevError("INPUT_INVALID", f"item {item.get('item_id')!r}: exactly one of text / text_ref")
    if has_text:
        prep = item.get("preparation_id", PREPARATION_ID)
        if prep != "full_text.v1":
            raise JevError("INPUT_INVALID", f"item {item.get('item_id')!r}: inline text uses full_text.v1")
        return item["text"], prep, sha256(item["text"]) if isinstance(item["text"], str) else "", str(item.get("source", item.get("item_id")))
    prep = item.get("preparation_id")
    if prep != "text_2000.v0":
        raise JevError("INPUT_INVALID", f"item {item.get('item_id')!r}: text_ref requires preparation_id text_2000.v0")
    ref = item["text_ref"]
    body = resolve_text_ref(ref)
    return body, prep, ref["line_sha256"], "%s:%d" % (ref["file"], ref["line_index"])


def compile_s0(text: str, declared: dict | None, taxonomy: dict, task: dict | None = None):
    """→ (questions: list[Question], provenance: {facet: {provenance, value|None, readable}})。task=None ⇔ v1。"""
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
    structural = (task or {}).get("structural_facets") or {}
    qs, prov = [], {}
    for f in taxonomy["facets"]:
        key, readable = f["key"], f["readable_from_text"]
        if key in declared:
            prov[key] = {"provenance": "DECLARED", "value": declared[key], "readable": readable}
        elif key in structural:
            prov[key] = {"provenance": "STRUCTURAL_COLD_READ", "value": structural[key]["value"], "readable": readable}
        elif readable in (True, "partial"):
            q = question_for(f)
            unknown_candidate(q)
            qs.append(q)
            prov[key] = {"provenance": "MODEL_CANDIDATE", "value": None, "readable": readable}
        else:
            prov[key] = {"provenance": "UNOBSERVABLE", "value": taxonomy["unknown_token"], "readable": readable}
    return qs, prov


def build_request(item: dict, taxonomy: dict, task: dict | None = None):
    """suite item {item_id, text|text_ref, preparation_id?, declared?} → (DecisionRequest, provenance)。"""
    text, prep, original_sha, source = item_text(item)
    qs, prov = compile_s0(text, item.get("declared"), taxonomy, task)
    req = DecisionRequest(request_id=f"{item['item_id']}:s0", item_id=item["item_id"], state=text, questions=qs,
                          source_refs=[source], original_input_sha256=original_sha, preparation_id=prep)
    return req.validate(), prov
