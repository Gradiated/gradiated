from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import time
import urllib.request


ROOT = pathlib.Path("/home/glmrunner/gemma4-ngram-critical")
PROJECT = ROOT / "project"
OUT = ROOT / "artifacts/profile"
IMAGE = (
    "docker.io/lmsysorg/sglang@sha256:"
    "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
CONTAINER = "gemma-ngram-critical-profile"


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def run(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def wait_model() -> None:
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen("http://127.0.0.1:30000/v1/models", timeout=5).read()
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("profile_server_readiness_timeout")


def launch() -> None:
    args = json.loads(
        (PROJECT / "inputs/evidence/candidate-full-launch.json").read_text()
    )["args"]
    run(["sudo", "docker", "rm", "-f", CONTAINER])
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
        "-v",
        f"{ROOT}:/work",
        "-v",
        f"{PROJECT / 'inputs/bound'}:/work/input:ro",
        "-v",
        f"{ROOT / 'checkpoint'}:/work/checkpoint:ro",
        "-e",
        "PYTHONPATH=/work/project:/work/input:/sgl-workspace/sglang/python",
        "-e",
        "DECODE_EQ_LM_HEAD=1",
        "-e",
        "DECODE_EQ_SHADOW_BASELINE=0",
        "-e",
        "DECODE_EQ_AUDIT=/work/artifacts/profile/decode-equivalent-audit.jsonl",
        "-e",
        "FP8_MODULE_AUDIT=/work/artifacts/profile/fp8-modules.jsonl",
        "-e",
        "FP8_CONSUMER_AUDIT=/work/artifacts/profile/fp8-consumers.jsonl",
        "-e",
        "FP8_RUNTIME_AUDIT=/work/artifacts/profile/fp8-runtime.json",
        "-e",
        "NGRAM_PROFILE_RANGES=1",
        "-e",
        "SGLANG_TORCH_PROFILER_DIR=/work/artifacts/profile/torch",
        "-e",
        "SGLANG_PROFILE_WITH_STACK=0",
        "-e",
        "SGLANG_PROFILE_RECORD_SHAPES=0",
        IMAGE,
        "python3",
        "/work/input/endpoint_entrypoint.py",
        *args,
    ]
    result = run(command)
    atomic(
        OUT / "launch.json",
        {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    if result.returncode:
        raise RuntimeError(f"profile_server_launch:{result.stderr[-1000:]}")
    wait_model()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    atomic(
        OUT / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "candidate_cuda_started": False,
            "scientific_invocation_started": False,
        },
    )
    launch()
    atomic(
        OUT / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "candidate_cuda_started": True,
            "scientific_invocation_started": True,
            "stage": "exact_c32_profile",
        },
    )
    runner = run(
        [
            "sudo",
            "docker",
            "exec",
            CONTAINER,
            "python3",
            "/work/project/profile_runner.py",
            "--output",
            "/work/artifacts/profile/c32",
            "--arm",
            "exact-ngram-profile",
            "--concurrency",
            "32",
        ],
        timeout=2400,
    )
    (OUT / "runner.stdout").write_text(runner.stdout)
    (OUT / "runner.stderr").write_text(runner.stderr)
    logs = run(["sudo", "docker", "logs", CONTAINER], timeout=120)
    (OUT / "server.stdout").write_text(logs.stdout)
    (OUT / "server.stderr").write_text(logs.stderr)
    trace_deadline = time.monotonic() + 120
    traces: list[pathlib.Path] = []
    while time.monotonic() < trace_deadline:
        traces = sorted((OUT / "torch").rglob("*trace*.json"))
        if traces:
            break
        time.sleep(2)
    health = run(
        ["curl", "-fsS", "--max-time", "15", "http://127.0.0.1:30000/v1/models"]
    )
    runner_terminal = OUT / "c32/TERMINAL.json"
    terminal = {
        "schema_version": 1,
        "kind": "exact_c32_ngram_profile",
        "runner_returncode": runner.returncode,
        "runner_terminal_present": runner_terminal.exists(),
        "runner": json.loads(runner_terminal.read_text())
        if runner_terminal.exists()
        else None,
        "trace_files": [
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in traces
        ],
        "server_healthy_after": health.returncode == 0,
        "server_health_stderr": health.stderr[-1000:],
        "scientific_result_interpretable": (
            runner.returncode in (0, 72)
            and runner_terminal.exists()
            and bool(traces)
        ),
    }
    atomic(OUT / "PROFILE_TERMINAL.json", terminal)
    if terminal["scientific_result_interpretable"]:
        run(["sudo", "docker", "rm", "-f", CONTAINER], timeout=120)
        return 0
    atomic(
        OUT / "REPAIR_STATE.json",
        {
            "schema_version": 1,
            "container": CONTAINER,
            "container_retained": True,
            "runner_terminal_retained": runner_terminal.exists(),
            "repair": "retrieve diagnostics and stop/finalize the profiler without replaying c32",
        },
    )
    return 74


if __name__ == "__main__":
    raise SystemExit(main())
