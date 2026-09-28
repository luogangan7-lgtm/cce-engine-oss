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
| COMPARED_QWEN_CANDIDATES ✅ 2026-09-27 | Qwen3-4B-Instruct-2507 and Qwen3.5-4B under the same frozen rule | run https://github.com/luogangan7-lgtm/cce-engine-oss/actions/runs/36316049972: neither is a full replacement (see the Qwen section) |
| PRODUCTION_ENABLED | **not part of this delivery**; Decider-2B and both Qwen candidates are different readers from Jev | — |

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

**Prepare done 2026-09-27** — run https://github.com/luogangan7-lgtm/cce-engine-oss/actions/runs/36315123922 (archived `archive/36315123922`),
permit `prepare-llm-2026-09-27-1`, both legs green in 4–5 min:

| model | params loaded | load report | checkpoint-F32 restored | smoke tok/s (runner CPU) | letter mass on the smoke rows | bitwise repeat |
|---|---:|---|---:|---|---|---|
| Qwen3-4B-Instruct-2507 | 4,022,468,096 | clean | 0 | 15.35 (Xeon Platinum 8573C) | 0.99999–1.0 | yes |
| Qwen3.5-4B (text) | 4,205,751,296 | clean | 48 | 15.93 (Xeon Platinum 8370C) | 0.994–0.996 | yes |

The READY assets locks were written by `cli.py assemble-assets-lock`. The smoke speed is about half the pre-run estimate because
MKL / oneDNN / ATen are pinned to AVX2 for cross-CPU reproducibility; the eval policy deadline was set from this measurement
(~91–96 min expected per leg, deadline 4.5 h).

**Full comparison done 2026-09-27** — run https://github.com/luogangan7-lgtm/cce-engine-oss/actions/runs/36316049972
(archived `archive/36316049972/<model_key>/`), permit `eval-compare-llm-2026-09-27-1`, frozen rule via
`probes/jev_candidate_vs_retest.py`, results `results/jev_candidate_<key>_vs_retest.json`. Both legs: preconditions all pass,
50/50 rerun pairs bitwise identical, 269/269 rows, letter mass median 1.0 / 0.995 (the models answer with a letter).

d(C, J1) / d(C, J2) out of 42 (Decider for reference; ≤ 4 in both rounds is needed for 可替代):

| facet | Qwen3-4B-2507 | verdict | Qwen3.5-4B | verdict | Decider-2B |
|---|---|---|---|---|---|
| 进程位置 | 26 / 26 | 不同读者 | 24 / 24 | 不同读者 | 24 / 24 |
| 触发事件 (headline) | 20 / 20 | 不同读者 | 19 / 19 | 不同读者 | 38 / 38 |
| 关系位置 | 16 / 16 | 不同读者 | 12 / 12 | 不可判 | 21 / 21 |
| 身体状态 | 11 / 11 | 不同读者 | 28 / 28 | 不同读者 | 17 / 17 |
| 资源状态 | 17 / 15 | 不同读者 | 15 / 12 | 不可判 | 17 / 16 |
| **overall** | 整体不可替代 (5/5 不同读者) | | 整体不可替代 (3 不同读者, 2 不可判) | | 整体不可替代 |

Neither candidate is a full replacement; the headline check fails for both (max d 20 and 19 ≥ 5). Both are closer to Jev than
Decider on 触发事件 and 关系位置, but the remaining gap is 11–28 disagreements per facet against a threshold of 4. The disagreements
are systematic label conventions rather than noise: Qwen3-4B-2507 abstains far more than Jev (未知 31/42 on 进程位置 vs Jev 5,
42/42 on 身体状态), and Qwen3.5-4B answers 无关 on 24/42 身体状态 rows where Jev says 未提及 (the frozen instruction says
"choose 未知" while these two facets use 未提及 — a pre-registered confound). Wall time per leg 73 / 82 min (AMD EPYC 9V74 / Xeon 8370C).

The originally planned single-facet screen was dropped before any data: with fp32 compute the run time is predictable from
the Decider anchor, runners are free and the two legs run in parallel, so the full comparison of both candidates gives strictly
more information with one permit fewer. The pre-registered headline check is still reported first:
`max(d(C,J1), d(C,J2)) ≥ 5` on 触发事件 means that facet cannot be 可替代, so the candidate is not a full replacement.

