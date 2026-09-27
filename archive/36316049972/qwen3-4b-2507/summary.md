# CCE Decider candidate evaluation (s0-compare-llm-v1)

- execution_status: **SUCCEEDED**
- coverage_status: **COMPLETE**
- semantic_acceptance: **FAILED**
- production_eligible: False
- backend / model_version: hf_choice / qwen3-4b-instruct-2507@cdbee75

| status | n |
|---|---:|
| DECLARED | 1 |
| OK | 58 |
| SEMANTIC_UNKNOWN | 211 |
| STRUCTURAL_COLD_READ | 54 |
| UNOBSERVABLE | 162 |

## timing (s)

- tokenizer_load_s: 3.184
- render_tokenize_s: 0.677
- model_load_s: 0.625
- first_forward_s: 12.3272
- all_forwards_s: 4383.941
- remaining_forwards_s: 4371.614
- wall_s: 4388.496
- peak_rss_kib: 8923984
- cgroup_memory_peak: 1015554048

## failures

- `SEMANTIC_CHECK_FAILED`: 1/9 asserted questions outside accepted set

_Infrastructure success and business acceptance are reported separately; items without gold are REVIEW_REQUIRED and never count as accuracy._
