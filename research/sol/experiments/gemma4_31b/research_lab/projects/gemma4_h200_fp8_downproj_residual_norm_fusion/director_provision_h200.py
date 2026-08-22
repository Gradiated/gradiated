#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


LAB = Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects/gemma4_h200_fp8_downproj_residual_norm_fusion"
FACTORY_SRC = Path("/root/workspace/research/factory/src")
NEBIUS_TOOLS = Path(
    "/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius"
)
SSH_PUBLIC_KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519.pub")
SSH_IDENTITY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = Path("/root/.config/nebius/glm-campaign/known_hosts")
PROJECT_ID = "project-e00h1vhmpr00vbmfd5k7pg"
REGION = "eu-north1"
SUBNET_ID = "vpcsubnet-e00gr2f2ydymwjmr4f"
PLATFORM = "gpu-h200-sxm"
PRESET = "1gpu-16vcpu-200gb"
HOURLY_COST_USD = 2.45
LIFECYCLE_SECONDS = 4200


sys.path.insert(0, str(NEBIUS_TOOLS))
import placement_control  # noqa: E402
import vllm_smoke_control  # noqa: E402


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def first_prefixed(value: Any, prefix: str) -> str:
    for item in walk(value):
        if isinstance(item, str) and item.startswith(prefix):
            return item
    raise RuntimeError(f"provider response omitted {prefix} identity")


def public_ipv4(value: Any) -> str:
    address = placement_control.extract_public_ipv4(value)
    if not address:
        raise RuntimeError("provider response omitted public IPv4")
    return address


def main() -> int:
    started_at_utc = utc_now()
    started_epoch = time.time()
    deadline_epoch = started_epoch + LIFECYCLE_SECONDS
    deadline_utc = (
        dt.datetime.fromtimestamp(deadline_epoch, dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dt%H%Mz").lower()
    name = f"gemma4-downproj-h200-{stamp}"
    disk_name = f"{name}-boot"
    cloud_init = placement_control.make_cloud_init(SSH_PUBLIC_KEY.read_text())
    command = placement_control.build_create_command(
        name=name,
        disk_name=disk_name,
        cloud_init=cloud_init,
        disk_gib=100,
        platform=PLATFORM,
        preset=PRESET,
        preemptible=True,
        labels={"lab": "gemma4-31b", "project": "downproj-residual-norm"},
    )
    create = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=150,
        check=False,
    )
    if create.returncode:
        raise RuntimeError(f"Nebius create failed with exit {create.returncode}")
    payload = json.loads(create.stdout)
    instance_id = placement_control.extract_instance_id(payload)
    disk_id = first_prefixed(payload, "computedisk-")
    address = public_ipv4(payload)
    bench_id = f"h200-downproj-{instance_id}"
    watchdog = vllm_smoke_control.start_independent_watchdog(
        instance_id,
        disk_name,
        deadline_epoch,
        f"{name}-watchdog",
        unit_manager="user",
    )
    spec = {
        "id": bench_id,
        "provider": "nebius",
        "accelerator": "nvidia-h200-sxm",
        "hourly_cost_usd": HOURLY_COST_USD,
        "resource": {
            "project_id": PROJECT_ID,
            "region": REGION,
            "instance_id": instance_id,
            "instance_name": name,
            "disk_id": disk_id,
            "disk_name": disk_name,
            "public_ipv4": address,
            "platform": PLATFORM,
            "preset": PRESET,
            "allocation_type": "preemptible",
            "subnet_id": SUBNET_ID,
            "ssh_user": "glmrunner",
            "ssh_identity_path": str(SSH_IDENTITY),
            "known_hosts_namespace": str(KNOWN_HOSTS),
            "connection_state": "created_unprobed",
        },
        "contents": {
            "schema_version": 1,
            "project": "gemma4_h200_fp8_downproj_residual_norm_fusion",
            "role": "cold_h200_downproj_residual_norm_exact_consumer_component",
            "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "checkpoint": "No full checkpoint required; exact-shape component inputs are not staged.",
            "image": "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6; not yet pulled.",
            "runtime": "Fresh Nebius ubuntu24.04-cuda13.0 base; strict connection and accelerator identity are not yet verified.",
            "caches": "None assumed.",
            "server_state": "Provider-created and protected in maintenance; no SSH, setup, CUDA, or science performed.",
            "scientific_terminal": "Exact M=1/16/32 down-to-QKV component unconsumed.",
            "state": "maintenance_identity_unverified",
            "summary": "Protected cold H200 created for strict identity verification and the sole down-projection exact-consumer claimant.",
            "next": "Director must perform one strict identity and quiescence probe before making the bench ready.",
        },
        "lifecycle": {
            "provider_started_at_utc": started_at_utc,
            "deadline_utc": deadline_utc,
            "watchdog": watchdog,
        },
    }
    with tempfile.TemporaryDirectory() as directory:
        spec_path = Path(directory) / "bench.json"
        spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
        register = subprocess.run(
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
            ],
            env={"PYTHONPATH": str(FACTORY_SRC)},
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    if register.returncode:
        raise RuntimeError(f"GPU pool registration failed: {register.stderr.strip()}")
    result = {
        "schema_version": 1,
        "classification": "registered_maintenance_cold_h200",
        "provider_started_at_utc": started_at_utc,
        "deadline_utc": deadline_utc,
        "bench_id": bench_id,
        "instance_id": instance_id,
        "instance_name": name,
        "disk_id": disk_id,
        "disk_name": disk_name,
        "public_ipv4": address,
        "project_id": PROJECT_ID,
        "region": REGION,
        "platform": PLATFORM,
        "preset": PRESET,
        "allocation_type": "preemptible",
        "hourly_cost_usd": HOURLY_COST_USD,
        "watchdog": watchdog,
        "reservation_authorized_usd": 3.0,
        "conservative_lifecycle_seconds": LIFECYCLE_SECONDS,
        "conservative_compute_cost_usd": HOURLY_COST_USD
        * LIFECYCLE_SECONDS
        / 3600,
        "provider_mutation_performed": True,
        "inventory_condition": "maintenance",
        "identity_verified": False,
        "created_at_utc": utc_now(),
    }
    (PROJECT / "H200_PROVIDER_CREATE_RESULT.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
