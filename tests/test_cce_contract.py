#!/usr/bin/env python3
"""Executable gates for the context-bound CCE measurement contract."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_contract import validate_case  # noqa: E402
from cce_foundation_adapter import adapt  # noqa: E402
from cce_event_assemble import assemble  # noqa: E402
from cce_subject_profile import build_from_cards, validate_collection  # noqa: E402
from cce_case_assemble import build_request  # noqa: E402
from cce_foundation_prepare import fingerprint  # noqa: E402
from cce_video_parse import _audio_capabilities  # noqa: E402


case = json.loads((ROOT / "examples" / "cce_foundation_case_v1.json").read_text(encoding="utf-8"))
valid = validate_case(case)
assert valid["ok"], valid

leaked = copy.deepcopy(case)
leaked["cce_requests"][0]["outcome_refs"] = ["outcome:future"]
blocked = validate_case(leaked)
assert not blocked["ok"] and any("forbidden CCE inputs" in e for e in blocked["errors"]), blocked

profile_input = copy.deepcopy(case)
profile_input["cce_requests"][0]["subject_refs"] = ["subject:person:v3"]
blocked = validate_case(profile_input)
assert not blocked["ok"] and any("forbidden CCE inputs" in e for e in blocked["errors"]), blocked

bad_time = copy.deepcopy(case)
bad_time["observations"][0]["time"] = {"start": 6.4, "end": 5.2}
blocked = validate_case(bad_time)
assert not blocked["ok"] and any("half-open" in e for e in blocked["errors"]), blocked

parsed = {"name": "adapter-test", "video": "does-not-exist.mp4", "duration": 3.0,
          "visual": {"0.5": {"M3": {"scene": "a visible scene"}}}, "ocr": {"0.5": ["visible text"]},
          "ocr_meta": {"engine": "test"}, "audio": {"transcript": "visible speech", "event_tags": ["BGM"]},
          "cinematography": {"shot_boundaries": [1.2]}, "completeness": {}}
adapter_case = adapt(parsed, ROOT / "examples" / "cce_foundation_case_v1.json")
adapted = validate_case(adapter_case)
assert adapted["ok"], adapted
assembled = validate_case(assemble(adapter_case))
assert assembled["ok"] and assembled["counts"]["events"] > adapted["counts"]["events"], assembled

adapter_case["context_snapshots"] = copy.deepcopy(case["context_snapshots"])
request_case = build_request(adapter_case, "event_packet@v1")
request_verdict = validate_case(request_case)
assert request_verdict["ok"] and request_verdict["counts"]["cce_requests"] == 1, request_verdict
request = request_case["cce_requests"][0]
assert request["context_snapshot_ref"] == request_case["context_snapshots"][0]["id"], request
assert request["measurement_mode"] == "stimulus", request
assert not any(k in request for k in ("subject_refs", "context_refs", "baseline_ref", "profile_version")), request

transition_source = copy.deepcopy(case)
transition_source["cce_requests"] = []
transition_source["state_snapshots"] = [{
    "id": "state:builder-before", "subject_ref": "subject:demo", "observed_at": "2026-08-13T07:59:00Z",
    "assertion": "inferred", "dimensions": {"attention": 0.2}, "evidence_refs": ["evt:caption-001"],
    "confidence": 0.9, "temporal_scope": "session",
}]
transition_request_case = build_request(transition_source, "event_packet@v2", "transition", "state:builder-before")
transition_request = transition_request_case["cce_requests"][0]
assert transition_request["pre_state_snapshot_ref"] == "state:builder-before"
assert transition_request["id"] != request["id"], "measurement mode/pre-state must participate in request identity"

platform_only = copy.deepcopy(case)
platform_only["context_snapshots"][0]["dimensions"] = {}
blocked = validate_case(platform_only)
assert not blocked["ok"] and any("Universal Context" in e for e in blocked["errors"]), blocked

transition = copy.deepcopy(case)
transition["state_snapshots"] = [
    {"id": "state:before", "subject_ref": "subject:demo", "observed_at": "2026-08-13T07:59:00Z",
     "assertion": "inferred", "dimensions": {"attention": 0.2, "trust": 0.4},
     "evidence_refs": ["evt:caption-001"], "confidence": 0.9, "temporal_scope": "session"},
    {"id": "state:after", "subject_ref": "subject:demo", "observed_at": "2026-08-13T08:01:00Z",
     "assertion": "inferred", "dimensions": {"attention": 0.6, "trust": 0.5},
     "evidence_refs": ["evt:caption-001"], "confidence": 0.7, "temporal_scope": "session"},
]
transition["cce_requests"][0].update({"measurement_mode": "transition", "pre_state_snapshot_ref": "state:before"})
transition["state_transitions"] = [{
    "id": "transition:demo", "request_ref": "req:demo-001", "pre_state_snapshot_ref": "state:before",
    "post_state_snapshot_ref": "state:after", "delta": {"attention": 0.4, "trust": 0.1},
    "evidence_refs": ["evt:caption-001"], "confidence": 0.7,
}]
transition["measurement_results"] = [{
    "id": "result:transition", "request_ref": "req:demo-001", "assertion": "derived",
    "model_version": "test", "input_fingerprint": "sha256:test", "confidence": 0.7,
    "evidence_refs": ["evt:caption-001"], "state_transition_ref": "transition:demo",
}]
assert validate_case(transition)["ok"], validate_case(transition)
bad_delta = copy.deepcopy(transition)
bad_delta["state_transitions"][0]["delta"]["attention"] = 0.1
blocked = validate_case(bad_delta)
assert not blocked["ok"] and any("state_after - state_before" in e for e in blocked["errors"]), blocked

cards_path = ROOT / "docs" / "subject_cards_v3_20260813.json"
cards = build_from_cards(json.loads(cards_path.read_text(encoding="utf-8")), cards_path)
card_verdict = validate_collection(cards)
assert card_verdict["ok"] and card_verdict["counts"]["reference_cards"] == 13, card_verdict
assert all("profile_version" not in row and "subject_type" not in row for row in cards["cards"]), cards
assert cards["kind"] == "cce.subject_card_collection.v1"
assert all(row["subject_ref"].startswith("subject:reddit:") for row in cards["cards"])
assert all("not a subject" not in row["limits"] for row in cards["cards"])
assert cards["segment_capabilities"]["structural_subject_segments"].startswith("descriptive_allowed")

subject_contract = json.loads((ROOT / "config" / "cce_subject_system_contract_v1.json").read_text(encoding="utf-8"))
assert set(subject_contract["scale_axis"]) == {"individual", "dynamic_segment", "population"}
assert set(subject_contract["stage_axis"]) == {"target", "delivered", "reached", "activated", "action", "conversion"}
assert len(subject_contract["parameter_registry"]) == 56
assert subject_contract["hard_gates"]["no_singleton_segment"]
window_contract = json.loads((ROOT / "config" / "cce_subject_window_contract_v1.json").read_text(encoding="utf-8"))
assert set(window_contract["window_types"]) == set(subject_contract["stage_axis"])

assert len(fingerprint(ROOT / "examples" / "cce_foundation_case_v1.json")) == 16
audio_capabilities = _audio_capabilities(True, ["BGM"])
assert audio_capabilities["source_layers"]["bgm"]["status"] == "detected_not_separated", audio_capabilities

print("PASS: three CCE modes, Universal Context, exact State Transition, 56-domain subject contract, population stages, evidence-backed subject cards, leakage/time gates, event adapters, and audio boundary")
