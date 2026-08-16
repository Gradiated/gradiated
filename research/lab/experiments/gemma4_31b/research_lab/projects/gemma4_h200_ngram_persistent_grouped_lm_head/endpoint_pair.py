#!/usr/bin/env python3
"""One matched c32 qualified-control/grouped-candidate endpoint pair."""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import subprocess
import time
import urllib.request


ROOT = pathlib.Path(
    os.environ.get(
        "GROUPED_LM_HEAD_REMOTE_ROOT",
        "/home/glmrunner/gemma4-persistent-grouped-lm-head",
    )
)
PROJECT = ROOT / "project"
CHECKPOINT = ROOT / "checkpoint"
OUT = pathlib.Path(
    os.environ.get("GROUPED_LM_HEAD_PAIR_ROOT", str(ROOT / "artifacts/pair"))
)
IMAGE = (
    "docker.io/lmsysorg/sglang@sha256:"
    "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
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
    "--speculative-algorithm",
    "NGRAM",
    "--port",
    "30000",
]


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def run(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, text=True, capture_output=True, check=False, timeout=timeout
    )


def events(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def container_running(name: str) -> bool:
    result = run(
        ["sudo", "docker", "inspect", "-f", "{{.State.Running}}", name],
        timeout=30,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def wait_model(name: str) -> None:
    for _ in range(300):
        if not container_running(name):
            logs = run(["sudo", "docker", "logs", name], timeout=30)
            raise RuntimeError(
                f"server_exited_before_ready:{name}:{logs.stderr[-800:]}"
            )
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:30000/v1/models", timeout=5
            ) as response:
                if MODEL in response.read().decode():
                    return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f"model_readiness_timeout:{name}")


def launch(arm: str, candidate: bool) -> str:
    name = f"gemma-grouped-lm-head-{arm}"
    stale = run(["sudo", "docker", "ps", "-aq", "-f", f"name=^{name}$"])
    if stale.stdout.strip():
        raise RuntimeError(f"stale_experiment_container:{name}")
    environment = [
        "-e",
        "PYTHONPATH=/work/project:/work/project/inputs/bound:/sgl-workspace/sglang/python",
        "-e",
        f"TOKEN_TRACE_EVENTS=/work/artifacts/{arm}-token-events.jsonl",
        "-e",
        f"FP8_MODULE_AUDIT=/work/artifacts/{arm}-fp8-modules.jsonl",
        "-e",
        f"FP8_CONSUMER_AUDIT=/work/artifacts/{arm}-fp8-consumers.jsonl",
        "-e",
        f"FP8_RUNTIME_AUDIT=/work/artifacts/{arm}-fp8-runtime.json",
    ]
    if candidate:
        environment += [
            "-e",
            "GROUPED_LM_HEAD=1",
            "-e",
            f"GROUPED_LM_HEAD_AUDIT=/work/artifacts/{arm}-candidate-audit.jsonl",
        ]
    else:
        environment += [
            "-e",
            "DECODE_EQ_LM_HEAD=1",
            "-e",
            f"DECODE_EQ_AUDIT=/work/artifacts/{arm}-control-audit.jsonl",
        ]
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
            f"{PROJECT}:/work/project:ro",
            "-v",
            f"{OUT}:/work/artifacts",
            "-v",
            f"{CHECKPOINT}:/work/checkpoint:ro",
            *environment,
            IMAGE,
            "python3",
            "/work/project/inputs/bound/endpoint_entrypoint.py",
            *BASE,
        ],
        timeout=120,
    )
    atomic(
        OUT / f"{arm}-launch.json",
        {
            "arm": arm,
            "candidate": candidate,
            "args": BASE,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    if result.returncode:
        raise RuntimeError(f"server_launch_failed:{arm}:{result.stderr[-800:]}")
    wait_model(name)
    return name


def run_c32(name: str, arm: str) -> dict:
    result = run(
        [
            "sudo",
            "docker",
            "exec",
            name,
            "python3",
            "/work/project/inputs/bound/exact_runner.py",
            "--output",
            f"/work/artifacts/{arm}-c32",
            "--arm",
            arm,
            "--concurrency",
            "32",
        ],
        timeout=1800,
    )
    (OUT / f"{arm}-driver.stdout").write_text(result.stdout)
    (OUT / f"{arm}-driver.stderr").write_text(result.stderr)
    terminal = OUT / f"{arm}-c32/TERMINAL.json"
    if result.returncode not in (0, 72) or not terminal.exists():
        raise RuntimeError(f"c32_driver_invalid:{arm}:{result.returncode}")
    return json.loads(terminal.read_text())


def stop(name: str, arm: str) -> bool:
    logs = run(["sudo", "docker", "logs", name], timeout=120)
    (OUT / f"{arm}-server.stdout").write_text(logs.stdout)
    (OUT / f"{arm}-server.stderr").write_text(logs.stderr)
    result = run(["sudo", "docker", "rm", "-f", name], timeout=120)
    return result.returncode == 0 and not container_running(name)


def cumulative_finals(arm: str) -> list[dict]:
    deltas: dict[str, list[int]] = {}
    finals: list[dict] = []
    for row in events(OUT / f"{arm}-token-events.jsonl"):
        rid = row.get("rid")
        if row.get("stage") == "scheduler_to_detokenizer":
            deltas.setdefault(rid, []).extend(row["scheduler_output_ids_delta"])
        elif row.get("stage") == "post_generation_pre_parser_final":
            item = dict(row)
            ids = deltas.get(rid, [])
            item["scheduler_output_ids"] = ids
            item["emitted_token_ids"] = ids
            item["completion_counter_inputs"] = {
                "emitted_token_count": len(ids),
                "scheduler_delta_count": len(ids),
            }
            finals.append(item)
    return [
        row
        for row in finals
        if row.get("prompt_tokens") == 4214 and row.get("completion_counter") == 358
    ]


def token_projection(rows: list[dict]) -> list[dict]:
    result = [
        {
            key: row.get(key)
            for key in (
                "scheduler_output_ids",
                "emitted_token_ids",
                "finish_reason",
                "prompt_tokens",
                "completion_counter",
            )
        }
        for row in rows
    ]
    return sorted(
        result, key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":"))
    )


