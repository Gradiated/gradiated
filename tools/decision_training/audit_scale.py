"""Index canonical candidates and quarantine exact conflicts/protected case groups."""

import argparse
import array
import collections
import hashlib
import json
import sqlite3
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

from data import grams, normalized_state, read_jsonl, text
from prepare_scale import digest_file


def canonical_text(value):
    return " ".join(unicodedata.normalize("NFKC", text(value)).casefold().split())


def key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).digest()[:16]


def decision_keys(row):
    """Align nominal option probabilities by description; ordinal order stays fixed."""
    options = [canonical_text(value) for value in row["descriptions"]]
    if len(set(options)) != len(options):
        raise ValueError("canonical option descriptions are not distinct")
    order = list(range(len(options)))
    if row["question"]["type"] != "score":
        order.sort(key=options.__getitem__)
    state = row["state"]
    if isinstance(state, str):
        try:
            parsed = json.loads(state)
            if isinstance(parsed, (dict, list)):
                state = parsed
        except (ValueError, TypeError):
            pass
    state = canonical_text(state)
    instructions = canonical_text(row["question"]["instructions"])
    visible = [
        state,
        row["question"]["type"],
        instructions,
        [options[i] for i in order],
    ]
    target = [round(row["target"][i], 6) for i in order]
    # Empty and very short states often contain no scenario: group by full input.
    scenario = key([state]) if len(state.split()) >= 8 else key(visible)
    return scenario, key(visible), key(target)


class Components:
    def __init__(self, count):
        self.parents = array.array("I", range(count))

    def root(self, index):
        while self.parents[index] != index:
            self.parents[index] = self.parents[self.parents[index]]
            index = self.parents[index]
        return index

    def union(self, left, right):
        left, right = self.root(left), self.root(right)
        self.parents[max(left, right)] = min(left, right)


