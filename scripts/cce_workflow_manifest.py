#!/usr/bin/env python3
"""Build the aggregate audit manifest for a normalized outbound CCE submission."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build(normalized: dict[str, Any], artifacts: Path) -> dict[str, Any]:
    expected = {row["_meta"]["job_id"]: row for row in normalized.get("items", [])}
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    profile = normalized.get("profile")
    for path in artifacts.rglob("manifest.json"):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        meta = manifest.get("submission") or {}
        job_id = meta.get("job_id")
        if job_id not in expected:
            errors.append(f"unexpected or missing submission metadata in {path}")
            continue
        if job_id in found:
            errors.append(f"duplicate job artifact {job_id}")
            continue
        item = expected[job_id]
        if manifest.get("text_sha256") != item["_meta"].get("text_sha256"):
            errors.append(f"exact input fingerprint mismatch for {job_id}")
        alignment = None
        alignment_path = path.with_name("reply_alignment.json")
        if profile == "outbound_reply":
            if not alignment_path.exists():
                errors.append(f"reply alignment missing for {job_id}")
            else:
                alignment = json.loads(alignment_path.read_text(encoding="utf-8")).get("verdict") or {}
                if alignment.get("PASS") is not True:
                    errors.append(f"reply alignment gate failed for {job_id}")
        measurement_complete = (manifest.get("stages") or {}).get("s1_readout", {}).get("status") == "OK"
        found[job_id] = {"job_id": job_id, "content_id": meta.get("content_id"),
            "profile": meta.get("profile"), "text_sha256": manifest.get("text_sha256"),
            "engine_complete": manifest.get("complete") is True, "failed_at": manifest.get("failed_at"),
            "measurement_complete": measurement_complete,
            "reply_alignment_pass": alignment.get("PASS") if alignment is not None else None,
            "artifact_dir": str(path.parent)}
        if profile == "subject_chain" and not measurement_complete:
            errors.append(f"s1 response measurement incomplete for {job_id}")
        elif profile != "subject_chain" and manifest.get("complete") is not True:
            errors.append(f"engine chain incomplete for {job_id}: {manifest.get('failed_at')}")
    missing = sorted(set(expected) - set(found))
    if missing: errors.append("missing job artifacts: " + ", ".join(missing))
    return {"kind": "cce.workflow_manifest.v1", "schema_version": normalized.get("schema_version"),
        "submission_id": normalized.get("submission_id"), "profile": normalized.get("profile"),
        "complete": not errors and len(found) == len(expected), "items_expected": len(expected),
        "items_completed": len(found), "jobs": [found[key] for key in sorted(found)], "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalized", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    normalized = json.loads(args.normalized.read_text(encoding="utf-8"))
    manifest = build(normalized, args.artifacts)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"submission_id": manifest["submission_id"], "complete": manifest["complete"],
                      "items": manifest["items_completed"], "errors": manifest["errors"]}, ensure_ascii=False))
    raise SystemExit(0 if manifest["complete"] else 1)


if __name__ == "__main__": main()
