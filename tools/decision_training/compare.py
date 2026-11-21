"""Compare frozen public predictions with paired uncertainty and fair calibration."""

import argparse
import json
import math
import random
from pathlib import Path

from benchmark_identity import verify_benchmark
from data import read_jsonl

TEMPERATURES = (0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0)


def probabilities(logits, temperature):
    values = [x / temperature for x in logits]
    maximum = max(values)
    values = [math.exp(x - maximum) for x in values]
    total = sum(values)
    return [x / total for x in values]


def fit_temperature(dev):
    def loss(temperature):
        total = 0
        for row in dev:
            scaled = [z / temperature for z in row["logits"]]
            maximum = max(scaled)
            log_sum = maximum + math.log(sum(math.exp(z - maximum) for z in scaled))
            total += sum(y * (log_sum - z) for y, z in zip(row["target"], scaled))
        return total / len(dev)

    return min(TEMPERATURES, key=loss)


def metrics(rows, temperature=None):
    bins = [[] for _ in range(10)]
    correct, brier = [], []
    for row in rows:
        labels = list(row["probs"])
        values = (
            list(row["probs"].values())
            if temperature is None
            else probabilities(row["logits"], temperature)
        )
        predicted = min(labels, key=lambda label: (-values[labels.index(label)], label))
        gold = str(row["expected"])
        hit = predicted == gold
        confidence = max(values)
        correct.append(hit)
        brier.append(
            sum((p - (label == gold)) ** 2 for label, p in zip(labels, values))
        )
        bins[min(int(confidence * 10), 9)].append((confidence, hit))
    count = len(rows)
    accuracy = sum(correct) / count
    ece = sum(abs(sum(p - y for p, y in bucket)) for bucket in bins) / count
    z = 1.959963984540054
    center = (accuracy + z * z / (2 * count)) / (1 + z * z / count)
    radius = (
        z
        * math.sqrt(accuracy * (1 - accuracy) / count + z * z / (4 * count * count))
        / (1 + z * z / count)
    )
    return {
        "n": count,
        "accuracy": accuracy,
        "accuracy_wilson_95": [center - radius, center + radius],
        "brier": sum(brier) / count,
        "ece": ece,
        "temperature": temperature or 1.0,
    }


def paired_accuracy(control, candidate, seed=20261120, resamples=10000):
    left = {r["id"]: r for r in control}
    right = {r["id"]: r for r in candidate}
    if (
        len(left) != len(control)
        or len(right) != len(candidate)
        or left.keys() != right.keys()
    ):
        raise ValueError("paired evaluation requires unique, identical item ids")
    differences = [
        int(right[key]["correct"]) - int(left[key]["correct"]) for key in sorted(left)
    ]
    wins, losses = differences.count(1), differences.count(-1)
    discordant = wins + losses
    probability = (
        min(
            1.0,
            2
            * sum(math.comb(discordant, k) for k in range(min(wins, losses) + 1))
            / 2**discordant,
        )
        if discordant
        else 1.0
    )
    rng = random.Random(seed)
    samples = sorted(
        sum(rng.choices(differences, k=len(differences))) / len(differences)
        for _ in range(resamples)
    )
    return {
        "accuracy_delta": sum(differences) / len(differences),
        "paired_bootstrap_95": [
            samples[int(resamples * 0.025)],
            samples[int(resamples * 0.975)],
        ],
        "candidate_only_correct": wins,
        "control_only_correct": losses,
        "mcnemar_exact_two_sided_p": probability,
        "seed": seed,
        "resamples": resamples,
    }


def validate_benchmark_predictions(predictions, benchmark):
    gold = {row["id"]: row for row in benchmark}
    if (
        len(predictions) != len(gold)
        or len({row["id"] for row in predictions}) != len(gold)
        or {row["id"] for row in predictions} != set(gold)
    ):
        raise ValueError("prediction set is not the complete frozen benchmark")
    for row in predictions:
        task = gold[row["id"]]
        if (
            str(row["expected"]) != str(task["expected"])
            or list(row["probs"]) != (task["labels"])
        ):
            raise ValueError(
                "prediction labels or expected answers differ from frozen benchmark"
            )
        predicted = min(task["labels"], key=lambda label: (-row["probs"][label], label))
        if row["correct"] is not (predicted == str(task["expected"])):
            raise ValueError("stored correctness differs from frozen benchmark scoring")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--linden-results", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--benchmark",
        type=Path,
        help="Explicit frozen benchmark when collection does not include data/jevbench-231.jsonl",
    )
    args = parser.parse_args()
    output = args.run_dir / "outputs"
    control = read_jsonl(output / "baseline-jevbench.jsonl")
    candidate = read_jsonl(output / "trained-jevbench.jsonl")
    benchmark_path = args.benchmark or args.run_dir / "data" / "jevbench-231.jsonl"
    verify_benchmark(benchmark_path)
    benchmark = read_jsonl(benchmark_path)
    validate_benchmark_predictions(control, benchmark)
    validate_benchmark_predictions(candidate, benchmark)
    base_temp = fit_temperature(read_jsonl(output / "baseline-dev.jsonl"))
    trained_temp = fit_temperature(read_jsonl(output / "trained-dev.jsonl"))
    report = {
        "scope": "JevBench frozen 231 public tasks; not an official leaderboard rank",
        "baseline_raw": metrics(control),
        "baseline_dev_calibrated": metrics(control, base_temp),
        "trained_raw": metrics(candidate, 1.0),
        "trained_dev_calibrated": metrics(candidate, trained_temp),
        "paired_vs_baseline": paired_accuracy(control, candidate),
        "calibration_selection": "Each model fits the same temperature grid on its own source-held-out dev predictions; no benchmark labels used.",
    }
    if args.linden_results:
        rows = read_jsonl(args.linden_results)
        gold = {r["id"]: r["expected"] for r in control}
        linden = [
            {**r, "id": r["task_id"], "expected": gold[r["task_id"]]} for r in rows
        ]
        if any(not r.get("valid") for r in linden):
            raise ValueError("Linden reference has invalid probability outputs")
        report["linden_native"] = metrics(linden)
        report["paired_vs_linden"] = paired_accuracy(linden, candidate)
    destination = args.output or output / "comparison.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
