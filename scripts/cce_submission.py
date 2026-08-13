#!/usr/bin/env python3
"""Validate and materialize the only supported production CCE submission envelope."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from cce_response_chain import build_dispatch, validate_response_source
from cce_window_chain import validate_chain


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"
PROFILES = {"outbound_post", "outbound_reply", "subject_chain"}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_ITEMS = 8
AUDIENCE_MIN_WORDS = 1000
AUDIENCE_MIN_UTTERANCES = 30


def text_sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _instant(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _required(obj: Any, fields: tuple[str, ...], path: str, errors: list[str]) -> None:
    if not isinstance(obj, dict):
        errors.append(f"{path} must be an object")
        return
    for field in fields:
        if obj.get(field) in (None, "", []):
            errors.append(f"{path}.{field} is required")


def _exact_text(obj: Any, path: str, errors: list[str]) -> None:
    _required(obj, ("text", "text_sha256"), path, errors)
    if not isinstance(obj, dict):
        return
    text, digest = obj.get("text"), obj.get("text_sha256")
    if isinstance(digest, str) and not SHA256.fullmatch(digest):
        errors.append(f"{path}.text_sha256 must use sha256:<64 lowercase hex>")
    if isinstance(text, str) and isinstance(digest, str) and text_sha256(text) != digest:
        errors.append(f"{path}.text_sha256 does not match exact UTF-8 text")


def _context(value: Any, path: str, taxonomy: dict[str, list[str]], errors: list[str]) -> None:
    _required(value, ("summary", "declaration"), path, errors)
    if not isinstance(value, dict) or not isinstance(value.get("declaration"), dict):
        return
    declaration = value["declaration"]
    if not declaration:
        errors.append(f"{path}.declaration must not be empty")
    for key, item in declaration.items():
        if key not in taxonomy:
            errors.append(f"{path}.declaration unknown facet {key!r}")
        elif item not in taxonomy[key]:
            errors.append(f"{path}.declaration invalid {key}={item!r}")


def _audience(value: Any, path: str, errors: list[str]) -> str | None:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return None
    expected = value.get("sha256")
    if not isinstance(expected, str) or not SHA256.fullmatch(expected):
        errors.append(f"{path}.sha256 must use sha256:<64 lowercase hex>")
    corpus: str | None = None
    if value.get("corpus_path"):
        raw_path = Path(str(value["corpus_path"]))
        if raw_path.is_absolute() or ".." in raw_path.parts:
            errors.append(f"{path}.corpus_path must be a safe repository-relative path")
        else:
            resolved = ROOT / raw_path
            if not resolved.is_file():
                errors.append(f"{path}.corpus_path does not exist")
            else:
                corpus = resolved.read_text(encoding="utf-8")
                if expected and file_sha256(resolved) != expected:
                    errors.append(f"{path}.sha256 does not match corpus_path bytes")
    elif isinstance(value.get("utterances"), list):
        utterances = value["utterances"]
        if not all(isinstance(row, str) and row.strip() for row in utterances):
            errors.append(f"{path}.utterances must contain non-empty strings")
        corpus = "\n".join(utterances)
        if expected and text_sha256(corpus) != expected:
            errors.append(f"{path}.sha256 does not match newline-joined utterances")
    else:
        errors.append(f"{path} requires corpus_path or utterances")
    if corpus is not None:
        rows = [row for row in corpus.splitlines() if len(row.strip()) > 10]
        words = len(corpus.split())
        if len(rows) < AUDIENCE_MIN_UTTERANCES or words < AUDIENCE_MIN_WORDS:
            errors.append(f"{path} requires >=30 utterances and >=1000 words; got {len(rows)}/{words}")
    return corpus


def _repo_json(value: dict[str, Any], inline_key: str, path_key: str,
               sha_key: str, errors: list[str]) -> dict[str, Any] | None:
    inline = value.get(inline_key)
    if isinstance(inline, dict):
        return inline
    raw_path, expected = value.get(path_key), value.get(sha_key)
    if not raw_path:
        errors.append(f"{inline_key} or {path_key} is required")
        return None
    path = Path(str(raw_path))
    if path.is_absolute() or ".." in path.parts:
        errors.append(f"{path_key} must be a safe repository-relative path")
        return None
    resolved = ROOT / path
    if not resolved.is_file():
        errors.append(f"{path_key} does not exist")
        return None
    if not isinstance(expected, str) or not SHA256.fullmatch(expected):
        errors.append(f"{sha_key} must use sha256:<64 lowercase hex>")
    elif file_sha256(resolved) != expected:
        errors.append(f"{sha_key} does not match {path_key} bytes")
    try:
        result = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path_key} is not valid JSON: {exc}")
        return None
    if not isinstance(result, dict):
        errors.append(f"{path_key} must contain a JSON object")
        return None
    return result


def validate_submission(value: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if value.get("kind") != "cce.submission.v1": errors.append("kind must be cce.submission.v1")
    if value.get("schema_version") != SCHEMA_VERSION: errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(value.get("submission_id"), str) or not SAFE_ID.fullmatch(value["submission_id"]):
        errors.append("submission_id must be a safe 3-128 character identifier")
    if value.get("profile") not in PROFILES: errors.append(f"profile must be one of {sorted(PROFILES)}")
    if not _instant(value.get("submitted_at")): errors.append("submitted_at must be ISO-8601")
    _required(value.get("producer"), ("system", "trace_id"), "producer", errors)

    taxonomy_file = ROOT / "config" / "context_taxonomy.json"
    taxonomy_data = json.loads(taxonomy_file.read_text(encoding="utf-8"))
    taxonomy = {row["key"]: row["values"] for row in taxonomy_data["facets"]}
    profile = value.get("profile")
    normalized_items: list[dict[str, Any]] = []

    if profile in {"outbound_post", "outbound_reply"}:
        items = value.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
            errors.append(f"items must contain 1-{MAX_ITEMS} entries")
            items = []
        seen: set[str] = set()
        for index, item in enumerate(items):
            path = f"items[{index}]"
            _required(item, ("job_id", "content_id", "platform", "surface", "domain", "language", "speaker_role", "context"), path, errors)
            if not isinstance(item, dict): continue
            job_id = item.get("job_id")
            if not isinstance(job_id, str) or not SAFE_ID.fullmatch(job_id): errors.append(f"{path}.job_id is invalid")
            if job_id in seen: errors.append(f"{path}.job_id is duplicated")
            seen.add(job_id)
            if not isinstance(item.get("content_id"), str) or not SAFE_ID.fullmatch(item["content_id"]):
                errors.append(f"{path}.content_id is invalid")
            if item.get("domain") != "hearing_aid":
                errors.append(f"{path}.domain must be hearing_aid for the current adapter")
            _context(item.get("context"), f"{path}.context", taxonomy, errors)
            context = item.get("context") if isinstance(item.get("context"), dict) else {}
            meta = {"submission_id": value.get("submission_id"), "job_id": job_id,
                    "content_id": item.get("content_id"), "profile": profile,
                    "schema_version": SCHEMA_VERSION, "platform": item.get("platform"),
                    "surface": item.get("surface"), "domain": item.get("domain"),
                    "speaker_role": item.get("speaker_role"), "language": item.get("language")}
            if profile == "outbound_post":
                if (item.get("platform"), item.get("surface"), item.get("speaker_role")) != (
                        "reddit", "r/HearingAids", "otc_hearing_aid_oem"):
                    errors.append(f"{path} is outside the frozen r/HearingAids OTC-OEM post adapter")
                objective = item.get("objective")
                _required(objective, ("metric",), f"{path}.objective", errors)
                if isinstance(objective, dict) and objective.get("metric") != "model_comment_rate_per_1000_views":
                    errors.append(f"{path}.objective.metric is outside the frozen s7/s8 ruler")
                _exact_text(item, path, errors)
                audience = _audience(item.get("audience"), f"{path}.audience", errors)
                comparator = item.get("comparator")
                _required(comparator, ("content_id", "text", "text_sha256"), f"{path}.comparator", errors)
                _exact_text(comparator, f"{path}.comparator", errors)
                if isinstance(comparator, dict) and len(str(comparator.get("text", "")).split()) < 20:
                    errors.append(f"{path}.comparator.text must contain at least 20 words")
                normalized_items.append({"mode": "post", "text": item.get("text"),
                    "context": context.get("summary"), "context_decl": json.dumps(context.get("declaration", {}), ensure_ascii=False),
                    "audience": audience or "", "ref_post": (comparator or {}).get("text", ""),
                    "ref_tag": job_id, "_meta": {**meta, "objective": objective,
                    "text_sha256": item.get("text_sha256")}})
            else:
                reader, draft = item.get("reader"), item.get("draft")
                _required(reader, ("actor_ref", "evidence_ref", "observed_at", "source", "text", "text_sha256"), f"{path}.reader", errors)
                _exact_text(reader, f"{path}.reader", errors); _exact_text(draft, f"{path}.draft", errors)
                if isinstance(reader, dict) and not _instant(reader.get("observed_at")):
                    errors.append(f"{path}.reader.observed_at must be ISO-8601")
                normalized_items.append({"mode": "reply", "text": (draft or {}).get("text", ""),
                    "reader_text": (reader or {}).get("text", ""), "context": context.get("summary"),
                    "context_decl": json.dumps(context.get("declaration", {}), ensure_ascii=False), "ref_tag": job_id,
                    "translated": bool(item.get("translated")), "_meta": {**meta,
                    "text_sha256": (draft or {}).get("text_sha256"), "reader_text_sha256": (reader or {}).get("text_sha256"),
                    "reader_actor_ref": (reader or {}).get("actor_ref"), "reader_evidence_ref": (reader or {}).get("evidence_ref")}})

    subject_dispatch = None
    resolved_chain = None
    resolved_source = None
    if profile == "subject_chain":
        chain = _repo_json(value, "subject_chain", "subject_chain_path", "subject_chain_sha256", errors)
        source = _repo_json(value, "response_source", "response_source_path", "response_source_sha256", errors)
        resolved_chain, resolved_source = chain, source
        if not isinstance(chain, dict) or not isinstance(source, dict):
            errors.append("subject_chain profile requires subject_chain and response_source objects")
        else:
            chain_verdict = validate_chain(chain)
            source_verdict = validate_response_source(source, chain)
            if not chain_verdict["ok"]: errors.extend(f"subject_chain: {row}" for row in chain_verdict["errors"])
            if not source_verdict["ok"]: errors.extend(f"response_source: {row}" for row in source_verdict["errors"])
            responses = source.get("responses") or []
            if not 1 <= len(responses) <= MAX_ITEMS: errors.append(f"response_source.responses must contain 1-{MAX_ITEMS} entries")
            for index, response in enumerate(responses):
                _exact_text(response, f"response_source.responses[{index}]", errors)
            if not errors:
                subject_dispatch = build_dispatch(source, chain)

    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "normalized": {"kind": "cce.normalized_submission.v1", "schema_version": SCHEMA_VERSION,
                "submission_id": value.get("submission_id"), "profile": profile,
                "producer": value.get("producer"), "items": normalized_items,
                "subject_chain": resolved_chain if profile == "subject_chain" else None,
                "response_source": resolved_source if profile == "subject_chain" else None,
                "subject_dispatch": subject_dispatch}}


def write_package(value: dict[str, Any], outdir: Path) -> dict[str, Any]:
    verdict = validate_submission(value)
    if not verdict["ok"]: raise ValueError("invalid submission: " + "; ".join(verdict["errors"]))
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "submission.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    normalized = verdict["normalized"]
    items = normalized.get("items") or ((normalized.get("subject_dispatch") or {}).get("client_payload") or {}).get("items") or []
    if normalized["profile"] == "subject_chain":
        content_id = ((normalized.get("subject_chain") or {}).get("content") or {}).get("id")
        responses = (normalized.get("response_source") or {}).get("responses") or []
        for item, response in zip(items, responses):
            item["_meta"] = {"submission_id": normalized["submission_id"],
                "job_id": response.get("evidence_ref"), "content_id": content_id,
                "profile": "subject_chain", "schema_version": SCHEMA_VERSION,
                "text_sha256": response.get("text_sha256"), "actor_ref": response.get("actor_ref"),
                "evidence_ref": response.get("evidence_ref")}
        normalized["items"] = items
    (outdir / "normalized.json").write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (outdir / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"submission_id": normalized["submission_id"], "profile": normalized["profile"],
            "items": len(items), "indices": list(range(len(items)))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path)
    parser.add_argument("--outdir", type=Path)
    args = parser.parse_args()
    value = json.loads(args.submission.read_text(encoding="utf-8"))
    if args.outdir:
        result = write_package(value, args.outdir)
        print(json.dumps(result, ensure_ascii=False))
        return
    verdict = validate_submission(value)
    print(json.dumps({key: val for key, val in verdict.items() if key != "normalized"}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if verdict["ok"] else 1)


if __name__ == "__main__": main()
