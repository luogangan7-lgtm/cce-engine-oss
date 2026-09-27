# CCE Decider candidate evaluation (s0-compare-llm-v1)

- execution_status: **SUCCEEDED**
- coverage_status: **COMPLETE**
- semantic_acceptance: **FAILED**
- production_eligible: False
- backend / model_version: hf_choice / qwen3.5-4b@851bf6e

| status | n |
|---|---:|
| DECLARED | 1 |
| OK | 136 |
| SEMANTIC_UNKNOWN | 133 |
| STRUCTURAL_COLD_READ | 54 |
| UNOBSERVABLE | 162 |

## timing (s)

- tokenizer_load_s: 3.707
- render_tokenize_s: 0.868
- model_load_s: 1.047
- first_forward_s: 14.7314
- all_forwards_s: 4895.113
- remaining_forwards_s: 4880.382
- wall_s: 4900.819
- peak_rss_kib: 9865076
- cgroup_memory_peak: 1606971392

## failures

- `SEMANTIC_CHECK_FAILED`: 1/9 asserted questions outside accepted set

_Infrastructure success and business acceptance are reported separately; items without gold are REVIEW_REQUIRED and never count as accuracy._
