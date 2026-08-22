#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lab_dir=$(cd -- "$project_dir/../.." && pwd)
artifact_root=${STREAMING_GLOBAL_KV_ARTIFACT_ROOT:?}; bench=${STREAMING_GLOBAL_KV_BENCH:?}; expected=${STREAMING_GLOBAL_KV_EXPECTED_CLAIMED_AT:?}; release_by=${STREAMING_GLOBAL_KV_RELEASE_BY_UTC:?}; image=${STREAMING_GLOBAL_KV_IMAGE:?}; endpoint=${STREAMING_GLOBAL_KV_ENDPOINT_COMMAND:?}
pool=(env PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab_dir")
repair=/root/workspace/research/factory/tools/repair-handshake
"${pool[@]}" show --bench "$bench" >"$artifact_root/r1-bench.json"
readarray -t c < <(python3 - "$artifact_root/r1-bench.json" "$expected" <<'PY'
import json,sys
b=json.load(open(sys.argv[1])); assert b['claim']['claimed_at']==sys.argv[2] and b['claim']['project']=='gemma4_streaming_global_kv_memory_schedule'
r=b['resource']; print(r['ssh_user']); print(r['public_ipv4']); print(r['ssh_identity_path']); print(r['known_hosts_namespace'])
PY
)
user=${c[0]}; host=${c[1]}; key=${c[2]}; known=${c[3]}; remote=/home/glmrunner/streaming-global-kv
ssh=(ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" "$user@$host")
scp=(scp -p -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known")
stop=0; heartbeat(){ while [[ $stop == 0 ]]; do sleep 45; "${pool[@]}" heartbeat --project gemma4_streaming_global_kv_memory_schedule >"$artifact_root/heartbeat-r1.json" 2>&1 || true; done; }; heartbeat & hb=$!
cleanup(){ stop=1; kill "$hb" 2>/dev/null || true; wait "$hb" 2>/dev/null || true; }; trap cleanup EXIT
repair_wait(){ local kind; kind=$1; local diagnostic; diagnostic=$2; local scope; scope=$3; local rid; rid="streaming-global-kv-r1-${scope}"; "$repair" ready --root "$artifact_root" --repair-id "$rid" --deadline "$release_by" --failure-kind "$kind" --diagnostic "$diagnostic" --retry-scope "$scope" >"$artifact_root/repair-ready-r1.json"; "$repair" wait --root "$artifact_root" --repair-id "$rid" --deadline "$release_by" --poll-seconds 15 >"$artifact_root/repair-wait-r1.json" || true; }
"${ssh[@]}" "install -d '$remote/out/triton-cache' '$remote/out/xdg-cache'"
set +e
"${ssh[@]}" "sudo -n docker run --rm --gpus all --user \$(id -u):\$(id -g) -e TRITON_CACHE_DIR=/out/triton-cache -e XDG_CACHE_HOME=/out/xdg-cache -v '$remote/input:/work:ro' -v '$remote/out:/out' '$image' python3 /work/streaming_global_kv_h200_runner.py --output /out/CUDA_DISCRIMINATOR_R1.json" >"$artifact_root/cuda-r1.stdout" 2>"$artifact_root/cuda-r1.stderr"
code=$?
set -e
if [[ $code != 0 ]]; then repair_wait recoverable_cuda_integration "cuda_r1_exit_$code" cuda_discriminator; exit 1; fi
"${scp[@]}" "$user@$host:$remote/out/CUDA_DISCRIMINATOR_R1.json" "$artifact_root/CUDA_DISCRIMINATOR_R1.json"
python3 - "$artifact_root/CUDA_DISCRIMINATOR_R1.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); assert x['gates_pass'] and x['endpoint_eligible']
PY
set +e; "${ssh[@]}" "cd '$remote' && STREAMING_GLOBAL_KV_OUTPUT_ROOT='$remote/out/endpoint-r1' $endpoint" >"$artifact_root/endpoint-r1.stdout" 2>"$artifact_root/endpoint-r1.stderr"; code=$?; set -e
if [[ $code != 0 ]]; then repair_wait recoverable_endpoint_integration "endpoint_r1_exit_$code" endpoint_only; exit 1; fi
"${pool[@]}" show --bench "$bench" >"$artifact_root/pre-release-r1.json"
python3 - "$artifact_root/pre-release-r1.json" "$expected" <<'PY'
import json,sys
assert json.load(open(sys.argv[1]))['claim']['claimed_at']==sys.argv[2]
PY
"${pool[@]}" release --project gemma4_streaming_global_kv_memory_schedule --condition ready
