#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
FILES = [
    (HERE / "mirrored_ring_kv.py", "mirrored_ring_kv.py"),
    (HERE / "mirrored_component.py", "mirrored_component.py"),
    (HERE / "endpoint_mirrored_ring_patch.py", "endpoint_mirrored_ring_patch.py"),
    (HERE / "ring_ownership.py", "ring_ownership.py"),
    (HERE / "sitecustomize.py", "sitecustomize.py"),
    (HERE / "remote_component.sh", "remote_component.sh"),
    (HERE / "remote_endpoint.sh", "remote_endpoint.sh"),
    (HERE / "inputs/bound/control_ring_kv.py", "control_ring_kv.py"),
    (
        HERE / "inputs/bound/ring_e5m2_flash_ops.so",
        "ring_e5m2_flash_ops.so",
    ),
    (
        HERE / "inputs/bound/persisted_ring_endpoint.json",
        "persisted_ring_endpoint.json",
    ),
    *(
        (path, path.name)
        for path in sorted((HERE / "inputs/endpoint_stack").glob("*.py"))
    ),
]


def main() -> None:
    rows = []
    for path, remote_name in FILES:
        rows.append(
            {
                "path": str(path.relative_to(HERE)),
                "remote_name": remote_name,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    value = {
        "schema_version": 1,
        "project": "gemma4_h200_mirrored_ring_e5m2_local_fa3",
        "stage": "actual_producer_consumer_then_conditional_exact_c32",
        "files": sorted(rows, key=lambda row: row["remote_name"]),
    }
    (HERE / "GPU_INPUT_MANIFEST.json").write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
