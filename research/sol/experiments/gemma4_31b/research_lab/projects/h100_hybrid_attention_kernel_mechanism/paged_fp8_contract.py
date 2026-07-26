#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PAGE_SIZE = 16
OUTPUT_STEPS = 358
FIRST_GLOBAL_CONTEXT = 4214
LAST_GLOBAL_CONTEXT = 4571
LOCAL_LAYERS = 50
GLOBAL_LAYERS = 10
WHOLE_REQUEST_HURDLE_SECONDS = 0.027398761575976767
MIN_COMPONENT_SAVING_FRACTION = 0.10
MAX_FP8_DRAM_FRACTION = 0.60
MIN_COSINE = 0.99
MAX_NRMSE = 0.05
MIN_RESERVE_SECONDS = 7 * 60
WARMUPS = 20
REPETITIONS = 100

EXPECTED_IMAGE = (
    "docker.io/vllm/vllm-openai:gemma4@"
    "sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
)
EXPECTED_VLLM_VERSION = "0.19.1.dev6+g6d4a8e6d2"
EXPECTED_VLLM_REVISION = "6d4a8e6d2"
EXPECTED_SOURCE_HASHES = {
    "vllm/model_executor/layers/attention/attention.py":
        "2e45ac35100a1396bd03f9fe8d7f3e4dd41f3dc0a78b3bc7e5e118b536a0fe3c",
    "vllm/forward_context.py":
        "b3927fa778b1522c45b8a85e32be745c73ac5002a72d6b245f6d0cc028ddf57f",
    "vllm/config/vllm.py":
        "58aebc9654b3d62c9707be62df47ac43254b52218d9ea38c43d3026485ff9e01",
    "vllm/v1/attention/backend.py":
        "2ac9b29dcc36ae643162f6e28f502081073cd97a6844e7d19fff2c10ee0d6810",
    "vllm/v1/attention/backends/flash_attn.py":
        "38ae47c9eb4e6ab774ef4397015f45a2d05001f8b220a2347be86e57bbf54aa7",
    "vllm/v1/attention/backends/triton_attn.py":
        "0881156d666e81642879a943dc14fda1186060bc24676280497428a8e3c079a3",
}
EXPECTED_SIGNATURE_PARAMETERS = {
    "set_current_vllm_config": (
        "vllm_config", "check_compile", "prefix",
    ),
    "metadata_builder_init": (
        "self", "kv_cache_spec", "layer_names", "vllm_config", "device",
    ),
    "metadata_builder_build": (
        "self", "common_prefix_len", "common_attn_metadata", "fast_build",
    ),
    "unified_kv_cache_update": ("key", "value", "layer_name"),
    "unified_attention_with_output": (
        "query",
        "key",
        "value",
        "output",
        "layer_name",
        "output_scale",
        "output_block_scale",
        "kv_cache_dummy_dep",
    ),
}
REQUIRED_NCU_METRICS = (
    "dram__bytes_read.sum",
    "lts__t_bytes.sum",
    "sm__cycles_elapsed.avg",
    "sm__warps_active.avg.pct_of_peak_sustained_active",
)


@dataclass(frozen=True)
class Case:
    name: str
    context: int
    q_heads: int
    kv_heads: int
    head_dim: int
    layer_count: int
    sliding_window: int | None

    @property
    def family(self) -> str:
        return "local" if self.sliding_window is not None else "global"


CASES = {
    "local1024": Case("local1024", 1024, 32, 16, 256, 50, 1024),
    "global4214": Case("global4214", 4214, 32, 4, 512, 10, None),
    "global4393": Case("global4393", 4393, 32, 4, 512, 10, None),
    "global4571": Case("global4571", 4571, 32, 4, 512, 10, None),
}
SENTINEL_CASES = ("local1024", "global4214")
CONCURRENCIES = (8, 16, 32)


class ContractError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def full_slot_mapping(case: Case, concurrency: int) -> list[int]:
    pages_per_request = math.ceil(case.context / PAGE_SIZE)
    return [
        request * pages_per_request * PAGE_SIZE + token
        for request in range(concurrency)
        for token in range(case.context)
    ]


def decode_slot_mapping(case: Case, concurrency: int) -> list[int]:
    pages_per_request = math.ceil(case.context / PAGE_SIZE)
    return [
        request * pages_per_request * PAGE_SIZE + case.context - 1
        for request in range(concurrency)
    ]


def block_table(case: Case, concurrency: int) -> list[list[int]]:
    pages_per_request = math.ceil(case.context / PAGE_SIZE)
    return [
        list(
            range(
                request * pages_per_request,
                (request + 1) * pages_per_request,
            )
        )
        for request in range(concurrency)
    ]


