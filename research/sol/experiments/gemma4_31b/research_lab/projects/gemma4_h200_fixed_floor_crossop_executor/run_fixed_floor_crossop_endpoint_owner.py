#!/usr/bin/env python3
"""Durable controller for a later director-bound fixed-floor endpoint pair."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import threading
import time


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
POOL = ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
FACTORY_ENV = {**os.environ, "PYTHONPATH": "/root/workspace/research/factory/src"}


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command(arguments: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, text=True, capture_output=True, check=False, timeout=timeout, env=FACTORY_ENV)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def remaining(deadline: dt.datetime, reserve: int = 0) -> int:
    return max(1, int((deadline - utcnow()).total_seconds()) - reserve)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-binding", type=pathlib.Path, required=True)
    parser.add_argument("--owner-state", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    arguments = parser.parse_args()
    binding = json.loads(arguments.execution_binding.read_text())
    packet = json.loads((PROJECT / "ENDPOINT_INTEGRATION_PACKET_R1.json").read_text())
    if not binding.get("endpoint_execution_allowed") or binding.get("project") != packet["project"]:
        raise RuntimeError("director_execution_binding_required")
    deadline = dt.datetime.fromisoformat(binding["absolute_release_deadline_utc"].replace("Z", "+00:00"))
    bench = binding["bench_id"]
    expected = packet["files"]
    for name, digest in expected.items():
        if sha256(PROJECT / name) != digest:
            raise RuntimeError("packet_hash_mismatch:" + name)
    claim = command(POOL + ["claim", "--project", packet["project"], "--bench", bench, "--lease-seconds", str(remaining(deadline, 90))], 60)
    if claim.returncode:
        raise RuntimeError("claim_failed:" + claim.stderr[-800:])
    arguments.artifact_root.mkdir(parents=True, exist_ok=False)
    atomic(arguments.artifact_root / "CLAIM.json", {"stdout": claim.stdout, "at_utc": utcnow().isoformat()})
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(45):
            result = command(POOL + ["heartbeat", "--project", packet["project"]], 30)
            atomic(arguments.artifact_root / "HEARTBEAT.json", {"at_utc": utcnow().isoformat(), "returncode": result.returncode, "stderr": result.stderr[-800:]})

    threading.Thread(target=heartbeat, daemon=True).start()
    terminal: dict | None = None
    recoverable: dict | None = None
    try:
        inventory = json.loads(command(POOL + ["show", "--bench", bench], 30).stdout)
        resource = inventory["resource"]
        if resource["gpu_uuid"] != packet["identities"]["gpu_uuid"] or resource["ssh_ed25519_fingerprint"] != packet["identities"]["ssh_fingerprint"]:
            raise RuntimeError("bench_identity_mismatch")
        remote = binding["remote_root"]
        key, known = pathlib.Path(resource["ssh_identity_path"]), pathlib.Path(resource["known_hosts_namespace"])
        if not key.is_file() or not known.is_file(): raise RuntimeError("local_ssh_identity_missing")
        source = [name for name in expected if name.endswith(".py") or name.endswith(".json")]
        archive = arguments.artifact_root / "packet.tar"
        subprocess.run(["tar", "-cf", str(archive), "-C", str(PROJECT), *source], check=True, timeout=120)
        ssh_base = ["ssh", "-i", str(key), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known}", f"{resource['ssh_user']}@{resource['public_ipv4']}"]
        scp = ["scp", "-i", str(key), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known}", str(archive), f"{resource['ssh_user']}@{resource['public_ipv4']}:{remote}/packet.tar"]
        if subprocess.run(scp, text=True, capture_output=True, timeout=remaining(deadline, 240)).returncode: raise RuntimeError("packet_stage_failed")
        unpack = subprocess.run(ssh_base + [f"mkdir -p {remote}/project {remote}/artifacts && tar -xf {remote}/packet.tar -C {remote}/project"], text=True, capture_output=True, timeout=remaining(deadline, 210))
        if unpack.returncode: raise RuntimeError("packet_unpack_failed:" + unpack.stderr[-800:])
        remote_out = f"{remote}/artifacts/{arguments.artifact_root.name}"
        worker = subprocess.run(ssh_base + [f"python3 {remote}/project/run_fixed_floor_crossop_endpoint_pair.py --project {remote}/project --checkpoint {binding['checkpoint_path']} --output {remote_out}"], text=True, capture_output=True, timeout=remaining(deadline, 150))
        (arguments.artifact_root / "worker.stdout").write_text(worker.stdout); (arguments.artifact_root / "worker.stderr").write_text(worker.stderr)
        terminal = {"returncode": worker.returncode, "candidate_cuda_started": True, "remote_output": remote_out}
        if worker.returncode: recoverable = {"classification": "endpoint_worker_failure", "retry_scope": "pair_runner_only", "terminal": terminal}
        else:
            retrieved = subprocess.run([*scp[:-2], f"{resource['ssh_user']}@{resource['public_ipv4']}:{remote_out}/PAIR_TERMINAL.json", str(arguments.artifact_root / "PAIR_TERMINAL.json")], text=True, capture_output=True, timeout=remaining(deadline, 120))
            if retrieved.returncode: recoverable = {"classification": "terminal_retrieval_failure", "retry_scope": "retrieval_only", "terminal": terminal}
            else: terminal["pair"] = json.loads((arguments.artifact_root / "PAIR_TERMINAL.json").read_text())
    except Exception as exc:
        recoverable = {"classification": "controller_or_staging_failure", "retry_scope": "named_invalidated_stage_only", "error": f"{type(exc).__name__}: {exc}", "terminal": terminal}
    if recoverable:
        repair_id = "endpoint-r1-" + str(int(time.time()))
        diagnostic = arguments.artifact_root / "RECOVERABLE_DIAGNOSTIC.json"
        atomic(diagnostic, recoverable)
        ready = command(["/root/workspace/research/factory/tools/repair-handshake", "ready", "--root", str(arguments.artifact_root), "--repair-id", repair_id, "--deadline", deadline.isoformat(), "--failure-kind", recoverable["classification"], "--diagnostic", sha256(diagnostic), "--retry-scope", recoverable["retry_scope"]], 30)
        if ready.returncode:
            raise RuntimeError("repair_ready_failed:" + ready.stderr[-800:])
        wait = command(["/root/workspace/research/factory/tools/repair-handshake", "wait", "--root", str(arguments.artifact_root), "--repair-id", repair_id, "--deadline", deadline.isoformat()], remaining(deadline))
        if wait.returncode == 0 and json.loads(wait.stdout).get("state") == "requested":
            request_path = arguments.artifact_root / ".repair-handshakes" / repair_id / "REPAIR_REQUEST.json"
            consumed = request_path.with_name("REPAIR_REQUEST." + sha256(request_path) + ".consumed.json")
            request_path.replace(consumed)
            request = json.loads(consumed.read_text())
            if request.get("retry_scope") not in {"pair_runner_only", "retrieval_only"}:
                raise RuntimeError("unsupported_repair_scope:" + str(request.get("retry_scope")))
            if request["retry_scope"] == "pair_runner_only":
                retry = subprocess.run(ssh_base + [f"python3 {remote}/project/run_fixed_floor_crossop_endpoint_pair.py --project {remote}/project --checkpoint {binding['checkpoint_path']} --output {remote_out}-repair-{repair_id}"], text=True, capture_output=True, timeout=remaining(deadline, 150))
                (arguments.artifact_root / "repair-worker.stdout").write_text(retry.stdout); (arguments.artifact_root / "repair-worker.stderr").write_text(retry.stderr)
                if retry.returncode: raise RuntimeError("repair_pair_failed")
                remote_out = remote_out + "-repair-" + repair_id
            retrieved = subprocess.run([*scp[:-2], f"{resource['ssh_user']}@{resource['public_ipv4']}:{remote_out}/PAIR_TERMINAL.json", str(arguments.artifact_root / "PAIR_TERMINAL.json")], text=True, capture_output=True, timeout=remaining(deadline, 120))
            if retrieved.returncode: raise RuntimeError("repair_retrieval_failed")
            terminal = {"classification": "repaired_endpoint_terminal", "pair": json.loads((arguments.artifact_root / "PAIR_TERMINAL.json").read_text()), "repair_request_sha256": sha256(consumed)}
        else:
            terminal = {"classification": "repair_deadline_or_request_boundary", "recoverable": recoverable, "wait": wait.stdout[-800:]}
    atomic(arguments.artifact_root / "TERMINAL.json", terminal)
    release = command(POOL + ["release", "--project", packet["project"], "--condition", "ready", "--contents", str(arguments.artifact_root / "TERMINAL.json")], 60)
    atomic(arguments.artifact_root / "RELEASE.json", {"returncode": release.returncode, "stdout": release.stdout, "stderr": release.stderr})
    stop.set()


if __name__ == "__main__":
    main()
