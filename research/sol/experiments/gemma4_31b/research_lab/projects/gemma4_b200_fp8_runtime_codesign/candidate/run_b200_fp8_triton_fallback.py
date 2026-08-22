#!/usr/bin/env python3
import json,sys,traceback
from pathlib import Path
from types import SimpleNamespace
import torch
from vllm.v1.attention.backends.triton_attn import TritonAttentionImpl,TritonAttentionMetadata
from vllm.model_executor.layers.quantization.utils.fp8_utils import cutlass_scaled_mm
OUT=Path(sys.argv[sys.argv.index('--output')+1]);W=8;N=40
def put(x):
 OUT.parent.mkdir(parents=True,exist_ok=True);t=OUT.with_suffix('.tmp');t.write_text(json.dumps(x,indent=2));json.loads(t.read_text());t.replace(OUT)
def timing(fn):
 for _ in range(W):fn()
 torch.cuda.synchronize();a=[]
 for _ in range(N):s,e=torch.cuda.Event(True),torch.cuda.Event(True);s.record();y=fn();e.record();e.synchronize();a.append(s.elapsed_time(e))
 return y,sorted(a)
def rec(v):return {'invocation_scope':'concurrent_batch','completed_requests':32,'samples_ms':v,'p50_ms_per_invocation':v[20],'batch_total_seconds':v[20]/1000,'request_normalized_seconds':v[20]/32000}
def arm(name,kvh,d,ctx,fp8):
 B=32;page=16;blocks=B*((ctx+15)//16);q=torch.randn((B,32,d),device='cuda',dtype=torch.bfloat16);k=torch.randn((B,kvh,d),device='cuda',dtype=torch.bfloat16);v=torch.randn_like(k)
 cache=torch.empty((blocks,2,page,kvh,d),device='cuda',dtype=torch.float8_e4m3fn if fp8 else torch.bfloat16);slots=torch.arange(B,device='cuda',dtype=torch.int64)*((ctx+15)//16)*page+(ctx-1);bt=(torch.arange(blocks,device='cuda',dtype=torch.int32).view(B,-1));starts=torch.arange(B+1,device='cuda',dtype=torch.int32);lens=torch.full((B,),ctx,device='cuda',dtype=torch.int32)
 md=TritonAttentionMetadata(B,1,starts,ctx,lens,bt,slots,0,0,None,None,None,False,0,None,None,None)
 impl=TritonAttentionImpl(32,d,d**-.5,kvh,None,1024 if name=='local' else None,'fp8' if fp8 else 'auto');layer=SimpleNamespace(_q_scale_float=1.,_k_scale=torch.ones((),device='cuda',dtype=torch.float32),_v_scale=torch.ones((),device='cuda',dtype=torch.float32));out=torch.empty_like(q)
 impl.do_kv_cache_update(layer,k,v,cache,slots);torch.cuda.synchronize()
 f=lambda:impl.forward(layer,q,k,v,cache,md,output=out)
 smoke=f();torch.cuda.synchronize(); got,t=timing(f)
 return {'name':name,'native_kv_dtype':str(cache.dtype),'producer':'triton_reshape_and_cache_flash','consumer':'TritonAttentionImpl.forward -> unified_attention','first_call_complete':True,'timing':rec(t),'finite_nonzero':bool(torch.isfinite(got).all() and got.abs().sum()>0)}
def linear_stage():
 rows=[]
 for name,k,n in [('local_qkv',5376,16384),('local_o',8192,5376),('global_qkv',5376,20480),('global_o',16384,5376),('gate_up',5376,43008),('down',21504,5376)]:
  a=torch.randn((32,k),device='cuda',dtype=torch.bfloat16);w=torch.randn((k,n),device='cuda',dtype=torch.bfloat16);s=(448/a.abs().amax().clamp_min(1e-8)).float();a8=(a*s).clamp(-448,448).to(torch.float8_e4m3fn);sw=(448/w.abs().amax().clamp_min(1e-8)).float();bw=(w*sw).clamp(-448,448).to(torch.float8_e4m3fn).t().contiguous();f=lambda:cutlass_scaled_mm(a8,bw,s.reciprocal(),sw.reciprocal(),[1,1],output_dtype=torch.bfloat16);z,t=timing(f);rows.append({'name':name,'consumer':'vllm fp8_utils.cutlass_scaled_mm','first_call_complete':True,'timing':rec(t),'finite_nonzero':bool(torch.isfinite(z).all() and z.abs().sum()>0)})
 return rows
def main():
 r={'schema_version':1,'classification':'pre_science_integration_defect','science_started':False,'warmups':W,'samples':N,'stages':{}}
 try:
  assert torch.cuda.get_device_capability()[0]==10;r['science_started']=True
  r['stages']['linear']=linear_stage();put(r)
  for name,h,d,c in [('local',16,256,1024),('global',4,512,4393)]:
   r['stages'][name]={'bf16':arm(name,h,d,c,False),'e4m3':arm(name,h,d,c,True)};put(r)
  r['classification']='interpretable_exact_triton_fp8_kv_generation'
 except Exception as e:r.update({'classification':'consumer_runtime_defect' if r['science_started'] else 'pre_science_integration_defect','error':repr(e),'traceback':traceback.format_exc()[-6000:]})
 put(r)
if __name__=='__main__':main()