Local development used only tiny random-init models in the real checkpoint layouts and the real tokenizers on synthetic
text (fp32-compute path equals a full-fp32 reference exactly); no candidate weights were downloaded or run locally.

## Distillation test (owner 「蒸馏进行测试」 2026-09-27)

Question: can a small per-facet head on the candidates' option-letter logits reproduce Jev's s0 reading well enough to pass
the same frozen rule? Pre-registration `tests/data/jev_distill_prereg.json` was frozen and pushed in `7d67192` before any
teacher reading or training feature existed. It was revised once before measurement, after an adversarial review; the revision log is
in the file. Six students are all reported:

* family **T**: the teacher is today's Jev on the 66 corpus lines outside the 42 (full distributions, soft targets);
* family **X**: 7-fold cross-fit on the 42 using the J1 labels, so no item is predicted by a head that saw its label;
* each family is run for variant **A** Qwen3-4B-2507, **B** Qwen3.5-4B and **C** both.

The student's features and head:

* **Features:** per-model log-softmax of the letter logits over the facet's candidates.
* **Head:** multinomial logistic regression with λ chosen by leave-one-out, fitted with L-BFGS.
* **Verdicts:** the frozen `probes/jev_decider_vs_retest.py`, unchanged (sha-checked).
* **Power check:** a head is also trained on the model's own distribution ("self-teacher"). If it cannot reproduce that within 4/42, the facet is marked † (no power). The verdict itself is not changed.

The 66 training lines are the brand-free complement of the brand-selected 42: 0/66 mention a brand (vs 42/42), and the median
length is 170 vs 516 characters. Family X exists to separate "cannot transfer" from "cannot be learned from these features".

