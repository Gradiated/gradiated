#!/usr/bin/env python3
import argparse
import base64
import datetime
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parent
CAMPAIGN = HERE.parent
EXPERIMENT = CAMPAIGN.parent
IMAGE = "lmsysorg/sglang:v0.5.15-cu130@sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af"
GPU_TYPE = "NVIDIA A100 80GB PCIe"
ACTIVE = {"RUNNING", "CREATED", "RESTARTING"}

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(CAMPAIGN / "specs"))
from orchestrator import PhaseBOrchestrator, ProviderNotFound  # noqa: E402
from validate_contracts import admit_budget, validate_watchdog  # noqa: E402


class RunPodError(RuntimeError):
    pass


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_path(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text())


def safe_provider_error_body(raw_body):
    try:
        decoded = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(decoded, dict):
        return None
    allowed = {}
    for key in ("error", "status", "message", "code", "requestId", "request_id"):
        value = decoded.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None and key in decoded:
            allowed[key] = value
    return allowed or None


def frozen_archive_b64(directory):
    directory = Path(directory)
    manifest = load_json(directory / "FROZEN_MANIFEST.json")
    names = ["FROZEN_MANIFEST.json", *sorted(manifest["files"])]
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz", compresslevel=9) as archive:
        for name in names:
            path = directory / name
            if not path.is_file():
                raise RunPodError(f"frozen archive member is missing: {path}")
            info = archive.gettarinfo(str(path), arcname=name)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            with path.open("rb") as handle:
                archive.addfile(info, handle)
    return base64.b64encode(output.getvalue()).decode()


def build_request(preregistration, experiment_spec_sha256, deadline_epoch):
    remote_seconds = preregistration["timeouts"]["remote_command_seconds"]
    provider_request = preregistration["provider_request"]
    script_b64 = base64.b64encode((HERE / "remote_baseline.sh").read_bytes()).decode()
    command = (
        'printf %s "$SCRIPT_B64" | base64 -d > /tmp/campaign-100-phase-b.sh; '
        "chmod 700 /tmp/campaign-100-phase-b.sh; "
        f"timeout --signal=TERM --kill-after=120 {remote_seconds} /tmp/campaign-100-phase-b.sh"
    )
    request = {
        "name": provider_request["name"],
        "imageName": IMAGE,
        "computeType": "GPU",
        "gpuTypeIds": [provider_request.get("gpu_type_id", GPU_TYPE)],
        "gpuTypePriority": "availability",
        "gpuCount": 1,
        "cloudType": provider_request["cloud_class"],
        "containerDiskInGb": 40,
        "volumeInGb": 100,
        "volumeMountPath": "/workspace",
        "ports": ["8000/tcp"],
        "dockerEntrypoint": ["/bin/bash", "-lc"],
        "dockerStartCmd": [command],
        "env": {
            "SCRIPT_B64": script_b64,
            "WORKLOAD_ARCHIVE_B64": frozen_archive_b64(CAMPAIGN / "workloads"),
            "QUALITY_ARCHIVE_B64": frozen_archive_b64(CAMPAIGN / "quality"),
            "EXPERIMENT_SPEC_SHA256": experiment_spec_sha256,
            "CAMPAIGN_DEADLINE_EPOCH": str(deadline_epoch),
        },
    }
    optional_provider_fields = {
        "allowed_cuda_versions": "allowedCudaVersions",
        "data_center_ids": "dataCenterIds",
        "data_center_priority": "dataCenterPriority",
        "interruptible": "interruptible",
        "support_public_ip": "supportPublicIp",
    }
    for source, destination in optional_provider_fields.items():
        if source in provider_request:
            request[destination] = provider_request[source]
    return request


