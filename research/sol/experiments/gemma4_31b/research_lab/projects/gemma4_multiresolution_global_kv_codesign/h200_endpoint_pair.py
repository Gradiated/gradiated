#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import time

ROOT = pathlib.Path("/home/glmrunner/gemma4-multiresolution-global-kv")
INPUT = ROOT / "endpoint-input"
CHECKPOINT = ROOT / "checkpoint"
OUT = pathlib.Path(os.environ.get("GLOBAL_KV_OUTPUT_ROOT", ROOT / "endpoint-artifacts"))
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
BASE = [
    "--model-path", "/work/checkpoint", "--tokenizer-path", "/work/checkpoint",
    "--served-model-name", "google/gemma-4-31B-it", "--dtype", "bfloat16",
    "--quantization", "fp8", "--tp-size", "1", "--kv-cache-dtype", "fp8_e5m2",
    "--host", "0.0.0.0", "--context-length", "5000", "--max-running-requests", "32",
    "--mem-fraction-static", "0.85", "--enable-metrics", "--skip-server-warmup",
    "--enable-dynamic-chunking", "--chunked-prefill-size", "2048",
    "--enable-fused-qk-norm-rope", "--cuda-graph-max-bs", "32",
    "--prefill-attention-backend", "triton", "--decode-attention-backend", "triton",
    "--page-size", "1", "--num-continuous-decode-steps", "1",
    "--triton-attention-num-kv-splits", "8", "--tool-call-parser", "gemma4", "--port", "30000",
]


