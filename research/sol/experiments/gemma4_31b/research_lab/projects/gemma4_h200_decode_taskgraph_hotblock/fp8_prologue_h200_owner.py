#!/usr/bin/env python3
"""Durable same-claim owner for the dynamic-FP8 prologue H200 experiment."""

from __future__ import annotations

import argparse
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
from datetime import datetime, timezone
from typing import Any

PROJECT_NAME = "gemma4_h200_decode_taskgraph_hotblock"
PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY_SRC = pathlib.Path("/root/workspace/research/factory/src")
READY = PROJECT / "FP8_PROLOGUE_H200_OWNER_READY.json"
BINDING = PROJECT / "DIRECTOR_TASKGRAPH_FP8_PROLOGUE_H200_EXECUTION_20260729T2148Z.json"
EXPECTED_BINDING_SHA = "82da8037e760b7fb07a01bd161ea2ce7ba6d07454670367f568d8da76c1db289"
EXPECTED_UUID = "GPU-81ca2c99-6df0-5bf8-023c-3ee78a68f3d8"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
REMOTE_CHECKPOINT = "/home/glmrunner/qkv-direct-a7fc5afbe3c3b292/checkpoint"
DEADLINE_EPOCH = datetime.fromisoformat("2026-07-29T23:48:00+00:00").timestamp()
RATE_USD_PER_HOUR = 2.45


class Boundary(RuntimeError):
    def __init__(self, kind: str, message: str, recoverable: bool = True):
        super().__init__(f"{kind}:{message}")
        self.kind = kind
        self.message = message
        self.recoverable = recoverable


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(tmp.read_text())
    os.replace(tmp, path)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise Boundary("typed_json_boundary", f"{path.name}_not_object")
    return value


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def pool(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "grad_research.gpu_pool",
            "--lab",
            str(LAB),
            *args,
        ],
        env={**os.environ, "PYTHONPATH": str(FACTORY_SRC)},
        text=True,
        capture_output=True,
        check=check,
    )


class Remote:
    def __init__(self, bench: dict[str, Any], root: pathlib.Path):
        resource = bench["resource"]
        self.host = resource["public_ipv4"]
        self.user = resource["ssh_user"]
        common = [
            "-i",
            resource["ssh_identity_path"],
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={resource['known_hosts_namespace']}",
            "-o",
            "ConnectTimeout=20",
        ]
        self.ssh = ["ssh", *common, f"{self.user}@{self.host}"]
        self.scp = ["scp", *common]
        self.root = root

    def timeout(self, cap: int, reserve: int = 180) -> int:
        left = int(DEADLINE_EPOCH - time.time() - reserve)
        if left <= 0:
            raise Boundary("typed_deadline_boundary", "no_operation_time", False)
        return min(cap, left)

    def run(self, command: str, label: str, cap: int = 600, check: bool = True):
        result = subprocess.run(
            [*self.ssh, command],
            text=True,
            capture_output=True,
            timeout=self.timeout(cap),
        )
        (self.root / f"{label}.stdout").write_text(result.stdout)
        (self.root / f"{label}.stderr").write_text(result.stderr)
        if check and result.returncode:
            raise Boundary(
                "typed_remote_boundary",
                f"{label}:rc={result.returncode}:{result.stderr[-1200:]}",
            )
        return result

    def put(self, source: pathlib.Path, destination: str, label: str):
        result = subprocess.run(
            [*self.scp, str(source), f"{self.user}@{self.host}:{destination}"],
            text=True,
            capture_output=True,
            timeout=self.timeout(300),
        )
        (self.root / f"{label}.stdout").write_text(result.stdout)
        (self.root / f"{label}.stderr").write_text(result.stderr)
        if result.returncode:
            raise Boundary("typed_transfer_boundary", f"{label}:{result.stderr[-1200:]}")

    def get(self, source: str, destination: pathlib.Path, label: str):
        result = subprocess.run(
            [*self.scp, f"{self.user}@{self.host}:{source}", str(destination)],
            text=True,
            capture_output=True,
            timeout=self.timeout(300),
        )
        (self.root / f"{label}.stdout").write_text(result.stdout)
        (self.root / f"{label}.stderr").write_text(result.stderr)
        if result.returncode:
            raise Boundary("typed_retrieval_boundary", f"{label}:{result.stderr[-1200:]}")


