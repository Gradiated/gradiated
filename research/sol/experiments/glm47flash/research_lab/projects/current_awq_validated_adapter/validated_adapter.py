#!/usr/bin/env python3
"""Validated SSH/cloud-init envelope for the frozen current-AWQ V2 launcher."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import yaml


PROJECT = Path(__file__).resolve().parent
V2 = PROJECT.parent / "current_awq_frontier_v2" / "frontier_v2.py"
PLACEMENT = PROJECT.parents[2] / "campaign_100" / "nebius" / "placement_control.py"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def one_line_ssh_ed25519(public_key: Path) -> bytes:
    value = public_key.read_bytes()
    lines = value.splitlines()
    if len(lines) != 1 or not lines[0] or not lines[0].startswith(b"ssh-ed25519 "):
        raise RuntimeError("public key must be exactly one nonempty ssh-ed25519 line")
    if b"-----BEGIN" in value or b"-----END" in value:
        raise RuntimeError("public key must not contain PEM markers")
    return lines[0]


def derived_public_key(private_key: Path) -> bytes:
    result = subprocess.run(
        ["ssh-keygen", "-y", "-f", str(private_key)],
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError("private key could not derive a public key")
    return result.stdout.strip()


def validated_cloud_init(placement, public_line: bytes) -> str:
    text = placement.make_cloud_init(public_line.decode("utf-8"))
    parsed = yaml.safe_load(text)
    users = parsed.get("users") if isinstance(parsed, dict) else None
    if not isinstance(users, list) or len(users) != 1 or not isinstance(users[0], dict):
        raise RuntimeError("cloud-init must have exactly one user mapping")
    keys = users[0].get("ssh_authorized_keys")
    if keys != [public_line.decode("utf-8")]:
        raise RuntimeError("cloud-init must have exactly one matching authorized-key scalar")
    return text


def validate_adapter(private_key: Path, public_key: Path) -> dict:
    placement = load_module(PLACEMENT, "validated_adapter_placement")
    public_line = one_line_ssh_ed25519(public_key)
    derived = derived_public_key(private_key)
    if derived != public_line:
        raise RuntimeError("private/public key pair mismatch")
    cloud_init = validated_cloud_init(placement, public_line)
    try:
        one_line_ssh_ed25519_bytes(b"-----BEGIN CERTIFICATE-----\na\n-----END CERTIFICATE-----\n")
    except RuntimeError:
        negative_rejected = True
    else:
        raise RuntimeError("multiline PEM fixture was accepted")
    return {
        "schema_version": 1,
        "private_key_derives_selected_public_key": True,
        "public_key_type": "ssh-ed25519",
        "public_key_bytes": len(public_key.read_bytes()),
        "public_key_lines": 1,
        "public_key_sha256": sha256(public_line),
        "cloud_init_sha256": sha256(cloud_init.encode()),
        "cloud_init_yaml_parser": "PyYAML.safe_load",
        "authorized_key_scalars": 1,
        "negative_multiline_pem_rejected": negative_rejected,
        "launcher_sha256": sha256(Path(__file__).read_bytes()),
        "frozen_v2_launcher_sha256": sha256(V2.read_bytes()),
        "placement_source_sha256": sha256(PLACEMENT.read_bytes()),
    }


def one_line_ssh_ed25519_bytes(value: bytes) -> bytes:
    lines = value.splitlines()
    if len(lines) != 1 or not lines[0] or not lines[0].startswith(b"ssh-ed25519 "):
        raise RuntimeError("public key must be exactly one nonempty ssh-ed25519 line")
    if b"-----BEGIN" in value or b"-----END" in value:
        raise RuntimeError("public key must not contain PEM markers")
    return lines[0]


def run(args: argparse.Namespace) -> int:
    v2 = load_module(V2, "validated_adapter_v2")
    nebius = str(PLACEMENT.parent)
    if nebius not in sys.path:
        sys.path.insert(0, nebius)
    import vllm_smoke_control as control

    original = control.make_cloud_init

    def make_cloud_init(public_key: str) -> str:
        supplied = one_line_ssh_ed25519_bytes(public_key.encode())
        if supplied != one_line_ssh_ed25519(args.ssh_public_key):
            raise RuntimeError("launcher was passed a public key other than the validated file")
        placement = load_module(PLACEMENT, "validated_adapter_runtime_placement")
        return validated_cloud_init(placement, supplied)

    control.make_cloud_init = make_cloud_init
    try:
        return v2.run(args)
    finally:
        control.make_cloud_init = original


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--ssh-public-key", type=Path, required=True)
    parser.add_argument("--experiment-spec-sha256", required=True)
    parser.add_argument("--num-kv-splits", type=int, choices=(4, 8, 16), default=4)
    parser.add_argument("--max-num-seqs", type=int, choices=(8, 16, 32), default=32)
    parser.add_argument("--frontier-concurrencies", default="1,8,16,32")
    parser.add_argument("--absolute-timeout-seconds", type=int, default=2700)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    report = validate_adapter(args.ssh_key, args.ssh_public_key)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "validated-adapter-precreate.json").write_bytes(canonical(report) + b"\n")
    if args.preflight_only:
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
