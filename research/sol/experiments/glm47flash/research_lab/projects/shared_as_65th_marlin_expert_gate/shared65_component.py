#!/usr/bin/env python3
"""One-layer L40S A0/A1/B WNA16 component experiment."""
from __future__ import annotations
import argparse, hashlib, inspect, json, math, statistics
from pathlib import Path
import torch
import torch.nn.functional as F

PAYLOAD=Path('/input/payload.safetensors')
BF16=Path('/input')
HIDDEN=2048; WIDTH=1536; E=65; ROUTED=64; M=32; REPS=40; WARM=12

def pct(xs, q): return sorted(xs)[max(0,min(len(xs)-1,math.ceil(q*len(xs))-1))]
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def load_weights():
    from safetensors.torch import load_file
    from vllm import _custom_ops as ops
    from vllm.model_executor.layers.quantization.utils.marlin_utils import marlin_moe_permute_scales
    x=load_file(str(PAYLOAD),device='cuda')
    gidx=torch.empty((E,0),dtype=torch.int32,device='cuda')
    w13=ops.gptq_marlin_moe_repack(x['w13_packed'],gidx,256*8,3072,4,is_a_8bit=False)
    w2=ops.gptq_marlin_moe_repack(x['w2_packed'],gidx,192*8,2048,4,is_a_8bit=False)
    s13=marlin_moe_permute_scales(x['w13_scale'],size_k=3072,size_n=3072,group_size=32,is_a_8bit=False)
    s2=marlin_moe_permute_scales(x['w2_scale'],size_k=1536,size_n=2048,group_size=32,is_a_8bit=False)
    return w13,w2,s13,s2

def bf16_shared(x):
    gate=torch.from_file(str(BF16/'shared_bf16_gate_proj.bin'),dtype=torch.bfloat16,size=1536*2048).reshape(1536,2048).cuda()
    up=torch.from_file(str(BF16/'shared_bf16_up_proj.bin'),dtype=torch.bfloat16,size=1536*2048).reshape(1536,2048).cuda()
    down=torch.from_file(str(BF16/'shared_bf16_down_proj.bin'),dtype=torch.bfloat16,size=2048*1536).reshape(2048,1536).cuda()
    return F.linear(F.silu(F.linear(x,gate)*F.linear(x,up)),down)

