#!/usr/bin/env python3
"""Run the single stock-SWA allocation-history prefix through request 870."""

from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import pickle
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
CONTAINER = "gemma4-ngram-torch-staircase"
ARRIVAL_SPACING = 0.6946101132986054
SCHEDULED = 871
HISTORY_START_INDEX = 760
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


def launch() -> list[str]:
    frozen = json.loads((CONTROL / "launch-5000.json").read_text())["cmd"]
    module_index = frozen.index("sglang.launch_server")
    server_args = frozen[module_index + 1 :]
    command = [
        "sudo", "docker", "run", "-d", "--name", CONTAINER, "--gpus", "all",
        "--ipc=host", "--network", "host",
        "-e", "PYTHONPATH=/work/instrumentation",
        "-e", "TORCH_STAIRCASE_OUT=/work/out",
        "-v", f"{ROOT}:/work",
        "-v", (
            "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/"
            "checkpoint:/work/checkpoint:ro"
        ),
        IMAGE, "python3", "-m", "sglang.launch_server", *server_args,
    ]
    result = run(command, 120)
    atomic(
        "LAUNCH.json",
        {
            "command_after_image": command[command.index(IMAGE) + 1 :],
            "environment": [
                "PYTHONPATH=/work/instrumentation",
                "TORCH_STAIRCASE_OUT=/work/out",
            ],
            "leaf_split_environment_present": any(
                "SGLANG_OPT_SWA_SPLIT_LEAF_ON_INSERT" in x for x in command
            ),
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


def parse_metrics(raw: str) -> dict[str, float]:
    wanted = {
        "sglang:full_token_usage", "sglang:kv_available_tokens",
        "sglang:kv_evictable_tokens", "sglang:kv_used_tokens",
        "sglang:num_queue_reqs", "sglang:num_retracted_reqs",
        "sglang:num_running_reqs", "sglang:swa_available_tokens",
        "sglang:swa_evictable_tokens", "sglang:swa_used_tokens",
        "sglang:swa_token_usage", "sglang:token_usage",
    }
    result = {}
    for line in raw.splitlines():
        name = line.split("{", 1)[0]
        if name in wanted:
            try:
                result[name] = float(line.rsplit(" ", 1)[1])
            except ValueError:
                pass
    return result


def sample(stop: threading.Event, started_wall: float, rows: list[dict]) -> None:
    while not stop.wait(0.5):
        smi = run(
            [
                "nvidia-smi",
                "--query-gpu=timestamp,utilization.gpu,power.draw,memory.used",
                "--format=csv,noheader,nounits",
            ],
            10,
        )
        row = {
            "wall_time": time.time(),
            "elapsed_wall_seconds": time.time() - started_wall,
            "nvidia_smi": smi.stdout.strip(),
        }
        try:
            row["metrics"] = parse_metrics(get_metrics())
        except Exception as exc:
            row["metrics_error"] = repr(exc)
        rows.append(row)


def post(body: dict) -> tuple[dict, float]:
    native = {
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
        json.dumps(native, separators=(",", ":")).encode(),
        {"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=1200) as response:
        parsed = json.loads(response.read())
    return parsed, time.monotonic() - started


def body(row: dict, tag: str) -> dict:
    value = dict(row["request_body"])
    value["model"] = MODEL
    value["ignore_eos"] = True
    value["min_tokens"] = 358
    value["max_tokens"] = 358
    value["request_id"] = "staircase-" + tag
    return value


def normalized(parsed: dict, request_body: dict) -> dict:
    meta = parsed.get("meta_info") or {}
    usage = {
        "prompt_tokens": meta.get("prompt_tokens", len(request_body["prompt"])),
        "completion_tokens": meta.get("completion_tokens", request_body["max_tokens"]),
    }
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return {
        "output_ids": (
            parsed.get("output_ids")
            or meta.get("output_ids")
            or meta.get("completion_token_ids")
        ),
        "finish_reason": meta.get("finish_reason") or parsed.get("finish_reason"),
        "usage": usage,
    }


def execute(index: int, scheduled: float, request_body: dict, origin: float, control: dict) -> dict:
    started = time.monotonic() - origin
    try:
        parsed, latency = post(request_body)
        value = normalized(parsed, request_body)
        return {
            "i": index,
            "scheduled_s": scheduled,
            "client_started_s": started,
            "completed_s": time.monotonic() - origin,
            "latency_seconds": latency,
            "output_ids_match_control": value["output_ids"] == control["output_ids"],
            "finish_reason_matches_control": value["finish_reason"] == control["finish_reason"],
            "usage_matches_control": value["usage"] == control["usage"],
            **value,
        }
    except Exception as exc:
        return {
            "i": index, "scheduled_s": scheduled, "client_started_s": started,
            "completed_s": time.monotonic() - origin, "error": repr(exc),
        }


def wait_for_history(pattern: str, timeout: float) -> list[Path]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        paths = list(OUT.glob(pattern))
        if paths:
            return paths
        time.sleep(0.25)
    raise RuntimeError(f"allocator_observer_timeout:{pattern}")


def frame_key(frames: list[dict]) -> str:
    useful = []
    for frame in frames or []:
        filename = str(frame.get("filename", ""))
        if "/torch/" in filename and len(useful) < 1:
            continue
        useful.append(
            f"{filename}:{frame.get('line', 0)}:{frame.get('name', '')}"
        )
    return " <- ".join(useful[:6]) or "<no-python-stack>"


def analyze_snapshots() -> dict:
    stats = []
    for path in OUT.glob("allocator-stats.*.jsonl"):
        stats.extend(json.loads(line) for line in path.read_text().splitlines())
    by_pid = {}
    for row in stats:
        by_pid.setdefault(row["pid"], []).append(row)
    processes = []
    for pid, rows in by_pid.items():
        rows.sort(key=lambda row: row["wall_time"])
        starts = list(OUT.glob(f"allocator-start.{pid}.pickle"))
        ends = list(OUT.glob(f"allocator-end.{pid}.pickle"))
        if not starts or not ends:
            continue
        with starts[0].open("rb") as handle:
            before = pickle.load(handle)
        with ends[0].open("rb") as handle:
            after = pickle.load(handle)
        before_segments = {
            (s.get("address"), s.get("total_size"), repr(s.get("segment_pool_id"))): s
            for s in before.get("segments", [])
        }
        new_segments = [
            s for s in after.get("segments", [])
            if (s.get("address"), s.get("total_size"), repr(s.get("segment_pool_id")))
            not in before_segments
        ]
        ranked = {}
        for segment in new_segments:
            pool = repr(segment.get("segment_pool_id"))
            for block in segment.get("blocks", []):
                histories = block.get("history") or []
                frames = histories[-1].get("frames", []) if histories else []
                key = (pool, frame_key(frames))
                ranked[key] = ranked.get(key, 0) + int(block.get("size", 0))
        ranked_rows = [
            {"segment_pool_id": pool, "stack": stack, "bytes": size}
            for (pool, stack), size in ranked.items()
        ]
        ranked_rows.sort(key=lambda row: row["bytes"], reverse=True)
        processes.append(
            {
                "pid": pid,
                "reserved_start": rows[0]["reserved_bytes"],
                "reserved_end": rows[-1]["reserved_bytes"],
                "reserved_delta": rows[-1]["reserved_bytes"] - rows[0]["reserved_bytes"],
                "new_segment_bytes": sum(int(s.get("total_size", 0)) for s in new_segments),
                "new_segment_count": len(new_segments),
                "new_segment_pools": {
                    pool: sum(
                        int(s.get("total_size", 0))
                        for s in new_segments
                        if repr(s.get("segment_pool_id")) == pool
                    )
                    for pool in {
                        repr(s.get("segment_pool_id")) for s in new_segments
                    }
                },
                "site_ranked_new_segment_blocks": ranked_rows[:30],
            }
        )
    processes.sort(key=lambda row: row["reserved_delta"], reverse=True)
    return {"processes": processes}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    atomic("INVOCATION_STATE.json", {"science_started": False, "phase": "server_load"})
    trace = json.loads((CONTROL / "TRACE_PACKET.json").read_text())
    group = next(x for x in trace["primary_groups"] if x["name"] == "primary_c1")
    controls = [json.loads(line) for line in COMPARATOR.read_text().splitlines()]
    if len(controls) < SCHEDULED:
        raise RuntimeError("comparator_too_short")
    run(["sudo", "docker", "rm", "-f", CONTAINER], 60)
    run(["sudo", "docker", "rm", "-f", "gemma4-ngram-swa-pressure"], 60)
    server_args = launch()
    wait_server()
    post(body(group["warmup"], "warmup"))
    (OUT / "metrics-before.prom").write_text(get_metrics())
    samples = []
    stop = threading.Event()
    sampled_wall = time.time()
    sampler = threading.Thread(target=sample, args=(stop, sampled_wall, samples), daemon=True)
    sampler.start()
    started = time.monotonic()
    atomic(
        "INVOCATION_STATE.json",
        {"science_started": True, "phase": "stock_prefix", "scheduled": SCHEDULED},
    )
    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for index in range(SCHEDULED):
            scheduled = index * ARRIVAL_SPACING
            time.sleep(max(0.0, started + scheduled - time.monotonic()))
            if index == HISTORY_START_INDEX:
                atomic(
                    "START_HISTORY",
                    {"request_index": index, "wall_time": time.time()},
                )
                wait_for_history("HISTORY_STARTED.*.json", 30)
            source = copy.deepcopy(group["scored"][index % len(group["scored"])])
            request_body = body(source, str(index))
            request_body["prompt"][535] = 200000 + index
            futures.append(
                pool.submit(execute, index, scheduled, request_body, started, controls[index])
            )
        rows = [future.result() for future in concurrent.futures.as_completed(futures)]
    ended = time.monotonic()
    atomic("DUMP_HISTORY", {"request_index": 870, "wall_time": time.time()})
    started_markers = list(OUT.glob("HISTORY_STARTED.*.json"))
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if len(list(OUT.glob("HISTORY_DUMPED.*.json"))) >= len(started_markers):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("allocator_dump_timeout")
    stop.set()
    sampler.join(5)
    rows.sort(key=lambda row: row["i"])
    (OUT / "requests-prefix.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )
    (OUT / "telemetry-prefix.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in samples)
    )
    (OUT / "metrics-after.prom").write_text(get_metrics())
    attribution = analyze_snapshots()
    atomic("ATTRIBUTION.json", attribution)
    valid = [row for row in rows if "error" not in row]
    exact = [
        row for row in valid
        if row["output_ids_match_control"]
        and row["finish_reason_matches_control"]
        and row["usage_matches_control"]
    ]
    terminal = {
        "result": "measured_stock_swa_allocator_prefix",
        "attribution_science_consumed": True,
        "identity": {
            "image": IMAGE,
            "model": MODEL,
            "server_args": server_args,
            "trace_packet_sha256": hashlib.sha256(
                (CONTROL / "TRACE_PACKET.json").read_bytes()
            ).hexdigest(),
            "comparator_sha256": hashlib.sha256(COMPARATOR.read_bytes()).hexdigest(),
        },
        "primary": {
            "scheduled": SCHEDULED,
            "completed": len(valid),
            "failures": [row for row in rows if "error" in row],
            "elapsed_seconds": ended - started,
            "exact_index_aligned_semantics_matching_control": len(exact),
            "latency_p50_seconds": statistics.median(
                row["latency_seconds"] for row in valid
            ) if valid else None,
        },
        "attribution": attribution,
        "leaf_split_environment_present": False,
        "container_retained_healthy": run(
            ["sudo", "docker", "inspect", "-f", "{{.State.Running}}", CONTAINER], 20
        ).stdout.strip() == "true",
    }
    atomic("ATTRIBUTION_TERMINAL.json", terminal)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logs = run(["sudo", "docker", "logs", CONTAINER], 60)
        atomic(
            "ATTEMPT_TERMINAL.json",
            {
                "result": "recoverable_attribution_harness_or_runtime_failure",
                "error": repr(exc),
                "science_started": (
                    (OUT / "INVOCATION_STATE.json").exists()
                    and json.loads((OUT / "INVOCATION_STATE.json").read_text()).get(
                        "science_started", False
                    )
                ),
            },
        )
        (OUT / "container.stdout.log").write_text(logs.stdout)
        (OUT / "container.stderr.log").write_text(logs.stderr)
        raise
