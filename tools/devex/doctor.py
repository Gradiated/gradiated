#!/usr/bin/env python3
"""Report the repo-local agent development environment without exposing secrets."""

from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def command_status(name: str) -> str:
    path = shutil.which(name)
    return f"ok ({path})" if path else "missing"


def module_status(name: str) -> str:
    return "ok" if importlib.util.find_spec(name) else "missing"


def main() -> int:
    print(f"repo: {ROOT}")
    print(f"python: {os.sys.executable}")
    print("\nCommands:")
    for name in ("git", "docker", "uv", "cargo", "rustc", "gh", "node"):
        print(f"  {name:8} {command_status(name)}")
    print("\nPython modules:")
    for name in ("playwright", "browser_use", "pytest"):
        print(f"  {name:16} {module_status(name)}")
    print("\nRepo paths:")
    for relative in ("AGENTS.md", ".agents/skills", "tasks", "Makefile", "tools/browser/pyproject.toml", "tools/github/agent.py", "research/sol", "research/fable"):
        path = ROOT / relative
        print(f"  {relative:32} {'present' if path.exists() else 'missing'}")
    print("\nCredential variables present (values hidden):")
    names = sorted(name for name in os.environ if any(token in name for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD")))
    print("  " + (", ".join(names) if names else "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
