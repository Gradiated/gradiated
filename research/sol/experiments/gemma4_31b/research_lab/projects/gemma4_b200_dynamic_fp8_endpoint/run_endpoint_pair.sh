#!/usr/bin/env bash
set -Eeuo pipefail
root=${1:?remote_root}; image=${2:?image}; mkdir -p "$root/artifacts"
state(){ python3 - "$root/artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]);q=p.with_suffix('.part');v=json.loads(p.read_text())if p.exists()else{};v[sys.argv[2]]=True;q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n');os.replace(q,p)
PY
}
arm(){
  local name=$1 quant=$2 port=$3
  local out="$root/artifacts/$name" container="gemma4-b200-$name" checkpoint_host
  checkpoint_host=$(readlink -f "$root/checkpoint")
  mkdir -p "$out";sudo -n docker rm -f "$container" >/dev/null 2>&1||true;local cmd=(serve /work/checkpoint --served-model-name google/gemma-4-31B-it --host 127.0.0.1 --port "$port" --dtype bfloat16 --max-model-len 4608 --max-num-seqs 32 --max-num-batched-tokens 134848 --gpu-memory-utilization 0.90 --enable-prefix-caching);[ "$quant" = fp8 ]&&cmd+=(--quantization fp8);sudo -n docker run -d --entrypoint vllm --name "$container" --gpus all --ipc=host --network host -v "$root:/work" -v "$checkpoint_host:/work/checkpoint:ro" "$image" "${cmd[@]}" >"$out/container-id.txt";for _ in $(seq 1 240);do curl -fsS "http://127.0.0.1:$port/v1/models" >"$out/models.json" 2>"$out/models.stderr"&&break;if ! sudo -n docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null|grep -qx true;then sudo -n docker logs "$container" >"$out/server.log" 2>&1||true;return 70;fi;sleep 5;done;curl -fsS "http://127.0.0.1:$port/v1/models" >"$out/models.json";if [ "$name" = dynamic_fp8_candidate ];then state fp8_probe_science_started;python3 "$root/endpoint_driver.py" --host 127.0.0.1 --port "$port" --output "$out/fp8-probe" --arm fp8_probe --requests 1;sudo -n docker logs "$container" >"$out/server.log" 2>&1||true;grep -Eiq 'fp8|float8' "$out/server.log"||return 71;fi;state "${name}_science_started";python3 "$root/endpoint_driver.py" --host 127.0.0.1 --port "$port" --output "$out" --arm "$name";sudo -n docker logs "$container" >"$out/server.log" 2>&1||true;sudo -n docker rm -f "$container" >/dev/null 2>&1||true;}
arm bf16_control none 30000
arm dynamic_fp8_candidate fp8 30001
python3 - "$root/artifacts/bf16_control/TERMINAL.json" "$root/artifacts/dynamic_fp8_candidate/TERMINAL.json" "$root/artifacts/PAIR_TERMINAL.json" <<'PY'
import json,os,pathlib,sys
c,q=(json.load(open(x))for x in sys.argv[1:3]);valid=c['classification']==q['classification']=='endpoint_measurement'and c['complete_requests']==q['complete_requests']==32;v={'schema_version':1,'classification':'dynamic_fp8_endpoint_pair'if valid else'endpoint_pair_invalid','control':c,'candidate':q,'candidate_reduction_fraction':1-q['service_seconds_per_request']/c['service_seconds_per_request']if valid else None,'fixed_denominator_seconds_per_request':0.625149101968745,'price_normalized_target_seconds_per_request':0.500119281574996};p=pathlib.Path(sys.argv[3]);t=p.with_suffix('.part');t.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n');os.replace(t,p)
PY
