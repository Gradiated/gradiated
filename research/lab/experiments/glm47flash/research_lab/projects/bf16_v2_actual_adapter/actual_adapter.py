#!/usr/bin/env python3
"""Execution-equivalent BF16 V2 adapter with a provider-free precreate mode."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from typing import Any, Protocol

HERE = Path(__file__).resolve().parent
CAMPAIGN = HERE.parents[2]
NEBIUS = CAMPAIGN / "campaign_100" / "nebius"
sys.path.insert(0, str(NEBIUS))

MODEL_REVISION = "33faccf4c2ba82142214d0d4e16232a4e9ccfe10"
SHARDS = 48
WEIGHT_BYTES = 62_444_175_504
REQUIRED = (
    "raw-response-bytes", "normalized-output-bytes", "transform-decisions",
    "responses.jsonl", "runtime-evidence.json", "identity-manifest.json",
    "capture-result.json",
)
TOKEN_RE = re.compile(r"(?i)(token|secret|password|authorization|api[_-]?key)=([^\s]+)")


class AdapterError(RuntimeError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def redacted(text: str) -> str:
    return TOKEN_RE.sub(r"\1=<redacted>", text)[:4000]


def diagnostic(stage: str, result: subprocess.CompletedProcess[str] | Exception) -> dict[str, Any]:
    if isinstance(result, Exception):
        return {"stage": stage, "exception_type": type(result).__name__, "message": redacted(str(result))}
    return {"stage": stage, "exit_code": result.returncode,
            "stdout": redacted(result.stdout), "stderr": redacted(result.stderr)}


def load_contract(spec_path: Path, suite_manifest: Path, model_dir: Path) -> dict[str, Any]:
    spec = json.loads(spec_path.read_text())
    manifest = json.loads(suite_manifest.read_text())
    model_manifest = json.loads((model_dir / "model-files-manifest.json").read_text())
    identity = spec["runtime_identity"]
    if identity["model_revision"] != MODEL_REVISION:
        raise AdapterError("V2 identity is not complete revision 33facc")
    if model_manifest.get("revision") != MODEL_REVISION or model_manifest.get("shard_count") != SHARDS:
        raise AdapterError("checkpoint manifest identity mismatch")
    if model_manifest.get("weight_bytes") != WEIGHT_BYTES:
        raise AdapterError("checkpoint byte identity mismatch")
    if manifest.get("case_count") != 36:
        raise AdapterError("development suite is not the frozen 36-case contract")
    if spec["captures"]["count"] != 3 or spec["captures"]["absolute_session_timeout_seconds"] != 3600:
        raise AdapterError("capture geometry or deadline mismatch")
    return {"model_revision": MODEL_REVISION, "shard_count": SHARDS,
            "weight_bytes": WEIGHT_BYTES, "suite_sha256": digest(suite_manifest),
            "spec_sha256": digest(spec_path),
            "model_manifest_sha256": digest(model_dir / "model-files-manifest.json")}


class Backend(Protocol):
    def create(self, name: str, disk_name: str, cloud_init: str) -> str: ...
    def address(self, instance_id: str) -> str: ...
    def bootstrap(self, ip: str) -> None: ...
    def transfer(self, ip: str, model_dir: Path) -> None: ...
    def capture(self, ip: str, phase: int, deadline: int, remote_script: Path) -> Path: ...
    def retrieve(self, remote_artifact: Path, destination: Path) -> None: ...
    def delete(self, instance_id: str, disk_name: str) -> dict[str, Any]: ...


class NebiusBackend:
    """Provider implementation assembled from the historical H100 primitives."""

    def __init__(self, key: Path):
        from placement_control import (build_create_command, extract_instance_id, extract_public_ipv4,
                                       get_instance, make_cloud_init, delete_instance, wait_absent,
                                       list_items, metadata_id, metadata_name, delete_disk, wait_ssh)
        from stock_control import build_host_bootstrap, probe_model_transfer, transfer_local_model, run_ssh
        self.key = key
        self._build_create_command = build_create_command; self._extract_instance_id = extract_instance_id
        self._extract_public_ipv4 = extract_public_ipv4; self._get_instance = get_instance
        self._make_cloud_init = make_cloud_init; self._delete_instance = delete_instance
        self._wait_absent = wait_absent; self._list_items = list_items; self._metadata_id = metadata_id
        self._metadata_name = metadata_name; self._delete_disk = delete_disk
        self._run_ssh = run_ssh; self._wait_ssh = wait_ssh; self._bootstrap = build_host_bootstrap
        self._probe = probe_model_transfer; self._transfer = transfer_local_model

    def create_command(self, name: str, disk_name: str, cloud_init: str) -> list[str]:
        return self._build_create_command(name=name, disk_name=disk_name, cloud_init=cloud_init, disk_gib=250)

    def create(self, name: str, disk_name: str, cloud_init: str) -> str:
        proc = subprocess.run(self.create_command(name, disk_name, cloud_init), capture_output=True, text=True, timeout=180)
        if proc.returncode: raise AdapterError(json.dumps(diagnostic("provider_create", proc)))
        return self._extract_instance_id(json.loads(proc.stdout))

    def address(self, instance_id: str) -> str:
        end = time.time() + 600
        while time.time() < end:
            payload = self._get_instance(instance_id)
            if payload is None: raise AdapterError("instance disappeared before SSH readiness")
            ip = self._extract_public_ipv4(payload)
            if ip: self._wait_ssh(ip, self.key, end); return ip
            time.sleep(5)
        raise AdapterError("public IP readiness exceeded 600 seconds")

    def bootstrap(self, ip: str) -> None:
        result = self._run_ssh(ip, self.key, "bash -s", timeout=1800, input_text=self._bootstrap())
        if result.returncode: raise AdapterError(json.dumps(diagnostic("host_bootstrap", result)))

    def transfer(self, ip: str, model_dir: Path) -> None:
        if not self._probe(ip, self.key): raise AdapterError("model transfer probe failed")
        self._transfer(ip, self.key, model_dir, timeout=1800)

    def stage_suite(self, ip: str, suite_manifest: Path) -> None:
        from stock_control import scp_to
        fixture = suite_manifest.parent / "development.jsonl"
        if not fixture.is_file(): raise AdapterError("development fixture is missing beside suite manifest")
        scp_to(ip, self.key, [fixture, suite_manifest], "/home/glmrunner/input/")

    def capture(self, ip: str, phase: int, deadline: int, remote_script: Path) -> Path:
        from stock_control import scp_to, run_ssh
        scp_to(ip, self.key, [remote_script], "/home/glmrunner/v2-capture.sh")
        result = run_ssh(ip, self.key, ["bash", "/home/glmrunner/v2-capture.sh", str(phase), str(deadline)],
                         timeout=max(60, deadline - int(time.time()) + 30))
        if result.returncode: raise AdapterError(json.dumps(diagnostic(f"capture_{phase}", result)))
        self._ip = ip
        return Path(f"/home/glmrunner/v2-capture-{phase}.tar.gz")

    def retrieve(self, remote_artifact: Path, destination: Path) -> None:
        from stock_control import scp_from
        destination.mkdir(parents=True, exist_ok=True)
        archive = destination.with_suffix(".tar.gz")
        scp_from(self._ip, self.key, str(remote_artifact), archive)
        validate_archive(archive, destination, MODEL_REVISION)

    def delete(self, instance_id: str, disk_name: str) -> dict[str, Any]:
        self._delete_instance(instance_id); absent = self._wait_absent(instance_id, time.time() + 240)
        disk_ids = [self._metadata_id(row) for row in self._list_items("disk")
                    if self._metadata_name(row) == disk_name and self._metadata_id(row)]
        for disk_id in disk_ids: self._delete_disk(disk_id)
        instances = self._list_items("instance"); disks = self._list_items("disk")
        disk_absent = not any(self._metadata_name(row) == disk_name for row in disks)
        return {"pass": absent and not instances and disk_absent, "direct_absent": absent,
                "inventory_absent": not instances and disk_absent,
                "final_instance_count": len(instances), "final_disk_count": len(disks)}


def validate_artifact(root: Path, expected_revision: str) -> dict[str, Any]:
    missing = [name for name in REQUIRED if not (root / name).exists()]
    if missing:
        raise AdapterError(f"missing capture artifacts: {','.join(missing)}")
    identity = json.loads((root / "identity-manifest.json").read_text())
    if identity.get("model_revision") != expected_revision:
        raise AdapterError("capture artifact identity mismatch")
    return {"artifact_complete": True, "artifact_sha256": digest(root / "capture-result.json"),
            "required_count": len(REQUIRED)}


def validate_archive(archive: Path, destination: Path, expected_revision: str) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as bundle:
        bundle.extractall(destination, filter="data")
    roots = [path.parent for path in destination.rglob("identity-manifest.json")]
    if len(roots) != 1: raise AdapterError("capture archive must contain one identity manifest")
    root = roots[0]
    if root != destination:
        for item in root.iterdir(): item.replace(destination / item.name)
    return validate_artifact(destination, expected_revision)


def build_systemd_command(executable: Path, artifact_dir: Path, *, unit: str,
                          controller_args: list[str]) -> list[str]:
    return ["systemd-run", "--user", "--wait", "--collect", f"--unit={unit}",
            "--property=RuntimeMaxSec=30s", f"--working-directory={HERE}",
            f"--setenv=V2_ARTIFACT_DIR={artifact_dir}", sys.executable, str(executable),
            "--no-mutation", *controller_args]


def no_mutation(artifact_dir: Path) -> int:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    terminal = {"schema_version": 1, "kind": "v2_adapter_precreate_terminal",
                "mutation": False, "provider_create": False, "model_launch": False,
                "identity": MODEL_REVISION, "artifact_destination": str(artifact_dir),
                "pass": True}
    (artifact_dir / "precreate-terminal.json").write_text(json.dumps(terminal, sort_keys=True) + "\n")
    return 0


def run(backend: Backend, *, output: Path, name: str, model_dir: Path, spec: Path,
        suite_manifest: Path, remote_script: Path, key: Path | None = None,
        public_key: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    identity = load_contract(spec, suite_manifest, model_dir)
    started = time.time(); deadline = int(started) + 3600
    instance = None; disk = name + "-boot"; phases = []; outcome = "FAIL"; cleanup = {}
    try:
        cloud_init = ""
        if public_key is not None:
            from placement_control import make_cloud_init
            cloud_init = make_cloud_init(public_key.read_text())
        if dry_run:
            if hasattr(backend, "create_command"):
                (output / "provider-create-command.json").write_text(json.dumps(backend.create_command(name, disk, cloud_init)) + "\n")
            terminal = {"schema_version": 1, "kind": "actual_v2_adapter_precreate_terminal", "pass": True,
                        "mutation": False, "provider_create_called": False, "model_launch": False, "identity": identity}
            (output / "precreate-terminal.json").write_text(json.dumps(terminal, sort_keys=True) + "\n")
            return terminal
        instance = backend.create(name, disk, cloud_init)
        ip = backend.address(instance); backend.bootstrap(ip); backend.transfer(ip, model_dir)
        if hasattr(backend, "stage_suite"): backend.stage_suite(ip, suite_manifest)
        for phase in range(1, 4):
            if time.time() >= deadline: raise AdapterError("capture session deadline exceeded")
            remote = backend.capture(ip, phase, deadline, remote_script)
            local = output / f"capture-{phase}"; backend.retrieve(remote, local)
            phases.append({"phase": phase, **validate_artifact(local, MODEL_REVISION)})
        outcome = "PASS"
    except Exception as error:
        (output / "adapter-error.json").write_text(json.dumps(diagnostic("capture", error), sort_keys=True) + "\n")
    finally:
        if instance is not None:
            try: cleanup = backend.delete(instance, disk)
            except Exception as error: cleanup = {"pass": False, **diagnostic("cleanup", error)}
        else: cleanup = {"pass": True, "provider_created": False}
    result = {"schema_version": 1, "kind": "actual_v2_adapter_terminal", "identity": identity,
              "outcome": outcome, "phases": phases, "cleanup": cleanup,
              "pass": outcome == "PASS" and cleanup.get("pass") is True}
    (output / "terminal-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-mutation", action="store_true")
    parser.add_argument("--mutate", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--suite-manifest", type=Path, required=True)
    parser.add_argument("--remote-script", type=Path, required=True)
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--ssh-public-key", type=Path, required=True)
    args = parser.parse_args()
    if args.no_mutation and args.mutate: parser.error("mutation switches are exclusive")
    if not args.remote_script.is_file(): parser.error("remote capture script is missing")
    backend = NebiusBackend(args.ssh_key)
    result = run(backend, output=args.output, name=args.name, model_dir=args.model_dir, spec=args.spec,
                 suite_manifest=args.suite_manifest, remote_script=args.remote_script,
                 key=args.ssh_key, public_key=args.ssh_public_key, dry_run=not args.mutate)
    return 0 if result.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
