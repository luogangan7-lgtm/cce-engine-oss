# CCE Decider candidate ("local Jev") — GitHub-only deployment

Status ladder (each level is reported separately, never inferred from the next):

| level | meaning | how it is proven |
|---|---|---|
| CODE_READY | contracts, compiler, guard, budget, coverage, adapter, 3 workflows, pure tests | `cce-jev-contract.yml` green; `tests/test_cce_jev_boundary.py` green in the existing suite |
| ASSET_LOCK_READY | `locks/model.assets.lock.json` READY + `runtime-cpu.lock.txt` + `cpu-runtime.lock.json` READY, all generated on a GitHub runner and reviewed | prepare run URL + committed locks |
| GITHUB_RUNTIME_SMOKE_PASSED | one real load + ≥1 real forward on `ubuntu-24.04`, network isolation verified, report artifact | eval run URL, `execution_receipt.json` |
| S0_CANDIDATE_AVAILABLE | `reports/<run>/s0_candidates.jsonl` with full distributions for a registered suite | eval artifact |
| SEMANTIC_ACCEPTANCE_PENDING | smoke semantic assertions evaluated; 2 items never prove accuracy | `report.json.semantic_acceptance` |
| PRODUCTION_ENABLED | **not part of this delivery**; requires a separate measurement-procedure decision | — |

## What runs where

* **Local machine**: only pure Python (stdlib) tests with a fake backend / fake tokenizer. `cli.py eval|prepare` refuse
  with `EXECUTION_LOCATION_FORBIDDEN` before any import or download. No `from_pretrained`, no `hf_hub_download`, no torch.
* **GitHub-hosted `ubuntu-24.04`** (free for this public repo; no paid runners, no GPU): model file verification, CPU
  dependency lock, Docker image build, model download, one load, the smoke forwards. One load per job. No fallback to
  TypeSafe / MiniMax anywhere in `experiments/jev`.

## Workflows

| workflow | trigger | model? | permissions |
|---|---|---|---|
| `cce-jev-contract.yml` | push / PR on candidate paths | no | `contents: read` |
| `cce-jev-prepare.yml` | manual, `permit_id` | download + hash only, `model_forwards=0` | admit `contents: write` (ref only) / prepare `contents: read` |
| `cce-jev-eval.yml` | manual, `suite_id` (choice) + `permit_id` | one load, ≤16 forwards in `--network none` container | admit `contents: write` (ref only) / evaluate `contents: read` |

All official actions are pinned to full commit SHAs recorded in `locks/actions.lock.json`; `persist-credentials: false`;
inputs reach scripts only through `env:`; the model container inherits no `GITHUB_TOKEN` and no model API secret.

## Order of operations

1. **Phase A (this PR)** — code + pure tests. Exit: reviewable diff, contract workflow green, zero model bytes locally.
2. **Phase B — prepare** — owner approves one prepare permit (§10 caps: ≤5 GiB model, ≤3 GiB deps, 1 run, 35 min,
   0 forwards). Output: `model.assets.lock.proposal.json`, `runtime-cpu.lock.txt`, image id, SBOM, import smoke with
   network-isolation proof. Claude commits the reviewed locks (status → READY) in a follow-up PR.
3. **Phase C — smoke eval** — owner approves one eval permit bound to the reviewed locks and `s0-smoke-v1`
   (2 items, 11 model questions, ≤16 forwards, ≤2048 tokens/row, 3 CPU / 12 GiB, 1200 s). Output: report artifact.
4. **Phase D** — usage: *Actions → CCE Decider Candidate Evaluation → suite → permit → Run workflow → Summary / artifact*.

## Adapter contract (why it is strict)

* `DecisionRequest` keeps candidate order; `questions_sha256` (ontology) and `input_sha256` (text) are separate.
* `plan_work.prepare` renders with the upstream renderer, checks the state prefix is byte-identical after tokenization,
  refuses reordering, refuses `INPUT_TOO_LONG` (no `[:2000]` slicing, no chunking); the same `PreparedRows` are executed.
* `backend_decider` constructs `Decider(path, device="cpu", dtype=float32, use_graphs=False, temperature=<locked>)`,
  verifies the **effective** config (`T`, eager, isolated_levels, name `decider-v10`, dtype), wraps `slot_logits` so every
  backbone forward is counted, reserves budget **before** each forward, re-hashes the row at the `collate` boundary, and
  stores raw logits only for valid candidates.
* `run_suite` fixes `expected_items.json` before inference; every item×question ends in exactly one status; failures stay
  in the denominator; execution status ≠ semantic acceptance; `production_eligible` is always `false` here.
* Reports contain no source text: only ids, candidate labels, distributions, hashes, timings.

## Not done in this delivery (by design)

* No prepare / eval run has been executed (needs owner permits + budget approval).
* `model.assets.lock.json` and the runtime locks are `REQUIRES_GITHUB_PREPARE`; `permits/` is empty.
* The real-upstream rendering path is only exercised on GitHub; locally a shape-identical fake upstream is used.
* Smoke gold values are human-authored before any model run and marked for owner review in the suite manifest.
