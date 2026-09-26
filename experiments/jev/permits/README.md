# Permits (single-use, owner-approved)

A permit is a JSON file `<permit_id>.json` committed here **by the owner** when approving one GitHub run.
Claude never creates or marks a permit as approved. `.github/scripts/cce_jev_admit.py` consumes it atomically by
creating `refs/tags/cce-jev-consumed/<permit_id>`; a second trigger or a "Re-run jobs" is refused before any download.

```json
{
 "permit_id": "prepare-2026-09-25-1",
 "owner_approval_reference": "chat 2026-09-25 / issue #N",
 "expiry": "2026-10-02T00:00:00+00:00",
 "repository": "luogangan7-lgtm/cce-engine-oss",
 "workflow_id": "cce-jev-prepare.yml",
 "mode": "prepare",
 "max_runs": 1,
 "max_attempts": 1,
 "model_source_lock_sha256": "<sha256 of experiments/jev/locks/model.source.lock.json>",
 "asset_lock_sha256": "NOT_APPLICABLE_PREPARE",
 "runtime_lock_sha256": "NOT_APPLICABLE_PREPARE",
 "resource_policy": "asset_prepare.json",
 "resource_policy_sha256": "<sha256 of experiments/jev/policies/asset_prepare.json>"
}
```

An eval permit additionally carries `suite_id`, `suite_sha256`, the real `asset_lock_sha256` (lock status READY) and
`runtime_lock_sha256` (of `locks/runtime-cpu.lock.txt`). Its `resource_policy` must equal the `policy` in
`suites/<suite_id>.manifest.json` (`cpu_smoke.json` for s0-smoke-v1, `cpu_compare.json` for s0-compare-v1); admit refuses
a mismatch, runs the stdlib `cli.py plan --suite`, and confirms the model bundle cache exists — all **before** consuming.
The execution commit is fixed by the admit receipt at run time, never written into the permit itself.
