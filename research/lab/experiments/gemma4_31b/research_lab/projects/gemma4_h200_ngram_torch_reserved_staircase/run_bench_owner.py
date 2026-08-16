#!/usr/bin/env python3
"""Durable controller for the single retained-H200 allocator attribution."""

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
NEBIUS = Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = Path("/root/.config/nebius/glm-campaign/known_hosts")
DETACHED_OWNER = Path("/root/workspace/research/factory/tools/detached-owner")
ARTIFACT_SNAPSHOT = Path("/root/workspace/research/factory/tools/artifact-snapshot")
NAME = "gemma4_h200_ngram_torch_reserved_staircase"
BENCH = "h200-ngram-verifier-e00kcm9nfhwt7e7gbc"
REMOTE = "/home/glmrunner/gemma4-h200-ngram-torch-reserved-staircase"
CONTAINER = "gemma4-ngram-torch-staircase"
PACKET = PROJECT / "FROZEN_PACKET.tar"
LOCAL_OWNER_STATE = PROJECT / "LOCAL_OWNER.json"
DEADLINE = dt.datetime(2026, 7, 24, 20, 50, tzinfo=dt.timezone.utc)
REPAIR_DEADLINE = dt.datetime(2026, 7, 24, 20, 40, tzinfo=dt.timezone.utc)
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
            "python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args,
        ],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
    )


def ssh(ip: str, command: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "ssh", "-i", str(KEY), "-o", "BatchMode=yes",
            "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
            f"glmrunner@{ip}", command,
        ],
        timeout=timeout,
    )


def scp_to(ip: str, source: Path, target: str, timeout: int = 600):
    return run(
        [
            "scp", "-p", "-i", str(KEY), "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
            str(source), f"glmrunner@{ip}:{target}",
        ],
        timeout=timeout,
    )


def scp_from(ip: str, source: str, target: Path, timeout: int = 900):
    return run(
        [
            "scp", "-p", "-i", str(KEY), "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
            f"glmrunner@{ip}:{source}", str(target),
        ],
        timeout=timeout,
    )


def instance_ip() -> str:
    sys.path.insert(0, str(NEBIUS))
    from placement_control import extract_public_ipv4, get_instance

    value = extract_public_ipv4(get_instance("computeinstance-e00kcm9nfhwt7e7gbc"))
    if not value:
        raise RuntimeError("typed_provider_boundary:no_public_ip")
    return value


def claim_started_at() -> dt.datetime:
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = (
        benches[BENCH]
        if isinstance(benches, dict)
        else next(row for row in benches if row["id"] == BENCH)
    )
    claim = bench.get("claim")
    if not claim or claim.get("project") != NAME:
        raise RuntimeError("typed_pool_boundary:claim_not_owned")
    return dt.datetime.fromisoformat(claim["claimed_at"].replace("Z", "+00:00"))


def status_update(active_session: dict | None, summary: str) -> None:
    path = PROJECT / "STATUS.json"
    value = json.loads(path.read_text())
    value["active_session"] = active_session
    value["summary"] = summary
    atomic(path, value)


def stage(ip: str, artifact: Path) -> None:
    packet_sha = digest(PACKET)
    owner_sha = digest(DETACHED_OWNER)
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
            copied = scp_to(ip, source, partial)
            if copied.returncode:
                (artifact / f"{source.name}.scp.stderr").write_text(copied.stderr)
                raise RuntimeError(f"typed_staging_boundary:transfer:{source.name}")
            finalized = ssh(
                ip,
                f"test \"$(sha256sum {shlex.quote(partial)} | cut -d' ' -f1)\" = {expected} && "
                f"mv -f {shlex.quote(partial)} {shlex.quote(target)}",
                180,
            )
            if finalized.returncode:
                raise RuntimeError(f"typed_staging_boundary:verify:{source.name}")
    extracted = ssh(
        ip,
        f"cd {shlex.quote(REMOTE)} && tar -xf FROZEN_PACKET.tar && "
        "chmod +x detached-owner remote_attribution.py",
        180,
    )
    if extracted.returncode:
        raise RuntimeError("typed_staging_boundary:extract")
    atomic(
        artifact / "STAGING_MANIFEST.json",
        {"packet_sha256": packet_sha, "detached_owner_sha256": owner_sha},
    )


