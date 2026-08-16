import base64
import datetime
import gzip
import hashlib
import json
import os
import pathlib
import subprocess
import tarfile
import time
import urllib.error
import urllib.request

from runpod_rest import RunPodHttpError, request_json, validate_openapi_object


ROOT = pathlib.Path("/root/workspace/research/lab/experiments/glm47flash")
LEDGER = ROOT / "ledger.jsonl"
IMAGE = "lmsysorg/sglang:v0.5.15-cu130@sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af"
PHASE_CAP_USD = 2.0
PHASE_PRIOR_SPEND_USD = 0.42338672628037477
STARTUP_SECONDS = 300
ALLOCATION_SECONDS = 2400
ATTEMPT_NUMBER = 4
ATTEMPT = "phase3_attempt4_secure_l40s_kvb_extended_load_smoke"
GPU_TYPE_IDS = ["NVIDIA L40S"]


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def api(path, method="GET", payload=None, timeout=60):
    return request_json(
        "https://rest.runpod.io/v1",
        os.environ["RUNPOD_API_KEY"],
        path,
        method=method,
        payload=payload,
        timeout=timeout,
    )


def payload_audit(payload):
    with urllib.request.urlopen(
        "https://rest.runpod.io/v1/openapi.json", timeout=60
    ) as response:
        openapi_bytes = response.read()
    openapi = json.loads(openapi_bytes)
    schema = openapi["components"]["schemas"]["PodCreateInput"]
    errors = validate_openapi_object(payload, schema)
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    env_summary = {}
    for key, value in payload.get("env", {}).items():
        transport = base64.b64decode(value)
        source = gzip.decompress(transport) if key.endswith("_GZ_B64") else transport
        env_summary[key] = {
            "encoded_bytes": len(value),
            "transport_sha256": hashlib.sha256(transport).hexdigest(),
            "source_bytes": len(source),
            "source_sha256": hashlib.sha256(source).hexdigest(),
        }
    summary = {
        "openapi_url": "https://rest.runpod.io/v1/openapi.json",
        "openapi_sha256": hashlib.sha256(openapi_bytes).hexdigest(),
        "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "payload_bytes": len(payload_bytes),
        "schema_errors": errors,
        "payload": {
            key: value for key, value in payload.items() if key != "env"
        },
        "env": env_summary,
    }
    return summary


def append_ledger(row):
    with LEDGER.open("a") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def fetch(url, path):
    with urllib.request.urlopen(url, timeout=180) as response, path.open("wb") as handle:
        while chunk := response.read(8 * 1024 * 1024):
            handle.write(chunk)


def provider_active(pods):
    return [
        {
            "id": pod.get("id"),
            "name": pod.get("name"),
            "status": pod.get("desiredStatus"),
        }
        for pod in pods
        if pod.get("desiredStatus") in {"RUNNING", "CREATED", "RESTARTING"}
    ]


