#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cce.jev 入口。`--help` / `check-locks` / `plan` 永不 import torch、不联网、不读任何密钥文件。
`prepare` / `eval` 第一件事是 GitHub-only 守卫; 本机直接跑 = EXECUTION_LOCATION_FORBIDDEN(退出码 3), 在任何下载/import 之前。"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.jev.contracts import JevError, file_sha256, sha256  # noqa: E402
from experiments.jev import execution_guard  # noqa: E402

EXIT_TYPED = 3


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _receipt(path):
    r = _load(path)
    if r.get("schema") != execution_guard.RECEIPT_SCHEMA:
        raise JevError("PERMIT_NOT_APPROVED", "admission receipt schema mismatch")
    return r


LLM_PREPARE_WF, LLM_EVAL_WF = "cce-jev-llm-prepare.yml", "cce-jev-llm-eval.yml"


def _is_legacy(key) -> bool:
    return key in (None, "decider-2b")


def _model_locks(key):
    """(源锁 dict, 资产锁 dict, 源锁路径, 资产锁路径); 纯标准库。"""
    from experiments.jev import strict_assets as SA
    sp, ap = SA.model_paths(key)
    return SA.source_lock(sp), SA.assets_lock(ap), sp, ap


def _receipt_model(receipt: dict, key: str) -> None:
    """新许可(schema v2)在回执里列出被批准的模型键; 不在单子上的模型一律拒绝(不能拿 A 模型的许可跑 B)。"""
    if key not in (receipt.get("models") or []):
        raise JevError("PERMIT_NOT_APPROVED", f"model {key!r} not in the admitted permit's model list")


def cmd_check_locks(a):
    from experiments.jev import strict_assets as SA
    if not _is_legacy(getattr(a, "model", None)):
        src, assets, _sp, _ap = _model_locks(a.model)
        problems = [f"source lock file {n}: bad anchor" for n, spec in src["files"].items()
                    if spec["anchor"]["kind"] not in ("lfs_sha256", "git_blob_sha1") or int(spec["size"]) <= 0]
        rt = _load(HERE / "locks" / "cpu-runtime.lock.json"); dep = HERE / "locks" / "runtime-cpu.lock.txt"
        if a.require_ready:
            if assets.get("status") != "READY" or assets.get("revision") != src["revision"] or set(assets.get("files") or {}) != set(src["files"]):
                problems.append(f"models/{a.model}/model.assets.lock.json not READY / not matching the source lock (run the llm prepare, review, commit)")
            elif not (assets.get("observed_load") or {}).get("param_count"):
                problems.append(f"models/{a.model}/model.assets.lock.json lacks the reviewed observed_load (loading_info + param_count)")
            if rt.get("status") != "READY" or not dep.is_file() or rt.get("dependency_lock_sha256") != file_sha256(dep):
                problems.append("cpu runtime lock not READY / sha mismatch")
        print(json.dumps({"model": a.model, "backend": src.get("backend"), "revision": src["revision"], "assets_lock_status": assets.get("status"),
                          "problems": problems}, ensure_ascii=False, indent=1))
        if problems:
            raise JevError("DEPENDENCY_LOCK_INVALID", "; ".join(problems))
        return
    src = SA.source_lock()
    acts = _load(HERE / "locks" / "actions.lock.json")
    problems = []
    for name, spec in src["files"].items():
        if spec["anchor"]["kind"] not in ("lfs_sha256", "git_blob_sha1") or int(spec["size"]) <= 0:
            problems.append(f"source lock file {name}: bad anchor")
    assets = SA.assets_lock()
    rt = _load(HERE / "locks" / "cpu-runtime.lock.json")
    dep = HERE / "locks" / "runtime-cpu.lock.txt"
    ready = assets.get("status") == "READY" and rt.get("status") == "READY" and dep.is_file()
    if a.require_ready:
        if assets.get("status") != "READY":
            problems.append("model.assets.lock.json not READY (run cce-jev-prepare.yml, review, commit)")
        if rt.get("status") != "READY" or not dep.is_file():
            problems.append("cpu runtime lock not READY / runtime-cpu.lock.txt missing")
        elif rt.get("dependency_lock_sha256") != file_sha256(dep):
            problems.append("runtime-cpu.lock.txt sha256 != cpu-runtime.lock.json.dependency_lock_sha256")
    for wf in ("cce-jev-contract.yml", "cce-jev-prepare.yml", "cce-jev-eval.yml", LLM_PREPARE_WF, LLM_EVAL_WF):
        text = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("- uses:") or s.startswith("uses:"):
                ref = s.split("uses:", 1)[1].split("#")[0].strip()
                action, _, sha = ref.partition("@")
                base = "/".join(action.split("/")[:2])
                if base not in acts or acts[base]["sha"] != sha:
                    problems.append(f"{wf}: {ref} not pinned to actions.lock.json sha")
    print(json.dumps({"source_revision": src["revision"], "assets_lock_status": assets.get("status"), "runtime_lock_status": rt.get("status"),
                      "ready_for_eval": ready, "problems": problems}, ensure_ascii=False, indent=1))
    if problems:
        raise JevError("DEPENDENCY_LOCK_INVALID", "; ".join(problems))


