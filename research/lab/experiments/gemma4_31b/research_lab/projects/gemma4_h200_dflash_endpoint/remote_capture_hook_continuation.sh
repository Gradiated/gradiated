#!/usr/bin/env bash
# Run the admitted Gemma 4 capture-hook continuation without replaying AR diagnostic.
set -Eeuo pipefail

root=/home/glmrunner/gemma4-dflash/work
source_dir="$root/sglang"
models="$root/models"
inputs=/home/glmrunner/gemma4-dflash/continuation-inputs-20260724-hook1
run_root="$root/capture-hook-continuation"
results="$run_root/results"
base_image=gemma4-dflash-sglang:588d1f7bc942
image=gemma4-dflash-sglang:588d1f7bc942-gemma4hook
target_revision=b9ea41a2887d8607f594846523f94c6cc75ac8a4
draft_revision=eabd648301ce28583cc14757912e5e0f84e152e1
base_gemma_sha=a34a27e2f5722cc1c7d0ef418a73fc77ad701ead20a99c6471d26f1fb8700a80
patched_gemma_sha=5734767925504a60e80af7e2d25610e27013d3a8a2ad853a3e7d654e700e9bc6
stage=preflight
science_started=false
candidate_workload_started=false
telemetry_pid=

docker() { sudo docker "$@"; }

write_json() {
  local path=$1
  shift
  python3 - "$path" "$@" <<'PY'
import json
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
values = {}
for item in sys.argv[2:]:
    key, value = item.split("=", 1)
    if value in {"true", "false"}:
        values[key] = value == "true"
    elif value.lstrip("-").isdigit():
        values[key] = int(value)
    else:
        values[key] = value
temporary = path.with_suffix(path.suffix + ".part")
temporary.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n")
temporary.replace(path)
PY
}

finish() {
  local rc=$?
  set +e
  if [[ -n "$telemetry_pid" ]]; then
    kill "$telemetry_pid" >/dev/null 2>&1
    wait "$telemetry_pid" >/dev/null 2>&1
  fi
  docker logs gemma4-dflash > "$run_root/final-container.log" 2>&1
  docker inspect gemma4-dflash > "$run_root/final-container.inspect.json" 2>/dev/null
  write_json "$run_root/REMOTE_TERMINAL.json" \
    "stage=$stage" "exit_code=$rc" "science_started=$science_started" \
    "candidate_workload_started=$candidate_workload_started"
  find "$run_root" -type f -printf '%P %s\n' | sort > "$run_root/RESULTS.manifest"
}
trap finish EXIT

mkdir -p "$run_root" "$results"
test "$(git -C "$source_dir" rev-parse HEAD)" = 588d1f7bc9424201f89957e145f9d5af633a3eb8
test -d "$models/target"
test -d "$models/draft"
(
  cd "$inputs"
  sha256sum -c INPUTS.sha256
)

gemma_file="$source_dir/python/sglang/srt/models/gemma4_mm.py"
observed_gemma_sha=$(sha256sum "$gemma_file" | awk '{print $1}')
if [[ "$observed_gemma_sha" = "$base_gemma_sha" ]]; then
  git -C "$source_dir" apply "$inputs/gemma4_dflash_capture_hook.patch"
elif [[ "$observed_gemma_sha" != "$patched_gemma_sha" ]]; then
  write_json "$run_root/SOURCE_REJECT.json" \
    "classification=unexpected_pinned_gemma4_source" \
    "observed_sha256=$observed_gemma_sha" \
    "expected_base_sha256=$base_gemma_sha" \
    "expected_patched_sha256=$patched_gemma_sha"
  exit 65
fi
test "$(sha256sum "$gemma_file" | awk '{print $1}')" = "$patched_gemma_sha"
python3 -m py_compile "$gemma_file"
sha256sum "$gemma_file" > "$run_root/GEMMA4_SOURCE.sha256"
git -C "$source_dir" diff -- python/sglang/srt/models/gemma4_mm.py \
  > "$run_root/GEMMA4_SOURCE.diff"

