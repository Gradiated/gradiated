"""Verify supported public procedural targets against independent state oracles."""

import argparse
import collections
import hashlib
import json
import time
from pathlib import Path

from prepare_scale import PINS, digest_file
from semantic_oracles import ORACLES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=900)
    args = parser.parse_args()
    import pyarrow.parquet as pq

    started = time.monotonic()
    deadline = started + args.seconds
    root = args.run_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("retain previous semantic audit; output must be empty")
    sources = json.loads(args.source_manifest.read_text())
    source_hashes = {}
    for name in (
        "audit_semantics.py",
        "semantic_oracles.py",
        "prepare_scale.py",
        "data.py",
        "scale_data.py",
        "original_data.py",
    ):
        content = Path(__file__).with_name(name).read_bytes()
        (root / name).write_bytes(content)
        source_hashes[name] = hashlib.sha256(content).hexdigest()
    counts = collections.Counter()
    families = collections.defaultdict(collections.Counter)
    mismatches = []
    wording = collections.Counter()
    for source in sources:
        if (
            source["repo"] != "tasksource/procedural-typed-decisions"
            or source["revision"] != PINS[source["repo"]]
        ):
            raise ValueError("unreviewed semantic source")
        if digest_file(source["path"]) != source["sha256"]:
            raise ValueError("source hash mismatch")
        for batch in pq.ParquetFile(source["path"]).iter_batches(batch_size=2048):
            if time.monotonic() >= deadline:
                raise TimeoutError("semantic audit deadline")
            for row in batch.to_pylist():
                counts["source_states"] += 1
                family = row["task"]
                if family not in ORACLES:
                    continue
                stats = families[family]
                stats["states"] += 1
                try:
                    expected = ORACLES[family](json.loads(row["state"]))
                except (ValueError, TypeError, KeyError, ZeroDivisionError):
                    stats["uncovered_states"] += 1
                    continue
                questions = json.loads(row["questions"])
                answers = json.loads(row["answers"])
                for qid, value in expected.items():
                    if qid not in answers:
                        continue
                    q = questions[qid]
                    answer = answers[qid]
                    if family == "partial_observation_calibration":
                        wording[q["instructions"]] += 1
                    stats["checked_questions"] += 1
                    if q["type"] == "noul":
                        delta = abs(float(answer["noul"]) - value)
                    else:
                        probs = answer["probabilities"]
                        delta = (
                            max(
                                abs(prob - float(label == value))
                                for label, prob in probs.items()
                            )
                            if value in probs
                            else 1
                        )
                    if delta > 1e-6:
                        stats["mismatches"] += 1
                        if len(mismatches) < 30:
                            mismatches.append(
                                {
                                    "id": row["id"],
                                    "question": qid,
                                    "expected": value,
                                    "answer": answer,
                                    "max_probability_delta": delta,
                                }
                            )
        print(
            json.dumps(
                {
                    "file": source["file"],
                    "families": {key: dict(value) for key, value in families.items()},
                }
            ),
            flush=True,
        )
    result = {
        "status": "SEMANTIC_AUDIT_ONLY_NOT_ADMITTED",
        "source_manifest_sha256": digest_file(args.source_manifest),
        "executable_sources_sha256": source_hashes,
        "counts": dict(counts),
        "families": {key: dict(value) for key, value in families.items()},
        "mismatch_examples": mismatches,
        "sensor_question_wording": dict(wording),
        "seconds": time.monotonic() - started,
        "limitation": "Only three independent state oracles; numerical agreement does not certify question wording or other families",
    }
    (root / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    (root / "COMPLETE.json").write_text(
        json.dumps({"audit_sha256": digest_file(root / "audit.json")}) + "\n"
    )
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
