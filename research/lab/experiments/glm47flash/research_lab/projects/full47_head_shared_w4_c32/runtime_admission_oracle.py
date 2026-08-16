#!/usr/bin/env python3
"""Exact pinned-runtime scheme-selection oracle for selective W4 roots."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


HERE = Path(__file__).parent
ROOT = Path("/root/.cache/glm47flash-awq-full47-head-shared-w4-1bd3249b9802")
OUT = HERE / "artifacts" / "runtime_admission_r3" / "RUNTIME_ADMISSION.json"
IMAGE = "glm-vllm:0.15.0-transformers-1618d44"


def main() -> None:
    probe = r'''
import copy,json
from pathlib import Path
import torch
from vllm.model_executor.layers.linear import LinearBase
from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead
from vllm.model_executor.layers.quantization.compressed_tensors.compressed_tensors import CompressedTensorsConfig
root=Path('/model'); c=json.loads((root/'config.json').read_text())['quantization_config']
c=copy.deepcopy(c); c['config_groups']['head_w4']=copy.deepcopy(c['config_groups']['group_0']); c['config_groups']['head_w4']['targets']=['ParallelLMHead']
ct=CompressedTensorsConfig.from_config(c)
head=object.__new__(ParallelLMHead); linear=object.__new__(LinearBase)
before=ct.get_quant_method(head,'lm_head')
from vllm.model_executor.layers.quantization.compressed_tensors import compressed_tensors as module
source=Path(module.__file__); text=source.read_text(); needle='if isinstance(layer, LinearBase):'
if text.count(needle)!=1: raise RuntimeError('unexpected pinned dispatch source')
text=text.replace(needle,'if isinstance(layer, (LinearBase, ParallelLMHead)):')
source.write_text(text)
after=ct.get_quant_method(head,'lm_head'); shared=ct.get_quant_method(linear,'model.layers.1.mlp.shared_experts.gate_proj')
idx=json.loads((root/'model.safetensors.index.json').read_text())['weight_map']
required=['lm_head.weight_packed','lm_head.weight_scale','lm_head.weight_shape','model.layers.1.mlp.shared_experts.gate_proj.weight_packed','model.layers.1.mlp.shared_experts.gate_proj.weight_scale','model.layers.1.mlp.shared_experts.gate_proj.weight_shape']
print(json.dumps({'before':type(before).__name__ if before else None,'after':type(after).__name__ if after else None,'shared':type(shared).__name__ if shared else None,'required_payload_present':all(x in idx for x in required),'head_bf16_absent':'lm_head.weight' not in idx,'shared_bf16_absent':'model.layers.1.mlp.shared_experts.gate_proj.weight' not in idx,'source_patch_sha256':hashlib.sha256(text.encode()).hexdigest()}))
'''
    completed = subprocess.run(["docker", "run", "--rm", "-v", f"{ROOT}:/model:ro", "--entrypoint", "python3", IMAGE, "-c", "import hashlib;" + probe], text=True, capture_output=True, timeout=300)
    payload = {"runtime_image": IMAGE, "root": str(ROOT), "exit_code": completed.returncode, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:]}
    if completed.returncode == 0:
        payload["result"] = json.loads(next(line for line in reversed(completed.stdout.splitlines()) if line.startswith("{")))
        result=payload["result"]
        payload["pass"] = result["before"] is None and result["after"] == "CompressedTensorsLinearMethod" and result["shared"] == "CompressedTensorsLinearMethod" and result["required_payload_present"] and result["head_bf16_absent"] and result["shared_bf16_absent"]
    else: payload["pass"] = False
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(payload, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"artifact":str(OUT),"pass":payload["pass"]}))


if __name__ == '__main__': main()
