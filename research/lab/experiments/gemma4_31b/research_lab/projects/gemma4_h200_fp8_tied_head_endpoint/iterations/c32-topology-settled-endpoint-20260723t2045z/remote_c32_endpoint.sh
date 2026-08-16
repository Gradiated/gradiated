#!/usr/bin/env bash
set -Eeuo pipefail

root=${FP8_HEAD_REMOTE_ROOT:?}
input="$root/input"
artifacts="$root/artifacts"
checkpoint=/home/glmrunner/gemma4-async-result-pipeline/checkpoint
image=docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6
container=gemma-fp8-tied-head-topology-settled
port=30001
mkdir -p "$artifacts"

terminal() {
  python3 - "$artifacts/WORKER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(p.suffix+'.part')
q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}
state() {
  python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
x=json.loads(p.read_text()) if p.exists() else {'candidate_cuda_started':False,'smoke_science_started':False,'endpoint_science_started':False,'endpoint_request_accepted':False}
x[sys.argv[2]]=True; x['updated_unix_s']=time.time(); q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}
fail() { terminal integration_failure "$1"; exit 1; }
finalize() {
  set +e
  sudo docker logs "$container" >"$artifacts/server-final.log" 2>&1 || true
  sudo docker inspect "$container" >"$artifacts/container-inspect.json" 2>&1 || true
  nvidia-smi --query-gpu=timestamp,name,memory.used,utilization.gpu,power.draw --format=csv,noheader >"$artifacts/gpu-final.csv" 2>&1 || true
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/fp8-graph-endpoint-compact.tar.gz" -C "$artifacts" .
  sha256sum "$root/fp8-graph-endpoint-compact.tar.gz" >"$root/fp8-graph-endpoint-compact.tar.gz.sha256"
}
trap finalize EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || terminal integration_failure "$BASH_COMMAND"' ERR

