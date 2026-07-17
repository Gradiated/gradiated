#!/usr/bin/env python3
"""Compare the Cycle-135 stock histogram groups with the prior n-gram group."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
import tarfile
from pathlib import Path


def load_profiles(archive: Path):
    with tarfile.open(archive, "r:gz") as tf:
        member = next(m for m in tf.getmembers() if m.name.endswith("/performance-summary.json"))
        summary = json.load(tf.extractfile(member))
    profiles = []
    for profile in summary["profiles"]:
        rows = []
        for row in profile["rows"]:
            histogram = {int(token): int(count) for token, count in row["output_token_histogram"].items()}
            rows.append({"histogram": histogram, "stream_sha256": row["stream_sha256"], "complete": row["output_token_ids_complete"] and sum(histogram.values()) == row["output_tokens"] == row["token_event_count"] == 1024})
        profiles.append((profile["profile_id"], rows))
    return profiles


def aggregate(rows):
    result = collections.Counter()
    for row in rows:
        result.update(row["histogram"])
    return result


def coverage(held_out, training, shortlist_size):
    shortlist = {token for token, _ in aggregate(training).most_common(shortlist_size)}
    total = sum(sum(row["histogram"].values()) for row in held_out)
    covered = sum(sum(count for token, count in row["histogram"].items() if token in shortlist) for row in held_out)
    return covered / total


def profile_stats(rows):
    counts = aggregate(rows)
    return {
        "requests": len(rows),
        "complete_requests": sum(row["complete"] for row in rows),
        "distinct_stream_hashes": len({row["stream_sha256"] for row in rows}),
        "distinct_histogram_patterns": len({tuple(sorted(row["histogram"].items())) for row in rows}),
        "distinct_token_ids": len(counts),
        "per_request_distinct_token_counts": {str(k): v for k, v in collections.Counter(len(row["histogram"]) for row in rows).items()},
        "top_token": {"id": counts.most_common(1)[0][0], "count": counts.most_common(1)[0][1], "share": counts.most_common(1)[0][1] / (len(rows) * 1024)},
        "top_tokens": [{"id": token, "count": count, "share": count / (len(rows) * 1024)} for token, count in counts.most_common(8)],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", type=Path, required=True)
    ap.add_argument("--ngram", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    stock = load_profiles(args.stock)
    ngram = load_profiles(args.ngram)
    stock_rows = [row for _, rows in stock for row in rows]
    ngram_rows = [row for _, rows in ngram for row in rows]
    sizes = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024)
    held_out = {}
    for index, (name, rows) in enumerate(stock):
        training = [row for j, (_, group) in enumerate(stock) if j != index for row in group]
        held_out[name] = {str(k): coverage(rows, training, k) for k in sizes}
    all_stock = aggregate(stock_rows)
    all_ngram = aggregate(ngram_rows)
    result = {
        "schema_version": 2,
        "classification": "CORPUS_CLOSE",
        "decision": "The five stock concurrency profiles add method-free identities but not independent target-usage groups; the corpus remains too concentrated and under-grouped for shortlist nomination.",
        "evidence_class": "measured retained-artifact comparison; stream hashes are counted only as identity, never as semantic diversity",
        "archives": {
            "stock": {"path": str(args.stock), "sha256": hashlib.sha256(args.stock.read_bytes()).hexdigest(), "profiles": [name for name, _ in stock], "requests": len(stock_rows), "output_tokens": len(stock_rows) * 1024, "profile_stats": {name: profile_stats(rows) for name, rows in stock}},
            "ngram": {"path": str(args.ngram), "sha256": hashlib.sha256(args.ngram.read_bytes()).hexdigest(), "profiles": [name for name, _ in ngram], "requests": len(ngram_rows), "output_tokens": len(ngram_rows) * 1024, "profile_stats": {name: profile_stats(rows) for name, rows in ngram}},
        },
        "comparison": {
            "stock_dominant_token_share": all_stock.most_common(1)[0][1] / (len(stock_rows) * 1024),
            "ngram_dominant_token_share": all_ngram.most_common(1)[0][1] / (len(ngram_rows) * 1024),
            "stock_distinct_token_ids": len(all_stock),
            "ngram_distinct_token_ids": len(all_ngram),
            "shared_top_token_ids": [token for token, _ in all_stock.most_common(8) if token in all_ngram],
            "stock_profile_leave_one_out_coverage": held_out,
            "stock_profile_leave_one_out_min_at_99_9": min(held_out[name][str(k)] for name in held_out for k in sizes if held_out[name][str(k)] >= 0.999) if any(held_out[name][str(k)] >= 0.999 for name in held_out for k in sizes) else None,
        },
        "representativeness": {
            "independent_target_usage_groups": 1,
            "required_independent_groups": ">=2; concurrency is a serving condition, not a usage split",
            "unique_stock_stream_hashes": len({row["stream_sha256"] for row in stock_rows}),
            "interpretation": "All stock profiles use the same fixed 8K/1K synthetic workload and differ by concurrency/placement schedule. Distinct stream hashes therefore do not establish distinct prompts, semantic outputs, or target-usage groups. The n-gram archive is an additional method-conditioned group, not a second usage sample.",
            "failure_reasons": [
                "stock profile groups are concurrency repetitions of one fixed synthetic workload",
                "dominant token 154822 remains 93.06% across stock and 96.46% in n-gram",
                "profile-held-out coverage reaches 0.999 only at larger shortlists and is not independent-group coverage",
                "no exact source-bound fallback representation or semantic diversity evidence exists",
            ],
        },
        "economics": {"tested": False, "reason": "Representativeness fails before exact representation and endpoint-transfer economics.", "robust_gate_tok_per_s": 606.355, "new_stock_control_mean_tok_per_s": 602.157121, "required_control_ratio": 1.03},
        "scope_compliance": {"provider_spend_usd": 0.0, "cuda_used": False, "network_used": False, "checkpoint_mutated": False, "shared_runtime_mutated": False},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"classification": result["classification"], "output": str(args.out), "stock_requests": len(stock_rows), "independent_target_usage_groups": 1}, indent=2))


if __name__ == "__main__":
    main()
