#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import shutil
import statistics
import subprocess
import sys
import time
import traceback
import urllib.request


ROOT = pathlib.Path("/home/glmrunner/gemma4-h200-ngram-m384-cluster")
PROJECT = ROOT / "project"
ARTIFACTS = ROOT / "artifacts"
RUNTIME = ROOT / "runtime"
CONTROL = ROOT / "control-reference/control"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
CONTROL_SECONDS = 0.6049806232813353


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def run(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout)


def wait_model() -> None:
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen("http://127.0.0.1:30000/v1/models", timeout=5).read()
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("server_readiness_timeout")


def parse_sse(root: pathlib.Path) -> list[dict[str, object]]:
    rows = []
    for path in sorted(root.glob("response-*.sse")):
        token_ids: list[int] = []
        text = ""
        finish_reason = None
        usage = None
        for raw in path.read_bytes().splitlines():
            if not raw.startswith(b"data: ") or raw.strip() == b"data: [DONE]":
                continue
            item = json.loads(raw[6:])
            choice = (item.get("choices") or [{}])[0]
            token_ids.extend(choice.get("token_ids") or [])
            text += choice.get("text") or ""
            if choice.get("finish_reason") is not None:
                finish_reason = choice["finish_reason"]
            if item.get("usage") is not None:
                usage = item["usage"]
        rows.append(
            {
                "token_ids": token_ids,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "finish_reason": finish_reason,
                "usage": usage,
            }
        )
    return rows


def p95(values: list[float]) -> float:
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def prepare() -> pathlib.Path:
    kernel_base = ROOT / "kernel-base"
    if not (kernel_base / ".ready").exists():
        run(["rm", "-rf", str(kernel_base)])
        kernel_base.mkdir()
        extracted = run(["tar", "-xzf", str(ROOT / "kernel-build-base.tar.gz"), "-C", str(kernel_base)], 600)
        if extracted.returncode:
            raise RuntimeError(f"kernel_base_extract:{extracted.stderr[-1000:]}")
        cutlass = kernel_base / "inputs/cutlass-v0513-exact"
        cutlass.mkdir(parents=True, exist_ok=True)
        result = run(
            [
                "tar",
                "-xzf",
                str(kernel_base / "inputs/cutlass-57e3cfb47a2d9e0d46eb6335c3dc411498efa198.tar.gz"),
                "--strip-components=1",
                "-C",
                str(cutlass),
            ],
            600,
        )
        if result.returncode:
            raise RuntimeError(f"cutlass_extract:{result.stderr[-1000:]}")
        (kernel_base / ".ready").write_text("1\n")
    if not (RUNTIME / "inputs/bound/exact_runner.py").exists():
        RUNTIME.mkdir(exist_ok=True)
        result = run(["tar", "-xf", str(ROOT / "ngram-runtime.tar"), "-C", str(RUNTIME)], 120)
        if result.returncode:
            raise RuntimeError(f"runtime_extract:{result.stderr[-1000:]}")
    if not (CONTROL / "TERMINAL.json").exists():
        (ROOT / "control-reference").mkdir(exist_ok=True)
        result = run(
            ["tar", "-xzf", str(ROOT / "persisted-control.tar.gz"), "-C", str(ROOT / "control-reference")],
            120,
        )
        if result.returncode:
            raise RuntimeError(f"control_extract:{result.stderr[-1000:]}")
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    module = next(build.glob("gemma4_fp8_m384_cluster_n*.so"), None)
    if module is None:
        invocation = {
            "schema_version": 1,
            "compile_started": True,
            "candidate_cuda_started": False,
            "component_science_started": False,
            "endpoint_science_started": False,
        }
        atomic(ARTIFACTS / "INVOCATION_STATE.json", invocation)
        result = run(
            [
                "sudo",
                "docker",
                "run",
                "--rm",
                "--gpus",
                "all",
                "--ipc=host",
                "-v",
                f"{ROOT}:/work",
                IMAGE,
                "python3",
                "/work/project/build_candidate.py",
                "--project-root",
                "/work/project",
                "--kernel-base",
                "/work/kernel-base",
                "--build-root",
                "/work/build",
                "--output",
                "/work/artifacts/BUILD.json",
            ],
            1200,
        )
        (ARTIFACTS / "build.stdout").write_text(result.stdout)
        (ARTIFACTS / "build.stderr").write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(f"candidate_compile:{result.stderr[-2000:]}")
        module = next(build.glob("gemma4_fp8_m384_cluster_n*.so"), None)
    if module is None:
        raise RuntimeError("candidate_module_missing")
    return module


