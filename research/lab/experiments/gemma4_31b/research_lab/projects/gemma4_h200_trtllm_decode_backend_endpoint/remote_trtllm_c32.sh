#!/usr/bin/env bash
set -Eeuo pipefail

remote=/home/glmrunner/gemma-attention-endpoint
run_id=trtllm-decode-c32-20260718t1937z
root="$remote/$run_id"
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
container=gemma-trtllm-decode-c32
mkdir -p "$root"

terminal() {
  python3 - "$root/OWNER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); t=p.with_suffix('.part')
t.write_text(json.dumps({'schema_version':1,'status':'terminal','pass':False,'classification':sys.argv[2],'message':sys.argv[3],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n'); t.replace(p)
PY
}
trap 'terminal owner_failure "$BASH_COMMAND"' ERR

sha256sum "$remote/workspace/exact_mix_runner.py" > "$root/remote-runner.sha256"
test "$(awk '{print $1}' "$root/remote-runner.sha256")" = 143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7
test "$(find "$remote/checkpoint" -maxdepth 1 -type f | wc -l)" = 8
sudo docker image inspect "$image" > "$root/image-inspect.json"

# The predecessor left a failed vLLM container. Do not disturb an SGLang container.
sudo docker ps -a --format '{{.ID}} {{.Image}} {{.Names}}' > "$root/containers-before.txt"
while read -r id image_name name; do
  [[ -z "${id:-}" ]] && continue
  if [[ "$image_name $name" == *vllm* || "$name" == *vllm* ]]; then sudo docker rm -f "$id"; fi
done < "$root/containers-before.txt"

sudo docker run -d --name "$container" --gpus all --ipc=host --network host -v "$remote:/work" "$image" \
  python3 -m sglang.launch_server \
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint --dtype bfloat16 --tp-size 1 \
  --kv-cache-dtype fp8_e5m2 --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 \
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup \
  --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 \
  --prefill-attention-backend triton --decode-attention-backend trtllm_mha --page-size 64 > "$root/container-id.txt"

ready=0
for _ in $(seq 1 120); do
  if curl -fsS http://127.0.0.1:30000/v1/models > "$root/models.json" 2> "$root/models.stderr"; then ready=1; break; fi
  sleep 4
done
if (( ready != 1 )); then sudo docker logs "$container" > "$root/server.log" 2>&1 || true; terminal startup_failure server_not_ready; exit 71; fi
sudo docker inspect "$container" > "$root/container-inspect.json"
sudo docker logs "$container" > "$root/server-start.log" 2>&1

grep -F "prefill_attention_backend='triton'" "$root/server-start.log"
grep -F "decode_attention_backend='trtllm_mha'" "$root/server-start.log"
grep -F "page_size=64" "$root/server-start.log"
grep -F "kv_cache_dtype='fp8_e5m2'" "$root/server-start.log"
if grep -Eiq 'trtllm_mha.*falling back|fallback.*trtllm_mha|falling back.*attention' "$root/server-start.log"; then terminal unsupported backend_fallback; exit 72; fi

curl -fsS http://127.0.0.1:30000/metrics > "$root/metrics-preflight.prom"
if grep -Eq '^sglang:(num_running_requests|num_queued_requests).* [^0]' "$root/metrics-preflight.prom"; then terminal owner_failure nonzero_queue_before_flush; exit 73; fi
curl -fsS -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:30000/flush_cache -D "$root/flush-cache.headers" -o "$root/flush-cache.body"
grep -F '200' "$root/flush-cache.headers"

sudo docker exec "$container" python3 /work/workspace/exact_mix_runner.py --output "/work/$run_id/exact-mix" --arm trtllm_mha_decode_page64
sudo docker logs "$container" > "$root/server.log" 2>&1
sudo docker inspect "$container" > "$root/container-inspect-final.json"
tar -C "$remote" -czf "$remote/$run_id.tar.gz" "$run_id"
