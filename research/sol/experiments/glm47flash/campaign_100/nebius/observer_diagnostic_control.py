#!/usr/bin/env python3
"""Fail-closed retained L40S controller for the Nsight observer bracket."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from awq_smoke_control import (  # noqa: E402
    DISK_GIB,
    DISK_HOURLY_RATE_USD,
    HOURLY_RATE_USD,
    PLATFORM,
    PRESET,
    emit,
    probe_transfer,
    transfer_local_model,
    validate_local_model,
)
from placement_control import (  # noqa: E402
    build_create_command,
    delete_disk,
    delete_instance,
    extract_instance_id,
    extract_public_ipv4,
    find_named_instance,
    get_instance,
    list_items,
    make_cloud_init,
    metadata_id,
    metadata_name,
    wait_absent,
    wait_ssh,
)
from stock_control import extract_member, run_ssh, scp_from, scp_to, verify_internal_manifest  # noqa: E402
from vllm_smoke_control import (  # noqa: E402
    IMAGE,
    RUNTIME_IMAGE,
    TRANSFORMERS_REVISION,
    build_host_bootstrap as build_vllm_host_bootstrap,
)


ABSOLUTE_TIMEOUT_SECONDS = 2000
CLEANUP_RESERVE_SECONDS = 240
FACTORY_CLEANUP_RESERVE_USD = 0.07
MAX_COST_USD = 0.55
COMBINED_HOURLY_RATE_USD = HOURLY_RATE_USD + DISK_HOURLY_RATE_USD
NSYS_PACKAGE_VERSION = "2026.3.1.157"
NSYS_SIGNING_KEY_FINGERPRINT = "AE09FE4BBD223A84B2CCFCE3F60F4B3D7FA2AF80"
NSYS_SIGNING_KEY_URL = (
    "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0xF60F4B3D7FA2AF80"
)
FACTORY_PROGRAM = "glm-4.7-flash"
FACTORY_CAMPAIGN = "glm47-nebius-25"
FACTORY_RUN_ID = "glm47-observer-diagnostic-l40s-v4"
FACTORY_SETUP_KEY = "l40s:vllm:glm47:observer"
FALLBACK_MIN_SECONDS = 720
FALLBACK_MIN_COST_USD = 0.08
REMOTE_ARCHIVE = "/workspace/public-observer/observer-diagnostic.tar.gz"
REMOTE_SIDECAR = REMOTE_ARCHIVE + ".sha256"


class ObserverDiagnosticError(RuntimeError):
    pass


def session_labels(*, program: str, campaign: str, run_id: str) -> dict[str, str]:
    return {"program_id": program, "campaign_id": campaign, "run_id": run_id}


def _resource_labels(item: dict) -> dict[str, str]:
    metadata = item.get("metadata")
    value = metadata.get("labels") if isinstance(metadata, dict) else item.get("labels")
    return value if isinstance(value, dict) else {}


def _session_resource(item: dict, *, name: str, labels: dict[str, str]) -> bool:
    observed = _resource_labels(item)
    return metadata_name(item) == name or all(observed.get(key) == value for key, value in labels.items())


def build_factory_command(
    action: str,
    *,
    root: Path,
    program: str,
    owner: str,
    allocation_id: str,
    reservation_id: str | None = None,
    setup_key: str | None = None,
    provider_resource_id: str | None = None,
    absolute_deadline: str | None = None,
    verification_sha256: str | None = None,
    get_absent: bool = False,
    inventory_absent: bool = False,
) -> list[str]:
    if action not in {"register-allocation", "request-cleanup", "mark-cleanup-verified"}:
        raise ValueError("unsupported factory lifecycle action")
    command = [
        sys.executable,
        "-m",
        "grad_research",
        action,
        "--root",
        str(root),
        "--program",
        program,
        "--owner",
        owner,
        "--allocation-id",
        allocation_id,
        "--ttl-seconds",
        "3600",
    ]
    if action == "register-allocation":
        if not all((reservation_id, setup_key, provider_resource_id, absolute_deadline)):
            raise ValueError("factory allocation registration fields are incomplete")
        command.extend([
            "--reservation-id", str(reservation_id),
            "--provider", "nebius",
            "--provider-resource-id", str(provider_resource_id),
            "--setup-key", str(setup_key),
            "--absolute-deadline", str(absolute_deadline),
        ])
    elif action == "mark-cleanup-verified":
        if verification_sha256 is None or len(verification_sha256) != 64:
            raise ValueError("factory cleanup verification SHA-256 is required")
        command.extend(["--verification-sha256", verification_sha256])
        if get_absent:
            command.append("--get-absent")
        if inventory_absent:
            command.append("--inventory-absent")
    return command


def cleanup_verification_sha256(
    *,
    allocation_id: str,
    provider_resource_id: str,
    get_absent: bool,
    inventory_absent: bool,
) -> str:
    payload = {
        "allocation_id": allocation_id,
        "provider": "nebius",
        "provider_resource_id": provider_resource_id,
        "get_absent": get_absent,
        "inventory_absent": inventory_absent,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _factory_environment() -> dict[str, str]:
    environment = os.environ.copy()
    factory_src = str(HERE.parents[5] / "research" / "factory" / "src")
    environment["PYTHONPATH"] = factory_src + (os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
    return environment


def _run_factory_action(action: str, *, events: Path, **fields: object) -> None:
    command = build_factory_command(action, **fields)  # type: ignore[arg-type]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=45,
        env=_factory_environment(),
    )
    emit(events, "factory_lifecycle", action=action, returncode=result.returncode)
    if result.returncode:
        raise ObserverDiagnosticError(f"factory {action} failed with exit {result.returncode}")


def should_run_fallback(
    *,
    observer_pass: bool,
    remaining_seconds: float,
    remaining_cost_usd: float | None = None,
) -> bool:
    """Admit no-CPU-sampling B2/A3 only after a measured observer breach."""
    if remaining_cost_usd is None:
        remaining_cost_usd = max(0.0, remaining_seconds) * COMBINED_HOURLY_RATE_USD / 3600
    return (
        not observer_pass
        and remaining_seconds >= FALLBACK_MIN_SECONDS
        and remaining_cost_usd >= FALLBACK_MIN_COST_USD
    )


def repair_window_seconds(
    *,
    next_action_tested: bool,
    estimated_start_seconds: float,
    seconds_until_deadline: float,
) -> int:
    """Retain only for a tested amendment that can start inside ten minutes."""
    if (
        not next_action_tested
        or estimated_start_seconds < 0
        or estimated_start_seconds > 600
        or seconds_until_deadline <= CLEANUP_RESERVE_SECONDS
    ):
        return 0
    available = max(0, int(seconds_until_deadline - CLEANUP_RESERVE_SECONDS))
    return min(600, int(estimated_start_seconds), available)


def build_host_bootstrap() -> str:
    """Reuse the tested vLLM bootstrap, then pin and exercise Nsight pre-transfer."""
    return build_vllm_host_bootstrap() + f'''
sudo docker build --network=host -t {RUNTIME_IMAGE} - <<'NSYS_DOCKERFILE'
FROM {RUNTIME_IMAGE}
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg; \
    curl -fsSL '{NSYS_SIGNING_KEY_URL}' -o /tmp/nvidia-devtools.asc; \
    gpg --show-keys --with-colons /tmp/nvidia-devtools.asc | grep -F 'fpr:::::::::{NSYS_SIGNING_KEY_FINGERPRINT}:'; \
    gpg --dearmor -o /usr/share/keyrings/nvidia-devtools.gpg /tmp/nvidia-devtools.asc; \
    echo 'deb [signed-by=/usr/share/keyrings/nvidia-devtools.gpg] https://developer.download.nvidia.com/devtools/repos/ubuntu2204/amd64/ /' > /etc/apt/sources.list.d/nvidia-devtools.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends nsight-systems-cli={NSYS_PACKAGE_VERSION}; \
    rm -rf /var/lib/apt/lists/*
NSYS_DOCKERFILE
sudo docker run --rm --gpus all --pid=host \
  --cap-add SYS_ADMIN --cap-add SYS_PTRACE --cap-add PERFMON --security-opt seccomp=unconfined \
  --entrypoint bash {RUNTIME_IMAGE} -lc '
set -Eeuo pipefail
nsys --version | tee /tmp/nsys-version.txt
grep -F "{NSYS_PACKAGE_VERSION}" /tmp/nsys-version.txt
nsys status -e | tee /tmp/nsys-status.txt
grep -F "CPU Profiling Environment (process-tree): OK" /tmp/nsys-status.txt
nsys profile --help > /tmp/nsys-profile-help.txt
for flag in cuda-graph-trace sample cpuctxsw; do grep -F -- "--$flag" /tmp/nsys-profile-help.txt; done
echo gpu_metrics_collector=unsupported_on_l40s
cat > /tmp/nsys-probe.py <<"PY"
import torch
x = torch.ones(1024, device="cuda")
graph = torch.cuda.CUDAGraph()
torch.cuda.synchronize()
with torch.cuda.graph(graph):
    x.add_(1)
graph.replay()
torch.cuda.synchronize()
PY
nsys profile --force-overwrite=true --trace=cuda,nvtx,osrt --cuda-graph-trace=node \
  --cuda-event-trace=true --sample=process-tree --cpuctxsw=process-tree --backtrace=none \
  --duration=2 --output=/tmp/nsys-capability-probe python3 /tmp/nsys-probe.py
test -s /tmp/nsys-capability-probe.nsys-rep
nsys export --force-overwrite=true --type=sqlite --output=/tmp/nsys-capability-probe.sqlite /tmp/nsys-capability-probe.nsys-rep
test -s /tmp/nsys-capability-probe.sqlite
'
'''


def build_container_command(spec_hash: str, deadline_epoch: int, science_deadline_epoch: int) -> list[str]:
    return [
        "sudo", "docker", "run", "--rm", "--gpus", "all", "--ipc=host", "--pid=host",
        "--shm-size=24g", "--cap-add", "SYS_NICE", "--cap-add", "SYS_ADMIN",
        "--cap-add", "SYS_PTRACE", "--cap-add", "PERFMON", "--security-opt", "seccomp=unconfined",
        "-v", "/home/glmrunner/input:/input:ro", "-v", "/workspace:/workspace",
        "-e", f"EXPERIMENT_SPEC_SHA256={spec_hash}",
        "-e", f"CAMPAIGN_DEADLINE_EPOCH={deadline_epoch}",
        "-e", f"SCIENCE_DEADLINE_EPOCH={science_deadline_epoch}",
        "-e", f"FALLBACK_MIN_SECONDS={FALLBACK_MIN_SECONDS}",
        "-e", f"FALLBACK_MIN_COST_USD={FALLBACK_MIN_COST_USD}",
        "-e", f"COMBINED_HOURLY_RATE_USD={COMBINED_HOURLY_RATE_USD}",
        "-e", "MODEL_MANIFEST_PATH=/workspace/model-awq/model-files.sha256",
        "-e", "VLLM_RPC_TIMEOUT=1800000",
        "--entrypoint", "bash", RUNTIME_IMAGE, "-lc",
        "rm -f /etc/ld.so.conf.d/00-cuda-compat.conf /etc/ld.so.conf.d/cuda-compat.conf; ldconfig; exec bash /input/remote_observer_diagnostic.sh",
    ]


def _hold_for_tested_repair(
    output_dir: Path,
    events: Path,
    deadline: float,
    *,
    next_action_tested: bool,
    estimated_start_seconds: float,
) -> None:
    seconds = repair_window_seconds(
        next_action_tested=next_action_tested,
        estimated_start_seconds=estimated_start_seconds,
        seconds_until_deadline=deadline - time.time(),
    )
    if not seconds:
        emit(events, "repair_window_skipped", reason="no_tested_action_within_ten_minutes")
        return
    decision_path = output_dir / "repair-decision.json"
    until = time.time() + seconds
    emit(events, "repair_window_open", maximum_seconds=seconds)
    while time.time() < until:
        if decision_path.exists():
            try:
                decision = json.loads(decision_path.read_text())
            except Exception:
                decision = {"action": "invalid"}
            if decision.get("action") == "teardown":
                emit(events, "repair_decision_received", action="teardown")
                return
        time.sleep(min(5, max(0, until - time.time())))
    emit(events, "repair_window_expired")


def run(
    output_dir: Path,
    name: str,
    key: Path,
    public_key: Path,
    model_dir: Path,
    tokenizer_dir: Path,
    spec_hash: str,
    *,
    factory_root: Path,
    factory_program: str,
    factory_campaign: str,
    factory_run_id: str,
    factory_owner: str,
    factory_reservation_id: str,
    factory_allocation_id: str,
    factory_setup_key: str,
    factory_absolute_deadline: str,
    next_action_tested: bool = False,
    next_action_estimated_start_seconds: float = 0,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "summary.json").exists() or (output_dir / "events.jsonl").exists():
        raise ObserverDiagnosticError("output directory already contains a prior run")
    if len(spec_hash) != 64 or any(character not in "0123456789abcdef" for character in spec_hash):
        raise ObserverDiagnosticError("experiment spec must be a lowercase SHA-256")
    if (factory_program, factory_campaign, factory_run_id, factory_setup_key) != (
        FACTORY_PROGRAM, FACTORY_CAMPAIGN, FACTORY_RUN_ID, FACTORY_SETUP_KEY
    ):
        raise ObserverDiagnosticError("factory program, campaign, run, or setup identity drifted")

    identities = validate_local_model(model_dir)
    required = [
        HERE / "remote_observer_diagnostic.sh",
        HERE / "observer_workload.py",
        HERE / "vllm_observer_patch.py",
        HERE / "analyze_nsys_observer.py",
        HERE / "vllm_preflight.py",
        model_dir / "config.json",
        *(tokenizer_dir / item for item in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja")),
    ]
    if not all(path.is_file() for path in required):
        raise ObserverDiagnosticError("observer session inputs are incomplete")

    events = output_dir / "events.jsonl"
    started = time.time()
    admitted_deadline = dt.datetime.fromisoformat(factory_absolute_deadline.replace("Z", "+00:00")).timestamp()
    deadline = min(started + ABSOLUTE_TIMEOUT_SECONDS, admitted_deadline)
    if deadline <= started + CLEANUP_RESERVE_SECONDS:
        raise ObserverDiagnosticError("factory-admitted absolute deadline leaves no scientific window")
    science_deadline = deadline - CLEANUP_RESERVE_SECONDS
    disk_name = name + "-boot"
    instance_id = None
    allocation_result = None
    artifact_hash = None
    manifest_files = 0
    outcome = "FAIL"
    absent = False
    factory_registered = False
    factory_cleanup_requested = False
    factory_cleanup_verified = False

    initial_instances = list_items("instance")
    initial_disks = list_items("disk")
    labels = session_labels(program=factory_program, campaign=factory_campaign, run_id=factory_run_id)
    matching_instances = [row for row in initial_instances if _session_resource(row, name=name, labels=labels)]
    matching_disks = [row for row in initial_disks if _session_resource(row, name=disk_name, labels=labels)]
    if matching_instances or matching_disks or find_named_instance(name):
        raise ObserverDiagnosticError("factory-labeled or named resource from this run requires recovery before creation")
    if initial_instances:
        raise ObserverDiagnosticError("stock control failed: project already has an active or named instance")
    emit(events, "stock_control", instance_count=0, disk_count=len(initial_disks), matching_labeled_resources=0, **identities)
    contract = {
        "causal_hypothesis": "Pinned Nsight CUDA/NVTX/OSRT, node-level CUDA Graph, context-switch, and GPU metrics can expose the fixed decode critical path without changing throughput or median latency by more than 3% or tail latency by more than 5%.",
        "stock_control": "Patched vLLM observer hooks with Nsight collection off; A1 and A2 bracket B1 on the same retained L40S.",
        "candidate": "Nsight Systems 2026.3.1.157 CUDA/NVTX/OSRT, node-level CUDA Graph, and process-tree sampling; GPU Metrics explicitly unsupported on the L40S. Conditional B2 removes CPU sampling/context switching before A3 after an overhead breach.",
        "model": identities,
        "runtime": {"image": IMAGE, "derived_image": RUNTIME_IMAGE, "transformers_revision": TRANSFORMERS_REVISION},
        "hardware": {"count": 1, "platform": PLATFORM, "preset": PRESET, "purchase_model": "preemptible_stop"},
        "workload": {"prompt_tokens": 8192, "output_tokens": 32, "concurrency": 8, "requests_per_arm": 8, "seed": 470147, "prefix_cache": False},
        "quality_gate": "All requests must have exact 8192/32 geometry, finish_reason=length, and 32 correlated token timestamps.",
        "slo": {"all_request_ttft_ms_max": 10000, "all_request_tpot_ms_max": 100},
        "observer_overhead_gate": {"throughput_abs_fraction": 0.03, "median_e2e_abs_fraction": 0.03, "p95_e2e_abs_fraction": 0.05},
        "telemetry": ["request TTFT/TPOT/E2E/throughput/failures", "vLLM metrics and scheduler batches", "NVTX/CUDA/OSRT/context switches", "CUDA Graph nodes", "100 ms nvidia-smi GPU utilization/VRAM/power/clocks/temperature", "explicit Nsight GPU Metrics unavailability"],
        "artifact_contract": "Per-arm content-addressed archives plus raw nsys-rep/SQLite, workload rows, server logs, metrics, scheduler events, phase telemetry, environment identities, session manifest, and outer archive sidecar; retrieve and verify before delete.",
        "absolute_timeout_seconds": ABSOLUTE_TIMEOUT_SECONDS,
        "cleanup_reserve_seconds": CLEANUP_RESERVE_SECONDS,
        "factory_cleanup_reserve_usd": FACTORY_CLEANUP_RESERVE_USD,
        "max_total_cost_usd": MAX_COST_USD,
        "derived_rate_exposure_cap_usd": COMBINED_HOURLY_RATE_USD * ABSOLUTE_TIMEOUT_SECONDS / 3600,
        "derived_rate_plus_factory_cleanup_reserve_cap_usd": COMBINED_HOURLY_RATE_USD * ABSOLUTE_TIMEOUT_SECONDS / 3600 + FACTORY_CLEANUP_RESERVE_USD,
        "rates_usd_per_hour": {"compute": HOURLY_RATE_USD, "disk": DISK_HOURLY_RATE_USD, "public_ipv4_and_egress": "excluded_unknown"},
        "nsys_package_version": NSYS_PACKAGE_VERSION,
        "factory": {
            "root": str(factory_root),
            "program": factory_program,
            "campaign": factory_campaign,
            "run_id": factory_run_id,
            "owner": factory_owner,
            "reservation_id": factory_reservation_id,
            "allocation_id": factory_allocation_id,
            "setup_key": factory_setup_key,
            "absolute_deadline_utc": dt.datetime.fromtimestamp(deadline, dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }
    (output_dir / "provider-request.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")

    try:
        create = build_create_command(
            name=name,
            disk_name=disk_name,
            cloud_init=make_cloud_init(public_key.read_text()),
            disk_gib=DISK_GIB,
            platform=PLATFORM,
            preset=PRESET,
            preemptible=True,
            labels=labels,
        )
        proc = subprocess.run(create, capture_output=True, text=True, timeout=180)
        if proc.returncode:
            raise ObserverDiagnosticError(f"instance create failed with exit {proc.returncode}")
        instance_id = extract_instance_id(json.loads(proc.stdout))
        subprocess.Popen(
            [sys.executable, str(HERE / "placement_control.py"), "watchdog", instance_id, disk_name, str(deadline)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _run_factory_action("register-allocation", events=events, root=factory_root,
            program=factory_program, owner=factory_owner, allocation_id=factory_allocation_id,
            reservation_id=factory_reservation_id, setup_key=factory_setup_key,
            provider_resource_id=instance_id,
            absolute_deadline=dt.datetime.fromtimestamp(deadline, dt.timezone.utc).isoformat().replace("+00:00", "Z"))
        factory_registered = True
        emit(events, "instance_created", instance_id=instance_id)

        ip = None
        while time.time() < min(deadline, started + 420):
            payload = get_instance(instance_id)
            if payload is None:
                raise ObserverDiagnosticError("instance disappeared before readiness")
            ip = extract_public_ipv4(payload)
            if ip:
                break
            time.sleep(5)
        if not ip:
            raise ObserverDiagnosticError("public IP readiness exceeded placement window")
        wait_ssh(ip, key, min(deadline, started + 480))
        emit(events, "ssh_ready", elapsed_seconds=round(time.time() - started, 3))

        if run_ssh(ip, key, "mkdir -p /home/glmrunner/input/model-config-only", timeout=30).returncode:
            raise ObserverDiagnosticError("remote preflight input directory creation failed")
        scp_to(ip, key, [HERE / "vllm_preflight.py"], "/home/glmrunner/input/")
        scp_to(ip, key, [model_dir / "config.json"], "/home/glmrunner/input/model-config-only/")
        bootstrap_timeout = max(1, min(1200, int(deadline - time.time() - CLEANUP_RESERVE_SECONDS)))
        bootstrap = run_ssh(ip, key, "bash -s", timeout=bootstrap_timeout, input_text=build_host_bootstrap())
        (output_dir / "host-bootstrap.stdout.log").write_text(bootstrap.stdout)
        (output_dir / "host-bootstrap.stderr.log").write_text(bootstrap.stderr)
        if bootstrap.returncode:
            raise ObserverDiagnosticError("pinned vLLM/Nsight/CUDA capability preflight failed")
        emit(events, "nsys_preflight_passed", version=NSYS_PACKAGE_VERSION, before_model_transfer=True)

        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory)
            staged = []
            for source in required[:4]:
                target = staging / source.name
                shutil.copy2(source, target)
                staged.append(target)
            if run_ssh(ip, key, "mkdir -p /home/glmrunner/input/tokenizer", timeout=30).returncode:
                raise ObserverDiagnosticError("remote observer input directory creation failed")
            scp_to(ip, key, staged, "/home/glmrunner/input/")
            scp_to(ip, key, required[-3:], "/home/glmrunner/input/tokenizer/")

        if time.time() + CLEANUP_RESERVE_SECONDS + 300 >= deadline:
            raise ObserverDiagnosticError("insufficient cap remains for the retained checkpoint transfer and one bracket")
        probe_hash = probe_transfer(ip, key)
        emit(events, "tiny_transfer_probe_passed", sha256=probe_hash)
        transfer_started = time.time()
        transfer_local_model(ip, key, model_dir)
        emit(events, "verified_local_awq_transferred_once", elapsed_seconds=round(time.time() - transfer_started, 3))

        remote = run_ssh(
            ip,
            key,
            build_container_command(spec_hash, int(deadline), int(science_deadline)),
            timeout=max(1, int(deadline - time.time())),
        )
        (output_dir / "remote.stdout.log").write_text(remote.stdout)
        (output_dir / "remote.stderr.log").write_text(remote.stderr)

        archive = output_dir / "observer-diagnostic.tar.gz"
        sidecar = output_dir / "observer-diagnostic.remote.sha256"
        scp_from(ip, key, REMOTE_ARCHIVE, archive)
        scp_from(ip, key, REMOTE_SIDECAR, sidecar)
        artifact_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        if artifact_hash != sidecar.read_text().split()[0]:
            raise ObserverDiagnosticError("remote/local observer artifact hash mismatch")
        manifest_files = verify_internal_manifest(archive)
        allocation_result = json.loads(extract_member(archive, "/allocation-result.json"))
        outcome = "PASS" if remote.returncode == 0 and allocation_result.get("bracket_complete") is True else "FAIL"
        emit(events, "artifact_retrieved", sha256=artifact_hash, manifest_files=manifest_files, outcome=outcome)
    except Exception as error:
        emit(events, "experiment_error", error_type=type(error).__name__, message=str(error)[:500])
        if instance_id is not None and factory_registered and allocation_result is None:
            _hold_for_tested_repair(
                output_dir,
                events,
                deadline,
                next_action_tested=next_action_tested,
                estimated_start_seconds=next_action_estimated_start_seconds,
            )
    finally:
        if instance_id is None:
            try:
                for row in list_items("instance"):
                    if _session_resource(row, name=name, labels=labels) and metadata_id(row):
                        instance_id = metadata_id(row)
                        break
            except Exception:
                instance_id = None
        delete_requested = time.time()
        if instance_id and factory_registered:
            try:
                _run_factory_action("request-cleanup", events=events, root=factory_root,
                    program=factory_program, owner=factory_owner, allocation_id=factory_allocation_id)
                factory_cleanup_requested = True
            except Exception as error:
                emit(events, "factory_cleanup_request_error", error_type=type(error).__name__, message=str(error)[:300])
        if instance_id:
            delete_instance(instance_id)
            absent = wait_absent(instance_id, min(deadline + 240, time.time() + 240))
        else:
            absent = True
        for disk in list_items("disk"):
            if _session_resource(disk, name=disk_name, labels=labels) and metadata_id(disk):
                delete_disk(metadata_id(disk))
        final_instances = list_items("instance")
        final_disks = list_items("disk")
        named_instances = [row for row in final_instances if _session_resource(row, name=name, labels=labels)]
        named_disks = [row for row in final_disks if _session_resource(row, name=disk_name, labels=labels)]
        inventory_absent = not named_instances and not named_disks
        if factory_registered and absent and inventory_absent:
            verification_sha256 = cleanup_verification_sha256(
                allocation_id=factory_allocation_id,
                provider_resource_id=instance_id or "absent-before-create",
                get_absent=absent,
                inventory_absent=inventory_absent,
            )
            try:
                _run_factory_action("mark-cleanup-verified", events=events, root=factory_root,
                    program=factory_program, owner=factory_owner, allocation_id=factory_allocation_id,
                    verification_sha256=verification_sha256, get_absent=True, inventory_absent=True)
                factory_cleanup_verified = True
            except Exception as error:
                emit(events, "factory_cleanup_verification_error", error_type=type(error).__name__, message=str(error)[:300])
        cleanup = absent and inventory_absent and (factory_cleanup_verified if factory_registered else True)
        allocation_seconds = min(ABSOLUTE_TIMEOUT_SECONDS, max(0.0, delete_requested - started))
        cost = allocation_seconds / 3600 * COMBINED_HOURLY_RATE_USD
        summary = {
            "outcome": outcome,
            "cleanup_pass": cleanup,
            "instance_get_not_found": absent,
            "instance_id": instance_id,
            "factory_registered": factory_registered,
            "factory_cleanup_requested": factory_cleanup_requested,
            "factory_cleanup_verified": factory_cleanup_verified,
            "allocation_seconds": round(allocation_seconds, 3),
            "compute_cost_usd_derived": round(allocation_seconds / 3600 * HOURLY_RATE_USD, 9),
            "disk_cost_usd_derived": round(allocation_seconds / 3600 * DISK_HOURLY_RATE_USD, 9),
            "cost_usd_derived": round(cost, 9),
            "cost_cap_usd": MAX_COST_USD,
            "cost_basis": "measured exposure at authenticated Nebius preemptible VM and disk rates; public IPv4/egress excluded; invoice pending",
            "artifact_sha256": artifact_hash,
            "manifest_file_count": manifest_files,
            "allocation_result": allocation_result,
            "final_instance_count": len(named_instances),
            "final_disk_count": len(named_disks),
            "ended_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        emit(events, "cleanup_verified", cleanup_pass=cleanup, instance_get_not_found=absent, final_instance_count=len(named_instances), final_disk_count=len(named_disks))
    return 0 if outcome == "PASS" and cleanup else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--ssh-public-key", type=Path, required=True)
    parser.add_argument("--local-model-dir", type=Path, required=True)
    parser.add_argument("--reference-tokenizer-dir", type=Path, required=True)
    parser.add_argument("--experiment-spec-sha256", required=True)
    parser.add_argument("--factory-root", type=Path, required=True)
    parser.add_argument("--factory-program", required=True)
    parser.add_argument("--factory-campaign", required=True)
    parser.add_argument("--factory-run-id", required=True)
    parser.add_argument("--factory-owner", required=True)
    parser.add_argument("--factory-reservation-id", required=True)
    parser.add_argument("--factory-allocation-id", required=True)
    parser.add_argument("--factory-setup-key", required=True)
    parser.add_argument("--factory-absolute-deadline", required=True)
    parser.add_argument("--next-action-tested", action="store_true")
    parser.add_argument("--next-action-estimated-start-seconds", type=float, default=0)
    args = parser.parse_args()
    return run(
        args.output_dir,
        args.name,
        args.ssh_key,
        args.ssh_public_key,
        args.local_model_dir,
        args.reference_tokenizer_dir,
        args.experiment_spec_sha256,
        factory_root=args.factory_root,
        factory_program=args.factory_program,
        factory_campaign=args.factory_campaign,
        factory_run_id=args.factory_run_id,
        factory_owner=args.factory_owner,
        factory_reservation_id=args.factory_reservation_id,
        factory_allocation_id=args.factory_allocation_id,
        factory_setup_key=args.factory_setup_key,
        factory_absolute_deadline=args.factory_absolute_deadline,
        next_action_tested=args.next_action_tested,
        next_action_estimated_start_seconds=args.next_action_estimated_start_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
