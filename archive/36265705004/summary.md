# CCE Decider candidate evaluation (s0-smoke-v1)

- execution_status: **SUCCEEDED**
- coverage_status: **COMPLETE**
- semantic_acceptance: **FAILED**
- production_eligible: False
- backend / model_version: decider / v10

| status | n |
|---|---:|
| DECLARED | 1 |
| OK | 8 |
| SEMANTIC_UNKNOWN | 3 |
| UNOBSERVABLE | 6 |

## timing (s)

- tokenizer_load_s: 3.183
- render_tokenize_s: 0.003
- model_load_s: 2.042
- first_forward_s: 3.2591
- all_forwards_s: 33.694
- remaining_forwards_s: 30.435
- wall_s: 38.926
- peak_rss_kib: 11778904

## failures

- `SEMANTIC_CHECK_FAILED`: 4/11 asserted questions outside accepted set

_Infrastructure success and business acceptance are reported separately; 2 smoke items never prove accuracy._
