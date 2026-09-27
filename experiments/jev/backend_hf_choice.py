# -*- coding: utf-8 -*-
"""hf_choice 适配器: 指令模型(Qwen3 / Qwen3.5 文本端)按选项字母打分。一次加载, 单行一批, 无回退、无重试、无减批。

★ 数值路径(2026-09-27 定, 理由见 docs/cce_jev_deployment.md「Qwen 候选」):
  权重 = 发布的 bf16 原样(文件映射, 不复制成 fp32 —— 4B 的 fp32 放不进 12 GiB);
  计算 = fp32: 每个 nn.Linear 调用时 F.linear(x_fp32, W.float()), Embedding 输出转 fp32, 其余浮点参数/缓冲一律转 fp32,
  检查点里本来就是 F32 的张量(Qwen3.5 的 A_log / linear_attn.norm)从 safetensors 原值恢复。
  ⇒ 与 Decider(fp32)同一 dtype 路径; 不依赖 runner 是否有 AVX512_BF16/AMX(GitHub 池子 ~60% 是 AVX2), 跨 CPU 数值差在 fp32 量级。
★ 打分: 基座模型最后一层(已过 final norm)在最后位置的隐状态 h(fp32) · 输出嵌入的字母行(fp32)ᵀ —— 不对全词表调 lm_head。
  p = softmax(raw / T), T 来自源锁(1.0); 并列取靠前字母。诊断量(不进判决): 全词表 softmax 下字母的总质量、全词表 top-1 是否为某个字母。
★ 加载闸: missing / mismatched / unexpected 必须与资产锁里 prepare 实测并审过的清单逐项相同, 参数量相同, 类名与 model_type 相同。"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .contracts import DecisionRow, JevError, canonical, sha256
from .execution_guard import require
from .plan_work import PreparedRows


def _fp32_compute(model, torch):
    """把模型改成「bf16 存权重、fp32 算」; 返回计数。任何未覆盖到的非 fp32 浮点参数 ⇒ RUNTIME_UNSUPPORTED。"""
    import types
    nn, F = torch.nn, torch.nn.functional

    def lin(self, x):
        return F.linear(x.float(), self.weight.float(), None if self.bias is None else self.bias.float())

    def emb(self, ids):
        return F.embedding(ids, self.weight, self.padding_idx).float()

    n = {"linear": 0, "embedding": 0, "params_to_fp32": 0, "buffers_to_fp32": 0}
    sub = sorted({type(m).__name__ for m in model.modules()
                  if isinstance(m, (nn.Linear, nn.Embedding)) and type(m) not in (nn.Linear, nn.Embedding)})
    if sub:                                            # 子类的 forward 语义未知: 不猜, 拒绝
        raise JevError("RUNTIME_UNSUPPORTED", f"Linear/Embedding subclasses present: {sub}")
    kept = set()
    for mod in model.modules():
        if type(mod) is nn.Linear:
            mod.forward = types.MethodType(lin, mod); n["linear"] += 1
            kept.update(id(p) for p in mod.parameters(recurse=False))
        elif type(mod) is nn.Embedding:
            mod.forward = types.MethodType(emb, mod); n["embedding"] += 1
            kept.update(id(p) for p in mod.parameters(recurse=False))
    for mod in model.modules():
        for name, p in list(mod.named_parameters(recurse=False)):
            if id(p) not in kept and p.is_floating_point() and p.dtype != torch.float32:
                p.data = p.data.float(); n["params_to_fp32"] += 1
        for name, b in list(mod.named_buffers(recurse=False)):
            if b is not None and b.is_floating_point() and b.dtype != torch.float32:
                mod._buffers[name] = b.float(); n["buffers_to_fp32"] += 1
    stray = [nm for nm, p in model.named_parameters() if id(p) not in kept and p.dtype != torch.float32]
    if stray:
        raise JevError("RUNTIME_UNSUPPORTED", f"{len(stray)} parameters outside patched Linear/Embedding are not fp32 (e.g. {stray[0]})")
    return n


def _restore_checkpoint_f32(model, bundle: Path, torch) -> dict:
    """检查点里 dtype=F32 的张量按原值写回(bf16 加载会把它们舍入)。键名映射: 原名, 或 model.language_model.* → model.*。"""
    from safetensors import safe_open
    params = dict(model.named_parameters())
    restored, unmapped = 0, []
    for shard in sorted(p for p in bundle.iterdir() if p.name.endswith(".safetensors")):
        with open(shard, "rb") as fh:
            hlen = int.from_bytes(fh.read(8), "little")
            header = json.loads(fh.read(hlen))
        f32 = [k for k, v in header.items() if k != "__metadata__" and v.get("dtype") == "F32"]
        if not f32:
            continue
        with safe_open(str(shard), framework="pt") as st:
            for k in f32:
                target = next((c for c in (k, k.replace("model.language_model.", "model.", 1)) if c in params), None)
                if target is None:
                    if not (k.startswith("mtp.") or k.startswith("model.visual.")):
                        unmapped.append(k)
                    continue
                t = st.get_tensor(k)
                p = params[target]
                if p.dtype != torch.float32 or tuple(p.shape) != tuple(t.shape):
                    raise JevError("RUNTIME_UNSUPPORTED", f"checkpoint-F32 tensor {k} lands on a non-fp32 or differently shaped parameter")
                with torch.no_grad():
                    p.copy_(t)
                restored += 1
    if unmapped:
        raise JevError("MODEL_BUNDLE_INVALID", f"{len(unmapped)} checkpoint-F32 tensors map to no parameter (e.g. {unmapped[0]})")
    return {"restored": restored}


class HfChoiceBackend:
    def __init__(self, bundle_dir, src: dict, assets: dict, ledger, env: dict, receipt: dict, expect_workflow: str = "cce-jev-llm-eval.yml",
                 require_pinned_load: bool = True):
        require(env, receipt, expect_workflow)
        cfg = src["backend_config"]
        if cfg.get("storage_dtype") != "bfloat16" or cfg.get("compute_dtype") != "float32" or cfg.get("load_class") != "AutoModelForCausalLM":
            raise JevError("RUNTIME_UNSUPPORTED", "hf_choice supports storage bfloat16 / compute float32 / AutoModelForCausalLM only")
        import torch                                   # 延迟 import: 守卫之后
        from transformers import AutoModelForCausalLM
        threads = int(cfg["threads"])
        torch.set_num_threads(threads)
        bundle = Path(bundle_dir)
        t0 = time.monotonic()
        model, info = AutoModelForCausalLM.from_pretrained(str(bundle), dtype=torch.bfloat16, local_files_only=True, output_loading_info=True)
        model.eval()
        info = {k: sorted(str(x) for x in (v or [])) for k, v in info.items() if k in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")}
        if type(model).__name__ != cfg["expected_class"] or getattr(model.config, "model_type", None) != cfg.get("expected_model_type"):
            raise JevError("MODEL_VERSION_MISMATCH", f"loaded {type(model).__name__}/{getattr(model.config, 'model_type', None)} != lock {cfg['expected_class']}/{cfg.get('expected_model_type')}")
        param_count = int(sum(p.numel() for p in model.parameters()))
        pinned = (assets.get("observed_load") or {})
        if require_pinned_load:
            want = {"loading_info": pinned.get("loading_info"), "param_count": pinned.get("param_count")}
            got = {"loading_info": info, "param_count": param_count}
            if want != got:
                raise JevError("MODEL_BUNDLE_INVALID", f"load differs from the reviewed prepare observation: {canonical(got)[:300]} vs {canonical(want)[:300]}")
        elif info.get("mismatched_keys") or info.get("error_msgs"):
            raise JevError("MODEL_BUNDLE_INVALID", "mismatched keys / load errors during prepare smoke")
        self.patch = _fp32_compute(model, torch)
        self.f32 = _restore_checkpoint_f32(model, bundle, torch)
        self.load_s = round(time.monotonic() - t0, 3)
        self.model, self.torch, self.ledger, self.threads, self.cfg = model, torch, ledger, threads, cfg
        self.base = model.get_decoder() if hasattr(model, "get_decoder") else model.model
        self.out_w = model.get_output_embeddings().weight          # 绑定时即 embed_tokens.weight(bf16, 不复制)
        self.T = float(cfg["temperature"])
        self.param_count, self.loading_info = param_count, info
        self.forwards_observed = 0
        self.effective = {"backend": "hf_choice", "model_name": src["model_version"], "repo_id": src["repo_id"], "revision": src["revision"],
                          "class": type(model).__name__, "model_type": model.config.model_type, "param_count": param_count,
                          "storage_dtype": str(self.out_w.dtype), "compute_dtype": "torch.float32", "temperature": self.T,
                          "threads": threads, "letters": cfg["letters"], "prompt_spec": cfg["prompt_spec"], "patch": self.patch,
                          "checkpoint_f32_restored": self.f32["restored"], "loading_info": info, "load_s": self.load_s,
                          "torch": torch.__version__, "cpu_capability": _cpu_capability(torch)}

    def identities(self) -> dict:
        return dict(self.effective, device="cpu", batch_rows=1, layout="chat_letter")

    def _forward_last(self, ids):
        torch = self.torch
        self.forwards_observed += 1
        out = self.base(input_ids=torch.tensor([ids], dtype=torch.long), use_cache=False)
        return out.last_hidden_state[0, -1].float()

    def _vocab_diag(self, h, letter_ids):
        """全词表 softmax(分块, fp32)下字母的总质量与 top-1 是否为字母 —— 诊断「模型是不是真在用字母作答」, 不进判决。"""
        torch = self.torch
        W, step, mx, arg, chunks = self.out_w, 32768, None, None, []
        for s in range(0, W.shape[0], step):
            lg = W[s:s + step].float() @ h
            chunks.append(lg)
            m, a = lg.max(0)
            if mx is None or m > mx:
                mx, arg = m, s + int(a)
        full = torch.cat(chunks)
        lse = torch.logsumexp(full, 0)
        mass = float(torch.exp(full[letter_ids] - lse).sum())
        return round(mass, 6), int(arg) in set(letter_ids)

    def evaluate(self, prepared: PreparedRows, up=None) -> list:
        torch = self.torch
        out = []
        for r in prepared.rows:
            if sha256(canonical([list(r.ids), list(r.letter_ids)])) != r.row_sha256 or len(r.letter_ids) != r.nopts:
                raise JevError("INPUT_INVALID", f"{r.row_id}: row differs from the planned row")
            n = len(r.ids)
            self.ledger.reserve(1, n, n)                     # 预约在前向之前; 撞上限即失败
            before = self.forwards_observed
            t0 = time.monotonic()
            with torch.inference_mode():
                h = self._forward_last(list(r.ids))
                raw_t = self.out_w[list(r.letter_ids)].float() @ h
                mass, top_is_letter = self._vocab_diag(h, list(r.letter_ids))
            dt = time.monotonic() - t0
            if self.forwards_observed != before + 1:
                raise JevError("RESOURCE_EXCEEDED", f"{r.row_id}: forward count drift")
            raw = [float(x) for x in raw_t.tolist()]
            probs = [float(x) for x in torch.softmax(raw_t / self.T, -1).tolist()]
            j = max(range(len(probs)), key=probs.__getitem__)          # 并列取靠前(max 返回首个最大)
            out.append(DecisionRow(request_id=prepared.request_id, item_id=r.item_id, question_id=r.question_id, question_type=r.question_type,
                                   candidate_ids=list(r.candidate_ids), raw_candidate_logits=raw, probabilities=probs,
                                   selected_candidate=r.candidate_ids[j], semantic_status="OK",
                                   identities={"row_sha256": r.row_sha256, "kind": r.kind, "level": r.level,
                                               "letter_mass": mass, "vocab_top1_is_letter": top_is_letter},
                                   timing={"forward_s": round(dt, 4), "token_len": n, "padded_len": n}))
        return out


def _cpu_capability(torch) -> str:
    try:
        return str(torch.backends.cpu.get_cpu_capability())
    except Exception:  # noqa: BLE001
        return "unavailable"
