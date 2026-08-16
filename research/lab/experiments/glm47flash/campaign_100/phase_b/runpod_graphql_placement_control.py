#!/usr/bin/env python3
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from orchestrator import ProviderNotFound
from runpod_stock_control import (
    GRAPHQL_CREATE_MUTATION,
    GRAPHQL_CREATE_SURFACE,
    RunPodProvider,
    utc_now,
)


IMAGE = "runpod/pytorch"
NAME = "glm47flash-h100-ap-in-placement-control"
GPU_TYPE = "NVIDIA H100 80GB HBM3"
DATA_CENTER = "AP-IN-1"
CUDA_VERSIONS = ["13.0"]
CONTAINER_DISK_GB = 20
VOLUME_GB = 20
HERE = Path(__file__).resolve().parent
CAMPAIGN = HERE.parent
EXPERIMENT = CAMPAIGN.parent


class PlacementControlError(RuntimeError):
    pass


class PlacementWatchdog:
    def __init__(self, contract):
        if contract.get("independent_process") is not True:
            raise PlacementControlError("placement watchdog must be independent")
        if contract.get("maximum_deadline_seconds") != 300:
            raise PlacementControlError("placement watchdog deadline must be 300 seconds")
        self.log_path = self._campaign_path(contract.get("watchdog_log_path"))
        self.cancel_path = self._campaign_path(contract.get("watchdog_cancel_path"))
        if self.log_path == self.cancel_path:
            raise PlacementControlError("placement watchdog paths must be distinct")
        self.process = None
        self.absolute_deadline_utc = None

    @staticmethod
    def _campaign_path(relative_name):
        if not isinstance(relative_name, str) or not relative_name:
            raise PlacementControlError("placement watchdog path is missing")
        relative = Path(relative_name)
        if relative.is_absolute() or ".." in relative.parts:
            raise PlacementControlError("placement watchdog path escapes campaign")
        path = (CAMPAIGN / relative).resolve()
        if CAMPAIGN.resolve() not in path.parents:
            raise PlacementControlError("placement watchdog path escapes campaign")
        return path

    def start(self, pod_id):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.cancel_path.parent.mkdir(parents=True, exist_ok=True)
        self.cancel_path.unlink(missing_ok=True)
        deadline = time.time() + 300
        self.absolute_deadline_utc = datetime.datetime.fromtimestamp(
            deadline, datetime.timezone.utc
        ).isoformat().replace("+00:00", "Z")
        self.process = subprocess.Popen(
            [
                sys.executable,
                str(EXPERIMENT / "runpod_watchdog.py"),
                pod_id,
                str(deadline),
                str(self.cancel_path),
                str(self.log_path),
            ],
            start_new_session=True,
        )

    def cancel(self):
        self.cancel_path.touch()
        if self.process is not None:
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.terminate()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def hashed_error(error):
    payload = f"{type(error).__name__}:{error}".encode()
    return {"type": type(error).__name__, "sha256": hashlib.sha256(payload).hexdigest()}


def build_placement_request(preregistration):
    provider_request = preregistration.get("provider_request")
    if not isinstance(provider_request, dict):
        raise PlacementControlError("preregistration has no provider request")
    expected = {
        "cloud_class": "SECURE",
        "gpu_type_id": GPU_TYPE,
        "gpu_count": 1,
        "data_center_ids": [DATA_CENTER],
        "allowed_cuda_versions": CUDA_VERSIONS,
        "interruptible": False,
    }
    for key, value in expected.items():
        if provider_request.get(key) != value:
            raise PlacementControlError(f"placement contract mismatch: {key}")
    graphql_input = {
        "cloudType": "SECURE",
        "computeType": "GPU",
        "gpuCount": 1,
        "gpuTypeId": GPU_TYPE,
        "dataCenterId": DATA_CENTER,
        "allowedCudaVersions": CUDA_VERSIONS,
        "containerDiskInGb": CONTAINER_DISK_GB,
        "volumeInGb": VOLUME_GB,
        "imageName": IMAGE,
        "name": NAME,
    }
    return {
        "api_surface": GRAPHQL_CREATE_SURFACE,
        "query": GRAPHQL_CREATE_MUTATION,
        "variables": {"input": graphql_input},
    }


def safe_provider_row(row):
    allowed = (
        "id",
        "costPerHr",
        "createdAt",
        "desiredStatus",
        "imageName",
        "machineId",
        "gpuCount",
        "ports",
    )
    return {key: row.get(key) for key in allowed if key in row}


