#!/usr/bin/env python3
"""Validate retrieved DFlash CUDA-event costs and select a fixed c32 depth."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any


DEPTHS = (4, 8, 12, 16)
EXPECTED_ROWS = {4: 300, 8: 358, 12: 287, 16: 359}
EXPECTED_OBSERVER_SHA256 = (
    "c8d75000e6923b0db882a5c54414185663865fe464df6fbe6548d8bdab4f4573"
)
PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358
CONCURRENCY = 32


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(values: list[float]) -> dict[str, float | int]:
    center = median(values)
    ordered = sorted(values)
    trim = math.floor(len(ordered) * 0.1)
    trimmed = ordered[trim : len(ordered) - trim] if trim else ordered
    return {
        "count": len(values),
        "sum_ms": sum(values),
        "mean_ms": mean(values),
        "trimmed_mean_10pct_ms": mean(trimmed),
        "minimum_ms": ordered[0],
        "p10_ms": quantile(ordered, 0.10),
        "p25_ms": quantile(ordered, 0.25),
        "median_ms": center,
        "p75_ms": quantile(ordered, 0.75),
        "p90_ms": quantile(ordered, 0.90),
        "maximum_ms": ordered[-1],
        "median_absolute_deviation_ms": median(
            [abs(value - center) for value in values]
        ),
    }


def load_rows(path: Path, depth: int) -> list[dict[str, float | int]]:
    rows = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"timings_jsonl.line_{line_number}") from exc
        if set(row) != {"depth", "draft_ms", "verifier_ms"}:
            raise ValueError(f"timings_jsonl.line_{line_number}.fields")
        if row["depth"] != depth:
            raise ValueError(f"timings_jsonl.line_{line_number}.depth")
        for field in ("draft_ms", "verifier_ms"):
            value = row[field]
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"timings_jsonl.line_{line_number}.{field}")
            if value < 0:
                raise ValueError(f"timings_jsonl.line_{line_number}.{field}")
        if row["verifier_ms"] <= 0:
            raise ValueError(f"timings_jsonl.line_{line_number}.verifier_ms")
        rows.append(row)
    return rows


def validate_request_producer(depth_root: Path) -> dict[str, Any]:
    workload = json.loads((depth_root / "request" / "WORKLOAD.json").read_text())
    terminal = json.loads((depth_root / "request" / "TERMINAL.json").read_text())
    if workload.get("prompt_tokens") != PROMPT_TOKENS:
        raise ValueError("request.WORKLOAD.prompt_tokens")
    if workload.get("output_tokens") != OUTPUT_TOKENS:
        raise ValueError("request.WORKLOAD.output_tokens")
    if workload.get("concurrency") != CONCURRENCY:
        raise ValueError("request.WORKLOAD.concurrency")
    if terminal.get("concurrency") != CONCURRENCY:
        raise ValueError("request.TERMINAL.concurrency")
    rows = terminal.get("rows")
    if not isinstance(rows, list) or len(rows) != CONCURRENCY:
        raise ValueError("request.TERMINAL.rows")
    for index, row in enumerate(rows):
        if row.get("prompt_tokens") != PROMPT_TOKENS:
            raise ValueError(f"request.TERMINAL.rows.{index}.prompt_tokens")
        if row.get("completion_tokens") != OUTPUT_TOKENS:
            raise ValueError(f"request.TERMINAL.rows.{index}.completion_tokens")
        error = row.get("error")
        if not isinstance(error, str) or not error.startswith("JSONDecodeError:"):
            raise ValueError(f"request.TERMINAL.rows.{index}.error")
        response = depth_root / "request" / f"response-{index:02d}.sse"
        if not response.read_bytes().rstrip().endswith(b"data: [DONE]"):
            raise ValueError(f"request.response_{index:02d}.done_frame")
    if terminal.get("pass") is not False:
        raise ValueError("request.TERMINAL.pass")
    if terminal.get("complete_requests") != 0:
        raise ValueError("request.TERMINAL.complete_requests")
    return {
        "classification": "invalid_stream_consumer_separate_from_cost_validity",
        "terminal_pass": False,
        "complete_requests": 0,
        "json_decode_error_rows": CONCURRENCY,
        "producer_rows_with_bound_token_metadata": CONCURRENCY,
        "responses_with_done_frame": CONCURRENCY,
        "use_restriction": (
            "The metadata and terminal frames establish the fixed producer budget "
            "only. They do not authorize endpoint latency, output-token identity, "
            "text quality, or deterministic-equivalence claims."
        ),
    }


def validate_depth(root: Path, depth: int) -> dict[str, Any]:
    depth_root = root / f"depth-{depth}"
    observer = depth_root / "oracle" / "sitecustomize.py"
    observer_digest = sha256(observer)
    if observer_digest != EXPECTED_OBSERVER_SHA256:
        raise ValueError("oracle.sitecustomize_sha256")
    server_log = (depth_root / "server.log").read_text()
    if "skip_server_warmup=True" not in server_log:
        raise ValueError("server_args.skip_server_warmup")
    if f"speculative_num_draft_tokens={depth}" not in server_log:
        raise ValueError("server_args.speculative_num_draft_tokens")

    timing_path = depth_root / "timings.jsonl"
    rows = load_rows(timing_path, depth)
    if len(rows) != EXPECTED_ROWS[depth]:
        raise ValueError("timings_jsonl.row_count")
    paired = [
        row for row in rows if row["draft_ms"] > 0 and row["verifier_ms"] > 0
    ]
    zero_draft = [
        index
        for index, row in enumerate(rows)
        if row["draft_ms"] == 0 and row["verifier_ms"] > 0
    ]
    if not paired:
        raise ValueError("timings_jsonl.paired_rows")
    if any(row["draft_ms"] > 0 and row["verifier_ms"] == 0 for row in rows):
        raise ValueError("timings_jsonl.draft_without_verifier")
    first_paired = paired[0]
    if first_paired["draft_ms"] != max(row["draft_ms"] for row in paired):
        raise ValueError("timings_jsonl.first_paired_draft_not_cold_maximum")

    admitted = paired[1:]
    if not admitted:
        raise ValueError("timings_jsonl.post_warmup_paired_rows")
    draft = [float(row["draft_ms"]) for row in admitted]
    verifier = [float(row["verifier_ms"]) for row in admitted]
    combined = [draft_ms + verifier_ms for draft_ms, verifier_ms in zip(draft, verifier)]
    return {
        "depth": depth,
        "inputs": {
            "timings_jsonl": str(timing_path),
            "timings_jsonl_sha256": sha256(timing_path),
            "observer_sha256": observer_digest,
            "server_log_sha256": sha256(depth_root / "server.log"),
            "request_terminal_sha256": sha256(
                depth_root / "request" / "TERMINAL.json"
            ),
        },
        "sample_counts": {
            "all_rows": len(rows),
            "zero_draft_target_only_prefill_rows": len(zero_draft),
            "paired_decode_rows": len(paired),
            "warmup_rows_excluded": 1,
            "statistical_outlier_rows_excluded": 0,
            "controller_rows": len(admitted),
        },
        "zero_draft": {
            "row_indices": zero_draft,
            "classification": (
                "target-only prefill calls in the same outer DFlash worker hook; "
                "queued prefills may be interleaved with decode"
            ),
            "controller_admitted": False,
        },
        "warmup_and_outliers": {
            "warmup_policy": (
                "Exclude the first paired decode row from each fresh server because "
                "--skip-server-warmup was set and that row has the maximum measured "
                "draft time at every depth."
            ),
            "excluded_warmup": {
                "draft_ms": first_paired["draft_ms"],
                "verifier_ms": first_paired["verifier_ms"],
            },
            "outlier_policy": (
                "Retain every later finite positive paired row. The distribution is "
                "multimodal under changing live-batch geometry, and the immutable "
                "observer did not record a batch-size label that would justify "
                "deleting a timing plateau as noise."
            ),
        },
        "robust_summary": {
            "draft": summarize(draft),
            "verifier": summarize(verifier),
            "draft_plus_verifier": summarize(combined),
        },
        "request_consumer": validate_request_producer(depth_root),
    }


def build_terminal(root: Path) -> dict[str, Any]:
    first_invalid_field = None
    depth_rows = []
    try:
        for depth in DEPTHS:
            depth_rows.append(validate_depth(root, depth))
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        first_invalid_field = (
            str(exc)
            if isinstance(exc, ValueError)
            else f"{type(exc).__name__}: {exc}"
        )

    controller = None
    if first_invalid_field is None:
        fixed_output_tokens = CONCURRENCY * OUTPUT_TOKENS
        choices = []
        for row in depth_rows:
            total_ms = row["robust_summary"]["draft_plus_verifier"]["sum_ms"]
            choices.append(
                {
                    "depth": row["depth"],
                    "validated_draft_plus_verifier_cuda_event_ms": total_ms,
                    "fixed_producer_output_tokens": fixed_output_tokens,
                    "normalized_tokens_per_cuda_event_second": (
                        fixed_output_tokens / total_ms * 1000
                    ),
                }
            )
        choices.sort(
            key=lambda row: row["validated_draft_plus_verifier_cuda_event_ms"]
        )
        winner, runner_up = choices[:2]
        controller = {
            "objective": (
                "For the fixed 32 x 358-token producer budget, maximize committed "
                "output tokens per summed cycle-aligned draft-plus-verifier CUDA-"
                "event time; equivalently minimize the validated summed CUDA-event "
                "cost. Prefill, HTTP wall time, and failed stream parsing are outside "
                "this controller."
            ),
            "decision_basis": "measured_full_c32_producer_decode_cost",
            "choices": choices,
            "selected_depth": winner["depth"],
            "runner_up_depth": runner_up["depth"],
            "winner_cost_margin_fraction": (
                runner_up["validated_draft_plus_verifier_cuda_event_ms"]
                / winner["validated_draft_plus_verifier_cuda_event_ms"]
                - 1
            ),
            "decision": "select_depth_4_for_next_director_bound_endpoint_pair",
            "production_authorized": False,
            "endpoint_pair_authorized": False,
        }

    return {
        "schema_version": 1,
        "classification": "dflash_c32_depth_cost_validity_terminal",
        "pass": first_invalid_field is None,
        "first_invalid_field": first_invalid_field,
        "oracle_gate": {
            "path": "DFLASH_CYCLE_ORACLE_TERMINAL.json",
            "sha256": (
                "0a4a51ad2df17b92ff839c7adb51cb089594d2d83b808d621b3e9f7a0b3322fd"
            ),
            "cycles_evaluated": 112,
            "pass": True,
            "replayed": False,
        },
        "cost_scope": {
            "hardware": "nvidia-h200-sxm",
            "runtime": "SGLang 588d1f7bc9424201f89957e145f9d5af633a3eb8",
            "target": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "draft": (
                "z-lab/gemma-4-31B-it-DFlash@"
                "eabd648301ce28583cc14757912e5e0f84e152e1"
            ),
            "measurement": (
                "CUDA events around the draft-model forward and target-verifier "
                "forward within one DFlashWorkerV2.forward_batch_generation call"
            ),
            "cycle_alignment": (
                "A positive draft and verifier pair is emitted from one outer worker "
                "invocation. The bound runtime decode branch contains one draft "
                "forward followed by one target verification forward."
            ),
            "excludes": [
                "target-only prefill rows",
                "the first cold paired decode row per fresh server",
                "HTTP and scheduler wall time",
                "endpoint latency",
                "quality and token-equivalence inference from the c32 request files",
            ],
        },
        "input_root": str(root),
        "depths": depth_rows,
        "controller": controller,
        "provider_spend": {
            "phase_actual_spend_usd": 2.9737686855138894,
            "offline_validation_turn_new_spend_usd": 0.0,
            "authorized_phase_ceiling_usd": 4.0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    terminal = build_terminal(args.input_root)
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    return 0 if terminal["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
