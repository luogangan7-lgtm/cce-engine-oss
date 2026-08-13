#!/usr/bin/env python3
"""Build a context-bound CCE request from an evidence/event case.

CCE is the measurement instrument. It receives events plus a time-bound
Universal Context.  Transition mode may additionally receive an evidence-bound
pre-state snapshot, but never a person/segment profile answer, platform delivery
result or post-exposure outcome.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from cce_contract import validate_case
from cce_event_assemble import assemble


def request_id(content_id: str, event_ids: list[str], measurement_mode: str,
               pre_state_snapshot_ref: str | None = None) -> str:
    identity = [measurement_mode, pre_state_snapshot_ref or "none", *sorted(event_ids)]
    suffix = hashlib.sha256("\n".join(identity).encode()).hexdigest()[:10]
    return f"req:{content_id}:{suffix}"


def build_request(case: dict[str, Any], adapter: str, measurement_mode: str = "stimulus",
                  pre_state_snapshot_ref: str | None = None) -> dict[str, Any]:
    out = assemble(case)
    if not out.get("events"):
        raise ValueError("no events available: CCE request cannot bypass the event plane")
    contexts = out.get("context_snapshots") or []
    if len(contexts) != 1 or not contexts[0].get("id"):
        raise ValueError("exactly one context_snapshot is required for a CCE request")
    for forbidden in ("subject_refs", "contexts"):
        out.pop(forbidden, None)
    event_ids = [event["id"] for event in out["events"]]
    request = {
        "id": request_id(out["content"]["id"], event_ids, measurement_mode, pre_state_snapshot_ref),
        "measurement_mode": measurement_mode,
        "measurement_adapter": adapter,
        "event_refs": event_ids,
        "context_snapshot_ref": contexts[0]["id"],
        "prediction_time": "pre_exposure",
    }
    if measurement_mode == "transition":
        snapshots = {row.get("id") for row in out.get("state_snapshots", []) if isinstance(row, dict)}
        if pre_state_snapshot_ref not in snapshots:
            raise ValueError("transition mode requires a pre_state_snapshot_ref present in state_snapshots")
        request["pre_state_snapshot_ref"] = pre_state_snapshot_ref
    elif pre_state_snapshot_ref:
        raise ValueError("pre_state_snapshot_ref is only valid for transition mode")
    out["cce_requests"] = [request]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-case", type=Path, required=True)
    parser.add_argument("--adapter", default="event_packet@v1", help="declares the adapter; it does not execute it")
    parser.add_argument("--measurement-mode", choices=("stimulus", "observed_response", "transition"), default="stimulus")
    parser.add_argument("--pre-state-snapshot-ref")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    case = json.loads(args.evidence_case.read_text(encoding="utf-8"))
    out = build_request(case, args.adapter, args.measurement_mode, args.pre_state_snapshot_ref)
    verdict = validate_case(out)
    if not verdict["ok"]:
        raise SystemExit("request assembly failed contract:\n" + "\n".join(verdict["errors"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "request_id": out["cce_requests"][0]["id"], "events": len(out["events"]), "warnings": verdict["warnings"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
