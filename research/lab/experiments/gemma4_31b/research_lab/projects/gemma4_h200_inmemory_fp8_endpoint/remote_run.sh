#!/usr/bin/env bash
set -Eeuo pipefail

root=/home/glmrunner/gemma-kernel-frontier
input="$root/input"
checkpoint="$root/checkpoint"
artifacts="$root/artifacts/inmemory-fp8"
run="$artifacts/exact-c32"
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
container=gemma-inmemory-fp8-c32
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
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/inmemory-fp8-terminal.tar.gz" -C "$artifacts" .
  sha256sum "$root/inmemory-fp8-terminal.tar.gz" > "$root/inmemory-fp8-terminal.tar.gz.sha256"
}

fail() {
  terminal "$1" "$2"
  exit 1
}

trap 'test -f "$artifacts/OWNER_TERMINAL.json" || terminal owner_failure "$BASH_COMMAND"' ERR
trap finalize EXIT
rm -f "$artifacts/OWNER_TERMINAL.json"
sha256sum "$input/exact_mix_runner.py" "$input/coherence_runner.py" "$input/exact_shape_oracle.py" "$input/endpoint_entrypoint.py" "$input/remote_run.sh" > "$artifacts/input-sha256.txt"
grep -F '143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7' "$artifacts/input-sha256.txt" >/dev/null
grep -F 'ab2fdf5eca6a4e85617e8357aa7f6eea5f2946576cebf3f885a34100709f20b9' "$artifacts/input-sha256.txt" >/dev/null
grep -F '1144bf287467a463ab565617f0773c152d8f872395cf0cca9803ec2e3a0ed33d' "$artifacts/input-sha256.txt" >/dev/null
test "$(find "$checkpoint" -maxdepth 1 -type f | wc -l)" -eq 8 || fail consumer_failure checkpoint_file_count
sudo docker image inspect "$image" >/dev/null 2>&1 || sudo docker pull "$image" >"$artifacts/image-pull.log" 2>&1
sudo docker image inspect "$image" > "$artifacts/image-inspect.json"
if ! python3 - "$artifacts/oracle.json" 2>/dev/null <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True and x['consumer']['call_count'] >= 1
PY
then
  sudo docker run --rm --gpus all --ipc=host -v "$root:/work" "$image" \
    python3 /work/input/exact_shape_oracle.py --output /work/artifacts/inmemory-fp8/oracle.json \
    >"$artifacts/oracle.stdout" 2>"$artifacts/oracle.stderr" || fail numeric_negative exact_shape_oracle_failed
  python3 - "$artifacts/oracle.json" <<'PY' || fail numeric_negative exact_shape_oracle_gate_failed
import json,sys
x=json.load(open(sys.argv[1])); assert x.get('pass') is True and x['consumer']['call_count'] >= 1
PY
fi
ready=0
rm -f "$artifacts/server-fp8-modules.jsonl" "$artifacts/server-fp8-consumer.jsonl" "$artifacts/server-fp8-runtime.json"
sudo docker stop gemma-critical-path-saturation >/dev/null 2>&1 || true
sudo docker rm -f "$container" >/dev/null 2>&1 || true
sudo docker run -d --name "$container" --gpus all --ipc=host --network host -v "$root:/work" \
    -e INMEMORY_FP8_AUDIT=/work/artifacts/inmemory-fp8/server-fp8-modules.jsonl \
    -e INMEMORY_FP8_CONSUMER_AUDIT=/work/artifacts/inmemory-fp8/server-fp8-consumer.jsonl \
    -e INMEMORY_FP8_RUNTIME_AUDIT=/work/artifacts/inmemory-fp8/server-fp8-runtime.json \
    -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
    "$image" python3 /work/input/endpoint_entrypoint.py \
    --model-path /work/checkpoint --tokenizer-path /work/checkpoint \
    --served-model-name google/gemma-4-31B-it --dtype bfloat16 --quantization fp8 --tp-size 1 \
    --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000 --context-length 5000 \
    --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup \
    --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope \
    --cuda-graph-max-bs 32 --prefill-attention-backend triton --decode-attention-backend triton \
    --page-size 1 --num-continuous-decode-steps 1 --triton-attention-num-kv-splits 8 \
    >"$artifacts/container-id.txt"
sudo docker inspect "$container" >"$artifacts/docker-inspect.json"
python3 - "$artifacts/docker-inspect.json" <<'PY' || fail consumer_failure container_identity_mismatch
import json,sys
row=json.load(open(sys.argv[1]))[0]
assert row['Name'] == '/gemma-inmemory-fp8-c32'
assert row['Config']['Image'].endswith('sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a')
assert row['Config']['Entrypoint'] in (None, [], ['/opt/nvidia/nvidia_entrypoint.sh'])
assert '/work/input/endpoint_entrypoint.py' in row['Config']['Cmd']
assert '--quantization' in row['Config']['Cmd'] and row['Config']['Cmd'][row['Config']['Cmd'].index('--quantization') + 1] == 'fp8'
PY
for _ in $(seq 1 180); do
  if curl -fsS http://127.0.0.1:30000/v1/models >"$artifacts/models.json" 2>"$artifacts/models.stderr"; then ready=1; break; fi
  sleep 5
done
sudo docker logs "$container" >"$artifacts/server-start.log" 2>&1 || true
if [[ "$ready" -ne 1 ]]; then
  grep -Eqi 'out of memory|CUDA.*OOM' "$artifacts/server-start.log" && fail memory_failure server_start_oom
  fail consumer_failure server_not_ready
fi
curl -fsS http://127.0.0.1:30000/metrics >"$artifacts/metrics-preflight.prom"
python3 - "$artifacts/metrics-preflight.prom" <<'PY' || fail consumer_failure queue_not_idle
import re,sys
s=open(sys.argv[1]).read(); values=[]
for line in s.splitlines():
    if line.startswith(('sglang:num_running_reqs', 'sglang:num_queue_reqs')) and not line.startswith('#'):
        values.append(float(line.rsplit(' ', 1)[1]))
assert values and not any(value != 0.0 for value in values)
PY
curl -sS -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:30000/flush_cache -D "$artifacts/flush.headers" -o "$artifacts/flush.body"
grep -E '^HTTP/.* 200' "$artifacts/flush.headers" >/dev/null || fail consumer_failure cache_flush_not_200
test ! -e "$run" || fail endpoint_negative exact_c32_already_consumed
sudo docker exec "$container" python3 /work/input/exact_mix_runner.py --output /work/artifacts/inmemory-fp8/exact-c32 --arm inmemory_fp8 \
  >"$artifacts/exact-c32.stdout" 2>"$artifacts/exact-c32.stderr" || fail endpoint_negative exact_c32_runner_failed
sudo docker logs "$container" >"$artifacts/server-final.log" 2>&1 || true
python3 - "$artifacts/provenance.json" "$artifacts/server-fp8-modules.jsonl" "$artifacts/server-fp8-consumer.jsonl" "$artifacts/server-fp8-runtime.json" <<'PY'
import json,pathlib,sys
out=pathlib.Path(sys.argv[1])
files=[pathlib.Path(x) for x in sys.argv[2:]]
payload={'schema_version':1,'post_timing_capture':True,'module_audit_present':files[0].is_file(),'consumer_audit_present':files[1].is_file(),'runtime_audit_present':files[2].is_file()}
if files[0].is_file(): payload['module_rows']=sum(bool(line.strip()) for line in files[0].read_text().splitlines())
if files[1].is_file(): payload['consumer_rows']=sum(bool(line.strip()) for line in files[1].read_text().splitlines())
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
terminal completed scientific_schedule_completed
