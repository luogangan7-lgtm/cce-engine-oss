# -*- coding: utf-8 -*-
"""守卫: 普通本机 ⇒ 网络/模型 import 之前拒绝; 逐条环境缺失各自拒绝; attempt 2 拒绝; receipt 不符拒绝。"""
import json
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
                 ["cli.py", "prepare", "--receipt", str(receipt), "--dest", str(tmp_path / "b"), "--out", str(tmp_path / "o")],
                 # ★ 2026-09-27 hf_choice 入口同样: 守卫先于任何读锁/import/下载
                 ["cli.py", "eval", "--model", "qwen3-4b-2507", "--suite", "s0-smoke-v1", "--receipt", str(receipt), "--bundle", str(tmp_path), "--out", str(tmp_path / "reports" / "x")],
                 ["cli.py", "prepare", "--model", "qwen3.5-4b", "--receipt", str(receipt), "--dest", str(tmp_path / "b"), "--out", str(tmp_path / "o")],
                 ["cli.py", "prepare-smoke", "--model", "qwen3.5-4b", "--receipt", str(receipt), "--bundle", str(tmp_path), "--proposal", str(receipt), "--out", str(tmp_path / "o")],
                 ["cli.py", "fetch-bundle", "--model", "qwen3-4b-2507", "--receipt", str(receipt), "--dest", str(tmp_path / "b")]):
        p = subprocess.run([sys.executable, "-c", probe % (argv, str(CLI))], capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=120)
        assert "EXIT 3 LOADED []" in p.stdout, (p.stdout, p.stderr)
        assert "EXECUTION_LOCATION_FORBIDDEN" in p.stderr, p.stderr
        assert not (tmp_path / "b").exists() and not (tmp_path / "reports").exists()


def test_faking_env_without_receipt_still_refused():
    env = github_env()
    with pytest.raises(JevError):
        G.require(env, None)



def test_eval_policy_binding_inside_container():
    import importlib.util
    sp = importlib.util.spec_from_file_location("_cli_ep", CLI); cli = importlib.util.module_from_spec(sp); sp.loader.exec_module(cli)
    man = {"policy": "cpu_compare.json"}
    assert cli.eval_policy({"suite_id": "s0-compare-v1", "resource_policy": "cpu_compare.json"}, "s0-compare-v1", man)["policy_id"] == "cpu_compare.v1"
    for rc in ({"suite_id": "s0-smoke-v1", "resource_policy": "cpu_compare.json"}, {"suite_id": "s0-compare-v1", "resource_policy": "cpu_smoke.json"},
               {"suite_id": "s0-compare-v1", "resource_policy": "../x.json"}):
        try:
            cli.eval_policy(rc, "s0-compare-v1", man); raise AssertionError(rc)
        except JevError as e:
            assert e.code == "PERMIT_NOT_APPROVED"


def test_suite_files_lists_exactly_the_manifest_corpus_files():
    import json as _j
    env = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}; env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([sys.executable, str(CLI), "suite-files", "--suite", "s0-compare-v1"], capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=120)
    man = _j.loads((ROOT / "experiments/jev/suites/s0-compare-v1.manifest.json").read_text(encoding="utf-8"))
    assert p.returncode == 0 and p.stdout.split() == man["provenance"]["corpus_files"], (p.returncode, p.stdout)
    p = subprocess.run([sys.executable, str(CLI), "suite-files", "--suite", "s0-smoke-v1"], capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=120)
    assert p.returncode == 0 and p.stdout.strip() == ""


def test_host_check_upload_scans_suite_texts(tmp_path):
    import json as _j
    sys.path.insert(0, str(ROOT))
    from experiments.jev.run_suite import load_suite, suite_texts
    items, _ = load_suite("s0-compare-v1")
    t = suite_texts(items)[3]
    root = tmp_path / "reports" / "run"; root.mkdir(parents=True)
    (root / "report.json").write_text(_j.dumps({"ok": True}), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}; env["PYTHONDONTWRITEBYTECODE"] = "1"
    run = lambda: subprocess.run([sys.executable, str(CLI), "check-upload", "--root", str(root), "--suite", "s0-compare-v1"], capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=300)
    p = run(); assert p.returncode == 0 and '"leak_scanned_items": 54' in p.stdout, p.stderr[-300:]
    (root / "notes").write_text("x " + t[40:72] + " y", encoding="utf-8")                              # 无扩展名也要扫
    p = run(); assert p.returncode == 3 and "OUTPUT_INVALID" in p.stderr and t[40:60] not in p.stderr + p.stdout



def test_cmd_eval_routes_policy_through_eval_policy():
    """容器入口必须用回执策略(经 eval_policy), 不许再硬编码某个策略文件。"""
    import ast
    src = CLI.read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "cmd_eval")
    body = ast.get_source_segment(src, fn)
    assert "eval_policy(receipt, a.suite, manifest)" in body and "cpu_smoke" not in body and "cpu_compare" not in body and '_policy("' not in body
    llm = ast.get_source_segment(src, next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "_eval_llm"))
    assert "eval_policy(receipt, a.suite, manifest)" in llm and not any(f"cpu_{x}" in llm for x in ("smoke", "compare", "probe")) and '_policy("' not in llm and "_receipt_model(receipt, a.model)" in llm
    for name in ("_prepare_llm", "cmd_prepare_smoke", "cmd_fetch_bundle", "_eval_llm"):            # 守卫是每个 hf 入口的第一句
        f = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == name)
        first = next(st for st in f.body if not (isinstance(st, ast.Expr) and isinstance(getattr(st, "value", None), ast.Constant)))
        seg = ast.get_source_segment(src, first)
        assert "execution_guard.require(" in seg or name == "cmd_prepare_smoke" or name == "cmd_fetch_bundle", (name, seg)
        assert "execution_guard.require(env, receipt, LLM_" in ast.get_source_segment(src, f), name



@pytest.mark.parametrize("entry", ["_eval_llm", "cmd_fetch_bundle", "_prepare_llm", "cmd_prepare_smoke"])
def test_hf_entries_refuse_a_model_the_permit_did_not_admit(entry, monkeypatch, tmp_path):
    """许可只批了 qwen3.5-4b ⇒ 拿它跑 qwen3-4b-2507 在读锁/联网检查/加载之前就拒绝(行为, 不是源码 grep)。"""
    import argparse
    import experiments.jev.cli as C
    wf = C.LLM_EVAL_WF if entry in ("_eval_llm", "cmd_fetch_bundle") else C.LLM_PREPARE_WF
    env = github_env(wf); rec = receipt_for(env, wf); rec["models"] = ["qwen3.5-4b"]
    for k, val in env.items():
        monkeypatch.setenv(k, val)
    rf = tmp_path / "r.json"; rf.write_text(json.dumps(rec), encoding="utf-8")
    monkeypatch.setattr(C, "_model_locks", lambda *a, **k: pytest.fail("read locks before the permit binding"))
    monkeypatch.setattr(C, "_network_isolated", lambda *a, **k: pytest.fail("network check before the permit binding"))
    a = argparse.Namespace(model="qwen3-4b-2507", receipt=str(rf), suite="s0-compare-llm-v1", bundle=str(tmp_path), out=str(tmp_path / "reports" / "x"),
                           dest=str(tmp_path / "b"), plan_only=False, proposal=str(rf))
    with pytest.raises(JevError) as e:
        fn = getattr(C, entry)
        fn(a, env, rec) if entry in ("_eval_llm", "_prepare_llm") else fn(a)
    assert e.value.code == "PERMIT_NOT_APPROVED" and "not in the admitted permit" in e.value.detail
