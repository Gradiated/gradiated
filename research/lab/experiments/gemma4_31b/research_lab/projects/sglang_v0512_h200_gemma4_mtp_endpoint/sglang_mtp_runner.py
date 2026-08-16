#!/usr/bin/env python3
"""Run one exact c32 trace arm against a resident SGLang endpoint."""
import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import threading
import time
import urllib.error
import urllib.request


def request(body, path, barrier):
    barrier.wait()
    body = {**body, "stream": False}
    raw = json.dumps(body, separators=(",", ":")).encode()
    started = time.monotonic()
    try:
        reply = urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:30000/v1/completions", raw, {"Content-Type": "application/json"}), timeout=1800).read()
        parsed, error = json.loads(reply), None
    except Exception as exc:
        reply, parsed, error = b"", {}, repr(exc)
    choice = (parsed.get("choices") or [{}])[0]
    text = choice.get("text", "")
    usage = parsed.get("usage", {})
    row = {"request_sha256": hashlib.sha256(raw).hexdigest(), "response_sha256": hashlib.sha256(reply).hexdigest(), "output_id": hashlib.sha256(text.encode()).hexdigest(), "error": error, "wall_seconds": time.monotonic() - started, "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"), "text_nonempty": bool(text), "raw_response": parsed}
    path.write_text(json.dumps(row, sort_keys=True) + "\n")
    return row


def get(path, url):
    try:
        path.write_bytes(urllib.request.urlopen(url, timeout=30).read())
    except Exception as exc:
        path.with_suffix(path.suffix + ".error").write_text(repr(exc))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--arm", choices=("stock", "mtp"), required=True)
    args = parser.parse_args()
    trace = json.loads(pathlib.Path(args.trace).read_text())
    group = next(item for item in trace["primary_groups"] if item["concurrency"] == 16)
    bodies = [item["request_body"] for item in group["scored"] * 2]
    args.output.mkdir(parents=True, exist_ok=True)
    get(args.output / "metrics-before.prom", "http://127.0.0.1:30000/metrics")
    barrier = threading.Barrier(32)
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        rows = list(pool.map(lambda pair: request(pair[1], args.output / f"request-{pair[0]:02d}.json", barrier), enumerate(bodies)))
    elapsed = time.monotonic() - started
    get(args.output / "metrics-after.prom", "http://127.0.0.1:30000/metrics")
    valid = all(not row["error"] and row["text_nonempty"] and row["prompt_tokens"] == 4214 and row["completion_tokens"] == 358 for row in rows)
    terminal = {"classification": f"sglang_v0512_{args.arm}_c32", "arm": args.arm, "pass": valid, "complete_requests": sum(not row["error"] for row in rows), "required_requests": 32, "batch_seconds": elapsed, "service_seconds_per_request": elapsed / 32, "completed_requests_per_second": 32 / elapsed, "market_pass": valid and elapsed / 32 <= 0.47201182295214134, "rows": [{key: row[key] for key in ("request_sha256", "response_sha256", "output_id", "error", "wall_seconds", "prompt_tokens", "completion_tokens", "text_nonempty")} for row in rows]}
    (args.output / "TERMINAL.json").write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
    raise SystemExit(0 if valid else 72)


if __name__ == "__main__":
    main()
