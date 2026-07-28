#!/usr/bin/env python3
"""Construct and consume the bound fresh endpoint workload on a live server."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.request
import math


ROOT = Path(os.environ.get("FRESH_ENDPOINT_ROOT", ".")).resolve()
PACKET = ROOT / "inputs/fresh_endpoint_packet/candidate-v0.5.15/inputs"
RUN = ROOT / "artifacts/fresh-endpoint"
MODEL = "google/gemma-4-31B-it"
COUNT = 791
START = int(os.environ.get("FRESH_START", "62000"))
END = int(os.environ.get("FRESH_END", "62790"))


def json_safe(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def compact(value: object, sort: bool = False) -> bytes:
    return json.dumps(json_safe(value), separators=(",", ":"), sort_keys=sort, allow_nan=False).encode()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")
    part.replace(path)


def template() -> dict[str, object]:
    trace = json.loads((PACKET / "TRACE_PACKET.json").read_text())
    return next(row for row in trace["primary_groups"] if row["name"] == "primary_c1")["scored"][0]["request_body"]


def make_body(base: dict[str, object], synthetic_index: int) -> dict[str, object]:
    body = json.loads(json.dumps(base))
    body.update({"model": MODEL, "ignore_eos": True, "min_tokens": 358, "max_tokens": 358, "request_id": f"tail-overlap-{synthetic_index}"})
    prompt = list(body["prompt"])
    if len(prompt) != 4214:
        raise RuntimeError(f"template_prompt_length:{len(prompt)}")
    prompt[535] = 200000 + synthetic_index
    body["prompt"] = prompt
    return body


def construct() -> None:
    rows = [json.loads(line) for line in (PACKET / "exact_semantic_rows.jsonl").read_text().splitlines()[:COUNT]]
    if [row["i"] for row in rows] != list(range(COUNT)):
        raise RuntimeError("arrival_row_identity")
    if any(rows[i]["arrival_s"] > rows[i + 1]["arrival_s"] for i in range(COUNT - 1)):
        raise RuntimeError("arrival_order")
    base = template()
    fresh = []
    for row in rows:
        index = START + row["i"]
        body = make_body(base, index)
        fresh.append({
            "source_i": row["i"],
            "fresh_index": index,
            "arrival_s": row["arrival_s"],
            "request_body": body,
            "prompt_sha256": sha_bytes(compact(body["prompt"])),
            "request_sha256": sha_bytes(compact(body, True)),
        })
    if [row["fresh_index"] for row in fresh] != list(range(START, END + 1)):
        raise RuntimeError("fresh_index_interval")
    if len({row["prompt_sha256"] for row in fresh}) != COUNT or len({row["request_sha256"] for row in fresh}) != COUNT:
        raise RuntimeError("fresh_hash_uniqueness")
    historical_indices = list(range(1036)) + list(range(60000, 60004)) + list(range(61000, 61791)) + list(range(62000, 62791))
    historical = {sha_bytes(compact(make_body(base, index)["prompt"])) for index in historical_indices}
    fresh_prompts = {row["prompt_sha256"] for row in fresh}
    if historical & fresh_prompts:
        raise RuntimeError("novelty_intersection")
    if any(index in set(range(1036)) | set(range(60000, 60004)) | set(range(61000, 61791)) | set(range(62000, 62791)) for index in range(START, END + 1)):
        raise RuntimeError("novelty_index_intersection")
    RUN.mkdir(parents=True, exist_ok=True)
    output = RUN / "FRESH_WORKLOAD.jsonl"
    part = output.with_suffix(output.suffix + ".part")
    part.write_bytes(b"".join(compact(row, True) + b"\n" for row in fresh))
    parsed = [json.loads(line) for line in part.read_text().splitlines()]
    if parsed != fresh:
        raise RuntimeError("atomic_workload_validation")
    part.replace(output)
    atomic(RUN / "FRESH_WORKLOAD.json", {
        "schema_version": 1,
        "status": "complete",
        "row_count": COUNT,
        "index_interval": [START, END],
        "workload_sha256": sha_file(output),
        "prompt_hash_set_sha256": sha_bytes(compact(sorted(fresh_prompts))),
        "request_hash_set_sha256": sha_bytes(compact(sorted(row["request_sha256"] for row in fresh))),
        "trace_packet_sha256": sha_file(PACKET / "TRACE_PACKET.json"),
        "arrival_rows_sha256": sha_file(PACKET / "exact_semantic_rows.jsonl"),
        "construction_identity": sha_file(Path(__file__)),
    })


def get(path: str, timeout: float = 10) -> bytes:
    return urllib.request.urlopen(f"http://127.0.0.1:30000{path}", timeout=timeout).read()


def metrics() -> dict[str, float]:
    values: dict[str, float] = {}
    for line in get("/metrics").decode().splitlines():
        if not line or line.startswith("#") or " " not in line:
            continue
        name, raw = line.rsplit(" ", 1)
        try:
            values[name] = float(raw)
        except ValueError:
            continue
    return values


def wait_server() -> None:
    deadline = time.monotonic() + 720
    while time.monotonic() < deadline:
        try:
            models = json.loads(get("/v1/models", 4)).get("data", [])
            if MODEL in [row.get("id") for row in models]:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("server_not_ready")


def post(body: dict[str, object]) -> dict[str, object]:
    payload = {"input_ids": body["prompt"], "sampling_params": {"temperature": 0, "max_new_tokens": body["max_tokens"], "min_new_tokens": body["min_tokens"], "ignore_eos": body["ignore_eos"]}}
    request = urllib.request.Request("http://127.0.0.1:30000/generate", compact(payload), {"Content-Type": "application/json"})
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=1200) as response:
        answer = json.loads(response.read())
    meta = answer.get("meta_info") or {}
    usage = {"prompt_tokens": meta.get("prompt_tokens", len(body["prompt"])), "completion_tokens": meta.get("completion_tokens", body["max_tokens"])}
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return {"output_ids": answer.get("output_ids") or meta.get("output_ids") or meta.get("completion_token_ids"), "finish_reason": meta.get("finish_reason") or answer.get("finish_reason"), "usage": usage, "server_seconds": time.monotonic() - started}


def arm(name: str) -> None:
    marker = json.loads((RUN / "FRESH_WORKLOAD.json").read_text())
    workload_path = RUN / "FRESH_WORKLOAD.jsonl"
    if marker["status"] != "complete" or marker["workload_sha256"] != sha_file(workload_path):
        raise RuntimeError("workload_marker_invalid")
    rows = [json.loads(line) for line in workload_path.read_text().splitlines()]
    if len(rows) != COUNT or [row["fresh_index"] for row in rows] != list(range(START, END + 1)):
        raise RuntimeError("workload_rows_invalid")
    wait_server()
    origin = time.monotonic()
    telemetry: list[dict[str, object]] = []
    stop = threading.Event()

    def sample() -> None:
        while not stop.wait(0.5):
            try:
                telemetry.append({"elapsed_s": time.monotonic() - origin, "metrics": metrics()})
            except Exception as exc:
                telemetry.append({"elapsed_s": time.monotonic() - origin, "metrics_error": repr(exc)})

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    submissions = []
    results = []

    def invoke(row: dict[str, object], released: float) -> dict[str, object]:
        started = time.monotonic() - origin
        try:
            answer = post(row["request_body"])
            return {"fresh_index": row["fresh_index"], "source_i": row["source_i"], "arrival_s": row["arrival_s"], "released_s": released, "client_started_s": started, "completed_s": time.monotonic() - origin, "request_sha256": row["request_sha256"], **answer}
        except Exception as exc:
            return {"fresh_index": row["fresh_index"], "source_i": row["source_i"], "arrival_s": row["arrival_s"], "released_s": released, "error": repr(exc), "request_sha256": row["request_sha256"]}

    try:
        # The first invalid attempt lost the stock server inside fp8_scaled_mm
        # while 44 client workers were outstanding. Keep the bound arrival
        # schedule, but cap client pressure to the server's max-running=32 as
        # the localized supervision repair.
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
            futures = []
            for row in rows:
                time.sleep(max(0, origin + row["arrival_s"] - time.monotonic()))
                released = time.monotonic() - origin
                submissions.append({"fresh_index": row["fresh_index"], "planned_release_s": row["arrival_s"], "actual_release_s": released, "release_drift_seconds": released - row["arrival_s"]})
                futures.append(executor.submit(invoke, row, released))
            results = [future.result() for future in futures]
    finally:
        stop.set()
        thread.join(5)
    results.sort(key=lambda row: row["fresh_index"])
    output = RUN / f"arm_{name}"
    output.mkdir(parents=True, exist_ok=True)
    (output / "requests.jsonl").write_bytes(b"".join(compact(row, True) + b"\n" for row in results))
    (output / "telemetry.jsonl").write_bytes(b"".join(compact(row, True) + b"\n" for row in telemetry))
    failures = [row for row in results if "error" in row]
    elapsed = max((row.get("completed_s", 0) for row in results), default=0)
    total_tokens = sum(row.get("usage", {}).get("total_tokens", 0) for row in results)
    atomic(output / "ARM_RESULT.json", {"arm": name, "rows": len(results), "failures": failures, "elapsed_seconds": elapsed, "service_seconds_per_request": elapsed / COUNT if elapsed else None, "total_tokens": total_tokens, "telemetry_samples": len(telemetry), "release_drift_bounded": all(abs(row["release_drift_seconds"]) <= 0.25 for row in submissions), "request_rows_sha256": sha_file(output / "requests.jsonl"), "telemetry_sha256": sha_file(output / "telemetry.jsonl")})
    if failures:
        raise RuntimeError(f"endpoint_failures:{failures[0]}")


def compare() -> None:
    control = [json.loads(line) for line in (RUN / "arm_control/requests.jsonl").read_text().splitlines()]
    candidate = [json.loads(line) for line in (RUN / "arm_candidate/requests.jsonl").read_text().splitlines()]
    if [row["fresh_index"] for row in control] != [row["fresh_index"] for row in candidate]:
        raise RuntimeError("arm_request_identity_mismatch")
    mismatches = []
    for left, right in zip(control, candidate):
        left_semantic = {key: left.get(key) for key in ("output_ids", "finish_reason", "usage")}
        right_semantic = {key: right.get(key) for key in ("output_ids", "finish_reason", "usage")}
        if left_semantic != right_semantic:
            mismatches.append({"fresh_index": left["fresh_index"], "control": left_semantic, "candidate": right_semantic})
    c = json.loads((RUN / "arm_control/ARM_RESULT.json").read_text())
    a = json.loads((RUN / "arm_candidate/ARM_RESULT.json").read_text())
    control_telemetry = [json.loads(line) for line in (RUN / "arm_control/telemetry.jsonl").read_text().splitlines()]
    candidate_telemetry = [json.loads(line) for line in (RUN / "arm_candidate/telemetry.jsonl").read_text().splitlines()]
    atomic(RUN / "NORMALIZED_OUTPUT_COMPARISON.json", {"control_rows": len(control), "candidate_rows": len(candidate), "mismatch_count": len(mismatches), "first_mismatch": mismatches[0] if mismatches else None, "exact": not mismatches, "control_result": c, "candidate_result": a, "control_telemetry_samples": len(control_telemetry), "candidate_telemetry_samples": len(candidate_telemetry)})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("construct", "arm", "compare"))
    parser.add_argument("--arm", choices=("control", "candidate"))
    args = parser.parse_args()
    if args.mode == "construct":
        construct()
    elif args.mode == "arm":
        if not args.arm:
            raise SystemExit("--arm is required")
        arm(args.arm)
    else:
        compare()


if __name__ == "__main__":
    main()
