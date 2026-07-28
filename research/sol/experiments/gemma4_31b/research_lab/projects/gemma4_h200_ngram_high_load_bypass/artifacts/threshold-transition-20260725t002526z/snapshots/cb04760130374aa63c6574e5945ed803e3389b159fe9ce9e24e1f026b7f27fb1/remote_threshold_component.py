#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.request


ROOT = Path("/home/glmrunner/gemma4-h200-ngram-high-load-bypass")
OUT = ROOT / "threshold-metrics-guarded"
BOUND = ROOT / "bound_inputs"
CONTROL = BOUND / "inputs/control"
COMPARATOR = BOUND / "comparator.requests.jsonl"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
CHECKPOINT = (
    "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint"
)
CONTAINER = "gemma4-ngram-high-load-bypass-candidate"
MODEL = "google/gemma-4-31B-it"
COMPONENT_BEGIN = 791
COMPONENT_REQUESTS = 8
SUFFIX_END = 871
ARRIVAL_SPACING = 0.6946101132986054
LOG_LOCK = threading.Lock()


def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run(args: list[str], timeout: int | None = None):
    return subprocess.run(
        args, text=True, capture_output=True, check=False, timeout=timeout
    )


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(16 * 1024 * 1024):
            value.update(block)
    return value.hexdigest()


def capture_server_error(reason: str) -> None:
    with LOG_LOCK:
        result = run(["sudo", "docker", "logs", CONTAINER], timeout=120)
        (OUT / "SERVER_STDOUT_STDERR.log").write_text(
            result.stdout + result.stderr
        )
        atomic(
            OUT / "SERVER_ERROR_CAPTURE.json",
            {
                "reason": reason,
                "returncode": result.returncode,
                "captured_at_unix": time.time(),
                "log_sha256": sha256(OUT / "SERVER_STDOUT_STDERR.log"),
            },
        )


