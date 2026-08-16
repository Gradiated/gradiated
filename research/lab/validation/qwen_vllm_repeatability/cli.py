from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import (
    execute_campaign,
    load_spec,
    prepare_campaign,
    run_client_setup_probe,
    run_startup_probe,
    wait_for_clean_host,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("prepare", "startup-probe", "client-probe", "run", "wait-run"),
        nargs="?",
        default="prepare",
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    spec, raw = load_spec(args.config)
    if args.action == "prepare":
        result = prepare_campaign(spec, raw, args.output_root.resolve())
    elif args.action == "startup-probe":
        result = run_startup_probe(spec, raw, args.output_root.resolve())
    elif args.action == "client-probe":
        result = run_client_setup_probe(spec, raw, args.output_root.resolve())
    elif args.action == "wait-run":
        wait_for_clean_host(spec, args.output_root.resolve(), raw)
        result = execute_campaign(spec, raw, args.output_root.resolve())
    else:
        result = execute_campaign(spec, raw, args.output_root.resolve())
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
