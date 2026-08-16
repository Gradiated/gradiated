from __future__ import annotations

import json
import pathlib
import subprocess
import time
import traceback
import urllib.request
import datetime as dt


ROOT = pathlib.Path("/home/glmrunner/gemma4-ngram-qlen-two-stage")
PROJECT = ROOT / "project"
ARTIFACTS = ROOT / "artifacts"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
COMPONENT_CONTAINER = "gemma4-ngram-qlen-two-stage-component"


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run(args: list[str], timeout: int | None = None):
    return subprocess.run(
        args, capture_output=True, text=True, check=False, timeout=timeout
    )


def wait_model() -> None:
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(
                "http://127.0.0.1:30000/v1/models", timeout=5
            ).read()
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("component_server_readiness_timeout")


def run_component() -> dict:
    launch_args = json.loads(
        (PROJECT / "inputs/evidence/candidate-full-launch.json").read_text()
    )["args"]
    run(["sudo", "docker", "rm", "-f", COMPONENT_CONTAINER])
    command = [
        "sudo",
        "docker",
        "run",
        "-d",
        "--name",
        COMPONENT_CONTAINER,
        "--gpus",
        "all",
        "--ipc=host",
        "--network",
        "host",
        "-v",
        f"{ROOT}:/work",
        "-v",
        "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint:/work/checkpoint:ro",
        "-e",
        "PYTHONPATH=/work/project:/work/project/inputs/bound:/sgl-workspace/sglang/python",
        "-e",
        "QLEN_CAPTURE_ARTIFACT=/work/artifacts/component/COMPONENT_TERMINAL.json",
        "-e",
        "QLEN_CAPTURE_CANDIDATE=/work/project/inputs/bound/candidate_extend_attention.py",
        "-e",
        "QLEN_CAPTURE_ITERATIONS=9",
        "-e",
        "DECODE_EQ_LM_HEAD=1",
        "-e",
        "DECODE_EQ_SHADOW_BASELINE=0",
        "-e",
        "DECODE_EQ_AUDIT=/work/artifacts/component/decode-audit.jsonl",
        "-e",
        "FP8_MODULE_AUDIT=/work/artifacts/component/fp8-modules.jsonl",
        "-e",
        "FP8_CONSUMER_AUDIT=/work/artifacts/component/fp8-consumers.jsonl",
        "-e",
        "FP8_RUNTIME_AUDIT=/work/artifacts/component/fp8-runtime.json",
        IMAGE,
        "python3",
        "/work/project/production_endpoint_entrypoint.py",
        *launch_args,
        "--disable-cuda-graph",
    ]
    launched = run(command)
    atomic(
        ARTIFACTS / "component-launch.json",
        {
            "command": command,
            "returncode": launched.returncode,
            "stdout": launched.stdout,
            "stderr": launched.stderr,
        },
    )
    if launched.returncode:
        raise RuntimeError(f"component_server_launch:{launched.stderr[-1000:]}")
    runner = None
    try:
        wait_model()
        atomic(
            ARTIFACTS / "component/INVOCATION_STATE.json",
            {
                "schema_version": 1,
                "candidate_cuda_started": False,
                "scientific_invocation_started": True,
            },
        )
        runner = subprocess.Popen(
            [
                "sudo",
                "docker",
                "exec",
                COMPONENT_CONTAINER,
                "python3",
                "/work/project/inputs/bound/exact_runner.py",
                "--output",
                "/work/artifacts/component/trigger",
                "--arm",
                "component-trigger",
                "--concurrency",
                "32",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        terminal_path = ARTIFACTS / "component/COMPONENT_TERMINAL.json"
        error_path = ARTIFACTS / "component/COMPONENT_CAPTURE_ERROR.json"
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            if terminal_path.exists():
                break
            if error_path.exists():
                raise RuntimeError(
                    f"component_capture_error:{error_path.read_text()[-2000:]}"
                )
            if runner.poll() is not None:
                stdout, stderr = runner.communicate()
                (ARTIFACTS / "component.runner.stdout").write_text(stdout)
                (ARTIFACTS / "component.runner.stderr").write_text(stderr)
                raise RuntimeError(f"component_trigger_exited:{runner.returncode}")
            time.sleep(1)
        else:
            raise RuntimeError("component_capture_timeout")
        value = json.loads(terminal_path.read_text())
        atomic(
            ARTIFACTS / "component/INVOCATION_STATE.json",
            {
                "schema_version": 1,
                "candidate_cuda_started": True,
                "scientific_invocation_started": True,
                "component_terminal_persisted": True,
            },
        )
        return value
    finally:
        if runner is not None and runner.poll() is None:
            runner.terminate()
            try:
                stdout, stderr = runner.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                runner.kill()
                stdout, stderr = runner.communicate()
            (ARTIFACTS / "component.runner.stdout").write_text(stdout)
            (ARTIFACTS / "component.runner.stderr").write_text(stderr)
        logs = run(["sudo", "docker", "logs", COMPONENT_CONTAINER], 120)
        (ARTIFACTS / "component.server.stdout").write_text(logs.stdout)
        (ARTIFACTS / "component.server.stderr").write_text(logs.stderr)
        run(["sudo", "docker", "rm", "-f", COMPONENT_CONTAINER], 120)


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    atomic(
        ROOT / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "candidate_cuda_started": False,
            "scientific_invocation_started": False,
        },
    )
    component_path = ARTIFACTS / "COMPONENT_PERSISTED.json"
    if component_path.exists():
        component = json.loads(component_path.read_text())
    else:
        component = run_component()
        source = ARTIFACTS / "component/COMPONENT_TERMINAL.json"
        persisted = run(
            ["sudo", "install", "-m", "0644", str(source), str(component_path)]
        )
        if persisted.returncode:
            raise RuntimeError(
                f"component_persist_failed:{persisted.stderr[-1000:]}"
            )
    if not component.get("component_pass"):
        atomic(
            ARTIFACTS / "FINAL_TERMINAL.json",
            {
                "schema_version": 1,
                "classification": "scientific_terminal",
                "result": "two_stage_component_nonpositive_or_incorrect",
                "component": component,
                "endpoint_executed": False,
            },
        )
        return 2
    endpoint = run(
        ["/usr/bin/python3", str(PROJECT / "production_candidate_endpoint_once.py")],
        6000,
    )
    (ARTIFACTS / "candidate-endpoint.stdout").write_text(endpoint.stdout)
    (ARTIFACTS / "candidate-endpoint.stderr").write_text(endpoint.stderr)
    pair_path = ARTIFACTS / "pair/PAIR_TERMINAL.json"
    if endpoint.returncode not in (0, 75) or not pair_path.exists():
        raise RuntimeError(f"candidate_endpoint_harness_invalid:{endpoint.returncode}")
    pair = json.loads(pair_path.read_text())
    positive = (
        pair.get("valid")
        and pair.get("service_time_delta_fraction", 0) < 0
        and pair.get("p95_delta_fraction", 0) <= 0
    )
    atomic(
        ARTIFACTS / "FINAL_TERMINAL.json",
        {
            "schema_version": 1,
            "classification": "scientific_terminal",
            "result": "positive" if positive else "nonpositive_or_invalid",
            "component": component,
            "pair": pair,
            "endpoint_executed": True,
        },
    )
    return 0 if positive else 2


def entrypoint() -> int:
    while True:
        try:
            return main()
        except Exception as error:
            atomic(
                ROOT / "REPAIR_READY.json",
                {
                    "schema_version": 1,
                    "classification": "ordinary_integration_or_consumer_defect",
                    "error": repr(error),
                    "traceback": traceback.format_exc(),
                    "component_persisted": (
                        ARTIFACTS / "COMPONENT_PERSISTED.json"
                    ).exists(),
                    "retry_scope": (
                        "candidate_endpoint_only"
                        if (ARTIFACTS / "COMPONENT_PERSISTED.json").exists()
                        else "component_harness_only"
                    ),
                    "repair_deadline_utc": "2026-07-24T19:40:00Z",
                },
            )
            deadline = dt.datetime(
                2026, 7, 24, 19, 40, tzinfo=dt.timezone.utc
            )
            request = ROOT / "REPAIR_REQUEST.json"
            while dt.datetime.now(dt.timezone.utc) < deadline:
                if request.exists():
                    request.rename(
                        ROOT / f"REPAIR_REQUEST.consumed.{int(time.time())}.json"
                    )
                    (ROOT / "REPAIR_READY.json").unlink(missing_ok=True)
                    break
                time.sleep(5)
            else:
                raise


if __name__ == "__main__":
    raise SystemExit(entrypoint())
