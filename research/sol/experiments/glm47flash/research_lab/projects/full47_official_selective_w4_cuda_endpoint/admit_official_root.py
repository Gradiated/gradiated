#!/usr/bin/env python3
"""Emit a source-bound numerical and saturation audit for the combined official root."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path("/root/.cache/glm47flash-awq-full47-official-head-shared-w4-7ab75a5258cc")
SOURCE = Path("/root/.cache/glm47flash-awq-ab31d120")
OUT = HERE / "artifacts" / "official_materialization" / "OFFICIAL_LOCAL_ADMISSION.json"
IMAGE = "glm-vllm:0.15.0-transformers-1618d44"

PROBE = r'''
import json
from pathlib import Path
import torch
from safetensors import safe_open
from compressed_tensors.compressors.quantized_compressors import PackedQuantizationCompressor,unpack_from_int32
from compressed_tensors.quantization import QuantizationArgs
source,root=Path('/source'),Path('/root'); si=json.loads((source/'model.safetensors.index.json').read_text()); di=json.loads((root/'model.safetensors.index.json').read_text())
names=['lm_head.weight','model.layers.1.mlp.shared_experts.gate_proj.weight','model.layers.1.mlp.shared_experts.up_proj.weight','model.layers.1.mlp.shared_experts.down_proj.weight']; args=QuantizationArgs(num_bits=4,type='int',symmetric=True,strategy='group',group_size=32); producer=PackedQuantizationCompressor(); rows=[]
for name in names:
 p=name.removesuffix('.weight'); shard=di['weight_map'][p+'.weight_packed']
 with safe_open(str(source/si['weight_map'][name]),framework='pt',device='cpu') as s, safe_open(str(root/shard),framework='pt',device='cpu') as d:
  weight=s.get_tensor(name); packed=d.get_tensor(p+'.weight_packed'); scale=d.get_tensor(p+'.weight_scale'); shape=d.get_tensor(p+'.weight_shape'); restored=producer.decompress_weight({'weight_packed':packed,'weight_scale':scale,'weight_shape':shape},args); codes=unpack_from_int32(packed,4,tuple(shape.tolist())); err=restored.float()-weight.float()
  rows.append({'name':name,'shape':list(weight.shape),'finite':bool(torch.isfinite(restored).all()),'relative_l2':float(torch.linalg.vector_norm(err)/torch.linalg.vector_norm(weight.float()).clamp_min(1e-30)),'max_abs_error':float(err.abs().max()),'saturation_fraction':float((codes.abs()>=7).float().mean())})
selected=[n for n in si['weight_map'] if n=='lm_head.weight' or ('.mlp.shared_experts.' in n and '.layers.47.' not in n and n.endswith('.weight'))]; derived=[n for n in di['weight_map'] if n.endswith(('.weight_packed','.weight_scale','.weight_shape')) and (n.startswith('lm_head.') or ('.mlp.shared_experts.' in n and '.layers.47.' not in n))]
print(json.dumps({'pass':len(selected)==139 and len(derived)==417 and all(r['finite'] for r in rows),'selected_count':len(selected),'derived_count':len(derived),'observer':'mse','official_dequant_samples':rows},sort_keys=True))
'''

def main() -> None:
    command=["docker","run","--rm","--entrypoint","bash","-v",f"{SOURCE}:/source:ro","-v",f"{ROOT}:/root:ro",IMAGE,"-lc","python3 - <<'PY'\n"+PROBE+"\nPY"]
    run=subprocess.run(command,text=True,capture_output=True,timeout=900)
    payload=json.loads(run.stdout) if run.returncode == 0 else {"pass":False,"stderr_tail":run.stderr[-3000:]}
    payload.update({"schema_version":1,"root":str(ROOT),"root_manifest_sha256":hashlib.sha256((ROOT/'model-files-manifest.json').read_bytes()).hexdigest(),"exit_code":run.returncode})
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
    if not payload['pass']: raise SystemExit('official root admission failed')

if __name__ == '__main__': main()
