#!/usr/bin/env python3
"""Fail-closed owner preflight for the one future 55L/5G endpoint pair.

This file deliberately performs no SSH, pool mutation, staging, container, or
endpoint action.  A later exact execution binding may use its validation
result only after the director has moved the named bench out of maintenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PROJECT = "gemma4_hybrid_attention_placement_codesign"
PACKET = ROOT / "inputs/h200_55l5g_endpoint_packet/MANIFEST.json"
CUMULATIVE_CEILING_USD = 22.0
PRIOR_ACTUAL_USD = 9.960954252113235


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(reason: str) -> None:
    raise ValueError(reason)


def same_fields(left: dict[str, Any], right: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return all(left.get(field) == right.get(field) and bool(left.get(field)) for field in fields)


def validate(binding: dict[str, Any], bench: dict[str, Any]) -> dict[str, Any]:
    """Validate an execution binding against a currently live pool row.

    Connection, checkpoint, image, claim generation, watchdog, and release
    inputs are deliberately accepted only from the binding plus this row.
    """
    packet = load(PACKET)
    if binding.get("project") != PROJECT:
        fail("project_mismatch")
    if binding.get("packet_manifest_sha256") != sha256(PACKET):
        fail("packet_digest_mismatch")
    if binding.get("immutable_scientific_files") != packet.get("immutable_files"):
        fail("scientific_file_hashes_mismatch")
    if binding.get("pair_contract") != packet.get("pair_contract"):
        fail("pair_contract_mismatch")
    if binding.get("quality_preservation_claimed") is not False:
        fail("quality_contract_mismatch")

    budget = binding.get("budget", {})
    lifecycle = binding.get("lifecycle", {})
    if budget.get("cumulative_authorized_usd") != CUMULATIVE_CEILING_USD:
        fail("cumulative_ceiling_mismatch")
    if budget.get("prior_actual_usd") != PRIOR_ACTUAL_USD:
        fail("prior_actual_mismatch")
    if not isinstance(budget.get("maximum_lifecycle_usd"), (int, float)):
        fail("lifecycle_budget_missing")
    if PRIOR_ACTUAL_USD + float(budget["maximum_lifecycle_usd"]) > CUMULATIVE_CEILING_USD:
        fail("cumulative_budget_exceeded")

    live = binding.get("live_bench", {})
    resource = live.get("resource", {})
    row_resource = bench.get("resource", {})
    identity = ("instance_id", "disk_id", "public_ipv4", "ssh_user", "known_hosts_namespace", "ssh_ed25519_fingerprint")
    if not live.get("claim_generation"):
        fail("claim_generation_missing")
    if not (live.get("id") == bench.get("id") and same_fields(resource, row_resource, identity)):
        fail("live_bench_identity_mismatch")
    if bench.get("provider") != "nebius" or bench.get("accelerator") != "nvidia-h200-sxm":
        fail("incompatible_live_bench")
    if bench.get("status") != "available" or bench.get("claim") is not None:
        fail("bench_not_claimable")

    destinations = binding.get("runtime_destinations", {})
    contents = bench.get("contents", {})
    if not all(isinstance(destinations.get(k), str) and destinations[k] in str(contents.get(k, ""))
               for k in ("checkpoint", "image")):
        fail("runtime_destinations_not_bound_to_live_record")

    watchdog = lifecycle.get("watchdog", {})
    row_watchdog = bench.get("lifecycle", {}).get("watchdog", {})
    if watchdog != row_watchdog or lifecycle.get("watchdog_verified") is not True:
        fail("watchdog_identity_mismatch")
    release_by = lifecycle.get("release_by_utc")
    if not isinstance(release_by, str) or not release_by < str(bench.get("lifecycle", {}).get("deadline_utc", "")):
        fail("release_bound_invalid")
    if not binding.get("claim_allowed") or not binding.get("exact_execution_command"):
        fail("execution_authorization_missing")

    return {
        "valid": True,
        "bench_id": bench["id"],
        "claim_generation": live["claim_generation"],
        "release_by_utc": release_by,
        "packet_manifest_sha256": binding["packet_manifest_sha256"],
        "pair_limit": packet["pair_contract"]["maximum_valid_pair_invocations"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--bench-record", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate(load(args.binding), load(args.bench_record))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