stage=image_overlay
module_path=$(docker run --rm "$base_image" python3 -c \
  'import sglang.srt.models.gemma4_mm as m; print(m.__file__)' | tail -n 1)
test "$module_path" = /sgl-workspace/sglang/python/sglang/srt/models/gemma4_mm.py
overlay="$run_root/image-overlay"
mkdir -p "$overlay"
install -m 0444 "$gemma_file" "$overlay/gemma4_mm.py"
python3 - "$overlay/Dockerfile" "$base_image" "$module_path" <<'PY'
import pathlib
import sys
pathlib.Path(sys.argv[1]).write_text(
    f"FROM {sys.argv[2]}\nCOPY gemma4_mm.py {sys.argv[3]}\n"
)
PY
docker build -t "$image" "$overlay" > "$run_root/image-build.log" 2>&1
docker image inspect "$image" --format '{{.Id}}' > "$run_root/IMAGE_ID.txt"
docker run --rm -i "$image" python3 - <<'PY' > "$run_root/HOOK_IMPORT.json"
import inspect
import json
from sglang.srt.models.gemma4_mm import Gemma4ForConditionalGeneration
method = Gemma4ForConditionalGeneration.set_dflash_layers_to_capture
print(json.dumps({
    "class": Gemma4ForConditionalGeneration.__name__,
    "method": method.__name__,
    "source": inspect.getsource(method),
}, indent=2, sort_keys=True))
PY

start_server() {
  local arm=$1
  docker rm -f gemma4-dflash >/dev/null 2>&1 || true
  local flags=(--model-path /models/target --tokenizer-path /models/target --revision "$target_revision" --dtype bfloat16 --tp-size 1 --attention-backend triton --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup)
  if [[ "$arm" = dflash ]]; then
    flags+=(--speculative-algorithm DFLASH --speculative-draft-model-path /models/draft --speculative-draft-model-revision "$draft_revision" --speculative-num-draft-tokens 16 --speculative-draft-attention-backend fa4)
  fi
  docker run -d --name gemma4-dflash --gpus all --ipc=host --network host \
    -v "$models:/models:ro" -v "$inputs:/project:ro" -v "$run_root:/work/dflash" \
    "$image" python3 -m sglang.launch_server "${flags[@]}" \
    > "$run_root/${arm}.container-id"
  for _ in $(seq 1 180); do
    if curl -fsS http://127.0.0.1:30000/v1/models \
      > "$run_root/${arm}.models.json"; then
      write_json "$run_root/${arm}.HEALTH.json" \
        "pass=true" "arm=$arm" "model_probe_accepted=true"
      return 0
    fi
    sleep 5
  done
  docker logs gemma4-dflash > "$run_root/${arm}.server-start.log" 2>&1 || true
  write_json "$run_root/${arm}.HEALTH.json" \
    "pass=false" "arm=$arm" "model_probe_accepted=false"
  return 1
}

(
  while true; do
    printf '%s,' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw \
      --format=csv,noheader,nounits
    sleep 1
  done
) > "$run_root/gpu.csv" 2> "$run_root/gpu.stderr" &
telemetry_pid=$!

stage=dflash_diagnostic_server
resume_seed_api=false
prior_result="$results/dflash-diagnostic"
prior_server_log="$run_root/dflash-diagnostic.server.log"
if [[ -f "$prior_result/TERMINAL.json" ]] \
  && grep -q "unexpected keyword argument 'seed'" "$prior_server_log" \
  && ! grep -q 'DFLASH verify completed' "$prior_server_log" \
  && python3 - "$prior_result/TERMINAL.json" <<'PY'