def group_components(connection, count):
    components = Components(count)
    for field in ("case_key", "state_key", "input_key"):
        previous, representative = None, None
        for index, value in connection.execute(
            f"SELECT n,{field} FROM items ORDER BY {field}"
        ):
            if value == previous:
                components.union(index, representative)
            else:
                previous, representative = value, index
    return components


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=1200)
    args = parser.parse_args()
    import pyarrow.parquet as pq

    started = time.monotonic()
    deadline = started + args.seconds

    def check():
        if time.monotonic() >= deadline:
            raise TimeoutError("candidate audit deadline reached")

    root = args.run_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("retain previous audits; new output must be empty")
    manifest_path = args.candidates / "manifest.json"
    complete = json.loads((args.candidates / "COMPLETE.json").read_text())
    if digest_file(manifest_path) != complete["manifest_sha256"]:
        raise ValueError("candidate manifest digest differs")
    manifest = json.loads(manifest_path.read_text())
    for item in manifest["files"]:
        check()
        if digest_file(args.candidates / item["file"]) != item["sha256"]:
            raise ValueError("candidate shard digest differs")
    bench = read_jsonl(args.benchmark)
    benchmark_states = {normalized_state(row["state"]) for row in bench}
    benchmark_grams = set().union(*(grams(row["state"]) for row in bench))

    @lru_cache(maxsize=10000)
    def overlaps(state):
        return normalized_state(state) in benchmark_states or bool(
            grams(state) & benchmark_grams
        )

    connection = sqlite3.connect(root / "audit.sqlite")
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA temp_store=MEMORY")
    connection.execute("PRAGMA cache_size=-131072")
    connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 10000)
    connection.execute(
        "CREATE TABLE items(n INTEGER PRIMARY KEY,candidate_n INTEGER,case_key BLOB,state_key BLOB,input_key BLOB,target_key BLOB,family TEXT,source TEXT,kind TEXT,blocked INTEGER)"
    )
    counts, families = collections.Counter(), collections.Counter()
    zero_group_ids = set()
    for item in manifest["sources"]:
        if item["repo"] != "tasksource/tasksource-jev-typed-decisions":
            continue
        for batch in pq.ParquetFile(item["path"]).iter_batches(
            columns=["id", "group_id"]
        ):
            check()
            for row in batch.to_pylist():
                value = row["group_id"]
                if isinstance(value, (int, float)) and value == 0:
                    zero_group_ids.add(row["id"])
    counts["zero_group_raw_rows_repaired"] = len(zero_group_ids)
    index, candidate_n = 0, -1
    for item in manifest["files"]:
        check()
        pending = []
        for batch in pq.ParquetFile(args.candidates / item["file"]).iter_batches(
            batch_size=2048, columns=["record_json"]
        ):
            check()
            for entry in batch.to_pylist():
                candidate_n += 1
                row = json.loads(entry["record_json"])
                try:
                    state_key, input_key, target_key = decision_keys(row)
                except ValueError:
                    counts["ambiguous_canonical_options"] += 1
                    continue
                blocked = overlaps(text(row["state"]))
                counts["direct_benchmark_matching_questions"] += blocked
                family = row["family_group"]
                families[family] += 1
                group = row["group"]
                if (
                    row["source"] == "tasksource/tasksource-jev-typed-decisions"
                    and row["id"] in zero_group_ids
                ):
                    group = row["source"] + ":0"
                pending.append(
                    (
                        index,
                        candidate_n,
                        key(group),
                        state_key,
                        input_key,
                        target_key,
                        family,
                        row["source"],
                        row["question"]["type"],
                        int(blocked),
                    )
                )
                index += 1
            connection.executemany(
                "INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?)", pending
            )
            pending.clear()
        connection.commit()
        print(json.dumps({"file": item["file"], "indexed": index}), flush=True)
    for field in ("case_key", "state_key", "input_key"):
        check()
        connection.execute(f"CREATE INDEX by_{field} ON items({field})")
    connection.execute(
        "CREATE TABLE decisions AS SELECT input_key,MIN(n) AS representative,COUNT(*) AS copies,COUNT(DISTINCT target_key) AS targets FROM items GROUP BY input_key"
    )
    connection.execute("CREATE UNIQUE INDEX decision_key ON decisions(input_key)")
    counts.update(
        {
            "indexed_questions": index,
            "unique_exact_decisions": connection.execute(
                "SELECT COUNT(*) FROM decisions"
            ).fetchone()[0],
            "conflicting_exact_decisions": connection.execute(
                "SELECT COUNT(*) FROM decisions WHERE targets>1"
            ).fetchone()[0],
        }
    )
    components = group_components(connection, index)
    blocked_components = set()
    for (n,) in connection.execute(
        "SELECT i.n FROM items i JOIN decisions d ON i.input_key=d.input_key WHERE i.blocked=1 OR d.targets>1"
    ):
        blocked_components.add(components.root(n))
    counts["quarantined_case_components"] = len(blocked_components)
    counts["unique_case_components"] = sum(
        components.root(n) == n for n in range(index)
    )
    connection.execute(
        "CREATE TABLE disposition(n INTEGER PRIMARY KEY,component INTEGER,eligible_exact INTEGER)"
    )
    pending = []
    for n, representative, targets in connection.execute(
        "SELECT i.n,d.representative,d.targets FROM items i JOIN decisions d ON i.input_key=d.input_key ORDER BY i.n"
    ):
        component = components.root(n)
        eligible = (
            component not in blocked_components and n == representative and targets == 1
        )
        counts["remaining_exact_candidates"] += eligible
        counts["quarantined_group_questions"] += component in blocked_components
        pending.append((n, component, int(eligible)))
        if len(pending) >= 10000:
            check()
            connection.executemany("INSERT INTO disposition VALUES(?,?,?)", pending)
            pending.clear()
    connection.executemany("INSERT INTO disposition VALUES(?,?,?)", pending)
    connection.commit()
    connection.close()
    source = Path(__file__).read_bytes()
    (root / "audit_scale.py").write_bytes(source)
    result = {
        "status": "EXACT_AUDIT_ONLY_NOT_ADMITTED",
        "candidate_manifest_sha256": complete["manifest_sha256"],
        "benchmark_sha256": digest_file(args.benchmark),
        "audit_source_sha256": hashlib.sha256(source).hexdigest(),
        "counts": dict(counts),
        "families": dict(families),
        "seconds": time.monotonic() - started,
        "limitations": [
            "No near-duplicate or translation equivalence claim",
            "Semantic/source-terms admission and exact Inkling tokens remain required",
            "Dispositions select only exact deduplicated, conflict/group-screened candidates",
            "Probability conflict keys use six decimal places",
            "Original candidate row ordering retained through items.n; rejected canonical-option rows omitted",
        ],
    }
    (root / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    (root / "COMPLETE.json").write_text(
        json.dumps(
            {
                "audit_sha256": digest_file(root / "audit.json"),
                "sqlite_sha256": digest_file(root / "audit.sqlite"),
            }
        )
        + "\n"
    )
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
