#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SOURCE_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1 << 20), b""):
            value.update(part)
    return value.hexdigest()


def row(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def atomic(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    frozen = sorted(path for path in (ROOT / "inputs").rglob("*") if path.is_file())
    candidate = [
        ROOT / "e5m2_fa3_component.py",
        ROOT / "gemma4_layer_hybrid_backend.py",
        ROOT / "install_hybrid_backend.py",
        ROOT / "sitecustomize.py",
        ROOT / "remote_component.sh",
        ROOT / "remote_e5m2_candidate.sh",
        ROOT / "run_e5m2_owner.py",
    ]
    binding = {
        "schema_version": 1,
        "status": "frozen",
        "runtime": {
            "source_commit": SOURCE_COMMIT,
            "image": IMAGE,
            "accelerator": "nvidia-h200-sxm",
        },
        "operation": {
            "phase": "decode",
            "producer": "SWAKVPool.set_kv_buffer -> MHATokenToKVPool.set_kv_buffer",
            "control": "TritonAttnBackend.forward_decode/decode_attention_fwd",
            "candidate": "FlashAttentionBackend.forward_decode/sgl_kernel.flash_attn_with_kvcache(ver=3)",
            "batch_size": 32,
            "context_tokens": 1024,
            "page_size": 1,
            "query_dtype": "torch.bfloat16",
            "kv_dtype": "torch.float8_e5m2",
            "local_geometry": [32, 16, 256],
            "global_geometry": [32, 4, 512],
            "local_layers": [i for i in range(60) if (i + 1) % 6],
            "global_layers": list(range(5, 60, 6)),
        },
        "physical_hypothesis": {
            "change": "Bind FA3 v3 directly to the qualified E5M2 page-one local pool; no conversion or cache copy.",
            "predicted_movement": "Retain the prior local consumer reduction while producer bytes and all global Triton work remain unchanged.",
            "falsifier": "Unsupported E5M2 dispatch, numerical/state/padding failure, incomplete 50/10 routing, or conservative whole-request bound below 3%.",
        },
        "frozen_inputs": [row(path) for path in frozen],
        "candidate_files": [row(path) for path in candidate],
    }
    atomic(ROOT / "SOURCE_BINDING.json", binding)
    admitted = candidate[:-1] + [
        ROOT / "inputs/stack/fp8_qkv_paired_runner.py",
        ROOT / "inputs/stack/install_endpoint_patch.py",
        ROOT / "inputs/stack/proven_v0513_endpoint_entrypoint.py",
        ROOT / "inputs/stack/qkv_epilogue_discriminator.py",
        ROOT / "inputs/stack/stack_sitecustomize.py",
        ROOT / "SOURCE_BINDING.json",
    ]
    atomic(
        ROOT / "GPU_INPUT_MANIFEST.json",
        {"schema_version": 1, "files": [row(path) for path in admitted]},
    )
    print(json.dumps({"pass": True, "source_binding_sha256": digest(ROOT / "SOURCE_BINDING.json")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
