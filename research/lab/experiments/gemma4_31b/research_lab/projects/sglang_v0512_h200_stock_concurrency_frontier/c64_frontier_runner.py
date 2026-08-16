#!/usr/bin/env python3
"""Execute the bound SGLang c64 arm and, conditionally, c96 on one resident endpoint."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import subprocess
import threading
import time
import urllib.request


MODEL = "google/gemma-4-31B-it"
PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358
COMPARATOR_SERVICE_SECONDS = 0.3633031778124973
ECONOMIC_CEILING = 0.47201182295214134


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    part.replace(path)


def fetch(url: str, timeout: float = 30) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def gpu_sample(path: pathlib.Path, stop: threading.Event, interval: float) -> None:
    with path.open("w") as handle:
        handle.write("timestamp,index,memory.used,memory.total,utilization.gpu,power.draw\n")
        while not stop.is_set():
            try:
                result = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=timestamp,index,memory.used,memory.total,utilization.gpu,power.draw",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                for line in result.stdout.splitlines():
                    handle.write(line + "\n")
                if result.returncode:
                    handle.write(f"error,returncode={result.returncode}\n")
            except Exception as exc:  # preserve an observability diagnostic, not a false pass
                handle.write(f"error,{type(exc).__name__}:{exc}\n")
            handle.flush()
            stop.wait(interval)


def memory_safe(path: pathlib.Path) -> bool:
    peak = 0.0
    total = 0.0
    for line in path.read_text().splitlines()[1:]:
        fields = [item.strip() for item in line.split(",")]
        if len(fields) != 6 or fields[0] == "error":
            continue
        try:
            used = float(fields[2])
            capacity = float(fields[3])
        except ValueError:
            continue
        peak = max(peak, used)
        total = max(total, capacity)
    return total > 0 and peak < total * 0.95


def one_request(base: str, body: dict, root: pathlib.Path, index: int, barrier: threading.Barrier) -> dict:
    barrier.wait(timeout=120)
    request_body = {**body, "stream": False}
    raw_request = canonical(request_body)
    request_path = root / "requests" / f"request-{index:03d}.json"
    response_path = root / "responses" / f"response-{index:03d}.bin"
    request_path.write_bytes(raw_request)
    started = time.monotonic()
    parsed: dict = {}
    error = None
    try:
        request = urllib.request.Request(
            base + "/v1/completions",
            data=raw_request,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=1800) as response:
            raw_response = response.read()
        response_path.write_bytes(raw_response)
        parsed = json.loads(raw_response)
    except Exception as exc:
        raw_response = b""
        response_path.write_bytes(raw_response)
        error = {"type": type(exc).__name__, "message": str(exc)[:4000]}
    choice = (parsed.get("choices") or [{}])[0]
    usage = parsed.get("usage") or {}
    text = choice.get("text") or ""
    return {
        "index": index,
        "request_sha256": sha(raw_request),
        "response_sha256": sha(raw_response),
        "request_path": str(request_path),
        "response_path": str(response_path),
        "error": error,
        "wall_seconds": time.monotonic() - started,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "text_nonempty": bool(text),
        "output_id": sha(text.encode()),
    }


def run_arm(base: str, trace: dict, root: pathlib.Path, concurrency: int, interval: float) -> dict:
    group = next(item for item in trace["primary_groups"] if item["concurrency"] == 16)
    source = [item["request_body"] for item in group["scored"]]
    if len(source) != 16:
        raise ValueError("bound c16 scored group is not exactly 16 requests")
    bodies = [source[index % len(source)] for index in range(concurrency)]
    arm_root = root / f"c{concurrency}"
    (arm_root / "requests").mkdir(parents=True)
    (arm_root / "responses").mkdir()
    (arm_root / "telemetry").mkdir()
    atomic_json(arm_root / "request-contract.json", {
        "source_trace_sha256": sha(pathlib.Path(args_trace).read_bytes()),
        "source_group": "primary_c16.scored",
        "source_group_requests": 16,
        "concurrency": concurrency,
        "construction": "source scored bodies repeated in order; stream=false added as in repaired c32 consumer",
        "prompt_tokens": PROMPT_TOKENS,
        "output_tokens": OUTPUT_TOKENS,
        "model": MODEL,
    })
    atomic_json(arm_root / "models.json", json.loads(fetch(base + "/v1/models")))
    (arm_root / "metrics-before.prom").write_bytes(fetch(base + "/metrics"))
    stop = threading.Event()
    sampler = threading.Thread(target=gpu_sample, args=(arm_root / "telemetry" / "gpu.csv", stop, interval), daemon=True)
    sampler.start()
    barrier = threading.Barrier(concurrency)
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        rows = list(pool.map(lambda pair: one_request(base, pair[1], arm_root, pair[0], barrier), enumerate(bodies)))
    elapsed = time.monotonic() - started
    stop.set()
    sampler.join(timeout=max(2.0, interval * 2))
    (arm_root / "metrics-after.prom").write_bytes(fetch(base + "/metrics"))
    valid = all(
        row["error"] is None
        and row["text_nonempty"]
        and row["prompt_tokens"] == PROMPT_TOKENS
        and row["completion_tokens"] == OUTPUT_TOKENS
        for row in rows
    )
    terminal = {
        "schema_version": 1,
        "kind": "sglang_h200_stock_concurrency_stage",
        "arm": f"c{concurrency}",
        "pass": valid,
        "complete_requests": sum(row["error"] is None for row in rows),
        "required_requests": concurrency,
        "token_accounting_pass": valid,
        "batch_seconds": elapsed,
        "service_seconds_per_request": elapsed / concurrency,
        "completed_requests_per_second": concurrency / elapsed,
        "memory_safe": memory_safe(arm_root / "telemetry" / "gpu.csv"),
        "market_pass": valid and elapsed / concurrency <= ECONOMIC_CEILING,
        "improvement_vs_c32": 1 - (elapsed / concurrency) / COMPARATOR_SERVICE_SECONDS,
        "rows": rows,
        "artifacts": {
            "metrics_before": "metrics-before.prom",
            "metrics_after": "metrics-after.prom",
            "gpu_samples": "telemetry/gpu.csv",
        },
    }
    atomic_json(arm_root / "TERMINAL.json", terminal)
    return terminal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:30000")
    parser.add_argument("--trace", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--gpu-smi-interval", type=float, default=1.0)
    args = parser.parse_args()
    global args_trace
    args_trace = args.trace
    trace_path = pathlib.Path(args.trace)
    trace = json.loads(trace_path.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    stages = [run_arm(args.base, trace, args.output, 64, args.gpu_smi_interval)]
    c64 = stages[0]
    if c64["pass"] and c64["improvement_vs_c32"] >= 0.05 and c64["memory_safe"]:
        stages.append(run_arm(args.base, trace, args.output, 96, args.gpu_smi_interval))
        conditional = "c96"
    elif not c64["pass"] and any(
        row["error"] and any(token in row["error"]["message"].lower() for token in ("out of memory", "oom", "capacity"))
        for row in c64["rows"]
    ):
        stages.append(run_arm(args.base, trace, args.output, 48, args.gpu_smi_interval))
        conditional = "c48"
    else:
        conditional = "not_admitted"
    terminal = {
        "schema_version": 1,
        "kind": "sglang_h200_stock_concurrency_frontier",
        "trace_sha256": sha(trace_path.read_bytes()),
        "stages": [{"arm": row["arm"], "pass": row["pass"], "service_seconds_per_request": row["service_seconds_per_request"]} for row in stages],
        "conditional_arm": conditional,
        "terminal_decision": "c96_admitted_only_after_c64_ge_5pct_and_safe_memory_telemetry",
        "pass": bool(stages and stages[0]["pass"]),
    }
    atomic_json(args.output / "TERMINAL.json", terminal)
    return 0 if terminal["pass"] else 72


if __name__ == "__main__":
    raise SystemExit(main())
