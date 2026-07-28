#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
FILES = [
    "remote_combined_candidate.sh",
    "inputs/stack/sitecustomize.py",
    "inputs/stack/endpoint_ring_patch.py",
    "inputs/stack/ring_kv.py",
    "inputs/stack/ring_ownership.py",
    "inputs/stack/padded_noop_probe.py",
    "inputs/stack/fp8_qkv_paired_runner.py",
    "inputs/stack/proven_v0513_endpoint_entrypoint.py",
    "inputs/stack/install_endpoint_patch.py",
    "inputs/stack/qkv_epilogue_discriminator.py",
    "inputs/stack/attention_deferred_local_kv.py",
    "inputs/stack/host_min_new_tokens_gate.py",
    "inputs/stack/pinned_async_penalty_tokens.py",
    "inputs/stack/producer_fused_swa_translation.py",
    "inputs/stack/residual_intervention.py",
    "inputs/stack/PERSISTED_PADDED_NOOP_PROOF.json",
    "inputs/width/JOINT_NORM_SELECTION.json",
    "inputs/width/PERSISTED_WIDTH_ENDPOINT_TERMINAL.json",
]


def main() -> None:
    rows = []
    for name in FILES:
        path = HERE / name
        rows.append({
            "path": name,
            "remote_name": path.name,
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    (HERE / "GPU_INPUT_MANIFEST.json").write_text(json.dumps({"schema_version": 1, "files": rows}, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
