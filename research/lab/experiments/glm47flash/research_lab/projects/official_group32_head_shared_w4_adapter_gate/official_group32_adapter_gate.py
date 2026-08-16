#!/usr/bin/env python3
"""Fresh-process official uint4b8 adapter gate for GLM-4.7 Flash."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
MODEL = Path("/root/.cache/glm47flash-awq-ab31d120")
ARTIFACT = PROJECT / "artifacts" / "official_group32_adapter_gate" / "OFFICIAL_GROUP32_ADAPTER_GATE.json"
IMAGE = "glm-vllm:0.15.0-transformers-1618d44"


PROBE = r'''
import copy, hashlib, json, math, os, traceback
from pathlib import Path
import torch
from safetensors import safe_open
from compressed_tensors.compressors.quantized_compressors import PackedQuantizationCompressor
from compressed_tensors.quantization import QuantizationArgs
from vllm.model_executor.layers.linear import MergedColumnParallelLinear
from vllm.model_executor.models.glm4_moe import Glm4MoeMLP
from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead
from vllm.model_executor.layers.quantization.compressed_tensors.compressed_tensors import CompressedTensorsConfig, CompressedTensorsLinearMethod
from vllm.config import DeviceConfig, VllmConfig, set_current_vllm_config
from vllm.distributed.parallel_state import init_distributed_environment, initialize_model_parallel

ROOT = Path('/model')
config = json.loads((ROOT / 'config.json').read_text())
index = json.loads((ROOT / 'model.safetensors.index.json').read_text())

def selected_shared():
    return [f'model.layers.{layer}.mlp.shared_experts.{part}_proj.weight'
            for layer in range(1, 47) for part in ('gate', 'up', 'down')]

selected = ['lm_head.weight'] + selected_shared()
assert len(selected) == 139 and all(x in index['weight_map'] for x in selected)
candidate = copy.deepcopy(config['quantization_config'])
candidate['ignore'] = [x for x in candidate['ignore'] if x not in {n.removesuffix('.weight') for n in selected}]
candidate['config_groups']['parallel_lm_head_w4'] = {
    **copy.deepcopy(candidate['config_groups']['group_0']), 'targets': ['ParallelLMHead']}
ct = CompressedTensorsConfig.from_config(candidate)

args = QuantizationArgs(num_bits=4, type='int', symmetric=True, strategy='group', group_size=32)
producer = PackedQuantizationCompressor()

def mse_scale(weight):
    # MSE observer approximation, evaluated through the official producer/consumer.
    grouped = weight.float().reshape(weight.shape[0], -1, 32)
    base = grouped.abs().amax(-1).clamp_min(torch.finfo(torch.float32).tiny) / 7
    best_scale, best_loss = base, None
    for factor in torch.linspace(.70, 1.00, 16):
        scale = base * factor
        packed = producer.compress_weight(weight, scale.to(torch.bfloat16), args)
        restored = producer.decompress_weight({**packed, 'weight_scale': scale.to(torch.bfloat16)}, args)
        loss = (restored.float() - weight.float()).square().flatten(1).mean(1)
        if best_loss is None:
            best_scale, best_loss = scale, loss
        else:
            choose = loss < best_loss
            best_scale, best_loss = torch.where(choose[:, None], scale, best_scale), torch.minimum(loss, best_loss)
    return best_scale.to(torch.bfloat16)

def sample(name):
    with safe_open(str(ROOT / index['weight_map'][name]), framework='pt', device='cpu') as reader:
        weight = reader.get_slice(name)[:128].contiguous()
    scale = mse_scale(weight)
    packed = producer.compress_weight(weight, scale, args)
    restored = producer.decompress_weight({**packed, 'weight_scale': scale}, args)
    unpacked = producer.decompress_weight({**packed, 'weight_scale': scale}, args)
    err = restored.float() - weight.float()
    codes = __import__('compressed_tensors.compressors.quantized_compressors', fromlist=['unpack_from_int32']).unpack_from_int32(packed['weight_packed'], 4, weight.shape)
    return {'name': name, 'shape': list(weight.shape), 'packed_shape': list(packed['weight_packed'].shape),
            'scale_shape': list(scale.shape), 'official_pack_unpack_exact': bool(torch.equal(restored, unpacked)),
            'relative_l2': float(torch.linalg.vector_norm(err) / torch.linalg.vector_norm(weight.float()).clamp_min(1e-30)),
            'max_abs_error': float(err.abs().max()), 'saturation_fraction': float((codes.abs() >= 7).float().mean()),
            'packed_sha256': hashlib.sha256(packed['weight_packed'].numpy().tobytes()).hexdigest()}

head_stub = object.__new__(ParallelLMHead)
linear_stub = object.__new__(MergedColumnParallelLinear)
unrelated_stub = object.__new__(ParallelLMHead)
head_method = ct.get_quant_method(head_stub, 'lm_head')
linear_method = ct.get_quant_method(linear_stub, 'model.layers.1.mlp.shared_experts.gate_proj')
unrelated_method = ct.get_quant_method(unrelated_stub, 'model.layers.1.self_attn.q_a_proj')
init_distributed_environment(world_size=1, rank=0, distributed_init_method='tcp://127.0.0.1:29617', local_rank=0, backend='gloo')
initialize_model_parallel()
with set_current_vllm_config(VllmConfig(device_config=DeviceConfig('cpu'))):
    head = ParallelLMHead(154880, 2048, bias=False, params_dtype=torch.bfloat16, quant_config=ct, prefix='lm_head')
    shared = Glm4MoeMLP(2048, 1536, 'silu', quant_config=ct, prefix='model.layers.1.mlp.shared_experts')
registration = {
  'head_keys': sorted(head.state_dict()), 'shared_keys': sorted(shared.state_dict()),
  'head_bf16_weight_present': 'weight' in head._parameters,
  'shared_bf16_weight_present': any(k.endswith('.weight') for k in shared.state_dict()),
}
postload = {'attempted': False, 'head': None, 'shared': None, 'consumer': None}
for label, layer in [('head', head), ('shared', shared.gate_up_proj), ('shared_down', shared.down_proj)]:
    try:
        layer.quant_method.process_weights_after_loading(layer)
        postload[label] = {'pass': True}
    except Exception as error:
        postload[label] = {'pass': False, 'type': type(error).__name__, 'message': str(error), 'traceback_tail': traceback.format_exc()[-1800:]}
    postload['attempted'] = True
try:
    # This is the actual logits projection consumer used by the head/sampler contract.
    result = head.quant_method.apply(head, torch.zeros((1, 2048), dtype=torch.bfloat16), None)
    postload['consumer'] = {'pass': True, 'shape': list(result.shape), 'dtype': str(result.dtype), 'device': str(result.device)}
except Exception as error:
    postload['consumer'] = {'pass': False, 'type': type(error).__name__, 'message': str(error), 'traceback_tail': traceback.format_exc()[-1800:]}

samples = [sample('lm_head.weight'), sample('model.layers.1.mlp.shared_experts.gate_proj.weight'), sample('model.layers.1.mlp.shared_experts.up_proj.weight'), sample('model.layers.1.mlp.shared_experts.down_proj.weight')]
print('RESULT=' + json.dumps({
 'adapter': {'source_preimport': os.environ['ADAPTER_SOURCE_PREIMPORT'], 'selector': 'LinearBase_or_ParallelLMHead_only'},
 'selection': {'head_method': type(head_method).__name__ if head_method else None, 'head_scheme': type(getattr(head_stub, 'scheme', None)).__name__ if getattr(head_stub, 'scheme', None) else None, 'shared_method': type(linear_method).__name__ if linear_method else None, 'shared_scheme': type(getattr(linear_stub, 'scheme', None)).__name__ if getattr(linear_stub, 'scheme', None) else None, 'unrelated_method': type(unrelated_method).__name__ if unrelated_method else None},
 'registration': registration, 'postload_and_consumer': postload, 'samples': samples,
 'expected_selected_count': len(selected), 'all_selected_ignored_removed': not any(n.removesuffix('.weight') in candidate['ignore'] for n in selected),
}, sort_keys=True))
'''


def main() -> None:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "docker", "run", "--rm", "--entrypoint", "bash",
        "-v", f"{MODEL}:/model:ro", "-v", f"{PROJECT}:/work:ro", IMAGE, "-lc",
        "set -euo pipefail; "
        "src=/usr/local/lib/python3.12/dist-packages/vllm/model_executor/layers/quantization/compressed_tensors/compressed_tensors.py; "
        "cp \"$src\" /tmp/compressed_tensors.before.py; "
        "sed -i '/from vllm.model_executor.layers.linear import (/i from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead' \"$src\"; "
        "python3 - <<'PY'\nfrom pathlib import Path\np=Path('/usr/local/lib/python3.12/dist-packages/vllm/model_executor/layers/quantization/compressed_tensors/compressed_tensors.py')\ns=p.read_text(); needle='if isinstance(layer, LinearBase):'\nassert s.count(needle) == 1\np.write_text(s.replace(needle, 'if isinstance(layer, (LinearBase, ParallelLMHead)):'))\nPY\n"
        "export ADAPTER_SOURCE_PREIMPORT=$(sha256sum \"$src\" | cut -d\" \" -f1); "
        "python3 - <<'PY'\n" + PROBE + "\nPY",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=1200)
    probe = None
    if "RESULT=" in completed.stdout:
        probe = json.loads(completed.stdout.rsplit("RESULT=", 1)[1])
    payload = {
        "schema_version": 1,
        "checkpoint": str(MODEL),
        "checkpoint_revision": "ab31d120fbe79988fe2a0259993cf3c222aa8881",
        "runtime_image": IMAGE,
        "command_exit_code": completed.returncode,
        "probe": probe,
        "stdout_tail": completed.stdout[-6000:],
        "stderr_tail": completed.stderr[-6000:],
    }
    if probe is None:
        payload["decision"] = (
            "OFFICIAL_SELECTIVE_W4_RUNTIME_CLOSE_CUDA_KERNEL_SELECTION_BOUNDARY"
            if "MarlinLinearKernel cannot implement due to: Marlin only supported on CUDA" in completed.stderr
            else "OFFICIAL_SELECTIVE_W4_RUNTIME_CLOSE_EXECUTION_FAILURE"
        )
        payload["terminal"] = True
    else:
        selection = probe["selection"]
        postload = probe["postload_and_consumer"]
        ready = selection["head_method"] == "CompressedTensorsLinearMethod" and selection["head_scheme"] == "CompressedTensorsWNA16" and selection["shared_method"] == "CompressedTensorsLinearMethod" and selection["shared_scheme"] == "CompressedTensorsWNA16" and postload["head"]["pass"] and postload["shared"]["pass"] and postload["consumer"]["pass"]
        payload["decision"] = "OFFICIAL_SELECTIVE_W4_RUNTIME_READY" if ready else "OFFICIAL_SELECTIVE_W4_RUNTIME_CLOSE_CUDA_POSTLOAD_BOUNDARY"
        payload["terminal"] = True
    ARTIFACT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"artifact": str(ARTIFACT), "decision": payload["decision"], "exit": completed.returncode}))


if __name__ == "__main__":
    main()
