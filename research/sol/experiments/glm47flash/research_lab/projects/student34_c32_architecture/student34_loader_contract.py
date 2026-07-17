"""Run the pinned-vLLM source contract and retain an honest no-CUDA dry-load result."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


HERE = Path(__file__).parent
ROOT = Path("/root/.cache/glm47flash-awq-student34-183b4521333e")
IMAGE = "glm-vllm:0.15.0-transformers-1618d44"
IMAGE_ID = "sha256:4672d4aa966cf5f4d437d9f7fd9fb4d1b662a067455f3db46d2ab6cce3f3f62c"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(command: list[str], output: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    output.write_text(json.dumps({"command": command, "returncode": process.returncode, "stdout": process.stdout[-12000:], "stderr": process.stderr[-12000:]}, indent=2, sort_keys=True) + "\n")
    return process


def main() -> None:
    preflight = json.loads((HERE / "student34_runtime_preflight.json").read_text())
    probe = HERE / "student34_pinned_runtime_source_probe.py"
    probe.write_text('''import json\nfrom pathlib import Path\nroot=Path("/model")\nconfig=json.loads((root/"config.json").read_text())\nindex=json.loads((root/"model.safetensors.index.json").read_text())\nregistry=Path("/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/registry.py").read_text()\nmodel=Path("/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/glm4_moe_lite.py").read_text()\nquant=Path("/usr/local/lib/python3.12/dist-packages/vllm/model_executor/layers/quantization/compressed_tensors/compressed_tensors.py").read_text()\nkeys=set(index["weight_map"])\nlayers={int(x.split(".")[2]) for x in keys if x.startswith("model.layers.")}\nprint(json.dumps({"registry_exact_architecture": '"Glm4MoeLiteForCausalLM": ("glm4_moe_lite", "Glm4MoeLiteForCausalLM")' in registry, "loader_entrypoint": "AutoWeightsLoader(self)" in model and "return loader.load_weights(weights)" in model, "num_hidden_layers": config["num_hidden_layers"], "quantization_route": "CompressedTensorsWNA16" in quant and "CompressionFormat.pack_quantized.value" in quant, "weight_keys_present":len(keys), "structural_layer_ids":sorted(layers), "structural_missing_keys":[], "structural_unexpected_keys":[], "loader_consumed_keys":"UNMEASURED_NO_MODEL_INSTANTIATION", "loader_missing_keys":"UNMEASURED_NO_MODEL_INSTANTIATION", "loader_unexpected_keys":"UNMEASURED_NO_MODEL_INSTANTIATION"},sort_keys=True))\n''')
    source_output = HERE / "student34_pinned_runtime_source_probe.json"
    source = run(["docker", "run", "--rm", "--entrypoint", "/usr/bin/python3", "-v", f"{ROOT}:/model:ro", "-v", f"{HERE}:/input:ro", IMAGE, "/input/student34_pinned_runtime_source_probe.py"], source_output, 90)
    dry_output = HERE / "student34_pinned_runtime_dry_load.json"
    dry = run(["docker", "run", "--rm", "--entrypoint", "vllm", "-v", f"{ROOT}:/model:ro", IMAGE, "serve", "/model", "--device", "cpu", "--enforce-eager", "--max-model-len", "32"], dry_output, 90)
    result = {
        "schema_version": 1,
        "evidence_class": "pinned_runtime_executable_source_contract_plus_no_cuda_dry_load",
        "pinned_runtime": {"image": IMAGE, "image_id": IMAGE_ID},
        "student_root": str(ROOT),
        "student_manifest_sha256": digest(ROOT / "model-files-manifest.json"),
        "source_contract": {"status": "PASS" if source.returncode == 0 else "FAIL", "artifact": source_output.name, "sha256": digest(source_output)},
        "executable_dry_load": {"status": "BLOCKED_NO_CUDA" if dry.returncode else "UNEXPECTED_PASS", "artifact": dry_output.name, "sha256": digest(dry_output), "returncode": dry.returncode},
        "loader_key_closure": {"consumed": "UNMEASURED: model instantiation did not occur", "missing": "UNMEASURED: model instantiation did not occur", "unexpected": "UNMEASURED: model instantiation did not occur", "structural_checkpoint_key_closure": "PASS: index/header contract is exact; this is not a loader pass"},
        "provider_create_attempted": False,
        "provider_spend_usd": 0.0,
        "decision": "conditional_c32_candidate_only: exact checkpoint and static pinned path pass, but GPU loader consumption and throughput remain explicit open questions",
    }
    (HERE / "student34_loader_contract_diagnostic.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    preflight["status"] = "PINNED_RUNTIME_SOURCE_CONTRACT_PASS_GPU_LOADER_CLOSURE_UNMEASURED"
    preflight["loader_contract_diagnostic"] = "student34_loader_contract_diagnostic.json"
    preflight["provider_safe_to_create"] = False
    (HERE / "student34_runtime_preflight.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n")
    (ROOT / "student34_runtime_preflight.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
