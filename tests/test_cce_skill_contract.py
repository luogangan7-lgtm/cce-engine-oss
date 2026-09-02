#!/usr/bin/env python3
"""Regression gates for the unified CCE skill and GitHub client."""
from __future__ import annotations

import importlib.util
import json
import re
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = ROOT / "scripts" / "cce_github_client.py"
INSTALLER_PATH = ROOT / "scripts" / "install_cce_skill.py"


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_profiles_validate_and_exact_hashes_round_trip() -> None:
    client = _module(CLIENT_PATH, "cce_github_client")
    expected_counts = {
        "cce_submission_outbound_post_v1.json": 1,
        "cce_submission_outbound_reply_v1.json": 1,
        "cce_submission_subject_chain_v1.json": 8,
    }
    for name, count in expected_counts.items():
        result = client.verify_input(ROOT / "examples" / name, ROOT)
        assert result["ok"] is True
        assert result["items"] == count
        assert len(result["text_sha256"]) == count
        assert all(value.startswith("sha256:") and len(value) == 71
                   for value in result["text_sha256"].values())


def test_manifest_verifier_fails_closed_on_hash_mismatch() -> None:
    client = _module(CLIENT_PATH, "cce_github_client_verify")
    submission = ROOT / "examples" / "cce_submission_outbound_post_v1.json"
    verified = client.verify_input(submission, ROOT)
    job_id, digest = next(iter(verified["text_sha256"].items()))
    manifest = {
        "kind": "cce.workflow_manifest.v1",
        "submission_id": verified["submission_id"],
        "profile": verified["profile"],
        "complete": True,
        "items_expected": 1,
        "items_completed": 1,
        "jobs": [{"job_id": job_id, "profile": verified["profile"],
                  "text_sha256": digest, "engine_complete": True,
                  "measurement_complete": True, "failed_at": None}],
        "errors": [],
    }
    with tempfile.TemporaryDirectory() as raw:
        outdir = Path(raw)
        (outdir / "workflow-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        result = client.verify_result(submission, outdir, ROOT, "https://example/run/1")
        assert result["complete"] is True
        manifest["jobs"][0]["text_sha256"] = "sha256:" + "0" * 64
        (outdir / "workflow-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        try:
            client.verify_result(submission, outdir, ROOT)
        except client.ClientError as exc:
            assert "text_sha256 mismatch" in str(exc)
        else:
            raise AssertionError("tampered manifest was accepted")


def test_only_one_cce_skill_exists() -> None:
    skill_dirs = sorted(path.name for path in (ROOT / "skills").iterdir()
                        if path.is_dir())
    assert skill_dirs == ["cce"]
    skill = (ROOT / "skills" / "cce" / "SKILL.md").read_text(encoding="utf-8")
    assert "config/cce_capability_registry_v1.json" in skill
    assert "NOT_AVAILABLE_PRODUCTION" in skill
    assert "observed" in skill and "inferred" in skill and "derived" in skill
    assert "cce_predict.py" not in skill


def test_skill_requires_authorized_external_dispatch() -> None:
    skill = (ROOT / "skills" / "cce" / "SKILL.md").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "cce-submit.yml").read_text(
        encoding="utf-8"
    )
    for required in (
        "即时明确授权",
        "EXTERNAL_PROCESSING_NOT_AUTHORIZED",
        "离开本机",
        "PRIVATE",
        "Actions artifact",
        "密钥",
        "PII",
        "客户标识",
        "私有 URL",
        "账号名",
        "脱敏",
        "90 天",
        "actions/*@vN",
        "requirements.txt",
        "供应链",
        "不可信数据",
    ):
        assert required in skill, f"CCE 外发 Trust 边界缺少：{required}"
    retention_days = re.findall(r"retention-days:\s*(\d+)", workflow)
    assert retention_days and set(retention_days) == {"90"}, \
        "所有 CCE submission/result artifact 必须按披露统一留存 90 天"


def test_capability_registry_matches_production_workflow_boundary() -> None:
    registry = json.loads((ROOT / "config" / "cce_capability_registry_v1.json")
                          .read_text(encoding="utf-8"))
    assert registry["kind"] == "cce.capability_registry.v1"
    caps = {item["id"]: item for item in registry["capabilities"]}
    for capability in ("outbound_post_measurement", "outbound_reply_measurement",
                       "subject_population_chain"):
        assert caps[capability]["status"] == "production_github"
        assert caps[capability]["entrypoint"] == ".github/workflows/cce-submit.yml"
    video = caps["video_multimodal_parse_v5"]
    assert video["status"] == "component_only"
    assert video["implementation"] == "scripts/cce_video_parse.py"
    assert "production GitHub media-ingest workflow" in video["missing"]
    assert video["missing_state"] == "missing_no_capability"
    assert caps["standalone_image_ingest"]["status"] == "missing"
    assert caps["standalone_audio_ingest"]["status"] == "missing"


def test_installer_exposes_only_unified_skill_and_prunes_managed_legacy() -> None:
    installer = _module(INSTALLER_PATH, "install_cce_skill")
    with tempfile.TemporaryDirectory() as raw:
        target = Path(raw) / "installed"
        target.mkdir()
        legacy = target / "viral-content-recon"
        legacy.symlink_to(ROOT / "skills" / "viral-content-recon",
                          target_is_directory=True)
        result = installer.install(ROOT / "skills", target)
        assert result == {"ok": True, "visible_skills": 1, "drift": {}, "pruned": 1}
        assert (target / "cce").is_symlink()
        assert (target / "cce").resolve() == (ROOT / "skills" / "cce").resolve()
        assert not legacy.exists() and not legacy.is_symlink()


def test_workflow_has_unique_dispatch_identity() -> None:
    workflow = (ROOT / ".github" / "workflows" / "cce-submit.yml").read_text(encoding="utf-8")
    assert "run-name: CCE ${{ inputs.submission_id" in workflow
    assert "submission_id:" in workflow
    assert "dispatch submission_id does not match submission envelope" in workflow
    # 2026-08-18: 原先断言"我在硬编码清单里"。清单已改成遍历 tests/test_*.py,
    # 断言随之改成"遍历机制还在" —— 更强, 它保证所有测试都跑, 不只是我自己。
    assert "for t in tests/test_*.py" in workflow, \
        "CI 必须遍历 tests/test_*.py —— 退回硬编码清单会让新增测试永不执行"
    assert re.search(r'test "\$n" -ge \d+', workflow), \
        "遍历必须配数量下限自守 —— 否则路径写错会静默跑零个测试而 CI 全绿"


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"PASS: {len(tests)} CCE skill contract tests")
