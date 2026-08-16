#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-async-result-pipeline
input="$root/input"
artifacts="$root/artifacts"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
container=gemma4-async-result-pipeline
mkdir -p "$artifacts" "$root/cache/torch_extensions" "$root/live_sources"
rm -f "$artifacts/WORKER_TERMINAL.json"

atomic_terminal() {
  python3 - "$artifacts/WORKER_TERMINAL.json" "$1" <<'PY'
import json,os,pathlib,sys
path=pathlib.Path(sys.argv[1]); temporary=path.with_suffix(path.suffix+".part")
temporary.write_text(json.dumps({"schema_version":1,"status":"terminal","classification":sys.argv[2]},indent=2,sort_keys=True)+"\n")
os.replace(temporary,path)
PY
}

state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys,time
path=pathlib.Path(sys.argv[1]); temporary=path.with_suffix(path.suffix+".part")
value=json.loads(path.read_text()) if path.exists() else {
  "server_started":False,
  "control_scientific_started":False,
  "candidate_cuda_started":False,
  "candidate_scientific_started":False,
  "conditional_c32_started":False,
}
value[sys.argv[2]]=True
value["updated_epoch"]=time.time()
temporary.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
os.replace(temporary,path)
PY
}

fail() {
  atomic_terminal "integration_failure:$1"
  exit 1
}

compact() {
  set +e
  printf 'control\n' >"$artifacts/ASYNC_RESULT_ARM"
  sudo docker logs "$container" >"$artifacts/server-final.log" 2>&1 || true
  sudo docker inspect "$container" >"$artifacts/server-inspect.json" 2>&1 || true
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$root/async-result-compact.tar.gz" \
    -C "$root" artifacts live_sources
  sha256sum "$root/async-result-compact.tar.gz" >"$root/async-result-compact.tar.gz.sha256"
}

trap compact EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || fail "$BASH_COMMAND"' ERR

state owner_started
test -r "$root/checkpoint/model.safetensors.index.json" || fail checkpoint_missing
test "$(sha256sum "$root/checkpoint/model.safetensors.index.json" | awk '{print $1}')" = d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2 || fail checkpoint_identity
sudo docker image inspect "$image" >/dev/null || fail pinned_image_missing

sudo docker run --rm --gpus all --ipc=host \
  -v "$root:/work" \
  -e PYTHONPATH=/sgl-workspace/sglang/python \
  -e LIVE_SOURCE_ROOT=/work/live_sources \
  "$image" \
  python3 /work/input/freeze_live_sources.py \
  >"$artifacts/freeze-live.stdout" 2>"$artifacts/freeze-live.stderr" \
  || fail live_source_binding

cp "$input/async_result_sitecustomize.py" "$input/sitecustomize.py.part"
chmod 0444 "$input/sitecustomize.py.part"
mv -f "$input/sitecustomize.py.part" "$input/sitecustomize.py"
rm -f "$artifacts/async-result-audit.jsonl"
printf 'control\n' >"$artifacts/ASYNC_RESULT_ARM"
sudo docker rm -f gemma4-device-conditional-discriminator >/dev/null 2>&1 || true
sudo docker rm -f "$container" >/dev/null 2>&1 || true

state server_started
checkpoint=$(readlink -f "$root/checkpoint")
sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
  -v "$root:/work" \
  -v "$checkpoint:/work/checkpoint:ro" \
  -e PYTHONPATH=/work/input:/work/inputs/current_stack:/sgl-workspace/sglang/python \
  -e ASYNC_RESULT_AUDIT=/work/artifacts/async-result-audit.jsonl \
  -e ASYNC_RESULT_ARM_FILE=/work/artifacts/ASYNC_RESULT_ARM \
  -e RESIDUAL_ARM=candidate \
  -e QKV_STACK_ARM=candidate \
  -e FP8_STACK_MODULE_AUDIT=/work/artifacts/stack-modules.jsonl \
  -e FP8_STACK_CONSUMER_AUDIT=/work/artifacts/stack-consumers.jsonl \
  -e FP8_MODULE_AUDIT=/work/artifacts/fp8-modules.jsonl \
  -e FP8_CONSUMER_AUDIT=/work/artifacts/fp8-consumers.jsonl \
  -e FP8_RUNTIME_AUDIT=/work/artifacts/fp8-runtime.json \
  -e QKV_EPILOGUE_AUDIT=/work/artifacts/qkv.jsonl \
  -e RESIDUAL_CANDIDATE_AUDIT=/work/artifacts/residual.jsonl \
  -e SYNC_CANDIDATE_AUDIT=/work/artifacts/sync.jsonl \
  -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
  "$image" \
  python3 /work/inputs/current_stack/proven_v0513_endpoint_entrypoint.py \
  --model-path /work/checkpoint \
  --tokenizer-path /work/checkpoint \
  --served-model-name google/gemma-4-31B-it \
  --dtype bfloat16 \
  --quantization fp8 \
  --tp-size 1 \
  --kv-cache-dtype fp8_e5m2 \
  --host 0.0.0.0 \
  --port 30000 \
  --context-length 5000 \
  --max-running-requests 32 \
  --mem-fraction-static 0.85 \
  --enable-metrics \
  --skip-server-warmup \
  --enable-dynamic-chunking \
  --chunked-prefill-size 2048 \
  --enable-fused-qk-norm-rope \
  --cuda-graph-max-bs 32 \
  --prefill-attention-backend triton \
  --decode-attention-backend triton \
  --page-size 1 \
  --triton-attention-num-kv-splits 8 \
  >"$artifacts/container-id"

