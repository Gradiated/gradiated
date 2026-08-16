#!/usr/bin/env bash
set -Eeuo pipefail

root=${MIRRORED_RING_REMOTE_ROOT:?}
input="$root/input"
artifacts="$root/endpoint-artifacts"
component="$root/component-artifacts/COMPONENT_TERMINAL.json"
checkpoint=/home/glmrunner/gemma4-async-result-pipeline/checkpoint
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
container=gemma-mirrored-ring-candidate
mkdir -p "$artifacts" "$artifacts/candidate-audit"
rm -f "$artifacts/ENDPOINT_RESULT.json" "$artifacts/WORKER_TERMINAL.json"

atomic_terminal() {
  python3 - "$artifacts/WORKER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(".part")
q.write_text(json.dumps({
  "schema_version":1,
  "status":"terminal",
  "classification":sys.argv[2],
  "message":sys.argv[3],
  "timestamp_utc":datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z"),
},indent=2,sort_keys=True)+"\n")
os.replace(q,p)
PY
}

state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(".part")
x=json.loads(p.read_text()) if p.exists() else {
  "candidate_cuda_started":False,
  "candidate_science_started":False,
}
x[sys.argv[2]]=True
x["updated_unix_s"]=time.time()
q.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
os.replace(q,p)
PY
}

fail() {
  atomic_terminal integration_failure "$1"
  exit 1
}

compact() {
  set +e
  sudo docker logs "$container" >"$artifacts/candidate.server-final.log" 2>&1 || true
  sudo docker inspect "$container" >"$artifacts/candidate.container-inspect.json" 2>&1 || true
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -czf "$root/endpoint-compact.tar.gz.part" -C "$artifacts" .
  mv "$root/endpoint-compact.tar.gz.part" "$root/endpoint-compact.tar.gz"
  sha256sum "$root/endpoint-compact.tar.gz" >"$root/endpoint-compact.tar.gz.sha256"
}
trap compact EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || fail "$BASH_COMMAND"' ERR

python3 - "$component" <<'PY' || fail component_gate_not_positive
import json,sys
x=json.load(open(sys.argv[1]))
assert x.get("component_positive") is True
assert x.get("conditional_endpoint_admitted") is True
assert x.get("semantic_pass") is True
PY
test -d "$checkpoint" || fail checkpoint_missing
sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>&1 || fail pinned_image_not_resident

python3 - "$artifacts/INVOCATION_STATE.json" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(".part")
q.write_text(json.dumps({
  "candidate_cuda_started":False,
  "candidate_science_started":False,
  "updated_unix_s":time.time(),
},indent=2,sort_keys=True)+"\n")
os.replace(q,p)
PY

base_args=(
  --model-path /work/checkpoint --tokenizer-path /work/checkpoint
  --served-model-name google/gemma-4-31B-it --dtype bfloat16 --quantization fp8
  --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port 30000
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85
  --enable-metrics --skip-server-warmup --enable-dynamic-chunking
  --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32
  --prefill-attention-backend triton --decode-attention-backend triton --page-size 1
  --num-continuous-decode-steps 1 --triton-attention-num-kv-splits 8
)
printf '%q ' "${base_args[@]}" >"$artifacts/server-args.txt"

sudo docker rm -f gemma-width16384-candidate gemma-ring-candidate \
  gemma-ring-control "$container" >/dev/null 2>&1 || true
sudo docker stop gemma4-async-result-pipeline >/dev/null 2>&1 || true
state candidate_cuda_started
sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
  -v "$checkpoint:/work/checkpoint:ro" -v "$root:/work/mirrored" \
  -e PYTHONPATH=/work/mirrored/input:/sgl-workspace/sglang/python \
  -e STACKED_FRONTIER_ARM=candidate -e RING_CACHE_ARM=candidate \
  -e RING_CACHE_TRACE_TRANSITIONS=0 \
  -e RING_CACHE_AUDIT=/work/mirrored/endpoint-artifacts/candidate-audit/ring.jsonl \
  -e RESIDUAL_CANDIDATE_AUDIT=/work/mirrored/endpoint-artifacts/candidate-audit/residual.jsonl \
  -e QKV_EPILOGUE_AUDIT=/work/mirrored/endpoint-artifacts/candidate-audit/qkv.jsonl \
  -e FP8_MODULE_AUDIT=/work/mirrored/endpoint-artifacts/candidate-audit/modules.jsonl \
  -e FP8_CONSUMER_AUDIT=/work/mirrored/endpoint-artifacts/candidate-audit/consumers.jsonl \
  -e FP8_RUNTIME_AUDIT=/work/mirrored/endpoint-artifacts/candidate-audit/runtime.json \
  -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
  "$image" python3 /work/mirrored/input/proven_v0513_endpoint_entrypoint.py \
  "${base_args[@]}" >"$artifacts/candidate.container-id"

ready=0
for _ in $(seq 1 180); do
  if curl -fsS http://127.0.0.1:30000/v1/models \
    >"$artifacts/candidate.models.json" 2>"$artifacts/candidate.models.stderr"; then
    ready=1
    break
  fi
  if [[ "$(sudo docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" != true ]]; then
    break
  fi
  sleep 4
done
sudo docker logs "$container" >"$artifacts/candidate.server-start.log" 2>&1 || true
[[ "$(sudo docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" == true ]] \
  || fail candidate_container_not_running
[[ "$ready" -eq 1 ]] || fail candidate_server_not_ready

