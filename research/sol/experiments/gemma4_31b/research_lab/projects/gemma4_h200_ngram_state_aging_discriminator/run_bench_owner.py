#!/usr/bin/env python3
"""Bounded owner for the one admitted NGRAM state-aging trajectory."""

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
NEBIUS = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = Path("/root/.config/nebius/glm-campaign/known_hosts")
DETACHED_OWNER = Path("/root/workspace/research/factory/tools/detached-owner")
NAME = "gemma4_h200_ngram_state_aging_discriminator"
BENCH = "h200-ngram-verifier-e00kcm9nfhwt7e7gbc"
REMOTE = "/home/glmrunner/gemma4-h200-ngram-state-aging"
PACKET = PROJECT / "FROZEN_PACKET.tar"
DEADLINE = dt.datetime(2026, 7, 24, 16, 45, tzinfo=dt.timezone.utc)
REPAIR_DEADLINE = dt.datetime(2026, 7, 24, 16, 35, tzinfo=dt.timezone.utc)
HOURLY_USD = 2.46


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False, **kwargs)


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


def ssh(ip: str, command: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
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


def scp_from(ip: str, source: str, target: Path, timeout: int = 600):
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


def status_update(active_session: dict | None, summary: str) -> None:
    path = PROJECT / "STATUS.json"
    value = json.loads(path.read_text())
    value["active_session"] = active_session
    value["summary"] = summary
    atomic(path, value)


def stage(ip: str, artifact: Path) -> None:
    packet_sha = digest(PACKET)
    owner_sha = digest(DETACHED_OWNER)
    prepare = ssh(
        ip,
        f"install -d {shlex.quote(REMOTE)} {shlex.quote(REMOTE + '/out')}",
    )
    if prepare.returncode:
        raise RuntimeError("typed_staging_boundary:remote_prepare")
    for source, target, expected in [
        (PACKET, f"{REMOTE}/FROZEN_PACKET.tar", packet_sha),
        (DETACHED_OWNER, f"{REMOTE}/detached-owner", owner_sha),
    ]:
        test = ssh(
            ip,
            f"test -f {shlex.quote(target)} && "
            f"test \"$(sha256sum {shlex.quote(target)} | cut -d' ' -f1)\" = {expected}",
            120,
        )
        if test.returncode:
            partial = target + f".{expected}.part"
            transfer = scp_to(ip, source, partial)
            if transfer.returncode:
                (artifact / f"{source.name}.scp.stderr").write_text(transfer.stderr)
                raise RuntimeError(f"typed_staging_boundary:transfer:{source.name}")
            finalize = ssh(
                ip,
                f"test \"$(sha256sum {shlex.quote(partial)} | cut -d' ' -f1)\" = {expected} && "
                f"mv -f {shlex.quote(partial)} {shlex.quote(target)}",
                180,
            )
            if finalize.returncode:
                raise RuntimeError(f"typed_staging_boundary:verify:{source.name}")
    extract = ssh(
        ip,
        f"cd {shlex.quote(REMOTE)} && tar -xf FROZEN_PACKET.tar && "
        "chmod +x detached-owner remote_candidate.py",
        180,
    )
    if extract.returncode:
        raise RuntimeError("typed_staging_boundary:extract")
    atomic(
        artifact / "STAGING_MANIFEST.json",
        {
            "packet_sha256": packet_sha,
            "detached_owner_sha256": owner_sha,
            "remote": REMOTE,
        },
    )


def verify_remote_binding(ip: str, artifact: Path) -> None:
    manifest = json.loads((PROJECT / "inputs/CHECKPOINT_MANIFEST.json").read_text())
    checkpoint = (
        "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint"
    )
    checks = []
    for row in manifest["files"]:
        target = f"{checkpoint}/{row['name']}"
        checks.append(
            f"test \"$(stat -c %s {shlex.quote(target)})\" = {row['bytes']} && "
            f"test \"$(sha256sum {shlex.quote(target)} | cut -d' ' -f1)\" = {row['sha256']}"
        )
    command = " && ".join(checks) + (
        " && sudo docker image inspect "
        "docker.io/lmsysorg/sglang@sha256:"
        "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6 "
        "--format '{{index .RepoDigests 0}}'"
    )
    result = ssh(ip, command, 2400)
    (artifact / "remote-binding.stdout").write_text(result.stdout)
    (artifact / "remote-binding.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("typed_remote_integrity_boundary:checkpoint_or_image")


def launch_remote(ip: str, artifact: Path) -> None:
    command = (
        f"cd {shlex.quote(REMOTE)} && ./detached-owner start "
        f"--state {shlex.quote(REMOTE + '/OWNER.json')} "
        f"--log {shlex.quote(REMOTE + '/OWNER.log')} "
        f"--cwd {shlex.quote(REMOTE)} -- python3 remote_candidate.py"
    )
    result = ssh(ip, command, 60)
    (artifact / "remote-owner-launch.stdout").write_text(result.stdout)
    (artifact / "remote-owner-launch.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("typed_remote_owner_boundary:launch")


def retrieve(ip: str, artifact: Path) -> None:
    archive = f"{REMOTE}/compact.tar.gz"
    command = (
        f"cd {shlex.quote(REMOTE)} && tar -czf compact.tar.gz "
        "OWNER.json OWNER.log out 2>compact-tar.stderr; "
        "sha256sum compact.tar.gz > compact.tar.gz.sha256"
    )
    result = ssh(ip, command, 180)
    (artifact / "retrieval-command.stdout").write_text(result.stdout)
    (artifact / "retrieval-command.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("recoverable_retrieval_defect:remote_archive")
    for remote_name, local_name in [
        (archive, "compact.tar.gz"),
        (archive + ".sha256", "compact.tar.gz.sha256"),
    ]:
        copied = scp_from(ip, remote_name, artifact / local_name, 900)
        if copied.returncode:
            (artifact / f"{local_name}.scp.stderr").write_text(copied.stderr)
            raise RuntimeError("recoverable_retrieval_defect:scp")
    expected = (artifact / "compact.tar.gz.sha256").read_text().split()[0]
    if digest(artifact / "compact.tar.gz") != expected:
        raise RuntimeError("recoverable_retrieval_defect:hash")
    extracted = artifact / "retrieved"
    extracted.mkdir(exist_ok=True)
    untar = run(["tar", "-xzf", str(artifact / "compact.tar.gz"), "-C", str(extracted)])
    if untar.returncode:
        raise RuntimeError("recoverable_retrieval_defect:local_extract")


def remote_state(ip: str) -> dict[str, object]:
    result = ssh(
        ip,
        f"cd {shlex.quote(REMOTE)} && "
        "./detached-owner status --state OWNER.json 2>/dev/null; "
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


def release(condition: str, contents: dict[str, object]) -> None:
    contents_path = PROJECT / "BENCH_CONTENTS.json"
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
    if result.returncode:
        raise RuntimeError("typed_pool_boundary:release:" + result.stderr)


def main() -> int:
    run_id = dt.datetime.now(dt.timezone.utc).strftime("state-aging-%Y%m%dt%H%M%Sz")
    artifact = PROJECT / "artifacts" / run_id
    artifact.mkdir(parents=True, exist_ok=False)
    claim_started = time.time()
    claim = pool(
        "claim",
        "--project",
        NAME,
        "--bench",
        BENCH,
        "--lease-seconds",
        "300",
    )
    (artifact / "claim.stdout").write_text(claim.stdout)
    (artifact / "claim.stderr").write_text(claim.stderr)
    if claim.returncode:
        raise RuntimeError("typed_pool_boundary:claim")

    ip = instance_ip()
    stop_heartbeat = threading.Event()

    def heartbeat() -> None:
        while not stop_heartbeat.wait(45):
            result = pool("heartbeat", "--project", NAME)
            atomic(
                PROJECT / "OWNER_HEARTBEAT.json",
                {
                    "at_utc": utc_now(),
                    "returncode": result.returncode,
                    "stderr": result.stderr,
                },
            )

    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    heartbeat_thread.start()
    status_update(
        {
            "unit": str(PROJECT / "run_bench_owner.py"),
            "unit_manager": "foreground-controller",
            "pid": os.getpid(),
            "deadline_utc": DEADLINE.isoformat().replace("+00:00", "Z"),
            "artifact_root": str(artifact),
            "bench_id": BENCH,
            "remote_root": REMOTE,
            "expected_terminal": "FINAL_TERMINAL.json",
        },
        "Claimed the retained H200 once; immutable candidate staging and the single trajectory are owned by one bounded controller.",
    )
    disposition: str | None = None
    try:
        identity = ssh(
            ip,
            "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; "
            "sudo docker --version",
            45,
        )
        (artifact / "remote-identity.stdout").write_text(identity.stdout)
        (artifact / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_remote_boundary:ssh")
        stage(ip, artifact)
        verify_remote_binding(ip, artifact)
        launch_remote(ip, artifact)

        while dt.datetime.now(dt.timezone.utc) < DEADLINE:
            time.sleep(15)
            state = remote_state(ip)
            atomic(artifact / "REMOTE_STATE.json", state)
            if state["final"]:
                retrieve(ip, artifact)
                terminal = json.loads(
                    (artifact / "retrieved/out/FINAL_TERMINAL.json").read_text()
                )
                if not terminal.get("candidate_science_consumed"):
                    raise RuntimeError("recoverable_consumer_defect:unconsumed_terminal")
                gpu = ssh(
                    ip,
                    "sudo docker inspect -f '{{.State.Running}}' "
                    "gemma4-ngram-state-aging 2>/dev/null; "
                    "nvidia-smi --query-compute-apps=pid,used_memory "
                    "--format=csv,noheader,nounits",
                    45,
                )
                contents = {
                    "project": NAME,
                    "result": terminal["result"],
                    "artifacts": str(artifact.relative_to(PROJECT)),
                    "server_state": (
                        "Candidate container gemma4-ngram-state-aging remains "
                        "healthy on port 30000 with its exact instrumentation patch."
                    ),
                    "gpu_processes": gpu.stdout.strip(),
                    "checkpoint": (
                        "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/"
                        "checkpoint remains resident and read-only."
                    ),
                }
                release("maintenance", contents)
                disposition = "scientific_terminal_released_maintenance"
                break
            if state["attempt"] and not state["owner_live"]:
                retrieve(ip, artifact)
                atomic(
                    PROJECT / "REPAIR_READY.json",
                    {
                        "at_utc": utc_now(),
                        "artifact_root": str(artifact),
                        "diagnostic": "Remote worker exited without a scientific terminal.",
                        "repair_deadline_utc": REPAIR_DEADLINE.isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "claim_retained": True,
                    },
                )
                while dt.datetime.now(dt.timezone.utc) < REPAIR_DEADLINE:
                    request = PROJECT / "REPAIR_REQUEST.json"
                    if request.exists():
                        value = json.loads(request.read_text())
                        if value.get("action") != "retry_remote_worker":
                            raise RuntimeError("typed_repair_boundary:unsupported_action")
                        request.rename(
                            PROJECT / f"REPAIR_REQUEST.consumed.{int(time.time())}.json"
                        )
                        launch_remote(ip, artifact)
                        break
                    time.sleep(10)
                else:
                    raise RuntimeError("typed_repair_boundary:deadline")
        else:
            raise RuntimeError("typed_deadline_boundary:absolute")
    except Exception as exc:
        atomic(
            artifact / "OWNER_EXCEPTION.json",
            {"at_utc": utc_now(), "error": repr(exc)},
        )
        try:
            retrieve(ip, artifact)
        except Exception as retrieval_exc:
            atomic(
                artifact / "RETRIEVAL_EXCEPTION.json",
                {"error": repr(retrieval_exc), "at_utc": utc_now()},
            )
        guest = remote_state(ip)
        release(
            "maintenance",
            {
                "project": NAME,
                "result": "typed_owner_or_remote_boundary",
                "error": repr(exc),
                "artifacts": str(artifact.relative_to(PROJECT)),
                "remote_state": guest,
                "server_state": "Requires director inspection before reuse.",
            },
        )
        disposition = "typed_boundary_released_maintenance"
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(5)
        claimed_seconds = max(0.0, time.time() - claim_started)
        spend = claimed_seconds / 3600 * HOURLY_USD
        atomic(
            PROJECT / "OWNER_TERMINAL.json",
            {
                "at_utc": utc_now(),
                "disposition": disposition,
                "artifact_root": str(artifact),
                "claimed_seconds": claimed_seconds,
                "conservative_provider_spend_usd": spend,
            },
        )
        status_update(
            None,
            f"Bounded owner completed with disposition {disposition}; see {artifact}.",
        )
    return 0 if disposition == "scientific_terminal_released_maintenance" else 2


if __name__ == "__main__":
    raise SystemExit(main())
