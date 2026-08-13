#!/usr/bin/env python3
"""Validate and audit the downstream CCE subject projection chain.

This module deliberately distinguishes platform distribution from people who
actually interacted.  It never manufactures a subject from aggregate metrics,
and it reports missing evidence as NOT_MET/NOT_TESTABLE rather than filling it.
Subject entities are stable; windows are time-bound analytical projections.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any


WINDOW_TYPES = {"target", "reached", "activated", "action", "conversion"}
STATUS_RANK = {"PASS": 3, "PARTIAL": 2, "NOT_MET": 1, "NOT_TESTABLE": 0}


def _has_key(value: Any, keys: set[str]) -> bool:
    if isinstance(value, dict):
        return any(key in keys for key in value) or any(_has_key(v, keys) for v in value.values())
    if isinstance(value, list):
        return any(_has_key(v, keys) for v in value)
    return False


def _index(rows: Any, key: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        errors.append(f"{key} must be a list")
        return {}
    out: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or not row.get("id"):
            errors.append(f"{key}[{i}] requires id")
            continue
        if row["id"] in out:
            errors.append(f"{key} duplicate id {row['id']!r}")
        out[row["id"]] = row
    return out


def _distribution_is_valid(value: Any) -> bool:
    return (isinstance(value, dict) and bool(value)
            and all(isinstance(v, (int, float)) and v >= 0 for v in value.values())
            and math.isclose(sum(value.values()), 1.0, abs_tol=1e-6))


def _validate_population_analysis(value: Any, members: list[str], errors: list[str], path: str) -> None:
    if not isinstance(value, dict) or value.get("kind") != "cce.population_projection.v1":
        errors.append(f"{path} requires cce.population_projection.v1")
        return
    member_distributions = value.get("member_distributions")
    if not isinstance(member_distributions, dict) or set(member_distributions) != set(members):
        errors.append(f"{path}.member_distributions must preserve every activated member")
    else:
        for member, distribution in member_distributions.items():
            if not _distribution_is_valid(distribution):
                errors.append(f"{path}.member_distributions[{member}] must sum to 1")
    composition = value.get("composition") or {}
    if composition.get("known_member_count") != len(members) or not composition.get("coverage_scope"):
        errors.append(f"{path}.composition must declare known member count and coverage")
    heterogeneity = value.get("heterogeneity") or {}
    pair_count = len(members) * (len(members) - 1) // 2
    if heterogeneity.get("metric") != "pairwise_jensen_shannon_divergence_bits" or heterogeneity.get("pair_count") != pair_count:
        errors.append(f"{path}.heterogeneity must report pairwise JS across every member pair")
    for key in ("mean", "minimum", "maximum"):
        if not isinstance(heterogeneity.get(key), (int, float)) or not 0 <= heterogeneity[key] <= 1:
            errors.append(f"{path}.heterogeneity.{key} must be in [0,1]")
    mixture = value.get("segment_mixture")
    if not isinstance(mixture, list) or not mixture:
        errors.append(f"{path}.segment_mixture must be non-empty")
    else:
        segment_members = [member for segment in mixture for member in (segment.get("member_refs") or [])]
        if sorted(segment_members) != sorted(members) or len(segment_members) != len(set(segment_members)):
            errors.append(f"{path}.segment_mixture must partition activated members exactly once")
        weights = [segment.get("weight") for segment in mixture]
        if any(not isinstance(weight, (int, float)) or weight < 0 for weight in weights) or not math.isclose(sum(weights), 1.0, abs_tol=1e-6):
            errors.append(f"{path}.segment_mixture weights must sum to 1")
        for index, segment in enumerate(mixture):
            if not segment.get("segment_id") or not _distribution_is_valid(segment.get("centroid_distribution")):
                errors.append(f"{path}.segment_mixture[{index}] requires id and valid auxiliary centroid")
            cohesion = segment.get("within_segment_mean_js")
            if not isinstance(cohesion, (int, float)) or not 0 <= cohesion <= 1:
                errors.append(f"{path}.segment_mixture[{index}].within_segment_mean_js must be in [0,1]")
    segmentation = value.get("segmentation") or {}
    if segmentation.get("status") != "descriptive_not_causal":
        errors.append(f"{path}.segmentation must declare descriptive_not_causal")


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _window_bounds(value: Any) -> tuple[datetime, datetime] | None:
    if not isinstance(value, dict):
        return None
    start, end = _instant(value.get("start")), _instant(value.get("end"))
    return (start, end) if start and end and start <= end else None


def validate_chain(bundle: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if bundle.get("kind") != "cce.subject_window_chain.v1":
        errors.append("kind must be cce.subject_window_chain.v1")
    if _has_key({"entities": bundle.get("subject_entities", []), "windows": bundle.get("subject_windows", [])},
                {"profile_version", "subject_version"}):
        errors.append("subject entities/windows must not be versioned profiles")

    evidence = _index(bundle.get("evidence_records", []), "evidence_records", errors)
    subjects = _index(bundle.get("subject_entities", []), "subject_entities", errors)
    windows = _index(bundle.get("subject_windows", []), "subject_windows", errors)
    behaviors = _index(bundle.get("behavior_records", []), "behavior_records", errors)
    commercial = _index(bundle.get("commercial_records", []), "commercial_records", errors)
    distribution = _index(bundle.get("distribution_records", []), "distribution_records", errors)
    measurements = _index(bundle.get("response_measurements", []), "response_measurements", errors)
    attribution_results = _index(bundle.get("attribution_results", []), "attribution_results", errors)
    content_id = (bundle.get("content") or {}).get("id")

    for eid, row in evidence.items():
        if row.get("content_ref") != content_id:
            errors.append(f"evidence_records[{eid}].content_ref must match chain content id")
        if not _instant(row.get("observed_at")):
            errors.append(f"evidence_records[{eid}].observed_at must be ISO-8601")
    for did, row in distribution.items():
        if row.get("content_ref") != content_id:
            errors.append(f"distribution_records[{did}].content_ref must match chain content id")
        if not _instant(row.get("observed_at")):
            errors.append(f"distribution_records[{did}].observed_at must be ISO-8601")

    for sid, subject in subjects.items():
        p = f"subject_entities[{sid}]"
        if subject.get("subject_id") != sid:
            errors.append(f"{p}.subject_id must equal id")
        if not isinstance(subject.get("core"), dict):
            errors.append(f"{p} requires stable core object")
        identities = subject.get("identity_evidence")
        if not isinstance(identities, list):
            errors.append(f"{p}.identity_evidence must be an append-only list")
        states = subject.get("state_observations")
        if not isinstance(states, list):
            errors.append(f"{p}.state_observations must be a list")
        for i, state in enumerate(states or []):
            if not isinstance(state, dict) or not state.get("observed_at") or not state.get("evidence_refs"):
                errors.append(f"{p}.state_observations[{i}] requires observed_at and evidence_refs")
            elif state.get("assertion") not in {"observed", "inferred", "derived", "unknown"}:
                errors.append(f"{p}.state_observations[{i}] requires an epistemic assertion")

    by_type: dict[str, list[dict[str, Any]]] = {kind: [] for kind in WINDOW_TYPES}
    for wid, window in windows.items():
        kind = window.get("window_type")
        if kind not in WINDOW_TYPES:
            errors.append(f"subject_windows[{wid}].window_type invalid")
            continue
        by_type[kind].append(window)
        for field in ("time_window", "population_set", "evidence_refs"):
            if not window.get(field): errors.append(f"subject_windows[{wid}] missing {field}")
        bounds = _window_bounds(window.get("time_window"))
        if not bounds:
            errors.append(f"subject_windows[{wid}].time_window must be ordered ISO-8601 instants")
        for ref in window.get("evidence_refs") or []:
            if ref not in evidence:
                errors.append(f"subject_windows[{wid}].evidence_refs contains unknown evidence {ref!r}")
        pop = window.get("population_set") or {}
        if kind == "reached":
            if pop.get("kind") in {"aggregate_metric", "platform_exposure"}:
                errors.append(f"subject_windows[{wid}] distribution metrics cannot define a reached subject")
            members = pop.get("member_refs") or []
            if not members:
                errors.append(f"subject_windows[{wid}] reached window requires observed member_refs")
            member_evidence = window.get("member_evidence") or {}
            for member in members:
                refs = member_evidence.get(member) or []
                if not refs or any(ref not in evidence for ref in refs):
                    errors.append(f"subject_windows[{wid}] member {member!r} lacks valid interaction evidence")
                for ref in refs:
                    if ref in evidence and evidence[ref].get("actor_ref") != member:
                        errors.append(f"subject_windows[{wid}] member {member!r} evidence actor does not match")
                    observed = _instant(evidence.get(ref, {}).get("observed_at"))
                    if bounds and observed and not bounds[0] <= observed <= bounds[1]:
                        errors.append(f"subject_windows[{wid}] member {member!r} evidence falls outside time_window")
            coverage = pop.get("coverage")
            if not isinstance(coverage, dict) or coverage.get("scope") != "identified_inbound_only":
                errors.append(f"subject_windows[{wid}] must declare identified_inbound_only observability coverage")
        if kind == "activated":
            refs = window.get("measurement_result_refs") or []
            if not refs or any(ref not in measurements for ref in refs):
                errors.append(f"subject_windows[{wid}] activated window requires response measurements")
            if "aggregate_distribution" in window or "aggregate_layer_distributions" in window:
                errors.append(f"subject_windows[{wid}] arithmetic-mean population fields are forbidden")
            members = (window.get("population_set") or {}).get("member_refs") or []
            _validate_population_analysis(window.get("population_analysis"), members, errors,
                                          f"subject_windows[{wid}].population_analysis")
        if kind == "action":
            refs = window.get("behavior_record_refs") or []
            if not refs or any(ref not in behaviors for ref in refs):
                errors.append(f"subject_windows[{wid}] action window requires behavior records")
            for ref in refs:
                if ref in behaviors and behaviors[ref].get("observation_scope") != "post_exposure_observed_action":
                    errors.append(f"subject_windows[{wid}] behavior {ref!r} is not an observed post-exposure action")
        if kind == "conversion":
            refs = window.get("commercial_record_refs") or []
            if not refs or any(ref not in commercial for ref in refs):
                errors.append(f"subject_windows[{wid}] conversion window requires commercial records")
            for ref in refs:
                if ref in commercial and (not commercial[ref].get("publish_id") or not commercial[ref].get("join_evidence_refs")):
                    errors.append(f"subject_windows[{wid}] commercial record {ref!r} lacks publish join evidence")

    reached_members = {
        member for window in by_type["reached"]
        for member in ((window.get("population_set") or {}).get("member_refs") or [])
    }
    for mid, row in measurements.items():
        p = f"response_measurements[{mid}]"
        for field in ("actor_ref", "response_evidence_refs", "assertion", "model_version", "input_fingerprint", "distribution", "confidence"):
            if row.get(field) in (None, "", []):
                errors.append(f"{p} missing {field}")
        if row.get("actor_ref") not in reached_members:
            errors.append(f"{p}.actor_ref must belong to an observed reached window")
        if row.get("assertion") != "derived":
            errors.append(f"{p}.assertion must be derived; response text is observed evidence, not observed psychology")
        refs = row.get("response_evidence_refs") or []
        if any(ref not in evidence for ref in refs):
            errors.append(f"{p}.response_evidence_refs contains unknown evidence")
        if not _distribution_is_valid(row.get("distribution")):
            errors.append(f"{p}.distribution must be non-negative and sum to 1")
        confidence = row.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append(f"{p}.confidence must be in [0,1]")

    for bid, row in behaviors.items():
        if row.get("observation_scope") != "post_exposure_observed_action":
            warnings.append(f"behavior_records[{bid}] is contextual evidence, not action-window evidence")
        else:
            for field in ("actor_ref", "occurred_at", "evidence_ref", "publish_id"):
                if not row.get(field):
                    errors.append(f"behavior_records[{bid}] missing {field}")
            if row.get("evidence_ref") not in evidence:
                errors.append(f"behavior_records[{bid}].evidence_ref must reference observed evidence")
            if not _instant(row.get("occurred_at")):
                errors.append(f"behavior_records[{bid}].occurred_at must be ISO-8601")
    for cid, row in commercial.items():
        for field in ("actor_ref", "observed_at", "publish_id", "join_evidence_refs"):
            if not row.get(field):
                errors.append(f"commercial_records[{cid}] missing {field}")
        if not _instant(row.get("observed_at")):
            errors.append(f"commercial_records[{cid}].observed_at must be ISO-8601")

    activated_members = {
        member for window in by_type["activated"]
        for member in ((window.get("population_set") or {}).get("member_refs") or [])
    }
    measured_actors = {row.get("actor_ref") for row in measurements.values()}
    if activated_members and activated_members != measured_actors:
        errors.append("activated window member_refs must equal response measurement actors")
    action_members = {
        member for window in by_type["action"]
        for member in ((window.get("population_set") or {}).get("member_refs") or [])
    }
    action_actors = {row.get("actor_ref") for row in behaviors.values()
                     if row.get("observation_scope") == "post_exposure_observed_action"}
    if action_members and action_members != action_actors:
        errors.append("action window member_refs must equal observed post-exposure action actors")
    conversion_members = {
        member for window in by_type["conversion"]
        for member in ((window.get("population_set") or {}).get("member_refs") or [])
    }
    conversion_actors = {row.get("actor_ref") for row in commercial.values()}
    if conversion_members and conversion_members != conversion_actors:
        errors.append("conversion window member_refs must equal joined commercial actors")

    for i, protocol in enumerate(bundle.get("attribution_protocols", [])):
        if not isinstance(protocol, dict):
            errors.append(f"attribution_protocols[{i}] must be an object")
            continue
        ref = protocol.get("result_ref")
        if ref and ref not in attribution_results:
            errors.append(f"attribution_protocols[{i}].result_ref must reference attribution_results")

    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "counts": {"evidence": len(evidence), "subjects": len(subjects), "windows": len(windows), "distribution": len(distribution),
                       "response_measurements": len(measurements), "behavior": len(behaviors), "commercial": len(commercial),
                       "attribution_results": len(attribution_results)}}


def _gate(status: str, reason: str, evidence_refs: list[str] | None = None) -> dict[str, Any]:
    return {"status": status, "reason": reason, "evidence_refs": evidence_refs or []}


def audit_chain(bundle: dict[str, Any]) -> dict[str, Any]:
    validation = validate_chain(bundle)
    windows = bundle.get("subject_windows", [])
    by_type = {kind: [w for w in windows if w.get("window_type") == kind] for kind in WINDOW_TYPES}
    measurement = bundle.get("content_measurement") or {}
    distribution = bundle.get("distribution_records", [])
    response_measurements = bundle.get("response_measurements", [])
    behaviors = [r for r in bundle.get("behavior_records", []) if r.get("observation_scope") == "post_exposure_observed_action"]
    commercial = [r for r in bundle.get("commercial_records", []) if r.get("publish_id") and r.get("join_evidence_refs")]

    gates: dict[str, dict[str, Any]] = {}
    if measurement.get("status") == "completed_validated" and measurement.get("result_refs"):
        gates["content_measurement"] = _gate("PASS", "validated content measurement exists", measurement["result_refs"])
    elif measurement.get("status") == "legacy_only":
        gates["content_measurement"] = _gate("PARTIAL", "legacy content readout exists but is not a validated response measurement", measurement.get("result_refs"))
    else:
        gates["content_measurement"] = _gate("NOT_MET", "no validated CCE content measurement result")

    if distribution:
        complete = any(r.get("window_complete") is True for r in distribution)
        refs = [r["id"] for r in distribution if r.get("id")]
        gates["distribution_observed"] = _gate("PASS" if complete else "PARTIAL",
                                                "platform delivery observed" if complete else "platform delivery partially observed; final window missing", refs)
    else:
        gates["distribution_observed"] = _gate("NOT_MET", "no platform delivery record")
    gates["target_window"] = _gate("PASS", "target window declared", [w["id"] for w in by_type["target"]]) if by_type["target"] else _gate("NOT_MET", "no target population rule/window")
    gates["reached_window"] = _gate("PASS", "identified inbound interactors form an observed reached window", [w["id"] for w in by_type["reached"]]) if by_type["reached"] else _gate("NOT_MET", "no identified inbound-interactor window")
    measurement_ids = {row.get("id") for row in response_measurements}
    valid_activation = [w for w in by_type["activated"] if w.get("measurement_result_refs") and all(ref in measurement_ids for ref in w["measurement_result_refs"])]
    behavior_ids = {row.get("id") for row in behaviors}
    valid_action = [w for w in by_type["action"] if w.get("behavior_record_refs") and all(ref in behavior_ids for ref in w["behavior_record_refs"])]
    commercial_ids = {row.get("id") for row in commercial}
    valid_conversion = [w for w in by_type["conversion"] if w.get("commercial_record_refs") and all(ref in commercial_ids for ref in w["commercial_record_refs"])]
    gates["activated_window"] = _gate("PASS", "member response measurements aggregated", [w["id"] for w in valid_activation]) if valid_activation else _gate("NOT_MET", "no CCE measurements of reached members' responses")
    gates["action_window"] = _gate("PASS", "post-exposure actions observed", [w["id"] for w in valid_action]) if valid_action else _gate("NOT_MET", "no attributable post-exposure action window")
    gates["conversion_window"] = _gate("PASS", "commercial outcomes joined to publish_id", [w["id"] for w in valid_conversion]) if valid_conversion else _gate("NOT_MET", "no publish-to-commercial joined outcome")

    pairs = [("target_to_reached", "target_window", "reached_window"),
             ("reached_to_activated", "reached_window", "activated_window"),
             ("activated_to_action", "activated_window", "action_window"),
             ("action_to_conversion", "action_window", "conversion_window")]
    protocols = {row.get("delta"): row for row in bundle.get("attribution_protocols", []) if isinstance(row, dict)}
    deltas = {}
    for name, left, right in pairs:
        protocol = protocols.get(name) or {}
        protocol_ready = all(protocol.get(field) for field in ("frozen_at", "comparison_space", "metric", "result_ref"))
        if gates[left]["status"] == gates[right]["status"] == "PASS" and protocol_ready:
            deltas[name] = _gate("PASS", "adjacent windows and frozen comparison result are present", [protocol["result_ref"]])
        else:
            missing = []
            if gates[left]["status"] != "PASS": missing.append(left)
            if gates[right]["status"] != "PASS": missing.append(right)
            if not protocol_ready: missing.append("frozen comparable attribution protocol/result")
            deltas[name] = _gate("NOT_TESTABLE", "requires " + ", ".join(missing))
    required = ["content_measurement", "distribution_observed", "target_window", "reached_window", "activated_window", "action_window", "conversion_window"]
    overall = "VERIFIED" if validation["ok"] and all(gates[k]["status"] == "PASS" for k in required) and all(row["status"] == "PASS" for row in deltas.values()) else "NOT_VERIFIED"
    return {"kind": "cce.subject_window_chain_audit.v1", "overall_status": overall,
            "validation": validation, "gates": gates, "attribution_deltas": deltas}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    report = audit_chain(bundle)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    raise SystemExit(0 if report["validation"]["ok"] else 1)


if __name__ == "__main__": main()
