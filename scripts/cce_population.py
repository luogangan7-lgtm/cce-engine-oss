#!/usr/bin/env python3
"""Synthesize an evidence-bound Population Subject without inventing an average person.

A population is represented as a weighted mixture of observed member distributions.
The mixture marginal is a legitimate population summary, but it is explicitly not an
individual profile. Descriptive mode candidates require more than one supporting member; isolated
members remain unassigned instead of being mislabeled as one-person modes.
"""
from __future__ import annotations

import hashlib
import math
from itertools import combinations
from typing import Any


MODE_JS_THRESHOLD = 0.08
MIN_MODE_SIZE = 2


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


def _field_structure(modes: list[dict[str, Any]], unassigned: list[str],
                     weights: dict[str, float], pairwise: list[float]) -> dict[str, Any]:
    """场结构 = 这个 population field 被分成了几个模态、各占多少、还剩多少未归属。

    不回答「这个场应该有几个模态」—— 那要真值。只描述当前证据分出了什么。
    """
    mode_weights = [row["weight"] for row in modes]
    return {
        "mode_count": len(modes),
        "unassigned_member_count": len(unassigned),
        "mode_weights": mode_weights,
        "largest_mode_weight": max(mode_weights) if mode_weights else 0.0,
        # 模态数为 0/1 时「多峰」无从谈起, 显式写出来而不是给一个会被误读的 0
        "shape": ("no_supported_mode" if not modes else
                  "single_mode" if len(modes) == 1 else "multi_mode"),
        "heterogeneity_mean_js": sum(pairwise) / len(pairwise) if pairwise else 0.0,
        "assertion": "derived",
        "inference_scope": "descriptive_not_causal",
        "warning": "模态数由 js_threshold 与 min_mode_size 决定, 不是场的固有属性",
    }


def _mode_coverage(modes: list[dict[str, Any]], unassigned: list[str],
                   weights: dict[str, float]) -> dict[str, Any]:
    """模态覆盖率。★ 分母是**已观测成员**, 不是目标人群。"""
    covered_refs = [ref for row in modes for ref in row["member_refs"]]
    covered_weight = sum(row["weight"] for row in modes)
    total = len(covered_refs) + len(unassigned)
    return {
        "covered_member_count": len(covered_refs),
        "uncovered_member_count": len(unassigned),
        "covered_weight": covered_weight,
        "uncovered_weight": sum(weights[m] for m in unassigned),
        "covered_member_share": len(covered_refs) / total if total else 0.0,
        "denominator": "known_member_count",
        "not_denominator": "target_population_size",
        "warning": ("覆盖率的分母是已观测成员数。没有抽样框时它**不是**"
                    "「这个圈子里有多大比例属于某个模态」。"),
    }


def _mode_activation(modes: list[dict[str, Any]], evidence_refs: list[str],
                     stage: str) -> dict[str, Any]:
    """模态激活: 每个模态背后**实际有多少条测量证据**支撑。

    与 mode_coverage 的区别: coverage 问「成员归没归属」, activation 问
    「这个模态是被测出来的还是被阈值切出来的」。支撑成员数 == min_mode_size
    的模态是**刚好够线**的, 单独标出来 —— 它最容易在阈值微调下消失。
    """
    rows = [{
        "mode_id": row["mode_id"],
        "supporting_member_count": len(row["member_refs"]),
        "weight": row["weight"],
        "within_mode_mean_js": row["within_mode_mean_js"],
        "activation_stage": stage,
    } for row in modes]
    minimal = [r["mode_id"] for r in rows if r["supporting_member_count"] <= 2]
    return {
        "stage": stage,
        "modes": rows,
        "evidence_ref_count": len(evidence_refs),
        "minimally_supported_mode_ids": minimal,
        "warning": ("supporting_member_count 恰为 2 的模态只是刚过 min_mode_size, "
                    "阈值微调即可使其消失; 不得当作稳定结构陈述。") if minimal else None,
        "assertion": "derived",
    }