def run(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False, timeout=timeout)


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def launch(arm: str, candidate: bool) -> str:
    name = f"gemma4-global-kv-{arm}"
    if candidate and os.environ.get("H200_ENTRY_SCOPE") != "endpoint_activation_repair4":
        existing = run(["sudo", "-n", "docker", "inspect", "--format", "{{.State.Running}}", name], 30)
        if existing.returncode == 0 and existing.stdout.strip() == "true":
            return wait_for_health(name, arm)
    run(["sudo", "-n", "docker", "rm", "-f", name], 60)
    environment = []
    args = list(BASE)
    if candidate:
        environment = [
            "-e", "PYTHONPATH=/work/input:/sgl-workspace/sglang/python",
            "-e", "GLOBAL_KV_HOOK=1",
            "-e", f"GLOBAL_KV_TELEMETRY=/work/artifacts/{arm}-global-kv.jsonl",
            "-e", f"GLOBAL_KV_DIAGNOSTIC=/work/artifacts/{arm}-hook-diagnostic.json",
        ]
        args.append("--disable-cuda-graph")
    command = [
        "sudo", "-n", "docker", "run", "-d", "--name", name, "--gpus", "all",
        "--ipc=host", "--network", "host", "-v", f"{CHECKPOINT}:/work/checkpoint:ro",
        "-v", f"{INPUT}:/work/input:ro", "-v", f"{OUT}:/work/artifacts",
        *environment, IMAGE, "python3", "-c",
        "import global_kv_sglang_hook as h; h.install(); import runpy; runpy.run_module('sglang.launch_server', run_name='__main__')" if candidate else "import runpy; runpy.run_module('sglang.launch_server', run_name='__main__')",
        *args,
    ]
    result = run(command, 120)
    atomic(OUT / f"{arm}-launch.json", {"command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
    if result.returncode:
        raise RuntimeError(f"server_launch_failed:{arm}")
    return wait_for_health(name, arm)


def wait_for_health(name: str, arm: str) -> str:
    deadline = time.time() + 600
    while time.time() < deadline:
        try:
            health = run(["curl", "-fsS", "--max-time", "10", "http://127.0.0.1:30000/health"], 15)
        except subprocess.TimeoutExpired as exc:
            atomic(OUT / f"{arm}-health-timeout.json", {"arm": arm, "timeout_seconds": exc.timeout, "at_epoch": time.time()})
            time.sleep(3)
            continue
        if health.returncode == 0:
            return name
        state = run(["sudo", "-n", "docker", "inspect", "--format", "{{.State.Running}} {{.State.ExitCode}}", name], 30)
        if state.returncode == 0 and state.stdout.startswith("false"):
            logs = run(["sudo", "-n", "docker", "logs", name], 60)
            (OUT / f"{arm}-server.stdout").write_text(logs.stdout)
            (OUT / f"{arm}-server.stderr").write_text(logs.stderr)
            raise RuntimeError(f"server_exited_before_ready:{arm}")
        time.sleep(3)
    raise RuntimeError(f"server_readiness_timeout:{arm}")


def stop(name: str, arm: str) -> None:
    logs = run(["sudo", "-n", "docker", "logs", name], 120)
    (OUT / f"{arm}-server.stdout").write_text(logs.stdout)
    (OUT / f"{arm}-server.stderr").write_text(logs.stderr)
    run(["sudo", "-n", "docker", "rm", "-f", name], 120)
    time.sleep(3)


def arm(name: str, candidate: bool) -> dict:
    output = OUT / f"{name}-c32"
    if output.exists():
        archived = OUT / f"{name}-c32.invalid-{int(time.time())}"
        output.rename(archived)
    container = launch(name, candidate)
    science = OUT / f"{name}-science-started.json"
    atomic(science, {"arm": name, "at_epoch": time.time()})
    result = run([
        "sudo", "-n", "docker", "exec", container, "python3", "/work/input/exact_runner.py",
        "--output", f"/work/artifacts/{name}-c32", "--arm", name, "--concurrency", "32",
    ], 1800)
    (OUT / f"{name}-driver.stdout").write_text(result.stdout)
    (OUT / f"{name}-driver.stderr").write_text(result.stderr)
    stop(container, name)
    terminal_path = output / "TERMINAL.json"
    if not terminal_path.is_file():
        raise RuntimeError(f"endpoint_terminal_missing:{name}:{result.returncode}")
    terminal = json.loads(terminal_path.read_text())
    if result.returncode or not terminal.get("pass"):
        raise RuntimeError(f"endpoint_arm_invalid:{name}:{result.returncode}")
    return terminal


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    scope = os.environ.get("H200_ENTRY_SCOPE", "endpoint_pair")
    if scope in {"endpoint_repair2", "endpoint_activation_repair3", "endpoint_activation_repair4"}:
        stock_path = OUT / "STOCK_TERMINAL.json"
        if not stock_path.is_file():
            raise RuntimeError("adopted_stock_terminal_missing")
        stock = json.loads(stock_path.read_text())
    else:
        stock = arm("stock", False)
        atomic(OUT / "STOCK_TERMINAL.json", stock)
    if scope in {"endpoint_activation_repair3", "endpoint_activation_repair4"}:
        probe_output = OUT / "activation-probe"
        if probe_output.exists():
            probe_output.rename(OUT / f"activation-probe.invalid-{int(time.time())}")
        probe_container = launch("candidate", True)
        probe = run(["sudo", "-n", "docker", "exec", probe_container, "python3", "/work/input/exact_runner.py", "--output", "/work/artifacts/activation-probe", "--arm", "activation_probe", "--concurrency", "1"], 900)
        (OUT / "activation-probe.stdout").write_text(probe.stdout)
        (OUT / "activation-probe.stderr").write_text(probe.stderr)
        telemetry_path = OUT / "candidate-global-kv.jsonl"
        probe_rows = [json.loads(line) for line in telemetry_path.read_text().splitlines()] if telemetry_path.exists() else []
        probe_terminal = json.loads((probe_output / "TERMINAL.json").read_text()) if (probe_output / "TERMINAL.json").is_file() else None
        probe_ok = bool(probe.returncode == 0 and probe_terminal and probe_terminal.get("pass") and any(row.get("phase") in {"prefill", "decode"} and row.get("compact_entries") is not None and not row.get("fallback", True) for row in probe_rows))
        atomic(OUT / "ACTIVATION_PROBE.json", {"pass": probe_ok, "returncode": probe.returncode, "terminal": probe_terminal, "telemetry_rows": len(probe_rows), "rows": probe_rows[-16:]})
        if not probe_ok:
            raise RuntimeError("intervention_not_activated")
    candidate = arm("candidate", True)
    telemetry = OUT / "candidate-global-kv.jsonl"
    rows = [json.loads(line) for line in telemetry.read_text().splitlines()] if telemetry.exists() else []
    result = {
        "schema_version": 1,
        "classification": "scientific_terminal",
        "comparison_order": ["stock", "candidate"],
        "stock": stock,
        "candidate": candidate,
        "candidate_path": {
            "telemetry_rows": len(rows),
            "max_compact_entries": max((row["compact_entries"] for row in rows), default=None),
            "fallback": any(row.get("fallback") for row in rows),
            "phases": sorted(set(row["phase"] for row in rows)),
            "hook_sha256": hashlib.sha256((INPUT / "global_kv_sglang_hook.py").read_bytes()).hexdigest(),
        },
        "service_delta_seconds_per_request": candidate["service_seconds_per_request"] - stock["service_seconds_per_request"],
        "target_pass": candidate["service_seconds_per_request"] <= 0.500119281574996,
    }
    atomic(OUT / "ENDPOINT_PAIR_TERMINAL.json", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
