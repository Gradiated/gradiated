#!/usr/bin/env python3
"""Audit that the retrieved NCU launch is the preregistered sliced-V GEMM."""

from __future__ import annotations

import argparse
import json
import pathlib


def atomic_json(path: pathlib.Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component-result", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.component_result.read_text())
    kernel = str(result["metrics"]["Kernel Name"]["value"])
    normalized = kernel.casefold()
    matrix_multiply = any(marker in normalized for marker in ("gemm", "matmul"))
    audit = {
        "schema_version": 1,
        "status": "valid_sliced_v_capture" if matrix_multiply else "invalid_ncu_capture",
        "expected": "one sliced-V matrix-multiply kernel",
        "observed_kernel_name": kernel,
        "observed_gpu_time": result["metrics"]["gpu__time_duration.sum"],
        "capture_is_sliced_v_matmul": matrix_multiply,
        "counter_gate_is_admissible": matrix_multiply,
        "decision_impact": (
            "none: the exact-shape latency gate independently rejects; the admitted bytes also fail the oracle"
        ),
        "scientific_replay_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output, audit)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if matrix_multiply else 2


if __name__ == "__main__":
    raise SystemExit(main())
