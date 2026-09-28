# CCE Decider candidate evaluation (s0-distill2-v1)

- execution_status: **SUCCEEDED**
- coverage_status: **COMPLETE**
- semantic_acceptance: **FAILED**
- production_eligible: False
- backend / model_version: hf_choice / qwen3-4b-instruct-2507@cdbee75

| status | n |
|---|---:|
| DECLARED | 1 |
| OK | 78 |
| SEMANTIC_UNKNOWN | 521 |
| STRUCTURAL_COLD_READ | 120 |
| UNOBSERVABLE | 360 |

## timing (s)

- tokenizer_load_s: 3.642
- render_tokenize_s: 1.495
- model_load_s: 0.891
- first_forward_s: 13.8914
- all_forwards_s: 9334.013
- remaining_forwards_s: 9320.122
- wall_s: 9340.24
- peak_rss_kib: 9029736
- cgroup_memory_peak: 1121951744

## failures

- `SEMANTIC_CHECK_FAILED`: 1/9 asserted questions outside accepted set

_Infrastructure success and business acceptance are reported separately; items without gold are REVIEW_REQUIRED and never count as accuracy._
