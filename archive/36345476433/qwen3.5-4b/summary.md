# CCE Decider candidate evaluation (s0-distill2-v1)

- execution_status: **SUCCEEDED**
- coverage_status: **COMPLETE**
- semantic_acceptance: **FAILED**
- production_eligible: False
- backend / model_version: hf_choice / qwen3.5-4b@851bf6e

| status | n |
|---|---:|
| DECLARED | 1 |
| OK | 227 |
| SEMANTIC_UNKNOWN | 372 |
| STRUCTURAL_COLD_READ | 120 |
| UNOBSERVABLE | 360 |

## timing (s)

- tokenizer_load_s: 4.139
- render_tokenize_s: 1.819
- model_load_s: 1.129
- first_forward_s: 15.2796
- all_forwards_s: 9843.988
- remaining_forwards_s: 9828.708
- wall_s: 9851.269
- peak_rss_kib: 9781084
- cgroup_memory_peak: 1520832512

## failures

- `SEMANTIC_CHECK_FAILED`: 1/9 asserted questions outside accepted set

_Infrastructure success and business acceptance are reported separately; items without gold are REVIEW_REQUIRED and never count as accuracy._
