"""Build a repaired, screened release index; export requires independent completion."""

import argparse
import collections
import hashlib
import json
import sqlite3
import time
from functools import lru_cache
from pathlib import Path

from audit_scale import Components, decision_keys, key
from data import grams, normalized_state, read_jsonl, text, validate_row
from prepare_scale import PINS, digest_file
from scale_data import curate_candidate
from source_policy import (
    EXCLUSION_EVIDENCE,
    VERSION,
    canonical_family,
    heldout_family,
    near_state_key,
    rejection,
    source_priority,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, action="append", required=True)
    parser.add_argument("--benchmark", type=Path, action="append", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=2400)
    args = parser.parse_args()
    import pyarrow as pa
    import pyarrow.parquet as pq

    started = time.monotonic()
    deadline = started + args.seconds
    root = args.run_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("retain prior release generations; output must be empty")
    source = root / "index-source"
    source.mkdir()
    source_hashes = {}
    protected_directory = root / "protected"
    protected_directory.mkdir()
    protected_files = {}
    for path in args.benchmark:
        sha = digest_file(path)
        relative = "protected/" + sha + ".jsonl"
        (root / relative).write_bytes(path.read_bytes())
        protected_files[relative] = sha
    for name in (
        "release_index.py",
        "source_policy.py",
        "scale_data.py",
        "original_data.py",
        "data.py",
        "audit_scale.py",
        "prepare_scale.py",
    ):
        content = Path(__file__).with_name(name).read_bytes()
        (source / name).write_bytes(content)
        source_hashes[name] = hashlib.sha256(content).hexdigest()

    def check():
        if time.monotonic() >= deadline:
            raise TimeoutError("release index deadline")

    inputs = []
    approvals = json.loads(
        Path(__file__).with_name("candidate_approvals.json").read_text()
    )
    for directory in args.candidates:
        marker = json.loads((directory / "COMPLETE.json").read_text())
        if digest_file(directory / "manifest.json") != marker["manifest_sha256"]:
            raise ValueError("candidate manifest mismatch")
        manifest = json.loads((directory / "manifest.json").read_text())
        approval = approvals.get(marker["manifest_sha256"])
        if approval is None or manifest["builder"] != approval["builder"]:
            raise ValueError("candidate builder has not been approved")
        archived = root / "candidate-source" / marker["manifest_sha256"]
        archived.mkdir(parents=True)
        for name, expected in approval["builder"].items():
            path = directory / "source" / name
            if digest_file(path) != expected:
                raise ValueError("candidate executable source differs from approval")
            (archived / name).write_bytes(path.read_bytes())
        for item in manifest["sources"]:
            if (
                PINS.get(item["repo"]) != item["revision"]
                or "/train" not in item["file"]
            ):
                raise ValueError(
                    "release input has an unreviewed source or non-training split"
                )
        for item in manifest["files"]:
            check()
            if digest_file(directory / item["file"]) != item["sha256"]:
                raise ValueError("candidate shard mismatch")
        inputs.append(
            {
                "directory": str(directory.resolve()),
                "manifest_sha256": marker["manifest_sha256"],
                "manifest": manifest,
            }
        )
    benchmarks = [row for path in args.benchmark for row in read_jsonl(path)]
    exact = {normalized_state(row["state"]) for row in benchmarks}
    protected_grams = set().union(*(grams(row["state"]) for row in benchmarks))

    @lru_cache(maxsize=10000)
    def protected(state):
        return normalized_state(state) in exact or bool(grams(state) & protected_grams)

    db = sqlite3.connect(root / "release.sqlite")
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA temp_store=MEMORY")
    db.execute("PRAGMA cache_size=-262144")
    db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 10000)
    db.execute(
        "CREATE TABLE items(n INTEGER PRIMARY KEY,case_key BLOB,state_key BLOB,near_key BLOB,input_key BLOB,target_key BLOB,family TEXT,kind TEXT,language TEXT,priority INTEGER,dev INTEGER,blocked INTEGER)"
    )
    staged = root / "staged"
    staged.mkdir()
    files = []
    pending = []
    counts = collections.Counter()
    reasons = collections.Counter()
    n = 0

    def flush():
        if not pending:
            return
        path = staged / f"part-{len(files):05d}.parquet"
        pq.write_table(pa.Table.from_pylist(pending), path, compression="zstd")
        files.append(
            {
                "file": str(path.relative_to(root)),
                "rows": len(pending),
                "sha256": digest_file(path),
            }
        )
        pending.clear()

    for source_input in inputs:
        for file in source_input["manifest"]["files"]:
            rows = []
            for batch in pq.ParquetFile(
                Path(source_input["directory"]) / file["file"]
            ).iter_batches(batch_size=2048, columns=["record_json"]):
                check()
                for record in batch.column(0).to_pylist():
                    counts["input_questions"] += 1
                    original = json.loads(record)
                    try:
                        row = validate_row(curate_candidate(original))
                        provenance = row["provenance"]
                        if (
                            provenance["repo"] != row["source"]
                            or PINS.get(provenance["repo"]) != provenance["revision"]
                        ):
                            raise ValueError(
                                "candidate provenance differs from pinned source"
                            )
                        reason = rejection(row)
                        if reason:
                            reasons[reason] += 1
                            continue
                        state_key, input_key, target_key = decision_keys(row)
                    except (ValueError, KeyError, TypeError) as error:
                        reasons["invalid_or_unreviewed:" + str(error)] += 1
                        continue
                    family = canonical_family(
                        row.get("family_group", row["source_task"])
                    )
                    row = {**row, "family_group": family, "release_candidate_n": n}
                    block = protected(text(row["state"]))
                    counts["direct_protected_questions"] += block
                    counts["question_repairs"] += (
                        row["question"] != original["question"]
                    )
                    near = near_state_key(row) or state_key
                    rows.append(
                        (
                            n,
                            key(row["group"]),
                            state_key,
                            near,
                            input_key,
                            target_key,
                            family,
                            row["question"]["type"],
                            row.get("language") or "unspecified",
                            source_priority(row),
                            int(heldout_family(family)),
                            int(block),
                        )
                    )
                    pending.append(
                        {"n": n, "record_json": json.dumps(row, ensure_ascii=False)}
                    )
                    n += 1
                    if len(pending) >= 25000:
                        flush()
                db.executemany(
                    "INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows
                )
                rows.clear()
            db.commit()
            print(
                json.dumps(
                    {
                        "file": file["file"],
                        "staged": n,
                        "input": counts["input_questions"],
                    }
                ),
                flush=True,
            )
    flush()
    for field in ("case_key", "state_key", "near_key", "input_key"):
        check()
        db.execute(f"CREATE INDEX by_{field} ON items({field})")
    db.execute(
        "CREATE TABLE decisions AS SELECT input_key,MIN(priority*100000000+n)%100000000 AS representative,COUNT(DISTINCT target_key) AS targets FROM items GROUP BY input_key"
    )
    db.execute("CREATE UNIQUE INDEX decision_key ON decisions(input_key)")
    components = Components(n)
    for field in ("case_key", "state_key", "near_key", "input_key"):
        previous, representative = None, None
        for index, value in db.execute(f"SELECT n,{field} FROM items ORDER BY {field}"):
            if value == previous:
                components.union(index, representative)
            else:
                previous, representative = value, index
    blocked = set()
    heldout = set()
    for index, flag, dev, targets in db.execute(
        "SELECT i.n,i.blocked,i.dev,d.targets FROM items i JOIN decisions d USING(input_key)"
    ):
        component = components.root(index)
        if flag or targets > 1:
            blocked.add(component)
        if dev:
            heldout.add(component)
    db.execute(
        "CREATE TABLE disposition(n INTEGER PRIMARY KEY,component INTEGER,partition TEXT,eligible INTEGER)"
    )
    records = []
    for index, dev, representative, targets in db.execute(
        "SELECT i.n,i.dev,d.representative,d.targets FROM items i JOIN decisions d USING(input_key) ORDER BY i.n"
    ):
        component = components.root(index)
        partition = (
            "quarantine"
            if component in blocked
            else "dev"
            if component in heldout and dev
            else "withheld_case"
            if component in heldout
            else "train"
        )
        eligible = (
            index == representative and targets == 1 and partition in ("train", "dev")
        )
        counts[partition + "_questions"] += eligible
        counts["quarantined_component_questions"] += partition == "quarantine"
        records.append((index, component, partition, int(eligible)))
        if len(records) >= 10000:
            check()
            db.executemany("INSERT INTO disposition VALUES(?,?,?,?)", records)
            records.clear()
    db.executemany("INSERT INTO disposition VALUES(?,?,?,?)", records)
    db.execute("CREATE INDEX selection ON disposition(eligible,partition,n)")
    counts["staged_questions"] = n
    counts["split_components"] = sum(
        components.root(index) == index for index in range(n)
    )
    counts["conflicting_inputs"] = db.execute(
        "SELECT COUNT(*) FROM decisions WHERE targets>1"
    ).fetchone()[0]
    db.commit()
    db.close()
    manifest = {
        "status": "INDEX_COMPLETE_NOT_YET_ADMITTED",
        "policy_version": VERSION,
        "counts": dict(counts),
        "rejections": dict(reasons),
        "staged_files": files,
        "input_manifests": [
            {"directory": i["directory"], "sha256": i["manifest_sha256"]}
            for i in inputs
        ],
        "protected_files": protected_files,
        "executable_sources_sha256": source_hashes,
        "writer_exclusions": EXCLUSION_EVIDENCE,
        "near_grouping_scope": "Exact source cases, canonical states, input identity and same token-multiset/operator state. Near keys co-locate splits only; distinct inputs/counterfactual targets are not deleted by near keys. Arbitrary semantic/translation equivalence is not certified.",
        "seconds": time.monotonic() - started,
    }
    (root / "index.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (root / "INDEX-COMPLETE.json").write_text(
        json.dumps(
            {
                "index_sha256": digest_file(root / "index.json"),
                "sqlite_sha256": digest_file(root / "release.sqlite"),
            }
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "complete": True,
                "counts": dict(counts),
                "rejections": dict(reasons),
                "seconds": manifest["seconds"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
