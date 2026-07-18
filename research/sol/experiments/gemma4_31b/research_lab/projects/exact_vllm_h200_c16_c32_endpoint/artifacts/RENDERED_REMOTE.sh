#!/usr/bin/env bash
set -Eeuo pipefail
w=/home/glmrunner/gemma-owner-local-view
deadline=9999999999
started_epoch=$(date +%s)
mkdir -p "$w/artifacts" "$w/runtime"
finalize() {
  rc=$?
  curl -fsS http://127.0.0.1:30000/metrics > "$w/artifacts/metrics-final.prom" || true
  sudo docker logs gemma-vllm > "$w/artifacts/server.log" 2>&1 || true
  sudo docker inspect gemma-vllm > "$w/artifacts/container-inspect-final.json" 2>&1 || true
  if test -f "$w/runtime/gpu-telemetry.pid"; then kill "$(cat "$w/runtime/gpu-telemetry.pid")" 2>/dev/null || true; wait "$(cat "$w/runtime/gpu-telemetry.pid")" 2>/dev/null || true; fi
  cp "$w/runtime/gpu-telemetry.csv" "$w/artifacts/gpu-telemetry.csv" 2>/dev/null || true
  python3 - "$w/artifacts" "$started_epoch" "$rc" <<'PY'
import json,sys,time
from pathlib import Path
p=Path(sys.argv[1]); start=int(sys.argv[2]); rc=int(sys.argv[3])
semantic=json.loads((p/'semantic/TERMINAL.json').read_text()) if (p/'semantic/TERMINAL.json').is_file() else {'pass':False}
vllm=json.loads((p/'vllm/TERMINAL.json').read_text()) if (p/'vllm/TERMINAL.json').is_file() else {'pass':False}
market=any(a.get('concurrency') in (8,16) and a.get('completed_requests_per_second',0)>=2.094181 for a in vllm.get('arms',[]))
ready=(p/'sglang-image-ready.json').is_file() and time.time() <= 9999999999-600
ran_sglang=(p/'sglang/TERMINAL.json').is_file()
trigger={'pass':semantic.get('pass') is True and vllm.get('pass') is True and vllm.get('failure_count')==0 and vllm.get('reload_count')==0 and market and ready,'market_rps_pass':market,'sglang_start_ready_within_ten_minutes':ready,'run_sglang':ran_sglang,'classification':'vllm_market_trigger_true' if ran_sglang else 'vllm_market_trigger_false_cleanup'}
tmp=p/'VLLM_MARKET_TRIGGER.json.part'; tmp.write_text(json.dumps(trigger,sort_keys=True)); tmp.replace(p/'VLLM_MARKET_TRIGGER.json')
summary={'schema_version':1,'semantic':semantic,'vllm':vllm,'trigger':trigger,'provider_active_seconds':time.time()-start,'provider_rate_usd_per_hour':2.45,'estimated_compute_cost_usd':(time.time()-start)*2.45/3600,'remote_exit_code':rc}
tmp=p/'SUMMARY.json.part'; tmp.write_text(json.dumps(summary,sort_keys=True)); tmp.replace(p/'SUMMARY.json')
PY
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C "$w" -czf "$w/results.tar.gz.part" artifacts runtime
  mv "$w/results.tar.gz.part" "$w/results.tar.gz"
  sha256sum "$w/results.tar.gz" > "$w/results.tar.gz.sha256.part"
  mv "$w/results.tar.gz.sha256.part" "$w/results.tar.gz.sha256"
  exit "$rc"
}
trap finalize EXIT
if ! command -v docker >/dev/null 2>&1; then sudo apt-get update -qq && sudo apt-get install -y -qq docker.io curl ca-certificates; fi
sudo systemctl enable --now docker
if ! docker info >/dev/null 2>&1; then echo docker_unavailable >&2; exit 61; fi
if ! command -v nvidia-ctk >/dev/null 2>&1; then
 curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
 curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
 sudo apt-get update -qq && sudo apt-get install -y -qq nvidia-container-toolkit && sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
