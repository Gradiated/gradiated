from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import struct


KEYS = (
    "model.language_model.layers.0.input_layernorm.weight",
    "model.language_model.layers.0.pre_feedforward_layernorm.weight",
    "model.language_model.layers.0.self_attn.q_proj.weight",
    "model.language_model.layers.0.self_attn.k_proj.weight",
    "model.language_model.layers.0.self_attn.v_proj.weight",
    "model.language_model.layers.0.mlp.gate_proj.weight",
    "model.language_model.layers.0.mlp.up_proj.weight",
)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    args = parser.parse_args()

    with args.source.open("rb") as source:
        header_size = struct.unpack("<Q", source.read(8))[0]
        source_header = json.loads(source.read(header_size))
        source_data_start = 8 + header_size
        entries = {key: source_header[key] for key in KEYS}
        cursor = 0
        output_header = {}
        for key in KEYS:
            entry = entries[key]
            begin, end = entry["data_offsets"]
            size = end - begin
            output_header[key] = {
                "dtype": entry["dtype"],
                "shape": entry["shape"],
                "data_offsets": [cursor, cursor + size],
            }
            cursor += size
        header = json.dumps(output_header, separators=(",", ":"), sort_keys=True).encode()
        header += b" " * ((8 - len(header) % 8) % 8)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".part")
        with temporary.open("wb") as destination:
            destination.write(struct.pack("<Q", len(header)))
            destination.write(header)
            for key in KEYS:
                begin, end = entries[key]["data_offsets"]
                source.seek(source_data_start + begin)
                remaining = end - begin
                while remaining:
                    chunk = source.read(min(16 * 1024 * 1024, remaining))
                    if not chunk:
                        raise RuntimeError(f"unexpected EOF while copying {key}")
                    destination.write(chunk)
                    remaining -= len(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, args.output)

    value = {
        "schema_version": 1,
        "source_path": str(args.source),
        "source_sha256": sha256(args.source),
        "output_path": str(args.output),
        "output_sha256": sha256(args.output),
        "output_bytes": args.output.stat().st_size,
        "keys": list(KEYS),
        "payload_bytes": cursor,
    }
    manifest_temporary = args.manifest.with_suffix(args.manifest.suffix + ".part")
    manifest_temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(manifest_temporary, args.manifest)
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
