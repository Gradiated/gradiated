#!/usr/bin/env python3
"""Content-address official uint4b8 selective-W4 full47 checkpoints."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = Path("/root/.cache/glm47flash-awq-ab31d120")
IMAGE = "glm-vllm:0.15.0-transformers-1618d44"
OUT = HERE / "artifacts" / "official_materialization"
SCOPE_TOOL_DIR = HERE.parents[2] / "campaign_100" / "nebius"

sys.path.insert(0, str(SCOPE_TOOL_DIR))
from selective_w4_scope import (  # noqa: E402
    VALID_SCOPES,
    expected_weight_count,
    is_selective_candidate,
    selected_weight,
)

PRODUCER = r'''
import hashlib, json, os, sys
from pathlib import Path
import torch
from safetensors import safe_open
from safetensors.torch import save_file
from compressed_tensors.compressors.quantized_compressors import PackedQuantizationCompressor
from compressed_tensors.quantization import QuantizationArgs
sys.path.insert(0, '/scope')
from selective_w4_scope import apply_scope_to_config, expected_weight_count, is_selective_candidate, selected_weight, validate_scope_config

root=Path('/model'); scope=os.environ['GLM_SELECTIVE_W4_SCOPE']
config=json.loads((root/'config.json').read_text()); index=json.loads((root/'model.safetensors.index.json').read_text())
candidate_names=[name for name in index['weight_map'] if is_selective_candidate(name)]
names=[name for name in candidate_names if selected_weight(name,scope)]
expected=expected_weight_count(scope)
if len(names)!=expected: raise RuntimeError(f'scope count {len(names)} != {expected}')
args=QuantizationArgs(num_bits=4,type='int',symmetric=True,strategy='group',group_size=32)
producer=PackedQuantizationCompressor()
def mse_scale(weight):
  grouped=weight.float().reshape(weight.shape[0],-1,32); base=grouped.abs().amax(-1).clamp_min(torch.finfo(torch.float32).tiny)/7
  best_scale,best_loss=base,None
  for factor in torch.linspace(.70,1.00,16):
    scale=base*factor; packed=producer.compress_weight(weight,scale.to(torch.bfloat16),args)
    restored=producer.decompress_weight({**packed,'weight_scale':scale.to(torch.bfloat16)},args)
    loss=(restored.float()-weight.float()).square().flatten(1).mean(1)
    if best_loss is None: best_scale,best_loss=scale,loss
    else:
      choose=loss<best_loss; best_scale,best_loss=torch.where(choose[:,None],scale,best_scale),torch.minimum(loss,best_loss)
  return best_scale.to(torch.bfloat16)
grouped={}
for name in names: grouped.setdefault(index['weight_map'][name],[]).append(name)
converted=[]
for shard, targets in grouped.items():
  path=root/shard; temp=root/(shard+'.official.tmp'); tensors={}
  with safe_open(str(path),framework='pt',device='cpu') as source:
    for name in source.keys():
      if name in targets:
        weight=source.get_tensor(name); scale=mse_scale(weight); packed=producer.compress_weight(weight,scale,args)
        restored=producer.decompress_weight({**packed,'weight_scale':scale},args)
        if not torch.isfinite(restored).all(): raise RuntimeError(f'nonfinite official dequant: {name}')
        prefix=name.removesuffix('.weight'); tensors[prefix+'.weight_packed']=packed['weight_packed'].contiguous(); tensors[prefix+'.weight_scale']=scale.contiguous(); tensors[prefix+'.weight_shape']=torch.tensor(list(weight.shape),dtype=torch.int64)
        converted.append({'source':name,'shape':list(weight.shape),'packed_shape':list(packed['weight_packed'].shape),'scale_shape':list(scale.shape),'relative_l2':float(torch.linalg.vector_norm(restored.float()-weight.float())/torch.linalg.vector_norm(weight.float()).clamp_min(1e-30))})
      else: tensors[name]=source.get_tensor(name)
  save_file(tensors,str(temp),metadata={'format':'pt'}); temp.replace(path)
for name in names:
  del index['weight_map'][name]; prefix=name.removesuffix('.weight'); shard=next(k for k,v in grouped.items() if name in v)
  for suffix in ('.weight_packed','.weight_scale','.weight_shape'): index['weight_map'][prefix+suffix]=shard
config=apply_scope_to_config(config,candidate_names,scope)
validate_scope_config(config,candidate_names,scope)
index['metadata']['total_size']=sum((root/path).stat().st_size for path in sorted(set(index['weight_map'].values())))
(root/'config.json').write_text(json.dumps(config,indent=2,sort_keys=True)+'\n'); (root/'model.safetensors.index.json').write_text(json.dumps(index,indent=2,sort_keys=True)+'\n')
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
rows=[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(root.iterdir()) if p.is_file() and p.name not in {'model-files.sha256','model-files-manifest.json','.campaign-integrity-v1'}]
manifest={'schema_version':3,'repository':'local-derived/glm47flash-full47-official-selective-w4','revision':'ab31d120fbe79988fe2a0259993cf3c222aa8881','shard_count':4,'weight_bytes':sum(x['bytes'] for x in rows if x['path'].endswith('.safetensors')),'files':rows}
(root/'model-files-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n'); (root/'model-files.sha256').write_text(''.join(f"{x['sha256']}  {x['path']}\n" for x in rows))
print(json.dumps({'scope':scope,'scope_tensor_count':len(converted),'observer':'mse','official_producer':'PackedQuantizationCompressor','converted':converted,'manifest_sha256':sha(root/'model-files-manifest.json'),'weight_bytes':manifest['weight_bytes']},sort_keys=True))
'''


SCOPE_LABELS = {
    "combined": "full47-official-head-shared-w4",
    "head_only": "full47-official-head-w4-shared-bf16",
    "shared_only": "full47-official-shared-w4-bf16-head",
}
RESULT_KEYS = {
    "combined": "combined",
    "head_only": "head_w4_shared_bf16",
    "shared_only": "shared_w4_bf16_head",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tensor_hashes(root: Path, index: dict) -> dict[str, str]:
    headers: dict[str, tuple[int, dict]] = {}
    result = {}
    for name, shard in index["weight_map"].items():
        if shard not in headers:
            with (root / shard).open("rb") as handle:
                header_bytes = struct.unpack("<Q", handle.read(8))[0]
                headers[shard] = (8 + header_bytes, json.loads(handle.read(header_bytes)))
        base, header = headers[shard]
        start, end = header[name]["data_offsets"]
        digest = hashlib.sha256()
        with (root / shard).open("rb") as handle:
            handle.seek(base + start)
            remaining = end - start
            while remaining:
                block = handle.read(min(16 << 20, remaining))
                digest.update(block)
                remaining -= len(block)
        result[name] = digest.hexdigest()
    return result


def materialize(scope: str) -> dict:
    label = SCOPE_LABELS[scope]
    temporary = Path(tempfile.mkdtemp(prefix=f"official-{label}-", dir="/root/.cache"))
    try:
        for path in SOURCE.iterdir():
            if path.is_file(): shutil.copy2(path, temporary / path.name)
        command = ["docker", "run", "--rm", "--entrypoint", "bash", "-v", f"{temporary}:/model", "-v", f"{SCOPE_TOOL_DIR}:/scope:ro", "-e", f"GLM_SELECTIVE_W4_SCOPE={scope}", IMAGE, "-lc", "python3 - <<'PY'\n" + PRODUCER + "\nPY"]
        completed = subprocess.run(command, text=True, capture_output=True, timeout=4200)
        if completed.returncode:
            raise RuntimeError(completed.stderr[-4000:])
        try:
            producer_result = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("official producer did not emit a typed result") from error
        converted = producer_result.get("converted")
        if not isinstance(converted, list) or len(converted) != expected_weight_count(scope):
            raise RuntimeError("official producer numerical closure is incomplete")
        relative_l2 = [row.get("relative_l2") for row in converted if isinstance(row, dict)]
        if (
            len(relative_l2) != len(converted)
            or any(not isinstance(value, (int, float)) or not 0.0 <= value <= 0.20 for value in relative_l2)
        ):
            raise RuntimeError("official producer bounded pack/dequant admission failed")
        source_index = json.loads((SOURCE / "model.safetensors.index.json").read_text())
        index = json.loads((temporary / "model.safetensors.index.json").read_text())
        changed = [name for name in source_index["weight_map"] if selected_weight(name, scope)]
        expected = {name.removesuffix(".weight") + suffix for name in changed for suffix in (".weight_packed", ".weight_scale", ".weight_shape")}
        unrelated = set(source_index["weight_map"]) - set(changed)
        source_hashes, derived_hashes = tensor_hashes(SOURCE, source_index), tensor_hashes(temporary, index)
        derived_selective = {
            name
            for name in index["weight_map"]
            if name.endswith((".weight_packed", ".weight_scale", ".weight_shape"))
            and is_selective_candidate(name.rsplit("_", 1)[0])
        }
        closure = (
            len(changed) == expected_weight_count(scope)
            and expected == derived_selective
            and not (set(changed) & set(index["weight_map"]))
        )
        identity = all(source_hashes[name] == derived_hashes.get(name) for name in unrelated)
        manifest_sha = sha(temporary / "model-files-manifest.json")
        root = Path(f"/root/.cache/glm47flash-awq-{label}-{manifest_sha[:12]}")
        os.replace(temporary, root)
        return {"scope": scope, "root": str(root), "manifest_sha256": manifest_sha, "closure_pass": closure, "unrelated_byte_identity_pass": identity, "changed_bf16_tensors": len(changed), "derived_w4_tensors": len(expected), "numerical_admission_pass": True, "max_relative_l2": max(relative_l2), "producer_stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(), "source_config_sha256": sha(SOURCE / "config.json"), "source_index_sha256": sha(SOURCE / "model.safetensors.index.json")}
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scope",
        action="append",
        choices=VALID_SCOPES,
        help="materialize only the named scope; repeat for multiple scopes",
    )
    args = parser.parse_args()
    scopes = args.scope or ["combined", "shared_only"]
    OUT.mkdir(parents=True, exist_ok=True)
    result = {"schema_version": 2, "official_producer": "PackedQuantizationCompressor", "observer": "mse"}
    for scope in scopes:
        result[RESULT_KEYS[scope]] = materialize(scope)
    rows = [result[RESULT_KEYS[scope]] for scope in scopes]
    result["pass"] = all(row["closure_pass"] and row["unrelated_byte_identity_pass"] and row["numerical_admission_pass"] for row in rows)
    (OUT / "OFFICIAL_LOCAL_ADMISSION.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"artifact": str(OUT / "OFFICIAL_LOCAL_ADMISSION.json"), "pass": result["pass"]}, sort_keys=True))


if __name__ == "__main__":
    main()
