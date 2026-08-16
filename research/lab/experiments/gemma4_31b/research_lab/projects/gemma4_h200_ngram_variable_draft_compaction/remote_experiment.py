#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import pathlib
import statistics
import subprocess
import tarfile
import time
import urllib.request
import concurrent.futures
import importlib.util


ROOT = pathlib.Path("/home/glmrunner/gemma4-ngram-variable-compaction")
INPUT = ROOT / "input"
OUT = ROOT / "artifacts"
CACHE = ROOT / "cache"
CHECKPOINT = pathlib.Path(
    "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint"
)
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
MODEL = "google/gemma-4-31B-it"
BASE = [
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
    temporary.replace(path)


def run(
    args: list[str], timeout: int | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def wait_model() -> None:
    for _ in range(360):
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:30000/v1/models", timeout=5
            ) as response:
                if MODEL in response.read().decode():
                    return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("model_readiness_timeout")


def prepare_inputs() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    with tarfile.open(INPUT / "control-runtime-snapshot.tar.gz") as archive:
        archive.extractall(INPUT, filter="data")
    for name in ("endpoint_entrypoint.py", "exact_runner.py"):
        source = INPUT / "inputs/bound" / name
        target = INPUT / name
        target.write_bytes(source.read_bytes())


def launch(arm: str, variable: bool) -> str:
    name = f"gemma-ngram-compaction-{arm}"
    run(["sudo", "docker", "rm", "-f", name])
    environment = [
        "-e",
        "PYTHONPATH=/work/input:/sgl-workspace/sglang/python",
        "-e",
        f"NGRAM_COMPACTION_EVENTS=/work/artifacts/{arm}-component-events.jsonl",
        "-e",
        f"COMPACTION_AUDIT=/work/artifacts/{arm}-lm-head.jsonl",
        "-e",
        f"FP8_MODULE_AUDIT=/work/artifacts/{arm}-fp8-modules.jsonl",
        "-e",
        f"FP8_CONSUMER_AUDIT=/work/artifacts/{arm}-fp8-consumers.jsonl",
        "-e",
        f"FP8_RUNTIME_AUDIT=/work/artifacts/{arm}-fp8-runtime.json",
    ]
    if variable:
        environment += ["-e", "VARIABLE_NGRAM_COMPACTION=1"]
    else:
        environment += ["-e", "CONTROL_DECODE_EQ_LM_HEAD=1"]
    command = (
        "tar -xzf /work/input/compaction-source-packet.tar.gz "
        "-C /sgl-workspace/sglang && "
        "python3 /work/input/endpoint_entrypoint.py "
        + " ".join(BASE)
    )
    result = run(
        [
            "sudo",
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--gpus",
            "all",
            "--ipc=host",
            "--network",
            "host",
            "-v",
            f"{ROOT}:/work",
            "-v",
            f"{INPUT}:/work/input:ro",
            "-v",
            f"{CHECKPOINT}:/work/checkpoint:ro",
            "-v",
            f"{CACHE}:/root/.cache",
            *environment,
            IMAGE,
            "bash",
            "-lc",
            command,
        ]
    )
    atomic(
        OUT / f"{arm}-launch.json",
        {
            "args": BASE,
            "returncode": result.returncode,
            "stderr": result.stderr,
            "stdout": result.stdout,
            "variable": variable,
        },
    )
    if result.returncode:
        raise RuntimeError(f"launch_failed:{arm}:{result.stderr[-1000:]}")
    wait_model()
    return name


def stop(container: str, arm: str) -> None:
    logs = run(["sudo", "docker", "logs", container], timeout=120)
    (OUT / f"{arm}-server.stdout").write_text(logs.stdout)
    (OUT / f"{arm}-server.stderr").write_text(logs.stderr)
    result = run(["sudo", "docker", "rm", "-f", container], timeout=120)
    if result.returncode:
        raise RuntimeError(f"container_stop_failed:{arm}:{result.stderr[-500:]}")
    time.sleep(3)


def exact_run(container: str, arm: str, concurrency: int) -> dict:
    output = f"/work/artifacts/{arm}-c{concurrency}"
    result = run(
        [
            "sudo",
            "docker",
            "exec",
            container,
            "python3",
            "/work/input/exact_runner.py",
            "--output",
            output,
            "--arm",
            arm,
            "--concurrency",
            str(concurrency),
        ],
        timeout=2400,
    )
    (OUT / f"{arm}-c{concurrency}.stdout").write_text(result.stdout)
    (OUT / f"{arm}-c{concurrency}.stderr").write_text(result.stderr)
    if result.returncode not in (0, 72):
        raise RuntimeError(
            f"exact_runner_failed:{arm}:c{concurrency}:{result.returncode}:"
            f"{result.stderr[-1000:]}"
        )
    return json.loads((OUT / f"{arm}-c{concurrency}/TERMINAL.json").read_text())


def mixed_run(arm: str) -> dict:
    spec = importlib.util.spec_from_file_location(
        "bound_exact_runner", INPUT / "exact_runner.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    prefix = module.tokens("common-prefix", module.COMMON_TOKENS)
    bodies = []
    for index, output_tokens in enumerate((32, 64, 96, 128)):
        suffix = module.tokens(
            f"suffix-{index}", module.PROMPT_TOKENS - module.COMMON_TOKENS
        )
        suffix[0] = 200000 + index
        bodies.append(
            {
                "model": MODEL,
                "prompt": prefix + suffix,
                "max_tokens": output_tokens,
                "min_tokens": output_tokens,
                "ignore_eos": True,
                "temperature": 0,
                "seed": 20260718,
                "stream": True,
                "stream_options": {"include_usage": True},
                "return_token_ids": True,
                "add_special_tokens": False,
            }
        )
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                "http://127.0.0.1:30000/flush_cache",
                b"{}",
                {"Content-Type": "application/json"},
            ),
            timeout=30,
        ).read()
    except Exception:
        pass

    def one(index: int) -> dict:
        time.sleep(index * 0.75)
        request = urllib.request.Request(
            "http://127.0.0.1:30000/v1/completions",
            json.dumps(
                bodies[index], sort_keys=True, separators=(",", ":")
            ).encode(),
            {"Content-Type": "application/json"},
        )
        ids = []
        usage = {}
        with urllib.request.urlopen(request, timeout=1200) as response:
            for raw in response:
                if not raw.startswith(b"data: ") or raw.strip() == b"data: [DONE]":
                    continue
                item = json.loads(raw[6:])
                choice = (item.get("choices") or [{}])[0]
                ids.extend(choice.get("token_ids") or [])
                usage = item.get("usage") or usage
        return {"index": index, "token_ids": ids, "usage": usage}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        rows = list(executor.map(one, range(4)))
    result = {
        "pass": all(
            len(row["token_ids"]) == body["max_tokens"]
            for row, body in zip(rows, bodies)
        ),
        "rows": rows,
    }
    atomic(OUT / f"{arm}-mixed.json", result)
    return result


