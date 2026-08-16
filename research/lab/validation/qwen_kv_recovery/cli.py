from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from validation.qwen_int4_quality.schema import load_corpus

from .runner import run_recovery
from .schema import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a CPU-only Qwen3-0.6B exact KV-sharing recovery screen.",
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--first-holdout", type=Path, required=True)
    parser.add_argument("--confirmation-holdout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-training-target-tokens", type=int)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        config = load_config(args.config)
        maximum = (
            args.maximum_training_target_tokens or config.data.training_target_tokens
        )
        report = run_recovery(
            model_path=args.model,
            config_path=args.config,
            first_holdout_path=args.first_holdout,
            first_holdout=load_corpus(args.first_holdout),
            confirmation_holdout_path=args.confirmation_holdout,
            confirmation_holdout=load_corpus(args.confirmation_holdout),
            output_path=args.output,
            config=config,
            maximum_training_target_tokens=maximum,
        )
    except (FileNotFoundError, MemoryError, OSError, RuntimeError, ValueError) as error:
        print(f"Qwen KV recovery failed: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "output": str(args.output),
                "outcome": report["decision"]["outcome"],
                "peak_rss_bytes": report["resources"]["peak_rss_bytes"],
            },
            sort_keys=True,
        )
    )
    return 0
