# -*- coding: utf-8 -*-
"""cce.jev 纯合同层 —— 数据形状 · 校验 · 规范哈希 · 错误码。

import 零副作用: 只用标准库; 不碰 torch / transformers / decider / 网络 / 密钥文件。
候选顺序是合同的一部分: 有序列表原样保留, 规范哈希只做键排序, 不重排候选。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field

CONTRACT_VERSION = "cce.jev.contract.v1"
REPORT_SCHEMA = "cce.jev.evaluation.v1"
QUESTION_TYPES = ("choice", "noul", "score")
PROVENANCE = ("DECLARED", "MODEL_CANDIDATE", "UNOBSERVABLE", "STRUCTURAL_COLD_READ")
PREPARATION_IDS = ("full_text.v1", "text_2000.v0")   # text_2000.v0 = 与 2026-09-23 Jev/MiniMax 复测同一切片 line[:2000]
# 每个 item×question 的终态, 只能属其一; 失败项仍留在分母。
FINAL_STATUSES = ("OK", "DECLARED", "UNOBSERVABLE", "STRUCTURAL_COLD_READ", "SEMANTIC_UNKNOWN", "REVIEW_REQUIRED", "FAILED", "NOT_RUN")
ERROR_CODES = (
    "EXECUTION_LOCATION_FORBIDDEN",
    "PERMIT_NOT_APPROVED", "PERMIT_ALREADY_USED", "PERMIT_EXPIRED",
    "MODEL_BUNDLE_INVALID", "MODEL_VERSION_MISMATCH",
    "DEPENDENCY_LOCK_INVALID", "RUNTIME_UNSUPPORTED",
    "INPUT_INVALID", "INPUT_TOO_LONG",
    "BUDGET_EXCEEDED", "RESOURCE_EXCEEDED", "TIMEOUT",
    "OUTPUT_INVALID", "COVERAGE_MISMATCH", "SEMANTIC_CHECK_FAILED",
)
ID_RE = re.compile(r"^[A-Za-z0-9._:一-鿿-]{1,80}$")
MAX_CHOICE, MAX_LEVELS = 255, 10   # 与 decider.systemone 一致


class JevError(Exception):
    """类型化失败。code 必须在 ERROR_CODES 里; 不重试、不换模型、不静默修复。"""

    def __init__(self, code: str, detail: str = ""):
        if code not in ERROR_CODES:
            raise ValueError(f"unknown error code {code!r}")
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail = code, detail


def canonical(obj) -> str:
    """键排序 + 紧凑分隔; 列表顺序不动(候选顺序是合同)。"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256(data) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Question:
    question_id: str
    type: str
    instructions: str
    criteria: tuple          # ((candidate_id, description|None), ...) 有序; score: ((0, desc), (1, desc), ...)

    def validate(self) -> "Question":
        if not isinstance(self.question_id, str) or not ID_RE.match(self.question_id):
            raise JevError("INPUT_INVALID", f"question_id {self.question_id!r}")
        if self.type not in QUESTION_TYPES:
            raise JevError("INPUT_INVALID", f"question type {self.type!r}")
        if not isinstance(self.instructions, str) or not self.instructions.strip():
            raise JevError("INPUT_INVALID", f"{self.question_id}: empty instructions")
        ids = self.candidate_ids()
        if len(set(ids)) != len(ids):
            raise JevError("INPUT_INVALID", f"{self.question_id}: duplicate candidate ids")
        lo, hi = (2, MAX_LEVELS) if self.type == "score" else (2, MAX_CHOICE)
        if self.type == "noul":
            if tuple(ids) != ("false", "true"):
                raise JevError("INPUT_INVALID", f"{self.question_id}: noul candidates must be ('false','true')")
        elif not lo <= len(ids) <= hi:
            raise JevError("INPUT_INVALID", f"{self.question_id}: {len(ids)} candidates, need {lo}..{hi}")
        return self

    def candidate_ids(self) -> list:
        return [c[0] for c in self.criteria]

    def hash_form(self) -> list:
        """进哈希的形状: criteria 用有序对列表 —— canonical() 会排 dict 键, 只有列表能保住候选顺序。"""
        return [self.question_id, self.type, self.instructions, [list(c) for c in self.criteria]]

    def wire(self) -> dict:
        """Jev / System One 线格式(decider.systemone.render_question 读的就是这个)。dict 保序 ⇒ 候选顺序原样。"""
        if self.type == "score":
            return {"type": "score", "instructions": self.instructions, "criteria": [d for _, d in self.criteria]}
        if self.type == "noul":
            c = {k: d for k, d in self.criteria if d not in (None, "")}
            return {"type": "noul", "instructions": self.instructions, "criteria": c}
        return {"type": "choice", "instructions": self.instructions, "criteria": {k: d for k, d in self.criteria}}


