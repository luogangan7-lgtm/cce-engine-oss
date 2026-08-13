#!/usr/bin/env python3
"""Executable gates for subject-window semantics and the real post6 audit."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from cce_window_chain import audit_chain, validate_chain  # noqa: E402


bundle = json.loads((ROOT / "examples" / "cce_reddit_post6_chain_audit.json").read_text(encoding="utf-8"))
verdict = validate_chain(bundle)
assert verdict["ok"], verdict
audit = audit_chain(bundle)
assert audit["overall_status"] == "NOT_VERIFIED", audit
assert audit["gates"]["reached_window"]["status"] == "PASS", audit
assert audit["gates"]["distribution_observed"]["status"] == "PARTIAL", audit
for gate in ("activated_window", "action_window", "conversion_window"):
    assert audit["gates"][gate]["status"] == "NOT_MET", (gate, audit)
assert all(row["status"] == "NOT_TESTABLE" for row in audit["attribution_deltas"].values()), audit

versioned = copy.deepcopy(bundle)
versioned["subject_windows"][0]["profile_version"] = "v3"
assert not validate_chain(versioned)["ok"]

aggregate_reach = copy.deepcopy(bundle)
aggregate_reach["subject_windows"][0]["population_set"] = {"kind": "platform_exposure", "count": 197}
assert not validate_chain(aggregate_reach)["ok"]

missing_member_evidence = copy.deepcopy(bundle)
missing_member_evidence["subject_windows"][0]["member_evidence"].pop("reddit:u/user_46")
assert not validate_chain(missing_member_evidence)["ok"]

versioned_entity = copy.deepcopy(bundle)
versioned_entity["subject_entities"] = [{"id": "reddit:u/user_46", "subject_id": "reddit:u/user_46",
                                         "profile_version": "v3", "core": {},
                                         "identity_evidence": [], "state_observations": []}]
assert not validate_chain(versioned_entity)["ok"]

valid_entity = copy.deepcopy(bundle)
valid_entity["subject_entities"] = [{"id": "reddit:u/user_46", "subject_id": "reddit:u/user_46",
                                     "core": {"desire_baseline": "unknown"},
                                     "identity_evidence": [], "state_observations": []}]
assert validate_chain(valid_entity)["ok"], validate_chain(valid_entity)

bad_coverage = copy.deepcopy(bundle)
bad_coverage["subject_windows"][0]["population_set"]["coverage"] = "all viewers"
assert not validate_chain(bad_coverage)["ok"]

print("PASS: stable unversioned subject ontology, dynamic windows, distribution/reach split, observability, member evidence, and honest post6 chain audit")
