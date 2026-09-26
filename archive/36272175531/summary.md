# CCE Decider candidate evaluation (s0-compare-v1)

- execution_status: **SUCCEEDED**
- coverage_status: **COMPLETE**
- semantic_acceptance: **FAILED**
- production_eligible: False
- backend / model_version: decider / v10

| status | n |
|---|---:|
| DECLARED | 1 |
| OK | 117 |
| SEMANTIC_UNKNOWN | 152 |
| STRUCTURAL_COLD_READ | 54 |
| UNOBSERVABLE | 162 |

## timing (s)

- tokenizer_load_s: 4.065
- render_tokenize_s: 0.12
- model_load_s: 1.907
- first_forward_s: 4.1414
- all_forwards_s: 1444.031
- remaining_forwards_s: 1439.89
- wall_s: 1450.188
- peak_rss_kib: 11782132

## failures

- `SEMANTIC_CHECK_FAILED`: 2/9 asserted questions outside accepted set

_Infrastructure success and business acceptance are reported separately; items without gold are REVIEW_REQUIRED and never count as accuracy._
