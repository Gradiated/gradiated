#!/usr/bin/env bash
set -Eeuo pipefail

root=${FP8_HEAD_REMOTE_ROOT:?}
producer=/dev/shm/gemma4-fp8-tied-head-topology-resume
artifacts="$root/artifacts"
container=gemma-fp8-tied-head-topology-settled
mkdir -p "$artifacts"
terminal() { python3 - "$artifacts/WORKER_TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix(p.suffix+'.part'); q.write_text(json.dumps({'schema_version':1,'status':'terminal','classification':sys.argv[2],'message':sys.argv[3],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')},indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}
state() { python3 - "$artifacts/INVOCATION_STATE.json" "$1" <<'PY'
import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part'); x=json.loads(p.read_text()) if p.exists() else {'candidate_cuda_started':True,'smoke_science_started':True,'endpoint_science_started':False,'endpoint_request_accepted':False}; x[sys.argv[2]]=True; x['updated_unix_s']=time.time(); q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); os.replace(q,p)
PY
}
finalize() { set +e; sudo docker logs "$container" >"$artifacts/server-final.log" 2>&1 || true; sudo docker inspect "$container" >"$artifacts/container-inspect.json" 2>&1 || true; nvidia-smi --query-gpu=timestamp,name,memory.used,utilization.gpu,power.draw --format=csv,noheader >"$artifacts/gpu-final.csv" 2>&1 || true; tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$root/fp8-graph-endpoint-compact.tar.gz" -C "$artifacts" .; sha256sum "$root/fp8-graph-endpoint-compact.tar.gz" >"$root/fp8-graph-endpoint-compact.tar.gz.sha256"; }
trap finalize EXIT
trap 'test -f "$artifacts/WORKER_TERMINAL.json" || terminal integration_failure "$BASH_COMMAND"' ERR

rm -rf "$artifacts"; mkdir -p "$artifacts"
[[ "$(sudo docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" == true ]] || { terminal integration_failure resident_candidate_server_not_running; exit 1; }
test -s "$producer/artifacts/tied-head/representation.json" || { terminal integration_failure retained_representation_missing; exit 1; }
test -s "$producer/artifacts/SEMANTIC_SMOKE.json" || { terminal integration_failure retained_smoke_missing; exit 1; }
set +e
python3 - "$producer/artifacts/graph-boundary/STATE.json" "$producer/artifacts/graph-boundary/head.jsonl" "$artifacts/GRAPH_TOPOLOGY_DECISION.json" <<'PY'
import json,pathlib,sys
state=json.load(open(sys.argv[1])); heads=[json.loads(x) for x in pathlib.Path(sys.argv[2]).read_text().splitlines() if x]
required={1,2,4,8,12,16,24,32}; observed={int(x['m']) for x in heads if x.get('event')=='e4m3_head' and x.get('candidate_symbol')=='sglang.srt.layers.quantization.fp8_utils.apply_fp8_linear' and x.get('candidate_output',{}).get('dtype')=='torch.bfloat16' and x.get('embedding',{}).get('dtype')=='torch.bfloat16' and x.get('candidate_weight',{}).get('dtype')=='torch.float8_e4m3fn' and x.get('bf16_head_fallback') is False}
captured=set(state.get('successful_capture_batch_sizes',[])); count=int(state.get('candidate_head_count_lower_bound',0)); out={'schema_version':1,'required_padded_m':sorted(required),'captured_padded_m':sorted(captured),'e4m3_capture_m':sorted(observed),'candidate_head_count_lower_bound':count,'replayed_logits_processor_output':state.get('last_replay',{}).get('output_type')=='LogitsProcessorOutput','bf16_head_fallback_count':state.get('bf16_head_fallback_count'),'bf16_embedding_preserved':True,'logits_dtype':'torch.bfloat16','sampling_contract':'unchanged_pinned_sampler','post_replay_python_head_required':False,'pass':required.issubset(captured) and required.issubset(observed) and count>=25 and state.get('last_replay',{}).get('output_type')=='LogitsProcessorOutput' and state.get('bf16_head_fallback_count')==0}
pathlib.Path(sys.argv[3]).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); raise SystemExit(0 if out['pass'] else 20)
PY
topology_rc=$?; set -e; [[ "$topology_rc" == 0 ]] || { terminal graph_capture_reject retained_topology_contract_failed; exit 0; }
state endpoint_science_started
sudo docker exec "$container" python3 /work/fp8-topology-endpoint/input/binding/fp8_qkv_paired_runner.py --output /work/fp8-topology-endpoint/artifacts/endpoint --arm fp8_tied_head_e4m3_captured_graph_ring --concurrency 32 >"$artifacts/endpoint.runner.stdout" 2>"$artifacts/endpoint.runner.stderr" || { terminal endpoint_runner_failed resident_endpoint_runner_failed; exit 1; }
state endpoint_request_accepted
set +e
python3 - "$producer/artifacts/endpoint/TERMINAL.json" "$producer/artifacts/SEMANTIC_SMOKE.json" "$artifacts/GRAPH_TOPOLOGY_DECISION.json" "$producer/artifacts/graph-boundary/STATE.json" "$artifacts/ENDPOINT_RESULT.json" <<'PY'
import json,math,pathlib,sys
candidate,smoke,topology,state=[json.load(open(x)) for x in sys.argv[1:5]]; comparator=0.6556567115001144; latency=float(candidate['service_seconds_per_request']); cache=candidate.get('cache',{}); rows=candidate.get('rows',[])
accounting=cache.get('cached_prompt_tokens_delta')==17120 and cache.get('uncached_prompt_tokens_delta')==117728; finite=candidate.get('complete_requests')==32 and len(rows)==32 and all(x.get('error') is None and x.get('text_finite') is True and x.get('completion_tokens')==358 for x in rows); replay32=32 in state.get('observed_replay_raw_batch_sizes',[]) and state.get('replay_count_lower_bound',0)>0; valid=bool(candidate.get('pass') is True and accounting and finite and smoke.get('pass') is True and topology.get('pass') is True and replay32 and math.isfinite(latency))
out={'schema_version':1,'status':'terminal','classification':'endpoint_positive' if valid and latency<comparator else 'endpoint_nonpositive' if valid else 'endpoint_invalid','pass':valid and latency<comparator,'valid_endpoint':valid,'candidate_seconds_per_request':latency,'qualified_ring_comparator_seconds_per_request':comparator,'reduction_fraction':1-latency/comparator,'economic_ceiling_seconds_per_request':0.6381105231,'ceiling_pass':valid and latency<=0.6381105231,'accounting_pass':accounting,'finite_32_rows_pass':finite,'candidate_graph_replay_raw_m32_pass':replay32,'component_replayed':False,'graph_topology':topology,'semantic_smoke':smoke,'candidate':candidate,'quality_suite_required':True,'quality_claim_authorized':False}
pathlib.Path(sys.argv[5]).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); raise SystemExit(0 if valid else 20)
PY
endpoint_rc=$?; set -e; [[ "$endpoint_rc" == 0 ]] || { terminal endpoint_invalid endpoint_contract_failed; exit 0; }
terminal completed scientific_terminal_persisted
