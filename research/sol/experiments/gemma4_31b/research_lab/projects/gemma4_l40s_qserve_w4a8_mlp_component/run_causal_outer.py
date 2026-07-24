#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import shlex
import subprocess
import tarfile
import threading
import time


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
NAME = PROJECT.name
BENCH = "l40s-qserve-e00a74kcbps8v00fk4"
INSTANCE = "computeinstance-e00a74kcbps8v00fk4"
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.ssh/known_hosts")
PYTHONPATH = str(pathlib.Path("/root/workspace/research/factory/src"))
POOL = pathlib.Path("/usr/bin/python3")
PACKET = PROJECT / "CAUSAL_TRACE_PACKET.tar.gz"
PACKET_SHA256 = "83e21dde721c268c74f67f182bdbc57a0afe1de6901a6afc5e1fd386f6277c40"
MANIFEST_SHA256 = "ecd7a20c6dc61ce08a8e663a2c82043c33bf30cc4f90904911a07da63e4b1b96"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
RATE = 0.8629833
PRIOR_SPEND = 1.6504614233037829
ABSOLUTE_DEADLINE = datetime.datetime.fromisoformat(
    "2026-07-24T08:15:00+00:00"
).timestamp()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, **kwargs)


def pool(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = PYTHONPATH
    return run(
        [
            str(POOL),
            "-m",
            "grad_research.gpu_pool",
            "--lab",
            str(LAB),
            *arguments,
        ],
        capture_output=True,
        check=check,
        env=environment,
    )


def current_ip() -> str:
    result = run(
        [
            "nebius",
            "compute",
            "instance",
            "get",
            INSTANCE,
            "--format",
            "json",
            "--no-progress",
            "--no-check-update",
        ],
        capture_output=True,
        check=True,
    )
    value = json.loads(result.stdout)
    address = value["status"]["network_interfaces"][0]["public_ip_address"][
        "address"
    ]
    return str(address).split("/", 1)[0]


def ssh(ip: str, command: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "ssh",
            "-i",
            str(KEY),
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            f"glmrunner@{ip}",
            command,
        ],
        capture_output=True,
        timeout=timeout,
    )


