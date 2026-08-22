#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,pathlib,re
import torch,triton
from fused_qkv_kv_cache import _qkv_norm_rope_cache_kernel
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def plain(x):
 try:json.dumps(x);return x
 except TypeError:return repr(x)
def main():
 out=pathlib.Path(os.environ['RESOURCE_OUTPUT']);src=pathlib.Path(__file__).with_name('fused_qkv_kv_cache.py');dev=torch.cuda.get_device_properties(0);rows=[]
 if sha(src)!='4b697f3cc125c3b24f4e765be755feffbbc53ed259ada2762637afa1ebf8ef7d':raise RuntimeError('candidate_hash')
 for name,kv,d in [('local',16,256),('global',4,512)]:
  q=torch.empty((1,(32+2*kv)*d),device='cuda',dtype=torch.bfloat16);w=torch.empty((d,),device='cuda',dtype=torch.bfloat16);p=torch.empty(1,device='cuda',dtype=torch.int64);r=torch.empty((2,d),device='cuda',dtype=torch.float32);s=torch.empty(1,device='cuda',dtype=torch.int64);c=torch.empty((2,kv,d),device='cuda',dtype=torch.float8_e5m2)
  k=_qkv_norm_rope_cache_kernel.warmup(q,w,w,p,r,s,c,c,q.stride(0),c.stride(0),c.stride(1),2,NUM_Q_HEADS=32,NUM_KV_HEADS=kv,HEAD_DIM=d,HALF_DIM=d//2,Q_SIZE=32*d,KV_SIZE=kv*d,EPS=1e-6,K_SCALE=1.0,V_SCALE=1.0,WRITE_CACHE=True,BLOCK_HALF=d//2,num_warps=4,grid=(1,32+2*kv))
  m=k.metadata; md={n:plain(getattr(m,n)) for n in dir(m) if not n.startswith('_')}; kd={n:plain(getattr(k,n)) for n in ('name','hash','asm') if hasattr(k,n)};ptx=(getattr(k,'asm',{}) or {}).get('ptx',''); regs=md.get('num_regs',md.get('regs'));stores=md.get('spill_store_bytes',md.get('spill_stores'));loads=md.get('spill_load_bytes',md.get('spill_loads'))
  # ptxas metadata is authoritative; absence of a spill counter is not inferred as zero.
  rows.append({'class':name,'constexprs':{'NUM_Q_HEADS':32,'NUM_KV_HEADS':kv,'HEAD_DIM':d,'HALF_DIM':d//2,'WRITE_CACHE':True,'BLOCK_HALF':d//2,'num_warps':4},'registers_per_thread':regs,'spill_store_bytes':stores,'spill_load_bytes':loads,'metadata':md,'compiled_identity':{'type':type(k).__name__,'attrs':kd,'ptx_sha256':hashlib.sha256(ptx.encode()).hexdigest(),'ptx_maxnreg':re.findall(r'\.maxnreg\s+(\d+)',ptx)}})
 term={'terminal_type':'fixed_floor_crossop_h200_resource_metadata_r2','no_candidate_kernel_launch':True,'no_timing_loop':True,'no_endpoint':True,'candidate_sha256':sha(src),'gpu':{'name':dev.name,'cc':[dev.major,dev.minor]},'triton_version':triton.__version__,'rows':rows};term['passed']=all(isinstance(x['registers_per_thread'],int) and x['registers_per_thread']<=32 and x['spill_store_bytes']==0 and x['spill_load_bytes']==0 for x in rows);out.parent.mkdir(parents=True,exist_ok=True);tmp=out.with_suffix('.part');tmp.write_text(json.dumps(term,indent=2,sort_keys=True)+'\n');os.replace(tmp,out)
if __name__=='__main__':main()
