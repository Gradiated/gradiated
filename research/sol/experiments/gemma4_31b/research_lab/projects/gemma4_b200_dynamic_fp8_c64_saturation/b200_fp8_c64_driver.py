#!/usr/bin/env python3
import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import pathlib
import threading
import time
import urllib.request


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def request_one(pair, base, output, barrier):
    index, body = pair
    (output / f"request-{index:02}.json").write_bytes(canonical(body))
    barrier.wait()
    started = time.monotonic()
    raw, token_ids, text, usage, error = [], [], "", {}, None
    try:
        request = urllib.request.Request(base + "/v1/completions", canonical(body), {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=1800) as response:
            for line in response:
                raw.append(line)
                if line.startswith(b"data: ") and line.strip() != b"data: [DONE]":
                    item = json.loads(line[6:])
                    choice = (item.get("choices") or [{}])[0]
                    token_ids.extend(choice.get("token_ids") or [])
                    text += choice.get("text") or ""
                    usage = item.get("usage") or usage
    except Exception as exc:
        error = repr(exc)
    elapsed = time.monotonic() - started
    (output / f"response-{index:02}.sse").write_bytes(b"".join(raw))
    return {
        "index": index,
        "error": error,
        "seconds": elapsed,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "returned_token_ids": len(token_ids),
        "nonempty": bool(text),
        "request_sha256": hashlib.sha256(canonical(body)).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--binding", type=pathlib.Path, required=True)
    args = parser.parse_args()
    binding = json.loads(args.binding.read_text())
    identities = binding["immutable_identities"]
    if binding["driver_sha256"] != digest(pathlib.Path(__file__).resolve()):
        raise SystemExit("bound driver digest mismatch")
    if identities != {
        "checkpoint_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "runtime_quantization": "runtime_dynamic_fp8_weights",
        "predecessor_workload": "c32/4214/358/text-only/non-reasoning",
        "workload": "c64/4214/358/text-only/non-reasoning",
        "model": "google/gemma-4-31B-it",
    }:
        raise SystemExit("bound immutable identities mismatch")
    token_contract = binding["request_token_contract"]
    if token_contract != {"c32_requests": 32, "prompt_tokens": 4214, "completion_tokens": 358, "returned_token_ids": 358}:
        raise SystemExit("bound token contract mismatch")
    args.output.mkdir(parents=True, exist_ok=True)
    prefix = [1000 + ((index * 7919 + 17) % 48000) for index in range(535)]
    bodies = []
    for index in range(64):
        suffix = [60000 + index] + [1000 + ((index * 4214 + token * 1543) % 48000) for token in range(3678)]
        bodies.append({
            "model": identities["model"],
            "prompt": prefix + suffix,
            "max_tokens": 358,
            "min_tokens": 358,
            "ignore_eos": True,
            "temperature": 0,
            "seed": 20260728 + index,
            "stream": True,
            "stream_options": {"include_usage": True},
            "return_token_ids": True,
            "add_special_tokens": False,
        })
    predecessor_requests = binding["predecessor_request_sha256"]
    if len(predecessor_requests) != 32 or [hashlib.sha256(canonical(body)).hexdigest() for body in bodies[:32]] != predecessor_requests:
        raise SystemExit("c64 request prefix does not match authoritative c32 request identities")

    def science_started():
        write_json(args.output / "SCIENCE_STARTED.json", {
            "schema_version": 1,
            "arm": "dynamic_fp8_c64_saturation",
            "binding_sha256": digest(args.binding),
            "requests": 64,
            "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    barrier = threading.Barrier(64, action=science_started)
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as executor:
        rows = list(executor.map(lambda pair: request_one(pair, f"http://{args.host}:{args.port}", args.output, barrier), enumerate(bodies)))
    batch_seconds = time.monotonic() - started
    complete = all(
        row["error"] is None
        and row["prompt_tokens"] == 4214
        and row["completion_tokens"] == 358
        and row["returned_token_ids"] == 358
        and row["nonempty"]
        and math.isfinite(row["seconds"])
        for row in rows
    )
    write_json(args.output / "TERMINAL.json", {
        "schema_version": 1,
        "classification": "endpoint_measurement" if complete else "endpoint_invalid",
        "arm": "dynamic_fp8_c64_saturation",
        "complete_requests": sum(row["error"] is None for row in rows),
        "service_seconds_per_request": batch_seconds / 64,
        "batch_seconds": batch_seconds,
        "rows": rows,
        "identity": identities,
        "binding_sha256": digest(args.binding),
    })


if __name__ == "__main__":
    main()
