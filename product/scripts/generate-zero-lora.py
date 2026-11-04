"""Generate a synthetic rank-one, zero-weight DeepSeek upload fixture."""

import argparse
import json
import struct
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    product = Path(__file__).resolve().parents[1]
    runtimes = json.loads((product / "inference/gpu/runtimes.json").read_text())
    runtime = next(value for value in runtimes.values()
                   if value["model_id"] == "deepseek/deepseek-v4.1-flash")
    release = runtime["release"]
    repo, revision = release["model_path"], release["model_revision"]
    url = f"https://huggingface.co/{repo}/resolve/{revision}/config.json"
    with urllib.request.urlopen(url, timeout=20) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Oversized base configuration")
    document = json.loads(raw)
    config = document.get("text_config", document)
    layers = config["num_hidden_layers"]
    input_size = config["q_lora_rank"]
    output_size = config["num_attention_heads"] * config["head_dim"]
    header, offset = {"__metadata__": {"format": "pt"}}, 0
    for layer in range(layers):
        for side, shape in (("A", [1, input_size]), ("B", [output_size, 1])):
            size = 2 * shape[0] * shape[1]
            name = f"base_model.model.layers.{layer}.attn.wq_b.lora_{side}.weight"
            header[name] = {"dtype": "BF16", "shape": shape,
                            "data_offsets": [offset, offset + size]}
            offset += size
    encoded = json.dumps(header, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 8)
    args.output.mkdir(parents=True, exist_ok=True)
    adapter = {"base_model_name_or_path": repo, "revision": revision,
               "peft_type": "LORA", "task_type": "CAUSAL_LM", "r": 1,
               "lora_alpha": 1, "lora_dropout": 0.0, "target_modules": ["wq_b"],
               "bias": "none", "inference_mode": True, "use_dora": False,
               "fan_in_fan_out": False}
    (args.output / "adapter_config.json").write_text(json.dumps(adapter, indent=2) + "\n")
    with (args.output / "adapter_model.safetensors").open("wb") as output:
        output.write(struct.pack("<Q", len(encoded)))
        output.write(encoded)
        output.write(bytes(offset))
    print(json.dumps({"output": str(args.output), "layers": layers,
                      "rank": 1, "dtype": "BF16", "weights_bytes": offset,
                      "revision": revision, "synthetic": True}))


if __name__ == "__main__":
    main()
