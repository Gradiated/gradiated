#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

HEAD_MS = (8, 16, 32)
LINEAR_MS = (8, 16, 32, 3679)
LINEAR_SHAPES = (
    "sliding_qkv", "global_qkv", "sliding_output",
    "global_output", "gate_up", "down",
)
CEILING_SECONDS = 0.5479752315195353
TRIGGER = "H100_HEAD_SURVIVES_AND_HISTORICAL_SETUP_DOMINATES_AND_LINEAR_READY"


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valid_head_result(result: object, expected_ms: tuple[int, ...] = HEAD_MS) -> bool:
    if not isinstance(result, dict) or result.get("type") != "gemma4_h100_actual_parallel_lm_head_bf16":
        return False
    rows = result.get("rows")
    if not isinstance(rows, list) or [row.get("m") for row in rows if isinstance(row, dict)] != list(expected_ms):
        return False
    for row in rows:
        oracle = row.get("oracle", {})
        timing = row.get("cuda_event_ms", {})
        floor = row.get("per_request_head_seconds_at_358_steps")
        if not (
            row.get("pass") is True
            and oracle.get("finite") is True
            and oracle.get("nonzero") is True
            and oracle.get("varied_sign") is True
            and isinstance(timing.get("p50"), (int, float))
            and math.isfinite(timing["p50"]) and timing["p50"] > 0
            and isinstance(floor, (int, float)) and math.isfinite(floor) and floor > 0
        ):
            return False
    return result.get("pass") is True and result.get("all_actual_consumers_pass") is True


def valid_linear_result(result: object) -> bool:
    if not isinstance(result, dict) or result.get("type") != "gemma4_h100_stock_bf16_exact_linears":
        return False
    rows = result.get("rows")
    observed = {(row.get("shape"), row.get("m")) for row in rows or [] if isinstance(row, dict)}
    expected = {(shape, m) for shape in LINEAR_SHAPES for m in LINEAR_MS}
    return (
        result.get("pass") is True
        and result.get("all_actual_consumers_pass") is True
        and result.get("sweep", {}).get("pass") is True
        and isinstance(rows, list) and len(rows) == 24
        and observed == expected and all(row.get("pass") is True for row in rows)
    )


def historical_setup_pass(context: object) -> bool:
    return bool(
        isinstance(context, dict)
        and context.get("authenticated_prior_h100") is True
        and context.get("controller_allocation_seconds", 0) > 500
        and context.get("recorded_scored_cuda_seconds_upper_bound", math.inf) < 5
        and context.get("source_sha256")
    )


def conditional_trigger(primary: object, history: object, deadline_epoch: float, now_epoch: float) -> bool:
    if not isinstance(primary, dict):
        return False
    result = primary.get("result")
    return bool(
        primary.get("stage") == "primary"
        and primary.get("pass") is True
        and valid_head_result(result)
        and any(row["per_request_head_seconds_at_358_steps"] < CEILING_SECONDS for row in result["rows"])
        and historical_setup_pass(history)
        and history.get("linear_ready") is True
        and deadline_epoch - now_epoch >= 420
    )


def independent_audit_authorizes(audit: object, candidate_sha256: str) -> bool:
    return bool(
        isinstance(audit, dict)
        and audit.get("type") == "h100_parallel_lm_head_independent_final_program_audit"
        and audit.get("pass") is True
        and audit.get("decision") == "pass_before_create"
        and audit.get("candidate_precreate_sha256") == candidate_sha256
    )
