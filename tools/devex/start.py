#!/usr/bin/env python3
"""Run the standard repository-agent startup sequence."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workstream", choices=("sol", "fable"))
    args = parser.parse_args()

    context = [sys.executable, "tools/devex/context.py"]
    if args.workstream:
        context += ["--workstream", args.workstream]

    for command in (context, [sys.executable, "tools/devex/check.py"]):
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            return result.returncode

    print("agent startup checks passed; continue with the GitHub issue workflow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
