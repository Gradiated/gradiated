#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import sys
import threading
import time


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path(
    "/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius"
)
DETACHED_OWNER = PROJECT / "inputs/detached-owner"
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
NAME = "gemma4_h200_ngram_variable_draft_compaction"
BENCH = "h200-ngram-verifier-e00kcm9nfhwt7e7gbc"
REMOTE = "/home/glmrunner/gemma4-ngram-variable-compaction"
DEADLINE = dt.datetime(2026, 7, 24, 16, 45, tzinfo=dt.timezone.utc)
REPAIR_DEADLINE = dt.datetime(2026, 7, 24, 16, 30, tzinfo=dt.timezone.utc)
HOURLY_USD = 2.46


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(
    args: list[str], **kwargs: object
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, text=True, capture_output=True, check=False, **kwargs
    )


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(16 * 1024 * 1024):
            value.update(block)
    return value.hexdigest()


def pool(*args: str) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "python3",
            "-m",
            "grad_research.gpu_pool",
            "--lab",
            str(LAB),
            *args,
        ],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
    )


def ssh(ip: str, command: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "ssh",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            "ServerAliveInterval=20",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            f"glmrunner@{ip}",
            command,
        ],
        timeout=timeout,
    )


def scp_to(
    ip: str, source: pathlib.Path, target: str, timeout: int = 300
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "scp",
            "-p",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            "ServerAliveInterval=20",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            str(source),
            f"glmrunner@{ip}:{target}",
        ],
        timeout=timeout,
    )


def scp_from(
    ip: str, source: str, target: pathlib.Path, timeout: int = 300
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "scp",
            "-p",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            "ServerAliveInterval=20",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            f"glmrunner@{ip}:{source}",
            str(target),
        ],
        timeout=timeout,
    )


def instance_ip() -> str:
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = (
        benches[BENCH]
        if isinstance(benches, dict)
        else next(row for row in benches if row["id"] == BENCH)
    )
    sys.path.insert(0, str(NEBIUS))
    from placement_control import extract_public_ipv4, get_instance

    value = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
    if not value:
        raise RuntimeError("typed_provider_boundary:no_public_ip")
    return value


def verify_packet() -> dict:
    packet = json.loads((PROJECT / "IMMUTABLE_PACKET.json").read_text())
    for row in packet["files"]:
        path = PROJECT / row["path"]
        if path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
            raise RuntimeError(f"typed_local_integrity_boundary:{row['path']}")
    checkpoint = packet["checkpoint"]
    for name, expected in checkpoint["files"].items():
        if digest(PROJECT / checkpoint["local_path"] / name) != expected:
            raise RuntimeError(f"typed_local_checkpoint_boundary:{name}")
    return packet


def verify_remote_checkpoint(ip: str, packet: dict, artifact: pathlib.Path) -> None:
    checkpoint = packet["checkpoint"]
    rows = []
    for name, expected in checkpoint["files"].items():
        path = pathlib.PurePosixPath(checkpoint["resident_path"]) / name
        result = ssh(
            ip,
            f"test -f {shlex.quote(str(path))} && "
            f"printf '%s ' \"$(stat -c %s {shlex.quote(str(path))})\" && "
            f"sha256sum {shlex.quote(str(path))}",
            timeout=1800,
        )
        if result.returncode or expected not in result.stdout:
            (artifact / f"checkpoint-{name}.stderr").write_text(result.stderr)
            raise RuntimeError(f"typed_remote_checkpoint_boundary:{name}")
        rows.append({"name": name, "sha256": expected, "stdout": result.stdout})
        atomic(artifact / "checkpoint-progress.json", rows)
    atomic(artifact / "CHECKPOINT_TERMINAL.json", {"pass": True, "files": rows})


