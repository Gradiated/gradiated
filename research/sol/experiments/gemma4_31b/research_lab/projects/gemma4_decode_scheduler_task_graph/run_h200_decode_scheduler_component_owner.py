#!/usr/bin/env python3
"""Durable, retained-claim owner for the admitted H200 scheduler component."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import tarfile
import threading
import time
from pathlib import Path
from typing import Any


PROJECT = "gemma4_decode_scheduler_task_graph"
ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
FACTORY_SRC = Path("/root/workspace/research/factory/src")
DETACHED_OWNER = Path("/root/workspace/research/factory/tools/detached-owner")
REPAIR = Path("/root/workspace/research/factory/tools/repair-handshake")
REQUEST = ROOT / "DIRECTOR_DECODE_SCHEDULER_H200_COMPONENT_REQUEST_20260727T0323Z.json"
OFFLINE_TERMINAL = ROOT / "DECODE_SCHEDULER_TASK_GRAPH_OFFLINE_TERMINAL.json"
STATUS = ROOT / "STATUS.json"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
REMOTE_ROOT = "/home/glmrunner/gemma4-decode-scheduler-task-graph"
REMOTE_PROJECT = "/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_decode_scheduler_task_graph"
RATE_USD_PER_HOUR = 2.4597222
MAX_OWNER_SECONDS = 2040
PACKET_MEMBERS = (
    "decode_scheduler_task_graph.py",
    "install_decode_scheduler_task_graph.py",
    "exact_h200_consumer.py",
    "DECODE_SCHEDULER_TASK_GRAPH_OFFLINE_TERMINAL.json",
    "DIRECTOR_DECODE_SCHEDULER_H200_COMPONENT_REQUEST_20260727T0323Z.json",
)


class OwnerError(RuntimeError):
    pass


class RepairRequested(OwnerError):
    pass


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def rfc3339(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def command(argv: list[str], timeout: int, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, check=False, timeout=timeout, env=env)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise OwnerError(f"invalid_json:{path.name}:{error}") from error
    if not isinstance(value, dict):
        raise OwnerError(f"json_object_required:{path.name}")
    return value


def packet_manifest() -> list[dict[str, Any]]:
    return [
        {"path": name, "bytes": (ROOT / name).stat().st_size, "sha256": sha256(ROOT / name)}
        for name in PACKET_MEMBERS
    ]


def exact_command() -> str:
    terminal = load_json(OFFLINE_TERMINAL)
    command_value = terminal.get("h200_consumer", {}).get("command")
    if not isinstance(command_value, str) or not command_value:
        raise OwnerError("offline_terminal_exact_command_missing")
    return command_value


def verify_local_contract() -> dict[str, Any]:
    request = load_json(REQUEST)
    terminal = load_json(OFFLINE_TERMINAL)
    source = request.get("component", {})
    expected = {
        "decode_scheduler_task_graph.py": source.get("candidate_source_sha256"),
        "install_decode_scheduler_task_graph.py": source.get("installer_sha256"),
        "exact_h200_consumer.py": source.get("consumer_sha256"),
        "DECODE_SCHEDULER_TASK_GRAPH_OFFLINE_TERMINAL.json": source.get("offline_terminal_sha256"),
    }
    checks = {f"hash:{name}": isinstance(wanted, str) and sha256(ROOT / name) == wanted for name, wanted in expected.items()}
    checks["request_hash"] = sha256(REQUEST) == load_json(STATUS)["director_component_request"]["sha256"]
    checks["pinned_image"] = request.get("execution_contract", {}).get("image") == IMAGE
    checks["no_checkpoint"] = request.get("execution_contract", {}).get("checkpoint_required") is False
    checks["one_component_invocation"] = request.get("execution_contract", {}).get("maximum_component_invocations") == 1
    checks["exact_command"] = exact_command() == terminal.get("h200_consumer", {}).get("command")
    checks["detached_owner_tool"] = DETACHED_OWNER.is_file() and os.access(DETACHED_OWNER, os.X_OK)
    checks["repair_handshake_tool"] = REPAIR.is_file() and os.access(REPAIR, os.X_OK)
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise OwnerError(f"local_contract_failed:{','.join(failed)}")
    return {"checks": checks, "packet_members": packet_manifest(), "exact_command": exact_command()}


def binding_value(path: Path) -> dict[str, Any]:
    binding = load_json(path)
    needed = ("bench_id", "host", "ssh_user", "identity_file", "known_hosts_file", "deadline_utc")
    missing = [key for key in needed if not isinstance(binding.get(key), str) or not binding[key]]
    if missing:
        raise OwnerError(f"binding_missing:{','.join(missing)}")
    if binding.get("project") not in (None, PROJECT):
        raise OwnerError("binding_project_mismatch")
    if binding.get("accelerator") not in (None, "nvidia-h200-sxm"):
        raise OwnerError("binding_accelerator_mismatch")
    if not Path(binding["identity_file"]).is_file() or not Path(binding["known_hosts_file"]).is_file():
        raise OwnerError("controller_identity_missing")
    deadline = dt.datetime.fromisoformat(binding["deadline_utc"].replace("Z", "+00:00"))
    if deadline <= utc_now():
        raise OwnerError("binding_deadline_elapsed")
    binding["deadline_utc"] = rfc3339(deadline)
    return binding


def durable_owner_state(path: Path) -> dict[str, Any]:
    for _ in range(50):
        if path.is_file():
            state = load_json(path)
            if state.get("unit_manager") != "pid":
                raise OwnerError("owner_state_not_controller_pid")
            if state.get("pid") != os.getpid():
                raise OwnerError("owner_state_pid_mismatch")
            if not isinstance(state.get("start_ticks"), int):
                raise OwnerError("owner_state_start_ticks_missing")
            return {"unit": str(path.resolve()), "pid": state["pid"], "start_ticks": state["start_ticks"], "unit_manager": "pid"}
        time.sleep(0.1)
    raise OwnerError("owner_state_not_persisted")


class Remote:
    def __init__(self, binding: dict[str, Any]):
        self.binding = binding
        self.target = f"{binding['ssh_user']}@{binding['host']}"
        self.common = ["-i", binding["identity_file"], "-o", "BatchMode=yes", "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={binding['known_hosts_file']}"]

    def ssh(self, script: str, timeout: int) -> subprocess.CompletedProcess[str]:
        return command(["ssh", *self.common, self.target, script], timeout)

    def scp_to(self, source: Path, destination: str, timeout: int) -> subprocess.CompletedProcess[str]:
        return command(["scp", "-p", *self.common, str(source), f"{self.target}:{destination}"], timeout)

    def scp_from(self, source: str, destination: Path, timeout: int) -> subprocess.CompletedProcess[str]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        return command(["scp", "-p", *self.common, f"{self.target}:{source}", str(destination)], timeout)


def pool(*args: str) -> subprocess.CompletedProcess[str]:
    return command(["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args], 60, env={**os.environ, "PYTHONPATH": str(FACTORY_SRC)})


def bounded_timeout(deadline: dt.datetime, requested: int) -> int:
    remaining = int((deadline - utc_now()).total_seconds())
    if remaining <= 0:
        raise OwnerError("owner_deadline_elapsed")
    return min(requested, remaining)


def write_command_logs(artifact: Path, stem: str, result: subprocess.CompletedProcess[str]) -> None:
    (artifact / f"{stem}.stdout.log").write_text(result.stdout)
    (artifact / f"{stem}.stderr.log").write_text(result.stderr)
    atomic_json(artifact / f"{stem}.result.json", {"returncode": result.returncode, "at_utc": rfc3339(utc_now())})


def retrieve(remote: Remote, remote_path: str, local: Path, deadline: dt.datetime, *, required: bool) -> bool:
    result = remote.scp_from(remote_path, local, bounded_timeout(deadline, 300))
    atomic_json(local.with_suffix(local.suffix + ".retrieval.json"), {"remote_path": remote_path, "returncode": result.returncode, "stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]})
    if result.returncode and required:
        raise OwnerError(f"typed_retrieval_boundary:{Path(remote_path).name}:{result.stderr[-500:]}")
    return result.returncode == 0


def remote_packet(remote: Remote, packet: Path, manifest: list[dict[str, Any]], deadline: dt.datetime) -> str:
    packet_hash = sha256(packet)
    remote_packet = f"{REMOTE_ROOT}/packets/{packet_hash}.tar"
    remote_project = f"{REMOTE_ROOT}/packets/{packet_hash}"
    wanted_manifest = json.dumps(manifest, sort_keys=True)
    probe = remote.ssh(
        f"mkdir -p {shlex.quote(REMOTE_ROOT)}/packets {shlex.quote(REMOTE_ROOT)}/runs && "
        f"test -f {shlex.quote(remote_project)}/PACKET_MANIFEST.json && "
        f"test \"$(sha256sum {shlex.quote(remote_packet)} | cut -d' ' -f1)\" = {packet_hash}",
        bounded_timeout(deadline, 120),
    )
    if probe.returncode == 0:
        return remote_project
    part = f"{remote_packet}.{packet_hash}.part"
    sent = remote.scp_to(packet, part, bounded_timeout(deadline, 600))
    if sent.returncode:
        raise OwnerError(f"packet_stage_copy:{sent.stderr[-500:]}")
    finalize = remote.ssh(
        f"set -eu; test \"$(sha256sum {shlex.quote(part)} | cut -d' ' -f1)\" = {packet_hash}; "
        f"rm -rf {shlex.quote(remote_project)}.part; mkdir -p {shlex.quote(remote_project)}.part; "
        f"tar -xf {shlex.quote(part)} -C {shlex.quote(remote_project)}.part; "
        f"printf '%s\\n' {shlex.quote(wanted_manifest)} > {shlex.quote(remote_project)}.part/PACKET_MANIFEST.json; "
        f"mv {shlex.quote(remote_project)}.part {shlex.quote(remote_project)}; mv {shlex.quote(part)} {shlex.quote(remote_packet)}",
        bounded_timeout(deadline, 300),
    )
    if finalize.returncode:
        raise OwnerError(f"packet_stage_finalize:{finalize.stderr[-500:]}")
    return remote_project


def pull_image(remote: Remote, deadline: dt.datetime) -> None:
    result = remote.ssh(f"sudo -n docker pull {shlex.quote(IMAGE)}", bounded_timeout(deadline, 900))
    if result.returncode:
        raise OwnerError(f"pinned_image_pull:{result.stderr[-500:]}")


def release(bench_id: str, claimed_at: str, condition: str, contents: Path, artifact: Path) -> None:
    result = pool("release", "--project", PROJECT, "--bench", bench_id, "--expected-claimed-at", claimed_at, "--condition", condition, "--contents", str(contents))
    write_command_logs(artifact, "release", result)
    if result.returncode:
        raise OwnerError(f"release_failed:{result.stderr[-500:]}")


def update_status(**changes: Any) -> None:
    status = load_json(STATUS)
    status.update(changes)
    atomic_json(STATUS, status)


def retain_for_repair(remote: Remote, artifact: Path, deadline: dt.datetime, diagnostic: str, bench_id: str, claimed_at: str, session: dict[str, Any]) -> None:
    repair_id = f"decode-scheduler-{artifact.name}-{time.time_ns()}"
    repair_root = artifact / "repair"
    ready = command([str(REPAIR), "ready", "--root", str(repair_root), "--repair-id", repair_id, "--deadline", rfc3339(deadline), "--failure-kind", "ordinary_pre_science_integration_or_retrieval_defect", "--diagnostic", diagnostic, "--retry-scope", "only pinned-image, packet staging, launcher, retrieval, or unstarted exact consumer; never replay a retrieved scientific terminal"], 60)
    write_command_logs(artifact, "repair_ready", ready)
    if ready.returncode:
        raise OwnerError(f"repair_handshake_failed:{ready.stderr[-500:]}")
    atomic_json(ROOT / "REPAIR_READY.json", {"artifact_root": str(artifact), "repair_id": repair_id, "bench_id": bench_id, "claimed_at": claimed_at, "deadline_utc": rfc3339(deadline), "diagnostic": diagnostic, "handshake_root": str(repair_root)})
    update_status(active_session={**session, "artifact_root": str(artifact), "bench_id": bench_id, "expected_claimed_at": claimed_at, "deadline_utc": rfc3339(deadline), "repair_handshake_root": str(repair_root), "forward_progress": "retained claim heartbeating while awaiting a hash-bound repair request"})
    waited = command([str(REPAIR), "wait", "--root", str(repair_root), "--repair-id", repair_id, "--poll-seconds", "5"], bounded_timeout(deadline, MAX_OWNER_SECONDS))
    write_command_logs(artifact, "repair_wait", waited)
    if waited.returncode == 0 and '"state": "requested"' in waited.stdout:
        raise RepairRequested("repair_request_requires_replacement_owner")
    raise OwnerError("repair_deadline_or_handshake_terminal")


def run_owner(binding_path: Path, owner_state_path: Path) -> int:
    contract = verify_local_contract()
    binding = binding_value(binding_path)
    deadline = min(dt.datetime.fromisoformat(binding["deadline_utc"].replace("Z", "+00:00")), utc_now() + dt.timedelta(seconds=MAX_OWNER_SECONDS))
    artifact = ROOT / "artifacts" / utc_now().strftime("h200-decode-scheduler-%Y%m%dt%H%M%Sz")
    artifact.mkdir(parents=True, exist_ok=False)
    atomic_json(artifact / "OWNER_CONTRACT.json", {"binding_sha256": sha256(binding_path), "deadline_utc": rfc3339(deadline), **contract})
    session = durable_owner_state(owner_state_path)
    update_status(active_session={**session, "artifact_root": str(artifact), "bench_id": binding["bench_id"], "deadline_utc": rfc3339(deadline), "expected_terminal": "artifacts/h200_exact_consumer/TERMINAL.json", "forward_progress": "durable controller verified; atomic claim has not yet been attempted"})
    claim = pool("claim", "--project", PROJECT, "--bench", binding["bench_id"], "--lease-seconds", "300")
    write_command_logs(artifact, "claim", claim)
    if claim.returncode:
        raise OwnerError(f"typed_pool_boundary:claim:{claim.stderr[-500:]}")
    bench = json.loads(claim.stdout)
    claimed_at = bench["claim"]["claimed_at"]
    if bench["id"] != binding["bench_id"]:
        raise OwnerError("claimed_unbound_bench")
    remote = Remote(binding)
    stopping = threading.Event()

    def heartbeat() -> None:
        while not stopping.wait(45):
            result = pool("heartbeat", "--project", PROJECT, "--bench", binding["bench_id"])
            write_command_logs(artifact, "heartbeat", result)

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    released = False
    terminal_local = artifact / "TERMINAL.json"
    invocation_local = artifact / "INVOCATION_STATE.json"
    try:
        initial = pool("heartbeat", "--project", PROJECT, "--bench", binding["bench_id"])
        write_command_logs(artifact, "initial_heartbeat", initial)
        if initial.returncode:
            raise OwnerError(f"initial_heartbeat:{initial.stderr[-500:]}")
        packet = artifact / "packet.tar"
        with tarfile.open(packet.with_suffix(".part"), "w") as archive:
            for member in PACKET_MEMBERS:
                archive.add(ROOT / member, arcname=member, recursive=False)
        os.replace(packet.with_suffix(".part"), packet)
        remote_project = remote_packet(remote, packet, contract["packet_members"], deadline)
        pull_image(remote, deadline)
        output = f"{REMOTE_ROOT}/runs/{artifact.name}"
        prepare = remote.ssh(f"rm -rf {shlex.quote(output)}.part; mkdir -p {shlex.quote(output)}.part; mv {shlex.quote(output)}.part {shlex.quote(output)}", bounded_timeout(deadline, 120))
        write_command_logs(artifact, "prepare_output", prepare)
        if prepare.returncode:
            raise OwnerError(f"output_prepare:{prepare.stderr[-500:]}")
        exact = exact_command()
        remote_command = (
            f"sudo -n docker run --rm --gpus all --network none --ipc=host "
            # Docker must create the nested exact-command output mount beneath
            # this absolute project path.  A read-only parent mount prevents
            # runc from creating that mountpoint before Python starts.
            f"-v {shlex.quote(remote_project)}:{shlex.quote(REMOTE_PROJECT)} "
            f"-v {shlex.quote(output)}:{shlex.quote(REMOTE_PROJECT + '/artifacts/h200_exact_consumer')} "
            f"-w {shlex.quote(REMOTE_PROJECT)} {shlex.quote(IMAGE)} /bin/bash -lc {shlex.quote(exact)}"
        )
        result = remote.ssh(remote_command, bounded_timeout(deadline, 900))
        write_command_logs(artifact, "exact_component", result)
        remote_terminal = output + "/TERMINAL.json"
        remote_invocation = output + "/INVOCATION_STATE.json"
        terminal_retrieved = retrieve(remote, remote_terminal, terminal_local, deadline, required=False)
        invocation_retrieved = retrieve(remote, remote_invocation, invocation_local, deadline, required=False)
        if terminal_retrieved:
            terminal = load_json(terminal_local)
            invocation = load_json(invocation_local) if invocation_retrieved else {"candidate_cuda_invocation_started": "unknown"}
            atomic_json(ROOT / "H200_COMPONENT_TERMINAL.json", {"terminal": terminal, "terminal_sha256": sha256(terminal_local), "invocation": invocation, "invocation_sha256": sha256(invocation_local) if invocation_retrieved else None, "raw_evidence_root": str(artifact)})
            contents = artifact / "BENCH_CONTENTS.json"
            atomic_json(contents, {"project": PROJECT, "result": terminal.get("result", terminal.get("terminal_type")), "artifacts": str(artifact), "image": IMAGE, "checkpoint": "none; this component is checkpoint-free", "candidate_cuda_invocation_started": invocation.get("candidate_cuda_invocation_started"), "server_state": "No resident endpoint; pinned image and project packet retained.", "release_reason": "typed terminal retrieved"})
            update_status(actual_spend_usd=float(load_json(STATUS).get("actual_spend_usd", 0.0)) + max(0.0, (utc_now() - dt.datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))).total_seconds()) * RATE_USD_PER_HOUR / 3600.0, active_session=None, summary="H200 decode scheduler component terminal retrieved and claim released.")
            release(binding["bench_id"], claimed_at, "ready", contents, artifact)
            released = True
            return 0
        diagnostic = f"exact_component_exit={result.returncode}; terminal_retrieved={terminal_retrieved}; invocation_retrieved={invocation_retrieved}"
        retain_for_repair(remote, artifact, deadline, diagnostic, binding["bench_id"], claimed_at, session)
    except RepairRequested:
        # The claim remains live.  The replacement owner receives the
        # hash-bound request and must adopt this exact claim generation.
        return 2
    except Exception as error:
        if not released:
            try:
                retain_for_repair(remote, artifact, deadline, repr(error), binding["bench_id"], claimed_at, session)
            except Exception as repair_error:
                atomic_json(artifact / "OWNER_FAILURE.json", {"error": repr(error), "repair_error": repr(repair_error), "claimed_at": claimed_at, "deadline_utc": rfc3339(deadline)})
                # A nonrecoverable owner/repair boundary reaches maintenance only
                # after preserving the diagnostic and exact claim generation.
                contents = artifact / "BENCH_CONTENTS.json"
                atomic_json(contents, {"project": PROJECT, "result": "typed_owner_or_deadline_boundary", "artifacts": str(artifact), "image": IMAGE, "checkpoint": "none", "release_reason": repr(repair_error)})
                release(binding["bench_id"], claimed_at, "maintenance", contents, artifact)
                released = True
                raise
        raise
    finally:
        stopping.set()
        thread.join(2)


def offline_check() -> int:
    contract = verify_local_contract()
    print(json.dumps({"pass": True, "checks": contract["checks"], "packet_members": contract["packet_members"], "exact_command_sha256": hashlib.sha256(contract["exact_command"].encode()).hexdigest()}, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--owner-state", type=Path)
    parser.add_argument("--offline-check", action="store_true")
    args = parser.parse_args()
    if args.offline_check:
        return offline_check()
    if args.binding is None:
        parser.error("--binding is required unless --offline-check is used")
    if args.owner_state is None:
        parser.error("--owner-state is required so STATUS.json can bind the durable controller")
    return run_owner(args.binding, args.owner_state)


if __name__ == "__main__":
    raise SystemExit(main())
