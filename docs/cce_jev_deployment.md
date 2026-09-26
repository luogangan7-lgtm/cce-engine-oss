# CCE Decider candidate ("local Jev") — GitHub-only deployment

Status ladder (each level is reported separately, never inferred from the next):

| level | meaning | how it is proven |
|---|---|---|
| CODE_READY | contracts, compiler, guard, budget, coverage, adapter, 3 workflows, pure tests | `cce-jev-contract.yml` green; `tests/test_cce_jev_boundary.py` green in the existing suite |
| ASSET_LOCK_READY ✅ 2026-09-25 | `locks/model.assets.lock.json` READY + `runtime-cpu.lock.txt` + `cpu-runtime.lock.json` READY, generated on a GitHub runner and reviewed | prepare run https://github.com/luogangan7-lgtm/cce-engine-oss/actions/runs/36032048288 (4 min 05 s job; 3.78 GB downloaded in 25 s; 0 forwards; torch 2.14.0+cpu / transformers 5.17.0; container network blocked) |
| GITHUB_RUNTIME_SMOKE_PASSED ✅ 2026-09-27 | one real load + ≥1 real forward on `ubuntu-24.04`, network isolation verified, report artifact | eval run https://github.com/luogangan7-lgtm/cce-engine-oss/actions/runs/36265705004 (archived `archive/36265705004`): 1 load, 11 real forwards (counted at `slot_logits` == ledger), 1,881,825,088 params float32 CPU, cgroup memory.max 12 GiB / swap 0 / cpu 3 / pids 256, network blocked (DNS + IP) |
| S0_CANDIDATE_AVAILABLE ✅ 2026-09-27 | `reports/<run>/s0_candidates.jsonl` with full distributions for a registered suite | 11 rows, raw logits for valid candidates only, coverage 18/18 (DECLARED 1 · UNOBSERVABLE 6 · OK 8 · SEMANTIC_UNKNOWN 3) |
| SEMANTIC_ACCEPTANCE ❌ FAILED 2026-09-27 | smoke semantic assertions evaluated; 2 items never prove accuracy | 7/11 inside the pre-registered accepted sets. Fails: 情绪余温 ×2 (picked 负向余温 / 中性; the cold-read structural rule allows only 首轮无余温 / 未知), 进程位置 on the no-information item (已决定在执行 0.705), 触发事件 on item 1 (刚花过钱 0.722 vs 受挫/出故障 0.256; text literally contains both a purchase and a failure — gold was single-valued, left unchanged after seeing results) |
| PRODUCTION_ENABLED | **not part of this delivery**; requires a separate measurement-procedure decision | — |

## Smoke time and resource account (eval run 36265705004)

| segment | seconds |
|---|---:|
| queue (created → admit start) | 5 |
| admit (permit + atomic ref) | 5 |
| checkout / artifact / python | 4 |
| cache restore (2.94 GB compressed bundle) | 31 |
| bundle verify (7 files sha256) | 3 |
| runtime image build from recipe | 70 |
| container: tokenizer load | 3.2 |
| container: model load | 2.0 |
| container: first real forward | 3.3 |
| container: remaining 10 forwards | 30.4 |
| container wall | 38.9 |
| report + upload | 1 |
| evaluate job total | 155 |

Peak RSS of the model process: 11,778,904 KiB (≈ 11.2 GiB) against a 12 GiB cgroup limit — **94 % of the limit with float32 weights**. Any larger input, batch > 1, or second model object will OOM; bf16 on CPU or a larger runner is the upgrade path, each needing a new identity and a new permit.

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
