#!/usr/bin/env python3
import argparse, hashlib, json, math, statistics, time
from pathlib import Path

COMMIT='752a3a504485790a2e8491cacbb35c137339ad34'
EXPECTED={
 '/usr/local/lib/python3.12/dist-packages/vllm/v1/attention/backends/mla/triton_mla.py':'647a6d5f4c46f3057fdedce04cc2ee3b15ade713b1d7752df00e347efbd62ef6',
 '/usr/local/lib/python3.12/dist-packages/vllm/v1/attention/ops/triton_reshape_and_cache_flash.py':'5e9aa13eca7ce718ce0648f11454bb0e0e98e9f5da40ee22bd8d0b05f4ba1d03',
}
PAGE=16; HEADS=1; WIDTH=576; VALUE=512; SPLITS=4; FP8_MAX=448.0
def pct(xs,q): return sorted(xs)[max(0,min(len(xs)-1,math.ceil(q*len(xs))-1))]
def timed(torch,fn,warm=20,reps=60):
 for _ in range(warm): fn()
 torch.cuda.synchronize(); vals=[]
 for _ in range(reps):
  a=torch.cuda.Event(enable_timing=True); b=torch.cuda.Event(enable_timing=True); a.record(); fn(); b.record(); torch.cuda.synchronize(); vals.append(a.elapsed_time(b)*1000)
 return {'samples':len(vals),'mean_us':statistics.fmean(vals),'p50_us':pct(vals,.5),'p95_us':pct(vals,.95)}
def run_arm(torch,writer,decode,batch,context,mode,seed):
 torch.manual_seed(seed); blocks=math.ceil(context/PAGE); total=batch*blocks; tokens=batch*context
 key=torch.randn(tokens,1,WIDTH,dtype=torch.bfloat16,device='cuda'); value=key[...,:VALUE]
 q=torch.randn(batch,20,WIDTH,dtype=torch.bfloat16,device='cuda'); gen=torch.Generator(device='cuda'); gen.manual_seed(seed+7)
 table=torch.randperm(total,generator=gen,device='cuda').reshape(batch,blocks).to(torch.int32); slots=(table[:,:,None]*PAGE+torch.arange(PAGE,device='cuda')[None,None,:]).reshape(-1)[:tokens].to(torch.int32)
 dtype='bfloat16' if mode=='bf16' else 'fp8'; cdtype=torch.bfloat16 if mode=='bf16' else torch.float8_e4m3fn
 kc=torch.empty(total,PAGE,1,WIDTH,dtype=cdtype,device='cuda'); vc=kc[...,:VALUE]; one=torch.tensor(1.,dtype=torch.float32,device='cuda')
 scale=torch.tensor(max(1e-6,key.float().abs().max().item()/FP8_MAX),dtype=torch.float32,device='cuda') if mode=='fp8' else one
 def write(): writer(key,value,kc,vc,slots,dtype,scale,scale)
 write(); torch.cuda.synchronize();
 logical_k=kc[table].reshape(batch,context,WIDTH).float()*(scale if mode=='fp8' else 1.)
 logical_v=vc[table].reshape(batch,context,VALUE).float()*(scale if mode=='fp8' else 1.)
 scores=torch.einsum('bhd,btd->bht',q.float(),logical_k)*VALUE**-0.5; ref_o=torch.einsum('bht,btd->bhd',scores.softmax(-1),logical_v); ref_l=torch.logsumexp(scores,dim=-1)
 logits=torch.empty(batch,20,SPLITS,VALUE+1,dtype=torch.float32,device='cuda'); out=torch.zeros(batch,20,VALUE,dtype=torch.bfloat16,device='cuda'); lse=torch.zeros(batch,20,dtype=torch.bfloat16,device='cuda'); lens=torch.full((batch,),context,dtype=torch.int32,device='cuda')
 def stage(): decode(q,kc[...,:],vc,out,lse,table,lens,logits,SPLITS,VALUE**-0.5,PAGE,k_scale=scale,v_scale=scale,is_mla=True)
 # The upstream public call performs writer, stage-1 attention, and split reduction.
 stage(); torch.cuda.synchronize(); err_o=(out.float()-ref_o).abs().max().item(); err_l=(lse.float()-ref_l).abs().max().item()
 wt=timed(torch,write); at=timed(torch,stage)
 return {'mode':mode,'batch':batch,'context':context,'allocated_bytes':kc.numel()*kc.element_size()+4,'cache_bytes':kc.numel()*kc.element_size(),'scale_bytes':4,'scale':scale.item(),'saturation':bool((kc.float().abs()>=FP8_MAX).any().item()) if mode=='fp8' else False,'output_max_abs':err_o,'lse_max_abs':err_l,'numerical_pass':bool(torch.isfinite(out.float()).all().item() and torch.allclose(out.float(),ref_o,atol=.03,rtol=.03) and torch.allclose(lse.float(),ref_l,atol=.10,rtol=.03)),'writer':wt,'attention_full':at}
def main():
 p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); p.add_argument('--seed',type=int,default=1234); a=p.parse_args(); import torch
 if not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
 for path,want in EXPECTED.items():
  got=hashlib.sha256(Path(path).read_bytes()).hexdigest()
  if got!=want: raise RuntimeError(f'upstream source hash mismatch {path}: {got}')
 from vllm.v1.attention.ops.triton_reshape_and_cache_flash import triton_reshape_and_cache_flash as writer
 from vllm.v1.attention.ops.triton_decode_attention import decode_attention_fwd as decode
 rows=[]
 for b in (1,8,32):
  for c in (8193,9215):
   for m in ('bf16','fp8'): rows.append(run_arm(torch,writer,decode,b,c,m,a.seed+b+c))
 by={(r['batch'],r['context'],r['mode']):r for r in rows}; checks=[]
 for c in (8193,9215):
  b=by[(32,c,'bf16')]; f=by[(32,c,'fp8')]; checks.append({'context':c,'bytes_exact':f['allocated_bytes']==math.ceil(c/PAGE)*32*576+4,'numerical_pass':f['numerical_pass'] and not f['saturation'],'writer_improvement':1-f['writer']['p50_us']/b['writer']['p50_us'],'attention_improvement':1-f['attention_full']['p50_us']/b['attention_full']['p50_us'],'p95_no_regression':f['attention_full']['p95_us']<=b['attention_full']['p95_us']})
 gate=all(x['bytes_exact'] and x['numerical_pass'] and x['writer_improvement']>=.10 and x['attention_improvement']>=.10 and x['p95_no_regression'] for x in checks)
 out={'schema_version':1,'upstream_commit':COMMIT,'geometry':{'page_size':PAGE,'kv_heads':1,'cache_width':WIDTH,'value_width':VALUE,'splits':SPLITS},'rows':rows,'checks':checks,'component_gate':gate,'decision':'UPSTREAM_ONEHEAD_FP8_COMPONENT_PASS' if gate else 'UPSTREAM_ONEHEAD_FP8_COMPONENT_CLOSE','device':{'name':torch.cuda.get_device_name(),'capability':torch.cuda.get_device_capability(),'memory':torch.cuda.get_device_properties(0).total_memory}}
 a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); return 0 if gate else 1
 raise SystemExit(main())