def sse_token_rows(arm: str) -> list[list[int]]:
    result = []
    for path in sorted((OUT / f"{arm}-c32").glob("response-*.sse")):
        ids: list[int] = []
        for raw in path.read_bytes().splitlines():
            if not raw.startswith(b"data: ") or raw.strip() == b"data: [DONE]":
                continue
            item = json.loads(raw[6:])
            choice = (item.get("choices") or [{}])[0]
            ids.extend(choice.get("token_ids") or [])
        result.append(ids)
    return result


def metric_values(path: pathlib.Path) -> dict[str, list[float]]:
    selected = (
        "sglang:spec_verify_calls_total",
        "sglang:spec_accept_length",
        "sglang:spec_accept_rate",
        "sglang:spec_num_draft_tokens",
        "sglang:prompt_tokens_histogram_sum",
        "sglang:uncached_prompt_tokens_histogram_sum",
    )
    values: dict[str, list[float]] = {name: [] for name in selected}
    for line in path.read_text().splitlines():
        for name in selected:
            if line.startswith(name) and not line.startswith("#"):
                values[name].append(float(line.rsplit(" ", 1)[1]))
    return values


def telemetry(arm: str) -> dict:
    before = metric_values(OUT / f"{arm}-c32/metrics-before.prom")
    after = metric_values(OUT / f"{arm}-c32/metrics-after.prom")
    result = {}
    for name in before:
        left = sum(before[name]) if before[name] else None
        right = sum(after[name]) if after[name] else None
        result[name] = {
            "before": left,
            "after": right,
            "delta": None if left is None or right is None else right - left,
        }
    return result


def p95(terminal: dict) -> float:
    values = sorted(float(row["wall_seconds"]) for row in terminal["rows"])
    return values[max(0, math.ceil(0.95 * len(values)) - 1)]


def arm(arm_name: str, candidate: bool) -> dict:
    name = launch(arm_name, candidate)
    terminal = run_c32(name, arm_name)
    finals = cumulative_finals(arm_name)
    result = {
        "terminal": terminal,
        "finals": finals,
        "sse_token_ids": sse_token_rows(arm_name),
        "telemetry": telemetry(arm_name),
        "p95_completion_seconds": p95(terminal),
        "container": name,
        "clean_shutdown": False,
    }
    atomic(OUT / f"{arm_name.upper()}_PRODUCER_STAGE.json", result)
    result["clean_shutdown"] = stop(name, arm_name)
    atomic(OUT / f"{arm_name.upper()}_PRODUCER_STAGE.json", result)
    return result


def request_hashes(value: dict) -> list[str]:
    return [row["request_sha256"] for row in value["terminal"]["rows"]]


