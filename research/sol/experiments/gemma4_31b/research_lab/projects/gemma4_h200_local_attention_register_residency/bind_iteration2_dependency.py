#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil


HERE = pathlib.Path(__file__).resolve().parent
EXPECTED_PROJECT = "gemma4_h200_flashinfer_metadata_scalar_elimination"
EXPECTED_BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dependency-project", type=pathlib.Path, required=True)
    parser.add_argument("--terminal", type=pathlib.Path, required=True)
    parser.add_argument("--pool-inventory", type=pathlib.Path, required=True)
    parser.add_argument("--bench", default=EXPECTED_BENCH)
    args = parser.parse_args()
    if args.dependency_project.name != EXPECTED_PROJECT:
        raise RuntimeError("unexpected_dependency_project")
    status = json.loads((args.dependency_project / "STATUS.json").read_text())
    terminal = json.loads(args.terminal.read_text())
    if terminal.get("status") != "terminal":
        raise RuntimeError("dependency_terminal_not_durable")
    pool = json.loads(args.pool_inventory.read_text())
    bench = pool["benches"][args.bench]
    dependency_status_settled = (
        status.get("status") != "active" and status.get("active_session") is None
    )
    dependency_bench_released = (
        bench.get("status") == "available" and bench.get("claim") is None
    )
    if not (dependency_status_settled or dependency_bench_released):
        raise RuntimeError("dependency_not_terminal_or_released")

    destination = HERE / "inputs/evidence/flashinfer_metadata_scalar_terminal.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.part")
    shutil.copyfile(args.terminal, temporary)
    os.replace(temporary, destination)
    source_hash = sha256(args.terminal)
    if sha256(destination) != source_hash:
        raise RuntimeError("dependency_snapshot_hash_mismatch")
    binding = {
        "schema_version": 1,
        "pass": True,
        "dependency_project": EXPECTED_PROJECT,
        "source_terminal": str(args.terminal),
        "source_terminal_sha256": source_hash,
        "project_local_snapshot": "inputs/evidence/flashinfer_metadata_scalar_terminal.json",
        "project_local_snapshot_sha256": source_hash,
        "dependency_classification": terminal.get("classification"),
        "dependency_completion_proof": (
            "settled_status" if dependency_status_settled else "durable_terminal_and_atomic_pool_release"
        ),
        "dependency_status_stale_at_binding": not dependency_status_settled,
        "released_bench": args.bench,
        "released_bench_inventory_updated_at": bench.get("updated_at"),
        "dependency_actual_spend_usd": status.get("actual_spend_usd"),
        "dependency_frontier_seconds_per_request": status.get(
            "current_frontier_seconds_per_request"
        ),
    }
    atomic_json(HERE / "ITERATION2_DEPENDENCY_BINDING.json", binding)
    print(json.dumps(binding, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