def main():
    started = time.monotonic()
    pod_id = None
    record = {
        "attempt": ATTEMPT,
        "started_at": utc(),
        "phase_cap_usd": PHASE_CAP_USD,
        "phase_prior_spend_usd": PHASE_PRIOR_SPEND_USD,
        "prior_campaign_spend_usd": 4.112385662812516,
        "image": IMAGE,
        "runtime_source_commit": "f63458b5beaceabbd9d749b9fc956370e1b649e6",
        "model": "cyankiwi/GLM-4.7-Flash-AWQ-4bit",
        "model_revision": "ab31d120fbe79988fe2a0259993cf3c222aa8881",
        "intervention": "four-part fused MLA loader patch with canonical kv_b W4A16 dequantization",
        "gpu_role": "single exact Ada 48GB path",
        "gpu_type_ids": GPU_TYPE_IDS,
        "events": [],
    }
    try:
        _, pods = api("/pods")
        active = provider_active(pods)
        record["pre_mutation_active_pods"] = active
        if active:
            raise RuntimeError("active pods prevent mutation: " + json.dumps(active))
        if PHASE_PRIOR_SPEND_USD >= PHASE_CAP_USD:
            raise RuntimeError("phase spend cap exhausted")
        command = (
            "export CAMPAIGN_DEADLINE_EPOCH=$(( $(date +%s)+2100 )); "
            "printf %s \"$SCRIPT_GZ_B64\" | base64 -d | gzip -d > /tmp/run.sh; "
            "chmod +x /tmp/run.sh; "
            "timeout --signal=TERM 2200 /tmp/run.sh"
        )
        payload = {
            "name": "glm47flash-phase3-secure-l40s-kvb-load-smoke-20260713",
            "imageName": IMAGE,
            "computeType": "GPU",
            "gpuTypeIds": GPU_TYPE_IDS,
            "gpuTypePriority": "availability",
            "gpuCount": 1,
            "cloudType": "SECURE",
            "allowedCudaVersions": ["13.0"],
            "supportPublicIp": True,
            "containerDiskInGb": 30,
            "volumeInGb": 50,
            "volumeMountPath": "/workspace",
            "ports": ["8000/tcp"],
            "dockerEntrypoint": ["/bin/bash", "-lc"],
            "dockerStartCmd": [command],
            "env": {
                "SCRIPT_GZ_B64": base64.b64encode(
                    gzip.compress(
                        (ROOT / "phase2_awq_smoke.sh").read_bytes(), mtime=0
                    )
                ).decode(),
                "PATCHER_GZ_B64": base64.b64encode(
                    gzip.compress(
                        (ROOT / "patch_sglang_awq_loader.py").read_bytes(), mtime=0
                    )
                ).decode(),
            },
        }
        audit = payload_audit(payload)
        record["payload_audit"] = audit
        (ROOT / f"phase3-attempt{ATTEMPT_NUMBER}-payload-audit.json").write_text(
            json.dumps(audit, indent=2) + "\n"
        )
        if audit["schema_errors"]:
            raise RuntimeError("payload schema errors: " + json.dumps(audit["schema_errors"]))
        _, pod = api("/pods", "POST", payload, 120)
        pod_id = pod["id"]
        rate = float(pod.get("costPerHr", 0.33))
        maximum_cost = rate * ALLOCATION_SECONDS / 3600
        if PHASE_PRIOR_SPEND_USD + maximum_cost > PHASE_CAP_USD:
            raise RuntimeError("allocation deadline could exceed phase cap")
        record.update(
            {
                "pod_id": pod_id,
                "hourly_rate_usd": rate,
                "provider_created_at": pod.get("createdAt"),
                "maximum_deadline_cost_usd": maximum_cost,
            }
        )
        record["events"].append({"at": utc(), "event": "pod_created"})
        append_ledger({"timestamp": utc(), "event": "pod_created", **record})
        cancel = ROOT / f".watchdog-{pod_id}.cancel"
        cancel.unlink(missing_ok=True)
        subprocess.Popen(
            [
                "python3",
                str(ROOT / "runpod_watchdog.py"),
                pod_id,
                str(time.time() + ALLOCATION_SECONDS),
                str(cancel),
                str(ROOT / f"phase3-attempt{ATTEMPT_NUMBER}-watchdog.jsonl"),
            ],
            start_new_session=True,
        )
        endpoint = None
        startup_deadline = time.monotonic() + STARTUP_SECONDS
        while time.monotonic() < startup_deadline:
            _, state = api("/pods/" + pod_id, timeout=30)
            status = state.get("desiredStatus")
            if status not in {"RUNNING", "CREATED", "RESTARTING"}:
                raise RuntimeError("provider terminal state during startup: " + str(status))
            mappings = state.get("portMappings") or {}
            port = mappings.get("8000") or mappings.get(8000)
            if state.get("publicIp") and port:
                endpoint = f"http://{state['publicIp']}:{port}"
                record["events"].append({"at": utc(), "event": "artifact_endpoint_ready"})
                break
            time.sleep(5)
        if endpoint is None:
            raise TimeoutError("five-minute startup deadline exceeded")
        terminal = None
        experiment_deadline = time.monotonic() + ALLOCATION_SECONDS - STARTUP_SECONDS
        while time.monotonic() < experiment_deadline:
            try:
                with urllib.request.urlopen(endpoint + "/STATUS", timeout=10) as response:
                    status_text = response.read().decode().strip()
                if status_text in {"READY", "FAILED"}:
                    terminal = status_text
                    break
            except (urllib.error.URLError, TimeoutError):
                pass
            _, state = api("/pods/" + pod_id, timeout=30)
            status = state.get("desiredStatus")
            if status not in {"RUNNING", "CREATED", "RESTARTING"}:
                raise RuntimeError("provider terminal state before artifact: " + str(status))
            time.sleep(10)
        if terminal not in {"READY", "FAILED"}:
            raise TimeoutError("experiment deadline exceeded")
        artifact = ROOT / f"phase3-attempt{ATTEMPT_NUMBER}-awq-smoke.tar.gz"
        checksum = ROOT / f"phase3-attempt{ATTEMPT_NUMBER}-awq-smoke.tar.gz.sha256.remote"
        fetch(endpoint + "/phase2-awq-smoke.tar.gz", artifact)
        fetch(endpoint + "/phase2-awq-smoke.tar.gz.sha256", checksum)
        local_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
        remote_hash = checksum.read_text().split()[0]
        if local_hash != remote_hash:
            raise ValueError("artifact checksum mismatch")
        record.update(
            {
                "terminal_status": terminal,
                "artifact": {
                    "path": str(artifact),
                    "bytes": artifact.stat().st_size,
                    "sha256": local_hash,
                },
            }
        )
        record["events"].append(
            {"at": utc(), "event": "artifact_verified", "terminal_status": terminal}
        )
        with tarfile.open(artifact, "r:gz") as archive:
            names = set(archive.getnames())
            determinism_name = "phase2-awq-smoke/determinism.json"
            screen_name = "phase2-awq-smoke/throughput-screen.json"
            if determinism_name in names:
                record["determinism"] = json.load(archive.extractfile(determinism_name))
            if screen_name in names:
                screen = json.load(archive.extractfile(screen_name))
                output_rate = screen["output_tokens_per_second"]
                cost_per_million = rate / 3600 / output_rate * 1_000_000
                parity_rate = rate / 3600 * 1_000_000 / 0.88
                record["economics_screen"] = {
                    "measurement": screen,
                    "hourly_rate_usd": rate,
                    "required_output_tokens_per_second_for_0_88": parity_rate,
                    "cost_per_million_output_equivalent_usd": cost_per_million,
                    "promising_against_0_88": cost_per_million <= 0.88,
                    "scope": "4K-context 3072/384 c8 screen; not matched 8192/1024 evidence",
                }
        if terminal == "FAILED":
            record["error"] = "remote harness reported FAILED"
    except Exception as error:
        if isinstance(error, RunPodHttpError):
            record["http_error"] = error.details
        record["error"] = repr(error)
        record["events"].append(
            {"at": utc(), "event": "attempt_failed", "error": repr(error)}
        )
    finally:
        delete_status = None
        verification = "not_created"
        if pod_id:
            try:
                delete_status, _ = api("/pods/" + pod_id, "DELETE", timeout=30)
            except RunPodHttpError as error:
                delete_status = error.details["status"]
                record["delete_http_error"] = error.details
            for _ in range(6):
                try:
                    api("/pods/" + pod_id, timeout=30)
                    verification = "present"
                except RunPodHttpError as error:
                    verification = f"http_{error.details['status']}"
                    if error.details["status"] == 404:
                        break
                time.sleep(2)
            (ROOT / f".watchdog-{pod_id}.cancel").touch()
        elapsed = time.monotonic() - started
        spend = elapsed * float(record.get("hourly_rate_usd", 0)) / 3600
        record.update(
            {
                "finished_at": utc(),
                "allocation_seconds": elapsed,
                "conservative_spend_usd": spend,
                "phase_cumulative_spend_usd": PHASE_PRIOR_SPEND_USD + spend,
                "teardown": {
                    "delete_http_status": delete_status,
                    "verification": verification,
                },
            }
        )
        (ROOT / f"phase3-attempt{ATTEMPT_NUMBER}-orchestrator.json").write_text(
            json.dumps(record, indent=2) + "\n"
        )
        append_ledger({"timestamp": utc(), "event": "attempt_finished", **record})
        print(json.dumps(record, indent=2), flush=True)
    return 0 if record.get("terminal_status") == "READY" and record["teardown"]["verification"] == "http_404" else 1


if __name__ == "__main__":
    raise SystemExit(main())
