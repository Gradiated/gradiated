#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import sys


def main() -> int:
    terminal = json.load(open(sys.argv[1]))
    workload = json.load(open(sys.argv[2]))
    component = json.load(open(sys.argv[3]))
    output = pathlib.Path(sys.argv[4])
    args = pathlib.Path(sys.argv[5]).read_text()
    rows = terminal.get("rows", [])
    identities = [
        row.get("request_sha256")
        for row in sorted(rows, key=lambda row: row.get("index", -1))
    ]
    expected_identities = workload.get("request_sha256", [])
    usage = all(
        row.get("prompt_tokens") == 4214 and row.get("completion_tokens") == 358
        for row in rows
    )
    responses = all(
        row.get("text_nonempty")
        and row.get("text_finite")
        and row.get("error") is None
        for row in rows
    )
    accounting = (
        terminal.get("cache", {}).get("cached_prompt_tokens_delta") == 17120
        and terminal.get("cache", {}).get("uncached_prompt_tokens_delta") == 117728
    )
    path_ok = (
        component.get("pass") is True
        and "--kv-cache-dtype fp8_e5m2" in args
        and args.count("attention-backend triton") == 2
        and "flash" not in args.lower()
    )
    valid = (
        terminal.get("pass") is True
        and terminal.get("complete_requests") == 32
        and len(rows) == 32
        and usage
        and responses
        and accounting
        and identities == expected_identities
        and path_ok
    )
    service = float(terminal["service_seconds_per_request"])
    control = 0.6743258590313417
    local_boundary_fraction = 0.15312032
    perfect_local_removal_seconds = service * (1 - local_boundary_fraction)
    recoverable = perfect_local_removal_seconds < control
    classification = (
        "retain_mixed"
        if valid and (service < control or recoverable)
        else "close_mixed"
    )
    value = {
        "schema_version": 1,
        "status": "terminal",
        "classification": classification,
        "pass": valid,
        "candidate_service_seconds_per_request": service,
        "persisted_e5m2_control_seconds_per_request": control,
        "persisted_uniform_e4m3_seconds_per_request": 0.7022842785938792,
        "relative_to_control_fraction": 1 - service / control,
        "economic_ceiling_seconds_per_request": 0.6381105231,
        "local_attention_boundary_fraction": local_boundary_fraction,
        "perfect_local_removal_seconds_per_request": perfect_local_removal_seconds,
        "recoverable_by_perfect_local_attention_removal": recoverable,
        "component_path_check": component,
        "request_identity_pass": identities == expected_identities,
        "usage_pass": usage,
        "accounting_pass": accounting,
        "response_pass": responses,
        "candidate_path_pass": path_ok,
        "candidate": terminal,
    }
    temporary = output.with_suffix(".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
