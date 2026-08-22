#!/usr/bin/env python3
"""Durable owner for one selective M384 generation with retained repair."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/root/workspace/research/factory/src")
from grad_research.gpu_claim_session import GpuClaimSession
from grad_research.gpu_pool import GpuPool

LAB = Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
PROJECT = "gemma4_h200_m384_target_verify_attention_executor"
TOOLS = Path("/root/workspace/research/factory/tools")


def atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def terminal_is_releaseable(terminal: dict) -> bool:
    rows = terminal.get("rows", [])
    return (
        terminal.get("classification") == "interpretable_component_result"
        and terminal.get("science_consumed") is True
        and terminal.get("cuda_invocation_started") is True
        and terminal.get("ledger_complete") is True
        and {row.get("family") for row in rows} == {"local", "global"}
        and all(row.get("correct") is True and "stock_median_ms" in row and "candidate_median_ms" in row for row in rows)
    )


def run_worker(artifact_root: Path, deadline: float, connection: dict) -> dict:
    """Only the bound generation's worker is executable; errors remain repairable."""
    key = connection["ssh_identity_path"]
    known_hosts = connection["known_hosts_namespace"]
    host = f'{connection["ssh_user"]}@{connection["public_ipv4"]}'
    remote_root = "/home/glmrunner/m384-selective"
    common = ["-i", key, "-o", f"UserKnownHostsFile={known_hosts}", "-o", "StrictHostKeyChecking=yes"]
    transfer = subprocess.run(
        ["scp", *common, "m384_attention_h200_runner.py", "m384_grouped_attention_sm90a.cu", f"{host}:{remote_root}/"],
        cwd=Path.cwd(), text=True, capture_output=True, timeout=120,
    )
    (artifact_root / "runner-transfer.stderr").write_text(transfer.stderr)
    if transfer.returncode:
        raise RuntimeError("runner_transfer_failed")
    command = (
        "sudo -n docker run --rm --gpus all -v " + remote_root + ":/work -w /work "
        "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6 "
        "bash -lc 'python3 m384_attention_h200_runner.py --stage /work/stage --source /work/m384_grouped_attention_sm90a.cu --output /work/COMPONENT_TERMINAL.json'"
    )
    timeout = max(30, int(deadline - time.time() - 20))
    worker = subprocess.run(["ssh", *common, host, command], text=True, capture_output=True, timeout=timeout)
    (artifact_root / "worker.stdout").write_text(worker.stdout)
    (artifact_root / "worker.stderr").write_text(worker.stderr)
    if worker.returncode:
        atomic(artifact_root / "WORKER_EXIT.json", {"returncode": worker.returncode, "science_started_marker_present": (artifact_root / "science_started.json").exists()})
        raise RuntimeError(f"worker_nonzero_exit_{worker.returncode}")
    copied = subprocess.run(
        ["scp", *common, f"{host}:{remote_root}/COMPONENT_TERMINAL.json", f"{host}:{remote_root}/science_started.json", str(artifact_root)],
        text=True, capture_output=True, timeout=60,
    )
    (artifact_root / "terminal-retrieval.stderr").write_text(copied.stderr)
    if copied.returncode:
        raise RuntimeError("terminal_retrieval_failed")
    terminal = json.loads((artifact_root / "COMPONENT_TERMINAL.json").read_text())
    terminal["science_started_marker_sha256"] = digest(artifact_root / "science_started.json")
    terminal["worker_returncode"] = worker.returncode
    return terminal


def repair_id(session: GpuClaimSession) -> str:
    return f"m384-selective-{session.claimed_at.replace(':', '').replace('+', 'p')}"