def response_token_rows(root: pathlib.Path) -> list[list[int]]:
    rows = []
    for path in sorted(root.glob("response-*.sse")):
        ids = []
        for raw in path.read_bytes().splitlines():
            if not raw.startswith(b"data: ") or raw.strip() == b"data: [DONE]":
                continue
            item = json.loads(raw[6:])
            choice = (item.get("choices") or [{}])[0]
            ids.extend(choice.get("token_ids") or [])
        rows.append(ids)
    return rows


def events(arm: str) -> list[dict]:
    path = OUT / f"{arm}-component-events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def component_summary(
    control_terminals: dict[str, dict],
    candidate_terminals: dict[str, dict],
) -> dict:
    token_rows = {}
    exact_responses = True
    for key in ("c1", "c4"):
        left = response_token_rows(OUT / f"control-component-{key}")
        right = response_token_rows(OUT / f"candidate-component-{key}")
        token_rows[key] = {
            "control_lengths": [len(row) for row in left],
            "candidate_lengths": [len(row) for row in right],
            "exact": left == right,
        }
        exact_responses &= left == right
    control_mixed = json.loads((OUT / "control-mixed.json").read_text())
    candidate_mixed = json.loads((OUT / "candidate-mixed.json").read_text())
    mixed_tokens_exact = [
        row["token_ids"] for row in control_mixed["rows"]
    ] == [row["token_ids"] for row in candidate_mixed["rows"]]
    exact_responses &= mixed_tokens_exact
    token_rows["mixed"] = {
        "control_lengths": [
            len(row["token_ids"]) for row in control_mixed["rows"]
        ],
        "candidate_lengths": [
            len(row["token_ids"]) for row in candidate_mixed["rows"]
        ],
        "exact": mixed_tokens_exact,
    }

    control_events = events("control")
    candidate_events = events("candidate")
    control_by_shape: dict[tuple[int, ...], list[dict]] = {}
    candidate_by_shape: dict[tuple[int, ...], list[dict]] = {}
    for row in control_events:
        control_by_shape.setdefault(
            tuple(row["producer_valid_lengths"]), []
        ).append(row)
    for row in candidate_events:
        candidate_by_shape.setdefault(
            tuple(row["producer_valid_lengths"]), []
        ).append(row)

    shared_shapes = sorted(set(control_by_shape) & set(candidate_by_shape))
    shape_rows = []
    exact_top2_ids = True
    max_top2_abs_error = 0.0
    for shape in shared_shapes:
        left_rows = control_by_shape[shape]
        right_rows = candidate_by_shape[shape]
        count = min(len(left_rows), len(right_rows))
        for index in range(count):
            left = left_rows[index]
            right = right_rows[index]
            ids_exact = left["top2_ids"] == right["top2_ids"]
            exact_top2_ids &= ids_exact
            error = max(
                (
                    abs(a - b)
                    for left_pair, right_pair in zip(
                        left["top2_values"], right["top2_values"]
                    )
                    for a, b in zip(left_pair, right_pair)
                ),
                default=0.0,
            )
            max_top2_abs_error = max(max_top2_abs_error, error)
        control_ms = [row["target_forward_ms"] for row in left_rows]
        candidate_ms = [row["target_forward_ms"] for row in right_rows]
        shape_rows.append(
            {
                "shape": list(shape),
                "control_count": len(left_rows),
                "candidate_count": len(right_rows),
                "paired_count": count,
                "control_target_forward_median_ms": statistics.median(control_ms),
                "candidate_target_forward_median_ms": statistics.median(
                    candidate_ms
                ),
                "target_forward_speedup": (
                    statistics.median(control_ms)
                    / statistics.median(candidate_ms)
                    if statistics.median(candidate_ms)
                    else None
                ),
            }
        )

    observed_lengths = {
        length for row in candidate_events for length in row["producer_valid_lengths"]
    }
    mixed_observed = any(
        len(set(row["producer_valid_lengths"])) > 1 for row in candidate_events
    )
    reduced = [
        row
        for row in shape_rows
        if sum(row["shape"]) < 12 * len(row["shape"])
        and row["paired_count"] > 0
    ]
    weighted_control = sum(
        row["control_target_forward_median_ms"] for row in reduced
    )
    weighted_candidate = sum(
        row["candidate_target_forward_median_ms"] for row in reduced
    )
    positive = bool(reduced) and weighted_candidate < weighted_control
    exact_consumers = (
        exact_responses
        and exact_top2_ids
        and max_top2_abs_error == 0.0
        and all(value["pass"] for value in control_terminals.values())
        and all(value["pass"] for value in candidate_terminals.values())
        and control_mixed["pass"]
        and candidate_mixed["pass"]
    )
    coverage = 1 in observed_lengths and 12 in observed_lengths and mixed_observed
    return {
        "schema_version": 1,
        "classification": "variable_ngram_exact_component",
        "coverage": {
            "all_one": 1 in observed_lengths,
            "all_twelve": 12 in observed_lengths,
            "mixed_batch": mixed_observed,
            "observed_lengths": sorted(observed_lengths),
            "pass": coverage,
        },
        "exact_consumers": exact_consumers,
        "exact_response_tokens": exact_responses,
        "exact_top2_ids": exact_top2_ids,
        "max_top2_abs_error": max_top2_abs_error,
        "positive_target_forward_component": positive,
        "reduced_shape_control_median_sum_ms": weighted_control,
        "reduced_shape_candidate_median_sum_ms": weighted_candidate,
        "shape_rows": shape_rows,
        "token_rows": token_rows,
        "admit_c32": coverage and exact_consumers and positive,
    }