POLICY_RE = re.compile(r"^[a-z0-9_]{3,40}\.json$")


def _policy(name: str) -> dict:
    if not POLICY_RE.match(name or ""):
        raise JevError("PERMIT_NOT_APPROVED", f"resource policy name {name!r}")
    p = HERE / "policies" / name
    if not p.is_file():
        raise JevError("PERMIT_NOT_APPROVED", f"resource policy {name} not registered")
    return _load(p)


def _manifest_policy(manifest: dict) -> str:
    return manifest.get("policy", "cpu_smoke.json")


def eval_policy(receipt: dict, suite: str, manifest: dict) -> dict:
    """容器内再核一次(admit 已在消耗前核过): 回执 suite == 请求 suite, 回执策略 == suite 清单策略; 返回该策略。"""
    if receipt.get("suite_id") != suite:
        raise JevError("PERMIT_NOT_APPROVED", f"receipt suite {receipt.get('suite_id')!r} != {suite!r}")
    if receipt.get("resource_policy") != _manifest_policy(manifest):
        raise JevError("PERMIT_NOT_APPROVED", f"permit policy {receipt.get('resource_policy')!r} != suite policy {_manifest_policy(manifest)!r}")
    return _policy(receipt["resource_policy"])


def cmd_plan(a):
    """编译 suite → 预期集合与问题数, 零 tokenizer、零模型。"""
    from experiments.jev.run_suite import expected_set, load_suite, suite_task, _check_policy
    from experiments.jev.compile_context import build_request, load_taxonomy
    items, manifest = load_suite(a.suite)
    tax = load_taxonomy()
    task_id, task = suite_task(manifest, tax)
    compiled = [build_request(it, tax, task) for it in items]
    exp = expected_set(compiled)
    policy = _policy(_manifest_policy(manifest))
    _check_policy(items, compiled, policy, a.suite, task_id)
    nq = sum(1 for e in exp if e["status"] == "NOT_RUN")
    print(json.dumps({"suite_id": a.suite, "suite_sha256": manifest["suite_sha256"], "task": task_id, "policy": policy["policy_id"],
                      "items": len(items), "expected_rows": len(exp), "structural_rows": sum(1 for e in exp if e["status"] == "STRUCTURAL_COLD_READ"),
                      "preparation_ids": sorted({req.preparation_id for req, _ in compiled}),
                      "model_questions": nq, "policy_max_questions": policy["max_questions"], "policy_max_rows": policy["max_rows"],
                      "within_policy": nq <= policy["max_questions"] and len(items) <= policy["max_items"],
                      "questions_sha256": sorted({req.questions_sha256() for req, _ in compiled})}, ensure_ascii=False, indent=1))


def _network_isolated() -> dict:
    """真实检查: 新建 socket 无法联网(不能只断言环境变量)。"""
    out = {}
    for host, port in (("huggingface.co", 443), ("1.1.1.1", 443)):
        try:
            socket.create_connection((host, port), timeout=3).close()
            out[host] = "REACHABLE"
        except OSError as e:
            out[host] = f"blocked:{type(e).__name__}"
    return out


