#!/usr/bin/env python3
"""Analyze an A/B/A/.../B/A sequence with bracketed paired effects."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path


def percentile(values: list[float], fraction: float) -> float:
    rows = sorted(values)
    return rows[round((len(rows) - 1) * fraction)]


def analyze(sequence: list[dict], identity: str, resamples: int = 10_000) -> dict:
    if len(sequence) < 3 or len(sequence) % 2 == 0:
        raise ValueError("sequence must be odd-length control/candidate/.../control")
    if any(row.get("role") != ("control" if index % 2 == 0 else "candidate") for index, row in enumerate(sequence)):
        raise ValueError("sequence must alternate control and candidate, starting and ending with control")
    pairs = []
    for index in range(1, len(sequence), 2):
        before = float(sequence[index - 1]["value"])
        candidate = float(sequence[index]["value"])
        after = float(sequence[index + 1]["value"])
        bracket = statistics.fmean((before, after))
        pairs.append({
            "candidate_label": sequence[index]["label"],
            "control_before_label": sequence[index - 1]["label"],
            "control_after_label": sequence[index + 1]["label"],
            "control_bracket_mean": bracket,
            "candidate_value": candidate,
            "relative_effect": candidate / bracket - 1.0,
        })
    effects = [row["relative_effect"] for row in pairs]
    seed = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], "big")
    generator = random.Random(seed)
    enough_repetitions = len(effects) >= 3
    bootstrapped = [] if not enough_repetitions else [
        statistics.median(generator.choices(effects, k=len(effects)))
        for _ in range(resamples)
    ]
    return {
        "schema_version": 1,
        "identity": identity,
        "seed": seed,
        "resamples": resamples,
        "sequence": sequence,
        "pairs": pairs,
        "independent_candidate_repetitions": len(effects),
        "paired_effect_median": statistics.median(effects),
        "paired_effect_mean": statistics.fmean(effects),
        "paired_percentile_bootstrap_95": None if not enough_repetitions else {
            "lower": percentile(bootstrapped, 0.025),
            "upper": percentile(bootstrapped, 0.975),
        },
        "precision_status": "interval_reported_three_or_more_candidate_repetitions" if enough_repetitions else "descriptive_only_fewer_than_three_candidate_repetitions",
        "claim_limit": "descriptive bracketed same-session effect; fewer than three independent candidate repetitions do not support interval or significance language; validity still requires matched correctness, quality, SLO, workload, and allocation identity",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--resamples", type=int, default=10_000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sequence = json.loads(args.input.read_text())["sequence"]
    args.output.write_text(
        json.dumps(analyze(sequence, args.identity, args.resamples), indent=2, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
