#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tarfile
import threading
import time


NAME = "gemma4_l40s_awq_bf16_group_scale_consumer"
PREDECESSOR = "gemma4_l40s_qserve_kv4_attention_component"
BENCH = "l40s-qserve-e00a74kcbps8v00fk4"
LAB = pathlib.Path(
    "/root/workspace/research/sol/experiments/gemma4_31b/research_lab"
)
PROJECT = LAB / "projects" / NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path(
    "/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius"
)
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
REMOTE_ROOT = "/home/glmrunner/gemma4-exact-awq-consumer"
RATE = 0.8629833
AUTHORIZED_USD = 8.0
PRIOR_SPEND_USD = 0.0


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, **kwargs)


def pool(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            "-m",
            "grad_research.gpu_pool",
            "--lab",
            str(LAB),
            *arguments,
        ],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
        capture_output=True,
        check=check,
    )


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--deadline-epoch", type=int, required=True)
    parser.add_argument("--resume-retrieval", action="store_true")
    args = parser.parse_args()
    args.artifact_root = args.artifact_root.resolve()
    args.artifact_root.mkdir(parents=True, exist_ok=args.resume_retrieval)
    events = args.artifact_root / "outer-events.jsonl"

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(
                json.dumps(
                    {"epoch": time.time(), "event": event, **fields},
                    sort_keys=True,
                )
                + "\n"
            )
            handle.flush()

    packet = (PROJECT / "EXACT_CONSUMER_PACKET.tar.gz").resolve()
    data_packet = (PROJECT / "EXACT_CONSUMER_DATA.tar.gz").resolve()
    manifest = (PROJECT / "EXACT_CONSUMER_GPU_INPUT_MANIFEST.json").resolve()
    packet_hash = sha256(packet)
    data_packet_hash = sha256(data_packet)
    manifest_hash = sha256(manifest)
    packet_digest = (PROJECT / "EXACT_CONSUMER_PACKET.sha256").read_text().split()[0]
    data_packet_digest = (
        PROJECT / "EXACT_CONSUMER_DATA.sha256"
    ).read_text().split()[0]
    if packet_hash != packet_digest:
        raise RuntimeError("project_local_packet_identity_mismatch")
    if data_packet_hash != data_packet_digest:
        raise RuntimeError("project_local_data_packet_identity_mismatch")
    with tarfile.open(packet, "r:gz") as archive:
        names = set(archive.getnames())
    if "EXACT_CONSUMER_GPU_INPUT_MANIFEST.json" not in names:
        raise RuntimeError("project_local_packet_missing_manifest")

    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = (
        benches[BENCH]
        if isinstance(benches, dict)
        else next(row for row in benches if row["id"] == BENCH)
    )
    if bench["accelerator"] != "nvidia-l40s":
        raise RuntimeError("typed_pool_boundary:bench_not_l40s")
    if float(bench["hourly_cost_usd"]) != RATE:
        raise RuntimeError("typed_pool_boundary:rate_changed")
    predecessor = json.loads(
        (LAB / "projects" / PREDECESSOR / "STATUS.json").read_text()
    )
    if (
        predecessor.get("status") == "active"
        or bench.get("claim") is not None
        or bench.get("status") != "available"
    ):
        atomic(
            args.artifact_root / "QUEUE_BLOCKER.json",
            {
                "schema_version": 1,
                "classification": "typed_external_queue_blocker",
                "predecessor": PREDECESSOR,
                "predecessor_status": predecessor.get("status"),
                "bench_status": bench.get("status"),
                "bench_claim": bench.get("claim"),
            },
        )
        return 76
    lifecycle_deadline = datetime.datetime.fromisoformat(
        bench["lifecycle"]["deadline_utc"].replace("Z", "+00:00")
    ).timestamp()
    remaining_seconds = int((AUTHORIZED_USD - PRIOR_SPEND_USD) * 3600 / RATE)
    deadline = min(
        args.deadline_epoch,
        int(time.time()) + remaining_seconds,
        int(lifecycle_deadline) - 120,
    )
    if deadline <= time.time() + 900:
        atomic(
            args.artifact_root / "LIFECYCLE_BLOCKER.json",
            {
                "schema_version": 1,
                "classification": "typed_external_lifecycle_blocker",
                "watchdog_deadline_utc": bench["lifecycle"]["deadline_utc"],
                "minimum_required_seconds": 900,
                "available_seconds": lifecycle_deadline - time.time(),
            },
        )
        return 77

    claimed = False
    stop = threading.Event()
    release_condition: str | None = None
    release_contents: dict[str, object] = {}
    started = time.time()

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME, check=False)
            emit(
                "heartbeat",
                returncode=result.returncode,
                stderr=result.stderr[-1200:],
            )

    thread = threading.Thread(target=heartbeat, daemon=True)

    try:
        lease = max(900, deadline - int(time.time()))
        result = pool(
            "claim",
            "--project",
            NAME,
            "--bench",
            BENCH,
            "--lease-seconds",
            str(lease),
        )
        claimed = True
        emit("claimed", lease_seconds=lease, result=json.loads(result.stdout))
        thread.start()

        sys.path.insert(0, str(NEBIUS))
        from placement_control import extract_public_ipv4, get_instance
        from stock_control import run_ssh

        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip:
            raise RuntimeError("typed_provider_boundary:no_public_ip")
        identity = run_ssh(
            ip,
            KEY,
            "hostname; nvidia-smi --query-gpu=name,uuid,memory.total "
            "--format=csv,noheader; df -h /; sudo docker image inspect "
            + shlex.quote(IMAGE)
            + " >/dev/null && printf image_present",
            timeout=90,
        )
        (args.artifact_root / "remote-identity.stdout").write_text(identity.stdout)
        (args.artifact_root / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_remote_boundary:identity_or_image_failed")
        compute = run_ssh(
            ip,
            KEY,
            "nvidia-smi --query-compute-apps=pid,used_memory "
            "--format=csv,noheader,nounits",
            timeout=60,
        )
        (args.artifact_root / "remote-compute.stdout").write_text(
            compute.stdout
        )
        (args.artifact_root / "remote-compute.stderr").write_text(
            compute.stderr
        )
        if compute.returncode:
            raise RuntimeError("typed_remote_boundary:compute_query_failed")
        if compute.stdout.strip():
            raise RuntimeError(
                "typed_resident_state_boundary:compute_process_remains"
            )

        remote_packet = f"{REMOTE_ROOT}/packets/{packet_hash}.tar.gz"
        remote_packet_part = f"{remote_packet}.part"
        remote_data_packet = (
            f"{REMOTE_ROOT}/packets/{data_packet_hash}.data.tar.gz"
        )
        remote_data_packet_part = f"{remote_data_packet}.part"
        remote_run = f"{REMOTE_ROOT}/runs/{packet_hash}"
        remote_output = f"{REMOTE_ROOT}/outputs/{args.artifact_root.name}"
        prepared = run_ssh(
            ip,
            KEY,
            "mkdir -p "
            + " ".join(
                shlex.quote(path)
                for path in (
                    f"{REMOTE_ROOT}/packets",
                    f"{REMOTE_ROOT}/runs",
                    remote_output,
                )
            ),
            timeout=60,
        )
        if prepared.returncode:
            raise RuntimeError("typed_remote_boundary:prepare_failed")
        matched = run_ssh(
            ip,
            KEY,
            f"test -f {shlex.quote(remote_packet)} && "
            f"test \"$(sha256sum {shlex.quote(remote_packet)} | awk '{{print $1}}')\" "
            f"= {packet_hash}",
            timeout=60,
        )
        if matched.returncode:
            copied = run(
                [
                    "scp",
                    "-i",
                    str(KEY),
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    "-o",
                    f"UserKnownHostsFile={KNOWN_HOSTS}",
                    str(packet),
                    f"glmrunner@{ip}:{remote_packet_part}",
                ],
                capture_output=True,
                timeout=300,
            )
            (args.artifact_root / "packet-transfer.stderr").write_text(copied.stderr)
            if copied.returncode:
                raise RuntimeError("typed_transfer_boundary:packet_scp_failed")
            finalized = run_ssh(
                ip,
                KEY,
                f"test \"$(sha256sum {shlex.quote(remote_packet_part)} | "
                f"awk '{{print $1}}')\" = {packet_hash} && "
                f"chmod 0444 {shlex.quote(remote_packet_part)} && "
                f"mv {shlex.quote(remote_packet_part)} {shlex.quote(remote_packet)}",
                timeout=60,
            )
            if finalized.returncode:
                raise RuntimeError("typed_transfer_boundary:packet_finalize_failed")
        data_matched = run_ssh(
            ip,
            KEY,
            f"test -f {shlex.quote(remote_data_packet)} && "
            f"test \"$(sha256sum {shlex.quote(remote_data_packet)} | "
            f"awk '{{print $1}}')\" = {data_packet_hash}",
            timeout=60,
        )
        if data_matched.returncode:
            data_copied = run(
                [
                    "scp",
                    "-i",
                    str(KEY),
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    "-o",
                    f"UserKnownHostsFile={KNOWN_HOSTS}",
                    str(data_packet),
                    f"glmrunner@{ip}:{remote_data_packet_part}",
                ],
                capture_output=True,
                timeout=600,
            )
            (args.artifact_root / "data-transfer.stderr").write_text(
                data_copied.stderr
            )
            if data_copied.returncode:
                raise RuntimeError(
                    "typed_transfer_boundary:data_packet_scp_failed"
                )
            data_finalized = run_ssh(
                ip,
                KEY,
                f"test \"$(sha256sum "
                f"{shlex.quote(remote_data_packet_part)} | "
                f"awk '{{print $1}}')\" = {data_packet_hash} && "
                f"chmod 0444 {shlex.quote(remote_data_packet_part)} && "
                f"mv {shlex.quote(remote_data_packet_part)} "
                f"{shlex.quote(remote_data_packet)}",
                timeout=60,
            )
            if data_finalized.returncode:
                raise RuntimeError(
                    "typed_transfer_boundary:data_packet_finalize_failed"
                )
        extracted = run_ssh(
            ip,
            KEY,
            f"if test -f {shlex.quote(remote_run + '/.PACKET_SHA256')} && "
            f"test \"$(cat {shlex.quote(remote_run + '/.PACKET_SHA256')})\" = "
            f"{packet_hash}; then true; else rm -rf {shlex.quote(remote_run + '.part')} "
            f"&& mkdir -p {shlex.quote(remote_run + '.part')} "
            f"&& tar -xzf {shlex.quote(remote_packet)} -C "
            f"{shlex.quote(remote_run + '.part')} "
            f"&& tar -xzf {shlex.quote(remote_data_packet)} -C "
            f"{shlex.quote(remote_run + '.part')} "
            f"&& printf %s {packet_hash} > "
            f"{shlex.quote(remote_run + '.part/.PACKET_SHA256')} "
            f"&& mv {shlex.quote(remote_run + '.part')} {shlex.quote(remote_run)}; fi",
            timeout=120,
        )
        if extracted.returncode:
            raise RuntimeError("typed_transfer_boundary:packet_extract_failed")
        emit(
            "immutable_packet_staged",
            packet_sha256=packet_hash,
            data_packet_sha256=data_packet_hash,
            manifest_sha256=manifest_hash,
        )

        if args.resume_retrieval:
            worker = subprocess.CompletedProcess([], 0, "", "")
            emit("retrieval_resumed_without_candidate_replay")
        else:
            remote_command = (
                f"printf %s {int(time.time())} > "
                f"{shlex.quote(remote_output + '/REMOTE_INVOCATION_INTENT.txt')}; "
                f"sudo docker run --rm --gpus all --ipc=host --network host "
                f"-v {shlex.quote(remote_run)}:/packet:ro "
                f"-v {shlex.quote(remote_output)}:/output "
                f"{shlex.quote(IMAGE)} bash "
                f"/packet/inputs/exact_consumer/run_component.sh "
                f"/packet /output >{shlex.quote(remote_output + '/worker.stdout')} "
                f"2>{shlex.quote(remote_output + '/worker.stderr')}"
            )
            emit("component_worker_started")
            worker = run_ssh(
                ip,
                KEY,
                remote_command,
                timeout=max(300, deadline - int(time.time()) - 300),
            )
            atomic(
                args.artifact_root / "worker-ssh.json",
                {
                    "returncode": worker.returncode,
                    "stdout": worker.stdout[-4000:],
                    "stderr": worker.stderr[-4000:],
                },
            )

        remote_archive = f"{remote_output}.retrieval.tar.gz"
        remote_archive_part = f"{remote_archive}.part"
        packed = run_ssh(
            ip,
            KEY,
            f"sudo tar -czf {shlex.quote(remote_archive_part)} -C "
            f"{shlex.quote(remote_output)} . && "
            f"sudo chown glmrunner:glmrunner {shlex.quote(remote_archive_part)} "
            f"&& mv -f {shlex.quote(remote_archive_part)} "
            f"{shlex.quote(remote_archive)}",
            timeout=120,
        )
        if packed.returncode:
            raise RuntimeError("recoverable_retrieval_failure:remote_pack")
        retrieved = run(
            [
                "scp",
                "-i",
                str(KEY),
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                f"UserKnownHostsFile={KNOWN_HOSTS}",
                f"glmrunner@{ip}:{remote_archive}",
                str(args.artifact_root / "remote-output.tar.gz"),
            ],
            capture_output=True,
            timeout=300,
        )
        if retrieved.returncode:
            raise RuntimeError("recoverable_retrieval_failure:archive_scp")
        with tarfile.open(
            args.artifact_root / "remote-output.tar.gz", "r:gz"
        ) as archive:
            archive.extractall(args.artifact_root / "retrieved", filter="data")
        component_path = args.artifact_root / "retrieved/component/TERMINAL.json"
        invocation_path = (
            args.artifact_root / "retrieved/component/INVOCATION_STATE.json"
        )
        terminal = (
            json.loads(component_path.read_text())
            if component_path.is_file()
            else None
        )
        invocation = (
            json.loads(invocation_path.read_text())
            if invocation_path.is_file()
            else None
        )
        emit(
            "component_worker_finished",
            worker_returncode=worker.returncode,
            terminal_classification=terminal.get("classification")
            if terminal
            else None,
            invocation=invocation,
        )

        if terminal and terminal.get("pass"):
            metrics = ",".join(
                (
                    "dram__bytes_read.sum",
                    "lts__t_sectors_op_read.sum",
                    "sm__warps_active.avg.pct_of_peak_sustained_active",
                    "sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active",
                    "launch__registers_per_thread",
                    "launch__shared_mem_per_block_dynamic",
                    "l1tex__t_sectors_pipe_lsu_mem_local_op_ld.sum",
                    "l1tex__t_sectors_pipe_lsu_mem_local_op_st.sum",
                    "smsp__inst_executed_op_barrier.sum",
                )
            )
            for arm in ("candidate", "control"):
                profile_output = f"{remote_output}/profile-{arm}"
                profile_command = (
                    f"sudo docker run --rm --gpus all --ipc=host "
                    f"--cap-add SYS_ADMIN "
                    f"-v {shlex.quote(remote_run)}:/packet:ro "
                    f"-v {shlex.quote(remote_output)}:/output "
                    f"{shlex.quote(IMAGE)} bash -lc "
                    + shlex.quote(
                        f"export PYTHONPATH=/output/build-source; "
                        f"ncu --profile-from-start off --target-processes all "
                        f"--metrics {metrics} --csv --page raw "
                        f"python3 /packet/inputs/exact_consumer/exact_component.py "
                        f"--project /packet "
                        f"--manifest /packet/EXACT_CONSUMER_GPU_INPUT_MANIFEST.json "
                        f"--output /output/profile-{arm} "
                        f"--counter-probe {arm} "
                        f">/output/profile-{arm}.csv "
                        f"2>/output/profile-{arm}.stderr"
                    )
                )
                profile = run_ssh(
                    ip,
                    KEY,
                    profile_command,
                    timeout=max(300, deadline - int(time.time()) - 240),
                )
                emit(
                    "counter_finished",
                    arm=arm,
                    returncode=profile.returncode,
                )
                if profile.returncode:
                    raise RuntimeError(
                        f"recoverable_counter_consumer_failure:{arm}"
                    )
            counter_archive = f"{remote_output}/counter-compact.tar.gz"
            counter_pack = run_ssh(
                ip,
                KEY,
                f"cd {shlex.quote(remote_output)} && "
                "rm -f counter-compact.tar.gz.part && "
                "files=\"$(find . -maxdepth 2 -type f "
                "\\( -path './profile-*' -o -name 'profile-*.csv' "
                "-o -name 'profile-*.stderr' \\) -printf '%p ')\" && "
                "test -n \"$files\" && "
                "tar -czf counter-compact.tar.gz.part $files && "
                "mv counter-compact.tar.gz.part counter-compact.tar.gz",
                timeout=120,
            )
            if counter_pack.returncode:
                raise RuntimeError(
                    "recoverable_counter_retrieval_failure:pack"
                )
            counter_retrieved = run(
                [
                    "scp",
                    "-i",
                    str(KEY),
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    "-o",
                    f"UserKnownHostsFile={KNOWN_HOSTS}",
                    f"glmrunner@{ip}:{counter_archive}",
                    str(args.artifact_root / "counter-compact.tar.gz"),
                ],
                capture_output=True,
                timeout=300,
            )
            if counter_retrieved.returncode:
                raise RuntimeError(
                    "recoverable_counter_retrieval_failure:scp"
                )

        if terminal and terminal.get("classification") == "component_positive":
            atomic(
                args.artifact_root / "REPAIR_READY.json",
                {
                    "schema_version": 1,
                    "classification": "conditional_endpoint_required",
                    "diagnostic": (
                        "Exact AWQ component and minimum counter packet passed; "
                        "conditional coherence integration is required."
                    ),
                    "absolute_repair_deadline_epoch": deadline,
                    "bench": BENCH,
                    "remote_run": remote_run,
                    "remote_output": remote_output,
                },
            )
            emit("conditional_endpoint_handoff_ready")
            while time.time() < deadline - 180:
                disposition = args.artifact_root / "FINAL_DISPOSITION.json"
                if disposition.is_file():
                    final = json.loads(disposition.read_text())
                    release_condition = str(final["release_condition"])
                    release_contents = dict(final["contents"])
                    emit("final_disposition_received", final=final)
                    break
                time.sleep(10)
            if release_condition is None:
                release_condition = "maintenance"
                release_contents = {
                    "project": NAME,
                    "classification": "endpoint_handoff_deadline",
                    "artifacts": str(args.artifact_root.relative_to(PROJECT)),
                    "server_state": "No component container remains; conditional checkpoint/endpoint was not finalized before the project deadline.",
                }
        elif terminal is not None:
            release_condition = "ready"
            release_contents = {
                "project": NAME,
                "classification": terminal.get("classification"),
                "artifacts": str(args.artifact_root.relative_to(PROJECT)),
                "result": (
                    "Exact AWQ group-scale component reached a scientific "
                    "terminal; minimum counters were collected when the "
                    "component was numerically valid."
                ),
                "candidate_cuda_started": bool(
                    invocation and invocation.get("candidate_cuda_started")
                ),
                "scientific_invocation_started": bool(
                    invocation and invocation.get("candidate_science_started")
                ),
                "server_state": (
                    "No container remains; pinned image, exact packet, "
                    "compiled SM89 extension, and resident checkpoint remain."
                ),
            }
        elif invocation and not invocation.get("candidate_science_started"):
            atomic(
                args.artifact_root / "REPAIR_READY.json",
                {
                    "schema_version": 1,
                    "classification": "recoverable_pre_science_integration_failure",
                    "diagnostic": {
                        "worker_returncode": worker.returncode,
                        "invocation": invocation,
                    },
                    "absolute_repair_deadline_epoch": deadline,
                    "bench": BENCH,
                    "remote_run": remote_run,
                    "remote_output": remote_output,
                },
            )
            emit("pre_science_repair_ready")
            while time.time() < deadline - 180:
                disposition = args.artifact_root / "FINAL_DISPOSITION.json"
                if disposition.is_file():
                    final = json.loads(disposition.read_text())
                    release_condition = str(final["release_condition"])
                    release_contents = dict(final["contents"])
                    break
                time.sleep(10)
            if release_condition is None:
                release_condition = "maintenance"
                release_contents = {
                    "project": NAME,
                    "classification": "pre_science_repair_deadline",
                    "artifacts": str(args.artifact_root.relative_to(PROJECT)),
                }
        else:
            release_condition = "maintenance"
            release_contents = {
                "project": NAME,
                "classification": "scientific_failure_without_terminal",
                "artifacts": str(args.artifact_root.relative_to(PROJECT)),
                "candidate_cuda_started": bool(
                    invocation and invocation.get("candidate_cuda_started")
                ),
                "scientific_invocation_started": bool(
                    invocation and invocation.get("candidate_science_started")
                ),
                "server_state": "Remote evidence was retrieved; director disposition required.",
            }
    except Exception as error:
        emit("outer_exception", type=type(error).__name__, message=str(error))
        if (
            claimed
            and release_condition is None
            and str(error).startswith("recoverable_")
        ):
            atomic(
                args.artifact_root / "REPAIR_READY.json",
                {
                    "schema_version": 1,
                    "classification": "recoverable_consumer_failure",
                    "diagnostic": f"{type(error).__name__}:{error}",
                    "absolute_repair_deadline_epoch": deadline,
                    "bench": BENCH,
                },
            )
            emit("recoverable_consumer_repair_ready")
            while time.time() < deadline - 180:
                disposition = args.artifact_root / "FINAL_DISPOSITION.json"
                if disposition.is_file():
                    final = json.loads(disposition.read_text())
                    release_condition = str(final["release_condition"])
                    release_contents = dict(final["contents"])
                    break
                time.sleep(10)
        if release_condition is None:
            release_condition = "maintenance"
            release_contents = {
                "project": NAME,
                "classification": "outer_controller_failure",
                "diagnostic": f"{type(error).__name__}:{error}",
                "artifacts": str(args.artifact_root.relative_to(PROJECT)),
            }
    finally:
        stop.set()
        if thread.is_alive():
            thread.join(timeout=5)
        exposure = max(0.0, time.time() - started) * RATE / 3600
        atomic(
            args.artifact_root / "COST.json",
            {
                "schema_version": 1,
                "prior_spend_usd": PRIOR_SPEND_USD,
                "turn_exposure_seconds": max(0.0, time.time() - started),
                "turn_exposure_usd": exposure,
                "cumulative_spend_usd": PRIOR_SPEND_USD + exposure,
                "rate_usd_per_hour": RATE,
            },
        )
        if claimed and release_condition is not None:
            contents_path = args.artifact_root / "FINAL_BENCH_CONTENTS.json"
            atomic(contents_path, release_contents)
            pool(
                "update",
                "--project",
                NAME,
                "--contents",
                str(contents_path),
            )
            released = pool(
                "release",
                "--project",
                NAME,
                "--condition",
                release_condition,
                "--contents",
                str(contents_path),
            )
            emit(
                "released",
                condition=release_condition,
                result=json.loads(released.stdout),
            )
    return 0 if release_condition == "ready" else 75


if __name__ == "__main__":
    raise SystemExit(main())
