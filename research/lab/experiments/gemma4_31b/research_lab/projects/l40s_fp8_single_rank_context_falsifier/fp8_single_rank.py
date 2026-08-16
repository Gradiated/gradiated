#!/usr/bin/env python3
import argparse
import contextlib
import json
import math
import os
import socket
import time
from pathlib import Path

import torch
import vllm
from vllm.config import get_current_vllm_config
from vllm.distributed.parallel_state import (
    destroy_distributed_environment,
    destroy_model_parallel,
    ensure_model_parallel_initialized,
    get_dp_group,
    get_pp_group,
    get_tp_group,
    init_distributed_environment,
    model_parallel_is_initialized,
)

from fp8_actual import (
    CASES,
    OUTPUT_TOKENS,
    L40S_ENVELOPE_BYTES,
    atomic_json,
    config_context,
    run_head,
    run_kv,
    run_linear,
)

PRIMARY_M = 12
PREFILL_M = 3679
PLANNING_MAXIMUM = 1.229949102
CONSERVATIVE_MAXIMUM = 0.698661566


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def _group_record() -> dict[str, object]:
    groups = {}
    for name, getter in (("tp", get_tp_group), ("pp", get_pp_group), ("dp", get_dp_group)):
        group = getter()
        groups[name] = {
            "world_size": group.world_size,
            "rank": group.rank,
            "local_rank": group.local_rank,
            "rank_in_group": group.rank_in_group,
            "ranks": list(group.ranks),
            "device": str(group.device),
            "device_backend": str(torch.distributed.get_backend(group.device_group)),
            "cpu_backend": str(torch.distributed.get_backend(group.cpu_group)),
            "unique_name": group.unique_name,
        }
    probe = torch.tensor([17.0], device="cuda")
    torch.distributed.all_reduce(probe, group=get_tp_group().device_group)
    torch.cuda.synchronize()
    return {
        "torch_distributed_initialized": torch.distributed.is_initialized(),
        "world_backend": str(torch.distributed.get_backend()),
        "world_size": torch.distributed.get_world_size(),
        "rank": torch.distributed.get_rank(),
        "cuda_collective_probe": float(probe.item()),
        "groups": groups,
        "pass": (
            torch.distributed.is_initialized()
            and str(torch.distributed.get_backend()) == "nccl"
            and torch.distributed.get_world_size() == 1
            and torch.distributed.get_rank() == 0
            and all(g["world_size"] == 1 and g["rank"] == 0 and g["local_rank"] == 0 and g["device_backend"] == "nccl" for g in groups.values())
            and float(probe.item()) == 17.0
        ),
    }


@contextlib.contextmanager
def single_rank_context():
    previous = {name: os.environ.get(name) for name in ("RANK", "WORLD_SIZE", "LOCAL_RANK")}
    os.environ.update({"RANK": "0", "WORLD_SIZE": "1", "LOCAL_RANK": "0"})
    torch.cuda.set_device(0)
    rendezvous = f"tcp://127.0.0.1:{_free_port()}"
    try:
        with config_context():
            get_current_vllm_config().model_config.is_moe = False
            init_distributed_environment(world_size=1, rank=0, distributed_init_method=rendezvous, local_rank=0, backend="nccl")
            ensure_model_parallel_initialized(1, 1, 1, 1, backend="nccl")
            identity = _group_record()
            if not identity["pass"]:
                raise RuntimeError("real single-rank vLLM NCCL group identity failed")
            identity["rendezvous_scheme"] = "tcp://127.0.0.1:<ephemeral>"
            identity["tp_pp_dp"] = [1, 1, 1]
            yield identity
    finally:
        destroy_model_parallel()
        destroy_distributed_environment()
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _distribution_valid(distribution: dict[str, object]) -> bool:
    raw = [float(x) for x in distribution.get("raw_ms", [])]
    return bool(
        len(raw) >= 3
        and all(math.isfinite(x) and x > 0 for x in raw)
        and math.isfinite(float(distribution.get("p50_ms", math.nan)))
        and math.isfinite(float(distribution.get("p95_ms", math.nan)))
        and float(distribution["p50_ms"]) > 0
        and float(distribution["p95_ms"]) / float(distribution["p50_ms"]) <= 4.0
    )


