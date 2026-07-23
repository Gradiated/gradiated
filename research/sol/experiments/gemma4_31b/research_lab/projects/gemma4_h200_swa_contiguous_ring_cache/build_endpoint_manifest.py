#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
PATHS = [
    HERE / "ring_kv.py",
    HERE / "endpoint_ring_patch.py",
    HERE / "sitecustomize.py",
    HERE / "remote_endpoint_pair.sh",
    HERE / "CANDIDATE_SEMANTIC_REJECT.json",
    *(HERE / "inputs" / "endpoint_stack").glob("*.py"),
]


def main() -> None:
    rows = []
    for path in sorted(PATHS):
        rows.append(
            {
                "path": str(path.relative_to(HERE)),
                "remote_name": path.name,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    (HERE / "ENDPOINT_GPU_MANIFEST.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project": "gemma4_h200_swa_contiguous_ring_cache",
                "stage": "conditional_exact_c32_pair",
                "files": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