def accounting_valid(value: dict) -> bool:
    terminal = value["terminal"]
    finals = value["finals"]
    return bool(
        terminal.get("pass")
        and terminal.get("complete_requests") == 32
        and len(finals) == 32
        and all(
            row.get("completion_counter")
            == row["completion_counter_inputs"]["emitted_token_count"]
            for row in finals
        )
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    atomic(
        OUT / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "control_started": False,
            "control_complete": False,
            "candidate_started": False,
            "candidate_complete": False,
        },
    )
    control_stage = OUT / "CONTROL_PRODUCER_STAGE.json"
    if control_stage.exists():
        control = json.loads(control_stage.read_text())
        if (
            control.get("terminal", {}).get("pass")
            and len(control.get("finals", [])) == 32
            and len(control.get("sse_token_ids", [])) == 32
            and not control.get("clean_shutdown")
            and control.get("container")
        ):
            control["clean_shutdown"] = stop(
                control["container"], "control-shutdown-repair"
            )
            atomic(control_stage, control)
        if not (
            control.get("terminal", {}).get("pass")
            and len(control.get("finals", [])) == 32
            and len(control.get("sse_token_ids", [])) == 32
            and control.get("clean_shutdown")
        ):
            raise RuntimeError("persisted_control_producer_incomplete")
    else:
        atomic(
            OUT / "INVOCATION_STATE.json",
            {
                "schema_version": 1,
                "control_started": True,
                "control_complete": False,
                "candidate_started": False,
                "candidate_complete": False,
            },
        )
        control = arm("control", False)
    atomic(
        OUT / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "control_started": True,
            "control_complete": True,
            "candidate_started": True,
            "candidate_complete": False,
        },
    )
    candidate_stage = OUT / "CANDIDATE_PRODUCER_STAGE.json"
    if candidate_stage.exists():
        candidate = json.loads(candidate_stage.read_text())
        if (
            candidate.get("terminal", {}).get("pass")
            and len(candidate.get("finals", [])) == 32
            and len(candidate.get("sse_token_ids", [])) == 32
            and not candidate.get("clean_shutdown")
            and candidate.get("container")
        ):
            candidate["clean_shutdown"] = stop(
                candidate["container"], "candidate-shutdown-repair"
            )
            atomic(candidate_stage, candidate)
        if not (
            candidate.get("terminal", {}).get("pass")
            and len(candidate.get("finals", [])) == 32
            and len(candidate.get("sse_token_ids", [])) == 32
            and candidate.get("clean_shutdown")
        ):
            raise RuntimeError("persisted_candidate_producer_incomplete")
    else:
        candidate = arm("candidate", True)
    atomic(
        OUT / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "control_started": True,
            "control_complete": True,
            "candidate_started": True,
            "candidate_complete": True,
        },
    )
    control_service = float(control["terminal"]["service_seconds_per_request"])
    candidate_service = float(candidate["terminal"]["service_seconds_per_request"])
    control_p95 = float(control["p95_completion_seconds"])
    candidate_p95 = float(candidate["p95_completion_seconds"])
    hashes_exact = request_hashes(control) == request_hashes(candidate)
    sse_exact = (
        len(control["sse_token_ids"]) == 32
        and control["sse_token_ids"] == candidate["sse_token_ids"]
    )
    trace_exact = token_projection(control["finals"]) == token_projection(
        candidate["finals"]
    )
    control_ngram = control["telemetry"]
    candidate_ngram = candidate["telemetry"]
    ngram_present = all(
        candidate_ngram[name]["after"] is not None
        for name in (
            "sglang:spec_verify_calls_total",
            "sglang:spec_accept_length",
            "sglang:spec_accept_rate",
            "sglang:spec_num_draft_tokens",
        )
    )
    audit = events(OUT / "candidate-candidate-audit.jsonl")
    valid = bool(
        accounting_valid(control)
        and accounting_valid(candidate)
        and hashes_exact
        and sse_exact
        and trace_exact
        and ngram_present
        and audit
        and control["clean_shutdown"]
        and candidate["clean_shutdown"]
    )
    result = {
        "schema_version": 1,
        "classification": "matched_c32_grouped_lm_head_endpoint_pair",
        "valid": valid,
        "requests_per_arm": 32,
        "request_hashes_exact": hashes_exact,
        "sse_token_ids_exact": sse_exact,
        "target_and_emitted_trace_exact": trace_exact,
        "usage_and_cache_accounting_valid": (
            accounting_valid(control) and accounting_valid(candidate)
        ),
        "ngram_telemetry_present": ngram_present,
        "control_ngram_telemetry": control_ngram,
        "candidate_ngram_telemetry": candidate_ngram,
        "candidate_path_present": bool(audit),
        "candidate_audit": audit,
        "failures_per_arm": {
            "control": 32 - int(control["terminal"]["complete_requests"]),
            "candidate": 32 - int(candidate["terminal"]["complete_requests"]),
        },
        "clean_shutdown": {
            "control": control["clean_shutdown"],
            "candidate": candidate["clean_shutdown"],
        },
        "control_service_seconds_per_request": control_service,
        "candidate_service_seconds_per_request": candidate_service,
        "service_time_delta_fraction": candidate_service / control_service - 1.0,
        "control_p95_completion_seconds": control_p95,
        "candidate_p95_completion_seconds": candidate_p95,
        "p95_delta_fraction": candidate_p95 / control_p95 - 1.0,
    }
    atomic(OUT / "PAIR_RESULT.json", result)
    atomic(OUT / "PAIR_TERMINAL.json", result)
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
