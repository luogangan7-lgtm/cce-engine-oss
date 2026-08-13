#!/usr/bin/env python3
"""Build a content-only CCE request from an evidence/event case.

CCE is the measurement instrument.  It must not receive a person, a segment,
a profile version, platform state, or post-exposure evidence.  Those belong to
the downstream subject-window and mechanism layers.
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


def request_id(content_id: str, event_ids: list[str]) -> str:
    suffix = hashlib.sha256("\n".join(sorted(event_ids)).encode()).hexdigest()[:10]
    return f"req:{content_id}:{suffix}"


def build_request(case: dict[str, Any], adapter: str) -> dict[str, Any]:
    out = assemble(case)
    if not out.get("events"):
        raise ValueError("no events available: CCE request cannot bypass the event plane")
    for forbidden in ("subject_refs", "contexts"):
        out.pop(forbidden, None)
    event_ids = [event["id"] for event in out["events"]]
    out["cce_requests"] = [{
        "id": request_id(out["content"]["id"], event_ids),
        "measurement_adapter": adapter,
        "event_refs": event_ids,
        "prediction_time": "pre_exposure",
    }]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-case", type=Path, required=True)
    parser.add_argument("--adapter", default="event_packet@v1", help="declares the adapter; it does not execute it")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    case = json.loads(args.evidence_case.read_text(encoding="utf-8"))
    out = build_request(case, args.adapter)
    verdict = validate_case(out)
    if not verdict["ok"]:
        raise SystemExit("request assembly failed contract:\n" + "\n".join(verdict["errors"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "request_id": out["cce_requests"][0]["id"], "events": len(out["events"]), "warnings": verdict["warnings"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
