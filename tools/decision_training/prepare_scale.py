"""Build traceable candidate shards; a separate admission gate must approve training."""

import argparse
import collections
import hashlib
import json
from pathlib import Path

from data import normalize_tasksource, text
from scale_data import curate_candidate, normalize_procedural, normalize_verqen

PINS = {
    "tasksource/tasksource-jev-typed-decisions": "8df2e5c9a33f19a2c2b8febf291c3acb0a91a8a8",
    "tasksource/procedural-typed-decisions": "05ca1d0388f57461a634a7caed67145d28e2eca7",
    "zorqelis-ai/verqen-decisions": "c21319ea8c28ad5103be185aea1f2e4323570bcd",
}
TERMS = {
    "apache-2.0",
    "mit",
    "cc0-1.0",
    "cc-by-3.0",
    "cc-by-4.0",
    "cc-by-sa-3.0",
    "cc-by-sa-4.0",
    "afl-3.0",
}


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def candidates(raw, repo):
    if repo == "tasksource/tasksource-jev-typed-decisions":
        yield None, lambda: normalize_tasksource(raw)
    elif repo == "zorqelis-ai/verqen-decisions":
        questions = raw["questions"]
        for index, question in enumerate(questions):
            yield (
                index,
                lambda q=question, i=index: next(
                    normalize_verqen({**raw, "questions": [q]}, question_offset=i)
                ),
            )
    elif repo == "tasksource/procedural-typed-decisions":
        questions, answers = json.loads(raw["questions"]), json.loads(raw["answers"])
        if set(questions) != set(answers):
            raise ValueError("native question/answer IDs differ")
        for key, question in questions.items():
            yield (
                key,
                lambda k=key, q=question: next(
                    normalize_procedural(
                        {
                            **raw,
                            "questions": {k: q},
                            "answers": {k: answers[k]},
                        }
                    )
                ),
            )
    else:
        raise ValueError("unsupported source")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", action="append", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    import pyarrow as pa
    import pyarrow.parquet as pq

    root = args.run_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("candidate output must be empty; retain previous generations")
    sources = [
        item for path in args.source_manifest for item in json.loads(path.read_text())
    ]
    for item in sources:
        path = Path(item["path"])
        if PINS.get(item["repo"]) != item["revision"]:
            raise ValueError("unreviewed source revision")
        if path.stat().st_size != item["bytes"] or digest_file(path) != item["sha256"]:
            raise ValueError("source bytes differ from acquisition manifest")
        if "/train" not in item["file"]:
            raise ValueError("only recorded training files are allowed")
    source_dir = root / "source"
    source_dir.mkdir()
    builder = {}
    for name in ("prepare_scale.py", "scale_data.py", "data.py", "data_sources.json"):
        content = Path(__file__).with_name(name).read_bytes()
        (source_dir / name).write_bytes(content)
        builder[name] = hashlib.sha256(content).hexdigest()
    counts, rejects, output_files = collections.Counter(), collections.Counter(), []
    pending = []

    def flush():
        if not pending:
            return
        path = root / f"candidate-{len(output_files):05d}.parquet"
        pq.write_table(pa.Table.from_pylist(pending), path, compression="zstd")
        output_files.append(
            {"file": path.name, "rows": len(pending), "sha256": digest_file(path)}
        )
        pending.clear()

    with (root / "rejections.jsonl").open("w") as rejected:
        for item in sources:
            repo = item["repo"]
            row_index = 0
            for batch in pq.ParquetFile(item["path"]).iter_batches(batch_size=2048):
                for raw in batch.to_pylist():
                    counts["source_rows"] += 1
                    try:
                        for question_id, convert in candidates(raw, repo):
                            try:
                                row = convert()
                                if row is None:
                                    raise ValueError(
                                        "existing licence/provenance filter"
                                    )
                                row = curate_candidate(row)
                                if repo.endswith("verqen-decisions") and not all(
                                    term in TERMS
                                    for term in row["license"].lower().split("/")
                                ):
                                    raise ValueError("unreviewed source licence")
                            except (ValueError, TypeError, KeyError) as error:
                                reason = str(error)
                                rejects[reason] += 1
                                rejected.write(
                                    json.dumps(
                                        {
                                            "repo": repo,
                                            "file": item["file"],
                                            "row": row_index,
                                            "question": question_id,
                                            "reason": reason,
                                        }
                                    )
                                    + "\n"
                                )
                                continue
                            row["provenance"] = {
                                "repo": repo,
                                "revision": item["revision"],
                                "file": item["file"],
                                "row": row_index,
                                "question": question_id,
                            }
                            row.setdefault("family_group", row["source_task"].lower())
                            counts[repo] += 1
                            counts["candidate_questions"] += 1
                            counts["wording_repairs"] += int(bool(row.get("curation")))
                            pending.append(
                                {
                                    "id": row["id"],
                                    "source": repo,
                                    "source_task": row["source_task"],
                                    "family_group": row["family_group"],
                                    "group": row["group"],
                                    "license": row["license"],
                                    "kind": row["question"]["type"],
                                    "state_sha256": hashlib.sha256(
                                        text(row["state"]).encode()
                                    ).hexdigest(),
                                    "record_json": json.dumps(row, ensure_ascii=False),
                                }
                            )
                            if len(pending) >= 25000:
                                flush()
                    except (ValueError, TypeError, KeyError) as error:
                        raise ValueError(
                            f"invalid source row {repo}/{item['file']}:{row_index}"
                        ) from error
                    row_index += 1
            print(
                json.dumps({"file_complete": item["file"], "counts": dict(counts)}),
                flush=True,
            )
    flush()
    manifest = {
        "status": "CANDIDATES_ONLY_NOT_ADMITTED_FOR_TRAINING",
        "normalization_version": "canonical-v2-zero-groups-preserved",
        "curation_version": "sensor-event-probability-wording-v1",
        "sources": sources,
        "builder": builder,
        "counts": dict(counts),
        "rejections": dict(rejects),
        "files": output_files,
        "remaining_gates": [
            "semantic source admission",
            "protected benchmark/group exclusion",
            "cross-source exact/near dedup and conflicting-target quarantine",
            "source-family/scenario holdouts",
            "exact Inkling token audit",
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (root / "COMPLETE.json").write_text(
        json.dumps({"manifest_sha256": digest_file(root / "manifest.json")}) + "\n"
    )


if __name__ == "__main__":
    main()
