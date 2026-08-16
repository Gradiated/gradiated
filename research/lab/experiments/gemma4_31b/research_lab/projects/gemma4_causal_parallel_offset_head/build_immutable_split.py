#!/usr/bin/env python3
"""Materialize the exact c32 request identities and immutable 4096/512 split."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil


EXPECTED = {
    "workload": "7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d",
    "token_trace": "d30fdf18fc95549b0c5037b190ad3e6446a053db8e380690c70b45eb82c14caa",
    "runner": "143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7",
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_bytes(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)


def atomic_json(path: pathlib.Path, value: object) -> None:
    atomic_bytes(
        path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    )


def row_score(domain: str, request_sha256: str, offset: int) -> str:
    return hashlib.sha256(
        f"{domain}|{request_sha256}|{offset}".encode()
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workload", required=True, type=pathlib.Path)
    parser.add_argument("--token-trace", required=True, type=pathlib.Path)
    parser.add_argument("--runner", required=True, type=pathlib.Path)
    parser.add_argument("--output-root", required=True, type=pathlib.Path)
    args = parser.parse_args()
    observed = {
        "workload": sha256(args.workload),
        "token_trace": sha256(args.token_trace),
        "runner": sha256(args.runner),
    }
    if observed != EXPECTED:
        raise RuntimeError(f"input_hash_mismatch:{observed}")
    workload = json.loads(args.workload.read_text())
    trace = json.loads(args.token_trace.read_text())
    request_hashes = workload["request_sha256"]
    if len(request_hashes) != 32 or len(trace) != 32:
        raise RuntimeError("expected_exact_c32")
    holdout_requests = sorted(
        range(32),
        key=lambda index: row_score("holdout-request", request_hashes[index], 0),
    )[:4]
    train_requests = sorted(set(range(32)) - set(holdout_requests))
    candidates: dict[int, list[dict]] = {}
    for request_index, request_sha256 in enumerate(request_hashes):
        emitted = trace[request_index]["emitted_token_ids"]
        if len(emitted) != 358:
            raise RuntimeError(
                f"target_token_count:{request_index}:{len(emitted)}"
            )
        candidates[request_index] = [
            {
                "example_id": row_score("offset-example", request_sha256, offset),
                "request_index": request_index,
                "request_sha256": request_sha256,
                "target_start_offset": offset,
                "target_token_ids": emitted[offset : offset + 16],
            }
            for offset in range(len(emitted) - 15)
        ]
    holdout = []
    for request_index in holdout_requests:
        holdout.extend(
            sorted(
                candidates[request_index],
                key=lambda row: row_score(
                    "holdout-offset", row["request_sha256"], row["target_start_offset"]
                ),
            )[:128]
        )
    train_pool = [
        row for request_index in train_requests for row in candidates[request_index]
    ]
    train = sorted(
        train_pool,
        key=lambda row: row_score(
            "train-offset", row["request_sha256"], row["target_start_offset"]
        ),
    )[:4096]
    if len(train) != 4096 or len(holdout) != 512:
        raise RuntimeError("split_size_failure")
    if {row["request_sha256"] for row in train} & {
        row["request_sha256"] for row in holdout
    }:
        raise RuntimeError("request_disjointness_failure")
    inputs = args.output_root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    snapshots = {
        "qualified_c32_workload.json": args.workload,
        "qualified_c32_token_trace.json": args.token_trace,
        "exact_runner.py": args.runner,
    }
    for name, source in snapshots.items():
        destination = inputs / name
        shutil.copyfile(source, destination)
        os.chmod(destination, 0o444)
    for name, rows in (
        ("train_4096.jsonl", train),
        ("holdout_512.jsonl", holdout),
    ):
        destination = inputs / name
        atomic_bytes(
            destination,
            b"".join(
                json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
                + b"\n"
                for row in rows
            ),
        )
        os.chmod(destination, 0o444)
    manifest = {
        "schema_version": 1,
        "classification": "immutable_request_disjoint_target_generated_split",
        "seed_domain": "sha256 domain-separated deterministic ranking",
        "model": {
            "id": "google/gemma-4-31B-it",
            "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        },
        "workload": {
            "concurrency": 32,
            "prompt_tokens": 4214,
            "output_tokens": 358,
            "shared_prefix_tokens": 535,
        },
        "train": {
            "examples": len(train),
            "requests": train_requests,
            "request_count": len({row["request_sha256"] for row in train}),
            "path": "inputs/train_4096.jsonl",
            "sha256": sha256(inputs / "train_4096.jsonl"),
        },
        "holdout": {
            "examples": len(holdout),
            "requests": holdout_requests,
            "request_count": len(holdout_requests),
            "path": "inputs/holdout_512.jsonl",
            "sha256": sha256(inputs / "holdout_512.jsonl"),
        },
        "request_disjoint": True,
        "input_snapshots": {
            name: {"sha256": sha256(inputs / name)}
            for name in sorted(snapshots)
        },
        "limitation": (
            "The split binds target-generated token windows and request identity. "
            "Matching layer-tap tensors must be produced by the bound one-pass "
            "capture before training or holdout scoring."
        ),
    }
    atomic_json(args.output_root / "IMMUTABLE_SPLIT.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
