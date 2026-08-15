#!/usr/bin/env python3
"""Print a compact, deterministic context pack for a new repository agent."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

WORKSTREAMS = {
    "sol": {
        "instructions": "research/sol/AGENTS.md",
        "start": "research/sol/README.md",
        "handoff": "research/sol/CONTEXT_HANDOFF.md",
        "artifacts": ("research/sol/docs", "research/sol/evidence", "research/sol/experiments"),
        "checks": "cd research/sol && cargo fmt --check && cargo clippy --workspace --all-targets -- -D warnings && cargo test --workspace",
    },
    "fable": {
        "instructions": "research/fable/CLAUDE.md",
        "start": "research/fable/README.md",
        "handoff": "research/fable/docs/REPORT.md",
        "artifacts": ("research/fable/docs", "research/fable/evidence", "research/fable/experiments"),
        "checks": "read research/fable/CLAUDE.md; run the narrowest relevant Rust/Python checks",
    },
}


def exists(relative: str) -> str:
    path = ROOT / relative
    return f"{relative} [{'present' if path.exists() else 'missing'}]"


def git_summary() -> str:
    result = subprocess.run(
        ["git", "status", "--short", "--branch"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    lines = result.stdout.splitlines()
    branch = lines[0] if lines else "git status unavailable"
    changed = sum(1 for line in lines[1:] if line.strip())
    return f"{branch} ({changed} changed/untracked entries; inspect before editing)"


def print_pack(workstream: str | None) -> None:
    print("AGENT CONTEXT PACK")
    print(f"repo: {ROOT}")
    print(f"git: {git_summary()}")
    print("\nRead first:")
    for path in ("AGENTS.md", "README.md", "docs/ARCHITECTURE.md", "docs/DATA_MODEL.md"):
        print(f"- {exists(path)}")

    selected = [workstream] if workstream else list(WORKSTREAMS)
    for name in selected:
        spec = WORKSTREAMS[name]
        print(f"\nWorkstream: {name}")
        for key in ("instructions", "start", "handoff"):
            print(f"- {exists(spec[key])}")
        print("- artifact roots:")
        for artifact_root in spec["artifacts"]:
            print(f"  - {exists(artifact_root)}")
        print(f"- checks: {spec['checks']}")

    print("\nBefore changing files:")
    print("- claim one GitHub issue; confirm the Project status and owner")
    print("- reserve directory/artifact scope; do not edit another agent's files")
    print("- state the acceptance check, budget/timeout, and artifact paths")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workstream", choices=sorted(WORKSTREAMS))
    args = parser.parse_args()
    print_pack(args.workstream)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
