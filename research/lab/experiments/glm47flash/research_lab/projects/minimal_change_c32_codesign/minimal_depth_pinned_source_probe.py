"""Inspect the pinned vLLM loader/quantization route for the derived proxy."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


root = Path("/model")
config = json.loads((root / "config.json").read_text())
index = json.loads((root / "model.safetensors.index.json").read_text())
registry_path = Path("/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/registry.py")
model_path = Path("/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/glm4_moe_lite.py")
quant_path = Path("/usr/local/lib/python3.12/dist-packages/vllm/model_executor/layers/quantization/compressed_tensors/compressed_tensors.py")
registry = registry_path.read_text()
model = model_path.read_text()
quant = quant_path.read_text()
keys = set(index["weight_map"])
layers = sorted({int(key.split(".")[2]) for key in keys if key.startswith("model.layers.")})
result = {
    "evidence_class": "measured_pinned_runtime_source_contract",
    "proxy_root": str(root),
    "config": {"num_hidden_layers": config["num_hidden_layers"], "model_type": config["model_type"], "architectures": config["architectures"], "quant_method": config["quantization_config"]["quant_method"]},
    "structural_keys": {"count": len(keys), "layer_ids": layers, "index_metadata_total_size": index["metadata"]["total_size"]},
    "runtime_source": {
        "registry_exact_architecture": '"Glm4MoeLiteForCausalLM": ("glm4_moe_lite", "Glm4MoeLiteForCausalLM")' in registry,
        "auto_weights_loader": "AutoWeightsLoader(self)" in model and "return loader.load_weights(weights)" in model,
        "compressed_tensors_wna16": "CompressedTensorsWNA16" in quant and "CompressionFormat.pack_quantized.value" in quant,
        "registry_sha256": sha256(registry_path),
        "model_sha256": sha256(model_path),
        "quantization_sha256": sha256(quant_path),
    },
    "loader_consumed_missing_unexpected": "UNMEASURED_NO_MODEL_INSTANTIATION",
    "cuda_load": "NOT_RUN_NO_GPU_AUTHORIZED",
    "decision": "STRUCTURAL_ROUTE_PASS_GPU_LOADER_OPEN",
}
print(json.dumps(result, indent=2, sort_keys=True))