def stage(ip: str, artifact: pathlib.Path) -> None:
    result = ssh(ip, f"install -d {REMOTE}/input {REMOTE}/artifacts {REMOTE}/cache")
    if result.returncode:
        raise RuntimeError("typed_staging_boundary:remote_root")
    files = [
        PROJECT / "inputs/compaction-source-packet.tar.gz",
        PROJECT / "inputs/control-runtime-snapshot.tar.gz",
        PROJECT / "variable_decode_lm_head.py",
        PROJECT / "sitecustomize.py",
        PROJECT / "remote_experiment.py",
        DETACHED_OWNER,
    ]
    rows = []
    for source in files:
        target_name = (
            "detached-owner" if source == DETACHED_OWNER else source.name
        )
        target = f"{REMOTE}/input/{target_name}"
        expected = digest(source)
        size = source.stat().st_size
        match = ssh(
            ip,
            f"test -f {shlex.quote(target)} && "
            f"test \"$(stat -c %s {shlex.quote(target)})\" = {size} && "
            f"test \"$(sha256sum {shlex.quote(target)} | cut -d' ' -f1)\" = {expected}",
        )
        if match.returncode:
            partial = f"{target}.{expected}.part"
            transfer = scp_to(ip, source, partial)
            if transfer.returncode:
                (artifact / f"{target_name}.scp.stderr").write_text(transfer.stderr)
                raise RuntimeError(f"typed_staging_boundary:{target_name}")
            finalize = ssh(
                ip,
                f"test \"$(stat -c %s {shlex.quote(partial)})\" = {size} && "
                f"test \"$(sha256sum {shlex.quote(partial)} | cut -d' ' -f1)\" = {expected} && "
                f"chmod 0444 {shlex.quote(partial)} && "
                f"mv -f {shlex.quote(partial)} {shlex.quote(target)}",
            )
            if finalize.returncode:
                raise RuntimeError(f"typed_staging_finalize_boundary:{target_name}")
        rows.append(
            {"name": target_name, "bytes": size, "sha256": expected}
        )
    ssh(ip, f"chmod 0555 {REMOTE}/input/detached-owner")
    atomic(artifact / "STAGING_TERMINAL.json", {"pass": True, "files": rows})


