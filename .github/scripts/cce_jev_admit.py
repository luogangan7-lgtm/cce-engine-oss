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
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JEV = ROOT / "experiments" / "jev"
PERMIT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{3,63}$")
SUITE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,40}$")
REQUIRED = ("permit_id", "owner_approval_reference", "expiry", "repository", "workflow_id", "mode", "max_runs", "max_attempts",
            "model_source_lock_sha256", "asset_lock_sha256", "runtime_lock_sha256", "resource_policy", "resource_policy_sha256")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def fail(code: str, detail: str) -> "NoReturn":
    print(f"{code}: {detail}", file=sys.stderr)
    sys.exit(3)


def main() -> int:
    env = os.environ
    pid, mode, suite = env.get("PERMIT_ID", ""), env.get("MODE", ""), env.get("SUITE_ID", "")
    if not PERMIT_RE.match(pid):
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
    missing = [k for k in REQUIRED if k not in permit]
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
    if permit["model_source_lock_sha256"] != sha(locks / "model.source.lock.json"):
        fail("PERMIT_NOT_APPROVED", "model_source_lock_sha256 != committed source lock")
    pol = JEV / "policies" / str(permit["resource_policy"])
    if not pol.is_file() or permit["resource_policy_sha256"] != sha(pol):
        fail("PERMIT_NOT_APPROVED", "resource policy missing or sha mismatch")
    if mode == "prepare":
        if permit["asset_lock_sha256"] != "NOT_APPLICABLE_PREPARE" or permit["runtime_lock_sha256"] != "NOT_APPLICABLE_PREPARE":
            fail("PERMIT_NOT_APPROVED", "prepare permit must mark asset/runtime locks NOT_APPLICABLE_PREPARE")
        suite_sha = None
    else:
        if not SUITE_RE.match(suite) or permit.get("suite_id") != suite:
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
               "suite_sha256": suite_sha, "locks": {"model_source_lock_sha256": permit["model_source_lock_sha256"],
                                                    "asset_lock_sha256": permit["asset_lock_sha256"], "runtime_lock_sha256": permit["runtime_lock_sha256"]},
               "resource_policy": permit["resource_policy"], "consumed_ref": ref, "owner_approval_reference": permit["owner_approval_reference"],
               "admitted_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    Path(env.get("RECEIPT_OUT", "admission_receipt.json")).write_text(json.dumps(receipt, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"admitted": True, "permit_id": pid, "mode": mode, "consumed_ref": ref, "execution_commit": commit}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