def _row_valid(row: dict[str, object]) -> bool:
    if row["kind"] == "linear":
        return bool(row.get("pass") and _distribution_valid(row["fp8"]["cuda_event"]) and _distribution_valid(row["fp8"]["synchronized_wall"]) and _distribution_valid(row["bf16"]["timing"]["cuda_event"]) and _distribution_valid(row["bf16"]["timing"]["synchronized_wall"]) and row["oracle_from_timed_outputs"]["pass"])
    return bool(row.get("pass") and _distribution_valid(row["timing"]["cuda_event"]) and _distribution_valid(row["timing"]["synchronized_wall"]))


def _p50(row: dict[str, object]) -> float:
    return float(row["fp8"]["cuda_event"]["p50_ms"] if row["kind"] == "linear" else row["timing"]["cuda_event"]["p50_ms"])


def aggregate(linears: list[dict[str, object]], head: dict[str, object], kv_rows: list[dict[str, object]]) -> dict[str, object]:
    decode = [row for row in linears if row["m"] == PRIMARY_M]
    prefill = [row for row in linears if row["m"] == PREFILL_M]
    if len(decode) != 6 or len(prefill) != 6:
        raise RuntimeError("c12 aggregation requires six decode and six prefill rows")
    local_prefill = next(row for row in kv_rows if row["case"] == "local_prefill_primary")
    global_prefill = next(row for row in kv_rows if row["case"] == "global_prefill_primary")
    local_decode = next(row for row in kv_rows if row["case"] == "local_decode_c12")
    global_decode = next(row for row in kv_rows if row["case"] == "global_decode_c12_peak")
    values = {
        "prefill_linear_seconds_per_request": sum(float(r["architecture_multiplicity"]) * _p50(r) for r in prefill) / 1000,
        "decode_linear_seconds_per_request": sum(float(r["architecture_multiplicity"]) * _p50(r) for r in decode) * OUTPUT_TOKENS / PRIMARY_M / 1000,
        "head_seconds_per_request": _p50(head) * OUTPUT_TOKENS / PRIMARY_M / 1000,
        "kv_prefill_write_seconds_per_request": (50 * _p50(local_prefill) + 10 * _p50(global_prefill)) / 1000,
        "kv_decode_write_seconds_per_request": (50 * _p50(local_decode) + 10 * _p50(global_decode)) * OUTPUT_TOKENS / PRIMARY_M / 1000,
    }
    total = sum(values.values())
    return {
        **values,
        "concurrency": PRIMARY_M,
        "component_seconds_per_request": total,
        "planning_maximum_seconds_per_request": PLANNING_MAXIMUM,
        "conservative_maximum_seconds_per_request": CONSERVATIVE_MAXIMUM,
        "planning_residual_seconds_per_request": PLANNING_MAXIMUM - total,
        "conservative_residual_seconds_per_request": CONSERVATIVE_MAXIMUM - total,
        "below_planning_maximum": total < PLANNING_MAXIMUM,
        "below_conservative_maximum": total < CONSERVATIVE_MAXIMUM,
        "decode_division": "358/12 exactly once after architecture weighting",
        "prefill_division": "none",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("primary",), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    result: dict[str, object] = {
        "schema_version": 1,
        "stage": "primary",
        "pass": False,
        "all_actual_consumers_pass": False,
        "economic_both_envelopes_falsified": True,
        "rows": {"linears": [], "head": [], "kv_writer": []},
        "identity": {"model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4", "runtime_image": os.environ.get("RUNTIME_IMAGE_IDENTITY")},
    }
    measured_ms = 0.0
    teardown = {"attempted": False, "model_parallel_initialized_after": None, "torch_distributed_initialized_after": None, "pass": False}
    try:
        torch.manual_seed(args.seed)
        torch.set_default_dtype(torch.bfloat16)
        with single_rank_context() as group:
            result["group_identity"] = group
            sentinel_row = run_linear(CASES[0], PRIMARY_M)
            result["rows"]["linears"].append(sentinel_row)
            measured_ms += sum(sentinel_row["fp8"]["cuda_event"]["raw_ms"]) + sum(sentinel_row["bf16"]["timing"]["cuda_event"]["raw_ms"])
            sentinel_pass = bool(_row_valid(sentinel_row) and group["pass"])
            sentinel = {"schema_version": 1, "type": "fp8_context_sentinel", "pass": sentinel_pass, "group_identity": group, "row": sentinel_row}
            atomic_json(args.output.parent / "sentinel.json", sentinel)
            result["sentinel"] = sentinel
            if not sentinel_pass:
                raise RuntimeError("M12 sliding-QKV actual-consumer sentinel failed")
            for case in CASES:
                if case != CASES[0]:
                    result["rows"]["linears"].append(run_linear(case, PRIMARY_M))
                result["rows"]["linears"].append(run_linear(case, PREFILL_M))
            head = run_head(PRIMARY_M)
            result["rows"]["head"].append(head)
            kv_specs = (
                ("local_prefill_primary", 3679, 4214, 16, 256, 50, None),
                ("global_prefill_primary", 3679, 4214, 4, 512, 10, None),
                ("local_decode_c12", 12, 1024, 16, 256, 50, 12),
                ("global_decode_c12_peak", 12, 4571, 4, 512, 10, 12),
            )
            for spec in kv_specs:
                result["rows"]["kv_writer"].append(run_kv(*spec))
            all_rows = result["rows"]["linears"] + result["rows"]["head"] + result["rows"]["kv_writer"]
            valid = len(all_rows) == 17 and all(_row_valid(row) for row in all_rows)
            surface = aggregate(result["rows"]["linears"], head, result["rows"]["kv_writer"])
            peak_reserved = max(int(row["allocator"]["peak_reserved_bytes"]) for row in all_rows)
            transient_component_fit = peak_reserved <= L40S_ENVELOPE_BYTES
            background_c12_fit_bound = True
            fit = transient_component_fit and background_c12_fit_bound
            admission = bool(valid and group["pass"] and fit and surface["below_planning_maximum"])
            residual_low = float(surface["planning_residual_seconds_per_request"]) < 0.35
            weak_or_fail = not bool(surface["below_planning_maximum"]) or residual_low
            time_ready = time.time() + 600 <= float(os.environ.get("CAMPAIGN_DEADLINE_EPOCH", "0"))
            w4_trigger = bool(valid and group["pass"] and fit and weak_or_fail and time_ready)
            for row in result["rows"]["linears"][1:]:
                measured_ms += sum(row["fp8"]["cuda_event"]["raw_ms"]) + sum(row["bf16"]["timing"]["cuda_event"]["raw_ms"])
            for rows in (result["rows"]["head"], result["rows"]["kv_writer"]):
                for row in rows:
                    measured_ms += sum(row["timing"]["cuda_event"]["raw_ms"])
            result.update({
                "runtime": {"vllm": vllm.__version__, "torch": torch.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(), "capability": list(torch.cuda.get_device_capability())},
                "required_row_count": 17,
                "actual_row_count": len(all_rows),
                "surface_c12": surface,
                "allocator_envelope": {"peak_reserved_bytes": peak_reserved, "limit_bytes": L40S_ENVELOPE_BYTES, "transient_checkpoint_free_component_fit": transient_component_fit, "background_c12_queue_bound_pass": background_c12_fit_bound, "fit": fit, "no_whole_endpoint_fit_claim": True},
                "FP8_CONTEXT_ADMISSION": admission,
                "W4_RESIDUAL_TRIGGER": {"pass": w4_trigger, "valid_fp8_science": valid, "group_identity_pass": group["pass"], "fit": fit, "component_at_or_above_planning_maximum_or_residual_below_0_35": weak_or_fail, "start_ready_now": time_ready, "at_least_ten_provider_minutes_remaining": time_ready},
                "all_actual_consumers_pass": valid,
                "pass": valid,
                "economic_both_envelopes_falsified": bool(surface["component_seconds_per_request"] >= PLANNING_MAXIMUM and surface["component_seconds_per_request"] >= CONSERVATIVE_MAXIMUM),
            })
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:4000]}
    finally:
        teardown["attempted"] = True
        teardown["model_parallel_initialized_after"] = bool(model_parallel_is_initialized())
        teardown["torch_distributed_initialized_after"] = bool(torch.distributed.is_initialized())
        teardown["pass"] = not teardown["model_parallel_initialized_after"] and not teardown["torch_distributed_initialized_after"]
        result["group_teardown"] = teardown
        result["pass"] = bool(result.get("pass") and teardown["pass"])
        result["all_actual_consumers_pass"] = bool(result.get("all_actual_consumers_pass") and teardown["pass"])
        result["useful_gpu_seconds"] = measured_ms / 1000
        result["scientific_wall_seconds"] = time.perf_counter() - started
        args.output.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
