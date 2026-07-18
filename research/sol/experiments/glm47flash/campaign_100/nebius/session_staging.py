#!/usr/bin/env python3
"""Resumable, content-bound checkpoint staging for retained GPU sessions."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import shlex
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Callable


from placement_control import SSH_USER, ssh_base
from stock_control import run_ssh


class StagingError(RuntimeError):
    pass


LOCAL_INTEGRITY_MARKER = ".campaign-local-integrity-v1.json"
REMOTE_STAGING_MARKER = ".campaign-staging-contract-v1"


@dataclass(frozen=True)
class CheckpointFile:
    path: str
    bytes: int


@dataclass(frozen=True)
class RemoteCheckpointState:
    sizes: dict[str, int]
    marker_manifest_match: bool
    staging_manifest_match: bool = False


@dataclass(frozen=True)
class TransferPlan:
    files: tuple[CheckpointFile, ...]
    total_bytes: int
    reusable_bytes: int
    marker_manifest_match: bool

    @property
    def transfer_bytes(self) -> int:
        return self.total_bytes - self.reusable_bytes


@dataclass(frozen=True)
class TransferResult:
    total_bytes: int
    reusable_bytes: int
    scheduled_bytes: int
    files_total: int
    files_reused: int
    files_scheduled: int
    attempts: int
    marker_manifest_match: bool
    elapsed_seconds: float


def checkpoint_files(model_dir: Path) -> tuple[CheckpointFile, ...]:
    referenced = set()
    for line in (model_dir / "model-files.sha256").read_text().splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            raise StagingError("checkpoint checksum manifest row is invalid")
        referenced.add(fields[1].lstrip("*"))
    files = []
    for path in sorted(model_dir.rglob("*")):
        if (
            not path.is_file()
            or ".cache" in path.relative_to(model_dir).parts
            or (path.name == LOCAL_INTEGRITY_MARKER and path.name not in referenced)
        ):
            continue
        relative = path.relative_to(model_dir)
        if len(relative.parts) != 1:
            raise StagingError(f"checkpoint staging currently requires flat files: {relative}")
        files.append(CheckpointFile(str(relative), path.stat().st_size))
    if not files or not any(row.path == "model-files.sha256" for row in files):
        raise StagingError("checkpoint lacks model-files.sha256")
    transferred = {row.path for row in files}
    excluded = sorted(referenced - transferred)
    if excluded:
        raise StagingError(
            "checkpoint checksum manifest references files excluded from transfer: "
            + ", ".join(excluded)
        )
    return tuple(files)


def validate_local_files_cached(
    model_dir: Path,
    rows: list[dict[str, object]],
    *,
    persist_marker: bool = True,
) -> dict[str, object]:
    """Validate payload bytes and report success, cache reuse, and transfer inventory."""
    if model_dir.is_symlink():
        raise StagingError("local checkpoint root must not be a symlink")
    normalized = []
    metadata = []
    for row in rows:
        try:
            relative = Path(str(row["path"]))
            expected_bytes = int(row["bytes"])
            expected_sha256 = str(row["sha256"])
        except (KeyError, TypeError, ValueError) as error:
            raise StagingError("local checkpoint manifest row is invalid") from error
        if relative.is_absolute() or ".." in relative.parts:
            raise StagingError(f"local checkpoint manifest path escapes root: {relative}")
        path = model_dir / relative
        if path.is_symlink():
            raise StagingError(f"local checkpoint file must not be a symlink: {relative}")
        if not path.is_file() or path.stat().st_size != expected_bytes:
            raise StagingError(f"local checkpoint file missing or truncated: {relative}")
        stat = path.stat()
        with path.open("rb") as handle:
            head = handle.read(64 * 1024)
            if stat.st_size > len(head):
                handle.seek(max(0, stat.st_size - 64 * 1024))
                tail = handle.read(64 * 1024)
            else:
                tail = b""
        normalized.append({"path": str(relative), "bytes": expected_bytes, "sha256": expected_sha256})
        metadata.append(
            {
                "path": str(relative),
                "bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "ctime_ns": stat.st_ctime_ns,
                "inode": stat.st_ino,
                "device": stat.st_dev,
                "sample_sha256": hashlib.sha256(head + tail).hexdigest(),
            }
        )
    contract_sha256 = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    metadata_sha256 = hashlib.sha256(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    marker_path = model_dir / LOCAL_INTEGRITY_MARKER
    try:
        marker = json.loads(marker_path.read_text())
    except (OSError, json.JSONDecodeError):
        marker = None

    def validation_result(marker_reused: bool) -> dict[str, object]:
        transfer_files = checkpoint_files(model_dir)
        return {
            "pass": True,
            "marker_reused": marker_reused,
            "payload_files_total": len(normalized),
            "payload_bytes": sum(int(row["bytes"]) for row in normalized),
            "transfer_files_total": len(transfer_files),
            "transfer_bytes": sum(row.bytes for row in transfer_files),
            "transfer_files": [asdict(row) for row in transfer_files],
        }
    if persist_marker and marker == {"contract_sha256": contract_sha256, "metadata_sha256": metadata_sha256}:
        return validation_result(True)
    for row in normalized:
        digest = hashlib.sha256()
        with (model_dir / row["path"]).open("rb") as handle:
            for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != row["sha256"]:
            raise StagingError(f"local checkpoint checksum mismatch: {row['path']}")
    if persist_marker:
        temporary = marker_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"contract_sha256": contract_sha256, "metadata_sha256": metadata_sha256},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        temporary.replace(marker_path)
    return validation_result(False)


def checksum_manifest_sha256(model_dir: Path) -> str:
    return hashlib.sha256((model_dir / "model-files.sha256").read_bytes()).hexdigest()


def transfer_timeout_seconds(
    total_bytes: int,
    *,
    throughput_floor_bytes_per_second: int = 20_000_000,
    fixed_overhead_seconds: int = 180,
    minimum_seconds: int = 900,
    maximum_seconds: int = 3600,
) -> int:
    if total_bytes <= 0 or throughput_floor_bytes_per_second <= 0:
        raise StagingError("transfer size and throughput floor must be positive")
    estimate = math.ceil(total_bytes / throughput_floor_bytes_per_second) + fixed_overhead_seconds
    return min(maximum_seconds, max(minimum_seconds, estimate))


def plan_transfer(
    files: tuple[CheckpointFile, ...],
    remote: RemoteCheckpointState,
) -> TransferPlan:
    missing = tuple(row for row in files if remote.sizes.get(row.path) != row.bytes)
    total = sum(row.bytes for row in files)
    return TransferPlan(
        files=missing,
        total_bytes=total,
        reusable_bytes=total - sum(row.bytes for row in missing),
        marker_manifest_match=remote.marker_manifest_match,
    )


def build_remote_state_command(
    target: str,
    files: tuple[CheckpointFile, ...],
    manifest_sha256: str,
) -> list[str]:
    payload = base64.b64encode(
        json.dumps([asdict(row) for row in files], separators=(",", ":")).encode()
    ).decode()
    code = """import base64,json,sys
