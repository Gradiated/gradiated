#!/usr/bin/env python3
"""One-shot Gemma FP8 owner using the shared Nebius retained-owner primitives."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path


P = Path(__file__).resolve().parent
N = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
sys.path.insert(0, str(N))

from placement_control import (  # noqa: E402
    VerifiedRetainedOwner,
    build_create_command,
    extract_instance_id,
    extract_public_ipv4,
    get_instance,
    make_cloud_init,
)
from session_staging import transfer_checkpoint, transfer_timeout_seconds  # noqa: E402
from stock_control import (  # noqa: E402
    extract_member,
    run_ssh,
    scp_from,
    scp_to,
    verify_internal_manifest,
)
from vllm_smoke_control import start_independent_watchdog, write_create_diagnostic  # noqa: E402


IMAGE = "vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
CHECKPOINT_TERMINAL_SHA256 = "5f0765fa37f308e21d665571a92c29ba1998b22b5ee67d1edbfac103dafec481"
INDEX_SHA256 = "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2"
TRACE_SHA256 = "ccc559094ee612d5da11e771c2ebf8ac14046ad03b8ec7bd6ae165be25725d68"
ECONOMICS_SHA256 = "690e0e457c6e8e9121b54fb7f88abc92c3dcc358e1d71accffddb083878d00d6"
PLANNING_HURDLE_RPS = 0.7170614380702235
CONSERVATIVE_HURDLE_RPS = 1.1583551336753017
GPU_RATE_USD_PER_HOUR = 0.8484
DISK_RATE_USD_PER_HOUR = 0.0194444

CK = P.parent / "sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint"
TERM = CK.parent / "CHECKPOINT_TERMINAL.json"
PACK = P.parent / "gemma_exact_cache_trace_contract/TRACE_PACKET.json"
ECONOMICS = P.parent / "l40s_saturation_economic_gate/SATURATION_GATE.json"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUB = Path("/root/.config/nebius/glm-campaign/ssh_ed25519.pub")
PROGRAM_FILES = (P / "gemma_fp8_owner.py", P / "gemma_fp8_runner.py", P / "remote_gemma_fp8.sh")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def inventory() -> list[dict[str, object]]:
    rows = []
    for kind in ("instance", "disk"):
        command = [
            "/root/.nebius/bin/nebius", "compute", kind, "list",
            "--parent-id", "project-e00h1vhmpr00vbmfd5k7pg", "--all",
            "--profile", "glm-campaign", "--format", "json", "--no-progress",
            "--timeout", "30s",
        ]
        query = subprocess.run(command, capture_output=True, text=True, timeout=40)
        try:
            value = json.loads(query.stdout) if query.stdout.strip() else None
        except json.JSONDecodeError:
            value = None
        empty_payload = value in ({}, [])
        if isinstance(value, dict):
            listed = value.get("items", value.get("instances", value.get("disks")))
            empty_payload = empty_payload or listed == []
        rows.append(
            {
                "kind": kind,
                "returncode": query.returncode,
                "stdout_sha256": hashlib.sha256(query.stdout.encode()).hexdigest(),
                "stderr_sha256": hashlib.sha256(query.stderr.encode()).hexdigest(),
                "empty": query.returncode == 0 and empty_payload and not query.stderr.strip(),
            }
        )
    return rows


def build_host_bootstrap() -> str:
    return f"""set -Eeuo pipefail
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
for attempt in 1 2 3; do sudo docker pull {IMAGE} && break; test "$attempt" = 3 && exit 1; sleep 10; done
sudo docker image inspect {IMAGE} --format '{{{{json .RepoDigests}}}}'
sudo docker run --rm --gpus all {IMAGE} nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits
"""


def build_create_argv(name: str) -> list[str]:
    return build_create_command(
        name=name,
        disk_name=name + "-boot",
        cloud_init=make_cloud_init(PUB.read_text()),
        disk_gib=200,
        platform="gpu-l40s-a",
        preset="1gpu-16vcpu-64gb",
        preemptible=True,
    )


def build_remote_argv(deadline_epoch: int, provider_started_epoch: float) -> list[str]:
    return [
        "sudo", "docker", "run", "--rm", "--gpus", "all", "--ipc=host",
        "-v", "/home/glmrunner/input:/input:ro", "-v", "/workspace:/workspace",
        "-e", f"CAMPAIGN_DEADLINE_EPOCH={deadline_epoch}",
        "-e", f"CAMPAIGN_PROVIDER_STARTED_EPOCH={provider_started_epoch:.6f}",
        "-e", f"GEMMA_RUNTIME_IMAGE={IMAGE}",
        "-e", f"EXPERIMENT_SPEC_SHA256={sha256_file(PACK)}",
        "-e", f"ECONOMICS_SPEC_SHA256={sha256_file(ECONOMICS)}",
        "-e", f"PROVIDER_GPU_RATE_USD_PER_HOUR={GPU_RATE_USD_PER_HOUR}",
        "-e", f"PROVIDER_DISK_RATE_USD_PER_HOUR={DISK_RATE_USD_PER_HOUR}",
        "--entrypoint", "bash", IMAGE, "/input/remote_gemma_fp8.sh",
    ]


def _trace_contract(packet: dict[str, object]) -> bool:
    identity = packet.get("identity")
    if not isinstance(identity, dict) or identity.get("model") != "google/gemma-4-31B-it":
        return False
    if identity.get("revision") != REVISION or identity.get("runtime_image") != IMAGE:
        return False
    groups = packet.get("primary_groups")
    if not isinstance(groups, list) or [(row.get("name"), row.get("concurrency")) for row in groups] != [
        ("primary_c1", 1), ("primary_c4", 4), ("primary_c8", 8), ("primary_c16", 16)
    ]:
        return False
    request_bodies = []
    for group in groups:
        if group.get("maximum_cacheable_common_tokens") != 528:
            return False
        assertions = group.get("metrics_assertions")
        if not isinstance(assertions, dict) or assertions.get("scored_query_delta_tokens") != group["concurrency"] * 4214:
            return False
        request_bodies.append(group["warmup"]["request_body"])
        request_bodies.extend(row["request_body"] for row in group["scored"])
    separate = packet.get("separate_10k_stream")
    if not isinstance(separate, dict):
        return False
    request_bodies.append(separate["request_body"])
    return all(
        isinstance(body.get("prompt"), list)
        and all(isinstance(token, int) for token in body["prompt"])
        and body.get("add_special_tokens") is False
        and body.get("return_token_ids") is True
        and body.get("stream") is True
        and body.get("stream_options") == {"include_usage": True}
        for body in request_bodies
    ) and len(separate["request_body"]["prompt"]) == 10_000 and separate["request_body"].get("max_tokens") == 358


def _source_contract() -> dict[str, bool]:
    owner_source = (P / "gemma_fp8_owner.py").read_text()
    runner_source = (P / "gemma_fp8_runner.py").read_text()
    remote_source = (P / "remote_gemma_fp8.sh").read_text()
    ast.parse(owner_source)
    ast.parse(runner_source)
    required_runner = (
        "prompt_token_ids_returned", "output_token_ids", "ttft_ms", "itl_ms",
        "request_queue_time_seconds_sum", "request_prefill_time_seconds_sum",
        "request_decode_time_seconds_sum", "prefix_cache_queries", "prefix_cache_hits",
        "single_10k",
        "atomic_json", "economics", "complete_request_count", "failure_count",
    )
    required_remote = (
        "telemetry.csv", "utilization.gpu", "memory.used", "power.draw",
        "semantic_and_baseline", "PREFIX_TRIGGER", "PREFIX_START_READY",
        "prefix-off", "PREFIX_FALSE_CLEANUP", "allocation-result.json",
        "provider_seconds", "reload_count", "manifest.json", ".tar.gz.tmp",
    )
    required_owner = (
        "VerifiedRetainedOwner", "transfer_checkpoint", "start_independent_watchdog",
        "write_create_diagnostic", "verify_internal_manifest", ".part", "/workspace",
        "build_create_argv", "build_remote_argv", "validate_allocation_result",
    )
    return {
        "runner_complete_contract": all(value in runner_source for value in required_runner),
        "remote_complete_contract": all(value in remote_source for value in required_remote),
        "shared_lifecycle_contract": all(value in owner_source for value in required_owner),
        "semantic_before_ladder": remote_source.index("phase semantic_and_baseline begin") < remote_source.index('PREFIX_TRIGGER="$(python3'),
        "internal_manifest_and_atomic_retrieval": "verify_internal_manifest(archive_part)" in owner_source and "archive_part.replace(archive)" in owner_source,
        "user_owned_workspace": "sudo chown -R glmrunner:glmrunner /workspace /home/glmrunner/input" in owner_source,
        "continuous_hbm_util_power": all(value in remote_source for value in ("memory.used", "utilization.gpu", "power.draw", "sleep 1")),
        "prefix_trigger_and_false_cleanup": all(value in remote_source for value in ("PREFIX_TRIGGER", "PREFIX_START_READY", "PREFIX_FALSE_CLEANUP=true", "PREFIX_RC")),
    }


def audit(output: Path, name: str, deadline_seconds: int) -> None:
    terminal = json.loads(TERM.read_text())
    packet = json.loads(PACK.read_text())
    economics = json.loads(ECONOMICS.read_text())
    create_argv = build_create_argv(name)
    remote_argv = build_remote_argv(1_900_000_000, 1_899_995_200.0)
    source_checks = _source_contract()
    syntax = {
        "owner_py_compile": subprocess.run([sys.executable, "-m", "py_compile", str(P / "gemma_fp8_owner.py")], capture_output=True).returncode == 0,
        "runner_py_compile": subprocess.run([sys.executable, "-m", "py_compile", str(P / "gemma_fp8_runner.py")], capture_output=True).returncode == 0,
        "remote_bash_n": subprocess.run(["bash", "-n", str(P / "remote_gemma_fp8.sh")], capture_output=True).returncode == 0,
    }
    planning = economics["economic_surface"]["planning_base"]["DeepInfra_fp8"]["required_completed_requests_per_second"]["planning"]
    conservative = economics["economic_surface"]["conservative"]["DeepInfra_fp8"]["required_completed_requests_per_second"]["planning"]
    checks = {
        "artifacts_parent_exists": output.parent == P / "artifacts" and output.parent.is_dir(),
        "fresh_owner_output_nonexistent": not output.exists(),
        "fresh_lowercase_name": name == name.lower() and name.startswith("gemma-l40s-fp8-") and name not in {"gemma-l40s-fp8-20260717t091500z"},
        "ssh_keypair_present": KEY.is_file() and PUB.is_file(),
        "checkpoint_terminal_exact": sha256_file(TERM) == CHECKPOINT_TERMINAL_SHA256 and terminal.get("pass") is True and terminal.get("revision") == REVISION and terminal.get("checkpoint_root") == str(CK),
        "checkpoint_index_exact": sha256_file(CK / "model.safetensors.index.json") == INDEX_SHA256,
        "runtime_image_exact": IMAGE in remote_argv and f"GEMMA_RUNTIME_IMAGE={IMAGE}" in remote_argv,
        "trace_exact": sha256_file(PACK) == TRACE_SHA256 and _trace_contract(packet),
        "economics_exact": sha256_file(ECONOMICS) == ECONOMICS_SHA256 and planning == PLANNING_HURDLE_RPS and conservative == CONSERVATIVE_HURDLE_RPS,
        "real_create_argv": create_argv[0] == "/root/.nebius/bin/nebius" and create_argv[1:4] == ["compute", "instance", "create"] and create_argv[create_argv.index("--name") + 1] == name and create_argv[create_argv.index("--resources-platform") + 1] == "gpu-l40s-a" and create_argv[create_argv.index("--boot-disk-managed-disk-size-gibibytes") + 1] == "200",
        "remote_container_contract": remote_argv[-3:] == ["--entrypoint", "bash", IMAGE, "/input/remote_gemma_fp8.sh"][-3:] and "/workspace:/workspace" in remote_argv and "/home/glmrunner/input:/input:ro" in remote_argv,
        "budget_contract": deadline_seconds == 4800 and GPU_RATE_USD_PER_HOUR * deadline_seconds / 3600 + DISK_RATE_USD_PER_HOUR * deadline_seconds / 3600 < 2.0,
        **syntax,
        **source_checks,
    }
    report = {
        "schema_version": 2,
        "classification": "full_contract_final_program_terminal",
        "name": name,
        "owner_output": str(output),
        "deadline_seconds": deadline_seconds,
        "checks": checks,
        "pass": all(checks.values()),
        "identities": {
            "checkpoint_terminal_sha256": sha256_file(TERM),
            "checkpoint_index_sha256": sha256_file(CK / "model.safetensors.index.json"),
            "runtime_image": IMAGE,
            "trace_sha256": sha256_file(PACK),
            "economics_sha256": sha256_file(ECONOMICS),
        },
        "program_sha256": {path.name: sha256_file(path) for path in PROGRAM_FILES},
        "create_argv_sha256": hashlib.sha256(json.dumps(create_argv, separators=(",", ":")).encode()).hexdigest(),
        "remote_argv_sha256": hashlib.sha256(json.dumps(remote_argv, separators=(",", ":")).encode()).hexdigest(),
        "first_scientific_arms": ["semantic_falsifier", "primary_c1", "primary_c4", "primary_c8", "primary_c16", "separate_10k"],
        "conditional_arm": {"arm": "prefix_off_primary_c16", "threshold": 0.393755, "start_ready_seconds": 600, "false_branch": "cleanup"},
    }
    atomic_json(P / "FINAL_PROGRAM_AUDIT.json", report)
    if not report["pass"]:
        failed = [key for key, value in checks.items() if not value]
        raise RuntimeError("final program audit failed: " + ", ".join(failed))


def retrieve(ip: str, output: Path) -> dict[str, object]:
    archive_part = output / "remote-artifact.tar.gz.part"
    sidecar_part = output / "remote-artifact.tar.gz.sha256.part"
    scp_from(ip, KEY, "/workspace/public-gemma4-online-fp8/gemma4-online-fp8.tar.gz", archive_part)
    scp_from(ip, KEY, "/workspace/public-gemma4-online-fp8/gemma4-online-fp8.tar.gz.sha256", sidecar_part)
    if sha256_file(archive_part) != sidecar_part.read_text().split()[0]:
        raise RuntimeError("artifact hash mismatch")
    manifest_files = verify_internal_manifest(archive_part)
    result = json.loads(extract_member(archive_part, "/allocation-result.json"))
    archive = output / "remote-artifact.tar.gz"
    sidecar = output / "remote-artifact.tar.gz.sha256"
    archive_part.replace(archive)
    sidecar_part.replace(sidecar)
    atomic_json(output / "artifact-retrieval-terminal.json", {"pass": True, "archive_sha256": sha256_file(archive), "manifest_file_count": manifest_files})
    return result


def validate_allocation_result(result: dict[str, object]) -> bool:
    required = {
        "complete", "pass", "semantic", "profiles", "single_10k", "prefix_trigger",
        "prefix_executed", "prefix_disposition", "complete_request_count", "failure_count",
        "reload_count", "economics", "useful_gpu_seconds", "provider_seconds",
        "provider", "runtime_image", "experiment_spec_sha256", "economics_spec_sha256",
    }
    return required.issubset(result) and result.get("experiment_spec_sha256") == TRACE_SHA256 and result.get("economics_spec_sha256") == ECONOMICS_SHA256


def run(output: Path, name: str, deadline_seconds: int) -> int:
    if not os.getenv("INVOCATION_ID") or os.getenv("SYSTEMD_EXEC_PID") != str(os.getpid()):
        raise RuntimeError("durable systemd owner required")
    audit(output, name, deadline_seconds)
    rows = inventory()
    atomic_json(P / "PROVIDER_INVENTORY.json", {"pass": all(row["empty"] for row in rows), "resources": rows, "timestamp_epoch": time.time()})
    if not all(row["empty"] for row in rows):
        raise RuntimeError("authenticated inventory not empty")
    output.mkdir()
    started = time.time()
    deadline = started + deadline_seconds
    instance_id = None
    stage = "create"
    result = None
    remote_returncode = None
    try:
        with VerifiedRetainedOwner(name, output / "cleanup.json") as owner:
            create = subprocess.run(build_create_argv(name), capture_output=True, text=True, timeout=180)
            write_create_diagnostic(output, create)
            if create.returncode:
                raise RuntimeError("provider create failed")
            instance_id = extract_instance_id(json.loads(create.stdout))
            owner.bind_instance(instance_id)
            watchdog = start_independent_watchdog(instance_id, name + "-boot", deadline, name + "-watchdog")
            atomic_json(output / "watchdog.json", watchdog)
            ip = None
            while time.time() < min(deadline, started + 600):
                instance = get_instance(instance_id)
                ip = extract_public_ipv4(instance) if instance else None
                if ip:
                    break
                time.sleep(5)
            if not ip:
                raise RuntimeError("public IP readiness exceeded")
            from placement_control import wait_ssh

            wait_ssh(ip, KEY, min(deadline, started + 600))
            stage = "workspace"
            workspace = run_ssh(ip, KEY, "sudo mkdir -p /workspace/model /home/glmrunner/input && sudo chown -R glmrunner:glmrunner /workspace /home/glmrunner/input", timeout=60)
            if workspace.returncode:
                raise RuntimeError("remote workspace ownership failed")
            stage = "bootstrap"
            bootstrap = run_ssh(ip, KEY, "bash -s", timeout=min(1800, max(60, int(deadline - time.time() - 900))), input_text=build_host_bootstrap())
            (output / "host-bootstrap.stdout.log").write_text(bootstrap.stdout)
            (output / "host-bootstrap.stderr.log").write_text(bootstrap.stderr)
            if bootstrap.returncode:
                raise RuntimeError("exact-image host bootstrap failed")
            stage = "transfer"
            total_bytes = sum(path.stat().st_size for path in CK.iterdir() if path.is_file())
            transfer = transfer_checkpoint(
                ip,
                KEY,
                CK,
                "/workspace/model",
                timeout_seconds=min(transfer_timeout_seconds(total_bytes), max(60, int(deadline - time.time() - 900))),
            )
            atomic_json(output / "checkpoint-transfer.json", {**transfer.__dict__, "pass": True})
            stage = "program"
            scp_to(ip, KEY, [P / "gemma_fp8_runner.py", P / "remote_gemma_fp8.sh", PACK], "/home/glmrunner/input/")
            stage = "science"
            remote = run_ssh(ip, KEY, build_remote_argv(int(deadline), started), timeout=max(60, int(deadline - time.time() - 240)))
            remote_returncode = remote.returncode
            atomic_json(output / "remote-run.json", {"returncode": remote.returncode, "stdout_tail": remote.stdout[-2000:], "stderr_tail": remote.stderr[-4000:]})
            result = retrieve(ip, output)
            if not validate_allocation_result(result):
                raise RuntimeError("allocation result contract incomplete")
            if remote.returncode or result.get("pass") is not True or result.get("complete") is not True:
                raise RuntimeError("typed semantic/endpoint failure")
            owner.complete("exact_gemma_online_fp8_l40s_terminal")
    except Exception as error:
        atomic_json(output / "failure.json", {"stage": stage, "type": type(error).__name__, "message": str(error), "instance_id": instance_id})
    finally:
        provider_seconds = time.time() - started
        useful_gpu_seconds = result.get("useful_gpu_seconds") if isinstance(result, dict) else None
        cleanup = None
        if output.exists() and (output / "cleanup.json").exists():
            cleanup = json.loads((output / "cleanup.json").read_text())
        atomic_json(
            output / "SUMMARY.json",
            {
                "name": name,
                "instance_id": instance_id,
                "remote_returncode": remote_returncode,
                "provider_seconds": provider_seconds,
                "useful_gpu_seconds": useful_gpu_seconds,
                "compute_cost_usd_derived": provider_seconds / 3600 * GPU_RATE_USD_PER_HOUR,
                "disk_cost_usd_derived": provider_seconds / 3600 * DISK_RATE_USD_PER_HOUR,
                "result": result,
                "cleanup": cleanup,
                "ended_epoch": time.time(),
            },
        )
    return 0 if isinstance(result, dict) and result.get("pass") is True and result.get("complete") is True else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--deadline-seconds", type=int, default=4800)
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    if args.audit_only:
        audit(args.output, args.name, args.deadline_seconds)
        raise SystemExit(0)
    raise SystemExit(run(args.output, args.name, args.deadline_seconds))


if __name__ == "__main__":
    main()
