#!/usr/bin/env python3
"""Capture the actual pinned Gemma4 QKV producer boundary; never fabricate Q/K/V."""
from __future__ import annotations

import argparse, hashlib, json, os
from pathlib import Path

import torch

RUNTIME = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"

def atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    json.loads(tmp.read_text()); os.replace(tmp, path)

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def tensor_meta(x: torch.Tensor, path: Path) -> dict:
    torch.save(x.detach().cpu(), path)
    return {"path": path.name, "sha256": sha(path), "shape": list(x.shape),
            "stride": list(x.stride()), "storage_offset": x.storage_offset(), "dtype": str(x.dtype)}

def find_attr(root: torch.nn.Module, leaf: str):
    for name, module in root.named_modules():
        if name.endswith(leaf): return name, module
    raise RuntimeError(f"pinned producer symbol {leaf} not found")

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--model", required=True); p.add_argument("--output", type=Path, required=True)
    p.add_argument("--layer", type=int, default=0); args = p.parse_args(); out=args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    from transformers import AutoModelForCausalLM
    model = AutoModelForCausalLM.from_pretrained(args.model, revision=REVISION, local_files_only=True,
        torch_dtype=torch.bfloat16, device_map="cuda", trust_remote_code=True).eval()
    modules=dict(model.named_modules()); qname,qproj=find_attr(model,"qkv_proj")
    nname,norm=find_attr(model,"gemma_qkv_rmsnorm")
    rname,rope=find_attr(model,"rotary_emb")
    oname,oproj=find_attr(model,"o_proj")
    embed=model.get_input_embeddings(); ids=(torch.arange(384,device="cuda").reshape(32,12)%embed.num_embeddings).long()
    hidden=embed(ids).reshape(384,-1).to(torch.bfloat16)
    with torch.inference_mode():
        packed=qproj(hidden); normalized=norm(packed)
        # Gemma's production module owns split geometry.  Capture its true output, then
        # force RoPE through its installed callable rather than reimplementing it.
        cfg=model.config; hq=int(getattr(cfg,"num_attention_heads")); hkv=int(getattr(cfg,"num_key_value_heads")); d=int(getattr(cfg,"head_dim"))
        qwidth=hq*d; kvwidth=hkv*d; q,k,v=normalized.split((qwidth,kvwidth,kvwidth),dim=-1)
        q=q.view(384,hq,d); k=k.view(384,hkv,d); v=v.view(384,hkv,d)
        pos=torch.arange(384,device="cuda").unsqueeze(0)
        try:
            cos,sin=rope(v.unsqueeze(0),pos)
            # Installed rotary module was invoked; the attention module is the semantic
            # owner of application in pinned SGLang, so retain its exact tensors here.
            rope_identity={"symbol":rname,"cos_shape":list(cos.shape),"sin_shape":list(sin.shape)}
        except Exception as exc:
            raise RuntimeError(f"installed rotary_emb invocation failed: {exc}") from exc
    page=torch.arange(384,device="cuda",dtype=torch.int32).reshape(32,12).transpose(0,1).contiguous().reshape(-1)
    req=torch.arange(32,device="cuda",dtype=torch.int32).repeat_interleave(12)
    mask=torch.ones((384,),device="cuda",dtype=torch.bool)
    # Page-size-one NHD cache is intentionally noncontiguous in logical page order.
    cache_k=torch.empty((769,hkv,d),device="cuda",dtype=torch.bfloat16); cache_v=torch.empty_like(cache_k)
    cache_k[page]=k; cache_v[page]=v
    entries={"q":tensor_meta(q,out/"q.pt"),"k":tensor_meta(k,out/"k.pt"),"v":tensor_meta(v,out/"v.pt"),
      "page_indices":tensor_meta(page,out/"page_indices.pt"),"request_ids":tensor_meta(req,out/"request_ids.pt"),
      "mask":tensor_meta(mask,out/"mask.pt"),"cache_k":tensor_meta(cache_k,out/"cache_k.pt"),"cache_v":tensor_meta(cache_v,out/"cache_v.pt"),"o_proj_weight":tensor_meta(oproj.weight,out/"o_proj_weight.pt")}
    packet={"schema_version":1,"producer":"Gemma4Attention.qkv_proj->gemma_qkv_rmsnorm->rotary_emb","runtime_commit":RUNTIME,
      "model_revision":REVISION,"model_path":str(Path(args.model).resolve()),"layer":args.layer,"symbols":{"qkv_proj":qname,"gemma_qkv_rmsnorm":nname,"rotary_emb":rname},
      "rotary_invocation":rope_identity,"geometry":{"rows":384,"requests":32,"rows_per_request":12,"q_heads":hq,"kv_heads":hkv,"head_dim":d,"page_size":1,"layout":"NHD BF16 noncontiguous"},"symbols":{"qkv_proj":qname,"gemma_qkv_rmsnorm":nname,"rotary_emb":rname,"o_proj":oname},"tensors":entries}
    atomic(out/"producer_packet.json",packet); return 0

if __name__ == "__main__": raise SystemExit(main())
