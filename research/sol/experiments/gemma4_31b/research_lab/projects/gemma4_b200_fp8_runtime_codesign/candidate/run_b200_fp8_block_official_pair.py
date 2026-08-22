#!/usr/bin/env python3
import json,sys,traceback
from pathlib import Path
import torch
import torch.nn.functional as F
import vllm._custom_ops as ops
from vllm.config import VllmConfig, set_current_vllm_config
from vllm.model_executor.layers.quantization.input_quant_fp8 import QuantFP8
from vllm.model_executor.layers.quantization.utils.quant_utils import GroupShape
O=Path(sys.argv[sys.argv.index('--output')+1]); FS=[('local_qkv',5376,16384),('local_o',8192,5376),('global_qkv',5376,20480),('global_o',16384,5376),('gate_up',5376,43008),('down',21504,5376)]
def put(x):
 t=O.with_suffix('.tmp');O.parent.mkdir(parents=True,exist_ok=True);t.write_text(json.dumps(x));t.replace(O)
def run(f):
 for _ in range(8):f()
 torch.cuda.synchronize();z=[]
 for _ in range(40): a,b=torch.cuda.Event(True),torch.cuda.Event(True);a.record();y=f();b.record();b.synchronize();z+=[a.elapsed_time(b)]
 return y,sorted(z)
def wq(w):
 x=w.reshape(w.shape[0]//128,128,w.shape[1]//128,128).permute(0,2,1,3);s=(448/x.abs().amax((2,3)).clamp_min(1e-8)).float();q=(x*s[...,None,None]).clamp(-448,448).to(torch.float8_e4m3fn).permute(0,2,1,3).reshape_as(w);return q,s.t().contiguous().t()
def main():
 r={'classification':'pre_science_integration_defect','science_started':False,'rows':[],'producer':'QuantFP8(static=False,group_shape=GroupShape(1,128),use_ue8m0=False,column_major_scales=True)'}
 try:
  with set_current_vllm_config(VllmConfig()): q=QuantFP8(static=False,group_shape=GroupShape(1,128),use_ue8m0=False,column_major_scales=True)
  r['science_started']=True
  for m in (32,3679,384):
   for name,k,n in FS:
    a=torch.randn(m,k,device='cuda',dtype=torch.bfloat16);w=torch.randn(k,n,device='cuda',dtype=torch.bfloat16);ref,b=run(lambda:a@w); aq,sa=q(a); bq,sb=wq(w);bc=bq.t().contiguous().t();got,c=run(lambda:ops.cutlass_scaled_mm(a=aq,b=bc,scale_a=sa,scale_b=sb.reciprocal(),out_dtype=torch.bfloat16,bias=None));e=got.float()-ref.float();r['rows'].append({'family':name,'m':m,'bf16_p50_ms':b[20],'fp8_p50_ms':c[20],'cosine':float(F.cosine_similarity(got.float().flatten(),ref.float().flatten(),0)),'nrmse':float(e.norm()/ref.float().norm().clamp_min(1e-8)),'a_scale_shape':list(sa.shape),'a_scale_stride':list(sa.stride()),'b_stride':list(bc.stride()),'path':'QuantFP8->vllm._custom_ops.cutlass_scaled_mm'});put(r)
  r['classification']='interpretable_official_block_linear_pair';r['numerical_pass']=all(x['cosine']>=.999 and x['nrmse']<=.03 for x in r['rows'])
 except Exception as e:r.update({'classification':'consumer_runtime_defect','error':repr(e),'traceback':traceback.format_exc()[-4000:]})
 put(r)
main()
