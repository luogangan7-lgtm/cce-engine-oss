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
assert dispatch["verification"]["expected_input_sha1"] == [input_sha1(row["text"]) for row in source["responses"]]


def vector(length: int) -> list[float]:
    return [1.0 / length] * length


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    for i, row in enumerate(source["responses"]):
        artifact = root / f"cce-{i}-test"
        artifact.mkdir()
        (artifact / "manifest.json").write_text(json.dumps({
            "mode": "reply", "text_sha1": input_sha1(row["text"]),
            "complete": i != 0, "failed_at": "s4_guard" if i == 0 else None,
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
    assert set(activated_window["aggregate_layer_distributions"]) == {"desire", "need", "emotion", "action"}
    assert all(abs(sum(values.values()) - 1.0) < 1e-9
               for values in activated_window["aggregate_layer_distributions"].values())
    first = activated["response_measurements"][0]
    assert first["provenance"]["s1_measurement_complete"] is True
    assert first["provenance"]["downstream_reply_chain_complete"] is False
    assert first["provenance"]["downstream_reply_chain_failed_at"] == "s4_guard"
    assert all("profile_version" not in row and "subject_version" not in row for row in activated["subject_entities"])
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

print("PASS: exact inbound fingerprints, s1-only response scope, downstream guard isolation, stable subjects, instantaneous states, and activated aggregation")
