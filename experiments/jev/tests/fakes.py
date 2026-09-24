# -*- coding: utf-8 -*-
"""纯测试用的假件: 假 tokenizer · 同形假上游(state-first 渲染) · 假后端。零 torch、零网络。
假上游只复刻上游 build/render/plan_rows 的**形状**(前缀 + 题块 + 单槽); 真实上游只在 GitHub smoke 验证。"""
from __future__ import annotations

from types import SimpleNamespace

from experiments.jev.contracts import DecisionRow


class FakeTokenizer:
    pad_token_id = 0

    def encode(self, text, add_special_tokens=False):
        return [ord(c) + 1 for c in text]          # 0 留给 pad


def _render_question(spec):
    t = spec.get("type", "choice"); ins = spec.get("instructions"); crit = spec.get("criteria")
    if t == "choice":
        names = list(crit); opts = [n if crit[n] in (None, "") else f"{n}: {crit[n]}" for n in names]
    elif t == "score":
        names = list(range(len(crit))); opts = [f"{i}: {c}" for i, c in enumerate(crit)]
    else:
        names = [False, True]; opts = ["no", "yes"]
    return dict(question=ins, options=opts, type="noul" if t == "bool" else t, names=names,
                legend=[str(c) for c in crit] if t == "score" else None, isolated=True)


def _plan_rows(rqs, isolated=True):
    rows, index = [], []
    for k, r in rqs.items():
        if isolated and r["type"] == "score":
            rws = [(f"{r['question']}\nProposed answer: {l}\nDoes the proposed answer fit?", ["no", "yes"]) for l in r["legend"]]
            index.append((k, "iso", len(rows), len(rws))); rows += [dict(question=t, options=o) for t, o in rws]
        else:
            index.append((k, "list", len(rows), 1)); rows.append(dict(question=r["question"], options=r["options"]))
    return rows, index


def _build(example, tok, rng=None, max_options=255, max_ctx_tokens=1536, layout="state_first"):
    ids = list(tok.encode("Context:\n" + example.context, add_special_tokens=False)[:max_ctx_tokens])
    q = example.qs[0]
    opts = list(range(len(q.options)))
    rng.shuffle(opts)
    block = "\n\nQuestion: " + q.text + "\nOptions:" + "".join(f"\n({j}) {q.options[oi]}" for j, oi in enumerate(opts)) + "\nAnswer: ("
    ids += tok.encode(block, add_special_tokens=False)
    return dict(ids=ids, slots=[len(ids) - 1], golds=[0], nopts=[len(opts)], perms=[opts])


class _Q:
    def __init__(self, text, options, gold=0):
        self.text, self.options, self.gold = text, options, gold


class _Example:
    def __init__(self, context, qs):
        self.context, self.qs = context, qs


def _collate(items, pad_id):
    T = ((max(len(it["ids"]) for it in items) + 63) // 64) * 64
    return {"input_ids": _FakeTensor([[*it["ids"], *([pad_id] * (T - len(it["ids"])))] for it in items]),
            "attention_mask": None, "slot_idx": [it["slots"][0] for it in items], "slot_batch": [i for i, _ in enumerate(items)],
            "nopts": [it["nopts"][0] for it in items]}


class _FakeTensor:
    def __init__(self, rows):
        self.rows = rows; self.shape = (len(rows), len(rows[0]) if rows else 0)

    def __getitem__(self, key):
        b, sl = key
        return _FakeVec(self.rows[b][sl])


class _FakeVec:
    def __init__(self, v):
        self.v = v

    def tolist(self):
        return list(self.v)


def fake_upstream(truncate_to=None, reorder=False):
    """truncate_to: 注错 — 渲染器悄悄截断 state; reorder: 注错 — 渲染器重排候选。"""
    def build(example, tok, rng=None, max_options=255, max_ctx_tokens=1536, layout="state_first"):
        class R:
            def shuffle(self, x):
                if reorder: x.reverse()
            def sample(self, xs, k): return xs[:k]
        return _build(example, tok, R(), max_options, truncate_to if truncate_to is not None else max_ctx_tokens, layout)
    return SimpleNamespace(build=build, MAX_OPTIONS=255, render_state=lambda s: s if isinstance(s, str) else __import__("json").dumps(s, ensure_ascii=False),
                           render_question=_render_question, plan_rows=_plan_rows, Q=_Q, Example=_Example, collate=_collate)


class FakeBackend:
    """answers: None ⇒ 恒选第一个候选(注错用, 语义闸必须变红); dict {(item, qid): candidate} ⇒ 指定答案。"""

    def __init__(self, ledger, answers=None, raw_logits=False, bad=None):
        self.ledger, self.answers, self.raw_logits, self.bad = ledger, answers, raw_logits, bad
        self.forwards_observed = 0

    def identities(self):
        return {"backend": "fake", "model_name": "fake-first-option", "param_count": 0, "dtype": "none", "device": "cpu", "load_s": 0.0}

    def evaluate(self, prepared, up):
        out = []
        for r in prepared.rows:
            self.ledger.reserve(1, r.padded_len, r.token_len)
            self.forwards_observed += 1
            n = len(r.candidate_ids)
            pick = 0 if self.answers is None else r.candidate_ids.index(self.answers[(r.item_id, r.question_id)])
            probs = [0.03 / (n - 1)] * n; probs[pick] = 0.97
            if self.bad == "nan":
                probs[pick] = float("nan")
            elif self.bad == "negative":
                probs[0], probs[pick] = -0.5, probs[pick] + 0.5 + probs[0] if pick else probs[0]
            elif self.bad == "short":
                probs = probs[:-1]
            out.append(DecisionRow(request_id=prepared.request_id, item_id=r.item_id, question_id=r.question_id, question_type=r.question_type,
                                   candidate_ids=list(r.candidate_ids), raw_candidate_logits=([0.0] * n if self.raw_logits else "unavailable"),
                                   probabilities=probs, selected_candidate=r.candidate_ids[pick], semantic_status="OK",
                                   identities={"row_sha256": r.row_sha256}, timing={"forward_s": 0.001, "token_len": r.token_len, "padded_len": r.padded_len}))
            if self.bad == "duplicate":
                out.append(out[-1])
            if self.bad == "drop":
                out.pop()
        return out


def github_env(workflow="cce-jev-eval.yml", **over):
    env = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "GITHUB_REPOSITORY": "luogangan7-lgtm/cce-engine-oss",
           "GITHUB_WORKFLOW_REF": f"luogangan7-lgtm/cce-engine-oss/.github/workflows/{workflow}@refs/heads/master",
           "GITHUB_RUN_ID": "123456789", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40}
    env.update(over)
    return env


def receipt_for(env, workflow="cce-jev-eval.yml", suite_id="s0-smoke-v1"):
    return {"schema": "cce.jev.admission-receipt.v1", "permit_id": "TEST-PERMIT", "repository": env["GITHUB_REPOSITORY"],
            "execution_commit": env["GITHUB_SHA"], "run_id": env["GITHUB_RUN_ID"], "workflow_id": workflow, "suite_id": suite_id}
