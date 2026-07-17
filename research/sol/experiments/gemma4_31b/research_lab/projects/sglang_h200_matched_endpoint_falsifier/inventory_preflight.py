#!/usr/bin/env python3
"""Emit diagnostic-bearing Nebius instance/disk inventory evidence.

Nebius CLI 0.24 renders an empty protobuf list as zero bytes under JSON, but as
the explicit empty mapping ``{}`` under YAML.  This preflight uses the latter
and fails closed on any nonempty payload, stderr, timeout, or nonzero exit.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
OUT = HERE / "artifacts" / "PROVIDER_INVENTORY_TERMINAL.json"
NEBIUS = Path("/root/.nebius/bin/nebius")
PROJECT_ID = "project-e00h1vhmpr00vbmfd5k7pg"
PROFILE = "glm-campaign"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def inspect(kind: str) -> dict[str, object]:
    command = [
        str(NEBIUS), "compute", kind, "list",
        "--parent-id", PROJECT_ID,
        "--all",
        "--profile", PROFILE,
        "--format", "yaml",
        "--no-progress",
        "--timeout", "30s",
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired as exc:
        return {
            "kind": kind,
            "command": command,
            "outcome": "subprocess_timeout",
            "timeout_seconds": exc.timeout,
            "empty": False,
        }
    stdout = proc.stdout
    stderr = proc.stderr
    parsed = None
    if stdout.strip():
        try:
            # The expected YAML empty mapping is also valid JSON.  Refuse more
            # complex YAML so the decision does not depend on an implicit
            # parser or ambiguous scalar conversion.
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = "unparsed"
    empty = proc.returncode == 0 and parsed == {} and not stderr.strip()
    return {
        "kind": kind,
        "command": command,
        "returncode": proc.returncode,
        "stdout": {
            "bytes": len(stdout.encode()),
            "sha256": digest(stdout),
            "sanitized_text": stdout,
        },
        "stderr": {
            "bytes": len(stderr.encode()),
            "sha256": digest(stderr),
            "sanitized_text": stderr,
        },
        "parsed_type": type(parsed).__name__,
        "empty": empty,
    }


def main() -> int:
    rows = [inspect("instance"), inspect("disk")]
    passed = all(row.get("empty") is True for row in rows)
    terminal = {
        "schema_version": 1,
        "classification": (
            "authenticated_empty_provider_inventory"
            if passed else "provider_inventory_precreate_failure"
        ),
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "repair": "replace zero-byte JSON rendering with explicit YAML empty-mapping rendering",
        "profile": PROFILE,
        "project_id": PROJECT_ID,
        "resources": rows,
        "pass": passed,
        "provider_create_allowed_by_inventory_gate": passed,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
