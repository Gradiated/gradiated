#!/usr/bin/env python3
"""Pack and bind the exact GLM-4.7 Flash output head without checkpoint mutation."""

import hashlib
import json
import subprocess
from pathlib import Path


PROJECT = Path(__file__).parent
MODEL = Path("/root/.cache/glm47flash-awq-ab31d120")
OUT = PROJECT / "lm_head_w4_bridge.json"
IMAGE = "glm-vllm:0.15.0-transformers-1618d44"
REVISION = "ab31d120fbe79988fe2a0259993cf3c222aa8881"
BASE_DIGEST = "sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    index = json.loads((MODEL / "model.safetensors.index.json").read_text())
    shard = MODEL / index["weight_map"]["lm_head.weight"]
    probe = r'''
import copy
import hashlib
import json
import struct
from pathlib import Path

import torch
from safetensors import safe_open
from vllm.model_executor.layers.quantization.compressed_tensors.compressed_tensors import CompressedTensorsConfig
from vllm.model_executor.layers.quantization.kernels.mixed_precision.MPLinearKernel import MPLinearLayerConfig
from vllm.model_executor.layers.quantization.kernels.mixed_precision.marlin import MarlinLinearKernel
from vllm.model_executor.layers.quantization.utils.marlin_utils import check_marlin_supports_shape
from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead
from vllm.scalar_type import scalar_types

model = Path("/model")
config = json.loads((model / "config.json").read_text())
index = json.loads((model / "model.safetensors.index.json").read_text())
head = "lm_head.weight"
shard = model / index["weight_map"][head]
with shard.open("rb") as stream:
    header_len = struct.unpack("<Q", stream.read(8))[0]
    header = json.loads(stream.read(header_len))
spec = header[head]
start, end = spec["data_offsets"]
raw_digest = hashlib.sha256()
with shard.open("rb") as stream:
    stream.seek(8 + header_len + start)
    remaining = end - start
    while remaining:
        chunk = stream.read(min(8 * 1024 * 1024, remaining))
        raw_digest.update(chunk)
        remaining -= len(chunk)

rows, cols = spec["shape"]
group = 32
pack_factor = 8
chunk_rows = 256
source_sum_sq = error_sum_sq = error_abs_sum = 0.0
source_abs_max = error_abs_max = 0.0
element_count = saturation_count = qmin_count = qmax_count = 0
packed_digest = hashlib.sha256()
scale_digest = hashlib.sha256()
with safe_open(str(shard), framework="pt", device="cpu") as reader:
    view = reader.get_slice(head)
    for begin in range(0, rows, chunk_rows):
        weight = view[begin:min(begin + chunk_rows, rows), :].to(torch.float32)
        grouped = weight.reshape(-1, cols // group, group)
        scale = grouped.abs().amax(dim=-1) / 7.0
        scale = torch.where(scale == 0, torch.ones_like(scale), scale).to(torch.bfloat16)
        q = torch.round(grouped / scale.float().unsqueeze(-1)).clamp(-8, 7).to(torch.int8)
        unpacked = q.reshape(-1, cols).float() * scale.float().repeat_interleave(group, dim=1)
        error = unpacked - weight
        source_sum_sq += float(weight.square().sum())
        error_sum_sq += float(error.square().sum())
        error_abs_sum += float(error.abs().sum())
        source_abs_max = max(source_abs_max, float(weight.abs().max()))
        error_abs_max = max(error_abs_max, float(error.abs().max()))
        saturation_count += int((q.abs() >= 7).sum())
        qmin_count += int((q == -8).sum())
        qmax_count += int((q == 7).sum())
        element_count += q.numel()
        # Native compressed-tensors packs eight signed 4-bit two's-complement values
        # along K into int32; retain digest rather than a second 170 MiB checkpoint.
        unsigned = (q.to(torch.int16) & 0xF).reshape(-1, cols // pack_factor, pack_factor)
        packed = sum(unsigned[..., i] << (4 * i) for i in range(pack_factor)).to(torch.int32)
        packed_digest.update(packed.numpy().tobytes())
        scale_digest.update(scale.view(torch.uint16).numpy().tobytes())

candidate_config = copy.deepcopy(config["quantization_config"])
candidate_config["ignore"] = [x for x in candidate_config["ignore"] if x != "lm_head"]
ct = CompressedTensorsConfig.from_config(candidate_config)
head_layer = object.__new__(ParallelLMHead)
head_method = ct.get_quant_method(head_layer, "lm_head")
try:
    scheme = ct.get_scheme(layer=None, layer_name="lm_head")
    scheme_failure = None
except ValueError as error:
    scheme = None
    scheme_failure = str(error)
linear = MPLinearLayerConfig(
    full_weight_shape=(cols, rows), partition_weight_shape=(cols, rows),
    weight_type=scalar_types.uint4b8, act_type=torch.bfloat16, group_size=32,
    zero_points=False, has_g_idx=False,
)
shape_ok, shape_reason = check_marlin_supports_shape(rows, cols, cols, 32)
marlin_ok, marlin_reason = MarlinLinearKernel.can_implement(linear)
print("RESULT=" + json.dumps({
    "head": {"name": head, "dtype": spec["dtype"], "shape": spec["shape"], "bytes": end-start,
             "raw_sha256": raw_digest.hexdigest(), "shard": shard.name},
    "packing": {
       "scheme": "symmetric_int4_group32_two_complement_K_packed", "pack_factor": pack_factor,
       "weight_packed": {"name": "lm_head.weight_packed", "dtype": "I32", "shape": [rows, cols // pack_factor], "bytes": rows * cols // 2, "sha256": packed_digest.hexdigest()},
       "weight_scale": {"name": "lm_head.weight_scale", "dtype": "BF16", "shape": [rows, cols // group], "bytes": rows * (cols // group) * 2, "sha256": scale_digest.hexdigest()},
       "weight_shape": {"name": "lm_head.weight_shape", "dtype": "I64", "shape": [2], "bytes": 16, "value": [rows, cols]},
       "candidate_bytes": rows * cols // 2 + rows * (cols // group) * 2 + 16,
       "error": {"rmse": (error_sum_sq / element_count) ** .5, "mae": error_abs_sum / element_count,
                 "max_abs": error_abs_max, "relative_l2": (error_sum_sq / source_sum_sq) ** .5,
                 "source_abs_max": source_abs_max},
       "quantized_values": {"elements": element_count, "abs_ge_7_fraction": saturation_count / element_count,
                            "minus_8_fraction": qmin_count / element_count, "plus_7_fraction": qmax_count / element_count},
    },
    "loader": {"lm_head_removed_from_ignore": "lm_head" not in candidate_config["ignore"],
               "lm_head_class_mro": [x.__name__ for x in type(head_layer).__mro__],
               "quant_method_for_actual_parallel_lm_head": type(head_method).__name__ if head_method else None,
               "matched_scheme_class": type(scheme).__name__ if scheme else None,
               "scheme_selection_failure": scheme_failure,
               "scheme_group_size": getattr(scheme, "group_size", None),
               "scheme_symmetric": getattr(scheme, "symmetric", None),
               "scheme_weight_type": str(getattr(scheme, "quant_type", None))},
    "marlin": {"runtime": __import__("vllm").__version__, "target_compute_capability": 89,
               "shape_gate": {"pass": shape_ok, "reason": shape_reason},
               "live_cpu_can_implement": {"pass": marlin_ok, "reason": marlin_reason},
               "dispatch_contract": {str(m): "MarlinLinearKernel.apply_weights [M,2048] x [2048,154880]" for m in (1, 8, 16)},
               "limitation": "no CUDA allocation by project scope; live_cpu_can_implement is expected false only because Marlin requires CUDA"},
}, sort_keys=True))
'''
    command = [
        "docker", "run", "--rm", "--entrypoint", "bash",
        "-v", f"{MODEL}:/model:ro", IMAGE, "-lc",
        "python3 - <<'PY'\n" + probe + "\nPY",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=900)
    artifact = {
        "schema_version": 1,
        "checkpoint": str(MODEL),
        "checkpoint_revision": REVISION,
        "config_sha256": sha256(MODEL / "config.json"),
        "index_sha256": sha256(MODEL / "model.safetensors.index.json"),
        "runtime_image": IMAGE,
        "expected_base_digest": BASE_DIGEST,
        "fixture_sha256": sha256(Path(__file__)),
        "probe_exit_code": completed.returncode,
        "probe": (json.loads(completed.stdout.split("RESULT=", 1)[1])
                  if completed.returncode == 0 and "RESULT=" in completed.stdout else None),
        "probe_stdout_tail": completed.stdout[-2000:],
        "probe_stderr_tail": completed.stderr[-4000:],
    }
    OUT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"artifact": str(OUT), "exit": completed.returncode,
                      "result": artifact["probe"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