def launch() -> list[str]:
    frozen = json.loads((CONTROL / "launch-5000.json").read_text())["cmd"]
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
        "PYTHONPATH=/work/candidate:/work/bound_inputs",
        "-e",
        "HIGH_LOAD_BYPASS_OUT=/work/threshold-metrics-guarded",
        "-e",
        "SPARSE_PENALTY_OUT=/work/threshold-metrics-guarded",
        "-v",
        f"{ROOT}:/work",
        "-v",
        f"{CHECKPOINT}:/work/checkpoint:ro",
        IMAGE,
        "python3",
        "-m",
        "sglang.launch_server",
        *server_args,
    ]
    result = run(command, timeout=120)
    atomic(
        OUT / "LAUNCH.json",
        {
            "server_args": server_args,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    if result.returncode:
        raise RuntimeError("component_server_launch_failed")
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
    capture_server_error("server_not_ready")
    raise RuntimeError("component_server_not_ready")


def native_request(prompt: list[int]) -> bytes:
    return json.dumps(
        {
            "input_ids": prompt,
            "sampling_params": {
                "temperature": 0,
                "max_new_tokens": 358,
                "min_new_tokens": 358,
                "ignore_eos": True,
            },
        },
        separators=(",", ":"),
    ).encode()


def post(prompt: list[int]) -> tuple[dict, float]:
    request = urllib.request.Request(
        "http://127.0.0.1:30000/generate",
        native_request(prompt),
        {"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=120) as response:
        value = json.loads(response.read())
    return value, time.monotonic() - started


def normalize(value: dict, prompt_tokens: int) -> dict:
    meta = value.get("meta_info") or {}
    output_ids = (
        value.get("output_ids")
        or meta.get("output_ids")
        or meta.get("completion_token_ids")
    )
    usage = {
        "prompt_tokens": meta.get("prompt_tokens", prompt_tokens),
        "completion_tokens": meta.get("completion_tokens", 358),
        "total_tokens": meta.get("prompt_tokens", prompt_tokens)
        + meta.get("completion_tokens", 358),
    }
    return {
        "output_ids": output_ids,
        "finish_reason": meta.get("finish_reason") or value.get("finish_reason"),
        "usage": usage,
    }


def execute(index: int, prompt: list[int], comparator: dict) -> dict:
    started = time.monotonic()
    try:
        value, latency = post(prompt)
        normalized = normalize(value, len(prompt))
        return {
            "i": index,
            "latency_seconds": latency,
            **normalized,
            "output_ids_match_control": (
                normalized["output_ids"] == comparator["output_ids"]
            ),
            "finish_reason_matches_control": (
                normalized["finish_reason"] == comparator["finish_reason"]
            ),
            "usage_matches_control": normalized["usage"] == comparator["usage"],
        }
    except Exception as exc:
        capture_server_error(f"request_{index}:{type(exc).__name__}")
        return {
            "i": index,
            "elapsed_seconds": time.monotonic() - started,
            "error": repr(exc),
        }


def events() -> list[dict]:
    path = OUT / "HIGH_LOAD_BYPASS_EVENTS.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text().splitlines() if line.strip()
    ]


def summarize(selected: list[dict]) -> dict:
    steps = [value for value in selected if value["kind"] == "decode_step"]
    bypass = [
        value
        for value in steps
        if value["mode"] == "ordinary_greedy_target_decode"
    ]
    full_ngram_rows = sum(value["batch_size"] * 12 for value in steps)
    target_rows = sum(value["target_rows"] for value in steps)
    invariant_fields = (
        "req_to_token_matches_out_cache_loc",
        "input_ids_match_authoritative_request_tokens",
    )
    return {
        "events": len(selected),
        "decode_steps": len(steps),
        "bypass_steps": len(bypass),
        "ngram_steps": len(steps) - len(bypass),
        "target_rows": target_rows,
        "full_ngram_target_rows": full_ngram_rows,
        "target_rows_saved": full_ngram_rows - target_rows,
        "bypass_invariants": all(
            value["spec_algorithm_after"].endswith("NONE")
            and value["spec_info_after"] is None
            and value["input_ids_after"] == value["batch_size"]
            and value["allocated_cache_slots"] == value["batch_size"]
            and value["unique_cache_slots"] == value["batch_size"]
            and value["accept_lens"] is None
            and all(value[field] for field in invariant_fields)
            for value in bypass
        ),
        "first_bypass": bypass[0] if bypass else None,
    }


def exact_rows(rows: list[dict]) -> bool:
    return bool(rows) and all(
        "error" not in row
        and row["output_ids_match_control"]
        and row["finish_reason_matches_control"]
        and row["usage_matches_control"]
        for row in rows
    )


def run_component(
    prompt: list[int], comparators: list[dict]
) -> tuple[list[dict], dict]:
    barrier = threading.Barrier(COMPONENT_REQUESTS)

    def one(offset: int) -> dict:
        barrier.wait()
        index = COMPONENT_BEGIN + offset
        return execute(index, prompt, comparators[index])

    atomic(
        OUT / "COMPONENT_SCIENCE_STARTED.json",
        {
            "candidate_cuda_expected": True,
            "requests": COMPONENT_REQUESTS,
            "threshold": 8,
        },
    )
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=COMPONENT_REQUESTS
    ) as executor:
        rows = list(executor.map(one, range(COMPONENT_REQUESTS)))
    telemetry = summarize(events())
    passed = (
        exact_rows(rows)
        and telemetry["bypass_steps"] >= 1
        and telemetry["target_rows_saved"] > 0
        and telemetry["bypass_invariants"]
    )
    terminal = {
        "schema_version": 1,
        "result": "exact_positive_threshold_component" if passed else "component_reject",
        "passed": passed,
        "rows": rows,
        "telemetry": telemetry,
    }
    atomic(OUT / "COMPONENT_TERMINAL.json", terminal)
    return rows, terminal


def run_suffix(
    prompt: list[int], comparators: list[dict], event_offset: int
) -> dict:
    origin = time.monotonic()

    def one(index: int) -> dict:
        scheduled = (index - COMPONENT_BEGIN) * ARRIVAL_SPACING
        delay = origin + scheduled - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        row = execute(index, prompt, comparators[index])
        row["scheduled_s"] = scheduled
        row["completed_s"] = time.monotonic() - origin
        return row

    atomic(
        OUT / "SUFFIX_SCIENCE_STARTED.json",
        {
            "begin": COMPONENT_BEGIN,
            "end_exclusive": SUFFIX_END,
            "settled_prefix_replayed": False,
        },
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
        rows = list(executor.map(one, range(COMPONENT_BEGIN, SUFFIX_END)))
    selected = events()[event_offset:]
    telemetry = summarize(selected)
    exact = exact_rows(rows)
    terminal = {
        "schema_version": 1,
        "result": "exact_suffix" if exact else "suffix_reject",
        "exact": exact,
        "scheduled": len(rows),
        "completed": sum("error" not in row for row in rows),
        "exact_rows": sum(
            "error" not in row
            and row["output_ids_match_control"]
            and row["finish_reason_matches_control"]
            and row["usage_matches_control"]
            for row in rows
        ),
        "persisted_exact_prefix_rows": 791,
        "combined_exact_rows": 791 + len(rows) if exact else None,
        "settled_prefix_replayed": False,
        "rows": rows,
        "telemetry": telemetry,
    }
    atomic(OUT / "SUFFIX_TERMINAL.json", terminal)
    return terminal


def main() -> None:
    if OUT.exists():
        raise RuntimeError("threshold_transition_output_already_exists")
    OUT.mkdir(parents=True)
    comparators = [
        json.loads(line) for line in COMPARATOR.read_text().splitlines() if line
    ]
    trace = json.loads((CONTROL / "TRACE_PACKET.json").read_text())
    group = next(
        value for value in trace["primary_groups"] if value["name"] == "primary_c1"
    )
    prompt = group["scored"][0]["request_body"]["prompt"]
    if len(comparators) != 1036 or len(prompt) != 4214:
        raise RuntimeError("bound_input_identity_mismatch")

    run(["sudo", "docker", "rm", "-f", CONTAINER], timeout=120)
    launch()
    waiter = subprocess.Popen(
        ["sudo", "docker", "wait", CONTAINER],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def watch_server() -> None:
        stdout, stderr = waiter.communicate()
        atomic(
            OUT / "SERVER_EXIT.json",
            {"stdout": stdout, "stderr": stderr, "at_unix": time.time()},
        )
        capture_server_error("container_exit")

    threading.Thread(target=watch_server, daemon=True).start()
    wait_server()
    component_rows, component = run_component(prompt, comparators)
    event_offset = len(events())
    suffix = (
        run_suffix(prompt, comparators, event_offset)
        if component["passed"]
        else None
    )
    capture_server_error("post_measurement_snapshot")
    final = {
        "schema_version": 1,
        "result": (
            "exact_component_and_suffix"
            if suffix is not None and suffix["exact"]
            else component["result"]
            if suffix is None
            else suffix["result"]
        ),
        "component": component,
        "suffix": suffix,
        "component_rows_sha256": hashlib.sha256(
            json.dumps(
                component_rows, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        "comparator_sha256": sha256(COMPARATOR),
        "candidate_sha256": sha256(ROOT / "candidate/high_load_bypass.py"),
        "persisted_prefix_snapshot": (
            "c09b906cb9aee3fb68705ca9c7bbd4bbd11c45d3c685a4c01c3df2cdfcfc2103"
        ),
        "settled_prefix_replayed": False,
        "full_endpoint_started": False,
    }
    atomic(OUT / "FINAL_TERMINAL.json", final)


if __name__ == "__main__":
    main()
