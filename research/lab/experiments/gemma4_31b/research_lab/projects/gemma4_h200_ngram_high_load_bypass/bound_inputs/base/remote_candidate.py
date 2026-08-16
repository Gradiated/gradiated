#!/usr/bin/env python3
"""One frozen fixed-rate NGRAM corpus-lifetime candidate trajectory."""

from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import threading
import time
import urllib.request


ROOT = Path("/home/glmrunner/gemma4-h200-ngram-torch-reserved-staircase")
OUT = ROOT / "out"
CONTROL = ROOT / "inputs/control"
COMPARATOR = ROOT / "inputs/comparator/requests.jsonl"
MODEL = "google/gemma-4-31B-it"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
CONTAINER = "gemma4-ngram-torch-staircase-candidate"
ARRIVAL_SPACING = 0.6946101132986054
SCHEDULED = 1036
MAX_WORKERS = 32


def atomic(name: str, value: object) -> None:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, text=True, capture_output=True, check=False, timeout=timeout
    )


def sha256_json(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def launch() -> list[str]:
    launch_record = json.loads((CONTROL / "launch-5000.json").read_text())
    frozen = launch_record["cmd"]
    module_index = frozen.index("sglang.launch_server")
    server_args = frozen[module_index + 1 :]
    command = [
        "sudo",
        "docker",
        "run",
        "-d",
        "--name",
        CONTAINER,
        "--gpus",
        "all",
        "--ipc=host",
        "--network",
        "host",
        "-e",
        "PYTHONPATH=/work/candidate",
        "-e",
        "TORCH_STAIRCASE_OUT=/work/out",
        "-v",
        f"{ROOT}:/work",
        "-v",
        (
            "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/"
            "checkpoint:/work/checkpoint:ro"
        ),
        IMAGE,
        "python3",
        "-m",
        "sglang.launch_server",
        *server_args,
    ]
    result = run(command, timeout=120)
    atomic(
        "LAUNCH.json",
        {
            "command_after_image": command[command.index(IMAGE) + 1 :],
            "server_args": server_args,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    if result.returncode:
        raise RuntimeError("launch_failed")
    return server_args


def wait_server() -> None:
    deadline = time.monotonic() + 720
    while time.monotonic() < deadline:
        try:
            body = urllib.request.urlopen(
                "http://127.0.0.1:30000/v1/models", timeout=4
            ).read()
            if MODEL.encode() in body:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("server_not_ready")


def get_metrics() -> str:
    return urllib.request.urlopen(
        "http://127.0.0.1:30000/metrics", timeout=10
    ).read().decode()


METRIC_NAMES = {
    "sglang:cached_tokens_total",
    "sglang:evicted_tokens_total",
    "sglang:eviction_duration_seconds_count",
    "sglang:eviction_duration_seconds_sum",
    "sglang:full_token_usage",
    "sglang:kv_available_tokens",
    "sglang:kv_evictable_tokens",
    "sglang:kv_used_tokens",
    "sglang:num_queue_reqs",
    "sglang:num_retracted_reqs",
    "sglang:num_running_reqs",
    "sglang:spec_accept_length",
    "sglang:spec_accept_rate",
    "sglang:swa_available_tokens",
    "sglang:swa_evictable_tokens",
    "sglang:swa_used_tokens",
    "sglang:swa_token_usage",
    "sglang:token_usage",
}


def parse_metrics(raw: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for line in raw.splitlines():
        if not line or line.startswith("#"):
            continue
        name = line.split("{", 1)[0]
        if name not in METRIC_NAMES:
            continue
        try:
            result[name] = float(line.rsplit(" ", 1)[1])
        except ValueError:
            continue
    return result


def sample(stop: threading.Event, started_wall: float, rows: list[dict]) -> None:
    while not stop.wait(2):
        row: dict[str, object] = {
            "wall_time": time.time(),
            "elapsed_wall_seconds": time.time() - started_wall,
        }
        smi = run(
            [
                "nvidia-smi",
                "--query-gpu=timestamp,utilization.gpu,power.draw,memory.used",
                "--format=csv,noheader,nounits",
            ],
            timeout=10,
        )
        row["nvidia_smi"] = smi.stdout.strip()
        try:
            row["metrics"] = parse_metrics(get_metrics())
        except Exception as exc:
            row["metrics_error"] = repr(exc)
        rows.append(row)


def post(body: dict) -> tuple[dict, dict, bytes]:
    native = {
        "input_ids": body["prompt"],
        "sampling_params": {
            "temperature": 0,
            "max_new_tokens": body["max_tokens"],
            "min_new_tokens": body["min_tokens"],
            "ignore_eos": body["ignore_eos"],
        },
    }
    raw_request = json.dumps(native, separators=(",", ":")).encode()
    request = urllib.request.Request(
        "http://127.0.0.1:30000/generate",
        raw_request,
        {"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=1200) as response:
        raw = response.read()
    ended = time.monotonic()
    parsed = json.loads(raw)
    meta = parsed.get("meta_info") or {}
    parsed["usage"] = {
        "prompt_tokens": meta.get("prompt_tokens", len(body["prompt"])),
        "completion_tokens": meta.get("completion_tokens", body["max_tokens"]),
        "total_tokens": meta.get(
            "prompt_tokens", len(body["prompt"])
        )
        + meta.get("completion_tokens", body["max_tokens"]),
    }
    timing = {
        "latency_seconds": ended - started,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
    }
    return parsed, timing, raw


def body(row: dict, tag: str) -> dict:
    value = dict(row["request_body"])
    value["model"] = MODEL
    value["ignore_eos"] = True
    value["min_tokens"] = 358
    value["max_tokens"] = 358
    value["request_id"] = "sustainable-" + tag
    return value


def normalized_response(parsed: dict) -> dict:
    meta = parsed.get("meta_info") or {}
    output_ids = (
        parsed.get("output_ids")
        or meta.get("output_ids")
        or meta.get("completion_token_ids")
    )
    text = parsed.get("text")
    return {
        "text": text,
        "output_ids": output_ids,
        "finish_reason": meta.get("finish_reason") or parsed.get("finish_reason"),
        "usage": parsed.get("usage"),
    }


def execute(
    index: int,
    scheduled: float,
    request_body: dict,
    origin: float,
    control: dict,
) -> dict:
    client_started = time.monotonic() - origin
    try:
        parsed, timing, raw = post(request_body)
        normalized = normalized_response(parsed)
        candidate_request_sha = sha256_json(request_body)
        return {
            "i": index,
            "scheduled_s": scheduled,
            "client_started_s": client_started,
            "completed_s": time.monotonic() - origin,
            "usage": parsed["usage"],
            "timing": timing,
            "request_sha256": candidate_request_sha,
            "output_ids_match_control": normalized["output_ids"]
            == control["output_ids"],
            "finish_reason_matches_control": normalized["finish_reason"]
            == control["finish_reason"],
            "usage_matches_control": parsed["usage"] == control["usage"],
            "normalized_response_sha256": sha256_json(normalized),
            "output_ids": normalized["output_ids"],
            "text_sha256": (
                hashlib.sha256(str(normalized["text"]).encode()).hexdigest()
                if normalized["text"] is not None
                else None
            ),
            "finish_reason": normalized["finish_reason"],
            "raw_response_prefix": raw[:512].decode(errors="replace"),
        }
    except Exception as exc:
        return {
            "i": index,
            "scheduled_s": scheduled,
            "client_started_s": client_started,
            "completed_s": time.monotonic() - origin,
            "error": repr(exc),
        }


def windows(rows: list[dict]) -> list[dict]:
    result = []
    for lower in range(0, SCHEDULED, 100):
        group = [
            row
            for row in rows
            if lower <= row["i"] < min(SCHEDULED, lower + 100)
            and "error" not in row
        ]
        if not group:
            continue
        latencies = [row["timing"]["latency_seconds"] for row in group]
        queues = [
            max(0.0, row["client_started_s"] - row["scheduled_s"])
            for row in group
        ]
        result.append(
            {
                "request_index_begin": lower,
                "request_index_end_exclusive": min(SCHEDULED, lower + 100),
                "completed": len(group),
                "latency_mean_seconds": statistics.mean(latencies),
                "latency_median_seconds": statistics.median(latencies),
                "latency_max_seconds": max(latencies),
                "client_queue_mean_seconds": statistics.mean(queues),
                "client_queue_max_seconds": max(queues),
                "exact_semantics_matches_control": sum(
                    bool(row["output_ids_match_control"])
                    and bool(row["finish_reason_matches_control"])
                    and bool(row["usage_matches_control"])
                    for row in group
                ),
            }
        )
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    atomic(
        "INVOCATION_STATE.json",
        {"science_started": False, "phase": "candidate_server_load"},
    )
    trace = json.loads((CONTROL / "TRACE_PACKET.json").read_text())
    group = next(x for x in trace["primary_groups"] if x["name"] == "primary_c1")
    control_rows = [
        json.loads(line) for line in COMPARATOR.read_text().splitlines()
    ]
    if len(control_rows) != SCHEDULED:
        raise RuntimeError("control_row_count_mismatch")

    run(["sudo", "docker", "rm", "-f", CONTAINER], timeout=60)
    run(
        ["sudo", "docker", "rm", "-f", "gemma4-ngram-torch-staircase"],
        timeout=60,
    )
    server_args = launch()
    wait_server()
    atomic(
        "INVOCATION_STATE.json",
        {"science_started": False, "phase": "candidate_warmup"},
    )
    warmup_request = body(group["warmup"], "warmup")
    post(warmup_request)
    before_raw = get_metrics()
    (OUT / "metrics-before-primary.prom").write_text(before_raw)
    (OUT / "PRIMARY_ARMED").write_text("frozen primary begins\n")

    samples: list[dict] = []
    stop = threading.Event()
    sampled_wall = time.time()
    sampler = threading.Thread(
        target=sample, args=(stop, sampled_wall, samples), daemon=True
    )
    sampler.start()
    started = time.monotonic()
    atomic(
        "INVOCATION_STATE.json",
        {
            "science_started": True,
            "phase": "candidate_primary_open_loop",
            "scheduled": SCHEDULED,
        },
    )
    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for index in range(SCHEDULED):
            scheduled = index * ARRIVAL_SPACING
            due = started + scheduled
            time.sleep(max(0.0, due - time.monotonic()))
            source = copy.deepcopy(group["scored"][index % len(group["scored"])])
            request_body = body(source, str(index))
            request_body["prompt"][535] = 200000 + index
            futures.append(
                pool.submit(
                    execute,
                    index,
                    scheduled,
                    request_body,
                    started,
                    control_rows[index],
                )
            )
        rows = [future.result() for future in concurrent.futures.as_completed(futures)]

    ended = time.monotonic()
    stop.set()
    sampler.join(5)
    rows.sort(key=lambda row: row["i"])
    (OUT / "requests.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )
    (OUT / "telemetry.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in samples)
    )
    window_rows = windows(rows)
    atomic("WINDOWS.json", window_rows)
    after_raw = None
    metrics_after_error = None
    try:
        after_raw = get_metrics()
        (OUT / "metrics-after.prom").write_text(after_raw)
    except Exception as exc:
        metrics_after_error = repr(exc)
        atomic("METRICS_AFTER_UNAVAILABLE.json", {"error": metrics_after_error})

    valid = [row for row in rows if "error" not in row]
    failures = [row for row in rows if "error" in row]
    output_matches = sum(bool(row["output_ids_match_control"]) for row in valid)
    finish_matches = sum(
        bool(row["finish_reason_matches_control"]) for row in valid
    )
    usage_matches = sum(bool(row["usage_matches_control"]) for row in valid)
    exact_matches = sum(
        bool(row["output_ids_match_control"])
        and bool(row["finish_reason_matches_control"])
        and bool(row["usage_matches_control"])
        for row in valid
    )
    final_queue = max(
        [0.0]
        + [
            row["client_started_s"] - row["scheduled_s"]
            for row in rows
        ]
    )
    total_tokens = sum(row["usage"]["total_tokens"] for row in valid)
    terminal = {
        "result": "measured_target_verify_broadcast_reuse_candidate",
        "candidate_science_consumed": True,
        "intervention": {
            "kind": "target_verify_additive_broadcast_workspace_reuse",
            "owner": "BatchedPenalizerOrchestrator.apply",
            "removed_temporary": "repeat_interleave(additive, repeat, dim=0)",
            "request_or_scheduler_setting_changed": False,
        },
        "identity": {
            "image": IMAGE,
            "model": MODEL,
            "server_args": server_args,
            "trace_packet_sha256": hashlib.sha256(
                (CONTROL / "TRACE_PACKET.json").read_bytes()
            ).hexdigest(),
            "control_requests_sha256": hashlib.sha256(
                COMPARATOR.read_bytes()
            ).hexdigest(),
        },
        "primary": {
            "scheduled": SCHEDULED,
            "completed": len(valid),
            "failures": failures,
            "elapsed_seconds": ended - started,
            "total_tokens": total_tokens,
            "final_client_queue_seconds": final_queue,
            "output_token_sequences_matching_control": output_matches,
            "finish_reasons_matching_control": finish_matches,
            "usage_matching_control": usage_matches,
            "exact_index_aligned_semantics_matching_control": exact_matches,
            "latency_p50_seconds": (
                statistics.median(
                    row["timing"]["latency_seconds"] for row in valid
                )
                if valid
                else None
            ),
        },
        "telemetry_samples": len(samples),
        "metric_final": parse_metrics(after_raw) if after_raw is not None else None,
        "metrics_after_error": metrics_after_error,
        "container_retained_healthy": (
            run(
                [
                    "sudo",
                    "docker",
                    "inspect",
                    "-f",
                    "{{.State.Running}}",
                    CONTAINER,
                ],
                timeout=20,
            ).stdout.strip()
            == "true"
        ),
    }
    if valid and total_tokens:
        terminal["economics"] = {
            "planning_h200_usd_per_hour": 3.25,
            "tokens_per_second": total_tokens / (ended - started),
            "usd_per_million_total_tokens": (
                3.25 / 3600 * 1_000_000 / (total_tokens / (ended - started))
            ),
        }
    atomic("FINAL_TERMINAL.json", terminal)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logs = run(["sudo", "docker", "logs", CONTAINER], timeout=60)
        atomic(
            "ATTEMPT_TERMINAL.json",
            {
                "result": "recoverable_candidate_harness_or_runtime_failure",
                "error": repr(exc),
                "candidate_science_started": (
                    (OUT / "INVOCATION_STATE.json").exists()
                    and json.loads(
                        (OUT / "INVOCATION_STATE.json").read_text()
                    ).get("science_started", False)
                ),
                "container_logs_stdout_sha256": hashlib.sha256(
                    logs.stdout.encode()
                ).hexdigest(),
                "container_logs_stderr_sha256": hashlib.sha256(
                    logs.stderr.encode()
                ).hexdigest(),
            },
        )
        (OUT / "container.stdout.log").write_text(logs.stdout)
        (OUT / "container.stderr.log").write_text(logs.stderr)
        raise
