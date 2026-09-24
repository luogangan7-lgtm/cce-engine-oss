# -*- coding: utf-8 -*-
"""GitHub-only 防误运行守卫 —— 真实资产下载 / tokenizer 加载 / 模型依赖 import / 构造器之前都调它。

★ 环境变量不是不可伪造的安全证明。真正的执行边界来自受信 workflow、托管 runner、单次许可和无模型本地测试;
  guard 是防误用控制, receipt 是可核对的运行记录。不要在本机设置这些变量骗过守卫。
"""
from __future__ import annotations

from .contracts import JevError

APPROVED_REPOSITORY = "luogangan7-lgtm/cce-engine-oss"
APPROVED_REF = "refs/heads/master"
APPROVED_WORKFLOWS = ("cce-jev-prepare.yml", "cce-jev-eval.yml")
RECEIPT_SCHEMA = "cce.jev.admission-receipt.v1"


def problems(env: dict, receipt: dict | None = None, expect_workflow: str | None = None) -> list:
    p = []
    if env.get("GITHUB_ACTIONS") != "true":
        p.append("GITHUB_ACTIONS != true")
    if env.get("RUNNER_ENVIRONMENT") != "github-hosted":
        p.append("RUNNER_ENVIRONMENT != github-hosted")
    if env.get("GITHUB_REPOSITORY") != APPROVED_REPOSITORY:
        p.append(f"GITHUB_REPOSITORY != {APPROVED_REPOSITORY}")
    wfs = (expect_workflow,) if expect_workflow else APPROVED_WORKFLOWS
    wref = env.get("GITHUB_WORKFLOW_REF", "")
    if not any(wref == f"{APPROVED_REPOSITORY}/.github/workflows/{w}@{APPROVED_REF}" for w in wfs):
        p.append(f"GITHUB_WORKFLOW_REF {wref!r} not an approved workflow on {APPROVED_REF}")
    if not env.get("GITHUB_RUN_ID"):
        p.append("GITHUB_RUN_ID missing")
    if env.get("GITHUB_RUN_ATTEMPT") != "1":
        p.append(f"GITHUB_RUN_ATTEMPT {env.get('GITHUB_RUN_ATTEMPT')!r} != 1 (re-runs are refused)")
    if not env.get("GITHUB_SHA"):
        p.append("GITHUB_SHA missing")
    if receipt is None:
        p.append("no admission receipt")
    else:
        if receipt.get("schema") != RECEIPT_SCHEMA:
            p.append("receipt schema mismatch")
        if not receipt.get("permit_id"):
            p.append("receipt without permit_id")
        if receipt.get("repository") != env.get("GITHUB_REPOSITORY"):
            p.append("receipt repository != GITHUB_REPOSITORY")
        if receipt.get("execution_commit") != env.get("GITHUB_SHA"):
            p.append("receipt execution_commit != GITHUB_SHA")
        if str(receipt.get("run_id")) != str(env.get("GITHUB_RUN_ID")):
            p.append("receipt run_id != GITHUB_RUN_ID")
        if expect_workflow and receipt.get("workflow_id") != expect_workflow:
            p.append(f"receipt workflow_id != {expect_workflow}")
    return p


def require(env: dict, receipt: dict | None = None, expect_workflow: str | None = None) -> None:
    p = problems(env, receipt, expect_workflow)
    if p:
        raise JevError("EXECUTION_LOCATION_FORBIDDEN", "; ".join(p))
