#!/usr/bin/env python3
"""Assemble conservative CCE events from Foundation observations.

This is deliberately an event *assembler*, not a psychological inference
engine.  It emits atomic events and time-synchronised composites only; words
such as reinforces, attention, trust or intent never arise from overlap alone.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from cce_contract import validate_case

ASSEMBLER_VERSION = "1.0.0"


ATOMIC_TYPES = {
    "visual_frame_description": "visual_frame_observed",
    "on_screen_text": "on_screen_text_observed",
    "speech_transcript": "speech_observed",
    "audio_tags": "audio_tags_observed",
}


def overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ta, tb = a.get("time"), b.get("time")
    if not isinstance(ta, dict) or not isinstance(tb, dict):
        return False
    return max(ta["start"], tb["start"]) < min(ta["end"], tb["end"])


def intersection(a: dict[str, Any], b: dict[str, Any]) -> dict[str, float]:
    return {"start": max(a["time"]["start"], b["time"]["start"]),
            "end": min(a["time"]["end"], b["time"]["end"])}


def assemble(case: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(case)
    observations = out.get("observations") or []
    existing = {event.get("id") for event in out.get("events") or []}
    events = out.setdefault("events", [])
    atomic: list[dict[str, Any]] = []
    for obs in observations:
        event_type = ATOMIC_TYPES.get(obs.get("kind"))
        if not event_type or not isinstance(obs.get("time"), dict):
            continue
        eid = "evt:assembled:" + obs["id"].replace("obs:", "")
        if eid in existing:
            continue
        event = {
            "id": eid, "event_type": event_type, "layer": "atomic", "assertion": "derived",
            "time": obs["time"], "member_refs": [obs["id"]], "evidence_refs": [obs["id"]],
            # 该事件是**既有观测的 1:1 复述** ⇒ 给定成员即必然为真, 不是测量结果。
            "confidence": 1.0, "confidence_basis": "definitional",
            "provenance": {"producer": "cce_event_assemble", "version": ASSEMBLER_VERSION},
        }
        events.append(event); atomic.append(event); existing.add(eid)

    # Cross-modal composite only asserts synchronisation.  It intentionally
    # avoids "reinforcement", which needs a separately validated mechanism.
    visuals = [e for e in atomic if e["event_type"] == "visual_frame_observed"]
    texts = [e for e in atomic if e["event_type"] == "on_screen_text_observed"]
    for visual in visuals:
        for text in texts:
            if not overlaps(visual, text):
                continue
            eid = f"evt:assembled:sync:{visual['id'].split(':')[-2]}:{text['id'].split(':')[-1]}"
            if eid in existing:
                continue
            events.append({
                "id": eid, "event_type": "cross_modal_synchronization", "layer": "composite",
                "assertion": "derived", "time": intersection(visual, text),
                "member_refs": [visual["id"], text["id"]],
                "evidence_refs": visual["evidence_refs"] + text["evidence_refs"],
                # 「两区间重叠」由时间戳算出 ⇒ 构造上必然为真, 不是同步强度的度量。
                "confidence": 1.0, "confidence_basis": "definitional",
                "relations": ["synchronizes"],
                "provenance": {"producer": "cce_event_assemble", "version": ASSEMBLER_VERSION},
            })
            existing.add(eid)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    case = json.loads(args.case.read_text(encoding="utf-8"))
    out = assemble(case)
    verdict = validate_case(out)
    if not verdict["ok"]:
        raise SystemExit("assembler emitted invalid contract:\n" + "\n".join(verdict["errors"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "events": verdict["counts"]["events"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
