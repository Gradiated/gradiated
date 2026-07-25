from __future__ import annotations

import collections
import gzip
import hashlib
import json
import statistics
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
TRACE = PROJECT / "inputs/trace/exact_c32_profile.trace.json.gz"
TERMINAL = PROJECT / "inputs/evidence/EXACT_C32_TERMINAL.json"
METRICS_BEFORE = PROJECT / "inputs/evidence/metrics-before.prom"
METRICS_AFTER = PROJECT / "inputs/evidence/metrics-after.prom"
OUTPUT = PROJECT / "artifacts/BOUND_CRITICAL_PATH.json"

EXPECTED_LOCAL_HASHES = {
    TRACE: "37e2c73a57e8e63bd7ec0a3465cc1edded8b9dc63507d97e85a767306a97a48b",
    TERMINAL: "6ca48ede7fb2a2ed236b021d5b815ef9d1506020c5693f81c2cff5f7fee71282",
    METRICS_BEFORE: "d495cff990e9b8822e333e90bf755df5eb80aabc705a0b7b32a78ec7a08012f8",
    METRICS_AFTER: "1a16e8775f3e2710142f3b8fad403cee8c9fc3fe36523d2c53e12166c04c1a78",
}

ATTENTION_KERNEL = "_fwd_kernel"
CUTLASS_FP8_PREFIX = "void cutlass::device_kernel<cutlass_3x_gemm_sm90_fp8"
LM_HEAD_KERNEL = "nvjet_sm90_tst_512x32_64x3_2x1_v_bz_TNT"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_prometheus(path: Path) -> dict[str, float]:
    result: dict[str, float] = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        try:
            name, value = line.rsplit(" ", 1)
            result[name] = float(value)
        except ValueError:
            continue
    return result


