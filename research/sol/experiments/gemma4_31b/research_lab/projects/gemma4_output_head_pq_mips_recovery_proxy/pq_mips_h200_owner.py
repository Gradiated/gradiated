#!/usr/bin/env python3
"""Bounded durable owner for the reserved warm-H200 PQ-MIPS experiment."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from typing import Any

PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parent.parent
FACTORY = PROJECT.parents[5] / "factory"
POOL = [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
REPAIR = FACTORY / "tools" / "repair-handshake"
PROJECT_ID = "gemma4_output_head_pq_mips_recovery_proxy"
BENCH_ID = "h200-qkv-endpoint-computeinstance-e00qxw871hz1r79fjt"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"json_object_required:{path}")
    return value


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    json.loads(temporary.read_text())
    temporary.replace(path)


def run(command: list[str], timeout: float, evidence: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=max(1, timeout),
        check=False,
        env={**os.environ, "PYTHONPATH": str(FACTORY / "src")},
    )
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(result.stdout)
    evidence.with_suffix(evidence.suffix + ".stderr").write_text(result.stderr)
    return result


def remaining(deadline: float, cap: float) -> float:
    value = min(cap, deadline - time.time())
    if value <= 0:
        raise TimeoutError("absolute_owner_deadline_reached")
    return value


def validate_packet(ready_path: Path) -> dict[str, Any]:
    ready = load(ready_path)
    packet = ready["packet"]
    root = PROJECT / packet["root"]
    manifest_path = PROJECT / packet["manifest"]
    archive = PROJECT / packet["archive"]
    weight = PROJECT / packet["weight_snapshot"]["path"]
    checks = {
        "ready_project": ready.get("project") == PROJECT_ID,
        "ready_claim_false": ready.get("claim_allowed") is False,
        "manifest_hash": sha(manifest_path) == packet["manifest_sha256"],
        "archive_hash": sha(archive) == packet["archive_sha256"],
        "weight_hash": sha(weight) == packet["weight_snapshot"]["sha256"],
        "owner_hash": sha(Path(__file__).resolve()) == ready["source_hashes"]["owner"],
        "worker_hash": sha(PROJECT / "pq_mips_h200_worker.py")
        == ready["source_hashes"]["worker"],
    }
    manifest = load(manifest_path)
    checks["packet_identity"] = (
        manifest["packet_identity_sha256"] == packet["identity_sha256"]
    )
    for row in manifest["files"]:
        source = root / row["path"]
        checks[f"member:{row['path']}"] = (
            source.is_file()
            and source.stat().st_size == row["bytes"]
            and sha(source) == row["sha256"]
        )
    with tarfile.open(archive, "r") as bundle:
        names = sorted(item.name for item in bundle if item.isfile())
        checks["archive_members"] = names == sorted(
            ["PACKET_MANIFEST.json", *[row["path"] for row in manifest["files"]]]
        )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"offline_packet_validation_failed:{failed}")
    return {
        "ready": ready,
        "manifest": manifest,
        "root": root,
        "manifest_path": manifest_path,
        "archive": archive,
        "weight": weight,
        "checks": checks,
    }


def validate_authority(path: Path, ready_path: Path, packet: dict[str, Any]) -> dict[str, Any]:
    authority = load(path)
    start_by = dt.datetime.fromisoformat(
        authority["lifecycle"]["claim_start_by_utc"].replace("Z", "+00:00")
    ).timestamp()
    deadline = dt.datetime.fromisoformat(
        authority["lifecycle"]["owner_deadline_utc"].replace("Z", "+00:00")
    ).timestamp()
    if not (
        authority.get("project") == PROJECT_ID
        and authority.get("gpu_claim_allowed") is True
        and authority.get("bench", {}).get("id") == BENCH_ID
        and authority.get("source_ready", {}).get("sha256") == sha(ready_path)
        and authority.get("source_ready", {}).get("packet_identity_sha256")
        == packet["ready"]["packet"]["identity_sha256"]
        and time.time() < start_by < deadline
    ):
        raise RuntimeError("later_director_claim_authority_invalid_or_expired")
    return authority


def pool(output: Path, deadline: float, *arguments: str) -> dict[str, Any]:
    result = run([*POOL, *arguments], remaining(deadline, 60), output)
    if result.returncode:
        raise RuntimeError(f"gpu_pool_command_failed:{arguments[0]}")
    return json.loads(result.stdout)


def heartbeat(stop: threading.Event, output: Path, deadline: float) -> None:
    while not stop.wait(20):
        if time.time() >= deadline:
            return
        result = run(
            [*POOL, "heartbeat", "--project", PROJECT_ID],
            min(30, max(1, deadline - time.time())),
            output / "heartbeat.latest",
        )
        if result.returncode:
            atomic(
                output / "HEARTBEAT_FAILURE.json",
                {"returncode": result.returncode, "at_epoch": time.time()},
            )


def ssh_parts(bench: dict[str, Any]) -> tuple[list[str], str]:
    resource = bench["resource"]
    key = Path(resource["ssh_identity_path"])
    known = Path(resource["known_hosts_namespace"])
    if not key.is_file() or not known.is_file():
        raise RuntimeError("established_ssh_identity_missing")
    destination = f"{resource['ssh_user']}@{resource['public_ipv4']}"
    return (
        [
            "ssh",
            "-i",
            str(key),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={known}",
        ],
        destination,
    )


def remote(
    ssh: list[str],
    destination: str,
    shell: str,
    deadline: float,
    evidence: Path,
    cap: float = 600,
) -> subprocess.CompletedProcess[str]:
    return run([*ssh, destination, shell], remaining(deadline, cap), evidence)


def scp(
    ssh: list[str],
    destination: str,
    source: str,
    target: str,
    deadline: float,
    evidence: Path,
    from_remote: bool = False,
) -> subprocess.CompletedProcess[str]:
    options = ssh[1:]
    command = (
        ["scp", *options, f"{destination}:{source}", target]
        if from_remote
        else ["scp", *options, source, f"{destination}:{target}"]
    )
    return run(command, remaining(deadline, 900), evidence)


def stage_file(
    ssh: list[str],
    destination: str,
    source: Path,
    target: str,
    digest: str,
    deadline: float,
    evidence: Path,
) -> None:
    temporary = f"{target}.{digest}.part"
    match = (
        f"test -f {shlex.quote(target)} && "
        f"test \"$(stat -c %s {shlex.quote(target)})\" = {source.stat().st_size} && "
        f"test \"$(sha256sum {shlex.quote(target)} | cut -d' ' -f1)\" = {digest}"
    )
    if remote(ssh, destination, match, deadline, evidence.with_name(evidence.name + ".match"), 300).returncode == 0:
        return
    remote(
        ssh,
        destination,
        f"rm -f {shlex.quote(temporary)}",
        deadline,
        evidence.with_name(evidence.name + ".clean"),
        60,
    )
    if scp(
        ssh,
        destination,
        str(source),
        temporary,
        deadline,
        evidence.with_name(evidence.name + ".copy"),
    ).returncode:
        raise RuntimeError(f"immutable_stage_copy_failed:{source.name}")
    finalize = (
        f"test \"$(stat -c %s {shlex.quote(temporary)})\" = {source.stat().st_size} && "
        f"test \"$(sha256sum {shlex.quote(temporary)} | cut -d' ' -f1)\" = {digest} && "
        f"chmod 0444 {shlex.quote(temporary)} && mv {shlex.quote(temporary)} {shlex.quote(target)}"
    )
    if remote(ssh, destination, finalize, deadline, evidence.with_name(evidence.name + ".finalize"), 300).returncode:
        raise RuntimeError(f"immutable_stage_finalize_failed:{source.name}")


def retrieve_compact(
    ssh: list[str],
    destination: str,
    remote_output: str,
    local: Path,
    deadline: float,
) -> None:
    local.mkdir(parents=True, exist_ok=True)
    names = (
        "PRODUCER_STARTED.json",
        "PRODUCER_TERMINAL.json",
        "SCIENCE_STARTED.json",
        "OUTPUT_HEAD_PQ_MIPS_H200_TERMINAL.json",
        "worker.stdout",
        "worker.stderr",
    )
    for name in names:
        probe = remote(
            ssh,
            destination,
            f"test -f {shlex.quote(remote_output + '/' + name)}",
            deadline,
            local / f"{name}.probe",
            30,
        )
        if probe.returncode == 0:
            scp(
                ssh,
                destination,
                remote_output + "/" + name,
                str(local / name),
                deadline,
                local / f"{name}.retrieve",
                from_remote=True,
            )


def terminal_complete(path: Path, producer: Path) -> bool:
    value = load(path)
    producer_value = load(producer)
    points = value.get("correctness", {}).get("operating_points", [])
    return bool(
        value.get("classification")
        in {
            "typed_h200_positive_pq_mips_capture_recall_and_traffic",
            "typed_h200_falsification_fixed_pq_mips_capture_recall",
        }
        and value.get("science_started") is True
        and value.get("scientific_samples_consumed") == 1
        and value.get("producer_terminal_sha256") == sha(producer)
        and producer_value.get("classification")
        == "deterministic_vectorized_pq_producer_complete"
        and producer_value.get("producer_consumed") is True
        and producer_value.get("science_started") is False
        and producer_value.get("cpu_reference", {}).get("pass") is True
        and producer_value.get("geometry", {}).get("weight_shape") == [262144, 5376]
        and producer_value.get("geometry", {}).get("subspaces") == 2688
        and producer_value.get("geometry", {}).get("dimensions_per_subspace") == 2
        and producer_value.get("geometry", {}).get("codebook_rows") == 256
        and value.get("identities", {}).get("tied_weight_tensor")
        == "1053f051b1b894bb5f80eb52cdd434b8028aaad27c3006fcfdec48ac8c46d98d"
        and value.get("identities", {}).get("source_weight_shard")
        == "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa"
        and value.get("geometry", {}).get("weight_shape") == [262144, 5376]
        and value.get("geometry", {}).get("shortlist_sizes") == [256, 1024, 4096]
        and len(value.get("geometry", {}).get("selected_batch_rows", [])) == 2
        and [row.get("shortlist_size") for row in points] == [256, 1024, 4096]
        and all(len(row.get("batches", [])) == 2 for row in points)
        and set(
            value.get("h200_component_seconds", {})
            .get("exact_union_rescore_by_shortlist", {})
            .keys()
        )
        == {"256", "1024", "4096"}
        and all(
            "traffic" in batch
            and "physical_union_rows" in batch
            and "exact_rescore_greedy_agreement" in batch
            and "complete_stock_candidate_recall" in batch
            for row in points
            for batch in row["batches"]
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready", type=Path, default=PROJECT / "PQ_MIPS_H200_PRODUCER_READY.json")
    parser.add_argument("--authority", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--offline-validate", action="store_true")
    args = parser.parse_args()
    packet = validate_packet(args.ready)
    if args.offline_validate:
        print(json.dumps({"pass": True, "checks": packet["checks"]}, sort_keys=True))
        return 0
    if args.authority is None or args.output is None:
        parser.error("--authority and --output are required for execution")
    authority = validate_authority(args.authority, args.ready, packet)
    deadline = dt.datetime.fromisoformat(
        authority["lifecycle"]["owner_deadline_utc"].replace("Z", "+00:00")
    ).timestamp()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    atomic(
        output / "OWNER_BINDING.json",
        {
            "owner_sha256": sha(Path(__file__).resolve()),
            "ready_sha256": sha(args.ready),
            "authority_sha256": sha(args.authority),
            "absolute_deadline_utc": authority["lifecycle"]["owner_deadline_utc"],
        },
    )
    claim = pool(
        output / "claim.stdout",
        deadline,
        "claim",
        "--project",
        PROJECT_ID,
        "--bench",
        BENCH_ID,
    )
    bench = pool(output / "bench.stdout", deadline, "show", "--bench", BENCH_ID)
    if bench.get("claim", {}).get("project") != PROJECT_ID:
        raise RuntimeError("claimed_bench_ownership_mismatch")
    claimed_at = bench["claim"]["claimed_at"]
    ssh, destination = ssh_parts(bench)
    stop = threading.Event()
    heart = threading.Thread(target=heartbeat, args=(stop, output, deadline), daemon=True)
    heart.start()
    remote_root = f"/home/glmrunner/pq-mips-h200/{packet['ready']['packet']['identity_sha256']}"
    remote_packet = remote_root + "/packet"
    remote_weight = remote_root + "/weight/tied_output_weight.safetensors"
    remote_output = remote_root + "/output"
    prepare = (
        f"mkdir -p {shlex.quote(remote_root + '/weight')} {shlex.quote(remote_output)}"
    )
    if remote(ssh, destination, prepare, deadline, output / "remote-prepare").returncode:
        raise RuntimeError("remote_root_prepare_failed")
    archive_target = remote_root + "/packet.tar"
    stage_file(
        ssh,
        destination,
        packet["archive"],
        archive_target,
        packet["ready"]["packet"]["archive_sha256"],
        deadline,
        output / "stage-packet",
    )
    extract = (
        f"rm -rf {shlex.quote(remote_packet + '.part')} && "
        f"mkdir -p {shlex.quote(remote_packet + '.part')} && "
        f"tar -xf {shlex.quote(archive_target)} -C {shlex.quote(remote_packet + '.part')} && "
        f"rm -rf {shlex.quote(remote_packet)} && mv {shlex.quote(remote_packet + '.part')} {shlex.quote(remote_packet)}"
    )
    if remote(ssh, destination, extract, deadline, output / "extract-packet", 300).returncode:
        raise RuntimeError("remote_packet_extract_failed")
    weight_row = packet["ready"]["packet"]["weight_snapshot"]
    stage_file(
        ssh,
        destination,
        packet["weight"],
        remote_weight,
        weight_row["sha256"],
        deadline,
        output / "stage-weight",
    )
    generation = 0
    released = False
    try:
        while time.time() < deadline:
            resume = remote(
                ssh,
                destination,
                f"test -f {shlex.quote(remote_output + '/PRODUCER_TERMINAL.json')}",
                deadline,
                output / f"attempt-{generation}.producer-probe",
                30,
            ).returncode == 0
            worker = packet["manifest"]["worker_command"]
            command = [
                "sudo",
                "-n",
                "docker",
                "run",
                "--rm",
                "--gpus",
                "all",
                "--ipc=host",
                "--entrypoint",
                "python3",
                "-v",
                f"{remote_packet}:/work/input:ro",
                "-v",
                f"{remote_root}/weight:/work/weight:ro",
                "-v",
                f"{remote_output}:/work/output",
                IMAGE,
                *worker[1:],
                *(["--resume-producer"] if resume else []),
            ]
            shell = (
                f"{shlex.join(command)} >{shlex.quote(remote_output + '/worker.stdout')} "
                f"2>{shlex.quote(remote_output + '/worker.stderr')}"
            )
            result = remote(
                ssh,
                destination,
                shell,
                deadline,
                output / f"attempt-{generation}.worker",
                max(60, deadline - time.time()),
            )
            retrieve_compact(
                ssh,
                destination,
                remote_output,
                output / f"attempt-{generation}.compact",
                deadline,
            )
            compact = output / f"attempt-{generation}.compact"
            terminal = compact / "OUTPUT_HEAD_PQ_MIPS_H200_TERMINAL.json"
            producer = compact / "PRODUCER_TERMINAL.json"
            if (
                result.returncode == 0
                and terminal.is_file()
                and producer.is_file()
                and terminal_complete(terminal, producer)
            ):
                contents = output / "BENCH_CONTENTS.json"
                atomic(
                    contents,
                    {
                        "schema_version": 1,
                        "state": "pq_mips_h200_science_complete_unoccupied",
                        "project": PROJECT_ID,
                        "artifacts": f"terminal {sha(terminal)} producer {sha(producer)}",
                        "checkpoint": "Exact checkpoint and caches remain resident.",
                        "image": IMAGE,
                        "server_state": "No server or container remains; accelerator is expected unoccupied.",
                        "next": "Ready for director-selected successor.",
                    },
                )
                pool(
                    output / "release.stdout",
                    deadline,
                    "release",
                    "--project",
                    PROJECT_ID,
                    "--bench",
                    BENCH_ID,
                    "--expected-claimed-at",
                    claimed_at,
                    "--condition",
                    "ready",
                    "--contents",
                    str(contents),
                )
                released = True
                atomic(output / "TERMINAL.json", load(terminal))
                return 0
            repair_id = f"pq-mips-{generation}-{time.time_ns()}"
            scope = (
                "held_out_consumer_from_persisted_producer"
                if producer.is_file()
                else "unconsumed_vectorized_producer"
            )
            ready = run(
                [
                    str(REPAIR),
                    "ready",
                    "--root",
                    str(output),
                    "--repair-id",
                    repair_id,
                    "--deadline",
                    authority["lifecycle"]["owner_deadline_utc"],
                    "--failure-kind",
                    "recoverable_worker_or_retrieval_defect",
                    "--diagnostic",
                    str(compact),
                    "--retry-scope",
                    scope,
                ],
                remaining(deadline, 30),
                output / f"{repair_id}.ready",
            )
            if ready.returncode:
                raise RuntimeError("repair_handshake_ready_failed")
            waited = run(
                [
                    str(REPAIR),
                    "wait",
                    "--root",
                    str(output),
                    "--repair-id",
                    repair_id,
                    "--deadline",
                    authority["lifecycle"]["owner_deadline_utc"],
                    "--poll-seconds",
                    "5",
                ],
                remaining(deadline, deadline - time.time()),
                output / f"{repair_id}.wait",
            )
            if waited.returncode:
                break
            status = json.loads(waited.stdout)
            if status.get("state") != "requested":
                break
            patch = Path(status["request"]["patch_artifact"])
            if not patch.is_file():
                raise RuntimeError("repair_patch_artifact_missing")
            stage_file(
                ssh,
                destination,
                patch,
                remote_root + f"/repair-{generation}.tar",
                sha(patch),
                deadline,
                output / f"repair-{generation}.stage",
            )
            patch_shell = (
                f"tar -xf {shlex.quote(remote_root + f'/repair-{generation}.tar')} "
                f"-C {shlex.quote(remote_packet)}"
            )
            if remote(ssh, destination, patch_shell, deadline, output / f"repair-{generation}.apply", 120).returncode:
                raise RuntimeError("repair_patch_apply_failed")
            generation += 1
        retrieve_compact(ssh, destination, remote_output, output / "deadline-compact", deadline)
        contents = output / "BENCH_CONTENTS.json"
        atomic(
            contents,
            {
                "schema_version": 1,
                "state": "pq_mips_owner_deadline_maintenance",
                "project": PROJECT_ID,
                "artifacts": str(output / "deadline-compact"),
                "checkpoint": "Exact checkpoint and PQ project inputs remain resident.",
                "image": IMAGE,
                "server_state": "Worker container exited or was fenced by the owner deadline.",
                "next": "Director disposition required from compact producer/science markers.",
            },
        )
        pool(
            output / "release-maintenance.stdout",
            deadline + 120,
            "release",
            "--project",
            PROJECT_ID,
            "--bench",
            BENCH_ID,
            "--expected-claimed-at",
            claimed_at,
            "--condition",
            "maintenance",
            "--contents",
            str(contents),
        )
        released = True
        return 2
    finally:
        stop.set()
        heart.join(5)
        if not released:
            atomic(
                output / "OWNER_EXIT_WITH_LIVE_CLAIM.json",
                {
                    "classification": "owner_exception_claim_retained_for_repair",
                    "claimed_at": claimed_at,
                    "at_epoch": time.time(),
                },
            )


if __name__ == "__main__":
    raise SystemExit(main())
