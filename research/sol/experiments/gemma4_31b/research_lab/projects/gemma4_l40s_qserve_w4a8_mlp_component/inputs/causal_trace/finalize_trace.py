#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib


ROOT = pathlib.Path("/work/artifacts/qserve-causal-trace")
DEPTHS = (0, 1, 15, 30, 45, 60)


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    trace_path = (
        ROOT / "TRACE_TERMINAL_NORMALIZED.json"
        if (ROOT / "TRACE_TERMINAL_NORMALIZED.json").is_file()
        else ROOT / "TRACE_TERMINAL.json"
    )
    trace = json.loads(trace_path.read_text())
    oracle = json.loads((ROOT / "ORACLE_TERMINAL.json").read_text())
    capture = json.loads((ROOT / "ORACLE_CAPTURE_REQUEST.json").read_text())
    failures = []
    for name in ("gate_up", "activation", "down"):
        comparison = oracle["stages"][name][
            "fused_vs_dequantized_w4_oracle"
        ]
        if (
            comparison["relative_l2"] > 0.01
            or comparison["cosine_similarity"] < 0.999
            or comparison["actual_nonfinite"] != 0
            or comparison["reference_nonfinite"] != 0
        ):
            failures.append(
                {
                    "kind": "fused_oracle_mismatch",
                    "stage": name,
                    "metrics": comparison,
                }
            )
    for row in trace["rows"]:
        depth = int(row["depth"])
        counts = row["path_counts"]["routes"]
        total_calls = sum(int(value) for value in counts.values())
        steps, remainder = divmod(total_calls, 60)
        expected = {
            "fp8_prefill": 0,
            "w4_decode": steps * depth,
            "fp8_decode": steps * (60 - depth),
        }
        observed = {
            name: int(counts.get(name, 0))
            for name in expected
        }
        if remainder or observed != expected:
            failures.append(
                {
                    "kind": "path_count_mismatch",
                    "depth": depth,
                    "total_layer_calls": total_calls,
                    "full_forward_steps": steps,
                    "remainder": remainder,
                    "expected": expected,
                    "observed": observed,
                }
            )
    divergences = [
        item["first_output_divergence"]
        for item in trace["curve"][1:]
        if item["first_output_divergence"] is not None
    ]
    cumulative = bool(divergences) and all(
        right <= left for left, right in zip(divergences, divergences[1:])
    )
    if not cumulative:
        failures.append(
            {
                "kind": "noncumulative_depth_curve",
                "divergences": divergences,
            }
        )
    if not capture["matches_trace_row"]:
        failures.append({"kind": "capture_request_not_deterministic"})

    fused_or_path_failures = [
        item
        for item in failures
        if item["kind"] in {"fused_oracle_mismatch", "path_count_mismatch"}
    ]
    representation_evidence = not fused_or_path_failures and cumulative
    repair_already_consumed = True
    integration_defect = bool(failures) and not repair_already_consumed
    result = {
        "schema_version": 1,
        "classification": (
            "integration_defect_repair_permitted"
            if integration_defect
            else "uncalibrated_w4_representation_reject"
        ),
        "pass": representation_evidence and not integration_defect,
        "decision": (
            "one narrow mapping/order/scale/routing repair is permitted"
            if integration_defect
            else "close uncalibrated all-layer W4; the single repair is consumed and no held-out gate or endpoint is permitted"
        ),
        "trace_terminal": trace_path.name,
        "oracle_terminal": "ORACLE_TERMINAL.json",
        "capture_request": "ORACLE_CAPTURE_REQUEST.json",
        "first_divergent_target": trace["first_divergent_target"],
        "cumulative_depth_degradation": cumulative,
        "fused_oracle_failures": failures,
        "representation_evidence": representation_evidence,
        "single_repair_consumed": repair_already_consumed,
        "residual_capture_nondeterminism": not capture["matches_trace_row"],
        "heldout_gate_started": False,
        "c32_started": False,
    }
    atomic(ROOT / "TERMINAL.json", result)
    state = json.loads((ROOT / "INVOCATION_STATE.json").read_text())
    state["scientific_terminal"] = result["classification"]
    atomic(ROOT / "INVOCATION_STATE.json", state)
    return 75 if integration_defect else 0


if __name__ == "__main__":
    raise SystemExit(main())
