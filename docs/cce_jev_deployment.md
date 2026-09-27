# CCE Decider candidate ("local Jev") — GitHub-only deployment

Status ladder (each level is reported separately, never inferred from the next):

| level | meaning | how it is proven |
|---|---|---|
| CODE_READY | contracts, compiler, guard, budget, coverage, adapter, 3 workflows, pure tests | `cce-jev-contract.yml` green; `tests/test_cce_jev_boundary.py` green in the existing suite |
| ASSET_LOCK_READY ✅ 2026-09-25 | `locks/model.assets.lock.json` READY + `runtime-cpu.lock.txt` + `cpu-runtime.lock.json` READY, generated on a GitHub runner and reviewed | prepare run https://github.com/luogangan7-lgtm/cce-engine-oss/actions/runs/36032048288 (4 min 05 s job; 3.78 GB downloaded in 25 s; 0 forwards; torch 2.14.0+cpu / transformers 5.17.0; container network blocked) |
| GITHUB_RUNTIME_SMOKE_PASSED ✅ 2026-09-27 | one real load + ≥1 real forward on `ubuntu-24.04`, network isolation verified, report artifact | eval run https://github.com/luogangan7-lgtm/cce-engine-oss/actions/runs/36265705004 (archived `archive/36265705004`): 1 load, 11 real forwards (counted at `slot_logits` == ledger), 1,881,825,088 params float32 CPU, cgroup memory.max 12 GiB / swap 0 / cpu 3 / pids 256, network blocked (DNS + IP) |
| S0_CANDIDATE_AVAILABLE ✅ 2026-09-27 | `reports/<run>/s0_candidates.jsonl` with full distributions for a registered suite | 11 rows, raw logits for valid candidates only, coverage 18/18 (DECLARED 1 · UNOBSERVABLE 6 · OK 8 · SEMANTIC_UNKNOWN 3) |
| SEMANTIC_ACCEPTANCE ❌ FAILED 2026-09-27 | smoke semantic assertions evaluated; 2 items never prove accuracy | 7/11 inside the pre-registered accepted sets. Fails: 情绪余温 ×2 (picked 负向余温 / 中性; the cold-read structural rule allows only 首轮无余温 / 未知), 进程位置 on the no-information item (已决定在执行 0.705), 触发事件 on item 1 (刚花过钱 0.722 vs 受挫/出故障 0.256; text literally contains both a purchase and a failure — gold was single-valued, left unchanged after seeing results) |
| COMPARED_WITH_JEV ✅ 2026-09-27 | same 42 retest items, same `line[:2000]` slice, same question wire and candidate order as the stored TypeSafe Jev readings; frozen pre-registration | eval run https://github.com/luogangan7-lgtm/cce-engine-oss/actions/runs/36272175531 (archived `archive/36272175531`), analysis `results/jev_decider_vs_retest.json` |
| PRODUCTION_ENABLED | **not part of this delivery**; the comparison says Decider-2B is a different reader from Jev on all 5 facets | — |

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

## Comparison with TypeSafe Jev (task contract s0_context.v2, suite s0-compare-v1)

Pre-registration: `tests/data/jev_decider_vs_retest_prereg.json` (frozen before the run; three pre-data revisions, rule numbers never changed).
Contract v2: 情绪余温 is no longer a model question (not declared ⇒ 首轮无余温, provenance STRUCTURAL_COLD_READ); gold is an accepted set frozen before any run.
Since 2026-09-27 production s0 (`scripts/cce_full_run.py`) applies the same structural rule; the single definition is `scripts/cce_s0_jev.STRUCTURAL`, pinned equal to the v2 contract by `tests/test_cce_s0_wiring.py`.
Arms: Decider-2B (this run, 269 real forwards in 1,444 s, 1 load, 0 downloads) vs the stored TypeSafe Jev and MiniMax readings of 2026-09-23 (0 new paid calls).
Preconditions: all passed (50 within-run repeat pairs bit-identical; 9 cross-run smoke rows within 2.3e-6; per-row candidate order and question hashes equal to production `jev_questions`).
Two independent recomputations from raw files matched every number.

| facet | d(D,J1) / 42 | d(D,J2) | Jev self d(J1,J2) | change rate CP95 | κ(D,J1) [boot 95%] | 未知 picks D / J1 | verdict |
|---|---:|---:|---:|---|---|---:|---|
| 进程位置 | 24 | 24 | 0 | 0.41–0.72 | 0.30 [0.15, 0.46] | 19 / 5 | 不同读者 |
| 触发事件 | 38 | 38 | 0 | 0.77–0.97 | 0.05 [0.00, 0.11] | 0 / 15 | 不同读者 |
| 关系位置 | 21 | 21 | 0 | 0.34–0.66 | 0.30 [0.15, 0.46] | 28 / 15 | 不同读者 |
| 身体状态 | 17 | 17 | 0 | 0.26–0.57 | −0.12 [−0.18, −0.04] | 36 / 31 | 不同读者 |
| 资源状态 | 17 | 16 | 3 | 0.26–0.57 | 0.18 [−0.02, 0.39] | 36 / 23 | 不同读者 |

Overall (pre-registered rule): **not replaceable** — swapping Jev for Decider-2B would change the s0 top-1 reading on roughly 38–90 % of these items depending on the facet. There is no gold, so this says nothing about which reader is more accurate.

What the data supports beyond the verdict (exact McNemar on discordant items):
- On 进程位置, 关系位置, 资源状态 Decider abstains (选 未知/未提及) where Jev commits: discordant 14–0, 13–0, 14–1 (p ≤ 0.0034). On 身体状态 the difference is not significant (6 vs 11, p = 0.33).
- On 触发事件 Decider never picks 未知; it picks the null-content label 无明显触发 on 38/42 (Jev: 未知 15, 受挫/出故障 19). Merging 无明显触发 into 未知 still leaves d = 23.
- On 资源状态 most of the disagreement is an abstention-threshold difference: when Decider abstains and Jev commits, Jev's label is Decider's second choice on 13/14.
- The 情绪余温 structural problem is confirmed on the stored readings (MiniMax 42/42, Jev 12/42 violations); in contract v2 Decider is not asked.

Not separable with this run (each would need a new permit): option position vs "being the unknown option" (the unknown representation is the last candidate on every facet), English-only model vs Chinese candidate labels, one-question-per-row vs Jev's six-in-one request, and drift of the Jev backend since 2026-09-23. Temperature does not matter for these counts (top-1 is invariant to T).

Pre-registered predictions scored honestly: 2 of 4. The prediction that Decider would *over-read* was wrong; it abstains more.

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