rm -rf "$artifacts"
mkdir -p "$artifacts/tied-head" "$artifacts/graph-boundary" "$artifacts/runtime-audit"
test -d "$checkpoint" || fail checkpoint_missing
sudo docker image inspect "$image" >"$artifacts/image-inspect.json" 2>&1 || fail pinned_image_missing
sha256sum "$input"/stack/*.py "$input"/binding/* "$input"/source/*.py >"$artifacts/input-sha256.txt"
if sudo docker ps --format '{{.Names}}' | grep -qx gemma-static-c32; then
  terminal typed_external_bench_hbm_occupied gemma-static-c32_retains_122GiB_and_port_30001
  exit 0
fi
sudo docker rm -f gemma-width-recovered-candidate gemma-late30-width16384-candidate "$container" >/dev/null 2>&1 || true

state candidate_cuda_started
sudo docker run -d --name "$container" --gpus all --ipc=host --network host \
 -v "$checkpoint:/work/checkpoint:ro" -v "$root:/work/fp8-topology-endpoint" \
 -e PYTHONPATH=/work/fp8-topology-endpoint/input/stack:/sgl-workspace/sglang/python \
 -e STACKED_FRONTIER_ARM=candidate -e RING_CACHE_ARM=candidate \
 -e RING_CACHE_AUDIT=/work/fp8-topology-endpoint/artifacts/runtime-audit/ring.jsonl \
 -e RING_CACHE_TRACE_TRANSITIONS=0 -e RESIDUAL_CANDIDATE_AUDIT=/work/fp8-topology-endpoint/artifacts/runtime-audit/residual.jsonl \
 -e QKV_EPILOGUE_AUDIT=/work/fp8-topology-endpoint/artifacts/runtime-audit/qkv.jsonl \
 -e FP8_MODULE_AUDIT=/work/fp8-topology-endpoint/artifacts/runtime-audit/modules.jsonl \
 -e FP8_CONSUMER_AUDIT=/work/fp8-topology-endpoint/artifacts/runtime-audit/consumers.jsonl \
 -e FP8_RUNTIME_AUDIT=/work/fp8-topology-endpoint/artifacts/runtime-audit/runtime.json \
 -e FP8_TIED_HEAD_ARM=candidate -e FP8_TIED_HEAD_MODE=endpoint \
 -e FP8_TIED_HEAD_AUDIT=/work/fp8-topology-endpoint/artifacts/tied-head \
 -e FP8_GRAPH_BOUNDARY_AUDIT=/work/fp8-topology-endpoint/artifacts/graph-boundary \
 -e SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision \
 "$image" python3 /work/fp8-topology-endpoint/input/stack/proven_v0513_endpoint_entrypoint.py \
 --model-path /work/checkpoint --tokenizer-path /work/checkpoint --served-model-name google/gemma-4-31B-it \
 --dtype bfloat16 --quantization fp8 --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --port "$port" \
 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup \
 --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --cuda-graph-max-bs 32 \
 --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 \
 --triton-attention-num-kv-splits 8 >"$artifacts/container-id"
ready=0
for _ in $(seq 1 180); do
  if curl -fsS "http://127.0.0.1:$port/v1/models" >"$artifacts/models.json" 2>"$artifacts/models.stderr"; then ready=1; break; fi
  [[ "$(sudo docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" == true ]] || break
  sleep 4
done
sudo docker logs "$container" >"$artifacts/server-start.log" 2>&1 || true
[[ "$ready" == 1 ]] || fail candidate_server_not_ready
for _ in $(seq 1 90); do
  test -s "$artifacts/tied-head/representation.json" && break
  sleep 2
done
test -s "$artifacts/tied-head/representation.json" || fail candidate_representation_absent
test -s "$artifacts/graph-boundary/SOURCE_BINDING.json" || fail graph_source_binding_absent
test ! -e "$artifacts/tied-head/COMPONENT_RESULT.json" || fail forbidden_component_replay

state smoke_science_started
python3 - "$port" "$artifacts/SEMANTIC_SMOKE.json" <<'PY'
import json,pathlib,sys,urllib.request
port=int(sys.argv[1]); rows=[]
for expected,prompt in [('json','Return only a JSON object with key "status" and string value "ok".'),('READY','Reply with exactly: READY'),('4','What is 2+2? Reply with only the number.')]:
 body=json.dumps({'model':'google/gemma-4-31B-it','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':32}).encode()
 raw=json.load(urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions',body,{'Content-Type':'application/json'}),timeout=300)); text=raw['choices'][0]['message']['content'].strip()
 if expected=='json':
  try: passed=json.loads(text.removeprefix('```json').removesuffix('```').strip()).get('status')=='ok'
  except Exception: passed=False
 else: passed=text==expected
 rows.append({'expected':expected,'text':text[:500],'pass':passed,'finite':isinstance(text,str),'usage':raw.get('usage',{})})
out={'schema_version':1,'pass':all(x['pass'] for x in rows),'rows':rows}; pathlib.Path(sys.argv[2]).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); raise SystemExit(0 if out['pass'] else 20)
PY
smoke_rc=$?
[[ "$smoke_rc" == 0 ]] || { terminal semantic_reject candidate_failed_cheap_semantic_smoke; exit 0; }

python3 - "$artifacts/graph-boundary/STATE.json" "$artifacts/graph-boundary/head.jsonl" "$artifacts/GRAPH_TOPOLOGY_DECISION.json" <<'PY'
import json,pathlib,sys
state=json.load(open(sys.argv[1])); rows=[json.loads(x) for x in pathlib.Path(sys.argv[2]).read_text().splitlines() if x]
required=[1,2,4,8,12,16,24,32]; captured=set(state.get('successful_capture_batch_sizes',[])); heads={int(x['m']) for x in rows if x.get('event')=='e4m3_head' and x.get('stream_capturing') is True}
out={'schema_version':1,'required_padded_m':required,'captured_padded_m':sorted(captured),'e4m3_capture_m':sorted(heads),'bf16_head_fallback_count':state.get('bf16_head_fallback_count'),'bf16_embedding_preserved':True,'logits_dtype':'torch.bfloat16','sampling_contract':'unchanged_pinned_sampler','pass':set(required).issubset(captured) and set(required).issubset(heads) and state.get('bf16_head_fallback_count')==0}
pathlib.Path(sys.argv[3]).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); raise SystemExit(0 if out['pass'] else 20)
PY
topology_rc=$?
[[ "$topology_rc" == 0 ]] || { terminal graph_capture_reject required_e4m3_capture_shapes_missing; exit 0; }

state endpoint_science_started
sudo docker exec "$container" python3 /work/fp8-topology-endpoint/input/binding/fp8_qkv_paired_runner.py --output /work/fp8-topology-endpoint/artifacts/endpoint --arm fp8_tied_head_e4m3_captured_graph_ring --concurrency 32 >"$artifacts/endpoint.runner.stdout" 2>"$artifacts/endpoint.runner.stderr" || fail endpoint_runner_failed
state endpoint_request_accepted
python3 - "$artifacts/endpoint/TERMINAL.json" "$artifacts/SEMANTIC_SMOKE.json" "$artifacts/GRAPH_TOPOLOGY_DECISION.json" "$artifacts/graph-boundary/STATE.json" "$artifacts/ENDPOINT_RESULT.json" <<'PY'
import json,math,pathlib,sys
candidate,smoke,topology,state=[json.load(open(x)) for x in sys.argv[1:5]]; comparator=0.6556567115001144
cache=candidate.get('cache',{}); rows=candidate.get('rows',[]); latency=float(candidate['service_seconds_per_request'])
accounting=cache.get('cached_prompt_tokens_delta')==17120 and cache.get('uncached_prompt_tokens_delta')==117728
finite=candidate.get('complete_requests')==32 and len(rows)==32 and all(x.get('error') is None and x.get('text_finite') is True and x.get('completion_tokens')==358 for x in rows)
replay32=32 in state.get('observed_replay_raw_batch_sizes',[]) and state.get('replay_count_lower_bound',0)>0
valid=bool(candidate.get('pass') is True and accounting and finite and smoke.get('pass') is True and topology.get('pass') is True and replay32 and math.isfinite(latency))
out={'schema_version':1,'status':'terminal','classification':'endpoint_positive' if valid and latency<comparator else 'endpoint_nonpositive' if valid else 'endpoint_invalid','pass':valid and latency<comparator,'valid_endpoint':valid,'candidate_seconds_per_request':latency,'qualified_ring_comparator_seconds_per_request':comparator,'reduction_fraction':1-latency/comparator,'economic_ceiling_seconds_per_request':0.6381105231,'ceiling_pass':valid and latency<=0.6381105231,'accounting_pass':accounting,'finite_32_rows_pass':finite,'candidate_graph_replay_raw_m32_pass':replay32,'component_replayed':False,'graph_topology':topology,'semantic_smoke':smoke,'candidate':candidate,'quality_suite_required':True,'quality_claim_authorized':False}
pathlib.Path(sys.argv[5]).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); raise SystemExit(0 if valid else 20)
PY
endpoint_rc=$?
[[ "$endpoint_rc" == 0 ]] || { terminal endpoint_invalid endpoint_contract_failed; exit 0; }
terminal completed scientific_terminal_persisted
