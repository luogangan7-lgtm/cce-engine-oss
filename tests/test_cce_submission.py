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
from cce_full_run import CHAINS  # noqa: E402
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
submission_contract = json.loads((ROOT / "config" / "cce_submission_contract_v1.json").read_text(encoding="utf-8"))
assert registry["production_entrypoint"] == ".github/workflows/cce-submit.yml"
assert all((ROOT / path).is_file() for path in registry["workflows"]), registry
assert [path for path, meta in registry["workflows"].items() if meta["class"] == "production"] == [registry["production_entrypoint"]]
# 2026-08-18: 追加 qualified_readout —— Measurement System 的出口闸。
# 这份硬编码期望是**冻结期望**, 动它必须是有意的: 本次是有意加段, 不是被动跟随。
assert submission_contract["profiles"]["outbound_post"]["stages"] == [
    "s0_context", "s1_readout", "s2_knots", "s3_emotion_policy", "s4_guard", "qualified_readout"
]
assert [stage.stage_name for stage in CHAINS["outbound_post"]] == submission_contract["profiles"]["outbound_post"]["stages"]
# 2026-08-18: 补上缺失的孪生断言。此前只钉 outbound_post, 不钉 outbound_reply ——
# 于是契约写 6 段、CHAINS["reply"] 只有 5 段, 静态层与聚合层都看不见, 持续数周。
assert [stage.stage_name for stage in CHAINS["reply"]] == submission_contract["profiles"]["outbound_reply"]["stages"]
assert [stage.stage_name for stage in CHAINS["response"]] == [
    "s0_context", "s1_readout", "s2_knots", "s3_emotion_policy"
]

for profile, value in examples.items():
    verdict = validate_submission(value)
    assert verdict["ok"], (profile, verdict)
    assert verdict["normalized"]["profile"] == profile
    if profile == "subject_chain":
        assert verdict["normalized"]["response_source"]["context"]["dimensions"]
    else:
        snapshot = verdict["normalized"]["items"][0]["_meta"]["context_snapshot"]
        assert snapshot["dimensions"] and snapshot["provenance"], snapshot
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
        "chain": submission_contract["profiles"]["outbound_post"]["stages"],
    }), encoding="utf-8")
    aggregate = build_workflow_manifest(normalized, root / "artifacts")
    assert aggregate["complete"] is True, aggregate

# 对齐诊断按需开启(2026-08-15): 没跑就没有 reply_alignment.json。
# 关着跑必须照样 complete; 明确要求跑过而文件缺失才算错误。
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    package = root / "package"
    write_package(examples["outbound_reply"], package)
    normalized = json.loads((package / "normalized.json").read_text(encoding="utf-8"))
    item = normalized["items"][0]
    artifact = root / "artifacts" / "item-0"
    artifact.mkdir(parents=True)
    (artifact / "manifest.json").write_text(json.dumps({
        "text_sha256": item["_meta"]["text_sha256"], "complete": True, "failed_at": None,
        "submission": item["_meta"], "stages": {"s1_readout": {"status": "OK"}},
        "chain": submission_contract["profiles"]["outbound_reply"]["stages"],
    }), encoding="utf-8")

    off = build_workflow_manifest(normalized, root / "artifacts")
    assert off["complete"] is True, off
    assert off["jobs"][0]["reply_alignment_pass"] is None, off

    required = build_workflow_manifest(normalized, root / "artifacts", require_alignment=True)
    assert not required["complete"] and any("reply alignment missing" in e for e in required["errors"]), required

    (artifact / "reply_alignment.json").write_text(
        json.dumps({"verdict": {"PASS": True, "九结对齐": {"alignment_score": 0.72}}}), encoding="utf-8")
    for flag in (False, True):
        got = build_workflow_manifest(normalized, root / "artifacts", require_alignment=flag)
        assert got["complete"] is True and got["jobs"][0]["reply_alignment_pass"] is True, got

