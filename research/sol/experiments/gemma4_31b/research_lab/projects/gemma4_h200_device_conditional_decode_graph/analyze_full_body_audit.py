from __future__ import annotations

import argparse
import collections
import json
import pathlib


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--support", type=pathlib.Path, required=True)
    parser.add_argument("--workload", type=pathlib.Path, required=True)
    parser.add_argument("--audit", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    support = json.loads(args.support.read_text())
    workload = json.loads(args.workload.read_text())
    start = workload["started_monotonic_s"]
    end = workload["ended_monotonic_s"]
    events = [
        json.loads(line)
        for line in args.audit.read_text().splitlines()
        if line.strip()
    ]
    window = [
        row
        for row in events
        if start <= float(row.get("monotonic_s", -1)) <= end
    ]
    counts = collections.Counter(row["event"] for row in window)
    graph_rows = [
        row for row in window if row["event"] == "CudaGraphRunner.replay_complete"
    ]
    captured_sizes = sorted(
        {
            int(row["captured_batch_size"])
            for row in graph_rows
            if row.get("captured_batch_size") is not None
        }
    )
    raw_sizes = sorted(
        {
            int(row["raw_batch_size"])
            for row in graph_rows
            if row.get("raw_batch_size") is not None
        }
    )
    host_boundaries = {
        "sample": counts["ModelRunner.sample"],
        "decode_result_processing": counts[
            "SchedulerBatchResultProcessor.process_batch_result_decode"
        ],
        "scheduler_result_processing": counts["Scheduler.process_batch_result"],
        "next_decode_preparation": counts["ScheduleBatch.prepare_for_decode"],
        "next_running_batch_update": counts["Scheduler.update_running_batch"],
    }
    host_intervention_proven = (
        host_boundaries["sample"] >= 4
        and host_boundaries["decode_result_processing"] >= 4
        and host_boundaries["scheduler_result_processing"] >= 4
        and host_boundaries["next_decode_preparation"] >= 3
    )
    padded_graph_proven = any(
        row.get("captured_batch_size") != row.get("raw_batch_size")
        for row in graph_rows
    )
    workload_pass = bool(workload.get("pass"))
    full_body_support = bool(support.get("full_body_support", {}).get("pass"))

    if not workload_pass:
        classification = "full_body_discriminator_workload_invalid"
    elif host_intervention_proven and not full_body_support:
        classification = "full_body_host_intervention_required"
    elif full_body_support:
        classification = "full_body_candidate_support_present"
    else:
        classification = "full_body_support_inconclusive"

    result = {
        "schema_version": 1,
        "status": "terminal",
        "classification": classification,
        "repeat_tokens": 4,
        "support_discriminator": support,
        "workload": workload,
        "window": {
            "started_monotonic_s": start,
            "ended_monotonic_s": end,
            "event_count": len(window),
        },
        "event_counts": dict(sorted(counts.items())),
        "host_boundaries": host_boundaries,
        "host_intervention_proven": host_intervention_proven,
        "raw_graph_batch_sizes": raw_sizes,
        "captured_graph_batch_sizes": captured_sizes,
        "padded_graph_proven": padded_graph_proven,
        "full_body_state_equivalence_pass": False,
        "fewer_host_round_trips_pass": False,
        "fewer_graph_launches_pass": False,
        "endpoint_gate_pass": False,
        "candidate_scientific_invocation_began": False,
        "support_scientific_invocation_began": bool(
            support.get("scientific_invocation_began")
        ),
        "pass": classification == "full_body_candidate_support_present",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0 if classification != "full_body_discriminator_workload_invalid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
