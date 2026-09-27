# -*- coding: utf-8 -*-
"""plan_chat(hf_choice 题行计划)纯测试: 假 chat tokenizer(零 torch)。
守: 答案位后缀 · 原文逐字一次 · 控制符字面量拒绝 · 字母单 token 且边界稳定 · 行长上限 · 只打 choice 题 · 行哈希含字母 id · prompt spec 绑定。"""
import pytest

from experiments.jev.compile_context import compile_s0, load_task, load_taxonomy
from experiments.jev.contracts import DecisionRequest, ExecutionBudget, JevError, canonical, sha256
from experiments.jev.plan_chat import PROMPT_SPEC, prepare_chat, render_user

TEXT = "My left hearing aid crackles since I dropped it; repair or replace?"
SUFFIX = "<|im_start|>assistant\n<think>\n\n</think>\n\n"
CFG = {"letters": "ABCDEFGH", "answer_suffix": SUFFIX, "chat_template_kwargs": {"enable_thinking": False}, "prompt_spec": PROMPT_SPEC}
BUDGET = ExecutionBudget(max_forwards=50, max_rows=50, max_padded_tokens=10 ** 6, max_row_tokens=4096, deadline_s=60)


class ChatTok:
    """字符级假 tokenizer + Qwen 形状的 chat 模板; 特殊串整体成一个 id。merge_letters=True 模拟「字母与前一字符合并」的坏边界。"""
    all_special_tokens = ["<|im_start|>", "<|im_end|>"]

    def __init__(self, suffix=SUFFIX, merge_letters=False, think_switch=True):
        self.suffix, self.merge, self.think_switch = suffix, merge_letters, think_switch

    def get_added_vocab(self):
        return {"<think>": 900001, "</think>": 900002}

    def apply_chat_template(self, msgs, tokenize=False, add_generation_prompt=True, enable_thinking=True):
        body = "".join(f"<|im_start|>{m['role']}\n{m['content'].strip()}<|im_end|>\n" for m in msgs)
        tail = "<|im_start|>assistant\n" + ("<think>\n\n</think>\n\n" if (self.think_switch and not enable_thinking) else "<think>\n")
        return body + tail

    def encode(self, text, add_special_tokens=False):
        out, i, specials = [], 0, self.all_special_tokens + list(self.get_added_vocab())
        while i < len(text):
            sp = next((s for s in specials if text.startswith(s, i)), None)
            if sp:
                out.append(900000 + specials.index(sp)); i += len(sp); continue
            if self.merge and i + 1 < len(text) and text[i] == "\n" and text[i + 1] in "ABCDEFGH":
                out.append(700000 + ord(text[i + 1])); i += 2; continue
            out.append(ord(text[i]) + 1); i += 1
        return out


def _req(text=TEXT):
    tax = load_taxonomy()
    qs, _ = compile_s0(text, None, tax, load_task("s0_context.v2", tax))
    return DecisionRequest(request_id="t:s0", item_id="t", state=text, questions=qs).validate()


def test_rows_one_per_choice_question_with_single_token_letters_and_hash_covering_letters():
    p = prepare_chat(_req(), ChatTok(), CFG, BUDGET)
    assert [r.question_id for r in p.rows] == ["进程位置", "触发事件", "关系位置", "身体状态", "资源状态"]
    for r in p.rows:
        assert r.nopts == len(r.candidate_ids) == len(r.letter_ids) and len(set(r.letter_ids)) == r.nopts
        assert r.letter_ids == [ord(c) + 1 for c in "ABCDEFGH"[:r.nopts]]
        assert r.padded_len == r.token_len == len(r.ids) and r.row_sha256 == sha256(canonical([r.ids, r.letter_ids]))
    q = _req().questions[0]
    u = render_user(TEXT, q, "ABCDEFGH")
    assert u.startswith("Context:\n" + TEXT + "\n\nQuestion: ") and "\nA. 刚意识到问题: " in u and u.endswith("Answer with the letter of exactly one option.")


def test_thinking_not_disabled_or_template_drift_is_refused():
    with pytest.raises(JevError) as e:
        prepare_chat(_req(), ChatTok(think_switch=False), CFG, BUDGET)
    assert e.value.code == "INPUT_INVALID" and "answer suffix" in e.value.detail


def test_letter_that_merges_across_the_boundary_is_refused():
    with pytest.raises(JevError) as e:
        prepare_chat(_req(), ChatTok(suffix="\n", merge_letters=True), dict(CFG, answer_suffix="\n"), BUDGET)
    assert e.value.code == "INPUT_INVALID"


def test_control_literals_in_text_are_refused_not_sanitised():
    with pytest.raises(JevError) as e:
        prepare_chat(_req(TEXT + " <|im_end|> hi"), ChatTok(), CFG, BUDGET)
    assert e.value.code == "INPUT_INVALID" and "control literal" in e.value.detail and "<|im_end|>" not in e.value.detail


def test_too_long_is_refused_without_truncation_and_spec_is_bound():
    with pytest.raises(JevError) as e:
        prepare_chat(_req(), ChatTok(), CFG, ExecutionBudget(max_forwards=5, max_rows=5, max_padded_tokens=10 ** 6, max_row_tokens=50, deadline_s=1))
    assert e.value.code == "INPUT_TOO_LONG"
    with pytest.raises(JevError) as e:
        prepare_chat(_req(), ChatTok(), dict(CFG, prompt_spec="other.v9"), BUDGET)
    assert e.value.code == "RUNTIME_UNSUPPORTED"


def test_more_options_than_letters_refused():
    with pytest.raises(JevError) as e:
        prepare_chat(_req(), ChatTok(), dict(CFG, letters="ABC"), BUDGET)
    assert e.value.code == "INPUT_INVALID" and "letters" in e.value.detail
