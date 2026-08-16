#!/usr/bin/env python3
"""Measure exact Gemma c16/c32 request paths and an output-scaling discriminator."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import statistics
import subprocess
import threading
import time
import urllib.request


BASE = "http://127.0.0.1:30000"


def atomic_json(path: pathlib.Path, value: object) -> None:
    partial = path.with_suffix(path.suffix + ".part")
    partial.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    partial.replace(path)


def fetch(path: str, timeout: float = 30) -> bytes:
    return urllib.request.urlopen(BASE + path, timeout=timeout).read()


def post(path: str, body: dict | None = None, timeout: float = 30) -> bytes:
    raw = json.dumps(body or {}, separators=(",", ":")).encode()
    request = urllib.request.Request(BASE + path, raw, {"Content-Type": "application/json"})
    return urllib.request.urlopen(request, timeout=timeout).read()


def sample_gpu(path: pathlib.Path, stop: threading.Event) -> None:
    with path.open("w") as output:
        output.write("monotonic_s,utilization_gpu_pct,memory_used_mib,power_w,sm_clock_mhz,memory_clock_mhz\n")
        while not stop.is_set():
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,power.draw,clocks.sm,clocks.mem",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            output.write(f"{time.monotonic():.6f},{result.stdout.strip()}\n")
            output.flush()
            stop.wait(0.2)


def one_request(body: dict, root: pathlib.Path, index: int, barrier: threading.Barrier) -> dict:
    raw = json.dumps({**body, "stream": False}, separators=(",", ":")).encode()
    barrier.wait(timeout=60)
    started = time.monotonic()
    error = None
    parsed: dict = {}
    response = b""
    try:
        request = urllib.request.Request(BASE + "/v1/completions", raw, {"Content-Type": "application/json"})
        response = urllib.request.urlopen(request, timeout=600).read()
        parsed = json.loads(response)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:2000]
    ended = time.monotonic()
    choice = (parsed.get("choices") or [{}])[0]
    usage = parsed.get("usage") or {}
    text = choice.get("text") or ""
    row = {
        "index": index,
        "started_monotonic_s": started,
        "ended_monotonic_s": ended,
        "wall_seconds": ended - started,
        "error": error,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "text_nonempty": bool(text),
        "request_sha256": hashlib.sha256(raw).hexdigest(),
        "response_sha256": hashlib.sha256(response).hexdigest(),
    }
    atomic_json(root / f"request-{index:02d}.json", row)
    return row


def run_arm(root: pathlib.Path, source: list[dict], concurrency: int, output_tokens: int) -> dict:
    arm = root / f"c{concurrency}_o{output_tokens}"
    arm.mkdir()
    try:
        (arm / "flush-cache.json").write_bytes(post("/flush_cache"))
    except Exception as exc:
        (arm / "flush-cache.error").write_text(repr(exc) + "\n")
    time.sleep(1)
    (arm / "metrics-before.prom").write_bytes(fetch("/metrics"))
    bodies = []
    for index in range(concurrency):
        body = dict(source[index % len(source)])
        body.update({"max_tokens": output_tokens, "min_tokens": output_tokens, "ignore_eos": True})
        bodies.append(body)
    stop = threading.Event()
    sampler = threading.Thread(target=sample_gpu, args=(arm / "gpu.csv", stop), daemon=True)
    sampler.start()
    barrier = threading.Barrier(concurrency)
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        rows = list(pool.map(lambda pair: one_request(pair[1], arm, pair[0], barrier), enumerate(bodies)))
    batch_seconds = time.monotonic() - started
    stop.set()
    sampler.join(timeout=2)
    (arm / "metrics-after.prom").write_bytes(fetch("/metrics"))
    valid = all(
        row["error"] is None
        and row["text_nonempty"]
        and row["prompt_tokens"] == 4214
        and row["completion_tokens"] == output_tokens
        for row in rows
    )
    walls = [row["wall_seconds"] for row in rows]
    terminal = {
        "arm": arm.name,
        "pass": valid,
        "concurrency": concurrency,
        "prompt_tokens_per_request": 4214,
        "output_tokens_per_request": output_tokens,
        "complete_requests": sum(row["error"] is None for row in rows),
        "batch_seconds": batch_seconds,
        "service_seconds_per_request": batch_seconds / concurrency,
        "output_tokens_per_second": concurrency * output_tokens / batch_seconds,
        "request_wall_seconds": {
            "min": min(walls),
            "median": statistics.median(walls),
            "max": max(walls),
        },
        "rows": rows,
    }
    atomic_json(arm / "TERMINAL.json", terminal)
    return terminal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    trace = json.loads(args.trace.read_text())
    group = next(item for item in trace["primary_groups"] if item["concurrency"] == 16)
    source = [item["request_body"] for item in group["scored"]]
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "models.json").write_bytes(fetch("/v1/models"))
    arms = []
    for concurrency, output_tokens in ((16, 1), (16, 358), (32, 358)):
        arm = run_arm(args.output, source, concurrency, output_tokens)
        arms.append(arm)
        atomic_json(args.output / "PARTIAL.json", {"arms": arms})
        if not arm["pass"]:
            break
    summary = {"schema_version": 1, "kind": "gemma4_h200_critical_path", "pass": len(arms) == 3 and all(x["pass"] for x in arms), "arms": arms}
    if len(arms) >= 2 and arms[0]["pass"] and arms[1]["pass"]:
        prefill_bound = arms[0]["batch_seconds"]
        decode_increment = arms[1]["batch_seconds"] - prefill_bound
        summary["output_scaling_discriminator"] = {
            "c16_o1_batch_seconds": prefill_bound,
            "c16_incremental_o2_to_o358_seconds": decode_increment,
            "decode_increment_fraction_of_c16_o358_batch": decode_increment / arms[1]["batch_seconds"],
            "incremental_seconds_per_additional_output_token": decode_increment / 357,
            "interpretation": "analytical phase bound; flush-cache isolation and exact endpoint measurements, not additive kernel attribution",
        }
    atomic_json(args.output / "TERMINAL.json", summary)
    return 0 if summary["pass"] else 72


if __name__ == "__main__":
    raise SystemExit(main())
