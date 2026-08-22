#!/usr/bin/env python3
import json, sys, traceback
from pathlib import Path
import torch
import torch.nn.functional as nnf
import vllm._custom_ops as ops

OUT = Path(sys.argv[sys.argv.index("--output") + 1])
FAMILIES = [("local_qkv",5376,16384),("local_o",8192,5376),("global_qkv",5376,20480),("global_o",16384,5376),("gate_up",5376,43008),("down",21504,5376)]

def persist(value):
    tmp = OUT.with_suffix(".tmp")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(value, sort_keys=True))
    tmp.replace(OUT)

def timed(fn):
    for _ in range(8): fn()
    torch.cuda.synchronize()
    values = []
    for _ in range(40):
        start, end = torch.cuda.Event(True), torch.cuda.Event(True)
        start.record(); result = fn(); end.record(); end.synchronize()
        values.append(start.elapsed_time(end))
    return result, sorted(values)

def quant_a(a):
    scales = (448 / a.abs().reshape(a.shape[0], -1, 128).amax(2).clamp_min(1e-8)).float()
    q = (a.reshape(a.shape[0], -1, 128) * scales.unsqueeze(-1)).clamp(-448,448).to(torch.float8_e4m3fn).reshape_as(a)
    return q, scales

def quant_b(w):
    blocks = w.reshape(w.shape[0] // 128, 128, w.shape[1] // 128, 128).permute(0,2,1,3)
    scales = (448 / blocks.abs().amax((2,3)).clamp_min(1e-8)).float()
    q = (blocks * scales[...,None,None]).clamp(-448,448).to(torch.float8_e4m3fn).permute(0,2,1,3).reshape_as(w)
    return q, scales

def main():
    report = {"classification":"pre_science_integration_defect","science_started":False,"rows":[],"activation_group_shape":[1,128],"weight_group_shape":[128,128],"consumer":"vllm._custom_ops.cutlass_scaled_mm via CutlassFp8BlockScaledMMKernel contract","units":"M32 one B32 invocation divided by 32 requests; M3679 per request; M384 uncharged"}
    try:
        report["science_started"] = True
        for m in (32,3679,384):
            for family,k,n in FAMILIES:
                a = torch.randn(m,k,device="cuda",dtype=torch.bfloat16)
                w = torch.randn(k,n,device="cuda",dtype=torch.bfloat16)
                ref, b = timed(lambda: a @ w)
                aq, asa = quant_a(a); bq, bsa = quant_b(w)
                bcol = bq.t().contiguous().t()
                sbcol = bsa.t().contiguous().t()
                got, c = timed(lambda: ops.cutlass_scaled_mm(a=aq, b=bcol, scale_a=asa.reciprocal(), scale_b=sbcol.reciprocal(), out_dtype=torch.bfloat16, bias=None))
                err = got.float() - ref.float()
                row = {"family":family,"m":m,"k":k,"n":n,"bf16_p50_ms":b[20],"fp8_p50_ms":c[20],"cosine":float(nnf.cosine_similarity(got.float().flatten(),ref.float().flatten(),0)),"nrmse":float(err.norm()/ref.float().norm().clamp_min(1e-8)),"activation_scale_shape":list(asa.shape),"weight_scale_shape":list(bsa.shape),"b_stride":list(bcol.stride()),"scale_b_stride":list(sbcol.stride()),"path":"vllm/CutlassFp8BlockScaledMMKernel->ops.cutlass_scaled_mm"}
                report["rows"].append(row); persist(report)
        report["classification"]="interpretable_block_scaled_linear_pair"
        report["numerical_pass"] = all(r["cosine"] >= .999 and r["nrmse"] <= .03 for r in report["rows"])
    except Exception as exc:
        report.update({"classification":"consumer_runtime_defect","error":repr(exc),"traceback":traceback.format_exc()[-5000:]})
    persist(report)

if __name__ == "__main__": main()
