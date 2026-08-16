#!/usr/bin/env bash
set -Eeuo pipefail

remote=/home/glmrunner/gemma-attention-endpoint
workspace=$remote/workspace/global-head256-rope
run_id=global-head256-rope-c32-20260718t2240z
run=$remote/$run_id
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
retained_container=gemma-global-head256-c32
container=gemma-global-head256-rope-c32
deadline_epoch=1784416800
packaged=0
mkdir -p "$run"

terminal() {
  python3 - "$run/OWNER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','pass':False,'classification':sys.argv[2],'message':sys.argv[3],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n'); q.replace(p)
PY
}
capture_state() {
  sudo docker logs "$container" > "$run/server.log" 2>&1 || true
  sudo docker inspect "$container" > "$run/container-inspect-final.json" 2> "$run/container-inspect-final.stderr" || true
  curl -fsS http://127.0.0.1:30000/get_server_info > "$run/server-info-final.json" 2> "$run/server-info-final.stderr" || true
}
package() {
  (( packaged == 0 )) || return
  packaged=1
  cd "$remote"
  tar -czf "$run_id.tar.gz" "$run_id"
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

(( $(date +%s) < deadline_epoch )) || fail deadline_expired before_remote_launch
find "$remote/checkpoint" -maxdepth 1 -type f -printf '%f\t%s\n' | sort > "$run/checkpoint-before.tsv"
test "$(wc -l < "$run/checkpoint-before.tsv")" -eq 8 || fail identity_failure checkpoint_file_count
sudo docker image inspect "$image" > "$run/image-inspect.json"
sudo docker run --rm "$image" sha256sum \
  /sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py \
  /sgl-workspace/sglang/python/sglang/srt/models/gemma4_mm.py \
  /sgl-workspace/sglang/python/sglang/srt/configs/model_config.py > "$run/container-source-sha256.txt"
grep -F '683895c5140c920199713a18885006d17a1b1b3dda0ba01c797af02d09885856' "$run/container-source-sha256.txt"
grep -F 'e0200b074c49624c5ecb58a0eb075cef696510274bada56dce0a6424b1acad14' "$run/container-source-sha256.txt"
grep -F 'b212439c1cd2e32e289512d151bd4f185dbd13a6644d7d3ba7db7c93ef8b6b09' "$run/container-source-sha256.txt"
sha256sum "$workspace"/* > "$run/transferred-input-sha256.txt"
grep -F '63c6e3151ae46fb05accfd71b23281d7a350e6fb8bbbd9cbef5903f0f065dc25' "$run/transferred-input-sha256.txt"
grep -F '94a5bca79a254ca2642dd300b45af549bfd23718340a56aa83a059df2f95bd45' "$run/transferred-input-sha256.txt"
grep -F 'ba6a44488466db5667c47c8266d33e79eaebb2b4143e6192b0aeb9ce62837132' "$run/transferred-input-sha256.txt"
grep -F '143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7' "$run/transferred-input-sha256.txt"
grep -F 'cdea4e0eddf69057785c0d09ef0e69e25adb5d8b3e2f5deb9bd0658552eb6af3' "$run/transferred-input-sha256.txt"
grep -F 'b662ff32ad05455a27a64db461aa39777727c7d507a43f30508dc17656f0b017' "$run/transferred-input-sha256.txt"

sudo docker rm -f "$retained_container" "$container" > "$run/stopped-candidate-containers.txt" 2> "$run/stopped-candidate-containers.stderr" || true
sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
  -e SGLANG_GEMMA4_GLOBAL_HEAD256_SLICE=1 \
  -e SGLANG_GEMMA4_GLOBAL_HEAD256_MANIFEST=/work/global-head256-transformed-tensors.json \
  -v "$remote:/work" -v "$remote/checkpoint:/work/checkpoint:ro" \
  -v "$workspace/gemma4_causal.py:/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py:ro" \
  -v "$workspace/gemma4_mm.py:/sgl-workspace/sglang/python/sglang/srt/models/gemma4_mm.py:ro" \
  -v "$workspace/model_config.py:/sgl-workspace/sglang/python/sglang/srt/configs/model_config.py:ro" \
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
test -s "$remote/global-head256-transformed-tensors.json" || fail loader_failure transformed_manifest_missing
cp "$remote/global-head256-transformed-tensors.json" "$run/transformed-tensors.json"
sudo docker inspect "$container" > "$run/container-inspect.json"
curl -fsS http://127.0.0.1:30000/get_server_info > "$run/server-info.json"

if ! sudo docker exec "$container" python3 /work/workspace/global-head256-rope/runtime_rotary_oracle.py > "$run/runtime-rotary-oracle.stdout" 2> "$run/runtime-rotary-oracle.stderr"; then
  cp "$remote/rotary-runtime-oracle.json" "$run/runtime-rotary-oracle.json" 2>/dev/null || true
  fail mechanism_oracle_failure pinned_runtime_inverse_frequency_mismatch
fi
cp "$remote/rotary-runtime-oracle.json" "$run/runtime-rotary-oracle.json"

sudo docker exec "$container" python3 /work/workspace/global-head256-rope/coherence_runner.py > "$run/coherence.stdout" 2> "$run/coherence.stderr"
cp "$remote/coherence.json" "$run/coherence.json"
if ! python3 - "$run/coherence.json" <<'PY'
import json,pathlib,sys
result=json.loads(pathlib.Path(sys.argv[1]).read_text())
raise SystemExit(0 if result.get('pass') and len(result.get('rows',[])) == 3 and all(row.get('rule_pass') for row in result['rows']) else 2)
PY
then
  fail coherence_failure one_or_more_rules_failed
fi

curl -fsS http://127.0.0.1:30000/metrics > "$run/metrics-before-flush.prom"
curl -fsS -o "$run/flush-body.txt" -w '%{http_code}' -X POST http://127.0.0.1:30000/flush_cache > "$run/flush-status.txt"
curl -fsS http://127.0.0.1:30000/metrics > "$run/idle-metrics.prom"
test "$(cat "$run/flush-status.txt")" = 200 || fail cache_boundary_failure flush_not_http_200

sudo docker exec "$container" python3 /work/workspace/global-head256-rope/exact_mix_runner.py \
  --output "/work/$run_id/exact-mix" --arm global_head256_rope_preserving_triton_c32

capture_state
find "$remote/checkpoint" -maxdepth 1 -type f -printf '%f\t%s\n' | sort > "$run/checkpoint-after.tsv"
cmp "$run/checkpoint-before.tsv" "$run/checkpoint-after.tsv" || fail checkpoint_mutation checkpoint_metadata_changed
python3 - "$run/OWNER_TERMINAL.json" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','pass':True,'classification':'captured','timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n'); q.replace(p)
PY
package
