#!/usr/bin/env python3
import hashlib, json, re
from pathlib import Path

HERE=Path(__file__).resolve().parent; LAB=HERE.parents[1]
H200=LAB/'projects/h200_bf16_exact_linear_floor'; W4=LAB/'projects/h100_w4_marlin_direct_falsifier'; MECH=LAB/'projects/h100_w4_marlin_exact_shape_mechanism/MECHANISM.json'; HEAD=LAB/'projects/gemma_l40s_parallel_lm_head_component/vllm_parallel_lm_head_bench.py'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
campaign=(LAB/'CAMPAIGN.md').read_text(); brief=(HERE/'PROJECT.md').read_text(); h200=json.loads((H200/'artifacts/RECONCILED_TERMINAL.json').read_text()); w4=json.loads((W4/'artifacts/RECONCILED_TERMINAL.json').read_text()); mech=json.loads(MECH.read_text()); model=re.search(r'`(google/gemma-4-31B-it)` at revision `([0-9a-f]{40})`',campaign); exact=mech['immutable_inputs']['model_geometry']; image=h200['measurement_validity']['runtime_image']; ceiling=mech['immutable_inputs']['planning_ceiling_seconds_per_request']; head_hash=sha(HEAD); post=(H200/'artifacts/POST_CREATE_CORRECTION_AUDIT.json').read_text()
checks={
 'campaign_model':model is not None and exact==f'{model.group(1)}@{model.group(2)}',
 'brief_model':exact in brief,'brief_image':image in brief,'brief_ceiling':str(ceiling) in brief,
 'h200_actual_head':h200['measurement_validity']['conditional_pass'] and h200['measurement_validity']['head_consumer']=='vllm.model_executor.layers.vocab_parallel_embedding.ParallelLMHead',
 'head_program_bound':head_hash in post,
 'geometry':'262,144×5,376' in brief and '358' in brief,
 'workload':'4,214 prompt / 358 output / 12.7% cache' in brief,
 'h100_cleanup':w4['cleanup']['cleanup_pass'] and w4['cleanup']['final_instance_count']==0 and w4['cleanup']['final_disk_count']==0,
 'historical_setup_gate':'>500 seconds' in brief and '<5 seconds' in brief,
 'sentinel':'M8 sentinel atomically retrieved' in brief,
 'conditional':'H100_HEAD_SURVIVES_AND_HISTORICAL_SETUP_DOMINATES_AND_LINEAR_READY' in brief,
 'independent_audit':'separate independent audit' in brief and 'may not create while that audit is pending' in brief,
 'budgets':'35 minutes' in brief and '20 minutes' in brief and '0.34 H100 GPU-hours' in brief and '`$1.30`' in brief,
 'one_allocation':'One allocation' in brief and 'zero repair/restart' in brief,
}
out={'schema_version':1,'type':'h100_parallel_lm_head_director_identity_assertion','pass':all(checks.values()),'checks':checks,'identity':{'model':exact,'image':image,'vllm':h200['measurement_validity']['vllm_version'],'gpu':'NVIDIA H100 80GB HBM3','ceiling_seconds_per_request':ceiling},'authoritative_hashes':{'CAMPAIGN.md':sha(LAB/'CAMPAIGN.md'),'H200_RECONCILED_TERMINAL.json':sha(H200/'artifacts/RECONCILED_TERMINAL.json'),'POST_CREATE_CORRECTION_AUDIT.json':sha(H200/'artifacts/POST_CREATE_CORRECTION_AUDIT.json'),'vllm_parallel_lm_head_bench.py':head_hash,'W4_RECONCILED_TERMINAL.json':sha(W4/'artifacts/RECONCILED_TERMINAL.json'),'MECHANISM.json':sha(MECH),'PROJECT.md':sha(HERE/'PROJECT.md')}}
print(json.dumps(out,indent=2,sort_keys=True)); raise SystemExit(0 if out['pass'] else 1)