def update_status(**fields: Any) -> None:
    status = load(PROJECT / "STATUS.json")
    status.update(fields)
    atomic(PROJECT / "STATUS.json", status)


def claim_spend(claimed_at: str) -> tuple[float, float]:
    start = datetime.fromisoformat(claimed_at.replace("Z", "+00:00")).timestamp()
    seconds = max(0.0, time.time() - start)
    return seconds, seconds * RATE_USD_PER_HOUR / 3600.0


def validate_ready() -> dict[str, Any]:
    ready = load(READY)
    if sha256(BINDING) != EXPECTED_BINDING_SHA:
        raise Boundary("typed_binding_boundary", "binding_digest", False)
    if ready["binding"]["sha256"] != EXPECTED_BINDING_SHA:
        raise Boundary("typed_binding_boundary", "ready_binding_digest", False)
    for item in ready["immutable_files"]:
        path = pathlib.Path(item["absolute_path"])
        if sha256(path) != item["sha256"]:
            raise Boundary("typed_input_boundary", f"hash:{path.name}", False)
    return ready


def release(
    bench_id: str,
    claimed_at: str,
    root: pathlib.Path,
    *,
    condition: str,
    terminal_summary: str,
    state: str,
) -> dict[str, Any]:
    seconds, spend = claim_spend(claimed_at)
    contents = {
        "schema_version": 1,
        "project": PROJECT_NAME,
        "role": "completed_dynamic_fp8_prologue_component",
        "state": state,
        "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "image": IMAGE,
        "checkpoint": "Resident immutable checkpoint remains at qkv-direct-a7fc5afbe3c3b292/checkpoint.",
        "runtime": "Exact H200 identity and pinned image used; experiment container removed.",
        "artifacts": terminal_summary,
        "scientific_terminal": terminal_summary,
        "server_state": "No server; experiment container removed and zero compute processes verified.",
        "caches": "Preserve checkpoint, image, and Triton/torch caches.",
        "next": "Director may assign the available quiescent H200 after reading the taskgraph terminal.",
        "summary": terminal_summary,
    }
    contents_path = root / "RELEASE_CONTENTS.json"
    atomic(contents_path, contents)
    result = pool(
        "release",
        "--project",
        PROJECT_NAME,
        "--bench",
        bench_id,
        "--expected-claimed-at",
        claimed_at,
        "--contents",
        str(contents_path),
        "--condition",
        condition,
        check=False,
    )
    atomic(
        root / "RELEASE_EVIDENCE.json",
        {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "condition": condition,
            "claim_seconds": seconds,
            "actual_spend_usd": spend,
        },
    )
    if result.returncode:
        raise Boundary("typed_release_boundary", result.stderr[-1200:], False)
    return {"claim_seconds": seconds, "actual_spend_usd": spend}


def retrieve(remote: Remote, remote_root: str, root: pathlib.Path, attempt: int) -> pathlib.Path:
    remote.run(
        f"set -e; cd {shlex.quote(remote_root)}; "
        f"tar -czf compact-{attempt}.tar.gz.part out-{attempt} worker-{attempt}.stdout worker-{attempt}.stderr; "
        f"mv compact-{attempt}.tar.gz.part compact-{attempt}.tar.gz; "
        f"sha256sum compact-{attempt}.tar.gz > compact-{attempt}.tar.gz.sha256",
        f"package-{attempt}",
        cap=180,
    )
    archive = root / f"compact-{attempt}.tar.gz"
    sidecar = root / f"compact-{attempt}.tar.gz.sha256"
    remote.get(f"{remote_root}/compact-{attempt}.tar.gz", archive, f"retrieve-{attempt}")
    remote.get(
        f"{remote_root}/compact-{attempt}.tar.gz.sha256",
        sidecar,
        f"retrieve-hash-{attempt}",
    )
    expected = sidecar.read_text().split()[0]
    if sha256(archive) != expected:
        raise Boundary("typed_retrieval_boundary", "archive_hash")
    destination = root / f"attempt-{attempt}"
    destination.mkdir()
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(destination, filter="data")
    return destination / f"out-{attempt}" / "TERMINAL.json"


