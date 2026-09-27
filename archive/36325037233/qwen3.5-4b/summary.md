# CCE Decider candidate evaluation (s0-distill-train-v1)

- execution_status: **SUCCEEDED**
- coverage_status: **COMPLETE**
- semantic_acceptance: **NOT_ESTABLISHED**
- production_eligible: False
- backend / model_version: hf_choice / qwen3.5-4b@851bf6e

| status | n |
|---|---:|
| OK | 91 |
| SEMANTIC_UNKNOWN | 239 |
| STRUCTURAL_COLD_READ | 66 |
| UNOBSERVABLE | 198 |

## timing (s)

- tokenizer_load_s: 3.444
- render_tokenize_s: 0.722
- model_load_s: 0.976
- first_forward_s: 16.8142
- all_forwards_s: 5153.64
- remaining_forwards_s: 5136.826
- wall_s: 5158.854
- peak_rss_kib: 9532108
- cgroup_memory_peak: 1265123328

_Infrastructure success and business acceptance are reported separately; items without gold are REVIEW_REQUIRED and never count as accuracy._
