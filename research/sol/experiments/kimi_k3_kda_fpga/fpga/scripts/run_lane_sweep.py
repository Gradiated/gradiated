#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from pathlib import Path


K26_LIMITS = {
    "lut": 117_120,
    "flip_flop": 234_240,
    "bram36": 144,
    "dsp": 1_248,
}


def numeric_count(value: object) -> int:
    if isinstance(value, dict):
        return int(value["count"])
    return int(value)


def run_variant(root: Path, output_dir: Path, head_dim: int, lanes: int, timeout: int) -> dict[str, object]:
    variant_dir = output_dir / f"lanes_{lanes}"
    variant_dir.mkdir(parents=True, exist_ok=True)
    stats_path = variant_dir / "stats.json"
    command = (
        "read_verilog -sv rtl/kda_state_bank.sv rtl/kda_core.sv; "
        f"chparam -set HEAD_DIM {head_dim} -set LANES {lanes} kda_core; "
        "synth_xilinx -family xcu -top kda_core; "
        f"tee -o {stats_path} stat -json -hierarchy"
    )
    started = time.monotonic()
    completed = subprocess.run(
        ["yosys", "-q", "-p", command],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    elapsed = time.monotonic() - started
    (variant_dir / "synthesis.log").write_text(completed.stdout + completed.stderr)
    if completed.returncode != 0:
        raise RuntimeError(f"Yosys failed for lanes={lanes}; see {variant_dir / 'synthesis.log'}")
    stats = json.loads(stats_path.read_text())
    design = stats["design"]
    cells = design["num_cells_by_type"]

    def cell_count(name: str) -> int:
        return numeric_count(cells.get(name, 0))

    lut = sum(cell_count(f"LUT{width}") for width in range(1, 7))
    flip_flop = sum(cell_count(name) for name in ("FDRE", "FDSE", "FDCE", "FDPE"))
    bram36 = cell_count("RAMB36E2") + cell_count("RAMB18E2") / 2.0
    dsp = cell_count("DSP48E2")
    cycles = 7 * head_dim * (head_dim // lanes)
    return {
        "evidence_class": "open_source_synthesis_proxy",
        "head_dim": head_dim,
        "lanes": lanes,
        "cycles_per_head": cycles,
        "latency_us_at_100mhz": cycles / 100.0,
        "latency_us_at_150mhz": cycles / 150.0,
        "latency_us_at_200mhz": cycles / 200.0,
        "dsp48e2": dsp,
        "dsp_percent": 100.0 * dsp / K26_LIMITS["dsp"],
        "bram36_equivalent": bram36,
        "bram_percent": 100.0 * bram36 / K26_LIMITS["bram36"],
        "lut_primitives": lut,
        "lut_percent": 100.0 * lut / K26_LIMITS["lut"],
        "flip_flops": flip_flop,
        "flip_flop_percent": 100.0 * flip_flop / K26_LIMITS["flip_flop"],
        "synthesis_seconds": elapsed,
        "stats_path": str(stats_path.relative_to(root)),
        "log_path": str((variant_dir / "synthesis.log").relative_to(root)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--head-dim", type=int, default=128)
    parser.add_argument("--lanes", type=int, nargs="+", default=[4, 8, 16, 32])
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output-dir", type=Path, default=Path("results/lane_sweep"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [run_variant(root, output_dir, args.head_dim, lanes, args.timeout) for lanes in args.lanes]
    result = {
        "experiment": {
            "name": "kda_kv260_lane_sweep",
            "evidence_class": "open_source_synthesis_proxy",
            "hypothesis": "more state lanes reduce recurrence cycles until DSP, SRAM banking, routing, or timing dominates",
            "stock_control": "4-lane banked state core",
            "workload": f"one fixed-point {args.head_dim}x{args.head_dim} recurrent KDA head",
            "quality_gate": "all variants use identical arithmetic and infer FPGA block RAM",
            "transfer_limit": "Yosys mapping does not establish Vivado timing closure, power, or measured KV260 latency",
        },
        "k26_limits_vendor_reported": K26_LIMITS,
        "rows": rows,
    }
    (output_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    with (output_dir / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
