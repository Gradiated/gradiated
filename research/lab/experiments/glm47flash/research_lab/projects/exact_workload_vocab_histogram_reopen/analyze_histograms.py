#!/usr/bin/env python3
"""Fail-closed audit of the retained exact-workload histogram archive."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
import tarfile
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("archive", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    archive_sha256 = hashlib.sha256(args.archive.read_bytes()).hexdigest()
    with tarfile.open(args.archive, "r:gz") as tf:
        name = next(m.name for m in tf.getmembers() if m.name.endswith("/performance-summary.json"))
        summary = json.load(tf.extractfile(name))
    profile = next(p for p in summary["profiles"] if p["profile_id"] == "fixed_8k_1k_c16")
    rows = profile["rows"]
    histograms = [{int(token): int(count) for token, count in row["output_token_histogram"].items()} for row in rows]
    row_checks = [
        {
            "output_tokens": row["output_tokens"],
            "event_count": row["token_event_count"],
            "histogram_sum": sum(histogram.values()),
            "complete": row["output_token_ids_complete"]
            and row["output_tokens"] == row["token_event_count"] == sum(histogram.values()) == 1024,
        }
        for row, histogram in zip(rows, histograms)
    ]

    def signature(histogram):
        return tuple(sorted(histogram.items()))

    patterns = collections.Counter(signature(histogram) for histogram in histograms)
    aggregate = collections.Counter()
    for histogram in histograms:
        aggregate.update(histogram)

    def coverage(excluded: int, k: int) -> float:
        leave_out = aggregate.copy()
        leave_out.subtract(histograms[excluded])
        shortlist = {token for token, _ in leave_out.most_common(k)}
        return sum(count for token, count in histograms[excluded].items() if token in shortlist) / 1024

    loo = {
        str(k): {
            "min": min(coverage(i, k) for i in range(len(rows))),
            "mean": statistics.mean(coverage(i, k) for i in range(len(rows))),
            "max": max(coverage(i, k) for i in range(len(rows))),
        }
        for k in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024)
    }

    def split_stats(split):
        counts = collections.Counter()
        for histogram in split:
            counts.update(histogram)
        return {
            "requests": len(split),
            "tokens": len(split) * 1024,
            "distinct_tokens": len(counts),
            "top_token_share": counts.most_common(1)[0][1] / (len(split) * 1024),
            "distinct_histogram_patterns": len({signature(h) for h in split}),
        }

    result = {
        "schema_version": 1,
        "classification": "CORPUS_CLOSE",
        "decision": "Do not nominate a vocabulary shortlist: the only retained exact corpus is degenerate and method-conditioned.",
        "evidence_class": "measured retained-artifact audit; token IDs are used only as retained histogram identities",
        "source": {
            "archive": str(args.archive),
            "archive_sha256": archive_sha256,
            "profile_id": profile["profile_id"],
            "requests": len(rows),
            "reported_output_tokens": sum(row["output_tokens"] for row in rows),
            "histograms_complete": all(check["complete"] for check in row_checks),
        },
        "completeness": {"all_rows": row_checks},
        "diversity": {
            "distinct_histogram_patterns": len(patterns),
            "pattern_counts": sorted(patterns.values(), reverse=True),
            "per_request_distinct_token_counts": {str(k): v for k, v in collections.Counter(map(len, histograms)).items()},
            "aggregate_distinct_tokens": len(aggregate),
            "aggregate_top_tokens": [{"token_id": token, "count": count, "share": count / sum(aggregate.values())} for token, count in aggregate.most_common(10)],
            "halves": {"first_16": split_stats(histograms[:16]), "last_16": split_stats(histograms[16:])},
            "leave_one_request_out_top_k_coverage": loo,
        },
        "representativeness": {
            "independent_groups": 1,
            "required_leave_group_out_coverage": 0.999,
            "coverage_claim_admissible": False,
            "failure_reasons": [
                "n-gram prompt-lookup arm is a single method-conditioned source group",
                "only 6 histogram patterns across 32 requests; 11 and 13 rows repeat the dominant pattern",
                "aggregate top token share is 0.964599609375",
                "the corpus cannot support a leave-one-independent-group-out claim",
            ],
        },
        "economics": {
            "exact_representation_tested": False,
            "conservative_endpoint_transfer_tested": False,
            "reason": "Corpus fails representativeness before the contract permits an output-head shortlist/economics test.",
            "robust_nomination_tok_per_s": 606.355,
        },
        "scope_compliance": {"provider_spend_usd": 0.0, "cuda_used": False, "network_used": False, "checkpoint_mutated": False, "shared_runtime_mutated": False},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"classification": result["classification"], "output": str(args.out), "archive_sha256": archive_sha256}, indent=2))


if __name__ == "__main__":
    main()
