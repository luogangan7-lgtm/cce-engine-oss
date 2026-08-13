#!/usr/bin/env python3
"""Cross-validate the CCE measurement plane and downstream subject chain.

Passing each JSON validator separately is insufficient: the content id and the
validated content measurement result must also be the same records used by the
downstream chain.  This module is the only entry point allowed to emit VERIFIED.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cce_contract import validate_case
from cce_window_chain import audit_chain


def _gate(status: str, reason: str, refs: list[str] | None = None) -> dict[str, Any]:
    return {"status": status, "reason": reason, "evidence_refs": refs or []}


def audit_end_to_end(measurement_case: dict[str, Any] | None,
                     subject_chain: dict[str, Any]) -> dict[str, Any]:
    downstream = audit_chain(subject_chain)
    gates: dict[str, dict[str, Any]] = {}
    if measurement_case is None:
        measurement_validation = None
        gates["measurement_case"] = _gate("NOT_MET", "no CCE analysis case supplied")
        gates["content_identity_link"] = _gate("NOT_TESTABLE", "requires a CCE analysis case")
        gates["content_result_link"] = _gate("NOT_TESTABLE", "requires a CCE analysis case")
    else:
        measurement_validation = validate_case(measurement_case)
        gates["measurement_case"] = _gate(
            "PASS" if measurement_validation["ok"] else "NOT_MET",
            "CCE analysis case passes contract" if measurement_validation["ok"] else "CCE analysis case violates contract",
        )
        measurement_content = (measurement_case.get("content") or {}).get("id")
        downstream_content = (subject_chain.get("content") or {}).get("id")
        if measurement_content and measurement_content == downstream_content:
            gates["content_identity_link"] = _gate("PASS", "measurement and downstream chain use the same content id", [measurement_content])
        else:
            gates["content_identity_link"] = _gate("NOT_MET", "measurement and downstream content ids do not match")

        declared = subject_chain.get("content_measurement") or {}
        declared_refs = declared.get("result_refs") or []
        actual_refs = {row.get("id") for row in measurement_case.get("measurement_results", []) if isinstance(row, dict)}
        if declared.get("status") == "completed_validated" and declared_refs and all(ref in actual_refs for ref in declared_refs):
            gates["content_result_link"] = _gate("PASS", "downstream content measurement refs resolve to validated CCE results", declared_refs)
        elif declared.get("status") == "legacy_only":
            gates["content_result_link"] = _gate("PARTIAL", "legacy readout is recorded but is not a validated CCE measurement result", declared_refs)
        else:
            gates["content_result_link"] = _gate("NOT_MET", "downstream content measurement refs do not resolve to validated CCE results", declared_refs)

    required = ("measurement_case", "content_identity_link", "content_result_link")
    overall = (
        "VERIFIED"
        if downstream["overall_status"] == "VERIFIED"
        and all(gates[name]["status"] == "PASS" for name in required)
        else "NOT_VERIFIED"
    )
    return {
        "kind": "cce.end_to_end_audit.v1",
        "overall_status": overall,
        "measurement_validation": measurement_validation,
        "cross_plane_gates": gates,
        "downstream_audit": downstream,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject-chain", required=True, type=Path)
    parser.add_argument("--measurement-case", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    chain = json.loads(args.subject_chain.read_text(encoding="utf-8"))
    case = json.loads(args.measurement_case.read_text(encoding="utf-8")) if args.measurement_case else None
    report = audit_end_to_end(case, chain)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    validation_ok = report["downstream_audit"]["validation"]["ok"]
    if report["measurement_validation"] is not None:
        validation_ok = validation_ok and report["measurement_validation"]["ok"]
    raise SystemExit(0 if validation_ok else 1)


if __name__ == "__main__":
    main()
