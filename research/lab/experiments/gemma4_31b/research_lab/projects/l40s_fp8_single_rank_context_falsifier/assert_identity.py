#!/usr/bin/env python3
import hashlib, json
from pathlib import Path
P=Path(__file__).resolve().parent; LAB=P.parent.parent; brief=(P/'PROJECT.md').read_text()
paths={
 'identity':LAB/'projects/l40s_online_fp8_actual_consumer_floor/artifacts/DIRECTOR_IDENTITY_ASSERTION.json',
 'failure':LAB/'projects/l40s_online_fp8_actual_consumer_floor/artifacts/RECONCILED_TERMINAL.json',
 'residual':LAB/'projects/l40s_fp8_attention_kv_residual_floor/ATTENTION_KV_RESIDUAL_FLOOR.json',
 'queue':LAB/'projects/l40s_fp8_c12_c14_background_queue_bound/QUEUE_BOUND.json',
}
data={k:json.loads(v.read_text()) for k,v in paths.items()}
sha=lambda x:hashlib.sha256(x.read_bytes()).hexdigest()
ident=data['identity']; fail=data['failure']; residual=data['residual']; queue=data['queue']
checks={
 'prior_identity_pass':ident.get('pass') is True,
 'failure_bound':fail.get('classification')=='paid_zero_row_current_vllm_tensor_parallel_context_failure',
 'zero_rows_gpu':fail['terminal_failure']['rows']['total']==0 and fail['terminal_failure']['useful_gpu_seconds']==0.0,
 'exact_error':fail['terminal_failure']['error']['message']=='tensor model parallel group is not initialized',
 'cleanup_zero':fail['cleanup']['cleanup_pass'] and fail['cleanup']['final_instance_count']==0 and fail['cleanup']['final_disk_count']==0,
 'residual_terminal':residual['decision']['classification']=='residual_threshold_bound',
 'queue_terminal':queue['decision']['classification']=='background_batching_credible_region',
 'model_image_brief':ident['extracted']['model'] in brief and ident['extracted']['revision'] in brief and ident['extracted']['runtime_image'] in brief,
 'all_shapes_brief':all(f'{v[0]}->{v[1]}' in brief for v in ident['extracted']['shapes'].values()),
 'context_only_no_fallback':all(x in brief for x in ('single-process/single-rank','Do not monkeypatch','direct `torch._scaled_mm`','one allocation','no repair')),
}
out={'schema_version':1,'type':'director_identity_assertion','checks':checks,'pass':all(checks.values()),'extracted':{'identity':ident['extracted'],'prior_failure':{'classification':fail['classification'],'error':fail['terminal_failure']['error']['message'],'rows':fail['terminal_failure']['rows']['total'],'useful_gpu_seconds':fail['terminal_failure']['useful_gpu_seconds']},'residual_decision':residual['decision']['classification'],'queue_decision':queue['decision']['classification']},'authoritative_inputs':{k:{'path':str(v),'sha256':sha(v)} for k,v in paths.items()}}
t=P/'artifacts/DIRECTOR_IDENTITY_ASSERTION.json';t.parent.mkdir(parents=True,exist_ok=True);t.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print(json.dumps(out,sort_keys=True));raise SystemExit(0 if out['pass'] else 1)