def make_routes(kind):
    if kind=='balanced': ids=torch.arange(M*4,device='cuda',dtype=torch.int64).reshape(M,4).remainder(64)
    else: ids=torch.tensor([[0,1,2,3]]*(M//2)+[[60,61,62,63]]*(M-M//2),device='cuda',dtype=torch.int64)
    g=torch.Generator(device='cuda'); g.manual_seed(9091 if kind=='balanced' else 9092)
    raw=torch.rand((M,4),generator=g,device='cuda',dtype=torch.float32)+0.05
    norm=raw/raw.sum(dim=1,keepdim=True)
    return ids,norm

def wna16(w13,w2,s13,s2,x,weights,ids):
    from vllm.model_executor.layers.fused_moe.fused_marlin_moe import fused_marlin_moe
    from vllm.scalar_type import scalar_types
    return fused_marlin_moe(x,w13,w2,None,None,s13,s2,weights,ids,quant_type_id=scalar_types.uint4b8.id,global_num_experts=E,activation='silu',is_k_full=True)

def run_case(w13,w2,s13,s2,kind,seed):
    ids,norm=make_routes(kind); g=torch.Generator(device='cuda'); g.manual_seed(seed)
    x=torch.randn((M,HIDDEN),generator=g,device='cuda',dtype=torch.bfloat16)
    routed=norm*1.8
    ids65=torch.cat((ids,torch.full((M,1),64,device='cuda',dtype=torch.int64)),1)
    weights65=torch.cat((routed,torch.ones((M,1),device='cuda')),1)
    shared_ids=torch.full((M,1),64,device='cuda',dtype=torch.int64); shared_w=torch.ones((M,1),device='cuda',dtype=torch.float32)
    shared_stream=torch.cuda.Stream(); join=torch.cuda.Event()
    def a0():
        routed_out=[None]
        routed_out[0]=wna16(w13[:64],w2[:64],s13[:64],s2[:64],x,routed,ids)
        with torch.cuda.stream(shared_stream): shared_out=bf16_shared(x); join.record(shared_stream)
        torch.cuda.current_stream().wait_event(join)
        return routed_out[0]+shared_out
    def a1():
        routed_out=wna16(w13[:64],w2[:64],s13[:64],s2[:64],x,routed,ids)
        with torch.cuda.stream(shared_stream): shared_out=wna16(w13,w2,s13,s2,x,shared_w,shared_ids)
        join.record(shared_stream); torch.cuda.current_stream().wait_event(join)
        return routed_out+shared_out
    def b(): return wna16(w13,w2,s13,s2,x,weights65,ids65)
    # Warm and measure complete operations including stream join/final add.
    for fn in (a0,a1,b):
        for _ in range(WARM): fn()
        torch.cuda.synchronize()
    timings={}; outputs={}
    for name,fn in (('A0',a0),('A1',a1),('B',b)):
        vals=[]; last=None
        for _ in range(REPS):
            start=torch.cuda.Event(enable_timing=True); end=torch.cuda.Event(enable_timing=True); start.record(); last=fn(); end.record(); torch.cuda.synchronize(); vals.append(start.elapsed_time(end)*1000)
        timings[name]={'samples':len(vals),'p50_us':pct(vals,.5),'p95_us':pct(vals,.95),'mean_us':statistics.fmean(vals),'values_us':vals}; outputs[name]=last
    e1=(outputs['A1']-outputs['B']).float(); e0=(outputs['A1']-outputs['A0']).float()
    return {'timings':timings,'errors':{'A1_vs_B_max_abs':float(e1.abs().max()),'A1_vs_B_rel_l2':float(torch.linalg.vector_norm(e1)/torch.linalg.vector_norm(outputs['A1'].float()).clamp_min(1e-12)),'A1_vs_A0_max_abs':float(e0.abs().max()),'A1_vs_A0_rel_l2':float(torch.linalg.vector_norm(e0)/torch.linalg.vector_norm(outputs['A0'].float()).clamp_min(1e-12))},'route_ids':ids.cpu().tolist(),'route_weights':norm.cpu().tolist()}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,required=True); ap.add_argument('--seed',type=int,required=True); a=ap.parse_args()
    result={'sweep_pass':True,'component_pass':False,'decision':'TYPED_COMPONENT_CLOSE','experiment':'shared65_one_layer_a0_a1_b','geometry':{'M':M,'hidden':HIDDEN,'width':WIDTH,'routed_experts':64,'fused_experts':65,'routed_top_k':4,'fused_top_k':5,'routed_scaling_factor':1.8,'norm_topk_prob':True,'block_size_m':8,'shared_padding_c32':0},'payload':{'path':str(PAYLOAD),'sha256':digest(PAYLOAD),'manifest':json.loads((PAYLOAD.parent/'manifest.json').read_text()),'shared_bf16_hashes':{p:digest(BF16/f'shared_bf16_{p}.bin') for p in ('gate_proj','up_proj','down_proj')}}}
    try:
        if not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
        import vllm.model_executor.layers.fused_moe.fused_marlin_moe as fm
        result['runtime']={'gpu':torch.cuda.get_device_name(),'capability':list(torch.cuda.get_device_capability()),'vllm':__import__('vllm').__version__,'fused_marlin_source':inspect.getsourcefile(fm),'fused_marlin_source_sha256':digest(inspect.getsourcefile(fm))}
        w13,w2,s13,s2=load_weights(); result['runtime'].update({'w13_shape':list(w13.shape),'w2_shape':list(w2.shape),'s13_shape':list(s13.shape),'s2_shape':list(s2.shape),'kernel':'vllm.model_executor.layers.fused_moe.fused_marlin_moe.fused_marlin_moe -> ops.moe_wna16_marlin_gemm'})
        result['cases']={k:run_case(w13,w2,s13,s2,k,a.seed+i) for i,k in enumerate(('balanced','skew'))}
        gate=True
        for row in result['cases'].values():
            t=row['timings']; gate &= t['A0']['p50_us']/t['B']['p50_us']>=1.63 and t['B']['p95_us']<=t['A0']['p95_us'] and row['errors']['A1_vs_B_max_abs']<=0.05 and row['errors']['A1_vs_B_rel_l2']<=0.01
        result['component_pass']=bool(gate); result['decision']='SHARED65_COMPONENT_PASS' if gate else 'RUNTIME_COMPONENT_CLOSE'
    except Exception as e:
        result['error']={'type':type(e).__name__,'message':str(e)}; result['decision']='RUNTIME_COMPONENT_CLOSE'
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); print(json.dumps(result,indent=2,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
