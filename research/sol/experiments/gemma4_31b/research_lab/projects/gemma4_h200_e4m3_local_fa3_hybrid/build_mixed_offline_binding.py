#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEPENDENCY_ROOT = ROOT / "inputs/mixed_dependency"
OUTPUT = ROOT / "MIXED_SOURCE_BINDING.json"
TERMINAL = (
    ROOT
    / "artifacts/mixed-offline-binding-20260723"
    / "OFFLINE_BINDING_TERMINAL.json"
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def row(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def main() -> int:
    manifest_path = DEPENDENCY_ROOT / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    for expected in manifest["files"]:
        path = DEPENDENCY_ROOT / expected["name"]
        if digest(path) != expected["sha256"]:
            raise RuntimeError(f"dependency_snapshot_mismatch:{path.name}")

    candidate_paths = [
        ROOT / "gemma4_layer_hybrid_backend.py",
        ROOT / "install_hybrid_backend.py",
        ROOT / "sitecustomize.py",
        ROOT / "e4m3_fa3_component.py",
        ROOT / "remote_component.sh",
        ROOT / "remote_hybrid_candidate.sh",
        ROOT / "run_hybrid_owner.py",
    ]
    local_ids = [index for index in range(60) if (index + 1) % 6]
    global_ids = list(range(5, 60, 6))
    binding = {
        "schema_version": 1,
        "status": "mixed_offline_binding_pass",
        "runtime": {
            "release": "SGLang v0.5.13",
            "source_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "image": "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6",
            "accelerator": "nvidia-h200-sxm",
        },
        "geometry": {
            "page_size": 1,
            "local": {
                "layer_ids": local_ids,
                "q_heads": 32,
                "kv_heads": 16,
                "head_dim": 256,
                "window_tokens": 1024,
                "kv_dtype": "torch.float8_e4m3fn",
                "control": "TritonAttnBackend",
                "candidate": "FlashAttentionBackend/fa3",
            },
            "global": {
                "layer_ids": global_ids,
                "q_heads": 32,
                "kv_heads": 4,
                "head_dim": 512,
                "kv_dtype": "torch.float8_e5m2",
                "backend": "TritonAttnBackend",
            },
        },
        "producer_consumer_contract": {
            "producer": "dependency mixed_kv_patch.install_mixed_kv -> SWAKVPool.set_kv_buffer -> per-pool MHATokenToKVPool.set_kv_buffer",
            "local_control": "TritonAttnBackend.forward_decode -> decode_attention_fwd",
            "local_candidate": "FlashAttentionBackend.forward_decode -> sgl_kernel.flash_attn_with_kvcache(ver=3)",
            "global_unchanged": "TritonAttnBackend forward_extend/forward_decode with the full E5M2 sub-pool",
            "scale_convention": "unchanged per-layer RadixAttention k_scale/v_scale",
            "slot_mapping": "full slots for global; full_to_swa_index_mapping for local",
        },
        "physical_hypothesis": {
            "change": "Replace only the local E4M3 paged Triton consumer with stock Hopper FA3; preserve the global E5M2 paged pool and Triton consumer.",
            "prediction": "The local decode boundary falls enough to recover the measured mixed-KV comparator penalty and beat 0.6743258590313417 s/request.",
            "falsifier": "Numerical mismatch, local/global dtype or slot-path mismatch, component regression, insufficient projected recovery, or exact c32 regression.",
            "local_wall_fraction": 0.1531203203096733,
        },
        "dependency_manifest": row(manifest_path),
        "dependency_files": [row(DEPENDENCY_ROOT / item["name"]) for item in manifest["files"]],
        "candidate_files": [row(path) for path in candidate_paths],
        "offline_validation": {
            "router": "Pinned-image 50 local / 10 global dispatch and dual metadata lifecycle passed.",
            "installer": "Pinned-image mixed-constructor patch parsed and preserved global E5M2 after local FA3 construction.",
            "cuda_execution_equivalent": False,
            "reason": "Target execution belongs to the post-dependency claimed H200 component.",
        },
    }
    atomic(OUTPUT, binding)
    terminal = {
        "schema_version": 1,
        "status": "terminal",
        "classification": "mixed_exact_source_binding_complete",
        "pass": True,
        "source_binding": OUTPUT.name,
        "source_binding_sha256": digest(OUTPUT),
        "scientific_invocation_started": False,
        "candidate_cuda_invocation_started": False,
        "provider_spend_usd": 0.0,
    }
    atomic(TERMINAL, terminal)
    print(json.dumps(terminal, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
