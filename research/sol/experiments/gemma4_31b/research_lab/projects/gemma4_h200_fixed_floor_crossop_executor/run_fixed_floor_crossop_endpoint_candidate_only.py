#!/usr/bin/env python3
"""Candidate-only boundary; never creates or touches control state."""
from __future__ import annotations
import argparse, json, pathlib

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--control-observer", type=pathlib.Path, required=True)
    p.add_argument("--output", type=pathlib.Path, required=True)
    a = p.parse_args()
    observer = json.loads(a.control_observer.read_text())
    if not observer.get("pass"):
        raise SystemExit("immutable_control_token_observer_incomplete")
    raise SystemExit("candidate_runner_requires_bound_runtime_adapter")

if __name__ == "__main__":
    raise SystemExit(main())
