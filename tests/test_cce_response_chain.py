#!/usr/bin/env python3
"""Executable gates for exact-input response measurement ingestion."""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_response_chain import ACTIONS, DESIRES, EMOTIONS, NEED_KEYS, build_dispatch, ingest, input_sha1  # noqa: E402
from cce_window_chain import audit_chain, validate_chain  # noqa: E402


source = json.loads((ROOT / "examples" / "cce_reddit_post6_responses_v1.json").read_text(encoding="utf-8"))
chain = json.loads((ROOT / "examples" / "cce_reddit_post6_chain_audit.json").read_text(encoding="utf-8"))
dispatch = build_dispatch(source, chain)
assert dispatch["event_type"] == "cce-batch"
assert len(dispatch["client_payload"]["items"]) == 8
assert all(item["mode"] == "response" for item in dispatch["client_payload"]["items"])
assert dispatch["verification"]["expected_input_sha1"] == [input_sha1(row["text"]) for row in source["responses"]]


def vector(length: int) -> list[float]:
    return [1.0 / length] * length


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    for i, row in enumerate(source["responses"]):
        artifact = root / f"cce-{i}-test"
        artifact.mkdir()
        (artifact / "manifest.json").write_text(json.dumps({
            "mode": "response", "text_sha1": input_sha1(row["text"]),
            "complete": True, "failed_at": None,
            "started": "2026-08-13 00:00:00", "stages": {"s1_readout": {"status": "OK"}},
        }), encoding="utf-8")
        (artifact / "s1_readout.json").write_text(json.dumps({
            "input_sha": __import__("hashlib").sha256(row["text"].encode()).hexdigest()[:16],
            "instrument": {"stage1": "frozen-author-state-test"},
            "stage1": {
                "k_requested": 3, "k_ok": 3,
                "layers": {"desire_vec": vector(len(DESIRES)), "need_vec": vector(len(NEED_KEYS)),
                           "emotion_vec": vector(len(EMOTIONS)), "action_vec": vector(len(ACTIONS))},
                "within_js": {"desire_vec": 0.1, "need_vec": 0.1, "emotion_vec": 0.1, "action_vec": 0.1},
            },
        }), encoding="utf-8")
    activated = ingest(source, chain, root)
    verdict = validate_chain(activated)
    audit = audit_chain(activated)
    assert verdict["ok"], verdict
    assert len(activated["response_measurements"]) == 8
    assert len(activated["subject_entities"]) == 8
    assert audit["gates"]["activated_window"]["status"] == "PASS", audit
    assert audit["overall_status"] == "NOT_VERIFIED", audit
    activated_window = next(row for row in activated["subject_windows"] if row["window_type"] == "activated")
    population = activated_window["population_subject"]
    assert set(population["member_distributions"]) == {row["actor_ref"] for row in source["responses"]}
    assert population["heterogeneity"]["pair_count"] == 28
    assert abs(sum(population["member_weights"].values()) - 1.0) < 1e-9
    assert abs(sum(row["weight"] for row in population["mode_mixture"]) + population["unassigned_weight"] - 1.0) < 1e-9
    assert population["mode_partition"]["status"] in {"descriptive_not_causal", "insufficient_support"}
    assert population["population_mixture"]["marginal_semantics"].endswith("never an individual persona")
    assert "aggregate_distribution" not in activated_window and "aggregate_layer_distributions" not in activated_window
    mean_person = copy.deepcopy(activated)
    mean_window = next(row for row in mean_person["subject_windows"] if row["window_type"] == "activated")
    mean_window.pop("population_subject")
    mean_window["aggregate_distribution"] = {"activated": 0.5, "not_activated": 0.5}
    assert not validate_chain(mean_person)["ok"]
    first = activated["response_measurements"][0]
    assert first["assertion"] == "derived"
    assert first["measurement_scope"] == "derived_response_text_distribution"
    assert first["provenance"]["s1_measurement_complete"] is True
    assert first["provenance"]["response_chain_complete"] is True
    assert first["provenance"]["response_chain_failed_at"] is None
    assert all("profile_version" not in row and "subject_version" not in row for row in activated["subject_entities"])
    assert all(state["assertion"] == "inferred" for subject in activated["subject_entities"] for state in subject["state_observations"])
    broken = copy.deepcopy(source)
    broken["responses"][0]["text"] += " changed"
    try:
        ingest(broken, chain, root)
    except ValueError as exc:
        assert "missing exact-input CCE artifact" in str(exc)
    else:
        raise AssertionError("changed input must not reuse an artifact")

    failed_s1 = root / "cce-0-test" / "manifest.json"
    manifest = json.loads(failed_s1.read_text(encoding="utf-8"))
    manifest["stages"]["s1_readout"]["status"] = "FAIL"
    failed_s1.write_text(json.dumps(manifest), encoding="utf-8")
    try:
        ingest(source, chain, root)
    except ValueError as exc:
        assert "remote CCE s1 failed" in str(exc)
    else:
        raise AssertionError("failed s1 measurement must be rejected")

print("PASS: exact inbound fingerprints, response s0-s3 scope, inferred state boundary, stable subjects, and heterogeneity-preserving population projection")
