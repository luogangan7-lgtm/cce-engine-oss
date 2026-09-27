#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""admit job(纯标准库, 不加载待测模型代码): 核 permit → 原子占用许可(唯一 git ref) → 写准入 receipt。

许可文件: experiments/jev/permits/<permit_id>.json, 由 owner 在批准时提交(Claude 不得自行标记批准)。
重复触发 / Re-run(attempt≠1) / 过期 / 锁哈希不符 / suite 不符 ⇒ 在任何模型下载之前拒绝。
唯一 ref refs/tags/cce-jev-consumed/<permit_id> 创建失败 ⇒ 拒绝; 网络状态不明 ⇒ 按可能已消耗处理, 不重试。"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JEV = ROOT / "experiments" / "jev"
PERMIT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{3,63}$")
SUITE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,40}$")
REQUIRED = ("permit_id", "owner_approval_reference", "expiry", "repository", "workflow_id", "mode", "max_runs", "max_attempts",
            "model_source_lock_sha256", "asset_lock_sha256", "runtime_lock_sha256", "resource_policy", "resource_policy_sha256")
# ★ 2026-09-27 许可 schema v2(hf_choice 候选): 顶层不再绑单个模型锁, 改为 models 清单逐个绑; 运行时锁照绑。
REQUIRED_V2 = ("permit_id", "owner_approval_reference", "expiry", "repository", "workflow_id", "mode", "max_runs", "max_attempts",
               "models", "runtime_lock_sha256", "resource_policy", "resource_policy_sha256")
MODEL_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{2,40}$")
LLM_WORKFLOWS = ("cce-jev-llm-prepare.yml", "cce-jev-llm-eval.yml")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def bundle_cache_key(root: Path = ROOT) -> str:
    """与工作流 hashFiles('experiments/jev/locks/model.source.lock.json') 相同: 单文件 = sha256(sha256(bytes))。"""
    return "cce-jev-bundle-%s-x64" % hashlib.sha256(hashlib.sha256((root / "experiments/jev/locks/model.source.lock.json").read_bytes()).digest()).hexdigest()


def fail(code: str, detail: str) -> "NoReturn":
    print(f"{code}: {detail}", file=sys.stderr)
    sys.exit(3)


def _hf_available(src: dict, hf: str) -> None:
    """消耗之前: 固定修订仍可匿名取到, 且每个文件的大小/锚点与源锁一致(只读元数据)。不通 ⇒ 不消耗、拒绝。"""
    try:
        rq = urllib.request.Request(f"{hf}/api/models/{src['repo_id']}/revision/{src['revision']}", headers={"User-Agent": "cce-jev-admit/1"})
        with urllib.request.urlopen(rq, timeout=30) as r:
            info = json.load(r)
        if info.get("sha") != src["revision"] or info.get("gated") not in (False, None) or info.get("private"):
            fail("PERMIT_NOT_APPROVED", f"{src['repo_id']}@{src['revision'][:8]} no longer anonymously available at the pinned revision; permit NOT consumed")
        rq = urllib.request.Request(f"{hf}/api/models/{src['repo_id']}/paths-info/{src['revision']}", method="POST",
                                    data=json.dumps({"paths": sorted(src["files"])}).encode(), headers={"Content-Type": "application/json", "User-Agent": "cce-jev-admit/1"})
        with urllib.request.urlopen(rq, timeout=30) as r:
            rows = {x["path"]: x for x in json.load(r)}
    except urllib.error.HTTPError as e:
        fail("PERMIT_NOT_APPROVED", f"HF metadata check failed HTTP {e.code} for {src['repo_id']}; permit NOT consumed")
    except Exception as e:  # noqa: BLE001
        fail("PERMIT_NOT_APPROVED", f"cannot reach HF metadata ({type(e).__name__}); permit NOT consumed")
    for name, spec in src["files"].items():
        x = rows.get(name) or {}
        lfs = x.get("lfs") or {}
        size, oid = (lfs.get("size"), lfs.get("oid")) if lfs else (x.get("size"), x.get("oid"))
        if size != spec["size"] or oid != spec["anchor"]["value"]:
            fail("PERMIT_NOT_APPROVED", f"{src['repo_id']}:{name} metadata differs from the source lock; permit NOT consumed")


