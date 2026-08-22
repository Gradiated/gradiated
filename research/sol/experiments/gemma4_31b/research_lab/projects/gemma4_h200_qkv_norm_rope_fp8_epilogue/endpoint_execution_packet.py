#!/usr/bin/env python3
"""Cold-H200 worker for one bound QKV-direct c32 endpoint submission.

The script is controller-local.  It consumes only the project-local packet,
one later execution binding, and one `gpu_pool show` bench record.  It never
claims or releases a bench and never calls a provider API.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tarfile
import time
from typing import Any


PROJECT_NAME = "gemma4_h200_qkv_norm_rope_fp8_epilogue"
PROJECT = pathlib.Path(__file__).resolve().parent
INPUTS = PROJECT / "inputs" / "endpoint_packet"
MANIFEST = INPUTS / "PACKET_MANIFEST.json"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
MODEL = "google/gemma-4-31B-it"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
SGLANG_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
CHECKPOINT_MANIFEST_SHA256 = (
    "6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6"
)
QUALIFIED_SECONDS = 0.625149101968745
TARGET_SECONDS = 0.500119281574996
AUTHORIZED_USD = 10.0
MINIMUM_PACKET_TO_RELEASE_SECONDS = 85 * 60
ARTIFACT_SNAPSHOT = pathlib.Path(
    "/root/workspace/research/factory/tools/artifact-snapshot"
)


class Boundary(RuntimeError):
    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}:{message}")
        self.kind = kind
        self.message = message


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def load_object(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise Boundary("typed_input_boundary", f"{path.name}_not_object")
    return value


def validate_local_inputs(*, deep_checkpoint: bool) -> dict[str, Any]:
    manifest = load_object(MANIFEST)
    if manifest.get("schema_version") != 1:
        raise Boundary("typed_input_boundary", "packet_manifest_schema")
    checked = []
    for row in manifest["files"]:
        path = (INPUTS / row["path"]).resolve()
        if INPUTS not in path.parents or not path.is_file():
            raise Boundary("typed_input_boundary", f"missing:{row['path']}")
        stat = path.stat()
        if stat.st_size != row["bytes"]:
            raise Boundary("typed_input_boundary", f"size:{row['path']}")
        if row.get("checkpoint") and not deep_checkpoint:
            identity = row["local_identity"]
            if (
                stat.st_dev != identity["device"]
                or stat.st_ino != identity["inode"]
                or stat.st_mtime_ns != identity["mtime_ns"]
            ):
                raise Boundary(
                    "typed_input_boundary", f"checkpoint_metadata:{row['path']}"
                )
        elif sha256(path) != row["sha256"]:
            raise Boundary("typed_input_boundary", f"sha256:{row['path']}")
        checked.append(row["path"])
    if sha256(INPUTS / "CHECKPOINT_MANIFEST.json") != CHECKPOINT_MANIFEST_SHA256:
        raise Boundary("typed_input_boundary", "checkpoint_manifest_identity")
    workload = load_object(INPUTS / "WORKLOAD.json")
    if (
        workload.get("concurrency") != 32
        or workload.get("prompt_tokens") != 4214
        or workload.get("output_tokens") != 358
        or len(workload.get("request_sha256", [])) != 32
    ):
        raise Boundary("typed_input_boundary", "workload_geometry")
    launch = load_object(INPUTS / "LAUNCH.json")
    required = {
        "--model-path",
        "--kv-cache-dtype",
        "--cuda-graph-max-bs",
        "--decode-attention-backend",
        "--page-size",
    }
    if not required.issubset(set(launch.get("args", []))):
        raise Boundary("typed_input_boundary", "launch_geometry")
    return {
        "schema_version": 1,
        "pass": True,
        "deep_checkpoint": deep_checkpoint,
        "checked_files": checked,
        "packet_manifest_sha256": sha256(MANIFEST),
        "checkpoint_manifest_sha256": CHECKPOINT_MANIFEST_SHA256,
    }


def validate_binding(
    binding: dict[str, Any], ready_sha256: str, *, require_full_lifecycle: bool = True
) -> None:
    expected = {
        "project": PROJECT_NAME,
        "decision": "one_qkv_direct_c32_endpoint",
        "claim_allowed": True,
        "endpoint_submission_limit": 1,
        "model": f"{MODEL}@{REVISION}",
        "checkpoint_manifest_sha256": CHECKPOINT_MANIFEST_SHA256,
        "image": IMAGE,
        "sglang_commit": SGLANG_COMMIT,
        "accelerator": "nvidia-h200-sxm",
        "endpoint_packet_ready_sha256": ready_sha256,
    }
    bad = {
        key: {"expected": value, "observed": binding.get(key)}
        for key, value in expected.items()
        if binding.get(key) != value
    }
    if bad:
        raise Boundary("typed_binding_boundary", json.dumps(bad, sort_keys=True))
    if float(binding["conservative_project_exposure_usd"]) > AUTHORIZED_USD:
        raise Boundary("typed_budget_boundary", "exposure_above_10_usd")
    if require_full_lifecycle and (
        int(binding["absolute_release_deadline_epoch"])
        <= time.time() + MINIMUM_PACKET_TO_RELEASE_SECONDS
    ):
        raise Boundary("typed_deadline_boundary", "insufficient_packet_to_release_time")


def validate_bench(bench: dict[str, Any], binding: dict[str, Any]) -> None:
    resource = bench.get("resource") or {}
    claim = bench.get("claim") or {}
    checks = {
        "bench_id": bench.get("id") == binding.get("bench_id"),
        "accelerator": bench.get("accelerator") == "nvidia-h200-sxm",
        "project_claim": claim.get("project") == PROJECT_NAME,
        "ssh_state": resource.get("connection_state")
        == "strict_ssh_cloud_init_h200_verified",
        "gpu_name": resource.get("gpu_name") == "NVIDIA H200",
        "gpu_uuid": resource.get("gpu_uuid") == binding.get("gpu_uuid"),
        "watchdog": (bench.get("lifecycle") or {})
        .get("watchdog", {})
        .get("unit")
        == binding.get("watchdog"),
        "hourly_rate": float(bench.get("hourly_cost_usd", 1e9))
        == float(binding.get("hourly_cost_usd")),
    }
    if not all(checks.values()):
        raise Boundary(
            "typed_bench_boundary",
            json.dumps({key: value for key, value in checks.items() if not value}),
        )
    for key in (
        "public_ipv4",
        "ssh_user",
        "ssh_identity_path",
        "known_hosts_namespace",
    ):
        if not resource.get(key):
            raise Boundary("typed_bench_boundary", f"missing_resource_{key}")
    for key in ("ssh_identity_path", "known_hosts_namespace"):
        if not pathlib.Path(resource[key]).exists():
            raise Boundary("typed_controller_boundary", f"missing_{key}")


def classify_endpoint(
    terminal: dict[str, Any],
    path_rows: list[dict[str, Any]],
    raw_response_count: int,
    cleanup: dict[str, Any],
) -> dict[str, Any]:
    workload = load_object(INPUTS / "WORKLOAD.json")
    rows = terminal.get("rows") or []
    path_scopes = {
        (row.get("geometry") or {}).get("scope")
        for row in path_rows
        if row.get("candidate_symbol")
        == "_qkv_norm_rope_direct_fp8_cache_kernel"
    }
    accounting = (
        terminal.get("pass") is True
        and terminal.get("endpoint_submission_count") == 1
        and terminal.get("concurrency") == 32
        and terminal.get("complete_requests") == 32
        and len(rows) == 32
        and [row.get("request_sha256") for row in rows]
        == workload["request_sha256"]
        and all(
            row.get("error") is None
            and row.get("prompt_tokens") == 4214
            and row.get("completion_tokens") == 358
            and row.get("text_nonempty") is True
            for row in rows
        )
    )
    candidate_seconds = terminal.get("service_seconds_per_request")
    interpretable = (
        accounting
        and path_scopes == {"local", "global"}
        and raw_response_count == 32
        and isinstance(candidate_seconds, (int, float))
        and candidate_seconds > 0
        and cleanup.get("zero_gpu") is True
    )
    return {
        "schema_version": 1,
        "pass": interpretable,
        "classification": (
            "endpoint_positive"
            if interpretable and candidate_seconds < QUALIFIED_SECONDS
            else "endpoint_negative"
            if interpretable
            else "endpoint_incomplete"
        ),
        "endpoint_submission_count": 1,
        "endpoint_science_consumed": True,
        "candidate_seconds_per_request": candidate_seconds,
        "qualified_seconds_per_request": QUALIFIED_SECONDS,
        "target_seconds_per_request": TARGET_SECONDS,
        "delta_vs_qualified_seconds_per_request": (
            None
            if not isinstance(candidate_seconds, (int, float))
            else candidate_seconds - QUALIFIED_SECONDS
        ),
        "fractional_improvement_vs_qualified": (
            None
            if not isinstance(candidate_seconds, (int, float))
            else (QUALIFIED_SECONDS - candidate_seconds) / QUALIFIED_SECONDS
        ),
        "meets_campaign_target": (
            isinstance(candidate_seconds, (int, float))
            and candidate_seconds <= TARGET_SECONDS
        ),
        "quality_gate": {
            "request_and_token_accounting": accounting,
            "local_and_global_candidate_path": path_scopes == {"local", "global"},
            "raw_responses": raw_response_count,
            "zero_gpu_cleanup": cleanup.get("zero_gpu") is True,
        },
    }


class Remote:
    def __init__(
        self,
        bench: dict[str, Any],
        deadline_epoch: int,
        artifact_root: pathlib.Path,
    ):
        resource = bench["resource"]
        self.host = resource["public_ipv4"]
        self.user = resource["ssh_user"]
        self.key = pathlib.Path(resource["ssh_identity_path"])
        self.known_hosts = pathlib.Path(resource["known_hosts_namespace"])
        self.deadline = deadline_epoch
        self.root = artifact_root
        common = [
            "-i",
            str(self.key),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self.known_hosts}",
            "-o",
            "ConnectTimeout=20",
        ]
        self.ssh_prefix = ["ssh", *common, f"{self.user}@{self.host}"]
        self.scp_prefix = ["scp", *common]

    def timeout(self, cap: int, reserve: int = 0) -> int:
        remaining = int(self.deadline - time.time() - reserve)
        if remaining <= 0:
            raise Boundary("typed_deadline_boundary", "operation_has_no_time")
        return min(cap, remaining)

    def run(
        self,
        command: str,
        *,
        cap: int,
        reserve: int = 0,
        label: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [*self.ssh_prefix, command],
            text=True,
            capture_output=True,
            timeout=self.timeout(cap, reserve),
        )
        (self.root / f"{label}.stdout").write_text(result.stdout)
        (self.root / f"{label}.stderr").write_text(result.stderr)
        if check and result.returncode:
            raise Boundary(
                "typed_remote_boundary",
                f"{label}:rc={result.returncode}:{result.stderr[-1000:]}",
            )
        return result

    def put(
        self,
        source: pathlib.Path,
        destination: str,
        *,
        cap: int,
        reserve: int,
    ) -> None:
        result = subprocess.run(
            [
                *self.scp_prefix,
                str(source),
                f"{self.user}@{self.host}:{destination}",
            ],
            text=True,
            capture_output=True,
            timeout=self.timeout(cap, reserve),
        )
        if result.returncode:
            raise Boundary(
                "typed_transfer_boundary",
                f"{source.name}:rc={result.returncode}:{result.stderr[-1000:]}",
            )

    def get(
        self,
        source: str,
        destination: pathlib.Path,
        *,
        cap: int,
        reserve: int,
    ) -> None:
        result = subprocess.run(
            [
                *self.scp_prefix,
                f"{self.user}@{self.host}:{source}",
                str(destination),
            ],
            text=True,
            capture_output=True,
            timeout=self.timeout(cap, reserve),
        )
        if result.returncode:
            raise Boundary(
                "typed_retrieval_boundary",
                f"{source}:rc={result.returncode}:{result.stderr[-1000:]}",
            )


def remote_atomic(remote: Remote, path: str, value: dict[str, Any], label: str) -> None:
    encoded = base64.b64encode(
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    ).decode()
    script = (
        "import base64,os,pathlib;"
        f"p=pathlib.Path({path!r});"
        "p.parent.mkdir(parents=True,exist_ok=True);"
        "q=p.with_suffix(p.suffix+'.part');"
        f"q.write_bytes(base64.b64decode({encoded!r}));"
        "os.replace(q,p)"
    )
    remote.run(
        f"python3 -c {shlex.quote(script)}",
        cap=60,
        reserve=300,
        label=label,
    )


def zero_gpu_from_output(result: subprocess.CompletedProcess[str]) -> bool:
    compute_text = result.stdout.partition("COMPUTE_BEGIN")[2].partition(
        "COMPUTE_END"
    )[0]
    memory_text = result.stdout.partition("MEMORY_BEGIN")[2].partition(
        "MEMORY_END"
    )[0]
    compute_lines = [
        line.strip() for line in compute_text.splitlines() if line.strip()
    ]
    memory_lines = [
        line.strip() for line in memory_text.splitlines() if line.strip()
    ]
    return (
        not compute_lines
        and bool(memory_lines)
        and all(line == "0" for line in memory_lines)
    )


def stage_file(
    remote: Remote,
    source: pathlib.Path,
    final: str,
    expected: str,
    *,
    cap: int,
    reserve: int,
) -> None:
    check = remote.run(
        f"test -f {shlex.quote(final)} && "
        f"test \"$(sha256sum {shlex.quote(final)} | awk '{{print $1}}')\" "
        f"= {shlex.quote(expected)}",
        cap=min(600, cap),
        reserve=reserve,
        label=f"reconcile-{source.name}",
        check=False,
    )
    if check.returncode == 0:
        return
    partial = f"{final}.{expected}.part"
    remote.put(source, partial, cap=cap, reserve=reserve)
    remote.run(
        f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" "
        f"= {shlex.quote(expected)} && chmod 0444 {shlex.quote(partial)} && "
        f"mv -f {shlex.quote(partial)} {shlex.quote(final)}",
        cap=cap,
        reserve=reserve,
        label=f"finalize-{source.name}",
    )


def execute(
    binding: dict[str, Any],
    bench: dict[str, Any],
    artifact_root: pathlib.Path,
    deadline: int,
) -> int:
    packet_hash = sha256(MANIFEST)
    remote_root = f"/home/{bench['resource']['ssh_user']}/qkv-direct-{packet_hash[:16]}"
    input_root = f"{remote_root}/input"
    checkpoint_root = f"{remote_root}/checkpoint"
    remote_artifacts = f"{remote_root}/artifacts"
    container = f"qkv-direct-{packet_hash[:12]}"
    remote = Remote(bench, deadline, artifact_root)
    state: dict[str, Any] = {
        "schema_version": 1,
        "phase": "pre_science",
        "launch_attempted": False,
        "endpoint_science_started": False,
        "endpoint_submission_count": 0,
        "science_observation": "pre_driver",
        "remote_root": remote_root,
        "container": container,
    }
    atomic(artifact_root / "INVOCATION_STATE.json", state)
    cleanup = {"attempted": False, "zero_gpu": False}
    terminal: dict[str, Any] | None = None
    reachable = False
    try:
        identity = remote.run(
            "set -e; hostname; "
            "nvidia-smi --query-gpu=name,uuid,driver_version,memory.used "
            "--format=csv,noheader,nounits; "
            "nvidia-smi --query-compute-apps=pid,process_name "
            "--format=csv,noheader || true; sudo -n docker version --format '{{.Server.Version}}'",
            cap=90,
            reserve=600,
            label="remote-identity",
        )
        reachable = True
        if "NVIDIA H200" not in identity.stdout or binding["gpu_uuid"] not in identity.stdout:
            raise Boundary("typed_hardware_boundary", "H200_identity_mismatch")
        remote.run(
            f"mkdir -p {shlex.quote(input_root)} {shlex.quote(checkpoint_root)} "
            f"{shlex.quote(remote_artifacts)}",
            cap=60,
            reserve=600,
            label="remote-prepare",
        )
        manifest = load_object(MANIFEST)
        for row in manifest["files"]:
            source = INPUTS / row["path"]
            if row.get("checkpoint"):
                final = f"{checkpoint_root}/{pathlib.Path(row['path']).name}"
                cap = 2400
            else:
                final = f"{input_root}/{row['remote_name']}"
                cap = 600
            stage_file(
                remote,
                source,
                final,
                row["sha256"],
                cap=cap,
                reserve=600,
            )
        remote.run(
            f"sudo -n docker image inspect {shlex.quote(IMAGE)} >/dev/null 2>&1 || "
            f"sudo -n docker pull {shlex.quote(IMAGE)}; "
            f"sudo -n docker image inspect {shlex.quote(IMAGE)} "
            "--format '{{json .RepoDigests}}'",
            cap=1800,
            reserve=600,
            label="image-reconcile",
        )
        launch = load_object(INPUTS / "LAUNCH.json")["args"]
        command = [
            "sudo",
            "-n",
            "docker",
            "run",
            "-d",
            "--name",
            container,
            "--gpus",
            "all",
            "--network",
            "host",
            "-e",
            "QKV_ENDPOINT_ARTIFACT_ROOT=/work/artifacts",
            "-v",
            f"{checkpoint_root}:/work/checkpoint:ro",
            "-v",
            f"{input_root}:/work/input:ro",
            "-v",
            f"{remote_artifacts}:/work/artifacts",
            "--entrypoint",
            "python3",
            IMAGE,
            "/work/input/endpoint_entrypoint.py",
            *launch,
        ]
        state["launch_attempted"] = True
        atomic(artifact_root / "INVOCATION_STATE.json", state)
        remote_atomic(
            remote,
            f"{remote_artifacts}/INVOCATION_STATE.json",
            state,
            "state-launch-attempted",
        )
        remote.run(
            f"sudo -n docker rm -f {shlex.quote(container)} >/dev/null 2>&1 || true; "
            + " ".join(shlex.quote(part) for part in command),
            cap=180,
            reserve=600,
            label="server-launch",
        )
        readiness_deadline = min(deadline - 600, int(time.time()) + 1200)
        readiness_command = (
            f"end={readiness_deadline}; while test \"$(date +%s)\" -lt \"$end\"; do "
            f"state=$(sudo -n docker inspect -f '{{{{.State.Status}}}}' "
            f"{shlex.quote(container)} 2>/dev/null || true); "
            "if test \"$state\" != running; then "
            f"sudo -n docker logs {shlex.quote(container)} 2>&1 | tail -400; exit 74; fi; "
            "curl -fsS --max-time 3 http://127.0.0.1:30000/v1/models && exit 0; "
            "sleep 3; done; exit 75"
        )
        remote.run(
            readiness_command,
            cap=1200,
            reserve=600,
            label="server-readiness",
        )
        state["science_observation"] = "pending"
        atomic(artifact_root / "INVOCATION_STATE.json", state)
        remote_atomic(
            remote,
            f"{remote_artifacts}/INVOCATION_STATE.json",
            state,
            "state-before-driver",
        )
        driver_command = (
            f"set -u; rm -rf {shlex.quote(remote_artifacts + '/endpoint')}; "
            f"python3 {shlex.quote(input_root + '/endpoint_driver.py')} "
            f"--output {shlex.quote(remote_artifacts + '/endpoint')} "
            f"--admitted-workload {shlex.quote(input_root + '/WORKLOAD.json')} "
            f"--science-marker {shlex.quote(remote_artifacts + '/SCIENCE_STARTED.json')} "
            f">{shlex.quote(remote_artifacts + '/DRIVER.stdout')} "
            f"2>{shlex.quote(remote_artifacts + '/DRIVER.stderr')} & "
            "worker=$!; "
            "while kill -0 \"$worker\" 2>/dev/null; do "
            f"container_state=$(sudo -n docker inspect -f "
            f"'{{{{.State.Status}}}}' {shlex.quote(container)} 2>/dev/null || true); "
            "if test \"$container_state\" != running; then "
            f"sudo -n docker logs {shlex.quote(container)} "
            f">{shlex.quote(remote_artifacts + '/SERVER_EXIT_DURING_DRIVER.log')} "
            "2>&1 || true; "
            "kill -TERM \"$worker\" 2>/dev/null || true; "
            "wait \"$worker\" 2>/dev/null || true; exit 76; fi; "
            "sleep 2; done; "
            "worker_rc=0; wait \"$worker\" || worker_rc=$?; exit \"$worker_rc\""
        )
        driver_timeout = remote.timeout(1800, reserve=420)
        driver = remote.run(
            f"timeout --signal=TERM {driver_timeout} bash -lc "
            f"{shlex.quote(driver_command)}",
            cap=driver_timeout + 15,
            reserve=405,
            label="endpoint-driver",
            check=False,
        )
        marker = remote.run(
            f"cat {shlex.quote(remote_artifacts + '/SCIENCE_STARTED.json')}",
            cap=30,
            reserve=390,
            label="science-marker",
            check=False,
        )
        if marker.returncode == 0:
            marker_value = json.loads(marker.stdout)
            state["endpoint_science_started"] = marker_value.get(
                "endpoint_science_started", False
            )
            state["endpoint_submission_count"] = marker_value.get(
                "endpoint_submission_count", 0
            )
            state["phase"] = "science_submitted"
            state["science_observation"] = "observed"
        else:
            state["science_observation"] = "marker_absent_after_driver"
        atomic(artifact_root / "INVOCATION_STATE.json", state)
        remote_atomic(
            remote,
            f"{remote_artifacts}/INVOCATION_STATE.json",
            state,
            "state-after-driver",
        )
        if driver.returncode:
            raise Boundary(
                "typed_endpoint_boundary",
                f"driver_rc={driver.returncode}:{driver.stderr[-1000:]}",
            )
        terminal = json.loads(
            remote.run(
                f"cat {shlex.quote(remote_artifacts + '/endpoint/TERMINAL.json')}",
                cap=30,
                reserve=360,
                label="endpoint-terminal",
            ).stdout
        )
    except Exception as error:
        if not isinstance(error, Boundary):
            error = Boundary("typed_worker_boundary", f"{type(error).__name__}:{error}")
        terminal = {
            "schema_version": 1,
            "classification": (
                "integration_failure"
                if not state["endpoint_science_started"]
                else "endpoint_attempt_incomplete"
            ),
            "pass": False,
            "message": str(error),
        }
    finally:
        cleanup["attempted"] = reachable
        if reachable:
            logs = remote.run(
                f"sudo -n docker logs {shlex.quote(container)} 2>&1 || true",
                cap=120,
                reserve=240,
                label="server-final-log",
                check=False,
            )
            cleanup_result = remote.run(
                f"sudo -n docker rm -f {shlex.quote(container)} >/dev/null 2>&1 || true; "
                f"sudo -n chown -R {shlex.quote(bench['resource']['ssh_user'])}:"
                f"{shlex.quote(bench['resource']['ssh_user'])} "
                f"{shlex.quote(remote_artifacts)}; "
                "echo COMPUTE_BEGIN; "
                "nvidia-smi --query-compute-apps=pid --format=csv,noheader || true; "
                "echo COMPUTE_END; echo MEMORY_BEGIN; "
                "nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits; "
                "echo MEMORY_END",
                cap=180,
                reserve=180,
                label="zero-gpu-cleanup",
                check=False,
            )
            cleanup["zero_gpu"] = zero_gpu_from_output(cleanup_result)
            cleanup["server_log_bytes"] = len(logs.stdout.encode())
            remote_atomic(
                remote,
                f"{remote_artifacts}/INVOCATION_STATE.json",
                state,
                "state-final",
            )
            remote_atomic(
                remote,
                f"{remote_artifacts}/WORKER_TERMINAL.json",
                terminal,
                "worker-terminal-remote",
            )
            remote.run(
                f"tar -czf {shlex.quote(remote_root + '/compact.tar.gz.part')} "
                f"-C {shlex.quote(remote_artifacts)} . && "
                f"mv {shlex.quote(remote_root + '/compact.tar.gz.part')} "
                f"{shlex.quote(remote_root + '/compact.tar.gz')} && "
                f"sha256sum {shlex.quote(remote_root + '/compact.tar.gz')} > "
                f"{shlex.quote(remote_root + '/compact.tar.gz.sha256')}",
                cap=180,
                reserve=120,
                label="compact-package",
                check=False,
            )
            try:
                remote.get(
                    f"{remote_root}/compact.tar.gz",
                    artifact_root / "compact.tar.gz.part",
                    cap=300,
                    reserve=60,
                )
                remote.get(
                    f"{remote_root}/compact.tar.gz.sha256",
                    artifact_root / "compact.tar.gz.sha256",
                    cap=60,
                    reserve=30,
                )
                expected = (
                    artifact_root / "compact.tar.gz.sha256"
                ).read_text().split()[0]
                if sha256(artifact_root / "compact.tar.gz.part") != expected:
                    raise Boundary("typed_retrieval_boundary", "compact_hash_mismatch")
                os.replace(
                    artifact_root / "compact.tar.gz.part",
                    artifact_root / "compact.tar.gz",
                )
            except Exception as retrieval_error:
                if terminal.get("classification") == "integration_failure":
                    terminal["retrieval_error"] = str(retrieval_error)
                else:
                    terminal = {
                        "schema_version": 1,
                        "classification": "endpoint_attempt_incomplete",
                        "pass": False,
                        "message": str(retrieval_error),
                    }

    archive = artifact_root / "compact.tar.gz"
    if archive.is_file():
        snapshot = subprocess.run(
            [
                str(ARTIFACT_SNAPSHOT),
                "--archive",
                str(archive),
                "--root",
                str(artifact_root / "snapshots"),
            ],
            text=True,
            capture_output=True,
            timeout=max(1, min(120, int(deadline - time.time()))),
        )
        (artifact_root / "artifact-snapshot.stdout").write_text(snapshot.stdout)
        (artifact_root / "artifact-snapshot.stderr").write_text(snapshot.stderr)
        if snapshot.returncode == 0 and terminal.get("classification") not in {
            "integration_failure",
            "endpoint_attempt_incomplete",
        }:
            destination = pathlib.Path(json.loads(snapshot.stdout)["destination"])
            endpoint_terminal = load_object(destination / "endpoint" / "TERMINAL.json")
            path_rows = [
                json.loads(line)
                for line in (destination / "PATH_PROOF.jsonl").read_text().splitlines()
                if line.strip()
            ]
            raw_count = len(list((destination / "endpoint").glob("response-*.sse")))
            terminal = classify_endpoint(
                endpoint_terminal, path_rows, raw_count, cleanup
            )
    atomic(artifact_root / "INVOCATION_STATE.json", state)
    atomic(artifact_root / "CLEANUP.json", cleanup)
    atomic(artifact_root / "WORKER_TERMINAL.json", terminal)
    return 0 if terminal.get("pass") is True else 1


def offline_plan() -> dict[str, Any]:
    launch = load_object(INPUTS / "LAUNCH.json")["args"]
    return {
        "schema_version": 1,
        "pass": True,
        "network_or_accelerator_actions": 0,
        "future_phases": [
            "strict_ssh_identity",
            "resumable_hash_reconciled_staging",
            "pinned_image_reconcile",
            "candidate_server_launch",
            "bounded_health_and_server_supervision",
            "one_c32_submission",
            "compact_retrieval_and_artifact_snapshot",
            "zero_gpu_cleanup",
        ],
        "launch_args_sha256": hashlib.sha256(
            json.dumps(launch, separators=(",", ":")).encode()
        ).hexdigest(),
        "submission_limit": 1,
        "repair_contract": {
            "pre_science": "integration_failure; retain claim and repair packet",
            "post_submission": "endpoint_attempt_incomplete; never silently replay",
            "complete": "endpoint_positive or endpoint_negative",
        },
    }


def recover_prior(
    binding: dict[str, Any],
    bench: dict[str, Any],
    prior: pathlib.Path,
    root: pathlib.Path,
    deadline: int,
) -> int:
    """Adopt/retrieve a submitted prior arm without launching or submitting."""
    state = load_object(prior / "INVOCATION_STATE.json")
    remote_root = str(state.get("remote_root") or "")
    remote: Remote | None = None
    if state.get("endpoint_science_started") is not True:
        if not remote_root.startswith(f"/home/{bench['resource']['ssh_user']}/"):
            raise Boundary("typed_retrieval_boundary", "prior_remote_root_invalid")
        remote = Remote(bench, deadline, root)
        marker = remote.run(
            f"cat {shlex.quote(remote_root + '/artifacts/SCIENCE_STARTED.json')}",
            cap=60,
            reserve=180,
            label="repair-science-marker",
            check=False,
        )
        if marker.returncode == 0:
            marker_value = json.loads(marker.stdout)
            state["endpoint_science_started"] = marker_value.get(
                "endpoint_science_started"
            )
            state["endpoint_submission_count"] = marker_value.get(
                "endpoint_submission_count"
            )
            state["science_observation"] = "recovered"
    if (
        state.get("endpoint_science_started") is not True
        or state.get("endpoint_submission_count") != 1
    ):
        raise Boundary("typed_repair_boundary", "prior_arm_submission_not_proven")
    cleanup = (
        load_object(prior / "CLEANUP.json")
        if (prior / "CLEANUP.json").is_file()
        else {"attempted": False, "zero_gpu": False}
    )
    if cleanup.get("zero_gpu") is not True:
        if not remote_root.startswith(f"/home/{bench['resource']['ssh_user']}/"):
            raise Boundary("typed_retrieval_boundary", "prior_remote_root_invalid")
        if remote is None:
            remote = Remote(bench, deadline, root)
        container = str(state.get("container") or "")
        if not container.startswith("qkv-direct-"):
            raise Boundary("typed_repair_boundary", "prior_container_identity")
        cleanup_result = remote.run(
            f"sudo -n docker rm -f {shlex.quote(container)} >/dev/null 2>&1 || true; "
            "echo COMPUTE_BEGIN; "
            "nvidia-smi --query-compute-apps=pid --format=csv,noheader || true; "
            "echo COMPUTE_END; echo MEMORY_BEGIN; "
            "nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits; "
            "echo MEMORY_END",
            cap=180,
            reserve=120,
            label="repair-zero-gpu",
            check=False,
        )
        cleanup = {
            "attempted": True,
            "zero_gpu": zero_gpu_from_output(cleanup_result),
            "repair_cleanup": True,
        }
        if cleanup["zero_gpu"] is not True:
            raise Boundary("typed_cleanup_boundary", "repair_zero_gpu_failed")
    archive = prior / "compact.tar.gz"
    if archive.is_file():
        expected = (
            (prior / "compact.tar.gz.sha256").read_text().split()[0]
            if (prior / "compact.tar.gz.sha256").is_file()
            else sha256(archive)
        )
        if sha256(archive) != expected:
            raise Boundary("typed_retrieval_boundary", "prior_compact_hash_mismatch")
        os.link(archive, root / "compact.tar.gz")
    else:
        if not remote_root.startswith(f"/home/{bench['resource']['ssh_user']}/"):
            raise Boundary("typed_retrieval_boundary", "prior_remote_root_invalid")
        if remote is None:
            remote = Remote(bench, deadline, root)
        remote.run(
            f"test -f {shlex.quote(remote_root + '/compact.tar.gz')} || "
            f"(tar -czf {shlex.quote(remote_root + '/compact.tar.gz.part')} "
            f"-C {shlex.quote(remote_root + '/artifacts')} . && "
            f"mv {shlex.quote(remote_root + '/compact.tar.gz.part')} "
            f"{shlex.quote(remote_root + '/compact.tar.gz')}); "
            f"sha256sum {shlex.quote(remote_root + '/compact.tar.gz')} > "
            f"{shlex.quote(remote_root + '/compact.tar.gz.sha256')}",
            cap=180,
            reserve=90,
            label="repair-package",
        )
        remote.get(
            f"{remote_root}/compact.tar.gz",
            root / "compact.tar.gz.part",
            cap=300,
            reserve=60,
        )
        remote.get(
            f"{remote_root}/compact.tar.gz.sha256",
            root / "compact.tar.gz.sha256",
            cap=60,
            reserve=30,
        )
        expected = (root / "compact.tar.gz.sha256").read_text().split()[0]
        if sha256(root / "compact.tar.gz.part") != expected:
            raise Boundary("typed_retrieval_boundary", "recovered_compact_hash_mismatch")
        os.replace(root / "compact.tar.gz.part", root / "compact.tar.gz")
    snapshot = subprocess.run(
        [
            str(ARTIFACT_SNAPSHOT),
            "--archive",
            str(root / "compact.tar.gz"),
            "--root",
            str(root / "snapshots"),
        ],
        text=True,
        capture_output=True,
        timeout=max(1, min(120, int(deadline - time.time()))),
    )
    (root / "artifact-snapshot.stdout").write_text(snapshot.stdout)
    (root / "artifact-snapshot.stderr").write_text(snapshot.stderr)
    if snapshot.returncode:
        raise Boundary("typed_retrieval_boundary", snapshot.stderr[-1000:])
    destination = pathlib.Path(json.loads(snapshot.stdout)["destination"])
    endpoint_terminal = load_object(destination / "endpoint" / "TERMINAL.json")
    path_proof = destination / "PATH_PROOF.jsonl"
    if not path_proof.is_file():
        if remote is None:
            remote = Remote(bench, deadline, root)
        remote_path_proof = f"{remote_root}/artifacts/PATH_PROOF.jsonl"
        probe = remote.run(
            f"test -s {shlex.quote(remote_path_proof)}",
            cap=60,
            reserve=90,
            label="repair-path-proof-probe",
            check=False,
        )
        if probe.returncode == 0:
            path_proof = root / "RECOVERED_PATH_PROOF.jsonl"
            remote.get(
                remote_path_proof,
                path_proof,
                cap=60,
                reserve=60,
            )
        else:
            raise Boundary("typed_retrieval_boundary", "path_proof_missing")
    path_rows = [
        json.loads(line)
        for line in path_proof.read_text().splitlines()
        if line.strip()
    ]
    raw_count = len(list((destination / "endpoint").glob("response-*.sse")))
    terminal = classify_endpoint(endpoint_terminal, path_rows, raw_count, cleanup)
    atomic(root / "INVOCATION_STATE.json", state)
    atomic(root / "CLEANUP.json", cleanup)
    atomic(root / "WORKER_TERMINAL.json", terminal)
    return 0 if terminal.get("pass") is True else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path)
    parser.add_argument("--deadline-epoch", type=int)
    parser.add_argument("--execution-binding", type=pathlib.Path)
    parser.add_argument("--bench-record", type=pathlib.Path)
    parser.add_argument("--offline-validate", action="store_true")
    parser.add_argument("--deep-checkpoint", action="store_true")
    parser.add_argument(
        "--repair-scope",
        choices=(
            "pre_science_launcher_staging_or_adapter",
            "retrieval_or_terminal_adoption_no_endpoint_replay",
        ),
    )
    parser.add_argument("--prior-artifact-root", type=pathlib.Path)
    args = parser.parse_args()
    local = validate_local_inputs(deep_checkpoint=args.deep_checkpoint)
    if args.offline_validate:
        value = {"local_inputs": local, "execution_plan": offline_plan()}
        if args.artifact_root:
            args.artifact_root.mkdir(parents=True, exist_ok=False)
            atomic(args.artifact_root / "OFFLINE_VALIDATION.json", value)
        print(json.dumps(value, sort_keys=True))
        return 0
    if not all(
        (
            args.artifact_root,
            args.deadline_epoch,
            args.execution_binding,
            args.bench_record,
        )
    ):
        parser.error(
            "execution requires artifact-root, deadline-epoch, "
            "execution-binding, and bench-record"
        )
    root = args.artifact_root.resolve()
    if PROJECT not in root.parents or root.exists():
        raise Boundary("typed_controller_boundary", "artifact_root_not_fresh_project_path")
    root.mkdir(parents=True)
    binding = load_object(args.execution_binding)
    ready_path = PROJECT / "ENDPOINT_EXECUTION_PACKET_READY.json"
    validate_binding(
        binding,
        sha256(ready_path),
        require_full_lifecycle=args.repair_scope is None,
    )
    bench = load_object(args.bench_record)
    validate_bench(bench, binding)
    if args.repair_scope:
        if args.prior_artifact_root is None:
            raise Boundary("typed_repair_boundary", "prior_artifact_root_missing")
        prior = args.prior_artifact_root.resolve()
        if PROJECT not in prior.parents:
            raise Boundary("typed_repair_boundary", "prior_artifact_root_outside_project")
        prior_state = load_object(prior / "INVOCATION_STATE.json")
        if args.repair_scope == "retrieval_or_terminal_adoption_no_endpoint_replay":
            return recover_prior(binding, bench, prior, root, args.deadline_epoch)
        if prior_state.get("endpoint_science_started") is not False:
            raise Boundary("typed_repair_boundary", "pre_science_retry_after_submission")
    return execute(binding, bench, root, args.deadline_epoch)


if __name__ == "__main__":
    raise SystemExit(main())
