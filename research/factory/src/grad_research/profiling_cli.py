from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .profiling import (
    ProfilingError,
    analyze_profile,
    append_shape_record,
    compare_profiles,
    default_sampler_command,
    probe_host,
    run_capture,
)
from .gcore_inventory import GcoreInventoryError, load_cached_gcore_inventory, load_or_refresh_gcore_inventory
from .provider_inventory import ProviderInventoryError, load_provider_inventory


FACTORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROVIDERS = FACTORY_ROOT / "data" / "providers.json"
DEFAULT_GCORE_INVENTORY = FACTORY_ROOT / "docs" / "GCORE.md"
DEFAULT_ATLAS = FACTORY_ROOT / "data" / "profiling_shape_atlas.json"


def _command(arguments: list[str]) -> list[str]:
    return arguments[1:] if arguments[:1] == ["--"] else arguments


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="grad-profile",
        description="Capture and normalize selective GPU profiling evidence without provisioning infrastructure.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    probe = subparsers.add_parser("probe", help="Record host, accelerator, topology, and profiler readiness")
    probe.add_argument("--output", type=Path, required=True)

    providers = subparsers.add_parser("providers", help="Show candidate provider interfaces and profiling status")
    providers.add_argument("--inventory", type=Path, default=DEFAULT_PROVIDERS)
    providers.add_argument("--provider")
    providers.add_argument("--gcore-inventory", type=Path, default=DEFAULT_GCORE_INVENTORY)
    providers.add_argument("--refresh", action="store_true", help="Force a Gcore inventory refresh")
    providers.add_argument("--offline", action="store_true", help="Read the cached Gcore Markdown inventory only")

    capture = subparsers.add_parser("capture", help="Run a profiler-off baseline or a bounded diagnostic capture")
    capture.add_argument("--tier", choices=("baseline", "timeline", "compute"), default="baseline")
    capture.add_argument("--backend", choices=("nvidia", "amd"), default="nvidia")
    capture.add_argument("--output-root", type=Path, required=True)
    capture.add_argument("--timeout", type=float, default=900)
    capture.add_argument("--sample-interval", type=float, default=1.0)
    capture.add_argument("--kernel-name")
    capture.add_argument("--nvtx-include")
    capture.add_argument("--launch-skip", type=int)
    capture.add_argument("--launch-count", type=int)
    capture.add_argument("--section", action="append")
    capture.add_argument("--artifact", type=Path, action="append")
    capture.add_argument("--no-sampler", action="store_true")
    capture.add_argument("command", nargs=argparse.REMAINDER)

    analyze = subparsers.add_parser("analyze", help="Normalize profiler output into one summary")
    analyze.add_argument("--run-dir", type=Path, required=True)
    analyze.add_argument("--torch-trace", type=Path)
    analyze.add_argument("--nsys-sqlite", type=Path)
    analyze.add_argument("--ncu-csv", type=Path)
    analyze.add_argument("--rocprof-kernel-csv", type=Path)
    analyze.add_argument("--benchmark", type=Path)
    analyze.add_argument("--semantics", type=Path)

    compare = subparsers.add_parser("compare", help="Compare control and candidate summaries")
    compare.add_argument("--control", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--output", type=Path)

    shape = subparsers.add_parser("shape-record", help="Append a measured exact-shape result to the shared atlas")
    shape.add_argument("--atlas", type=Path, default=DEFAULT_ATLAS)
    shape.add_argument("--input", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.subcommand == "probe":
            result = probe_host(args.output)
        elif args.subcommand == "providers":
            result = load_provider_inventory(args.inventory)
            if args.provider:
                provider = result["providers"].get(args.provider)
                if not provider:
                    raise ProviderInventoryError(f"unknown provider: {args.provider}")
                if args.provider == "gcore":
                    live = (
                        load_cached_gcore_inventory(args.gcore_inventory)
                        if args.offline
                        else load_or_refresh_gcore_inventory(args.gcore_inventory, force=args.refresh)
                    )
                    result = {**provider, "live_inventory": live}
                else:
                    result = provider
        elif args.subcommand == "capture":
            command = _command(args.command)
            sampler = None if args.no_sampler or args.backend != "nvidia" else default_sampler_command()
            result = run_capture(
                tier=args.tier,
                backend=args.backend,
                command=command,
                output_root=args.output_root,
                timeout_seconds=args.timeout,
                sample_interval_seconds=args.sample_interval,
                sampler_command=sampler,
                kernel_name=args.kernel_name,
                nvtx_include=args.nvtx_include,
                launch_skip=args.launch_skip,
                launch_count=args.launch_count,
                sections=args.section,
                artifact_paths=args.artifact,
            )
        elif args.subcommand == "analyze":
            result = analyze_profile(
                run_dir=args.run_dir,
                torch_trace=args.torch_trace,
                nsys_sqlite=args.nsys_sqlite,
                ncu_csv=args.ncu_csv,
                rocprof_kernel_csv=args.rocprof_kernel_csv,
                benchmark_path=args.benchmark,
                semantics_path=args.semantics,
            )
        elif args.subcommand == "compare":
            result = compare_profiles(args.control, args.candidate, args.output)
        else:
            result = append_shape_record(args.atlas, json.loads(args.input.read_text()))
    except (OSError, json.JSONDecodeError, ProfilingError, ProviderInventoryError, GcoreInventoryError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
