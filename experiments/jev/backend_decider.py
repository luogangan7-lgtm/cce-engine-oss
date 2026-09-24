# -*- coding: utf-8 -*-
"""唯一模型适配器: Decider(Mapika/decider-2b v10) CPU eager, float32, 一次加载, 微批 1 行。

构造前守卫(GitHub-only) → 延迟 import torch/decider → 显式配置构造 → 核对**构造后有效配置** → 包住 slot_logits 计数。
每行: 同一 PreparedRow 走 collate → 在 slot_logits 边界再核行哈希 → 账本原子预约 → 前向 → 只保存有效候选的 raw logits。
无回退(不去 TypeSafe/MiniMax)、无自动重试、无减批。"""
from __future__ import annotations

import time

from .contracts import DecisionRow, JevError, canonical, sha256
from .execution_guard import require
from .plan_work import PreparedRows


class DeciderBackend:
    def __init__(self, bundle_dir, cfg: dict, ledger, env: dict, receipt: dict, threads: int = 3, expect_workflow: str = "cce-jev-eval.yml"):
        require(env, receipt, expect_workflow)
        if cfg.get("neutralize_none"):
            raise JevError("RUNTIME_UNSUPPORTED", "neutralize_none=True not supported by this adapter")
        import torch                                   # 延迟 import: 守卫之后
        from decider.infer import Decider
        torch.set_num_threads(int(threads))
        t0 = time.monotonic()
        d = Decider(path=str(bundle_dir), device="cpu", dtype=torch.float32, use_graphs=False, temperature=cfg["temperature"])
        self.load_s = round(time.monotonic() - t0, 3)
        eff = {"temperature": float(d.T), "device": str(d.dev), "engine": d.eng is None and "eager" or "graph",
               "isolated_levels": bool(d.isolated_levels), "name": d.name, "neutralize_none": bool(d.neutralize_none),
               "schema_first": bool(d.schema_first), "dtype": str(next(d.m.parameters()).dtype)}
        want = {"temperature": float(cfg["temperature"]), "device": "cpu", "engine": "eager", "isolated_levels": bool(cfg["isolated_levels"]),
                "name": "decider-" + str(cfg["version"]), "neutralize_none": False, "schema_first": False, "dtype": "torch.float32"}
        diff = {k: (eff[k], want[k]) for k in want if eff[k] != want[k]}
        if diff:
            raise JevError("MODEL_VERSION_MISMATCH", f"effective config differs from lock: {diff}")
        self.d, self.torch, self.ledger, self.threads = d, torch, ledger, int(threads)
        self.effective = eff
        self.param_count = int(sum(p.numel() for p in d.m.parameters()))
        self.forwards_observed = 0
        orig = d.m.slot_logits

        def counted(*a, **k):
            self.forwards_observed += 1          # 任何路径的 backbone 前向都计数
            return orig(*a, **k)
        d.m.slot_logits = counted

    def identities(self) -> dict:
        return {"backend": "decider", "model_name": self.effective["name"], "param_count": self.param_count,
                "dtype": self.effective["dtype"], "device": "cpu", "threads": self.threads, "temperature": self.effective["temperature"],
                "isolated_levels": self.effective["isolated_levels"], "layout": "state_first", "batch_rows": 1, "load_s": self.load_s,
                "torch": self.torch.__version__}

    def evaluate(self, prepared: PreparedRows, up) -> list:
        torch = self.torch
        pad = self.d.m.tok.pad_token_id
        out = []
        for r in prepared.rows:
            item = {"ids": list(r.ids), "slots": [r.slot], "golds": [0], "nopts": [r.nopts], "perms": [list(range(r.nopts))]}
            b = up.collate([item], pad)
            n = len(r.ids)
            got = b["input_ids"][0, :n].tolist()
            if got != list(r.ids) or sha256(canonical(got)) != r.row_sha256 or int(b["slot_idx"][0]) != r.slot or int(b["nopts"][0]) != r.nopts:
                raise JevError("INPUT_INVALID", f"{r.row_id}: row differs at slot_logits boundary from planned row")
            T = int(b["input_ids"].shape[1])
            self.ledger.reserve(1, T, n)                     # 预约在前向之前; 撞上限即失败
            before = self.forwards_observed
            t0 = time.monotonic()
            with torch.no_grad():
                lg = self.d.m.slot_logits(b["input_ids"], b["attention_mask"], b["slot_idx"], b["slot_batch"], b["nopts"])
            dt = time.monotonic() - t0
            if self.forwards_observed != before + 1:
                raise JevError("RESOURCE_EXCEEDED", f"{r.row_id}: forward count drift ({self.forwards_observed - before} per row)")
            valid = lg[0, :r.nopts].float()
            raw = [float(x) for x in valid.tolist()]
            probs = [float(x) for x in torch.softmax(valid / self.d.T, -1).tolist()]
            j = max(range(len(probs)), key=probs.__getitem__)
            out.append(DecisionRow(request_id=prepared.request_id, item_id=r.item_id, question_id=r.question_id, question_type=r.question_type,
                                   candidate_ids=list(r.candidate_ids), raw_candidate_logits=raw, probabilities=probs,
                                   selected_candidate=r.candidate_ids[j], semantic_status="OK",
                                   identities={"row_sha256": r.row_sha256, "kind": r.kind, "level": r.level},
                                   timing={"forward_s": round(dt, 4), "token_len": n, "padded_len": T}))
        return out
