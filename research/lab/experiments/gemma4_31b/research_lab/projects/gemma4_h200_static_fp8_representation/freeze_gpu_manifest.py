#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


HERE = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    producer = json.loads((HERE / "PRODUCER_MANIFEST.json").read_text())
    roles = {
        "static_fp8_consumer.py": "exact H200 serialized-representation consumer",
        "remote_static_fp8_component.sh": "remote component launcher",
    }
    rows = list(producer["files"])
    for name, role in roles.items():
        path = HERE / name
        rows.append(
            {
                "path": name,
                "remote_name": name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "role": role,
            }
        )
    value = {
        "schema_version": 1,
        "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "runtime_image": "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6",
        "producer_manifest_sha256": sha256(HERE / "PRODUCER_MANIFEST.json"),
        "files": rows,
    }
    path = HERE / "GPU_INPUT_MANIFEST.json"
    temporary = path.with_suffix(".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
