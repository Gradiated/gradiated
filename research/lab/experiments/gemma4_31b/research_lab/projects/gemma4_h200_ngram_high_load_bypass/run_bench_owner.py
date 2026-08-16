#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading
import time


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY = Path("/root/workspace/research/factory/src")
NEBIUS = Path(
    "/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius"
)
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = Path("/root/.config/nebius/glm-campaign/known_hosts")
DETACHED_OWNER = Path("/root/workspace/research/factory/tools/detached-owner")
ARTIFACT_SNAPSHOT = Path(
    "/root/workspace/research/factory/tools/artifact-snapshot"
)
NAME = "gemma4_h200_ngram_high_load_bypass"
BENCH = "h200-ngram-verifier-e00kcm9nfhwt7e7gbc"
INSTANCE = "computeinstance-e00kcm9nfhwt7e7gbc"
REMOTE = "/home/glmrunner/gemma4-h200-ngram-high-load-bypass"
CHECKPOINT = (
    "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint"
)
PACKET = PROJECT / "REPAIR_PACKET.metrics-persistence.tar"
PACKET_SHA256 = "4a97181c49d3336687a22eb38299dd1d82834829b200b0d614a8d33fa43a0139"
LOCAL_STATE = PROJECT / "CONTROLLER_OWNER_REPAIR.json"
DEADLINE = dt.datetime(2026, 7, 25, 0, 50, tzinfo=dt.timezone.utc)
REPAIR_DEADLINE = dt.datetime(
    2026, 7, 25, 0, 44, tzinfo=dt.timezone.utc
)
HOURLY_USD = 2.46


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(args: list[str], **kwargs):
    return subprocess.run(
        args, text=True, capture_output=True, check=False, **kwargs
    )


def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(16 * 1024 * 1024):
            value.update(block)
    return value.hexdigest()


def pool(*args: str):
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


def ssh(ip: str, command: str, timeout: int = 60):
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


def scp_to(ip: str, source: Path, target: str, timeout: int = 600):
    return run(
        [
            "scp",
            "-p",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            str(source),
            f"glmrunner@{ip}:{target}",
        ],
        timeout=timeout,
    )


