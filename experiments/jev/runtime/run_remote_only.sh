#!/usr/bin/env bash
# Host-side wrapper that runs the isolated model container. Refuses to run anywhere but a GitHub-hosted runner.
# Usage (from cce-jev-eval.yml): run_remote_only.sh <image> <bundle_dir> <receipt.json> <out_dir> <suite_id> <deadline_s>
set -euo pipefail

IMAGE="$1"; BUNDLE="$2"; RECEIPT="$3"; OUT="$4"; SUITE="$5"; DEADLINE="${6:-1200}"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

if [[ "${GITHUB_ACTIONS:-}" != "true" || "${RUNNER_ENVIRONMENT:-}" != "github-hosted" || "${GITHUB_REPOSITORY:-}" != "luogangan7-lgtm/cce-engine-oss" ]]; then
  echo "EXECUTION_LOCATION_FORBIDDEN: model container only runs on a GitHub-hosted runner of luogangan7-lgtm/cce-engine-oss" >&2
  exit 3
fi
[[ "$SUITE" =~ ^[a-z0-9][a-z0-9-]{2,40}$ ]] || { echo "INPUT_INVALID: suite id" >&2; exit 3; }
[[ -d "$BUNDLE" && -f "$RECEIPT" ]] || { echo "MODEL_BUNDLE_INVALID: bundle dir or receipt missing" >&2; exit 3; }
mkdir -p "$OUT"; chown 1001:1001 "$OUT" 2>/dev/null || sudo chown 1001:1001 "$OUT"

IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$IMAGE")"
echo "image_id=$IMAGE_ID"
# Effective limits are recorded from the container's cgroup by the evaluate job (not just echoed here).
set +e
timeout --signal=KILL $((DEADLINE + 60)) docker run --name cce-jev-eval \
  --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --user 1001:1001 --cpus 3 --memory 12g --memory-swap 12g --pids-limit 256 \
  --tmpfs /tmp:rw,size=256m,uid=1001,gid=1001 \
  -v "$BUNDLE:/model:ro" \
  -v "$ROOT/experiments/jev:/work/experiments/jev:ro" \
  -v "$ROOT/config/context_taxonomy.json:/work/config/context_taxonomy.json:ro" \
  -v "$RECEIPT:/receipt.json:ro" \
  -v "$OUT:/out:rw" \
  -e GITHUB_ACTIONS -e RUNNER_ENVIRONMENT -e GITHUB_REPOSITORY -e GITHUB_WORKFLOW_REF -e GITHUB_RUN_ID -e GITHUB_RUN_ATTEMPT \
  -e GITHUB_SHA -e GITHUB_JOB -e RUNNER_NAME -e RUNNER_ARCH -e RUNNER_OS \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -e HF_HUB_DISABLE_TELEMETRY=1 -e TOKENIZERS_PARALLELISM=false \
  -e OMP_NUM_THREADS=3 -e MKL_NUM_THREADS=3 -e "CCE_JEV_IMAGE_ID=$IMAGE_ID" \
  -e HOME=/tmp -e HF_HOME=/tmp/hf -e XDG_CACHE_HOME=/tmp/cache \
  "$IMAGE" /work/experiments/jev/cli.py eval --suite "$SUITE" --receipt /receipt.json --bundle /model --out /out/reports/run
RC=$?
set -e
echo "docker_exit=$RC"
# no --rm: the workflow inspects State.OOMKilled after exit (a KILL by OOM and by timeout both give 137)
exit "$RC"
