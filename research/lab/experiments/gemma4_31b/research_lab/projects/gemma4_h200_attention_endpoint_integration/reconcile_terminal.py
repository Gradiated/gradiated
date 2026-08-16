#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    stock_path = args.artifact_root / "STOCK_TERMINAL.json"
    candidate_path = args.artifact_root / "CANDIDATE_TERMINAL.json"
    oracle_path = args.artifact_root / "NUMERICAL_ORACLE.json"
    stock = load(stock_path)
    candidate = load(candidate_path)
    oracle = load(oracle_path)
    endpoint_gate = bool(
        candidate.get("pass")
        and candidate.get("complete_requests") == 32
        and candidate.get("output_tokens_per_request") == 358
        and candidate.get("service_seconds_per_request", float("inf")) <= 0.6206366743249874
    )
    passed = endpoint_gate and oracle.get("pass") is True
    terminal = {
        "schema_version": 1,
        "status": "terminal",
        "pass": passed,
        "classification": "endpoint_performance_promotion" if passed else "performance_terminal" if oracle.get("pass") else "quality_terminal",
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "gate": {
            "maximum_service_seconds_per_request": 0.6206366743249874,
            "complete_requests": 32,
            "output_tokens_per_request": 358,
            "endpoint_pass": endpoint_gate,
            "numerical_pass": oracle.get("pass") is True,
        },
        "stock": stock,
        "candidate": candidate,
        "numerical_oracle": oracle,
        "artifacts": {
            "stock_terminal_sha256": sha256(stock_path),
            "candidate_terminal_sha256": sha256(candidate_path),
            "numerical_oracle_sha256": sha256(oracle_path),
            "candidate_patch_sha256": (args.artifact_root / "candidate-patch.sha256").read_text().split()[0],
        },
    }
    partial = args.artifact_root / "TERMINAL.json.part"
    partial.write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
    partial.replace(args.artifact_root / "TERMINAL.json")


if __name__ == "__main__":
    main()
