#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


HERE = Path(__file__).resolve().parent
FILES = (
    "ring_kv.py",
    "ring_component.py",
    "remote_component.sh",
    "inputs/source/decode_attention.v0.5.13.py",
    "inputs/source/memory_pool.v0.5.13.py",
    "inputs/source/swa_memory_pool.v0.5.13.py",
    "inputs/source/triton_backend.v0.5.13.py",
    "inputs/production_config.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


rows = []
for relative in FILES:
    path = HERE / relative
    rows.append(
        {
            "path": relative,
            "remote_name": relative.replace("/", "__"),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    )
value = {
    "schema_version": 1,
    "project": "gemma4_h200_swa_contiguous_ring_cache",
    "component": rows,
}
target = HERE / "GPU_INPUT_MANIFEST.json"
temporary = target.with_suffix(".json.part")
temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
os.replace(temporary, target)
print(json.dumps(value, indent=2, sort_keys=True))