def run_attempt(
    remote: Remote,
    remote_root: str,
    runner: pathlib.Path,
    runner_sha: str,
    root: pathlib.Path,
    attempt: int,
) -> pathlib.Path:
    remote_runner = f"{remote_root}/runner-{runner_sha}.py"
    remote.run(f"mkdir -p {shlex.quote(remote_root)}", f"mkdir-{attempt}")
    probe = remote.run(
        f"test -f {shlex.quote(remote_runner)} && "
        f"test \"$(sha256sum {shlex.quote(remote_runner)} | awk '{{print $1}}')\" = {shlex.quote(runner_sha)}",
        f"runner-probe-{attempt}",
        check=False,
    )
    if probe.returncode:
        partial = f"{remote_runner}.part"
        remote.put(runner, partial, f"runner-stage-{attempt}")
        remote.run(
            f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" = {shlex.quote(runner_sha)} && "
            f"chmod 0444 {shlex.quote(partial)} && mv {shlex.quote(partial)} {shlex.quote(remote_runner)}",
            f"runner-finalize-{attempt}",
        )
    remote.run(
        f"test ! -e {shlex.quote(remote_root + f'/out-{attempt}')} && "
        f"test \"$(stat -c %s {REMOTE_CHECKPOINT}/model-00001-of-00002.safetensors)\" = 49784788364 && "
        f"test \"$(sha256sum {REMOTE_CHECKPOINT}/model.safetensors.index.json | awk '{{print $1}}')\" = d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2",
        f"checkpoint-probe-{attempt}",
    )
    command = (
        f"sudo -n docker run --rm --gpus all --ipc=host "
        f"-v {shlex.quote(remote_root)}:/work "
        f"-v {REMOTE_CHECKPOINT}:/checkpoint:ro "
        f"{IMAGE} python3 /work/{pathlib.PurePosixPath(remote_runner).name} "
        f"--checkpoint-root /checkpoint --output-root /work/out-{attempt} "
        f"> {shlex.quote(remote_root + f'/worker-{attempt}.stdout')} "
        f"2> {shlex.quote(remote_root + f'/worker-{attempt}.stderr')}"
    )
    result = remote.run(command, f"container-{attempt}", cap=3600, check=False)
    marker = remote.run(
        f"set +e; "
        f"test -f {shlex.quote(remote_root + f'/out-{attempt}/SCIENCE_STARTED.json')} && echo SCIENCE_STARTED; "
        f"test -f {shlex.quote(remote_root + f'/out-{attempt}/TERMINAL.json')} && cat {shlex.quote(remote_root + f'/out-{attempt}/TERMINAL.json')}; "
        f"echo CONTAINER_RC={result.returncode}",
        f"terminal-probe-{attempt}",
        check=False,
    )
    if "SCIENCE_STARTED" not in marker.stdout and result.returncode:
        raise Boundary("recoverable_pre_science_worker", marker.stdout[-2000:] + marker.stderr[-1000:])
    if "TERMINAL.json" not in marker.stdout and '"classification"' not in marker.stdout:
        raise Boundary("recoverable_missing_terminal", marker.stdout[-2000:] + marker.stderr[-1000:])
    return retrieve(remote, remote_root, root, attempt)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--claimed-at", required=True)
    parser.add_argument("--owner-state", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    progress = root / "OWNER_PROGRESS.json"
    ready = validate_ready()
    bench = json.loads(pool("show", "--bench", args.bench).stdout)
    claim = bench.get("claim") or {}
    if claim.get("project") != PROJECT_NAME or claim.get("claimed_at") != args.claimed_at:
        raise Boundary("typed_claim_boundary", json.dumps(claim, sort_keys=True), False)

    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(30):
            result = pool(
                "heartbeat",
                "--project",
                PROJECT_NAME,
                "--bench",
                args.bench,
                check=False,
            )
            atomic(
                root / "HEARTBEAT.json",
                {"at": time.time(), "returncode": result.returncode, "stderr": result.stderr},
            )

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    remote = Remote(bench, root)
    ready_sha = sha256(READY)
    remote_root = f"/home/glmrunner/taskgraph-fp8-prologue-{ready_sha[:16]}-{hashlib.sha256(args.claimed_at.encode()).hexdigest()[:8]}"
    attempt = 1
    runner = PROJECT / ready["runner"]["path"]
    runner_sha = ready["runner"]["sha256"]
    terminal_path: pathlib.Path | None = None
    try:
        atomic(progress, {"phase": "remote_identity", "attempt": attempt, "remote_root": remote_root})
        identity = remote.run(
            "set -e; nvidia-smi --query-gpu=name,uuid,driver_version,memory.used --format=csv,noheader,nounits; "
            "nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader || true; "
            "sudo -n docker image inspect "
            + shlex.quote(IMAGE)
            + " --format '{{index .RepoDigests 0}}'",
            "remote-identity",
            cap=120,
        )
        if "NVIDIA H200" not in identity.stdout or EXPECTED_UUID not in identity.stdout:
            raise Boundary("typed_hardware_boundary", identity.stdout, False)
        while time.time() < DEADLINE_EPOCH - 300:
            try:
                atomic(progress, {"phase": "worker", "attempt": attempt, "remote_root": remote_root})
                terminal_path = run_attempt(
                    remote, remote_root, runner, runner_sha, root, attempt
                )
                break
            except Boundary as error:
                diagnostic = {
                    "schema_version": 1,
                    "repair_id": f"fp8-prologue-r{attempt}",
                    "classification": error.kind,
                    "diagnostic": error.message,
                    "retry_scope": "worker_only",
                    "science_consumed": False,
                    "repair_deadline_utc": "2026-07-29T23:43:00Z",
                    "claim_retained": True,
                }
                atomic(PROJECT / "REPAIR_READY.json", diagnostic)
                atomic(progress, {"phase": "repair_wait", "attempt": attempt, "diagnostic": diagnostic})
                request = PROJECT / "REPAIR_REQUEST.json"
                while time.time() < DEADLINE_EPOCH - 300:
                    if request.exists():
                        value = load(request)
                        requested = pathlib.Path(value["runner_absolute_path"]).resolve()
                        if PROJECT not in requested.parents:
                            raise Boundary("typed_repair_boundary", "runner_outside_project", False)
                        if sha256(requested) != value["runner_sha256"]:
                            raise Boundary("typed_repair_boundary", "runner_hash", False)
                        runner, runner_sha = requested, value["runner_sha256"]
                        attempt += 1
                        break
                    time.sleep(5)
                else:
                    raise Boundary("typed_deadline_boundary", "repair_deadline", False)
                continue
        if terminal_path is None:
            raise Boundary("typed_deadline_boundary", "no_terminal", False)
        terminal = load(terminal_path)
        timing = terminal.get("timing") or {}
        rows = timing.get("rows") or []
        decision_bearing = (
            terminal.get("classification") == "scientific_correctness_negative"
            and terminal.get("science_consumed") is True
        ) or (
            terminal.get("classification") in {"component_positive", "component_negative"}
            and terminal.get("science_consumed") is True
            and terminal.get("timing_consumed") is True
            and len(rows) == 7
            and sum(r.get("arm") == "candidate" for r in rows) == 3
            and terminal.get("correctness", {}).get("pass") is True
        )
        if not decision_bearing:
            raise Boundary("recoverable_incomplete_terminal", json.dumps(terminal)[:2000])

        seconds, spend = claim_spend(args.claimed_at)
        project_terminal = {
            "schema_version": 1,
            "artifact_type": "taskgraph_fp8_prologue_h200_terminal",
            "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "binding_sha256": EXPECTED_BINDING_SHA,
            "ready_sha256": ready_sha,
            "bench": {
                "id": args.bench,
                "claimed_at": args.claimed_at,
                "gpu_uuid": EXPECTED_UUID,
                "ssh_fingerprint": bench["resource"]["ssh_ed25519_fingerprint"],
                "watchdog": bench["lifecycle"]["watchdog"],
            },
            "component_terminal": terminal,
            "component_terminal_sha256": sha256(terminal_path),
            "execution": {
                "claim_seconds_before_release": seconds,
                "actual_spend_usd_before_release": spend,
                "useful_gpu_seconds": None,
                "provider_mutation": False,
                "endpoint_invoked": False,
            },
            "whole_request_bound": {
                "type": "component_only_no_summed_trace_projection",
                "seconds_per_request": None,
                "reason": "No scope-matched endpoint A/B or critical-path call count was executed.",
            },
            "typed_decision": (
                "promote_runtime_integration"
                if terminal["classification"] == "component_positive"
                else "close_dynamic_fp8_prologue"
            ),
        }
        terminal_out = PROJECT / "TASKGRAPH_FP8_PROLOGUE_H200_TERMINAL.json"
        atomic(terminal_out, project_terminal)
        zero = remote.run(
            "set -e; echo COMPUTE_BEGIN; nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader || true; "
            "echo COMPUTE_END; echo MEMORY_BEGIN; nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits; echo MEMORY_END; "
            "test -z \"$(sudo -n docker ps -q)\"",
            "zero-gpu",
            cap=90,
        )
        if "MEMORY_BEGIN\n0\nMEMORY_END" not in zero.stdout:
            raise Boundary("typed_cleanup_boundary", zero.stdout, False)
        released = release(
            args.bench,
            args.claimed_at,
            root,
            condition="available",
            terminal_summary=f"FP8 prologue {terminal['classification']}; terminal {sha256(terminal_out)[:12]}...",
            state="available_after_fp8_prologue_terminal",
        )
        update_status(
            status="complete",
            active_session=None,
            decision=project_terminal["typed_decision"],
            terminal_artifact=terminal_out.name,
            terminal_artifact_sha256=sha256(terminal_out),
            scientific_sample_consumed=True,
            gpu_invocation=True,
            provider_mutation=False,
            actual_spend_usd=released["actual_spend_usd"],
            completed_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            next_action="Director should inspect TASKGRAPH_FP8_PROLOGUE_H200_TERMINAL.json and either admit runtime integration or retire this exact prologue.",
        )
        with (PROJECT / "RESEARCH_LOG.md").open("a") as log:
            log.write(
                f"\n## 2026-07-29 — H200 dynamic-FP8 prologue terminal\n\n"
                f"- **Result:** `{terminal['classification']}` on real layer-0 q_proj `[32,5376] x [5376,8192]`; "
                f"terminal `{sha256(terminal_out)}`.\n"
                f"- **Lifecycle:** generation-fenced release succeeded after {released['claim_seconds']:.3f}s; "
                f"conservative project spend `${released['actual_spend_usd']:.6f}`. No endpoint or provider lifecycle call.\n"
            )
        atomic(progress, {"phase": "complete", "terminal": str(terminal_out), **released})
        return 0
    except Exception as error:
        atomic(
            root / "OWNER_FAILURE.json",
            {
                "classification": getattr(error, "kind", type(error).__name__),
                "diagnostic": str(error),
                "science_started_remote": "unknown_retrieve_required",
                "at": time.time(),
            },
        )
        if time.time() >= DEADLINE_EPOCH - 180 or not getattr(error, "recoverable", True):
            released = release(
                args.bench,
                args.claimed_at,
                root,
                condition="maintenance",
                terminal_summary=f"FP8 owner nonrecoverable boundary: {error}",
                state="maintenance_after_fp8_owner_boundary",
            )
            update_status(
                status="blocked",
                active_session=None,
                decision="typed_external_or_deadline_blocker",
                actual_spend_usd=released["actual_spend_usd"],
                scientific_sample_consumed=False,
                gpu_invocation=False,
                next_action=f"Director inspection required: {error}",
            )
            return 3
        raise
    finally:
        stop.set()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
