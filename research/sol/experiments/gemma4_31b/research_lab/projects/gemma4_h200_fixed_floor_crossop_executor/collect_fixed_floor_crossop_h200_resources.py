#!/usr/bin/env python3
"""Compile-only resource recovery for the two accepted WRITE_CACHE specializations."""
from __future__ import annotations
import hashlib, json, os, pathlib, re
import torch, triton
from fused_qkv_kv_cache import _qkv_norm_rope_cache_kernel

SOURCE_HASH='4b697f3cc125c3b24f4e765be755feffbbc53ed259ada2762637afa1ebf8ef7d'
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
 out=pathlib.Path(os.environ['RESOURCE_OUTPUT']); out.parent.mkdir(parents=True,exist_ok=True)
 source=pathlib.Path(__file__).with_name('fused_qkv_kv_cache.py')
 if sha(source)!=SOURCE_HASH: raise RuntimeError('candidate_hash')
 device=torch.cuda.get_device_properties(0)
 if device.major!=9 or 'H200' not in device.name: raise RuntimeError('exact_h200_required')
 rows=[]
 for name,kv,dim in [('local',16,256),('global',4,512)]:
  width=(32+2*kv)*dim; token=1
  qkv=torch.empty((token,width),device='cuda',dtype=torch.bfloat16); w=torch.empty((dim,),device='cuda',dtype=torch.bfloat16); pos=torch.empty((token,),device='cuda',dtype=torch.int64); rope=torch.empty((2,dim),device='cuda',dtype=torch.float32); slots=torch.empty((token,),device='cuda',dtype=torch.int64); cache=torch.empty((2,kv,dim),device='cuda',dtype=torch.float8_e5m2)
  compiled=_qkv_norm_rope_cache_kernel.warmup(qkv,w,w,pos,rope,slots,cache,cache,qkv.stride(0),cache.stride(0),cache.stride(1),cache.shape[0],NUM_Q_HEADS=32,NUM_KV_HEADS=kv,HEAD_DIM=dim,HALF_DIM=dim//2,Q_SIZE=32*dim,KV_SIZE=kv*dim,EPS=1e-6,K_SCALE=1.0,V_SCALE=1.0,WRITE_CACHE=True,BLOCK_HALF=dim//2,num_warps=4,grid=(1,32+2*kv))
  meta=compiled.metadata; asm=getattr(compiled,'asm',{}); ptx=asm.get('ptx','') if isinstance(asm,dict) else ''
  # ptxas emits local-memory traffic only when spills exist; retain raw resource identities.
  nsp=int(getattr(compiled,'n_spills',0)); regs=int(compiled.n_regs)
  rows.append({'class':name,'constexprs':{'NUM_Q_HEADS':32,'NUM_KV_HEADS':kv,'HEAD_DIM':dim,'HALF_DIM':dim//2,'WRITE_CACHE':True,'BLOCK_HALF':dim//2,'num_warps':4},'registers_per_thread':regs,'spill_stores_bytes':0 if nsp==0 else None,'spill_loads_bytes':0 if nsp==0 else None,'n_spills':nsp,'metadata':{'name':getattr(meta,'name',None),'shared':getattr(meta,'shared',None),'cluster_dims':getattr(meta,'cluster_dims',None)},'ptx_sha256':hashlib.sha256(ptx.encode()).hexdigest(),'ptx_maxnreg':re.findall(r'\.maxnreg\s+(\d+)',ptx),'compiled_object_type':type(compiled).__name__})
 terminal={'terminal_type':'fixed_floor_crossop_h200_resource_recovery','no_candidate_kernel_launch':True,'no_timing_loop':True,'no_endpoint':True,'candidate_sha256':sha(source),'gpu':{'name':device.name,'cc':[device.major,device.minor]},'triton_version':triton.__version__,'rows':rows}
 terminal['passed']=all(r['registers_per_thread']<=32 and r['spill_stores_bytes']==0 and r['spill_loads_bytes']==0 for r in rows)
 t=out.with_suffix('.part');t.write_text(json.dumps(terminal,indent=2,sort_keys=True)+'\n');os.replace(t,out)
if __name__=='__main__':main()
