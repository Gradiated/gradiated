#!/usr/bin/env python3
"""Target-GPU exact-shape BF16 versus explicit Marlin W4 output-head timing."""

import argparse
import hashlib
import json
import math
import statistics
import time
from pathlib import Path


K, N, GROUP = 2048, 154880, 32
THRESHOLD = 3.4076163734378415


def percentile(values, fraction):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * fraction) - 1)]


def timed(torch, fn, warmups=16, repetitions=60):
    for _ in range(warmups): fn()
    torch.cuda.synchronize()
    starts = [torch.cuda.Event(enable_timing=True) for _ in range(repetitions)]
    ends = [torch.cuda.Event(enable_timing=True) for _ in range(repetitions)]
    for start, end in zip(starts, ends):
        start.record(); fn(); end.record()
    torch.cuda.synchronize()
    values = [start.elapsed_time(end) * 1000 for start, end in zip(starts, ends)]
    return {'samples': len(values), 'mean_us': statistics.fmean(values), 'p50_us': percentile(values, .5), 'p95_us': percentile(values, .95), 'min_us': min(values), 'max_us': max(values)}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seed', type=int, default=1234); args = parser.parse_args()
    import torch
    from vllm import _custom_ops as ops
    from vllm.model_executor.layers.quantization.utils.marlin_utils import apply_gptq_marlin_linear, marlin_make_empty_g_idx, marlin_make_workspace_new, marlin_permute_scales
    from vllm.scalar_type import scalar_types
    if not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
    torch.manual_seed(args.seed)
    qpacked = torch.load('/input/lm_head_qweight.pt', map_location='cuda', weights_only=True)
    scales = torch.load('/input/lm_head_scales.pt', map_location='cuda', weights_only=True)
    if tuple(qpacked.shape) != (K // 8, N) or tuple(scales.shape) != (K // GROUP, N): raise RuntimeError('unexpected staged head shape')
    empty = torch.empty(0, dtype=torch.int, device='cuda')
    marlin_weight = ops.gptq_marlin_repack(qpacked.contiguous(), empty, K, N, 4)
    marlin_scales = marlin_permute_scales(scales.contiguous(), K, N, GROUP)
    workspace = marlin_make_workspace_new(torch.device('cuda'))
    gidx = marlin_make_empty_g_idx(torch.device('cuda'))
    unpacked = torch.empty((K, N), dtype=torch.int8, device='cuda')
    for bit in range(8): unpacked[bit::8] = ((qpacked >> (4 * bit)) & 15).to(torch.int8)
    bf16_weight = ((unpacked.float() - 8) * scales.repeat_interleave(GROUP, dim=0).float()).to(torch.bfloat16)
    del unpacked
    rows=[]
    for m in (1, 8, 16):
        x=torch.randn((m,K), device='cuda', dtype=torch.bfloat16)
        def bf16(): return x @ bf16_weight
        def w4(): return apply_gptq_marlin_linear(x, marlin_weight, marlin_scales, gidx, gidx, empty, workspace, scalar_types.uint4b8, N, K, True)
        reference=bf16(); candidate=w4(); torch.cuda.synchronize()
        error=(candidate.float()-reference.float()).abs()
        bf16_t=timed(torch,bf16); w4_t=timed(torch,w4)
        rows.append({'m':m,'bf16_timing':bf16_t,'marlin_w4_timing':w4_t,'speedup_p50':bf16_t['p50_us']/w4_t['p50_us'],'speedup_p95':bf16_t['p95_us']/w4_t['p95_us'],'output_max_abs_error':float(error.max()),'output_relative_l2':float(error.square().sum().sqrt()/reference.float().square().sum().sqrt()),'finite':bool(torch.isfinite(candidate).all())})
    device=torch.cuda.get_device_properties(0)
    m16=next(row for row in rows if row['m']==16)
    torch.cuda.synchronize(); peak=torch.cuda.max_memory_allocated()
    result={'schema_version':1,'seed':args.seed,'shape':{'activation':[None,K],'weight':[K,N],'group_size':GROUP},'device':{'name':device.name,'capability':list(torch.cuda.get_device_capability()),'sm_count':device.multi_processor_count,'total_memory_bytes':device.total_memory},'payload_sha256':{'qweight':hashlib.sha256(Path('/input/lm_head_qweight.pt').read_bytes()).hexdigest(),'scales':hashlib.sha256(Path('/input/lm_head_scales.pt').read_bytes()).hexdigest()},'rows':rows,'peak_vram_bytes':peak,'m16_threshold':THRESHOLD,'m16_pass':m16['finite'] and m16['output_relative_l2'] < .02 and m16['speedup_p50'] >= THRESHOLD,'sweep_pass':all(row['finite'] and row['output_relative_l2'] < .02 for row in rows),'decision':'PROMOTE_RUNTIME_INTEGRATION' if m16['speedup_p50'] >= THRESHOLD else 'CLOSE_W4_HEAD_LINEAGE'}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')


if __name__ == '__main__': main()
