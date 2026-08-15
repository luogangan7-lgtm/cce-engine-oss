#!/usr/bin/env python3
"""Install the single versioned CCE skill and prune managed legacy links."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


SKILL_NAME = "cce"
LEGACY_SKILLS = (
    "b2b-outreach-composer",
    "b2c-consumer-composer",
    "cce-github-client",
    "viral-amplification-architect",
    "viral-behavior-signals",
    "viral-comment-intelligence",
    "viral-content-generator",
    "viral-content-recon",
    "viral-copy-decoder",
    "viral-dialogue-decoder",
    "viral-performance-audit",
    "viral-person-decoder",
    "viral-psychology-excavator",
    "viral-structure-decoder",
    "viral-visual-forensics",
)


def _managed_legacy(target: Path, source_root: Path) -> bool:
    if not target.is_symlink():
        return False
    try:
        resolved = target.resolve()
    except OSError:
        return False
    return resolved.parent == source_root


def check(source_root: Path, target_root: Path) -> dict[str, object]:
    source = source_root / SKILL_NAME
    target = target_root / SKILL_NAME
    drift: dict[str, str] = {}
    if not (source / "SKILL.md").is_file():
        drift[SKILL_NAME] = "missing versioned source"
    if not target.is_symlink():
        drift[SKILL_NAME] = "not an exact symlink"
    elif target.resolve() != source.resolve():
        drift[SKILL_NAME] = f"points to {target.resolve()}"
    for name in LEGACY_SKILLS:
        legacy = target_root / name
        if legacy.exists() or legacy.is_symlink():
            drift[name] = "legacy CCE skill still installed"
    return {"ok": not drift, "visible_skills": 1, "drift": drift}


def install(source_root: Path, target_root: Path) -> dict[str, object]:
    source_root = source_root.resolve()
    target_root = target_root.resolve()
    source = source_root / SKILL_NAME
    if not (source / "SKILL.md").is_file():
        raise RuntimeError(f"missing versioned skill: {source}")
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / SKILL_NAME
    if target.exists() or target.is_symlink():
        if not target.is_symlink() or target.resolve() != source.resolve():
            raise RuntimeError(f"refusing to replace unmanaged target: {target}")
    else:
        target.symlink_to(source, target_is_directory=True)

    pruned: list[tuple[Path, str]] = []
    try:
        for name in LEGACY_SKILLS:
            legacy = target_root / name
            if not (legacy.exists() or legacy.is_symlink()):
                continue
            if not _managed_legacy(legacy, source_root):
                raise RuntimeError(f"refusing to prune unmanaged legacy target: {legacy}")
            link_target = os.readlink(legacy)
            legacy.unlink()
            pruned.append((legacy, link_target))
        result = check(source_root, target_root)
        if not result["ok"]:
            raise RuntimeError(f"post-install drift: {result['drift']}")
        return {**result, "pruned": len(pruned)}
    except Exception:
        for legacy, link_target in reversed(pruned):
            legacy.symlink_to(link_target, target_is_directory=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path,
                        default=Path(__file__).resolve().parents[1] / "skills")
    parser.add_argument("--target-root", type=Path,
                        default=Path.home() / ".codex" / "skills")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--install", action="store_true")
    args = parser.parse_args()
    try:
        result = check(args.source_root.resolve(), args.target_root.resolve()) \
            if args.check else install(args.source_root, args.target_root)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        raise SystemExit(0 if result["ok"] else 1)
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
