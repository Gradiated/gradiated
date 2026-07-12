from __future__ import annotations

import argparse
from pathlib import Path


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute one pinned SCALE-Sim GEMM case."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--topology", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)

    from scalesim.scale_sim import scalesim

    args.output.mkdir(parents=True, exist_ok=True)
    simulation = scalesim(
        save_disk_space=True,
        verbose=False,
        config=str(args.config),
        topology=str(args.topology),
        layout=str(args.layout),
        input_type_gemm=True,
    )
    simulation.run_scale(top_path=str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
