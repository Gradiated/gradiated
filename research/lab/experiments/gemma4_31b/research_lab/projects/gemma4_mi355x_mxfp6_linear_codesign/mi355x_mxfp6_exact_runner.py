#!/usr/bin/env python3
"""Run the exact Gemma 4 dense MXFP6 hipBLASLt discriminator on gfx950."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PROJECT_DIR / "MI355X_MXFP6_TARGET_RESULT.json"

SHAPES = (
    ("sliding_qkv", 50, 5376, 16384),
    ("sliding_o", 50, 8192, 5376),
    ("global_qkv", 10, 5376, 20480),
    ("global_o", 10, 16384, 5376),
    ("gate_up", 60, 5376, 43008),
    ("down", 60, 21504, 5376),
)
M_VALUES = (32, 384)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_bench_csv(stdout: str) -> dict[str, str]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if not line.startswith("[0]:"):
            continue
        header = next(csv.reader([line.split(":", 1)[1]]))
        if index + 1 >= len(lines):
            break
        values = next(csv.reader([lines[index + 1]]))
        if len(header) != len(values):
            raise RuntimeError(
                f"hipblaslt-bench CSV width mismatch: {len(header)} != {len(values)}"
            )
        return dict(zip((item.strip() for item in header), (item.strip() for item in values)))
    raise RuntimeError("hipblaslt-bench did not emit its [0]: CSV record")


def benchmark_command(
    bench: Path,
    m: int,
    n: int,
    k: int,
    cold_iters: int,
    iters: int,
    *,
    verify: bool,
) -> list[str]:
    command = [
        str(bench),
        "--function",
        "matmul",
        "-m",
        str(m),
        "-n",
        str(n),
        "-k",
        str(k),
        "--transA",
        "N",
        "--transB",
        "N",
        "--a_type",
        "bf6_r",
        "--b_type",
        "bf6_r",
        "--c_type",
        "bf16_r",
        "--d_type",
        "bf16_r",
        "--compute_type",
        "f32_r",
        "--scaleA",
        "3",
        "--scaleB",
        "3",
        "--alpha",
        "1",
        "--beta",
        "0",
        "--initialization",
        "trig_float",
        "--cold_iters",
        str(cold_iters),
        "--iters",
        str(iters),
        "--use_gpu_timer",
        "--print_kernel_info",
    ]
    if verify:
        command.extend(("--verify", "1"))
    return command


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hipblaslt-bench", type=Path, required=True)
    parser.add_argument("--rocminfo", type=Path, default=Path("/opt/rocm/bin/rocminfo"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cold-iters", type=int, default=20)
    parser.add_argument("--iters", type=int, default=100)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to replay existing target result: {args.output}")
    for executable in (args.hipblaslt_bench, args.rocminfo):
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise SystemExit(f"required executable is unavailable: {executable}")
    if args.cold_iters < 1 or args.iters < 20:
        raise SystemExit("cold-iters must be >=1 and iters must be >=20")

    rocminfo = subprocess.run(
        [str(args.rocminfo)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if "gfx950" not in rocminfo.stdout:
        raise SystemExit("target identity failed: rocminfo did not report gfx950")

    help_result = subprocess.run(
        [str(args.hipblaslt_bench), "--help"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    required_help = ("--scaleA", "--scaleB", "--a_type", "--b_type", "--use_gpu_timer")
    missing_help = [fragment for fragment in required_help if fragment not in help_result.stdout]
    if missing_help:
        raise SystemExit(f"hipblaslt-bench contract missing: {missing_help}")

    science_started = args.output.with_suffix(".science_started")
    science_started.write_text("gfx950 identity and hipBLASLt CLI validated\n")

    correctness_command = benchmark_command(
        args.hipblaslt_bench,
        32,
        128,
        128,
        args.cold_iters,
        args.iters,
        verify=True,
    )
    correctness_result = subprocess.run(
        correctness_command,
        capture_output=True,
        text=True,
        timeout=120,
    )
    correctness_raw = {
        "command": correctness_command,
        "returncode": correctness_result.returncode,
        "stderr": correctness_result.stderr[-16000:],
        "stdout": correctness_result.stdout[-16000:],
    }
    atomic_json(args.output.with_suffix(".tiny_correctness.raw.json"), correctness_raw)
    if correctness_result.returncode != 0:
        atomic_json(
            args.output,
            {
                "classification": "typed_target_failure",
                "failed_stage": "tiny_layout_correctness",
                **correctness_raw,
            },
        )
        raise SystemExit(correctness_result.returncode)
    correctness_record = parse_bench_csv(correctness_result.stdout)
    correctness_norm_error = float(correctness_record.get("norm_error", "nan"))
    if not math.isfinite(correctness_norm_error):
        raise RuntimeError("tiny layout correctness result lacks finite norm_error")

    rows: list[dict[str, Any]] = []
    for name, layers, k, n in SHAPES:
        for m in M_VALUES:
            command = benchmark_command(
                args.hipblaslt_bench,
                m,
                n,
                k,
                args.cold_iters,
                args.iters,
                verify=False,
            )
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300,
            )
            raw_path = args.output.with_suffix(f".{name}.m{m}.raw.json")
            atomic_json(
                raw_path,
                {
                    "command": command,
                    "returncode": result.returncode,
                    "stderr": result.stderr[-16000:],
                    "stdout": result.stdout[-16000:],
                },
            )
            if result.returncode != 0:
                terminal = {
                    "classification": "typed_target_failure",
                    "failed_shape": {"name": name, "m": m, "n": n, "k": k},
                    "raw_path": str(raw_path),
                    "returncode": result.returncode,
                }
                atomic_json(args.output, terminal)
                raise SystemExit(result.returncode)
            record = parse_bench_csv(result.stdout)
            microseconds = float(record["us"])
            if not math.isfinite(microseconds) or microseconds <= 0:
                raise RuntimeError(f"non-finite timing for {name} M={m}: {microseconds}")
            rows.append(
                {
                    "command": command,
                    "dimensions": {"m": m, "n": n, "k": k},
                    "layers": layers,
                    "name": name,
                    "raw_path": str(raw_path),
                    "raw_record": record,
                    "time_microseconds": microseconds,
                }
            )
            atomic_json(
                args.output.with_suffix(f".{name}.m{m}.stage.json"),
                {"classification": "valid_stage", "row": rows[-1]},
            )

    atomic_json(
        args.output,
        {
            "classification": (
                "valid_target_mi355x_mxfp6_timing_matrix_with_tiny_layout_correctness"
            ),
            "correctness": {
                "dimensions": {"m": 32, "n": 128, "k": 128},
                "norm_error": correctness_norm_error,
                "raw_record": correctness_record,
            },
            "hardware": "gfx950",
            "representation": {
                "activation": "OCP MXFP6 E3M2, 32-element E8M0 block scale",
                "accumulation": "FP32",
                "output": "BF16",
                "weight": "OCP MXFP6 E3M2, 32-element E8M0 block scale",
            },
            "rows": rows,
            "runner_sha256": sha256(Path(__file__)),
            "schema_version": 1,
            "unproven": [
                "full-shape numerical comparison",
                "dynamic activation packing time",
                "vLLM dispatch and endpoint effect",
            ],
        },
    )


if __name__ == "__main__":
    main()
