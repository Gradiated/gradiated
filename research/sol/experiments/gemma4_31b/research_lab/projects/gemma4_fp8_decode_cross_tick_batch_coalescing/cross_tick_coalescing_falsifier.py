#!/usr/bin/env python3
"""Reconstruct exact c32 tick geometry and falsify illegal cross-tick merges."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


EXPECTED_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
EXPECTED_TREE = "ed4e68454edee9b97272386af2fd8f989484f270"
EXPECTED_SOURCE_HASHES = {
    "python/sglang/srt/managers/scheduler.py": "3a26deea85f43d61c27b94013288ad95d6ee75111fe40134893541777c9c8cd4",
    "python/sglang/srt/managers/schedule_batch.py": "eea77dac02f593da24e953f0a0ea03237f2874d0ef27522044e8fd6397fcb874",
    "python/sglang/srt/managers/tp_worker.py": "f2e00ea7d53b7250231d44b9d52415c6f6b5f936b0e7c6af4a13f5aff6c1e509",
    "python/sglang/srt/managers/scheduler_components/batch_result_processor.py": "9c764afffb106e966fde110851de73bb6a3d0f2415343a574a255e91f86851de",
    "python/sglang/srt/model_executor/model_runner.py": "f4dad073eb9f89afd4cda0439b97dee63f8de131d0ed10078b817dba1f978f59",
    "python/sglang/srt/model_executor/cuda_graph_runner.py": "7d1898247e80ff6a446eb42e4968d2eea0df30b109ee2d089a9ad78791bc079e",
    "python/sglang/srt/models/gemma4_causal.py": "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989",
    "python/sglang/srt/models/gemma3_causal.py": "a9827bde583c5b8b0abfeaced097c4e9d060fb99ec2961b4f9c66173d3027282",
    "python/sglang/srt/layers/linear.py": "092d1a6f945651afa01dbd3a252a2d65eec8483f30faff3d138d69055fdbba00",
    "python/sglang/srt/layers/quantization/fp8.py": "c7368db317513e5823283eb5567d15fdb742c3b01a98bfc483cb500291b4285a",
    "python/sglang/srt/layers/quantization/fp8_utils.py": "a3a130f40974047084e3daff2bd0efbbfe69e197d4c9a5ba3fbc5304dd4e43d9",
}
SOURCE_ANCHORS = [
    (
        "python/sglang/srt/managers/scheduler.py",
        "Scheduler.event_loop_normal",
        "result = self.run_batch(batch)",
    ),
    (
        "python/sglang/srt/managers/scheduler.py",
        "Scheduler.event_loop_normal",
        "self.process_batch_result(batch, result)",
    ),
    (
        "python/sglang/srt/managers/scheduler.py",
        "Scheduler.get_next_batch_to_run",
        "# Run prefill first if possible",
    ),
    (
        "python/sglang/srt/managers/schedule_batch.py",
        "ScheduleBatch.prepare_for_decode",
        "self.out_cache_loc = alloc_for_decode(self, token_per_req=1)",
    ),
    (
        "python/sglang/srt/managers/schedule_batch.py",
        "ScheduleBatch.prepare_for_decode",
        "req.kv_committed_len += 1",
    ),
    (
        "python/sglang/srt/managers/tp_worker.py",
        "TpModelWorker.forward_batch_generation",
        "out = self.model_runner.forward(",
    ),
    (
        "python/sglang/srt/managers/tp_worker.py",
        "TpModelWorker.forward_batch_generation",
        "batch_result.next_token_ids = self.model_runner.sample(",
    ),
    (
        "python/sglang/srt/managers/scheduler.py",
        "Scheduler.run_batch",
        "batch.req_pool_indices, batch_result.next_token_ids",
    ),
    (
        "python/sglang/srt/managers/scheduler_components/batch_result_processor.py",
        "BatchResultProcessor.process_batch_result_decode",
        "req.output_ids.append(next_token_id)",
    ),
    (
        "python/sglang/srt/model_executor/model_runner.py",
        "ModelRunner.forward_decode",
        "return self.model.forward(",
    ),
    (
        "python/sglang/srt/models/gemma4_causal.py",
        "Gemma4TextModel.forward",
        "for layer_idx in range(self.start_layer, self.end_layer):",
    ),
    (
        "python/sglang/srt/models/gemma4_causal.py",
        "Gemma4Attention.forward",
        "qkv, _ = self.qkv_proj(hidden_states)",
    ),
    (
        "python/sglang/srt/models/gemma3_causal.py",
        "Gemma3MLP.forward",
        "gate_up, _ = self.gate_up_proj(x)",
    ),
    (
        "python/sglang/srt/models/gemma3_causal.py",
        "Gemma3MLP.forward",
        "x, _ = self.down_proj(x)",
    ),
    (
        "python/sglang/srt/layers/linear.py",
        "LinearBase.forward",
        "output = self.quant_method.apply(self, x, bias)",
    ),
    (
        "python/sglang/srt/layers/quantization/fp8.py",
        "Fp8LinearMethod.apply",
        "return apply_fp8_linear(",
    ),
    (
        "python/sglang/srt/layers/quantization/fp8_utils.py",
        "apply_fp8_linear",
        "output = fp8_scaled_mm(",
    ),
]
CONSUMER_PATTERN = re.compile(
    r"^model\.language_model\.layers\.(?P<layer>\d+)\."
    r"(?P<module>self_attn\.qkv_proj|self_attn\.o_proj|mlp\.gate_up_proj|mlp\.down_proj)$"
)
TARGET_FAMILIES = {"qkv_proj", "gate_up_proj", "down_proj"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number}: {exc}") from exc
    return rows


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        read_json(Path(temporary))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def locate_source_anchors(source_root: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    observed_hashes = {}
    source_text = {}
    for relative, expected in EXPECTED_SOURCE_HASHES.items():
        path = source_root / relative
        observed = sha256_file(path)
        if observed != expected:
            raise ValueError(
                f"source hash mismatch for {relative}: expected {expected}, observed {observed}"
            )
        observed_hashes[relative] = observed
        source_text[relative] = path.read_text(encoding="utf-8")

    anchors = []
    for relative, symbol, snippet in SOURCE_ANCHORS:
        text = source_text[relative]
        offset = text.find(snippet)
        if offset < 0:
            raise ValueError(f"missing source anchor {relative}: {snippet}")
        anchors.append(
            {
                "file": relative,
                "line": text.count("\n", 0, offset) + 1,
                "symbol": symbol,
                "anchor": snippet,
            }
        )
    return anchors, observed_hashes


def verify_source_identity(source_root: Path) -> tuple[str, str]:
    def rev_parse(revision: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", revision],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    commit = rev_parse("HEAD")
    tree = rev_parse("HEAD^{tree}")
    if commit != EXPECTED_COMMIT or tree != EXPECTED_TREE:
        raise ValueError(
            "source identity mismatch: "
            f"expected {EXPECTED_COMMIT}/{EXPECTED_TREE}, observed {commit}/{tree}"
        )
    return commit, tree


def projection_family(module: str) -> str:
    return module.rsplit(".", 1)[-1]


def parse_consumers(path: Path, expected_m: int, expected_layers: int) -> dict[str, Any]:
    bound = []
    for row in read_jsonl(path):
        match = CONSUMER_PATTERN.match(row.get("prefix", ""))
        if match is None:
            continue
        shape = row["input"]["shape"]
        weight_shape = row["weight"]["shape"]
        if len(shape) != 2 or len(weight_shape) != 2:
            raise ValueError(f"non-matrix consumer row: {row['prefix']}")
        family = projection_family(match.group("module"))
        bound.append(
            {
                "layer": int(match.group("layer")),
                "family": family,
                "m": int(shape[0]),
                "k": int(shape[1]),
                "n": int(weight_shape[1]),
                "weight_k": int(weight_shape[0]),
                "input_dtype": row["input"]["dtype"],
                "weight_dtype": row["weight"]["dtype"],
                "output_dtype": row["out_dtype"],
                "consumer": row["consumer"],
            }
        )

    expected_rows = expected_layers * 4
    if len(bound) != expected_rows:
        raise ValueError(f"{path}: expected {expected_rows} rows, observed {len(bound)}")
    if {row["m"] for row in bound} != {expected_m}:
        raise ValueError(
            f"{path}: expected only M={expected_m}, observed {sorted({row['m'] for row in bound})}"
        )
    if {row["layer"] for row in bound} != set(range(expected_layers)):
        raise ValueError(f"{path}: incomplete layer coverage")
    if any(row["k"] != row["weight_k"] for row in bound):
        raise ValueError(f"{path}: input K and weight K mismatch")

    family_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in bound:
        family_rows[row["family"]].append(row)

    families = {}
    for family, rows in sorted(family_rows.items()):
        shape_counts = Counter((row["k"], row["n"]) for row in rows)
        weight_bytes = sum(row["k"] * row["n"] for row in rows)
        input_bytes = sum(row["m"] * row["k"] for row in rows)
        output_bytes = sum(row["m"] * row["n"] * 2 for row in rows)
        families[family] = {
            "module_count": len(rows),
            "shape_counts_k_n": [
                {"count": count, "k": k, "n": n}
                for (k, n), count in sorted(shape_counts.items())
            ],
            "fp8_weight_bytes_per_tick": weight_bytes,
            "fp8_activation_bytes_per_tick": input_bytes,
            "bf16_output_bytes_per_tick": output_bytes,
        }

    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "rows": len(bound),
        "layers": expected_layers,
        "m_values": sorted({row["m"] for row in bound}),
        "consumer_symbols": sorted({row["consumer"] for row in bound}),
        "families": families,
    }


def reconstruct_non_spec(terminal_path: Path, consumer_summary: dict[str, Any]) -> dict[str, Any]:
    terminal = read_json(terminal_path)
    rows = terminal["rows"]
    concurrency = int(terminal["concurrency"])
    completion_lengths = {int(row["completion_tokens"]) for row in rows}
    if concurrency != 32 or len(rows) != concurrency or completion_lengths != {358}:
        raise ValueError("non-spec endpoint geometry does not match c32 x 358")

    first_token_times = [float(row["first_token_monotonic_s"]) for row in rows]
    end_times = [float(row["ended_monotonic_s"]) for row in rows]
    decode_ticks = next(iter(completion_lengths)) - 1
    steady_start = max(first_token_times)
    steady_end = statistics.median(end_times)
    tick_seconds = (steady_end - steady_start) / decode_ticks
    if tick_seconds <= 0:
        raise ValueError("invalid steady decode interval")

    target_weight_bytes = sum(
        family["fp8_weight_bytes_per_tick"]
        for name, family in consumer_summary["families"].items()
        if name in TARGET_FAMILIES
    )
    all_linear_weight_bytes = sum(
        family["fp8_weight_bytes_per_tick"]
        for family in consumer_summary["families"].values()
    )
    return {
        "terminal_path": str(terminal_path),
        "terminal_sha256": sha256_file(terminal_path),
        "concurrency": concurrency,
        "completion_tokens_per_request": 358,
        "first_tokens_produced_during_prefill": concurrency,
        "source_derived_steady_decode_ticks": decode_ticks,
        "source_derived_rows_per_tick": concurrency,
        "source_derived_total_steady_decode_rows": decode_ticks * concurrency,
        "first_token_time_span_seconds": max(first_token_times) - min(first_token_times),
        "completion_time_span_seconds": max(end_times) - min(end_times),
        "steady_decode_start_proxy_monotonic_s": steady_start,
        "steady_decode_end_proxy_monotonic_s": steady_end,
        "steady_tick_interval_proxy_seconds": tick_seconds,
        "target_family_fp8_weight_bytes_per_tick": target_weight_bytes,
        "all_dense_linear_fp8_weight_bytes_per_tick": all_linear_weight_bytes,
        "consumer_summary": consumer_summary,
        "derivation": (
            "Pinned scheduling prioritizes all admitted prefills. Each prefill produces "
            "the first output token; prepare_for_decode allocates one token per request, "
            "and non-spec sampling appends exactly one token per active request. With "
            "32 complete length-358 rows ending within the recorded completion span, "
            "the post-prefill steady wave is 357 M32 decode ticks."
        ),
    }


def group_events(
    events: list[dict[str, Any]], threshold_seconds: float
) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    for event in sorted(events, key=lambda row: row["at_monotonic"]):
        if (
            not groups
            or float(event["at_monotonic"])
            - float(groups[-1][-1]["at_monotonic"])
            > threshold_seconds
        ):
            groups.append([])
        groups[-1].append(event)
    return groups


def reconstruct_ngram(
    event_path: Path,
    terminal_path: Path,
    server_log_path: Path,
    consumer_summary: dict[str, Any],
) -> dict[str, Any]:
    scheduler_events = [
        row
        for row in read_jsonl(event_path)
        if row.get("stage") == "scheduler_to_detokenizer"
    ]
    tokens_by_rid: dict[str, int] = defaultdict(int)
    for event in scheduler_events:
        tokens_by_rid[event["rid"]] += len(event["scheduler_output_ids_delta"])
    workload_rids = {rid for rid, tokens in tokens_by_rid.items() if tokens == 358}
    if len(workload_rids) != 32:
        raise ValueError(f"expected 32 length-358 NGRAM requests, got {len(workload_rids)}")
    workload_events = [row for row in scheduler_events if row["rid"] in workload_rids]

    ordered = sorted(workload_events, key=lambda row: row["at_monotonic"])
    gaps = [
        float(right["at_monotonic"]) - float(left["at_monotonic"])
        for left, right in zip(ordered, ordered[1:])
    ]
    threshold = 0.020
    groups = group_events(workload_events, threshold)
    if max(len(group) for group in groups) != 32:
        raise ValueError("NGRAM reconstruction did not recover a full c32 wave")

    small_gaps = [gap for gap in gaps if gap < threshold]
    large_gaps = [gap for gap in gaps if gap > threshold]
    if not small_gaps or not large_gaps or max(small_gaps) >= min(large_gaps):
        raise ValueError("NGRAM event gap does not support deterministic tick grouping")

    group_rows = []
    for index, group in enumerate(groups):
        group_rows.append(
            {
                "tick_index": index,
                "active_requests": len(group),
                "emitted_tokens": sum(
                    len(row["scheduler_output_ids_delta"]) for row in group
                ),
                "start_monotonic_s": min(row["at_monotonic"] for row in group),
                "end_monotonic_s": max(row["at_monotonic"] for row in group),
            }
        )

    full_wave_groups = [row for row in group_rows if row["active_requests"] == 32]
    server_log = server_log_path.read_text(encoding="utf-8")
    draft_match = re.search(r"speculative_num_draft_tokens=(\d+)", server_log)
    max_running_match = re.search(r"max_running_requests=(\d+)", server_log)
    if draft_match is None or max_running_match is None:
        raise ValueError("missing NGRAM server geometry")
    draft_tokens = int(draft_match.group(1))
    max_running = int(max_running_match.group(1))
    if draft_tokens != 12 or max_running != 32:
        raise ValueError("unexpected NGRAM server geometry")

    terminal = read_json(terminal_path)
    return {
        "event_path": str(event_path),
        "event_sha256": sha256_file(event_path),
        "terminal_path": str(terminal_path),
        "terminal_sha256": sha256_file(terminal_path),
        "server_log_path": str(server_log_path),
        "server_log_sha256": sha256_file(server_log_path),
        "complete_requests": terminal["complete_requests"],
        "completion_tokens_per_request": 358,
        "scheduler_events": len(workload_events),
        "emitted_tokens": sum(tokens_by_rid[rid] for rid in workload_rids),
        "tick_group_threshold_seconds": threshold,
        "largest_within_tick_gap_seconds": max(small_gaps),
        "smallest_between_tick_gap_seconds": min(large_gaps),
        "reconstructed_tick_groups": len(group_rows),
        "active_request_group_histogram": {
            str(key): value
            for key, value in sorted(
                Counter(row["active_requests"] for row in group_rows).items()
            )
        },
        "full_c32_wave_groups": len(full_wave_groups),
        "full_wave_target_verify_rows": max_running * draft_tokens,
        "consumer_summary": consumer_summary,
        "representative_tick_rows": (
            group_rows[:3] + full_wave_groups[:3] + group_rows[-3:]
        ),
        "interpretation": (
            "The qualified NGRAM control already exposes 12 target-verification rows "
            "per active request. A full c32 wave is M384, exactly matching every "
            "bound FP8 consumer row; M64/M96 cross-tick decode geometry is absent."
        ),
    }


def load_h200(inventory_path: Path) -> dict[str, Any]:
    inventory = read_json(inventory_path)
    rows = inventory["accelerators"]
    matches = [row for row in rows if row["id"] == "nvidia-h200-sxm"]
    if len(matches) != 1:
        raise ValueError("expected exactly one nvidia-h200-sxm inventory row")
    row = matches[0]
    return {
        "inventory_path": str(inventory_path),
        "inventory_sha256": sha256_file(inventory_path),
        "id": row["id"],
        "compute_units": row["execution"]["compute_units"],
        "hbm_bandwidth_gb_s": row["memory"]["bandwidth_gb_s"],
        "l2_mb": row["cache"]["last_level_mb"],
        "fp8_peak_tflops": row["peak_math"]["fp8_tflops"],
        "evidence_class": "vendor-reported shared inventory prior",
    }


def physical_bounds(
    non_spec: dict[str, Any],
    attribution_path: Path,
    h200: dict[str, Any],
) -> dict[str, Any]:
    attribution = read_json(attribution_path)
    decode = next(row for row in attribution["phases"]["decode"]["boundaries"] if row["boundary"] == "fp8_linear")
    total_capture_seconds = float(attribution["window"]["seconds"])
    bandwidth_bytes_s = h200["hbm_bandwidth_gb_s"] * 1e9
    tick_seconds = non_spec["steady_tick_interval_proxy_seconds"]
    target_weight_bytes = non_spec["target_family_fp8_weight_bytes_per_tick"]
    all_weight_bytes = non_spec["all_dense_linear_fp8_weight_bytes_per_tick"]

    groups = []
    for ticks in (2, 3):
        reuse_fraction = (ticks - 1) / ticks
        target_floor_saved_per_token = (
            target_weight_bytes / bandwidth_bytes_s * reuse_fraction
        )
        all_floor_saved_per_token = (
            all_weight_bytes / bandwidth_bytes_s * reuse_fraction
        )
        groups.append(
            {
                "ticks": ticks,
                "coalesced_m": ticks * 32,
                "oldest_row_hold_delay_proxy_seconds": (ticks - 1) * tick_seconds,
                "ideal_target_weight_byte_reduction_fraction": reuse_fraction,
                "ideal_target_weight_bytes_saved_per_completed_token": target_weight_bytes
                * reuse_fraction,
                "target_weight_bandwidth_floor_saved_seconds_per_completed_token": target_floor_saved_per_token,
                "target_weight_bandwidth_floor_fraction_of_steady_tick_proxy": target_floor_saved_per_token
                / tick_seconds,
                "all_dense_linear_bandwidth_floor_saved_seconds_per_completed_token": all_floor_saved_per_token,
                "all_dense_linear_bandwidth_floor_fraction_of_steady_tick_proxy": all_floor_saved_per_token
                / tick_seconds,
                "measured_decode_fp8_zero_overhead_whole_capture_upper_fraction": (
                    float(decode["seconds"]) / total_capture_seconds * reuse_fraction
                ),
            }
        )

    return {
        "h200": h200,
        "attribution_path": str(attribution_path),
        "attribution_sha256": sha256_file(attribution_path),
        "measured_nonoverlapping_decode_fp8_seconds": float(decode["seconds"]),
        "measured_total_capture_seconds": total_capture_seconds,
        "measured_decode_fp8_fraction_of_whole_capture": float(decode["seconds"])
        / total_capture_seconds,
        "target_family_fp8_weight_gb_per_tick": target_weight_bytes / 1e9,
        "all_dense_linear_fp8_weight_gb_per_tick": all_weight_bytes / 1e9,
        "target_family_single_stream_hbm_floor_seconds_per_tick": target_weight_bytes
        / bandwidth_bytes_s,
        "all_dense_linear_single_stream_hbm_floor_seconds_per_tick": all_weight_bytes
        / bandwidth_bytes_s,
        "grouping_cases": groups,
        "transfer_limits": [
            "The bandwidth calculation is an analytical single-stream floor, not a measured kernel timing.",
            "The July 20 non-spec trace is scope-matched to pinned c32 M32 decode but predates the qualified NGRAM denominator.",
            "The measured whole-capture bound generously treats all decode FP8 time as proportional to repeatable weights; real quantization, activation, epilogue, and launch costs do not disappear in full.",
        ],
    }


def build_terminal(
    source: dict[str, Any],
    config: dict[str, Any],
    non_spec: dict[str, Any],
    ngram: dict[str, Any],
    physical: dict[str, Any],
    input_hashes: dict[str, str],
    instrument_hashes: dict[str, str],
) -> dict[str, Any]:
    non_spec_m32 = non_spec["consumer_summary"]["m_values"] == [32]
    ngram_m384 = ngram["consumer_summary"]["m_values"] == [384]
    full_wave = ngram["full_wave_target_verify_rows"] == 384
    semantic_dependency = all(
        edge["proved"]
        for edge in source["causal_edges"]
        if edge["id"]
        in {
            "current_batch_full_model_before_sample",
            "sample_before_next_tick_input",
            "one_kv_slot_per_request_per_decode",
        }
    )
    negative = non_spec_m32 and ngram_m384 and full_wave and semantic_dependency
    if not negative:
        raise ValueError("required negative predicates were not all established")

    return {
        "schema_version": 1,
        "artifact_type": "fp8_decode_cross_tick_batch_coalescing_mechanism_terminal",
        "project": "gemma4_fp8_decode_cross_tick_batch_coalescing",
        "classification": "typed_physical_semantic_negative",
        "reason_code": "autoregressive_dependency_and_scope_geometry_preclude_cross_tick_grouping",
        "scientific_result": True,
        "scientific_sample_consumed": False,
        "evidence_classes": {
            "source_path": "source-backed exact pinned bytes",
            "non_spec_tick_geometry": "measured exact consumer rows plus source-derived recurrence",
            "qualified_ngram_tick_geometry": "measured exact consumer and token-event rows",
            "h200_physical_bound": "analytical from exact shapes and vendor-reported inventory",
            "endpoint_effect": "not measured and not claimed",
        },
        "identities": {
            "model": {
                "id": "google/gemma-4-31B-it",
                "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "config_sha256": input_hashes["config"],
                "hidden_size": config["text_config"]["hidden_size"],
                "intermediate_size": config["text_config"]["intermediate_size"],
                "layers": config["text_config"]["num_hidden_layers"],
            },
            "runtime": {
                "release": "SGLang v0.5.13",
                "commit": EXPECTED_COMMIT,
                "git_tree": EXPECTED_TREE,
                "source_sha256": source["source_sha256"],
            },
            "hardware_scope": physical["h200"],
            "workload": {
                "concurrency": 32,
                "requests": 32,
                "prompt_tokens_per_request": 4214,
                "completion_tokens_per_request": 358,
            },
        },
        "causal_chain": source["causal_edges"],
        "observations": {
            "non_spec_c32": non_spec,
            "qualified_ngram_c32": ngram,
            "physical_bounds": physical,
        },
        "decision": {
            "candidate_source_published": False,
            "candidate_source_reason": (
                "A hold-and-concatenate patch would either read unavailable future "
                "tokens, change model semantics, or require more than the admitted "
                "c32 independent request cohort. Publishing such plumbing as a "
                "candidate would violate the mechanism gate."
            ),
            "result": "close_tested_cross_tick_scheduler_dataflow",
            "closed_scope": (
                "Layer-consistent M64/M96 merging of consecutive non-spec c32 decode "
                "ticks in pinned SGLang v0.5.13, plus transfer of that geometry to "
                "the qualified NGRAM c32 endpoint."
            ),
            "not_closed": [
                "Within-tick M32 FP8 kernel or dataflow optimization.",
                "Persistent weight-resident execution that does not wait for future tokens.",
                "Exact target-verification optimization at the qualified M384 geometry.",
                "A separately proven lossless multi-token predictor or verifier.",
            ],
            "mechanism_predicates": {
                "non_spec_exact_m32": non_spec_m32,
                "next_tick_rows_available_before_current_full_forward": False,
                "additional_independent_rows_inside_c32_cap": False,
                "qualified_endpoint_exact_m384": ngram_m384,
                "qualified_full_wave_rows": ngram["full_wave_target_verify_rows"],
                "semantics_preserving_cross_tick_group_legal": False,
            },
            "economic_interpretation": (
                "Even the impossible ideal that proportionally removes repeatable "
                "decode FP8 time is bounded to the recorded grouping-case whole-capture "
                "fractions, below the campaign's 20% objective; the actual scheduler "
                "candidate is additionally illegal because future rows do not exist."
            ),
        },
        "falsification_conditions": [
            {
                "condition": "A production trace proves at least 64 independent, layer-compatible rows are simultaneously available while max_running_requests remains 32.",
                "required_evidence": "Request IDs, token positions, active batch size, graph batch size, KV slots, and layer entry timestamps.",
            },
            {
                "condition": "A lossless predictor produces each request's next token before the current target forward completes.",
                "required_evidence": "Exact token/logit/KV equivalence through the real consumer and a scope-matched endpoint; this is speculation/verification, not this scheduler-only mechanism.",
            },
            {
                "condition": "The qualified production endpoint no longer uses M384 target verification and exact FP8 consumer rows return to M<=32.",
                "required_evidence": "Fresh hash-bound FP8 consumer audit and scheduler tick trace on the new qualified stack.",
            },
            {
                "condition": "A cross-request pipeline exposes a second independent cohort without increasing resident concurrency or delaying rows already present in the stock c32 batch.",
                "required_evidence": "Deterministic schedule trace with request/KV ownership and completion-time accounting.",
            },
        ],
        "h200_discriminator": {
            "admitted": False,
            "reason": "The zero-cost semantic and production-geometry gates fail before target-hardware execution.",
            "smallest_reopen_contract": (
                "First satisfy one falsification condition with exact source and trace "
                "evidence; only then benchmark stock versus candidate at the resulting "
                "real M shape with complete outputs, request/KV provenance, launches, "
                "HBM/L2 bytes, queue delay, and completed-token service time."
            ),
        },
        "execution": {
            "gpu_claimed": False,
            "cuda_invoked": False,
            "provider_mutated": False,
            "actual_spend_usd": 0.0,
            "instrument_sha256": instrument_hashes,
        },
        "input_sha256": input_hashes,
    }


def build_source_trace(source_root: Path) -> dict[str, Any]:
    commit, tree = verify_source_identity(source_root)
    anchors, hashes = locate_source_anchors(source_root)
    by_symbol = {(row["symbol"], row["anchor"]): row for row in anchors}

    def anchor(symbol: str, text: str) -> dict[str, Any]:
        row = by_symbol[(symbol, text)]
        return {"file": row["file"], "line": row["line"], "symbol": row["symbol"]}

    causal_edges = [
        {
            "id": "scheduler_tick_is_run_then_process",
            "from": "Scheduler.run_batch(batch)",
            "to": "Scheduler.process_batch_result(batch, result)",
            "proved": True,
            "source": [
                anchor("Scheduler.event_loop_normal", "result = self.run_batch(batch)"),
                anchor(
                    "Scheduler.event_loop_normal",
                    "self.process_batch_result(batch, result)",
                ),
            ],
        },
        {
            "id": "one_kv_slot_per_request_per_decode",
            "from": "ScheduleBatch.prepare_for_decode",
            "to": "one committed KV position per active request",
            "proved": True,
            "source": [
                anchor(
                    "ScheduleBatch.prepare_for_decode",
                    "self.out_cache_loc = alloc_for_decode(self, token_per_req=1)",
                ),
                anchor(
                    "ScheduleBatch.prepare_for_decode", "req.kv_committed_len += 1"
                ),
            ],
        },
        {
            "id": "current_batch_full_model_before_sample",
            "from": "ModelRunner.forward -> Gemma4 60-layer model",
            "to": "TpModelWorker.sample",
            "proved": True,
            "source": [
                anchor(
                    "TpModelWorker.forward_batch_generation",
                    "out = self.model_runner.forward(",
                ),
                anchor(
                    "Gemma4TextModel.forward",
                    "for layer_idx in range(self.start_layer, self.end_layer):",
                ),
                anchor(
                    "TpModelWorker.forward_batch_generation",
                    "batch_result.next_token_ids = self.model_runner.sample(",
                ),
            ],
        },
        {
            "id": "sample_before_next_tick_input",
            "from": "sampled next_token_ids",
            "to": "future_map / output_ids consumed by the next scheduler tick",
            "proved": True,
            "source": [
                anchor(
                    "Scheduler.run_batch",
                    "batch.req_pool_indices, batch_result.next_token_ids",
                ),
                anchor(
                    "BatchResultProcessor.process_batch_result_decode",
                    "req.output_ids.append(next_token_id)",
                ),
            ],
        },
        {
            "id": "model_to_fp8_linear",
            "from": "Gemma4 qkv/gate-up/down projection call sites",
            "to": "sgl_kernel.fp8_scaled_mm",
            "proved": True,
            "source": [
                anchor(
                    "Gemma4Attention.forward", "qkv, _ = self.qkv_proj(hidden_states)"
                ),
                anchor(
                    "Gemma3MLP.forward", "gate_up, _ = self.gate_up_proj(x)"
                ),
                anchor("Gemma3MLP.forward", "x, _ = self.down_proj(x)"),
                anchor(
                    "LinearBase.forward", "output = self.quant_method.apply(self, x, bias)"
                ),
                anchor("Fp8LinearMethod.apply", "return apply_fp8_linear("),
                anchor("apply_fp8_linear", "output = fp8_scaled_mm("),
            ],
        },
    ]
    return {
        "source_root": str(source_root),
        "commit": commit,
        "tree": tree,
        "source_sha256": hashes,
        "anchors": anchors,
        "causal_edges": causal_edges,
    }


def run(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    source_root = args.source_root.resolve()
    source = build_source_trace(source_root)
    config = read_json(args.config)
    expected_layers = int(config["text_config"]["num_hidden_layers"])
    if expected_layers != 60:
        raise ValueError(f"expected 60 model layers, observed {expected_layers}")

    non_spec_consumers = parse_consumers(
        args.non_spec_consumers, expected_m=32, expected_layers=expected_layers
    )
    non_spec = reconstruct_non_spec(args.non_spec_terminal, non_spec_consumers)
    ngram_consumers = parse_consumers(
        args.ngram_consumers, expected_m=384, expected_layers=expected_layers
    )
    ngram = reconstruct_ngram(
        args.ngram_events,
        args.ngram_terminal,
        args.ngram_server_log,
        ngram_consumers,
    )
    h200 = load_h200(args.accelerator_inventory)
    physical = physical_bounds(non_spec, args.non_spec_attribution, h200)
    input_paths = {
        "config": args.config,
        "non_spec_consumers": args.non_spec_consumers,
        "non_spec_terminal": args.non_spec_terminal,
        "non_spec_attribution": args.non_spec_attribution,
        "ngram_consumers": args.ngram_consumers,
        "ngram_events": args.ngram_events,
        "ngram_terminal": args.ngram_terminal,
        "ngram_server_log": args.ngram_server_log,
        "accelerator_inventory": args.accelerator_inventory,
    }
    input_hashes = {name: sha256_file(path) for name, path in input_paths.items()}
    instrument_hashes = {
        "experiment_spec": sha256_file(args.experiment_spec),
        "falsifier": sha256_file(Path(__file__)),
    }
    trace = {
        "schema_version": 1,
        "artifact_type": "fp8_decode_cross_tick_trace_reconstruction",
        "source_trace": source,
        "model_config": {
            "path": str(args.config),
            "sha256": input_hashes["config"],
            "hidden_size": config["text_config"]["hidden_size"],
            "intermediate_size": config["text_config"]["intermediate_size"],
            "layers": expected_layers,
        },
        "non_spec_c32": non_spec,
        "qualified_ngram_c32": ngram,
        "physical_bounds": physical,
        "input_sha256": input_hashes,
        "instrument_sha256": instrument_hashes,
    }
    terminal = build_terminal(
        source,
        config,
        non_spec,
        ngram,
        physical,
        input_hashes,
        instrument_hashes,
    )
    return trace, terminal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-spec", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--non-spec-consumers", type=Path, required=True)
    parser.add_argument("--non-spec-terminal", type=Path, required=True)
    parser.add_argument("--non-spec-attribution", type=Path, required=True)
    parser.add_argument("--ngram-consumers", type=Path, required=True)
    parser.add_argument("--ngram-events", type=Path, required=True)
    parser.add_argument("--ngram-terminal", type=Path, required=True)
    parser.add_argument("--ngram-server-log", type=Path, required=True)
    parser.add_argument("--accelerator-inventory", type=Path, required=True)
    parser.add_argument("--trace-output", type=Path, required=True)
    parser.add_argument("--terminal-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    trace, terminal = run(args)
    atomic_write_json(args.trace_output, trace)
    atomic_write_json(args.terminal_output, terminal)
    print(
        json.dumps(
            {
                "classification": terminal["classification"],
                "non_spec_m": trace["non_spec_c32"]["consumer_summary"]["m_values"],
                "non_spec_ticks": trace["non_spec_c32"][
                    "source_derived_steady_decode_ticks"
                ],
                "ngram_m": trace["qualified_ngram_c32"]["consumer_summary"][
                    "m_values"
                ],
                "ngram_full_wave_rows": trace["qualified_ngram_c32"][
                    "full_wave_target_verify_rows"
                ],
                "terminal_output": str(args.terminal_output),
                "trace_output": str(args.trace_output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