bad_hash = copy.deepcopy(examples["outbound_post"])
bad_hash["items"][0]["text"] += " changed"
assert not validate_submission(bad_hash)["ok"]

bad_context = copy.deepcopy(examples["outbound_reply"])
bad_context["items"][0]["context"]["declaration"]["社会在场"] = "独处"
assert not validate_submission(bad_context)["ok"]

missing_reader = copy.deepcopy(examples["outbound_reply"])
missing_reader["items"][0].pop("reader")
assert not validate_submission(missing_reader)["ok"]

# Reddit is the stable adapter; the subreddit is a runtime context snapshot.
other_community = copy.deepcopy(examples["outbound_post"])
other_community["items"][0]["surface"]["id"] = "r/HearingLoss"
assert validate_submission(other_community)["ok"], validate_submission(other_community)

bad_adapter = copy.deepcopy(examples["outbound_post"])
bad_adapter["items"][0]["platform_adapter"]["version"] = "2.0.0"
assert not validate_submission(bad_adapter)["ok"]

platform_only_context = copy.deepcopy(examples["outbound_post"])
platform_only_context["items"][0]["context"].pop("dimensions")
assert not validate_submission(platform_only_context)["ok"]

flat_surface = copy.deepcopy(examples["outbound_post"])
flat_surface["items"][0]["surface"] = "r/HearingAids"
assert not validate_submission(flat_surface)["ok"]

unsupported_domain = copy.deepcopy(examples["outbound_post"])
unsupported_domain["items"][0]["domain"] = "fragrance"
domain_verdict = validate_submission(unsupported_domain)
assert not domain_verdict["ok"] and any("guard_profile does not cover domain" in row for row in domain_verdict["errors"])

versioned_subject = copy.deepcopy(examples["subject_chain"])
chain = json.loads((ROOT / versioned_subject.pop("subject_chain_path")).read_text(encoding="utf-8"))
versioned_subject.pop("subject_chain_sha256")
chain["subject_windows"][0]["profile_version"] = "v3"
versioned_subject["subject_chain"] = chain
assert not validate_submission(versioned_subject)["ok"]

print("PASS: schema 1.1 profiles, Universal Context artifacts, dynamic community context, versioned platform adapter, s0-s4 production post chain, exact fingerprints, and non-versioned subjects")

# 2026-08-18 新增: chain 断言的反向测试。
# 纪律: 不做反向测试的断言等同于没有断言 —— 它必须能被观察到失败。
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    package = root / "package"
    write_package(examples["outbound_reply"], package)
    normalized = json.loads((package / "normalized.json").read_text(encoding="utf-8"))
    item = normalized["items"][0]
    contract_chain = submission_contract["profiles"]["outbound_reply"]["stages"]

    def _mk(chain):
        art = root / f"rt-{abs(hash(tuple(chain)))}"
        (art / "item-0").mkdir(parents=True)
        (art / "item-0" / "manifest.json").write_text(json.dumps({
            "text_sha256": item["_meta"]["text_sha256"], "complete": True, "failed_at": None,
            "submission": item["_meta"], "stages": {"s1_readout": {"status": "OK"}},
            "chain": chain,
        }), encoding="utf-8")
        return build_workflow_manifest(normalized, art)

    assert _mk(contract_chain)["complete"] is True, "契约链必须绿"
    dropped = _mk([s for s in contract_chain if s != "reader_baseline"])
    assert not dropped["complete"] and any("contract chain mismatch" in e for e in dropped["errors"]), \
        "摘掉 reader_baseline 必须红 —— 这正是 2026-08-18 之前持续数周未被发现的那个缺陷"
    reordered = _mk([contract_chain[1], contract_chain[0]] + contract_chain[2:])
    assert not reordered["complete"], "顺序也是契约的一部分, 乱序必须红"

print("test_cce_submission: OK (含 chain 断言反向测试)")
