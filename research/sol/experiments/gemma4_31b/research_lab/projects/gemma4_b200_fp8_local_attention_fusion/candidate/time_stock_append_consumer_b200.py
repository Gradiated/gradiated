#!/usr/bin/env python3
import argparse, json, os, time
from pathlib import Path
import numpy as np
import torch

BATCH=32; QH=32; KH=16; D=256; PAGE=16; WINDOW=1023; SAMPLES=40; WARMUPS=8; CALLS=17900
def write(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.tmp');t.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n');os.replace(t,p)
def pct(x): return {f'p{q}_ms':float(np.percentile(x,q)) for q in (10,50,90)}
def main():
 a=argparse.ArgumentParser();a.add_argument('--project-root',type=Path,required=True);a.add_argument('--artifact-root',type=Path,required=True);z=a.parse_args(); started=time.time()
 try:
  if not torch.cuda.is_available() or torch.cuda.get_device_properties(0).major!=10: raise RuntimeError('typed_external_blocker: expected SM100')
  from flashinfer.decode import trtllm_batch_decode_with_kv_cache
  import vllm._custom_ops
  g=torch.Generator(device='cuda');g.manual_seed(20260728)
  lens=[4214+round(i*(4571-4214)/31) for i in range(BATCH)]; blocks=[(x+15)//16 for x in lens]; maxb=max(blocks); pages=1+BATCH*65
  table=torch.zeros((BATCH,maxb),dtype=torch.int32); slots=[];n=1
  for i,(l,b) in enumerate(zip(lens,blocks)):
   ps=list(range(n,n+65));n+=65;table[i,b-65:b]=torch.tensor(ps);slots.append(ps[-1]*16+(l-1)%16)
  table=table.to('cuda');raw=torch.randn((pages,2,PAGE,KH,D),dtype=torch.bfloat16,device='cuda',generator=g);initial=raw.permute(0,1,3,2,4);cache=initial.clone()
  q=torch.randn((BATCH,QH,D),dtype=torch.bfloat16,device='cuda',generator=g);k=torch.randn((BATCH,KH,D),dtype=torch.bfloat16,device='cuda',generator=g);v=torch.randn((BATCH,KH,D),dtype=torch.bfloat16,device='cuda',generator=g)
  slots=torch.tensor(slots,dtype=torch.int64,device='cuda');seq=torch.tensor(lens,dtype=torch.int32,device='cuda');workspace=torch.zeros(128*1024*1024,dtype=torch.uint8,device='cuda');scale=torch.ones(1,dtype=torch.float32,device='cuda')
  def reset(): cache.copy_(initial)
  def append(): torch.ops._C_cache_ops.reshape_and_cache_flash(k,v,cache[:,0].transpose(1,2),cache[:,1].transpose(1,2),slots,'auto',scale,scale)
  def consumer(): return trtllm_batch_decode_with_kv_cache(query=q,kv_cache=cache,workspace_buffer=workspace,block_tables=table,seq_lens=seq,max_seq_len=max(lens),bmm1_scale=1.0,bmm2_scale=1.0,window_left=WINDOW,kv_layout='HND',enable_pdl=False,backend='trtllm-gen',q_len_per_req=1)
  def composite(): append();return consumer()
  for fn in (append,consumer,composite):
   for _ in range(WARMUPS): reset(); (append() if fn is consumer else None);fn();torch.cuda.synchronize()
  z.artifact_root.mkdir(parents=True,exist_ok=True);(z.artifact_root/'stock_decomposition_science_started').write_text('true\n')
  values={}; outputs={}; caches={}
  for name,fn,pre in [('append_only',append,False),('consumer_only',consumer,True),('composite',composite,False)]:
   xs=[]
   for _ in range(SAMPLES):
    reset(); pre and append();s,e=torch.cuda.Event(True),torch.cuda.Event(True);s.record();out=fn();e.record();torch.cuda.synchronize();xs.append(float(s.elapsed_time(e)));outputs[name]=out;caches[name]=cache.clone()
   values[name]=xs
  finite=all(o is None or bool(torch.isfinite(o.float()).all()) for o in outputs.values()); cache_equal=bool(torch.equal(caches['consumer_only'],caches['composite']))
  result={'schema_version':1,'terminal':'interpretable','interpretable_result':True,'scientific_sample_consumed':True,'warmups_per_scope':WARMUPS,'samples_per_scope':SAMPLES,'geometry':'B32 HND BF16 H256 GQA2 page16 window1024','timing':{n:{**pct(x),'samples_ms':x,'projected_seconds_per_request':float(np.median(x)*CALLS/1000)} for n,x in values.items()},'correctness':{'finite_output':finite,'cache_bitwise_equal_consumer_vs_composite':cache_equal},'elapsed_seconds':time.time()-started}
  write(z.artifact_root/'STOCK_DECOMPOSITION_TERMINAL.json',result);return 0
 except Exception as e: write(z.artifact_root/'STOCK_DECOMPOSITION_TERMINAL.json',{'schema_version':1,'terminal':'invalid_attempt','interpretable_result':False,'scientific_sample_consumed':False,'error':str(e)});return 1
if __name__=='__main__': raise SystemExit(main())
