#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import time
import urllib.request


MODEL = "google/gemma-4-31B-it"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
CONTROL_CONTAINER = "gemma4-packed-m384-control"
CANDIDATE_CONTAINER = "gemma4-packed-m384-candidate"
EXPECTED_CACHE = {"uncached_prompt_tokens_delta": 117728, "cached_prompt_tokens_delta": 17120}
BASE_ARGS = [
    "--model-path",
    "/work/checkpoint",
    "--tokenizer-path",
    "/work/checkpoint",
    "--served-model-name",
    MODEL,
    "--dtype",
    "bfloat16",
    "--quantization",
    "fp8",
    "--tp-size",
    "1",
    "--kv-cache-dtype",
    "fp8_e5m2",
    "--host",
    "0.0.0.0",
    "--context-length",
    "5000",
    "--max-running-requests",
    "32",
    "--mem-fraction-static",
    "0.85",
    "--enable-metrics",
    "--skip-server-warmup",
    "--enable-dynamic-chunking",
    "--chunked-prefill-size",
    "2048",
    "--enable-fused-qk-norm-rope",
    "--cuda-graph-max-bs",
    "32",
    "--prefill-attention-backend",
    "triton",
    "--decode-attention-backend",
    "triton",
    "--page-size",
    "1",
    "--num-continuous-decode-steps",
    "1",
    "--triton-attention-num-kv-splits",
    "8",
    "--tool-call-parser",
    "gemma4",
    "--port",
    "30000",
    "--speculative-algorithm",
    "NGRAM",
]


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    args: list[str], *, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def docker(*args: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return run(["sudo", "-n", "docker", *args], timeout=timeout)


def remaining(deadline_epoch: float, maximum: float) -> float:
    value = min(maximum, deadline_epoch - time.time())
    if value <= 0:
        raise TimeoutError("absolute_deadline_reached")
    return value


def verify_inputs(root: pathlib.Path, manifest_path: pathlib.Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    observed: dict[str, dict] = {}
    for row in manifest["packet_files"] + manifest["checkpoint_files"]:
        path = root / row["path"]
        if not path.is_file() or path.stat().st_size != row["bytes"]:
            raise RuntimeError(f"input_size_mismatch:{row['path']}")
        digest = sha256(path)
        if digest != row["sha256"]:
            raise RuntimeError(f"input_hash_mismatch:{row['path']}:{digest}")
        observed[row["path"]] = {"bytes": path.stat().st_size, "sha256": digest}
    image = docker("image", "inspect", IMAGE, "--format", "{{json .RepoDigests}}")
    if image.returncode:
        raise RuntimeError(f"image_identity_unavailable:{image.stderr[-1000:]}")
    return {"files": observed, "image_inspect": image.stdout.strip()}


def write_launch_state(root: pathlib.Path, arm: str, value: dict) -> None:
    atomic(root / "artifacts" / f"{arm}.launch-state.json", value)


def start_server(
    root: pathlib.Path, arm: str, container: str, deadline_epoch: float
) -> None:
    artifacts = root / "artifacts"
    docker("rm", "-f", container, timeout=30)
    environment = [
        "-e",
        "PYTHONPATH=/work/input:/sgl-workspace/sglang/python",
        "-e",
        "DECODE_EQ_LM_HEAD=1",
        "-e",
        f"DECODE_EQ_AUDIT=/work/artifacts/{arm}.decode-eq.jsonl",
        "-e",
        f"TOKEN_TRACE_EVENTS=/work/artifacts/{arm}.token-events.jsonl",
        "-e",
        f"FP8_MODULE_AUDIT=/work/artifacts/{arm}.fp8-modules.jsonl",
        "-e",
        f"FP8_CONSUMER_AUDIT=/work/artifacts/{arm}.fp8-consumers.jsonl",
        "-e",
        f"FP8_RUNTIME_AUDIT=/work/artifacts/{arm}.fp8-runtime.json",
        "-e",
        f"PACKED_M384_ENDPOINT_ARM={arm}",
        "-e",
        f"PACKED_M384_ROUTE_AUDIT=/work/artifacts/{arm}.route.jsonl",
        "-e",
        f"PACKED_M384_AUDIT=/work/artifacts/{arm}.candidate.jsonl",
    ]
    result = docker(
        "run",
        "-d",
        "--name",
        container,
        "--gpus",
        "all",
        "--ipc=host",
        "--network",
        "host",
        "-v",
        f"{root}:/work",
        *environment,
        IMAGE,
        "python3",
        "/work/input/endpoint_entrypoint.py",
        *BASE_ARGS,
        timeout=remaining(deadline_epoch, 60),
    )
    write_launch_state(
        root,
        arm,
        {
            "arm": arm,
            "container": container,
            "launch_attempted": True,
            "returncode": result.returncode,
            "stderr": result.stderr[-4000:],
            "stdout": result.stdout[-4000:],
        },
    )
    if result.returncode:
        raise RuntimeError(f"server_launch_failed:{arm}:{result.stderr[-1000:]}")
    while remaining(deadline_epoch, 5) > 0:
        state = docker("inspect", container, "--format", "{{.State.Running}} {{.State.ExitCode}}")
        if state.returncode or not state.stdout.startswith("true "):
            logs = docker("logs", container)
            (artifacts / f"{arm}.server.log").write_text(
                logs.stdout + "\n--- stderr ---\n" + logs.stderr
            )
            raise RuntimeError(f"server_exited_before_ready:{arm}:{state.stdout.strip()}")
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:30000/v1/models", timeout=3
            ) as response:
                if MODEL in response.read().decode():
                    runtime = artifacts / f"{arm}.fp8-runtime.json"
                    if not runtime.is_file():
                        raise RuntimeError(f"runtime_audit_missing:{arm}")
                    return
        except RuntimeError:
            raise
        except Exception:
            time.sleep(2)
    raise TimeoutError(f"server_readiness_timeout:{arm}")


def run_arm(
    root: pathlib.Path, arm: str, container: str, deadline_epoch: float
) -> dict:
    artifacts = root / "artifacts"
    output = artifacts / arm
    if output.exists():
        raise RuntimeError(f"arm_output_already_exists:{arm}")
    state_path = artifacts / "INVOCATION_STATE.json"
    state = json.loads(state_path.read_text())
    state[f"{arm}_science_started"] = True
    atomic(state_path, state)
    atomic(
        artifacts / f"{arm}.science-started.json",
        {
            "arm": arm,
            "container": container,
            "science_started": True,
            "stage": "immediately_before_exact_c32_request_submission",
            "time_epoch": time.time(),
        },
    )
    command = [
        "exec",
        container,
        "python3",
        "/work/input/exact_runner.py",
        "--output",
        f"/work/artifacts/{arm}",
        "--arm",
        arm,
        "--concurrency",
        "32",
    ]
    process = subprocess.Popen(
        ["sudo", "-n", "docker", *command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    while process.poll() is None:
        if time.time() >= deadline_epoch:
            process.terminate()
            raise TimeoutError(f"arm_deadline:{arm}")
        state = docker("inspect", container, "--format", "{{.State.Running}} {{.State.ExitCode}}")
        if state.returncode or not state.stdout.startswith("true "):
            process.terminate()
            stdout, stderr = process.communicate(timeout=10)
            (artifacts / f"{arm}.runner.stdout").write_text(stdout)
            (artifacts / f"{arm}.runner.stderr").write_text(stderr)
            raise RuntimeError(f"server_exited_during_arm:{arm}:{state.stdout.strip()}")
        time.sleep(2)
    stdout, stderr = process.communicate()
    (artifacts / f"{arm}.runner.stdout").write_text(stdout)
    (artifacts / f"{arm}.runner.stderr").write_text(stderr)
    terminal_path = output / "TERMINAL.json"
    if not terminal_path.is_file():
        raise RuntimeError(f"arm_terminal_missing:{arm}:{process.returncode}")
    terminal = json.loads(terminal_path.read_text())
    if process.returncode not in (0, 72):
        raise RuntimeError(f"arm_runner_failed:{arm}:{process.returncode}")
    return terminal


def stop_control(root: pathlib.Path) -> None:
    logs = docker("logs", CONTROL_CONTAINER)
    (root / "artifacts" / "control.server.log").write_text(
        logs.stdout + "\n--- stderr ---\n" + logs.stderr
    )
    result = docker("rm", "-f", CONTROL_CONTAINER, timeout=30)
    if result.returncode:
        raise RuntimeError(f"control_stop_failed:{result.stderr[-1000:]}")


def jsonl(path: pathlib.Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def sse_tokens(root: pathlib.Path) -> list[list[int]]:
    values: list[list[int]] = []
    for path in sorted(root.glob("response-*.sse")):
        tokens: list[int] = []
        for line in path.read_bytes().splitlines():
            if not line.startswith(b"data: ") or line.strip() == b"data: [DONE]":
                continue
            value = json.loads(line[6:])
            tokens.extend((value.get("choices") or [{}])[0].get("token_ids") or [])
        values.append(tokens)
    return values


def trace_projection(path: pathlib.Path) -> list[dict]:
    deltas: dict[str, list[int]] = {}
    finals: list[dict] = []
    for row in jsonl(path):
        rid = row.get("rid")
        if row.get("stage") == "scheduler_to_detokenizer":
            deltas.setdefault(rid, []).extend(row["scheduler_output_ids_delta"])
        elif row.get("stage") == "post_generation_pre_parser_final":
            finals.append(
                {
                    "completion_counter": row.get("completion_counter"),
                    "emitted_token_ids": deltas.get(rid, []),
                    "finish_reason": row.get("finish_reason"),
                    "parser_input_utf8_hex": row.get("parser_input_utf8_hex"),
                    "prompt_tokens": row.get("prompt_tokens"),
                }
            )
    return sorted(finals, key=lambda value: json.dumps(value, sort_keys=True))


def valid_arm(terminal: dict) -> bool:
    cache = terminal.get("cache", {})
    return bool(
        terminal.get("pass")
        and terminal.get("complete_requests") == 32
        and len(terminal.get("rows", [])) == 32
        and all(cache.get(key) == value for key, value in EXPECTED_CACHE.items())
        and all(row.get("returned_token_ids") == 358 for row in terminal["rows"])
    )


def consume(
    root: pathlib.Path, control: dict, candidate: dict, input_identity: dict
) -> dict:
    artifacts = root / "artifacts"
    control_tokens = sse_tokens(artifacts / "control")
    candidate_tokens = sse_tokens(artifacts / "candidate")
    control_trace = trace_projection(artifacts / "control.token-events.jsonl")
    candidate_trace = trace_projection(artifacts / "candidate.token-events.jsonl")
    routes = jsonl(artifacts / "candidate.route.jsonl")
    candidate_calls = [row for row in routes if row.get("route") == "candidate"]
    rejected = [row for row in routes if row.get("route") == "rejected_no_fallback"]
    local_calls = sum(bool(row.get("local")) for row in candidate_calls)
    global_calls = sum(bool(row.get("global")) for row in candidate_calls)
    dispatch = jsonl(artifacts / "candidate.candidate.jsonl")
    local_dispatch = sum(row.get("kind") == "local_d256" for row in dispatch)
    global_dispatch = sum(row.get("kind") == "global_d512" for row in dispatch)
    request_hashes_exact = [
        row["request_sha256"] for row in control.get("rows", [])
    ] == [row["request_sha256"] for row in candidate.get("rows", [])]
    tokens_exact = (
        len(control_tokens) == 32
        and control_tokens == candidate_tokens
        and all(len(row) == 358 for row in control_tokens)
    )
    trace_exact = (
        len(control_trace) == 32
        and control_trace == candidate_trace
        and all(
            row["completion_counter"] == len(row["emitted_token_ids"]) == 358
            for row in control_trace
        )
    )
    routing_exact = bool(
        not rejected
        and local_calls > 0
        and global_calls > 0
        and local_calls == local_dispatch
        and global_calls == global_dispatch
        and local_calls == 5 * global_calls
        and local_calls % 50 == 0
        and global_calls % 10 == 0
    )
    gates = {
        "candidate_no_fallback_and_exact_50_10_routing": routing_exact,
        "cache_accounting_exact": valid_arm(control) and valid_arm(candidate),
        "complete_finite_nonempty_rows": valid_arm(control) and valid_arm(candidate),
        "exact_request_hashes": request_hashes_exact,
        "exact_sse_target_tokens": tokens_exact,
        "exact_target_to_emitted_trace": trace_exact,
    }
    valid = all(gates.values())
    control_seconds = control.get("service_seconds_per_request")
    candidate_seconds = candidate.get("service_seconds_per_request")
    reduction = (
        None
        if control_seconds is None or candidate_seconds is None
        else 1.0 - candidate_seconds / control_seconds
    )
    classification = (
        "semantic_or_path_reject"
        if not valid
        else "endpoint_positive"
        if reduction is not None and reduction > 0
        else "endpoint_nonpositive"
    )
    return {
        "schema_version": 1,
        "type": "packed_m384_matched_c32_endpoint_terminal",
        "classification": classification,
        "pass": valid,
        "gates": gates,
        "identity": input_identity,
        "control": control,
        "candidate": candidate,
        "control_service_seconds_per_request": control_seconds,
        "candidate_service_seconds_per_request": candidate_seconds,
        "service_reduction_fraction": reduction,
        "complete_request_throughput": {
            "control": control.get("complete_request_throughput"),
            "candidate": candidate.get("complete_request_throughput"),
        },
        "routing": {
            "candidate_local_calls": local_calls,
            "candidate_global_calls": global_calls,
            "dispatch_local_calls": local_dispatch,
            "dispatch_global_calls": global_dispatch,
            "rejected_target_calls": len(rejected),
        },
        "candidate_server": {
            "container": CANDIDATE_CONTAINER,
            "port": 30000,
            "retained": True,
            "release_condition": "maintenance_unless_director_names_compatible_successor",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--absolute-deadline-epoch", type=float, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    identity = verify_inputs(root, args.manifest.resolve())
    atomic(
        artifacts / "INVOCATION_STATE.json",
        {
            "candidate_science_started": False,
            "control_science_started": False,
            "identity_validated": True,
        },
    )
    control_path = artifacts / "control" / "TERMINAL.json"
    if control_path.is_file():
        control = json.loads(control_path.read_text())
        if not valid_arm(control):
            raise RuntimeError("persisted_control_invalid")
    else:
        start_server(root, "control", CONTROL_CONTAINER, args.absolute_deadline_epoch)
        control = run_arm(
            root, "control", CONTROL_CONTAINER, args.absolute_deadline_epoch
        )
        stop_control(root)
    atomic(
        artifacts / "CONTROL_PRODUCER_STAGE.json",
        {"control": control, "persisted": True, "valid": valid_arm(control)},
    )
    start_server(root, "candidate", CANDIDATE_CONTAINER, args.absolute_deadline_epoch)
    candidate = run_arm(
        root, "candidate", CANDIDATE_CONTAINER, args.absolute_deadline_epoch
    )
    terminal = consume(root, control, candidate, identity)
    atomic(artifacts / "ENDPOINT_TERMINAL.json", terminal)
    atomic(
        artifacts / "RESIDENT_SERVER.json",
        terminal["candidate_server"],
    )
    return 0 if terminal["pass"] else 74


if __name__ == "__main__":
    raise SystemExit(main())
