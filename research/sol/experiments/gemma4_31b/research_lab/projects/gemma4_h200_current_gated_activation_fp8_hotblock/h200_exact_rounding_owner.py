#!/usr/bin/env python3
"""Bounded controller-host owner for the one exact-rounding H200 invocation."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
LAB = ROOT.parents[2]
BENCH = "h200-streaming-global-kv-fresh-computeinstance-e00n8vffvr4jkmm33f"
PROJECT = "gemma4_h200_current_gated_activation_fp8_hotblock"
DEADLINE = "2026-07-29T16:58:00Z"
OUT = ROOT / "artifacts/gated-activation-fp8-exact-rounding-h200-20260729t1646z-repair1"
STATE = OUT / "OWNER_STATE.json"
LOG = OUT / "OWNER_PROGRESS.log"
REMOTE = "/home/glmrunner/gated-activation-fp8-exact-rounding-20260729t1646z-repair1"
SSH = ["ssh", "-i", "/root/.config/nebius/glm-campaign/ssh_ed25519", "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts", "-o", "StrictHostKeyChecking=yes", "glmrunner@89.169.96.163"]
SCP = ["scp", "-i", "/root/.config/nebius/glm-campaign/ssh_ed25519", "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts", "-o", "StrictHostKeyChecking=yes"]


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(tmp.read_text())
    os.replace(tmp, path)


def record(phase: str, **more: object) -> None:
    data = {"phase": phase, "updated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "deadline_utc": DEADLINE, **more}
    atomic(STATE, data)
    with LOG.open("a") as f:
        f.write(json.dumps(data, sort_keys=True) + "\n")


def run(argv: list[str], timeout: int = 300, **kw: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, **kw)


def heartbeat() -> None:
    run(["bash", "-lc", f"PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab {LAB} heartbeat --project {PROJECT} --bench {BENCH}"], 20)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=False)
    record("claimed_owner_started", remote_root=REMOTE)
    heartbeat()
    files = ["h200_exact_rounding_runner.py", "h200_runner.py", "gated_activation_fp8_exact_rounding.py", "gated_activation_fp8_exact_rounding.cu", "GATED_ACTIVATION_FP8_COMPONENT_EXECUTION_MANIFEST_20260729T1622Z.json", "inputs/gemma4-layer0-down-proj-component.safetensors"]
    hashes = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files}
    atomic(OUT / "STAGED_INPUT_HASHES.json", hashes)
    prep = run(SSH + [f"rm -rf {REMOTE}.tmp; mkdir -p {REMOTE}.tmp/inputs"], 30)
    if prep.returncode:
        record("remote_pre_science_failure", stderr=prep.stderr, stdout=prep.stdout); return 2
    for f in files:
        target = f"glmrunner@89.169.96.163:{REMOTE}.tmp/{f}"
        cp = run(SCP + [str(ROOT / f), target], 180)
        if cp.returncode:
            record("stage_failure", file=f, stderr=cp.stderr, stdout=cp.stdout); return 2
    verify = run(SSH + [f"cd {REMOTE}.tmp && sha256sum {' '.join(files)} && mv {REMOTE}.tmp {REMOTE}"], 60)
    if verify.returncode:
        record("stage_verify_failure", stderr=verify.stderr, stdout=verify.stdout); return 2
    record("staged_and_verified", hashes=hashes)
    heartbeat()
    cmd = f"cd {REMOTE} && sudo -n docker run --rm --gpus all -v {REMOTE}:/workspace -w /workspace docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6 python3 h200_exact_rounding_runner.py --component-safetensors inputs/gemma4-layer0-down-proj-component.safetensors --component-manifest GATED_ACTIVATION_FP8_COMPONENT_EXECUTION_MANIFEST_20260729T1622Z.json --output artifacts/gated-activation-fp8-exact-rounding-h200-20260729t1646z-repair1 --repetitions 100; code=$?; sudo -n chown -R glmrunner:glmrunner {REMOTE}/artifacts; exit $code"
    record("science_command_submitted")
    result = run(SSH + [cmd], 330)
    (OUT / "remote_runner.stdout").write_text(result.stdout)
    (OUT / "remote_runner.stderr").write_text(result.stderr)
    record("science_command_returned", returncode=result.returncode)
    retrieve = run(SCP + ["-r", f"glmrunner@89.169.96.163:{REMOTE}/artifacts/gated-activation-fp8-exact-rounding-h200-20260729t1646z-repair1", str(OUT / "remote-artifacts")], 90)
    if retrieve.returncode:
        record("retrieval_failure", stderr=retrieve.stderr, stdout=retrieve.stdout, runner_returncode=result.returncode); return 3
    terminal = OUT / "remote-artifacts/TERMINAL.json"
    if terminal.exists():
        atomic(OUT / "RETRIEVED_TERMINAL.json", json.loads(terminal.read_text()))
        record("terminal_retrieved", terminal_sha256=hashlib.sha256(terminal.read_bytes()).hexdigest(), runner_returncode=result.returncode)
        return 0
    record("terminal_missing", runner_returncode=result.returncode)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