def scp_from(ip: str, source: str, target: Path, timeout: int = 900):
    return run(
        [
            "scp",
            "-p",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
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
    sys.path.insert(0, str(NEBIUS))
    from placement_control import extract_public_ipv4, get_instance

    value = extract_public_ipv4(get_instance(INSTANCE))
    if not value:
        raise RuntimeError("typed_provider_boundary:no_public_ip")
    return value


def claim() -> dt.datetime:
    result = pool("claim", "--project", NAME, "--bench", BENCH)
    if result.returncode:
        raise RuntimeError("typed_pool_boundary:claim:" + result.stderr)
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    value = inventory["benches"][BENCH]["claim"]["claimed_at"]
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def spend_since(claimed_at: dt.datetime, prior: float) -> float:
    seconds = max(
        0.0,
        (dt.datetime.now(dt.timezone.utc) - claimed_at).total_seconds(),
    )
    return prior + seconds / 3600 * HOURLY_USD


def update_status(active_session, summary: str, spend: float) -> None:
    path = PROJECT / "STATUS.json"
    value = json.loads(path.read_text())
    value["active_session"] = active_session
    value["summary"] = summary
    value["actual_spend_usd"] = spend
    atomic(path, value)


def stage(ip: str, packet: Path, remote_name: str) -> None:
    packet_sha = digest(packet)
    owner_sha = digest(DETACHED_OWNER)
    created = ssh(ip, f"mkdir -p {shlex.quote(REMOTE)}", 60)
    if created.returncode:
        raise RuntimeError("typed_staging_boundary:mkdir")
    for source, target, expected in (
        (packet, f"{REMOTE}/{remote_name}", packet_sha),
        (DETACHED_OWNER, f"{REMOTE}/detached-owner", owner_sha),
    ):
        matched = ssh(
            ip,
            f"test -f {shlex.quote(target)} && "
            f"test \"$(sha256sum {shlex.quote(target)} | cut -d' ' -f1)\" "
            f"= {expected}",
            120,
        )
        if matched.returncode:
            temporary = f"{target}.{expected}.part"
            copied = scp_to(ip, source, temporary)
            if copied.returncode:
                raise RuntimeError(
                    f"typed_staging_boundary:{source.name}:{copied.stderr}"
                )
            finalized = ssh(
                ip,
                f"test \"$(sha256sum {shlex.quote(temporary)} | cut -d' ' -f1)\" "
                f"= {expected} && mv -f {shlex.quote(temporary)} "
                f"{shlex.quote(target)}",
                180,
            )
            if finalized.returncode:
                raise RuntimeError(
                    f"typed_staging_verify_boundary:{source.name}"
                )
    extracted = ssh(
        ip,
        f"cd {shlex.quote(REMOTE)} && tar -xf {shlex.quote(remote_name)} "
        "&& chmod 0555 detached-owner remote_experiment.py",
        240,
    )
    if extracted.returncode:
        raise RuntimeError(
            "typed_staging_boundary:extract:" + extracted.stderr[-1000:]
        )


def launch_remote(ip: str, state_name: str) -> None:
    result = ssh(
        ip,
        f"cd {shlex.quote(REMOTE)} && ./detached-owner start "
        f"--state {shlex.quote(REMOTE + '/' + state_name)} "
        f"--log {shlex.quote(REMOTE + '/' + state_name.replace('.json', '.log'))} "
        f"--cwd {shlex.quote(REMOTE)} --unit-manager pid -- "
        "python3 remote_experiment.py",
        60,
    )
    if result.returncode:
        raise RuntimeError(
            "typed_remote_owner_boundary:launch:" + result.stderr[-1000:]
        )


def remote_state(ip: str, state_name: str) -> dict:
    result = ssh(
        ip,
        f"cd {shlex.quote(REMOTE)} && "
        f"./detached-owner status --state {shlex.quote(state_name)} "
        "2>/dev/null; "
        "test -f out/FINAL_TERMINAL.json && echo FINAL_PRESENT || true; "
        "test -f out/ATTEMPT_TERMINAL.json && echo ATTEMPT_PRESENT || true; "
        "cat out/INVOCATION_STATE.json 2>/dev/null || true",
        45,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "final": "FINAL_PRESENT" in result.stdout,
        "attempt": "ATTEMPT_PRESENT" in result.stdout,
        "owner_live": '"live": true' in result.stdout,
    }


def retrieve(ip: str, artifact: Path, state_name: str) -> Path:
    artifact.mkdir(parents=True, exist_ok=True)
    log_name = state_name.replace(".json", ".log")
    archive_name = f"compact-{int(time.time())}.tar.gz"
    command = (
        f"cd {shlex.quote(REMOTE)} && "
        f"tar -czf {shlex.quote(archive_name)} "
        f"{shlex.quote(state_name)} {shlex.quote(log_name)} out "
        "remote_experiment.py candidate bound_inputs/MATERIALIZED_SHA256SUMS.txt "
        f"2>{shlex.quote(archive_name + '.stderr')} && "
        f"sha256sum {shlex.quote(archive_name)} > "
        f"{shlex.quote(archive_name + '.sha256')}"
    )
    archived = ssh(ip, command, 600)
    atomic(
        artifact / f"{archive_name}.command.json",
        {
            "returncode": archived.returncode,
            "stdout": archived.stdout,
            "stderr": archived.stderr,
        },
    )
    if archived.returncode:
        raise RuntimeError("recoverable_retrieval_defect:archive")
    for suffix in ("", ".sha256"):
        copied = scp_from(
            ip,
            f"{REMOTE}/{archive_name}{suffix}",
            artifact / f"{archive_name}{suffix}",
        )
        if copied.returncode:
            raise RuntimeError("recoverable_retrieval_defect:scp")
    expected = (artifact / f"{archive_name}.sha256").read_text().split()[0]
    if digest(artifact / archive_name) != expected:
        raise RuntimeError("recoverable_retrieval_defect:hash")
    snapshot = run(
        [
            str(ARTIFACT_SNAPSHOT),
            "--archive",
            str(artifact / archive_name),
            "--root",
            str(artifact / "snapshots"),
        ]
    )
    if snapshot.returncode:
        raise RuntimeError("recoverable_retrieval_defect:snapshot")
    return Path(json.loads(snapshot.stdout)["destination"])


def release(contents: dict) -> None:
    path = PROJECT / "BENCH_CONTENTS.json"
    atomic(path, contents)
    result = pool(
        "release",
        "--project",
        NAME,
        "--condition",
        "maintenance",
        "--contents",
        str(path),
    )
    if result.returncode:
        raise RuntimeError("typed_pool_boundary:release:" + result.stderr)


def main() -> int:
    if digest(PACKET) != PACKET_SHA256:
        raise RuntimeError("typed_repair_packet_hash_boundary")
    prior = float(
        json.loads((PROJECT / "STATUS.json").read_text()).get(
            "actual_spend_usd", 0.0
        )
    )
    claimed_at = claim()
    run_id = dt.datetime.now(dt.timezone.utc).strftime(
        "high-load-bypass-%Y%m%dt%H%M%Sz"
    )
    artifact = PROJECT / "artifacts" / run_id
    artifact.mkdir(parents=True, exist_ok=False)
    ip = instance_ip()
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME)
            atomic(
                PROJECT / "OWNER_HEARTBEAT.json",
                {
                    "at_utc": utc_now(),
                    "returncode": result.returncode,
                    "stderr": result.stderr,
                },
            )

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    for _ in range(200):
        if LOCAL_STATE.exists():
            break
        time.sleep(0.02)
    local_owner = json.loads(LOCAL_STATE.read_text())
    active = {
        "unit": str(LOCAL_STATE),
        "unit_manager": "pid",
        "pid": local_owner["pid"],
        "start_ticks": local_owner["start_ticks"],
        "deadline_utc": DEADLINE.isoformat().replace("+00:00", "Z"),
        "artifact_root": str(artifact),
        "bench_id": BENCH,
        "remote_root": REMOTE,
        "expected_terminal": "FINAL_TERMINAL.json",
    }
    update_status(
        active,
        "PID-managed controller owns the retained H200 claim.",
        spend_since(claimed_at, prior),
    )
    state_name = "EXPERIMENT_OWNER.json"
    disposition = "active"
    try:
        stage(ip, PACKET, f"REPAIR_PACKET.{PACKET_SHA256}.tar")
        launch_remote(ip, state_name)
        while dt.datetime.now(dt.timezone.utc) < DEADLINE:
            time.sleep(10)
            state = remote_state(ip, state_name)
            atomic(artifact / "REMOTE_STATE.json", state)
            if state["final"]:
                snapshot = retrieve(ip, artifact, state_name)
                terminal = json.loads(
                    (snapshot / "out/FINAL_TERMINAL.json").read_text()
                )
                gpu = ssh(
                    ip,
                    "sudo docker ps --format '{{.Names}} {{.Status}}'; "
                    "nvidia-smi --query-compute-apps=pid,used_memory "
                    "--format=csv,noheader,nounits",
                    45,
                )
                spend = spend_since(claimed_at, prior)
                update_status(
                    None,
                    f"Measured terminal {terminal['result']} persisted at {snapshot}.",
                    spend,
                )
                release(
                    {
                        "schema_version": 1,
                        "project": NAME,
                        "result": terminal["result"],
                        "candidate_sample_consumed": True,
                        "scientific_invocation_started": True,
                        "artifacts": str(artifact.relative_to(PROJECT)),
                        "checkpoint": (
                            f"{CHECKPOINT} remains resident and read-only."
                        ),
                        "runtime": (
                            "Pinned SGLang v0.5.13 FP8, page-1 E5M2 KV, "
                            "depth-12 NGRAM below eight and ordinary greedy "
                            "target decode at eight or more."
                        ),
                        "server_state": (
                            "Final candidate container remains loaded on port "
                            "30000; no compatible successor is identified."
                        ),
                        "gpu_processes": gpu.stdout.strip(),
                    }
                )
                disposition = "scientific_terminal_released_maintenance"
                break
            if state["attempt"] and not state["owner_live"]:
                snapshot = retrieve(ip, artifact, state_name)
                attempt = snapshot / "out/ATTEMPT_TERMINAL.json"
                atomic(
                    PROJECT / "REPAIR_READY.json",
                    {
                        "schema_version": 1,
                        "at_utc": utc_now(),
                        "classification": (
                            "ordinary_integration_or_consumer_defect"
                        ),
                        "diagnostic": str(attempt),
                        "snapshot": str(snapshot),
                        "artifact_root": str(artifact),
                        "claim_retained": True,
                        "retry_scope": (
                            "Patch and retry only the invalidated operation; "
                            "preserve PREFIX_PERSISTED.json if present."
                        ),
                        "repair_deadline_utc": REPAIR_DEADLINE.isoformat().replace(
                            "+00:00", "Z"
                        ),
                    },
                )
                while dt.datetime.now(dt.timezone.utc) < REPAIR_DEADLINE:
                    request = PROJECT / "REPAIR_REQUEST.json"
                    if request.exists():
                        value = json.loads(request.read_text())
                        packet = Path(value["packet_path"])
                        expected = value["packet_sha256"]
                        if digest(packet) != expected:
                            raise RuntimeError("typed_repair_boundary:packet_hash")
                        state_name = (
                            f"EXPERIMENT_OWNER_REPAIR{int(time.time())}.json"
                        )
                        stage(ip, packet, f"REPAIR_PACKET.{expected}.tar")
                        ssh(
                            ip,
                            f"cd {shlex.quote(REMOTE)} && "
                            "mv out/ATTEMPT_TERMINAL.json "
                            f"out/ATTEMPT_TERMINAL.{int(time.time())}.json",
                            60,
                        )
                        request.rename(
                            PROJECT
                            / f"REPAIR_REQUEST.consumed.{int(time.time())}.json"
                        )
                        launch_remote(ip, state_name)
                        break
                    time.sleep(5)
                else:
                    disposition = "repair_deadline"
                    break
        if disposition == "active":
            disposition = "absolute_deadline"
        if disposition in {"absolute_deadline", "repair_deadline"}:
            spend = spend_since(claimed_at, prior)
            update_status(
                None,
                f"Controller reached {disposition}; director disposition required.",
                spend,
            )
            release(
                {
                    "schema_version": 1,
                    "project": NAME,
                    "result": disposition,
                    "candidate_sample_consumed": False,
                    "scientific_invocation_started": True,
                    "artifacts": str(artifact.relative_to(PROJECT)),
                    "server_state": "Remote state requires director inspection.",
                }
            )
    finally:
        stop.set()
        thread.join(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
