#!/usr/bin/env python3
import argparse, hashlib, json, subprocess
from pathlib import Path

PROJECT=Path(__file__).resolve().parent
IMAGE='docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79'
CONTROLLER=Path('/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py')
FILES=(PROJECT/'kv_paged_actual.py',PROJECT/'remote_stage.sh',PROJECT/'h100_owner.py',CONTROLLER)
def main():
 p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
 probe=subprocess.run(['docker','run','--rm','--network=none','--entrypoint','python3',IMAGE,'-c',"import inspect,json,vllm; from vllm.model_executor.layers.attention.attention import unified_kv_cache_update,unified_attention_with_output; from vllm.v1.attention.ops.triton_unified_attention import unified_attention; print(json.dumps({'vllm':vllm.__version__,'producer':str(inspect.signature(unified_kv_cache_update)),'consumer':str(inspect.signature(unified_attention_with_output)),'backend':str(inspect.signature(unified_attention))}))"],capture_output=True,text=True,timeout=180)
 observed=None
 for line in reversed(probe.stdout.splitlines()):
  try: observed=json.loads(line); break
  except json.JSONDecodeError: pass
 src=(PROJECT/'kv_paged_actual.py').read_text(); remote=(PROJECT/'remote_stage.sh').read_text(); owner=(PROJECT/'h100_owner.py').read_text()
 lifecycle=remote+owner+CONTROLLER.read_text()
 checks={'exact_image_imports_actual_producer_and_backend':isinstance(observed,dict) and observed.get('vllm')=='0.19.1.dev6+g6d4a8e6d2' and 'layer_name' in observed.get('producer','') and 'block_table' in observed.get('backend',''),'real_call_is_first_cuda_atom':all(x in src for x in ('unified_kv_cache_update(key, value','unified_attention','torch.linspace')),'no_standin_or_uninvoked_acceptance':all(x not in src for x in ('reshape_and_cache_flash','flash_attn_varlen_func')),'typed_retrieval_cleanup_owner':all(x in lifecycle for x in ('stage-terminal.json','VerifiedRetainedOwner','start_independent_watchdog','stage_retrieved')),'staged_files':all(x.is_file() for x in FILES)}
 result={'schema_version':1,'type':'h100_actual_paged_fp8_kv_behavioral_precreate','image':IMAGE,'probe_returncode':probe.returncode,'probe_stderr_tail':probe.stderr[-2000:],'observed':observed,'checks':checks,'staged_sha256':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in FILES if x.is_file()},'pass':all(checks.values()),'cuda_execution_boundary':'The exact-image CPU probe binds signatures; the first remotely retrieved CUDA atom invokes unified_kv_cache_update before any timing claim.'}
 a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); return 0 if result['pass'] else 1
if __name__=='__main__': raise SystemExit(main())
