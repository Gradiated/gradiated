#!/usr/bin/env python3
import argparse, json, os, statistics, time, types
from pathlib import Path
import torch
from vllm.config import VllmConfig, set_current_vllm_config
from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead

def atomic(path, value):
 t=path.with_suffix('.tmp'); t.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(t,path)
def main():
 p=argparse.ArgumentParser(); p.add_argument('--stage',required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--seed',type=int,required=True); a=p.parse_args()
 r={'schema_version':1,'stage':a.stage,'pass':False,'all_actual_consumers_pass':False,'economic_both_envelopes_falsified':False,'rows':[]}; start=time.perf_counter()
 try:
  c=VllmConfig(); c.model_config=types.SimpleNamespace(dtype=torch.bfloat16,head_dtype=None)
  with set_current_vllm_config(c):
   with torch.device('cuda'): head=ParallelLMHead(262144,5376,params_dtype=torch.bfloat16,prefix='model.lm_head')
   head.weight.data.zero_()
   for m in (1,2,4,8,16):
    x=torch.randn((m,5376),device='cuda',dtype=torch.bfloat16); torch.cuda.reset_peak_memory_stats(); fn=lambda: head.quant_method.apply(head,x,None)
    for _ in range(3): fn()
    torch.cuda.synchronize(); samples=[]
    for _ in range(8): s,e=torch.cuda.Event(True),torch.cuda.Event(True); s.record(); fn(); e.record(); e.synchronize(); samples.append(s.elapsed_time(e))
    y=fn(); finite=bool(torch.isfinite(y).all()); err=float(y.float().abs().max()); r['rows'].append({'m':m,'k':5376,'n':262144,'consumer':f'{type(head).__module__}.{type(head).__name__}','method':f'{type(head.quant_method).__module__}.{type(head.quant_method).__name__}','finite':finite,'max_absolute_error_zero_oracle':err,'pass':finite and err<=0.015625,'cuda_event_ms':{'p50':statistics.median(samples),'p95':sorted(samples)[-1]},'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved()}); del x,y
  r['all_actual_consumers_pass']=len(r['rows'])==5 and all(x['pass'] for x in r['rows']); r['pass']=r['all_actual_consumers_pass']
 except Exception as e: r['error']={'type':type(e).__name__,'message':str(e)[:2000]}
 r['useful_gpu_seconds']=time.perf_counter()-start; a.output.parent.mkdir(parents=True,exist_ok=True); atomic(a.output,r); return 0 if r['pass'] else 1
if __name__=='__main__': raise SystemExit(main())