def build_population_subject(measurements: list[dict[str, Any]], coverage_scope: str,
                             threshold: float = MODE_JS_THRESHOLD, *,
                             weights: dict[str, float] | None = None,
                             min_mode_size: int = MIN_MODE_SIZE,
                             stage: str = "activated", exhaustive: bool = False,
                             time_window: dict[str, str] | None = None,
                             evidence_refs: list[str] | None = None) -> dict[str, Any]:
    if not measurements:
        raise ValueError("population synthesis requires at least one member measurement")
    # 铁律 25: 群体内容优化以 Coverage/Structure 为中心 —— 而覆盖率是**某个已声明框**的分数。
    # ★ 2026-09-03 实测 coverage_scope="" 曾被放行, 于是 mode_coverage 算出来了却
    #   没说覆盖的是什么的 ⇒ 下游只能把它读成「覆盖了全部」。
    if not (coverage_scope or "").strip():
        raise ValueError(
            "coverage_scope 不能为空 —— 铁律 25: 覆盖率是**某个已声明框**的分数。"
            "不声明框, mode_coverage 就会被读成「覆盖了全部」。")
    if min_mode_size < 2:
        raise ValueError("a descriptive mode candidate requires at least two members")
    members = {
        row["actor_ref"]: _validate_distribution(row["distribution"], f"measurement[{row['actor_ref']}]")
        for row in measurements
    }
    if len(members) != len(measurements):
        raise ValueError("population synthesis requires one measurement per unique member")
    member_refs = sorted(members)
    member_weights, weighting_method = _normalise_weights(member_refs, measurements, weights)
    pairwise = [_js(members[left], members[right]) for left, right in combinations(member_refs, 2)]

    modes: list[dict[str, Any]] = []
    unassigned: list[str] = []
    for group in _components(members, threshold):
        if len(group) < min_mode_size:
            unassigned.extend(group)
            continue
        internal = [_js(members[left], members[right]) for left, right in combinations(group, 2)]
        digest = hashlib.sha256("\n".join(group).encode()).hexdigest()[:10]
        modes.append({
            "mode_id": f"dynamic-response:{digest}",
            "mode_basis": "shared_stimulus_response_similarity",
            "member_refs": group,
            "weight": sum(member_weights[member] for member in group),
            "centroid_distribution": _weighted_centroid(group, members, member_weights),
            "within_mode_mean_js": sum(internal) / len(internal),
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
    mode_partition_status = "descriptive_not_causal" if modes else "insufficient_support"
    return {
        "kind": "cce.population_subject.v2",
        "population_id": population_id,
        "scale": "population",
        "stage": stage,
        "time_window": time_window or {"status": "not_supplied"},
        "evidence_refs": unique_evidence_refs,
        "provenance": {"producer": "cce_population", "version": "2.0.0", "assertion": "derived"},
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
        "mode_mixture": modes,
        "unassigned_member_refs": unassigned,
        "unassigned_weight": sum(member_weights[member] for member in unassigned),
        # ── §44 P2 新增。三者都只是**已观测证据的描述**, 不新增任何推断能力:
        #    覆盖率的分母是 known_member_count, 不是「这个圈子有多少人」。
        "field_structure": _field_structure(modes, unassigned, member_weights, pairwise),
        "mode_coverage": _mode_coverage(modes, unassigned, member_weights),
        "mode_activation": _mode_activation(modes, unique_evidence_refs, stage),
        "mode_partition": {
            "method": "response_similarity_connected_components",
            "js_threshold": threshold,
            "min_mode_size": min_mode_size,
            "status": mode_partition_status,
            "inference_scope": "descriptive_not_causal",
            "warning": "singletons are unassigned evidence components, not one-person modes",
        },
        "uncertainty": {
            "status": "not_estimated",
            "reason": "no probability sampling frame or repeated-window resampling protocol supplied",
        },
    }


def build_population_analysis(measurements: list[dict[str, Any]], coverage_scope: str,
                              threshold: float = MODE_JS_THRESHOLD, **kwargs: Any) -> dict[str, Any]:
    """Backward-compatible function name; the returned object is a Population Subject."""
    return build_population_subject(measurements, coverage_scope, threshold, **kwargs)


def _field_drift(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """场漂移: 两个窗口之间**结构量**的变化, 不解释成因。

    ★ 成员集合本身变了的时候, 结构差里混着「换了一批人」和「同一批人变了」——
    两者在这里分不开, 所以显式标 confounded, 不给一个会被当成因果的数。
    """
    def _fs(node):
        return node.get("field_structure") or {}
    prev_fs, cur_fs = _fs(previous), _fs(current)
    prev_members = set(previous.get("member_distributions", {}))
    cur_members = set(current.get("member_distributions", {}))
    shared = prev_members & cur_members
    membership_changed = prev_members != cur_members
    def _d(key, default=0.0):
        return (cur_fs.get(key, default) or default) - (prev_fs.get(key, default) or default)
    return {
        "mode_count_delta": _d("mode_count"),
        "largest_mode_weight_delta": _d("largest_mode_weight"),
        "heterogeneity_mean_js_delta": _d("heterogeneity_mean_js"),
        "unassigned_weight_delta": (current.get("unassigned_weight", 0.0)
                                    - previous.get("unassigned_weight", 0.0)),
        "membership": {
            "previous_n": len(prev_members), "current_n": len(cur_members),
            "shared_n": len(shared), "changed": membership_changed,
        },
        "confounded": membership_changed,
        "assertion": "derived",
        "inference_scope": "descriptive_not_causal",
        "warning": ("成员集合在两窗口之间发生变化, 结构差里同时含有「换了一批人」与"
                    "「同一批人变了」, 二者不可分 —— 不得读作人群发生了变化。")
                   if membership_changed else
                   ("成员集合相同, 结构差只反映响应变化; 但仍不构成因果陈述 ——"
                    "没有干预、没有对照。"),
    }


def partition_projection(population: dict[str, Any], target_domain: str, *,
                         frame: dict[str, Any] | None = None) -> dict[str, Any]:
    """把模态划分投影到一个声明的目标域。

    ★ 没有抽样框就**投不了**。这不是保守, 是算术: 已观测 n 个成员在目标域
    总体 N 中的占比, 在 N 未知时无界。所以无框时返回 NOT_PROJECTABLE_NO_FRAME
    并给出为什么无界, 而不是把观测占比换个名字当投影结果。

    frame 需要: {"cell_totals": {cell: N_cell}, "member_cells": {member_ref: cell}}
    """
    modes = population.get("mode_mixture", [])
    observed = {row["mode_id"]: row["weight"] for row in modes}
    base = {"kind": "cce.partition_projection.v1", "target_domain": target_domain,
            "source_population_id": population.get("population_id"),
            "observed_mode_weights": observed,
            "assertion": "derived", "inference_scope": "descriptive_not_causal"}
    if not frame:
        return {**base, "status": "NOT_PROJECTABLE_NO_FRAME", "projected_mode_shares": None,
                "reason": ("目标域没有抽样框/单元总数。已观测 n 个成员在总体 N 中的占比"
                           "在 N 未知时无界 —— 观测占比换个名字不是投影结果。"),
                "needed": ["cell_totals", "member_cells"]}
    cell_totals = frame.get("cell_totals") or {}
    member_cells = frame.get("member_cells") or {}
    missing = sorted({m for row in modes for m in row["member_refs"]} - set(member_cells))
    if missing:
        return {**base, "status": "NOT_PROJECTABLE_UNMAPPED_MEMBERS",
                "projected_mode_shares": None,
                "unmapped_member_refs": missing,
                "reason": "抽样框没有覆盖全部已观测成员, 投影会静默丢人。"}
    unknown_cells = sorted(set(member_cells.values()) - set(cell_totals))
    if unknown_cells:
        return {**base, "status": "NOT_PROJECTABLE_UNKNOWN_CELL_TOTAL",
                "projected_mode_shares": None, "unknown_cells": unknown_cells,
                "reason": "有单元缺 total, 该单元的放大系数无从计算。"}
    observed_per_cell: dict[str, int] = {}
    for cell in member_cells.values():
        observed_per_cell[cell] = observed_per_cell.get(cell, 0) + 1
    grand_total = sum(cell_totals[c] for c in observed_per_cell)
    projected = {}
    for row in modes:
        mass = sum(cell_totals[member_cells[m]] / observed_per_cell[member_cells[m]]
                   for m in row["member_refs"])
        projected[row["mode_id"]] = mass / grand_total if grand_total else 0.0
    unassigned_mass = sum(cell_totals[member_cells[m]] / observed_per_cell[member_cells[m]]
                          for m in population.get("unassigned_member_refs", [])
                          if m in member_cells)
    return {**base, "status": "PROJECTED",
            "projected_mode_shares": projected,
            "projected_unassigned_share": unassigned_mass / grand_total if grand_total else 0.0,
            "frame": {"cells": sorted(observed_per_cell), "grand_total": grand_total,
                      "observed_per_cell": observed_per_cell},
            "method": "design_weight_by_cell = cell_total / observed_in_cell",
            "warning": ("投影只在抽样框声明的域内成立; 单元内**非随机**抽样时"
                        "放大系数仍带选择偏倚, 本函数不修正它。")}


def compare_population_projections(previous_window_ref: str, previous: dict[str, Any],
                                   current_window_ref: str, current: dict[str, Any]) -> dict[str, Any]:
    """Describe stable-mode continuity without claiming causal population change."""
    old = {row["mode_id"]: set(row["member_refs"]) for row in previous.get("mode_mixture", [])}
    new = {row["mode_id"]: set(row["member_refs"]) for row in current.get("mode_mixture", [])}
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
        "kind": "cce.population_evolution.v2",
        "previous_window_ref": previous_window_ref,
        "current_window_ref": current_window_ref,
        "events": events,
        # ── §44 P2: window_transition 是 events 的具名契约字段。
        #    这一段逻辑本来就在, 只是从来没有以 P2 要求的名字出现在产物里 ——
        #    「实现了」和「契约上可被下游依赖」不是一回事。
        "window_transition": {
            "from": previous_window_ref, "to": current_window_ref,
            "events": events,
            "event_counts": {kind: sum(1 for e in events if e["event"] == kind)
                             for kind in ("continue", "split", "merge", "create", "disappear")},
            "assertion": "derived", "inference_scope": "descriptive_not_causal",
        },
        "field_drift": _field_drift(previous, current),
        "status": "descriptive_not_causal",
        "comparability": {
            "shared_members": len(set(previous.get("member_distributions", {})) & set(current.get("member_distributions", {}))),
            "previous_unassigned": len(previous.get("unassigned_member_refs", [])),
            "current_unassigned": len(current.get("unassigned_member_refs", [])),
            "warning": "membership or response changes alone do not establish a causal population transition",
        },
    }
