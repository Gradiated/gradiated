#!/usr/bin/env python3
"""Absolute-path, systemd-bound controller for the current AWQ frontier."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path


ROOT = Path("/root/workspace")
PROJECT = ROOT / "research/lab/experiments/glm47flash/research_lab/projects/current_awq_service_boundary"
V2 = PROJECT.parent / "current_awq_frontier_v2" / "frontier_v2.py"
VALIDATED = PROJECT.parent / "current_awq_validated_adapter" / "validated_adapter.py"
PLACEMENT = ROOT / "research/lab/experiments/glm47flash/campaign_100/nebius/placement_control.py"
MODEL = Path("/root/.cache/glm47flash-awq-ab31d120")


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def absolute(path: Path) -> Path:
    if not path.is_absolute() or path.resolve() != path:
        raise RuntimeError(f"path is not canonical absolute: {path}")
    return path


def parse_spec(spec_path: Path, expected: str) -> dict:
    actual = digest(spec_path)
    if actual != expected:
        raise RuntimeError("experiment spec hash mismatch")
    value = json.loads(spec_path.read_text())
    if value["frontier"] != [1, 8, 16, 32] or value["fixed"]["input_tokens"] != 8192:
        raise RuntimeError("unexpected scientific workload binding")
    return value


def inventories(placement) -> dict:
    instances = placement.list_items("instance")
    disks = placement.list_items("disk")
    return {"instance_count": len(instances), "disk_count": len(disks), "empty": not instances and not disks}


def terminal(output: Path, value: dict) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "precreate-terminal.json").write_bytes(canonical(value) + b"\n")


def controller(args: argparse.Namespace) -> int:
    output = absolute(args.output_dir)
    key = absolute(args.ssh_key)
    public = absolute(args.ssh_public_key)
    spec_path = absolute(args.experiment_spec)
    for path in (PROJECT, V2, VALIDATED, PLACEMENT, MODEL, key, public, spec_path):
        if not path.exists():
            raise RuntimeError(f"required path missing: {path}")
    spec = parse_spec(spec_path, args.experiment_spec_sha256)
    validated = module(VALIDATED, "service_boundary_validated")
    adapter = validated.validate_adapter(key, public)
    v2 = module(V2, "service_boundary_v2")
    with tempfile.TemporaryDirectory(prefix="service-boundary-stage-") as raw:
        manifest = v2.write_staging(Path(raw))
    placement = module(PLACEMENT, "service_boundary_placement")
    nebius_dir = str(PLACEMENT.parent)
    if nebius_dir not in sys.path:
        sys.path.insert(0, nebius_dir)
    import awq_smoke_control
    identity = awq_smoke_control.validate_local_model(MODEL)
    inventory = inventories(placement)
    sources = {str(path): digest(path) for path in (Path(__file__).resolve(), V2, VALIDATED, PLACEMENT, spec_path)}
    base = {
        "schema_version": 1,
        "kind": "glm47_current_awq_service_boundary_terminal",
        "mode": args.mode,
        "provider_create_reached": False,
        "working_directory": str(ROOT),
        "controller_current_working_directory": os.getcwd(),
        "controller_source": str(Path(__file__).resolve()),
        "source_sha256": sources,
        "experiment_spec_sha256": args.experiment_spec_sha256,
        "scientific_binding": {"frontier": spec["frontier"], "input_tokens": spec["fixed"]["input_tokens"], "max_output_tokens": spec["fixed"]["max_output_tokens"]},
        "validated_adapter": adapter,
        "staging_manifest": manifest,
        "model_identity": identity,
        "inventory": inventory,
        "watchdog_contract": {"absolute_timeout_seconds": args.absolute_timeout_seconds, "controller_pid": os.getpid(), "no_mutation": args.mode == "no-mutation"},
    }
    if args.mode == "no-mutation":
        result = {**base, "typed_state": "precreate_pass" if inventory["empty"] else "precreate_inventory_not_empty", "pass": inventory["empty"]}
        terminal(output, result)
        return 0 if result["pass"] else 1
    result = {**base, "typed_state": "mutation_starting", "pass": False, "provider_create_reached": True}
    terminal(output, result)
    forwarded = argparse.Namespace(
        output_dir=output, name=args.name, ssh_key=key, ssh_public_key=public,
        experiment_spec_sha256=args.experiment_spec_sha256, num_kv_splits=4,
        max_num_seqs=32, frontier_concurrencies="1,8,16,32",
        absolute_timeout_seconds=args.absolute_timeout_seconds, preflight_only=False,
    )
    return validated.run(forwarded)


def service(args: argparse.Namespace) -> int:
    output = absolute(args.output_dir)
    token = uuid.uuid4().hex[:12]
    unit = f"glm47-awq-service-boundary-{token}"
    command = [sys.executable, str(Path(__file__).resolve()), "controller", "--mode", args.mode,
               "--output-dir", str(output), "--name", args.name, "--ssh-key", str(args.ssh_key),
               "--ssh-public-key", str(args.ssh_public_key), "--experiment-spec", str(args.experiment_spec),
               "--experiment-spec-sha256", args.experiment_spec_sha256,
               "--absolute-timeout-seconds", str(args.absolute_timeout_seconds)]
    launch = subprocess.run(["systemd-run", "--user", "--collect", "--wait", "--pipe",
                             f"--unit={unit}", "--working-directory=/root/workspace",
                             "--setenv=PYTHONUNBUFFERED=1", f"--property=RuntimeMaxSec={args.absolute_timeout_seconds}s", *command],
                            capture_output=True, text=True, timeout=args.absolute_timeout_seconds + 180)
    properties = subprocess.run(["systemctl", "--user", "show", f"{unit}.service", "--property=ActiveState,Result,ExecMainStatus,WorkingDirectory,ControlGroup"], capture_output=True, text=True)
    report = {"schema_version": 1, "unit": f"{unit}.service", "command": command, "returncode": launch.returncode,
              "stdout_sha256": hashlib.sha256(launch.stdout.encode()).hexdigest(), "stderr_sha256": hashlib.sha256(launch.stderr.encode()).hexdigest(),
              "unit_properties": properties.stdout, "unit_properties_returncode": properties.returncode,
              "source_sha256": digest(Path(__file__).resolve()), "working_directory": str(ROOT)}
    output.mkdir(parents=True, exist_ok=True)
    (output / "systemd-service-report.json").write_bytes(canonical(report) + b"\n")
    return launch.returncode


def arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="entry", required=True)
    for name in ("controller", "service"):
        item = subs.add_parser(name)
        item.add_argument("--mode", choices=("no-mutation", "mutation"), required=True)
        item.add_argument("--output-dir", type=Path, required=True)
        item.add_argument("--name", required=True)
        item.add_argument("--ssh-key", type=Path, required=True)
        item.add_argument("--ssh-public-key", type=Path, required=True)
        item.add_argument("--experiment-spec", type=Path, required=True)
        item.add_argument("--experiment-spec-sha256", required=True)
        item.add_argument("--absolute-timeout-seconds", type=int, default=2700)
    return parser


def main() -> int:
    args = arguments().parse_args()
    return controller(args) if args.entry == "controller" else service(args)


if __name__ == "__main__":
    raise SystemExit(main())
