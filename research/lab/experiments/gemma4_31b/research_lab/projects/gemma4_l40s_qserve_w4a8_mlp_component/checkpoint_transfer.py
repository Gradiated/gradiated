#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import time


PROJECT = pathlib.Path(__file__).resolve().parent
SOURCE = PROJECT / "inputs/checkpoint"
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def ssh(ip: str, command: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "ssh",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={KNOWN}",
            f"glmrunner@{ip}",
            command,
        ],
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def transfer(
    ip: str,
    remote: str,
    row: dict[str, object],
    artifacts: pathlib.Path,
) -> dict[str, object]:
    name = str(row["name"])
    expected = str(row["sha256"])
    source = SOURCE / name
    final = f"{remote}/checkpoint/{name}"
    partial = f"{remote}/checkpoint/.{name}.{expected}.part"
    matched = ssh(
        ip,
        f"test -f {shlex.quote(final)} && "
        f"test \"$(stat -c%s {shlex.quote(final)})\" = {row['bytes']} && "
        f"test \"$(sha256sum {shlex.quote(final)} | awk '{{print $1}}')\" "
        f"= {expected}",
        1800,
    )
    if matched.returncode == 0:
        return {
            **row,
            "status": "already_matched",
            "seconds": 0.0,
        }
    resumed = ssh(ip, f"test -f {shlex.quote(partial)}", 60).returncode == 0
    batch = artifacts / f".{name}.sftp"
    batch.write_text(
        f"put {'-a ' if resumed else ''}{shlex.quote(str(source))} "
        f"{shlex.quote(partial)}\n"
    )
    started = time.monotonic()
    result = subprocess.run(
        [
            "sftp",
            "-b",
            str(batch),
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={KNOWN}",
            f"glmrunner@{ip}",
        ],
        text=True,
        capture_output=True,
        timeout=7200,
    )
    (artifacts / f"{name}.sftp.stdout").write_text(result.stdout)
    (artifacts / f"{name}.sftp.stderr").write_text(result.stderr)
    seconds = time.monotonic() - started
    if result.returncode:
        raise RuntimeError(
            f"typed_transfer_boundary:sftp_failed:{name}:{result.stderr[-1000:]}"
        )
    finalized = ssh(
        ip,
        f"test \"$(stat -c%s {shlex.quote(partial)})\" = {row['bytes']} && "
        f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" "
        f"= {expected} && chmod 0444 {shlex.quote(partial)} && "
        f"mv {shlex.quote(partial)} {shlex.quote(final)}",
        1800,
    )
    if finalized.returncode:
        raise RuntimeError(
            f"typed_transfer_boundary:remote_finalize_failed:{name}:"
            f"{finalized.stderr[-1000:]}"
        )
    return {
        **row,
        "status": "resumed" if resumed else "transferred",
        "seconds": seconds,
        "bytes_per_second": int(row["bytes"]) / seconds,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", required=True)
    parser.add_argument("--remote-root", required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((PROJECT / "CHECKPOINT_MANIFEST.json").read_text())
    if sum(int(row["bytes"]) for row in manifest["files"]) != int(
        manifest["checkpoint_bytes"]
    ):
        raise RuntimeError("checkpoint_manifest_size_mismatch")
    for row in manifest["files"]:
        path = SOURCE / row["name"]
        if (
            not path.is_file()
            or path.stat().st_size != row["bytes"]
            or sha256(path) != row["sha256"]
        ):
            raise RuntimeError(f"project_local_checkpoint_mismatch:{row['name']}")
    prepared = ssh(
        args.ip,
        f"mkdir -p {shlex.quote(args.remote_root + '/checkpoint')}",
        60,
    )
    if prepared.returncode:
        raise RuntimeError("typed_transfer_boundary:remote_prepare_failed")
    weights = [
        row for row in manifest["files"] if row["name"].endswith(".safetensors")
    ]
    metadata = [row for row in manifest["files"] if row not in weights]
    outcomes: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        outcomes.extend(
            executor.map(
                lambda row: transfer(
                    args.ip,
                    args.remote_root,
                    row,
                    args.artifact_root,
                ),
                weights,
            )
        )
    for row in metadata:
        outcomes.append(
            transfer(args.ip, args.remote_root, row, args.artifact_root)
        )
    atomic(
        args.artifact_root / "CHECKPOINT_TRANSFER_TERMINAL.json",
        {
            "schema_version": 1,
            "pass": True,
            "checkpoint_bytes": manifest["checkpoint_bytes"],
            "files": outcomes,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
