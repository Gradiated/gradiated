#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import urllib.request


BASE = "http://127.0.0.1:30000"
ROOT = pathlib.Path("/work/artifacts/qserve-causal-trace")
CONTROL = ROOT / "TRACE_CONTROL.json"
EVENTS = ROOT / "trace-events.jsonl"


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def post(path: str, body: dict[str, object], timeout: int = 1800) -> tuple[dict, bytes]:
    raw_body = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    request = urllib.request.Request(
        BASE + path,
        data=raw_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    try:
        parsed = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        parsed = {"raw_text": raw.decode("utf-8", errors="replace")}
    return parsed, raw


def output_ids(response: dict) -> list[int]:
    values = (response.get("meta_info") or {}).get("output_ids") or response.get(
        "output_ids"
    )
    if not isinstance(values, list) or not all(isinstance(value, int) for value in values):
        raise ValueError("native response omitted output token IDs")
    return values


def event_counts(run_id: str) -> dict[str, int]:
    routes: dict[str, int] = {}
    for line in EVENTS.read_text().splitlines():
        event = json.loads(line)
        if event.get("event") != "layer_route" or event.get("run_id") != run_id:
            continue
        route = str(event["route"])
        routes[route] = routes.get(route, 0) + 1
    return routes


def main() -> int:
    trace = json.loads((ROOT / "TRACE_TERMINAL_NORMALIZED.json").read_text())
    target = trace["first_divergent_target"]
    row = next(item for item in trace["rows"] if int(item["depth"]) == int(target["depth"]))
    run_id = "oracle-capture-corrected"
    atomic(
        CONTROL,
        {
            "schema_version": 1,
            "run_id": run_id,
            "depth": int(target["depth"]),
            "capture_layer": int(target["layer"]),
            "capture_step": int(target["decode_step"]),
        },
    )
    post("/flush_cache", {}, timeout=60)
    response, raw = post("/generate", row["request"])
    ids = output_ids(response)
    result = {
        "schema_version": 1,
        "target": target,
        "response": response,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "output_ids": ids,
        "matches_trace_row": ids == row["output_ids"],
        "path_counts": {"routes": event_counts(run_id)},
        "producer_rows_replayed": False,
        "consumer_repair": "corrected prompt-prefill/decode step offset only",
    }
    atomic(ROOT / "ORACLE_CAPTURE_REQUEST.json", result)
    if not (ROOT / "captured-hidden.pt").is_file():
        raise RuntimeError("corrected capture request did not persist hidden state")
    if not result["matches_trace_row"]:
        raise RuntimeError("corrected capture request was nondeterministic")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
