#!/usr/bin/env python3
"""Create the admitted, deterministic AWQ W4 performance-proxy checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
SOURCE = HERE.parent / "sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint"
SOURCE_TERMINAL = SOURCE.parent / "CHECKPOINT_TERMINAL.json"
TERMINAL = HERE / "W4_CHECKPOINT_TERMINAL.json"


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    args = parser.parse_args()
    started = time.time()
    if not os.environ.get("INVOCATION_ID") or os.environ.get("SYSTEMD_EXEC_PID") != str(os.getpid()):
        raise RuntimeError("durable user-systemd owner required")
    root = args.artifact_root.resolve()
    output = root / "checkpoint"
    try:
        source_terminal = json.loads(SOURCE_TERMINAL.read_text())
        if source_terminal.get("pass") is not True or not SOURCE.is_dir():
            raise RuntimeError("bound source checkpoint terminal is not passing")
        if time.time() >= args.deadline_epoch:
            raise TimeoutError("local materialization deadline expired before launch")
        root.mkdir(parents=True, exist_ok=True)
        if output.exists():
            attempt = 1
            while (root / f"checkpoint-repair-{attempt}").exists():
                attempt += 1
            output = root / f"checkpoint-repair-{attempt}"
        spec = HERE / "w4_quantize_in_container.py"
        command = [
            "docker", "run", "--rm", "--network=none", "--ipc=host",
            "-v", f"{SOURCE}:/source:ro", "-v", f"{root}:/output",
            "-v", f"{spec}:/input/w4_quantize_in_container.py:ro",
            "--entrypoint", "python3", IMAGE, "/input/w4_quantize_in_container.py",
            "--source", "/source", "--output", f"/output/{output.name}",
            "--deadline-epoch", str(args.deadline_epoch),
        ]
        (root / "COMMAND.json").write_text(json.dumps(command, indent=2) + "\n")
        process = subprocess.run(command, text=True, capture_output=True, timeout=max(60, int(args.deadline_epoch - time.time()) + 60))
        (root / "quantizer.stdout.log").write_text(process.stdout[-16000:])
        (root / "quantizer.stderr.log").write_text(process.stderr[-16000:])
        internal = root / "QUANTIZER_TERMINAL.json"
        if process.returncode != 0 or not internal.is_file():
            raise RuntimeError(f"container quantizer failed returncode={process.returncode}")
        result = json.loads(internal.read_text())
        if result.get("pass") is not True:
            raise RuntimeError("container quantizer returned typed failure")
        if output.stat().st_size if output.is_file() else False:
            raise RuntimeError("checkpoint output is not a directory")
        copied = []
        for source_file in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "processor_config.json"):
            source_path = SOURCE / source_file
            target = output / source_file
            if not target.is_file() or sha256(source_path) != sha256(target):
                raise RuntimeError(f"metadata copy mismatch: {source_file}")
            copied.append({"path": source_file, "sha256": sha256(target), "bytes": target.stat().st_size})
        terminal = {
            "schema_version": 1,
            "classification": "w4_checkpoint_materialized_verified",
            "pass": True,
            "performance_proxy_only": True,
            "source_terminal_sha256": sha256(SOURCE_TERMINAL),
            "artifact_root": str(root),
            "checkpoint_root": str(output),
            "quantizer_terminal_sha256": sha256(internal),
            "metadata_copies": copied,
            "elapsed_seconds": round(time.time() - started, 3),
        }
        atomic_json(TERMINAL, terminal)
        return 0
    except Exception as error:
        atomic_json(TERMINAL, {
            "schema_version": 1,
            "classification": "w4_checkpoint_materialization_failure",
            "pass": False,
            "error_type": type(error).__name__,
            "message": str(error),
            "artifact_root": str(root),
            "elapsed_seconds": round(time.time() - started, 3),
        })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
