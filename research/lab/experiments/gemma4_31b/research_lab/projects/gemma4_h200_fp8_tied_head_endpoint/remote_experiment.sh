#!/usr/bin/env bash
set -Eeuo pipefail

root=${FP8_HEAD_REMOTE_ROOT:?}
input="$root/input"
artifacts="$root/artifacts"
checkpoint=/home/glmrunner/gemma4-async-result-pipeline/checkpoint
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
container=gemma-fp8-tied-head
port=30001
mkdir -p "$artifacts"

atomic() {
  python3 - "$1" "$2" "$3" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(p.suffix+".part")
q.write_text(json.dumps({"schema_version":1,"status":"terminal","classification":sys.argv[2],"message":sys.argv[3],"timestamp_utc":datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z")},indent=2,sort_keys=True)+"\n")
os.replace(q,p)
PY
}

state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(".part")
x=json.loads(p.read_text()) if p.exists() else {"candidate_cuda_started":False,"component_science_started":False,"endpoint_science_started":False}
x[sys.argv[2]]=True; x["updated_unix_s"]=time.time()
q.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n"); os.replace(q,p)
PY
}

fail() {
  atomic "$artifacts/WORKER_TERMINAL.json" integration_failure "$1"
  exit 1
}

finalize() {
  set +e
  sudo docker logs "$container" >"$artifacts/server-final.log" 2>&1 || true
  sudo docker inspect "$container" >"$artifacts/container-inspect.json" 2>&1 || true
  nvidia-smi --query-gpu=timestamp,name,memory.used,utilization.gpu,power.draw --format=csv,noheader >"$artifacts/gpu-final.csv" 2>&1 || true
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/fp8-head-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/fp8-head-compact.tar.gz" >"$root/fp8-head-compact.tar.gz.sha256"
}
trap finalize EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || atomic "$artifacts/WORKER_TERMINAL.json" integration_failure "$BASH_COMMAND"' ERR

rm -rf "$artifacts"
mkdir -p "$artifacts/tied-head" "$artifacts/runtime-audit"
test -d "$checkpoint" || fail checkpoint_missing
sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>&1 || fail pinned_image_missing
sha256sum "$input"/stack/*.py "$input"/binding/* >"$artifacts/input-sha256.txt"

sudo docker rm -f gemma-width-recovered-candidate "$container" >/dev/null 2>&1 || true
state candidate_cuda_started
sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
  -v "$checkpoint:/work/checkpoint:ro" -v "$root:/work/fp8-head" \
  -e PYTHONPATH=/work/fp8-head/input/stack:/sgl-workspace/sglang/python \
  -e STACKED_FRONTIER_ARM=candidate -e RING_CACHE_ARM=candidate \
  -e RING_CACHE_AUDIT=/work/fp8-head/artifacts/runtime-audit/ring.jsonl \
  -e RING_CACHE_TRACE_TRANSITIONS=0 \
  -e RESIDUAL_CANDIDATE_AUDIT=/work/fp8-head/artifacts/runtime-audit/residual.jsonl \
  -e QKV_EPILOGUE_AUDIT=/work/fp8-head/artifacts/runtime-audit/qkv.jsonl \
  -e FP8_MODULE_AUDIT=/work/fp8-head/artifacts/runtime-audit/modules.jsonl \
  -e FP8_CONSUMER_AUDIT=/work/fp8-head/artifacts/runtime-audit/consumers.jsonl \
  -e FP8_RUNTIME_AUDIT=/work/fp8-head/artifacts/runtime-audit/runtime.json \
  -e FP8_TIED_HEAD_ARM=candidate -e FP8_TIED_HEAD_MODE=component \
  -e FP8_TIED_HEAD_AUDIT=/work/fp8-head/artifacts/tied-head \
  -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
  "$image" python3 /work/fp8-head/input/stack/proven_v0513_endpoint_entrypoint.py \
    --model-path /work/checkpoint --tokenizer-path /work/checkpoint \
    --served-model-name google/gemma-4-31B-it --dtype bfloat16 --quantization fp8 \
    --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port "$port" \
    --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 \
    --enable-metrics --skip-server-warmup --enable-dynamic-chunking \
    --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 \
    --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 \
    --num-continuous-decode-steps 1 --triton-attention-num-kv-splits 8 \
    >"$artifacts/container-id"

ready=0
for _ in $(seq 1 180); do
  if curl -fsS "http://127.0.0.1:$port/v1/models" >"$artifacts/models.json" 2>"$artifacts/models.stderr"; then
    ready=1
    break
  fi
  [[ "$(sudo docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" == true ]] || break
  sleep 4
done
sudo docker logs "$container" >"$artifacts/server-start.log" 2>&1 || true
[[ "$ready" == 1 ]] || fail candidate_server_not_ready
test -s "$artifacts/tied-head/representation.json" || fail candidate_representation_absent
grep -q '"embedding_preserved": true' "$artifacts/tied-head/representation.json" || fail embedding_not_preserved
grep -q '"separate_storage": true' "$artifacts/tied-head/representation.json" || fail candidate_storage_not_separate

state component_science_started
python3 - "$port" "$artifacts/component-requests.json" <<'PY'
import concurrent.futures,json,pathlib,sys,time,urllib.request
port=int(sys.argv[1]); output=pathlib.Path(sys.argv[2])
prompts=[f"State the integer {i} in one word." for i in range(32)]
def request(prompt):
 body=json.dumps({"model":"google/gemma-4-31B-it","messages":[{"role":"user","content":prompt}],"temperature":0,"max_tokens":1}).encode()
 req=urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",body,{"Content-Type":"application/json"})
 with urllib.request.urlopen(req,timeout=300) as response:
  return json.load(response)
waves=[]
for wave in range(3):
 start=time.time()
 with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
  rows=list(pool.map(request,prompts))
 waves.append({"wave":wave,"elapsed_s":time.time()-start,"responses":len(rows)})
 if pathlib.Path("/dev/shm/gemma4-fp8-tied-head/artifacts/tied-head/COMPONENT_RESULT.json").exists():
  break
output.write_text(json.dumps({"waves":waves},indent=2)+"\n")
PY
test -s "$artifacts/tied-head/COMPONENT_RESULT.json" || fail component_exact_m32_not_observed

set +e
python3 - "$artifacts/tied-head/COMPONENT_RESULT.json" "$artifacts/COMPONENT_DECISION.json" <<'PY'
import json,math,pathlib,sys
x=json.load(open(sys.argv[1]))
rows=x["rows"]
finite=all(r["numerical"]["candidate_nonfinite_count"]==0 and r["activation_nonfinite_count"]==0 for r in rows)
numerical=all(r["numerical"]["cosine"]>=0.995 and r["numerical"]["relative_l2"]<=0.08 and r["numerical"]["argmax_agreement"]>=0.5 and r["numerical"]["top10_overlap"]>=0.7 for r in rows)
timing=all(r["candidate_timing"]["median_ms"] < r["baseline_timing"]["median_ms"] for r in rows)
m32=next(r for r in rows if r["m"]==32)
ratio=m32["candidate_timing"]["median_ms"]/m32["baseline_timing"]["median_ms"]
head_baseline=0.010869238160550593
whole_bound=head_baseline*(1-ratio)
positive=finite and numerical and timing and x["graph_capture_seen"] and whole_bound>0
out={"schema_version":1,"pass":positive,"finite_pass":finite,"numerical_pass":numerical,"timing_pass":timing,"cuda_graph_pass":x["graph_capture_seen"],"m32_latency_ratio":ratio,"historical_bf16_head_seconds_per_request":head_baseline,"credible_whole_request_reduction_bound_seconds":whole_bound,"promotion":"exact_c32" if positive else "component_reject","component":x}
pathlib.Path(sys.argv[2]).write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
raise SystemExit(0 if positive else 20)
PY
component_rc=$?
set -e
if [[ "$component_rc" -eq 20 ]]; then
  atomic "$artifacts/WORKER_TERMINAL.json" component_reject no_credible_positive_whole_request_bound
  exit 0
fi

set +e
python3 - "$port" "$artifacts/semantic-smoke.json" <<'PY'
import json,pathlib,sys,urllib.request
port=int(sys.argv[1]); rows=[]
cases=[("json","Return only a JSON object with key \"status\" and string value \"ok\"."),("READY","Reply with exactly: READY"),("4","What is 2+2? Reply with only the number.")]
for expected,prompt in cases:
 body=json.dumps({"model":"google/gemma-4-31B-it","messages":[{"role":"user","content":prompt}],"temperature":0,"max_tokens":32}).encode()
 raw=json.load(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",body,{"Content-Type":"application/json"}),timeout=300))
 text=raw["choices"][0]["message"]["content"].strip()
 if expected=="json":
  try: passed=json.loads(text.strip("`json\n")).get("status")=="ok"
  except Exception: passed=False
 else: passed=text==expected
 rows.append({"expected":expected,"text":text[:500],"pass":passed})
out={"pass":all(r["pass"] for r in rows),"rows":rows}
pathlib.Path(sys.argv[2]).write_text(json.dumps(out,indent=2)+"\n")
raise SystemExit(0 if out["pass"] else 20)
PY
smoke_rc=$?
set -e
if [[ "$smoke_rc" -eq 20 ]]; then
  atomic "$artifacts/WORKER_TERMINAL.json" semantic_reject candidate_failed_cheap_semantic_smoke
  exit 0
fi

state endpoint_science_started
sudo docker exec "$container" python3 /work/fp8-head/input/binding/fp8_qkv_paired_runner.py \
  --output /work/fp8-head/artifacts/endpoint --arm fp8_tied_head_e4m3_ring --concurrency 32 \
  >"$artifacts/endpoint.runner.stdout" 2>"$artifacts/endpoint.runner.stderr" || fail endpoint_runner_failed

set +e
python3 - "$artifacts/endpoint/TERMINAL.json" "$artifacts/COMPONENT_DECISION.json" "$artifacts/semantic-smoke.json" "$artifacts/ENDPOINT_RESULT.json" <<'PY'
import json,math,pathlib,sys
candidate,component,smoke=[json.load(open(p)) for p in sys.argv[1:4]]
comparator=0.6556567115001144
latency=float(candidate["service_seconds_per_request"])
accounting=candidate.get("cache",{}).get("cached_prompt_tokens_delta")==17120 and candidate.get("cache",{}).get("uncached_prompt_tokens_delta")==117728
rows=candidate.get("complete_requests")==32 and len(candidate.get("rows",[]))==32 and all(r.get("text_finite") for r in candidate["rows"])
valid=candidate.get("pass") is True and accounting and rows and smoke.get("pass") is True and math.isfinite(latency)
out={"schema_version":1,"status":"terminal","classification":"endpoint_positive" if valid and latency<comparator else "endpoint_nonpositive_or_invalid","pass":valid and latency<comparator,"candidate_seconds_per_request":latency,"qualified_ring_comparator_seconds_per_request":comparator,"reduction_fraction":1-latency/comparator,"economic_ceiling_seconds_per_request":0.6381105231,"ceiling_pass":valid and latency<=0.6381105231,"accounting_pass":accounting,"finite_32_rows_pass":rows,"component":component,"semantic_smoke":smoke,"candidate":candidate,"quality_suite_required":True,"quality_claim_authorized":False}
pathlib.Path(sys.argv[4]).write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
raise SystemExit(0 if valid else 20)
PY
endpoint_rc=$?
set -e
if [[ "$endpoint_rc" -eq 20 ]]; then
  atomic "$artifacts/WORKER_TERMINAL.json" endpoint_invalid endpoint_contract_failed
  exit 0
fi
atomic "$artifacts/WORKER_TERMINAL.json" completed scientific_terminal_persisted
