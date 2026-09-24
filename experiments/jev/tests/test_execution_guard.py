# -*- coding: utf-8 -*-
"""守卫: 普通本机 ⇒ 网络/模型 import 之前拒绝; 逐条环境缺失各自拒绝; attempt 2 拒绝; receipt 不符拒绝。"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from experiments.jev import execution_guard as G
from experiments.jev.contracts import JevError
from experiments.jev.tests.fakes import github_env, receipt_for

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "experiments" / "jev" / "cli.py"


def test_full_github_env_with_receipt_passes():
    env = github_env(); G.require(env, receipt_for(env), "cce-jev-eval.yml")
    env = github_env("cce-jev-prepare.yml"); G.require(env, receipt_for(env, "cce-jev-prepare.yml"), "cce-jev-prepare.yml")


def test_plain_local_environment_is_forbidden():
    with pytest.raises(JevError) as e:
        G.require({k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}, None)
    assert e.value.code == "EXECUTION_LOCATION_FORBIDDEN"


@pytest.mark.parametrize("over", [
    {"GITHUB_ACTIONS": "false"}, {"RUNNER_ENVIRONMENT": "self-hosted"}, {"GITHUB_REPOSITORY": "someone/else"},
    {"GITHUB_WORKFLOW_REF": "luogangan7-lgtm/cce-engine-oss/.github/workflows/cce-submit.yml@refs/heads/master"},
    {"GITHUB_WORKFLOW_REF": "luogangan7-lgtm/cce-engine-oss/.github/workflows/cce-jev-eval.yml@refs/heads/feature"},
    {"GITHUB_RUN_ID": ""}, {"GITHUB_RUN_ATTEMPT": "2"}, {"GITHUB_SHA": ""},
])
def test_each_missing_or_wrong_variable_is_refused(over):
    env = github_env(**over)
    with pytest.raises(JevError) as e:
        G.require(env, receipt_for(github_env()), "cce-jev-eval.yml")
    assert e.value.code == "EXECUTION_LOCATION_FORBIDDEN"


def test_receipt_must_match_run_and_commit():
    env = github_env()
    for bad in (dict(execution_commit="b" * 40), dict(run_id="999"), dict(repository="x/y"), dict(schema="other"), dict(permit_id=""), dict(workflow_id="cce-jev-prepare.yml")):
        r = receipt_for(env); r.update(bad)
        with pytest.raises(JevError):
            G.require(env, r, "cce-jev-eval.yml")
    with pytest.raises(JevError):
        G.require(env, None, "cce-jev-eval.yml")
    with pytest.raises(JevError):        # prepare receipt cannot be used for eval
        G.require(env, receipt_for(env, "cce-jev-prepare.yml"), "cce-jev-eval.yml")


def test_real_cli_eval_and_prepare_refuse_locally_before_any_import_or_download(tmp_path):
    """真实 runner CLI 在普通本机: 退出码 3 + EXECUTION_LOCATION_FORBIDDEN, 且 torch/decider/huggingface_hub 从未被 import。"""
    receipt = tmp_path / "r.json"; receipt.write_text('{"schema": "cce.jev.admission-receipt.v1", "permit_id": "x"}', encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_") and k != "RUNNER_ENVIRONMENT"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    probe = ("import runpy, sys; sys.argv = %r; "
             "code = 0\n"
             "try:\n    runpy.run_path(%r, run_name='__main__')\nexcept SystemExit as e:\n    code = e.code\n"
             "loaded = [m for m in ('torch', 'transformers', 'decider', 'huggingface_hub') if m in sys.modules]\n"
             "print('EXIT', code, 'LOADED', loaded)")
    for argv in (["cli.py", "eval", "--suite", "s0-smoke-v1", "--receipt", str(receipt), "--bundle", str(tmp_path), "--out", str(tmp_path / "reports" / "x")],
                 ["cli.py", "prepare", "--receipt", str(receipt), "--dest", str(tmp_path / "b"), "--out", str(tmp_path / "o")]):
        p = subprocess.run([sys.executable, "-c", probe % (argv, str(CLI))], capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=120)
        assert "EXIT 3 LOADED []" in p.stdout, (p.stdout, p.stderr)
        assert "EXECUTION_LOCATION_FORBIDDEN" in p.stderr, p.stderr
        assert not (tmp_path / "b").exists() and not (tmp_path / "reports").exists()


def test_faking_env_without_receipt_still_refused():
    env = github_env()
    with pytest.raises(JevError):
        G.require(env, None)
