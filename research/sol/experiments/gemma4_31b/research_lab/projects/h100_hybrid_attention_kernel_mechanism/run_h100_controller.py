#!/usr/bin/env python3
"""Durable owner for the registered H100 component execution.

The controller deliberately resolves mutable connection data only after its
atomic pool claim.  The scientific command and its project-local inputs stay
unchanged; this file owns only lifecycle, transport, and retrieval.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT = "h100_hybrid_attention_kernel_mechanism"
REGISTERED_BINDING = "DIRECTOR_H100_REGISTERED_BINDING_20260726T1543Z.json"
SSH_IDENTITY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
IMAGE = (
    "docker.io/vllm/vllm-openai:gemma4@"
    "sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77"
    "c32e0a732a79"
)


class ControllerBindingError(RuntimeError):
    """A fail-closed controller or bench binding defect."""


@dataclass(frozen=True)
class BenchConnection:
    bench_id: str
    host: str
    user: str
    known_hosts: Path
    fingerprint: str
    remote_root: str
    lifecycle_deadline: str


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def parse_utc(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ControllerBindingError(f"cannot read JSON binding {path}: {error}") from error
    if not isinstance(value, dict):
        raise ControllerBindingError(f"JSON binding is not an object: {path}")
    return value


def lab_for_project(root: Path) -> Path:
    # root is .../research_lab/projects/<project>; no provider path is guessed.
    lab = root.parent.parent
    if lab.name != "research_lab":
        raise ControllerBindingError(f"unexpected project layout: {root}")
    return lab


def registered_spec(root: Path) -> dict[str, Any]:
    binding = load_json(root / REGISTERED_BINDING)
    if binding.get("project") != PROJECT:
        raise ControllerBindingError("registered binding belongs to another project")
    bench = binding.get("bench")
    resource = binding.get("provider_resource")
    if not isinstance(bench, dict) or not isinstance(resource, dict):
        raise ControllerBindingError("registered binding lacks bench/provider resource")
    bench_id = bench.get("id")
    if not isinstance(bench_id, str) or not bench_id:
        raise ControllerBindingError("registered binding lacks bench id")
    spec_name = bench.get("spec")
    spec_hash = bench.get("spec_sha256")
    if not isinstance(spec_name, str) or not isinstance(spec_hash, str):
        raise ControllerBindingError("registered binding lacks immutable bench spec")
    spec_path = root / spec_name
    observed_spec_hash = __import__("hashlib").sha256(spec_path.read_bytes()).hexdigest()
    if observed_spec_hash != spec_hash:
        raise ControllerBindingError("registered bench spec hash mismatch")
    spec = load_json(spec_path)
    if spec.get("id") != bench_id or spec.get("accelerator") != "nvidia-h100-sxm":
        raise ControllerBindingError("registered bench spec identity mismatch")
    spec_resource = spec.get("resource")
    if not isinstance(spec_resource, dict):
        raise ControllerBindingError("registered bench spec lacks resource")
    fields = (
        "public_ipv4",
        "ssh_user",
        "known_hosts_namespace",
        "ssh_ed25519_fingerprint",
    )
    for name in fields:
        if resource.get(name) is not None and resource.get(name) != spec_resource.get(name):
            raise ControllerBindingError(f"registered binding/spec mismatch: {name}")
    return {
        "bench_id": bench_id,
        "accelerator": "nvidia-h100-sxm",
        "public_ipv4": resource.get("public_ipv4", spec_resource.get("public_ipv4")),
        "ssh_user": spec_resource.get("ssh_user"),
        "known_hosts_namespace": resource.get(
            "known_hosts_namespace", spec_resource.get("known_hosts_namespace")
        ),
        "ssh_ed25519_fingerprint": resource.get(
            "ssh_ed25519_fingerprint", spec_resource.get("ssh_ed25519_fingerprint")
        ),
    }


def claim_bench(lab: Path, bench_id: str) -> None:
    env = {**os.environ, "PYTHONPATH": "research/factory/src"}
    command = [
        sys.executable,
        "-m",
        "grad_research.gpu_pool",
        "--lab",
        str(lab),
        "claim",
        "--project",
        PROJECT,
        "--bench",
        bench_id,
    ]
    completed = subprocess.run(command, cwd="/root/workspace", env=env, check=False)
    if completed.returncode != 0:
        raise ControllerBindingError(f"atomic claim failed with exit {completed.returncode}")


def read_claimed_connection(lab: Path, expected: dict[str, Any]) -> BenchConnection:
    inventory_path = lab / "runtime" / "gpus.json"
    inventory = load_json(inventory_path)
    benches = inventory.get("benches")
    if not isinstance(benches, dict):
        raise ControllerBindingError("GPU inventory benches must be an object")
    bench = benches.get(expected["bench_id"])
    if not isinstance(bench, dict):
        raise ControllerBindingError("expected current H100 bench is absent")

    if bench.get("id") != expected["bench_id"]:
        raise ControllerBindingError("inventory bench id mismatch")
    if bench.get("accelerator") != expected["accelerator"]:
        raise ControllerBindingError("inventory bench is not nvidia-h100-sxm")
    if bench.get("status") == "retired":
        raise ControllerBindingError("retired bench is not executable")
    if bench.get("status") != "claimed":
        raise ControllerBindingError("bench is not claimed by the controller")

    claim = bench.get("claim")
    if not isinstance(claim, dict) or claim.get("project") != PROJECT:
        raise ControllerBindingError("bench claim is absent or owned by another project")
    now = utc_now()
    lease_until = claim.get("lease_until_utc")
    lifecycle = bench.get("lifecycle")
    lifecycle_deadline = lifecycle.get("deadline_utc") if isinstance(lifecycle, dict) else None
    if not isinstance(lease_until, str) or parse_utc(lease_until) <= now:
        raise ControllerBindingError("bench claim lease is expired")
    if not isinstance(lifecycle_deadline, str) or parse_utc(lifecycle_deadline) <= now:
        raise ControllerBindingError("bench lifecycle is expired")
    if claim.get("stale") is True:
        raise ControllerBindingError("bench claim is marked stale")

    resource = bench.get("resource")
    if not isinstance(resource, dict):
        raise ControllerBindingError("bench resource is missing")
    fields = {
        "public_ipv4": resource.get("public_ipv4"),
        "ssh_user": resource.get("ssh_user"),
        "known_hosts_namespace": resource.get("known_hosts_namespace"),
        "ssh_ed25519_fingerprint": resource.get("ssh_ed25519_fingerprint"),
    }
    for name, value in fields.items():
        if not isinstance(value, str) or not value:
            raise ControllerBindingError(f"bench resource field is missing: {name}")
        if value != expected[name]:
            raise ControllerBindingError(f"bench resource field mismatches binding: {name}")

    known_hosts = Path(fields["known_hosts_namespace"])
    if not known_hosts.is_absolute():
        raise ControllerBindingError("known-hosts namespace must be absolute")
    remote_root = f"/home/{fields['ssh_user']}/{PROJECT}/{expected['bench_id']}"
    return BenchConnection(
        bench_id=expected["bench_id"],
        host=fields["public_ipv4"],
        user=fields["ssh_user"],
        known_hosts=known_hosts,
        fingerprint=fields["ssh_ed25519_fingerprint"],
        remote_root=remote_root,
        lifecycle_deadline=lifecycle_deadline,
    )


def ssh_base(connection: BenchConnection) -> list[str]:
    return [
        "ssh",
        "-i",
        str(SSH_IDENTITY),
        "-o",
        "BatchMode=yes",
        "-o",
        f"UserKnownHostsFile={connection.known_hosts}",
        "-o",
        "StrictHostKeyChecking=yes",
        f"{connection.user}@{connection.host}",
    ]


def scp_to(connection: BenchConnection, local: Path, remote: str) -> None:
    subprocess.run(
        [
            "scp",
            "-i",
            str(SSH_IDENTITY),
            "-o",
            "BatchMode=yes",
            "-o",
            f"UserKnownHostsFile={connection.known_hosts}",
            "-o",
            "StrictHostKeyChecking=yes",
            str(local),
            f"{connection.user}@{connection.host}:{remote}",
        ],
        check=True,
    )


def scp_from(connection: BenchConnection, remote: str, local: Path) -> None:
    subprocess.run(
        [
            "scp",
            "-i",
            str(SSH_IDENTITY),
            "-o",
            "BatchMode=yes",
            "-o",
            f"UserKnownHostsFile={connection.known_hosts}",
            "-o",
            "StrictHostKeyChecking=yes",
            f"{connection.user}@{connection.host}:{remote}",
            str(local),
        ],
        check=True,
    )


def exact_start_command(
    connection: BenchConnection, deadline: str
) -> tuple[str, str]:
    remote_out = f"{connection.remote_root}/artifacts/h100-paged-fp8-{connection.bench_id}"
    argv = [
        "python3",
        "paged_fp8_execution.py",
        "run",
        "--readiness",
        "H100_PAGED_FP8_EXECUTION_READY.json",
        "--output-root",
        remote_out,
        "--absolute-deadline-utc",
        deadline,
        "--image-digest",
        IMAGE,
    ]
    command = (
        f"cd {shlex.quote(connection.remote_root)} && "
        "sudo -n docker run --rm --gpus all --ipc=host "
        f"-v {shlex.quote(connection.remote_root)}:{shlex.quote(connection.remote_root)} "
        f"--workdir {shlex.quote(connection.remote_root)} --entrypoint python3 "
        f"{shlex.quote(IMAGE)} "
        f"{shlex.join(argv[1:])}"
    )
    return command, remote_out


def recovery_start_command(
    connection: BenchConnection, deadline: str
) -> tuple[str, str, str]:
    remote_out = f"{connection.remote_root}/artifacts/h100-paged-fp8-{connection.bench_id}"
    recovery_terminal = f"{remote_out}/recovery-worker-terminal.json"
    argv = [
        "python3",
        "paged_fp8_execution.py",
        "recovery-worker",
        "--readiness",
        "H100_PAGED_FP8_EXECUTION_READY.json",
        "--output",
        recovery_terminal,
        "--absolute-deadline-utc",
        deadline,
        "--image-digest",
        IMAGE,
    ]
    command = (
        f"cd {shlex.quote(connection.remote_root)} && "
        "sudo -n docker run --rm --gpus all --ipc=host "
        f"-v {shlex.quote(connection.remote_root)}:{shlex.quote(connection.remote_root)} "
        f"--workdir {shlex.quote(connection.remote_root)} --entrypoint python3 "
        f"{shlex.quote(IMAGE)} {shlex.join(argv[1:])}"
    )
    return command, remote_out, recovery_terminal


def retrieve_if_present(
    connection: BenchConnection, remote: str, local: Path
) -> bool:
    local.parent.mkdir(parents=True, exist_ok=True)
    try:
        scp_from(connection, remote, local)
        return True
    except Exception as exc:
        (local.parent / f"retrieval_error_{local.name}.txt").write_text(
            repr(exc) + "\n"
        )
        return False


def classify_resident_diagnostic(
    connection: BenchConnection, remote_out: str, local_root: Path
) -> dict[str, Any]:
    diagnostic_root = local_root / "diagnostic-first"
    diagnostic_root.mkdir(parents=True, exist_ok=True)
    timing = diagnostic_root / "resident-local1024-c8.timing.json"
    terminal = diagnostic_root / "resident-terminal.json"
    launch_marker = diagnostic_root / "resident-candidate-invocation-started.txt"
    timing_present = retrieve_if_present(
        connection, f"{remote_out}/local1024-c8.timing.json", timing
    )
    terminal_present = retrieve_if_present(
        connection, f"{remote_out}/H100_PAGED_FP8_EXECUTION_TERMINAL.json", terminal
    )
    launch_marker_present = retrieve_if_present(
        connection, f"{remote_out}/candidate_invocation_started_utc.txt", launch_marker
    )
    science_markers = []
    for name in (
        "local1024-c8-recovery-bf16.counter-worker.science_started.json",
        "local1024-c8-recovery-fp8_e4m3.counter-worker.science_started.json",
    ):
        path = diagnostic_root / name
        if retrieve_if_present(connection, f"{remote_out}/{name}", path):
            science_markers.append(str(path))
    decision_bearing = False
    diagnostic: dict[str, Any] = {}
    if timing_present:
        try:
            diagnostic = load_json(timing)
            decision_bearing = not bool(diagnostic.get("error")) and bool(
                diagnostic.get("pass")
            )
        except ControllerBindingError as exc:
            diagnostic = {"error": {"type": type(exc).__name__, "message": str(exc)}}
    classification = {
        "type": "h100_resident_pair_worker_diagnostic",
        "timing_present": timing_present,
        "terminal_present": terminal_present,
        "controller_launch_marker_present": launch_marker_present,
        "science_markers": science_markers,
        "decision_bearing_row": decision_bearing,
        "scientific_sample_consumed": decision_bearing or bool(science_markers),
        "diagnostic": diagnostic,
    }
    (diagnostic_root / "classification.json").write_text(
        json.dumps(classification, indent=2) + "\n"
    )
    if decision_bearing or science_markers:
        raise ControllerBindingError(
            "resident diagnostic indicates an already-consumed decision-bearing row"
        )
    return classification


def heartbeat(stop: threading.Event, lab: Path, bench_id: str) -> None:
    while not stop.wait(45):
        env = {**os.environ, "PYTHONPATH": "research/factory/src"}
        subprocess.run(
            [
                sys.executable,
                "-m",
                "grad_research.gpu_pool",
                "--lab",
                str(lab),
                "heartbeat",
                "--project",
                PROJECT,
                "--bench",
                bench_id,
            ],
            cwd="/root/workspace",
            env=env,
            check=False,
        )


def retain_recoverable_pre_science_claim(terminal: Path, deadline_utc: str) -> bool:
    if not terminal.exists() or utc_now() >= parse_utc(deadline_utc):
        return False
    try:
        result = json.loads(terminal.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    return result.get("result") == "integration_error" and result.get(
        "scientific_sample_consumed"
    ) is False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", type=Path, required=True)
    ap.add_argument("--output-root", type=Path, required=True)
    ap.add_argument("--deadline", required=True)
    args = ap.parse_args()
    root = args.project_root.resolve()
    out = args.output_root.resolve()
    out.mkdir(parents=True, exist_ok=True)
    lab = lab_for_project(root)
    expected = registered_spec(root)

    # The eventual execution owner claims atomically before resolving any
    # mutable host, user, known-hosts, fingerprint, or remote-path data.
    claim_bench(lab, expected["bench_id"])
    connection = read_claimed_connection(lab, expected)
    remote_out = f"{connection.remote_root}/artifacts/h100-paged-fp8-{connection.bench_id}"
    resident = classify_resident_diagnostic(connection, remote_out, out)
    command, remote_out, recovery_terminal = recovery_start_command(
        connection, args.deadline
    )
    (out / "controller_binding.json").write_text(
        json.dumps(
            {
                "type": "h100_current_record_controller_binding",
                "project": PROJECT,
                "bench_id": connection.bench_id,
                "host": connection.host,
                "ssh_user": connection.user,
                "known_hosts_namespace": str(connection.known_hosts),
                "ssh_ed25519_fingerprint": connection.fingerprint,
                "remote_root": connection.remote_root,
                "remote_output_root": remote_out,
                "exact_start_command": command,
                "resident_diagnostic": resident,
                "recovery_terminal": recovery_terminal,
                "scientific_program": "paged_fp8_execution.py",
                "scientific_inputs_unchanged": True,
                "provider_mutation_by_this_turn": False,
            },
            indent=2,
        )
        + "\n"
    )

    (out / "controller_started.json").write_text(
        json.dumps(
            {
                "type": "h100_controller_started",
                "bench": connection.bench_id,
                "started_monotonic": time.monotonic(),
                "deadline": args.deadline,
            },
            indent=2,
        )
        + "\n"
    )
    stop = threading.Event()
    hb = threading.Thread(
        target=heartbeat, args=(stop, lab, connection.bench_id), daemon=True
    )
    hb.start()
    rc = 1
    try:
        subprocess.run(
            ssh_base(connection)
            + [f"mkdir -p {shlex.quote(connection.remote_root)}/artifacts"],
            check=True,
        )
        for name in (
            "paged_fp8_execution.py",
            "paged_fp8_contract.py",
            "H100_PAGED_FP8_EXECUTION_READY.json",
        ):
            scp_to(connection, root / name, f"{connection.remote_root}/{name}")
        marker = f"{remote_out}/candidate_invocation_started_utc.txt"
        subprocess.run(
            ssh_base(connection)
            + [
                f"mkdir -p {shlex.quote(remote_out)} && "
                f"date -u +%FT%TZ > {shlex.quote(marker)}"
            ],
            check=True,
        )
        with (out / "remote_stdout.log").open("w") as stdout, (
            out / "remote_stderr.log"
        ).open("w") as stderr:
            proc = subprocess.run(
                ssh_base(connection) + [command],
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
        rc = proc.returncode
        recovery_local = out / "recovery-worker-terminal.json"
        retrieve_if_present(connection, recovery_terminal, recovery_local)
        retrieve_if_present(
            connection,
            f"{remote_out}/candidate_invocation_started_utc.txt",
            out / "candidate_invocation_started_utc.txt",
        )
        for name in (
            "primitive-pair-worker.capture.json",
            "local1024-c8.primitive.timing.json",
            "local1024-c8-bf16.counter-worker.json",
            "local1024-c8-fp8_e4m3.counter-worker.json",
            "local1024-c8-bf16.ncu.csv",
            "local1024-c8-fp8_e4m3.ncu.csv",
        ):
            retrieve_if_present(connection, f"{remote_out}/{name}", out / name)
        if recovery_local.exists():
            recovery = load_json(recovery_local)
            (out / "H100_PAGED_FP8_EXECUTION_TERMINAL.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "type": "h100_paged_fp8_execution_terminal",
                        "pass": bool(recovery.get("pass")),
                        "result": recovery.get("result", "integration_error"),
                        "started_at_utc": recovery.get("started_at_utc"),
                        "completed_at_utc": recovery.get("completed_at_utc"),
                        "identity_contract": recovery.get("identity_contract"),
                        "identity_contract_sha256": recovery.get("identity_contract_sha256"),
                        "provider_create_allowed": False,
                        "scientific_sample_consumed": bool(
                            recovery.get("scientific_sample_consumed")
                        ),
                        "recovery_worker_terminal": recovery,
                    },
                    indent=2,
                )
                + "\n"
            )
        terminal = out / "H100_PAGED_FP8_EXECUTION_TERMINAL.json"
        marker_out = out / "candidate_invocation_started_utc.txt"
        if terminal.exists():
            (out / "controller_complete.json").write_text(
                json.dumps(
                    {
                        "type": "h100_controller_complete",
                        "returncode": rc,
                        "terminal": str(terminal),
                        "candidate_invocation_started": marker_out.exists(),
                        "finished_monotonic": time.monotonic(),
                    },
                    indent=2,
                )
                + "\n"
            )
        else:
            (out / "controller_incomplete.json").write_text(
                json.dumps(
                    {
                        "type": "h100_controller_incomplete",
                        "returncode": rc,
                        "candidate_invocation_started": marker_out.exists(),
                        "finished_monotonic": time.monotonic(),
                    },
                    indent=2,
                )
                + "\n"
            )
    finally:
        stop.set()
        hb.join(timeout=5)
        terminal = out / "H100_PAGED_FP8_EXECUTION_TERMINAL.json"
        if retain_recoverable_pre_science_claim(terminal, args.deadline):
            (out / "retained_claim.json").write_text(
                json.dumps(
                    {
                        "type": "h100_controller_retained_claim",
                        "reason": "recoverable_pre_science_integration_error",
                        "terminal": str(terminal),
                        "deadline_utc": args.deadline,
                    },
                    indent=2,
                )
                + "\n"
            )
        elif not terminal.exists() and utc_now() < parse_utc(args.deadline):
            # A missing terminal is an unclassified/retrieval or launcher
            # boundary, not evidence that the guest is safe to release. Keep
            # the claim for same-owner repair until a terminal or deadline.
            (out / "retained_claim.json").write_text(
                json.dumps(
                    {
                        "type": "h100_controller_retained_claim",
                        "reason": "pre_science_or_retrieval_boundary_without_terminal",
                        "terminal": str(terminal),
                        "deadline_utc": args.deadline,
                    },
                    indent=2,
                )
                + "\n"
            )
        else:
            condition = "ready" if terminal.exists() else "maintenance"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "grad_research.gpu_pool",
                    "--lab",
                    str(lab),
                    "release",
                    "--project",
                    PROJECT,
                    "--bench",
                    connection.bench_id,
                    "--condition",
                    condition,
                ],
                cwd="/root/workspace",
                env={**os.environ, "PYTHONPATH": "research/factory/src"},
                check=False,
            )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
