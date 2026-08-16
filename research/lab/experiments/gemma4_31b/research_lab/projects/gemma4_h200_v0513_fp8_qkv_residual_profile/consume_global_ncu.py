#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time


NAME = "gemma4_h200_v0513_fp8_qkv_residual_profile"
LAB = pathlib.Path("/root/workspace/research/lab/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
BENCH = "h200-v0513-fp8qkv-e00t4pa49nhc2g7jwe"
REMOTE = "/home/glmrunner/gemma4-h200-v0513-fp8-qkv-residual-profile"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"


def pool(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args],
        env={**os.environ, "PYTHONPATH": str(FACTORY)}, capture_output=True, text=True, check=check,
    )


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    output = PROJECT / "artifacts/global-ncu-20260720t1136z"
    started = time.time()
    status = json.loads((PROJECT / "STATUS.json").read_text())
    prior = float(status["measured_project_spend_usd"])
    claimed = False
    terminal: dict[str, object] = {}
    try:
        claim = pool("claim", "--project", NAME, "--bench", BENCH, "--lease-seconds", "600")
        claimed = True
        inventory = json.loads((LAB / "runtime/gpus.json").read_text())
        benches = inventory["benches"]
        bench = benches[BENCH] if isinstance(benches, dict) else next(row for row in benches if row["id"] == BENCH)
        sys.path.insert(0, str(NEBIUS))
        from placement_control import extract_public_ipv4, get_instance
        from stock_control import run_ssh
        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip:
            raise RuntimeError("typed_provider_boundary:no_public_ip")
        command = (
            f"sudo docker run --rm -v {REMOTE}:/work {IMAGE} /usr/local/cuda/bin/ncu "
            "--import /work/global-ncu-artifacts/global-fwd.ncu-rep --csv --page raw "
            f"| sudo tee {REMOTE}/global-ncu-artifacts/ncu-export.csv >/dev/null"
        )
        result = run_ssh(ip, KEY, command, timeout=180)
        (output / "ncu-consumer.stdout").write_text(result.stdout)
        (output / "ncu-consumer.stderr").write_text(result.stderr)
        if result.returncode:
            raise RuntimeError("typed_consumer_boundary:ncu_export_failed")
        local_csv = output / "global_ncu/ncu-export.csv"
        copied = subprocess.run([
            "scp", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", f"glmrunner@{ip}:{REMOTE}/global-ncu-artifacts/ncu-export.csv", str(local_csv),
        ], capture_output=True, text=True, timeout=120)
        if copied.returncode:
            raise RuntimeError("typed_retrieval_boundary:ncu_export_scp_failed")
        raw = local_csv.read_text(errors="replace")
        if '"_fwd_kernel"' not in raw:
            raise RuntimeError("typed_counter_boundary:exact_global_kernel_absent")
        exposure = time.time() - started
        rate = float(bench["hourly_cost_usd"])
        terminal = {"schema_version": 1, "status": "terminal", "pass": True, "classification": "ncu_complete", "report_sha256": hashlib.sha256((output / "global_ncu/global-fwd.ncu-rep").read_bytes()).hexdigest(), "csv_sha256": hashlib.sha256(local_csv.read_bytes()).hexdigest(), "provider_exposure_seconds": exposure, "provider_spend_usd": exposure * rate / 3600, "cumulative_provider_spend_usd": prior + exposure * rate / 3600}
        atomic(output / "NCU_TERMINAL.json", terminal)
        return 0
    except Exception as error:
        terminal = {"schema_version": 1, "status": "terminal", "pass": False, "classification": "ncu_consumer_failure", "error": {"type": type(error).__name__, "message": str(error)}}
        atomic(output / "NCU_TERMINAL.json", terminal)
        return 1
    finally:
        if claimed:
            pool("release", "--project", NAME, "--condition", "ready", check=False)


if __name__ == "__main__":
    raise SystemExit(main())
