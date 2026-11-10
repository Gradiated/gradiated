"""Merge evaluation shards and score them with the Decision Index kit.

    python -m gdecide.score --suite SUITE_DIR --run RUN_DIR [--sample sample-ids.json] [--compare OTHER_RUN_DIR]

With ``--sample`` the suite is restricted to the sampled run ids, so coverage and chance are computed on the
sample instead of counting every unsampled row as unanswered. Writes ``scores.json`` into the run directory and
prints the index, the five areas and every benchmark's skill (and the paired difference with ``--compare``).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def merged_results(run: Path) -> Path:
    target = run / "results.jsonl"
    seen: dict[str, str] = {}
    for shard in sorted(run.glob("results-*.jsonl")):
        for line in shard.read_text().splitlines():
            try:
                seen[json.loads(line)["run_id"]] = line
            except (json.JSONDecodeError, KeyError):
                continue
    target.write_text("".join(v + "\n" for v in seen.values()))
    return target


def score(suite_dir: str, run: Path, sample: set[str] | None, edition: str = "0.3") -> dict:
    from decision_index.pipeline import score_run
    from decision_index.suite.io import Suite

    class SampledSuite(Suite):
        def rows(self, apply_exclusions=False):
            for row in super().rows(apply_exclusions):
                if sample is None or row["_evaluation"]["run_id"] in sample:
                    yield row

    suite = SampledSuite(suite_dir, edition)
    out = run / ("scored-sample" if sample else "scored")
    score_run(suite, merged_results(run), "gradiated-decide", out)
    return json.loads((out / "index.json").read_text())


def summary(index: dict) -> dict:
    return {
        "index": index["index"],
        "areas": {a["id"]: round(a["skill"], 4) for a in index["areas"]},
        "benchmarks": {k: round(v["skill"], 4) for k, v in index["benchmarks"].items() if v.get("in_index")},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--sample")
    parser.add_argument("--compare")
    args = parser.parse_args()
    sample = set(json.loads(Path(args.sample).read_text())) if args.sample else None
    mine = summary(score(args.suite, Path(args.run), sample))
    report = {"run": args.run, **mine}
    if args.compare:
        other = summary(score(args.suite, Path(args.compare), sample))
        report["delta_index"] = round(mine["index"] - other["index"], 3)
        report["delta_areas"] = {k: round(v - other["areas"][k], 4) for k, v in mine["areas"].items()}
        report["delta_benchmarks"] = {k: round(v - other["benchmarks"].get(k, 0), 4) for k, v in mine["benchmarks"].items()}
    (Path(args.run) / "gdecide-score.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