def launch_remote(ip: str, artifact: Path) -> None:
    command = (
        f"cd {shlex.quote(REMOTE)} && ./detached-owner start "
        f"--state {shlex.quote(REMOTE + '/ATTRIBUTION_OWNER.json')} "
        f"--log {shlex.quote(REMOTE + '/ATTRIBUTION_OWNER.log')} "
        f"--cwd {shlex.quote(REMOTE)} -- python3 remote_attribution.py"
    )
    result = ssh(ip, command, 60)
    (artifact / "remote-owner-launch.stdout").write_text(result.stdout)
    (artifact / "remote-owner-launch.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("typed_remote_owner_boundary:launch")


def remote_state(ip: str) -> dict[str, object]:
    result = ssh(
        ip,
        f"cd {shlex.quote(REMOTE)} && "
        "./detached-owner status --state ATTRIBUTION_OWNER.json 2>/dev/null; "
        "test -f out/ATTRIBUTION_TERMINAL.json && echo ATTRIBUTION_PRESENT || true; "
        "test -f out/ATTEMPT_TERMINAL.json && echo ATTEMPT_PRESENT || true; "
        "cat out/INVOCATION_STATE.json 2>/dev/null || true",
        45,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "attribution": "ATTRIBUTION_PRESENT" in result.stdout,
        "attempt": "ATTEMPT_PRESENT" in result.stdout,
        "owner_live": '"live": true' in result.stdout,
    }


def retrieve(ip: str, artifact: Path) -> Path:
    result = ssh(
        ip,
        f"cd {shlex.quote(REMOTE)} && tar -czf compact.tar.gz "
        "ATTRIBUTION_OWNER.json ATTRIBUTION_OWNER.log out "
        "donor-source-v2.tar.gz donor-container-inspect.json "
        "donor-pip-freeze.txt DONOR_CAPTURE_SHA256SUMS 2>compact-tar.stderr && "
        "sha256sum compact.tar.gz > compact.tar.gz.sha256",
        300,
    )
    (artifact / "retrieval-command.stdout").write_text(result.stdout)
    (artifact / "retrieval-command.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("recoverable_retrieval_defect:remote_archive")
    for remote_name, local_name in [
        (f"{REMOTE}/compact.tar.gz", "compact.tar.gz"),
        (f"{REMOTE}/compact.tar.gz.sha256", "compact.tar.gz.sha256"),
    ]:
        copied = scp_from(ip, remote_name, artifact / local_name)
        if copied.returncode:
            (artifact / f"{local_name}.scp.stderr").write_text(copied.stderr)
            raise RuntimeError("recoverable_retrieval_defect:scp")
    expected = (artifact / "compact.tar.gz.sha256").read_text().split()[0]
    if digest(artifact / "compact.tar.gz") != expected:
        raise RuntimeError("recoverable_retrieval_defect:hash")
    snapshot = run(
        [
            str(ARTIFACT_SNAPSHOT), "--archive", str(artifact / "compact.tar.gz"),
            "--root", str(artifact / "snapshots"),
        ]
    )
    (artifact / "artifact-snapshot.stdout").write_text(snapshot.stdout)
    (artifact / "artifact-snapshot.stderr").write_text(snapshot.stderr)
    if snapshot.returncode:
        raise RuntimeError("recoverable_retrieval_defect:artifact_snapshot")
    return Path(json.loads(snapshot.stdout)["destination"])


def release(contents: dict[str, object]) -> None:
    contents_path = PROJECT / "BENCH_CONTENTS.json"
    atomic(contents_path, contents)
    result = pool(
        "release", "--project", NAME, "--condition", "maintenance",
        "--contents", str(contents_path),
    )
    if result.returncode:
        raise RuntimeError("typed_pool_boundary:release:" + result.stderr)


def main() -> int:
    run_id = dt.datetime.now(dt.timezone.utc).strftime("torch-staircase-%Y%m%dt%H%M%Sz")
    artifact = PROJECT / "artifacts" / run_id
    artifact.mkdir(parents=True, exist_ok=False)
    claimed_at = claim_started_at()
    ip = instance_ip()
    stop_heartbeat = threading.Event()

    def heartbeat() -> None:
        while not stop_heartbeat.wait(45):
            result = pool("heartbeat", "--project", NAME)
            atomic(
                PROJECT / "OWNER_HEARTBEAT.json",
                {"at_utc": utc_now(), "returncode": result.returncode, "stderr": result.stderr},
            )

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    for _ in range(100):
        if LOCAL_OWNER_STATE.exists():
            break
        time.sleep(0.02)
    local_owner = json.loads(LOCAL_OWNER_STATE.read_text())
    status_update(
        {
            "unit": str(LOCAL_OWNER_STATE),
            "unit_manager": "pid",
            "pid": local_owner["pid"],
            "start_ticks": local_owner["start_ticks"],
            "deadline_utc": DEADLINE.isoformat().replace("+00:00", "Z"),
            "artifact_root": str(artifact),
            "bench_id": BENCH,
            "remote_root": REMOTE,
            "expected_terminal": "ATTRIBUTION_TERMINAL.json",
        },
        "The retained H200 is claimed once; one PID-managed owner spans stock-prefix attribution, retrieval, repair disposition, and release.",
    )
    disposition = None
    try:
        stage(ip, artifact)
        launch_remote(ip, artifact)
        while dt.datetime.now(dt.timezone.utc) < DEADLINE:
            time.sleep(10)
            state = remote_state(ip)
            atomic(artifact / "REMOTE_STATE.json", state)
            if state["attribution"]:
                snapshot = retrieve(ip, artifact)
                terminal = json.loads(
                    (snapshot / "out/ATTRIBUTION_TERMINAL.json").read_text()
                )
                if not terminal.get("attribution_science_consumed"):
                    raise RuntimeError("recoverable_consumer_defect:unconsumed_terminal")
                ready = {
                    "at_utc": utc_now(),
                    "artifact_root": str(artifact),
                    "snapshot": str(snapshot),
                    "diagnostic": "Valid allocation-history producer persisted.",
                    "retry_scope": (
                        "Finalize with no candidate, or stage exactly one source-specific "
                        "candidate without replaying the prefix."
                    ),
                    "repair_deadline_utc": REPAIR_DEADLINE.isoformat().replace("+00:00", "Z"),
                    "claim_retained": True,
                }
                atomic(PROJECT / "REPAIR_READY.json", ready)
                request = PROJECT / "REPAIR_REQUEST.json"
                while dt.datetime.now(dt.timezone.utc) < REPAIR_DEADLINE:
                    if request.exists():
                        value = json.loads(request.read_text())
                        if value.get("action") != "finalize_no_candidate":
                            raise RuntimeError("typed_repair_boundary:unsupported_action")
                        request.rename(
                            PROJECT / f"REPAIR_REQUEST.consumed.{int(time.time())}.json"
                        )
                        gpu = ssh(
                            ip,
                            "sudo docker inspect -f '{{.State.Running}}' "
                            f"{CONTAINER} 2>/dev/null; "
                            "nvidia-smi --query-compute-apps=pid,used_memory "
                            "--format=csv,noheader,nounits",
                            45,
                        )
                        release(
                            {
                                "project": NAME,
                                "result": value.get("result", "attribution_no_candidate"),
                                "artifacts": str(artifact.relative_to(PROJECT)),
                                "server_state": (
                                    "Stock-SWA attribution container "
                                    f"{CONTAINER} remains loaded on port 30000."
                                ),
                                "gpu_processes": gpu.stdout.strip(),
                                "checkpoint": (
                                    "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/"
                                    "checkpoint remains resident and read-only."
                                ),
                            }
                        )
                        disposition = "scientific_terminal_released_maintenance"
                        break
                    time.sleep(5)
                if disposition:
                    break
                raise RuntimeError("typed_repair_boundary:deadline")
            if state["attempt"] and not state["owner_live"]:
                retrieve(ip, artifact)
                atomic(
                    PROJECT / "REPAIR_READY.json",
                    {
                        "at_utc": utc_now(),
                        "artifact_root": str(artifact),
                        "diagnostic": "Remote worker exited without attribution terminal.",
                        "retry_scope": "Patch and retry only the invalidated prefix operation.",
                        "repair_deadline_utc": REPAIR_DEADLINE.isoformat().replace("+00:00", "Z"),
                        "claim_retained": True,
                    },
                )
                raise RuntimeError("recoverable_attribution_defect:repair_required")
        else:
            raise RuntimeError("typed_deadline_boundary:absolute")
    except Exception as exc:
        atomic(artifact / "OWNER_EXCEPTION.json", {"at_utc": utc_now(), "error": repr(exc)})
        try:
            retrieve(ip, artifact)
        except Exception as retrieval_exc:
            atomic(
                artifact / "RETRIEVAL_EXCEPTION.json",
                {"at_utc": utc_now(), "error": repr(retrieval_exc)},
            )
        guest = remote_state(ip)
        release(
            {
                "project": NAME,
                "result": "typed_owner_or_remote_boundary",
                "error": repr(exc),
                "artifacts": str(artifact.relative_to(PROJECT)),
                "remote_state": guest,
                "server_state": "Requires director inspection before reuse.",
            }
        )
        disposition = "typed_boundary_released_maintenance"
    finally:
        stop_heartbeat.set()
        thread.join(5)
        claimed_seconds = max(
            0.0, (dt.datetime.now(dt.timezone.utc) - claimed_at).total_seconds()
        )
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
        status_path = PROJECT / "STATUS.json"
        status = json.loads(status_path.read_text())
        status["active_session"] = None
        status["actual_spend_usd"] = spend
        status["summary"] = (
            f"Bounded owner completed with disposition {disposition}; see {artifact}."
        )
        atomic(status_path, status)
    return 0 if disposition == "scientific_terminal_released_maintenance" else 2


if __name__ == "__main__":
    raise SystemExit(main())
