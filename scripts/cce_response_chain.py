#!/usr/bin/env python3
"""Prepare and ingest CCE measurements for observed inbound responses.

The GitHub workflow may measure arbitrary reply drafts, so artifact names are
not trusted.  Ingestion joins exclusively on the exact input SHA-1 stored by
the remote manifest, then maps the author's measured state to a stable subject
entity and an activated subject-window projection.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from cce_window_chain import audit_chain, validate_chain
from cce_platform_adapter import validate_platform_context
from exp_v4_causal_chain import ACTIONS, EMOTIONS
from exp_v4_full_validation import DESIRES, NEED_KEYS


LAYER_LABELS = {
    "desire": ("desire_vec", DESIRES),
    "need": ("need_vec", NEED_KEYS),
    "emotion": ("emotion_vec", EMOTIONS),
    "action": ("action_vec", ACTIONS),
}


def input_sha1(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def _index(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value or value in out:
            raise ValueError(f"{key} must be present and unique")
        out[value] = row
    return out


def validate_response_source(source: dict[str, Any], chain: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if source.get("kind") != "cce.response_source.v1":
        errors.append("kind must be cce.response_source.v1")
    context = source.get("context")
    if not isinstance(context, dict) or any(not context.get(field) for field in (
            "platform", "platform_adapter", "surface", "domain", "summary")):
        errors.append("response source requires context.platform/platform_adapter/surface/domain/summary")
    else:
        platform_verdict = validate_platform_context(
            context.get("platform"), context.get("platform_adapter"), context.get("surface"),
            "response_source.context")
        errors.extend(platform_verdict["errors"])
    content_ref = source.get("content_ref")
    if content_ref != (chain.get("content") or {}).get("id"):
        errors.append("response source content_ref must match chain content id")
    evidence = {row.get("id"): row for row in chain.get("evidence_records", []) if isinstance(row, dict)}
    reached = [row for row in chain.get("subject_windows", []) if row.get("window_type") == "reached"]
    reached_members = {
        member for window in reached
        for member in ((window.get("population_set") or {}).get("member_refs") or [])
    }
    responses = source.get("responses")
    if not isinstance(responses, list) or not responses:
        errors.append("responses must be a non-empty list")
        responses = []
    seen_evidence: set[str] = set()
    seen_actors: set[str] = set()
    for i, row in enumerate(responses):
        p = f"responses[{i}]"
        if not isinstance(row, dict):
            errors.append(f"{p} must be an object")
            continue
        for field in ("evidence_ref", "actor_ref", "observed_at", "text", "source"):
            if not row.get(field):
                errors.append(f"{p} missing {field}")
        evidence_ref, actor_ref = row.get("evidence_ref"), row.get("actor_ref")
        if evidence_ref in seen_evidence:
            errors.append(f"{p}.evidence_ref is duplicated")
        if actor_ref in seen_actors:
            errors.append(f"{p}.actor_ref is duplicated; aggregate multiple responses before this contract")
        seen_evidence.add(evidence_ref)
        seen_actors.add(actor_ref)
        fact = evidence.get(evidence_ref)
        if not fact:
            errors.append(f"{p}.evidence_ref does not resolve")
        elif (fact.get("actor_ref"), fact.get("observed_at"), fact.get("source")) != (
                actor_ref, row.get("observed_at"), row.get("source")):
            errors.append(f"{p} does not match the observed chain evidence")
    if reached_members != seen_actors:
        errors.append("response actors must exactly cover the observed reached-window members")
    return {"ok": not errors, "errors": errors, "counts": {"responses": len(responses), "reached_members": len(reached_members)}}


def build_dispatch(source: dict[str, Any], chain: dict[str, Any]) -> dict[str, Any]:
    verdict = validate_response_source(source, chain)
    if not verdict["ok"]:
        raise ValueError("invalid response source: " + "; ".join(verdict["errors"]))
    items = []
    context = source["context"]
    platform_context = validate_platform_context(
        context["platform"], context["platform_adapter"], context["surface"],
        "response_source.context")["canonical"]
    space = platform_context["space"]
    for row in source["responses"]:
        comment_id = row["evidence_ref"].split(":", 1)[-1]
        items.append({
            "mode": "response",
            "text": row["text"],
            "context": f"{context['platform']} {space['kind']} {space['id']} {context['domain']} "
                       f"inbound response to {source['content_ref']}: {context['summary']}",
            "ref_tag": f"post6-inbound-{comment_id}",
        })
    return {
        "event_type": "cce-batch",
        "client_payload": {"items": items},
        "verification": {
            "join": "manifest.text_sha1 == sha1(exact inbound text)",
            "expected_input_sha1": [input_sha1(row["text"]) for row in source["responses"]],
        },
    }


def _artifact_index(root: Path) -> dict[str, tuple[dict[str, Any], dict[str, Any], Path]]:
    out: dict[str, tuple[dict[str, Any], dict[str, Any], Path]] = {}
    for manifest_path in root.rglob("manifest.json"):
        readout_path = manifest_path.with_name("s1_readout.json")
        if not readout_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        readout = json.loads(readout_path.read_text(encoding="utf-8"))
        digest = manifest.get("text_sha1")
        if not isinstance(digest, str) or not digest:
            continue
        if digest in out:
            raise ValueError(f"duplicate artifact input fingerprint {digest}")
        out[digest] = (manifest, readout, manifest_path.parent)
    return out


def _measurement(row: dict[str, Any], artifact: tuple[dict[str, Any], dict[str, Any], Path]) -> dict[str, Any]:
    manifest, readout, artifact_dir = artifact
    expected_sha1 = input_sha1(row["text"])
    if manifest.get("text_sha1") != expected_sha1 or readout.get("input_sha") != hashlib.sha256(row["text"].encode()).hexdigest()[:16]:
        raise ValueError(f"artifact fingerprint mismatch for {row['evidence_ref']}")
    if (manifest.get("stages") or {}).get("s1_readout", {}).get("status") != "OK":
        raise ValueError(f"remote CCE s1 failed for {row['evidence_ref']}")
    stage1 = readout.get("stage1") or {}
    vectors = stage1.get("layers") or {}
    layer_distributions: dict[str, dict[str, float]] = {}
    flattened: dict[str, float] = {}
    for layer, (vector_key, labels) in LAYER_LABELS.items():
        vector = vectors.get(vector_key)
        if not isinstance(vector, list) or len(vector) != len(labels):
            raise ValueError(f"{row['evidence_ref']} invalid {vector_key}")
        if any(not isinstance(value, (int, float)) or value < 0 for value in vector):
            raise ValueError(f"{row['evidence_ref']} invalid values in {vector_key}")
        total = sum(vector)
        if total <= 0:
            raise ValueError(f"{row['evidence_ref']} empty {vector_key}")
        layer_distributions[layer] = {label: value / total for label, value in zip(labels, vector)}
        flattened.update({f"{layer}:{label}": value / total / len(LAYER_LABELS) for label, value in zip(labels, vector)})
    flat_total = sum(flattened.values())
    flattened = {key: value / flat_total for key, value in flattened.items()}
    within = [value for value in (stage1.get("within_js") or {}).values() if isinstance(value, (int, float))]
    repeatability = max(0.0, min(1.0, 1.0 - sum(within) / len(within))) if within else 0.0
    comment_id = row["evidence_ref"].split(":", 1)[-1]
    return {
        "id": f"response_measurement:{comment_id}",
        "actor_ref": row["actor_ref"],
        "response_evidence_refs": [row["evidence_ref"]],
        "observed_at": row["observed_at"],
        "measurement_scope": "observed_response_author_state",
        "model_version": (readout.get("instrument") or {}).get("stage1", "unknown"),
        "input_fingerprint": f"sha1:{expected_sha1}",
        "distribution": flattened,
        "layer_distributions": layer_distributions,
        "confidence": repeatability,
        "confidence_semantics": "within-run repeatability; not probability of truth or causal attribution",
        "provenance": {
            "artifact": artifact_dir.name,
            "run_started": manifest.get("started"),
            "s1_measurement_complete": True,
            "response_chain_complete": bool(manifest.get("complete")),
            "response_chain_failed_at": manifest.get("failed_at"),
            "response_scope_note": "response mode runs s0-s3; only exact s1 distributions enter the activated-state aggregation",
            "instrument": readout.get("instrument"),
            "k_requested": stage1.get("k_requested"),
            "k_ok": stage1.get("k_ok"),
        },
    }


def _mean_distribution(measurements: list[dict[str, Any]]) -> dict[str, float]:
    keys = set().union(*(row["distribution"] for row in measurements))
    return {key: sum(row["distribution"].get(key, 0.0) for row in measurements) / len(measurements) for key in sorted(keys)}


def _mean_layer_distributions(measurements: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Preserve the four CCE probability spaces instead of only flattening them."""
    out: dict[str, dict[str, float]] = {}
    for layer in LAYER_LABELS:
        keys = set().union(*(row["layer_distributions"][layer] for row in measurements))
        values = {
            key: sum(row["layer_distributions"][layer].get(key, 0.0) for row in measurements) / len(measurements)
            for key in sorted(keys)
        }
        total = sum(values.values())
        out[layer] = {key: value / total for key, value in values.items()}
    return out


