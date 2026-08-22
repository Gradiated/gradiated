#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any


SOURCES = ("instruction", "reasoning", "code", "tool_use")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    temporary.replace(path)


def primary_id(row: dict[str, Any]) -> str:
    value = row.get("primary_id") or row.get("id")
    if not isinstance(value, str) or not value:
        raise ValueError("every regenerated row must have a nonempty primary_id or id")
    return value.rsplit("_gen", 1)[0]


def ranked_ids(source: str, groups: dict[str, list[dict[str, Any]]], seed: int) -> list[str]:
    return sorted(
        groups,
        key=lambda value: hashlib.sha256(
            f"{seed}:{source}:{value}".encode()
        ).hexdigest(),
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    digest = hashlib.sha256()
    with temporary.open("wb") as output:
        for row in rows:
            encoded = (
                json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n"
            ).encode()
            output.write(encoded)
            digest.update(encoded)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)
    return digest.hexdigest()


def split(
    inputs: dict[str, Path],
    output_dir: Path,
    *,
    train_per_source: int,
    holdout_per_source: int,
    seed: int,
) -> dict[str, Any]:
    train_rows: list[dict[str, Any]] = []
    holdout_rows: list[dict[str, Any]] = []
    source_rows: dict[str, dict[str, int]] = {}
    selected_ids: dict[str, dict[str, list[str]]] = {}

    for source in SOURCES:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        with inputs[source].open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"{inputs[source]}:{line_number}: invalid JSON"
                    ) from error
                if not isinstance(row, dict):
                    raise ValueError(f"{inputs[source]}:{line_number}: row is not object")
                groups[primary_id(row)].append(row)

        required = train_per_source + holdout_per_source
        if len(groups) < required:
            raise ValueError(
                f"{source} has {len(groups)} unique requests; {required} required"
            )
        ids = ranked_ids(source, groups, seed)
        holdout_ids = ids[:holdout_per_source]
        train_ids = ids[holdout_per_source:required]
        if set(train_ids) & set(holdout_ids):
            raise AssertionError("train/holdout request identity overlap")

        for split_name, chosen, destination in (
            ("train", train_ids, train_rows),
            ("holdout", holdout_ids, holdout_rows),
        ):
            for request_id in chosen:
                for row in groups[request_id]:
                    tagged = dict(row)
                    metadata = dict(tagged.get("metadata") or {})
                    metadata["dataset_domain"] = source
                    metadata["dataset_split"] = split_name
                    tagged["metadata"] = metadata
                    destination.append(tagged)

        source_rows[source] = {
            "available_unique_requests": len(groups),
            "train_unique_requests": len(train_ids),
            "holdout_unique_requests": len(holdout_ids),
            "train_generated_rows": sum(len(groups[x]) for x in train_ids),
            "holdout_generated_rows": sum(len(groups[x]) for x in holdout_ids),
        }
        selected_ids[source] = {"train": train_ids, "holdout": holdout_ids}

    train_path = output_dir / "train.jsonl"
    holdout_path = output_dir / "holdout.jsonl"
    train_sha = write_jsonl(train_path, train_rows)
    holdout_sha = write_jsonl(holdout_path, holdout_rows)
    manifest = {
        "schema_version": 1,
        "seed": seed,
        "algorithm": "sha256(seed:domain:primary_id), ascending",
        "request_disjoint": True,
        "source_stratified": True,
        "train_unique_requests": train_per_source * len(SOURCES),
        "holdout_unique_requests": holdout_per_source * len(SOURCES),
        "source_rows": source_rows,
        "selected_ids": selected_ids,
        "outputs": {
            "train": {
                "path": str(train_path),
                "sha256": train_sha,
                "generated_rows": len(train_rows),
            },
            "holdout": {
                "path": str(holdout_path),
                "sha256": holdout_sha,
                "generated_rows": len(holdout_rows),
            },
        },
    }
    atomic_json(output_dir / "SPLIT_MANIFEST.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    for source in SOURCES:
        parser.add_argument(f"--{source.replace('_', '-')}", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--train-per-source", type=int, default=1250)
    parser.add_argument("--holdout-per-source", type=int, default=128)
    parser.add_argument("--seed", type=int, default=20260729)
    args = parser.parse_args()
    inputs = {
        source: getattr(args, source)
        for source in SOURCES
    }
    result = split(
        inputs,
        args.output_dir,
        train_per_source=args.train_per_source,
        holdout_per_source=args.holdout_per_source,
        seed=args.seed,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
