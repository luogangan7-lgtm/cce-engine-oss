#!/usr/bin/env python3
"""Build a context-bound CCE request and anonymous model-input projection.

CCE is the measurement instrument. It receives events plus a time-bound
Universal Context.  Transition mode may additionally receive an evidence-bound
pre-state snapshot, but never a person/mode profile answer, platform delivery
result or post-exposure outcome. The model-input projection strips the snapshot's
subject join key: that key remains outside CCE for downstream aggregation only.
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


# 旧名与新名必须**同时**永久禁止。
# 只留新名, 历史模型和外部输入仍可用旧名把身份/分群字段重新注入; 删旧名不等于旧攻击面消失。
# 旧名在这里是 DENYLIST_SENTINEL —— 代表「拒绝能力」, 不代表业务还依赖旧本体。
# 参见 config/ontology_legacy_exceptions_v1.json。
MODEL_FORBIDDEN_KEYS = {
    "subject_ref", "subject_refs", "subject_id", "profile_version", "subject_version",
    "subject_card", "subject_cards", "population_id",
    # canonical v2 本体
    "mode_id", "population_field_id", "evidence_unit_id",
    # legacy denylist sentinels (v1 本体, 永不删除)
    "segment_id", "individual_id",
}


def _forbidden_model_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return ({str(key) for key in value if key in MODEL_FORBIDDEN_KEYS}
                | set().union(*(_forbidden_model_keys(item) for item in value.values()), set()))
    if isinstance(value, list):
        return set().union(*(_forbidden_model_keys(item) for item in value), set())
    return set()


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


def build_model_input(case: dict[str, Any], request_ref: str | None = None) -> dict[str, Any]:
    """Project a validated case into the only payload a CCE adapter may consume.

    Full cases retain ``subject_ref`` on state snapshots solely to join pre/post
    evidence after measurement. This projection emits state values without that
    identifier, so CCE conditions on an evidence-bound baseline state rather than
    on a person, mode, profile, product audience, or population label.
    """
    verdict = validate_case(case)
    if not verdict["ok"]:
        raise ValueError("cannot project invalid CCE case:\n" + "\n".join(verdict["errors"]))
    requests = [row for row in case.get("cce_requests", [])
                if request_ref is None or row.get("id") == request_ref]
    if len(requests) != 1:
        raise ValueError("exactly one matching cce_request is required")
    request = requests[0]
    events = {row["id"]: row for row in case.get("events", [])}
    contexts = {row["id"]: row for row in case.get("context_snapshots", [])}
    payload = {
        "kind": "cce.measurement_input.v1",
        "request_ref": request["id"],
        "measurement_mode": request["measurement_mode"],
        "measurement_adapter": request["measurement_adapter"],
        "prediction_time": request["prediction_time"],
        "event_stream": [copy.deepcopy(events[ref]) for ref in request["event_refs"]],
        "context_snapshot": copy.deepcopy(contexts[request["context_snapshot_ref"]]),
        "boundary": "anonymous state measurement; Subject is constructed downstream",
    }
    if request["measurement_mode"] == "transition":
        snapshots = {row["id"]: row for row in case.get("state_snapshots", [])}
        snapshot = snapshots[request["pre_state_snapshot_ref"]]
        payload["baseline_state"] = {
            field: copy.deepcopy(snapshot[field])
            for field in ("observed_at", "assertion", "dimensions", "evidence_refs",
                          "confidence", "temporal_scope")
        }
    forbidden = _forbidden_model_keys(payload)
    if forbidden:
        raise ValueError("CCE model input contains downstream Subject keys: " + ", ".join(sorted(forbidden)))
    return payload


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
