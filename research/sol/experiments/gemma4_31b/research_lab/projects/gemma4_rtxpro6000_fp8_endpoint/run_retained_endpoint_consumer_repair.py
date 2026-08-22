#!/usr/bin/env python3
"""Retry only the zero-request endpoint consumer through the retained SSH server."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time


PROJECT = Path(__file__).resolve().parent
ARTIFACT_ROOT = (
    PROJECT / "artifacts" / "rtxpro6000-fp8-endpoint-20260729t0338z"
)
PAIR_ROOT = ARTIFACT_ROOT / "endpoint-pair"
GENERATION = "repair-1785301292"
ARCHIVED_ROOT = ARTIFACT_ROOT / f"endpoint-pair-{GENERATION}-zero-request-partial"
FRESH_ROOT = ARTIFACT_ROOT / f"endpoint-pair-{GENERATION}-ssh-tunnel"
EVIDENCE_PATH = ARTIFACT_ROOT / "ENDPOINT_CONSUMER_SSH_TUNNEL_REPAIR.json"
STDOUT_PATH = ARTIFACT_ROOT / f"{GENERATION}-endpoint-consumer.stdout"
STDERR_PATH = ARTIFACT_ROOT / f"{GENERATION}-endpoint-consumer.stderr"
WORKLOAD = PROJECT / "inputs" / "c32_requests.jsonl"
LAB_ENDPOINT_PAIR = (
    PROJECT.parents[5] / "factory" / "tools" / "lab-endpoint-pair"
)
PUBLIC_HOST = "213.192.6.70"
PUBLIC_PORT = 60547
LOCAL_PORT = 19124
REMOTE_PORT = 19123
PUBLIC_URL = f"http://{PUBLIC_HOST}:{PUBLIC_PORT}"
SSH = [
    "ssh",
    "-F",
    "/dev/null",
    "-i",
    "/root/.config/nebius/glm-campaign/ssh_ed25519",
    "-o",
    "UserKnownHostsFile=/root/.config/runpod/gemma4/known_hosts",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "BatchMode=yes",
    "-o",
    "ExitOnForwardFailure=yes",
    "-o",
    "ServerAliveInterval=15",
    "-o",
    "ServerAliveCountMax=4",
    "-p",
    "40070",
    "-N",
    "-L",
    f"127.0.0.1:{LOCAL_PORT}:127.0.0.1:{REMOTE_PORT}",
    f"root@{PUBLIC_HOST}",
]
IPTABLES_RULE = [
    "-t",
    "nat",
    "-I",
    "OUTPUT",
    "1",
    "-p",
    "tcp",
    "-d",
    PUBLIC_HOST,
    "--dport",
    str(PUBLIC_PORT),
    "-j",
    "REDIRECT",
    "--to-ports",
    str(LOCAL_PORT),
]
IPTABLES_DELETE = [
    "-t",
    "nat",
    "-D",
    "OUTPUT",
    "-p",
    "tcp",
    "-d",
    PUBLIC_HOST,
    "--dport",
    str(PUBLIC_PORT),
    "-j",
    "REDIRECT",
    "--to-ports",
    str(LOCAL_PORT),
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def digest(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def manifest(root: Path) -> list[dict[str, object]]:
    return [
        {**digest(path), "relative_path": str(path.relative_to(root))}
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def write_json_atomic(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def wait_for_tunnel(process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"SSH tunnel exited with {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", LOCAL_PORT), timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError("SSH tunnel did not accept local connections")


def main() -> int:
    started_at = utc_now()
    run = json.loads((PAIR_ROOT / "run.json").read_text())
    progress = run.get("progress", {})
    complete_requests = sum(
        int(row.get("complete_requests", 0)) for row in progress.values()
    )
    successful_requests = sum(
        int(row.get("successful_requests", 0)) for row in progress.values()
    )
    if run.get("complete") or complete_requests or successful_requests:
        raise RuntimeError("existing endpoint consumer has decision-bearing results")
    if ARCHIVED_ROOT.exists() or FRESH_ROOT.exists() or EVIDENCE_PATH.exists():
        raise FileExistsError("repair output already exists; refusing a silent replay")

    partial_manifest = manifest(PAIR_ROOT)
    os.rename(PAIR_ROOT, ARCHIVED_ROOT)

    command = [
        str(LAB_ENDPOINT_PAIR),
        "run",
        "--workload",
        str(WORKLOAD),
        "--output-dir",
        str(FRESH_ROOT),
        "--control-url",
        PUBLIC_URL,
        "--candidate-url",
        PUBLIC_URL,
        "--arm-order",
        "control",
        "--concurrency",
        "32",
        "--timeout-seconds",
        "900",
    ]
    tunnel: subprocess.Popen[bytes] | None = None
    rule_installed = False
    returncode: int | None = None
    exception: str | None = None
    try:
        tunnel = subprocess.Popen(SSH)
        wait_for_tunnel(tunnel)
        subprocess.run(["iptables", *IPTABLES_RULE], check=True)
        rule_installed = True
        with STDOUT_PATH.open("wb") as stdout, STDERR_PATH.open("wb") as stderr:
            completed = subprocess.run(
                command,
                cwd=PROJECT.parents[6],
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
        returncode = completed.returncode
    except Exception as error:  # Preserve an interpretable repair artifact on failure.
        exception = f"{type(error).__name__}: {error}"
    finally:
        if rule_installed:
            subprocess.run(["iptables", *IPTABLES_DELETE], check=True)
        if tunnel is not None and tunnel.poll() is None:
            tunnel.send_signal(signal.SIGTERM)
            try:
                tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tunnel.kill()
                tunnel.wait(timeout=10)

    fresh_run_path = FRESH_ROOT / "run.json"
    fresh_run = json.loads(fresh_run_path.read_text()) if fresh_run_path.exists() else {}
    valid = bool(
        returncode == 0
        and fresh_run.get("complete")
        and fresh_run.get("artifact_complete")
        and fresh_run.get("all_requests_successful")
        and fresh_run.get("progress", {}).get("control", {}).get("complete_requests")
        == 32
        and fresh_run.get("progress", {}).get("control", {}).get(
            "successful_requests"
        )
        == 32
    )
    if valid:
        os.rename(FRESH_ROOT, PAIR_ROOT)

    evidence = {
        "schema_version": 1,
        "kind": "endpoint_consumer_ssh_tunnel_repair",
        "generation": GENERATION,
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "decision": "retry only the zero-request endpoint consumer",
        "hypothesis": (
            "The retained SGLang server is healthy on remote loopback, and routing "
            "the unchanged public endpoint URL through SSH repairs only transport."
        ),
        "scope": "endpoint_consumer_only",
        "sample_limit": 1,
        "prior_partial": {
            "complete_requests": complete_requests,
            "successful_requests": successful_requests,
            "archived_root": str(ARCHIVED_ROOT),
            "manifest": partial_manifest,
        },
        "scientific_contract": {
            "arm_order": ["control"],
            "concurrency": 32,
            "endpoint_url": PUBLIC_URL,
            "endpoint_url_sha256": hashlib.sha256(PUBLIC_URL.encode()).hexdigest(),
            "timeout_seconds": 900,
            "workload": digest(WORKLOAD),
        },
        "transport_amendment": {
            "ssh_destination": f"root@{PUBLIC_HOST}:40070",
            "forward": f"127.0.0.1:{LOCAL_PORT}->127.0.0.1:{REMOTE_PORT}",
            "redirect_destination": f"{PUBLIC_HOST}:{PUBLIC_PORT}",
            "redirect_removed": rule_installed,
        },
        "command": command,
        "returncode": returncode,
        "exception": exception,
        "valid_interpretable_sample": valid,
        "result": digest(PAIR_ROOT / "run.json") if valid else (
            digest(fresh_run_path) if fresh_run_path.exists() else None
        ),
        "stdout": digest(STDOUT_PATH) if STDOUT_PATH.exists() else None,
        "stderr": digest(STDERR_PATH) if STDERR_PATH.exists() else None,
    }
    write_json_atomic(EVIDENCE_PATH, evidence)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
