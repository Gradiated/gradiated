#!/usr/bin/env python3
from __future__ import annotations

import gzip
import hashlib
import json
import os
import pathlib
import tarfile
from typing import Any


PROJECT = pathlib.Path(__file__).resolve().parent
MANIFEST = PROJECT / "EXACT_CONSUMER_GPU_INPUT_MANIFEST.json"
PACKET = PROJECT / "EXACT_CONSUMER_PACKET.tar.gz"
PACKET_DIGEST = PROJECT / "EXACT_CONSUMER_PACKET.sha256"
DATA_PACKET = PROJECT / "EXACT_CONSUMER_DATA.tar.gz"
DATA_PACKET_DIGEST = PROJECT / "EXACT_CONSUMER_DATA.sha256"
INPUT_ROOT = "inputs/exact_consumer"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def archive_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.mode = 0o555 if info.mode & 0o111 else 0o444
    return info


def write_archive(path: pathlib.Path, files: list[pathlib.Path]) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            mtime=0,
        ) as compressed:
            with tarfile.open(
                fileobj=compressed,
                mode="w",
                format=tarfile.PAX_FORMAT,
            ) as archive:
                for source in sorted(files):
                    archive.add(
                        source,
                        arcname=str(source.relative_to(PROJECT)),
                        recursive=False,
                        filter=archive_filter,
                    )
    os.replace(temporary, path)


def main() -> int:
    inputs = sorted(
        path
        for path in (PROJECT / INPUT_ROOT).rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and not path.name.endswith((".pyc", ".part"))
    )
    bindings = [
        PROJECT / "EXACT_CONSUMER_BINDING.json",
    ]
    files = bindings + inputs
    data_files = [
        path
        for path in inputs
        if path.relative_to(PROJECT / INPUT_ROOT).parts[0] == "producer"
    ]
    source_runner_files = bindings + [
        path for path in inputs if path not in data_files
    ]
    source = (
        PROJECT
        / INPUT_ROOT
        / "producer/layer0_mlp_awq-871a79d70b4fe23a.safetensors"
    )
    if source.is_symlink():
        raise RuntimeError("project_local_awq_source_must_not_be_symlink")
    if sha256(source) != (
        "871a79d70b4fe23a5b036a765a129556ff2b4a2affc86606e843dbae215e04f8"
    ):
        raise RuntimeError("project_local_awq_source_hash_mismatch")
    producer_terminal = json.loads(
        (
            PROJECT
            / INPUT_ROOT
            / "producer/layer0_exact_compute_v1/PREPARE_TERMINAL.json"
        ).read_text()
    )
    if not producer_terminal.get("pass"):
        raise RuntimeError("exact_producer_terminal_not_passing")
    manifest = {
        "schema_version": 1,
        "classification": "immutable_exact_awq_sm89_consumer_packet",
        "model": "google/gemma-4-31B-it",
        "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "accelerator": "nvidia-l40s",
        "architecture": "sm89",
        "fixed_schedule": {
            "cta": [32, 64, 128],
            "warp": [32, 32, 64],
            "warps": 4,
            "stages": 3,
            "group_size": 128,
            "partial_accumulation": "int32 group partial -> BF16 AWQ scale * FP16 token scale -> FP32 serial accumulation",
        },
        "source_awq_sha256": sha256(source),
        "producer_terminal_sha256": sha256(
            PROJECT
            / INPUT_ROOT
            / "producer/layer0_exact_compute_v1/PREPARE_TERMINAL.json"
        ),
        "files": {
            str(path.relative_to(PROJECT)): sha256(path)
            for path in sorted(files)
        },
    }
    atomic_json(MANIFEST, manifest)
    write_archive(PACKET, source_runner_files + [MANIFEST])
    write_archive(DATA_PACKET, data_files)
    packet_hash = sha256(PACKET)
    data_packet_hash = sha256(DATA_PACKET)
    PACKET_DIGEST.write_text(f"{packet_hash}  {PACKET.name}\n")
    DATA_PACKET_DIGEST.write_text(
        f"{data_packet_hash}  {DATA_PACKET.name}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