def c32_summary(control: dict, candidate: dict) -> dict:
    control_tokens = response_token_rows(OUT / "control-c32")
    candidate_tokens = response_token_rows(OUT / "candidate-c32")
    exact = control_tokens == candidate_tokens
    control_service = control["service_seconds_per_request"]
    candidate_service = candidate["service_seconds_per_request"]
    return {
        "schema_version": 1,
        "classification": "matched_c32_endpoint_pair",
        "control": control,
        "candidate": candidate,
        "complete_32_of_32": (
            control["complete_requests"] == 32
            and candidate["complete_requests"] == 32
        ),
        "exact_returned_token_ids": exact,
        "control_service_seconds_per_request": control_service,
        "candidate_service_seconds_per_request": candidate_service,
        "service_speedup": control_service / candidate_service,
        "service_change_fraction": (
            control_service - candidate_service
        )
        / control_service,
        "pass": (
            exact
            and control["pass"]
            and candidate["pass"]
            and candidate_service < control_service
        ),
    }


def main() -> int:
    prepare_inputs()
    retained_control = (
        (OUT / "control-component-c1/TERMINAL.json").exists()
        and (OUT / "control-component-c4/TERMINAL.json").exists()
        and (OUT / "control-mixed.json").exists()
        and (OUT / "control-component-events.jsonl").exists()
        and not (OUT / "COMPONENT_TERMINAL.json").exists()
    )
    terminal: dict[str, object] = {
        "schema_version": 1,
        "candidate_cuda_started": False,
        "scientific_invocation_started": False,
        "retained_control_consumed_once": retained_control,
    }
    atomic(OUT / "PROGRESS.json", terminal)

    if retained_control:
        control_terminals = {
            "c1": json.loads(
                (OUT / "control-component-c1/TERMINAL.json").read_text()
            ),
            "c4": json.loads(
                (OUT / "control-component-c4/TERMINAL.json").read_text()
            ),
            "mixed": json.loads((OUT / "control-mixed.json").read_text()),
        }
    else:
        control = launch("control", variable=False)
        terminal["candidate_cuda_started"] = True
        terminal["scientific_invocation_started"] = True
        atomic(OUT / "PROGRESS.json", terminal)
        control_terminals = {
            "c1": exact_run(control, "control-component", 1),
            "c4": exact_run(control, "control-component", 4),
        }
        control_terminals["mixed"] = mixed_run("control")
        stop(control, "control")

    candidate = launch("candidate", variable=True)
    terminal["candidate_cuda_started"] = True
    terminal["scientific_invocation_started"] = True
    atomic(OUT / "PROGRESS.json", terminal)
    candidate_terminals = {
        "c1": exact_run(candidate, "candidate-component", 1),
        "c4": exact_run(candidate, "candidate-component", 4),
    }
    candidate_terminals["mixed"] = mixed_run("candidate")
    component = component_summary(control_terminals, candidate_terminals)
    atomic(OUT / "COMPONENT_TERMINAL.json", component)

    endpoint = None
    if component["admit_c32"]:
        candidate_c32 = exact_run(candidate, "candidate", 32)
        stop(candidate, "candidate")
        control_c32_server = launch("control-c32", variable=False)
        control_c32 = exact_run(control_c32_server, "control", 32)
        stop(control_c32_server, "control-c32")
        endpoint = c32_summary(control_c32, candidate_c32)
        atomic(OUT / "ENDPOINT_TERMINAL.json", endpoint)
    else:
        stop(candidate, "candidate")

    terminal.update(
        {
            "component": component,
            "endpoint": endpoint,
            "result": (
                "endpoint_positive"
                if endpoint and endpoint["pass"]
                else (
                    "endpoint_nonpositive_or_inexact"
                    if endpoint
                    else "component_not_admitted"
                )
            ),
        }
    )
    atomic(OUT / "TERMINAL.json", terminal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
