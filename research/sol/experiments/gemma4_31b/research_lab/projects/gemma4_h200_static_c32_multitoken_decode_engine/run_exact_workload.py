#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sys


HERE = pathlib.Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--output-tokens", type=int, required=True)
    args = parser.parse_args()

    runner_path = HERE / "inputs" / "bound" / "fp8_qkv_paired_runner.py"
    if not runner_path.is_file():
        runner_path = HERE / "bound" / "fp8_qkv_paired_runner.py"
    spec = importlib.util.spec_from_file_location("bound_exact_runner", runner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load bound exact runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUTPUT_TOKENS = args.output_tokens
    sys.argv = [
        str(runner_path),
        "--output",
        str(args.output),
        "--arm",
        args.arm,
        "--concurrency",
        "32",
    ]
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(main())