def metric_delta(
    before: dict[str, float], after: dict[str, float], prefix: str, required_label: str = ""
) -> float:
    matches = [
        name
        for name in after
        if name.startswith(prefix) and (not required_label or required_label in name)
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected_one_metric:{prefix}:{matches}")
    name = matches[0]
    return after[name] - before.get(name, 0.0)


def union_us(intervals: list[tuple[float, float]]) -> float:
    if not intervals:
        return 0.0
    total = 0.0
    start, end = sorted(intervals)[0]
    for next_start, next_end in sorted(intervals)[1:]:
        if next_start > end:
            total += end - start
            start, end = next_start, next_end
        else:
            end = max(end, next_end)
    return total + end - start


def kernel_signature(event: dict) -> tuple:
    args = event.get("args", {})
    return (
        event["name"],
        tuple(args.get("grid", [])),
        tuple(args.get("block", [])),
        args.get("registers per thread"),
        args.get("shared memory"),
    )


def summarize_kernel_rows(rows: list[dict]) -> dict:
    durations = [row["dur"] for row in rows]
    name, grid, block, registers, shared_memory = kernel_signature(rows[0])
    return {
        "kernel": name,
        "launches": len(rows),
        "summed_us": sum(durations),
        "median_us": statistics.median(durations),
        "minimum_us": min(durations),
        "maximum_us": max(durations),
        "grid": list(grid),
        "block": list(block),
        "registers_per_thread": registers,
        "dynamic_shared_memory_bytes": shared_memory,
    }


def main() -> None:
    local_hashes = {str(path.relative_to(PROJECT)): sha256(path) for path in EXPECTED_LOCAL_HASHES}
    for path, expected in EXPECTED_LOCAL_HASHES.items():
        if local_hashes[str(path.relative_to(PROJECT))] != expected:
            raise RuntimeError(f"local_hash_mismatch:{path}")

    binding = json.loads((PROJECT / "EVIDENCE_BINDING.json").read_text())
    binding_checks = {}
    for name, record in binding["bound_artifacts"].items():
        path = (PROJECT / record["path"]).resolve()
        actual = sha256(path)
        binding_checks[name] = {
            "path": str(path),
            "expected_sha256": record["sha256"],
            "actual_sha256": actual,
            "match": actual == record["sha256"],
        }
    if not all(row["match"] for row in binding_checks.values()):
        raise RuntimeError("evidence_binding_mismatch")

    with gzip.open(TRACE, "rt", encoding="utf-8") as handle:
        trace = json.load(handle)
    complete = [
        event
        for event in trace["traceEvents"]
        if event.get("ph") == "X"
        and isinstance(event.get("ts"), (int, float))
        and isinstance(event.get("dur"), (int, float))
    ]
    target_rows = sorted(
        (event for event in complete if event.get("name") == "ngram.target_forward_verify"),
        key=lambda event: event["ts"],
    )
    accept_rows = sorted(
        (
            event
            for event in complete
            if event.get("name") == "ngram.accept_bookkeeping_and_cache"
            and event["dur"] > 100_000
        ),
        key=lambda event: event["ts"],
    )
    if len(target_rows) != 15 or len(accept_rows) != 15:
        raise RuntimeError(f"unexpected_verification_cycles:{len(target_rows)}:{len(accept_rows)}")

    target_cycles = []
    for target, accept in zip(target_rows, accept_rows, strict=True):
        target_end = target["ts"] + target["dur"]
        if accept["ts"] < target_end:
            raise RuntimeError("acceptance_sync_precedes_target_enqueue")
        target_cycles.append(
            {
                "start_us": target["ts"],
                "end_us": accept["ts"] + accept["dur"],
                "enqueue_us": target["dur"],
                "queued_completion_us": accept["dur"],
                "critical_us": accept["ts"] + accept["dur"] - target["ts"],
            }
        )

    cycle_intervals = [(row["start_us"], row["end_us"]) for row in target_cycles]
    cycle_durations = [row["critical_us"] for row in target_cycles]
    recurrence = [
        target_rows[index + 1]["ts"] - target_rows[index]["ts"]
        for index in range(len(target_rows) - 1)
    ]

    kernels = [event for event in complete if event.get("cat") == "kernel"]
    grouped: dict[tuple, list[dict]] = collections.defaultdict(list)
    for event in kernels:
        grouped[kernel_signature(event)].append(event)
    attention = [
        summarize_kernel_rows(rows)
        for signature, rows in grouped.items()
        if signature[0] == ATTENTION_KERNEL
    ]
    fp8_gemm_rows = [
        event for event in kernels if str(event.get("name", "")).startswith(CUTLASS_FP8_PREFIX)
    ]
    lm_head_rows = [event for event in kernels if event.get("name") == LM_HEAD_KERNEL]
    attention_sum_us = sum(row["summed_us"] for row in attention)
    gpu_intervals = [
        (event["ts"], event["ts"] + event["dur"])
        for event in complete
        if event.get("cat") in {"kernel", "gpu_memcpy", "gpu_memset"}
        and target_rows[0]["ts"] <= event["ts"] <= accept_rows[-1]["ts"] + accept_rows[-1]["dur"]
    ]

    before = parse_prometheus(METRICS_BEFORE)
    after = parse_prometheus(METRICS_AFTER)
    graph_passes = metric_delta(
        before,
        after,
        "sglang:cuda_graph_passes_total",
        'mode="decode_cuda_graph"',
    )
    request_verify_calls = metric_delta(before, after, "sglang:spec_verify_calls_total")
    terminal = json.loads(TERMINAL.read_text())
    requests = terminal["complete_requests"]
    baseline_seconds_per_request = binding["baseline_seconds_per_request"]
    target_seconds_per_request = binding["target_seconds_per_request"]
    required_savings_seconds = baseline_seconds_per_request - target_seconds_per_request
    mean_target_cycle_seconds = statistics.mean(cycle_durations) / 1e6
    request_equivalent_passes = request_verify_calls / requests
    conservative_target_seconds_per_request = (
        mean_target_cycle_seconds * request_equivalent_passes / requests
    )
    graph_count_target_seconds_per_request = mean_target_cycle_seconds * graph_passes / requests
    attention_fraction_of_target_gpu_union = attention_sum_us / union_us(gpu_intervals)
    attention_maximum_whole_request_fraction_range = [
        conservative_target_seconds_per_request
        / baseline_seconds_per_request
        * attention_fraction_of_target_gpu_union,
        graph_count_target_seconds_per_request
        / baseline_seconds_per_request
        * attention_fraction_of_target_gpu_union,
    ]

    output = {
        "schema_version": 1,
        "classification": "measured_trace_plus_counter_derived_whole_request_bound",
        "binding": {
            "all_external_hashes_match": True,
            "external": binding_checks,
            "project_local_immutable_snapshots": local_hashes,
        },
        "scope": {
            "model": binding["model"],
            "runtime_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "hardware": "nvidia-h200-sxm",
            "concurrency": requests,
            "speculative_algorithm": "NGRAM",
            "depth": 12,
            "target_rows": 384,
            "output_tokens_per_request": 358,
        },
        "whole_request": {
            "measured_profiled_batch_seconds": terminal["batch_seconds"],
            "measured_profiled_service_seconds_per_request": terminal[
                "service_seconds_per_request"
            ],
            "quality_qualified_baseline_seconds_per_request": baseline_seconds_per_request,
            "objective_seconds_per_request": target_seconds_per_request,
            "required_savings_seconds_per_request": required_savings_seconds,
        },
        "target_verification_critical_path": {
            "captured_cycles": len(target_cycles),
            "non_overlapping_union_us": union_us(cycle_intervals),
            "mean_cycle_us": statistics.mean(cycle_durations),
            "median_cycle_us": statistics.median(cycle_durations),
            "mean_recurrence_us": statistics.mean(recurrence),
            "gpu_interval_union_us": union_us(gpu_intervals),
            "request_verify_calls_counter": request_verify_calls,
            "request_equivalent_full_batch_passes": request_equivalent_passes,
            "cuda_graph_passes_counter": graph_passes,
            "conservative_projected_seconds_per_request": conservative_target_seconds_per_request,
            "graph_count_projected_seconds_per_request": graph_count_target_seconds_per_request,
            "conservative_fraction_of_qualified_baseline": (
                conservative_target_seconds_per_request / baseline_seconds_per_request
            ),
            "graph_count_fraction_of_qualified_baseline": (
                graph_count_target_seconds_per_request / baseline_seconds_per_request
            ),
            "required_target_boundary_speedup_fraction_range": [
                required_savings_seconds / graph_count_target_seconds_per_request,
                required_savings_seconds / conservative_target_seconds_per_request,
            ],
            "ceiling_20_percent_physically_open": (
                conservative_target_seconds_per_request > required_savings_seconds
            ),
            "coverage_limit": (
                "The exact trace covers 15 fully active post-first-token M384 cycles, not the "
                "whole request. Full-request target share is counter-derived and must be replaced "
                "by one short scope-matched H200 capture before an endpoint claim."
            ),
        },
        "kernel_families": {
            "attention": {
                "producer": "TritonAttnBackend.forward_extend",
                "consumer": "Gemma4Attention.forward output projection",
                "symbol": "sglang.srt.layers.attention.triton_ops.extend_attention._fwd_kernel",
                "launches": sum(row["launches"] for row in attention),
                "launches_per_target_cycle": sum(row["launches"] for row in attention)
                / len(target_cycles),
                "summed_us": attention_sum_us,
                "summed_fraction_of_gpu_union": attention_fraction_of_target_gpu_union,
                "maximum_whole_request_fraction_range": (
                    attention_maximum_whole_request_fraction_range
                ),
                "subtypes": attention,
                "exact_geometry": [
                    {
                        "layers": 50,
                        "subtype": "local_sliding_extend",
                        "q_shape": [384, 32, 256],
                        "kv_heads": 16,
                        "v_head_dim": 256,
                        "window": 1024,
                        "dtype": "bf16 query / fp8_e5m2 KV cache / bf16 output",
                    },
                    {
                        "layers": 10,
                        "subtype": "global_extend",
                        "q_shape": [384, 32, 512],
                        "kv_heads": 4,
                        "v_head_dim": 512,
                        "window": None,
                        "dtype": "bf16 query / fp8_e5m2 KV cache / bf16 output",
                    },
                ],
                "physical_interpretation": (
                    "Both exact M384 subtypes compile at 255 registers/thread and one CTA per SM. "
                    "The trace realizes 7.76 grid waves per layer, so the dominant fixed-shape "
                    "opportunity is reducing per-CTA live query-row state and padded query work, "
                    "not adding grid supply."
                ),
            },
            "fp8_projections": {
                "producer": "dynamic per-token FP8 quantization",
                "consumer": "Gemma4 attention/MLP residual stream",
                "symbol": "CUTLASS SM90 128x128x128 2x1x1 pingpong FP8 fast-accum GEMM",
                "launches": len(fp8_gemm_rows),
                "launches_per_target_cycle": len(fp8_gemm_rows) / len(target_cycles),
                "summed_us": sum(row["dur"] for row in fp8_gemm_rows),
                "median_us": statistics.median(row["dur"] for row in fp8_gemm_rows),
                "registers_per_thread": fp8_gemm_rows[0]["args"]["registers per thread"],
                "dynamic_shared_memory_bytes": fp8_gemm_rows[0]["args"]["shared memory"],
                "shapes_mnk": [
                    {"family": "local_qkv", "shape": [384, 16384, 5376], "calls_per_cycle": 50},
                    {"family": "global_qkv", "shape": [384, 20480, 5376], "calls_per_cycle": 10},
                    {"family": "local_o", "shape": [384, 5376, 8192], "calls_per_cycle": 50},
                    {"family": "global_o", "shape": [384, 5376, 16384], "calls_per_cycle": 10},
                    {"family": "gate_up", "shape": [384, 43008, 5376], "calls_per_cycle": 60},
                    {"family": "down", "shape": [384, 5376, 21504], "calls_per_cycle": 60},
                ],
            },
            "tied_lm_head": {
                "producer": "request-major depth-sliced hidden states",
                "consumer": "NGRAM greedy target verification and acceptance",
                "symbol": LM_HEAD_KERNEL,
                "launches": len(lm_head_rows),
                "launches_per_target_cycle": len(lm_head_rows) / len(target_cycles),
                "summed_us": sum(row["dur"] for row in lm_head_rows),
                "median_us": statistics.median(row["dur"] for row in lm_head_rows),
                "registers_per_thread": lm_head_rows[0]["args"]["registers per thread"],
                "dynamic_shared_memory_bytes": lm_head_rows[0]["args"]["shared memory"],
                "shape_mnk": [32, 262144, 5376],
                "depth_launches": 12,
            },
        },
        "decision": {
            "result": "20_percent_ceiling_open_but_requires_large_boundary_speedup",
            "selected_change_20_percent_ceiling_open": False,
            "selected_boundary": "fixed_m384_extend_attention",
            "selected_change": (
                "Exact q_len=12 c32 attention dispatch with an eight-row query tile for both "
                "local and global layers; preserve the stock fallback for every other geometry."
            ),
            "falsifier": (
                "Reject if the exact consumer differs, graph replay does not select the candidate, "
                "or warm target-forward critical time fails to beat stock by enough to retain a "
                "material whole-request bound."
            ),
            "interpretation": (
                "The complete target-forward executor retains a 25.36-28.93% whole-request "
                "ceiling, but the measured attention family alone is at most 17.03-19.42%. "
                "This intervention can be retained as a stackable gain but cannot by itself "
                "establish the 20% project objective."
            ),
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.part")
    temporary.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    temporary.replace(OUTPUT)


if __name__ == "__main__":
    main()
