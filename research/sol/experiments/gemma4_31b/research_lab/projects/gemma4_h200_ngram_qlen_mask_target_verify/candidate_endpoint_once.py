#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import statistics
import subprocess
import time
import urllib.request


ROOT = pathlib.Path("/home/glmrunner/gemma4-ngram-qlen-mask-observer-v3")
PROJECT = ROOT / "project"
OUT = ROOT / "artifacts/pair"
CONTROL = ROOT / "control-reference/control"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout)


def wait_model() -> None:
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen("http://127.0.0.1:30000/v1/models", timeout=5).read()
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("candidate_server_readiness_timeout")


def parse_sse(root: pathlib.Path) -> list[dict]:
    rows = []
    for path in sorted(root.glob("response-*.sse")):
        token_ids, text, finish_reason, usage = [], "", None, None
        for raw in path.read_bytes().splitlines():
            if not raw.startswith(b"data: ") or raw.strip() == b"data: [DONE]":
                continue
            item = json.loads(raw[6:])
            choice = (item.get("choices") or [{}])[0]
            token_ids.extend(choice.get("token_ids") or [])
            text += choice.get("text") or ""
            finish_reason = choice.get("finish_reason", finish_reason)
            usage = item.get("usage", usage)
        rows.append({"token_ids": token_ids, "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "finish_reason": finish_reason, "usage": usage})
    return rows


def p95(values: list[float]) -> float:
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    args = json.loads((PROJECT / "inputs/evidence/candidate-full-launch.json").read_text())["args"]
    name = "gemma-ngram-qlen-candidate-repair-v2"
    run(["sudo", "docker", "rm", "-f", name])
    command = [
        "sudo", "docker", "run", "-d", "--name", name, "--gpus", "all", "--ipc=host", "--network", "host",
        "-v", f"{ROOT}:/work", "-v", f"{PROJECT / 'inputs/bound'}:/work/input:ro",
        "-v", "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint:/work/checkpoint:ro",
        "-v", f"{PROJECT / 'inputs/bound/candidate_extend_attention.py'}:/sgl-workspace/sglang/python/sglang/srt/layers/attention/triton_ops/extend_attention.py:ro",
        "-v", f"{PROJECT / 'inputs/bound/candidate_triton_backend.py'}:/sgl-workspace/sglang/python/sglang/srt/layers/attention/triton_backend.py:ro",
        "-v", f"{PROJECT / 'inputs/bound/candidate_ngram_worker.py'}:/sgl-workspace/sglang/python/sglang/srt/speculative/ngram_worker.py:ro",
        "-e", "PYTHONPATH=/work/input:/sgl-workspace/sglang/python", "-e", "DECODE_EQ_LM_HEAD=1", "-e", "DECODE_EQ_SHADOW_BASELINE=0",
        "-e", "DECODE_EQ_AUDIT=/work/artifacts/pair/candidate-decode-audit.jsonl", "-e", "FP8_MODULE_AUDIT=/work/artifacts/pair/candidate-fp8-modules.jsonl",
        "-e", "FP8_CONSUMER_AUDIT=/work/artifacts/pair/candidate-fp8-consumers.jsonl", "-e", "FP8_RUNTIME_AUDIT=/work/artifacts/pair/candidate-fp8-runtime.json",
        "-e", "NGRAM_TREE_ATTN_AUDIT=/work/artifacts/pair/candidate-tree-attention-audit.jsonl", IMAGE, "python3", "/work/input/endpoint_entrypoint.py", *args,
    ]
    launched = run(command)
    atomic(OUT / "candidate-launch.json", {"command": command, "returncode": launched.returncode, "stdout": launched.stdout, "stderr": launched.stderr})
    if launched.returncode:
        raise RuntimeError(f"candidate_server_launch:{launched.stderr[-1000:]}")
    try:
        wait_model()
        atomic(OUT / "INVOCATION_STATE.json", {"schema_version": 1, "arm": "candidate", "candidate": True, "candidate_cuda_started": True, "scientific_invocation_started": True})
        result = run(["sudo", "docker", "exec", name, "python3", "/work/input/exact_runner.py", "--output", "/work/artifacts/pair/candidate", "--arm", "candidate", "--concurrency", "32"], 2400)
        (OUT / "candidate.runner.stdout").write_text(result.stdout)
        (OUT / "candidate.runner.stderr").write_text(result.stderr)
        logs = run(["sudo", "docker", "logs", name], 120)
        (OUT / "candidate.server.stdout").write_text(logs.stdout)
        (OUT / "candidate.server.stderr").write_text(logs.stderr)
        health = run(["curl", "-fsS", "--max-time", "15", "http://127.0.0.1:30000/v1/models"])
        terminal_path = OUT / "candidate/TERMINAL.json"
        if result.returncode not in (0, 72) or not terminal_path.exists():
            raise RuntimeError(f"candidate_runner_invalid:{result.returncode}")
        candidate = json.loads(terminal_path.read_text())
        control = json.loads((CONTROL / "TERMINAL.json").read_text())
        semantic_match = parse_sse(CONTROL) == parse_sse(OUT / "candidate") and [x["request_sha256"] for x in control["rows"]] == [x["request_sha256"] for x in candidate["rows"]]
        candidate_path_rows = sum(1 for line in (OUT / "candidate-tree-attention-audit.jsonl").read_text().splitlines() if line.strip()) if (OUT / "candidate-tree-attention-audit.jsonl").exists() else 0
        terminal = {"schema_version": 1, "kind": "candidate_only_exact_c32_against_persisted_measured_v1_control", "control_replayed": False, "complete_32_control": control["complete_requests"] == 32, "complete_32_candidate": candidate["complete_requests"] == 32, "semantics_match": semantic_match, "server_stable": health.returncode == 0, "control_seconds_per_request": control["service_seconds_per_request"], "candidate_seconds_per_request": candidate["service_seconds_per_request"], "service_time_delta_fraction": candidate["service_seconds_per_request"] / control["service_seconds_per_request"] - 1, "control_p95_completion_seconds": p95([x["wall_seconds"] for x in control["rows"]]), "candidate_p95_completion_seconds": p95([x["wall_seconds"] for x in candidate["rows"]]), "p95_delta_fraction": p95([x["wall_seconds"] for x in candidate["rows"]]) / p95([x["wall_seconds"] for x in control["rows"]]) - 1, "candidate_path_rows": candidate_path_rows}
        terminal["valid"] = terminal["complete_32_control"] and terminal["complete_32_candidate"] and terminal["semantics_match"] and terminal["server_stable"] and candidate_path_rows > 0
        atomic(OUT / "PAIR_TERMINAL.json", terminal)
        return 0 if terminal["valid"] else 75
    finally:
        run(["sudo", "docker", "rm", "-f", name], 120)


if __name__ == "__main__":
    raise SystemExit(main())
