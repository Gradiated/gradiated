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
NEBIUS = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = Path("/root/.config/nebius/glm-campaign/known_hosts")
DETACHED_OWNER = Path("/root/workspace/research/factory/tools/detached-owner")
ARTIFACT_SNAPSHOT = Path("/root/workspace/research/factory/tools/artifact-snapshot")
NAME = "gemma4_h200_ngram_adaptive_draft_depth"
BENCH = "h200-ngram-verifier-e00kcm9nfhwt7e7gbc"
INSTANCE = "computeinstance-e00kcm9nfhwt7e7gbc"
REMOTE = "/home/glmrunner/gemma4-h200-ngram-adaptive-depth"
CHECKPOINT = "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint"
PACKET = PROJECT / "FROZEN_PACKET.tar"
LOCAL_STATE = PROJECT / "LOCAL_OWNER.json"
DEADLINE = dt.datetime(2026, 7, 24, 22, 20, tzinfo=dt.timezone.utc)
HOURLY_USD = 2.46


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
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


def scp_to(
    ip: str, source: Path, target: str, timeout: int = 600
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
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            str(source),
            f"glmrunner@{ip}:{target}",
        ],
        timeout=timeout,
    )


def scp_from(
    ip: str, source: str, target: Path, timeout: int = 900
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


def claimed_at() -> dt.datetime:
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


def update_status(active_session: dict | None, summary: str, spend: float) -> None:
    path = PROJECT / "STATUS.json"
    value = json.loads(path.read_text())
    value["active_session"] = active_session
    value["summary"] = summary
    value["actual_spend_usd"] = spend
    atomic(path, value)


def stage(ip: str, packet: Path, remote_name: str = "FROZEN_PACKET.tar") -> None:
    packet_sha = digest(packet)
    owner_sha = digest(DETACHED_OWNER)
    ssh(ip, f"mkdir -p {shlex.quote(REMOTE)}", 60)
    for source, target, expected in [
        (packet, f"{REMOTE}/{remote_name}", packet_sha),
        (DETACHED_OWNER, f"{REMOTE}/detached-owner", owner_sha),
    ]:
        test = ssh(
            ip,
            f"test -f {shlex.quote(target)} && "
            f"test \"$(sha256sum {shlex.quote(target)} | cut -d' ' -f1)\" = {expected}",
            120,
        )
        if test.returncode:
            partial = f"{target}.{expected}.part"
            copied = scp_to(ip, source, partial)
            if copied.returncode:
                raise RuntimeError(f"typed_staging_boundary:{source.name}")
            finalized = ssh(
                ip,
                f"test \"$(sha256sum {shlex.quote(partial)} | cut -d' ' -f1)\" = {expected} && "
                f"mv -f {shlex.quote(partial)} {shlex.quote(target)}",
                180,
            )
            if finalized.returncode:
                raise RuntimeError(f"typed_staging_verify_boundary:{source.name}")
    extracted = ssh(
        ip,
        f"cd {shlex.quote(REMOTE)} && tar -xf {shlex.quote(remote_name)} && "
        "chmod +x detached-owner remote_experiment.py",
        180,
    )
    if extracted.returncode:
        raise RuntimeError("typed_staging_boundary:extract")


def launch_remote(ip: str, state_name: str = "EXPERIMENT_OWNER.json") -> None:
    result = ssh(
        ip,
        f"cd {shlex.quote(REMOTE)} && ./detached-owner start "
        f"--state {shlex.quote(REMOTE + '/' + state_name)} "
        f"--log {shlex.quote(REMOTE + '/' + state_name.replace('.json', '.log'))} "
        f"--cwd {shlex.quote(REMOTE)} -- python3 remote_experiment.py",
        60,
    )
    if result.returncode:
        raise RuntimeError("typed_remote_owner_boundary:launch:" + result.stderr)


def remote_state(ip: str, state_name: str) -> dict[str, object]:
    result = ssh(
        ip,
        f"cd {shlex.quote(REMOTE)} && "
        f"./detached-owner status --state {shlex.quote(state_name)} 2>/dev/null; "
        "test -f out/FINAL_TERMINAL.json && echo FINAL_PRESENT || true; "
        "test -f out/COMPONENT_TERMINAL.json && echo COMPONENT_PRESENT || true; "
        "test -f out/ATTEMPT_TERMINAL.json && echo ATTEMPT_PRESENT || true; "
        "cat out/INVOCATION_STATE.json 2>/dev/null || true",
        45,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "final": "FINAL_PRESENT" in result.stdout,
        "component": "COMPONENT_PRESENT" in result.stdout,
        "attempt": "ATTEMPT_PRESENT" in result.stdout,
        "owner_live": '"live": true' in result.stdout,
    }


def retrieve(ip: str, artifact: Path, state_name: str) -> Path:
    log_name = state_name.replace(".json", ".log")
    command = (
        f"cd {shlex.quote(REMOTE)} && "
        f"items='{shlex.quote(state_name)} {shlex.quote(log_name)} out "
        "remote_experiment.py reference candidate base inputs'; "
        "test ! -e installed-consumer-sources.tar.gz || "
        "items=\"$items installed-consumer-sources.tar.gz\"; "
        "test ! -e donor-container-inspect.json || "
        "items=\"$items donor-container-inspect.json\"; "
        "tar -czf compact.tar.gz $items 2>compact-tar.stderr && "
        "sha256sum compact.tar.gz > compact.tar.gz.sha256"
    )
    archived = ssh(ip, command, 300)
    (artifact / "retrieval-command.stdout").write_text(archived.stdout)
    (artifact / "retrieval-command.stderr").write_text(archived.stderr)
    if archived.returncode:
        raise RuntimeError("recoverable_retrieval_defect:archive")
    for remote_name, local_name in [
        (f"{REMOTE}/compact.tar.gz", "compact.tar.gz"),
        (f"{REMOTE}/compact.tar.gz.sha256", "compact.tar.gz.sha256"),
    ]:
        copied = None
        for _ in range(3):
            copied = scp_from(ip, remote_name, artifact / local_name)
            if not copied.returncode:
                break
            time.sleep(2)
        if copied is None or copied.returncode:
            raise RuntimeError("recoverable_retrieval_defect:scp")
    expected = (artifact / "compact.tar.gz.sha256").read_text().split()[0]
    if digest(artifact / "compact.tar.gz") != expected:
        raise RuntimeError("recoverable_retrieval_defect:hash")
    snapshot = run(
        [
            str(ARTIFACT_SNAPSHOT),
            "--archive",
            str(artifact / "compact.tar.gz"),
            "--root",
            str(artifact / "snapshots"),
        ]
    )
    (artifact / "artifact-snapshot.stdout").write_text(snapshot.stdout)
    (artifact / "artifact-snapshot.stderr").write_text(snapshot.stderr)
    if snapshot.returncode:
        raise RuntimeError("recoverable_retrieval_defect:snapshot")
    return Path(json.loads(snapshot.stdout)["destination"])


def release(contents: dict[str, object]) -> None:
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
    run_id = dt.datetime.now(dt.timezone.utc).strftime(
        "adaptive-depth-%Y%m%dt%H%M%Sz"
    )
    artifact = PROJECT / "artifacts" / run_id
    artifact.mkdir(parents=True, exist_ok=False)
    prior_spend = float(
        json.loads((PROJECT / "STATUS.json").read_text()).get(
            "actual_spend_usd", 0.0
        )
    )
    claim_time = claimed_at()
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
    for _ in range(100):
        if LOCAL_STATE.exists():
            break
        time.sleep(0.02)
    local_owner = json.loads(LOCAL_STATE.read_text())
    update_status(
        {
            "unit": str(LOCAL_STATE),
            "unit_manager": "pid",
            "pid": local_owner["pid"],
            "start_ticks": local_owner["start_ticks"],
            "deadline_utc": DEADLINE.isoformat().replace("+00:00", "Z"),
            "artifact_root": str(artifact),
            "bench_id": BENCH,
            "remote_root": REMOTE,
            "expected_terminal": "FINAL_TERMINAL.json",
        },
        "One PID-managed controller owns the claimed H200 through component, conditional endpoint, retrieval, and release.",
        prior_spend,
    )
    disposition = "active"
    state_name = "EXPERIMENT_OWNER.json"
    try:
        stage(ip, PACKET)
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
                component = json.loads(
                    (snapshot / "out/COMPONENT_TERMINAL.json").read_text()
                )
                candidate_consumed = bool(
                    terminal.get("candidate_science_consumed")
                )
                gpu = ssh(
                    ip,
                    "sudo docker ps --format '{{.Names}} {{.Status}}'; "
                    "nvidia-smi --query-compute-apps=pid,used_memory "
                    "--format=csv,noheader,nounits",
                    45,
                )
                claimed_seconds = (
                    dt.datetime.now(dt.timezone.utc) - claim_time
                ).total_seconds()
                spend = prior_spend + (
                    max(0.0, claimed_seconds) / 3600 * HOURLY_USD
                )
                update_status(
                    None,
                    f"Measured terminal {terminal['result']} persisted at {snapshot}.",
                    spend,
                )
                release(
                    {
                        "project": NAME,
                        "result": terminal["result"],
                        "candidate_sample_consumed": candidate_consumed,
                        "component_result": component["result"],
                        "artifacts": str(artifact.relative_to(PROJECT)),
                        "server_state": (
                            "Final adaptive-depth candidate container remains "
                            "loaded on port 30000; no compatible successor identified."
                        ),
                        "gpu_processes": gpu.stdout.strip(),
                        "checkpoint": f"{CHECKPOINT} remains resident and read-only.",
                    }
                )
                disposition = "scientific_terminal_released_maintenance"
                break
            if state["attempt"] and not state["owner_live"]:
                snapshot = retrieve(ip, artifact, state_name)
                atomic(
                    PROJECT / "REPAIR_READY.json",
                    {
                        "at_utc": utc_now(),
                        "artifact_root": str(artifact),
                        "snapshot": str(snapshot),
                        "diagnostic": str(
                            snapshot / "out/ATTEMPT_TERMINAL.json"
                        ),
                        "retry_scope": (
                            "Patch and retry only the invalidated consumer stage; "
                            "preserve COMPONENT_TERMINAL.json when present."
                        ),
                        "repair_deadline_utc": DEADLINE.isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "claim_retained": True,
                    },
                )
                while dt.datetime.now(dt.timezone.utc) < DEADLINE:
                    request = PROJECT / "REPAIR_REQUEST.json"
                    if request.exists():
                        value = json.loads(request.read_text())
                        packet_value = value.get("packet_path") or value.get(
                            "patch_artifact"
                        )
                        if not packet_value:
                            raise RuntimeError(
                                "typed_repair_boundary:packet_path"
                            )
                        packet = Path(packet_value)
                        expected_digest = value.get("packet_sha256") or digest(
                            packet
                        )
                        if digest(packet) != expected_digest:
                            raise RuntimeError(
                                "typed_repair_boundary:packet_hash"
                            )
                        state_name = (
                            f"EXPERIMENT_OWNER_REPAIR{int(time.time())}.json"
                        )
                        stage(
                            ip,
                            packet,
                            f"REPAIR_{expected_digest}.tar",
                        )
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
                    raise RuntimeError("typed_deadline_boundary:repair")
        else:
            raise RuntimeError("typed_deadline_boundary:absolute")
    except Exception as exc:
        atomic(
            artifact / "OWNER_EXCEPTION.json",
            {"at_utc": utc_now(), "error": repr(exc)},
        )
        try:
            retrieve(ip, artifact, state_name)
        except Exception as retrieval_exc:
            atomic(
                artifact / "RETRIEVAL_EXCEPTION.json",
                {"at_utc": utc_now(), "error": repr(retrieval_exc)},
            )
        claimed_seconds = (
            dt.datetime.now(dt.timezone.utc) - claim_time
        ).total_seconds()
        spend = prior_spend + (
            max(0.0, claimed_seconds) / 3600 * HOURLY_USD
        )
        update_status(
            None,
            f"Typed owner boundary {exc!r}; retained evidence requires director disposition.",
            spend,
        )
        release(
            {
                "project": NAME,
                "result": "typed_owner_or_deadline_boundary",
                "error": repr(exc),
                "artifacts": str(artifact.relative_to(PROJECT)),
                "remote_state": remote_state(ip, state_name),
                "server_state": "Requires director inspection before reuse.",
            }
        )
        disposition = "typed_boundary_released_maintenance"
    finally:
        stop.set()
        thread.join(5)
        claimed_seconds = (
            dt.datetime.now(dt.timezone.utc) - claim_time
        ).total_seconds()
        spend = prior_spend + (
            max(0.0, claimed_seconds) / 3600 * HOURLY_USD
        )
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
    return 0 if disposition == "scientific_terminal_released_maintenance" else 2


if __name__ == "__main__":
    raise SystemExit(main())
