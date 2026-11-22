"""Reconstruct and check the Experiment 13 context-cost tables from pinned traces."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import tarfile


PROFILE_RUN = "attention-profile-rtl-20261117T104256Z"
BASELINE_RUN = "attention-exp-pair-v2-rtl-20261117T230104Z"
CLOCK_MHZ = 50
FIXED_SCORED_CYCLES = 37_643
SCORING_CYCLES = 1_681
FIXED_WITHOUT_SCORING = FIXED_SCORED_CYCLES - SCORING_CYCLES
SAVED_DIGITS_PER_DIVISION = 24

# These pins are from the archived runs' artifact lists.
ARTIFACTS = (
    (PROFILE_RUN, "replay.tar.gz", "3b2d9433951827dce637add34287f3959447790257820a8fbe44d8f19aa49f2b"),
    (BASELINE_RUN, "simulation.tar.gz", "5c66c50778943d4601f4bbc8d93741522dada0d333b558c6f23e31adf3e2cff9"),
    (BASELINE_RUN, "model-results.json", "af8073c6f797d4881dd48a8a65f63d4ed1133cdca3b352a1e69b4a082c6cb974"),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verified_artifact(repo, run_id, filename, digest):
    record = repo / "hardware/research/inference/results" / run_id / "run.json"
    artifacts = json.loads(record.read_text(encoding="utf-8"))["artifacts"]
    matches = [item for item in artifacts if Path(item["path"]).name == filename]
    require(len(matches) == 1, f"{run_id}: expected one entry for {filename}")
    item = matches[0]
    require(item["sha256"] == digest, f"{run_id}: run record pin differs for {filename}")
    path = repo / item["path"]
    data = path.read_bytes()
    require(len(data) == item["bytes"] and hashlib.sha256(data).hexdigest() == digest,
            f"{path}: archive size or SHA-256 differs")
    return path


def trace_rows(archive, member):
    with archive.extractfile(member) as stream:
        return [line.split() for line in stream.read().decode("ascii").splitlines()]


def ms(cycles):
    return f"{cycles / (CLOCK_MHZ * 1000):.5f}"


def position_rows(case, profile, baseline, total_positions):
    old_rows = trace_rows(profile, f"replay/cases/{case}/attention-profile.txt")
    pair_rows = trace_rows(baseline, f"replay/{case}/attention-pairs.txt")
    cache_rows = trace_rows(baseline, f"replay/{case}/overlap-profile.txt")
    events = trace_rows(baseline, f"replay/{case}/attention-events.txt")
    require(len(old_rows) == len(pair_rows) == len(cache_rows) == total_positions,
            f"{case}: trace lengths differ from the recorded request depth")

    rows = []
    probability_events = (event for event in events if event[0] == "P")
    for depth, (old, pair, cache) in enumerate(zip(old_rows, pair_rows, cache_rows), 1):
        old, pair, cache = (list(map(int, tokens)) for tokens in (old, pair, cache))
        require((len(old), len(pair), len(cache)) == (31, 9, 9)
                and old[:2] == [depth, depth] and pair[0] == cache[0] == depth,
                f"{case}: invalid trace shape or occupied depth {depth}")
        states = old[2:20]
        cache_states = (1, 2, 3, 12, 13, 14)
        old_cache_cycles = sum(states[index] for index in cache_states)
        # The archive stores lookahead handshakes alongside the disjoint states.
        # Exclude those overlapping handshakes from the cycle sum.
        require(cache[1:] == [2 * depth, 32 * depth, 32 * depth, 30 * depth,
                              32, 32 * depth, 32 * depth, 32 * (depth - 1)],
                f"{case}: unexpected cache schedule at depth {depth}")
        cache_cycles = sum(cache[index] for index in (1, 2, 3, 5, 6, 7))
        require(old_cache_cycles - cache_cycles == 62 * depth - 32
                and all(old[index] == 0 for index in (20, 21, 22, 23, 29, 30)),
                f"{case}: unexpected cache saving or baseline stall at depth {depth}")

        # Match a completed probability to every position in each of the two heads.
        for head in ("0", "1"):
            for index in range(depth):
                event = next(probability_events, None)
                require(event is not None and event[1:3] == [head, str(index)],
                        f"{case}: probability events out of order at depth {depth}")

        probability_phase = sum(states[9:12])
        radix_steps = old[27]
        divisions = 2 * depth
        require(probability_phase == 37 * divisions and radix_steps == 32 * divisions,
                f"{case}: unexpected probability schedule at depth {depth}")
        exponent_cycles = pair[1]
        attention = sum(states) - old_cache_cycles - sum(states[6:9]) + cache_cycles + exponent_cycles
        scored = FIXED_SCORED_CYCLES + attention
        saving = SAVED_DIGITS_PER_DIVISION * divisions
        rows.append({
            "occupied_kv_rows": depth,
            "attention_wait_cycles": attention,
            "cache_traversal_cycles": cache_cycles,
            "exponential_phase_cycles": exponent_cycles,
            "probability_divisions": divisions,
            "probability_phase_cycles": probability_phase,
            "probability_radix_steps": radix_steps,
            "scored_prediction_cycles": scored,
            "scored_prediction_ms_at_50_mhz": ms(scored),
            "divider_forecast_saved_cycles": saving,
            "divider_forecast_scored_cycles": scored - saving,
        })
    require(next(probability_events, None) is None, f"{case}: unexpected extra probability events")
    return rows


def verify_boundaries(case, baseline, data, rows):
    raw_phases = trace_rows(baseline, f"replay/{case}/phases.txt")
    raw_cache = trace_rows(baseline, f"replay/{case}/cache.kv")
    require(len(raw_phases) == 2, f"{case}: expected prefix and completion snapshots")
    for boundary, raw in zip(("prefix", "done"), raw_phases):
        stats = data[boundary]
        depth = stats["positions"]
        phases = stats["phases"]
        snapshot = [row for row in raw_cache if row[0] == boundary]
        require(raw[0] == boundary and
                list(map(int, raw[1:])) ==
                [int(stats["first_valid"]), stats["first"], stats["last"], stats["done"], *phases],
                f"{case}: {boundary} summary differs from the raw phase snapshot")
        require(len(snapshot) == 1 and list(map(int, snapshot[0][1:])) == [depth, stats["cycles"]],
                f"{case}: {boundary} occupancy or counter differs from the raw cache snapshot")

        attention = sum(row["attention_wait_cycles"] for row in rows[:depth])
        fixed = depth * FIXED_WITHOUT_SCORING
        if boundary == "prefix":
            # The monitor samples on entry to LOGIT_START, before counting that
            # edge. It has captured one fewer IDLE clock than at completion.
            fixed -= 1
            require(phases[0] == 2 * depth - 1 and phases[17:19] == [0, 0],
                    f"{case}: prefix was not captured before the first scoring launch")
        else:
            require(phases[0] == 2 * depth and phases[17] == depth - data["prefix"]["positions"] + 1
                    and phases[18] == (SCORING_CYCLES - 1) * phases[17]
                    and stats["cycles"] == stats["done"],
                    f"{case}: unexpected completion, idle or score-launch accounting")
            fixed += SCORING_CYCLES * phases[17]
        require(attention == phases[8] and fixed + attention == sum(phases) == stats["cycles"],
                f"{case}: reconstructed {boundary} cycles do not match the archive")


def request_forecast(case, data, rows):
    prefix, done = data["prefix"], data["done"]

    def saved_through(depth):
        return sum(row["divider_forecast_saved_cycles"] for row in rows[:depth])

    prefix_saving = saved_through(prefix["positions"])
    done_saving = saved_through(done["positions"])
    outputs = data["outputs"]
    first_saving = last_saving = ""
    if done["first_valid"]:
        last_depth = prefix["positions"] + outputs - 1
        require(outputs > 0 and prefix["positions"] <= last_depth <= done["positions"],
                f"{case}: useful output boundary falls outside the processed positions")
        first_saving = prefix_saving
        last_saving = saved_through(last_depth)

    return {
        "case": case,
        "prefix_positions": prefix["positions"],
        "completed_positions": done["positions"],
        "score_projections": done["phases"][17],
        "output_tokens": outputs,
        "baseline_prefix_cycles": prefix["cycles"],
        "baseline_first_output_cycles": done["first"] if done["first_valid"] else "",
        "baseline_last_output_cycles": done["last"] if done["first_valid"] else "",
        "baseline_done_cycles": done["cycles"],
        "divider_forecast_saved_prefix_cycles": prefix_saving,
        "divider_forecast_saved_first_output_cycles": first_saving,
        "divider_forecast_saved_last_output_cycles": last_saving,
        "divider_forecast_saved_done_cycles": done_saving,
        "divider_forecast_done_cycles": done["cycles"] - done_saving,
        "divider_forecast_saved_done_ms_at_50_mhz": ms(done_saving),
        "divider_forecast_done_reduction_pct": f"{100 * done_saving / done['cycles']:.5f}",
    }


def csv_bytes(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(),
                        help="Checkout containing the archived runs (default: current directory)")
    parser.add_argument("--write", action="store_true",
                        help="Regenerate the two CSVs next to this script instead of checking them")
    args = parser.parse_args()

    profile_path, baseline_path, results_path = (
        verified_artifact(args.repo_root, *pin) for pin in ARTIFACTS
    )
    cases = json.loads(results_path.read_text(encoding="utf-8"))["candidate"]
    require(len(cases) == 7, "Expected all seven archived Experiment 13 replay cases")
    forecasts = []
    depth_rows = []
    with tarfile.open(profile_path) as profile, tarfile.open(baseline_path) as baseline:
        for case, data in sorted(cases.items()):
            rows = position_rows(case, profile, baseline, data["done"]["positions"])
            verify_boundaries(case, baseline, data, rows)
            forecasts.append(request_forecast(case, data, rows))
            if case == "full-context-cap0":
                require(len(rows) == 256 and data["outputs"] == 0
                        and data["done"]["phases"][17] == 1,
                        "The full-context fixture no longer has just one scoring projection")
                depth_rows = rows

    require(depth_rows, "Missing full-context chart case")
    output_dir = Path(__file__).resolve().parent
    for filename, rows in (("cache-depth.csv", depth_rows), ("request-forecasts.csv", forecasts)):
        path = output_dir / filename
        content = csv_bytes(rows)
        if args.write:
            path.write_bytes(content)
        else:
            require(path.read_bytes() == content, f"{filename}: generated content differs")
    print("Verified three archival hashes, seven prefix and done boundaries, "
          "256 chart rows and seven request forecasts.")


if __name__ == "__main__":
    main()
