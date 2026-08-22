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
PROJECT_ID = "gemma4_vllm026_sm120_heterogeneous_attention_split"
PROJECT = LAB / "projects" / PROJECT_ID
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
BASE_IMAGE = "runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404"
SCIENTIFIC_IMAGE = (
    "docker.io/vllm/vllm-openai:nightly@"
    "sha256:494f9c118fb6684bcdd26bb37c687b16163278c0e18f5c157c9185c2584598b7"
)
NAME = "gemma4-sm120-attention-c32-endpoint-20260729t1130z"
LIFECYCLE_SECONDS = 90 * 60
MAX_HOURLY_COST_USD = 1.89
AUTHORIZED_PROJECT_USD = 6.0
PROJECT_PRIOR_ACTUAL_USD = 2.83
OWNER_READY = PROJECT / "SM120_ATTENTION_C32_ENDPOINT_OWNER_READY.json"
OWNER_READY_SHA256 = (
    "a33638d3f322b731591f810f38a3f7932fedd33127e2efa38ca9efe57071bb78"
)
ARTIFACT = (
    PROJECT / "DIRECTOR_SM120_ATTENTION_C32_PROVIDER_CREATE_20260729T1130Z.json"
)
SPEC_PATH = (
    PROJECT / "DIRECTOR_SM120_ATTENTION_C32_BENCH_SPEC_20260729T1130Z.json"
)
EVENTS = (
    PROJECT
    / "artifacts/sm120-attention-c32-provider-20260729t1130z/events.jsonl"
)


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
    if not OWNER_READY.is_file():
        raise RuntimeError("the bound SM120 c32 owner-ready artifact is absent")

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
        "imageName": BASE_IMAGE,
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

    created: dict[str, object] | None = None
    pod_id: str | None = None
    watchdog_unit: str | None = None
    try:
        created = provider.create(request)
        raw_pod_id = created.get("id")
        pod_id = str(raw_pod_id) if raw_pod_id else None
        hourly_cost = float(created.get("costPerHr", 0))
        if not pod_id:
            raise RuntimeError("RunPod create response omitted pod id")
        if hourly_cost <= 0 or hourly_cost > MAX_HOURLY_COST_USD:
            raise RuntimeError(
                f"created pod hourly cost {hourly_cost} exceeds "
                f"{MAX_HOURLY_COST_USD}"
            )

        watchdog_unit = f"gemma4-sm120-attention-c32-{pod_id}-watchdog.service"
        watchdog_cancel = PROJECT / f".watchdog-{pod_id}.cancel"
        watchdog_log = (
            PROJECT
            / "artifacts/sm120-attention-c32-provider-20260729t1130z"
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

        bench_id = f"rtxpro6000-sm120-attention-c32-{pod_id}"
        resource: dict[str, object] = {
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
                "project": PROJECT_ID,
                "state": "provider_created_maintenance_pending_identity_probe",
                "model": (
                    "Exact google/gemma-4-31B-it@"
                    "b9ea41a2887d8607f594846523f94c6cc75ac8a4 for the matched "
                    "SM120 all-TRITON versus 50-TRITON/10-FLEX c32 endpoint pair."
                ),
                "checkpoint": (
                    "Not staged; bind manifest SHA-256 "
                    "864f24f4631315cd17cc8a3ff1ea57b2725d2a24f29c45778b101f16b5228a4f "
                    "and 62,546,338,248 bytes."
                ),
                "image": (
                    f"Fresh provider base {BASE_IMAGE}; the later launch binding "
                    f"must preserve scientific image {SCIENTIFIC_IMAGE} and the "
                    "official vLLM 0.26.0+cu129 wheel."
                ),
                "runtime": (
                    "Fresh RunPod secure 1x RTX PRO 6000 Blackwell Workstation "
                    "Edition; strict SSH, sm_120, and idle-GPU identity are not "
                    "yet verified."
                ),
                "caches": "None; cold pod and 160-GiB persistent volume.",
                "server_state": (
                    "No endpoint, model load, checkpoint staging, setup, CUDA "
                    "call, or scientific request has started."
                ),
                "artifacts": (
                    f"{ARTIFACT.name}; {OWNER_READY.name} SHA-256 "
                    f"{OWNER_READY_SHA256}"
                ),
                "scientific_terminal": (
                    "The matched all-TRITON versus 50-TRITON/10-FLEX concurrent-"
                    "c32 endpoint pair remains unconsumed."
                ),
                "next": (
                    "Director verifies provider runtime ports, strict SSH "
                    "identity, exact sm_120 hardware, and zero accelerator "
                    "allocations once, then publishes the execution binding and "
                    "marks this bench ready only for "
                    "gemma4_vllm026_sm120_heterogeneous_attention_split."
                ),
            },
        }
        atomic_json(SPEC_PATH, spec)
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
                    str(SPEC_PATH),
                    "--condition",
                    "maintenance",
                ]
            ).stdout
        )
        future_exposure_usd = hourly_cost * LIFECYCLE_SECONDS / 3600
        if PROJECT_PRIOR_ACTUAL_USD + future_exposure_usd > AUTHORIZED_PROJECT_USD:
            raise RuntimeError("conservative cumulative lifecycle exceeds reservation")
        artifact = {
            "schema_version": 1,
            "classification": "provider_created_registered_maintenance",
            "project": PROJECT_ID,
            "provider_started_at_utc": provider_started_at,
            "deadline_utc": deadline_utc,
            "maximum_lifecycle_seconds": LIFECYCLE_SECONDS,
            "maximum_gpu_exposure_usd": future_exposure_usd,
            "authorized_project_usd": AUTHORIZED_PROJECT_USD,
            "project_prior_actual_usd": PROJECT_PRIOR_ACTUAL_USD,
            "conservative_cumulative_usd": (
                PROJECT_PRIOR_ACTUAL_USD + future_exposure_usd
            ),
            "owner_ready": {
                "path": str(OWNER_READY),
                "sha256": OWNER_READY_SHA256,
            },
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
            "science_or_setup_ran": False,
            "next": (
                "One later director observation must resolve runtime connection "
                "identity, verify strict SSH, exact sm_120 hardware, and a "
                "quiescent accelerator, then publish an execution binding and "
                "mark the registered bench ready. No claim, setup, or experiment "
                "is authorized by this artifact."
            ),
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
    except Exception:
        if watchdog_unit:
            subprocess.run(
                ["systemctl", "--user", "stop", watchdog_unit],
                check=False,
                text=True,
                capture_output=True,
            )
        if pod_id:
            provider.delete(pod_id)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
