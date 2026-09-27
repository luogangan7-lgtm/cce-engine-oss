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

## 2×2 abstention probe (task contract s0_context.v3, suite s0-probe-v1)

Why Decider abstains more than Jev: candidate order (original / reversed) × candidate language (Chinese / one fixed English translation). Cell 0 = the comparison run above; three new cells in eval run https://github.com/luogangan7-lgtm/cce-engine-oss/actions/runs/36302960105 (archived `archive/36302960105`, 640 forwards in 2,783 s, CPU recorded). Pre-registration `tests/data/jev_decider_probe_prereg.json` (frozen before the run; rule numbers unchanged by its pre-data revisions). Anchors: 10/10 rows reproduce the comparison run (max |Δp| 3.3e-6). An independent recomputation matched every number. Analysis `results/jev_decider_probe.json`.

| facet | 未知 picks, cells 0 / reversed-zh / English / reversed-en (Jev) | what moved it (frozen rule) | agreement with Jev, cell 0 → English |
|---|---|---|---:|
| 进程位置 | 19 / 15 / 1 / 5 (Jev 5) | the English translation (Holm-significant, excess 14 → −4); order also matters in Chinese (d = 24) | 18 → 24 of 42 |
| 触发事件 | 无明显触发∪未知: 38 / 37 / 38 / 38 (Jev 16) | neither factor | 4 → 4 |
| 关系位置 | 28 / 25 / 33 / 35 (Jev 15) | neither explains it; English moved it the wrong way (not significant) | 21 → 14 |
| 身体状态 (exploratory) | 36 / 32 / 19 / 29 (Jev 31) | English moved picks into 无关, not toward Jev | 25 → 14 |
| 资源状态 | 36 / 39 / 37 / 37 (Jev 23) | neither factor | 25 → 24 |

What the data supports:
- 进程位置's excess abstention is mostly an effect of this one whole-package English translation (it also removes the Chinese cells' code-mixing, where 未知 is the only English-described option). English overshoots: 1 abstention against Jev's 5, and a new 回看复盘 mode appears (0 → 11; Jev uses it twice). Agreement with Jev rises only to 24/42, so still not replaceable.
- In Chinese, reversing the order raised quasi-abstention on 进程位置 (未知 + 无关进程: 21 → 34), so Decider's reading of that facet depends on candidate order.
- 触发事件 is not really abstention: Decider never picks 未知; the split with Jev is 无明显触发 vs 受挫/出故障, stable under both manipulations.
- 资源状态 is stable under both manipulations; since Jev's label is usually Decider's second choice and every cell keeps the contract's "choose unknown" with only 未提及 on offer, this may be a threshold or task-contract property rather than a model property.
- No cell of any facet reaches 可替代. The 2026-09-27 comparison verdict (not replaceable) stands.

Not separable here: translation vs code-mixing, model vs facet definitions/option sets, T = 1.3 and this single translation only. All 5 pre-registered predictions came true, but most carried little risk; the one risky prediction held on 进程位置 only.

## Qwen candidates (backend `hf_choice`, owner 「批准实测」 2026-09-27)

Decider-2B was a different reader from Jev on all 5 facets, so two instruct models were chosen after web research plus
independent licence checks (`results` of that research are in the Humaux store, not in this repo):
`Qwen/Qwen3-4B-Instruct-2507@cdbee75f` (key `qwen3-4b-2507`) and `Qwen/Qwen3.5-4B@851bf6e8` (key `qwen3.5-4b`, text-only load).
Both are Apache-2.0 and ungated. The Decider path (locks, workflows, permits, results) is untouched.