class RunPodProvider:
    def __init__(self, *, event_log, deadline_epoch, startup_timeout_seconds):
        self.event_log = Path(event_log)
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
        self.deadline_epoch = deadline_epoch
        self.startup_timeout_seconds = startup_timeout_seconds
        self.last_pod_id = None
        self.created_monotonic = None
        self.created_at = None
        self.hourly_rate = None
        self.last_state = None
        self.harvest_record = None
        self.delete_record = None

    def _emit(self, event, **fields):
        row = {"timestamp": utc_now(), "event": event, **fields}
        with self.event_log.open("a") as handle:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    def _api(self, path, method="GET", payload=None, timeout=60):
        headers = {"Authorization": "Bearer " + os.environ["RUNPOD_API_KEY"]}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, separators=(",", ":")).encode()
        request = urllib.request.Request(
            "https://rest.runpod.io/v1" + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                return response.status, json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            raw_body = error.read(64 * 1024)
            safe_headers = {}
            for name in ("content-type", "content-length", "date", "x-request-id", "request-id"):
                value = error.headers.get(name) if error.headers is not None else None
                if value is not None:
                    safe_headers[name] = value
            self._emit(
                "provider_http_error",
                method=method,
                path=path,
                http_status=error.code,
                response_headers=safe_headers,
                response_body_bytes=len(raw_body),
                response_body_sha256=hashlib.sha256(raw_body).hexdigest(),
                safe_response_body=safe_provider_error_body(raw_body),
            )
            if path.startswith("/pods/") and error.code == 404:
                if method == "GET":
                    raise ProviderNotFound(path) from None
                if method == "DELETE":
                    return 404, None
            raise RunPodError(f"RunPod {method} {path} failed with HTTP {error.code}") from None

    def inventory(self):
        status, rows = self._api("/pods")
        active = [row.get("id") for row in rows if row.get("desiredStatus", row.get("status")) in ACTIVE]
        self._emit("inventory", http_status=status, count=len(rows), active_ids=active)
        return rows

    def create(self, request):
        self.created_monotonic = time.monotonic()
        status, row = self._api("/pods", "POST", request, timeout=120)
        self.last_pod_id = row.get("id")
        self.created_at = row.get("createdAt") or utc_now()
        self.hourly_rate = float(row.get("costPerHr", 0))
        self._emit(
            "pod_created",
            http_status=status,
            pod_id=self.last_pod_id,
            hourly_rate_usd=self.hourly_rate,
            provider_created_at=self.created_at,
        )
        return row

    def get(self, pod_id):
        status, row = self._api("/pods/" + pod_id, timeout=30)
        self.last_state = row
        self._emit(
            "pod_get",
            http_status=status,
            pod_id=pod_id,
            desired_status=row.get("desiredStatus", row.get("status")),
            machine_id=row.get("machineId"),
        )
        return row

    @staticmethod
    def _endpoint(row):
        mappings = row.get("portMappings") or {}
        public_port = mappings.get("8000", mappings.get(8000))
        if isinstance(public_port, dict):
            public_port = public_port.get("publicPort")
        if row.get("publicIp") and public_port:
            return f"http://{row['publicIp']}:{public_port}"
        return None

    @staticmethod
    def _read_url(url, timeout=20):
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()

    @classmethod
    def _fetch(cls, url, destination):
        destination = Path(destination)
        with urllib.request.urlopen(url, timeout=240) as response, destination.open("wb") as handle:
            while True:
                chunk = response.read(8 * 1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)

    def harvest(self, pod_id, destination):
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        endpoint = None
        placement_deadline = min(time.time() + self.startup_timeout_seconds, self.deadline_epoch)
        while time.time() < placement_deadline:
            row = self.get(pod_id)
            state = row.get("desiredStatus", row.get("status"))
            if state not in ACTIVE:
                raise RunPodError(f"pod entered terminal provider state: {state}")
            endpoint = self._endpoint(row)
            if endpoint:
                try:
                    self._read_url(endpoint + "/STATUS", timeout=5)
                    break
                except (urllib.error.URLError, TimeoutError):
                    endpoint = None
            time.sleep(5)
        if endpoint is None:
            raise RunPodError("artifact endpoint missed the preregistered startup deadline")
        self._emit("artifact_endpoint_ready", pod_id=pod_id)

        terminal = None
        while time.time() < self.deadline_epoch:
            try:
                terminal = self._read_url(endpoint + "/STATUS", timeout=10).decode().strip()
                if terminal in {"READY", "FAILED"}:
                    break
            except (urllib.error.URLError, TimeoutError):
                pass
            self.get(pod_id)
            time.sleep(10)
        if terminal not in {"READY", "FAILED"}:
            raise RunPodError("remote experiment missed the absolute harvest deadline")

        archive = destination / "phase-b-control.tar.gz"
        sidecar = destination / "phase-b-control.tar.gz.sha256.remote"
        self._fetch(endpoint + "/phase-b-control.tar.gz", archive)
        self._fetch(endpoint + "/phase-b-control.tar.gz.sha256", sidecar)
        local_hash = sha256_path(archive)
        remote_hash = sidecar.read_text().split()[0]
        if local_hash != remote_hash:
            raise RunPodError("retrieved artifact hash differs from remote sidecar")
        exit_code = self._read_url(endpoint + "/EXIT_CODE", timeout=20).decode().strip()
        self.harvest_record = {
            "terminal_status": terminal,
            "remote_exit_code": exit_code,
            "artifact_path": str(archive),
            "artifact_bytes": archive.stat().st_size,
            "artifact_sha256": local_hash,
        }
        (destination / "harvest.json").write_text(json.dumps(self.harvest_record, indent=2) + "\n")
        self._emit("artifact_verified", pod_id=pod_id, **self.harvest_record)

    def delete(self, pod_id):
        requested_at = utc_now()
        try:
            status, _ = self._api("/pods/" + pod_id, "DELETE", timeout=30)
        except ProviderNotFound:
            status = 404
        self.delete_record = {"delete_requested_at": requested_at, "delete_http_status": status}
        self._emit("pod_delete", pod_id=pod_id, **self.delete_record)
        return status


class IndependentWatchdog:
    def __init__(self, contract):
        self.contract = contract
        self.process = None
        self.cancel_path = None

    def start(self, pod_id):
        log_path = CAMPAIGN / self.contract["watchdog_log_path"]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.cancel_path = log_path.with_suffix(log_path.suffix + ".cancel")
        self.cancel_path.unlink(missing_ok=True)
        deadline = datetime.datetime.fromisoformat(
            self.contract["absolute_deadline_utc"].replace("Z", "+00:00")
        ).timestamp()
        self.process = subprocess.Popen(
            [
                sys.executable,
                str(EXPERIMENT / "runpod_watchdog.py"),
                pod_id,
                str(deadline),
                str(self.cancel_path),
                str(log_path),
            ],
            start_new_session=True,
        )

    def cancel(self):
        if self.cancel_path is not None:
            self.cancel_path.touch()
        if self.process is not None:
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.terminate()


def preflight(paths):
    preregistration = load_json(paths.preregistration)
    admission = load_json(paths.admission)
    watchdog = load_json(paths.watchdog)
    gate = load_json(paths.gate)
    if gate.get("gate") != "A" or gate.get("status") != "passed":
        raise RunPodError("Gate A is not signed")
    if sha256_path(paths.gate) != preregistration["gate_a_manifest_sha256"]:
        raise RunPodError("preregistration does not bind the current Gate A manifest")
    validate_watchdog(watchdog)
    decision = admit_budget(
        admission,
        baseline_path=paths.baseline,
        inventory_snapshot_path=paths.inventory,
        watchdog_contract_path=paths.watchdog,
    )
    deadline = datetime.datetime.fromisoformat(
        watchdog["absolute_deadline_utc"].replace("Z", "+00:00")
    ).timestamp()
    if deadline <= time.time():
        raise RunPodError("watchdog deadline is already in the past")
    request = build_request(preregistration, sha256_path(paths.preregistration), int(deadline))
    return preregistration, admission, watchdog, request, decision, deadline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--admission", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--watchdog", required=True, type=Path)
    parser.add_argument("--gate", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--preflight", action="store_true")
    arguments = parser.parse_args()
    preregistration, admission, watchdog, request, decision, deadline = preflight(arguments)
    if arguments.preflight:
        safe_request = {key: value for key, value in request.items() if key != "env"}
        print(json.dumps({"preflight": "pass", "budget": decision, "request": safe_request}, indent=2))
        return 0
    if os.environ.get("CAMPAIGN_100_COORDINATOR") != "1":
        raise RunPodError("CAMPAIGN_100_COORDINATOR=1 is required for mutation")

    arguments.destination.mkdir(parents=True, exist_ok=True)
    provider = RunPodProvider(
        event_log=arguments.destination / "provider-events.jsonl",
        deadline_epoch=deadline,
        startup_timeout_seconds=preregistration["timeouts"]["provider_startup_seconds"],
    )
    orchestrator = PhaseBOrchestrator(
        provider=provider,
        baseline_path=arguments.baseline,
        inventory_snapshot_path=arguments.inventory,
        watchdog_contract_path=arguments.watchdog,
        gate_a_manifest_path=arguments.gate,
        expected_gate_a_manifest_sha256=preregistration["gate_a_manifest_sha256"],
        watchdog_factory=IndependentWatchdog,
    )
    started_at = utc_now()
    started_monotonic = time.monotonic()
    result = {"started_at": started_at, "experiment_spec_sha256": sha256_path(arguments.preregistration)}
    exit_code = 1
    try:
        orchestration = orchestrator.run(request, admission, watchdog, arguments.destination)
        result.update(orchestration)
        exit_code = int(
            orchestration["harvest_status"] != "complete"
            or orchestration["delete_http_status"] != 204
            or orchestration["teardown_verification"] != "http_404"
            or not provider.harvest_record
            or provider.harvest_record["terminal_status"] != "READY"
            or provider.harvest_record["remote_exit_code"] != "0"
        )
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    result.update(
        {
            "finished_at": utc_now(),
            "allocation_seconds": time.monotonic() - started_monotonic,
            "pod_id": provider.last_pod_id,
            "hourly_rate_usd": provider.hourly_rate,
            "provider_created_at": provider.created_at,
            "last_state": provider.last_state,
            "harvest": provider.harvest_record,
            "delete": provider.delete_record,
            "exit_code": exit_code,
        }
    )
    (arguments.destination / "orchestration-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "pod_id": result.get("pod_id"),
                "harvest_status": result.get("harvest_status"),
                "delete_http_status": result.get("delete_http_status"),
                "teardown_verification": result.get("teardown_verification"),
                "allocation_seconds": result["allocation_seconds"],
                "exit_code": exit_code,
                "error": result.get("error"),
            },
            indent=2,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
