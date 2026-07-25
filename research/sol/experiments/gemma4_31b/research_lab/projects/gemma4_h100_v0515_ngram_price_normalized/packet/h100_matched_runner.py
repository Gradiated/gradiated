#!/usr/bin/env python3
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import threading
import time
import urllib.request
from pathlib import Path


ROOT = Path(os.environ["UPSTREAM_REBASE_ROOT"])
OUT = Path(os.environ.get("UPSTREAM_REBASE_OUT", str(ROOT / "out")))
INPUT = ROOT / "inputs"
MODEL = "google/gemma-4-31B-it"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd"
)
COMMIT = "f63458b5beaceabbd9d749b9fc956370e1b649e6"
CONTAINER = os.environ.get("UPSTREAM_REBASE_CONTAINER", "gemma4-ngram-upstream-v0515")
REQUESTS = int(os.environ.get("UPSTREAM_REBASE_REQUESTS", "171"))
H100_PLANNING_USD_PER_GPU_HOUR = 2.8
TARGET_USD_PER_MILLION_TOTAL_TOKENS = 0.14
SUSTAINABLE_UTILIZATION = 0.90
MIN_FULL_POOL_TOKENS = 82512
MIN_SWA_POOL_TOKENS = 18648
MIN_POST_GRAPH_AVAILABLE_GIB = 8.0


