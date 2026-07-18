#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path

from h100_head_contract import CEILING_SECONDS, TRIGGER, atomic_json, historical_setup_pass, valid_head_result, valid_linear_result


def valid_telemetry(value: object) -> bool:
    return bool(
        isinstance(value, dict)
        and value.get("gpu_names") == ["NVIDIA H100 80GB HBM3"]
        and isinstance(value.get("scoped_rows"), int)
        and value["scoped_rows"] >= 1
        and value.get("cadence_lte_200ms") is True
    )


def valid_sentinel(terminal: object) -> bool:
    return bool(
        isinstance(terminal, dict)
        and terminal.get("stage") == "primary"
        and terminal.get("type") == "retrieved_h100_actual_parallel_lm_head_sentinel"
        and terminal.get("pass") is True
        and valid_head_result(terminal.get("result"), (8,))
        and valid_telemetry(terminal.get("telemetry"))
    )


def valid_remainder(terminal: object) -> bool:
    return bool(
        isinstance(terminal, dict)
        and terminal.get("stage") == "conditional"
        and terminal.get("type") == "persisted_h100_actual_parallel_lm_head_m16_m32"
        and terminal.get("pass") is True
        and valid_head_result(terminal.get("result"), (16, 32))
        and valid_telemetry(terminal.get("telemetry"))
    )


def linear_trigger(sentinel: object, remainder: object, history: object, deadline_epoch: float, now_epoch: float) -> bool:
    if not valid_sentinel(sentinel) or not valid_remainder(remainder) or not historical_setup_pass(history):
        return False
    rows = sentinel["result"]["rows"] + remainder["result"]["rows"]
    return bool(
        any(row["per_request_head_seconds_at_358_steps"] < CEILING_SECONDS for row in rows)
        and history.get("linear_ready") is True
        and deadline_epoch - now_epoch >= 420
    )


def build_terminal(
    sentinel: object,
    remainder: object,
    history: object,
    deadline_epoch: float,
    now_epoch: float,
    linear_result: object | None,
    telemetry: object,
) -> dict[str, object]:
    trigger = linear_trigger(sentinel, remainder, history, deadline_epoch, now_epoch)
    terminal: dict[str, object] = {
        "schema_version": 1,
        "stage": "conditional",
        "type": "retrieved_h100_head_m16_m32_then_optional_exact_linears",
        "trigger_name": TRIGGER,
        "trigger": trigger,
        "head_evidence_persisted_before_trigger": valid_remainder(remainder),
        "sentinel": sentinel,
        "head_m16_m32": remainder,
        "historical_setup": history,
        "telemetry": telemetry,
        "linear_attempted": linear_result is not None,
    }
    if not valid_sentinel(sentinel) or not valid_remainder(remainder) or not valid_telemetry(telemetry):
        terminal.update(pass=False, disposition="typed_head_or_telemetry_failure")
    elif not trigger:
        terminal.update(pass=True, disposition="head_preserved_trigger_false_cleanup")
    elif valid_linear_result(linear_result):
        terminal.update(pass=True, disposition="head_preserved_exact_24_linears_pass", linear_result=linear_result)
    else:
        terminal.update(pass=False, disposition="head_preserved_linear_failure", linear_result=linear_result)
    return terminal


def manifest(root: Path) -> list[dict[str, object]]:
    return [
        {"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(root.rglob("*")) if path.is_file() and path.name != "manifest.json"
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sentinel", type=Path, required=True)
    parser.add_argument("--remainder", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--linear-result", type=Path)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    parser.add_argument("--now-epoch", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text())
    terminal = build_terminal(
        load(args.sentinel), load(args.remainder), load(args.history), args.deadline_epoch,
        args.now_epoch, load(args.linear_result) if args.linear_result and args.linear_result.is_file() else None,
        load(args.telemetry),
    )
    atomic_json(args.output, terminal)
    return 0 if terminal["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
