#!/usr/bin/env python3
import argparse, hashlib, inspect, json, os, statistics, time, types
from pathlib import Path
import torch, vllm
from vllm.config import VllmConfig, set_current_vllm_config
from vllm.distributed.parallel_state import ensure_model_parallel_initialized, init_distributed_environment
from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead

MS=(8,16,32,3679); HIDDEN=5376; VOCAB=262144
def atomic(path,value):
 t=path.with_suffix(path.suffix+'.tmp');t.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');os.replace(t,path)
def timing(fn):
 for _ in range(3): fn()
 torch.cuda.synchronize(); values=[]; output=None
 for _ in range(5):
  s,e=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True);s.record();output=fn();e.record();e.synchronize();values.append(s.elapsed_time(e))
 return {'p50_ms':statistics.median(values),'raw_ms':values},output
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();r={'type':'actual_h100_bf16_parallel_lm_head','stage':'head','rows':[],'pass':False}
 try:
  torch.manual_seed(20260717);c=VllmConfig();c.model_config=types.SimpleNamespace(dtype=torch.bfloat16,head_dtype=None,is_moe=False)
  with set_current_vllm_config(c):
   init_distributed_environment(world_size=1,rank=0,distributed_init_method='tcp://127.0.0.1:29500',local_rank=0,backend='nccl');ensure_model_parallel_initialized(1,1)
   with torch.device('cuda'): h=ParallelLMHead(VOCAB,HIDDEN,params_dtype=torch.bfloat16,prefix='model.lm_head')
   h.weight.data.normal_(0,0.01)
   identity={'vllm':vllm.__version__,'gpu':torch.cuda.get_device_name(),'capability':list(torch.cuda.get_device_capability()),'consumer':f'{type(h).__module__}.{type(h).__name__}','consumer_sha256':hashlib.sha256(inspect.getsource(type(h)).encode()).hexdigest()}
   for m in MS:
    x=torch.randn((m,HIDDEN),device='cuda',dtype=torch.bfloat16);torch.cuda.reset_peak_memory_stats();fn=lambda:h.quant_method.apply(h,x,None);t,y=timing(fn);ref=torch.mm(x,h.weight.t());delta=(y.float()-ref.float());rmse=float(torch.sqrt(torch.mean(delta*delta)));rr=float(torch.sqrt(torch.mean(ref.float()*ref.float())));nrmse=rmse/max(rr,1e-12);cos=float(torch.nn.functional.cosine_similarity(y.float().flatten(),ref.float().flatten(),dim=0));ok=bool(torch.isfinite(y).all() and float(y.float().abs().max())>1e-6 and nrmse<=0.01 and cos>=0.999)
    r['rows'].append({'m':m,'timing':t,'finite_nontrivial':bool(torch.isfinite(y).all() and float(y.float().abs().max())>1e-6),'oracle':{'normalized_rmse':nrmse,'cosine_similarity':cos,'pass':ok},'allocator':{'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved()},'pass':ok});del x,y,ref,delta
   r['identity']=identity;r['pass']=len(r['rows'])==4 and all(x['pass'] for x in r['rows'])
 except Exception as e:r['error']={'type':type(e).__name__,'message':str(e)[:4000]}
 atomic(a.output,r);return 0 if r['pass'] else 1
if __name__=='__main__':raise SystemExit(main())