def _admit_v2(env, permit, pid, mode, suite, wf_file):
    """schema v2(hf_choice 候选): models 清单逐个核锁 → (eval) suite/策略/计划 → HF 元数据可达 —— 全在消耗之前。返回 (models, 回执锁块, suite_sha)。"""
    if wf_file not in LLM_WORKFLOWS:
        fail("PERMIT_NOT_APPROVED", "a models-list permit only runs the llm candidate workflows")
    models = permit["models"]
    if not isinstance(models, list) or not 1 <= len(models) <= 4:
        fail("PERMIT_NOT_APPROVED", "models must be a list of 1..4 entries")
    keys = [m.get("model_key") if isinstance(m, dict) else None for m in models]
    if len(set(keys)) != len(keys) or not all(isinstance(k, str) and MODEL_KEY_RE.fullmatch(k) and ".." not in k for k in keys):
        fail("PERMIT_NOT_APPROVED", "model keys missing, malformed or duplicated")
    locks = JEV / "locks"
    rt = locks / "runtime-cpu.lock.txt"
    if not rt.is_file() or permit["runtime_lock_sha256"] != sha(rt):
        fail("PERMIT_NOT_APPROVED", "runtime lock missing or sha mismatch")
    srcs, block = {}, {}
    for m in models:
        k = m["model_key"]; d = JEV / "models" / k
        sp, ap = d / "model.source.lock.json", d / "model.assets.lock.json"
        if not sp.is_file() or m.get("model_source_lock_sha256") != sha(sp):
            fail("PERMIT_NOT_APPROVED", f"model {k}: source lock missing or sha mismatch")
        src = json.loads(sp.read_text(encoding="utf-8"))
        if src.get("backend") != "hf_choice" or src.get("execution_location") != "github_hosted_actions_only" or src.get("remote_inference_allowed") is not False:
            fail("PERMIT_NOT_APPROVED", f"model {k}: not an hf_choice lock with the GitHub-only boundary")
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}", str(src.get("repo_id")))
                or not re.fullmatch(r"[0-9a-f]{40}", str(src.get("revision"))) or not src.get("files")
                or not all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", n) for n in src["files"])):
            fail("PERMIT_NOT_APPROVED", f"model {k}: repo / revision / file names are not plain pinned identifiers")
        if mode == "prepare":
            if m.get("asset_lock_sha256") != "NOT_APPLICABLE_PREPARE":
                fail("PERMIT_NOT_APPROVED", f"model {k}: prepare permit must mark asset_lock_sha256 NOT_APPLICABLE_PREPARE")
        else:
            assets = json.loads(ap.read_text(encoding="utf-8")) if ap.is_file() else {}
            if assets.get("status") != "READY" or m.get("asset_lock_sha256") != sha(ap) or not (assets.get("observed_load") or {}).get("param_count"):
                fail("PERMIT_NOT_APPROVED", f"model {k}: asset lock not READY (with reviewed observed_load) or sha mismatch")
        cl = subprocess.run([sys.executable, str(JEV / "cli.py"), "check-locks", "--model", k] + (["--require-ready"] if mode == "eval" else []),
                            cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        if cl.returncode != 0:                          # 与腿里同一道锁闸, 在消耗之前跑(手工合成资产锁的笔误不许烧许可)
            fail("PERMIT_NOT_APPROVED", f"model {k}: lock gate failed before consumption: " + (cl.stderr.strip().splitlines() or ["?"])[-1][:200])
        srcs[k] = src
        block[k] = {"model_source_lock_sha256": m["model_source_lock_sha256"], "asset_lock_sha256": m["asset_lock_sha256"]}
    suite_sha = None
    pol = JEV / "policies" / str(permit["resource_policy"])
    policy = json.loads(pol.read_text(encoding="utf-8"))
    if policy.get("mode") != mode or policy.get("backend") != "hf_choice":
        fail("PERMIT_NOT_APPROVED", "resource policy mode/backend do not match this run")
    need = ("smoke_deadline_s", "job_timeout_min", "max_download_bytes", "max_model_bytes") if mode == "prepare" else \
           ("model_load_plus_infer_deadline_s", "job_timeout_min", "max_download_bytes")
    if not all(isinstance(policy.get(f), int) and not isinstance(policy.get(f), bool) and policy.get(f) > 0 for f in need):
        fail("PERMIT_NOT_APPROVED", f"resource policy lacks positive integer {need}")
    if mode == "eval":
        if not SUITE_RE.fullmatch(suite) or permit.get("suite_id") != suite:
            fail("PERMIT_NOT_APPROVED", "suite_id missing or does not match permit")
        sf = JEV / "suites" / f"{suite}.jsonl"
        if not sf.is_file():
            fail("PERMIT_NOT_APPROVED", f"suite {suite} not registered")
        suite_sha = sha(sf)
        if permit.get("suite_sha256") != suite_sha:
            fail("PERMIT_NOT_APPROVED", "suite_sha256 != committed suite")
        mf = JEV / "suites" / f"{suite}.manifest.json"
        manifest = json.loads(mf.read_text(encoding="utf-8")) if mf.is_file() else {}
        if permit["resource_policy"] != manifest.get("policy", "cpu_smoke.json"):
            fail("PERMIT_NOT_APPROVED", f"permit resource_policy {permit['resource_policy']} != suite manifest policy {manifest.get('policy', 'cpu_smoke.json')}")
        if ("suite_ids" in policy and suite not in policy["suite_ids"]) or policy.get("task", "s0_context.v1") != manifest.get("task", "s0_context.v1"):
            fail("PERMIT_NOT_APPROVED", "resource policy suite_ids / task do not cover this suite")
        pr = subprocess.run([sys.executable, str(JEV / "cli.py"), "plan", "--suite", suite], cwd=str(ROOT), capture_output=True, text=True, timeout=300)
        if pr.returncode != 0:
            fail("PERMIT_NOT_APPROVED", "suite plan failed before consumption: " + (pr.stderr.strip().splitlines() or ["?"])[-1][:200])
        if not json.loads(pr.stdout).get("within_policy"):
            fail("PERMIT_NOT_APPROVED", "suite plan exceeds the permit's resource policy")
    # 与取件器同一个主机(strict_assets.HF_BASE); 覆盖只作测试缝, 在 Actions 里设了就拒绝(防被前序步骤写进 $GITHUB_ENV)
    if env.get("CCE_JEV_TEST_HF_ENDPOINT") and env.get("GITHUB_ACTIONS") == "true":
        fail("PERMIT_NOT_APPROVED", "CCE_JEV_TEST_HF_ENDPOINT is a test seam and must not be set in Actions")
    if mode == "prepare":
        for k in keys:                                  # 与腿里 plan_download 同一上限, 在消耗之前核
            if sum(int(f["size"]) for f in srcs[k]["files"].values()) > int(policy["max_model_bytes"]):
                fail("PERMIT_NOT_APPROVED", f"model {k}: planned download exceeds the policy max_model_bytes")
    hf = (env.get("CCE_JEV_TEST_HF_ENDPOINT") or "https://huggingface.co").rstrip("/")
    for k in keys:
        _hf_available(srcs[k], hf)
    return keys, block, suite_sha


def main() -> int:
    env = os.environ
    pid, mode, suite = env.get("PERMIT_ID", ""), env.get("MODE", ""), env.get("SUITE_ID", "")
    if not PERMIT_RE.fullmatch(pid):
        fail("PERMIT_NOT_APPROVED", "permit_id has an invalid shape")
    if mode not in ("prepare", "eval"):
        fail("PERMIT_NOT_APPROVED", f"mode {mode!r}")
    if env.get("GITHUB_RUN_ATTEMPT") != "1":
        fail("PERMIT_ALREADY_USED", "run attempt != 1 (Re-run jobs is refused; a new permit is required)")
    if env.get("GITHUB_REF") != "refs/heads/master":
        fail("PERMIT_NOT_APPROVED", f"only refs/heads/master may execute (got {env.get('GITHUB_REF')!r})")
    wf_file = env.get("GITHUB_WORKFLOW_REF", "").split("@")[0].rsplit("/", 1)[-1]
    pf = JEV / "permits" / f"{pid}.json"
    if not pf.is_file():
        fail("PERMIT_NOT_APPROVED", f"no approved permit file experiments/jev/permits/{pid}.json at this commit")
    permit = json.loads(pf.read_text(encoding="utf-8"))
    v2 = "models" in permit
    missing = [k for k in (REQUIRED_V2 if v2 else REQUIRED) if k not in permit]
    if missing:
        fail("PERMIT_NOT_APPROVED", f"permit missing {missing}")
    if permit["permit_id"] != pid or permit["mode"] != mode or permit["repository"] != env.get("GITHUB_REPOSITORY") or permit["workflow_id"] != wf_file:
        fail("PERMIT_NOT_APPROVED", "permit_id/mode/repository/workflow_id do not match this run")
    if not str(permit["owner_approval_reference"]).strip():
        fail("PERMIT_NOT_APPROVED", "owner_approval_reference empty")
    if int(permit["max_runs"]) != 1 or int(permit["max_attempts"]) != 1:
        fail("PERMIT_NOT_APPROVED", "max_runs / max_attempts must be 1")
    try:
        expiry = dt.datetime.fromisoformat(str(permit["expiry"]).replace("Z", "+00:00"))
    except ValueError:
        fail("PERMIT_NOT_APPROVED", "expiry not ISO-8601")
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=dt.timezone.utc)
    if dt.datetime.now(dt.timezone.utc) > expiry:
        fail("PERMIT_EXPIRED", f"permit expired at {expiry.isoformat()}")
    locks = JEV / "locks"
    pol = JEV / "policies" / str(permit["resource_policy"])
    if not re.fullmatch(r"[a-z0-9_]{3,40}\.json", str(permit["resource_policy"])) or not pol.is_file() or permit["resource_policy_sha256"] != sha(pol):
        fail("PERMIT_NOT_APPROVED", "resource policy missing or sha mismatch")
    models, model_locks = ["decider-2b"], None
    if v2:
        models, model_locks, suite_sha = _admit_v2(env, permit, pid, mode, suite, wf_file)
    elif wf_file in LLM_WORKFLOWS:
        fail("PERMIT_NOT_APPROVED", "the llm candidate workflows need a models-list (v2) permit")
    elif permit["model_source_lock_sha256"] != sha(locks / "model.source.lock.json"):
        fail("PERMIT_NOT_APPROVED", "model_source_lock_sha256 != committed source lock")
    if v2:
        pass
    elif mode == "prepare":
        if permit["asset_lock_sha256"] != "NOT_APPLICABLE_PREPARE" or permit["runtime_lock_sha256"] != "NOT_APPLICABLE_PREPARE":
            fail("PERMIT_NOT_APPROVED", "prepare permit must mark asset/runtime locks NOT_APPLICABLE_PREPARE")
        suite_sha = None
    else:
        if not SUITE_RE.fullmatch(suite) or permit.get("suite_id") != suite:
            fail("PERMIT_NOT_APPROVED", "suite_id missing or does not match permit")
        sf = JEV / "suites" / f"{suite}.jsonl"
        if not sf.is_file():
            fail("PERMIT_NOT_APPROVED", f"suite {suite} not registered")
        suite_sha = sha(sf)
        if permit.get("suite_sha256") != suite_sha:
            fail("PERMIT_NOT_APPROVED", "suite_sha256 != committed suite")
        assets = json.loads((locks / "model.assets.lock.json").read_text(encoding="utf-8"))
        rt = locks / "runtime-cpu.lock.txt"
        if assets.get("status") != "READY" or permit["asset_lock_sha256"] != sha(locks / "model.assets.lock.json"):
            fail("PERMIT_NOT_APPROVED", "asset lock not READY or sha mismatch")
        if not rt.is_file() or permit["runtime_lock_sha256"] != sha(rt):
            fail("PERMIT_NOT_APPROVED", "runtime lock missing or sha mismatch")
        # ---- 许可策略 ↔ suite 清单 ↔ 任务合同 必须一致(否则消耗后才在容器里失败)
        mf = JEV / "suites" / f"{suite}.manifest.json"
        manifest = json.loads(mf.read_text(encoding="utf-8")) if mf.is_file() else {}
        policy = json.loads(pol.read_text(encoding="utf-8"))
        if permit["resource_policy"] != manifest.get("policy", "cpu_smoke.json"):
            fail("PERMIT_NOT_APPROVED", f"permit resource_policy {permit['resource_policy']} != suite manifest policy {manifest.get('policy', 'cpu_smoke.json')}")
        if policy.get("mode") != "eval" or ("suite_ids" in policy and suite not in policy["suite_ids"]) or policy.get("task", "s0_context.v1") != manifest.get("task", "s0_context.v1"):
            fail("PERMIT_NOT_APPROVED", "resource policy mode / suite_ids / task do not cover this suite")
        # ---- 纯标准库编排预检(suite sha、语料指针整行+切片 sha、预算上限), 不加载模型、不联网
        pr = subprocess.run([sys.executable, str(JEV / "cli.py"), "plan", "--suite", suite], cwd=str(ROOT), capture_output=True, text=True, timeout=300)
        if pr.returncode != 0:
            fail("PERMIT_NOT_APPROVED", "suite plan failed before consumption: " + (pr.stderr.strip().splitlines() or ["?"])[-1][:200])
        if not json.loads(pr.stdout).get("within_policy"):
            fail("PERMIT_NOT_APPROVED", "suite plan exceeds the permit's resource policy")
        # ---- 模型缓存必须已在(eval 不下载; 缺了就先不消耗, 走 prepare 重热)
        key = bundle_cache_key()
        if env.get("BUNDLE_CACHE_KEY") and env["BUNDLE_CACHE_KEY"] != key:
            fail("PERMIT_NOT_APPROVED", "workflow bundle cache key != key recomputed from the source lock")
        creq = urllib.request.Request(f"{env.get('GITHUB_API_URL', 'https://api.github.com')}/repos/{env.get('GITHUB_REPOSITORY')}/actions/caches?key={urllib.parse.quote(key)}&ref=refs%2Fheads%2Fmaster",
                                      headers={"Authorization": f"Bearer {env.get('GITHUB_TOKEN', '')}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        try:
            with urllib.request.urlopen(creq, timeout=30) as r:
                caches = json.load(r).get("actions_caches", [])
        except Exception as e:  # noqa: BLE001
            fail("PERMIT_NOT_APPROVED", f"cannot verify the model bundle cache ({type(e).__name__}); permit NOT consumed")
        if not any(c.get("key") == key for c in caches):
            fail("PERMIT_NOT_APPROVED", "model bundle cache missing (evicted?); re-warm it with a prepare permit first; permit NOT consumed")
    # ---- atomic consumption: create a unique ref; existing ⇒ already used; unknown ⇒ treat as consumed
    repo, commit, token = env.get("GITHUB_REPOSITORY"), env.get("GITHUB_SHA"), env.get("GITHUB_TOKEN")
    if not (repo and commit and token):
        fail("PERMIT_NOT_APPROVED", "missing repository/commit/token for consumption")
    ref = f"refs/tags/cce-jev-consumed/{pid}"
    req = urllib.request.Request(f"{env.get('GITHUB_API_URL', 'https://api.github.com')}/repos/{repo}/git/refs",
                                 data=json.dumps({"ref": ref, "sha": commit}).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status != 201:
                fail("PERMIT_ALREADY_USED", f"ref creation returned {r.status}; treating permit as consumed")
    except urllib.error.HTTPError as e:
        if e.code == 422:
            fail("PERMIT_ALREADY_USED", f"{ref} already exists")
        fail("PERMIT_ALREADY_USED", f"ref creation failed HTTP {e.code}; network state unknown, treating permit as consumed")
    except Exception as e:  # noqa: BLE001
        fail("PERMIT_ALREADY_USED", f"ref creation failed ({type(e).__name__}); treating permit as consumed, no retry")
    receipt = {"schema": "cce.jev.admission-receipt.v1", "permit_id": pid, "mode": mode, "repository": repo, "execution_commit": commit,
               "run_id": env.get("GITHUB_RUN_ID"), "run_attempt": env.get("GITHUB_RUN_ATTEMPT"), "workflow_id": wf_file,
               "workflow_ref": env.get("GITHUB_WORKFLOW_REF"), "actor": env.get("GITHUB_ACTOR"), "suite_id": suite or None,
               "suite_sha256": suite_sha,
               "locks": ({"runtime_lock_sha256": permit["runtime_lock_sha256"], "models": model_locks} if v2 else
                         {"model_source_lock_sha256": permit["model_source_lock_sha256"],
                          "asset_lock_sha256": permit["asset_lock_sha256"], "runtime_lock_sha256": permit["runtime_lock_sha256"]}),
               "resource_policy": permit["resource_policy"], "consumed_ref": ref, "owner_approval_reference": permit["owner_approval_reference"],
               "admitted_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    if v2:
        receipt["models"] = models
    Path(env.get("RECEIPT_OUT", "admission_receipt.json")).write_text(json.dumps(receipt, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if env.get("GITHUB_OUTPUT"):                    # 矩阵腿 = 许可批准的模型键(经正则), 不来自用户输入
        with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write("models=" + json.dumps(models) + "\n")
    print(json.dumps({"admitted": True, "permit_id": pid, "mode": mode, "consumed_ref": ref, "execution_commit": commit}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
