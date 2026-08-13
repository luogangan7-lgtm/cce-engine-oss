#!/usr/bin/env python3
"""Synthesize an evidence-bound Population Subject without inventing an average person.

A population is represented as a weighted mixture of observed member distributions.
The mixture marginal is a legitimate population summary, but it is explicitly not an
individual profile. Descriptive segment candidates require more than one supporting member; isolated
members remain unassigned instead of being mislabeled as one-person segments.
"""
from __future__ import annotations

import hashlib
import math
from itertools import combinations
from typing import Any


SEGMENT_JS_THRESHOLD = 0.08
MIN_SEGMENT_SIZE = 2


def _js(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    midpoint = {key: (left.get(key, 0.0) + right.get(key, 0.0)) / 2 for key in keys}

    def kl(row: dict[str, float]) -> float:
        return sum(value * math.log2(value / midpoint[key])
                   for key, value in row.items() if value > 0 and midpoint[key] > 0)

    return (kl(left) + kl(right)) / 2


def _validate_distribution(value: Any, name: str) -> dict[str, float]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{name} must be a non-empty distribution")
    if any(not isinstance(item, (int, float)) or item < 0 for item in value.values()):
        raise ValueError(f"{name} values must be non-negative numbers")
    total = sum(value.values())
    if not math.isclose(total, 1.0, abs_tol=1e-6):
        raise ValueError(f"{name} must sum to 1")
    return {str(key): float(item) for key, item in value.items()}


def _normalise_weights(members: list[str], measurements: list[dict[str, Any]],
                       supplied: dict[str, float] | None) -> tuple[dict[str, float], str]:
    raw = supplied or {
        row["actor_ref"]: row.get("population_weight")
        for row in measurements if row.get("population_weight") is not None
    }
    if raw:
        if set(raw) != set(members):
            raise ValueError("population weights must cover every member exactly once")
        if any(not isinstance(value, (int, float)) or value <= 0 for value in raw.values()):
            raise ValueError("population weights must be positive numbers")
        total = sum(raw.values())
        return ({member: raw[member] / total for member in members},
                "provided_member_weights_unverified")
    weight = 1.0 / len(members)
    return {member: weight for member in members}, "equal_member_within_observed_sample"


def _weighted_centroid(member_refs: list[str], distributions: dict[str, dict[str, float]],
                       weights: dict[str, float]) -> dict[str, float]:
    keys = sorted(set().union(*(distributions[member] for member in member_refs)))
    denominator = sum(weights[member] for member in member_refs)
    return {
        key: sum(distributions[member].get(key, 0.0) * weights[member]
                 for member in member_refs) / denominator
        for key in keys
    }


def _weighted_quantile(values: list[tuple[float, float]], quantile: float) -> float:
    ordered = sorted(values)
    total = sum(weight for _, weight in ordered)
    threshold = quantile * total
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def _distribution_summary(distributions: dict[str, dict[str, float]],
                          weights: dict[str, float]) -> dict[str, Any]:
    members = sorted(distributions)
    keys = sorted(set().union(*distributions.values()))
    return {
        "marginal_distribution": _weighted_centroid(members, distributions, weights),
        "marginal_semantics": "weighted population marginal; never an individual persona",
        "component_quantiles": {
            key: {
                "p25": _weighted_quantile([(distributions[m].get(key, 0.0), weights[m]) for m in members], 0.25),
                "median": _weighted_quantile([(distributions[m].get(key, 0.0), weights[m]) for m in members], 0.50),
                "p75": _weighted_quantile([(distributions[m].get(key, 0.0), weights[m]) for m in members], 0.75),
            }
            for key in keys
        },
    }


def _components(member_distributions: dict[str, dict[str, float]], threshold: float) -> list[list[str]]:
    remaining = set(member_distributions)
    groups: list[list[str]] = []
    while remaining:
        root = min(remaining)
        remaining.remove(root)
        group = {root}
        frontier = [root]
        while frontier:
            current = frontier.pop()
            neighbors = {candidate for candidate in remaining
                         if _js(member_distributions[current], member_distributions[candidate]) <= threshold}
            remaining -= neighbors
            group |= neighbors
            frontier.extend(neighbors)
        groups.append(sorted(group))
    return sorted(groups, key=lambda row: (-len(row), row))


def build_population_subject(measurements: list[dict[str, Any]], coverage_scope: str,
                             threshold: float = SEGMENT_JS_THRESHOLD, *,
                             weights: dict[str, float] | None = None,
                             min_segment_size: int = MIN_SEGMENT_SIZE,
                             stage: str = "activated", exhaustive: bool = False,
                             time_window: dict[str, str] | None = None,
                             evidence_refs: list[str] | None = None) -> dict[str, Any]:
    if not measurements:
        raise ValueError("population synthesis requires at least one member measurement")
    if min_segment_size < 2:
        raise ValueError("a descriptive segment candidate requires at least two members")
    members = {
        row["actor_ref"]: _validate_distribution(row["distribution"], f"measurement[{row['actor_ref']}]")
        for row in measurements
    }
    if len(members) != len(measurements):
        raise ValueError("population synthesis requires one measurement per unique member")
    member_refs = sorted(members)
    member_weights, weighting_method = _normalise_weights(member_refs, measurements, weights)
    pairwise = [_js(members[left], members[right]) for left, right in combinations(member_refs, 2)]

    segments: list[dict[str, Any]] = []
    unassigned: list[str] = []
    for group in _components(members, threshold):
        if len(group) < min_segment_size:
            unassigned.extend(group)
            continue
        internal = [_js(members[left], members[right]) for left, right in combinations(group, 2)]
        digest = hashlib.sha256("\n".join(group).encode()).hexdigest()[:10]
        segments.append({
            "segment_id": f"dynamic-response:{digest}",
            "segment_basis": "shared_stimulus_response_similarity",
            "member_refs": group,
            "weight": sum(member_weights[member] for member in group),
            "centroid_distribution": _weighted_centroid(group, members, member_weights),
            "within_segment_mean_js": sum(internal) / len(internal),
            "assertion": "derived",
        })

    window_identity = "" if time_window is None else f"{time_window.get('start', '')}/{time_window.get('end', '')}"
    unique_evidence_refs = sorted(set(evidence_refs or []))
    identity_material = "\n".join([
        stage,
        coverage_scope,
        window_identity,
        *member_refs,
        *unique_evidence_refs,
    ])
    population_id = "population:" + hashlib.sha256(identity_material.encode()).hexdigest()[:16]
    unassigned = sorted(unassigned)
    inference_level = "enumerated_population" if exhaustive else "descriptive_nonprobability_sample"
    segmentation_status = "descriptive_not_causal" if segments else "insufficient_support"
    return {
        "kind": "cce.population_subject.v1",
        "population_id": population_id,
        "scale": "population",
        "stage": stage,
        "time_window": time_window or {"status": "not_supplied"},
        "evidence_refs": unique_evidence_refs,
        "provenance": {"producer": "cce_population", "version": "1.0.0", "assertion": "derived"},
        "definition": {
            "unit": "identified_subject",
            "coverage_scope": coverage_scope,
            "estimand": "distribution of CCE response states in the declared coverage scope",
            "inference_level": inference_level,
        },
        "sampling": {
            "frame": coverage_scope,
            "method": "enumeration" if exhaustive else "nonprobability_observed_sample",
            "weighting_method": weighting_method,
            "representative_of_broader_population": False if not exhaustive else True,
            "assumptions": [] if exhaustive else [
                "only observed members are represented",
                "no inference to silent or unobserved people without an external sampling frame",
            ],
        },
        "member_distributions": members,
        "member_weights": member_weights,
        "population_mixture": {
            "kind": "weighted_empirical_mixture",
            "components": [
                {"member_ref": member, "weight": member_weights[member],
                 "distribution_ref": f"member_distributions.{member}"}
                for member in member_refs
            ],
            **_distribution_summary(members, member_weights),
        },
        "composition": {
            "known_member_count": len(members),
            "coverage_scope": coverage_scope,
            "exhaustive": exhaustive,
        },
        "heterogeneity": {
            "metric": "pairwise_jensen_shannon_divergence_bits",
            "pair_count": len(pairwise),
            "mean": sum(pairwise) / len(pairwise) if pairwise else 0.0,
            "minimum": min(pairwise) if pairwise else 0.0,
            "maximum": max(pairwise) if pairwise else 0.0,
        },
        "segment_mixture": segments,
        "unassigned_member_refs": unassigned,
        "unassigned_weight": sum(member_weights[member] for member in unassigned),
        "segmentation": {
            "method": "response_similarity_connected_components",
            "js_threshold": threshold,
            "min_segment_size": min_segment_size,
            "status": segmentation_status,
            "inference_scope": "descriptive_not_causal",
            "warning": "singletons are unassigned evidence components, not one-person segments",
        },
        "uncertainty": {
            "status": "not_estimated",
            "reason": "no probability sampling frame or repeated-window resampling protocol supplied",
        },
    }


def build_population_analysis(measurements: list[dict[str, Any]], coverage_scope: str,
                              threshold: float = SEGMENT_JS_THRESHOLD, **kwargs: Any) -> dict[str, Any]:
    """Backward-compatible function name; the returned object is a Population Subject."""
    return build_population_subject(measurements, coverage_scope, threshold, **kwargs)


def compare_population_projections(previous_window_ref: str, previous: dict[str, Any],
                                   current_window_ref: str, current: dict[str, Any]) -> dict[str, Any]:
    """Describe stable-segment continuity without claiming causal population change."""
    old = {row["segment_id"]: set(row["member_refs"]) for row in previous.get("segment_mixture", [])}
    new = {row["segment_id"]: set(row["member_refs"]) for row in current.get("segment_mixture", [])}
    events: list[dict[str, Any]] = []
    for old_id, old_members in old.items():
        successors = [new_id for new_id, new_members in new.items() if old_members & new_members]
        if not successors:
            events.append({"event": "disappear", "from": [old_id], "to": []})
        elif len(successors) > 1:
            events.append({"event": "split", "from": [old_id], "to": sorted(successors)})
        else:
            events.append({"event": "continue", "from": [old_id], "to": successors})
    for new_id, new_members in new.items():
        predecessors = [old_id for old_id, old_members in old.items() if new_members & old_members]
        if not predecessors:
            events.append({"event": "create", "from": [], "to": [new_id]})
        elif len(predecessors) > 1:
            events.append({"event": "merge", "from": sorted(predecessors), "to": [new_id]})
    return {
        "kind": "cce.population_evolution.v1",
        "previous_window_ref": previous_window_ref,
        "current_window_ref": current_window_ref,
        "events": events,
        "status": "descriptive_not_causal",
        "comparability": {
            "shared_members": len(set(previous.get("member_distributions", {})) & set(current.get("member_distributions", {}))),
            "previous_unassigned": len(previous.get("unassigned_member_refs", [])),
            "current_unassigned": len(current.get("unassigned_member_refs", [])),
            "warning": "membership or response changes alone do not establish a causal population transition",
        },
    }
