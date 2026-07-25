#!/usr/bin/env python3
"""Durable controller for the bound sequential H200 experiment."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import tarfile
import threading
import time
from typing import Any


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
REPAIR = pathlib.Path("/root/workspace/research/factory/tools/repair-handshake")
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
NAME = "gemma4_h200_ngram_persistent_grouped_lm_head"
PREDECESSOR = "gemma4_h200_ngram_fixed_m384_executor_rewrite"
BENCH = "h200-dflash-adapter-e00vyqp7gxsr34wrtz"
REMOTE = "/home/glmrunner/gemma4-persistent-grouped-lm-head"
RESIDENT_CHECKPOINT = "/home/glmrunner/gemma4-fixed-m384-executor/checkpoint"
RATE = 2.45
AUTHORIZED_USD = 5.0
TARGET_SECONDS_PER_REQUEST = 0.500119281574996
PROJECT_DEADLINE = dt.datetime(2026, 7, 25, 21, 45, tzinfo=dt.timezone.utc)
MAX_CLAIM_SECONDS = 90 * 60
IMAGE = (
    "docker.io/lmsysorg/sglang@sha256:"
    "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
SOURCE_FILES = [
    "PROJECT.md",
    "DIRECTOR_BINDING.json",
    "grouped_lm_head.py",
    "exact_consumer_component.py",
    "counter_probe.py",
    "endpoint_pair.py",
    "remote_experiment.py",
    "sitecustomize.py",
    "token_trace_hook.py",
    "inputs/bound/CHECKPOINT_MANIFEST.json",
    "inputs/bound/CRITICAL_PATH_FINAL_TERMINAL.json",
    "inputs/bound/INTERVENTION_BINDING.json",
    "inputs/bound/QUALIFIED_LATEST_TERMINAL.json",
    "inputs/bound/TRACE_ANALYSIS_REPAIR.json",
    "inputs/bound/config.json",
    "inputs/bound/decode_equivalent_lm_head.py",
    "inputs/bound/endpoint_entrypoint.py",
    "inputs/bound/exact_runner.py",
    "inputs/bound/forward_batch_info.py",
    "inputs/bound/logits_processor.py",
    "inputs/bound/model.safetensors.index.json",
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    args: list[str], timeout: int | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
        env=env,
    )


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


def inventory_bench() -> dict[str, Any]:
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    if isinstance(benches, dict):
        return benches[BENCH]
    return next(row for row in benches if row["id"] == BENCH)


def predecessor_terminal() -> tuple[pathlib.Path, dict[str, Any]]:
    path = LAB / "projects" / PREDECESSOR / "MIXED_LOCAL_M384_TERMINAL.json"
    if not path.exists():
        raise RuntimeError("typed_queue_boundary:predecessor_terminal_missing")
    return path, json.loads(path.read_text())


def terminal_service_time(value: object) -> float | None:
    if isinstance(value, dict):
        for key in (
            "candidate_service_seconds_per_request",
            "service_seconds_per_request",
        ):
            item = value.get(key)
            if isinstance(item, (int, float)):
                return float(item)
        for item in value.values():
            found = terminal_service_time(item)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = terminal_service_time(item)
            if found is not None:
                return found
    return None


def check_gates() -> tuple[dict[str, Any], pathlib.Path, dict[str, Any]]:
    spend = json.loads((LAB / "runtime/spend_cap.json").read_text())
    reservation = spend.get("reservations", {}).get(NAME)
    if not reservation or float(reservation.get("authorized_usd", -1)) != 5.0:
        raise RuntimeError("typed_budget_boundary:exact_5_usd_reservation_missing")
    terminal_path, terminal = predecessor_terminal()
    if terminal.get("supersedes_grouped_lm_head") is True:
        raise RuntimeError("typed_scientific_boundary:predecessor_supersedes_mechanism")
    service = terminal_service_time(terminal)
    if service is not None and service <= TARGET_SECONDS_PER_REQUEST:
        raise RuntimeError(
            "typed_scientific_boundary:predecessor_already_meets_campaign_target"
        )
    bench = inventory_bench()
    if bench.get("status") != "available" or bench.get("claim"):
        raise RuntimeError("typed_queue_boundary:priority_8490_not_released")
    lifecycle = dt.datetime.fromisoformat(
        bench["lifecycle"]["deadline_utc"].replace("Z", "+00:00")
    )
    remaining = (lifecycle - dt.datetime.now(dt.timezone.utc)).total_seconds()
    if remaining < 60 * 60:
        raise RuntimeError("typed_lifecycle_boundary:less_than_60_minutes")
    if not KEY.is_file() or not KNOWN_HOSTS.is_file():
        raise RuntimeError("typed_identity_boundary:local_ssh_identity_missing")
    return bench, terminal_path, terminal


def ssh(ip: str, command: str, timeout: int) -> subprocess.CompletedProcess[str]:
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
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            f"glmrunner@{ip}",
            command,
        ],
        timeout=timeout,
    )


def scp_to(ip: str, source: pathlib.Path, target: str, timeout: int) -> None:
    result = run(
        [
            "scp",
            "-p",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            str(source),
            f"glmrunner@{ip}:{target}",
        ],
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"staging_copy_failed:{source.name}:{result.stderr[-800:]}")


def scp_from(ip: str, source: str, target: pathlib.Path, timeout: int) -> None:
    result = run(
        [
            "scp",
            "-p",
            "-i",
            str(KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            f"glmrunner@{ip}:{source}",
            str(target),
        ],
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"retrieval_copy_failed:{source}:{result.stderr[-800:]}")


def source_packet(artifact: pathlib.Path) -> tuple[pathlib.Path, dict[str, Any], str]:
    rows = []
    for relative in SOURCE_FILES:
        path = PROJECT / relative
        if not path.is_file():
            raise RuntimeError(f"source_packet_file_missing:{relative}")
        rows.append(
            {"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path)}
        )
    manifest = {"schema_version": 1, "files": rows}
    manifest_bytes = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode()
    identity = hashlib.sha256(manifest_bytes).hexdigest()
    manifest["identity_sha256"] = identity
    packet_root = artifact / "source-packets" / identity
    packet_root.mkdir(parents=True, exist_ok=True)
    manifest_path = packet_root / "SOURCE_MANIFEST.json"
    atomic(manifest_path, manifest)
    archive = packet_root / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for relative in SOURCE_FILES:
            bundle.add(PROJECT / relative, arcname=relative, recursive=False)
        bundle.add(manifest_path, arcname="SOURCE_MANIFEST.json", recursive=False)
    return archive, manifest, identity


def stage_source(
    ip: str, artifact: pathlib.Path
) -> tuple[dict[str, Any], pathlib.Path]:
    archive, manifest, identity = source_packet(artifact)
    archive_digest = sha256(archive)
    snapshot = f"{REMOTE}/snapshots/{identity}"
    match = ssh(
        ip,
        f"test -f {shlex.quote(snapshot + '/SOURCE_MANIFEST.json')} && "
        f"test \"$(sha256sum {shlex.quote(snapshot + '/SOURCE_MANIFEST.json')} | cut -d' ' -f1)\" = "
        f"{sha256(archive.parent / 'SOURCE_MANIFEST.json')}",
        120,
    )
    reused = match.returncode == 0
    if not reused:
        unexpected = ssh(ip, f"test -e {shlex.quote(snapshot)}", 30)
        if unexpected.returncode == 0:
            raise RuntimeError(f"source_snapshot_identity_mismatch:{identity}")
        remote_archive = f"{REMOTE}/source-{identity}.tar.gz.part"
        prepare = ssh(
            ip,
            f"install -d {shlex.quote(REMOTE + '/snapshots')} && "
            f"rm -f {shlex.quote(remote_archive)}",
            120,
        )
        if prepare.returncode:
            raise RuntimeError(f"source_stage_prepare:{prepare.stderr[-800:]}")
        scp_to(ip, archive, remote_archive, 600)
        temporary = snapshot + ".part"
        finalize = ssh(
            ip,
            f"test \"$(sha256sum {shlex.quote(remote_archive)} | cut -d' ' -f1)\" = "
            f"{archive_digest} && "
            f"rm -rf {shlex.quote(temporary)} && mkdir {shlex.quote(temporary)} && "
            f"tar -xzf {shlex.quote(remote_archive)} -C {shlex.quote(temporary)} && "
            f"chmod -R a-w {shlex.quote(temporary)} && "
            f"mv {shlex.quote(temporary)} {shlex.quote(snapshot)} && "
            f"rm -f {shlex.quote(remote_archive)}",
            600,
        )
        if finalize.returncode:
            raise RuntimeError(f"source_stage_finalize:{finalize.stderr[-800:]}")
    activate = ssh(
        ip,
        f"if test -L {shlex.quote(REMOTE + '/project')}; then "
        f"ln -sfn {shlex.quote(snapshot)} {shlex.quote(REMOTE + '/project')}; "
        f"elif test ! -e {shlex.quote(REMOTE + '/project')}; then "
        f"ln -s {shlex.quote(snapshot)} {shlex.quote(REMOTE + '/project')}; "
        "else exit 43; fi",
        120,
    )
    if activate.returncode:
        raise RuntimeError(f"source_activation_failed:{activate.returncode}")
    value = {
        "identity_sha256": identity,
        "archive_sha256": archive_digest,
        "remote_snapshot": snapshot,
        "reused": reused,
        "files": manifest["files"],
    }
    atomic(artifact / "SOURCE_STAGING.json", value)
    return value, archive.parent / "SOURCE_MANIFEST.json"


def remote_file_matches(
    ip: str, path: str, size: int, digest: str, timeout: int
) -> bool:
    result = ssh(
        ip,
        f"test -f {shlex.quote(path)} && "
        f"test \"$(stat -c %s {shlex.quote(path)})\" = {size} && "
        f"test \"$(sha256sum {shlex.quote(path)} | cut -d' ' -f1)\" = {digest}",
        timeout,
    )
    return result.returncode == 0


def stage_checkpoint(ip: str, artifact: pathlib.Path) -> dict[str, Any]:
    manifest = json.loads(
        (PROJECT / "inputs/bound/CHECKPOINT_MANIFEST.json").read_text()
    )
    prepare = ssh(
        ip,
        f"sudo install -d -o glmrunner -g glmrunner {shlex.quote(REMOTE + '/checkpoint')}",
        120,
    )
    if prepare.returncode:
        raise RuntimeError("checkpoint_directory_prepare_failed")
    rows = []
    for item in manifest["files"]:
        name = item["name"]
        size = int(item["bytes"])
        digest = item["sha256"]
        source = f"{RESIDENT_CHECKPOINT}/{name}"
        target = f"{REMOTE}/checkpoint/{name}"
        timeout = max(120, min(2400, size // 35_000_000 + 120))
        if remote_file_matches(ip, target, size, digest, timeout):
            rows.append({**item, "path": target, "reused": True})
            continue
        exists = ssh(ip, f"test -e {shlex.quote(target)}", 30)
        if exists.returncode == 0:
            raise RuntimeError(f"checkpoint_target_mismatch:{name}")
        if not remote_file_matches(ip, source, size, digest, timeout):
            raise RuntimeError(f"resident_checkpoint_mismatch:{name}")
        partial = f"{target}.{digest}.part"
        result = ssh(
            ip,
            f"sudo rm -f {shlex.quote(partial)} && "
            f"sudo ln {shlex.quote(source)} {shlex.quote(partial)} && "
            f"sudo chmod 0444 {shlex.quote(partial)} && "
            f"sudo mv {shlex.quote(partial)} {shlex.quote(target)}",
            120,
        )
        if result.returncode:
            raise RuntimeError(f"checkpoint_hardlink_failed:{name}")
        rows.append({**item, "path": target, "reused": False})
        atomic(
            artifact / "CHECKPOINT_STAGING_PROGRESS.json",
            {
                "schema_version": 1,
                "files": rows,
                "total_files": len(manifest["files"]),
            },
        )
    value = {
        "schema_version": 1,
        "total_bytes": manifest["total_bytes"],
        "files": rows,
        "materialization": "verified immutable hardlinks from resident predecessor snapshot",
    }
    atomic(artifact / "CHECKPOINT_STAGING.json", value)
    return value


def update_status(**updates: object) -> None:
    value = json.loads((PROJECT / "STATUS.json").read_text())
    value.update(updates)
    atomic(PROJECT / "STATUS.json", value)


def heartbeat(stop: threading.Event, artifact: pathlib.Path) -> None:
    while not stop.wait(60):
        result = pool("heartbeat", "--project", NAME)
        atomic(
            artifact / "OWNER_HEARTBEAT.json",
            {
                "at_utc": utc_now(),
                "returncode": result.returncode,
                "stdout": result.stdout[-1000:],
                "stderr": result.stderr[-1000:],
            },
        )


def compact_retrieval(ip: str, remote_artifact: str, artifact: pathlib.Path) -> None:
    paths = [
        "PERSISTENT_GROUPED_LM_HEAD_TERMINAL.json",
        "COMPONENT_PERSISTED.json",
        "PAIR_PERSISTED.json",
        "component/INVOCATION_STATE.json",
        "pair/INVOCATION_STATE.json",
        "REMOTE_EXCEPTION.json",
    ]
    compact = artifact / "compact"
    compact.mkdir(parents=True, exist_ok=True)
    for relative in paths:
        target = compact / relative.replace("/", "__")
        result = run(
            [
                "scp",
                "-p",
                "-i",
                str(KEY),
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                f"UserKnownHostsFile={KNOWN_HOSTS}",
                f"glmrunner@{ip}:{remote_artifact}/{relative}",
                str(target),
            ],
            timeout=300,
        )
        atomic(
            compact / (target.name + ".retrieval.json"),
            {
                "path": relative,
                "returncode": result.returncode,
                "stderr": result.stderr[-800:],
            },
        )


def full_retrieval(ip: str, remote_artifact: str, artifact: pathlib.Path) -> None:
    remote_archive = f"{REMOTE}/result.tar.gz"
    pack = ssh(
        ip,
        f"rm -f {shlex.quote(remote_archive + '.part')} && "
        f"tar -czf {shlex.quote(remote_archive + '.part')} "
        f"-C {shlex.quote(remote_artifact)} . && "
        f"mv {shlex.quote(remote_archive + '.part')} {shlex.quote(remote_archive)} && "
        f"sha256sum {shlex.quote(remote_archive)}",
        1800,
    )
    (artifact / "pack.stdout").write_text(pack.stdout)
    (artifact / "pack.stderr").write_text(pack.stderr)
    if pack.returncode:
        raise RuntimeError("typed_retrieval_boundary:remote_pack_failed")
    expected = pack.stdout.split()[0]
    partial = artifact / ".result.tar.gz.part"
    scp_from(ip, remote_archive, partial, 1800)
    if sha256(partial) != expected:
        raise RuntimeError("typed_retrieval_boundary:archive_hash_mismatch")
    archive = artifact / "result.tar.gz"
    partial.replace(archive)
    target = artifact / "retrieved"
    with tarfile.open(archive, "r:gz") as bundle:
        bundle.extractall(target, filter="data")


def invoke_remote(
    ip: str, remote_artifact: str, deadline: dt.datetime, artifact: pathlib.Path
) -> subprocess.CompletedProcess[str]:
    command = (
        f"install -d {shlex.quote(remote_artifact)} && "
        f"GROUPED_LM_HEAD_ARTIFACT_ROOT={shlex.quote(remote_artifact)} "
        f"GROUPED_LM_HEAD_DEADLINE_UTC={shlex.quote(deadline.isoformat())} "
        f"python3 {shlex.quote(REMOTE + '/project/remote_experiment.py')}"
    )
    remaining = int((deadline - dt.datetime.now(dt.timezone.utc)).total_seconds())
    result = ssh(ip, command, max(1, remaining))
    stamp = time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())
    (artifact / f"worker-{stamp}.stdout").write_text(result.stdout)
    (artifact / f"worker-{stamp}.stderr").write_text(result.stderr)
    atomic(
        artifact / f"worker-{stamp}.json",
        {"returncode": result.returncode, "at_utc": utc_now()},
    )
    return result


def repair_wait(
    artifact: pathlib.Path, deadline: dt.datetime, diagnostic: pathlib.Path
) -> bool:
    ready = run(
        [
            str(REPAIR),
            "ready",
            "--root",
            str(PROJECT),
            "--deadline",
            deadline.isoformat(),
            "--failure-kind",
            "recoverable_integration_or_consumer_defect",
            "--diagnostic",
            str(diagnostic),
            "--retry-scope",
            "Only the invalidated component, counter consumer, endpoint consumer, or retrieval operation; reuse persisted producer stages.",
        ]
    )
    (artifact / "repair-ready.stdout").write_text(ready.stdout)
    (artifact / "repair-ready.stderr").write_text(ready.stderr)
    if ready.returncode:
        return False
    remaining = int((deadline - dt.datetime.now(dt.timezone.utc)).total_seconds())
    if remaining <= 0:
        return False
    waited = run(
        [str(REPAIR), "wait", "--root", str(PROJECT), "--poll-seconds", "5"],
        timeout=remaining,
    )
    (artifact / "repair-wait.stdout").write_text(waited.stdout)
    (artifact / "repair-wait.stderr").write_text(waited.stderr)
    return waited.returncode == 0 and (PROJECT / "REPAIR_REQUEST.json").exists()


def release(
    artifact: pathlib.Path, condition: str, contents: dict[str, Any]
) -> dict[str, Any]:
    contents_path = artifact / "BENCH_CONTENTS.json"
    atomic(contents_path, contents)
    results = []
    for _ in range(2):
        result = pool(
            "release",
            "--project",
            NAME,
            "--condition",
            condition,
            "--contents",
            str(contents_path),
        )
        results.append(result)
        if result.returncode == 0:
            break
        time.sleep(2)
    (artifact / "release.stdout").write_text(
        "\n".join(item.stdout for item in results)
    )
    (artifact / "release.stderr").write_text(
        "\n".join(item.stderr for item in results)
    )
    return {
        "condition": condition,
        "returncode": result.returncode,
        "released": result.returncode == 0,
        "at_utc": utc_now(),
    }


def main() -> int:
    bench, predecessor_path, predecessor = check_gates()
    lifecycle = dt.datetime.fromisoformat(
        bench["lifecycle"]["deadline_utc"].replace("Z", "+00:00")
    )
    now = dt.datetime.now(dt.timezone.utc)
    deadline = min(
        PROJECT_DEADLINE,
        lifecycle - dt.timedelta(minutes=10),
        now + dt.timedelta(seconds=MAX_CLAIM_SECONDS),
    )
    if (deadline - now).total_seconds() < 60 * 60:
        raise RuntimeError("typed_lifecycle_boundary:claim_window_below_60_minutes")
    work_deadline = deadline - dt.timedelta(minutes=10)
    claim = pool("claim", "--project", NAME, "--bench", BENCH)
    if claim.returncode:
        raise RuntimeError(f"typed_pool_boundary:claim_failed:{claim.stderr[-800:]}")
    claimed_at = dt.datetime.now(dt.timezone.utc)
    stamp = claimed_at.strftime("%Y%m%dt%H%M%SZ").lower()
    artifact = PROJECT / "artifacts" / f"grouped-lm-head-{stamp}"
    artifact.mkdir(parents=True, exist_ok=False)
    (artifact / "claim.stdout").write_text(claim.stdout)
    (artifact / "claim.stderr").write_text(claim.stderr)
    ip = inventory_bench()["resource"]["public_ipv4"]
    stop = threading.Event()
    heartbeat_thread = threading.Thread(
        target=heartbeat, args=(stop, artifact), daemon=True
    )
    heartbeat_thread.start()
    remote_artifact = f"{REMOTE}/artifacts/{stamp}"
    source_state: dict[str, Any] = {}
    checkpoint_state: dict[str, Any] = {}
    scientific_terminal: dict[str, Any] | None = None
    release_state: dict[str, Any] | None = None
    owner_state = PROJECT / "OWNER_CONTROLLER.json"
    if owner_state.exists():
        owner = json.loads(owner_state.read_text())
        update_status(
            active_session={
                "artifact_root": str(artifact.relative_to(PROJECT)),
                "bench_id": BENCH,
                "deadline_utc": deadline.isoformat(),
                "expected_terminal": "PERSISTENT_GROUPED_LM_HEAD_TERMINAL.json",
                "forward_progress": "atomic claim complete; staging immutable source and checkpoint bytes",
                "unit": str(owner_state),
                "pid": owner["pid"],
                "start_ticks": owner["start_ticks"],
                "unit_manager": "pid",
            }
        )
    try:
        for prepare_attempt in range(2):
            try:
                source_state, _ = stage_source(ip, artifact)
                checkpoint_state = stage_checkpoint(ip, artifact)
                break
            except Exception as error:
                diagnostic = artifact / (
                    f"prepare-attempt-{prepare_attempt + 1}-diagnostic.json"
                )
                atomic(
                    diagnostic,
                    {
                        "schema_version": 1,
                        "classification": "recoverable_pre_science_staging_defect",
                        "error": f"{type(error).__name__}: {error}",
                        "attempt": prepare_attempt + 1,
                        "scientific_arms_consumed": False,
                    },
                )
                if prepare_attempt or not repair_wait(
                    artifact, work_deadline, diagnostic
                ):
                    raise
        atomic(
            artifact / "PREDECESSOR_GATE.json",
            {
                "path": str(predecessor_path),
                "sha256": sha256(predecessor_path),
                "terminal": predecessor,
            },
        )
        for attempt in range(2):
            try:
                result = invoke_remote(
                    ip, remote_artifact, work_deadline, artifact
                )
                worker_returncode: int | str = result.returncode
            except Exception as error:
                worker_returncode = f"{type(error).__name__}: {error}"
            compact_retrieval(ip, remote_artifact, artifact)
            remote_terminal = (
                artifact
                / "compact/PERSISTENT_GROUPED_LM_HEAD_TERMINAL.json"
            )
            if remote_terminal.exists():
                scientific_terminal = json.loads(remote_terminal.read_text())
                break
            diagnostic = artifact / f"attempt-{attempt + 1}-diagnostic.json"
            atomic(
                diagnostic,
                {
                    "schema_version": 1,
                    "classification": "recoverable_integration_or_consumer_defect",
                    "attempt": attempt + 1,
                    "worker_returncode": worker_returncode,
                    "compact_retrieval": [
                        path.name
                        for path in (artifact / "compact").glob("*")
                    ],
                },
            )
            if attempt or not repair_wait(
                artifact, work_deadline, diagnostic
            ):
                break
            stage_source(ip, artifact)
        if scientific_terminal is None:
            compact_retrieval(ip, remote_artifact, artifact)
            guest = ssh(
                ip,
                "sudo docker ps --no-trunc --format '{{json .}}'; "
                "nvidia-smi --query-compute-apps=pid,process_name,used_memory "
                "--format=csv,noheader,nounits",
                120,
            )
            (artifact / "guest-state.stdout").write_text(guest.stdout)
            (artifact / "guest-state.stderr").write_text(guest.stderr)
            elapsed = (
                dt.datetime.now(dt.timezone.utc) - claimed_at
            ).total_seconds()
            spend = min(AUTHORIZED_USD, max(0.0, elapsed) * RATE / 3600)
            update_status(
                actual_spend_usd=spend,
                summary="Claim retained through bounded repair but no scientific terminal became durable before disposition.",
            )
            boundary = {
                "schema_version": 1,
                "classification": "typed_external_or_repair_boundary",
                "result": "no_scientific_terminal",
                "actual_spend_usd": spend,
                "guest_state": str(
                    (artifact / "guest-state.stdout").relative_to(PROJECT)
                ),
            }
            release_state = release(
                artifact,
                "maintenance",
                {
                    "schema_version": 1,
                    "project": NAME,
                    "result": "repair_or_deadline_boundary",
                    "server_state": guest.stdout[-4000:],
                    "checkpoint": checkpoint_state,
                    "source": source_state,
                    "artifact": str(artifact.relative_to(PROJECT)),
                },
            )
            boundary["bench_release"] = release_state
            atomic(PROJECT / "PERSISTENT_GROUPED_LM_HEAD_TERMINAL.json", boundary)
            update_status(
                status="complete",
                active_session=None,
                decision="typed_external_or_repair_boundary",
                terminal_artifact="PERSISTENT_GROUPED_LM_HEAD_TERMINAL.json",
            )
            return 2
        for retrieval_attempt in range(2):
            try:
                full_retrieval(ip, remote_artifact, artifact)
                break
            except Exception as error:
                diagnostic = artifact / (
                    f"retrieval-attempt-{retrieval_attempt + 1}-diagnostic.json"
                )
                atomic(
                    diagnostic,
                    {
                        "schema_version": 1,
                        "classification": "recoverable_retrieval_defect",
                        "error": f"{type(error).__name__}: {error}",
                        "scientific_terminal_preserved": True,
                    },
                )
                if retrieval_attempt or not repair_wait(
                    artifact, work_deadline, diagnostic
                ):
                    raise
        elapsed = (
            dt.datetime.now(dt.timezone.utc) - claimed_at
        ).total_seconds()
        spend = min(AUTHORIZED_USD, max(0.0, elapsed) * RATE / 3600)
        update_status(actual_spend_usd=spend)
        contents = {
            "schema_version": 1,
            "project": NAME,
            "result": scientific_terminal.get("result"),
            "artifact": str(artifact.relative_to(PROJECT)),
            "source": source_state,
            "checkpoint": checkpoint_state,
            "image": IMAGE,
            "server_state": "No experiment server or worker remains; checkpoint hardlinks, image, compiler, and CUDA caches retained.",
            "next": "Available for a compatible director-selected H200 project.",
            "actual_spend_usd": spend,
        }
        release_state = release(artifact, "ready", contents)
        if not release_state["released"]:
            raise RuntimeError("typed_pool_boundary:ready_release_failed")
        final = {
            **scientific_terminal,
            "provider": {
                "bench_id": BENCH,
                "claimed_at_utc": claimed_at.isoformat(),
                "completed_at_utc": utc_now(),
                "hourly_rate_usd": RATE,
                "actual_spend_usd": spend,
                "release": release_state,
            },
            "source": source_state,
            "checkpoint": checkpoint_state,
            "artifact_root": str(artifact.relative_to(PROJECT)),
        }
        atomic(PROJECT / "PERSISTENT_GROUPED_LM_HEAD_TERMINAL.json", final)
        update_status(
            status="complete",
            active_session=None,
            summary=(
                "Bound grouped LM-head experiment reached a scientific terminal "
                f"with result {scientific_terminal.get('result')}."
            ),
            decision=scientific_terminal.get("result"),
            terminal_artifact="PERSISTENT_GROUPED_LM_HEAD_TERMINAL.json",
        )
        return 0 if scientific_terminal.get("result") == "positive" else 2
    except Exception as error:
        try:
            compact_retrieval(ip, remote_artifact, artifact)
        except Exception:
            pass
        guest = ssh(
            ip,
            "sudo docker ps --no-trunc --format '{{json .}}'; "
            "nvidia-smi --query-compute-apps=pid,process_name,used_memory "
            "--format=csv,noheader,nounits",
            120,
        )
        (artifact / "unhandled-guest-state.stdout").write_text(guest.stdout)
        (artifact / "unhandled-guest-state.stderr").write_text(guest.stderr)
        elapsed = (
            dt.datetime.now(dt.timezone.utc) - claimed_at
        ).total_seconds()
        spend = min(AUTHORIZED_USD, max(0.0, elapsed) * RATE / 3600)
        update_status(actual_spend_usd=spend)
        release_state = release(
            artifact,
            "maintenance",
            {
                "schema_version": 1,
                "project": NAME,
                "result": "controller_or_repair_boundary",
                "error": f"{type(error).__name__}: {error}",
                "server_state": guest.stdout[-4000:],
                "checkpoint": checkpoint_state,
                "source": source_state,
                "artifact": str(artifact.relative_to(PROJECT)),
                "actual_spend_usd": spend,
            },
        )
        boundary = {
            "schema_version": 1,
            "classification": "typed_controller_or_repair_boundary",
            "result": "no_scientific_terminal"
            if scientific_terminal is None
            else scientific_terminal.get("result"),
            "error": f"{type(error).__name__}: {error}",
            "actual_spend_usd": spend,
            "scientific_terminal": scientific_terminal,
            "bench_release": release_state,
            "artifact_root": str(artifact.relative_to(PROJECT)),
        }
        atomic(PROJECT / "PERSISTENT_GROUPED_LM_HEAD_TERMINAL.json", boundary)
        update_status(
            status="complete",
            active_session=None,
            decision="typed_controller_or_repair_boundary",
            terminal_artifact="PERSISTENT_GROUPED_LM_HEAD_TERMINAL.json",
        )
        return 2
    finally:
        stop.set()
        heartbeat_thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
