#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import struct
from typing import BinaryIO


KEYS = (
    "model.language_model.layers.0.mlp.gate_proj.weight",
    "model.language_model.layers.0.mlp.up_proj.weight",
)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_range(
    source: BinaryIO, destination: BinaryIO, start: int, length: int
) -> None:
    source.seek(start)
    remaining = length
    while remaining:
        block = source.read(min(8 << 20, remaining))
        if not block:
            raise RuntimeError("unexpected_source_eof")
        destination.write(block)
        remaining -= len(block)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"output_exists:{args.output}")

    with args.source.open("rb") as source:
        source_header_bytes = struct.unpack("<Q", source.read(8))[0]
        source_header = json.loads(source.read(source_header_bytes))
    data_start = 8 + source_header_bytes
    missing = set(KEYS) - source_header.keys()
    if missing:
        raise RuntimeError(f"missing_source_keys:{sorted(missing)}")

    output_header: dict[str, object] = {
        "__metadata__": {
            "format": "pt",
            "purpose": "gemma4_h200_operation_overlap_discriminator",
        }
    }
    output_offset = 0
    ranges = []
    for key in KEYS:
        source_row = source_header[key]
        source_left, source_right = source_row["data_offsets"]
        length = source_right - source_left
        output_header[key] = {
            "dtype": source_row["dtype"],
            "shape": source_row["shape"],
            "data_offsets": [output_offset, output_offset + length],
        }
        ranges.append((data_start + source_left, length))
        output_offset += length

    encoded_header = json.dumps(
        output_header, separators=(",", ":"), sort_keys=True
    ).encode()
    encoded_header += b" " * ((8 - len(encoded_header) % 8) % 8)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    with args.source.open("rb") as source, temporary.open("wb") as destination:
        destination.write(struct.pack("<Q", len(encoded_header)))
        destination.write(encoded_header)
        for start, length in ranges:
            copy_range(source, destination, start, length)
        destination.flush()
        os.fsync(destination.fileno())
    os.replace(temporary, args.output)
    args.output.chmod(0o444)

    manifest = {
        "schema_version": 1,
        "source": {
            "path": str(args.source.resolve()),
            "sha256": sha256(args.source),
        },
        "snapshot": {
            "path": str(args.output.resolve()),
            "sha256": sha256(args.output),
            "bytes": args.output.stat().st_size,
            "mode": "0444",
            "keys": {
                key: {
                    "dtype": output_header[key]["dtype"],
                    "shape": output_header[key]["shape"],
                }
                for key in KEYS
            },
        },
        "byte_semantics": "Tensor payload bytes copied without conversion; only the safetensors header and selected-key offsets were rewritten.",
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    temporary_manifest = args.manifest.with_suffix(".part")
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    os.replace(temporary_manifest, args.manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
