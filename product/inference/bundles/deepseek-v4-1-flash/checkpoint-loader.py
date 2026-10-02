"""Check the production loader against DeepSeek's FP8 scale dtype without GPUs."""

import json
import struct
import tempfile
from pathlib import Path

import torch
from vllm.model_executor.model_loader.weight_utils import safetensors_weights_iterator

with tempfile.TemporaryDirectory() as directory:
    checkpoint = Path(directory) / "scale.safetensors"
    header = json.dumps(
        {"scale": {"dtype": "F8_E8M0", "shape": [1], "data_offsets": [0, 1]}}
    ).encode()
    header += b" " * (-len(header) % 8)
    checkpoint.write_bytes(struct.pack("<Q", len(header)) + header + b"\x7f")

    weights = dict(
        safetensors_weights_iterator(
            [str(checkpoint)],
            use_tqdm_on_load=False,
            safetensors_load_strategy="prefetch",
        )
    )
    assert weights.keys() == {"scale"}
    assert weights["scale"].dtype == torch.float8_e8m0fnu
    assert weights["scale"].view(torch.uint8).tolist() == [127]

print("DeepSeek FP8 checkpoint loader verified")
