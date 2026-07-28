#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import struct
from typing import Any


PROJECT = pathlib.Path(__file__).resolve().parent
CHECKPOINT = PROJECT / "inputs/checkpoint"
OUTPUT = PROJECT / "artifacts/local-preparation/MANIFEST.json"
EXPECTED_FILES = {
    "config.json": (4621, "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1"),
    "tokenizer.json": (32169626, "cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f"),
    "tokenizer_config.json": (2095, "90c3a3ba5bf53818383a58e1a776cbcacd2a038d4812eaa373e1522f2d06f3df"),
    "chat_template.jinja": (18683, "ae53464bf3be25802b3a5b37def7fd89667067d7577049b3b2d74c4d8de4c6d4"),
    "processor_config.json": (1689, "32bdf45d2ad4cc29a0822ddd157a182de76644f0419a6228d151495256e9813c"),
    "model.safetensors.index.json": (120246, "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2"),
    "model-00001-of-00002.safetensors": (49784788364, "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa"),
    "model-00002-of-00002.safetensors": (12761549884, "018912220f559f7025d60333e0996183cd538aa77ad6f4988a89ce47be681f10"),
}
EXPECTED_INPUTS = {
    "exact_mix_runner.py": "143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7",
    "coherence_runner.py": "cdea4e0eddf69057785c0d09ef0e69e25adb5d8b3e2f5deb9bd0658552eb6af3",
}
EXPECTED_PROGRAMS = {
    "endpoint_entrypoint.py": "ab2fdf5eca6a4e85617e8357aa7f6eea5f2946576cebf3f885a34100709f20b9",
    "exact_shape_oracle.py": "1144bf287467a463ab565617f0773c152d8f872395cf0cca9803ec2e3a0ed33d",
    "remote_run.sh": "b998e17e346ed67c10d729c3c85e74bd1d840dffb5117ce97bf8196432a5e17a",
    "PINNED_SGLANG_AUDIT_CONTRACT.json": "db24f6147eecffac633f6a7bd7c109017abd8d62b57626ce52b4ce455f24d960",
}
IMAGE = "docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(16 * 1024 * 1024):
            value.update(block)
    return value.hexdigest()


def read_headers() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(CHECKPOINT.glob("*.safetensors")):
        with path.open("rb") as handle:
            header_size = struct.unpack("<Q", handle.read(8))[0]
            header = json.loads(handle.read(header_size))
        result.update({name: value for name, value in header.items() if name != "__metadata__"})
    return result


def require_tensor(headers: dict[str, dict[str, Any]], name: str, shape: list[int]) -> None:
    value = headers.get(name)
    if not value or value.get("dtype") != "BF16" or value.get("shape") != shape:
        raise ValueError(f"unexpected tensor contract for {name}: {value}")