@dataclass
class DecisionRequest:
    request_id: str
    item_id: str
    state: object                    # str 或 JSON 数据(dict/list); 作为数据, 绝不执行
    questions: list                  # list[Question], 有序
    source_refs: list = field(default_factory=list)
    original_input_sha256: str = ""
    contract_version: str = CONTRACT_VERSION
    preparation_id: str = "full_text.v1"

    def validate(self) -> "DecisionRequest":
        for name in ("request_id", "item_id"):
            v = getattr(self, name)
            if not isinstance(v, str) or not ID_RE.match(v):
                raise JevError("INPUT_INVALID", f"{name} {v!r}")
        if not isinstance(self.state, (str, dict, list)):
            raise JevError("INPUT_INVALID", "state must be str or JSON data")
        if isinstance(self.state, str) and not self.state.strip():
            raise JevError("INPUT_INVALID", "empty state")
        if not self.questions:
            raise JevError("INPUT_INVALID", "no questions")
        seen = set()
        for q in self.questions:
            q.validate()
            if q.question_id in seen:
                raise JevError("INPUT_INVALID", f"duplicate question_id {q.question_id}")
            seen.add(q.question_id)
        if self.contract_version != CONTRACT_VERSION:
            raise JevError("INPUT_INVALID", f"contract_version {self.contract_version!r}")
        if self.preparation_id not in PREPARATION_IDS:
            raise JevError("INPUT_INVALID", f"preparation_id {self.preparation_id!r}")
        return self

    def questions_sha256(self) -> str:
        """题目集 hash —— 与输入 hash 分开, 不把每篇不同文本记成不同本体版本。"""
        return sha256(canonical([q.hash_form() for q in self.questions]))

    def input_sha256(self) -> str:
        return sha256(canonical({"state": self.state, "questions": [q.hash_form() for q in self.questions],
                                 "preparation_id": self.preparation_id}))

    def expected_keys(self) -> list:
        return [(self.item_id, q.question_id) for q in self.questions]


@dataclass(frozen=True)
class ExecutionBudget:
    max_forwards: int
    max_rows: int
    max_padded_tokens: int
    max_row_tokens: int
    deadline_s: float
    max_download_bytes: int = 0

    @classmethod
    def from_policy(cls, p: dict) -> "ExecutionBudget":
        return cls(max_forwards=int(p["max_forwards"]), max_rows=int(p["max_rows"]),
                   max_padded_tokens=int(p["max_padded_tokens"]), max_row_tokens=int(p["max_row_tokens"]),
                   deadline_s=float(p["model_load_plus_infer_deadline_s"]), max_download_bytes=int(p.get("max_download_bytes", 0)))


@dataclass
class DecisionRow:
    request_id: str
    item_id: str
    question_id: str
    question_type: str
    candidate_ids: list                  # 原始顺序
    raw_candidate_logits: object         # list[float](只含有效候选) 或 "unavailable"; 绝不伪造
    probabilities: list                  # 有效候选的完整分布
    selected_candidate: object           # 仅结果读出, 不代表准入
    semantic_status: str = "OK"
    identities: dict = field(default_factory=dict)
    timing: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)


def _finite_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def validate_row(row: DecisionRow, q: Question, tol: float = 1e-4) -> DecisionRow:
    """拒绝 NaN/Inf/负概率/重复或未知候选/缺候选/题型不符。容差显式, 不静默修复。"""
    ids = q.candidate_ids()
    if row.question_type != q.type:
        raise JevError("OUTPUT_INVALID", f"{row.question_id}: type {row.question_type!r} != {q.type!r}")
    if list(row.candidate_ids) != ids:
        raise JevError("OUTPUT_INVALID", f"{row.question_id}: candidate ids/order differ from question")
    p = row.probabilities
    if not isinstance(p, list) or len(p) != len(ids):
        raise JevError("OUTPUT_INVALID", f"{row.question_id}: {0 if not isinstance(p, list) else len(p)} probabilities for {len(ids)} candidates")
    for x in p:
        if not _finite_number(x) or x < 0:
            raise JevError("OUTPUT_INVALID", f"{row.question_id}: bad probability {x!r}")
    if abs(sum(p) - 1.0) > tol:
        raise JevError("OUTPUT_INVALID", f"{row.question_id}: probabilities sum {sum(p)!r} (tol {tol})")
    if row.raw_candidate_logits != "unavailable":
        lg = row.raw_candidate_logits
        if not isinstance(lg, list) or len(lg) != len(ids) or not all(_finite_number(x) for x in lg):
            raise JevError("OUTPUT_INVALID", f"{row.question_id}: raw logits must be finite floats for valid candidates only")
    if row.selected_candidate not in ids:
        raise JevError("OUTPUT_INVALID", f"{row.question_id}: selected {row.selected_candidate!r} not a candidate")
    if row.semantic_status not in FINAL_STATUSES:
        raise JevError("OUTPUT_INVALID", f"{row.question_id}: status {row.semantic_status!r}")
    return row
