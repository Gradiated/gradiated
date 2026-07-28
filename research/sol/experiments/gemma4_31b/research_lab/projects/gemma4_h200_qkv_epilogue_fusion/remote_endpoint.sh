#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma4-qkv-epilogue
shared=/home/glmrunner/gemma-kernel-frontier
input="$root/input"
artifacts="$root/artifacts/endpoint"
run="$artifacts/exact-c32"
checkpoint="$shared/checkpoint"
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
container=gemma-qkv-epilogue-c32
mkdir -p "$artifacts"

terminal() {
  python3 - "$artifacts/OWNER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
value={'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')}
q.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}

finalize() {
  set +e
  sudo docker logs "$container" >"$artifacts/server-final.log" 2>&1
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/endpoint-terminal.tar.gz" -C "$artifacts" .
  sha256sum "$root/endpoint-terminal.tar.gz" > "$root/endpoint-terminal.tar.gz.sha256"
}

fail() {
  terminal "$1" "$2"
  exit 1
}

trap 'test -f "$artifacts/OWNER_TERMINAL.json" || terminal owner_failure "$BASH_COMMAND"' ERR
trap finalize EXIT
rm -f "$artifacts/OWNER_TERMINAL.json" "$artifacts/qkv-audit.jsonl"
test "$(find "$checkpoint" -maxdepth 1 -type f | wc -l)" -eq 8 || fail integration_failure checkpoint_not_resident
sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>&1 || fail integration_failure pinned_image_not_resident
sha256sum "$input/qkv_epilogue_discriminator.py" "$input/install_endpoint_patch.py" "$input/exact_mix_runner.py" >"$artifacts/input-sha256.txt"
grep -F '143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7' "$artifacts/input-sha256.txt" >/dev/null || fail integration_failure runner_identity
test ! -e "$run" || fail endpoint_negative exact_c32_already_consumed

sudo docker rm -f gemma-inmemory-fp8-c32 >/dev/null 2>&1 || true
sudo docker rm -f "$container" >/dev/null 2>&1 || true
sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
  -v "$shared:/work" -v "$root:/qkv" \
  -e PYTHONPATH=/qkv/input:/sgl-workspace/sglang/python \
  -e QKV_EPILOGUE_AUDIT=/qkv/artifacts/endpoint/qkv-audit.jsonl \
  --entrypoint bash "$image" -lc \
  'python3 /qkv/input/install_endpoint_patch.py --output /qkv/artifacts/endpoint/PATCH.json && exec python3 -m sglang.launch_server --model-path /work/checkpoint --tokenizer-path /work/checkpoint --served-model-name google/gemma-4-31B-it --dtype bfloat16 --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 --triton-attention-num-kv-splits 8' \
  >"$artifacts/container-id.txt"

ready=0
for _ in $(seq 1 180); do
  if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/models.json" 2>"$artifacts/models.stderr"; then
    ready=1
    break
  fi
  sleep 5
done
sudo docker logs "$container" >"$artifacts/server-start.log" 2>&1 || true
if [[ "$ready" -ne 1 ]]; then
  grep -Eqi 'out of memory|CUDA.*OOM' "$artifacts/server-start.log" && fail integration_failure server_start_oom
  fail integration_failure server_not_ready
fi

curl -fsS http://127.0.0.1:30000/metrics >"$artifacts/metrics-preflight.prom"
python3 - "$artifacts/metrics-preflight.prom" <<'PY' || fail integration_failure queue_not_idle
import re,sys
s=open(sys.argv[1]).read(); values=re.findall(r'sglang:(?:num_running_reqs|num_queue_reqs)\s+([0-9.]+)',s)
assert values and not any(float(x)>0 for x in values)
PY
curl -sS -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:30000/flush_cache -D "$artifacts/flush.headers" -o "$artifacts/flush.body"
grep -E '^HTTP/.* 200' "$artifacts/flush.headers" >/dev/null || fail integration_failure cache_flush_not_200
sudo docker exec "$container" python3 /qkv/input/exact_mix_runner.py --output /qkv/artifacts/endpoint/exact-c32 --arm qkv_epilogue_fusion \
  >"$artifacts/exact-c32.stdout" 2>"$artifacts/exact-c32.stderr" || fail endpoint_negative exact_c32_runner_failed
python3 - "$artifacts/qkv-audit.jsonl" <<'PY' || fail path_unproven qkv_epilogue_audit_failed
import json,sys
rows=[json.loads(line) for line in open(sys.argv[1]) if line.strip()]
geometries={(row['num_q_heads'],row['num_kv_heads'],row['head_dim']) for row in rows}
assert (32,16,256) in geometries and (32,4,512) in geometries
assert all(row['candidate_symbol']=='_qkv_norm_rope_inplace_kernel' and row['dtype']=='torch.bfloat16' for row in rows)
PY
sudo docker inspect "$container" >"$artifacts/container-inspect.json"
sudo docker logs "$container" >"$artifacts/server-final.log" 2>&1 || true
terminal completed scientific_endpoint_completed
