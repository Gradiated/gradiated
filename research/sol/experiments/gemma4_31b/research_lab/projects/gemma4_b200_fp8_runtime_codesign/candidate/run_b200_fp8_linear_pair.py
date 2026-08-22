#!/usr/bin/env python3
import json,sys,traceback
from pathlib import Path
import torch
import torch.nn.functional as F
from vllm.model_executor.layers.quantization.utils.fp8_utils import cutlass_scaled_mm
O=Path(sys.argv[sys.argv.index('--output')+1]);W=8;N=40;FAMS=[('local_qkv',5376,16384),('local_o',8192,5376),('global_qkv',5376,20480),('global_o',16384,5376),('gate_up',5376,43008),('down',21504,5376)]
def save(x):
 O.parent.mkdir(parents=True,exist_ok=True);t=O.with_suffix('.tmp');t.write_text(json.dumps(x,indent=2));json.loads(t.read_text());t.replace(O)
def tm(f):
 for _ in range(W):f()
 torch.cuda.synchronize();x=[]
 for _ in range(N):a,b=torch.cuda.Event(True),torch.cuda.Event(True);a.record();y=f();b.record();b.synchronize();x.append(a.elapsed_time(b))
 return y,sorted(x)
def met(x,m):return {'samples_ms':x,'p50_ms':x[20],'scope':'concurrent_batch' if m==32 else 'request','completed_requests':32 if m==32 else 1,'batch_total_seconds':x[20]/1000,'request_normalized_seconds':x[20]/1000/(32 if m==32 else 1)}
def main():
 r={'schema_version':1,'classification':'pre_science_integration_defect','science_started':False,'warmups':W,'samples':N,'rows':[]}
 try:
  assert torch.cuda.get_device_capability()[0]==10;r['science_started']=True;torch.manual_seed(2141)
  for m in (32,3679,384):
   for name,k,n in FAMS:
    a=torch.randn((m,k),device='cuda',dtype=torch.bfloat16);w=torch.randn((k,n),device='cuda',dtype=torch.bfloat16);ref,bf=tm(lambda:a@w);sa=(448/a.abs().amax().clamp_min(1e-8)).float();sw=(448/w.abs().amax().clamp_min(1e-8)).float();a8=(a*sa).clamp(-448,448).to(torch.float8_e4m3fn);bw=(w*sw).clamp(-448,448).to(torch.float8_e4m3fn).t().contiguous();got,fp=tm(lambda:cutlass_scaled_mm(a8,bw,sa.reciprocal(),sw.reciprocal(),[1,1],output_dtype=torch.bfloat16));e=got.float()-ref.float();r['rows'].append({'m':m,'family':name,'charged':m!=384,'bf16':met(bf,m),'dynamic_e4m3_vllm_cutlass':met(fp,m),'cosine':float(F.cosine_similarity(got.float().flatten(),ref.float().flatten(),0)),'nrmse':float(e.norm()/ref.float().norm().clamp_min(1e-8))});save(r);del a,w,ref,a8,bw,got;torch.cuda.empty_cache()
  r['classification']='interpretable_exact_linear_pair';r['numerical_pass']=all(x['cosine']>=.999 and x['nrmse']<=.03 for x in r['rows'])
 except Exception as e:r.update({'classification':'consumer_runtime_defect' if r['science_started'] else 'pre_science_integration_defect','error':repr(e),'traceback':traceback.format_exc()[-6000:]})
 save(r)
if __name__=='__main__':main()
