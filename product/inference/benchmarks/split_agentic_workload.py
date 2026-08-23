#!/usr/bin/env python3
"""Split an agent-trace workload by session without cross-split leakage."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--train-fraction", type=float, default=0.70)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    parser.add_argument("--seed", default="gradiated-speculative-v1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0 < args.train_fraction < 1:
        raise ValueError("--train-fraction must be between zero and one")
    if not 0 < args.validation_fraction < 1:
        raise ValueError("--validation-fraction must be between zero and one")
    if args.train_fraction + args.validation_fraction >= 1:
        raise ValueError("train and validation fractions must sum to less than one")

    records: list[dict[str, object]] = []
    with args.input.open(encoding="utf-8") as workload:
        for line_number, line in enumerate(workload, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not record.get("session_id"):
                raise ValueError(f"{args.input}:{line_number}: missing session_id")
            records.append(record)

    unique_records: dict[str, dict[str, object]] = {}
    for record in records:
        unique_records.setdefault(str(record["session_id"]), record)
    records = list(unique_records.values())

    # Ranking a salted hash gives exact split sizes while remaining independent
    # of source-file order. All turns from a session stay in one split.
    records.sort(
        key=lambda record: hashlib.sha256(
            f"{args.seed}\0{record['session_id']}".encode()
        ).digest()
    )
    train_end = round(len(records) * args.train_fraction)
    validation_end = train_end + round(len(records) * args.validation_fraction)
    splits = {
        "train": records[:train_end],
        "validation": records[train_end:validation_end],
        "holdout": records[validation_end:],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "source": str(args.input),
        "seed": args.seed,
        "split_unit": "session_id",
        "deduplicated_sessions": len(records),
        "splits": {},
    }
    for name, split_records in splits.items():
        output = args.output_dir / f"{name}.jsonl"
        with output.open("w", encoding="utf-8") as stream:
            for record in split_records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        manifest["splits"][name] = {  # type: ignore[index]
            "path": str(output),
            "sessions": len(split_records),
            "session_ids_sha256": hashlib.sha256(
                "\n".join(str(record["session_id"]) for record in split_records).encode()
            ).hexdigest(),
        }

    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
