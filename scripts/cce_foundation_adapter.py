#!/usr/bin/env python3
"""Adapt a versioned ``cce_video_parse`` artifact into CCE Foundation evidence.

The adapter is intentionally conservative: it emits parser observations only.
Turning those observations into semantic / cross-modal events is a later,
versioned Event Assembler step; this keeps parser output from being promoted to
psychological claims by accident.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from cce_contract import validate_case


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_VERSION = "1.0.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def timepoint(ts: Any, duration: float) -> dict[str, float]:
    start = max(0.0, float(ts))
    # A decoded frame is a point observation. Encode it as the smallest useful
    # half-open interval rather than inventing a scene duration.
    end = min(duration, start + 0.001)
    if end <= start:
        start = max(0.0, duration - 0.001)
        end = duration
    return {"start": round(start, 6), "end": round(end, 6)}


def observation(record_id: str, kind: str, evidence_ref: str, provenance: dict[str, Any], **payload: Any) -> dict[str, Any]:
    return {"id": record_id, "kind": kind, "assertion": "observed",
            "evidence_refs": [evidence_ref], "provenance": provenance, **payload}


def adapt(parsed: dict[str, Any], source_path: Path, content_id: str | None = None) -> dict[str, Any]:
    video = Path(parsed.get("video") or source_path)
    content_hash = sha256_file(video) if video.is_file() else sha256_file(source_path)
    source = str(video) if video.is_file() else str(source_path)
    name = str(parsed.get("name") or source_path.stem)
    cid = content_id or f"content:video-parse:{name}"
    duration = float(parsed.get("duration") or 0.0)
    if duration <= 0:
        raise ValueError("parse artifact has no positive duration")
    parser_provenance = {
        "producer": "cce_video_parse",
        "adapter": "cce_foundation_adapter",
        "adapter_version": ADAPTER_VERSION,
        "parse_artifact": str(source_path),
        "parser_version": parsed.get("parser_version", "legacy_v4_or_earlier"),
        "parse_completeness": parsed.get("completeness", {}),
    }
    observations: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for ts, model_outputs in (parsed.get("visual") or {}).items():
        for model, fields in (model_outputs or {}).items():
            observations.append(observation(
                f"obs:visual:{name}:{ts}:{model}", "visual_frame_description", cid,
                {**parser_provenance, "model": model}, time=timepoint(ts, duration), value=fields,
            ))
    for ts, texts in (parsed.get("ocr") or {}).items():
        if texts:
            observations.append(observation(
                f"obs:ocr:{name}:{ts}", "on_screen_text", cid,
                {**parser_provenance, "engine": (parsed.get("ocr_meta") or {}).get("engine")},
                time=timepoint(ts, duration), value=texts,
            ))
    audio = parsed.get("audio") or {}
    if audio.get("transcript"):
        observations.append(observation(
            f"obs:asr:{name}", "speech_transcript", cid, parser_provenance,
            time={"start": 0.0, "end": duration}, value=audio["transcript"],
        ))
    if audio.get("event_tags"):
        observations.append(observation(
            f"obs:audio-tags:{name}", "audio_tags", cid, parser_provenance,
            time={"start": 0.0, "end": duration}, value=audio["event_tags"],
        ))
    for index, cut in enumerate((parsed.get("cinematography") or {}).get("shot_boundaries") or []):
        obs_id = f"obs:shot-cut:{name}:{index}"
        observations.append(observation(
            obs_id, "shot_boundary", cid, parser_provenance, time=timepoint(cut, duration), value={"cut_at": cut},
        ))
        events.append({
            "id": f"evt:shot-cut:{name}:{index}", "event_type": "shot_boundary", "layer": "atomic",
            "assertion": "observed", "time": timepoint(cut, duration), "member_refs": [obs_id],
            "evidence_refs": [obs_id], "confidence": 1.0,
        })

    return {
        "kind": "cce.analysis_case.v1",
        "content": {"id": cid, "format": "short_video", "source": source, "content_hash": content_hash},
        "observations": observations, "events": events,
        "cce_requests": [], "measurement_results": [], "exposures": [], "outcomes": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parse_artifact", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--content-id")
    args = parser.parse_args()
    parsed = json.loads(args.parse_artifact.read_text(encoding="utf-8"))
    case = adapt(parsed, args.parse_artifact, args.content_id)
    verdict = validate_case(case)
    if not verdict["ok"]:
        raise SystemExit("adapter emitted invalid contract:\n" + "\n".join(verdict["errors"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), **verdict["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
