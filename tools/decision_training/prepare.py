"""Acquire pinned public decision data, screen it, and write a reproducible mix."""

import argparse
import collections
import gzip
import hashlib
import json
import random
import urllib.request
from pathlib import Path

from data import (
    grams,
    normalize_tasksource,
    normalize_typed,
    normalized_state,
    split_rows,
    text,
)

TASKSOURCE = (
    "tasksource/tasksource-jev-typed-decisions",
    "8df2e5c9a33f19a2c2b8febf291c3acb0a91a8a8",
)
SN92 = (
    (
        "decisionmodels/sn92-generalist-train-v1",
        "2241ec2c5e9812178c3127165d830a3bc8006685",
    ),
    ("decisionmodels/sn92-specialists", "e2ff3bb099553fd9fd93f806152d5f261579bf3e"),
)
BENCH_REVISION = "609a664e81f46e03731600bd7bd9f1b7a61257c5"


def priority(source):
    return source.startswith("procedural-typed-decisions/") or any(
        key in source.lower()
        for key in (
            "helpsteer",
            "condaqa",
            "cuad",
            "when2call",
            "logical",
            "nli",
            "math",
            "temporal",
            "tool",
            "policy",
            "dynasent",
            "votes",
            "sts-",
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--tasksource-shards", type=int, choices=range(1, 7), default=6)
    parser.add_argument("--priority-cap", type=int, default=1000)
    parser.add_argument("--other-cap", type=int, default=150)
    parser.add_argument("--sn92-family-cap", type=int, default=1000)
    parser.add_argument("--dev-rows", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261121)
    args = parser.parse_args()
    if min(args.priority_cap, args.other_cap, args.sn92_family_cap, args.dev_rows) < 1:
        parser.error("sample bounds must be positive")
    import pyarrow.parquet as pq
    from huggingface_hub import HfApi, hf_hub_download

    root = args.run_dir.resolve()
    output = root / "data"
    output.mkdir(parents=True, exist_ok=True)
    inputs, counts, buckets = [], collections.Counter(), collections.defaultdict(list)
    rng = random.Random(args.seed)

    def acquire_github(path):
        url = f"https://raw.githubusercontent.com/fstandhartinger/jevbench/{BENCH_REVISION}/{path}"
        destination = root / "jevbench" / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as response:
            content = response.read()
        destination.write_bytes(content)
        inputs.append(
            {
                "url": url,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        )
        return destination

    benchmark = []
    for name in ("easy", "original", "hard"):
        path = acquire_github(f"datasets/public/{name}.jsonl")
        benchmark.extend(
            json.loads(line) for line in path.read_text().splitlines() if line
        )
    if len(benchmark) != 231:
        raise ValueError("the frozen JevBench suite must contain exactly 231 items")
    for name in ("__init__", "scoring", "tasks", "metrics"):
        acquire_github(f"jevbench/{name}.py")
    benchmark_grams = set().union(*(grams(row["state"]) for row in benchmark))
    benchmark_states = {normalized_state(row["state"]) for row in benchmark}
    seen = set()

    def acquire_hf(repo, revision, filename):
        path = Path(
            hf_hub_download(repo, filename, repo_type="dataset", revision=revision)
        )
        inputs.append(
            {
                "repo": repo,
                "revision": revision,
                "file": filename,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
        )
        return path

    def admit(row):
        if row is None:
            counts["excluded_terms_or_author"] += 1
            return
        state = normalized_state(row["state"])
        if state in benchmark_states or grams(row["state"]) & benchmark_grams:
            counts["benchmark_overlap"] += 1
            return
        if len(text(row["state"])) > 24000:
            counts["longer_than_24000_characters"] += 1
            return
        identity = hashlib.sha256((state + text(row["question"])).encode()).hexdigest()
        if identity in seen:
            counts["duplicate"] += 1
            return
        seen.add(identity)
        buckets[row["source_task"]].append(row)

    repo, revision = TASKSOURCE
    for shard in range(args.tasksource_shards):
        name = f"data/train-{shard:05d}-of-00006.parquet"
        path = acquire_hf(repo, revision, name)
        for batch in pq.ParquetFile(path).iter_batches(batch_size=2048):
            for row in batch.to_pylist():
                try:
                    admit(normalize_tasksource(row))
                except (KeyError, TypeError, ValueError):
                    counts["invalid_or_unsupported"] += 1
        print(json.dumps({"file": name, "counts": dict(counts)}), flush=True)

    for repo, revision in SN92:
        files = HfApi().list_repo_files(repo, repo_type="dataset", revision=revision)
        for name in files:
            if not (name.endswith((".jsonl.gz", "/train.jsonl"))):
                continue
            path = acquire_hf(repo, revision, name)
            opener = gzip.open if name.endswith(".gz") else open
            with opener(path, "rt") as stream:
                for line in stream:
                    try:
                        admit(normalize_typed(json.loads(line), repo))
                    except (KeyError, TypeError, ValueError):
                        counts["invalid_or_unsupported"] += 1

    selected = []
    for source, rows in sorted(buckets.items()):
        rng.shuffle(rows)
        cap = (
            args.sn92_family_cap
            if rows[0]["source"].startswith("decisionmodels/")
            else (args.priority_cap if priority(source) else args.other_cap)
        )
        selected.extend(rows[:cap])
    train, dev = split_rows(selected)
    rng.shuffle(train)
    rng.shuffle(dev)
    dev = dev[: args.dev_rows]
    if not train or not dev:
        raise ValueError("training and held-out dev data are both required")
    for name, rows in [("train", train), ("dev", dev), ("jevbench-231", benchmark)]:
        (output / f"{name}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        )
    manifest = {
        "seed": args.seed,
        "inputs": inputs,
        "counts": dict(counts),
        "train_rows": len(train),
        "dev_rows": len(dev),
        "benchmark_rows": len(benchmark),
        "jevbench_revision": BENCH_REVISION,
        "soft_target_rows": sum(sum(p > 0 for p in r["target"]) > 1 for r in train),
        "source_tasks": dict(collections.Counter(r["source_task"] for r in train)),
        "question_types": dict(
            collections.Counter(r["question"]["type"] for r in train)
        ),
        "selection": {k: v for k, v in vars(args).items() if k != "run_dir"},
        "filters": [
            "commercial-use tasksource rows",
            "named restricted synthetic author exclusions",
            "exact and word-13-gram state overlap against JevBench-231",
            "grouped train/dev split with normalized-state dev overlap exclusion",
        ],
        "files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in output.glob("*.jsonl")
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {k: manifest[k] for k in ("train_rows", "dev_rows", "soft_target_rows")}
        )
    )


if __name__ == "__main__":
    main()
