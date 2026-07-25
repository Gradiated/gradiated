from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import statistics
import subprocess
import time
import urllib.request


ROOT = pathlib.Path("/home/glmrunner/gemma4-fixed-m384-executor")
PROJECT = ROOT / "project"
OUT = pathlib.Path(os.environ.get("FIXED_M384_PAIR_ROOT", str(ROOT / "artifacts/pair")))
IMAGE = (
    "docker.io/lmsysorg/sglang@sha256:"
    "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)


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
    raise RuntimeError("pair_server_readiness_timeout")


def launch(arm: str, candidate: bool) -> str:
    name = f"gemma-fixed-m384-{arm}"
    args = json.loads(
        (PROJECT / "inputs/evidence/candidate-full-launch.json").read_text()
    )["args"]
    run(["sudo", "docker", "rm", "-f", name])
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
        f"{PROJECT / 'inputs/harness'}:/work/input:ro",
        "-v",
        f"{ROOT / 'checkpoint'}:/work/checkpoint:ro",
        "-e",
        "PYTHONPATH=/work/input:/sgl-workspace/sglang/python",
        "-e",
        "DECODE_EQ_LM_HEAD=1",
        "-e",
        "DECODE_EQ_SHADOW_BASELINE=0",
        "-e",
        f"DECODE_EQ_AUDIT=/work/artifacts/pair/{arm}-decode-audit.jsonl",
        "-e",
        f"FP8_MODULE_AUDIT=/work/artifacts/pair/{arm}-fp8-modules.jsonl",
        "-e",
        f"FP8_CONSUMER_AUDIT=/work/artifacts/pair/{arm}-fp8-consumers.jsonl",
        "-e",
        f"FP8_RUNTIME_AUDIT=/work/artifacts/pair/{arm}-fp8-runtime.json",
        "-e",
        f"FIXED_M384_AUDIT=/work/artifacts/pair/{arm}-fixed-m384-audit.jsonl",
    ]
    if candidate:
        command += [
            "-v",
            (
                f"{PROJECT / 'intervention/extend_attention_fixed_m384.py'}:"
                "/sgl-workspace/sglang/python/sglang/srt/layers/attention/"
                "triton_ops/extend_attention.py:ro"
            ),
        ]
    command += [
        IMAGE,
        "python3",
        "/work/input/endpoint_entrypoint.py",
        *args,
    ]
    result = run(command)
    atomic(
        OUT / f"{arm}-launch.json",
        {
            "candidate": candidate,
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    if result.returncode:
        raise RuntimeError(f"pair_server_launch:{arm}:{result.stderr[-1000:]}")
    wait_model()
    return name


def parse_sse(root: pathlib.Path) -> list[dict]:
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


def percentile95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def arm(arm_name: str, candidate: bool) -> dict:
    container = launch(arm_name, candidate)
    atomic(
        OUT / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "arm": arm_name,
            "candidate": candidate,
            "candidate_cuda_started": candidate,
            "scientific_invocation_started": True,
        },
    )
    output = OUT / arm_name
    result = run(
        [
            "sudo",
            "docker",
            "exec",
            container,
            "python3",
            "/work/input/exact_runner.py",
            "--output",
            f"/work/artifacts/pair/{arm_name}",
            "--arm",
            arm_name,
            "--concurrency",
            "32",
        ],
        timeout=2400,
    )
    (OUT / f"{arm_name}.runner.stdout").write_text(result.stdout)
    (OUT / f"{arm_name}.runner.stderr").write_text(result.stderr)
    logs = run(["sudo", "docker", "logs", container], timeout=120)
    (OUT / f"{arm_name}.server.stdout").write_text(logs.stdout)
    (OUT / f"{arm_name}.server.stderr").write_text(logs.stderr)
    health = run(
        ["curl", "-fsS", "--max-time", "15", "http://127.0.0.1:30000/v1/models"]
    )
    terminal_path = output / "TERMINAL.json"
    if result.returncode not in (0, 72) or not terminal_path.exists():
        raise RuntimeError(f"pair_runner_invalid:{arm_name}:{result.returncode}")
    terminal = json.loads(terminal_path.read_text())
    rows = terminal["rows"]
    summary = {
        "terminal": terminal,
        "semantic_rows": parse_sse(output),
        "request_sha256": [row["request_sha256"] for row in rows],
        "p95_completion_seconds": percentile95([row["wall_seconds"] for row in rows]),
        "median_completion_seconds": statistics.median(
            [row["wall_seconds"] for row in rows]
        ),
        "server_healthy_after": health.returncode == 0,
    }
    atomic(OUT / f"{arm_name}-PERSISTED.json", summary)
    run(["sudo", "docker", "rm", "-f", container], timeout=120)
    time.sleep(3)
    return summary


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    candidate_source = PROJECT / "intervention/extend_attention_fixed_m384.py"
    if not candidate_source.exists():
        raise RuntimeError("candidate_source_missing")
    baseline_source = PROJECT / "inputs/upstream/extend_attention.py"
    atomic(
        OUT / "PAIR_BINDING.json",
        {
            "schema_version": 1,
            "candidate_source_sha256": sha256(candidate_source),
            "baseline_source_sha256": sha256(baseline_source),
            "mount_target": (
                "sglang.srt.layers.attention.triton_ops.extend_attention"
            ),
            "order": ["control", "candidate"],
            "fixed_baseline": "decode_equivalent_lm_head@4d99a94e",
        },
    )
    control = arm("control", False)
    candidate = arm("candidate", True)
    semantics_match = (
        control["semantic_rows"] == candidate["semantic_rows"]
        and control["request_sha256"] == candidate["request_sha256"]
    )
    control_time = control["terminal"]["service_seconds_per_request"]
    candidate_time = candidate["terminal"]["service_seconds_per_request"]
    terminal = {
        "schema_version": 1,
        "kind": "matched_profiler_off_exact_c32_pair",
        "complete_32_control": control["terminal"]["complete_requests"] == 32,
        "complete_32_candidate": candidate["terminal"]["complete_requests"] == 32,
        "semantics_match": semantics_match,
        "server_stable": (
            control["server_healthy_after"] and candidate["server_healthy_after"]
        ),
        "control_seconds_per_request": control_time,
        "candidate_seconds_per_request": candidate_time,
        "service_time_delta_fraction": (candidate_time / control_time) - 1,
        "control_p95_completion_seconds": control["p95_completion_seconds"],
        "candidate_p95_completion_seconds": candidate["p95_completion_seconds"],
        "p95_delta_fraction": (
            candidate["p95_completion_seconds"]
            / control["p95_completion_seconds"]
        )
        - 1,
        "control_output_tokens_per_second": control["terminal"][
            "output_tokens_per_second"
        ],
        "candidate_output_tokens_per_second": candidate["terminal"][
            "output_tokens_per_second"
        ],
        "candidate_path_rows": sum(
            1
            for line in (OUT / "candidate-fixed-m384-audit.jsonl").read_text().splitlines()
            if line.strip()
        )
        if (OUT / "candidate-fixed-m384-audit.jsonl").exists()
        else 0,
    }
    terminal["valid"] = (
        terminal["complete_32_control"]
        and terminal["complete_32_candidate"]
        and terminal["semantics_match"]
        and terminal["server_stable"]
        and terminal["candidate_path_rows"] > 0
    )
    atomic(OUT / "PAIR_TERMINAL.json", terminal)
    return 0 if terminal["valid"] else 75


if __name__ == "__main__":
    raise SystemExit(main())
