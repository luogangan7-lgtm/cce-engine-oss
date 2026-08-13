#!/usr/bin/env python3
"""Executable gates for the unified production submission envelope."""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_submission import validate_submission, write_package  # noqa: E402
from cce_workflow_manifest import build as build_workflow_manifest  # noqa: E402


examples = {
    profile: json.loads((ROOT / "examples" / filename).read_text(encoding="utf-8"))
    for profile, filename in {
        "outbound_post": "cce_submission_outbound_post_v1.json",
        "outbound_reply": "cce_submission_outbound_reply_v1.json",
        "subject_chain": "cce_submission_subject_chain_v1.json",
    }.items()
}

registry = json.loads((ROOT / "config" / "cce_workflow_registry_v1.json").read_text(encoding="utf-8"))
assert registry["production_entrypoint"] == ".github/workflows/cce-submit.yml"
assert all((ROOT / path).is_file() for path in registry["workflows"]), registry
assert [path for path, meta in registry["workflows"].items() if meta["class"] == "production"] == [registry["production_entrypoint"]]

for profile, value in examples.items():
    verdict = validate_submission(value)
    assert verdict["ok"], (profile, verdict)
    assert verdict["normalized"]["profile"] == profile
    with tempfile.TemporaryDirectory() as temp:
        result = write_package(value, Path(temp))
        assert result["items"] == (8 if profile == "subject_chain" else 1), result
        normalized = json.loads((Path(temp) / "normalized.json").read_text(encoding="utf-8"))
        assert len(normalized["items"]) == result["items"]

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    package = root / "package"
    write_package(examples["outbound_post"], package)
    normalized = json.loads((package / "normalized.json").read_text(encoding="utf-8"))
    item = normalized["items"][0]
    artifact = root / "artifacts" / "item-0"
    artifact.mkdir(parents=True)
    (artifact / "manifest.json").write_text(json.dumps({
        "text_sha256": item["_meta"]["text_sha256"], "complete": True, "failed_at": None,
        "submission": item["_meta"], "stages": {"s1_readout": {"status": "OK"}},
    }), encoding="utf-8")
    aggregate = build_workflow_manifest(normalized, root / "artifacts")
    assert aggregate["complete"] is True, aggregate

bad_hash = copy.deepcopy(examples["outbound_post"])
bad_hash["items"][0]["text"] += " changed"
assert not validate_submission(bad_hash)["ok"]

bad_context = copy.deepcopy(examples["outbound_reply"])
bad_context["items"][0]["context"]["declaration"]["社会在场"] = "独处"
assert not validate_submission(bad_context)["ok"]

missing_reader = copy.deepcopy(examples["outbound_reply"])
missing_reader["items"][0].pop("reader")
assert not validate_submission(missing_reader)["ok"]

versioned_subject = copy.deepcopy(examples["subject_chain"])
chain = json.loads((ROOT / versioned_subject.pop("subject_chain_path")).read_text(encoding="utf-8"))
versioned_subject.pop("subject_chain_sha256")
chain["subject_windows"][0]["profile_version"] = "v3"
versioned_subject["subject_chain"] = chain
assert not validate_submission(versioned_subject)["ok"]

print("PASS: three standard profiles, exact fingerprints, context taxonomy, required reader evidence, and non-versioned subjects")
