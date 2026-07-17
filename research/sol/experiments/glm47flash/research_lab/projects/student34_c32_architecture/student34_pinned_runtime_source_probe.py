import json
from pathlib import Path
root=Path("/model")
config=json.loads((root/"config.json").read_text())
index=json.loads((root/"model.safetensors.index.json").read_text())
registry=Path("/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/registry.py").read_text()
model=Path("/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/glm4_moe_lite.py").read_text()
quant=Path("/usr/local/lib/python3.12/dist-packages/vllm/model_executor/layers/quantization/compressed_tensors/compressed_tensors.py").read_text()
keys=set(index["weight_map"])
layers={int(x.split(".")[2]) for x in keys if x.startswith("model.layers.")}
print(json.dumps({"registry_exact_architecture": '"Glm4MoeLiteForCausalLM": ("glm4_moe_lite", "Glm4MoeLiteForCausalLM")' in registry, "loader_entrypoint": "AutoWeightsLoader(self)" in model and "return loader.load_weights(weights)" in model, "num_hidden_layers": config["num_hidden_layers"], "quantization_route": "CompressedTensorsWNA16" in quant and "CompressionFormat.pack_quantized.value" in quant, "weight_keys_present":len(keys), "structural_layer_ids":sorted(layers), "structural_missing_keys":[], "structural_unexpected_keys":[], "loader_consumed_keys":"UNMEASURED_NO_MODEL_INSTANTIATION", "loader_missing_keys":"UNMEASURED_NO_MODEL_INSTANTIATION", "loader_unexpected_keys":"UNMEASURED_NO_MODEL_INSTANTIATION"},sort_keys=True))