def _cgroup_limits() -> dict:
    """容器内实际生效的 cgroup v2 限制(记录, 不只展示命令参数)。读不到就写 unavailable, 不编。"""
    out = {}
    for name in ("memory.max", "memory.swap.max", "cpu.max", "pids.max"):
        try:
            out[name] = Path("/sys/fs/cgroup", name).read_text(encoding="utf-8").strip()
        except OSError:
            out[name] = "unavailable"
    out["os.cpu_count"] = os.cpu_count()
    try:                                                    # 记录 CPU 型号: 跨 runner 的浮点差异要能事后诊断
        out["cpu_model"] = next((l.split(":", 1)[1].strip() for l in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines() if l.startswith("model name")), "unavailable")
    except OSError:
        out["cpu_model"] = "unavailable"
    return out


def cmd_prepare(a):
    env = dict(os.environ)
    receipt = _receipt(a.receipt)
    if not _is_legacy(getattr(a, "model", None)):
        return _prepare_llm(a, env, receipt)
    execution_guard.require(env, receipt, "cce-jev-prepare.yml")          # 任何下载之前
    from experiments.jev import strict_assets as SA
    from experiments.jev.budget import Ledger
    from experiments.jev.contracts import ExecutionBudget
    from experiments.jev.report import dump_json
    src = SA.source_lock()
    policy = _load(HERE / "policies" / "asset_prepare.json")
    budget = ExecutionBudget(max_forwards=0, max_rows=0, max_padded_tokens=0, max_row_tokens=0,
                             deadline_s=float(policy["job_timeout_min"]) * 60, max_download_bytes=int(policy["max_download_bytes"]))
    ledger = Ledger(budget)
    plan = SA.plan_download(src, int(policy["max_model_bytes"]))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    dump_json(out / "download_plan.json", plan)
    if a.plan_only:
        print(json.dumps(plan, indent=1)); return
    proposal = SA.download_bundle(src, a.dest, ledger, env, receipt)
    dump_json(out / "model.assets.lock.proposal.json", proposal)
    dump_json(out / "prepare_receipt.json", {"receipt": receipt, "ledger": ledger.snapshot(), "model_forwards": 0,
                                             "run": {k: env.get(k) for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "GITHUB_JOB", "RUNNER_NAME", "RUNNER_ARCH", "RUNNER_OS")}})
    ledger.write_jsonl(out / "resource_ledger.jsonl")
    print(json.dumps({"downloaded_bytes": ledger.download_bytes, "files": sorted(proposal["files"]), "model_forwards": 0}, indent=1))


def _prepare_llm(a, env, receipt):
    """hf_choice 候选的 prepare(宿主侧): 守卫 → 许可策略 → 下载计划 → 逐文件流式取 + 锚点核 → 资产锁提案。0 次前向。"""
    execution_guard.require(env, receipt, LLM_PREPARE_WF)                 # 任何下载之前
    _receipt_model(receipt, a.model)
    from experiments.jev import strict_assets as SA
    from experiments.jev.budget import Ledger
    from experiments.jev.contracts import ExecutionBudget
    from experiments.jev.report import dump_json
    src, _assets, _sp, _ap = _model_locks(a.model)
    policy = _policy(receipt.get("resource_policy"))
    if policy.get("mode") != "prepare":
        raise JevError("PERMIT_NOT_APPROVED", f"policy {policy.get('policy_id')} is not a prepare policy")
    budget = ExecutionBudget(max_forwards=0, max_rows=0, max_padded_tokens=0, max_row_tokens=0,
                             deadline_s=float(policy["job_timeout_min"]) * 60, max_download_bytes=int(policy["max_download_bytes"]))
    ledger = Ledger(budget)
    plan = SA.plan_download(src, int(policy["max_model_bytes"]))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    dump_json(out / "download_plan.json", plan | {"model": a.model})
    if a.plan_only:
        print(json.dumps(plan, indent=1)); return
    proposal = SA.fetch_bundle_http(src, a.dest, ledger, env, receipt, LLM_PREPARE_WF)
    dump_json(out / "model.assets.lock.proposal.json", proposal)
    dump_json(out / "prepare_receipt.json", {"receipt": receipt, "model": a.model, "ledger": ledger.snapshot(), "model_forwards_host": 0,
                                             "run": {k: env.get(k) for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "GITHUB_JOB", "RUNNER_NAME", "RUNNER_ARCH", "RUNNER_OS")}})
    ledger.write_jsonl(out / "resource_ledger.jsonl")
    print(json.dumps({"model": a.model, "downloaded_bytes": ledger.download_bytes, "files": sorted(proposal["files"])}, indent=1))