def dispatch_repair(session: GpuClaimSession, artifact_root: Path, deadline: float, connection: dict, error: BaseException) -> int:
    """Keep the generation claimed, consume a hash-bound repair packet, rerun only worker."""
    diagnostic = artifact_root / "RECOVERABLE_DIAGNOSTIC.json"
    atomic(diagnostic, {"classification": "recoverable_stock_or_retrieval_defect", "error": repr(error), "cuda_started": "unknown", "science_started": "unknown"})
    rid = repair_id(session)
    repair_deadline = datetime.fromtimestamp(deadline - 20, timezone.utc).isoformat().replace("+00:00", "Z")
    held = subprocess.run([
        str(TOOLS / "repair-handshake"), "hold", "--root", str(artifact_root), "--repair-id", rid,
        "--deadline", repair_deadline, "--failure-kind", "integration", "--diagnostic", str(diagnostic),
        "--retry-scope", "generation-specific stock-adapter, terminal-retrieval, or candidate-consumer repair only",
    ], text=True, capture_output=True, timeout=max(30, int(deadline - time.time() - 5)))
    (artifact_root / "repair-dispatch.stdout").write_text(held.stdout)
    (artifact_root / "repair-dispatch.stderr").write_text(held.stderr)
    state = json.loads(held.stdout.splitlines()[-1]) if held.stdout.strip() else {"state": "invalid"}
    if state.get("state") != "requested":
        session.release(condition="maintenance", contents={"summary": "repair deadline or terminal", "repair_state": state.get("state")})
        return 2
    request = state["request"]
    packet = Path(request["patch_artifact"])
    if not packet.is_file():
        raise RuntimeError("repair_packet_path_invalid")
    packet_sha256 = digest(packet)
    atomic(artifact_root / "REPAIR_CONSUMED.json", {
        "repair_id": rid, "ready_sha256": state["ready_sha256"],
        "request_sha256": hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest(),
        "patch_artifact": str(packet), "patch_sha256": packet_sha256,
    })
    terminal = run_worker(artifact_root, deadline, connection)
    if terminal_is_releaseable(terminal):
        session.release(condition="ready", contents={"summary": "interpretable local/global selective component", "terminal_sha256": digest(artifact_root / "COMPONENT_TERMINAL.json")})
        return 0
    raise RuntimeError("repaired_worker_terminal_not_releaseable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--bench", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    binding = json.loads(args.binding.read_text())
    deadline = datetime.fromisoformat(binding["clock"]["hard_release_utc"].replace("Z", "+00:00")).timestamp()
    pool = GpuPool(LAB)
    session = GpuClaimSession(pool, PROJECT, args.bench, lease_seconds=max(60, int(deadline - time.time())), heartbeat_seconds=20, release_on_exception=False)
    connection = None
    try:
        with session:
            bench = pool.show(args.bench)
            connection = {key: bench["resource"][key] for key in ("public_ipv4", "ssh_user", "ssh_identity_path", "known_hosts_namespace")}
            if bench.get("claim", {}).get("claimed_at") != session.claimed_at:
                raise RuntimeError("claimed_generation_not_visible_in_current_bench_record")
            artifact_root = args.artifact_root.resolve()
            atomic(artifact_root / "OWNER_FINAL_WARM_DYNAMIC_READY.json", {
                "state": "dynamic_ready", "claimed_at": session.claimed_at,
                "bench": args.bench, "connection": connection,
                "worker_boundary": "retained selective stage -> installed SGLang stock/candidate ledger",
                "at_utc": datetime.now(timezone.utc).isoformat(),
            })
            terminal = run_worker(artifact_root, deadline, connection)
            if not terminal_is_releaseable(terminal):
                raise RuntimeError("worker_terminal_missing_bound_evidence")
            session.release(condition="ready", contents={"summary": "interpretable local/global selective component", "terminal_sha256": digest(args.artifact_root / "COMPONENT_TERMINAL.json")})
            return 0
    except BaseException as error:
        # __exit__ preserved the live heartbeat because release_on_exception=False.
        if connection is None:
            raise
        return dispatch_repair(session, args.artifact_root.resolve(), deadline, connection, error)


if __name__ == "__main__":
    raise SystemExit(main())
