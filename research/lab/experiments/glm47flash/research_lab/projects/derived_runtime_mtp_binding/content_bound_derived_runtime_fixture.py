#!/usr/bin/env python3
"""Content-bound exact-runtime MTP binding probe; never allocates model weights."""

import hashlib
import json
import subprocess
import copy
from pathlib import Path


MODEL = Path("/root/.cache/glm47flash-awq-ab31d120")
IMAGE = "glm47-observer-patch-smoke:transformers-1618d44"
EXPECTED_BASE = "sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543"
REVISION = "1618d44b9295361607ec74d7be860ba886aac039"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    config = json.loads((MODEL / "config.json").read_text())
    index = json.loads((MODEL / "model.safetensors.index.json").read_text())
    layer_names = sorted(
        name for name in index["weight_map"] if name.startswith("model.layers.47.")
    )
    probe = r'''
import json
import copy
from vllm.config import ModelConfig, ParallelConfig, SpeculativeConfig
from vllm.model_executor.models import ModelRegistry
from vllm.model_executor.models.glm4_moe_lite import get_spec_layer_idx_from_weight_name
from vllm.model_executor.models.glm4_moe_lite_mtp import Glm4MoeLiteMTP

target = ModelConfig(model="/model", tokenizer="/model", max_model_len=16384,
                     quantization="compressed-tensors")
parallel = ParallelConfig(tensor_parallel_size=1)
target_hf_config = copy.deepcopy(target.hf_config)
overridden = SpeculativeConfig.hf_config_override(copy.deepcopy(target_hf_config))
rewriter = object.__new__(Glm4MoeLiteMTP)
names = json.loads(__import__("os").environ["LAYER_NAMES"])
mapped = []
for name in names:
    layer = get_spec_layer_idx_from_weight_name(target_hf_config, name)
    mapped.append({"name": name, "layer": layer,
                   "rewritten": rewriter._rewrite_spec_layer_name(layer, name)})
print("RESULT=" + json.dumps({
    "transformers_version": __import__("transformers").__version__,
    "vllm_version": __import__("vllm").__version__,
    "target_model_type": target.hf_config.model_type,
    "target_architecture": target.hf_config.architectures,
    "target_quantization": target.quantization,
    "target_registry": str(ModelRegistry.models["Glm4MoeLiteForCausalLM"]),
    "mtp_registry": str(ModelRegistry.models["Glm4MoeLiteMTPModel"]),
    "planner_override": {
        "model_type": overridden.model_type,
        "architectures": overridden.architectures,
        "num_hidden_layers": overridden.num_hidden_layers,
        "n_predict": overridden.n_predict,
    },
    "layer_mapping": mapped,
    "parallel_tensor_size": parallel.tensor_parallel_size,
}, sort_keys=True))
'''
    env = {"LAYER_NAMES": json.dumps(layer_names)}
    command = [
        "docker", "run", "--rm", "--entrypoint", "bash",
        "-e", f"LAYER_NAMES={json.dumps(layer_names)}",
        "-v", f"{MODEL}:/model:ro", IMAGE, "-lc",
        "python3 - <<'PY'\n" + probe + "\nPY",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, env={**__import__("os").environ, **env}, timeout=180)
    result = {
        "schema_version": 1,
        "image": IMAGE,
        "expected_base_digest": EXPECTED_BASE,
        "transformers_revision": REVISION,
        "checkpoint": str(MODEL),
        "config_sha256": sha256(MODEL / "config.json"),
        "index_sha256": sha256(MODEL / "model.safetensors.index.json"),
        "architecture": config["architectures"],
        "model_type": config["model_type"],
        "num_hidden_layers": config["num_hidden_layers"],
        "num_nextn_predict_layers": config["num_nextn_predict_layers"],
        "layer_47_tensor_count": len(layer_names),
        "layer_47_files": sorted({index["weight_map"][name] for name in layer_names}),
        "probe_exit_code": completed.returncode,
        "probe": (json.loads(completed.stdout.split("RESULT=", 1)[1].strip())
                  if completed.returncode == 0 and "RESULT=" in completed.stdout else None),
        "probe_stdout_tail": completed.stdout[-2000:],
        "probe_stderr_tail": completed.stderr[-4000:],
        "weight_materialization": "not attempted_by_scope",
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