# 合成冒烟文本: 自拟, CC0, 与语料无关(不是 Reddit 原文); 只用来在 prepare 里把「加载 → 渲染 → 前向 → 字母打分」整条路径跑通。
SMOKE_TEXT = ("I dropped my hearing aid on the kitchen floor last night and now the left one only crackles. "
              "I'm trying to figure out whether a repair is worth it or if I should just replace the pair.")


def cmd_prepare_smoke(a):
    """容器内(--network none): 用 eval 同一个 HfChoiceBackend 加载, 对合成文本的 5 道生产题各前向两次(逐位可重复性),
    记录加载报告 / 参数量 / 速度 / 字母质量 / CPU 能力。加载报告与参数量进资产锁提案, 审过后成为 eval 的加载闸。"""
    env = dict(os.environ)
    receipt = _receipt(a.receipt)
    execution_guard.require(env, receipt, LLM_PREPARE_WF)                 # 任何 import/加载之前
    _receipt_model(receipt, a.model)
    net = _network_isolated()
    if any(v == "REACHABLE" for v in net.values()):
        raise JevError("RUNTIME_UNSUPPORTED", f"network reachable inside model container: {net}")
    import time as _t
    from experiments.jev import strict_assets as SA
    from experiments.jev.backend_hf_choice import HfChoiceBackend
    from experiments.jev.budget import Ledger
    from experiments.jev.compile_context import compile_s0, load_task, load_taxonomy
    from experiments.jev.contracts import DecisionRequest, ExecutionBudget
    from experiments.jev.plan_chat import prepare_chat
    from experiments.jev.report import check_upload, dump_json
    src, _assets, _sp, _ap = _model_locks(a.model)
    proposal = _load(a.proposal)
    SA.verify_bundle(a.bundle, proposal, src)                               # 刚下载的字节 == 提案(= HF 锚点)
    tax = load_taxonomy()
    qs, _prov = compile_s0(SMOKE_TEXT, None, tax, load_task("s0_context.v2", tax))
    req = DecisionRequest(request_id="smoke:s0", item_id="prepare-smoke", state=SMOKE_TEXT, questions=qs).validate()
    budget = ExecutionBudget(max_forwards=2 * len(qs), max_rows=2 * len(qs), max_padded_tokens=2 * len(qs) * 2048, max_row_tokens=2048, deadline_s=1800)
    ledger = Ledger(budget)
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(a.bundle), local_files_only=True)
    plan = prepare_chat(req, tok, src["backend_config"], budget)
    t0 = _t.monotonic()
    be = HfChoiceBackend(a.bundle, src, proposal, ledger, env, receipt, expect_workflow=LLM_PREPARE_WF, require_pinned_load=False)
    load_s = round(_t.monotonic() - t0, 3)
    t1 = _t.monotonic(); r1 = be.evaluate(plan); r2 = be.evaluate(plan); fwd_s = _t.monotonic() - t1
    toks = 2 * sum(r.token_len for r in plan.rows)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    doc = {"model": a.model, "revision": src["revision"], "observed_load": {"loading_info": be.loading_info, "param_count": be.param_count},
           "effective": be.identities(), "load_s": load_s, "forwards": ledger.forwards, "tokens": toks, "forward_s_total": round(fwd_s, 3),
           "tok_per_s": round(toks / fwd_s, 2) if fwd_s > 0 else None,
           "repeat_bitwise_identical": all(x.raw_candidate_logits == y.raw_candidate_logits for x, y in zip(r1, r2)),
           "rows": [{"question_id": r.question_id, "token_len": r.timing["token_len"], "forward_s": r.timing["forward_s"],
                     "letter_mass": r.identities["letter_mass"], "vocab_top1_is_letter": r.identities["vocab_top1_is_letter"],
                     "selected": r.selected_candidate, "max_p": round(max(r.probabilities), 4)} for r in r1],
           "network_check": net, "cgroup_limits": _cgroup_limits(), "cgroup_memory_peak": _cgroup_peak(), "cpu_flags": _cpu_flags()}
    dump_json(out / "prepare_smoke.json", doc)
    check_upload(out, [p for p in out.iterdir() if p.is_file()], 20 * 1024 * 1024)
    print(json.dumps({k: doc[k] for k in ("model", "observed_load", "load_s", "tok_per_s", "repeat_bitwise_identical")}, ensure_ascii=False, indent=1))
    if not doc["repeat_bitwise_identical"]:
        raise JevError("RUNTIME_UNSUPPORTED", "same rows twice in one process gave different logits")


