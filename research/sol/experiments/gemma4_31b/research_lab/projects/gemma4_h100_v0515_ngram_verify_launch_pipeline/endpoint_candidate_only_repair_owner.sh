#!/usr/bin/env bash
set -euo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h100_v0515_ngram_verify_launch_pipeline
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
key=/root/.config/nebius/glm-campaign/ssh_ed25519
known=/root/.config/nebius/glm-campaign/known_hosts
host=89.169.103.97
remote=/home/glmrunner/gemma4-h100-packed-endpoint
artifact="$project/artifacts/candidate-only-repair-20260725t1457z"
image='docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd'
started=$(date +%s); mkdir -p "$artifact"
heartbeat() { while :; do PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project gemma4_h100_v0515_ngram_verify_launch_pipeline >>"$artifact/heartbeats.log" 2>&1 || true; sleep 45; done; }
heartbeat & hb=$!; trap 'kill "$hb" 2>/dev/null || true' EXIT
ssh -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" "glmrunner@$host" "bash -s -- '$remote' '$image'" >"$artifact/remote.log" 2>&1 <<'REMOTE'
set -euo pipefail
r=$1; image=$2; run="$r/workload-schema-repair-run"; name=packed-endpoint-candidate
sudo --non-interactive docker version --format '{{.Server.Version}}' >/dev/null
python3 - <<'PY'
import hashlib,json,pathlib
r=pathlib.Path('/home/glmrunner/gemma4-h100-packed-endpoint/workload-schema-repair-run')
m=json.loads((r/'FRESH_WORKLOAD.json').read_text()); w=(r/'fresh_workload.jsonl').read_bytes(); stock=json.loads((r/'arm_stock'/'ARM_RESULT.json').read_text())
assert m['status']=='complete' and m['workload_byte_sha256']==hashlib.sha256(w).hexdigest()
assert stock['rows']==791 and not stock['failures']
PY
probe_output=$(sudo --non-interactive docker run --rm --gpus all "$image" python3 -c 'import sglang.srt.speculative.ngram_worker as m; print("__SGLANG_MODULE_PATH__=" + m.__file__)')
mapfile -t module_markers < <(printf '%s\n' "$probe_output" | grep '^__SGLANG_MODULE_PATH__=' || true)
if [ "${#module_markers[@]}" -ne 1 ]; then
  printf 'candidate_module_path_marker_count=%s\n' "${#module_markers[@]}" >&2
  exit 42
fi
module=${module_markers[0]#__SGLANG_MODULE_PATH__=}
case "$module" in
  /*/ngram_worker.py) ;;
  *) printf 'candidate_module_path_invalid=%q\n' "$module" >&2; exit 43 ;;
esac
if [[ "$module" == *$'\n'* || "$module" == *$'\r'* || "$module" == *:* ]]; then
  printf 'candidate_module_path_unsafe=%q\n' "$module" >&2
  exit 44
fi
python3 - "$run/CANDIDATE_MODULE_PATH_GATE.json" "$module" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); value={'state':'validated_module_path_marker','marker':'__SGLANG_MODULE_PATH__','module_path':sys.argv[2]}; q=p.with_suffix('.json.part'); q.write_text(json.dumps(value,sort_keys=True)+'\n'); q.replace(p)
PY
mapfile -t args < <(python3 -c 'import json,shlex; print("\n".join(shlex.quote(x) for x in json.load(open("'"$r"'/packet/candidate-v0.5.15/inputs/ngram-launch.json"))["args"]))')
sudo --non-interactive docker rm -f "$name" >/dev/null 2>&1 || true
sudo --non-interactive docker run -d --name "$name" --network host --gpus all -v "$r/checkpoint:/work/checkpoint:ro" -v "$r/packet:/work/packet:ro" -v "$r/runtime-source/python/sglang/srt/speculative/ngram_worker.py:${module}:ro" "$image" python3 -m sglang.launch_server "${args[@]}"
if ! python3 "$r/endpoint_workload_consumer.py" arm --arm candidate; then sudo --non-interactive docker logs "$name" >"$run/candidate_server.log" 2>&1 || true; exit 41; fi
sudo --non-interactive docker logs "$name" >"$run/candidate_server.log" 2>&1 || true
sudo --non-interactive docker rm -f "$name" >/dev/null
REMOTE
scp -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known" -r "glmrunner@$host:$remote/workload-schema-repair-run" "$artifact/retrieved"
python3 - "$project" "$artifact/retrieved" "$started" <<'PY'
import hashlib,json,sys,time
from pathlib import Path
project=Path(sys.argv[1]); remote=Path(sys.argv[2]); started=int(sys.argv[3])
stock=json.loads((remote/'arm_stock'/'ARM_RESULT.json').read_text()); candidate=json.loads((remote/'arm_candidate'/'ARM_RESULT.json').read_text())
def rows(n): return [json.loads(x) for x in (remote/n/'requests.jsonl').read_text().splitlines()]
s,c=rows('arm_stock'),rows('arm_candidate'); first=None
for x,y in zip(s,c):
 if x['fresh_index']!=y['fresh_index'] or {k:x.get(k) for k in ('output_ids','finish_reason','usage')}!={k:y.get(k) for k in ('output_ids','finish_reason','usage')}:
  first={'fresh_index':x['fresh_index']}; break
result={'schema_version':1,'result':'measured_contemporaneous_fresh_packed_mask_endpoint_pair','candidate':'single_packed_cpu_full_mask_staging','fresh_indices':[61000,61790],'workload_marker_sha256':hashlib.sha256((remote/'FRESH_WORKLOAD.json').read_bytes()).hexdigest(),'workload_byte_sha256':hashlib.sha256((remote/'fresh_workload.jsonl').read_bytes()).hexdigest(),'stock':stock,'candidate_arm':candidate,'semantic_exact':first is None,'first_semantic_divergence':first,'service_time_delta_seconds_per_request':candidate['service_seconds_per_request']-stock['service_seconds_per_request'],'actual_spend_usd':1.65+2.95*(time.time()-started)/3600,'artifacts_remote':str(remote)}
for name,value in [('PACKED_MASK_FRESH_ENDPOINT_WORKLOAD_SCHEMA_REPAIR_RESULT.json',result),('PACKED_MASK_FRESH_ENDPOINT_WORKLOAD_SCHEMA_REPAIR_TERMINAL.json',{**result,'terminal':'scientific_result','stock_arm_consumed':True,'candidate_arm_consumed':True,'candidate_sample_consumed':True})]:
 p=project/name; q=p.with_suffix(p.suffix+'.part'); q.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n'); q.replace(p)
PY
PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_h100_v0515_ngram_verify_launch_pipeline --condition ready --contents 'Fresh workload and stock/candidate endpoint pair completed; server stopped; checkpoint, packet, image, runtime source, workload, and telemetry retained.'