fi
sudo docker pull 'vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79'
sudo docker image inspect 'vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79' > "$w/runtime/image-inspect.json"
sudo docker run --rm --gpus all --entrypoint nvidia-smi 'vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79' > "$w/runtime/nvidia-smi-image.txt"
(while test $(date +%s) -lt "$deadline"; do nvidia-smi --query-gpu=timestamp,name,uuid,memory.total,memory.used,utilization.gpu,utilization.memory,power.draw --format=csv,noheader,nounits; sleep 1; done) > "$w/runtime/gpu-telemetry.csv" 2> "$w/runtime/gpu-telemetry.stderr" & echo $! > "$w/runtime/gpu-telemetry.pid"
sudo docker run -d --name gemma-vllm --gpus all --ipc=host --shm-size=32g -p 30000:30000 -v "$w:$w" --entrypoint vllm 'vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79' serve "$w/model" --served-model-name 'google/gemma-4-31B-it' --dtype bfloat16 --max-model-len 12000 --max-num-seqs 32 --max-num-batched-tokens 65536 --enable-prefix-caching --enable-metrics --host 0.0.0.0 --port 30000 > "$w/runtime/container-id"
while ! curl -fsS http://127.0.0.1:30000/v1/models > "$w/runtime/models.json"; do
 if test "$(sudo docker inspect -f '{{.State.Running}}' gemma-vllm 2>/dev/null || true)" != true; then sudo docker logs gemma-vllm >&2 || true; exit 70; fi
 test $(date +%s) -lt "$deadline" || exit 71; sleep 5
done
sudo docker pull 'docker.io/lmsysorg/sglang:dev-gemma4@sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427' && sudo docker image inspect 'docker.io/lmsysorg/sglang:dev-gemma4@sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427' > "$w/artifacts/sglang-image-ready.json"
sudo docker exec gemma-vllm python3 "$w/input/trace_endpoint_runner.py" --trace "$w/input/TRACE_PACKET.json" --output "$w/artifacts/semantic" --mode semantic
sudo docker exec gemma-vllm python3 "$w/input/trace_endpoint_runner.py" --trace "$w/input/TRACE_PACKET.json" --output "$w/artifacts/vllm" --mode endpoint_c16_c32 --deadline-epoch 9999999999
if python3 - "$w/artifacts" "$deadline" <<'PY'
import json,sys,time
from pathlib import Path
p=Path(sys.argv[1]); deadline=int(sys.argv[2]); semantic=json.loads((p/'semantic/TERMINAL.json').read_text()); vllm=json.loads((p/'vllm/TERMINAL.json').read_text())
market=any(a.get('concurrency') in (8,16) and a.get('completed_requests_per_second',0)>=2.094181 for a in vllm.get('arms',[]))
ready=(p/'sglang-image-ready.json').is_file() and time.time()<=deadline-600
raise SystemExit(0 if semantic.get('pass') is True and vllm.get('pass') is True and vllm.get('failure_count')==0 and vllm.get('reload_count')==0 and market and ready else 1)
PY
then
 sudo docker rm -f gemma-vllm
 sudo docker run -d --name gemma-sglang --gpus all --ipc=host --shm-size=32g -p 30000:30000 -v "$w:$w" 'docker.io/lmsysorg/sglang:dev-gemma4@sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427' python3 -m sglang.launch_server --model-path "$w/model" --served-model-name 'google/gemma-4-31B-it' --dtype bfloat16 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000
 until curl -fsS http://127.0.0.1:30000/v1/models > "$w/runtime/sglang-models.json"; do test $(date +%s) -lt "$deadline" || exit 73; sleep 5; done
 sudo docker exec gemma-sglang python3 "$w/input/trace_endpoint_runner.py" --trace "$w/input/TRACE_PACKET.json" --output "$w/artifacts/sglang" --mode sglang
fi
