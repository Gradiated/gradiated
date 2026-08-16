#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
FILES = [
    (HERE / "ring_ownership.py", "ring_ownership.py"),
    (HERE / "ring_kv.py", "ring_kv.py"),
    (HERE / "padded_noop_probe.py", "padded_noop_probe.py"),
    (HERE / "endpoint_ring_patch.py", "endpoint_ring_patch.py"),
    (HERE / "sitecustomize.py", "sitecustomize.py"),
    (HERE / "remote_endpoint_pair.sh", "remote_endpoint_pair.sh"),
    (
        HERE / "artifacts" / "endpoint-evidence" / "control" / "TERMINAL.json",
        "persisted-control-terminal.json",
    ),
    (
        HERE / "artifacts" / "endpoint-evidence" / "PADDED_NOOP_PROOF.json",
        "persisted-padded-noop-proof.json",
    ),
    *(
        (path, path.name)
        for path in (HERE / "inputs" / "endpoint_stack").glob("*.py")
    ),
]


def main() -> None:
    rows = []
    for path, remote_name in sorted(FILES):
        rows.append(
            {
                "path": str(path.relative_to(HERE)),
                "remote_name": remote_name,
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
