from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import statistics
import time


K, N, GATE_UP = 21504, 5376, 43008


def atomic(path, value):
    part = path.with_suffix(path.suffix + '.part')
    part.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    os.replace(part, path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample(torch, fn):
    for _ in range(2): fn()
    torch.cuda.synchronize(); start=torch.cuda.Event(enable_timing=True); end=torch.cuda.Event(enable_timing=True)
    start.record(); out=fn(); end.record(); end.synchronize()
    return out, start.elapsed_time(end)


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',type=pathlib.Path,required=True); p.add_argument('--checkpoint',type=pathlib.Path,required=True); a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    state=a.output/'INVOCATION_STATE.json'; atomic(state,{'schema_version':2,'compile_started':False,'candidate_cuda_started':False,'candidate_science_started':False,'persisted_producer_rows':[]})
    import torch
    from safetensors import safe_open
    from fused_gelu_quant import fused_gelu_tanh_mul_quant, prepare, invocation_count
    from sglang.srt.layers.activation import GeluAndMul
    from sglang.srt.layers.quantization.fp8_kernel import sglang_per_token_quant_fp8
    from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm
    if not torch.cuda.is_available() or 'H200' not in torch.cuda.get_device_properties(0).name: raise RuntimeError('exact H200 required')
    shard=a.checkpoint/'model-00001-of-00002.safetensors'; key='model.language_model.layers.0.mlp.down_proj.weight'
    with safe_open(str(shard),framework='pt',device='cpu') as f: raw=f.get_tensor(key)
    if tuple(raw.shape)!=(N,K) or raw.dtype!=torch.bfloat16: raise RuntimeError(f'exact_down_weight_mismatch:{raw.dtype}:{tuple(raw.shape)}')
    weight_bf16=raw.cuda().t(); scale=(weight_bf16.float().abs().amax(dim=0)/448).clamp_min(1e-8).float(); weight=(weight_bf16/scale).to(torch.float8_e4m3fn)
    meta={'checkpoint_key':key,'checkpoint_shard':shard.name,'source_dtype':str(raw.dtype),'source_shape':list(raw.shape),'consumer_weight_dtype':str(weight.dtype),'consumer_weight_shape':list(weight.shape),'consumer_weight_stride':list(weight.stride()),'weight_scale_dtype':str(scale.dtype),'weight_scale_shape':list(scale.shape),'weight_scale_stride':list(scale.stride()),'column_major':weight.stride()==(1,K)}
    if not meta['column_major'] or scale.numel()!=N: raise RuntimeError(f'endpoint_cutlass_layout_mismatch:{meta}')
    atomic(a.output/'WEIGHT_METADATA.json',meta)
    s=json.loads(state.read_text()); s['compile_started']=True; atomic(state,s); prepare()
    rows=[]; activation=GeluAndMul(approximate='tanh'); torch.manual_seed(20260722)
    for m in (32,2048):
        gate=torch.empty((m,GATE_UP),device='cuda',dtype=torch.bfloat16).normal_(0,.7)
        def control_q(): return sglang_per_token_quant_fp8(activation(gate))
        s=json.loads(state.read_text()); s['candidate_cuda_started']=True; s['candidate_science_started']=True; atomic(state,s)
        candidate_q,candidate_s=fused_gelu_tanh_mul_quant(gate); torch.cuda.synchronize()
        persisted=a.output/f'PERSISTED_M{m}.pt'; torch.save({'q':candidate_q.cpu(),'scale':candidate_s.cpu(),'shape':list(candidate_q.shape),'strides':list(candidate_q.stride())},persisted)
        producer={'tokens':m,'path':persisted.name,'sha256':digest(persisted),'q_shape':list(candidate_q.shape),'q_stride':list(candidate_q.stride()),'scale_shape':list(candidate_s.shape),'scale_stride':list(candidate_s.stride())}; atomic(a.output/f'PERSISTED_M{m}.json',producer)
        s=json.loads(state.read_text()); s['persisted_producer_rows'].append(producer); atomic(state,s)
        saved=torch.load(persisted,weights_only=True); cq=saved['q'].cuda(); cs=saved['scale'].cuda()
        control_qv,control_s=control_q(); ad=(control_qv.float()*control_s-cq.float()*cs)
        control_out, control_ms=sample(torch,lambda: fp8_scaled_mm(control_qv,weight,control_s,scale,out_dtype=torch.bfloat16,bias=None))
        candidate_out, candidate_ms=sample(torch,lambda: fp8_scaled_mm(cq,weight,cs,scale,out_dtype=torch.bfloat16,bias=None))
        diff=control_out.float()-candidate_out.float(); l2=(torch.linalg.vector_norm(diff)/torch.linalg.vector_norm(control_out.float()).clamp_min(1e-12)).item(); cosine=torch.nn.functional.cosine_similarity(control_out.float().flatten(),candidate_out.float().flatten(),dim=0).item()
        _,cb=sample(torch,control_q); _,fb=sample(torch,lambda:fused_gelu_tanh_mul_quant(gate))
        row={'tokens':m,'control_boundary_ms':cb,'candidate_boundary_ms':fb,'control_component_ms':control_ms,'candidate_component_ms':candidate_ms,'output_relative_l2_error':l2,'output_cosine_similarity':cosine,'numerical_pass':l2<=.01 and cosine>=.9999,'timing_pass':fb<cb and candidate_ms<control_ms,'persisted_producer':producer,'bytes_removed_per_invocation':m*K*6,'launches_removed_per_invocation':1}; rows.append(row); atomic(a.output/f'ROW_M{m}.json',row)
    t={'schema_version':2,'kind':'persisted_real_down_weight_consumer_v2','candidate_symbol':'fused_gelu_tanh_mul_quant_kernel','consumer_symbol':'sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm','weight_metadata':meta,'rows':rows,'candidate_invocations':invocation_count(),'numerical_pass':all(x['numerical_pass'] for x in rows),'timing_pass':all(x['timing_pass'] for x in rows)}; t['pass']=t['numerical_pass'] and t['timing_pass']; t['classification']='component_positive' if t['pass'] else 'component_negative'; atomic(a.output/'TERMINAL.json',t); return 0 if t['pass'] else 20


if __name__=='__main__': raise SystemExit(main())
