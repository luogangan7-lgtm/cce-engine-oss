# -*- coding: utf-8 -*-
"""资产: 缺件/多件/损坏严格拒绝 · 锁未 READY 拒绝 · 下载计划超上限先停 · decider_config 缺/错即失败(不回默认温度) · 版本不符。"""
import json
from pathlib import Path

import pytest

from experiments.jev import strict_assets as SA
from experiments.jev.contracts import JevError, sha256

SRC = SA.source_lock()


def _bundle(tmp_path, files):
    d = tmp_path / "bundle"; d.mkdir()
    lock = {"schema": SA.ASSETS_SCHEMA, "status": "READY", "repo_id": SRC["repo_id"], "revision": SRC["revision"], "files": {}}
    for name, data in files.items():
        (d / name).write_bytes(data)
        lock["files"][name] = {"size": len(data), "sha256": sha256(data)}
    return d, lock


GOOD_CFG = json.dumps({"temperature": 1.3, "version": "v10", "isolated_levels": True, "max_options": 255, "schema_first": False, "neutralize_none": False}).encode()


def test_source_lock_pins_are_frozen():
    assert SRC["revision"] == "fa996cea58e1c1d8d1ab4d7124154f303b017f95" and SRC["source_revision"] == "7840bb93597e9ba60bf796b4cefbcc5192e5adfb"
    assert SRC["model_version"] == "v10" and SRC["remote_inference_allowed"] is False and SRC["training_enabled"] is False
    assert set(SRC["files"]) >= {"model.safetensors", "config.json", "decider_config.json", "tokenizer.json", "tokenizer_config.json"}
    assert SA.plan_download(SRC, 5 * 1024 ** 3)["total_bytes"] == SRC["planned_download_bytes"] < 5 * 1024 ** 3


def test_download_plan_over_cap_fails_before_any_download():
    with pytest.raises(JevError) as e:
        SA.plan_download(SRC, 1024)
    assert e.value.code == "BUDGET_EXCEEDED"


def test_verify_bundle_good_and_each_corruption_family(tmp_path):
    d, lock = _bundle(tmp_path, {"a.bin": b"aaa", "decider_config.json": GOOD_CFG})
    assert SA.verify_bundle(d, lock, SRC)["verified_files"] == ["a.bin", "decider_config.json"]
    (d / "extra.txt").write_bytes(b"x")
    with pytest.raises(JevError) as e:
        SA.verify_bundle(d, lock, SRC)
    assert e.value.code == "MODEL_BUNDLE_INVALID" and "extra" in e.value.detail
    (d / "extra.txt").unlink(); (d / "a.bin").unlink()
    with pytest.raises(JevError) as e:
        SA.verify_bundle(d, lock, SRC)
    assert "missing" in e.value.detail
    (d / "a.bin").write_bytes(b"aab")       # same size, different bytes
    with pytest.raises(JevError) as e:
        SA.verify_bundle(d, lock, SRC)
    assert "sha256" in e.value.detail
    (d / "a.bin").write_bytes(b"aaaa")      # size differs
    with pytest.raises(JevError) as e:
        SA.verify_bundle(d, lock, SRC)
    assert "size" in e.value.detail


def test_lock_not_ready_or_wrong_revision_refused(tmp_path):
    d, lock = _bundle(tmp_path, {"a.bin": b"aaa"})
    for bad in (dict(status="REQUIRES_GITHUB_PREPARE"), dict(files={}), dict(schema="other")):
        with pytest.raises(JevError) as e:
            SA.verify_bundle(d, {**lock, **bad}, SRC)
        assert e.value.code == "MODEL_BUNDLE_INVALID"
    with pytest.raises(JevError) as e:
        SA.verify_bundle(d, {**lock, "revision": "0" * 40}, SRC)
    assert e.value.code == "MODEL_VERSION_MISMATCH"
    assert SA.assets_lock()["generated_by"].startswith("cce-jev-prepare.yml")   # 仓内 READY 锁来自 GitHub prepare, 非本地手填


def test_decider_config_strict(tmp_path):
    d, _ = _bundle(tmp_path, {"decider_config.json": GOOD_CFG})
    assert SA.read_decider_config(d, SRC)["temperature"] == 1.3
    (d / "decider_config.json").unlink()
    with pytest.raises(JevError) as e:
        SA.read_decider_config(d, SRC)
    assert e.value.code == "MODEL_BUNDLE_INVALID"
    cfg = json.loads(GOOD_CFG); del cfg["temperature"]; (d / "decider_config.json").write_text(json.dumps(cfg))
    with pytest.raises(JevError):
        SA.read_decider_config(d, SRC)
    cfg = json.loads(GOOD_CFG); cfg["version"] = "v8"; (d / "decider_config.json").write_text(json.dumps(cfg))
    with pytest.raises(JevError) as e:
        SA.read_decider_config(d, SRC)
    assert e.value.code == "MODEL_VERSION_MISMATCH"
    cfg = json.loads(GOOD_CFG); cfg["schema_first"] = True; (d / "decider_config.json").write_text(json.dumps(cfg))
    with pytest.raises(JevError) as e:
        SA.read_decider_config(d, SRC)
    assert e.value.code == "RUNTIME_UNSUPPORTED"


def test_anchor_check_git_blob_and_lfs(tmp_path):
    p = tmp_path / "f"; p.write_bytes(b"hello\n")
    assert SA._anchor_ok(p, {"anchor": {"kind": "git_blob_sha1", "value": "ce013625030ba8dba906f756967f9e9ca394464a"}})
    assert SA._anchor_ok(p, {"anchor": {"kind": "lfs_sha256", "value": sha256(b"hello\n")}})
    assert not SA._anchor_ok(p, {"anchor": {"kind": "lfs_sha256", "value": "0" * 64}})


def test_download_refused_locally_before_import(tmp_path):
    from experiments.jev.budget import Ledger
    from experiments.jev.contracts import ExecutionBudget
    ledger = Ledger(ExecutionBudget(0, 0, 0, 0, 10.0, 10 ** 12))
    with pytest.raises(JevError) as e:
        SA.download_bundle(SRC, tmp_path / "x", ledger, {}, None)
    assert e.value.code == "EXECUTION_LOCATION_FORBIDDEN" and not (tmp_path / "x").exists() and ledger.download_bytes == 0
