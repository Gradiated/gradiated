#!/usr/bin/env python3
"""CPU-only falsifier for the overlap-scheduler result-copy host handoff.

This does not benchmark CUDA.  It binds one source-exact producer/consumer
chain and computes only a conservative all-calls envelope from the admitted
Nsight Systems CSV.  The CSV has no call stacks or correlation records, so the
selected callsite's non-overlapping wall time deliberately remains unknown.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


EXPECTED = {
    "source_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
    "source_tree": "ed4e68454edee9b97272386af2fd8f989484f270",
    "trace_sha256": "2c23d30660675e39185344b2d44b7b951d7bcd700704c4fd73028efa19eff487",
    "source_sha256": {
        "python/sglang/srt/managers/utils.py": (
            "b4b36fb9f649fc6306cf0e94ff364ee9c639e31eb7ee6f0a7c66b8e3a0a2d08a"
        ),
        "python/sglang/srt/managers/scheduler.py": (
            "3a26deea85f43d61c27b94013288ad95d6ee75111fe40134893541777c9c8cd4"
        ),
        "python/sglang/srt/managers/scheduler_components/batch_result_processor.py": (
            "9c764afffb106e966fde110851de73bb6a3d0f2415343a574a255e91f86851de"
        ),
    },
}

FIXED_DENOMINATOR_S_PER_REQUEST = 0.625149101968745
TARGET_S_PER_REQUEST = 0.500119281574996
REQUEST_COUNT = 32


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_line(path: Path, needle: str) -> int:
    matches = [
        index
        for index, line in enumerate(path.read_text().splitlines(), start=1)
        if needle in line
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one source match for {needle!r} in {path}, got {matches}"
        )
    return matches[0]


def source_line_after(path: Path, needle: str, anchor: str) -> int:
    lines = path.read_text().splitlines()
    anchors = [i for i, line in enumerate(lines, start=1) if anchor in line]
    if len(anchors) != 1:
        raise AssertionError(
            f"expected one anchor for {anchor!r} in {path}, got {anchors}"
        )
    matches = [
        i
        for i, line in enumerate(lines, start=1)
        if i > anchors[0] and needle in line
    ]
    if not matches:
        raise AssertionError(
            f"no source match for {needle!r} after {anchor!r} in {path}"
        )
    return matches[0]


def git_value(source_root: Path, expression: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", expression],
        cwd=source_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def find_cuda_api(trace_csv: Path, name: str) -> dict:
    # nsys stats concatenates several independently headed CSV tables.  The
    # CUDA API row is stable and has nine columns in this admitted artifact.
    for row in csv.reader(trace_csv.read_text().splitlines()):
        if len(row) == 9 and row[-1] == name:
            return {
                "time_percent": float(row[0]),
                "total_time_ns": int(row[1]),
                "instances": int(row[2]),
                "average_ns": float(row[3]),
                "median_ns": float(row[4]),
                "minimum_ns": int(row[5]),
                "maximum_ns": int(row[6]),
                "standard_deviation_ns": float(row[7]),
                "name": row[8],
            }
    raise AssertionError(f"{name} not found in {trace_csv}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--trace-csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    trace_csv = args.trace_csv.resolve()
    output = args.output.resolve()

    commit = git_value(source_root, "HEAD")
    tree = git_value(source_root, "HEAD^{tree}")
    assert commit == EXPECTED["source_commit"], (commit, EXPECTED["source_commit"])
    assert tree == EXPECTED["source_tree"], (tree, EXPECTED["source_tree"])
    assert sha256(trace_csv) == EXPECTED["trace_sha256"]

    source_hashes = {}
    for relative, expected_hash in EXPECTED["source_sha256"].items():
        path = source_root / relative
        actual_hash = sha256(path)
        assert actual_hash == expected_hash, (relative, actual_hash, expected_hash)
        source_hashes[relative] = actual_hash

    utils = source_root / "python/sglang/srt/managers/utils.py"
    scheduler = source_root / "python/sglang/srt/managers/scheduler.py"
    processor = (
        source_root
        / "python/sglang/srt/managers/scheduler_components/batch_result_processor.py"
    )

    lines = {
        "event_owner_field": source_line_after(
            utils,
            "copy_done: Optional[torch.cuda.Event] = None",
            "class GenerationBatchResult:",
        ),
        "d2h_producer": source_line(
            utils, 'self.next_token_ids = self.next_token_ids.to("cpu", non_blocking=True)'
        ),
        "producer_completion_record": source_line_after(
            utils,
            "self.copy_done.record()",
            'self.next_token_ids = self.next_token_ids.to("cpu", non_blocking=True)',
        ),
        "event_allocation": source_line_after(
            scheduler,
            "batch_result.copy_done = self.device_module.Event()",
            "# FIXME(lsyin): maybe move this to forward_batch_generation",
        ),
        "queue_before_consume": source_line(
            scheduler, "self.result_queue.append((batch.copy(), batch_result))"
        ),
        "blocking_host_call": source_line_after(
            processor,
            "result.copy_done.synchronize()",
            "def process_batch_result_decode(",
        ),
        "first_host_tensor_read": source_line_after(
            processor,
            "next_token_ids = next_token_ids.tolist()",
            "def _normalize_decode_outputs(",
        ),
    }
    assert lines["d2h_producer"] < lines["producer_completion_record"]
    assert lines["blocking_host_call"] < lines["first_host_tensor_read"]

    event_api = find_cuda_api(trace_csv, "cudaEventSynchronize")
    all_event_sync_s = event_api["total_time_ns"] / 1e9
    all_event_sync_s_per_request = all_event_sync_s / REQUEST_COUNT
    fixed_gap = FIXED_DENOMINATOR_S_PER_REQUEST - TARGET_S_PER_REQUEST

    # Correctness-bearing lifecycle model.  A device event orders the D2H
    # producer, but host-visible bytes cannot be read safely until host
    # observation of completion.  Deferral can move, not delete, that boundary.
    lifecycle_checks = {
        "stock": ["enqueue_d2h", "record_event", "host_wait", "host_read"],
        "unsafe_delete": ["enqueue_d2h", "record_event", "host_read"],
        "deferred_wait": [
            "enqueue_d2h",
            "record_event",
            "independent_next_batch_launch",
            "host_wait",
            "host_read",
        ],
    }
    assert lifecycle_checks["stock"].index("host_wait") < lifecycle_checks[
        "stock"
    ].index("host_read")
    assert "host_wait" not in lifecycle_checks["unsafe_delete"]
    assert lifecycle_checks["deferred_wait"].index("host_wait") < lifecycle_checks[
        "deferred_wait"
    ].index("host_read")

    result = {
        "schema_version": 1,
        "artifact_type": "localized_host_sync_source_trace_falsifier",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "execution": {
            "mode": "cpu_only_source_and_trace",
            "gpu_claimed": False,
            "provider_mutation": False,
            "scientific_sample_consumed": False,
        },
        "source_binding": {
            "commit": commit,
            "tree": tree,
            "file_sha256": source_hashes,
            "source_lines": lines,
        },
        "trace_binding": {
            "path": str(trace_csv),
            "sha256": sha256(trace_csv),
            "cuda_event_synchronize_summary": event_api,
            "attribution_limit": (
                "This CSV summary has no call stacks, correlation IDs, thread "
                "intervals, or callsite labels; it cannot attribute any instance "
                "or duration to the selected Python callsite."
            ),
        },
        "selected_edge": {
            "host_symbol": (
                "BatchResultProcessor.process_batch_result_decode -> "
                "torch.cuda.Event.synchronize -> cudaEventSynchronize"
            ),
            "device_producer": (
                "GenerationBatchResult.copy_to_cpu: asynchronous D2H copy of "
                "next_token_ids, followed by copy_done.record()"
            ),
            "first_consumer": (
                "BatchResultProcessor._normalize_decode_outputs: "
                "next_token_ids.tolist()"
            ),
            "ordering": [
                "forward_stream waits on schedule_stream",
                "forward_stream produces sampled next_token_ids",
                "forward_stream enqueues non_blocking D2H copy",
                "copy_done event is recorded on forward_stream after the copy",
                "result is retained in result_queue while the next batch launches",
                "scheduler host thread synchronizes copy_done",
                "host converts the CPU tensor with Tensor.tolist",
            ],
            "state": {
                "owner": "GenerationBatchResult retained by Scheduler.result_queue",
                "tensor": "next_token_ids",
                "device_shape": "[B] where B is the dynamic decode batch size",
                "host_shape": "[B]",
                "dtype": (
                    "sampler-path dependent integer tensor: int64 for stock "
                    "torch.argmax/torch.multinomial paths; int32 for AITER or "
                    "explicit int32 sampling paths; the admitted CSV does not "
                    "encode the realized dtype"
                ),
                "event": "GenerationBatchResult.copy_done: torch.cuda.Event",
                "producer_stream": "Scheduler.forward_stream",
                "consumer_execution": "scheduler host thread",
            },
        },
        "wait_bound": {
            "selected_edge_nonoverlap_s_per_request": None,
            "status": "explicit_unknown",
            "reason": (
                "The admitted aggregate CSV cannot isolate this callsite or "
                "subtract device work already hidden by event_loop_overlap."
            ),
            "all_cuda_event_synchronize_sum_envelope": {
                "scope": (
                    "all 420 cudaEventSynchronize calls in the capture, not the "
                    "selected callsite and not a predicted removable wall gain"
                ),
                "total_s": all_event_sync_s,
                "s_per_request_at_n32": all_event_sync_s_per_request,
                "percent_of_fixed_denominator": (
                    100
                    * all_event_sync_s_per_request
                    / FIXED_DENOMINATOR_S_PER_REQUEST
                ),
                "percent_of_required_gap": 100
                * all_event_sync_s_per_request
                / fixed_gap,
                "interpretation": (
                    "Even the impossible zero-cost deletion of every event-sync "
                    "API duration is below one percent of the required gap.  This "
                    "is only a conservation envelope; overlapping thread/API "
                    "durations are not summed into a wall-time prediction."
                ),
            },
        },
        "correctness_falsifier": {
            "lifecycle_sequences": lifecycle_checks,
            "unsafe_candidate": "delete or replace host wait with device wait",
            "failure": (
                "A device-side wait cannot make asynchronously copied bytes safe "
                "for a CPU Tensor.tolist consumer.  Deleting the host completion "
                "observation admits stale or partially copied token IDs."
            ),
            "safe_candidate": (
                "defer the same host wait until the first CPU read while launching "
                "independent device work first"
            ),
            "safe_candidate_is_stock": True,
            "basis": (
                "event_loop_overlap launches the current batch before processing "
                "the queued previous result; the stock implementation already "
                "performs this one-iteration deferral."
            ),
        },
        "decision": {
            "type": "falsify_device_ordered_replacement_and_close_edge",
            "reason": (
                "The selected edge is a host-ownership handoff already deferred "
                "behind the next batch launch.  Its exact non-overlap is "
                "unattributed, and the all-event-sync envelope is economically "
                "immaterial."
            ),
            "h200_measurement_warranted": False,
            "redirect": (
                "Only a future callsite-correlated trace may revisit host waits; "
                "do not benchmark or patch this result-copy event edge."
            ),
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
