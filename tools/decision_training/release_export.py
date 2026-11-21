"""Export a bounded, balanced, tokenized research release from a verified index."""

import argparse
import collections
import hashlib
import importlib.metadata
import json
import shutil
import signal
import sqlite3
import time
from pathlib import Path

from audit_tokens import initialize, terminating_pool, verify_tokenizer_directory
from data import read_jsonl, validate_row
from prepare_scale import digest_file
from runtime import runtime_fingerprint
from source_policy import VERSION, family_cap, rejection


def tokenize(records):
    import audit_tokens
    from prompting import render_prompt

    rows = [json.loads(record) for record in records]
    prompts = [render_prompt(audit_tokens.TOKENIZER, row) for row in rows]
    ids = audit_tokens.TOKENIZER(
        prompts, add_special_tokens=False, truncation=False, padding=False
    )["input_ids"]
    return list(zip(rows, ids, strict=True))


def apply_override(row, overrides):
    if row["source"] != "caiovicentino1/eikos-decisions":
        return row
    override = overrides["rows"][row["id"]]
    if override.get("reject"):
        return None
    return {
        **row,
        "license": override["license"],
        "attribution": override["attribution"],
    }


def select(db, train_limit=None):
    """Co-locate components, cap repetitive cases and round-robin language/type cells."""
    db.create_function("family_cap", 1, family_cap, deterministic=True)
    db.executescript("""
        CREATE TEMP TABLE component_ranked AS
        SELECT i.n,i.family,i.kind,i.language,i.input_key,d.component,d.partition,
          ROW_NUMBER() OVER(PARTITION BY d.partition,d.component ORDER BY i.input_key,i.n) AS case_rank
        FROM items i JOIN disposition d USING(n) WHERE d.eligible=1;
        CREATE TEMP TABLE cells AS
        SELECT *, ROW_NUMBER() OVER(PARTITION BY partition,family,language,kind ORDER BY input_key,n) AS cell_rank
        FROM component_ranked WHERE case_rank<=CASE WHEN partition='dev' THEN 1 ELSE 16 END;
        CREATE TEMP TABLE ranked AS
        SELECT *,ROW_NUMBER() OVER(PARTITION BY partition,family ORDER BY cell_rank,language,kind,input_key,n) AS family_rank
        FROM cells;
        CREATE TEMP TABLE chosen(n INTEGER PRIMARY KEY,partition TEXT,component INTEGER,family TEXT);
        INSERT INTO chosen SELECT n,partition,component,family FROM ranked
        WHERE partition='train' AND family_rank<=family_cap(family);
        INSERT INTO chosen SELECT n,partition,component,family FROM ranked
        WHERE partition='dev' ORDER BY family_rank,family,input_key,n LIMIT 10000;
        DROP TABLE component_ranked;
        DROP TABLE cells;
        DROP TABLE ranked;
    """)
    if train_limit is not None:
        db.execute(
            "DELETE FROM chosen WHERE partition='train' AND n NOT IN (SELECT n FROM chosen WHERE partition='train' ORDER BY n LIMIT ?)",
            (train_limit,),
        )
    if (
        db.execute(
            "SELECT COUNT(*) FROM (SELECT family FROM chosen GROUP BY family HAVING COUNT(DISTINCT partition)>1)"
        ).fetchone()[0]
        or db.execute(
            "SELECT COUNT(*) FROM (SELECT component FROM chosen GROUP BY component HAVING COUNT(DISTINCT partition)>1)"
        ).fetchone()[0]
    ):
        raise ValueError("release partitions overlap")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--tokenizer-dir", type=Path, required=True)
    parser.add_argument("--tokenizer-manifest", type=Path, required=True)
    parser.add_argument("--eikos-overrides", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--metadata-dir", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seconds", type=int, default=1100)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--train-limit", type=int)
    args = parser.parse_args()
    import pyarrow as pa
    import pyarrow.parquet as pq

    if not 1 <= args.workers <= 32 or args.seconds < 1 or args.max_length < 1:
        raise ValueError("invalid export bounds")
    started = time.monotonic()
    deadline = started + args.seconds

    def check(*unused):
        if unused or time.monotonic() >= deadline:
            raise TimeoutError("release export deadline")

    signal.signal(signal.SIGALRM, check)
    signal.setitimer(signal.ITIMER_REAL, args.seconds)
    root = args.run_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("export output must be empty")
    marker = json.loads((args.index / "INDEX-COMPLETE.json").read_text())
    for name, field in (
        ("index.json", "index_sha256"),
        ("release.sqlite", "sqlite_sha256"),
    ):
        if digest_file(args.index / name) != marker[field]:
            raise ValueError("index identity mismatch")
    index = json.loads((args.index / "index.json").read_text())
    if index["policy_version"] != VERSION:
        raise ValueError("index policy mismatch")
    token_manifest = json.loads(args.tokenizer_manifest.read_text())
    if token_manifest["revision"] != "6e7c8248f75265bdd4fbab5273304243b5d8c2cb":
        raise ValueError("wrong tokenizer")
    verify_tokenizer_directory(args.tokenizer_dir, token_manifest)
    overrides = json.loads(args.eikos_overrides.read_text())
    if (
        digest_file(args.eikos_overrides)
        != "07f0ca5ca66f8eb08ac4a038a4002577b51ba18f9e809f4c1ed47f3bd0cc2c73"
    ):
        raise ValueError("unreviewed legacy Eikos overrides")
    benchmark = list(read_jsonl(args.benchmark))
    if len(benchmark) != 231:
        raise ValueError("expected frozen public 231")
    from data import normalized_state

    protected_states = {
        normalized_state(row["state"])
        for filename in index["protected_files"]
        for row in read_jsonl(Path(filename))
    }
    if not all(normalized_state(row["state"]) in protected_states for row in benchmark):
        raise ValueError("benchmark was not protected by this index")
    metadata = root / "metadata"
    shutil.copytree(args.metadata_dir, metadata)
    for name, path in (
        ("eikos-terms-overrides.json", args.eikos_overrides),
        ("tokenizer-manifest.json", args.tokenizer_manifest),
        ("index.json", args.index / "index.json"),
        ("INDEX-COMPLETE.json", args.index / "INDEX-COMPLETE.json"),
    ):
        shutil.copy2(path, metadata / name)
    for filename, expected in index["protected_files"].items():
        path = Path(filename)
        if digest_file(path) != expected:
            raise ValueError("protected corpus changed")
        shutil.copy2(path, metadata / ("protected-" + path.name))
    shutil.copytree(args.index / "index-source", metadata / "index-source")
    source = root / "source"
    source.mkdir()
    for name in (
        "release_export.py",
        "audit_tokens.py",
        "prompting.py",
        "source_policy.py",
        "data.py",
        "prepare_scale.py",
        "scale_data.py",
        "original_data.py",
        "runtime.py",
    ):
        shutil.copy2(Path(__file__).with_name(name), source / name)
    shutil.copy2(args.benchmark, root / "jevbench-231.jsonl")
    db = sqlite3.connect(f"file:{args.index / 'release.sqlite'}?mode=ro", uri=True)
    db.execute("PRAGMA temp_store=MEMORY")
    db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 10000)
    select(db, args.train_limit)
    counts = collections.Counter()
    families = collections.Counter()
    languages = collections.Counter()
    kinds = collections.Counter()
    source_counts = collections.Counter()
    states = set()
    groups = set()
    train_families = set()
    dev_families = set()
    files = []
    pending = []
    dev_count = 0
    dev_candidates = collections.defaultdict(list)

    def flush():
        if not pending:
            return
        path = root / f"train-{len(files):05d}.parquet"
        pq.write_table(pa.Table.from_pylist(pending), path, compression="zstd")
        files.append(
            {"file": path.name, "rows": len(pending), "sha256": digest_file(path)}
        )
        pending.clear()

    def work():
        for item in index["staged_files"]:
            check()
            path = args.index / item["file"]
            if digest_file(path) != item["sha256"]:
                raise ValueError("staged input mismatch")
            # Each staged shard contains dense n, preserving its original index mapping.
            rows = pq.read_table(path).to_pylist()
            if not rows:
                continue
            chosen = {
                n: (partition, component)
                for n, partition, component in db.execute(
                    "SELECT n,partition,component FROM chosen WHERE n BETWEEN ? AND ?",
                    (rows[0]["n"], rows[-1]["n"]),
                )
            }
            records = []
            for value in rows:
                if value["n"] not in chosen:
                    continue
                partition, component = chosen[value["n"]]
                row = apply_override(json.loads(value["record_json"]), overrides)
                if row is None:
                    counts["eikos_unverified_split_rejected"] += 1
                    continue
                row = validate_row(row)
                if rejection(row):
                    raise ValueError("final source policy rejection")
                row["release_partition"] = partition
                row["release_component"] = component
                records.append(json.dumps(row, ensure_ascii=False))
                if len(records) == 512:
                    yield records
                    records = []
            if records:
                yield records

    # Bound submission: one shard is streamed in windows; no multi-million-row future queue.
    with (
        (root / "dev.jsonl").open("w") as dev,
        terminating_pool(
            max_workers=args.workers,
            initializer=initialize,
            initargs=(str(args.tokenizer_dir),),
        ) as pool,
    ):
        iterator = iter(work())
        while True:
            batches = []
            for _ in range(args.workers * 2):
                batch = next(iterator, None)
                if batch is None:
                    break
                batches.append(batch)
            if not batches:
                break
            for result in pool.map(
                tokenize, batches, timeout=max(0.01, deadline - time.monotonic())
            ):
                check()
                for row, ids in result:
                    partition = row["release_partition"]
                    if len(ids) > args.max_length:
                        counts[partition + "_too_long"] += 1
                        continue
                    if partition == "dev":
                        dev_candidates[row["family_group"]].append((row, len(ids)))
                        continue
                    else:
                        pending.append(
                            {
                                "record_json": json.dumps(row, ensure_ascii=False),
                                "input_ids": ids,
                            }
                        )
                        families[row["family_group"]] += 1
                        languages[row.get("language") or "unspecified"] += 1
                        kinds[row["question"]["type"]] += 1
                        source_counts[row["source"]] += 1
                        train_families.add(row["family_group"])
                        states.add(
                            hashlib.sha256(
                                json.dumps(
                                    row["state"], sort_keys=True, ensure_ascii=False
                                ).encode()
                            ).digest()[:16]
                        )
                        groups.add(row["release_component"])
                        if len(pending) >= 25000:
                            flush()
                    counts[partition + "_questions"] += 1
                    counts[partition + "_tokens"] += len(ids)
            print(
                json.dumps(
                    {"counts": dict(counts), "seconds": time.monotonic() - started}
                ),
                flush=True,
            )
        for values in dev_candidates.values():
            values.sort(
                key=lambda item: hashlib.sha256(item[0]["id"].encode()).digest()
            )
        for position in range(10000):
            for family in sorted(dev_candidates):
                if position >= len(dev_candidates[family]) or dev_count >= 1000:
                    continue
                row, length = dev_candidates[family][position]
                dev.write(json.dumps(row, ensure_ascii=False) + "\n")
                dev_count += 1
                dev_families.add(family)
                counts["dev_questions"] += 1
                counts["dev_tokens"] += length
            if dev_count == 1000:
                break
    flush()
    if (
        not counts["train_questions"]
        or dev_count != 1000
        or train_families & dev_families
    ):
        raise ValueError("release train/dev cardinality or family disjointness failed")
    manifest = {
        "status": "ADMITTED_RESEARCH_RELEASE"
        if args.train_limit is None
        else "SMOKE_ONLY",
        "policy_version": VERSION,
        "index_identity": marker,
        "counts": dict(counts),
        "train_states": len(states),
        "train_components": len(groups),
        "families": dict(families),
        "languages": dict(languages),
        "types": dict(kinds),
        "sources": dict(source_counts),
        "train_families": sorted(train_families),
        "dev_families": sorted(dev_families),
        "max_length": args.max_length,
        "files": files,
        "dev_sha256": digest_file(root / "dev.jsonl"),
        "benchmark_sha256": digest_file(root / "jevbench-231.jsonl"),
        "prompting_sha256": digest_file(source / "prompting.py"),
        "tokenizer_manifest_sha256": digest_file(args.tokenizer_manifest),
        "tokenizer_runtime": {
            name: importlib.metadata.version(name)
            for name in ("transformers", "tokenizers", "jinja2")
        },
        "tokenizer_implementation": runtime_fingerprint(check)["package_files"],
        "limitations": "Source-evidence-reviewed research mixture. No claim of fully independent semantic certification or arbitrary translation deduplication. Teacher confidence and exact/human targets retain source provenance. Near-state keys co-locate splits only. Benchmark expected labels are not used for selection.",
        "selection": "Exact input representatives; conflict/benchmark component quarantine; global family holdout; max16 questions/component; round-robin language/type family caps (SNLI/ESCI300k, procedural75k, others60k); no truncation. First256 of dev1000 reserved for calibration.",
        "seconds": time.monotonic() - started,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    all_files = [
        {
            "file": str(path.relative_to(root)),
            "sha256": digest_file(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]
    (root / "COMPLETE.json").write_text(
        json.dumps(
            {
                "manifest_sha256": digest_file(root / "manifest.json"),
                "files": all_files,
            },
            indent=2,
        )
        + "\n"
    )
    signal.setitimer(signal.ITIMER_REAL, 0)
    print(
        json.dumps(
            {
                "complete": True,
                "counts": dict(counts),
                "manifest_sha256": digest_file(root / "manifest.json"),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
