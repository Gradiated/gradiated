#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import sys
import threading
import time


NAME = "gemma4_h200_dense_fp8_linear_schedule"
LAB = pathlib.Path("/root/workspace/research/lab/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
KEY_CANDIDATES = (
    pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519"),
    pathlib.Path("/root/.config/gradiated/providers/gcore/id_ed25519"),
)
REMOTE = "/home/glmrunner/gemma4-h200-dense-fp8-streamk"
RATE_USD_PER_HOUR = 2.46


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, **kwargs)


def pool(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *arguments],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
        capture_output=True,
        check=check,
    )


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--absolute-deadline-epoch", type=int, required=True)
    parser.add_argument("--prior-exposure-seconds", type=float, required=True)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=False)
    events = args.artifact_root / "outer-events.jsonl"

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(json.dumps({"epoch": time.time(), "event": event, **fields}, sort_keys=True) + "\n")
            handle.flush()

    started = time.time()
    claimed = False
    stop = threading.Event()
    key = None
    release_condition = "ready"

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-1000:])

    thread = threading.Thread(target=heartbeat, daemon=True)
    try:
        lease = max(900, min(3600, args.absolute_deadline_epoch - int(time.time())))
        claim = pool("claim", "--project", NAME, "--bench", args.bench, "--lease-seconds", str(lease))
        claimed = True
        emit("claimed", result=json.loads(claim.stdout))
        thread.start()

        inventory = json.loads((LAB / "runtime/gpus.json").read_text())
        benches = inventory["benches"]
        bench = benches[args.bench] if isinstance(benches, dict) else next(row for row in benches if row["id"] == args.bench)
        sys.path.insert(0, str(NEBIUS))
        from placement_control import extract_public_ipv4, get_instance
        from stock_control import run_ssh

        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip:
            raise RuntimeError("typed_provider_boundary:no_public_ip")
        for candidate in KEY_CANDIDATES:
            if not candidate.is_file():
                continue
            identity = run_ssh(ip, candidate, "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader", timeout=60)
            if identity.returncode == 0:
                key = candidate
                break
        if key is None:
            raise RuntimeError("typed_remote_boundary:ssh_identity_failed")
        (args.artifact_root / "remote-identity.stdout").write_text(identity.stdout)
        (args.artifact_root / "remote-identity.stderr").write_text(identity.stderr)

        module_manifest = run_ssh(
            ip,
            key,
            f"module=$(find {REMOTE}/build -maxdepth 1 -type f -name 'gemma4_fp8_down_streamk*.so' -print -quit); "
            f"test -n \"$module\" && sha256sum \"$module\" && stat -c '%s %n' \"$module\" && cat {REMOTE}/artifacts/BUILD.json",
            timeout=120,
        )
        (args.artifact_root / "producer-manifest.stdout").write_text(module_manifest.stdout)
        (args.artifact_root / "producer-manifest.stderr").write_text(module_manifest.stderr)
        if module_manifest.returncode:
            raise RuntimeError("typed_producer_boundary:resident_module_unavailable")
        server = run_ssh(
            ip,
            key,
            "sudo docker inspect streamk-component --format '{{.State.Running}} {{.Id}}'; "
            "curl -fsS http://127.0.0.1:30000/v1/models",
            timeout=60,
        )
        (args.artifact_root / "resident-server.stdout").write_text(server.stdout)
        (args.artifact_root / "resident-server.stderr").write_text(server.stderr)
        if server.returncode:
            raise RuntimeError("typed_producer_boundary:resident_server_unavailable")

        command = (
            f"test ! -e {REMOTE}/artifacts/component-exact && "
            f"printf '%s\\n' '{{\"candidate_consumer_started\":true,\"producer_replayed\":false}}' "
            f">{REMOTE}/artifacts/CONSUMER_REPAIR_STATE.json.part && "
            f"mv {REMOTE}/artifacts/CONSUMER_REPAIR_STATE.json.part {REMOTE}/artifacts/CONSUMER_REPAIR_STATE.json && "
            f"sudo docker exec streamk-component python3 /work/program/inputs/runtime/fp8_qkv_paired_runner.py "
            f"--output /work/artifacts/component-exact --arm component --concurrency 32 "
            f">{REMOTE}/artifacts/component-exact.runner.stdout "
            f"2>{REMOTE}/artifacts/component-exact.runner.stderr"
        )
        consumer = run_ssh(
            ip,
            key,
            f"timeout --signal=TERM {max(600, args.absolute_deadline_epoch - int(time.time()) - 600)} bash -lc {shlex.quote(command)}",
            timeout=max(660, args.absolute_deadline_epoch - int(time.time())),
        )
        emit("consumer_returned", returncode=consumer.returncode)
        (args.artifact_root / "consumer-ssh.stdout").write_text(consumer.stdout)
        (args.artifact_root / "consumer-ssh.stderr").write_text(consumer.stderr)

        required = {
            "CONSUMER_REPAIR_STATE.json": f"{REMOTE}/artifacts/CONSUMER_REPAIR_STATE.json",
            "RUNNER_TERMINAL.json": f"{REMOTE}/artifacts/component-exact/TERMINAL.json",
            "runner.stdout": f"{REMOTE}/artifacts/component-exact.runner.stdout",
            "runner.stderr": f"{REMOTE}/artifacts/component-exact.runner.stderr",
            "down_streamk.jsonl": f"{REMOTE}/artifacts/component-audit/down_streamk.jsonl",
        }
        for local_name, remote_path in required.items():
            retrieved = run_ssh(ip, key, f"cat {shlex.quote(remote_path)}", timeout=120)
            (args.artifact_root / local_name).write_text(retrieved.stdout)
            (args.artifact_root / f"{local_name}.stderr").write_text(retrieved.stderr)
            if retrieved.returncode:
                raise RuntimeError(f"typed_retrieval_boundary:{local_name}")
        if consumer.returncode:
            raise RuntimeError("typed_consumer_boundary:exact_runner_failed")

        component = args.artifact_root / "COMPONENT_TERMINAL.json"
        consumed = run(
            [
                sys.executable,
                str(PROJECT / "consume_component.py"),
                "--audit",
                str(args.artifact_root / "down_streamk.jsonl"),
                "--runner-terminal",
                str(args.artifact_root / "RUNNER_TERMINAL.json"),
                "--build-log",
                str(PROJECT / "artifacts/dense-streamk-20260722t2236z/owner-repair1/remote/build.stdout"),
                "--sync-terminal",
                str(PROJECT / "artifacts/dense-streamk-20260722t2236z/prepared/SYNC_TERMINAL.json"),
                "--sync-binding",
                str(PROJECT / "artifacts/dense-streamk-20260722t2236z/prepared/SYNC_BINDING.json"),
                "--output",
                str(component),
            ],
            capture_output=True,
        )
        (args.artifact_root / "consume.stdout").write_text(consumed.stdout)
        (args.artifact_root / "consume.stderr").write_text(consumed.stderr)
        decision = json.loads(component.read_text())
        exposure = time.time() - started
        spend = exposure * RATE_USD_PER_HOUR / 3600
        prior_spend = args.prior_exposure_seconds * RATE_USD_PER_HOUR / 3600
        decision.update(
            classification="close_streamk_candidate" if not decision.get("correctness_pass") else decision["classification"],
            provider_exposure_seconds=exposure,
            provider_spend_usd=spend,
            prior_provider_spend_usd=prior_spend,
            cumulative_provider_spend_usd=prior_spend + spend,
            producer_replayed=False,
            consumer_only_repair=True,
        )
        atomic(args.artifact_root / "TERMINAL.json", decision)
        emit("scientific_terminal", classification=decision["classification"], spend_usd=spend)
        return 0
    except Exception as exception:
        atomic(
            args.artifact_root / "OUTER_FAILURE.json",
            {"classification": str(exception).split(":", 1)[0], "message": str(exception), "provider_exposure_seconds": time.time() - started},
        )
        if str(exception).startswith(("typed_provider_boundary", "typed_remote_boundary", "typed_retrieval_boundary")):
            release_condition = "maintenance"
        raise
    finally:
        if claimed:
            stop.set()
            thread.join(timeout=5)
            contents = {
                "project": NAME,
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "checkpoint": f"Exact checkpoint hard links retained at {REMOTE}/checkpoint",
                "image": "Pinned SGLang v0.5.13 digest 6113665 retained",
                "runtime": "Dense-FP8 Stream-K producer and consumer-repair artifacts retained",
                "caches": f"Compiled Stream-K module and CUDA caches retained at {REMOTE}/build",
                "server_state": "Healthy streamk-component server retained when responsive",
                "artifacts": str(args.artifact_root),
            }
            atomic(args.artifact_root / "BENCH_CONTENTS.json", contents)
            pool("release", "--project", NAME, "--condition", release_condition, "--contents", str(args.artifact_root / "BENCH_CONTENTS.json"), check=False)


if __name__ == "__main__":
    raise SystemExit(main())
