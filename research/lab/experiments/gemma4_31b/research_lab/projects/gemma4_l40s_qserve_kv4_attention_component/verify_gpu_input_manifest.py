#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="KV4_ATTENTION_GPU_INPUT_MANIFEST.json")
    args = parser.parse_args()
    manifest_path = ROOT / args.manifest
    manifest = json.loads(manifest_path.read_text())
    assert manifest["schema_version"] == 1
    assert manifest["required_compute_capability"] == "8.9"
    assert manifest["scientific_invocations"] == {
        "component": 1,
        "counter_replays": 4,
        "sweep": False,
        "endpoint": False,
        "checkpoint": False,
    }
    for relative, expected in manifest["files"].items():
        path = ROOT / relative
        assert path.is_file(), path
        actual = sha256(path)
        assert actual == expected, f"{relative}: {actual} != {expected}"
    continuation = json.loads((ROOT / "EXACT_GEMMA_KV4_CONTINUATION.json").read_text())
    spec = json.loads((ROOT / "EXPERIMENT_SPEC.json").read_text())
    assert continuation["fixed_geometry"]["local"]["head_dim"] == 256
    assert continuation["fixed_geometry"]["global"]["head_dim"] == 512
    assert spec["candidate"]["schedule"]["block_n"] == 32
    assert spec["candidate"]["schedule"]["max_splits"] == 8
    assert spec["measurement"]["iterations"] == 50
    print(json.dumps({
        "valid": True,
        "manifest": str(manifest_path.relative_to(ROOT)),
        "manifest_sha256": sha256(manifest_path),
        "file_count": len(manifest["files"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
