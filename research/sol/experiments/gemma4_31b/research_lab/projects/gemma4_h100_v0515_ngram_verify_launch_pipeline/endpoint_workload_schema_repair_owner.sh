#!/usr/bin/env bash
set -euo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h100_v0515_ngram_verify_launch_pipeline
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
key=/root/.config/nebius/glm-campaign/ssh_ed25519
known=/root/.config/nebius/glm-campaign/known_hosts
host=89.169.103.97
remote=/home/glmrunner/gemma4-h100-packed-endpoint
artifact="$project/artifacts/workload-schema-repair-20260725t1436z"
image='docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd'
started=$(date +%s); mkdir -p "$artifact"
heartbeat() { while :; do PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_h100_v0515_ngram_verify_launch_pipeline >>"$artifact/heartbeats.log" 2>&1 || true; sleep 45; done; }
heartbeat & hb=$!; trap 'kill "$hb" 2>/dev/null || true' EXIT
scp -i "$key" -o UserKnownHostsFile="$known" -o StrictHostKeyChecking=yes "$project/endpoint_workload_consumer.py" "glmrunner@$host:$remote/endpoint_workload_consumer.py"
ssh -i "$key" -o UserKnownHostsFile="$known" -o StrictHostKeyChecking=yes "glmrunner@$host" "bash -s -- '$remote' '$image'" >"$artifact/remote.log" 2>&1 <<'REMOTE'
set -euo pipefail
r=$1; image=$2
mkdir -p "$r/workload-schema-repair-run"
sudo --non-interactive docker version --format '{{.Server.Version}}' >/dev/null
sudo --non-interactive docker image inspect "$image" >/dev/null 2>&1 || sudo --non-interactive docker pull "$image"
python3 "$r/endpoint_workload_consumer.py" construct
run_arm() {
  arm=$1; name="packed-endpoint-$arm"; sudo --non-interactive docker rm -f "$name" >/dev/null 2>&1 || true
  mapfile -t args < <(python3 -c 'import json,shlex; print("\n".join(shlex.quote(x) for x in json.load(open("'"$r"'/packet/candidate-v0.5.15/inputs/ngram-launch.json"))["args"]))')
  extra=()
  if [ "$arm" = candidate ]; then
    module=$(sudo --non-interactive docker run --rm "$image" python3 -c 'import sglang.srt.speculative.ngram_worker as m; print(m.__file__)')
    extra=(-v "$r/runtime-source/python/sglang/srt/speculative/ngram_worker.py:${module}:ro")
  fi
  sudo --non-interactive docker run -d --name "$name" --network host --gpus all -v "$r/checkpoint:/work/checkpoint:ro" -v "$r/packet:/work/packet:ro" "${extra[@]}" "$image" python3 -m sglang.launch_server "${args[@]}"
  if ! python3 "$r/endpoint_workload_consumer.py" arm --arm "$arm"; then sudo --non-interactive docker logs "$name" >"$r/workload-schema-repair-run/${arm}_server.log" 2>&1 || true; exit 31; fi
  sudo --non-interactive docker logs "$name" >"$r/workload-schema-repair-run/${arm}_server.log" 2>&1 || true
  sudo --non-interactive docker rm -f "$name" >/dev/null
}
run_arm stock
run_arm candidate
REMOTE
scp -i "$key" -o UserKnownHostsFile="$known" -o StrictHostKeyChecking=yes -r "glmrunner@$host:$remote/workload-schema-repair-run" "$artifact/remote"
python3 - "$project" "$artifact" "$started" <<'PY'
import hashlib,json,sys,time
from pathlib import Path
project=Path(sys.argv[1]); artifact=Path(sys.argv[2]); started=int(sys.argv[3]); remote=artifact/'remote'
stock=json.loads((remote/'arm_stock'/'ARM_RESULT.json').read_text()); candidate=json.loads((remote/'arm_candidate'/'ARM_RESULT.json').read_text())
def rows(name): return [json.loads(x) for x in (remote/name/'requests.jsonl').read_text().splitlines()]
srows,crows=rows('arm_stock'),rows('arm_candidate')
if len(srows)!=791 or len(crows)!=791: raise RuntimeError('arm_row_count')
first=None
for s,c in zip(srows,crows):
    if s['fresh_index']!=c['fresh_index'] or {k:s.get(k) for k in ('output_ids','finish_reason','usage')}!={k:c.get(k) for k in ('output_ids','finish_reason','usage')}:
        first={'fresh_index':s['fresh_index']}; break
elapsed=time.time()-started; spend=1.55+2.95*elapsed/3600
result={'schema_version':1,'result':'measured_contemporaneous_fresh_packed_mask_endpoint_pair','candidate':'single_packed_cpu_full_mask_staging','workload_marker_sha256':hashlib.sha256((remote/'FRESH_WORKLOAD.json').read_bytes()).hexdigest(),'workload_byte_sha256':hashlib.sha256((remote/'fresh_workload.jsonl').read_bytes()).hexdigest(),'fresh_indices':[61000,61790],'stock':stock,'candidate_arm':candidate,'semantic_exact':first is None,'first_semantic_divergence':first,'service_time_delta_seconds_per_request':candidate['service_seconds_per_request']-stock['service_seconds_per_request'],'actual_spend_usd':spend,'artifacts_remote':str(remote)}
def atomic(name,value):
    path=project/name; part=path.with_suffix(path.suffix+'.part'); part.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n'); part.replace(path)
atomic('PACKED_MASK_FRESH_ENDPOINT_WORKLOAD_SCHEMA_REPAIR_RESULT.json',result)
terminal={**result,'terminal':'scientific_result','candidate_sample_consumed':True,'stock_arm_consumed':True,'candidate_arm_consumed':True,'release_required':True}
atomic('PACKED_MASK_FRESH_ENDPOINT_WORKLOAD_SCHEMA_REPAIR_TERMINAL.json',terminal)
atomic('PACKED_MASK_FRESH_ENDPOINT_GPU_CONSUMER_REPAIR_RESULT.json',result)
atomic('PACKED_MASK_FRESH_ENDPOINT_GPU_CONSUMER_REPAIR_TERMINAL.json',terminal)
PY
PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_h100_v0515_ngram_verify_launch_pipeline --condition ready --contents 'Fresh workload-schema-repair stock/candidate endpoint pair completed; server stopped; image, verified checkpoint, packet, runtime source, workload, and telemetry retained.'
