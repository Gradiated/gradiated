#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-device-conditional-graph
input="$root/input"
artifacts="$root/artifacts"
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
container=gemma4-device-conditional-discriminator
mkdir -p "$artifacts" "$root/cache/torch_extensions"
rm -f "$artifacts/WORKER_TERMINAL.json"

atomic_json() {
  python3 - "$1" "$2" "$3" <<'PY'
import json,os,pathlib,sys
path=pathlib.Path(sys.argv[1]); temporary=path.with_suffix(path.suffix+'.part')
temporary.write_text(json.dumps({'schema_version':1,'status':sys.argv[2],'classification':sys.argv[3]},indent=2,sort_keys=True)+'\n')
os.replace(temporary,path)
PY
}

state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys
path=pathlib.Path(sys.argv[1]); temporary=path.with_suffix(path.suffix+'.part')
value=json.loads(path.read_text()) if path.exists() else {
  'support_cuda_started':False,
  'support_science_started':False,
  'full_body_server_started':False,
  'full_body_science_started':False,
  'candidate_full_body_started':False,
}
value[sys.argv[2]]=True
temporary.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
os.replace(temporary,path)
PY
}

fail() {
  atomic_json "$artifacts/WORKER_TERMINAL.json" terminal "integration_failure:$1"
  exit 1
}

compact() {
  set +e
  sudo docker logs "$container" >"$artifacts/server-final.log" 2>&1 || true
  sudo docker inspect "$container" >"$artifacts/server-inspect.json" 2>&1 || true
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$root/device-graph-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/device-graph-compact.tar.gz" >"$root/device-graph-compact.tar.gz.sha256"
}

trap compact EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || fail "$BASH_COMMAND"' ERR

test -r "$root/checkpoint/model.safetensors.index.json" || fail checkpoint_missing
test "$(sha256sum "$root/checkpoint/model.safetensors.index.json" | awk '{print $1}')" = d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2 || fail checkpoint_identity
sudo docker image inspect "$image" >/dev/null || fail pinned_image_missing

if test -s "$artifacts/SUPPORT_DISCRIMINATOR.json" && \
   grep -F '"classification": "runtime_discriminator_failure"' "$artifacts/SUPPORT_DISCRIMINATOR.json" >/dev/null; then
  mv "$artifacts/SUPPORT_DISCRIMINATOR.json" "$artifacts/SUPPORT_DISCRIMINATOR.invalid-api.json"
fi
if ! test -s "$artifacts/SUPPORT_DISCRIMINATOR.json"; then
  state support_cuda_started
  state support_science_started
  sudo docker run --rm --gpus all --ipc=host \
    -v "$root:/work" \
    -e TORCH_EXTENSIONS_DIR=/work/cache/torch_extensions \
    -e PYTHONPATH=/sgl-workspace/sglang/python \
    "$image" \
    python3 /work/input/device_graph_discriminator.py \
      --output /work/artifacts/SUPPORT_DISCRIMINATOR.json \
    >"$artifacts/support.stdout" 2>"$artifacts/support.stderr" \
    || fail support_discriminator
fi

if ! test -s "$artifacts/MIXED_LENGTH_WORKLOAD.json"; then
  checkpoint=$(readlink -f "$root/checkpoint")
  test -r "$checkpoint/model.safetensors.index.json" || fail resolved_checkpoint_missing
  cp "$input/device_graph_sitecustomize.py" "$input/sitecustomize.py.part"
  chmod 0444 "$input/sitecustomize.py.part"
  mv -f "$input/sitecustomize.py.part" "$input/sitecustomize.py"
  rm -f "$artifacts/path-audit.jsonl"
  sudo docker rm -f "$container" >/dev/null 2>&1 || true
  state full_body_server_started
  sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
    -v "$root:/work" \
    -v "$checkpoint:/work/checkpoint:ro" \
    -e PYTHONPATH=/work/input:/work/inputs/current_stack:/sgl-workspace/sglang/python \
    -e DEVICE_GRAPH_PATH_AUDIT=/work/artifacts/path-audit.jsonl \
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
  grep -F "num_continuous_decode_steps=1" "$artifacts/server-start.log" >/dev/null || fail host_continuous_decode_default_not_proven
  grep -F "disable_overlap_schedule=False" "$artifacts/server-start.log" >/dev/null || fail baseline_schedule_identity_not_proven

  state full_body_science_started
  sudo docker exec "$container" python3 /work/input/mixed_length_discriminator.py \
    --output /work/artifacts/MIXED_LENGTH_WORKLOAD.json \
    >"$artifacts/mixed-length.stdout" 2>"$artifacts/mixed-length.stderr" \
    || fail mixed_length_workload
fi

python3 "$input/analyze_full_body_audit.py" \
  --support "$artifacts/SUPPORT_DISCRIMINATOR.json" \
  --workload "$artifacts/MIXED_LENGTH_WORKLOAD.json" \
  --audit "$artifacts/path-audit.jsonl" \
  --output "$artifacts/DEVICE_GRAPH_DISCRIMINATOR.json" \
  >"$artifacts/analyze.stdout" 2>"$artifacts/analyze.stderr" \
  || fail full_body_analysis

atomic_json "$artifacts/WORKER_TERMINAL.json" terminal discriminator_complete