| piece | where | why this way |
|---|---|---|
| model locks | `models/<key>/model.source.lock.json` (+ `model.assets.lock.json` after prepare) | one directory per model; legacy key `decider-2b` still resolves to `locks/` |
| numerics | `backend_hf_choice.py`: bf16 weights exactly as released, **fp32 compute** (each `nn.Linear` runs `F.linear(x, W.float())`, embeddings return fp32, other params fp32, checkpoint-F32 tensors restored from the safetensors) | fp32 weights do not fit 12 GiB; ~60% of GitHub runners are AVX2-only where bf16 GEMM is slow and ISA-dependent; fp32 compute is the same dtype path Decider ran, with predictable speed |
| scoring | `plan_chat.py` + backend: the model's own chat template, options lettered A–H, last-position hidden state · output-embedding rows of the letters, `T = 1` | instruct models answer in chat format; Qwen3.5 thinks by default, so `enable_thinking=False` and the rendered prompt must end with the empty think block (checked per row) |
| planning checks | suffix == locked `answer_suffix`; text verbatim exactly once; no tokenizer control literals in the text; each letter one token at the boundary; row ≤ 2048 tokens | a template or thinking-switch drift is refused before any forward |
| bundle transport | prepare and eval legs fetch the pinned revision with a stdlib streaming downloader, checking size + LFS sha256 / git blob sha1 per file (≤5 whole-file attempts, every attempt charged to the ledger, cap 24 GiB/leg incl. retries); eval then verifies every byte against the committed READY assets lock | two 8–9 GB bundles do not fit the public repo's 10 GB Actions cache; the files are content-addressed, so integrity does not depend on the client |
| load gate | prepare and eval both refuse any missing / mismatched key or load error and check the tied output head; eval also requires `loading_info` and the parameter count to equal the prepare observation, which `cli.py assemble-assets-lock` writes into the READY lock mechanically | no randomly initialised weight can reach scoring, and a key-remap change between prepare and eval is caught |
| workflows | `cce-jev-llm-prepare.yml`, `cce-jev-llm-eval.yml`: one matrix leg per model in the admitted permit, each on its own runner; `run_llm.sh` gives the same container isolation as the Decider wrapper, pins MKL / oneDNN / ATen to their AVX2 code paths, and kills a timed-out container before the host scans; the image is built with `WITH_DECIDER=0` (no git fetch at build time) | Decider workflows stay byte-identical |
| permits | schema v2: `models: [{model_key, model_source_lock_sha256, asset_lock_sha256}]`; before consuming, admit runs the legs' own `check-locks` per model, the suite plan, the planned-size cap and an HF metadata check (same host as the fetcher; the test override is refused inside Actions); it emits the matrix | one permit covers both candidates |
| prepare smoke | in the offline container: a self-written CC0 sentence × the 5 production questions × 2 forwards; load report, parameter count, tok/s, letter mass, bitwise repeatability | validates the whole scoring path on GitHub before the eval permit exists |
| comparison | suite `s0-compare-llm-v1` = `s0-compare-v1` items (same 42-item input set) with the owner-adjudicated smoke-01 gold; prereg `tests/data/jev_candidate_vs_retest_prereg.json`; analysis `probes/jev_candidate_vs_retest.py` runs the **frozen** `probes/jev_decider_vs_retest.py` unchanged (sha-checked) with only `PRE/SUITE/OUT` rebound | the gate test replays Decider's archived predictions through the wrapper and must reproduce the frozen verdicts |

The originally planned single-facet screen was dropped before any data: with fp32 compute the run time is predictable from
the Decider anchor, runners are free and the two legs run in parallel, so the full comparison of both candidates gives strictly
more information with one permit fewer. The pre-registered headline check is still reported first:
`max(d(C,J1), d(C,J2)) ≥ 5` on 触发事件 means that facet cannot be 可替代, so the candidate is not a full replacement.

Local development used only tiny random-init models in the real checkpoint layouts and the real tokenizers on synthetic
text (fp32-compute path equals a full-fp32 reference exactly); no candidate weights were downloaded or run locally.

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
| `cce-jev-llm-prepare.yml` | manual, `permit_id` (schema v2) | per model leg: fetch + anchor, synthetic smoke (10 forwards) | admit `contents: write` (ref only) / prepare `contents: read` |
| `cce-jev-llm-eval.yml` | manual, `suite_id` + `permit_id` (schema v2) | per model leg: fetch + verify, one load, the suite's rows in `--network none` container | admit `contents: write` (ref only) / evaluate `contents: read` |

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
