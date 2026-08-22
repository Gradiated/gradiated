#!/usr/bin/env python3
import json,sys,traceback
from pathlib import Path
import torch
import torch.nn.functional as F
from vllm.model_executor.layers.quantization.utils.fp8_utils import cutlass_scaled_mm
O=Path(sys.argv[sys.argv.index('--output')+1]);FAMS=[('local_qkv',5376,16384),('local_o',8192,5376),('global_qkv',5376,20480),('global_o',16384,5376),('gate_up',5376,43008),('down',21504,5376)]
def save(x):
 t=O.with_suffix('.tmp');O.parent.mkdir(parents=True,exist_ok=True);t.write_text(json.dumps(x));t.replace(O)
def run(f):
 for _ in range(8):f()
 torch.cuda.synchronize();z=[]
 for _ in range(40):a,b=torch.cuda.Event(True),torch.cuda.Event(True);a.record();y=f();b.record();b.synchronize();z.append(a.elapsed_time(b))
 return y,sorted(z)
def main():
 r={'classification':'pre_science_integration_defect','science_started':False,'rows':[],'activation_scale_granularity':'one_fp32_scale_per_token','weight_scale_granularity':'static_tensor'}
 try:
  r['science_started']=True
  for m in (32,3679,384):
   for name,k,n in FAMS:
    a=torch.randn(m,k,device='cuda',dtype=torch.bfloat16);w=torch.randn(k,n,device='cuda',dtype=torch.bfloat16);ref,b=run(lambda:a@w);sa=(448/a.abs().amax(1,keepdim=True).clamp_min(1e-8)).float();sw=(448/w.abs().amax().clamp_min(1e-8)).float();a8=(a*sa).clamp(-448,448).to(torch.float8_e4m3fn);bw=(w*sw).clamp(-448,448).to(torch.float8_e4m3fn).t().contiguous();got,c=run(lambda:cutlass_scaled_mm(a8,bw,sa.reciprocal(),sw.reciprocal(),[1,1],output_dtype=torch.bfloat16));e=got.float()-ref.float();r['rows'].append({'m':m,'family':name,'bf16_p50_ms':b[20],'fp8_p50_ms':c[20],'cosine':float(F.cosine_similarity(got.float().flatten(),ref.float().flatten(),0)),'nrmse':float(e.norm()/ref.float().norm().clamp_min(1e-8))});save(r)
  r['classification']='interpretable_dynamic_token_linear_pair';r['numerical_pass']=all(x['cosine']>=.999 and x['nrmse']<=.03 for x in r['rows'])
 except Exception as e:r.update({'classification':'consumer_runtime_defect','error':repr(e),'traceback':traceback.format_exc()[-4000:]})
 save(r)
main()