def run_control(
    preregistration,
    output_path,
    *,
    provider,
    watchdog_factory=PlacementWatchdog,
    monotonic=time.monotonic,
    sleep=time.sleep,
):
    if os.environ.get("CAMPAIGN_100_COORDINATOR") != "1":
        raise PlacementControlError("campaign coordinator environment is required")
    request = build_placement_request(preregistration)
    try:
        hourly_price_ceiling = Decimal(
            str(preregistration["provider_request"]["admission_hourly_price_ceiling_usd"])
        )
    except (KeyError, InvalidOperation, ValueError):
        raise PlacementControlError("placement hourly price ceiling is invalid") from None
    if not hourly_price_ceiling.is_finite() or hourly_price_ceiling <= 0:
        raise PlacementControlError("placement hourly price ceiling is invalid")
    watchdog_contract = preregistration.get("placement_control_watchdog")
    if not isinstance(watchdog_contract, dict):
        raise PlacementControlError("placement watchdog contract is missing")
    watchdog = watchdog_factory(watchdog_contract)
    output_path = Path(output_path)
    started = monotonic()
    result = {
        "schema_version": 1,
        "experiment_id": preregistration.get("experiment_id"),
        "control": "graphql_h100_placement_only",
        "started_at": utc_now(),
        "request_sha256": hashlib.sha256(canonical(request)).hexdigest(),
        "provider_response": None,
        "provider_state": None,
        "pod_id": None,
        "hourly_rate_usd": None,
        "hourly_price_ceiling_usd": float(hourly_price_ceiling),
        "delete_http_status": None,
        "teardown_verification": "not_created",
        "error": None,
        "cleanup_error": None,
        "watchdog": {
            "maximum_deadline_seconds": watchdog_contract.get("maximum_deadline_seconds"),
            "watchdog_log_path": watchdog_contract.get("watchdog_log_path"),
            "watchdog_cancel_path": watchdog_contract.get("watchdog_cancel_path"),
            "started": False,
            "cancelled_after_404": False,
            "absolute_deadline_utc": None,
        },
    }
    pod_id = None
    hourly_rate = None
    primary_error = None
    try:
        created = provider.create(request)
        pod_id = created.get("id")
        if not pod_id:
            raise PlacementControlError("provider response omitted pod id")
        result["pod_id"] = pod_id
        result["teardown_verification"] = "pending"
        watchdog.start(pod_id)
        result["watchdog"]["started"] = True
        result["watchdog"]["absolute_deadline_utc"] = getattr(
            watchdog, "absolute_deadline_utc", None
        )
        result["provider_response"] = safe_provider_row(created)
        try:
            hourly_rate_decimal = Decimal(str(created.get("costPerHr")))
        except (InvalidOperation, ValueError):
            raise PlacementControlError("provider response omitted hourly rate") from None
        if not hourly_rate_decimal.is_finite() or hourly_rate_decimal <= 0:
            raise PlacementControlError("provider response returned invalid hourly rate")
        hourly_rate = float(hourly_rate_decimal)
        result["hourly_rate_usd"] = hourly_rate
        if hourly_rate_decimal > hourly_price_ceiling:
            raise PlacementControlError("provider hourly rate exceeds preregistered ceiling")
        result["provider_state"] = safe_provider_row(provider.get(pod_id))
    except Exception as error:
        primary_error = error
    finally:
        if pod_id:
            try:
                result["delete_http_status"] = provider.delete(pod_id)
            except Exception as error:
                result["cleanup_error"] = hashed_error(error)
            for _ in range(60):
                try:
                    provider.get(pod_id)
                except ProviderNotFound:
                    result["teardown_verification"] = "http_404"
                    break
                except Exception as error:
                    if result["cleanup_error"] is None:
                        result["cleanup_error"] = hashed_error(error)
                    break
                sleep(2)
            if result["teardown_verification"] != "http_404" and result["cleanup_error"] is None:
                result["cleanup_error"] = hashed_error(
                    PlacementControlError("pod deletion did not reach HTTP 404")
                )
            if result["teardown_verification"] == "http_404" and result["watchdog"]["started"]:
                try:
                    watchdog.cancel()
                    result["watchdog"]["cancelled_after_404"] = True
                except Exception as error:
                    if result["cleanup_error"] is None:
                        result["cleanup_error"] = hashed_error(error)
        ended = monotonic()
        result["finished_at"] = utc_now()
        result["allocation_seconds"] = max(0.0, ended - started)
        if hourly_rate is not None:
            result["conservative_allocation_exposure_usd"] = (
                hourly_rate * result["allocation_seconds"] / 3600
            )
        else:
            result["conservative_allocation_exposure_usd"] = None
        if primary_error is not None:
            result["error"] = hashed_error(primary_error)
        result["success"] = (
            result["error"] is None
            and result["cleanup_error"] is None
            and result["delete_http_status"] == 204
            and result["teardown_verification"] == "http_404"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    preregistration = json.loads(arguments.preregistration.read_text())
    provider = RunPodProvider(
        event_log=arguments.output.parent / "provider-events.jsonl",
        deadline_epoch=time.time() + 300,
        startup_timeout_seconds=60,
    )
    result = run_control(
        preregistration,
        arguments.output,
        provider=provider,
    )
    print(json.dumps({
        "pod_id": result["pod_id"],
        "delete_http_status": result["delete_http_status"],
        "teardown_verification": result["teardown_verification"],
        "allocation_seconds": result["allocation_seconds"],
        "conservative_allocation_exposure_usd": result["conservative_allocation_exposure_usd"],
        "success": result["success"],
    }, indent=2))
    return int(not result["success"])


if __name__ == "__main__":
    raise SystemExit(main())
