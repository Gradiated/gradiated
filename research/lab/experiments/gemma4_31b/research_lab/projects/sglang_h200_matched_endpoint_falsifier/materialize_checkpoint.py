#!/usr/bin/env python3
"""Materialize and verify the immutable Gemma checkpoint without provider state."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


MODEL = "google/gemma-4-31B-it"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
FILES = {
    "config.json": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    "tokenizer.json": "cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f",
    "tokenizer_config.json": "90c3a3ba5bf53818383a58e1a776cbcacd2a038d4812eaa373e1522f2d06f3df",
    "chat_template.jinja": "ae53464bf3be25802b3a5b37def7fd89667067d7577049b3b2d74c4d8de4c6d4",
    "processor_config.json": "32bdf45d2ad4cc29a0822ddd157a182de76644f0419a6228d151495256e9813c",
    "model.safetensors.index.json": None,
    "model-00001-of-00002.safetensors": "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa",
    "model-00002-of-00002.safetensors": "018912220f559f7025d60333e0996183cd538aa77ad6f4988a89ce47be681f10",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bind_identities(project: Path, start_packet: Path, prefix_packet: Path, output: Path) -> dict[str, object]:
    start = json.loads(start_packet.read_text())
    prefix = json.loads(prefix_packet.read_text())
    brief = (project / "PROJECT.md").read_text()
    identities = start["identities"]
    checks = {
        "start_model": identities["model"] == f"{MODEL}@{REVISION}",
        "brief_model_revision": f"{MODEL}@{REVISION}" in brief,
        "brief_sglang_image": identities["sglang"]["image_manifest"] in brief,
        "brief_vllm_image": identities["vllm_control"]["image"] in brief,
        "prefix_model": prefix["identities"]["model"] == f"{MODEL}@{REVISION}",
        "prefix_runtime": prefix["identities"]["runtime"] == identities["vllm_control"]["runtime_source"],
        "metadata_hashes": all(
            FILES[name] == digest.removeprefix("sha256:")
            for name, digest in identities["model_files"].items()
        ),
    }
    result = {
        "schema_version": 1,
        "classification": "identity_assertion",
        "timestamp_utc": utc_now(),
        "project_sha256": sha256(project / "PROJECT.md"),
        "start_packet_sha256": sha256(start_packet),
        "prefix_packet_sha256": sha256(prefix_packet),
        "checks": checks,
        "pass": all(checks.values()),
    }
    atomic_json(output, result)
    return result


def download(path: Path, filename: str, deadline: float) -> None:
    if time.time() >= deadline:
        raise TimeoutError("checkpoint deadline reached before download")
    target = path / filename
    if target.exists():
        return
    partial = target.with_suffix(target.suffix + ".partial")
    url = f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{filename}"
    command = [
        "curl", "--fail", "--location", "--retry", "3", "--retry-all-errors",
        "--continue-at", "-", "--output", str(partial), url,
    ]
    timeout = max(1, int(deadline - time.time()))
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"download failed for {filename}: curl exit {result.returncode}")
    partial.replace(target)


def safetensors_header_valid(path: Path) -> bool:
    with path.open("rb") as handle:
        header_length = int.from_bytes(handle.read(8), "little")
        if not 2 <= header_length <= 256 * 1024 * 1024:
            return False
        return isinstance(json.loads(handle.read(header_length)), dict)


def run(args: argparse.Namespace) -> int:
    terminal = args.artifact_root / "CHECKPOINT_TERMINAL.json"
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    started = time.time()
    deadline = started + args.deadline_seconds
    identity = bind_identities(args.project, args.start_packet, args.prefix_packet, args.artifact_root / "IDENTITY_ASSERTION.json")
    if not identity["pass"]:
        atomic_json(terminal, {"classification": "identity_assertion_failed", "pass": False, "finished_at_utc": utc_now()})
        return 1
    model_root = args.artifact_root / "checkpoint"
    model_root.mkdir(exist_ok=True)
    try:
        for filename in FILES:
            download(model_root, filename, deadline)
        rows = []
        for filename, expected in FILES.items():
            path = model_root / filename
            observed = sha256(path)
            if expected and observed != expected:
                raise RuntimeError(f"sha256 mismatch for {filename}")
            rows.append({"path": filename, "bytes": path.stat().st_size, "sha256": observed})
        index = json.loads((model_root / "model.safetensors.index.json").read_text())
        weight_files = set(index.get("weight_map", {}).values())
        if weight_files != {"model-00001-of-00002.safetensors", "model-00002-of-00002.safetensors"}:
            raise RuntimeError("model index does not bind the expected two shards")
        if not all(safetensors_header_valid(model_root / filename) for filename in weight_files):
            raise RuntimeError("invalid safetensors header")
        if sum(row["bytes"] for row in rows) > 90 * 1024**3:
            raise RuntimeError("project-local 90 GiB storage cap exceeded")
        atomic_json(terminal, {
            "schema_version": 1,
            "classification": "checkpoint_materialized_verified",
            "pass": True,
            "model": MODEL,
            "revision": REVISION,
            "checkpoint_root": str(model_root),
            "files": rows,
            "identity_assertion": str(args.artifact_root / "IDENTITY_ASSERTION.json"),
            "elapsed_seconds": round(time.time() - started, 3),
            "finished_at_utc": utc_now(),
        })
        return 0
    except Exception as error:
        atomic_json(terminal, {
            "schema_version": 1,
            "classification": "checkpoint_materialization_failure",
            "pass": False,
            "error_type": type(error).__name__,
            "message": str(error),
            "elapsed_seconds": round(time.time() - started, 3),
            "finished_at_utc": utc_now(),
        })
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--start-packet", type=Path, required=True)
    parser.add_argument("--prefix-packet", type=Path, required=True)
    parser.add_argument("--deadline-seconds", type=int, default=4200)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
