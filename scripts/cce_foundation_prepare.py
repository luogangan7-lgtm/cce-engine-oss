#!/usr/bin/env python3
"""Prepare the context-bound CCE measurement packet and optional reference cards.

The cards are deliberately emitted beside, not inside, the measurement packet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cce_case_assemble import build_model_input, build_request
from cce_contract import validate_case
from cce_foundation_adapter import adapt
from cce_subject_profile import build_from_cards, validate_collection


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parse-artifact", type=Path, required=True)
    parser.add_argument("--context-snapshot", type=Path, required=True,
                        help="JSON context snapshot produced by a platform/manual context adapter")
    parser.add_argument("--cards", type=Path, help="optional auxiliary reference-card source")
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    evidence = adapt(json.loads(args.parse_artifact.read_text(encoding="utf-8")), args.parse_artifact)
    context_snapshot = json.loads(args.context_snapshot.read_text(encoding="utf-8"))
    evidence["context_snapshots"] = [context_snapshot]
    request = build_request(evidence, "event_packet@v1")
    verdict = validate_case(request)
    if not verdict["ok"]: raise SystemExit("invalid CCE request:\n" + "\n".join(verdict["errors"]))
    model_input = build_model_input(request)
    paths = {
        "evidence": args.outdir / "01_evidence.json",
        "model_input": args.outdir / "02_cce_model_input.json",
        "measurement_case": args.outdir / "03_measurement_case.json",
    }
    write(paths["evidence"], evidence)
    write(paths["model_input"], model_input)
    write(paths["measurement_case"], request)
    cards_status = "NOT_SUPPLIED"
    if args.cards:
        cards = build_from_cards(json.loads(args.cards.read_text(encoding="utf-8")), args.cards)
        card_verdict = validate_collection(cards)
        if not card_verdict["ok"]: raise SystemExit("invalid reference cards:\n" + "\n".join(card_verdict["errors"]))
        paths["reference_cards"] = args.outdir / "04_reference_cards.json"; write(paths["reference_cards"], cards)
        cards_status = "AUXILIARY_ONLY"
    manifest = {"kind": "cce.foundation.prepare_manifest.v2", "status": "READY_FOR_CONTENT_MEASUREMENT_ADAPTER",
                "measurement_boundary": "The CCE adapter consumes only the anonymous model_input projection. Subject join keys/cards/windows stay downstream.",
                "source": {"parse_artifact": str(args.parse_artifact), "context_snapshot": str(args.context_snapshot),
                           "cards": str(args.cards) if args.cards else None},
                "artifacts": {key: {"path": str(value), "sha256_16": fingerprint(value)} for key, value in paths.items()},
                "counts": verdict["counts"], "gates": {"contract": "PASS", "context_bound": "PASS", "outcome_leakage": "PASS", "reference_cards": cards_status}}
    write(args.outdir / "manifest.json", manifest); print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
