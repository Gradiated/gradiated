#!/usr/bin/env python3
import json, sys, traceback
from pathlib import Path
import torch
import torch.nn.functional as F
import flashinfer
from vllm.model_executor.layers.quantization.utils.fp8_utils import cutlass_scaled_mm

OUT=Path(sys.argv[sys.argv.index('--output')+1]); W=8; N=40
FAMS=[('local_qkv',5376,16384),('local_o',8192,5376),('global_qkv_materialized',5376,20480),('global_o',16384,5376),('gate_up',5376,43008),('down',21504,5376)]
def put(x):
 OUT.parent.mkdir(parents=True,exist_ok=True); t=OUT.with_suffix('.tmp');t.write_text(json.dumps(x,indent=2));json.loads(t.read_text());t.replace(OUT)
def q8(x):
 s=(448/x.abs().amax().clamp_min(1e-8)).float();return (x*s).clamp(-448,448).to(torch.float8_e4m3fn),s.reciprocal()
def timeit(fn):
 for _ in range(W):fn()
 torch.cuda.synchronize();v=[]
 for _ in range(N):
  a,b=torch.cuda.Event(True),torch.cuda.Event(True);a.record();y=fn();b.record();b.synchronize();v.append(a.elapsed_time(b))
 return y,sorted(v)
def row(v,scope,req,calls=1):
 return {'invocation_scope':scope,'completed_requests':req,'calls_per_endpoint_batch':calls,'samples_ms_per_invocation':v,'p10_ms_per_invocation':v[4],'p50_ms_per_invocation':v[20],'p90_ms_per_invocation':v[36],'batch_total_seconds':v[20]*calls/1000,'request_normalized_seconds':v[20]*calls/1000/req}
def kv(batch,kvh,d,ctx):
 page=16;pages=batch*((ctx+page-1)//page);k=torch.randn((pages,kvh,page,d),device='cuda',dtype=torch.bfloat16);v=torch.randn_like(k);k8,sk=q8(k);v8,sv=q8(v);cache=torch.stack((k8,v8),1);tables=torch.arange(pages,device='cuda',dtype=torch.int32).view(batch,-1);lens=torch.full((batch,),ctx,device='cuda',dtype=torch.int32);return cache,tables,lens,sk,sv
def main():
 r={'schema_version':1,'classification':'pre_science_integration_defect','science_started':False,'warmups_per_arm':W,'samples_per_arm':N,'hardware':torch.cuda.get_device_name(),'vllm_consumer':'vllm.model_executor.layers.quantization.utils.fp8_utils.cutlass_scaled_mm -> ops.cutlass_scaled_mm','flashinfer':flashinfer.__version__,'arm_markers':[]}
 try:
  assert torch.cuda.get_device_capability()[0]==10
  r['science_started']=True; linear=[]
  for m in (32,3679,384):
   for name,k,n in FAMS:
    a=torch.randn((m,k),device='cuda',dtype=torch.bfloat16); w=torch.randn((k,n),device='cuda',dtype=torch.bfloat16);a8,sa=q8(a);b8,sb=q8(w)
    # B is the required column-major [N,K] view, not the rejected row-major [K,N].
    # vLLM receives an [N,K] weight and transposes it into the CUTLASS-required
    # column-major [K,N] operand; this is the repaired production consumer path.
    bw=b8.t().contiguous()
    f=lambda:cutlass_scaled_mm(a8,bw,sa,sb,[1,1],output_dtype=torch.bfloat16)
    smoke=f();torch.cuda.synchronize();r['arm_markers'].append({'arm':f'linear:{m}:{name}','first_call_complete':True})
    ref=a@w;got,t=timeit(f);e=got.float()-ref.float();linear.append({'m':m,'name':name,'k':k,'n':n,'charged':m!=384,'candidate':row(t,'concurrent_batch' if m==32 else 'request',32 if m==32 else 1),'cosine':float(F.cosine_similarity(got.float().flatten(),ref.float().flatten(),0)),'nrmse':float(e.norm()/ref.float().norm().clamp_min(1e-8))});del a,w,a8,b8,smoke,ref,got;torch.cuda.empty_cache()
  att=[]
  for tag,kvh,d,ctx in [('local',16,256,1024),('global',4,512,4393)]:
   B=32;q=torch.randn((B,32,d),device='cuda',dtype=torch.bfloat16);cache,tables,lens,sk,sv=kv(B,kvh,d,ctx);ws=torch.empty((256<<20,),device='cuda',dtype=torch.uint8);scale=1/(d**.5)
   dec=lambda:flashinfer.decode.trtllm_batch_decode_with_kv_cache(q,cache,ws,tables,lens,ctx,scale,1.0,out_dtype=torch.bfloat16,kv_layout='HND',q_len_per_req=1)
   smoke=dec();torch.cuda.synchronize();r['arm_markers'].append({'arm':f'decode:{tag}','first_call_complete':True});got,t=timeit(dec)
   # Context consumer needs a genuine prefill sequence (not 32 one-token decode rows).
   cc=1;cq=torch.randn((32,32,d),device='cuda',dtype=torch.bfloat16);ccache,ctables,clens,_,_=kv(cc,kvh,d,ctx);cumq=torch.tensor([0,32],device='cuda',dtype=torch.int32);cumkv=torch.tensor([0,ctx],device='cuda',dtype=torch.int32)
   ctxfn=lambda:flashinfer.prefill.trtllm_batch_context_with_kv_cache(cq,ccache,ws,ctables,clens,32,ctx,scale,1.0,cc,cumq,cumkv,out_dtype=torch.bfloat16,kv_layout='HND')
   ctxout=ctxfn();torch.cuda.synchronize();r['arm_markers'].append({'arm':f'context:{tag}','first_call_complete':True});_,ct=timeit(ctxfn)
   att.append({'tag':tag,'q_heads':32,'kv_heads':kvh,'head_dim':d,'context':ctx,'decode_candidate':row(t,'concurrent_batch',32),'context_candidate':row(ct,'concurrent_batch',32),'output_finite':bool(torch.isfinite(got).all()),'consumer':'flashinfer TRTLLM-generation context+decode FP8-KV'})
  r.update({'classification':'interpretable_exact_component_generation','linear':linear,'attention':att,'counter_note':'profiler-off timings; installed consumer identities and first-call markers retained; no counter proxy substituted'})
 except Exception as e:r.update({'classification':'pre_science_integration_defect' if not r['science_started'] else 'consumer_runtime_defect','error':repr(e),'traceback':traceback.format_exc()[-7000:]})
 put(r)
if __name__=='__main__':main()
