#!/usr/bin/env python3
"""Paired FP8 stock/patched exact-shape component measurement."""
from __future__ import annotations
import argparse, hashlib, json, os, statistics
from pathlib import Path

SHAPES = (("sliding_qkv",5376,16384,50),("sliding_o",8192,5376,50),
          ("global_qkv_k_eq_v_materialized",5376,20480,10),("global_o",16384,5376,10),
          ("gate_up",5376,43008,60),("down",21504,5376,60))
M = 32

def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with tmp.open("w") as f:
        json.dump(value, f, indent=2, sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
    tmp.replace(path)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()

def tensor_hash(t) -> str:
    raw = t.detach().contiguous().view(__import__("torch").uint8).cpu().numpy().tobytes()
    return hashlib.sha256(raw).hexdigest()

def metrics(torch, actual, reference):
    a, r = actual.float().flatten(), reference.float().flatten()
    d = a-r; rmse = torch.sqrt(torch.mean(d*d)); rms = torch.sqrt(torch.mean(r*r)).clamp_min(1e-12)
    return {"finite":bool(torch.isfinite(a).all()), "cosine":float(torch.nn.functional.cosine_similarity(a,r,dim=0)), "normalized_rmse":float(rmse/rms), "max_abs":float(d.abs().max())}

def timed(torch, fn, warmup, repeats):
    for _ in range(warmup): fn()
    torch.cuda.synchronize(); values=[]
    for _ in range(repeats):
        start,end=torch.cuda.Event(True),torch.cuda.Event(True); start.record(); fn(); end.record(); end.synchronize(); values.append(float(start.elapsed_time(end)))
    return values

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--output",type=Path,required=True); p.add_argument("--arm",choices=("stock","patched"),required=True); p.add_argument("--oracle",type=Path); p.add_argument("--warmup",type=int,default=5); p.add_argument("--repeats",type=int,default=15); p.add_argument("--seed",type=int,default=20260728)
    a=p.parse_args()
    if a.warmup<2 or a.repeats<5: raise ValueError("warmup>=2 and repeats>=5 required")
    a.output.mkdir(parents=True,exist_ok=False)
    import torch
    from vllm import _custom_ops as ops
    if not torch.cuda.is_available(): raise RuntimeError("cuda_unavailable")
    cap=torch.cuda.get_device_capability()
    if cap!=(10,0): raise RuntimeError(f"sm100_required:{cap}")
    import vllm
    ops_path=Path(ops.__file__).resolve(); exts=sorted(ops_path.parent.glob("_C*.so"))
    if not exts: raise RuntimeError("vllm_custom_extension_missing")
    ext=exts[0]
    state={"schema_version":1,"arm":a.arm,"candidate_science_started":False,"first_shape":None,"vllm_python":str(Path(vllm.__file__).resolve()),"custom_ops_python":str(ops_path),"custom_extension":str(ext),"custom_extension_sha256":sha256(ext),"oracle_mode":"identical_deterministic_fp8_operands"}
    atomic_json(a.output/"INVOCATION_STATE.json",state)
    rows=[]
    for i,(name,k,n,mult) in enumerate(SHAPES):
        torch.manual_seed(a.seed+i); torch.cuda.manual_seed_all(a.seed+i)
        x=torch.randn((M,k),device="cuda",dtype=torch.bfloat16)*0.02; wb=torch.randn((n,k),device="cuda",dtype=torch.bfloat16)*0.02
        w,ws=ops.scaled_fp8_quant(wb); w=w.t(); xq,xs=ops.scaled_fp8_quant(x)
        operands={"x_quantized":tensor_hash(xq),"weight":tensor_hash(w),"x_scale":tensor_hash(xs),"weight_scale":tensor_hash(ws)}
        bf16_ref=x@wb.t()
        def gemm(): return ops.cutlass_scaled_mm(xq,w,xs,ws,out_dtype=torch.bfloat16)
        def quant_gemm():
            q,s=ops.scaled_fp8_quant(x); return ops.cutlass_scaled_mm(q,w,s,ws,out_dtype=torch.bfloat16)
        if not state["candidate_science_started"]:
            state["candidate_science_started"]=True; state["first_shape"]=name; atomic_json(a.output/"INVOCATION_STATE.json",state)
        out=gemm(); torch.cuda.synchronize()
        if not bool(torch.isfinite(out).all()): raise RuntimeError(f"nonfinite_output:{name}")
        bf16=metrics(torch,out,bf16_ref)
        paired=None
        if a.arm=="patched":
            if a.oracle is None: raise RuntimeError("paired_oracle_required")
            stock_path=a.oracle/f"OUTPUT_{name}.pt"
            if not stock_path.exists(): raise RuntimeError(f"stock_output_missing:{name}")
            stock=torch.load(stock_path,map_location="cuda",weights_only=True)
            paired=metrics(torch,out,stock)
            if not paired["finite"]: raise RuntimeError(f"paired_nonfinite:{name}")
        gm=timed(torch,gemm,a.warmup,a.repeats); qm=timed(torch,quant_gemm,a.warmup,a.repeats)
        torch.save(out.detach().cpu(),a.output/f"OUTPUT_{name}.pt")
        row={"name":name,"m":M,"k":k,"n":n,"multiplicity_per_decode_step":mult,"gemm_ms":gm,"quant_and_gemm_ms":qm,"gemm_p50_ms":statistics.median(gm),"quant_and_gemm_p50_ms":statistics.median(qm),"numeric":paired if paired is not None else bf16,"bf16_diagnostic":bf16,"paired_oracle":paired,"operand_hashes":operands,"candidate_symbol":"cutlass_gemm_caller_sm100_fp8<Cutlass3xGemmM16SwapAB>" if a.arm=="patched" else "cutlass_gemm_sm100_fp8_dispatch:stock_runtime_selection"}
        rows.append(row); atomic_json(a.output/f"ROW_{name}.json",row)
        del x,wb,w,ws,xq,xs,bf16_ref,out; torch.cuda.empty_cache()
    terminal={"schema_version":1,"classification":"component_arm_measurement","arm":a.arm,"candidate_science_started":state["candidate_science_started"],"vllm_python":state["vllm_python"],"custom_ops_python":state["custom_ops_python"],"custom_extension":state["custom_extension"],"custom_extension_sha256":state["custom_extension_sha256"],"rows":rows,"weighted_quant_and_gemm_p50_ms":sum(r["multiplicity_per_decode_step"]*r["quant_and_gemm_p50_ms"] for r in rows),"weighted_gemm_p50_ms":sum(r["multiplicity_per_decode_step"]*r["gemm_p50_ms"] for r in rows),"runner_sha256":sha256(Path(__file__).resolve()),"oracle":"paired stock output on identical deterministic FP8 operands; BF16 comparison diagnostic only","measurement":"profiler_off_warm_cuda_events_p50"}
    atomic_json(a.output/"TERMINAL.json",terminal); return 0
if __name__=="__main__": raise SystemExit(main())