def ensure_director_ready(events: pathlib.Path) -> None:
    listing = json.loads(pool("list").stdout)
    bench = next(row for row in listing["benches"] if row["id"] == BENCH)
    if bench["status"] == "available":
        return
    if (
        bench["status"] != "maintenance"
        or bench["contents"].get("project") != NAME
        or bench["contents"].get("classification") != "endpoint_reject"
    ):
        raise RuntimeError(
            f"typed_pool_boundary:bench_not_reusable:{bench['status']}"
        )
    result = pool("ready", "--bench", BENCH)
    with events.open("a") as handle:
        handle.write(
            json.dumps(
                {
                    "epoch": time.time(),
                    "event": "director_admitted_maintenance_bench_ready",
                    "bench": json.loads(result.stdout),
                },
                sort_keys=True,
            )
            + "\n"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=False)
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

    ensure_director_ready(events)
    lease_seconds = max(600, int(ABSOLUTE_DEADLINE - time.time()))
    claimed_result = pool(
        "claim",
        "--project",
        NAME,
        "--bench",
        BENCH,
        "--lease-seconds",
        str(lease_seconds),
    )
    claim = json.loads(claimed_result.stdout)
    claim_started = datetime.datetime.fromisoformat(
        claim["claim"]["claimed_at"].replace("Z", "+00:00")
    ).timestamp()
    emit("claimed", bench=BENCH, claim=claim["claim"])

    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME, check=False)
            emit(
                "heartbeat",
                returncode=result.returncode,
                stderr=result.stderr[-1000:],
            )

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    release_condition: str | None = None
    release_contents: dict[str, object] = {}
    ip = ""
    remote_root = "/home/glmrunner/gemma4-qserve-causal-trace"
    remote_input = f"{remote_root}/runs/{PACKET_SHA256}"
    remote_output = (
        "/home/glmrunner/gemma4-qserve-endpoint/artifacts/"
        "qserve-causal-trace"
    )
    try:
        ip = current_ip()
        emit("provider_identity", ip=ip, instance=INSTANCE)
        remote_prepare = ssh(
            ip,
            (
                f"mkdir -p {shlex.quote(remote_root + '/runs')} "
                f"{shlex.quote(remote_output)}; "
                f"if test -f {shlex.quote(remote_input + '/TRACE_INPUT_MANIFEST.json')}; "
                f"then sha256sum {shlex.quote(remote_input + '/TRACE_INPUT_MANIFEST.json')}; "
                "fi"
            ),
            30,
        )
        if remote_prepare.returncode:
            raise RuntimeError("typed_transfer_boundary:remote_prepare_failed")
        remote_archive = f"{remote_root}/packet-{PACKET_SHA256}.tar.gz"
        transferred = run(
            [
                "scp",
                "-i",
                str(KEY),
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                f"UserKnownHostsFile={KNOWN_HOSTS}",
                str(PACKET),
                f"glmrunner@{ip}:{remote_archive}.part",
            ],
            capture_output=True,
            timeout=120,
        )
        if transferred.returncode:
            raise RuntimeError("typed_transfer_boundary:packet_scp_failed")
        finalized = ssh(
            ip,
            (
                f"test \"$(sha256sum {shlex.quote(remote_archive + '.part')} "
                f"| cut -d' ' -f1)\" = {PACKET_SHA256}; "
                f"mv {shlex.quote(remote_archive + '.part')} "
                f"{shlex.quote(remote_archive)}; "
                f"rm -rf {shlex.quote(remote_input + '.part')}; "
                f"mkdir -p {shlex.quote(remote_input + '.part')}; "
                f"tar -C {shlex.quote(remote_input + '.part')} -xzf "
                f"{shlex.quote(remote_archive)}; "
                f"test \"$(sha256sum "
                f"{shlex.quote(remote_input + '.part/TRACE_INPUT_MANIFEST.json')} "
                f"| cut -d' ' -f1)\" = {MANIFEST_SHA256}; "
                f"mv {shlex.quote(remote_input + '.part')} "
                f"{shlex.quote(remote_input)}"
            ),
            60,
        )
        if finalized.returncode:
            atomic(
                args.artifact_root / "stage-diagnostic.json",
                {
                    "returncode": finalized.returncode,
                    "stdout": finalized.stdout[-4000:],
                    "stderr": finalized.stderr[-4000:],
                },
            )
            raise RuntimeError("typed_transfer_boundary:packet_finalize_failed")
        emit(
            "immutable_packet_staged",
            packet_sha256=PACKET_SHA256,
            manifest_sha256=MANIFEST_SHA256,
            remote_input=remote_input,
        )

        qserve = (
            "/home/glmrunner/gemma4-qserve-bf16/runs/"
            "8828d463cf965bab69e4eb1890c38a6ab713a6f555a5e4388ec1601472efb08a"
        )
        smoke = ssh(
            ip,
            (
                "sudo docker run --rm --gpus all --ipc=host "
                f"-e PYTHONPATH=/trace:{qserve}/inputs/bf16_epilogue/qserve_sm89 "
                f"-e QSERVE_EVENT_LOG={remote_output}/preflight-qserve-events.jsonl "
                f"-e QSERVE_TRACE_EVENTS={remote_output}/preflight-trace-events.jsonl "
                f"-v {remote_input}:/trace:ro "
                f"-v /home/glmrunner/gemma4-qserve-endpoint/input:/endpoint:ro "
                f"-v {qserve}:{qserve}:ro "
                "-v /home/glmrunner/gemma4-qserve-endpoint:/work "
                "--entrypoint python3 "
                f"{IMAGE} -c "
                + shlex.quote(
                    "import sitecustomize; "
                    "assert sitecustomize.base.QServeLinearMethod; "
                    "print('trace-import-pass')"
                )
            ),
            180,
        )
        atomic(
            args.artifact_root / "import-smoke.json",
            {
                "returncode": smoke.returncode,
                "stdout": smoke.stdout[-4000:],
                "stderr": smoke.stderr[-4000:],
            },
        )
        if smoke.returncode:
            raise RuntimeError("recoverable_pre_science:trace_import_failed")
        emit("trace_import_passed")

        worker = ssh(
            ip,
            (
                f"bash {shlex.quote(remote_input + '/run_trace.sh')} "
                f">{shlex.quote(remote_output + '/worker.stdout')} "
                f"2>{shlex.quote(remote_output + '/worker.stderr')}"
            ),
            max(600, int(ABSOLUTE_DEADLINE - time.time() - 300)),
        )
        atomic(
            args.artifact_root / "worker-ssh.json",
            {
                "returncode": worker.returncode,
                "stdout": worker.stdout[-4000:],
                "stderr": worker.stderr[-4000:],
            },
        )
        emit("worker_finished", returncode=worker.returncode)

        archive = f"{remote_root}/causal-trace-output.tar.gz"
        packed = ssh(
            ip,
            (
                f"sudo tar -C {shlex.quote(remote_output)} -czf "
                f"{shlex.quote(archive + '.part')} .; "
                f"sudo mv {shlex.quote(archive + '.part')} {shlex.quote(archive)}; "
                f"sudo chown glmrunner:glmrunner {shlex.quote(archive)}; "
                f"sha256sum {shlex.quote(archive)}"
            ),
            120,
        )
        if packed.returncode:
            raise RuntimeError("typed_retrieval_boundary:remote_pack_failed")
        atomic(
            args.artifact_root / "remote-archive.json",
            {"sha256_line": packed.stdout.strip()},
        )
        retrieved = run(
            [
                "scp",
                "-i",
                str(KEY),
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                f"UserKnownHostsFile={KNOWN_HOSTS}",
                f"glmrunner@{ip}:{archive}",
                str(args.artifact_root / "remote-output.tar.gz"),
            ],
            capture_output=True,
            timeout=300,
        )
        if retrieved.returncode:
            raise RuntimeError("typed_retrieval_boundary:archive_scp_failed")
        with tarfile.open(
            args.artifact_root / "remote-output.tar.gz", "r:gz"
        ) as handle:
            handle.extractall(args.artifact_root / "retrieved", filter="data")
        terminal_path = args.artifact_root / "retrieved/TERMINAL.json"
        invocation_path = args.artifact_root / "retrieved/INVOCATION_STATE.json"
        terminal = (
            json.loads(terminal_path.read_text())
            if terminal_path.is_file()
            else None
        )
        invocation = (
            json.loads(invocation_path.read_text())
            if invocation_path.is_file()
            else {}
        )
        emit(
            "evidence_retrieved",
            terminal=terminal.get("classification") if terminal else None,
            invocation=invocation,
        )
        if terminal and terminal.get("classification") == (
            "uncalibrated_w4_representation_reject"
        ):
            release_condition = "maintenance"
            release_contents = {
                "project": NAME,
                "classification": terminal["classification"],
                "artifacts": str(args.artifact_root.relative_to(PROJECT)),
                "result": (
                    "Real-weight prefix-depth trace and first-divergent-layer "
                    "oracle close uncalibrated all-layer W4."
                ),
                "scientific_terminal": str(
                    terminal_path.relative_to(PROJECT)
                ),
                "checkpoint": (
                    "/home/glmrunner/gemma4-qserve-endpoint/checkpoint; exact "
                    "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4"
                ),
                "w4_cache": (
                    "/home/glmrunner/gemma4-qserve-endpoint/w4_cache/"
                    "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2"
                ),
                "server_state": (
                    "gemma-qserve-bf16-endpoint remains loaded on port 30000 "
                    "with causal trace overlay and CUDA graphs disabled."
                ),
                "next_need": (
                    "Director disposition; consumed causal trace must not be replayed."
                ),
            }
        else:
            classification = (
                terminal.get("classification")
                if terminal
                else "recoverable_trace_failure"
            )
            atomic(
                args.artifact_root / "REPAIR_READY.json",
                {
                    "schema_version": 1,
                    "classification": classification,
                    "worker_returncode": worker.returncode,
                    "invocation": invocation,
                    "absolute_repair_deadline_epoch": ABSOLUTE_DEADLINE,
                    "remote_input": remote_input,
                    "remote_output": remote_output,
                    "ip": ip,
                },
            )
            emit("repair_handoff_ready", classification=classification)
            while time.time() < ABSOLUTE_DEADLINE - 180:
                disposition_path = args.artifact_root / "FINAL_DISPOSITION.json"
                if disposition_path.is_file():
                    disposition = json.loads(disposition_path.read_text())
                    release_condition = disposition["release_condition"]
                    release_contents = disposition["contents"]
                    break
                time.sleep(10)
            if release_condition is None:
                release_condition = "maintenance"
                release_contents = {
                    "project": NAME,
                    "classification": "causal_trace_repair_deadline",
                    "artifacts": str(args.artifact_root.relative_to(PROJECT)),
                    "server_state": (
                        "gemma-qserve-bf16-endpoint retained on port 30000; "
                        "inspect causal trace artifacts before mutation."
                    ),
                }
    except Exception as error:
        emit("outer_exception", error=repr(error))
        atomic(
            args.artifact_root / "OUTER_EXCEPTION.json",
            {
                "schema_version": 1,
                "classification": "outer_integration_failure",
                "error": repr(error),
                "ip": ip,
                "absolute_repair_deadline_epoch": ABSOLUTE_DEADLINE,
            },
        )
        while time.time() < ABSOLUTE_DEADLINE - 180:
            disposition_path = args.artifact_root / "FINAL_DISPOSITION.json"
            if disposition_path.is_file():
                disposition = json.loads(disposition_path.read_text())
                release_condition = disposition["release_condition"]
                release_contents = disposition["contents"]
                break
            time.sleep(10)
        if release_condition is None:
            release_condition = "maintenance"
            release_contents = {
                "project": NAME,
                "classification": "outer_repair_deadline",
                "artifacts": str(args.artifact_root.relative_to(PROJECT)),
                "server_state": "Inspect retained guest before mutation.",
            }
    finally:
        stop.set()
        thread.join(timeout=5)
        released_at = time.time()
        claim_seconds = max(0.0, released_at - claim_started)
        atomic(
            args.artifact_root / "COST.json",
            {
                "schema_version": 1,
                "prior_spend_usd": PRIOR_SPEND,
                "claim_started_epoch": claim_started,
                "released_epoch": released_at,
                "claim_exposure_seconds": claim_seconds,
                "claim_exposure_usd": claim_seconds * RATE / 3600,
                "cumulative_spend_usd": (
                    PRIOR_SPEND + claim_seconds * RATE / 3600
                ),
                "rate_usd_per_hour": RATE,
            },
        )
        if release_condition is not None:
            contents_path = args.artifact_root / "FINAL_BENCH_CONTENTS.json"
            atomic(contents_path, release_contents)
            released = pool(
                "release",
                "--project",
                NAME,
                "--condition",
                str(release_condition),
                "--contents",
                str(contents_path),
            )
            emit(
                "released",
                condition=release_condition,
                bench=json.loads(released.stdout),
            )
    return 0 if release_condition == "ready" else 75


if __name__ == "__main__":
    raise SystemExit(main())
