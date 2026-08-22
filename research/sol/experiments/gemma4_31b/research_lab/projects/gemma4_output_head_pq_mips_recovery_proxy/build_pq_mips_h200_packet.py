#!/usr/bin/env python3
"""Materialize and validate the immutable project-local H200 source packet."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parent
WEIGHT_KEY = "model.language_model.embed_tokens.weight"
SMALL_INPUT_NAMES = {
    "capture": "hidden_states.pt",
    "capture_terminal": "EXACT_CAPTURE_TERMINAL.json",
    "checkpoint_index": "model.safetensors.index.json",
    "config": "config.json",
    "lowrank_terminal": "LOSSLESS_LOWRANK_RESIDUAL_DISJOINT_TERMINAL.json",
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as stream:
        stream.write(canonical(value))
        temporary = Path(stream.name)
    json.loads(temporary.read_text())
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def raw_tensor_sha256(tensor, torch) -> str:
    value = tensor.contiguous().view(torch.uint8)
    return hashlib.sha256(value.numpy().tobytes()).hexdigest()


def link_or_copy(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if (
            destination.stat().st_size == source.stat().st_size
            and sha256_file(destination) == sha256_file(source)
        ):
            return "existing_verified"
        raise RuntimeError(f"conflicting_destination:{destination}")
    try:
        os.link(source, destination)
        return "read_only_source_hardlink_view"
    except OSError:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
        try:
            shutil.copyfile(source, temporary)
            if sha256_file(temporary) != sha256_file(source):
                raise RuntimeError(f"copy_hash_mismatch:{destination}")
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return "atomic_byte_copy"


def materialize_weight(source: Path, destination: Path, expected_tensor_hash: str) -> dict[str, Any]:
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file

    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        with safe_open(source, framework="pt", device="cpu") as handle:
            if WEIGHT_KEY not in handle.keys():
                raise RuntimeError("tied_weight_key_missing")
            tensor = handle.get_tensor(WEIGHT_KEY)
        if (
            tuple(tensor.shape) != (262144, 5376)
            or tensor.dtype != torch.bfloat16
            or raw_tensor_sha256(tensor, torch) != expected_tensor_hash
        ):
            raise RuntimeError("source_tied_weight_identity_mismatch")
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
        try:
            save_file({WEIGHT_KEY: tensor}, temporary)
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()
    with safe_open(destination, framework="pt", device="cpu") as handle:
        tensor = handle.get_tensor(WEIGHT_KEY)
    observed_tensor_hash = raw_tensor_sha256(tensor, torch)
    if (
        tuple(tensor.shape) != (262144, 5376)
        or tensor.dtype != torch.bfloat16
        or observed_tensor_hash != expected_tensor_hash
    ):
        raise RuntimeError("materialized_tied_weight_identity_mismatch")
    return {
        "path": str(destination.relative_to(PROJECT)),
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "tensor_sha256": observed_tensor_hash,
        "tensor_shape": [262144, 5376],
        "tensor_dtype": "torch.bfloat16",
        "weight_key": WEIGHT_KEY,
        "materialization": "project_local_single_tensor_safetensors",
    }


def deterministic_tar(root: Path, manifest: Path, archive: Path, files: list[dict[str, Any]]) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=archive.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with tarfile.open(temporary, "w", format=tarfile.PAX_FORMAT) as bundle:
            members = [("PACKET_MANIFEST.json", manifest)]
            members.extend((row["path"], root / row["path"]) for row in files)
            for name, source in members:
                info = bundle.gettarinfo(str(source), arcname=name)
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mtime = 0
                with source.open("rb") as payload:
                    bundle.addfile(info, payload)
        temporary.replace(archive)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default="/root/workspace/.agents/runtime/offset-head-torch/bin/python3")
    args = parser.parse_args()
    contract_path = PROJECT / "EXPERIMENT_CONTRACT.json"
    contract = json.loads(contract_path.read_text())
    packet_root = PROJECT / "inputs" / "h200-pq-mips"
    payload_root = packet_root / "payload"
    payload_root.mkdir(parents=True, exist_ok=True)
    materializations: dict[str, str] = {}
    for key, name in SMALL_INPUT_NAMES.items():
        source = (PROJECT / contract["inputs"][f"{key}_path"]).resolve()
        if sha256_file(source) != contract["inputs"][f"{key}_sha256"]:
            raise RuntimeError(f"source_hash_mismatch:{key}")
        materializations[key] = link_or_copy(source, payload_root / name)
    for source_name in (
        "EXPERIMENT_CONTRACT.json",
        "pq_mips_h200_worker.py",
        "pq_mips_h200_owner.py",
    ):
        source = PROJECT / source_name
        shutil.copyfile(source, payload_root / source_name)
    weight_source = (PROJECT / contract["inputs"]["weight_shard_path"]).resolve()
    if sha256_file(weight_source) != contract["inputs"]["weight_shard_sha256"]:
        raise RuntimeError("source_weight_shard_hash_mismatch")
    weight = materialize_weight(
        weight_source,
        packet_root / "tied_output_weight.safetensors",
        contract["inputs"]["tied_weight_tensor_sha256"],
    )
    self_test = subprocess.run(
        [args.python, str(PROJECT / "pq_mips_h200_worker.py"), "--self-test"],
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if self_test.returncode:
        raise RuntimeError(f"worker_self_test_failed:{self_test.stderr}")
    self_test_value = json.loads(self_test.stdout)
    files = []
    for source in sorted(
        path
        for path in payload_root.rglob("*")
        if path.is_file() and path.name != "PACKET_MANIFEST.json"
    ):
        files.append(
            {
                "path": str(source.relative_to(payload_root)),
                "bytes": source.stat().st_size,
                "sha256": sha256_file(source),
            }
        )
    packet_identity = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest_path = payload_root / "PACKET_MANIFEST.json"
    manifest = {
        "schema_version": 1,
        "packet_identity_sha256": packet_identity,
        "files": files,
        "weight_snapshot": weight,
        "frozen_science": {
            "model": contract["stock_control"]["model"],
            "revision": contract["stock_control"]["revision"],
            "subspaces": contract["candidate"]["subspaces"],
            "dimensions_per_subspace": contract["candidate"]["dimensions_per_subspace"],
            "codebook_rows": contract["candidate"]["codebook_rows"],
            "shortlist_sizes": contract["candidate"]["shortlist_sizes"],
            "batch_selection": contract["workload"]["batch_selection"],
            "traffic_accounting": contract["baseline_measurement"]["attribution"],
        },
        "worker_command": [
            "python3",
            "/work/input/pq_mips_h200_worker.py",
            "--contract",
            "/work/input/EXPERIMENT_CONTRACT.json",
            "--inputs",
            "/work/input",
            "--weight",
            "/work/weight/tied_output_weight.safetensors",
            "--output",
            "/work/output",
        ],
    }
    atomic_json(manifest_path, manifest)
    archive = PROJECT / "artifacts" / f"pq-mips-h200-packet-{packet_identity}.tar"
    deterministic_tar(payload_root, manifest_path, archive, files)
    with tarfile.open(archive, "r") as bundle:
        observed_members = sorted(item.name for item in bundle if item.isfile())
        expected_members = sorted(["PACKET_MANIFEST.json", *[row["path"] for row in files]])
        if observed_members != expected_members:
            raise RuntimeError("packet_archive_member_mismatch")
        for row in files:
            stream = bundle.extractfile(row["path"])
            payload = stream.read() if stream else b""
            if len(payload) != row["bytes"] or hashlib.sha256(payload).hexdigest() != row["sha256"]:
                raise RuntimeError(f"packet_archive_hash_mismatch:{row['path']}")
    validation = {
        "schema_version": 1,
        "classification": "offline_vectorized_producer_packet_valid",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "worker_self_test": self_test_value,
        "packet_identity_sha256": packet_identity,
        "packet_manifest": str(manifest_path.relative_to(PROJECT)),
        "packet_manifest_sha256": sha256_file(manifest_path),
        "packet_archive": str(archive.relative_to(PROJECT)),
        "packet_archive_sha256": sha256_file(archive),
        "weight_snapshot": weight,
        "input_materializations": materializations,
        "prohibitions_observed": {
            "gpu_pool_called": False,
            "ssh_called": False,
            "docker_called": False,
            "cuda_called": False,
            "endpoint_traffic": False,
            "provider_api_called": False,
            "held_out_scoring_run": False,
            "other_project_mutated": False,
        },
    }
    atomic_json(PROJECT / "artifacts" / "PQ_MIPS_H200_OFFLINE_VALIDATION.json", validation)
    print(json.dumps(validation, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
