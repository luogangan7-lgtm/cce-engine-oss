#!/usr/bin/env bash
# Host-side wrapper for the hf_choice candidate container (cce-jev-llm-prepare.yml smoke / cce-jev-llm-eval.yml eval).
# Same isolation as run_remote_only.sh (the Decider wrapper, left untouched): GitHub-hosted runner only, --network none,
# read-only rootfs, no capabilities, uid 1001, 3 CPU / 12 GiB / no extra swap, only the referenced corpus files mounted read-only.
# Usage: run_llm.sh smoke <image> <bundle_dir> <receipt.json> <out_dir> <model_key> <deadline_s> <proposal.json>
#        run_llm.sh eval  <image> <bundle_dir> <receipt.json> <out_dir> <model_key> <deadline_s> <suite_id>
set -euo pipefail

MODE="$1"; IMAGE="$2"; BUNDLE="$3"; RECEIPT="$4"; OUT="$5"; MODEL="$6"; DEADLINE="$7"; EXTRA="$8"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

if [[ "${GITHUB_ACTIONS:-}" != "true" || "${RUNNER_ENVIRONMENT:-}" != "github-hosted" || "${GITHUB_REPOSITORY:-}" != "luogangan7-lgtm/cce-engine-oss" ]]; then
  echo "EXECUTION_LOCATION_FORBIDDEN: model container only runs on a GitHub-hosted runner of luogangan7-lgtm/cce-engine-oss" >&2
  exit 3
fi
[[ "$MODE" == "smoke" || "$MODE" == "eval" ]] || { echo "INPUT_INVALID: mode" >&2; exit 3; }
[[ "$MODEL" =~ ^[a-z0-9][a-z0-9.-]{2,40}$ && "$MODEL" != *..* ]] || { echo "INPUT_INVALID: model key" >&2; exit 3; }
[[ "$DEADLINE" =~ ^[0-9]+$ ]] || { echo "INPUT_INVALID: deadline must come from the admitted policy" >&2; exit 3; }
[[ -d "$BUNDLE" && -f "$RECEIPT" ]] || { echo "MODEL_BUNDLE_INVALID: bundle dir or receipt missing" >&2; exit 3; }
mkdir -p "$OUT"; chown 1001:1001 "$OUT" 2>/dev/null || sudo chown 1001:1001 "$OUT"

MOUNTS=()
if [[ "$MODE" == "eval" ]]; then
  [[ "$EXTRA" =~ ^[a-z0-9][a-z0-9-]{2,40}$ ]] || { echo "INPUT_INVALID: suite id" >&2; exit 3; }
  FILES="$(python3 "$ROOT/experiments/jev/cli.py" suite-files --suite "$EXTRA")" || { echo "INPUT_INVALID: suite-files failed" >&2; exit 3; }
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    [[ "$f" =~ ^corpus/[A-Za-z0-9._-]+\.txt$ ]] || { echo "INPUT_INVALID: corpus ref" >&2; exit 3; }
    MOUNTS+=(-v "$ROOT/$f:/work/$f:ro")
  done <<< "$FILES"
  CMD=(/work/experiments/jev/cli.py eval --model "$MODEL" --suite "$EXTRA" --receipt /receipt.json --bundle /model --out /out/reports/run)
else
  [[ -f "$EXTRA" ]] || { echo "INPUT_INVALID: proposal file" >&2; exit 3; }
  MOUNTS+=(-v "$EXTRA:/proposal.json:ro")
  CMD=(/work/experiments/jev/cli.py prepare-smoke --model "$MODEL" --receipt /receipt.json --bundle /model --proposal /proposal.json --out /out)
fi
echo "extra_mounts=$(( ${#MOUNTS[@]} / 2 ))"

IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$IMAGE")"
echo "image_id=$IMAGE_ID"
set +e
# +300 s: model import, bundle re-verification and load happen before the in-container ledger clock starts
timeout --signal=KILL $((DEADLINE + 300)) docker run --name cce-jev-llm \
  --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --user 1001:1001 --cpus 3 --memory 12g --memory-swap 12g --pids-limit 256 \
  --tmpfs /tmp:rw,size=256m,uid=1001,gid=1001 \
  -v "$BUNDLE:/model:ro" \
  -v "$ROOT/experiments/jev:/work/experiments/jev:ro" \
  -v "$ROOT/config/context_taxonomy.json:/work/config/context_taxonomy.json:ro" \
  "${MOUNTS[@]}" \
  -v "$RECEIPT:/receipt.json:ro" \
  -v "$OUT:/out:rw" \
  -e GITHUB_ACTIONS -e RUNNER_ENVIRONMENT -e GITHUB_REPOSITORY -e GITHUB_WORKFLOW_REF -e GITHUB_RUN_ID -e GITHUB_RUN_ATTEMPT \
  -e GITHUB_SHA -e GITHUB_JOB -e RUNNER_NAME -e RUNNER_ARCH -e RUNNER_OS \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -e HF_HUB_DISABLE_TELEMETRY=1 -e TOKENIZERS_PARALLELISM=false \
  -e OMP_NUM_THREADS=3 -e MKL_NUM_THREADS=3 -e "CCE_JEV_IMAGE_ID=$IMAGE_ID" \
  -e HOME=/tmp -e HF_HOME=/tmp/hf -e XDG_CACHE_HOME=/tmp/cache \
  -e TRANSFORMERS_VERBOSITY=error -e PYTHONWARNINGS=ignore \
  "$IMAGE" "${CMD[@]}"
RC=$?
set -e
echo "docker_exit=$RC"
# no --rm: the workflow inspects State.OOMKilled after exit (a KILL by OOM and by timeout both give 137)
exit "$RC"
