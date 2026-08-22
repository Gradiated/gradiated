#!/usr/bin/env python3
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path


LAB = Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects/gemma4_rtxpro6000_fp8_endpoint"
SHARED_RUNPOD = Path(
    "/root/workspace/research/sol/experiments/glm47flash/campaign_100/phase_b"
)
WATCHDOG_SCRIPT = Path(
    "/root/workspace/research/sol/experiments/glm47flash/runpod_watchdog.py"
)
PRIVATE_KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUBLIC_KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519.pub")
KNOWN_HOSTS = Path("/root/.config/runpod/gemma4/known_hosts")

GPU_TYPE = "NVIDIA RTX PRO 6000 Blackwell Workstation Edition"
ACCELERATOR = "nvidia-rtx-pro-6000-blackwell-workstation"
IMAGE = "runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404"
NAME = "gemma4-rtxpro6000-workstation-fp8-endpoint-20260729t0312z"
LIFECYCLE_SECONDS = 5 * 60 * 60
MAX_HOURLY_COST_USD = 1.99
ARTIFACT = PROJECT / "DIRECTOR_RTXPRO6000_PROVIDER_CREATE_20260729T0312Z.json"
EVENTS = PROJECT / "artifacts/rtxpro6000-provider-20260729t0312z/events.jsonl"


