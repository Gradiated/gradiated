#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import subprocess


ROOT = pathlib.Path("/home/glmrunner/gemma4-ngram-qlen-mask-observer-v3")
PROJECT = ROOT / "project"
ARTIFACTS = ROOT / "artifacts"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"


def atomic(path: pathlib.Path, value: object) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    command = ["sudo", "docker", "run", "--rm", "--gpus", "all", "--ipc=host", "-v", f"{ROOT}:/work", "-e", "PYTHONPATH=/work/project:/work/project/inputs/bound:/sgl-workspace/sglang/python", IMAGE, "python3", "/work/project/observer_v3_component.py", "--artifact-root", "/work/artifacts/component", "--candidate", "/work/project/inputs/bound/candidate_extend_attention.py", "--prior-component", "/work/project/repair-v2-component-persisted.json"]
    result = subprocess.run(command, text=True, capture_output=True, check=False, timeout=1800)
    (ARTIFACTS / "component.stdout").write_text(result.stdout)
    (ARTIFACTS / "component.stderr").write_text(result.stderr)
    terminal_path = ARTIFACTS / "component/COMPONENT_TERMINAL.json"
    if result.returncode not in (0, 2) or not terminal_path.exists():
        raise RuntimeError(f"observer_component_harness_invalid:{result.returncode}")
    component = json.loads(terminal_path.read_text())
    atomic(ARTIFACTS / "COMPONENT_PERSISTED.json", component)
    if not component["component_pass"]:
        atomic(ARTIFACTS / "FINAL_TERMINAL.json", {"schema_version": 1, "classification": "scientific_terminal", "result": "observer_v3_component_nonpositive_or_incorrect", "component": component, "endpoint_executed": False})
        return 2
    endpoint = subprocess.run(["/usr/bin/python3", str(PROJECT / "candidate_endpoint_once.py")], text=True, capture_output=True, check=False, timeout=6000)
    (ARTIFACTS / "candidate-endpoint.stdout").write_text(endpoint.stdout)
    (ARTIFACTS / "candidate-endpoint.stderr").write_text(endpoint.stderr)
    pair_path = ARTIFACTS / "pair/PAIR_TERMINAL.json"
    if endpoint.returncode not in (0, 75) or not pair_path.exists():
        raise RuntimeError(f"candidate_endpoint_harness_invalid:{endpoint.returncode}")
    pair = json.loads(pair_path.read_text())
    atomic(ARTIFACTS / "FINAL_TERMINAL.json", {"schema_version": 1, "classification": "scientific_terminal", "result": "positive" if pair.get("valid") and pair.get("service_time_delta_fraction", 0) < 0 and pair.get("p95_delta_fraction", 1) < 0.05 else "nonpositive_or_invalid", "component": component, "pair": pair, "endpoint_executed": True})
    return 0 if pair.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
