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
    return {"index": index, "error": error, "seconds": elapsed, "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"), "returned_token_ids": len(token_ids), "nonempty": bool(text), "request_sha256": hashlib.sha256(canonical(body)).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--requests", type=int, default=32)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    prefix = [1000 + ((j * 7919 + 17) % 48000) for j in range(535)]
    bodies = []
    for index in range(args.requests):
        suffix = [60000 + index] + [1000 + ((index * 4214 + j * 1543) % 48000) for j in range(3678)]
        bodies.append({"model": "google/gemma-4-31B-it", "prompt": prefix + suffix, "max_tokens": 358, "min_tokens": 358, "ignore_eos": True, "temperature": 0, "seed": 20260728 + index, "stream": True, "stream_options": {"include_usage": True}, "return_token_ids": True, "add_special_tokens": False})
    barrier = threading.Barrier(args.requests)
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.requests) as executor:
        rows = list(executor.map(lambda pair: request_one(pair, f"http://{args.host}:{args.port}", args.output, barrier), enumerate(bodies)))
    batch_seconds = time.monotonic() - started
    complete = all(row["error"] is None and row["prompt_tokens"] == 4214 and row["completion_tokens"] == 358 and row["returned_token_ids"] == 358 and row["nonempty"] and math.isfinite(row["seconds"]) for row in rows)
    result = {"schema_version": 1, "classification": "endpoint_measurement" if complete else "endpoint_invalid", "arm": args.arm, "complete_requests": sum(row["error"] is None for row in rows), "service_seconds_per_request": batch_seconds / args.requests, "batch_seconds": batch_seconds, "rows": rows, "identity": {"checkpoint_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4", "workload": f"c{args.requests}/4214/358/text-only/non-reasoning", "runtime_quantization": "bf16" if args.arm == "bf16_control" else "runtime_dynamic_fp8_weights"}}
    temporary = args.output / "TERMINAL.json.part"
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.output / "TERMINAL.json")


if __name__ == "__main__":
    main()
