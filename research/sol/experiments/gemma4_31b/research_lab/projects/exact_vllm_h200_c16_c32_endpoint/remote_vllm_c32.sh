#!/usr/bin/env bash
set -Eeuo pipefail
remote=/home/glmrunner/gemma-attention-endpoint; run_id=vllm-c32-warm-bench-20260718t1912z; root="$remote/$run_id"; art="$root/artifacts"; image='vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79'
mkdir -p "$art" "$root/run"
term(){ python3 - "$art/TERMINAL.json" "$1" "$2" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]);p.write_text(json.dumps({'status':'terminal','pass':False,'classification':sys.argv[2],'message':sys.argv[3]},sort_keys=True)+'\n')
PY
}
finish(){ rc=$?; curl -fsS http://127.0.0.1:30000/metrics >"$art/metrics-final.prom" 2>&1 || true; sudo docker logs gemma-vllm-c32 >"$art/server.log" 2>&1 || true; sudo docker inspect gemma-vllm-c32 >"$art/container.json" 2>&1 || true; test -s "$art/TERMINAL.json" || term owner_failure "exit:$rc"; tar -C "$root" -czf "$root/artifacts.tar.gz" artifacts run; sha256sum "$root/artifacts.tar.gz" >"$root/artifacts.tar.gz.sha256"; exit "$rc"; }
trap finish EXIT
test "$(find "$remote/checkpoint" -maxdepth 1 -type f | wc -l)" -eq 8 || { term owner_failure checkpoint_file_count; exit 1; }
test "$(find "$remote/checkpoint" -maxdepth 1 -type f -printf '%s\n' | awk '{s+=$1}END{printf "%.0f",s}')" = 62578655208 || { term owner_failure checkpoint_bytes; exit 1; }
sudo docker image inspect "$image" >"$art/image.json" 2>/dev/null || sudo docker pull "$image" >"$art/image-pull.log" 2>&1
sudo docker image inspect "$image" >"$art/image.json"; sudo docker rm -f gemma-attention-endpoint gemma-vllm-c32 >/dev/null 2>&1 || true
sudo docker run -d --name gemma-vllm-c32 --gpus all --ipc=host --network host -v "$remote:/work" --entrypoint vllm "$image" serve /work/checkpoint --served-model-name google/gemma-4-31B-it --dtype bfloat16 --kv-cache-dtype fp8_e5m2 --enable-prefix-caching --max-model-len 5000 --max-num-seqs 32 --max-num-batched-tokens 160000 --host 0.0.0.0 --port 30000 >"$art/container-id.txt"
for x in $(seq 1 120); do curl -fsS http://127.0.0.1:30000/v1/models >"$art/models.json" 2>"$art/models.stderr" && break; sudo docker inspect -f '{{.State.Running}}' gemma-vllm-c32 | grep -q true || { term startup_failure container_exited; exit 1; }; sleep 5; done
test -s "$art/models.json" || { term startup_timeout model_not_ready; exit 1; }
(nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,power.draw --format=csv,noheader,nounits -lms 250 >"$art/gpu.csv" 2>"$art/gpu.stderr") & sample=$!
sudo docker exec gemma-vllm-c32 python3 /work/workspace/vllm_c32_consumer.py --output "/work/$run_id/run" >"$art/consumer.stdout" 2>"$art/consumer.stderr" || true; kill "$sample" 2>/dev/null || true
cp "$root/run/TERMINAL.json" "$art/candidate-terminal.json" || { term owner_failure candidate_terminal_missing; exit 1; }
python3 - "$art" <<'PY'
import json,pathlib
p=pathlib.Path(__import__('sys').argv[1]);c=json.loads((p/'candidate-terminal.json').read_text());v=bool(c.get('pass') and c.get('complete_requests')==32 and c.get('cache',{}).get('query_tokens')==134848 and c.get('reload_count')==0);s=c.get('service_seconds_per_request');base=.9194573941250042;ceil=.8734845244187539;cl='negative' if not v else 'promote' if s<=ceil else 'retain_incremental' if s<base else 'negative';(p/'TERMINAL.json').write_text(json.dumps({'status':'terminal','pass':v and cl!='negative','classification':cl,'candidate':c,'comparator_sha256':'1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3','runner_sha256':'143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7','server_state':'vLLM remains resident'},sort_keys=True)+'\n')
PY
