#!/usr/bin/env python3
"""CCE Foundation Contract v1 的零依赖结构验证器。

它故意只做不可争辩的契约检查：层级、引用、时间、认识论标签和真值泄漏。
它不评价任何心理推断，也不替代统计校准 gate。
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from cce_platform_adapter import validate_platform_context


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "cce_foundation_contract_v2.json"
VALID_ASSERTIONS = {"observed", "inferred", "derived"}
VALID_STATE_ASSERTIONS = VALID_ASSERTIONS | {"unknown"}
VALID_EVENT_LAYERS = {"atomic", "composite"}
MEASUREMENT_MODES = {"stimulus", "observed_response", "transition"}
CONTEXT_DIMENSIONS = {
    "time", "location", "environment", "device", "session", "social",
    "relationship", "life", "task", "current_goal",
}


def _err(errors: list[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def _is_ref(value: Any, known: set[str]) -> bool:
    return isinstance(value, str) and value in known


def _time_is_valid(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    start, end = value.get("start"), value.get("end")
    return all(isinstance(x, (int, float)) and math.isfinite(x) for x in (start, end)) and 0 <= start < end


def _instant_is_valid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _state_dimensions_are_valid(value: Any) -> bool:
    return (isinstance(value, dict) and bool(value)
            and all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1
                    for v in value.values()))


def _context_dimensions_are_valid(value: Any) -> bool:
    if not isinstance(value, dict) or not value or any(key not in CONTEXT_DIMENSIONS for key in value):
        return False
    for dimension in value.values():
        if not isinstance(dimension, dict) or "value" not in dimension:
            return False
        if dimension.get("assertion") not in VALID_STATE_ASSERTIONS:
            return False
        if not isinstance(dimension.get("evidence_refs"), list):
            return False
    return True


def validate_context_snapshot(context: Any, path: str = "context_snapshot") -> list[str]:
    errors: list[str] = []
    if not isinstance(context, dict):
        return [f"{path}: must be an object"]
    _require(context, path, ("id", "observed_at", "summary", "dimensions", "provenance"), errors)
    if not _instant_is_valid(context.get("observed_at")):
        _err(errors, path + ".observed_at", "must be ISO-8601")
    if not _context_dimensions_are_valid(context.get("dimensions")):
        _err(errors, path + ".dimensions", "must use explicit Universal Context dimensions with value/assertion/evidence_refs")
    platform_fields = (context.get("platform"), context.get("platform_adapter"), context.get("surface"))
    if any(value is not None for value in platform_fields):
        if not all(value is not None for value in platform_fields):
            _err(errors, path, "platform/platform_adapter/surface must be supplied together")
        else:
            verdict = validate_platform_context(*platform_fields, path)
            errors.extend(verdict["errors"])
    return errors


def _require(record: dict[str, Any], path: str, fields: tuple[str, ...], errors: list[str]) -> None:
    for field in fields:
        if field not in record or record[field] in (None, "", []):
            _err(errors, path, f"missing required field {field!r}")


def _index(case: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    rows = case.get(key, [])
    return {r["id"]: r for r in rows if isinstance(r, dict) and isinstance(r.get("id"), str)}


def validate_case(case: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, JSON-serialisable verdict; never raises for invalid input."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(case, dict):
        return {"ok": False, "errors": ["$: case must be an object"], "warnings": []}
    if case.get("kind") != "cce.analysis_case.v2":
        _err(errors, "kind", "must equal 'cce.analysis_case.v2'")

    content = case.get("content")
    if not isinstance(content, dict):
        _err(errors, "content", "must be an object")
    else:
        _require(content, "content", ("id", "format", "source", "content_hash"), errors)

    observations = _index(case, "observations")
    events = _index(case, "events")
    contexts = _index(case, "context_snapshots")
    state_snapshots = _index(case, "state_snapshots")
    requests = _index(case, "cce_requests")
    results = _index(case, "measurement_results")
    transitions = _index(case, "state_transitions")
    outcomes = _index(case, "outcomes")
    exposures = _index(case, "exposures")
    known_evidence = set(observations) | set(events)

    for key in ("observations", "events", "context_snapshots", "state_snapshots",
                "cce_requests", "measurement_results", "state_transitions", "outcomes"):
        rows = case.get(key, [])
        if not isinstance(rows, list):
            _err(errors, key, "must be a list")
            continue
        ids = [r.get("id") for r in rows if isinstance(r, dict)]
        if len(ids) != len(set(ids)):
            _err(errors, key, "record ids must be unique")

    for oid, obs in observations.items():
        p = f"observations[{oid}]"
        _require(obs, p, ("id", "kind", "assertion", "evidence_refs", "provenance"), errors)
        if obs.get("assertion") != "observed":
            _err(errors, p, "observations must use assertion='observed'")
        if "time" in obs and not _time_is_valid(obs["time"]):
            _err(errors, p + ".time", "must be a finite half-open [start,end) interval")

    for eid, event in events.items():
        p = f"events[{eid}]"
        _require(event, p, ("id", "event_type", "layer", "assertion", "member_refs", "evidence_refs", "confidence"), errors)
        if event.get("layer") not in VALID_EVENT_LAYERS:
            _err(errors, p + ".layer", "must be atomic or composite")
        if event.get("assertion") not in VALID_ASSERTIONS:
            _err(errors, p + ".assertion", f"must be one of {sorted(VALID_ASSERTIONS)}")
        if not isinstance(event.get("confidence"), (int, float)) or not 0 <= event["confidence"] <= 1:
            _err(errors, p + ".confidence", "must be in [0,1]")
        if "time" in event and not _time_is_valid(event["time"]):
            _err(errors, p + ".time", "must be a finite half-open [start,end) interval")
        for ref in event.get("member_refs", []):
            if ref not in known_evidence:
                _err(errors, p + ".member_refs", f"unknown evidence/event ref {ref!r}")
        for ref in event.get("evidence_refs", []):
            if ref not in observations:
                _err(errors, p + ".evidence_refs", f"must reference observed evidence, got {ref!r}")

    for cid, context in contexts.items():
        p = f"context_snapshots[{cid}]"
        errors.extend(validate_context_snapshot(context, p))

    for sid, snapshot in state_snapshots.items():
        p = f"state_snapshots[{sid}]"
        _require(snapshot, p, ("id", "subject_ref", "observed_at", "assertion", "dimensions",
                               "evidence_refs", "confidence", "temporal_scope"), errors)
        if not _instant_is_valid(snapshot.get("observed_at")):
            _err(errors, p + ".observed_at", "must be ISO-8601")
        if snapshot.get("assertion") not in VALID_STATE_ASSERTIONS:
            _err(errors, p + ".assertion", f"must be one of {sorted(VALID_STATE_ASSERTIONS)}")
        if not _state_dimensions_are_valid(snapshot.get("dimensions")):
            _err(errors, p + ".dimensions", "must be non-empty [0,1] scalar state dimensions")
        confidence = snapshot.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            _err(errors, p + ".confidence", "must be in [0,1]")
        if not isinstance(snapshot.get("evidence_refs"), list) or not snapshot.get("evidence_refs"):
            _err(errors, p + ".evidence_refs", "must preserve evidence for the state hypothesis")
        else:
            for ref in snapshot["evidence_refs"]:
                if ref not in known_evidence:
                    _err(errors, p + ".evidence_refs", f"unknown observation/event evidence {ref!r}")

    # A subject entity and its time-window projections are downstream, never CCE inputs.
    # Do not silently allow the old profile-centred shape to re-enter here.
    for forbidden in ("subject_refs", "contexts"):
        if case.get(forbidden):
            _err(errors, forbidden, "is not part of the CCE measurement case; use subject-window mechanism records downstream")

    for rid, request in requests.items():
        p = f"cce_requests[{rid}]"
        _require(request, p, ("id", "measurement_mode", "measurement_adapter", "event_refs", "context_snapshot_ref", "prediction_time"), errors)
        mode = request.get("measurement_mode")
        if mode not in MEASUREMENT_MODES:
            _err(errors, p + ".measurement_mode", f"must be one of {sorted(MEASUREMENT_MODES)}")
        if request.get("prediction_time") != "pre_exposure":
            _err(errors, p + ".prediction_time", "must be 'pre_exposure'")
        forbidden_inputs = ("outcome_refs", "post_exposure_features", "subject_refs", "context_refs",
                            "baseline_ref", "profile_version", "subject_version")
        if any(request.get(field) for field in forbidden_inputs):
            _err(errors, p, "forbidden CCE inputs: subject/legacy-context/outcome/post-exposure fields")
        pre_ref = request.get("pre_state_snapshot_ref")
        if mode == "transition":
            if pre_ref not in state_snapshots:
                _err(errors, p + ".pre_state_snapshot_ref", "transition mode requires an evidence-bound state snapshot")
        elif pre_ref:
            _err(errors, p + ".pre_state_snapshot_ref", "is only valid for transition mode")
        if request.get("context_snapshot_ref") not in contexts:
            _err(errors, p + ".context_snapshot_ref", "must reference a context_snapshot")
        for ref in request.get("event_refs", []):
            if ref not in events:
                _err(errors, p + ".event_refs", f"unknown event ref {ref!r}")

    for mid, result in results.items():
        p = f"measurement_results[{mid}]"
        _require(result, p, ("id", "request_ref", "assertion", "model_version", "input_fingerprint", "confidence", "evidence_refs"), errors)
        request = requests.get(result.get("request_ref"))
        if not request:
            _err(errors, p + ".request_ref", "must reference a cce_request")
        if result.get("assertion") != "derived":
            _err(errors, p + ".assertion", "model measurement results must be assertion='derived'")
        if not isinstance(result.get("confidence"), (int, float)) or not 0 <= result["confidence"] <= 1:
            _err(errors, p + ".confidence", "must be in [0,1]")
        dist = result.get("distribution")
        if request and request.get("measurement_mode") in {"stimulus", "observed_response"}:
            if not isinstance(dist, dict) or not dist:
                _err(errors, p + ".distribution", "stimulus/observed_response results require a distribution")
            elif any(not isinstance(v, (int, float)) or v < 0 for v in dist.values()):
                _err(errors, p + ".distribution", "values must be non-negative numbers")
            elif not math.isclose(sum(dist.values()), 1.0, abs_tol=1e-6):
                _err(errors, p + ".distribution", "values must sum to 1.0")
        if request and request.get("measurement_mode") == "transition":
            transition_ref = result.get("state_transition_ref")
            if transition_ref not in transitions:
                _err(errors, p + ".state_transition_ref", "transition result must reference a valid state_transition")
        for ref in result.get("evidence_refs", []):
            if ref not in events:
                _err(errors, p + ".evidence_refs", f"must reference event ids, got {ref!r}")

    for tid, transition in transitions.items():
        p = f"state_transitions[{tid}]"
        _require(transition, p, ("id", "request_ref", "pre_state_snapshot_ref", "post_state_snapshot_ref",
                                 "delta", "evidence_refs", "confidence"), errors)
        request = requests.get(transition.get("request_ref"))
        if not request or request.get("measurement_mode") != "transition":
            _err(errors, p + ".request_ref", "must reference a transition-mode cce_request")
        pre = state_snapshots.get(transition.get("pre_state_snapshot_ref"))
        post = state_snapshots.get(transition.get("post_state_snapshot_ref"))
        if not pre:
            _err(errors, p + ".pre_state_snapshot_ref", "must resolve")
        if not post:
            _err(errors, p + ".post_state_snapshot_ref", "must resolve")
        if request and transition.get("pre_state_snapshot_ref") != request.get("pre_state_snapshot_ref"):
            _err(errors, p + ".pre_state_snapshot_ref", "must equal the request pre_state_snapshot_ref")
        if pre and post:
            if pre.get("subject_ref") != post.get("subject_ref"):
                _err(errors, p, "pre/post snapshots must describe the same subject")
            before, after, delta = pre.get("dimensions") or {}, post.get("dimensions") or {}, transition.get("delta")
            shared = set(before) & set(after)
            if not isinstance(delta, dict) or set(delta) != shared:
                _err(errors, p + ".delta", "keys must equal the pre/post shared state dimensions")
            elif any(not isinstance(delta[key], (int, float)) or
                     not math.isclose(delta[key], after[key] - before[key], abs_tol=1e-6)
                     for key in shared):
                _err(errors, p + ".delta", "must equal state_after - state_before")
        confidence = transition.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            _err(errors, p + ".confidence", "must be in [0,1]")
        for ref in transition.get("evidence_refs", []):
            if ref not in known_evidence:
                _err(errors, p + ".evidence_refs", f"unknown observation/event evidence {ref!r}")

    for oid, outcome in outcomes.items():
        p = f"outcomes[{oid}]"
        _require(outcome, p, ("id", "exposure_ref", "observed_at", "metric", "value", "provenance"), errors)
        if outcome.get("exposure_ref") not in exposures:
            _err(errors, p + ".exposure_ref", "must reference an exposure record")
        if not isinstance(outcome.get("value"), (int, float)):
            _err(errors, p + ".value", "must be numeric")

    if not observations:
        warnings.append("no observations: a context-bound CCE request cannot be evidence-complete")
    if requests and not results:
        warnings.append("no measurement_results: valid request packet, but no completed measurement")
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "counts": {"observations": len(observations), "events": len(events),
                       "context_snapshots": len(contexts), "state_snapshots": len(state_snapshots),
                       "cce_requests": len(requests), "measurement_results": len(results),
                       "state_transitions": len(transitions), "outcomes": len(outcomes)}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="CCE analysis case JSON")
    parser.add_argument("--contract", action="store_true", help="print the active contract and exit")
    args = parser.parse_args()
    if args.contract:
        print(CONTRACT.read_text(encoding="utf-8"))
        return
    try:
        case = json.loads(args.case.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid input: {exc}")
    verdict = validate_case(case)
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    raise SystemExit(0 if verdict["ok"] else 1)


if __name__ == "__main__":
    main()