def ingest(source: dict[str, Any], chain: dict[str, Any], artifacts_dir: Path) -> dict[str, Any]:
    verdict = validate_response_source(source, chain)
    if not verdict["ok"]:
        raise ValueError("invalid response source: " + "; ".join(verdict["errors"]))
    artifacts = _artifact_index(artifacts_dir)
    measurements = []
    for row in source["responses"]:
        digest = input_sha1(row["text"])
        if digest not in artifacts:
            raise ValueError(f"missing exact-input CCE artifact for {row['evidence_ref']} ({digest})")
        measurements.append(_measurement(row, artifacts[digest]))

    out = copy.deepcopy(chain)
    existing_measurements = _index(out.get("response_measurements", []), "id") if out.get("response_measurements") else {}
    for row in measurements:
        if row["id"] in existing_measurements and existing_measurements[row["id"]] != row:
            raise ValueError(f"conflicting existing response measurement {row['id']}")
        existing_measurements[row["id"]] = row
    out["response_measurements"] = list(existing_measurements.values())

    reached = next((row for row in out.get("subject_windows", []) if row.get("window_type") == "reached"), None)
    if not reached:
        raise ValueError("reached window is required before activation")
    activated_id = reached["id"].replace(":reached:", ":activated:")
    activated = {
        "id": activated_id,
        "window_type": "activated",
        "time_window": copy.deepcopy(reached["time_window"]),
        "population_set": {
            "kind": "observed_response_authors",
            "member_refs": [row["actor_ref"] for row in measurements],
            "n": len(measurements),
        },
        "evidence_refs": [row["response_evidence_refs"][0] for row in measurements],
        "measurement_result_refs": [row["id"] for row in measurements],
        "aggregate_distribution": _mean_distribution(measurements),
        "aggregate_layer_distributions": _mean_layer_distributions(measurements),
        "aggregation": "unweighted mean across exact observed inbound responses",
    }
    windows = [row for row in out.get("subject_windows", []) if row.get("window_type") != "activated"]
    windows.append(activated)
    out["subject_windows"] = windows

    subjects = _index(out.get("subject_entities", []), "id") if out.get("subject_entities") else {}
    platform = source["context"]["platform"]
    for source_row, measurement in zip(source["responses"], measurements):
        subject = subjects.setdefault(source_row["actor_ref"], {
            "id": source_row["actor_ref"],
            "subject_id": source_row["actor_ref"],
            "core": {"status": "unknown", "reason": "single response cannot establish a stable desire baseline"},
            "identity_evidence": [],
            "state_observations": [],
        })
        identity = {
            "label": f"{platform}_actor_ref", "value": source_row["actor_ref"],
            "first_seen": source_row["observed_at"], "last_seen": source_row["observed_at"],
            "evidence_refs": [source_row["evidence_ref"]],
        }
        if identity not in subject["identity_evidence"]:
            subject["identity_evidence"].append(identity)
        state = {
            "observed_at": source_row["observed_at"], "window_ref": activated_id,
            "measurement_result_ref": measurement["id"], "evidence_refs": [source_row["evidence_ref"]],
        }
        if state not in subject["state_observations"]:
            subject["state_observations"].append(state)
    out["subject_entities"] = list(subjects.values())

    final = validate_chain(out)
    if not final["ok"]:
        raise ValueError("ingested chain violates contract: " + "; ".join(final["errors"]))
    return out


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--responses", required=True, type=Path)
    prepare.add_argument("--chain", required=True, type=Path)
    prepare.add_argument("--out", required=True, type=Path)
    import_cmd = sub.add_parser("ingest")
    import_cmd.add_argument("--responses", required=True, type=Path)
    import_cmd.add_argument("--chain", required=True, type=Path)
    import_cmd.add_argument("--artifacts-dir", required=True, type=Path)
    import_cmd.add_argument("--out", required=True, type=Path)
    import_cmd.add_argument("--audit-out", type=Path)
    args = parser.parse_args()
    source = json.loads(args.responses.read_text(encoding="utf-8"))
    chain = json.loads(args.chain.read_text(encoding="utf-8"))
    if args.command == "prepare":
        value = build_dispatch(source, chain)
        _write(args.out, value)
        print(json.dumps({"out": str(args.out), "items": len(value["client_payload"]["items"])}, ensure_ascii=False))
        return
    value = ingest(source, chain, args.artifacts_dir)
    report = audit_chain(value)
    _write(args.out, value)
    if args.audit_out:
        _write(args.audit_out, report)
    print(json.dumps({"out": str(args.out), "audit_out": str(args.audit_out) if args.audit_out else None,
                      "response_measurements": len(value["response_measurements"]),
                      "activated_gate": report["gates"]["activated_window"]["status"],
                      "overall_status": report["overall_status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