| step | where | facts |
|---|---|---|
| teacher reading | local API calls, `probes/jev_distill_teacher.py` | 76 attempts under a cross-process cap of 80 (fsync'd ledger + lock), 0 retries, train 66/66 + drift 10/10 ok, ~$0.004; committed in `01c55ec` before the training features existed |
| training features | https://github.com/luogangan7-lgtm/cce-engine-oss/actions/runs/36325037233 @ `7d67192`, permit `eval-distill-train-2026-09-27-1`, archived `archive/36325037233/<model_key>/` | 2 legs × 330 rows, both green, 82 / 90 min; model inference only on GitHub runners |
| exam features | `archive/36316049972` (reused, 0 new runs) | train/exam identities, backend config, candidate order and question sha checked equal |
| analysis | `probes/jev_distill_vs_retest.py` locally: numpy/scipy heads on the archived numbers only, no model loaded | all six readers: 0 precondition errors, 50/50 rerun pairs pass |

d(S, J1) / d(S, J2) out of 42. † means the head has no power on that facet (self-teacher d > 4). Reference rows:

* constant-majority baseline d0 (J1/J2): 29/29, 23/23, 22/22, 11/11, 19/17;
* best zero-shot candidate (J1/J2): 24/24, 19/19, 12/12, 11/11, 15/12.

| facet | TA | TB | TC | XA | XB | XC |
|---|---|---|---|---|---|---|
| 进程位置 | 18/18 不可判 † | 17/17 不可判 | 20/20 不同读者 † | 17/17 不可判 | 20/20 不同读者 | 19/19 不同读者 † |
| 触发事件 (headline) | 14/14 不可判 | 12/12 不可判 | 12/12 不可判 † | 16/16 不可判 † | 15/15 不可判 | 14/14 不可判 † |
| 关系位置 | 15/15 不可判 | 13/13 不可判 | 10/10 不可判 † | 13/13 不可判 | 13/13 不可判 | 13/13 不可判 † |
| 身体状态 | 9/9 不可判 | 9/9 不可判 | 11/11 不同读者 | 7/7 不可判 | 10/10 不同读者 | 5/5 不可判 |
| 资源状态 | 15/12 不同读者 | 12/9 不可判 | 13/10 不可判 | 18/15 不同读者 | 15/12 不可判 | 14/11 不可判 |
| **overall** | 不可替代 | 部分(全 不可判) | 不可替代 | 不可替代 | 不可替代 | 不可替代 |

**Under the frozen implementation no student is 可替代 on any facet, and none is a full replacement.** The headline check fails
for all six: 触发事件 max d is 12–16, and 5 or more rules out 可替代. The closest cell is XC 身体状态 at 5/5, one disagreement
above the threshold.

That closest cell is not robust. An independent verification recomputed everything with its own code:

* **What reproduced exactly:** all 30 cells from the committed coefficients, all 60 κ intervals, and the whole of family T on a full refit.
* **Where the X family breaks down:** in its 7-fold cross-fit, leave-one-out often leaves a class with no training example. Such folds occur for 资源状态 in 7/7 folds and for 触发事件 in 6/7. The held-out cross-entropy there has no finite optimum, so the λ choice depends on implementation details.

A post-hoc sensitivity run (`probes/jev_distill_ce_sensitivity.py` → `results/jev_distill_ce_sensitivity.json`, **not
pre-registered**) changes only the `+1e-12` guard in the cross-entropy. Four X cells move:

* XC 身体状态: 5/5 → 4/4, which is **可替代**;
* XC 资源状态: 14/11 → 18/15;
* XA 触发事件: 16 → 17;
* XB 资源状态: 15/12 → 14/11.

Family T and every reader's overall "not a full replacement" do not move. So the robust statements are:

* the T students and the headline failure hold as stated;
* X-family cells on 资源状态 / 触发事件 / 身体状态 are implementation-sensitive and should be read as ±1–4;
* the frozen verdicts stay as registered.

The heads do move toward Jev. On most facets they cut the zero-shot gap (e.g. 触发事件 19 → 12). On 进程位置, 触发事件 and 关系位置 they
beat the constant-majority baseline by 7–12. But 5–20 disagreements per facet remain against a tolerance of 4.

Family X, trained in-distribution on Jev's own labels, is no closer than family T. So on this evidence the gap is not mainly the
brand-free transfer.

Variant B has power on every facet, so B's result cannot be blamed on head capacity. Variant C, which concatenates both
models, lacks power on 2–3 facets at these sample sizes.

The power check is vacuous where the self-teacher is constant. That is the case for 身体状态 in variants A and C, where a
constant already scores d_self = 0 (and for 资源状态 a constant scores 2). The TC 身体状态 "不同读者" comes from a head that
answers 未知 on 42/42: it is the constant-majority reader (d = d0 = 11, net 0).

Training and exam features ran on different CPU models, although the build, the numeric environment (pinned to AVX2) and the backend configuration are identical; the effect was not measured.

Two descriptive checks, neither of which enters the verdict:

* **Teacher drift:** on the 10 rerun items, today's Jev differs from the 09-23 readings once (身体状态), and J1 vs J2 differ 0 times.
* **Distribution shift:** on the training lines the teacher answers 未知 far more often (触发事件 53/66 vs 15/42 in J1; 身体状态 62/66 vs 31/42). The standardised mean difference of exam features vs training features reaches 2.06 SD.

Pre-registered predictions: 5 of 6 held. The power prediction (at least 4/5 facets with power per variant) failed for both C
readers (2/5).

What this does **not** show: that Jev cannot be distilled in general. The features here are only 5–7 letter logits per model
(no hidden states); training is 66 short brand-free lines (T) or 36 labelled items (X); and the same 42 items have now been used
twice. Recompute gate: `tests/test_cce_jev_distill_head.py` requires every committed reader file and the summary to equal a fresh
run of the frozen analysis on the archives. Since 2026-09-28 it is in the heavy tier (`CCE_JEV_HEAVY=1`, about 20 minutes). Floats are compared at solver resolution (|Δ| ≤ 1e-5) and everything else exactly. The gate holds only on the producing platform (macOS): on a Linux runner the weakly regularised (λ = 1e-4), near-separable head fits stop at different points (head weights differ by up to about 0.5, descriptives at the 3rd decimal; two cce-jev-heavy runs on 2026-09-28). Whether any verdict differs across platforms was then checked directly (2026-09-29): `test_round1_verdict_fields_hold_across_platforms` compares every non-float field (verdicts, labels, counts, distances) and on the Linux runner found **0 differences in all 7 files**; float drift was at most 2e-5 for the T readers and up to 2.9 in the X readers' fitted weights, none of which reaches a label or verdict. So round-1 verdicts are platform-invariant; only the fitted parameters are not. CI runs that verdict-level check; the byte-level recompute stays on the producing platform.

## Distillation round 2: stronger student (owner 「再试一轮更强的学生」 2026-09-28)

The design came from three sources:

* a web research pass (GPT Pro);
* a three-way design panel (hidden-state probe / convention prompt / evidence-first) with a synthesis judge;
* an adversarial pre-freeze review, whose 5 P1 findings were fixed and 6 of 6 mutations caught.

Pre-registration `tests/data/jev_distill2_prereg.json` was frozen and pushed in `850d2a7` before any round-2 teacher reading or feature.

| step | where | facts |
|---|---|---|
| teacher | `probes/jev_distill2_teacher.py`, local API calls | J3 (42 exam) → R2 (66 training) → J4 (42 exam): 150/150 ok under a cumulative cap of 170, 0 retries, ~$0.008; read before the feature run was dispatched, committed in `d3b44b3` |
| features | https://github.com/luogangan7-lgtm/cce-engine-oss/actions/runs/36345476433 @ `850d2a7`, permit `eval-distill2-2026-09-28-1`, archived `archive/36345476433/<model_key>/` | 599 rows per leg (exam suite 54 + training 66), 156 / 164 min in-container, peak RSS 8.6 / 9.3 GiB of the 12 GiB limit. The prompt is unchanged, so every row_sha256 equals the round-1 archives; the letter logits differ from them by at most 2.3e-4. New `export_hidden` keeps the last-token state after blocks 18/27 (Qwen3-4B) and 16/24 (Qwen3.5-4B) plus the scored final state. `experiments/jev/hidden_export.py` writes only span coordinates of the 108 main posts (z-scored, SVD, ~2.7 MB): no raw vectors. |
| analysis | `probes/jev_distill2_vs_retest.py`, local numpy/scipy on the archived numbers, 78 min on 9 processes | 0 precondition errors, all fits converged, 50/50 rerun pairs pass |

The summary's `teacher2_sha256` is the sha of the teacher *output* file; the teacher *script* pin is in the prereg. Both legs report `semantic_acceptance` FAILED on 1 of 9 asserted smoke questions — identical to the round-1 exam run and not a precondition of this test. The single-use permit's consumed tag points at `850d2a7`.

What the analysis fits:

* **Primary student P:** per-facet multinomial logistic regression on both models' letter log-softmax plus the 6 span-coordinate blocks plus a training-post offset. The intercept is penalised, so the problem is strictly convex.
* **How P is evaluated:** leave-one-post-out on the 42, with the 66 pooled in; the near-duplicate exam pair is left out together. Settings are chosen from 126 configurations by inner 7-fold Brier score.
* **Targets:** today's Jev soft labels.
* **Secondary readers:** S1 uses letters only, S2 uses J1 hard targets, S3 is transfer only.

d(S, J1) / d(S, J2) out of 42. Round 1 is repeated in the last column for reference.

| facet | P (primary) | S1 letters | S2 J1 targets | S3 transfer | constant majority | round-1 best |
|---|---|---|---|---|---|---|
| 进程位置 | 14/14 不可判 | 14/14 不可判 | 16/16 不可判 | 18/18 不可判 | 29/29 | 17/17 |
| 触发事件 (headline) | **10/10 不可判** | 11/11 不可判 | 11/11 不可判 | 11/11 不可判 | 23/23 | 12/12 |
| 关系位置 | 10/10 不可判 | 14/14 不可判 | 12/12 不可判 | 10/10 不可判 | 22/22 | 10/10 |
| 身体状态 | 6/6 不可判 | **4/4 可替代** | **3/3 可替代** | 5/5 不可判 | 11/11 | 5/5 |
| 资源状态 | 12/9 不可判 | 14/11 不可判 | 16/13 不可判 | 12/9 不可判 | 19/17 | 12/9 |

**The primary student is not a replacement.** All five facets are 不可判, and the headline 触发事件 is at d = 10, where 5 or more rules out 可替代.

Two secondary readers reach 可替代 on 身体状态: S1 at 4/4 and S2 at 3/3. Treat this as exploratory only:

* this facet is 31/42 "未知", so the constant-majority reader already scores d = 11;
* the head fails the planted-teacher power check on this facet (d_planted = 5);
* these 42 posts are being used for the third time;
* confirming it needs new posts that nobody has authorised yet.

P versus the letters-only S1 shows no significant difference on any facet (exact McNemar p ≥ 0.29), so the hidden states did not buy a measurable gain.

Round-2 point estimates are lower than round 1's on several facets, but this is not a paired comparison. No round-2 reader isolates which change helped: pooling, fresh soft targets or the well-posed cross-validation.

Controls:

* **Permutation gate:** passes on every facet (median permuted d ≥ d0).
* **Planted-teacher power:** established only on 触发事件 (d_planted = 1). The other four facets have d_planted = 5–8, so their results cannot be read as "not learnable".
* **Learning curve on 触发事件:** flat (11.7 → 9.7 → 9.6 → 9.0 for 10/20/30/41 in-domain posts), so the data-limited flag is false.
* **Robustness:** switching the inner criterion to soft cross-entropy changes no verdict.

The teacher is stable:

* today's two reads differ from each other on at most 1 post per facet;
* against 09-23 they differ on at most 1 post, except 资源状态 = 3, which equals the J1/J2 disagreement itself;
* the q_E argmax reader scores 0–1 (3/0 on 资源状态) against J1/J2.

The pre-registered decision map gives **B**: power is established on 触发事件, the learning curve is flat, and max d = 10. So a linear read-out of these two 4B models' states does not reproduce Jev's 触发事件, and this student line is closed on s0.

Read B with two caveats from the independent verification:

* **No slack.** d is exactly 10, and one post (exam index 22) decides it. Its fold legitimately chose a different setting (Brier margin 7e-3), and with the modal setting d would be 9, which is outcome D. D gives the same practical answer, because the disagreements are mostly concrete choices (4 abstain / 5 concrete).
* **Narrow power check.** The power check shows the head can recover a strongly regularised linear labelling that this model class can already express. It does not by itself prove that linear read-outs cap out at d ≈ 10.

On the headline facet 6 of the 10 disagreements are concrete-choice, not abstention, so round-2's own rule gives no ground for a convention-prompt round 3.

Pre-registered predictions: 4 of 8 held (Q1 intervals, Q2, Q6 drift, Q8 gate). These failed:

* Q3: no 可替代 cell for P;
* Q4: P did not beat S1 by 2 or more on 3 facets;
* Q5: S1 was not within ±2 of round-1 XC on 4 facets;
* Q7: power was established on only 1 facet.

Independent verification (own code, a different solver) reproduced every committed number: all P folds on all facets, S1 and S3 on all facets, S2, the permutation seeds, the planted teachers and the learning curve. The provenance audit also passed: freeze before any measurement, teacher read before admission, row shas, span metadata, no raw text and no raw vectors.

Minor notes:

* Three teacher rows have a stored `choice` that differs from the argmax of their distribution. This only affects the drift description; q_E uses the distributions.
* The frozen analysis script's header docstring still says "tie < 1e-9, position mod 7". The code and the prereg use 1e-6 and group order mod 7.

Recompute gate: `CCE_JEV_HEAVY=1 pytest tests/test_cce_jev_distill2_head.py -k recompute` reruns the frozen analysis in a clean worktree of HEAD and requires byte-identical reader files and summary. It is opt-in because it takes about 1–1.5 h. It passed once on 2026-09-28 (7,041 s locally, worktree at 9620d89); the record is `results/jev_distill2_recompute_2026-09-28.json`. On CI the heavy tier (both synthetic end-to-end tests and round 1's other heavy tests; both recompute gates stay on the producing platform) runs only through the manual workflow `.github/workflows/cce-jev-heavy.yml`, not in the production contract job.

## What runs where

* **Local machine**: only pure Python (stdlib) tests with a fake backend / fake tokenizer. `cli.py eval|prepare` refuse
  with `EXECUTION_LOCATION_FORBIDDEN` before any import or download. No `from_pretrained`, no `hf_hub_download`, no torch.
  The distillation analysis fits numpy/scipy logistic heads on archived letter logits only (no model file, no inference);
  the distillation teacher is HTTP calls to TypeSafe Jev under a hard cap.
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