def utc_from_epoch(value: float) -> str:
    return (
        datetime.datetime.fromtimestamp(value, datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=True)


def main() -> int:
    if "RUNPOD_API_KEY" not in os.environ:
        raise RuntimeError("RUNPOD_API_KEY is not configured")
    if not PRIVATE_KEY.is_file() or not PUBLIC_KEY.is_file():
        raise RuntimeError("the established controller SSH identity is absent")
    sys.path.insert(0, str(SHARED_RUNPOD))
    from runpod_stock_control import RunPodProvider

    provider_started_epoch = time.time()
    provider_started_at = utc_from_epoch(provider_started_epoch)
    deadline_epoch = provider_started_epoch + LIFECYCLE_SECONDS
    deadline_utc = utc_from_epoch(deadline_epoch)
    provider = RunPodProvider(
        event_log=EVENTS,
        deadline_epoch=deadline_epoch,
        startup_timeout_seconds=180,
    )
    request = {
        "name": NAME,
        "imageName": IMAGE,
        "computeType": "GPU",
        "gpuTypeIds": [GPU_TYPE],
        "gpuTypePriority": "availability",
        "gpuCount": 1,
        "cloudType": "SECURE",
        "supportPublicIp": True,
        "containerDiskInGb": 80,
        "volumeInGb": 160,
        "volumeMountPath": "/workspace",
        "ports": ["22/tcp"],
        "env": {"PUBLIC_KEY": PUBLIC_KEY.read_text().strip()},
    }
    created = provider.create(request)
    pod_id = created.get("id")
    hourly_cost = float(created.get("costPerHr", 0))
    if not pod_id:
        raise RuntimeError("RunPod create response omitted pod id")
    if hourly_cost <= 0 or hourly_cost > MAX_HOURLY_COST_USD:
        raise RuntimeError(
            f"created pod hourly cost {hourly_cost} exceeds {MAX_HOURLY_COST_USD}"
        )

    watchdog_unit = f"gemma4-rtxpro6000-{pod_id}-watchdog.service"
    watchdog_cancel = PROJECT / f".watchdog-{pod_id}.cancel"
    watchdog_log = (
        PROJECT
        / "artifacts/rtxpro6000-provider-20260729t0312z"
        / "watchdog.jsonl"
    )
    watchdog_cancel.unlink(missing_ok=True)
    watchdog_log.parent.mkdir(parents=True, exist_ok=True)
    run_checked(["systemctl", "--user", "import-environment", "RUNPOD_API_KEY"])
    run_checked(
        [
            "systemd-run",
            "--user",
            "--unit",
            watchdog_unit,
            "--collect",
            sys.executable,
            str(WATCHDOG_SCRIPT),
            pod_id,
            str(deadline_epoch),
            str(watchdog_cancel),
            str(watchdog_log),
        ]
    )
    watchdog_state = run_checked(
        [
            "systemctl",
            "--user",
            "show",
            watchdog_unit,
            "-p",
            "MainPID",
            "-p",
            "ControlGroup",
            "-p",
            "ActiveState",
            "--value",
        ]
    ).stdout.splitlines()
    main_pid = int(watchdog_state[0])
    control_group = watchdog_state[1]
    active_state = watchdog_state[2]
    if main_pid <= 0 or active_state != "active":
        raise RuntimeError("RunPod watchdog did not become active")

    bench_id = f"rtxpro6000-gemma4-fp8-{pod_id}"
    resource = {
        "pod_id": pod_id,
        "pod_name": NAME,
        "gpu_type_id": GPU_TYPE,
        "cloud_type": "secure",
        "identity_file": str(PRIVATE_KEY),
        "identity_public_key": str(PUBLIC_KEY),
        "ssh_proxy_host": "ssh.runpod.io",
        "ssh_proxy_user": pod_id,
        "known_hosts_namespace": str(KNOWN_HOSTS),
        "connection_state": "pending_runtime_ports_and_strict_identity_probe",
    }
    machine_id = created.get("machineId")
    if machine_id:
        resource["machine_id"] = str(machine_id)
    spec = {
        "id": bench_id,
        "provider": "runpod",
        "accelerator": ACCELERATOR,
        "hourly_cost_usd": hourly_cost,
        "resource": resource,
        "lifecycle": {
            "provider_started_at_utc": provider_started_at,
            "deadline_utc": deadline_utc,
            "watchdog": {
                "unit": watchdog_unit,
                "unit_manager": "user",
                "main_pid": main_pid,
                "control_group": control_group,
            },
        },
        "contents": {
            "schema_version": 1,
            "project": "gemma4_rtxpro6000_fp8_endpoint",
            "state": "provider_created_maintenance_pending_identity_probe",
            "model": "Exact google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4 stock dynamic-FP8 endpoint.",
            "checkpoint": "Not staged; bind controller manifest SHA-256 864f24f4631315cd17cc8a3ff1ea57b2725d2a24f29c45778b101f16b5228a4f and 62,546,338,248 bytes.",
            "image": IMAGE,
            "runtime": "Fresh RunPod secure 1x RTX PRO 6000 Blackwell Workstation Edition; hardware and strict SSH identity not yet verified.",
            "caches": "None; cold pod and 160-GiB persistent volume.",
            "server_state": "No endpoint, model load, checkpoint staging, or scientific request has started.",
            "artifacts": str(ARTIFACT),
            "scientific_terminal": "One exact stock dynamic-FP8 true concurrent-c32 endpoint sample remains unconsumed.",
            "next": "Director verifies provider runtime ports, strict SSH identity, sm_120 hardware, and empty accelerator state once, then marks the bench ready for gemma4_rtxpro6000_fp8_endpoint.",
        },
    }
    spec_path = PROJECT / "DIRECTOR_RTXPRO6000_BENCH_SPEC_20260729T0312Z.json"
    atomic_json(spec_path, spec)
    registered = json.loads(
        run_checked(
            [
                sys.executable,
                "-m",
                "grad_research.gpu_pool",
                "--lab",
                str(LAB),
                "register",
                "--spec",
                str(spec_path),
                "--condition",
                "maintenance",
            ]
        ).stdout
    )
    artifact = {
        "schema_version": 1,
        "classification": "provider_created_registered_maintenance",
        "provider_started_at_utc": provider_started_at,
        "deadline_utc": deadline_utc,
        "maximum_lifecycle_seconds": LIFECYCLE_SECONDS,
        "maximum_gpu_exposure_usd": MAX_HOURLY_COST_USD
        * LIFECYCLE_SECONDS
        / 3600,
        "authorized_project_usd": 14.0,
        "project_prior_actual_usd": 0.0,
        "pod": {
            key: created.get(key)
            for key in (
                "id",
                "costPerHr",
                "createdAt",
                "desiredStatus",
                "imageName",
                "machineId",
                "gpuCount",
                "ports",
            )
            if created.get(key) is not None
        },
        "bench_id": bench_id,
        "bench_status": registered["status"],
        "watchdog": spec["lifecycle"]["watchdog"],
        "next": "One later director observation must resolve runtime connection identity, verify strict SSH and exact sm_120 hardware, then mark this registered bench ready. No setup or claim is authorized by this artifact.",
    }
    atomic_json(ARTIFACT, artifact)
    print(
        json.dumps(
            {
                "artifact": str(ARTIFACT),
                "bench_id": bench_id,
                "pod_id": pod_id,
                "hourly_cost_usd": hourly_cost,
                "deadline_utc": deadline_utc,
                "status": registered["status"],
                "watchdog_unit": watchdog_unit,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