def launch(mode: str, module: pathlib.Path) -> str:
    name = f"gemma-ngram-m384-{mode}"
    run(["sudo", "docker", "rm", "-f", name], 120)
    args = json.loads((RUNTIME / "inputs/evidence/candidate-full-launch.json").read_text())["args"]
    if mode == "component":
        args = [*args, "--disable-cuda-graph"]
    audit = ARTIFACTS / f"{mode}-audit.jsonl"
    if audit.exists():
        audit.unlink()
    command = [
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
        f"{RUNTIME / 'inputs/bound'}:/work/input:ro",
        "-v",
        "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint:/work/checkpoint:ro",
        "-e",
        "PYTHONPATH=/work/project:/work/input:/sgl-workspace/sglang/python",
        "-e",
        "DECODE_EQ_LM_HEAD=1",
        "-e",
        "DECODE_EQ_SHADOW_BASELINE=0",
        "-e",
        f"DECODE_EQ_AUDIT=/work/artifacts/{mode}-decode-audit.jsonl",
        "-e",
        f"FP8_MODULE_AUDIT=/work/artifacts/{mode}-fp8-modules.jsonl",
        "-e",
        f"FP8_CONSUMER_AUDIT=/work/artifacts/{mode}-fp8-consumers.jsonl",
        "-e",
        f"FP8_RUNTIME_AUDIT=/work/artifacts/{mode}-fp8-runtime.json",
        "-e",
        f"M384_MODE={mode}",
        "-e",
        f"M384_MODULE=/work/build/{module.name}",
        "-e",
        f"M384_AUDIT=/work/artifacts/{mode}-audit.jsonl",
        "-e",
        "M384_COMPONENT_ENABLE=/work/artifacts/component-live-request.enable",
        IMAGE,
        "python3",
        "/work/project/cluster_endpoint_entrypoint.py",
        *args,
    ]
    result = run(command, 120)
    atomic(
        ARTIFACTS / f"{mode}-launch.json",
        {"command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr},
    )
    if result.returncode:
        raise RuntimeError(f"{mode}_server_launch:{result.stderr[-1000:]}")
    wait_model()
    return name


def run_arm(mode: str, module: pathlib.Path) -> dict[str, object]:
    name = launch(mode, module)
    output = ARTIFACTS / mode
    if mode == "component":
        (ARTIFACTS / "component-live-request.enable").write_text(
            "enabled only after HTTP readiness and immediately before exact_runner\n"
        )
    state_path = ARTIFACTS / "INVOCATION_STATE.json"
    state = json.loads(state_path.read_text())
    state["candidate_cuda_started"] = True
    state[f"{mode}_science_started"] = True
    atomic(state_path, state)
    try:
        result = run(
            [
                "sudo",
                "docker",
                "exec",
                name,
                "python3",
                "/work/input/exact_runner.py",
                "--output",
                f"/work/artifacts/{mode}",
                "--arm",
                mode,
                "--concurrency",
                "32",
            ],
            2400,
        )
        (ARTIFACTS / f"{mode}.runner.stdout").write_text(result.stdout)
        (ARTIFACTS / f"{mode}.runner.stderr").write_text(result.stderr)
        logs = run(["sudo", "docker", "logs", name], 120)
        (ARTIFACTS / f"{mode}.server.stdout").write_text(logs.stdout)
        (ARTIFACTS / f"{mode}.server.stderr").write_text(logs.stderr)
        health = run(["curl", "-fsS", "--max-time", "15", "http://127.0.0.1:30000/v1/models"], 30)
        terminal_path = output / "TERMINAL.json"
        if result.returncode not in (0, 72) or not terminal_path.exists():
            raise RuntimeError(f"{mode}_runner_invalid:{result.returncode}")
        terminal = json.loads(terminal_path.read_text())
        return {
            "terminal": terminal,
            "semantic_rows": parse_sse(output),
            "request_sha256": [row["request_sha256"] for row in terminal["rows"]],
            "p95_completion_seconds": p95([row["wall_seconds"] for row in terminal["rows"]]),
            "server_healthy_after": health.returncode == 0,
        }
    finally:
        run(["sudo", "docker", "rm", "-f", name], 120)


def consume_component(summary: dict[str, object]) -> dict[str, object]:
    rows = [
        json.loads(line)
        for line in (ARTIFACTS / "component-audit.jsonl").read_text().splitlines()
        if line.strip()
    ]
    paths = [row for row in rows if row["phase"] == "production_candidate_path"]
    measurements = [row for row in rows if row["phase"] == "exact_real_weight_component"]
    numerical_pass = bool(measurements) and all(
        row["projection"]["bitwise_equal"]
        and row["projection"]["reference_nonfinite"] == 0
        and row["projection"]["candidate_nonfinite"] == 0
        and row["returned_to_unchanged_consumer"]
        for row in measurements
    )
    stock_total = sum(row["stock"]["median_us"] for row in measurements)
    candidate_total = sum(row["candidate"]["median_us"] for row in measurements)
    component_speedup = 1 - candidate_total / stock_total if stock_total else -1
    no_material_family_regression = all(row["candidate_speedup_fraction"] > -0.02 for row in measurements)
    control = json.loads((CONTROL / "TERMINAL.json").read_text())
    semantic_match = (
        parse_sse(CONTROL) == summary["semantic_rows"]
        and [row["request_sha256"] for row in control["rows"]] == summary["request_sha256"]
    )
    trace_kernel_seconds = 1.1632176339999984
    trace_window_seconds = 3.1657324599609375
    terminal = {
        "schema_version": 1,
        "kind": "exact_real_weight_m384_component",
        "component_rows": measurements,
        "candidate_path_rows": len(paths),
        "families": sorted({row["family"] for row in measurements}),
        "shapes_mnk": sorted({tuple(row["shape_mnk"]) for row in measurements}),
        "numerical_pass": numerical_pass,
        "component_speedup_fraction": component_speedup,
        "no_material_family_regression": no_material_family_regression,
        "complete_32": summary["terminal"]["complete_requests"] == 32,
        "semantics_match_persisted_control": semantic_match,
        "trace_normalized_opportunity_fraction": component_speedup
        * trace_kernel_seconds
        / trace_window_seconds,
        "trace_bound_caveat": "Summed FP8 kernel time overlaps other work; this is an analytical opportunity estimate, not additive wall attribution.",
    }
    terminal["component_pass"] = (
        numerical_pass
        and component_speedup > 0
        and no_material_family_regression
        and terminal["complete_32"]
        and semantic_match
        and len(paths) > 0
    )
    atomic(ARTIFACTS / "COMPONENT_TERMINAL.json", terminal)
    return terminal


def consume_endpoint(summary: dict[str, object]) -> dict[str, object]:
    control = json.loads((CONTROL / "TERMINAL.json").read_text())
    candidate = summary["terminal"]
    audit_path = ARTIFACTS / "endpoint-audit.jsonl"
    audit_rows = [
        json.loads(line) for line in audit_path.read_text().splitlines() if line.strip()
    ] if audit_path.exists() else []
    semantic_match = (
        parse_sse(CONTROL) == summary["semantic_rows"]
        and [row["request_sha256"] for row in control["rows"]] == summary["request_sha256"]
    )
    control_p95 = p95([row["wall_seconds"] for row in control["rows"]])
    candidate_p95 = summary["p95_completion_seconds"]
    terminal = {
        "schema_version": 1,
        "kind": "candidate_only_exact_c32_against_persisted_control",
        "control_replayed": False,
        "control_seconds_per_request": CONTROL_SECONDS,
        "candidate_seconds_per_request": candidate["service_seconds_per_request"],
        "service_time_delta_fraction": candidate["service_seconds_per_request"] / CONTROL_SECONDS - 1,
        "control_p95_completion_seconds": control_p95,
        "candidate_p95_completion_seconds": candidate_p95,
        "p95_delta_fraction": candidate_p95 / control_p95 - 1,
        "complete_32": candidate["complete_requests"] == 32,
        "semantics_match": semantic_match,
        "server_stable": summary["server_healthy_after"],
        "candidate_path_rows": len([row for row in audit_rows if row["phase"] == "production_candidate_path"]),
        "candidate_path_shapes": sorted(
            {tuple(row["shape_mnk"]) for row in audit_rows if row["phase"] == "production_candidate_path"}
        ),
    }
    terminal["valid"] = (
        terminal["complete_32"]
        and semantic_match
        and terminal["server_stable"]
        and terminal["candidate_path_rows"] > 0
    )
    terminal["pass"] = (
        terminal["valid"]
        and terminal["service_time_delta_fraction"] < 0
        and terminal["p95_delta_fraction"] <= 0
    )
    atomic(ARTIFACTS / "ENDPOINT_TERMINAL.json", terminal)
    return terminal


def main() -> int:
    ARTIFACTS.mkdir(exist_ok=True)
    if (ARTIFACTS / "COMPONENT_AUDIT_PERSISTED.jsonl").exists():
        result = run(["python3", str(PROJECT / "finalize_component.py")], 300)
        if result.returncode:
            raise RuntimeError(f"component_finalizer:{result.stderr[-2000:]}")
        return 0
    (ARTIFACTS / "component-live-request.enable").unlink(missing_ok=True)
    stale_component = ARTIFACTS / "component"
    if (
        stale_component.exists()
        and not (ARTIFACTS / "COMPONENT_TERMINAL.json").exists()
        and not (ARTIFACTS / "component-audit.jsonl").exists()
    ):
        preserved = ARTIFACTS / "INVALID_ATTEMPT_graph_replay_bypass_component"
        if not preserved.exists():
            shutil.move(stale_component, preserved)
        for name in (
            "component.runner.stdout",
            "component.runner.stderr",
            "component.server.stdout",
            "component.server.stderr",
        ):
            path = ARTIFACTS / name
            if path.exists():
                path.rename(ARTIFACTS / f"INVALID_ATTEMPT_graph_replay_bypass_{name}")
    invocation = {
        "schema_version": 1,
        "compile_started": False,
        "candidate_cuda_started": False,
        "component_science_started": False,
        "endpoint_science_started": False,
    }
    if (ARTIFACTS / "INVOCATION_STATE.json").exists():
        invocation.update(json.loads((ARTIFACTS / "INVOCATION_STATE.json").read_text()))
    atomic(ARTIFACTS / "INVOCATION_STATE.json", invocation)
    try:
        module = prepare()
        component_path = ARTIFACTS / "COMPONENT_TERMINAL.json"
        if component_path.exists():
            component = json.loads(component_path.read_text())
        else:
            component = consume_component(run_arm("component", module))
        if not component["component_pass"]:
            atomic(
                ARTIFACTS / "FINAL_TERMINAL.json",
                {
                    "schema_version": 1,
                    "classification": "scientific_terminal",
                    "result": "component_nonpositive_or_incorrect",
                    "component": component,
                    "endpoint_executed": False,
                },
            )
            return 0
        endpoint = consume_endpoint(run_arm("endpoint", module))
        if endpoint["candidate_path_rows"] == 0:
            raise RuntimeError("endpoint_zero_candidate_path_rows")
        atomic(
            ARTIFACTS / "FINAL_TERMINAL.json",
            {
                "schema_version": 1,
                "classification": "scientific_terminal",
                "result": "positive" if endpoint["pass"] else "endpoint_nonpositive_or_invalid",
                "component": component,
                "endpoint": endpoint,
                "endpoint_executed": True,
            },
        )
        return 0
    except Exception as error:
        diagnostic = {
            "schema_version": 1,
            "classification": "ordinary_integration_or_consumer_defect",
            "error": repr(error),
            "traceback": traceback.format_exc(),
            "invocation_state": json.loads((ARTIFACTS / "INVOCATION_STATE.json").read_text()),
            "component_persisted": (ARTIFACTS / "COMPONENT_TERMINAL.json").exists(),
            "retry_scope": "endpoint_only" if (ARTIFACTS / "COMPONENT_TERMINAL.json").exists() else "invalidated_precomponent_operation",
        }
        atomic(ARTIFACTS / "ATTEMPT_TERMINAL.json", diagnostic)
        atomic(
            ROOT / "REPAIR_READY.json",
            {
                **diagnostic,
                "repair_deadline_utc": "2026-07-24T18:42:00Z",
                "constraint": "same frozen M384-only 1x2x1 candidate and persisted producer stages",
            },
        )
        print(json.dumps(diagnostic, indent=2), file=sys.stderr)
        return 75
    finally:
        for name in ("gemma-ngram-m384-component", "gemma-ngram-m384-endpoint"):
            run(["sudo", "docker", "rm", "-f", name], 120)


if __name__ == "__main__":
    raise SystemExit(main())