import json
import sys
value = json.load(open(sys.argv[1]))
assert value["pass"] is False
assert value["raw_token_ids_present"] is False
assert all(row["returned_token_ids"] == 0 for row in value["rows"])
PY
then
  test ! -e "$results/dflash-diagnostic-pre-science-seed"
  test "$(docker inspect gemma4-dflash --format '{{.Config.Image}}')" = "$image"
  curl -fsS http://127.0.0.1:30000/v1/models \
    > "$run_root/dflash.models.json"
  mv "$prior_result" "$results/dflash-diagnostic-pre-science-seed"
  cp "$prior_server_log" \
    "$run_root/dflash-diagnostic-pre-science-seed.server.log"
  cp "$run_root/INVOCATION_STATE.json" \
    "$run_root/dflash-diagnostic-pre-science-seed.INVOCATION_STATE.json"
  cp "$run_root/REMOTE_TERMINAL.json" \
    "$run_root/dflash-diagnostic-pre-science-seed.REMOTE_TERMINAL.json"
  write_json "$run_root/PRE_SCIENCE_SEED_REPAIR.json" \
    "classification=wholly_absent_candidate_api_wiring_failure" \
    "requests_reached_http=4" "scheduler_requests=0" \
    "returned_token_ids=0" "dflash_verify_events=0" \
    "resident_server_reused=true"
  resume_seed_api=true
fi
if [[ "$resume_seed_api" = false ]]; then
  start_server dflash
fi
docker logs gemma4-dflash > "$run_root/dflash-diagnostic.server-health.log" 2>&1
grep -q 'Initialized DFLASH draft runner' "$run_root/dflash-diagnostic.server-health.log"

stage=dflash_diagnostic
science_started=true
candidate_workload_started=true
write_json "$run_root/INVOCATION_STATE.json" \
  "stage=$stage" "science_started=true" "candidate_workload_started=true"
set +e
docker exec gemma4-dflash python3 /project/dflash_endpoint_runner.py \
  --arm dflash-diagnostic --concurrency 4 \
  --output /work/dflash/results/dflash-diagnostic
diagnostic_rc=$?
set -e
docker logs gemma4-dflash > "$run_root/dflash-diagnostic.server.log" 2>&1
if [[ "$diagnostic_rc" -ne 0 ]]; then
  exit "$diagnostic_rc"
fi

set +e
python3 "$inputs/evaluate_dflash_diagnostic.py" \
  --candidate "$results/dflash-diagnostic" \
  --consumed-ar "$inputs/consumed-ar-diagnostic" \
  --server-log "$run_root/dflash-diagnostic.server.log" \
  --output "$run_root/DFLASH_DIAGNOSTIC_GATE.json"
gate_rc=$?
set -e
if [[ "$gate_rc" -ne 0 ]]; then
  stage=dflash_diagnostic_reject
  write_json "$run_root/FINAL_TERMINAL.json" \
    "status=terminal" \
    "classification=diagnostic_quality_or_integration_reject" \
    "dflash_diagnostic_consumed=true" "c32_pair_started=false"
  exit "$gate_rc"
fi

stage=ar_c32_server
start_server ar
stage=ar_c32
write_json "$run_root/C32_INVOCATION_STATE.json" \
  "stage=$stage" "ar_c32_started=true" "dflash_c32_started=false"
docker exec gemma4-dflash python3 /project/dflash_endpoint_runner.py \
  --arm ar-c32 --concurrency 32 --output /work/dflash/results/ar-c32
docker logs gemma4-dflash > "$run_root/ar-c32.server.log" 2>&1
sha256sum "$results/ar-c32/TERMINAL.json" > "$run_root/AR_C32_TERMINAL.sha256"

stage=dflash_c32_server
start_server dflash
stage=dflash_c32
write_json "$run_root/C32_INVOCATION_STATE.json" \
  "stage=$stage" "ar_c32_started=true" "dflash_c32_started=true"
docker exec gemma4-dflash python3 /project/dflash_endpoint_runner.py \
  --arm dflash-c32 --concurrency 32 --output /work/dflash/results/dflash-c32
docker logs gemma4-dflash > "$run_root/dflash-c32.server.log" 2>&1
grep -q 'DFLASH verify completed' "$run_root/dflash-c32.server.log"
sha256sum "$results/dflash-c32/TERMINAL.json" \
  > "$run_root/DFLASH_C32_TERMINAL.sha256"

stage=reconcile
python3 "$inputs/reconcile_dflash.py" --results "$results" \
  --output "$run_root/FINAL_TERMINAL.json"
stage=scientific_terminal
