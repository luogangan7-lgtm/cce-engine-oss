#!/usr/bin/env python3
"""Executable gates against collapsing heterogeneous populations into an average person."""
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
assert set(population["member_distributions"]) == {row["actor_ref"] for row in measurements}
assert len(population["segment_mixture"]) == 2, population
assert population["heterogeneity"]["maximum"] > 0.8, population
assert all(len(segment["member_refs"]) == 2 for segment in population["segment_mixture"]), population
assert "aggregate_distribution" not in population and "mean_distribution" not in population

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
