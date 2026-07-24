from __future__ import annotations

import argparse
import collections
import gzip
import json
import pathlib


RANGES = [
    "ngram.cpu_corpus_lookup",
    "ngram.draft_mask_and_indices",
    "ngram.cache_slot_prepare",
    "ngram.target_forward_verify",
    "ngram.accept_bookkeeping_and_cache",
    "ngram.cpu_corpus_update",
]


def load(path: pathlib.Path) -> dict:
    opener = gzip.open if path.suffix == ".gz" else path.open
    with opener(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def union_duration(intervals: list[tuple[float, float]]) -> float:
    if not intervals:
        return 0.0
    result = 0.0
    start, end = sorted(intervals)[0]
    for next_start, next_end in sorted(intervals)[1:]:
        if next_start > end:
            result += end - start
            start, end = next_start, next_end
        else:
            end = max(end, next_end)
    return result + end - start


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    events = load(args.trace)["traceEvents"]
    complete = [
        event
        for event in events
        if event.get("ph") == "X"
        and isinstance(event.get("ts"), (int, float))
        and isinstance(event.get("dur"), (int, float))
    ]
    semantic = {
        name: [event for event in complete if event.get("name") == name]
        for name in RANGES
    }
    semantic_events = [event for rows in semantic.values() for event in rows]
    if not semantic_events:
        raise RuntimeError("semantic_ranges_missing")
    window_start = min(event["ts"] for event in semantic_events)
    window_end = max(event["ts"] + event["dur"] for event in semantic_events)
    window = window_end - window_start

    gpu = [
        event
        for event in complete
        if window_start <= event["ts"] < window_end
        and str(event.get("cat", "")).lower()
        in {"kernel", "gpu_memcpy", "gpu_memset"}
        and event.get("name") not in RANGES
    ]
    kernel_groups: collections.Counter[str] = collections.Counter()
    for event in gpu:
        kernel_groups[str(event.get("name", "<unknown>"))] += event["dur"]
    gpu_intervals = [
        (max(window_start, event["ts"]), min(window_end, event["ts"] + event["dur"]))
        for event in gpu
    ]
    gpu_busy = union_duration(gpu_intervals)

    range_summary = {}
    for name, rows in semantic.items():
        intervals = [(row["ts"], row["ts"] + row["dur"]) for row in rows]
        range_summary[name] = {
            "calls": len(rows),
            "cpu_total_us": sum(row["dur"] for row in rows),
            "cpu_union_us": union_duration(intervals),
            "cpu_union_fraction_of_window": union_duration(intervals) / window,
        }

    draft_exclusive = (
        range_summary["ngram.draft_mask_and_indices"]["cpu_union_us"]
        - range_summary["ngram.cpu_corpus_lookup"]["cpu_union_us"]
        - range_summary["ngram.cache_slot_prepare"]["cpu_union_us"]
    )
    boundaries = {
        "draft_mask_indices_exclusive": max(0.0, draft_exclusive),
        "target_forward_verify": range_summary["ngram.target_forward_verify"][
            "cpu_union_us"
        ],
        "accept_bookkeeping_and_cache": range_summary[
            "ngram.accept_bookkeeping_and_cache"
        ]["cpu_union_us"],
        "cpu_corpus_update": range_summary["ngram.cpu_corpus_update"][
            "cpu_union_us"
        ],
        "gpu_idle_or_host_gap": max(0.0, window - gpu_busy),
    }
    ordered_boundaries = sorted(
        boundaries.items(), key=lambda item: item[1], reverse=True
    )
    output = {
        "schema_version": 1,
        "trace": str(args.trace),
        "window_us": window,
        "semantic_ranges": range_summary,
        "gpu": {
            "event_count": len(gpu),
            "interval_union_us": gpu_busy,
            "interval_union_fraction_of_window": gpu_busy / window,
            "top_events_by_summed_time_us": [
                {"name": name, "summed_us": duration}
                for name, duration in kernel_groups.most_common(30)
            ],
        },
        "non_overlapping_boundary_proxies_us": boundaries,
        "ordered_boundary_proxies": [
            {"name": name, "duration_us": duration}
            for name, duration in ordered_boundaries
        ],
        "caveat": (
            "CPU record ranges and GPU interval union use one wall-clock trace but "
            "asynchronous launches prevent treating their sums as additive."
        ),
    }
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
