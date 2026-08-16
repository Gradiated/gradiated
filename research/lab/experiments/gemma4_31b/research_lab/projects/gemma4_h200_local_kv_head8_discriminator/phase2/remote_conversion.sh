#!/usr/bin/env bash
set -Eeuo pipefail

remote=/home/glmrunner/gemma-local-kv8
bound=$remote/phase2-bound
checkpoint=$remote/checkpoint
run_id=local-kv8-conversion-20260719t-phase2
run=$remote/$run_id
image='docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a'
container=gemma-local-kv8-converted-c32
deadline_epoch="${DEADLINE_EPOCH:?missing DEADLINE_EPOCH}"
packaged=0
telemetry_pid=

write_terminal() {
  python3 - "$run/OWNER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
value={'schema_version':1,'status':'terminal','pass':False,'classification':sys.argv[2],
       'message':sys.argv[3],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')}
q.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); q.replace(p)
PY
}

capture_state() {
  sudo docker logs "$container" > "$run/server.log" 2>&1 || true
  sudo docker inspect "$container" > "$run/container-inspect-final.json" 2> "$run/container-inspect-final.stderr" || true
  curl -fsS http://127.0.0.1:30000/get_server_info > "$run/server-info-final.json" 2> "$run/server-info-final.stderr" || true
  nvidia-smi -q > "$run/nvidia-smi-final.txt" 2>&1 || true
}

package() {
  (( packaged == 0 )) || return
  packaged=1
  [[ -z "$telemetry_pid" ]] || { kill "$telemetry_pid" >/dev/null 2>&1 || true; wait "$telemetry_pid" >/dev/null 2>&1 || true; telemetry_pid=; }
  cd "$remote"
  tar --exclude="$run_id/distillation/teacher_capture" --exclude="$run_id/distillation/overlay.safetensors" -czf "$run_id.tar.gz" "$run_id"
  sha256sum "$run_id.tar.gz" > "$run_id.tar.gz.sha256"
}

scientific_fail() {
  trap - ERR
  capture_state
  write_terminal "$1" "$2"
  package
  exit 0
}

on_error() {
  local exit_code=$?
  trap - ERR
  capture_state
  if [[ -f "$run/distillation/SCIENTIFIC_STARTED" ]]; then
    write_terminal scientific_runtime_failure "exit=$exit_code command=$BASH_COMMAND"
    package || true
    exit 0
  fi
  printf '%s\n' "exit=$exit_code command=$BASH_COMMAND" > "$run/PREINVOCATION_FAILURE.txt"
  exit 42
}
trap on_error ERR

(( $(date +%s) < deadline_epoch )) || exit 43
mkdir -p "$run/distillation"
nvidia-smi --query-gpu=timestamp,index,name,utilization.gpu,utilization.memory,memory.used,power.draw,clocks.sm,clocks.mem,temperature.gpu --format=csv -l 1 > "$run/gpu.csv" 2> "$run/gpu.stderr" &
telemetry_pid=$!

cd "$bound"
sha256sum -c BOUND_SHA256.txt > "$run/bound-input-verification.log"
cd "$checkpoint"
sha256sum -c "$bound/CHECKPOINT_SHA256.txt" > "$run/checkpoint-verification.log"
find . -maxdepth 1 -type f -printf '%f\t%s\n' | sort > "$run/checkpoint-before.tsv"
test "$(wc -l < "$run/checkpoint-before.tsv")" -eq 8
test "$(du -sb . | cut -f1)" -eq 62578655208
sudo docker image inspect "$image" > "$run/image-inspect.json"
sudo docker rm -f "$container" > "$run/stopped-container.txt" 2> "$run/stopped-container.stderr" || true

set +e
sudo docker run --rm --gpus all --ipc=host --network host \
  -v "$checkpoint:/work/checkpoint:ro" -v "$bound:/bound:ro" -v "$run:/output" \
  "$image" python3 /bound/distill_local_kv8.py \
    --checkpoint /work/checkpoint \
    --bodies /bound/inputs/request_bodies \
    --contract /bound/TRAINING_CONTRACT.json \
    --output /output/distillation \
  > "$run/distill.stdout" 2> "$run/distill.stderr"
distill_exit=$?
set -e
printf '%s\n' "$distill_exit" > "$run/distill.exit"
if [[ "$distill_exit" -eq 3 ]]; then
  cp "$run/distillation/FIDELITY.json" "$run/FIDELITY.json"
  scientific_fail fidelity_negative heldout_block_or_end_to_end_gate_failed
fi
if [[ "$distill_exit" -ne 0 ]]; then
  if [[ -f "$run/distillation/SCIENTIFIC_STARTED" ]]; then
    scientific_fail distillation_runtime_failure "distill_exit=$distill_exit"
  fi
  printf '%s\n' "distill_exit=$distill_exit" > "$run/PREINVOCATION_FAILURE.txt"
  exit 42
fi
cp "$run/distillation/FIDELITY.json" "$run/FIDELITY.json"
overlay_sha=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["overlay_sha256"])' "$run/FIDELITY.json")
printf '%s  %s\n' "$overlay_sha" "$run/distillation/overlay.safetensors" > "$run/overlay.sha256"

sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
  -e SGLANG_GEMMA4_LOCAL_KV8=1 \
  -e SGLANG_GEMMA4_LOCAL_KV8_MANIFEST=/work/local-kv8-transformed-tensors.json \
  -e SGLANG_GEMMA4_LOCAL_KV8_OVERLAY=/output/distillation/overlay.safetensors \
  -e SGLANG_GEMMA4_LOCAL_KV8_OVERLAY_SHA256="$overlay_sha" \
  -v "$remote:/work" -v "$checkpoint:/work/checkpoint:ro" -v "$bound:/bound:ro" -v "$run:/output" \
  -v "$bound/patch/gemma4_causal.py:/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py:ro" \
  -v "$bound/patch/gemma4_mm.py:/sgl-workspace/sglang/python/sglang/srt/models/gemma4_mm.py:ro" \
  -v "$bound/patch/model_config.py:/sgl-workspace/sglang/python/sglang/srt/configs/model_config.py:ro" \
  "$image" python3 -m sglang.launch_server \
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 \
  --kv-cache-dtype fp8_e5m2 --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 \
  --context-length 12000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics \
  --skip-server-warmup --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope \
  --cuda-graph-max-bs 32 --max-prefill-tokens 16384 --prefill-attention-backend triton \
  --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 \
  --triton-attention-num-kv-splits 8 --stream-interval 1 > "$run/container-id.txt"

ready=0
for attempt in $(seq 1 180); do
  (( $(date +%s) < deadline_epoch )) || scientific_fail deadline_expired server_startup
  if curl -fsS http://127.0.0.1:30000/v1/models > "$run/models.json" 2> "$run/models.stderr"; then ready=1; break; fi
  sleep 4
done
sudo docker logs "$container" > "$run/server-start.log" 2>&1 || true
(( ready == 1 )) || scientific_fail startup_failure server_not_ready
cp "$remote/local-kv8-transformed-tensors.json" "$run/transformed-tensors.json"

sudo docker exec "$container" python3 /bound/bound_sources/coherence_runner.py > "$run/coherence.stdout" 2> "$run/coherence.stderr" || scientific_fail coherence_runtime_failure runner_failed
cp "$remote/coherence.json" "$run/coherence.json"
python3 - "$run/coherence.json" <<'PY' || scientific_fail coherence_negative one_or_more_rules_failed
import json,sys
x=json.load(open(sys.argv[1])); raise SystemExit(0 if x.get('pass') and len(x.get('rows',[]))==3 and all(r.get('rule_pass') for r in x['rows']) else 2)
PY

sudo docker exec "$container" python3 /bound/bound_sources/retrieval_10k_runner.py \
  --checkpoint /work/checkpoint --output "/output/retrieval-10k" \
  > "$run/retrieval.stdout" 2> "$run/retrieval.stderr" || scientific_fail retrieval_negative deterministic_10k_gate_failed
python3 - "$run/retrieval-10k/TERMINAL.json" <<'PY' || scientific_fail retrieval_negative deterministic_10k_gate_failed
import json,sys
x=json.load(open(sys.argv[1])); raise SystemExit(0 if x.get('pass') and x.get('cases')==3 and x.get('exact_matches')==3 else 2)
PY

curl -fsS http://127.0.0.1:30000/metrics > "$run/metrics-before-endpoint.prom"
curl -fsS -o "$run/flush-body.txt" -w '%{http_code}' -X POST http://127.0.0.1:30000/flush_cache > "$run/flush-status.txt"
test "$(cat "$run/flush-status.txt")" = 200 || scientific_fail cache_boundary_failure flush_not_http_200
sudo docker exec "$container" python3 /bound/bound_sources/exact_mix_runner.py \
  --output "/output/exact-mix" --arm local_kv8_distilled_triton_c32 \
  > "$run/exact.stdout" 2> "$run/exact.stderr" || scientific_fail endpoint_runtime_failure exact_runner_failed

capture_state
cd "$checkpoint"
find . -maxdepth 1 -type f -printf '%f\t%s\n' | sort > "$run/checkpoint-after.tsv"
cmp "$run/checkpoint-before.tsv" "$run/checkpoint-after.tsv" || scientific_fail checkpoint_mutation checkpoint_metadata_changed
python3 - "$run/OWNER_TERMINAL.json" "$run/exact-mix/TERMINAL.json" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); candidate=json.load(open(sys.argv[2])); cache=candidate.get('cache',{})
valid=bool(candidate.get('pass') and candidate.get('complete_requests')==32 and cache.get('cached_prompt_tokens_delta')==17120 and cache.get('uncached_prompt_tokens_delta')==117728)
service=candidate.get('service_seconds_per_request')
retained=bool(valid and service is not None and service < 0.9194573941250042)
promoted=bool(valid and service is not None and service <= 0.8734845244187539)
classification='broad_quality_promote' if promoted else ('retained_improvement' if retained else 'endpoint_negative')
value={'schema_version':1,'status':'terminal','classification':classification,'pass':retained,
       'performance_valid':valid,'broad_quality_promoted':promoted,'service_seconds_per_request':service,
       'reference_seconds_per_request':0.9194573941250042,'promotion_ceiling_seconds_per_request':0.8734845244187539,
       'candidate':candidate,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')}
q=p.with_suffix('.part'); q.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); q.replace(p)
PY
package
