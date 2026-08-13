#!/usr/bin/env python3
"""Executable gates against collapsing heterogeneous populations into an average person."""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_population import build_population_analysis, compare_population_projections  # noqa: E402


measurements = [
    {"actor_ref": "subject:a1", "distribution": {"approach": 0.98, "avoid": 0.02}},
    {"actor_ref": "subject:a2", "distribution": {"approach": 0.95, "avoid": 0.05}},
    {"actor_ref": "subject:b1", "distribution": {"approach": 0.03, "avoid": 0.97}},
    {"actor_ref": "subject:b2", "distribution": {"approach": 0.01, "avoid": 0.99}},
]
population = build_population_analysis(measurements, "fixture_complete", threshold=0.08)
assert population["kind"] == "cce.population_subject.v1"
assert set(population["member_distributions"]) == {row["actor_ref"] for row in measurements}
assert len(population["segment_mixture"]) == 2, population
assert population["heterogeneity"]["maximum"] > 0.8, population
assert all(len(segment["member_refs"]) == 2 for segment in population["segment_mixture"]), population
assert not population["unassigned_member_refs"] and population["unassigned_weight"] == 0
expected_marginal = {"approach": 0.4925, "avoid": 0.5075}
assert all(math.isclose(population["population_mixture"]["marginal_distribution"][key], value,
                        rel_tol=0.0, abs_tol=1e-12)
           for key, value in expected_marginal.items())
assert population["population_mixture"]["marginal_semantics"] == "weighted population marginal; never an individual persona"
assert population["population_mixture"]["component_quantiles"]["approach"]["p25"] == 0.01
assert "aggregate_distribution" not in population and "mean_distribution" not in population

isolated = build_population_analysis([
    {"actor_ref": f"subject:{index}", "distribution": {f"state:{index}": 1.0}}
    for index in range(8)
], "identified_inbound_only", threshold=0.08)
assert isolated["segment_mixture"] == [], isolated
assert len(isolated["unassigned_member_refs"]) == 8
assert isolated["segmentation"]["status"] == "insufficient_support"
assert isolated["composition"]["known_member_count"] == 8

later = build_population_analysis([
    measurements[0], measurements[2],
    {"actor_ref": "subject:a2", "distribution": {"approach": 0.51, "avoid": 0.49}},
    {"actor_ref": "subject:b2", "distribution": {"approach": 0.49, "avoid": 0.51}},
], "fixture_complete", threshold=0.08)
evolution = compare_population_projections("window:t1", population, "window:t2", later)
assert evolution["status"] == "descriptive_not_causal"
assert evolution["comparability"]["shared_members"] == 4
assert any(row["event"] in {"split", "merge", "create", "disappear"} for row in evolution["events"]), evolution

print("PASS: bimodal population remains bimodal, member distributions survive, heterogeneity is explicit, and evolution stays descriptive")