ready=0
for _ in $(seq 1 180); do
  if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/models.json" 2>"$artifacts/models.stderr"; then
    ready=1
    break
  fi
  if test "$(sudo docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" = false; then
    break
  fi
  sleep 5
done
sudo docker logs "$container" >"$artifacts/server-start.log" 2>&1 || true
test "$ready" -eq 1 || fail server_not_ready
grep -F "num_continuous_decode_steps=1" "$artifacts/server-start.log" >/dev/null || fail one_token_schedule_not_proven
grep -F "disable_overlap_schedule=False" "$artifacts/server-start.log" >/dev/null || fail overlap_schedule_not_proven

if test -s "$artifacts/discriminator-control/TERMINAL.json"; then
  sudo docker exec "$container" python3 /work/input/streaming_discriminator.py \
    --repair-existing /work/artifacts/discriminator-control \
    --checkpoint /work/checkpoint \
    >"$artifacts/discriminator-control-repair.stdout" \
    2>"$artifacts/discriminator-control-repair.stderr" \
    || fail discriminator_control_repair
fi
if ! test -s "$artifacts/discriminator-control/TERMINAL.json"; then
  state control_scientific_started
  sudo docker exec "$container" python3 /work/input/streaming_discriminator.py \
    --output /work/artifacts/discriminator-control \
    --arm control \
    --arm-file /work/artifacts/ASYNC_RESULT_ARM \
    --output-tokens 16 \
    --concurrency 32 \
    >"$artifacts/discriminator-control.stdout" 2>"$artifacts/discriminator-control.stderr" \
    || fail discriminator_control
fi

if ! test -s "$artifacts/discriminator-candidate/TERMINAL.json"; then
  state candidate_cuda_started
  state candidate_scientific_started
  sudo docker exec "$container" python3 /work/input/streaming_discriminator.py \
    --output /work/artifacts/discriminator-candidate \
    --arm candidate \
    --arm-file /work/artifacts/ASYNC_RESULT_ARM \
    --output-tokens 16 \
    --concurrency 32 \
    >"$artifacts/discriminator-candidate.stdout" 2>"$artifacts/discriminator-candidate.stderr" \
    || fail discriminator_candidate
fi

python3 "$input/analyze_discriminator.py" \
  --control "$artifacts/discriminator-control/TERMINAL.json" \
  --candidate "$artifacts/discriminator-candidate/TERMINAL.json" \
  --audit "$artifacts/async-result-audit.jsonl" \
  --output "$artifacts/RESULT_BOUNDARY_COMPONENT.json" \
  >"$artifacts/analyze-discriminator.stdout" 2>"$artifacts/analyze-discriminator.stderr" \
  || fail analyze_discriminator

if grep -F '"conditional_exact_c32_required": true' "$artifacts/RESULT_BOUNDARY_COMPONENT.json" >/dev/null; then
  state conditional_c32_started
  printf 'control\n' >"$artifacts/ASYNC_RESULT_ARM"
  sudo docker exec "$container" python3 /work/inputs/current_stack/fp8_qkv_paired_runner.py \
    --output /work/artifacts/c32-control \
    --arm control \
    >"$artifacts/c32-control.stdout" 2>"$artifacts/c32-control.stderr" \
    || fail c32_control
  printf 'candidate\n' >"$artifacts/ASYNC_RESULT_ARM"
  sudo docker exec "$container" python3 /work/inputs/current_stack/fp8_qkv_paired_runner.py \
    --output /work/artifacts/c32-candidate \
    --arm candidate \
    >"$artifacts/c32-candidate.stdout" 2>"$artifacts/c32-candidate.stderr" \
    || fail c32_candidate
  python3 "$input/analyze_endpoint_pair.py" \
    --control "$artifacts/c32-control/TERMINAL.json" \
    --candidate "$artifacts/c32-candidate/TERMINAL.json" \
    --output "$artifacts/C32_ENDPOINT_TERMINAL.json" \
    || fail analyze_c32
fi

cp "$artifacts/RESULT_BOUNDARY_COMPONENT.json" "$artifacts/TERMINAL.json"
atomic_terminal discriminator_complete
