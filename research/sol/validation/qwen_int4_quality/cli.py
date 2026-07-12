from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .runner import run_validation
from .schema import load_corpus, load_run_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure local Qwen3-0.6B quality deltas after weight-only INT4 quantize-dequantize.",
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        config = load_run_config(args.config)
        corpus = load_corpus(args.corpus)
        report = run_validation(
            args.model,
            args.config,
            args.corpus,
            config,
            corpus,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
        temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(args.output)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        print(f"quality validation failed: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {"output": str(args.output), "passed": report["quality_report"]["passed"]}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
