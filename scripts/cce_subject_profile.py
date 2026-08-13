#!/usr/bin/env python3
"""Deprecated module name; produce auxiliary reference cards, not subjects.

Cards retain public-history evidence that can help define or interpret a later
window.  They are neither versioned people nor inputs to CCE measurement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CARD_SOURCE = ROOT / "docs" / "subject_cards_v3_20260813.json"


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def top_components(text: str) -> dict[str, Any]:
    components = []
    for token in str(text or "").split():
        match = re.match(r"(.+?)(\d+(?:\.\d+)?)$", token)
        if match:
            components.append({"label": match.group(1), "value": float(match.group(2))})
    return {"components": components, "is_complete_distribution": False,
            "known_mass": round(sum(item["value"] for item in components), 6)}


def card_id(handle: str) -> str:
    return f"reference_card:reddit:{handle}"


def build_from_cards(cards: dict[str, Any], source: Path) -> dict[str, Any]:
    records = []
    for handle, card in cards.items():
        identities = [{"label": label, "first_seen": detail.get("首见"), "last_seen": detail.get("末见"),
                       "mentions": detail.get("提及"), "assertion": "observed_public_history"}
                      for label, detail in (card.get("③身份库(append-only,带考古)") or {}).items()]
        confidence = card.get("⑦置信") or {}
        records.append({
            "id": card_id(handle), "card_kind": "public_history_reference",
            "provenance": {"source": str(source), "source_hash": sha256(source),
                           "adapter": "cce_subject_profile(deprecated_name)", "adapter_version": "2.0.0"},
            "baseline_evidence": {"desire": top_components(card.get("①欲望基线")),
                                  "need": top_components(card.get("②需求配置")),
                                  "scope": "public_history_stratified_sample"},
            "identity_ledger": identities, "behavior_history": card.get("④行为频率") or {},
            "context_evidence": (card.get("⑤激活函数") or {}),
            "relationship_evidence": {"value": card.get("⑥关系阶段(M3)"), "assertion": "inferred"},
            "confidence": {"readouts": confidence.get("读出n"), "contexts": confidence.get("情境数"),
                           "split_half_js_desire": confidence.get("折半JS欲望"), "status": confidence.get("合格线")},
            "limits": ["not a subject", "not a population sample", "not a CCE input", "not a response signature"],
        })
    return {"kind": "cce.reference_card_collection.v1", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cards": records, "segment_construction_status": "blocked_no_validated_response_signature_matrix"}


def validate_collection(collection: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if collection.get("kind") != "cce.reference_card_collection.v1":
        errors.append("kind must be cce.reference_card_collection.v1")
    ids: set[str] = set()
    for index, record in enumerate(collection.get("cards", [])):
        p = f"cards[{index}]"
        if record.get("id") in ids: errors.append(f"{p}.id must be unique")
        ids.add(record.get("id"))
        for field in ("id", "card_kind", "provenance", "baseline_evidence", "limits"):
            if not record.get(field): errors.append(f"{p} missing {field}")
        if "profile_version" in record or record.get("subject_type"):
            errors.append(f"{p} must not reify a reference card as a versioned subject")
    return {"ok": not errors, "errors": errors, "counts": {"reference_cards": len(collection.get("cards", []))}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, default=CARD_SOURCE)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    collection = build_from_cards(json.loads(args.cards.read_text(encoding="utf-8")), args.cards)
    verdict = validate_collection(collection)
    if not verdict["ok"]: raise SystemExit("invalid reference cards:\n" + "\n".join(verdict["errors"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(collection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), **verdict["counts"]}, ensure_ascii=False))


if __name__ == "__main__": main()
