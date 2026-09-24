# -*- coding: utf-8 -*-
"""真实 tokenizer 题行计划: plan 与 execute 用同一份 PreparedRows。

流程(§7.4): 上游 renderer 生成 state/question/criteria → 锁定 tokenizer 得完整 token 序列 → 同一构造路径取最终 input_ids,
对照 state 前缀(截断/替换/重排/省略即拒) → 核算 padding 后长度 → 超限 INPUT_TOO_LONG(不裁文本、不减候选、不分块)。
上游模块延迟 import(load_upstream), 纯测试用 tests/fakes.py 的同形假上游。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from types import SimpleNamespace

from .contracts import DecisionRequest, ExecutionBudget, JevError, canonical, sha256


def ceil64(n: int) -> int:
    """decider.model.collate 把 T 向上取到 64 的倍数。"""
    return ((n + 63) // 64) * 64


class _Keep:
    """候选顺序原样(与上游 Decider.system_one 的 _Keep 相同)。"""

    def shuffle(self, x):
        pass

    def sample(self, xs, k):
        return xs[:k]


def load_upstream() -> SimpleNamespace:
    """仅 GitHub 隔离容器: 延迟 import 上游固定源码。"""
    from decider import prompt as P, systemone as S
    from decider.infer import Example, Q
    from decider.model import collate
    return SimpleNamespace(build=P.build, MAX_OPTIONS=P.MAX_OPTIONS, render_state=S.render_state,
                           render_question=S.render_question, plan_rows=S.plan_rows, Q=Q, Example=Example, collate=collate)


@dataclass
class PreparedRow:
    row_id: str
    item_id: str
    question_id: str
    question_type: str
    kind: str                 # "list" | "iso"(score 等级逐行 yes/no)
    level: object             # iso 行的等级序号, 否则 None
    candidate_ids: list
    ids: list
    slot: int
    nopts: int
    token_len: int
    padded_len: int
    row_sha256: str


@dataclass
class PreparedRows:
    request_id: str
    item_id: str
    preparation_id: str
    questions_sha256: str
    input_sha256: str
    state_tokens: int
    rows: list

    def summary(self) -> dict:
        return {"request_id": self.request_id, "item_id": self.item_id, "preparation_id": self.preparation_id,
                "questions_sha256": self.questions_sha256, "input_sha256": self.input_sha256, "state_tokens": self.state_tokens,
                "rows": len(self.rows), "padded_tokens": sum(r.padded_len for r in self.rows),
                "row_sha256": [r.row_sha256 for r in self.rows]}


def prepare(request: DecisionRequest, tok, up, cfg: dict, budget: ExecutionBudget) -> PreparedRows:
    request.validate()
    if cfg.get("neutralize_none"):
        raise JevError("RUNTIME_UNSUPPORTED", "neutralize_none=True would rewrite candidates behind the contract")
    ctx = up.render_state(request.state)
    qmap = {q.question_id: q for q in request.questions}
    rqs = {q.question_id: up.render_question(q.wire()) for q in request.questions}
    flat, index = up.plan_rows(rqs, bool(cfg.get("isolated_levels", False)))
    ctx_ids = list(tok.encode("Context:\n" + ctx, add_special_tokens=False))
    rows = []
    for qid, kind, s, n in index:
        q = qmap[qid]
        for j in range(n):
            r = flat[s + j]
            if len(r["options"]) > up.MAX_OPTIONS:
                raise JevError("INPUT_INVALID", f"{qid}: {len(r['options'])} options > {up.MAX_OPTIONS}")
            item = up.build(up.Example(ctx, [up.Q(r["question"], list(r["options"]), 0)]), tok, _Keep(),
                            max_options=up.MAX_OPTIONS, max_ctx_tokens=len(ctx_ids), layout="state_first")
            ids = list(item["ids"])
            if ids[:len(ctx_ids)] != ctx_ids:
                raise JevError("INPUT_INVALID", f"{qid}: state prefix truncated or altered by renderer")
            if len(item["slots"]) != 1 or item["nopts"][0] != len(r["options"]) or list(item["perms"][0]) != list(range(len(r["options"]))):
                raise JevError("INPUT_INVALID", f"{qid}: candidate set/order changed during rendering")
            if len(ids) > budget.max_row_tokens:
                raise JevError("INPUT_TOO_LONG", f"{qid}: row {len(ids)} tokens > {budget.max_row_tokens} (no truncation, no chunking)")
            cand = q.candidate_ids() if kind == "list" else ["false", "true"]
            if kind == "list" and len(cand) != item["nopts"][0]:
                raise JevError("INPUT_INVALID", f"{qid}: {len(cand)} contract candidates vs {item['nopts'][0]} rendered")
            rows.append(PreparedRow(row_id=f"{request.item_id}:{qid}:{j}", item_id=request.item_id, question_id=qid,
                                    question_type=q.type, kind=kind, level=(j if kind == "iso" else None), candidate_ids=cand,
                                    ids=ids, slot=int(item["slots"][0]), nopts=int(item["nopts"][0]), token_len=len(ids),
                                    padded_len=ceil64(len(ids)), row_sha256=sha256(canonical(ids))))
    if not rows:
        raise JevError("INPUT_INVALID", "no rows planned")
    return PreparedRows(request_id=request.request_id, item_id=request.item_id, preparation_id=request.preparation_id,
                        questions_sha256=request.questions_sha256(), input_sha256=request.input_sha256(),
                        state_tokens=len(ctx_ids), rows=rows)


def rows_json(prepared: PreparedRows) -> list:
    """可公开的行计划: 不含 token ids / 原文, 只含长度与哈希。"""
    return [{k: v for k, v in asdict(r).items() if k != "ids"} for r in prepared.rows]
