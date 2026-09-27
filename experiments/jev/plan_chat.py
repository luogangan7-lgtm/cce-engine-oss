# -*- coding: utf-8 -*-
"""hf_choice 题行计划: 指令模型的 chat 模板 + 选项字母, 在「答案位」读字母的 logits(prompt spec cce.jev.hf_choice.prompt.v1)。

与 plan_work.prepare 同一职责、同一产物形状(PreparedRows), 只是渲染器换成模型自己的 chat 模板:
  用户消息 = Context / Question / Options(A. 候选id: 描述) / 作答要求 → apply_chat_template(add_generation_prompt, 模型锁里的 kwargs)
渲染后逐项核(任何一项不成立 = INPUT_INVALID / INPUT_TOO_LONG, 不裁文本、不减候选、不分块):
  ① 渲染串 == 锁里的 user_head + 用户消息 + user_tail + answer_suffix, 逐字相等(加了系统提示、内容被裁剪/改写、思考开关没关、模板被换 ⇒ 拒)
  ② 原文里不含 tokenizer 的特殊/附加 token 字面量(否则会被解析成控制符)  ③ 每个用到的字母 L: encode(渲染+L) == encode(渲染)+[id_L]
  ④ 字母 id 互不相同  ⑤ 行长 ≤ max_row_tokens
行哈希 = sha256(canonical([ids, letter_ids])) —— 被打分的类别(字母 id)也在哈希里。"""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import DecisionRequest, ExecutionBudget, JevError, Question, canonical, sha256
from .plan_work import PreparedRows

PROMPT_SPEC = "cce.jev.hf_choice.prompt.v1"


@dataclass
class ChatRow:
    row_id: str
    item_id: str
    question_id: str
    question_type: str
    kind: str
    level: object
    candidate_ids: list
    ids: list
    letter_ids: list
    nopts: int
    token_len: int
    padded_len: int          # 单行一批、无填充 ⇒ = token_len
    row_sha256: str


def render_user(state: str, q: Question, letters: str) -> str:
    """用户消息(prompt spec v1)。选项行 = 「字母. 候选id: 描述」, 与 Decider/System One 的 wire 渲染同形。"""
    lines = []
    for L, (cid, desc) in zip(letters, q.criteria):
        lines.append(f"{L}. {cid}: {desc}" if desc not in (None, "") else f"{L}. {cid}")
    return (f"Context:\n{state}\n\nQuestion: {q.instructions}\nOptions:\n" + "\n".join(lines)
            + "\nAnswer with the letter of exactly one option.")


def _special_literals(tok) -> list:
    out = set(getattr(tok, "all_special_tokens", None) or [])
    try:
        out |= set((tok.get_added_vocab() or {}).keys())
    except (AttributeError, TypeError):
        pass
    return sorted(t for t in out if isinstance(t, str) and t)


def prepare_chat(request: DecisionRequest, tok, cfg: dict, budget: ExecutionBudget) -> PreparedRows:
    """cfg = 源锁 backend_config(letters / answer_suffix / chat_template_kwargs / prompt_spec)。"""
    request.validate()
    if cfg.get("prompt_spec") != PROMPT_SPEC:
        raise JevError("RUNTIME_UNSUPPORTED", f"prompt spec {cfg.get('prompt_spec')!r} != {PROMPT_SPEC}")
    state = request.state
    if not isinstance(state, str):
        raise JevError("INPUT_INVALID", "hf_choice needs a text state")
    letters, suffix, kwargs = cfg["letters"], cfg["answer_suffix"], dict(cfg.get("chat_template_kwargs") or {})
    bad = [t for t in _special_literals(tok) if t in state]
    if bad:
        raise JevError("INPUT_INVALID", f"{request.item_id}: text contains {len(bad)} tokenizer control literal(s)")
    rows = []
    for q in request.questions:
        if q.type != "choice":
            raise JevError("RUNTIME_UNSUPPORTED", f"{q.question_id}: hf_choice scores choice questions only (got {q.type})")
        cand = q.candidate_ids()
        if len(cand) > len(letters):
            raise JevError("INPUT_INVALID", f"{q.question_id}: {len(cand)} options > {len(letters)} letters")
        user = render_user(state, q, letters)
        rendered = tok.apply_chat_template([{"role": "user", "content": user}], tokenize=False, add_generation_prompt=True, **kwargs)
        if not isinstance(rendered, str) or rendered != cfg["user_head"] + user + cfg["user_tail"] + suffix:
            raise JevError("INPUT_INVALID", f"{q.question_id}: rendered prompt != locked head + user message + tail + answer suffix "
                                            "(system prompt added, content trimmed/altered, thinking switch or template changed)")
        ids = list(tok.encode(rendered, add_special_tokens=False))
        letter_ids = []
        for L in letters[:len(cand)]:
            ext = list(tok.encode(rendered + L, add_special_tokens=False))
            if len(ext) != len(ids) + 1 or ext[:-1] != ids:
                raise JevError("INPUT_INVALID", f"{q.question_id}: letter {L} is not a single token at the answer boundary")
            letter_ids.append(int(ext[-1]))
        if len(set(letter_ids)) != len(letter_ids):
            raise JevError("INPUT_INVALID", f"{q.question_id}: letter token ids collide")
        if len(ids) > budget.max_row_tokens:
            raise JevError("INPUT_TOO_LONG", f"{q.question_id}: row {len(ids)} tokens > {budget.max_row_tokens} (no truncation, no chunking)")
        rows.append(ChatRow(row_id=f"{request.item_id}:{q.question_id}:0", item_id=request.item_id, question_id=q.question_id,
                            question_type=q.type, kind="list", level=None, candidate_ids=cand, ids=ids, letter_ids=letter_ids,
                            nopts=len(cand), token_len=len(ids), padded_len=len(ids), row_sha256=sha256(canonical([ids, letter_ids]))))
    if not rows:
        raise JevError("INPUT_INVALID", "no rows planned")
    return PreparedRows(request_id=request.request_id, item_id=request.item_id, preparation_id=request.preparation_id,
                        questions_sha256=request.questions_sha256(), input_sha256=request.input_sha256(),
                        state_tokens=len(tok.encode(state, add_special_tokens=False)), rows=rows)
