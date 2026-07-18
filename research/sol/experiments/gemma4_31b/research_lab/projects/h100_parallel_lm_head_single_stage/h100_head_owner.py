#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
NEBIUS = LAB.parents[1] / "glm47flash/campaign_100/nebius"
sys.path.insert(0, str(NEBIUS))

import mla_microbench_control as controller
from placement_control import build_create_command, list_items, make_cloud_init, metadata_id, metadata_name

COMPONENT = LAB / "projects/gemma_l40s_parallel_lm_head_component"
FINAL = LAB / "projects/gemma_l40s_parallel_lm_head_measurement_final"
BENCHMARK = COMPONENT / "vllm_parallel_lm_head_bench.py"
REMOTE = COMPONENT / "remote_parallel_lm_head_stage.sh"
SSH_KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
SSH_PUBLIC_KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519.pub")
IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
PLATFORM = "gpu-h100-sxm"
PRESET = "1gpu-16vcpu-200gb"
RATE = 2.15
DISK_RATE = 0.0097222
PROVIDER_SECONDS = 1200
WALL_SECONDS = 1800
SPEND_CAP = 1.30
EXPECTED_BENCHMARK = "de7f843a07e10322446a5e173ef60df7dc14763f0924102a2a612e34bdf0ab71"
EXPECTED_REMOTE = "e7a947f9124541e387af448c4a11653f7040b45c78c2ebe9e036fd94f91ec255"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def argv_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def run_identity(output_dir: Path) -> dict[str, object]:
    process = subprocess.run(
        [sys.executable, str(PROJECT / "assert_identity.py")],
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError:
        result = {"pass": False, "error": "identity assertion emitted invalid JSON"}
    result["returncode"] = process.returncode
    atomic_json(output_dir / "IDENTITY_ASSERTION.json", result)
    return result


def audit(output_dir: Path, name: str, spec_hash: str) -> dict[str, object]:
    controller.validate_durable_owner()
    controller.PLATFORM = PLATFORM
    controller.PRESET = PRESET
    controller.DISK_GIB = 100
    controller.HOURLY_RATE_USD = RATE
    controller.DISK_HOURLY_RATE_USD = DISK_RATE
    source = BENCHMARK.read_text()
    remote = REMOTE.read_text()
    tree = ast.parse(source)
    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"MS", "HIDDEN", "VOCAB", "STEPS"}
    }
    create_argv = build_create_command(
        name=name,
        disk_name=f"{name}-boot",
        cloud_init=make_cloud_init(SSH_PUBLIC_KEY.read_text()),
        disk_gib=100,
        platform=PLATFORM,
        preset=PRESET,
        preemptible=True,
    )
    container_argv = controller.build_container_command(
        spec_hash,
        1_800_000_000,
        REMOTE.name,
        BENCHMARK.name,
        IMAGE,
        "primary",
        "h100-parallel-lm-head",
    )
    instances = list_items("instance")
    disks = list_items("disk")
    final_status = json.loads((FINAL / "STATUS.json").read_text())
    run_parameters = inspect.signature(controller.run).parameters
    checks = {
        "durable_user_systemd_owner": bool(os.environ.get("INVOCATION_ID")) and os.environ.get("SYSTEMD_EXEC_PID") == str(os.getpid()),
        "identity_assertion": json.loads((output_dir / "IDENTITY_ASSERTION.json").read_text()).get("pass") is True,
        "immutable_program": sha256(BENCHMARK) == EXPECTED_BENCHMARK,
        "immutable_wrapper": sha256(REMOTE) == EXPECTED_REMOTE,
        "successful_shared_controller_mechanics": final_status.get("last_result_classification") == "scope_valid_actual_parallel_lm_head_component_pass_cleanup_verified",
        "h100_placement": argv_value(create_argv, "--resources-platform") == PLATFORM and argv_value(create_argv, "--resources-preset") == PRESET,
        "single_h100_disk": argv_value(create_argv, "--boot-disk-managed-disk-size-gibibytes") == "100" and "--preemptible-on-preemption" in create_argv,
        "lowercase_real_create_argv": argv_value(create_argv, "--name") == name == argv_value(create_argv, "--hostname") and len(name) <= 63 and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", name) is not None,
        "empty_authenticated_inventory": not instances and not disks,
        "six_exact_rows": assignments == {"MS": (1, 2, 4, 8, 16, 32), "HIDDEN": 5376, "VOCAB": 262144, "STEPS": 358},
        "actual_consumer_oracle_and_timings": all(token in source for token in ("ParallelLMHead", "head.quant_method.apply(head, activations, None)", "torch.cuda.Event", "torch.isfinite(output).all()", "peak_allocated_bytes", "peak_reserved_bytes", "per_request_head_seconds_at_358_steps")),
        "telemetry_archive_manifest": all(token in remote for token in ("telemetry.csv", "nvidia-smi", "stage-terminal.json", "manifest.json", "tar --sort=name", "sha256sum")),
        "one_primary_container": (
            "STAGE=primary" in container_argv
            and REMOTE.name in container_argv[-1]
            and f"MICROBENCH_PATH=/input/{BENCHMARK.name}" in container_argv
        ),
        "conditional_omitted": run_parameters["conditional_remote_script"].default is None and run_parameters["conditional_benchmark_script"].default is None and run_parameters["conditional_input_files"].default == (),
        "adjacent_omission_preregistered": "none is start-ready within ten minutes" in (PROJECT / "PROJECT.md").read_text(),
        "watchdog_cleanup_accounting": all(token in inspect.getsource(controller.run) for token in ("VerifiedRetainedOwner", "start_independent_watchdog", "retained.complete(\"single_stage_pass\")", "cleanup_pass", "cost_usd_derived")),
        "bounded_provider_budget": PROVIDER_SECONDS <= 20 * 60 and (RATE + DISK_RATE) * PROVIDER_SECONDS / 3600 <= SPEND_CAP,
        "bounded_wall_storage": WALL_SECONDS == 30 * 60 and controller.DISK_GIB == 100 and "1 GiB retained plus 512 MiB temporary" in (PROJECT / "PROJECT.md").read_text(),
        "no_checkpoint_development_session": (
            not list(PROJECT.glob("*.safetensors"))
            and "retained mutable development session" in (PROJECT / "PROJECT.md").read_text()
            and "Repair ordinary import" in (PROJECT / "PROJECT.md").read_text()
        ),
    }
    result = {
        "schema_version": 1,
        "classification": "internal_behavioral_precreate_audit",
        "pass": all(checks.values()),
        "checks": checks,
        "placement": {"platform": PLATFORM, "preset": PRESET, "disk_gib": 100},
        "budget": {"wall_seconds": WALL_SECONDS, "provider_seconds": PROVIDER_SECONDS, "h100_hours": PROVIDER_SECONDS / 3600, "rate_usd_per_h100_hour": RATE, "disk_rate_usd_per_hour": DISK_RATE, "max_cost_usd": (RATE + DISK_RATE) * PROVIDER_SECONDS / 3600, "spend_cap_usd": SPEND_CAP},
        "hashes": {"program": sha256(BENCHMARK), "wrapper": sha256(REMOTE), "controller": sha256(Path(controller.__file__)), "create_argv": hashlib.sha256(json.dumps(create_argv).encode()).hexdigest()},
        "create": {"name": name, "hostname": argv_value(create_argv, "--hostname"), "disk_name": argv_value(create_argv, "--boot-disk-managed-disk-name"), "platform": argv_value(create_argv, "--resources-platform"), "preset": argv_value(create_argv, "--resources-preset")},
        "inventory": {"instances": [{"id": metadata_id(x), "name": metadata_name(x)} for x in instances], "disks": [{"id": metadata_id(x), "name": metadata_name(x)} for x in disks]},
    }
    atomic_json(output_dir / "PRECREATE_AUDIT.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--experiment-spec-sha256", required=True)
    args = parser.parse_args()
    identity = run_identity(args.output_dir)
    if identity.get("pass") is not True:
        atomic_json(args.output_dir / "PRECREATE_BLOCKER.json", {"schema_version": 1, "classification": "identity_assertion_failed", "identity": identity})
        return 2
    result = audit(args.output_dir, args.name, args.experiment_spec_sha256)
    if result["pass"] is not True:
        atomic_json(args.output_dir / "PRECREATE_BLOCKER.json", {"schema_version": 1, "classification": "internal_behavioral_precreate_audit_failed", "audit": result})
        return 2
    return controller.run(
        args.output_dir,
        args.name,
        SSH_KEY,
        SSH_PUBLIC_KEY,
        args.experiment_spec_sha256,
        REMOTE,
        BENCHMARK,
        (),
        "h100-parallel-lm-head",
        PROVIDER_SECONDS,
        IMAGE,
    )


if __name__ == "__main__":
    raise SystemExit(main())
