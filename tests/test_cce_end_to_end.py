#!/usr/bin/env python3
"""Executable cross-plane gates for the CCE end-to-end audit."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_end_to_end import audit_end_to_end  # noqa: E402
from cce_population import build_population_analysis  # noqa: E402


case = json.loads((ROOT / "examples" / "cce_foundation_case_v1.json").read_text(encoding="utf-8"))
case["measurement_results"] = [{
    "id": "result:demo-001", "request_ref": "req:demo-001", "model_version": "frozen-test",
    "input_fingerprint": "sha256:test", "assertion": "derived", "distribution": {"desire": 0.5, "need": 0.5},
    "confidence": 0.8, "evidence_refs": ["evt:caption-001"],
}]

chain = {
    "kind": "cce.subject_window_chain.v1",
    "content": {"id": "content:demo-001"},
    "content_measurement": {"status": "completed_validated", "result_refs": ["result:demo-001"]},
    "evidence_records": [
        {"id": "evidence:reach:1", "content_ref": "content:demo-001", "actor_ref": "subject:1", "observed_at": "2026-08-13T01:00:00Z"},
        {"id": "evidence:response:1", "content_ref": "content:demo-001", "actor_ref": "subject:1", "observed_at": "2026-08-13T02:00:00Z"},
    ],
    "distribution_records": [{"id": "distribution:1", "content_ref": "content:demo-001", "observed_at": "2026-08-13T00:30:00Z", "window_complete": True}],
    "subject_entities": [{
        "id": "subject:1", "subject_id": "subject:1", "core": {"desire_baseline": "stable-test"},
        "identity_evidence": [], "state_observations": [],
    }],
    "subject_windows": [
        {"id": "window:target", "window_type": "target", "time_window": {"start": "2026-08-13T00:00:00Z", "end": "2026-08-13T04:00:00Z"},
         "population_set": {"kind": "declared", "member_refs": ["subject:1"]}, "evidence_refs": ["evidence:reach:1"]},
        {"id": "window:reached", "window_type": "reached", "time_window": {"start": "2026-08-13T00:00:00Z", "end": "2026-08-13T04:00:00Z"},
         "population_set": {"kind": "observed_inbound_interactors", "member_refs": ["subject:1"],
                            "coverage": {"scope": "identified_inbound_only", "exhaustive": False}},
         "evidence_refs": ["evidence:reach:1"], "member_evidence": {"subject:1": ["evidence:reach:1"]}},
        {"id": "window:activated", "window_type": "activated", "time_window": {"start": "2026-08-13T00:00:00Z", "end": "2026-08-13T04:00:00Z"},
         "population_set": {"kind": "measured_responses", "member_refs": ["subject:1"]},
         "evidence_refs": ["evidence:response:1"], "measurement_result_refs": ["response:1"],
         "population_analysis": build_population_analysis([{"actor_ref": "subject:1", "distribution": {"activated": 0.7, "not_activated": 0.3}}], "identified_inbound_only")},
        {"id": "window:action", "window_type": "action", "time_window": {"start": "2026-08-13T00:00:00Z", "end": "2026-08-13T04:00:00Z"},
         "population_set": {"kind": "observed_actions", "member_refs": ["subject:1"]},
         "evidence_refs": ["evidence:response:1"], "behavior_record_refs": ["behavior:1"]},
        {"id": "window:conversion", "window_type": "conversion", "time_window": {"start": "2026-08-13T00:00:00Z", "end": "2026-08-13T04:00:00Z"},
         "population_set": {"kind": "joined_commercial", "member_refs": ["subject:1"]},
         "evidence_refs": ["evidence:response:1"], "commercial_record_refs": ["commercial:1"]},
    ],
    "response_measurements": [{
        "id": "response:1", "actor_ref": "subject:1", "response_evidence_refs": ["evidence:response:1"],
        "assertion": "derived", "model_version": "frozen-test", "input_fingerprint": "sha256:response",
        "distribution": {"activated": 0.7, "not_activated": 0.3}, "confidence": 0.8,
    }],
    "behavior_records": [{"id": "behavior:1", "actor_ref": "subject:1", "occurred_at": "2026-08-13T02:30:00Z",
                          "evidence_ref": "evidence:response:1", "publish_id": "publish:1",
                          "observation_scope": "post_exposure_observed_action"}],
    "commercial_records": [{"id": "commercial:1", "actor_ref": "subject:1", "observed_at": "2026-08-13T03:00:00Z",
                            "publish_id": "publish:1", "join_evidence_refs": ["join:1"]}],
    "attribution_results": [
        {"id": f"delta:{name}", "value": 1.0}
        for name in ("target_to_reached", "reached_to_activated", "activated_to_action", "action_to_conversion")
    ],
    "attribution_protocols": [
        {"delta": name, "frozen_at": "t-1", "comparison_space": "same-member", "metric": "test", "result_ref": f"delta:{name}"}
        for name in ("target_to_reached", "reached_to_activated", "activated_to_action", "action_to_conversion")
    ],
}

passed = audit_end_to_end(case, chain)
assert passed["overall_status"] == "VERIFIED", passed

mismatch = copy.deepcopy(case)
mismatch["content"]["id"] = "content:other"
assert audit_end_to_end(mismatch, chain)["overall_status"] == "NOT_VERIFIED"

fabricated_ref = copy.deepcopy(chain)
fabricated_ref["content_measurement"]["result_refs"] = ["result:not-real"]
assert audit_end_to_end(case, fabricated_ref)["overall_status"] == "NOT_VERIFIED"

real_chain = json.loads((ROOT / "examples" / "cce_reddit_post6_chain_audit.json").read_text(encoding="utf-8"))
real = audit_end_to_end(None, real_chain)
assert real["overall_status"] == "NOT_VERIFIED", real
assert real["cross_plane_gates"]["measurement_case"]["status"] == "NOT_MET", real

print("PASS: end-to-end content identity/result links, honest cross-plane verification, and real post6 NOT_VERIFIED")