def balanced_pair_orders(repetitions: int, seed: int) -> list[tuple[str, str]]:
    if repetitions % 2:
        raise ContractError("paired repetitions must be even")
    orders = [("bf16", "fp8_e4m3")] * (repetitions // 2)
    orders += [("fp8_e4m3", "bf16")] * (repetitions // 2)
    import random

    random.Random(seed).shuffle(orders)
    return orders


def _number(value: str) -> float:
    cleaned = value.strip().replace(",", "").replace("%", "")
    try:
        parsed = float(cleaned)
    except ValueError as exc:
        raise ContractError(f"non-numeric NCU value: {value!r}") from exc
    if not math.isfinite(parsed):
        raise ContractError(f"non-finite NCU value: {value!r}")
    return parsed


def parse_ncu_csv(path: Path, expected_range: str) -> dict[str, Any]:
    lines = [
        line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.lstrip().startswith('"')
    ]
    if not lines:
        raise ContractError("NCU CSV has no quoted table rows")
    rows = list(csv.DictReader(lines))
    if not rows or "Metric Name" not in rows[0]:
        raise ContractError("NCU CSV is missing the Metric Name column")

    values: dict[str, list[float]] = {name: [] for name in REQUIRED_NCU_METRICS}
    launches: set[tuple[str, str, str]] = set()
    for row in rows:
        metric = (row.get("Metric Name") or "").strip()
        if metric not in values:
            continue
        values[metric].append(_number(row.get("Metric Value") or ""))
        launches.add(
            (
                (row.get("ID") or "").strip(),
                (row.get("Kernel Name") or "").strip(),
                (row.get("Stream") or "").strip(),
            )
        )
    missing = [metric for metric, samples in values.items() if not samples]
    if missing:
        raise ContractError(f"NCU CSV missing metrics: {missing}")
    if not launches:
        raise ContractError("NCU CSV has no captured kernel launches")

    cycles = values["sm__cycles_elapsed.avg"]
    warps = values["sm__warps_active.avg.pct_of_peak_sustained_active"]
    cycle_weight = sum(cycles)
    achieved_warps = (
        sum(value * cycle for value, cycle in zip(warps, cycles)) / cycle_weight
        if cycle_weight > 0 else statistics.fmean(warps)
    )
    return {
        "schema_version": 1,
        "range": expected_range,
        "pass": True,
        "dram_bytes_read": sum(values["dram__bytes_read.sum"]),
        "l2_bytes": sum(values["lts__t_bytes.sum"]),
        "sm_cycles": sum(cycles),
        "achieved_active_warps_pct": achieved_warps,
        "kernel_launch_count": len(launches),
        "metrics": {name: samples for name, samples in values.items()},
    }


def validate_counter(counter: dict[str, Any], expected_range: str) -> None:
    if not counter.get("pass"):
        raise ContractError("counter record is not passing")
    if counter.get("range") != expected_range:
        raise ContractError("counter range does not match the timed arm")
    for name in (
        "dram_bytes_read",
        "l2_bytes",
        "sm_cycles",
        "achieved_active_warps_pct",
        "kernel_launch_count",
    ):
        value = counter.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ContractError(f"missing or non-finite counter {name}")
        if value < 0:
            raise ContractError(f"negative counter {name}")
    if counter["dram_bytes_read"] <= 0 or counter["kernel_launch_count"] <= 0:
        raise ContractError("counter capture contains no decision-bearing work")


def validate_oracles(oracles: dict[str, Any]) -> None:
    independent = oracles.get("bf16_vs_reference", {})
    representation = oracles.get("fp8_vs_bf16", {})
    for name, oracle in (
        ("bf16_vs_reference", independent),
        ("fp8_vs_bf16", representation),
    ):
        if not oracle.get("finite") or not oracle.get("nonzero"):
            raise ContractError(f"{name} is zero or non-finite")
        if oracle.get("cosine", -math.inf) < MIN_COSINE:
            raise ContractError(f"{name} cosine is below {MIN_COSINE}")
        if oracle.get("normalized_rmse", math.inf) > MAX_NRMSE:
            raise ContractError(f"{name} NRMSE is above {MAX_NRMSE}")


def evaluate_row(row: dict[str, Any]) -> dict[str, Any]:
    expected_range = lambda arm: (
        f"h100_paged_fp8::{row['case']}::c{row['concurrency']}::{arm}"
    )
    if row.get("producer_slots") != row.get("concurrency") * row.get("context"):
        raise ContractError("producer did not populate the complete context")
    if not row.get("native_trace", {}).get("pass"):
        raise ContractError("registered native construction trace is absent")
    validate_oracles(row.get("oracles", {}))
    bf16_counter = row.get("counters", {}).get("bf16", {})
    fp8_counter = row.get("counters", {}).get("fp8_e4m3", {})
    validate_counter(bf16_counter, expected_range("bf16"))
    validate_counter(fp8_counter, expected_range("fp8_e4m3"))
    bf16_ms = row.get("timing", {}).get("bf16", {}).get(
        "serialized_cuda_event_interval_union_ms_p50"
    )
    fp8_ms = row.get("timing", {}).get("fp8_e4m3", {}).get(
        "serialized_cuda_event_interval_union_ms_p50"
    )
    if not all(isinstance(value, (int, float)) and value > 0 for value in (bf16_ms, fp8_ms)):
        raise ContractError("paired timing is missing or non-positive")
    saving_fraction = (bf16_ms - fp8_ms) / bf16_ms
    dram_fraction = fp8_counter["dram_bytes_read"] / bf16_counter["dram_bytes_read"]
    launch_match = (
        fp8_counter["kernel_launch_count"] == bf16_counter["kernel_launch_count"]
    )
    passed = (
        saving_fraction >= MIN_COMPONENT_SAVING_FRACTION
        and dram_fraction <= MAX_FP8_DRAM_FRACTION
        and launch_match
    )
    return {
        "pass": passed,
        "saving_ms_per_batch_step": bf16_ms - fp8_ms,
        "saving_fraction": saving_fraction,
        "dram_fraction": dram_fraction,
        "launch_count_match": launch_match,
    }


def evaluate_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    evaluated = []
    for row in rows:
        result = evaluate_row(row)
        evaluated.append({**row, "evaluation": result, "pass": result["pass"]})
    return evaluated


def _linear_value(points: dict[int, float], context: int) -> float:
    ordered = sorted(points)
    if context < ordered[0] or context > ordered[-1]:
        raise ContractError("global context is outside measured interpolation range")
    if context in points:
        return points[context]
    upper = next(value for value in ordered if value > context)
    lower = ordered[ordered.index(upper) - 1]
    fraction = (context - lower) / (upper - lower)
    return points[lower] + fraction * (points[upper] - points[lower])


def aggregate_economics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    by_concurrency: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not row.get("pass"):
            raise ContractError("economic aggregation cannot consume a failed row")
        concurrency = int(row["concurrency"])
        bucket = by_concurrency.setdefault(
            concurrency, {"local": None, "global": {}}
        )
        saving_seconds_per_request_layer_step = (
            row["evaluation"]["saving_ms_per_batch_step"] / 1000.0 / concurrency
        )
        if row["family"] == "local":
            bucket["local"] = saving_seconds_per_request_layer_step
        else:
            bucket["global"][int(row["context"])] = saving_seconds_per_request_layer_step

    results = {}
    for concurrency in CONCURRENCIES:
        bucket = by_concurrency.get(concurrency)
        if bucket is None or bucket["local"] is None:
            raise ContractError(f"missing local row for c{concurrency}")
        required_contexts = {4214, 4393, 4571}
        if set(bucket["global"]) != required_contexts:
            raise ContractError(f"missing global rows for c{concurrency}")
        global_saving = sum(
            _linear_value(bucket["global"], context)
            for context in range(FIRST_GLOBAL_CONTEXT, LAST_GLOBAL_CONTEXT + 1)
        )
        local_saving = bucket["local"] * LOCAL_LAYERS * OUTPUT_STEPS
        global_saving *= GLOBAL_LAYERS
        total = local_saving + global_saving
        results[f"c{concurrency}"] = {
            "local_seconds_per_request": local_saving,
            "global_seconds_per_request": global_saving,
            "total_seconds_per_request": total,
            "hurdle_seconds_per_request": WHOLE_REQUEST_HURDLE_SECONDS,
            "pass": total >= WHOLE_REQUEST_HURDLE_SECONDS,
        }
    return {
        "schema_version": 1,
        "method": "50 local layers * 358 steps plus 10 global layers over "
                  "contexts 4214..4571 using piecewise-linear interpolation",
        "by_concurrency": results,
        "pass": all(result["pass"] for result in results.values()),
    }


def assert_context_byte_trend(rows: Iterable[dict[str, Any]]) -> None:
    grouped: dict[int, list[tuple[int, float]]] = {}
    for row in rows:
        if row["family"] != "global":
            continue
        reduction = (
            row["counters"]["bf16"]["dram_bytes_read"]
            - row["counters"]["fp8_e4m3"]["dram_bytes_read"]
        )
        grouped.setdefault(int(row["concurrency"]), []).append(
            (int(row["context"]), reduction)
        )
    for concurrency, samples in grouped.items():
        ordered = sorted(samples)
        if len(ordered) != 3:
            raise ContractError(f"global context sweep incomplete at c{concurrency}")
        reductions = [value for _, value in ordered]
        if not reductions[0] < reductions[1] < reductions[2]:
            raise ContractError(
                f"DRAM byte reduction does not increase with context at c{concurrency}"
            )


def remaining_seconds(deadline_utc: str, now: datetime | None = None) -> float:
    deadline = datetime.fromisoformat(deadline_utc.replace("Z", "+00:00"))
    current = now or datetime.now(timezone.utc)
    return (deadline - current).total_seconds()


def sentinel_continuation(
    rows: Iterable[dict[str, Any]],
    deadline_utc: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    evaluated = evaluate_rows(rows)
    names = {(row["case"], row["concurrency"]) for row in evaluated}
    expected = {(name, 8) for name in SENTINEL_CASES}
    reserve = remaining_seconds(deadline_utc, now)
    passed = (
        names == expected
        and all(row["pass"] for row in evaluated)
        and reserve >= MIN_RESERVE_SECONDS
    )
    return {
        "pass": passed,
        "conditional_sweep_allowed": passed,
        "remaining_seconds": reserve,
        "minimum_reserve_seconds": MIN_RESERVE_SECONDS,
        "rows": evaluated,
    }
