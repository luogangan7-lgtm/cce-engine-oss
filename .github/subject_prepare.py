#!/usr/bin/env python3
"""Validate a subject-chain payload and materialize its parallel CCE work items."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cce_contract import validate_case  # noqa: E402
from cce_response_chain import build_dispatch  # noqa: E402


def load_object(name: str) -> dict:
    raw = os.environ.get(name, "")
    if not raw.strip():
        raise ValueError(f"{name} is required")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    chain = load_object("CHAIN_JSON")
    responses = load_object("RESPONSES_JSON")
    dispatch = build_dispatch(responses, chain)
    package = ROOT / "subject-package"
    package.mkdir(exist_ok=True)
    items = dispatch["client_payload"]["items"]
    write(package / "chain.json", chain)
    write(package / "responses.json", responses)
    write(package / "dispatch.json", dispatch)
    write(package / "items.json", items)
    measurement_raw = os.environ.get("MEASUREMENT_CASE_JSON", "").strip()
    if measurement_raw and measurement_raw != "null":
        measurement_case = json.loads(measurement_raw)
        verdict = validate_case(measurement_case)
        if not verdict["ok"]:
            raise ValueError("invalid measurement case: " + "; ".join(verdict["errors"]))
        if (measurement_case.get("content") or {}).get("id") != (chain.get("content") or {}).get("id"):
            raise ValueError("measurement case and subject chain must use the same content id")
        write(package / "measurement-case.json", measurement_case)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write("indices=" + json.dumps(list(range(len(items)))) + "\n")
    print(json.dumps({"content_ref": responses.get("content_ref"), "items": len(items)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
