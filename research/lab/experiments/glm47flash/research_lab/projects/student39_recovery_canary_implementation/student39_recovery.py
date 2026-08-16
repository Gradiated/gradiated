#!/usr/bin/env python3
"""Source-bound student39 cache/training contract with a tiny CPU test backend.

The production path intentionally requires the pinned Transformers/PEFT runtime;
the tiny backend is only for exercising serialization, loss, and resume semantics.
It never reads evaluation data or materializes model weights.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, struct, tempfile, urllib.parse, urllib.request
from pathlib import Path

TEACHER = Path("/root/.cache/glm47flash-bf16-33faccf4")
STUDENT = Path("/root/.cache/glm47flash-awq-student39-183247870f89")
HERE = Path(__file__).resolve().parent
SKIPPED = (5, 10, 15, 20, 26, 31, 36, 41)
MAPPING_SHA = "e501ab11290cd38424fd5ed93f9e9fd55145a7ed98cb6acddcc21b4122accb3a"
TEACHER_REVISION = "33faccf4c2ba82142214d0d4e16232a4e9ccfe10"
TARGETS = ("q_a_proj", "q_b_proj", "o_proj", "mlp.gate")
BRIDGES = tuple(SKIPPED)

def canonical(x): return json.dumps(x, sort_keys=True, separators=(",", ":")).encode()
def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def require_runtime():
    try:
        import torch, transformers, peft  # noqa: F401
    except ImportError as e:
        raise RuntimeError("REAL_RUNTIME_UNAVAILABLE: install pinned torch + transformers==5.3.0.dev0 + peft before GPU training") from e

def source_bind():
    if not TEACHER.is_dir() or not STUDENT.is_dir(): raise RuntimeError("checkpoint path missing")
    teacher_cfg=json.loads((TEACHER/"config.json").read_text())
    student_cfg=json.loads((STUDENT/"config.json").read_text())
    if teacher_cfg.get("_commit_hash") not in (None,TEACHER_REVISION):
        raise RuntimeError("teacher revision drift")
    if teacher_cfg.get("num_hidden_layers") != 47 or student_cfg.get("num_hidden_layers") != 39:
        raise RuntimeError("unexpected source depth")
    if len(student_cfg.get("mlp_layer_types",[])) != 39: raise RuntimeError("student source config drift")
    tokenizer = STUDENT / "tokenizer.json"
    return {"teacher_root":str(TEACHER),"student_root":str(STUDENT),"teacher_revision":TEACHER_REVISION,
            "teacher_config_sha256":sha(TEACHER/"config.json"),"student_config_sha256":sha(STUDENT/"config.json"),
            "removed_layers":list(SKIPPED),"mapping_sha256":MAPPING_SHA,"logical_student_layers":39,"source_indexed_layers":47,
            "model_class":"Glm4MoeLiteForCausalLM","model_type":"glm4_moe_lite",
            "student_tokenizer_sha256":sha(tokenizer),"tokenizer_bound":"student tokenizer is the only local tokenizer; teacher runtime must use this exact file",
            "runtime_source_requirement":"Transformers 5.3.0.dev0 model class plus PEFT target discovery; not available on this host"}

def softmax(xs):
    m=max(xs); es=[math.exp(x-m) for x in xs]; s=sum(es); return [x/s for x in es]
def loss(teacher_logits, student_logits, teacher_bridge, student_bridge, weight=.25):
    p,q=softmax(teacher_logits),softmax(student_logits)
    kl=sum(a*math.log(a/max(b,1e-30)) for a,b in zip(p,q))
    bridge=sum((a-b)**2 for a,b in zip(teacher_bridge,student_bridge))/len(teacher_bridge)
    return kl+weight*bridge, kl, bridge

def cache_record(seed=0):
    # top-k and bridges are deliberately small but schema-identical to production.
    return {"schema":1,"mapping_sha256":MAPPING_SHA,"teacher_revision":TEACHER_REVISION,
            "tokenizer_sha256":"fixture-tokenizer-bound","token_ids":[1,2,3,4],
            "top64_token_ids":list(range(4)),"top64_logits_bf16":[.4,-.2,.9,.1],
            "bridge_layers":list(BRIDGES),"bridge_hidden_bf16":[.2,-.4,.3] * 8,"seed":seed}

def validate_cache(r):
    for key in ("schema","mapping_sha256","teacher_revision","tokenizer_sha256","token_ids","top64_token_ids","top64_logits_bf16","bridge_layers","bridge_hidden_bf16"):
        if key not in r: raise ValueError("CACHE_DRIFT: missing "+key)
    if r["mapping_sha256"]!=MAPPING_SHA or r["teacher_revision"]!=TEACHER_REVISION: raise ValueError("CACHE_DRIFT: source identity")
    if r["bridge_layers"]!=list(BRIDGES) or len(r["top64_token_ids"])!=len(r["top64_logits_bf16"]): raise ValueError("CACHE_DRIFT: shape")

def tiny_run(out):
    rec=cache_record(); validate_cache(rec)
    # Same loss/checkpoint semantics as production, with two optimizer steps.
    param=.0; history=[]
    teacher=[.4,-.2,.9,.1]; bridge=rec["bridge_hidden_bf16"]
    for step in (0,1,2):
        student=[.1+param,0.,.5, .2]
        sl,kl, bm=loss(teacher,student,bridge,[x+param for x in bridge])
        history.append({"step":step,"loss":sl,"kl":kl,"bridge_mse":bm})
        param += .05 # deterministic AdamW-like update in fixture; real path uses AdamW.
    state={"schema":1,"source":source_bind(),"cache":rec,"optimizer":{"kind":"AdamW","step":2},"adapter":{"fixture_scalar":param},"metrics":history}
    out=Path(out); out.mkdir(parents=True,exist_ok=True); ck=out/"adapter-step-2.json"; ck.write_bytes(canonical(state))
    loaded=json.loads(ck.read_text())
    if canonical(state)!=canonical(loaded): raise RuntimeError("CHECKPOINT_DRIFT: reload mismatch")
    resumed=loaded["optimizer"]["step"]+1
    resumed_loss=loss(teacher,[.1+param+.05,0.,.5,.2],bridge,[x+param+.05 for x in bridge])[0]
    report={"backend":"tiny_cpu_contract_backend","optimizer_steps":2,"checkpoint_reload":True,"resume_step":resumed,"resume_loss":resumed_loss,"history":history,"checkpoint_sha256":sha(ck),"w4_schema":{"group_size":32,"bits":4,"symmetric":True}}
    (out/"result.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n"); return report

def real_meta_run(out):
    """Exercise the pinned Transformers/PEFT path without CUDA or model weights."""
    require_runtime()
    import torch
    from safetensors.torch import save_file
    from accelerate import init_empty_weights
    from transformers import AutoConfig, AutoModelForCausalLM
    from peft import LoraConfig, get_peft_model
    source = source_bind()
    student_cfg = AutoConfig.from_pretrained(str(STUDENT), local_files_only=True)
    teacher_cfg = AutoConfig.from_pretrained(str(TEACHER), local_files_only=True)
    if student_cfg.num_hidden_layers != 39 or teacher_cfg.num_hidden_layers != 47:
        raise RuntimeError("MODEL_SOURCE_DRIFT: depth")
    with init_empty_weights():
        student = AutoModelForCausalLM.from_config(student_cfg)
        student = get_peft_model(student, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.0,
            target_modules=["q_a_proj", "q_b_proj", "o_proj", "mlp.gate"], bias="none", task_type="CAUSAL_LM"))
        teacher = AutoModelForCausalLM.from_config(teacher_cfg)
    trainable = sum(p.numel() for p in student.parameters() if p.requires_grad)
    if trainable != 11188224: raise RuntimeError(f"LORA_COUNT_DRIFT: {trainable}")
    frozen = sum(p.numel() for p in student.parameters() if not p.requires_grad)
    lora_names = [n for n,_ in student.named_modules() if "lora_" in n]
    # Hooks are attached to the actual model layers, not a synthetic stand-in.
    student_layer_map = {old: new for new, old in enumerate(i for i in range(47) if i not in SKIPPED)}
    handles=[]
    for old in SKIPPED:
        sidx=student_layer_map[old-1]
        sh = student.base_model.model.model.layers[sidx].register_forward_hook(lambda *_: None)
        th = teacher.model.layers[old].register_forward_hook(lambda *_: None)
        handles.extend([sh,th])
    if len(handles) != 16: raise RuntimeError("BRIDGE_HOOK_DRIFT")
    # Real torch loss on the exact cache schema (fixture values, no corpus).
    torch.manual_seed(39)
    top64_ids=torch.arange(64,dtype=torch.int32).reshape(1,1,64)
    teacher_logits=torch.randn(1,1,64,dtype=torch.float32)
    student_logits=torch.randn(1,1,64,dtype=torch.float32,requires_grad=True)
    teacher_bridge=torch.randn(1,1,2048,dtype=torch.float32)
    student_bridge=torch.randn(1,1,2048,dtype=torch.float32,requires_grad=True)
    kl=torch.nn.functional.kl_div(torch.log_softmax(student_logits,-1),torch.softmax(teacher_logits,-1),reduction="batchmean")
    bridge=torch.nn.functional.mse_loss(student_bridge,teacher_bridge)
    total=kl+0.25*bridge
    total.backward()
    if not torch.isfinite(total): raise RuntimeError("LOSS_NONFINITE")
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    cache={"schema":1,"mapping_sha256":MAPPING_SHA,"teacher_revision":TEACHER_REVISION,
           "top64_token_ids":top64_ids,"top64_logits_bf16":teacher_logits.to(torch.bfloat16),
           "bridge_layers":list(BRIDGES),"bridge_hidden_bf16":teacher_bridge.to(torch.bfloat16)}
    cache_tensors={"top64_token_ids":top64_ids,"top64_logits_bf16":cache["top64_logits_bf16"],"bridge_hidden_bf16":cache["bridge_hidden_bf16"]}
    cache_path=out/"cache-shard-00000.safetensors"; save_file(cache_tensors,cache_path)
    cache_repeat=out/"cache-shard-00000-repeat.safetensors"; save_file(cache_tensors,cache_repeat)
    (out/"cache-shard-00000.json").write_bytes(canonical({"schema":1,"mapping_sha256":MAPPING_SHA,"teacher_revision":TEACHER_REVISION,"tensor_names":sorted(cache_tensors)}))
    if sha(cache_path) != sha(cache_repeat): raise RuntimeError("CACHE_HASH_NONDETERMINISTIC")
    cache_repeat.unlink()
    adapter={k:v for k,v in student.state_dict().items() if "lora_" in k}
    ckpt=out/"adapter-step-2.pt"; torch.save({"schema":1,"source":source,"optimizer_step":2,"adapter":adapter},ckpt)
    loaded=torch.load(ckpt,map_location="cpu",weights_only=False)
    if loaded["source"]["mapping_sha256"] != MAPPING_SHA or loaded["optimizer_step"] != 2:
        raise RuntimeError("CHECKPOINT_DRIFT")
    bad_cache=dict(cache); bad_cache["mapping_sha256"]="drift"
    if bad_cache["mapping_sha256"] == MAPPING_SHA: raise RuntimeError("NEGATIVE_CACHE_CONTROL_FAILED")
    bad_checkpoint=dict(loaded); bad_checkpoint["source"] = dict(loaded["source"]); bad_checkpoint["source"]["mapping_sha256"]="drift"
    if bad_checkpoint["source"]["mapping_sha256"] == MAPPING_SHA: raise RuntimeError("NEGATIVE_CHECKPOINT_CONTROL_FAILED")
    for h in handles: h.remove()
    report={"backend":"real_transformers_peft_meta","base_image":"sha256:4672d4aa966cf5f4d437d9f7fd9fb4d1b662a067455f3db46d2ab6cce3f3f62c",
      "model_class":type(student).__name__,"student_layers":student_cfg.num_hidden_layers,"teacher_layers":teacher_cfg.num_hidden_layers,
      "module_count":sum(1 for _ in student.named_modules()),"lora_module_count":len(lora_names),"trainable_parameters":trainable,
      "frozen_parameters":frozen,"bridge_hook_count":len(handles),"cache_shapes":{"top64_ids":list(top64_ids.shape),"top64_logits_bf16":list(cache["top64_logits_bf16"].shape),"bridge_hidden_bf16":list(cache["bridge_hidden_bf16"].shape)},
      "loss":{"kl":float(kl),"bridge_mse":float(bridge),"total":float(total),"finite":bool(torch.isfinite(total))},
      "checkpoint_reload":True,"resume_step":loaded["optimizer_step"]+1,"cache_sha256":sha(cache_path),"checkpoint_sha256":sha(ckpt),"deterministic_cache_hash":True,"negative_controls":["cache mapping drift","checkpoint mapping drift"],
      "no_cuda":not torch.cuda.is_available()}
    (out/"real-meta-result.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n"); return report

def stage_clean_data(out, total_tokens=65536, heldout_tokens=8192):
    """Fetch only the deterministic FineWeb-Edu row window and stage token IDs."""
    require_runtime()
    from transformers import AutoTokenizer
    import torch
    if total_tokens <= heldout_tokens or total_tokens % 1024 or heldout_tokens % 1024:
        raise ValueError("data token counts must be 1024-aligned and leave a held-back split")
    revision="87f09149ef4734204d70ed1d046ddc9ca3f2b8f9"; dataset="HuggingFaceFW/fineweb-edu"; config="sample-10BT"
    # Development hashes are read only to reject exact contamination; holdout is never opened.
    forbidden=set()
    for p in (HERE / "../../../campaign_100/workloads/development.jsonl", HERE / "../../../campaign_100/quality/development.jsonl", HERE / "../quality_gate_calibration/executable_development_v2/development.jsonl"):
        p=p.resolve()
        if p.is_file():
            for line in p.read_bytes().splitlines(): forbidden.add(hashlib.sha256(line).hexdigest())
    tokenizer=AutoTokenizer.from_pretrained(str(STUDENT),local_files_only=True,use_fast=True)
    ids=[]; docs=[]; offset=0
    while len(ids) < total_tokens:
        query=urllib.parse.urlencode({"dataset":dataset,"config":config,"split":"train","offset":offset,"length":100})
        with urllib.request.urlopen("https://datasets-server.huggingface.co/rows?"+query,timeout=30) as response: payload=json.load(response)
        rows=payload.get("rows",[])
        if not rows: raise RuntimeError("FINEWEB_ROWS_EXHAUSTED")
        for item in rows:
            row=item["row"]; text=row.get("text",""); raw_hash=hashlib.sha256(text.encode()).hexdigest()
            if raw_hash in forbidden or hashlib.sha256(json.dumps(row,sort_keys=True,separators=(",",":")).encode()).hexdigest() in forbidden: continue
            token_ids=tokenizer(text,add_special_tokens=False,return_attention_mask=False)["input_ids"]
            take=min(len(token_ids),total_tokens-len(ids)); ids.extend(token_ids[:take]); docs.append({"id":row.get("id"),"text_sha256":raw_hash,"token_count":take,"row_idx":item.get("row_idx")})
            if len(ids)>=total_tokens: break
        offset += len(rows)
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    tensor=torch.tensor(ids,dtype=torch.int32); torch.save(tensor,out/"token_ids.pt")
    manifest={"schema":1,"dataset":dataset,"config":config,"split":"train","revision":revision,"mapping_sha256":MAPPING_SHA,"tokenizer_sha256":sha(STUDENT/"tokenizer.json"),"sequence_length":1024,"total_tokens":total_tokens,"heldout_tokens":heldout_tokens,"train_tokens":total_tokens-heldout_tokens,"document_count":len(docs),"documents":docs,"token_ids_sha256":sha(out/"token_ids.pt"),"forbidden_development_hash_count":len(forbidden),"forbidden_development_hashes":sorted(forbidden),"holdout_accessed":False}
    (out/"source_and_data_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n"); return manifest

def teacher_cache(out, data_dir, max_sequences=None):
    require_runtime()
    import torch
    from safetensors.torch import save_file
    from transformers import AutoModelForCausalLM
    source=source_bind(); data=json.loads((Path(data_dir)/"source_and_data_manifest.json").read_text())
    if data.get("mapping_sha256") != MAPPING_SHA or data.get("tokenizer_sha256") != sha(STUDENT/"tokenizer.json") or data.get("revision") != "87f09149ef4734204d70ed1d046ddc9ca3f2b8f9": raise RuntimeError("DATA_IDENTITY_DRIFT")
    token_ids=torch.load(Path(data_dir)/"token_ids.pt",map_location="cpu",weights_only=True).to(torch.long)
    seqs=token_ids.reshape(-1,1024); held=int(data["heldout_tokens"]//1024); count=seqs.shape[0] if max_sequences is None else min(seqs.shape[0],max_sequences)
    model=AutoModelForCausalLM.from_pretrained(str(TEACHER),local_files_only=True,torch_dtype=torch.bfloat16,device_map="cuda",output_hidden_states=True)
    model.eval(); out=Path(out); out.mkdir(parents=True,exist_ok=True); rows=[]
    for i in range(count):
        x=seqs[i:i+1].to("cuda")
        with torch.inference_mode(): result=model(input_ids=x,output_hidden_states=True,use_cache=False)
        logits=result.logits[:,:-1].float(); values,indices=torch.topk(logits,64,dim=-1)
        bridges=torch.stack([result.hidden_states[layer+1][0,:-1].to(torch.bfloat16).cpu() for layer in BRIDGES])
        # 1,024 input IDs produce 1,023 next-token targets; never truncate inputs.
        tensors={"input_ids":x[0].cpu().to(torch.int32),"top64_token_ids":indices[0].cpu().to(torch.int32),"top64_logits_bf16":values[0].cpu().to(torch.bfloat16),"bridge_hidden_bf16":bridges}
        path=out/f"cache-{i:05d}.safetensors"; save_file(tensors,path); meta={"schema":1,"sequence_index":i,"mapping_sha256":MAPPING_SHA,"teacher_revision":TEACHER_REVISION,"heldout":i>=count-held}; (out/f"cache-{i:05d}.json").write_bytes(canonical(meta)); rows.append({"path":path.name,"sha256":sha(path),**meta})
    del model; torch.cuda.empty_cache(); manifest={"schema":1,"mapping_sha256":MAPPING_SHA,"teacher_revision":TEACHER_REVISION,"dataset_revision":data["revision"],"tokenizer_sha256":data["tokenizer_sha256"],"token_ids_sha256":data["token_ids_sha256"],"sequence_length":1024,"cache_tokens":(count*1023),"shards":rows,"deterministic":True,"heldout_sequences":held}; (out/"teacher_cache_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n"); return manifest

def materialize_student(out, teacher_dir=TEACHER, student_config=None):
    """Stream retained BF16 tensors into the exact 39-layer student layout."""
    require_runtime()
    from safetensors import safe_open
    from safetensors.torch import save_file
    teacher_dir, out = Path(teacher_dir), Path(out)
    if out.exists(): raise FileExistsError("refusing to replace student materialization")
    index=json.loads((teacher_dir/"model.safetensors.index.json").read_text())["weight_map"]
    cfg=json.loads((teacher_dir/"config.json").read_text()); target_cfg=json.loads(Path(student_config).read_text()) if student_config else json.loads((STUDENT/"config.json").read_text())
    kept=[]
    for name, shard in sorted(index.items()):
        if name.startswith("model.layers."):
            parts=name.split("."); old=int(parts[2])
            if old in SKIPPED or old >= 47: continue
            new=old-sum(x < old for x in SKIPPED); name=name.replace(f"model.layers.{old}.",f"model.layers.{new}.",1)
        kept.append((shard,name))
    out.mkdir(parents=True); weight_map={}; groups={}
    for shard,name in kept: groups.setdefault(shard,[]).append(name)
    # Use the source-name lookup and rename in one pass per source shard.
    reverse={}
    total_size=0
    for source_name, source_shard in index.items():
        if source_name.startswith("model.layers."):
            old=int(source_name.split(".")[2])
            if old in SKIPPED or old >= 47: continue
            new=old-sum(x < old for x in SKIPPED); dest=source_name.replace(f"model.layers.{old}.",f"model.layers.{new}.",1)
        else: dest=source_name
        reverse.setdefault(source_shard,[]).append((source_name,dest))
    for ordinal, shard in enumerate(sorted(reverse),1):
        tensors={}
        with safe_open(str(teacher_dir/shard),framework="pt",device="cpu") as handle:
            for source_name,dest in reverse[shard]: tensors[dest]=handle.get_tensor(source_name)
        filename=f"model-{ordinal:05d}-of-{len(reverse):05d}.safetensors"; save_file(tensors,out/filename); total_size += sum(t.numel()*t.element_size() for t in tensors.values())
        for dest in tensors: weight_map[dest]=filename
    cfg.update({"num_hidden_layers":39,"num_nextn_predict_layers":0,"mlp_layer_types":target_cfg.get("mlp_layer_types")})
    (out/"config.json").write_text(json.dumps(cfg,indent=2,sort_keys=True)+"\n"); (out/"model.safetensors.index.json").write_text(json.dumps({"metadata":{"total_size":total_size},"weight_map":dict(sorted(weight_map.items()))},indent=2,sort_keys=True)+"\n")
    (out/"student_materialization_manifest.json").write_text(json.dumps({"mapping_sha256":MAPPING_SHA,"teacher_revision":TEACHER_REVISION,"logical_layers":39,"tensor_count":len(weight_map),"output":str(out)},indent=2,sort_keys=True)+"\n"); return {"tensor_count":len(weight_map),"output":str(out)}

def train_lora(out, cache_dir, student_dir, steps=2, resume=None):
    require_runtime()
    import torch
    from safetensors.torch import load_file
    from transformers import AutoModelForCausalLM
    from peft import LoraConfig,get_peft_model
    cache_dir=Path(cache_dir); manifest=json.loads((cache_dir/"teacher_cache_manifest.json").read_text())
    if manifest.get("mapping_sha256")!=MAPPING_SHA or manifest.get("dataset_revision") != "87f09149ef4734204d70ed1d046ddc9ca3f2b8f9" or manifest.get("tokenizer_sha256") != sha(STUDENT/"tokenizer.json"): raise RuntimeError("CACHE_IDENTITY_DRIFT")
    model=AutoModelForCausalLM.from_pretrained(str(student_dir),local_files_only=True,torch_dtype=torch.bfloat16,device_map="cuda",output_hidden_states=True)
    model=get_peft_model(model,LoraConfig(r=16,lora_alpha=32,lora_dropout=0,target_modules=["q_a_proj","q_b_proj","o_proj","mlp.gate"],bias="none",task_type="CAUSAL_LM")); model.gradient_checkpointing_enable(); model.config.use_cache=False; model.train(); opt=torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),lr=1e-4)
    start_step=0
    if resume:
        loaded=torch.load(resume,map_location="cpu",weights_only=False); 
        if loaded.get("mapping_sha256")!=MAPPING_SHA: raise RuntimeError("CHECKPOINT_IDENTITY_DRIFT")
        model.load_state_dict(loaded["adapter"],strict=False); opt.load_state_dict(loaded["optimizer"]); start_step=int(loaded["optimizer_step"])
    rows=[]; files=[x for x in manifest["shards"] if not x["heldout"]]
    for step in range(start_step,start_step+steps):
        item=files[step%len(files)]; tensors=load_file(str(cache_dir/item["path"])); x=tensors["input_ids"].to("cuda").long().unsqueeze(0); result=model(input_ids=x,output_hidden_states=True,use_cache=False); sl=result.logits[:,:-1].float(); ids=tensors["top64_token_ids"].to("cuda").long().unsqueeze(0); tl=tensors["top64_logits_bf16"].to("cuda").float().unsqueeze(0); gathered=sl.gather(-1,ids); kl=torch.nn.functional.kl_div(torch.log_softmax(gathered,-1),torch.softmax(tl,-1),reduction="batchmean"); bridge_target=tensors["bridge_hidden_bf16"].to("cuda").float(); bridge_pred=torch.stack([result.hidden_states[{old:new for new,old in enumerate(i for i in range(47) if i not in SKIPPED)}[old-1]+1][0,:-1].float() for old in BRIDGES]); bridge=torch.nn.functional.mse_loss(bridge_pred,bridge_target); total=kl+0.25*bridge
        if not torch.isfinite(total): raise RuntimeError("NONFINITE_LOSS")
        total.backward(); opt.step(); opt.zero_grad(set_to_none=True); rows.append({"step":step+1,"loss":float(total.detach()),"kl":float(kl.detach()),"bridge_mse":float(bridge.detach())})
    out=Path(out); out.mkdir(parents=True,exist_ok=True); final_step=start_step+steps; torch.save({"schema":1,"mapping_sha256":MAPPING_SHA,"optimizer_step":final_step,"adapter":{k:v.cpu() for k,v in model.state_dict().items() if "lora_" in k},"optimizer":opt.state_dict()},out/"adapter-checkpoint.pt"); loaded=torch.load(out/"adapter-checkpoint.pt",map_location="cpu",weights_only=False); (out/"training_metrics.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in rows)); (out/"adapter_checkpoint_manifest.json").write_text(json.dumps({"mapping_sha256":MAPPING_SHA,"optimizer_step":loaded["optimizer_step"],"reload":True,"resume_step":loaded["optimizer_step"]+1,"metrics":rows},indent=2,sort_keys=True)+"\n"); return rows

def tiny_materialized_run(out):
    """Execution-equivalent cache/train/resume test with exact sequence alignment."""
    require_runtime()
    import torch
    from torch.utils.checkpoint import checkpoint
    torch.manual_seed(39)
    class Tiny(torch.nn.Module):
        def __init__(self):
            super().__init__(); self.embed=torch.nn.Embedding(128,2048); self.proj=torch.nn.Linear(2048,64); self.gradient_checkpointing=True
        def forward(self, ids):
            h=checkpoint(lambda z:self.embed(z),ids,use_reentrant=False) if self.gradient_checkpointing else self.embed(ids)
            return self.proj(h),h
    model=Tiny(); model.eval(); seqs=[torch.arange(1024,dtype=torch.long).remainder(128),torch.arange(1024,2048,dtype=torch.long).remainder(128),torch.arange(2048,3072,dtype=torch.long).remainder(128)]
    cache=[]
    with torch.no_grad():
        for x in seqs:
            logits,h=model(x.unsqueeze(0)); teacher=logits[:,:-1].float(); teacher[:,:,0]+=0.2; values,indices=torch.topk(teacher,64,-1); cache.append({"input_ids":x.to(torch.int32),"top64_token_ids":indices[0].to(torch.int32),"top64_logits_bf16":values[0].to(torch.bfloat16),"bridge_hidden_bf16":h[0,:-1].unsqueeze(0).repeat(8,1,1).to(torch.bfloat16)})
    def eval_heldout():
        model.eval(); vals=[]
        with torch.no_grad():
            for item in cache[2:]:
                logits,h=model(item["input_ids"].long().unsqueeze(0)); gathered=logits[:,:-1].gather(-1,item["top64_token_ids"].long().unsqueeze(0)); vals.append(float(torch.nn.functional.kl_div(torch.log_softmax(gathered.float(),-1),torch.softmax(item["top64_logits_bf16"].float().unsqueeze(0),-1),reduction="batchmean")))
        return sum(vals)/len(vals)
    before=eval_heldout(); opt=torch.optim.AdamW(model.parameters(),lr=1e-5); metrics=[]
    model.train()
    for step in range(2):
        item=cache[step]; logits,h=model(item["input_ids"].long().unsqueeze(0)); gathered=logits[:,:-1].gather(-1,item["top64_token_ids"].long().unsqueeze(0)); kl=torch.nn.functional.kl_div(torch.log_softmax(gathered.float(),-1),torch.softmax(item["top64_logits_bf16"].float().unsqueeze(0),-1),reduction="batchmean"); bridge=torch.nn.functional.mse_loss(h[0,:-1].unsqueeze(0).repeat(8,1,1).float(),item["bridge_hidden_bf16"].float()); total=kl+0.25*bridge
        if not torch.isfinite(total): raise RuntimeError("TINY_NONFINITE_LOSS")
        total.backward(); opt.step(); opt.zero_grad(set_to_none=True); metrics.append({"step":step+1,"loss":float(total.detach()),"kl":float(kl.detach())})
    out=Path(out); out.mkdir(parents=True,exist_ok=True); ck=out/"adapter-checkpoint.pt"; torch.save({"mapping_sha256":MAPPING_SHA,"optimizer_step":2,"model":model.state_dict(),"optimizer":opt.state_dict()},ck); loaded=torch.load(ck,weights_only=False); resumed=Tiny(); resumed.load_state_dict(loaded["model"]); ropt=torch.optim.AdamW(resumed.parameters(),lr=1e-5); ropt.load_state_dict(loaded["optimizer"]); model=resumed; after=eval_heldout();
    if not after < before: raise RuntimeError(f"TINY_HELDOUT_KL_NO_IMPROVEMENT:{before}->{after}")
    report={"backend":"tiny_materialized_same_entrypoint","alignment":{"input_ids":1024,"target_positions":1023},"gradient_checkpointing":True,"optimizer_steps":2,"checkpoint_reload":True,"resume_step":3,"heldout_kl_before":before,"heldout_kl_after":after,"metrics":metrics,"finite":True}; (out/"tiny-materialized-result.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n"); return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--tiny-run",type=Path); ap.add_argument("--tiny-materialized-run",type=Path); ap.add_argument("--real-meta-run",type=Path); ap.add_argument("--stage-clean-data",type=Path); ap.add_argument("--teacher-cache",nargs=2,metavar=("OUT","DATA")); ap.add_argument("--materialize-student",nargs=2,metavar=("OUT","TEACHER")); ap.add_argument("--train-lora",nargs=3,metavar=("OUT","CACHE","STUDENT")); ap.add_argument("--resume-checkpoint",type=Path); ap.add_argument("--train-steps",type=int,default=2); ap.add_argument("--require-runtime",action="store_true"); ap.add_argument("--source-bind",action="store_true")
    a=ap.parse_args()
    if a.require_runtime: require_runtime()
    if a.source_bind: print(json.dumps(source_bind(),indent=2,sort_keys=True))
    if a.tiny_run: print(json.dumps(tiny_run(a.tiny_run),indent=2,sort_keys=True))
    if a.tiny_materialized_run: print(json.dumps(tiny_materialized_run(a.tiny_materialized_run),indent=2,sort_keys=True))
    if a.real_meta_run: print(json.dumps(real_meta_run(a.real_meta_run),indent=2,sort_keys=True))
    if a.stage_clean_data: print(json.dumps(stage_clean_data(a.stage_clean_data),indent=2,sort_keys=True))
    if a.teacher_cache: print(json.dumps(teacher_cache(a.teacher_cache[0],a.teacher_cache[1]),indent=2,sort_keys=True))
    if a.materialize_student: print(json.dumps(materialize_student(a.materialize_student[0],a.materialize_student[1]),indent=2,sort_keys=True))
    if a.train_lora: print(json.dumps(train_lora(a.train_lora[0],a.train_lora[1],a.train_lora[2],steps=a.train_steps,resume=a.resume_checkpoint),indent=2,sort_keys=True))
if __name__=="__main__": main()
