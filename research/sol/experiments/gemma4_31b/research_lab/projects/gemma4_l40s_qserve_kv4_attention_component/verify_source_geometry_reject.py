#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


OMNISERVE_COMMIT = "02b2925aa6fa3b92b06316a1524b7f38922cd9c8"
SOURCE_HASHES = {
    "kernels/setup.py": "6b24d3482e64ac4ad155297f2929dfbb3b44cfec95ee9a12951feb76bdaee08c",
    "kernels/csrc/fused_attention/fused_attention_fine_grained/fine_grained_common/applyBiasRopeUpdateKVCache.h": "a1298232f595a04d4d598d98d96ca7955fdb753dc8303d516be69eb39aca7127",
    "kernels/csrc/fused_attention/fused_attention_fine_grained/dense_attention/decoderMaskedMultiheadAttention.cu": "58a6c1fc9f07d5dba79871039f64891fd2655659de8a4040912e51a68fcc29c0",
    "kernels/csrc/fused_attention/fused_attention_fine_grained/dense_attention/decoderMaskedMultiheadAttentionTemplate.hpp": "54875aba713c5de1c71cce9e7292ee45af536e3fd0f21ebf35952c2a488fd6fe",
    "kernels/csrc/fused_attention/fused_attention_fine_grained/dense_attention/fused_attention.cpp": "a46980d49c4d33e0a3fee9c086a6d574afcd424788d53ac089d5719f3013539a",
    "kernels/csrc/fused_attention/common/kvCacheUtils.h": "1e87c405b594e22779b17cd2563ca17bb28b3da5e841e2c088c6292f7f7ea377",
}
MODEL_CONFIG_SHA256 = "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_bytes(repo: Path, path: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), "show", f"HEAD:{path}"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--omniserve", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    args = parser.parse_args()

    head = subprocess.run(
        ["git", "-C", str(args.omniserve), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    if head != OMNISERVE_COMMIT:
        raise SystemExit(f"OmniServe commit mismatch: {head}")

    source = {}
    for path, expected in SOURCE_HASHES.items():
        data = git_bytes(args.omniserve, path)
        actual = sha256_bytes(data)
        if actual != expected:
            raise SystemExit(f"source hash mismatch for {path}: {actual}")
        source[path] = data.decode()

    config_bytes = args.model_config.read_bytes()
    if sha256_bytes(config_bytes) != MODEL_CONFIG_SHA256:
        raise SystemExit("Gemma config hash mismatch")
    config = json.loads(config_bytes)["text_config"]
    layer_types = config["layer_types"]
    local_layers = [i for i, layer in enumerate(layer_types) if layer == "sliding_attention"]
    global_layers = [i for i, layer in enumerate(layer_types) if layer == "full_attention"]
    geometry = {
        "layers": len(layer_types),
        "local_layers": local_layers,
        "global_layers": global_layers,
        "query_heads": config["num_attention_heads"],
        "local_kv_heads": config["num_key_value_heads"],
        "local_head_dim": config["head_dim"],
        "global_kv_heads": config["num_global_key_value_heads"],
        "global_head_dim": config["global_head_dim"],
        "sliding_window": config["sliding_window"],
        "attention_k_eq_v": config["attention_k_eq_v"],
    }
    expected_geometry = {
        "layers": 60,
        "local_layers": [i for i in range(60) if i % 6 != 5],
        "global_layers": [i for i in range(60) if i % 6 == 5],
        "query_heads": 32,
        "local_kv_heads": 16,
        "local_head_dim": 256,
        "global_kv_heads": 4,
        "global_head_dim": 512,
        "sliding_window": 1024,
        "attention_k_eq_v": True,
    }
    if geometry != expected_geometry:
        raise SystemExit(f"Gemma geometry mismatch: {geometry}")

    setup = source["kernels/setup.py"]
    producer = source[
        "kernels/csrc/fused_attention/fused_attention_fine_grained/fine_grained_common/applyBiasRopeUpdateKVCache.h"
    ]
    consumer = source[
        "kernels/csrc/fused_attention/fused_attention_fine_grained/dense_attention/decoderMaskedMultiheadAttention.cu"
    ]
    if '"8.9"' not in setup:
        raise SystemExit("OmniServe setup does not bind SM89")
    if "else if (size_per_head <= 256)" not in producer:
        raise SystemExit("producer <=256 dispatch missing")
    if "doesn't support head size = %d" not in producer:
        raise SystemExit("producer unsupported-head terminal missing")
    if re.search(r"(?m)^\s*else if \(size_per_head <= 512\)", producer):
        raise SystemExit("producer unexpectedly supports head dimension 512")
    if not re.search(r"(?m)^\s*case 128:", consumer):
        raise SystemExit("consumer head dimension 128 instantiation missing")
    if re.search(r"(?m)^\s*case (256|512):", consumer):
        raise SystemExit("consumer unexpectedly supports Gemma head dimensions")
    if "default: assert(false);" not in consumer:
        raise SystemExit("consumer unsupported-head assertion missing")

    print(
        json.dumps(
            {
                "classification": "typed_source_geometry_reject",
                "consumer_supported_head_dimensions": [128],
                "geometry": geometry,
                "omniserve_commit": head,
                "producer_supported_head_dimension_maximum": 256,
                "sm89_build_target_present": True,
                "verified": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