python3 - "$artifacts/semantic-smoke.json" <<'PY' || fail semantic_smoke_failed
import json,sys,urllib.request
cases=[
  ("json","json",'Return only a JSON object with key "status" and string value "ok".'),
  ("ready","READY","Reply with exactly: READY"),
  ("arithmetic","4","What is 2+2? Reply with only the number."),
]
rows=[]
for label,want,prompt in cases:
 body=json.dumps({"model":"google/gemma-4-31B-it","messages":[{"role":"user","content":prompt}],"temperature":0,"max_tokens":32}).encode()
 raw=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:30000/v1/chat/completions",body,{"Content-Type":"application/json"}),timeout=180))
 text=raw["choices"][0]["message"]["content"].strip()
 if want=="json":
  try: ok=json.loads(text.strip("`json\n"))=={"status":"ok"}
  except (TypeError,ValueError): ok=False
 else: ok=text==want
 rows.append({"label":label,"want":want,"text":text,"pass":ok})
value={"rows":rows,"pass":all(row["pass"] for row in rows)}
open(sys.argv[1],"w").write(json.dumps(value,indent=2,sort_keys=True)+"\n")
assert value["pass"]
PY

state candidate_science_started
sudo docker exec "$container" python3 \
  /work/mirrored/input/fp8_qkv_paired_runner.py \
  --output /work/mirrored/endpoint-artifacts/candidate \
  --arm mirrored_ring_candidate --concurrency 32 \
  >"$artifacts/candidate.runner.stdout" 2>"$artifacts/candidate.runner.stderr" \
  || fail candidate_runner_failed

python3 - \
  "$input/persisted_ring_endpoint.json" \
  "$artifacts/candidate/TERMINAL.json" \
  "$artifacts/semantic-smoke.json" \
  "$artifacts/candidate-audit/ring.jsonl" \
  "$component" \
  "$artifacts/ENDPOINT_RESULT.json" <<'PY' || fail endpoint_evaluation_failed
import hashlib,json,math,os,pathlib,sys
baseline=json.load(open(sys.argv[1]))
candidate=json.load(open(sys.argv[2]))
smoke=json.load(open(sys.argv[3]))
audit_path=pathlib.Path(sys.argv[4])
component_path=pathlib.Path(sys.argv[5])
component=json.loads(component_path.read_text())
events=[json.loads(row) for row in audit_path.read_text().splitlines() if row] if audit_path.exists() else []
captures=[row for row in events if row.get("event")=="ring_decode_captured"]
reservations=[row for row in events if row.get("event")=="ring_region_reserved"]
local_ids=sorted({row.get("layer_id") for row in captures})
expected_local=[index for index in range(60) if index % 6 != 5]
path_ok=(
  local_ids==expected_local
  and bool(reservations)
  and all(
    row.get("window")==1024
    and row.get("physical_tokens")==2048
    and row.get("kv_heads")==16
    and row.get("head_dim")==256
    and row.get("consumer")=="single_invocation_ring_e5m2_fa3"
    and row.get("consumer_invocations")==1
    and row.get("output_logsumexp_merge_count")==0
    and row.get("producer")=="store_mirrored_ring_kv"
    for row in captures
  )
  and all(
    row.get("logical_tokens_per_request")==1024
    and row.get("physical_tokens_per_request")==2048
    and row.get("producer_mirror_positions_per_logical_token")==2
    for row in reservations
  )
)
accounting=(
  candidate.get("cache",{}).get("cached_prompt_tokens_delta")==17120
  and candidate.get("cache",{}).get("uncached_prompt_tokens_delta")==117728
)
control=float(baseline["candidate_service_seconds_per_request"])
changed=float(candidate["service_seconds_per_request"])
valid=(
  candidate.get("pass") is True
  and candidate.get("complete_requests")==32
  and len(candidate.get("rows",[]))==32
  and all(row.get("text_finite") and row.get("text_nonempty") for row in candidate["rows"])
  and accounting and smoke.get("pass") is True and path_ok
  and component.get("semantic_pass") is True
  and math.isfinite(control) and math.isfinite(changed)
)
classification="retain_mirrored_ring" if valid and changed<control else (
  "endpoint_negative" if valid else "invalid"
)
component_hash=hashlib.sha256(component_path.read_bytes()).hexdigest()
value={
  "schema_version":1,
  "status":"terminal",
  "classification":classification,
  "pass":valid,
  "persisted_ring_seconds_per_request":control,
  "candidate_seconds_per_request":changed,
  "reduction_fraction":1-changed/control,
  "economic_ceiling_seconds_per_request":0.6381105231,
  "ceiling_pass":valid and changed<=0.6381105231,
  "candidate":candidate,
  "semantic_smoke":smoke,
  "accounting_pass":accounting,
  "component_terminal_sha256":component_hash,
  "component_transition_semantics":component["boundaries"],
  "candidate_path_proof":{
    "pass":path_ok,
    "local_layer_ids":local_ids,
    "global_layer_count":10,
    "global_paged_e5m2_unchanged_by_construction":True,
    "mirrored_write_proof":bool(reservations),
    "single_fa3_call_proof":len(captures)==50,
    "events":events,
  },
}
out=pathlib.Path(sys.argv[6]); temporary=out.with_suffix(".part")
temporary.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
os.replace(temporary,out)
assert valid
PY

atomic_terminal endpoint_complete candidate_endpoint_terminal_persisted