def geometry(headers: dict[str, dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    text = config["text_config"]
    if (
        text["hidden_size"] != 5376
        or text["intermediate_size"] != 21504
        or text["num_hidden_layers"] != 60
        or text["num_attention_heads"] != 32
        or text["num_key_value_heads"] != 16
        or text["num_global_key_value_heads"] != 4
        or text["attention_k_eq_v"] is not True
    ):
        raise ValueError("frozen Gemma text geometry changed")
    families = {"sliding_attention": 0, "full_attention": 0}
    for layer, layer_type in enumerate(text["layer_types"]):
        families[layer_type] += 1
        prefix = f"model.language_model.layers.{layer}"
        q = [8192, 5376] if layer_type == "sliding_attention" else [16384, 5376]
        k = [4096, 5376] if layer_type == "sliding_attention" else [2048, 5376]
        o = [5376, 8192] if layer_type == "sliding_attention" else [5376, 16384]
        require_tensor(headers, f"{prefix}.self_attn.q_proj.weight", q)
        require_tensor(headers, f"{prefix}.self_attn.k_proj.weight", k)
        if layer_type == "sliding_attention":
            require_tensor(headers, f"{prefix}.self_attn.v_proj.weight", k)
        elif f"{prefix}.self_attn.v_proj.weight" in headers:
            raise ValueError(f"global layer {layer} unexpectedly has distinct V weights")
        require_tensor(headers, f"{prefix}.self_attn.o_proj.weight", o)
        require_tensor(headers, f"{prefix}.mlp.gate_proj.weight", [21504, 5376])
        require_tensor(headers, f"{prefix}.mlp.up_proj.weight", [21504, 5376])
        require_tensor(headers, f"{prefix}.mlp.down_proj.weight", [5376, 21504])
    if families != {"sliding_attention": 50, "full_attention": 10}:
        raise ValueError(f"unexpected layer family counts: {families}")
    k = 5376
    qkv_rows = 50 * 16384 + 10 * 20480
    fp8_weights = {
        "fused_qkv": qkv_rows * k,
        "attention_output": 50 * 5376 * 8192 + 10 * 5376 * 16384,
        "fused_gate_up": 60 * 43008 * 5376,
        "down": 60 * 5376 * 21504,
    }
    scale_elements = qkv_rows + 60 * 5376 + 60 * 43008 + 60 * 5376
    return {
        "layer_families": families,
        "included_runtime_modules": {
            "model.language_model.layers.*.self_attn.qkv_proj": 60,
            "model.language_model.layers.*.self_attn.o_proj": 60,
            "model.language_model.layers.*.mlp.gate_up_proj": 60,
            "model.language_model.layers.*.mlp.down_proj": 60,
        },
        "excluded_runtime_modules": [
            "model.vision_tower.*",
            "model.embed_vision.*",
            "model.language_model.embed_tokens (tied input/output embedding, not LinearBase)",
        ],
        "scale_granularity": "one float32 scale per output channel; dynamic one scale per activation token",
        "accumulation_and_output": "Hopper FP8 tensor-core GEMM with BF16 output",
        "resident_fp8_weight_bytes": sum(fp8_weights.values()),
        "resident_fp8_weight_bytes_by_family": fp8_weights,
        "resident_weight_scale_bytes": scale_elements * 4,
        "expected_fp8_module_count": 240,
        "oracle_shape": {"family": "fused_gate_up", "m": 32, "k": 5376, "n": 43008},
    }


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def main() -> int:
    actual_names = {path.name for path in CHECKPOINT.iterdir() if path.is_file()}
    if actual_names != set(EXPECTED_FILES):
        raise ValueError(f"checkpoint file set changed: {sorted(actual_names)}")
    files = []
    for name, (expected_bytes, expected_hash) in EXPECTED_FILES.items():
        path = CHECKPOINT / name
        actual = {"path": name, "bytes": path.stat().st_size, "sha256": digest(path)}
        actual["pass"] = actual["bytes"] == expected_bytes and actual["sha256"] == expected_hash
        files.append(actual)
    inputs = {}
    for name, expected_hash in EXPECTED_INPUTS.items():
        actual_hash = digest(PROJECT / "inputs" / name)
        inputs[name] = {"sha256": actual_hash, "pass": actual_hash == expected_hash}
    for name, expected_hash in EXPECTED_PROGRAMS.items():
        actual_hash = digest(PROJECT / name)
        inputs[name] = {"sha256": actual_hash, "pass": actual_hash == expected_hash}
    config = json.loads((CHECKPOINT / "config.json").read_text())
    result = {
        "schema_version": 1,
        "classification": "content_bound_inmemory_fp8_inputs",
        "model": f"google/gemma-4-31B-it@{REVISION}",
        "runtime_image": IMAGE,
        "checkpoint_terminal_sha256": "5f0765fa37f308e21d665571a92c29ba1998b22b5ee67d1edbfac103dafec481",
        "checkpoint_root": str(CHECKPOINT),
        "checkpoint_total_bytes": sum(row["bytes"] for row in files),
        "checkpoint_files": files,
        "gpu_inputs": inputs,
        "geometry": geometry(read_headers(), config),
        "implementation": {
            "loader": "SGLang Fp8Config(is_checkpoint_fp8_serialized=False, activation_scheme='dynamic')",
            "producer": "Fp8LinearMethod.process_weights_after_loading -> per_token_group_quant_fp8",
            "consumer": "Fp8LinearMethod.apply -> apply_fp8_linear -> sgl_kernel.fp8_scaled_mm",
            "selection": "--quantization fp8 with SGLANG_FP8_IGNORED_LAYERS=model.vision_tower,model.embed_vision",
            "serialization": False,
            "dequantized_hbm_intermediate": False,
            "sglang_tag_commit": "127b9e3283f7c2a43234b852ff5c9f1796d53624",
        },
    }
    result["pass"] = (
        result["checkpoint_total_bytes"] == 62578655208
        and all(row["pass"] for row in files)
        and all(row["pass"] for row in inputs.values())
    )
    atomic(OUTPUT, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
