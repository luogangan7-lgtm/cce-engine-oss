#!/usr/bin/env python3
"""Submit CCE to GitHub Actions and verify exact-input aggregate artifacts."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

DEFAULT_REPO = "luogangan7-lgtm/cce-engine"
WORKFLOW = "cce-submit.yml"


class ClientError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClientError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ClientError(f"{path} must contain a JSON object")
    return value


def _repo_root(explicit: Path | None) -> Path:
    if explicit:
        root = explicit.resolve()
    else:
        probe = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], text=True, capture_output=True
        )
        if probe.returncode:
            raise ClientError("not inside cce-engine; pass --repo-root")
        root = Path(probe.stdout.strip()).resolve()
    if not (root / "scripts" / "cce_submission.py").is_file():
        raise ClientError(f"not a cce-engine checkout: {root}")
    return root


def _validated_package(submission: Path, root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with tempfile.TemporaryDirectory(prefix="cce-client-") as raw:
        outdir = Path(raw)
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / "cce_submission.py"),
             str(submission.resolve()), "--outdir", str(outdir)],
            cwd=root, text=True, capture_output=True,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            raise ClientError(f"submission contract failed: {detail}")
        normalized = _json(outdir / "normalized.json")
        items_raw = json.loads((outdir / "items.json").read_text(encoding="utf-8"))
        if not isinstance(items_raw, list) or not items_raw:
            raise ClientError("validated submission produced no jobs")
        return normalized, items_raw


def _expected(normalized: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for item in items:
        meta = item.get("_meta") if isinstance(item, dict) else None
        if not isinstance(meta, dict):
            raise ClientError("normalized job is missing _meta")
        job_id, digest = meta.get("job_id"), meta.get("text_sha256")
        if not isinstance(job_id, str) or not isinstance(digest, str):
            raise ClientError("normalized job is missing job_id or text_sha256")
        if job_id in expected:
            raise ClientError(f"duplicate normalized job_id: {job_id}")
        expected[job_id] = digest
    return expected


def verify_input(submission: Path, root: Path) -> dict[str, Any]:
    normalized, items = _validated_package(submission, root)
    expected = _expected(normalized, items)
    return {
        "ok": True,
        "submission_id": normalized.get("submission_id"),
        "profile": normalized.get("profile"),
        "items": len(expected),
        "text_sha256": expected,
    }


def verify_result(submission: Path, result_dir: Path, root: Path,
                  run_url: str | None = None) -> dict[str, Any]:
    normalized, items = _validated_package(submission, root)
    expected = _expected(normalized, items)
    manifest = _json(result_dir / "workflow-manifest.json")
    errors: list[str] = []
    if manifest.get("kind") != "cce.workflow_manifest.v1":
        errors.append("manifest kind mismatch")
    if manifest.get("submission_id") != normalized.get("submission_id"):
        errors.append("submission_id mismatch")
    if manifest.get("profile") != normalized.get("profile"):
        errors.append("profile mismatch")
    if manifest.get("complete") is not True:
        errors.append("manifest complete is not true")
    if manifest.get("items_expected") != len(expected):
        errors.append("items_expected mismatch")
    if manifest.get("items_completed") != len(expected):
        errors.append("items_completed mismatch")
    if manifest.get("errors") not in ([], None):
        errors.append("manifest contains errors")

    jobs = manifest.get("jobs")
    actual: dict[str, dict[str, Any]] = {}
    if not isinstance(jobs, list):
        errors.append("manifest jobs must be a list")
        jobs = []
    for job in jobs:
        if not isinstance(job, dict) or not isinstance(job.get("job_id"), str):
            errors.append("manifest contains invalid job")
            continue
        if job["job_id"] in actual:
            errors.append(f"duplicate manifest job_id: {job['job_id']}")
        actual[job["job_id"]] = job
    if set(actual) != set(expected):
        errors.append("manifest job set mismatch")
    for job_id, digest in expected.items():
        job = actual.get(job_id, {})
        if job.get("profile") != normalized.get("profile"):
            errors.append(f"{job_id}: profile mismatch")
        if job.get("text_sha256") != digest:
            errors.append(f"{job_id}: text_sha256 mismatch")
        if job.get("engine_complete") is not True:
            errors.append(f"{job_id}: engine_complete is not true")
        if job.get("measurement_complete") is not True:
            errors.append(f"{job_id}: measurement_complete is not true")
        if job.get("failed_at") is not None:
            errors.append(f"{job_id}: failed_at is not null")
    if errors:
        raise ClientError("result verification failed: " + "; ".join(errors))
    return {
        "ok": True,
        "run_url": run_url,
        "submission_id": normalized.get("submission_id"),
        "profile": normalized.get("profile"),
        "complete": True,
        "items": len(expected),
        "text_sha256": expected,
        "artifact_dir": str(result_dir.resolve()),
    }


def _gh(args: list[str], *, stdin: str | None = None) -> str:
    result = subprocess.run(["gh", *args], input=stdin, text=True, capture_output=True)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise ClientError(f"gh {' '.join(args[:3])} failed: {detail}")
    return result.stdout.strip()


def _find_run(repo: str, submission_id: str, ref: str, after_id: int,
              timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    title = f"CCE {submission_id}"
    while time.monotonic() < deadline:
        raw = _gh(["run", "list", "--repo", repo, "--workflow", WORKFLOW,
                   "--event", "workflow_dispatch", "--branch", ref, "--limit", "30",
                   "--json", "databaseId,displayTitle,url,status,conclusion"])
        runs = json.loads(raw or "[]")
        matches = [row for row in runs if int(row.get("databaseId") or 0) > after_id
                   and row.get("displayTitle") == title]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ClientError(f"multiple workflow runs matched submission_id {submission_id}")
        time.sleep(2)
    raise ClientError(f"timed out locating workflow run for {submission_id}")


def run_submission(submission: Path, result_dir: Path, root: Path, repo: str,
                   ref: str, locate_timeout: int) -> dict[str, Any]:
    validated = verify_input(submission, root)
    _gh(["auth", "status", "--hostname", "github.com"])
    before_raw = _gh(["run", "list", "--repo", repo, "--workflow", WORKFLOW,
                      "--event", "workflow_dispatch", "--branch", ref, "--limit", "1",
                      "--json", "databaseId"])
    before = json.loads(before_raw or "[]")
    after_id = int(before[0]["databaseId"]) if before else 0
    payload = _json(submission)
    dispatch = {"submission_id": validated["submission_id"],
                "submission_json": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}
    _gh(["workflow", "run", WORKFLOW, "--repo", repo, "--ref", ref, "--json"],
        stdin=json.dumps(dispatch, ensure_ascii=False))
    run = _find_run(repo, str(validated["submission_id"]), ref, after_id, locate_timeout)
    run_id, run_url = str(run["databaseId"]), str(run["url"])
    _gh(["run", "watch", run_id, "--repo", repo, "--exit-status"])
    result_dir.mkdir(parents=True, exist_ok=True)
    _gh(["run", "download", run_id, "--repo", repo,
         "--name", f"cce-result-{run_id}", "--dir", str(result_dir)])
    return verify_result(submission, result_dir, root, run_url)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    p_input = sub.add_parser("verify-input")
    p_input.add_argument("submission", type=Path)
    p_result = sub.add_parser("verify-result")
    p_result.add_argument("submission", type=Path)
    p_result.add_argument("result_dir", type=Path)
    p_result.add_argument("--run-url")
    p_run = sub.add_parser("run")
    p_run.add_argument("submission", type=Path)
    p_run.add_argument("--repo", default=DEFAULT_REPO)
    p_run.add_argument("--ref", default="master")
    p_run.add_argument("--outdir", required=True, type=Path)
    p_run.add_argument("--locate-timeout", type=int, default=60)
    args = parser.parse_args()
    root = _repo_root(args.repo_root)
    try:
        if args.command == "verify-input":
            result = verify_input(args.submission, root)
        elif args.command == "verify-result":
            result = verify_result(args.submission, args.result_dir, root, args.run_url)
        else:
            result = run_submission(args.submission, args.outdir, root, args.repo,
                                    args.ref, args.locate_timeout)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    except ClientError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
