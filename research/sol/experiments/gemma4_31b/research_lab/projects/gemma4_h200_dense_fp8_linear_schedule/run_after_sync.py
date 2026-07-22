#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parent.parent
BASE_MANIFEST = PROJECT / "GPU_INPUT_MANIFEST.json"
BASE_PROGRAM = PROJECT / "PROGRAM.tar.gz"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def bench(args: argparse.Namespace) -> dict[str, object]:
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    if isinstance(benches, dict):
        return benches[args.bench]
    return next(row for row in benches if row["id"] == args.bench)


def prepare(args: argparse.Namespace) -> pathlib.Path:
    prepared = args.artifact_root / "prepared"
    prepared.mkdir(parents=True, exist_ok=False)
    terminal_bytes = args.sync_terminal.read_bytes()
    terminal = json.loads(terminal_bytes)
    sync_status = json.loads(args.sync_status.read_text())
    terminal_path = prepared / "SYNC_TERMINAL.json"
    terminal_path.write_bytes(terminal_bytes)
    terminal_sha256 = hashlib.sha256(terminal_bytes).hexdigest()
    binding = {
        "schema_version": 1,
        "source_project": "gemma4_h200_decode_sync_graph_elimination",
        "source_terminal": str(args.sync_terminal),
        "sha256": terminal_sha256,
        "classification": terminal.get("classification"),
        "pass": terminal.get("pass") is True,
        "immutable_binding_sha256": sync_status.get("immutable_binding_sha256"),
        "materialized_before_dense_claim": True,
    }
    atomic(prepared / "SYNC_BINDING.json", binding)

    base_manifest = json.loads(BASE_MANIFEST.read_text())
    base_program = next(row for row in base_manifest["programs"] if row["path"] == "PROGRAM.tar.gz")
    if BASE_PROGRAM.stat().st_size != base_program["bytes"] or sha256(BASE_PROGRAM) != base_program["sha256"]:
        raise RuntimeError("base_program_archive_identity_mismatch")
    with tempfile.TemporaryDirectory(dir=args.artifact_root) as temporary_directory:
        tree = pathlib.Path(temporary_directory) / "program"
        tree.mkdir()
        with tarfile.open(BASE_PROGRAM, "r:gz") as archive:
            archive.extractall(tree, filter="data")
        shutil.copy2(PROJECT / "consume_component.py", tree / "consume_component.py")
        shutil.copy2(PROJECT / "remote_streamk.sh", tree / "remote_streamk.sh")
        sync_root = tree / "inputs" / "sync"
        sync_root.mkdir(parents=True)
        shutil.copy2(terminal_path, sync_root / "TERMINAL.json")
        shutil.copy2(prepared / "SYNC_BINDING.json", sync_root / "BINDING.json")
        archive_part = prepared / "PROGRAM.tar.gz.part"
        with tarfile.open(archive_part, "w:gz", compresslevel=6) as archive:
            for child in sorted(tree.iterdir()):
                archive.add(child, arcname=child.name, recursive=True)
        program = prepared / "PROGRAM.tar.gz"
        os.replace(archive_part, program)

    manifest = json.loads(BASE_MANIFEST.read_text())
    for row in manifest["programs"]:
        if row["path"] == "PROGRAM.tar.gz":
            row.update(
                path=str(program.relative_to(PROJECT)),
                bytes=program.stat().st_size,
                sha256=sha256(program),
            )
    manifest["synchronization_result"] = {
        "terminal_path": str(terminal_path.relative_to(PROJECT)),
        "binding_path": str((prepared / "SYNC_BINDING.json").relative_to(PROJECT)),
        "sha256": terminal_sha256,
    }
    derived_manifest = prepared / "GPU_INPUT_MANIFEST.json"
    atomic(derived_manifest, manifest)
    atomic(
        args.artifact_root / "QUEUE_STATE.json",
        {
            "schema_version": 1,
            "state": "prepared_before_claim",
            "sync_terminal_sha256": terminal_sha256,
            "program_sha256": sha256(program),
            "manifest": str(derived_manifest),
        },
    )
    return derived_manifest


def main(args: argparse.Namespace) -> int:
    args.artifact_root.mkdir(parents=True, exist_ok=False)
    while time.time() < args.absolute_deadline_epoch:
        row = bench(args)
        sync_done = args.sync_terminal.is_file()
        available = row.get("status") == "available" and row.get("claim") is None
        if sync_done and available:
            break
        if row.get("status") == "maintenance":
            atomic(
                args.artifact_root / "QUEUE_TERMINAL.json",
                {"classification": "typed_dependency_boundary", "message": "retained_bench_released_to_maintenance"},
            )
            return 2
        time.sleep(15)
    else:
        atomic(
            args.artifact_root / "QUEUE_TERMINAL.json",
            {"classification": "typed_dependency_boundary", "message": "synchronization_release_deadline_expired"},
        )
        return 2

    manifest = prepare(args)
    owner_root = args.artifact_root / "owner"
    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT / "run_bench_owner.py"),
            "--bench",
            args.bench,
            "--artifact-root",
            str(owner_root),
            "--absolute-deadline-epoch",
            str(args.absolute_deadline_epoch),
            "--input-manifest",
            str(manifest),
        ],
        text=True,
        capture_output=True,
    )
    (args.artifact_root / "owner.stdout").write_text(completed.stdout)
    (args.artifact_root / "owner.stderr").write_text(completed.stderr)
    atomic(
        args.artifact_root / "QUEUE_TERMINAL.json",
        {
            "classification": "owner_returned",
            "owner_returncode": completed.returncode,
            "owner_terminal": str(owner_root / "TERMINAL.json"),
        },
    )
    return completed.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--sync-terminal", type=pathlib.Path, required=True)
    parser.add_argument("--sync-status", type=pathlib.Path, required=True)
    parser.add_argument("--absolute-deadline-epoch", type=int, required=True)
    raise SystemExit(main(parser.parse_args()))
