#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kda_sweep import run_sweep, write_outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the KDA FPGA architecture sweep")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "results",
    )
    args = parser.parse_args()
    result = run_sweep()
    write_outputs(result, args.output_dir)
    print(f"rows={result['all_row_count']}")
    print(f"kv260_candidates={result['candidate_count']}")
    print(f"pareto={len(result['pareto_frontier'])}")
    for label in ("best_latency", "best_energy", "best_balanced"):
        row = result[label]
        print(
            f"{label}={row['name']} latency_us={row['latency_us']:.3f} "
            f"energy_uJ={row['energy_proxy_uj']:.3f} resources="
            f"{row['logic_cells']}/{row['dsp_slices']}/{row['bram18k']}/{row['uram_blocks']}"
        )


if __name__ == "__main__":
    main()
