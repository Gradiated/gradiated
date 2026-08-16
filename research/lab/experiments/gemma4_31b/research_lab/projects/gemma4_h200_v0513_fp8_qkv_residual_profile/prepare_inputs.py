#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil


PROJECT = pathlib.Path(__file__).resolve().parent
DEFAULT_CHECKPOINT = (
    PROJECT.parent
    / "gemma4_h200_inmemory_fp8_endpoint/inputs/checkpoint"
)
CHECKPOINT_FILES = (
    ("config.json", 4621, "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1"),
    ("tokenizer.json", 32169626, "cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f"),
    ("tokenizer_config.json", 2095, "90c3a3ba5bf53818383a58e1a776cbcacd2a038d4812eaa373e1522f2d06f3df"),
    ("chat_template.jinja", 18683, "ae53464bf3be25802b3a5b37def7fd89667067d7577049b3b2d74c4d8de4c6d4"),
    ("processor_config.json", 1689, "32bdf45d2ad4cc29a0822ddd157a182de76644f0419a6228d151495256e9813c"),
    ("model.safetensors.index.json", 120246, "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2"),
    ("model-00001-of-00002.safetensors", 49784788364, "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa"),
    ("model-00002-of-00002.safetensors", 12761549884, "018912220f559f7025d60333e0996183cd538aa77ad6f4988a89ce47be681f10"),
)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def immutable_copy(source: pathlib.Path, destination: pathlib.Path, expected: str) -> None:
    if destination.is_file() and sha256(destination) == expected:
        destination.chmod(0o444)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{expected}.part")
    if temporary.exists():
        temporary.unlink()
    with source.open("rb") as reader, temporary.open("xb") as writer:
        shutil.copyfileobj(reader, writer, 16 * 1024 * 1024)
        writer.flush()
        os.fsync(writer.fileno())
    if sha256(temporary) != expected:
        temporary.unlink()
        raise RuntimeError(f"snapshot_hash_mismatch:{source}")
    temporary.chmod(0o444)
    os.replace(temporary, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint-source", type=pathlib.Path, default=DEFAULT_CHECKPOINT)
    args = parser.parse_args()

    bindings_path = PROJECT / "BINDINGS.json"
    bindings = json.loads(bindings_path.read_text())
    if bindings.get("schema_version") != 1:
        raise RuntimeError("unsupported_bindings_schema")
    if bindings["model"]["checkpoint_index_sha256"] != CHECKPOINT_FILES[5][2]:
        raise RuntimeError("checkpoint_index_binding_mismatch")
    if bindings["runtime"] != {
        "release": "sglang v0.5.13",
        "commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
        "image_linux_amd64": "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6",
    }:
        raise RuntimeError("runtime_binding_mismatch")
    if bindings["workload"] != {
        "concurrency": 32,
        "requests": 32,
        "prompt_tokens_per_request": 4214,
        "completion_tokens_per_request": 358,
        "cached_prompt_tokens_total": 17120,
        "fresh_prompt_tokens_total": 117728,
    }:
        raise RuntimeError("workload_binding_mismatch")

    bound_specs = {
        "authoritative_qkv_terminal": bindings["authoritative_qkv_terminal"],
        **bindings["source_bytes"],
    }
    bound_rows = []
    for label, spec in bound_specs.items():
        source = (PROJECT / spec["path"]).resolve()
        expected = spec["sha256"]
        if not source.is_file() or sha256(source) != expected:
            raise RuntimeError(f"binding_mismatch:{label}:{source}")
        suffix = "".join(source.suffixes)
        destination = PROJECT / "inputs/bound" / expected / f"{label}{suffix}"
        immutable_copy(source, destination, expected)
        bound_rows.append(
            {
                "label": label,
                "path": str(destination.relative_to(PROJECT)),
                "bytes": destination.stat().st_size,
                "sha256": expected,
                "source_provenance": str(source),
            }
        )

    checkpoint_rows = []
    for name, size, expected in CHECKPOINT_FILES:
        source = args.checkpoint_source / name
        if not source.is_file() or source.stat().st_size != size:
            raise RuntimeError(f"checkpoint_source_missing_or_wrong_size:{source}")
        destination = PROJECT / "inputs/checkpoint" / name
        immutable_copy(source, destination, expected)
        checkpoint_rows.append(
            {
                "path": str(destination.relative_to(PROJECT)),
                "name": name,
                "bytes": size,
                "sha256": expected,
                "source_provenance": str(source.resolve()),
            }
        )

    manifest = {
        "schema_version": 1,
        "pass": True,
        "bindings_path": "BINDINGS.json",
        "bindings_sha256": sha256(bindings_path),
        "model": bindings["model"],
        "runtime": bindings["runtime"],
        "representation": bindings["representation"],
        "workload": bindings["workload"],
        "economics": bindings["economics"],
        "bound_files": bound_rows,
        "checkpoint_files": checkpoint_rows,
        "checkpoint_bytes": sum(row["bytes"] for row in checkpoint_rows),
    }
    atomic_json(PROJECT / "INPUT_MANIFEST.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