def launch_remote(ip: str, artifact: pathlib.Path) -> None:
    command = (
        f"{REMOTE}/input/detached-owner start "
        f"--state {REMOTE}/WORKER_STATE.json "
        f"--log {REMOTE}/WORKER.log "
        f"--cwd {REMOTE} -- python3 {REMOTE}/input/remote_experiment.py"
    )
    result = ssh(ip, command)
    (artifact / "launch.stdout").write_text(result.stdout)
    (artifact / "launch.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("typed_remote_launch_boundary")


def retrieve(ip: str, artifact: pathlib.Path) -> None:
    pack = ssh(
        ip,
        f"tar -C {REMOTE} -czf {REMOTE}/retrieved.tar.gz "
        "artifacts WORKER.log WORKER_STATE.json",
        timeout=900,
    )
    (artifact / "pack.stdout").write_text(pack.stdout)
    (artifact / "pack.stderr").write_text(pack.stderr)
    if pack.returncode:
        raise RuntimeError("typed_retrieval_boundary:pack")
    result = scp_from(ip, f"{REMOTE}/retrieved.tar.gz", artifact / "retrieved.tar.gz", 900)
    if result.returncode:
        (artifact / "retrieve.stderr").write_text(result.stderr)
        raise RuntimeError("typed_retrieval_boundary:transfer")


def remote_status(ip: str) -> tuple[bool, bool]:
    terminal = ssh(ip, f"test -f {REMOTE}/artifacts/TERMINAL.json")
    status = ssh(
        ip,
        f"{REMOTE}/input/detached-owner status --state {REMOTE}/WORKER_STATE.json",
    )
    return terminal.returncode == 0, status.returncode == 0


def wait_repair(ip: str, artifact: pathlib.Path, diagnostic: str) -> bool:
    ready = {
        "schema_version": 1,
        "at_utc": utc_now(),
        "diagnostic": diagnostic,
        "repair_deadline_utc": REPAIR_DEADLINE.isoformat(),
        "bench_retained": True,
    }
    atomic(PROJECT / "REPAIR_READY.json", ready)
    while dt.datetime.now(dt.timezone.utc) < REPAIR_DEADLINE:
        request = PROJECT / "REPAIR_REQUEST.json"
        if request.exists():
            value = json.loads(request.read_text())
            request.replace(artifact / f"REPAIR_REQUEST-{int(time.time())}.json")
            if value.get("action") == "relaunch":
                stage(ip, artifact)
                launch_remote(ip, artifact)
                (PROJECT / "REPAIR_READY.json").unlink(missing_ok=True)
                return True
        time.sleep(15)
    return False


def release(artifact: pathlib.Path, condition: str, contents: dict) -> None:
    contents_path = artifact / "resident-contents.json"
    atomic(contents_path, contents)
    result = pool(
        "release",
        "--project",
        NAME,
        "--condition",
        condition,
        "--contents",
        str(contents_path),
    )
    (artifact / "release.stdout").write_text(result.stdout)
    (artifact / "release.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("typed_pool_boundary:release")


def main() -> int:
    run_id = dt.datetime.now(dt.timezone.utc).strftime("variable-compaction-%Y%m%dt%H%M%SZ")
    artifact = PROJECT / "artifacts" / run_id
    artifact.mkdir(parents=True, exist_ok=False)
    packet = verify_packet()
    claim = pool(
        "claim",
        "--project",
        NAME,
        "--bench",
        BENCH,
        "--lease-seconds",
        "900",
    )
    (artifact / "claim.stdout").write_text(claim.stdout)
    (artifact / "claim.stderr").write_text(claim.stderr)
    if claim.returncode:
        raise RuntimeError("typed_pool_boundary:claim")
    claimed_at = time.monotonic()
    stop_heartbeat = threading.Event()

    def heartbeat() -> None:
        while not stop_heartbeat.wait(60):
            result = pool("heartbeat", "--project", NAME)
            atomic(
                artifact / "heartbeat.json",
                {
                    "at_utc": utc_now(),
                    "returncode": result.returncode,
                    "stderr": result.stderr,
                },
            )

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    condition = "maintenance"
    contents: dict = {}
    try:
        ip = instance_ip()
        identity = ssh(
            ip,
            "hostname; nvidia-smi --query-gpu=name,uuid,memory.used "
            "--format=csv,noheader; sudo docker ps --format '{{.Names}} {{.Status}}'",
        )
        (artifact / "remote-identity.stdout").write_text(identity.stdout)
        (artifact / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_remote_boundary:identity")
        verify_remote_checkpoint(ip, packet, artifact)
        stage(ip, artifact)
        launch_remote(ip, artifact)

        while dt.datetime.now(dt.timezone.utc) < DEADLINE:
            terminal, live = remote_status(ip)
            if terminal:
                retrieve(ip, artifact)
                condition = "ready"
                contents = {
                    "project": NAME,
                    "result": "scientific_terminal_retrieved",
                    "artifacts": str(artifact.relative_to(PROJECT)),
                    "image": packet["base"]["image"],
                    "checkpoint": packet["checkpoint"]["resident_path"],
                    "runtime": "Pinned SGLang v0.5.13 variable NGRAM compaction packet executed.",
                    "server_state": "No experiment server remains; image, exact checkpoint, JIT and runtime caches retained.",
                }
                break
            if not live:
                retrieve(ip, artifact)
                if wait_repair(ip, artifact, "remote_worker_exited_without_terminal"):
                    continue
                contents = {
                    "project": NAME,
                    "result": "repair_deadline_without_scientific_terminal",
                    "artifacts": str(artifact.relative_to(PROJECT)),
                    "server_state": "Remote diagnostic retrieved; guest requires director disposition.",
                }
                break
            time.sleep(30)
        else:
            retrieve(ip, artifact)
            contents = {
                "project": NAME,
                "result": "absolute_deadline",
                "artifacts": str(artifact.relative_to(PROJECT)),
                "server_state": "Absolute project deadline reached after diagnostic retrieval.",
            }
        exposure = (time.monotonic() - claimed_at) * HOURLY_USD / 3600
        atomic(
            artifact / "OWNER_TERMINAL.json",
            {
                "schema_version": 1,
                "condition": condition,
                "actual_spend_usd": exposure,
                "completed_at_utc": utc_now(),
                "contents": contents,
            },
        )
        release(artifact, condition, contents)
        return 0
    except Exception as exc:
        exposure = (time.monotonic() - claimed_at) * HOURLY_USD / 3600
        atomic(
            artifact / "OWNER_FAILURE.json",
            {
                "schema_version": 1,
                "at_utc": utc_now(),
                "actual_spend_usd": exposure,
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        raise
    finally:
        stop_heartbeat.set()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