def _cgroup_peak():
    try:
        return int(Path("/sys/fs/cgroup/memory.peak").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return "unavailable"


def _cpu_flags():
    try:
        line = next(l for l in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines() if l.startswith("flags"))
        have = set(line.split(":", 1)[1].split())
        return {f: f in have for f in ("avx2", "fma", "avx512f", "avx512_bf16", "amx_bf16", "amx_tile", "avx_vnni")}
    except (OSError, StopIteration):
        return "unavailable"


def cmd_fetch_bundle(a):
    """eval 宿主侧(容器外, 联网): 按已提交且 READY 的资产锁取同一固定修订 → 逐字节核; 模型容器仍 --network none。"""
    env = dict(os.environ)
    receipt = _receipt(a.receipt)
    execution_guard.require(env, receipt, LLM_EVAL_WF)                    # 任何下载之前
    _receipt_model(receipt, a.model)
    from experiments.jev import strict_assets as SA
    from experiments.jev.budget import Ledger
    from experiments.jev.contracts import ExecutionBudget
    src, assets, _sp, _ap = _model_locks(a.model)
    if assets.get("status") != "READY":
        raise JevError("MODEL_BUNDLE_INVALID", f"models/{a.model} assets lock not READY")
    policy = _policy(receipt.get("resource_policy"))
    ledger = Ledger(ExecutionBudget(max_forwards=0, max_rows=0, max_padded_tokens=0, max_row_tokens=0, deadline_s=3600,
                                    max_download_bytes=int(policy["max_download_bytes"])))
    SA.fetch_bundle_http(src, a.dest, ledger, env, receipt, LLM_EVAL_WF)
    v = SA.verify_bundle(a.dest, assets, src)
    print(json.dumps({"model": a.model, "downloaded_bytes": ledger.download_bytes, "verified": v}, indent=1))


def cmd_verify_bundle(a):
    from experiments.jev import strict_assets as SA
    if not _is_legacy(getattr(a, "model", None)):
        src, lock, _sp, _ap = _model_locks(a.model)
        print(json.dumps({"verified": SA.verify_bundle(a.bundle, lock, src)}, ensure_ascii=False, indent=1))
        return
    src = SA.source_lock()
    lock = SA.assets_lock()
    v = SA.verify_bundle(a.bundle, lock, src)
    cfg = SA.read_decider_config(a.bundle, src)
    print(json.dumps({"verified": v, "decider_config": cfg}, ensure_ascii=False, indent=1))


def cmd_eval(a):
    env = dict(os.environ)
    receipt = _receipt(a.receipt)
    if not _is_legacy(getattr(a, "model", None)):
        return _eval_llm(a, env, receipt)
    execution_guard.require(env, receipt, "cce-jev-eval.yml")             # 任何 import/加载之前
    net = _network_isolated()
    if any(v == "REACHABLE" for v in net.values()):
        raise JevError("RUNTIME_UNSUPPORTED", f"network reachable inside model container: {net}")
    from experiments.jev import strict_assets as SA
    from experiments.jev.backend_decider import DeciderBackend
    from experiments.jev.plan_work import load_upstream
    from experiments.jev.run_suite import run
    src = SA.source_lock()
    lock = SA.assets_lock()
    verified = SA.verify_bundle(a.bundle, lock, src)                       # 缓存命中也核验
    cfg = SA.read_decider_config(a.bundle, src)
    from experiments.jev.run_suite import load_suite
    _items, manifest = load_suite(a.suite)
    policy = eval_policy(receipt, a.suite, manifest)                          # admit 已在同一提交核过此文件 sha
    rt = _load(HERE / "locks" / "cpu-runtime.lock.json")
    identities = {"cce_execution_commit": env.get("GITHUB_SHA"), "adapter_sha256": adapter_hash(),
                  "source_lock_sha256": file_sha256(SA.SOURCE_LOCK), "assets_lock_sha256": file_sha256(SA.ASSETS_LOCK),
                  "runtime_lock_sha256": file_sha256(HERE / "locks" / "runtime-cpu.lock.txt") if (HERE / "locks" / "runtime-cpu.lock.txt").is_file() else "unavailable",
                  "runtime_recipe": rt, "observed_image_id": env.get("CCE_JEV_IMAGE_ID", "unavailable"),
                  "upstream_source_commit": src["source_revision"], "model_revision": src["revision"], "model_version": src["model_version"],
                  "bundle": verified, "tokenizer_sha256": lock["files"].get("tokenizer.json", {}).get("sha256"),
                  "task_contract": _load(HERE / "tasks" / f"{manifest.get('task', 's0_context.v1')}.json")["task_id"],
                  "preparation_ids": sorted({it.get("preparation_id", "full_text.v1") for it in _items}),
                  "permit_id": receipt.get("permit_id"), "suite_id": a.suite,
                  "run": {k: env.get(k) for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB", "GITHUB_WORKFLOW_REF", "RUNNER_NAME", "RUNNER_ARCH", "RUNNER_OS")},
                  "network_check": net, "cgroup_limits": _cgroup_limits(), "threads": int(env.get("OMP_NUM_THREADS", "3")), "policy_id": policy["policy_id"]}

    def tok_factory():
        from transformers import AutoTokenizer
        return AutoTokenizer.from_pretrained(str(a.bundle), local_files_only=True)

    report = run(a.suite, a.out, policy, cfg, identities,
                 backend_factory=lambda ledger: DeciderBackend(a.bundle, cfg, ledger, env, receipt, threads=identities["threads"]),
                 tok_factory=tok_factory, upstream_factory=load_upstream)
    print(json.dumps({k: report[k] for k in ("execution_status", "coverage_status", "semantic_acceptance", "production_eligible", "failures")}, ensure_ascii=False, indent=1))
    if report["execution_status"] != "SUCCEEDED":
        raise JevError(report["failures"][0].get("code") if report["failures"] and report["failures"][0].get("code") in
                       __import__("experiments.jev.contracts", fromlist=["ERROR_CODES"]).ERROR_CODES else "RUNTIME_UNSUPPORTED", "evaluation failed; report written")


def _eval_llm(a, env, receipt):
    execution_guard.require(env, receipt, LLM_EVAL_WF)                    # 任何 import/加载之前
    _receipt_model(receipt, a.model)
    net = _network_isolated()
    if any(v == "REACHABLE" for v in net.values()):
        raise JevError("RUNTIME_UNSUPPORTED", f"network reachable inside model container: {net}")
    from experiments.jev import strict_assets as SA
    from experiments.jev.backend_hf_choice import HfChoiceBackend
    from experiments.jev.plan_chat import prepare_chat
    from experiments.jev.run_suite import load_suite, run
    src, assets, sp, ap = _model_locks(a.model)
    if src.get("backend") != "hf_choice":
        raise JevError("RUNTIME_UNSUPPORTED", f"model {a.model} backend {src.get('backend')!r} is not hf_choice")
    verified = SA.verify_bundle(a.bundle, assets, src)                     # 容器内再核一遍(宿主取回后)
    _items, manifest = load_suite(a.suite)
    policy = eval_policy(receipt, a.suite, manifest)
    rt = _load(HERE / "locks" / "cpu-runtime.lock.json")
    cfg = src["backend_config"]
    identities = {"backend": "hf_choice", "cce_execution_commit": env.get("GITHUB_SHA"), "adapter_sha256": adapter_hash(),
                  "model_key": a.model, "source_lock_sha256": file_sha256(sp), "assets_lock_sha256": file_sha256(ap),
                  "runtime_lock_sha256": file_sha256(HERE / "locks" / "runtime-cpu.lock.txt"), "runtime_recipe": rt,
                  "observed_image_id": env.get("CCE_JEV_IMAGE_ID", "unavailable"), "model_revision": src["revision"], "model_version": src["model_version"],
                  "repo_id": src["repo_id"], "bundle": verified, "tokenizer_sha256": assets["files"].get("tokenizer.json", {}).get("sha256"),
                  "task_contract": _load(HERE / "tasks" / f"{manifest.get('task', 's0_context.v1')}.json")["task_id"],
                  "preparation_ids": sorted({it.get("preparation_id", "full_text.v1") for it in _items}),
                  "permit_id": receipt.get("permit_id"), "suite_id": a.suite,
                  "run": {k: env.get(k) for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB", "GITHUB_WORKFLOW_REF", "RUNNER_NAME", "RUNNER_ARCH", "RUNNER_OS")},
                  "network_check": net, "cgroup_limits": _cgroup_limits(), "cpu_flags": _cpu_flags(), "threads": int(cfg["threads"]), "policy_id": policy["policy_id"]}

    def tok_factory():
        from transformers import AutoTokenizer
        return AutoTokenizer.from_pretrained(str(a.bundle), local_files_only=True)

    report = run(a.suite, a.out, policy, cfg, identities,
                 backend_factory=lambda ledger: HfChoiceBackend(a.bundle, src, assets, ledger, env, receipt, expect_workflow=LLM_EVAL_WF),
                 tok_factory=tok_factory, upstream_factory=lambda: None,
                 plan_fn=lambda req, tok, up, c, budget: prepare_chat(req, tok, c, budget))
    report.setdefault("timing", {})["cgroup_memory_peak"] = _cgroup_peak()
    print(json.dumps({k: report[k] for k in ("execution_status", "coverage_status", "semantic_acceptance", "production_eligible", "failures")}, ensure_ascii=False, indent=1))
    if report["execution_status"] != "SUCCEEDED":
        raise JevError(report["failures"][0].get("code") if report["failures"] and report["failures"][0].get("code") in
                       __import__("experiments.jev.contracts", fromlist=["ERROR_CODES"]).ERROR_CODES else "RUNTIME_UNSUPPORTED", "evaluation failed; report written")


def cmd_check_upload(a):
    """宿主侧上传前闸; --suite 给出时同时扫该 suite 全部输入文本(24 字符窗)不得出现在任何上传文件里。"""
    from experiments.jev.report import check_upload
    texts, policy_name = [], "cpu_smoke.json"
    if a.suite:
        from experiments.jev.run_suite import load_suite, suite_texts
        items, manifest = load_suite(a.suite)
        texts, policy_name = suite_texts(items), _manifest_policy(manifest)
    policy = _policy(policy_name)
    rel = check_upload(a.root, [p for p in Path(a.root).rglob("*") if p.is_file()], int(policy["report_max_bytes"]), forbidden_texts=texts)
    print(json.dumps({"root": a.root, "files": rel, "leak_scanned_items": len(texts)}, indent=1))


def cmd_policy_field(a):
    """工作流取策略字段(如载入+推理时限), 不让用户输入进 run: 块。策略名来自 admit 回执。"""
    receipt = _receipt(a.receipt)
    v = _policy(receipt.get("resource_policy"))[a.field]
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise JevError("PERMIT_NOT_APPROVED", f"policy field {a.field} is not numeric")
    print(int(v))


def cmd_suite_files(a):
    """该 suite 按指针引用的语料文件(每行一个, 已过正则), 供宿主只挂载这些文件(只读)。"""
    from experiments.jev.run_suite import load_suite
    from experiments.jev.compile_context import CORPUS_FILE_RE
    items, _ = load_suite(a.suite)
    files = sorted({it["text_ref"]["file"] for it in items if "text_ref" in it})
    for f in files:
        if not CORPUS_FILE_RE.match(f) or not (ROOT / f).is_file():
            raise JevError("INPUT_INVALID", f"suite file ref {f!r}")
        print(f)


def cmd_finalize(a):
    """宿主侧收尾(容器被杀/超时/OOM 也要写状态), 不再调用任何模型。"""
    from experiments.jev.report import dump_json
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rep = out / "report.json"
    status = {"docker_exit_code": a.docker_exit, "oom_killed": a.oom == "true", "report_present": rep.is_file(),
              "files": sorted(p.name for p in out.iterdir() if p.is_file())}
    if not rep.is_file():
        dump_json(rep, {"schema": "cce.jev.evaluation.v1", "mode": "shadow_eval", "backend": a.backend, "execution_status": "FAILED",
                        "coverage_status": "NOT_ESTABLISHED", "semantic_acceptance": "NOT_ESTABLISHED", "production_eligible": False,
                        "results": [], "failures": [{"code": "RESOURCE_EXCEEDED" if status["oom_killed"] else "TIMEOUT" if a.docker_exit in (124, 137) else "RUNTIME_UNSUPPORTED",
                                                     "detail": f"container exited {a.docker_exit} before writing a report"}]})
        (out / "summary.md").write_text(f"# CCE Decider candidate evaluation\n\n- execution_status: **FAILED** (container exit {a.docker_exit}, oom={status['oom_killed']})\n", encoding="utf-8")
    dump_json(out / "host_status.json", status)
    print(json.dumps(status, indent=1))


def adapter_hash() -> str:
    return sha256("".join(p.read_text(encoding="utf-8") for p in sorted(HERE.glob("*.py"))))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cce-jev", description="CCE Decider candidate (Jev) — pure contract locally; model steps only on GitHub-hosted runners")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("check-locks"); s.add_argument("--require-ready", action="store_true"); s.add_argument("--model", default=None); s.set_defaults(fn=cmd_check_locks)
    s = sub.add_parser("plan"); s.add_argument("--suite", required=True); s.set_defaults(fn=cmd_plan)
    s = sub.add_parser("prepare"); s.add_argument("--receipt", required=True); s.add_argument("--dest", required=True); s.add_argument("--out", required=True)
    s.add_argument("--plan-only", action="store_true"); s.add_argument("--model", default=None); s.set_defaults(fn=cmd_prepare)
    s = sub.add_parser("prepare-smoke"); s.add_argument("--receipt", required=True); s.add_argument("--bundle", required=True)
    s.add_argument("--proposal", required=True); s.add_argument("--out", required=True); s.add_argument("--model", required=True); s.set_defaults(fn=cmd_prepare_smoke)
    s = sub.add_parser("fetch-bundle"); s.add_argument("--receipt", required=True); s.add_argument("--dest", required=True)
    s.add_argument("--model", required=True); s.set_defaults(fn=cmd_fetch_bundle)
    s = sub.add_parser("verify-bundle"); s.add_argument("--bundle", required=True); s.add_argument("--model", default=None); s.set_defaults(fn=cmd_verify_bundle)
    s = sub.add_parser("eval"); s.add_argument("--suite", required=True); s.add_argument("--receipt", required=True)
    s.add_argument("--bundle", required=True); s.add_argument("--out", required=True); s.add_argument("--model", default=None); s.set_defaults(fn=cmd_eval)
    s = sub.add_parser("check-upload"); s.add_argument("--root", required=True); s.add_argument("--suite", default=None); s.set_defaults(fn=cmd_check_upload)
    s = sub.add_parser("policy-field"); s.add_argument("--receipt", required=True)
    s.add_argument("--field", required=True, choices=["model_load_plus_infer_deadline_s", "job_timeout_min", "max_forwards"]); s.set_defaults(fn=cmd_policy_field)
    s = sub.add_parser("suite-files"); s.add_argument("--suite", required=True); s.set_defaults(fn=cmd_suite_files)
    s = sub.add_parser("finalize"); s.add_argument("--out", required=True); s.add_argument("--docker-exit", type=int, required=True)
    s.add_argument("--oom", default="false"); s.add_argument("--backend", default="decider", choices=["decider", "hf_choice"]); s.set_defaults(fn=cmd_finalize)
    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except JevError as e:
        print(f"{e.code}: {e.detail}", file=sys.stderr)
        return EXIT_TYPED
    except Exception as e:  # noqa: BLE001 — 公仓日志: 不打 traceback、不打异常消息(可能含输入原文), 只报类型名
        print(f"UNHANDLED_EXCEPTION: {type(e).__name__} (message withheld)", file=sys.stderr)
        return EXIT_TYPED
    return 0


if __name__ == "__main__":
    sys.exit(main())
