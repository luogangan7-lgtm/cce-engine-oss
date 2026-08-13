#!/usr/bin/env python3
"""Validate the stable platform adapter and its time-bound runtime space.

The adapter owns protocol/field normalization.  A subreddit, channel, group or
account is a dynamic context value and must never be used as an adapter id.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "platform_adapter_registry_v1.json"


def _instant(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def validate_platform_context(platform: Any, adapter: Any, surface: Any,
                              path: str = "context") -> dict[str, Any]:
    errors: list[str] = []
    adapters = registry().get("adapters", {})
    if not isinstance(platform, str) or platform not in adapters:
        errors.append(f"{path}.platform is not backed by a registered platform adapter")
        return {"ok": False, "errors": errors, "canonical": None}
    spec = adapters[platform]
    if not isinstance(adapter, dict):
        errors.append(f"{path}.platform_adapter must be an object")
    else:
        if adapter.get("id") != spec.get("adapter_id"):
            errors.append(f"{path}.platform_adapter.id must equal {spec.get('adapter_id')!r}")
        if adapter.get("version") != spec.get("adapter_version"):
            errors.append(f"{path}.platform_adapter.version must equal {spec.get('adapter_version')!r}")
    if not isinstance(surface, dict):
        errors.append(f"{path}.surface must be an object")
        return {"ok": False, "errors": errors, "canonical": None}
    kind, surface_id = surface.get("kind"), surface.get("id")
    pattern = (spec.get("space_patterns") or {}).get(kind)
    if not isinstance(pattern, str):
        errors.append(f"{path}.surface.kind {kind!r} is unsupported by {platform}")
    elif not isinstance(surface_id, str) or re.fullmatch(pattern, surface_id) is None:
        errors.append(f"{path}.surface.id {surface_id!r} is invalid for {platform}/{kind}")
    if not _instant(surface.get("observed_at")):
        errors.append(f"{path}.surface.observed_at must be ISO-8601")
    canonical = None if errors else {
        "platform": {"id": platform, "adapter": adapter["id"], "adapter_version": adapter["version"]},
        "space": {"kind": kind, "id": surface_id, "observed_at": surface["observed_at"]},
    }
    return {"ok": not errors, "errors": errors, "canonical": canonical}
