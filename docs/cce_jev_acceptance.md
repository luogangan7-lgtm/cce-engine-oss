# CCE Decider candidate — acceptance and fault-injection matrix

Pure tests (`experiments/jev/tests`, discovered via `tests/test_cce_jev_boundary.py` and `cce-jev-contract.yml`):

| requirement (task book §13.1) | test | fault injected → observed refusal |
|---|---|---|
| plain-machine runner CLI refuses before network / model import | `test_execution_guard.py::test_real_cli_eval_and_prepare_refuse_locally_before_any_import_or_download` | real `cli.py eval` / `prepare` subprocess → exit 3, `EXECUTION_LOCATION_FORBIDDEN`, torch/decider/huggingface_hub never in `sys.modules`, no dirs created |
| import / help / test discovery load no torch, no download, no env-file read | `test_no_model_at_import.py` | socket.connect monkey-bombed; every module + `--help` / `check-locks` / `plan` run clean; heavy imports only indented (lazy) |
| declared facet not overridden, no model row | `test_compile_context.py::test_declared_value_is_kept_and_no_model_row_is_generated` | declared 关系位置/进程位置 → DECLARED, absent from questions |
| unreadable facet stays unknown | `test_compile_context.py::test_unreadable_facets_stay_unknown_without_model` | `readable_from_text=false` → UNOBSERVABLE, no question |
| compiler completeness | `test_compile_context.py::test_compiler_completeness_*`, `::test_questions_verbatim_equal_to_production_jev_questions` | facet key + desc in instructions, candidates in taxonomy order, unique unknown, wire == production `jev_questions` |
| wrong / missing config → no default temperature | `test_assets.py::test_decider_config_strict` | missing file / missing temperature / v8 / schema_first → typed failures |
| missing / extra / corrupt asset | `test_assets.py::test_verify_bundle_good_and_each_corruption_family` | extra file, missing file, same-size byte flip, size change → `MODEL_BUNDLE_INVALID` |
| permit duplicate / attempt 2 | `test_admit_script.py` | attempt=2 → `PERMIT_ALREADY_USED`; HTTP 422 → already used; unreachable API → treated as consumed, no retry |
| budget at limit | `test_budget.py::test_reserve_at_limit_fails_and_does_not_record` | 3rd reservation refused, ledger unchanged |
| empty / missing / duplicate output | `test_coverage_and_suite.py::test_coverage_gate_families`, `::test_bad_backend_outputs_*` | `COVERAGE_MISMATCH`, all 18 expected keys still in results |
| candidate isolation | `test_no_production_write.py` | full fake run → zero files changed in the repo tree outside the report dir |
| fake backend "first option always" | `test_coverage_and_suite.py::test_first_option_fake_backend_turns_semantic_gate_red_*` | `semantic_acceptance = FAILED`, `SEMANTIC_CHECK_FAILED` |
| output upload | `test_report_upload.py` | `.safetensors/.gguf/.pt/tokenizer.json`, path escape, size cap, secret shapes → `OUTPUT_INVALID` |
| renderer truncation / reordering | `test_plan_work.py` | fake upstream that truncates or reverses → `INPUT_INVALID`; oversize → `INPUT_TOO_LONG` |
| workflow structure | `test_workflow_contract.py` | SHA pins vs `actions.lock.json`, `persist-credentials: false`, no `pull_request_target`, inputs never inside `run:`, admit/evaluate permission split, container flags |

GitHub smoke acceptance (§13.2, **not yet executed**): runner identity, verified file manifest, non-zero param count and
forward count, complete coverage, CPU/float32/threads as locked, `network_check` blocked inside the container, peak
memory + timing breakdown (`timing` in `report.json`; queue/upload from Actions metadata), semantic assertions of the
2 smoke items reported separately from infrastructure success.