from pathlib import Path
root=Path(sys.argv[1])
rows=json.loads(base64.b64decode(sys.argv[2]))
sizes={row['path']:(root/row['path']).stat().st_size for row in rows if (root/row['path']).is_file()}
marker=root/'.campaign-integrity-v1'
staging=root/'.campaign-staging-contract-v1'
expected='manifest_sha256='+sys.argv[3]
matched=marker.is_file() and expected in marker.read_text().splitlines()
staging_matched=staging.is_file() and expected in staging.read_text().splitlines()
print(json.dumps({'sizes':sizes,'marker_manifest_match':matched,'staging_manifest_match':staging_matched},sort_keys=True))
"""
    return ["python3", "-c", code, target, payload, manifest_sha256]


def query_remote_state(
    ip: str,
    key: Path,
    target: str,
    files: tuple[CheckpointFile, ...],
    manifest_sha256: str,
) -> RemoteCheckpointState:
    parent = str(PurePosixPath(target).parent)
    if parent in {".", "/"}:
        raise StagingError("remote checkpoint target must have a dedicated session parent")
    prepare = run_ssh(
        ip,
        key,
        f"sudo install -d -o {SSH_USER} -g {SSH_USER} "
        f"{shlex.quote(parent)} {shlex.quote(target)}",
        timeout=30,
    )
    if prepare.returncode:
        raise StagingError("remote checkpoint directory preparation failed")
    result = run_ssh(
        ip,
        key,
        build_remote_state_command(target, files, manifest_sha256),
        timeout=30,
    )
    if result.returncode:
        raise StagingError("remote checkpoint state query failed")
    try:
        payload = json.loads(result.stdout)
        sizes = {str(path): int(size) for path, size in payload["sizes"].items()}
        marker_match = payload["marker_manifest_match"] is True
        staging_match = payload["staging_manifest_match"] is True
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise StagingError("remote checkpoint state response is invalid") from error
    return RemoteCheckpointState(
        sizes=sizes,
        marker_manifest_match=marker_match,
        staging_manifest_match=staging_match,
    )


def initialize_remote_staging(ip: str, key: Path, target: str, manifest_sha256: str) -> RemoteCheckpointState:
    parent = str(PurePosixPath(target).parent)
    if parent in {".", "/"}:
        raise StagingError("remote checkpoint target must have a dedicated session parent")
    quoted_parent = shlex.quote(parent)
    quoted_target = shlex.quote(target)
    quoted_marker = shlex.quote(f"{target}/{REMOTE_STAGING_MARKER}")
    command = (
        f"sudo install -d -o {SSH_USER} -g {SSH_USER} {quoted_parent} && "
        f"sudo rm -rf {quoted_target} && "
        f"sudo install -d -o {SSH_USER} -g {SSH_USER} {quoted_target} && "
        f"printf '%s\\n' {shlex.quote('manifest_sha256=' + manifest_sha256)} > {quoted_marker}"
    )
    result = run_ssh(ip, key, command, timeout=30)
    if result.returncode:
        raise StagingError("remote checkpoint staging initialization failed")
    return RemoteCheckpointState(sizes={}, marker_manifest_match=False, staging_manifest_match=True)


def build_scp_command(ip: str, key: Path, model_dir: Path, files: tuple[CheckpointFile, ...], target: str) -> list[str]:
    return [
        "scp",
        "-p",
        "-i",
        str(key),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts",
        *(str(model_dir / row.path) for row in files),
        f"{SSH_USER}@{ip}:{target}/",
    ]


def transfer_checkpoint(
    ip: str,
    key: Path,
    model_dir: Path,
    target: str,
    *,
    timeout_seconds: int | None = None,
    state_query: Callable[[str, Path, str, tuple[CheckpointFile, ...], str], RemoteCheckpointState] = query_remote_state,
    staging_initializer: Callable[[str, Path, str, str], RemoteCheckpointState] = initialize_remote_staging,
    command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> TransferResult:
    files = checkpoint_files(model_dir)
    manifest_sha = checksum_manifest_sha256(model_dir)
    timeout_seconds = timeout_seconds or transfer_timeout_seconds(sum(row.bytes for row in files))
    if timeout_seconds <= 0:
        raise StagingError("checkpoint transfer timeout must be positive")
    started = time.monotonic()
    deadline = started + timeout_seconds
    initial = state_query(ip, key, target, files, manifest_sha)
    if not initial.marker_manifest_match and not initial.staging_manifest_match:
        initial = staging_initializer(ip, key, target, manifest_sha)
    first_plan = plan_transfer(files, initial)
    if not first_plan.files:
        return TransferResult(
            total_bytes=first_plan.total_bytes,
            reusable_bytes=first_plan.reusable_bytes,
            scheduled_bytes=0,
            files_total=len(files),
            files_reused=len(files),
            files_scheduled=0,
            attempts=0,
            marker_manifest_match=initial.marker_manifest_match,
            elapsed_seconds=time.monotonic() - started,
        )
    attempts = 0
    scheduled_bytes = 0
    plan = first_plan
    current = initial
    while plan.files and attempts < 2:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise StagingError("checkpoint transfer exceeded its size-derived timeout")
        attempts += 1
        scheduled_bytes += sum(row.bytes for row in plan.files)
        try:
            result = command_runner(
                build_scp_command(ip, key, model_dir, plan.files, target),
                capture_output=True,
                text=True,
                timeout=remaining,
            )
        except subprocess.TimeoutExpired as error:
            raise StagingError("checkpoint transfer exceeded its size-derived timeout; completed files remain reusable") from error
        current = state_query(ip, key, target, files, manifest_sha)
        plan = plan_transfer(files, current)
        if result.returncode == 0 and not plan.files:
            break
        if attempts == 2:
            raise StagingError(
                f"checkpoint transfer incomplete after retry: {len(plan.files)} files and {plan.transfer_bytes} bytes remain"
            )
    elapsed = time.monotonic() - started
    final_plan = plan_transfer(files, current)
    if final_plan.files:
        raise StagingError("checkpoint transfer returned with incomplete files")
    files_reused = len(files) - len(first_plan.files)
    return TransferResult(
        total_bytes=first_plan.total_bytes,
        reusable_bytes=first_plan.reusable_bytes,
        scheduled_bytes=scheduled_bytes,
        files_total=len(files),
        files_reused=files_reused,
        files_scheduled=len(first_plan.files),
        attempts=attempts,
        marker_manifest_match=current.marker_manifest_match,
        elapsed_seconds=elapsed,
    )
