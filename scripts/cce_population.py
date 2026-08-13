#!/usr/bin/env python3
"""Build an evidence-preserving population projection from member distributions.

The population object is not an arithmetic-mean person.  Every member
distribution remains addressable; heterogeneity and descriptive response
segments are computed in addition to, never instead of, those observations.
"""
from __future__ import annotations

import hashlib
import math
from itertools import combinations
from typing import Any


SEGMENT_JS_THRESHOLD = 0.08


def _js(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    midpoint = {key: (left.get(key, 0.0) + right.get(key, 0.0)) / 2 for key in keys}

    def kl(row: dict[str, float]) -> float:
        return sum(value * math.log2(value / midpoint[key])
                   for key, value in row.items() if value > 0 and midpoint[key] > 0)

    return (kl(left) + kl(right)) / 2


def _centroid(rows: list[dict[str, float]]) -> dict[str, float]:
    keys = sorted(set().union(*rows))
    values = {key: sum(row.get(key, 0.0) for row in rows) / len(rows) for key in keys}
    total = sum(values.values())
    return {key: value / total for key, value in values.items()}


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


def build_population_analysis(measurements: list[dict[str, Any]], coverage_scope: str,
                              threshold: float = SEGMENT_JS_THRESHOLD) -> dict[str, Any]:
    if not measurements:
        raise ValueError("population analysis requires at least one member measurement")
    members = {row["actor_ref"]: row["distribution"] for row in measurements}
    if len(members) != len(measurements):
        raise ValueError("population analysis requires one measurement per unique member")
    pairwise = [_js(members[left], members[right]) for left, right in combinations(sorted(members), 2)]
    segments = []
    for group in _components(members, threshold):
        rows = [members[member] for member in group]
        internal = [_js(members[left], members[right]) for left, right in combinations(group, 2)]
        digest = hashlib.sha256("\n".join(group).encode()).hexdigest()[:10]
        segments.append({
            "segment_id": f"dynamic-response:{digest}",
            "member_refs": group,
            "weight": len(group) / len(members),
            "centroid_distribution": _centroid(rows),
            "within_segment_mean_js": sum(internal) / len(internal) if internal else 0.0,
        })
    return {
        "kind": "cce.population_projection.v1",
        "member_distributions": members,
        "composition": {
            "known_member_count": len(members),
            "coverage_scope": coverage_scope,
            "exhaustive": False,
        },
        "heterogeneity": {
            "metric": "pairwise_jensen_shannon_divergence_bits",
            "pair_count": len(pairwise),
            "mean": sum(pairwise) / len(pairwise) if pairwise else 0.0,
            "minimum": min(pairwise) if pairwise else 0.0,
            "maximum": max(pairwise) if pairwise else 0.0,
        },
        "segment_mixture": segments,
        "segmentation": {
            "method": "response_similarity_connected_components",
            "js_threshold": threshold,
            "status": "descriptive_not_causal",
        },
    }


def compare_population_projections(previous_window_ref: str, previous: dict[str, Any],
                                   current_window_ref: str, current: dict[str, Any]) -> dict[str, Any]:
    """Describe segment continuity without claiming causal population change."""
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
            "warning": "membership or response changes alone do not establish a causal population transition",
        },
    }
