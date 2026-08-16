#!/usr/bin/env python3
"""Fail-closed pinned-image binding check for the current AWQ MTP payload."""

import json
import subprocess
from pathlib import Path


MODEL = Path("/root/.cache/glm47flash-awq-ab31d120")
IMAGE = (
    "vllm/vllm-openai:v0.15.0@sha256:"
    "97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543"
)


def main() -> None:
    config = json.loads((MODEL / "config.json").read_text())
    index = json.loads((MODEL / "model.safetensors.index.json").read_text())
    layer = sorted(key for key in index["weight_map"] if key.startswith("model.layers.47."))
    probe = """
from vllm.config import ModelConfig
config = ModelConfig(model='/model', tokenizer='/model', max_model_len=16384)
print(config.hf_config.model_type)
"""
    completed = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "bash", "-v", f"{MODEL}:/model:ro", IMAGE, "-lc", f"python3 - <<'PY'\n{probe}\nPY"],
        check=False,
        capture_output=True,
        text=True,
    )
    print(json.dumps({
        "image": IMAGE,
        "checkpoint": str(MODEL),
        "architecture": config["architectures"],
        "model_type": config["model_type"],
        "num_hidden_layers": config["num_hidden_layers"],
        "num_nextn_predict_layers": config["num_nextn_predict_layers"],
        "layer_47_tensor_count": len(layer),
        "layer_47_files": sorted(set(index["weight_map"][key] for key in layer)),
        "model_config_exit_code": completed.returncode,
        "model_config_stdout": completed.stdout[-2000:],
        "model_config_stderr": completed.stderr[-4000:],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
