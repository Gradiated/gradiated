#!/usr/bin/env python3
"""Run the dependency-free repository DevEx checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    commands = [
        [sys.executable, "tools/devex/validate_skills.py"],
        [sys.executable, "tools/devex/doctor.py"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
