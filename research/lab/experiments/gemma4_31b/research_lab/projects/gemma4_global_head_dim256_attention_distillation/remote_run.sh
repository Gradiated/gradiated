#!/usr/bin/env bash
set -Eeuo pipefail

remote=/home/glmrunner/gemma-attention-endpoint
bound=$remote/workspace/head256-distill-bound-20260718t2311z-r1
run_id=head256-distill-20260718t2311z-r1
run=$remote/$run_id
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
retained_container=gemma-global-head256-rope-c32
container=gemma-global-head256-distilled
deadline_epoch=1784420700
packaged=0

terminal() {
  python3 - "$run/OWNER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','pass':False,'classification':sys.argv[2],'message':sys.argv[3],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n'); q.replace(p)
PY
}

package() {
  (( packaged == 0 )) || return
  packaged=1
  cd "$remote"
  tar --exclude="$run_id/capture" -czf "$run_id.tar.gz" "$run_id"
}

capture_state() {
  sudo docker logs "$container" > "$run/server.log" 2>&1 || true
  sudo docker inspect "$container" > "$run/container-inspect-final.json" 2> "$run/container-inspect-final.stderr" || true
  curl -fsS http://127.0.0.1:30000/get_server_info > "$run/server-info-final.json" 2> "$run/server-info-final.stderr" || true
}

fail() {
  capture_state
  terminal "$1" "$2"
  package
  exit 1
}

on_error() {
  local exit_code=$?
  trap - ERR
  capture_state
  terminal owner_failure "exit=$exit_code command=$BASH_COMMAND"
  package || true
  exit "$exit_code"
}
trap on_error ERR

(( $(date +%s) < deadline_epoch )) || { mkdir -p "$run"; fail deadline_expired before_remote_launch; }
mkdir -p "$run"
cd "$bound"
sha256sum -c BOUND_SHA256.txt > "$run/bound-input-verification.log"
find "$remote/checkpoint" -maxdepth 1 -type f -printf '%f\t%s\n' | sort > "$run/checkpoint-before.tsv"
test "$(wc -l < "$run/checkpoint-before.tsv")" -eq 8 || fail identity_failure checkpoint_file_count
sudo docker image inspect "$image" > "$run/image-inspect.json"
sudo docker rm -f "$retained_container" "$container" > "$run/stopped-containers.txt" 2> "$run/stopped-containers.stderr" || true

set +e
sudo docker run --rm --gpus all --ipc=host --network host \
  -v "$remote:/work" -v "$remote/checkpoint:/work/checkpoint:ro" -v "$bound:/bound:ro" \
  "$image" python3 /bound/distill.py \
    --checkpoint /work/checkpoint \
    --bodies /bound/inputs/request_bodies \
    --contract /bound/TRAINING_CONTRACT.json \
    --output "/work/$run_id/distillation" \
  > "$run/distill.stdout" 2> "$run/distill.stderr"
distill_exit=$?
set -e
printf '%s\n' "$distill_exit" > "$run/distill.exit"
if [[ "$distill_exit" -eq 3 ]]; then
  cp "$run/distillation/FIDELITY.json" "$run/FIDELITY.json"
  terminal fidelity_negative heldout_fidelity_gate_failed
  package
  exit 3
fi
[[ "$distill_exit" -eq 0 ]] || fail distillation_runtime_failure "distill_exit=$distill_exit"
cp "$run/distillation/FIDELITY.json" "$run/FIDELITY.json"
overlay_sha=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["overlay_sha256"])' "$run/FIDELITY.json")

sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
  -e SGLANG_GEMMA4_GLOBAL_HEAD256_SLICE=1 \
  -e SGLANG_GEMMA4_GLOBAL_HEAD256_MANIFEST=/work/head256-distilled-tensors.json \
  -e SGLANG_GEMMA4_GLOBAL_HEAD256_OVERLAY="/work/$run_id/distillation/overlay.safetensors" \
  -e SGLANG_GEMMA4_GLOBAL_HEAD256_OVERLAY_SHA256="$overlay_sha" \
  -v "$remote:/work" -v "$remote/checkpoint:/work/checkpoint:ro" -v "$bound:/bound:ro" \
  -v "$bound/patch/gemma4_causal.py:/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py:ro" \
  -v "$bound/patch/gemma4_mm.py:/sgl-workspace/sglang/python/sglang/srt/models/gemma4_mm.py:ro" \
  -v "$bound/patch/model_config.py:/sgl-workspace/sglang/python/sglang/srt/configs/model_config.py:ro" \
  "$image" python3 -m sglang.launch_server \
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 \
  --kv-cache-dtype fp8_e5m2 --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 \
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics \
  --skip-server-warmup --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope \
  --cuda-graph-max-bs 32 --max-prefill-tokens 16384 --prefill-attention-backend triton \
  --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 \
  --triton-attention-num-kv-splits 8 --stream-interval 1 > "$run/container-id.txt"

ready=0
for attempt in $(seq 1 150); do
  if curl -fsS http://127.0.0.1:30000/v1/models > "$run/models.json" 2> "$run/models.stderr"; then ready=1; break; fi
  sleep 4
done
sudo docker logs "$container" > "$run/server-start.log" 2>&1 || true
(( ready == 1 )) || fail startup_failure server_not_ready
cp "$remote/head256-distilled-tensors.json" "$run/transformed-tensors.json"
sudo docker exec "$container" python3 /bound/bound_sources/coherence_runner.py > "$run/coherence.stdout" 2> "$run/coherence.stderr" || fail coherence_runtime_failure runner_failed
cp "$remote/coherence.json" "$run/coherence.json"
if ! python3 - "$run/coherence.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); raise SystemExit(0 if x.get('pass') and len(x.get('rows',[]))==3 and all(r.get('rule_pass') for r in x['rows']) else 2)
PY
then
  fail coherence_negative one_or_more_rules_failed
fi

curl -fsS http://127.0.0.1:30000/metrics > "$run/metrics-before-flush.prom"
curl -fsS -o "$run/flush-body.txt" -w '%{http_code}' -X POST http://127.0.0.1:30000/flush_cache > "$run/flush-status.txt"
test "$(cat "$run/flush-status.txt")" = 200 || fail cache_boundary_failure flush_not_http_200
sudo docker exec "$container" python3 /bound/bound_sources/exact_mix_runner.py \
  --output "/work/$run_id/exact-mix" --arm global_head256_attention_distilled_triton_c32

capture_state
find "$remote/checkpoint" -maxdepth 1 -type f -printf '%f\t%s\n' | sort > "$run/checkpoint-after.tsv"
cmp "$run/checkpoint-before.tsv" "$run/checkpoint-after.tsv" || fail checkpoint_mutation checkpoint_metadata_changed
python3 - "$run/OWNER_TERMINAL.json" "$run/exact-mix/TERMINAL.json" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); candidate=json.load(open(sys.argv[2])); cache=candidate.get('cache',{})
valid=bool(candidate.get('pass') and candidate.get('complete_requests')==32 and cache.get('cached_prompt_tokens_delta')==17120 and cache.get('uncached_prompt_tokens_delta')==117728)
service=candidate.get('service_seconds_per_request'); promoted=bool(valid and service is not None and service<=0.8734845244187539)
value={'schema_version':1,'status':'terminal','classification':'promote' if promoted else 'endpoint_negative','pass':promoted,'performance_valid':valid,'service_seconds_per_request':service,'candidate':candidate,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')}
q=p.with_suffix('.part'); q.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); q.replace(p)
PY
package
