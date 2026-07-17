#!/usr/bin/env bash
set -Eeuo pipefail
deadline=${1:?deadline epoch required}
w=/home/glmrunner/gemma
start_server() {
  mode=$1
  sudo docker rm -f gemma-vllm >/dev/null 2>&1 || true
  cache_args=()
  if test "$mode" = on; then cache_args+=(--enable-prefix-caching); fi
  sudo docker run -d --rm --name gemma-vllm --gpus all --ipc=host --shm-size=32g -p 30000:30000 -v "$w:$w" 'vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79'     vllm serve "$w/model" --served-model-name 'google/gemma-4-31B-it' --dtype bfloat16 --max-model-len 12000 --max-num-seqs 32 --max-num-batched-tokens 65536 --enable-metrics --host 0.0.0.0 --port 30000 "${cache_args[@]}" > "$w/runtime/container-id-prefix-$mode"
  ready=0
  while test $(date +%s) -lt "$deadline"; do
    if curl -fsS http://127.0.0.1:30000/v1/models > "$w/runtime/models-prefix-$mode.json"; then ready=1; break; fi
    sleep 5
  done
  test "$ready" = 1
}
rm -rf "$w/artifacts/prefix-on" "$w/artifacts/prefix-off"
start_server on
sudo docker exec -e VLLM_MODEL='google/gemma-4-31B-it' gemma-vllm python3 "$w/input/gemma_exact_vllm_runner.py" --output "$w/artifacts/prefix-on" --tokenizer "$w/model" --mode prefix-on
start_server off
sudo docker exec -e VLLM_MODEL='google/gemma-4-31B-it' gemma-vllm python3 "$w/input/gemma_exact_vllm_runner.py" --output "$w/artifacts/prefix-off" --tokenizer "$w/model" --mode prefix-off
sudo docker logs gemma-vllm > "$w/artifacts/prefix-off/server.log" 2>&1 || true
cp "$w/runtime/gpu-telemetry.csv" "$w/artifacts/prefix-off/gpu-telemetry-through-prefix.csv"
python3 - "$w/artifacts" <<'PY'
import json,sys,time
from pathlib import Path
root=Path(sys.argv[1]); on=json.loads((root/'prefix-on/runner-result.json').read_text()); off=json.loads((root/'prefix-off/runner-result.json').read_text())
on_rows=[r for p in on['profiles'] for r in p['rows']]; off_rows=[r for p in off['profiles'] for r in p['rows']]
matched=[r['input_token_ids_sha256'] for r in on_rows]==[r['input_token_ids_sha256'] for r in off_rows]
terminal={'schema_version':2,'stage':'prefix_cache_on_off','pass':on.get('pass') is True and off.get('pass') is True and matched,
 'same_allocation_runtime_checkpoint':True,'matched_prompt_ids':matched,'reload_count':2,
 'on_completed_requests_per_second':on['profiles'][0]['completed_requests_per_second'],
 'off_completed_requests_per_second':off['profiles'][0]['completed_requests_per_second'],
 'on_useful_gpu_seconds':on.get('useful_gpu_seconds'),'off_useful_gpu_seconds':off.get('useful_gpu_seconds'),'written_at_epoch':time.time()}
tmp=root/'PREFIX_STAGE_TERMINAL.json.part'; tmp.write_text(json.dumps(terminal,indent=2,sort_keys=True)+'
'); tmp.replace(root/'PREFIX_STAGE_TERMINAL.json')
if not terminal['pass']: raise SystemExit(1)
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C "$w/artifacts" -czf "$w/prefix-stage.tar.gz" prefix-on prefix-off PREFIX_STAGE_TERMINAL.json
sha256sum "$w/prefix-stage.tar.gz" > "$w/prefix-stage.tar.gz.sha256"
