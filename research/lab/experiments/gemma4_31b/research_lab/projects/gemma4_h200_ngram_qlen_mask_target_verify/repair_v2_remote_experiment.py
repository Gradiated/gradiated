#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import subprocess


ROOT = pathlib.Path("/home/glmrunner/gemma4-ngram-qlen-mask")
PROJECT = ROOT / "project"
ARTIFACTS = ROOT / "artifacts"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False, timeout=timeout)


def component() -> dict:
    command = [
        "sudo", "docker", "run", "--rm", "--gpus", "all", "--ipc=host",
        "-v", f"{ROOT}:/work",
        "-e", "PYTHONPATH=/work/project:/work/project/inputs/bound:/sgl-workspace/sglang/python",
        IMAGE, "python3", "/work/project/component_benchmark.py",
        "--artifact-root", "/work/artifacts/component",
        "--candidate", "/work/project/inputs/bound/candidate_extend_attention.py",
    ]
    result = run(command, 1800)
    (ARTIFACTS / "component.stdout").write_text(result.stdout)
    (ARTIFACTS / "component.stderr").write_text(result.stderr)
    terminal_path = ARTIFACTS / "component" / "COMPONENT_TERMINAL.json"
    if result.returncode not in (0, 2) or not terminal_path.exists():
        raise RuntimeError(f"component_harness_invalid:{result.returncode}")
    terminal = json.loads(terminal_path.read_text())
    atomic(ARTIFACTS / "COMPONENT_PERSISTED.json", terminal)
    return terminal


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    component_value = component()
    if not component_value.get("component_pass"):
        atomic(ARTIFACTS / "FINAL_TERMINAL.json", {
            "schema_version": 1, "classification": "scientific_terminal",
            "result": "component_nonpositive_or_incorrect", "component": component_value,
            "endpoint_executed": False,
        })
        return 2
    result = run(["/usr/bin/python3", str(PROJECT / "candidate_endpoint_once.py")], 6000)
    (ARTIFACTS / "candidate-endpoint.stdout").write_text(result.stdout)
    (ARTIFACTS / "candidate-endpoint.stderr").write_text(result.stderr)
    pair_path = ARTIFACTS / "pair" / "PAIR_TERMINAL.json"
    if result.returncode not in (0, 75) or not pair_path.exists():
        raise RuntimeError(f"candidate_endpoint_harness_invalid:{result.returncode}")
    pair = json.loads(pair_path.read_text())
    atomic(ARTIFACTS / "FINAL_TERMINAL.json", {
        "schema_version": 1, "classification": "scientific_terminal",
        "result": "positive" if pair.get("valid") and pair.get("service_time_delta_fraction", 0) < 0 and pair.get("p95_delta_fraction", 1) < 0.05 else "nonpositive_or_invalid",
        "component": component_value, "counters": "not_collected_profiler_off_first",
        "pair": pair, "endpoint_executed": True,
    })
    return 0 if pair.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