def atomic(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    part.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get(url, timeout=10):
    return urllib.request.urlopen(url, timeout=timeout).read()


def post(body):
    payload = {
        "input_ids": body["prompt"],
        "sampling_params": {
            "temperature": 0,
            "max_new_tokens": body["max_tokens"],
            "min_new_tokens": body["min_tokens"],
            "ignore_eos": body["ignore_eos"],
        },
    }
    request = urllib.request.Request(
        "http://127.0.0.1:30000/generate",
        json.dumps(payload, separators=(",", ":")).encode(),
        {"Content-Type": "application/json"},
    )
    began = time.monotonic()
    with urllib.request.urlopen(request, timeout=1200) as reply:
        parsed = json.loads(reply.read())
    meta = parsed.get("meta_info") or {}
    usage = {
        "prompt_tokens": meta.get("prompt_tokens", len(body["prompt"])),
        "completion_tokens": meta.get("completion_tokens", body["max_tokens"]),
    }
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return {
        "usage": usage,
        "output_ids": (
            parsed.get("output_ids")
            or meta.get("output_ids")
            or meta.get("completion_token_ids")
        ),
        "finish_reason": meta.get("finish_reason") or parsed.get("finish_reason"),
        "latency_seconds": time.monotonic() - began,
    }


def request_body(template, index):
    value = dict(template["request_body"])
    value.update(
        {
            "model": MODEL,
            "ignore_eos": True,
            "min_tokens": 358,
            "max_tokens": 358,
            "request_id": f"tail-overlap-{index}",
        }
    )
    value["prompt"] = list(value["prompt"])
    value["prompt"][535] = 200000 + index
    return value


def metrics():
    raw = get("http://127.0.0.1:30000/metrics").decode()
    values = {}
    for line in raw.splitlines():
        if not line or line.startswith("#"):
            continue
        name = line.split("{", 1)[0]
        if name in {
            "sglang:num_queue_reqs",
            "sglang:num_running_reqs",
            "sglang:spec_accept_rate",
            "sglang:spec_accept_length",
        }:
            try:
                values[name] = float(line.rsplit(" ", 1)[1])
            except ValueError:
                pass
    return values


def wait_server():
    deadline = time.monotonic() + 720
    while time.monotonic() < deadline:
        try:
            payload = json.loads(get("http://127.0.0.1:30000/v1/models", 4))
            if MODEL in [row.get("id") for row in payload.get("data", [])]:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("server_not_ready")


def inspect_container(launch):
    result = subprocess.run(
        ["docker", "inspect", CONTAINER],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError("container_inspect_failed:" + result.stderr[-1000:])
    rows = json.loads(result.stdout)
    if len(rows) != 1:
        raise RuntimeError("container_inspect_cardinality")
    row = rows[0]
    labels = row.get("Config", {}).get("Labels") or {}
    configured_image = row.get("Config", {}).get("Image") or ""
    expected_digest = IMAGE.rsplit("@", 1)[1]
    actual_command = row.get("Config", {}).get("Cmd") or []
    expected_command = ["python3", "-m", "sglang.launch_server", *launch]
    identity = {
        "configured_image": configured_image,
        "container_image_id": row.get("Image"),
        "revision_label": labels.get("org.opencontainers.image.revision"),
        "entrypoint": row.get("Config", {}).get("Entrypoint"),
        "actual_command": actual_command,
        "expected_command": expected_command,
    }
    if expected_digest not in configured_image:
        raise RuntimeError("container_image_digest_mismatch:" + repr(identity))
    if identity["revision_label"] != COMMIT:
        raise RuntimeError("container_commit_label_mismatch:" + repr(identity))
    if actual_command != expected_command:
        raise RuntimeError("container_launch_argv_mismatch:" + repr(identity))
    return identity


def inspect_h100_fit():
    gpu = subprocess.run(
        [
            "docker",
            "exec",
            CONTAINER,
            "nvidia-smi",
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if gpu.returncode:
        raise RuntimeError("h100_identity_failed:" + gpu.stderr[-1000:])
    gpu_rows = [row.strip() for row in gpu.stdout.splitlines() if row.strip()]
    if len(gpu_rows) != 1:
        raise RuntimeError("h100_identity_cardinality:" + repr(gpu_rows))
    name, memory_mib = [value.strip() for value in gpu_rows[0].rsplit(",", 1)]
    if "H100" not in name or int(memory_mib) < 80000:
        raise RuntimeError("accelerator_not_h100_sxm_80gb:" + gpu_rows[0])

    logs = subprocess.run(
        ["docker", "logs", CONTAINER],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if logs.returncode:
        raise RuntimeError("container_logs_failed:" + logs.stderr[-1000:])
    text = logs.stdout + "\n" + logs.stderr
    patterns = {
        "full_pool_tokens": r"full_layer_tokens=(\d+)",
        "swa_pool_tokens": r"swa_layer_tokens=(\d+)",
        "post_graph_available_gib": (
            r"Capture cuda graph end\..*avail mem=([0-9.]+) GB"
        ),
        "weight_gib": r"Load weight end\..*mem usage=([0-9.]+) GB",
        "graph_gib": r"Capture cuda graph end\..*mem usage=([0-9.]+) GB",
    }
    fit = {"gpu_name": name, "gpu_memory_mib": int(memory_mib)}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match is None:
            raise RuntimeError("fit_log_field_missing:" + key)
        fit[key] = float(match.group(1))
    fit["full_pool_tokens"] = int(fit["full_pool_tokens"])
    fit["swa_pool_tokens"] = int(fit["swa_pool_tokens"])
    fit["gates"] = {
        "full_pool_tokens": fit["full_pool_tokens"] >= MIN_FULL_POOL_TOKENS,
        "swa_pool_tokens": fit["swa_pool_tokens"] >= MIN_SWA_POOL_TOKENS,
        "post_graph_available_gib": (
            fit["post_graph_available_gib"] >= MIN_POST_GRAPH_AVAILABLE_GIB
        ),
    }
    if not all(fit["gates"].values()):
        raise RuntimeError("h100_fit_gate_failed:" + repr(fit))
    return fit


def invoke(index, arrival, released, request, expected, origin):
    began = time.monotonic() - origin
    try:
        answer = post(request)
        semantic = {
            key: answer[key] for key in ("output_ids", "finish_reason", "usage")
        }
        expected_semantic = {
            key: expected["semantic"][key]
            for key in ("output_ids", "finish_reason", "usage")
        }
        mismatch_index = None
        if semantic["output_ids"] != expected_semantic["output_ids"]:
            pairs = zip(semantic["output_ids"], expected_semantic["output_ids"])
            mismatch_index = next(
                (
                    token_index
                    for token_index, (actual, bound) in enumerate(pairs)
                    if actual != bound
                ),
                min(len(semantic["output_ids"]), len(expected_semantic["output_ids"])),
            )
        return {
            "i": index,
            "arrival_s": arrival,
            "released_s": released,
            "client_started_s": began,
            "completed_s": time.monotonic() - origin,
            "request_sha256": hashlib.sha256(
                json.dumps(request, sort_keys=True).encode()
            ).hexdigest(),
            "semantic": semantic,
            "semantic_matches_bound": semantic == expected_semantic,
            "first_output_token_mismatch": mismatch_index,
            "server_seconds": answer["latency_seconds"],
        }
    except Exception as exc:
        return {
            "i": index,
            "arrival_s": arrival,
            "released_s": released,
            "client_started_s": began,
            "completed_s": time.monotonic() - origin,
            "error": repr(exc),
        }


def sample(stop, rows, origin):
    while not stop.wait(0.5):
        row = {"elapsed_s": time.monotonic() - origin}
        try:
            row["metrics"] = metrics()
        except Exception as exc:
            row["metrics_error"] = repr(exc)
        rows.append(row)


def main():
    atomic(
        "INVOCATION_STATE.json",
        {"science_started": False, "phase": "identity_and_input_verification"},
    )
    if REQUESTS not in (171, 791):
        raise RuntimeError("matched_packet_requires_171_or_791_requests")
    manifest = json.loads((INPUT / "INPUT_MANIFEST.json").read_text())
    for name, expected in manifest.items():
        if name == "support_two_terminal.json":
            continue
        if digest(INPUT / name) != expected:
            raise RuntimeError("input_hash_mismatch:" + name)
    runtime = json.loads((ROOT / "CANDIDATE_RUNTIME.json").read_text())
    candidate = runtime["candidate"]
    if candidate["commit"] != COMMIT or candidate["official_image"] != IMAGE:
        raise RuntimeError("candidate_identity_mismatch")
    controls = [
        json.loads(line)
        for line in (INPUT / "exact_semantic_rows.jsonl").read_text().splitlines()
    ][:REQUESTS]
    if [row["i"] for row in controls] != list(range(REQUESTS)):
        raise RuntimeError("bound_row_identity_mismatch")
    trace = json.loads((INPUT / "TRACE_PACKET.json").read_text())
    template = next(
        row for row in trace["primary_groups"] if row["name"] == "primary_c1"
    )["scored"][0]
    launch = json.loads((INPUT / "ngram-launch.json").read_text())["args"]
    if launch[launch.index("--speculative-algorithm") + 1] != "NGRAM":
        raise RuntimeError("launch_not_native_ngram")
    if "--speculative-ngram-external-corpus-path" in launch:
        raise RuntimeError("launch_uses_external_corpus")
    container_identity = inspect_container(launch)
    wait_server()
    fit_identity = inspect_h100_fit()
    atomic(
        "ACTIVATION_IDENTITY.json",
        {
            "container": CONTAINER,
            "candidate_image": IMAGE,
            "candidate_commit": COMMIT,
            "model": MODEL,
            "native_ngram": True,
            "depth": 12,
            "launch_args": launch,
            "container_identity": container_identity,
            "fit_identity": fit_identity,
        },
    )
    atomic(
        "INVOCATION_STATE.json",
        {
            "science_started": True,
            "phase": f"candidate_requests_0_through_{REQUESTS - 1}",
            "requests": REQUESTS,
        },
    )
    origin = time.monotonic()
    telemetry = []
    stop = threading.Event()
    thread = threading.Thread(target=sample, args=(stop, telemetry, origin), daemon=True)
    thread.start()
    submissions = []
    rows = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=44) as executor:
            futures = []
            for index in range(REQUESTS):
                arrival = controls[index]["arrival_s"]
                time.sleep(max(0, origin + arrival - time.monotonic()))
                released = time.monotonic() - origin
                future = executor.submit(
                    invoke,
                    index,
                    arrival,
                    released,
                    request_body(template, index),
                    controls[index],
                    origin,
                )
                futures.append(future)
                submissions.append(
                    {
                        "request": index,
                        "planned_release_s": arrival,
                        "actual_release_s": released,
                        "release_drift_seconds": released - arrival,
                    }
                )
            rows = [future.result() for future in futures]
    finally:
        stop.set()
        thread.join(5)
    rows.sort(key=lambda row: row["i"])
    (OUT / "requests.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )
    (OUT / "telemetry.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in telemetry)
    )
    failures = [row for row in rows if "error" in row]
    mismatches = [
        {
            "request": row["i"],
            "first_output_token_mismatch": row["first_output_token_mismatch"],
        }
        for row in rows
        if not row.get("semantic_matches_bound", False) and "error" not in row
    ]
    accept_lengths = [
        row["metrics"].get("sglang:spec_accept_length")
        for row in telemetry
        if row.get("metrics", {}).get("sglang:spec_accept_length") is not None
    ]
    activation = bool(accept_lengths and max(accept_lengths) > 1)
    elapsed_seconds = max(row["completed_s"] for row in rows)
    total_tokens = sum(
        row.get("semantic", {}).get("usage", {}).get("total_tokens", 0)
        for row in rows
    )
    queue_samples = [
        row["metrics"].get("sglang:num_queue_reqs")
        for row in telemetry
        if row.get("metrics", {}).get("sglang:num_queue_reqs") is not None
    ]
    planning_cost = (
        H100_PLANNING_USD_PER_GPU_HOUR
        * elapsed_seconds
        / 3600
        / total_tokens
        * 1_000_000
        if total_tokens
        else None
    )
    sustainable_cost = (
        planning_cost / SUSTAINABLE_UTILIZATION
        if planning_cost is not None
        else None
    )
    decision = {
        "all_requests_complete": len(rows) == REQUESTS and not failures,
        "normalized_semantics_exact": not mismatches and not failures,
        "failures_zero": not failures,
        "native_ngram_activation_observed": activation,
        "h100_fit_gate_passed": all(fit_identity["gates"].values()),
        "release_drift_bounded": all(
            abs(row["release_drift_seconds"]) <= 0.25 for row in submissions
        ),
    }
    terminal = {
        "result": (
            "measured_h100_v0515_activation_semantic_discriminator"
            if REQUESTS == 171
            else "measured_h100_v0515_matched_endpoint"
        ),
        "candidate_sample_consumed": True,
        "identity": {
            "image": IMAGE,
            "commit": COMMIT,
            "model": MODEL,
            "accelerator_required": "nvidia-h100-sxm",
            "ngram": "native_depth_12",
            "requests": f"0_through_{REQUESTS - 1}_at_bound_arrivals",
        },
        "decision": decision,
        "first_semantic_divergence": mismatches[0] if mismatches else None,
        "failures": failures,
        "requests": REQUESTS,
        "total_tokens": total_tokens,
        "elapsed_seconds": elapsed_seconds,
        "service_seconds_per_request": elapsed_seconds / REQUESTS,
        "max_spec_accept_length": max(accept_lengths) if accept_lengths else None,
        "queue_peak": max(queue_samples) if queue_samples else None,
        "queue_final": queue_samples[-1] if queue_samples else None,
    }
    if REQUESTS == 171:
        terminal["endpoint_admitted"] = all(decision.values())
    else:
        economics = {
            "planning_usd_per_gpu_hour": H100_PLANNING_USD_PER_GPU_HOUR,
            "planning_cost_usd_per_million_total_tokens": planning_cost,
            "sustainable_utilization": SUSTAINABLE_UTILIZATION,
            "sustainable_cost_usd_per_million_total_tokens": sustainable_cost,
            "target_usd_per_million_total_tokens": (
                TARGET_USD_PER_MILLION_TOTAL_TOKENS
            ),
        }
        terminal["economics"] = economics
        terminal["decision"].update(
            {
                "planning_cost_at_or_below_target": (
                    planning_cost <= TARGET_USD_PER_MILLION_TOTAL_TOKENS
                ),
                "sustainable_cost_at_or_below_target": (
                    sustainable_cost <= TARGET_USD_PER_MILLION_TOTAL_TOKENS
                ),
                "queue_peak_at_most_30": (
                    queue_samples is not None
                    and bool(queue_samples)
                    and max(queue_samples) <= 30
                ),
                "queue_final_zero": (
                    queue_samples is not None
                    and bool(queue_samples)
                    and queue_samples[-1] == 0
                ),
            }
        )
        terminal["placement_passes"] = all(terminal["decision"].values())
    atomic("FINAL_TERMINAL.json", terminal)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        atomic(
            "ATTEMPT_TERMINAL.json",
            {
                "classification": "recoverable_integration_or_typed_runtime_failure",
                "error": repr(exc),
                "candidate_sample_consumed": False,
            },
        )
        raise
