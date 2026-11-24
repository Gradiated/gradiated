"""Paired exact-match estimates with block-bootstrap confidence intervals."""
import argparse
from collections import defaultdict
import gzip
import json
from pathlib import Path

import numpy as np


def load(path):
    opener = gzip.open if path.suffix == ".gz" else open
    result = {}
    with opener(path, "rt") as rows:
        for row in map(json.loads, rows):
            uid = row["uid"]
            if uid in result:
                raise ValueError(f"Duplicate conflict {uid} in {path}")
            result[uid] = row
    return result


def compare(frozen, control, adapted, group):
    if not frozen or not (frozen.keys() == control.keys() == adapted.keys()):
        raise ValueError("Expected one prediction per frozen conflict from each model")
    blocks = defaultdict(lambda: [0, 0])
    improved = regressed = base_correct = new_correct = 0
    for uid, row in sorted(frozen.items()):
        a, b = control[uid], adapted[uid]
        for pred in (a, b):
            if (pred["merge"], pred["repo"]) != (row["merge"], row["repo"]):
                raise ValueError(f"Inconsistent provenance for {uid}")
            if type(pred["correct"]) is not bool:
                raise ValueError(f"Expected a boolean outcome for {uid}")
        base_correct += a["correct"]
        new_correct += b["correct"]
        improved += b["correct"] and not a["correct"]
        regressed += a["correct"] and not b["correct"]
        key = (row["repo"], row["merge"]) if group == "merge" else row["repo"]
        blocks[key][0] += int(b["correct"]) - int(a["correct"])
        blocks[key][1] += 1
    if len(blocks) < 2:
        raise ValueError("Need at least two independent sampling units")
    counts = np.array(list(blocks.values()))
    rng = np.random.default_rng(8493)
    replicates = []
    for _ in range(100):
        sample = rng.integers(len(counts), size=(100, len(counts)))
        totals = counts[sample].sum(axis=1)
        replicates.extend(totals[:, 0] / totals[:, 1])
    return dict(conflicts=len(frozen), grouping=group, groups=len(blocks),
                control_correct=base_correct, adapted_correct=new_correct,
                gained=improved, lost=regressed, delta=(improved-regressed)/len(frozen),
                delta_ci95=np.quantile(replicates, [0.025, 0.975]).tolist())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("frozen", "control", "adapted"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--group", choices=("merge", "repo"), required=True)
    args = parser.parse_args()
    print(json.dumps(compare(load(args.frozen), load(args.control), load(args.adapted), args.group), indent=2))
