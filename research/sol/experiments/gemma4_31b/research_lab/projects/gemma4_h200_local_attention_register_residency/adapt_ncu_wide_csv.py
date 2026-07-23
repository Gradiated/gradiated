#!/usr/bin/env python3
"""Adapt Nsight Compute's wide CSV export for the frozen consumer parser.

This is a consumer-only repair: it preserves the original export, selects the
two already-recorded _fwd_kernel rows, and repeats the header/units block that
the preregistered analyzer expects.  It never invokes CUDA or changes metrics.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_csv(path: Path, rows: list[list[str]]) -> None:
    temporary = path.with_name(f".{path.name}.repair-{os.getpid()}")
    with temporary.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.repair-{os.getpid()}")
    with temporary.open("w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()

    input_sha256 = sha256(args.input)
    with args.input.open(newline="") as handle:
        rows = list(csv.reader(handle))

    header_index = next(
        index
        for index, row in enumerate(rows)
        if "Kernel Name" in row and "ID" in row
    )
    header = rows[header_index]
    units = rows[header_index + 1]
    kernel_index = header.index("Kernel Name")
    kernels = [
        row
        for row in rows[header_index + 2 :]
        if len(row) == len(header) and row[kernel_index] == "_fwd_kernel"
    ]
    if len(kernels) != 2:
        raise RuntimeError(f"expected_two_persisted_fwd_rows:observed={len(kernels)}")

    if args.backup.exists():
        if sha256(args.backup) != input_sha256:
            raise RuntimeError("existing_backup_does_not_match_input")
    else:
        args.backup.write_bytes(args.input.read_bytes())
        args.backup.chmod(0o444)

    adapted_rows: list[list[str]] = []
    for kernel in kernels:
        adapted_rows.extend([header, units, kernel, []])
    atomic_write_csv(args.input, adapted_rows)

    payload: dict[str, object] = {
        "schema_version": 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "ordinary_consumer_format_adapter",
        "candidate_cuda_invocation_replayed": False,
        "scientific_producer_replayed": False,
        "source_sha256": input_sha256,
        "adapted_sha256": sha256(args.input),
        "backup_sha256": sha256(args.backup),
        "kernel_rows": len(kernels),
        "kernel_names": [row[kernel_index] for row in kernels],
        "metric_columns": len(header),
    }
    atomic_write_json(args.audit, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
