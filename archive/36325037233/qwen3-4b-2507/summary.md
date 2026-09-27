# CCE Decider candidate evaluation (s0-distill-train-v1)

- execution_status: **SUCCEEDED**
- coverage_status: **COMPLETE**
- semantic_acceptance: **NOT_ESTABLISHED**
- production_eligible: False
- backend / model_version: hf_choice / qwen3-4b-instruct-2507@cdbee75

| status | n |
|---|---:|
| OK | 20 |
| SEMANTIC_UNKNOWN | 310 |
| STRUCTURAL_COLD_READ | 66 |
| UNOBSERVABLE | 198 |

## timing (s)

- tokenizer_load_s: 4.013
- render_tokenize_s: 0.787
- model_load_s: 0.786
- first_forward_s: 15.1765
- all_forwards_s: 4711.761
- remaining_forwards_s: 4696.585
- wall_s: 4717.443
- peak_rss_kib: 8781664
- cgroup_memory_peak: 869847040

_Infrastructure success and business acceptance are reported separately; items without gold are REVIEW_REQUIRED and never count as accuracy._
