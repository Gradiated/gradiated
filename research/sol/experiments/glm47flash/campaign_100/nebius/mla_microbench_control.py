#!/usr/bin/env python3
"""Create, measure, retrieve, and destroy one bounded Nebius MLA microbenchmark VM."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from awq_smoke_control import emit  # noqa: E402
from placement_control import (  # noqa: E402
    build_create_command,
    delete_disk,
    delete_instance,
    extract_instance_id,
    extract_public_ipv4,
    find_named_instance,
    get_instance,
    list_items,
    make_cloud_init,
    metadata_id,
    metadata_name,
    VerifiedRetainedOwner,
    wait_absent,
    wait_ssh,
)
from stock_control import run_ssh, scp_from, scp_to, verify_internal_manifest  # noqa: E402
from vllm_smoke_control import (  # noqa: E402
    resolve_created_instance,
    start_independent_watchdog,
    write_create_diagnostic,
)


IMAGE = "vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543"
PLATFORM = "gpu-l40s-a"
PRESET = "1gpu-8vcpu-32gb"
DISK_GIB = 100
HOURLY_RATE_USD = 0.7492
DISK_HOURLY_RATE_USD = 0.0097222
ABSOLUTE_TIMEOUT_SECONDS = 2700


class MicrobenchControlError(RuntimeError):
    pass


def validate_durable_owner(environment: dict[str, str] | None = None) -> None:
    environment = os.environ if environment is None else environment
    if not environment.get("INVOCATION_ID") or environment.get("SYSTEMD_EXEC_PID") != str(os.getpid()):
        raise MicrobenchControlError("provider mutation requires durable service ownership")


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def read_stage_terminal(archive: Path) -> dict[str, object]:
    with tarfile.open(archive, "r:gz") as bundle:
        matches = [member for member in bundle.getmembers() if member.name.endswith("/stage-terminal.json")]
        if len(matches) != 1:
            raise MicrobenchControlError("stage archive lacks exactly one typed stage-terminal.json")
        handle = bundle.extractfile(matches[0])
        if handle is None:
            raise MicrobenchControlError("stage terminal cannot be read")
        try:
            terminal = json.loads(handle.read())
        except json.JSONDecodeError as error:
            raise MicrobenchControlError("stage terminal is not JSON") from error
    if not isinstance(terminal, dict) or not isinstance(terminal.get("stage"), str) or not isinstance(terminal.get("pass"), bool):
        raise MicrobenchControlError("stage terminal has no typed stage/pass contract")
    return terminal


def conditional_trigger(primary: dict[str, object]) -> bool:
    return (
        primary.get("stage") == "primary"
        and primary.get("pass") is True
        and primary.get("all_actual_consumers_pass") is True
        and primary.get("economic_both_envelopes_falsified") is False
    )


def hold_for_repair_decision(output_dir: Path, events: Path, deadline: float) -> None:
    decision_path = output_dir / "repair-decision.json"
    hold_deadline = min(deadline, time.time() + 600)
    emit(events, "repair_window_open", maximum_seconds=max(0, round(hold_deadline - time.time(), 3)))
    while time.time() < hold_deadline:
        if decision_path.exists():
            try:
                action = json.loads(decision_path.read_text()).get("action")
            except Exception:
                action = "invalid"
            emit(events, "repair_decision_received", action=action)
            if action == "teardown":
                return
        time.sleep(5)
    emit(events, "repair_window_expired")


def build_host_bootstrap(runtime_image: str = IMAGE) -> str:
    return f'''set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y docker.io curl ca-certificates gnupg
fi
sudo systemctl enable --now docker
if ! command -v nvidia-ctk >/dev/null 2>&1; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y nvidia-container-toolkit
fi
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
sudo docker pull {runtime_image}
sudo docker image inspect {runtime_image} --format '{{{{json .RepoDigests}}}}'
sudo docker run --rm --gpus all --entrypoint bash {runtime_image} -lc 'rm -f /etc/ld.so.conf.d/00-cuda-compat.conf /etc/ld.so.conf.d/cuda-compat.conf; ldconfig; exec python3 -c "import torch; print(torch.cuda.get_device_name())"'
'''


def build_container_command(
    spec_hash: str, deadline_epoch: int, remote_script: str = "remote_mla_microbench.sh",
    benchmark: str = "vllm_mla_microbench.py", runtime_image: str = IMAGE,
    stage: str = "primary", artifact_basename: str = "mla-microbench",
) -> list[str]:
    return [
        "sudo", "docker", "run", "--rm", "--gpus", "all", "--ipc=host", "--shm-size=16g",
        "-v", "/home/glmrunner/input:/input:ro", "-v", "/workspace:/workspace",
        "-e", f"EXPERIMENT_SPEC_SHA256={spec_hash}",
        "-e", f"CAMPAIGN_DEADLINE_EPOCH={deadline_epoch}",
        "-e", f"RUNTIME_IMAGE_IDENTITY={runtime_image}",
        "-e", f"MICROBENCH_PATH=/input/{benchmark}",
        "-e", f"STAGE={stage}", "-e", f"ARTIFACT_BASENAME={artifact_basename}",
        "--entrypoint", "bash", runtime_image, "-lc",
        f"rm -f /etc/ld.so.conf.d/00-cuda-compat.conf /etc/ld.so.conf.d/cuda-compat.conf; ldconfig; exec bash /input/{remote_script}",
    ]


def run(
    output_dir: Path, name: str, key: Path, public_key: Path, spec_hash: str,
    remote_script: Path | None = None, benchmark_script: Path | None = None,
    input_files: tuple[Path, ...] = (), artifact_basename: str = "mla-microbench",
    absolute_timeout_seconds: int = ABSOLUTE_TIMEOUT_SECONDS, runtime_image: str = IMAGE,
    conditional_remote_script: Path | None = None, conditional_benchmark_script: Path | None = None,
    conditional_input_files: tuple[Path, ...] = (), conditional_artifact_basename: str = "conditional-microbench",
) -> int:
    validate_durable_owner()
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "summary.json").exists():
        raise MicrobenchControlError("completed output directory already exists")
    script = remote_script or HERE / "remote_mla_microbench.sh"
    benchmark = benchmark_script or HERE / "vllm_mla_microbench.py"
    if not script.is_file() or not benchmark.is_file() or not all(path.is_file() for path in input_files):
        raise MicrobenchControlError("microbenchmark inputs are incomplete")
    conditional_paths = (conditional_remote_script, conditional_benchmark_script)
    if any(path is not None for path in conditional_paths):
        if not all(path is not None and path.is_file() for path in conditional_paths) or not all(path.is_file() for path in conditional_input_files):
            raise MicrobenchControlError("conditional microbenchmark inputs are incomplete")
    if list_items("instance"):
        raise MicrobenchControlError("active instances exist")
    events = output_dir / "events.jsonl"
    started = time.time()
    deadline = started + absolute_timeout_seconds
    instance_id = None
    disk_name = name + "-boot"
    outcome = "FAIL"
    stage_records: list[dict[str, object]] = []
    watchdog: dict[str, object] | None = None
    (output_dir / "provider-request.json").write_text(json.dumps({
        "name": name,
        "platform": PLATFORM,
        "preset": PRESET,
        "purchase_model": "preemptible_stop",
        "boot_disk_gib": DISK_GIB,
        "runtime_image": runtime_image,
        "hourly_rate_usd_vendor_calculator": HOURLY_RATE_USD,
        "disk_hourly_rate_usd_vendor_calculator": DISK_HOURLY_RATE_USD,
        "absolute_timeout_seconds": absolute_timeout_seconds,
        "max_total_cost_usd": (HOURLY_RATE_USD + DISK_HOURLY_RATE_USD) * absolute_timeout_seconds / 3600,
        "experiment_spec_sha256": spec_hash,
    }, indent=2, sort_keys=True) + "\n")
    try:
        with VerifiedRetainedOwner(name, output_dir / "cleanup.json") as retained:
            create = build_create_command(
            name=name,
            disk_name=disk_name,
            cloud_init=make_cloud_init(public_key.read_text()),
            disk_gib=DISK_GIB,
            platform=PLATFORM,
            preset=PRESET,
            preemptible=True,
        )
            proc = subprocess.run(create, capture_output=True, text=True, timeout=180)
            write_create_diagnostic(output_dir, proc)
            try:
                instance_id, reconciled_nonzero_exit = resolve_created_instance(proc, name)
            except Exception as error:
                raise MicrobenchControlError(str(error)) from error
            retained.bind_instance(instance_id)
            watchdog = start_independent_watchdog(instance_id, disk_name, deadline, f"{name}-watchdog")
            emit(
                events,
                "instance_created",
                instance_id=instance_id,
                create_returncode=proc.returncode,
                reconciled_nonzero_exit=reconciled_nonzero_exit,
                watchdog=watchdog,
            )
            ip = None
            while time.time() < min(deadline, started + 600):
                payload = get_instance(instance_id)
                if payload is None:
                    raise MicrobenchControlError("instance disappeared before readiness")
                ip = extract_public_ipv4(payload)
                if ip:
                    break
                time.sleep(5)
            if not ip:
                raise MicrobenchControlError("public IP readiness exceeded 600 seconds")
            wait_ssh(ip, key, min(deadline, started + 600))
            emit(events, "ssh_ready", elapsed_seconds=round(time.time() - started, 3))
            bootstrap = run_ssh(ip, key, "bash -s", timeout=1800, input_text=build_host_bootstrap(runtime_image))
            (output_dir / "host-bootstrap.stdout.log").write_text(bootstrap.stdout)
            (output_dir / "host-bootstrap.stderr.log").write_text(bootstrap.stderr)
            if bootstrap.returncode:
                raise MicrobenchControlError("host bootstrap failed")
            if run_ssh(ip, key, "mkdir -p /home/glmrunner/input", timeout=30).returncode:
                raise MicrobenchControlError("remote input directory creation failed")
            all_inputs = [script, benchmark, *input_files]
            if conditional_remote_script and conditional_benchmark_script:
                all_inputs.extend([conditional_remote_script, conditional_benchmark_script, *conditional_input_files])
            scp_to(ip, key, all_inputs, "/home/glmrunner/input/")

            def execute_stage(label: str, stage_script: Path, stage_benchmark: Path, basename: str) -> dict[str, object]:
                remote = run_ssh(ip, key, build_container_command(spec_hash, int(deadline), stage_script.name, stage_benchmark.name, runtime_image, label, basename), timeout=max(60, int(deadline - time.time()) + 180))
                (output_dir / f"{label}.stdout.log").write_text(remote.stdout)
                (output_dir / f"{label}.stderr.log").write_text(remote.stderr)
                partial = output_dir / f".{basename}.tar.gz.partial"
                sidecar = output_dir / f"{basename}.remote.sha256"
                scp_from(ip, key, f"/workspace/public-mla-microbench/{basename}.tar.gz", partial)
                scp_from(ip, key, f"/workspace/public-mla-microbench/{basename}.tar.gz.sha256", sidecar)
                digest = hashlib.sha256(partial.read_bytes()).hexdigest()
                if digest != sidecar.read_text().split()[0]:
                    raise MicrobenchControlError("remote/local artifact hash mismatch")
                archive = output_dir / f"{basename}.tar.gz"; partial.replace(archive)
                terminal = read_stage_terminal(archive)
                record = {"label": label, "returncode": remote.returncode, "archive": archive.name, "sha256": digest, "manifest_file_count": verify_internal_manifest(archive), "terminal": terminal}
                atomic_json(output_dir / f"{label}-stage.json", record)
                emit(events, "stage_retrieved", label=label, sha256=digest, terminal=terminal)
                return record

            primary = execute_stage("primary", script, benchmark, artifact_basename)
            stage_records.append(primary)
            if primary["returncode"] != 0:
                raise MicrobenchControlError("primary remote command failed after typed artifact retrieval")
            if conditional_remote_script and conditional_benchmark_script:
                trigger = conditional_trigger(primary["terminal"])
                atomic_json(output_dir / "conditional-trigger.json", {"primary_terminal": primary["terminal"], "trigger": trigger})
                if trigger:
                    conditional = execute_stage("conditional", conditional_remote_script, conditional_benchmark_script, conditional_artifact_basename)
                    stage_records.append(conditional)
                    if conditional["returncode"] != 0 or conditional["terminal"].get("stage") != "conditional" or conditional["terminal"].get("pass") is not True:
                        raise MicrobenchControlError("conditional terminal failed")
                    outcome = "PASS"; retained.complete("primary_and_conditional_pass")
                else:
                    outcome = "PRIMARY_TERMINAL_FALSE"; retained.complete("primary_terminal_false_cleanup")
            else:
                outcome = "PASS" if primary["terminal"].get("pass") is True else "FAIL"
                if outcome == "PASS":
                    retained.complete("single_stage_pass")
    except Exception as error:
        emit(events, "experiment_error", error_type=type(error).__name__, message=str(error))
    finally:
        cleanup_evidence = output_dir / "cleanup.json"
        cleanup = False
        if cleanup_evidence.exists():
            cleanup = json.loads(cleanup_evidence.read_text()).get("cleanup_pass") is True
        elapsed = max(0.0, time.time() - started)
        cost = elapsed / 3600 * (HOURLY_RATE_USD + DISK_HOURLY_RATE_USD)
        atomic_json(output_dir / "summary.json", {
            "outcome": outcome,
            "cleanup_pass": cleanup,
            "instance_id": instance_id,
            "watchdog": watchdog,
            "allocation_seconds": round(elapsed, 3),
            "cost_usd_derived": round(cost, 9),
            "cost_basis": "measured exposure at authenticated Nebius preemptible VM and disk rates; invoice pending",
            "stage_records": stage_records,
            "ended_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        })
        emit(events, "cleanup_verified", cleanup_pass=cleanup)
    return 0 if outcome == "PASS" and cleanup else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--ssh-public-key", type=Path, required=True)
    parser.add_argument("--experiment-spec-sha256", required=True)
    parser.add_argument("--remote-script", type=Path)
    parser.add_argument("--benchmark-script", type=Path)
    parser.add_argument("--input-file", type=Path, action="append", default=[])
    parser.add_argument("--artifact-basename", default="mla-microbench")
    parser.add_argument("--absolute-timeout-seconds", type=int, default=ABSOLUTE_TIMEOUT_SECONDS)
    parser.add_argument("--runtime-image", default=IMAGE)
    parser.add_argument("--conditional-remote-script", type=Path)
    parser.add_argument("--conditional-benchmark-script", type=Path)
    parser.add_argument("--conditional-input-file", type=Path, action="append", default=[])
    parser.add_argument("--conditional-artifact-basename", default="conditional-microbench")
    args = parser.parse_args()
    return run(
        args.output_dir, args.name, args.ssh_key, args.ssh_public_key, args.experiment_spec_sha256,
        args.remote_script, args.benchmark_script, tuple(args.input_file), args.artifact_basename,
        args.absolute_timeout_seconds, args.runtime_image, args.conditional_remote_script,
        args.conditional_benchmark_script, tuple(args.conditional_input_file),
        args.conditional_artifact_basename,
    )


if __name__ == "__main__":
    raise SystemExit(main())
