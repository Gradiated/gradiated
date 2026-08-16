#!/usr/bin/env python3

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
LAB_DIR = PROJECT_DIR.parent.parent
WORKSPACE_DIR = LAB_DIR.parents[4]

GEOMETRY_PATH = LAB_DIR / "projects/exact_geometry_runtime_opportunities/GEOMETRY.json"
COMPONENT_PATH = LAB_DIR / "projects/h200_bf16_exact_linear_floor/artifacts/RECONCILED_TERMINAL.json"
ECONOMIC_GATE_PATH = LAB_DIR / "projects/h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json"
INVENTORY_PATH = WORKSPACE_DIR / "research/factory/data/accelerator_inventory.json"
OUTPUT_PATH = PROJECT_DIR / "KV_ATTENTION_FLOOR.json"

CONCURRENCIES = (16, 32)
H100_BANDWIDTH_GB_S = 3350
K_EQ_V_SPECIALIZED_ROWS = 18_432
STOCK_GLOBAL_QKV_ROWS = 20_480
K_EQ_V_PROMOTION_THRESHOLD_FRACTION = 0.05


def load_json(path: Path):
    return json.loads(path.read_text())


def sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def selected_step_row(
    label,
    context_position,
    batch,
    local_layers,
    global_layers,
    local_window,
    kv_bytes_per_token_layer,
    l2_bytes,
    h200_bandwidth_bytes_s,
):
    local_tokens = min(context_position, local_window)
    read_bytes_per_request = kv_bytes_per_token_layer * (
        local_layers * local_tokens + global_layers * context_position
    )
    batch_read_bytes = batch * read_bytes_per_request
    optimistic_hbm_read_bytes = max(0, batch_read_bytes - l2_bytes)
    return {
        "label": label,
        "context_position_tokens": context_position,
        "local_tokens_read_per_layer_per_request": local_tokens,
        "global_tokens_read_per_layer_per_request": context_position,
        "read_bytes_per_request": read_bytes_per_request,
        "batch_read_bytes": batch_read_bytes,
        "optimistic_hbm_read_bytes_after_full_l2_credit": optimistic_hbm_read_bytes,
        "h200_optimistic_step_seconds": optimistic_hbm_read_bytes / h200_bandwidth_bytes_s,
        "h200_zero_l2_step_seconds": batch_read_bytes / h200_bandwidth_bytes_s,
    }


def main():
    geometry = load_json(GEOMETRY_PATH)
    component = load_json(COMPONENT_PATH)
    gate = load_json(ECONOMIC_GATE_PATH)
    inventory = load_json(INVENTORY_PATH)

    target = geometry["identities"]["target_model"]
    text_geometry = geometry["target_text_geometry_measured_from_config"]
    derived = geometry["derived_geometry"]
    economic = component["economic_gate"]
    gate_identity = gate["identities"]
    h200 = next(item for item in inventory["accelerators"] if item["id"] == "nvidia-h200-sxm")
    h100 = next(item for item in inventory["accelerators"] if item["id"] == "nvidia-h100-sxm")

    model = target["id"].lower()
    revision = target["revision"]
    prompt_tokens = derived["primary_prompt_tokens"]
    output_tokens = economic["workload"]["output_tokens"]
    local_layers = text_geometry["attention_pattern"]["sliding_attention_layers"]
    global_layers = text_geometry["attention_pattern"]["full_attention_layers"]
    local_window = text_geometry["sliding_window_tokens"]
    sliding_kv_bytes = derived["sliding_kv_bytes_per_token_per_layer"]
    global_kv_bytes = derived["global_kv_bytes_per_token_per_layer"]
    total_layers = text_geometry["num_hidden_layers"]
    h200_bandwidth_gb_s = h200["memory"]["bandwidth_gb_s"]
    h200_bandwidth_bytes_s = h200_bandwidth_gb_s * 1_000_000_000
    h100_bandwidth_gb_s = h100["memory"]["bandwidth_gb_s"]
    h100_bandwidth_bytes_s = h100_bandwidth_gb_s * 1_000_000_000
    l2_mib = h200["cache"]["last_level_mb"]
    l2_bytes = l2_mib * 1024 * 1024

    assertions = {
        "exact_model": model == economic["model"].lower() == gate_identity["model"].lower(),
        "exact_revision": revision == economic["revision"] == gate_identity["revision"],
        "exact_workload": (
            prompt_tokens == economic["workload"]["prompt_tokens"]
            == gate_identity["workload_campaign_mix"]["prompt_tokens"]
            and output_tokens == 358
            == gate_identity["workload_campaign_mix"]["output_tokens"]
        ),
        "exact_layer_pattern": local_layers == 50 and global_layers == 10 and total_layers == 60,
        "exact_local_window": local_window == 1024,
        "equal_exact_kv_bytes": sliding_kv_bytes == global_kv_bytes == 8192,
        "h200_inventory_prior": h200_bandwidth_gb_s == 4800 and l2_mib == 50,
        "h100_sensitivity_prior": h100_bandwidth_gb_s == H100_BANDWIDTH_GB_S,
        "component_terminal_complete": component["status"] == "complete",
    }
    if not all(assertions.values()):
        raise RuntimeError(f"identity assertion failed: {assertions}")

    contexts = list(range(prompt_tokens, prompt_tokens + output_tokens))
    midpoint_low_index = output_tokens // 2 - 1
    midpoint_high_index = output_tokens // 2
    selected_positions = (
        ("first", contexts[0]),
        ("median_low", contexts[midpoint_low_index]),
        ("median_high", contexts[midpoint_high_index]),
        ("last", contexts[-1]),
    )
    writes_per_request_per_step = total_layers * sliding_kv_bytes

    operating_points = []
    component_by_m = {row["m"]: row for row in component["combined_cuda_event_component_floor"]}
    primary_path = COMPONENT_PATH.parent / component["source_artifacts"]["primary_stage"]["path"]
    primary = load_json(primary_path)
    primary_rows = primary["terminal"]["result"]["rows"]

    strict_ceiling = economic["planning_base_total_service_ceiling_seconds_per_request"]["strict"]
    lenient_ceiling = economic["planning_base_total_service_ceiling_seconds_per_request"]["lenient"]

    for batch in CONCURRENCIES:
        selected_rows = [
            selected_step_row(
                label,
                context,
                batch,
                local_layers,
                global_layers,
                local_window,
                sliding_kv_bytes,
                l2_bytes,
                h200_bandwidth_bytes_s,
            )
            for label, context in selected_positions
        ]

        per_request_read_by_step = [
            sliding_kv_bytes * (
                local_layers * min(context, local_window) + global_layers * context
            )
            for context in contexts
        ]
        batch_read_by_step = [batch * item for item in per_request_read_by_step]
        optimistic_hbm_by_step = [max(0, item - l2_bytes) for item in batch_read_by_step]
        total_read_bytes_per_request = sum(per_request_read_by_step)
        total_batch_read_bytes = sum(batch_read_by_step)
        total_optimistic_hbm_bytes = sum(optimistic_hbm_by_step)
        total_l2_credit_bytes = total_batch_read_bytes - total_optimistic_hbm_bytes

        h200_optimistic_request_seconds = total_optimistic_hbm_bytes / h200_bandwidth_bytes_s / batch
        h200_zero_l2_request_seconds = total_batch_read_bytes / h200_bandwidth_bytes_s / batch
        h100_zero_l2_request_seconds = total_batch_read_bytes / h100_bandwidth_bytes_s / batch
        component_seconds = component_by_m[batch]["combined_seconds_per_request_358_steps"]

        residuals = {}
        for label, ceiling in (("strict", strict_ceiling), ("lenient", lenient_ceiling)):
            residual_request_seconds = ceiling - component_seconds
            residual_step_seconds = residual_request_seconds * batch / output_tokens
            combined_floor_seconds = component_seconds + h200_optimistic_request_seconds
            residuals[label] = {
                "whole_service_ceiling_seconds_per_request": ceiling,
                "whole_service_ceiling_average_batch_step_seconds": ceiling * batch / output_tokens,
                "measured_linears_plus_head_seconds_per_request": component_seconds,
                "measured_linears_plus_head_average_batch_step_seconds": component_seconds * batch / output_tokens,
                "positive_residual_seconds_per_request": max(0.0, residual_request_seconds),
                "positive_residual_average_batch_step_seconds": max(0.0, residual_step_seconds),
                "combined_linears_head_plus_optimistic_kv_seconds_per_request": combined_floor_seconds,
                "kv_floor_exceeds_positive_residual": (
                    residual_request_seconds > 0
                    and h200_optimistic_request_seconds > residual_request_seconds
                ),
                "combined_floor_exceeds_ceiling": combined_floor_seconds > ceiling,
            }

        global_qkv_row = next(
            row for row in primary_rows if row["shape"] == "global_qkv" and row["m"] == batch
        )
        width_removed_fraction = (
            STOCK_GLOBAL_QKV_ROWS - K_EQ_V_SPECIALIZED_ROWS
        ) / STOCK_GLOBAL_QKV_ROWS
        projected_per_layer_saving_ms = global_qkv_row["cuda_event_ms"]["p50"] * width_removed_fraction
        projected_architecture_step_saving_ms = projected_per_layer_saving_ms * global_layers
        projected_request_saving_seconds = (
            projected_architecture_step_saving_ms / 1000 * output_tokens / batch
        )
        projected_market_fraction = projected_request_saving_seconds / strict_ceiling

        operating_points.append({
            "batch_concurrency": batch,
            "selected_decode_steps": selected_rows,
            "aggregate_reads": {
                "total_read_bytes_per_request": total_read_bytes_per_request,
                "total_batch_read_bytes": total_batch_read_bytes,
                "full_l2_credit_bytes_over_request": total_l2_credit_bytes,
                "optimistic_h200_hbm_read_bytes_over_batch_request": total_optimistic_hbm_bytes,
            },
            "new_kv_writes_reported_separately": {
                "bytes_per_request_per_step": writes_per_request_per_step,
                "bytes_per_batch_per_step": writes_per_request_per_step * batch,
                "bytes_per_request_over_358_steps": writes_per_request_per_step * output_tokens,
                "included_in_primary_falsifier": False,
            },
            "bandwidth_floors_seconds_per_request": {
                "h200_4_8_tb_s_full_50_mib_l2_credit_each_step": h200_optimistic_request_seconds,
                "h200_4_8_tb_s_zero_l2_credit": h200_zero_l2_request_seconds,
                "h100_3_35_tb_s_zero_l2_credit_sensitivity": h100_zero_l2_request_seconds,
            },
            "residual_comparison": residuals,
            "primary_classification": (
                "falsified_by_optimistic_kv_read_floor"
                if residuals["strict"]["kv_floor_exceeds_positive_residual"]
                and residuals["lenient"]["kv_floor_exceeds_positive_residual"]
                else "preserved_not_proven"
            ),
            "k_eq_v_specialized_qkv_screen": {
                "evidence_type": "source_bound_optimistic_projection_from_measured_cuda_event_p50",
                "stock_executed_global_qkv_rows": STOCK_GLOBAL_QKV_ROWS,
                "specialized_global_qkv_rows": K_EQ_V_SPECIALIZED_ROWS,
                "width_removed_fraction": width_removed_fraction,
                "measured_stock_global_qkv_cuda_event_p50_ms_per_layer": global_qkv_row["cuda_event_ms"]["p50"],
                "global_layer_count": global_layers,
                "optimistic_projection_rule": "credit removed width fraction against the entire measured stock global-QKV p50; no kernel efficiency penalty",
                "projected_architecture_step_saving_ms": projected_architecture_step_saving_ms,
                "projected_request_saving_seconds": projected_request_saving_seconds,
                "fraction_of_strict_market_service_time": projected_market_fraction,
                "promotion_threshold_fraction": K_EQ_V_PROMOTION_THRESHOLD_FRACTION,
                "reaches_promotion_threshold": projected_market_fraction >= K_EQ_V_PROMOTION_THRESHOLD_FRACTION,
                "classification": (
                    "nominate_for_cuda_measurement"
                    if projected_market_fraction >= K_EQ_V_PROMOTION_THRESHOLD_FRACTION
                    else "closed_below_5_percent_market_service_time"
                ),
            },
        })

    artifact = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
        "evidence_type": "deterministic_exact_geometry_analytical_physical_lower_bound",
        "scope": "BF16 KV-cache reads for exact 4214/358 decode geometry at c16/c32; not an endpoint, kernel-efficiency, latency, or quality measurement",
        "identities": {
            "model": model,
            "revision": revision,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "decode_context_positions_inclusive": [contexts[0], contexts[-1]],
            "local_layers": local_layers,
            "global_layers": global_layers,
            "local_window_tokens": local_window,
            "kv_bytes_per_token_per_layer": sliding_kv_bytes,
            "h200_bandwidth_gb_s_decimal": h200_bandwidth_gb_s,
            "h200_l2_mib_binary_credit_per_batch_step": l2_mib,
            "h100_bandwidth_gb_s_decimal_sensitivity": h100_bandwidth_gb_s,
        },
        "source_artifacts": {
            "geometry": {"path": str(GEOMETRY_PATH), "sha256": sha256(GEOMETRY_PATH)},
            "linears_head_terminal": {"path": str(COMPONENT_PATH), "sha256": sha256(COMPONENT_PATH)},
            "economic_gate": {"path": str(ECONOMIC_GATE_PATH), "sha256": sha256(ECONOMIC_GATE_PATH)},
            "accelerator_inventory": {"path": str(INVENTORY_PATH), "sha256": sha256(INVENTORY_PATH)},
            "primary_stage_for_qkv_rows": {"path": str(primary_path), "sha256": sha256(primary_path)},
        },
        "identity_assertions": assertions,
        "formulas": {
            "context_position": "prompt_tokens + decode_index, for decode_index in [0, output_tokens-1]",
            "read_bytes_per_request_per_step": "8192 * (50 * min(context_position, 1024) + 10 * context_position)",
            "batch_read_bytes_per_step": "batch * read_bytes_per_request_per_step",
            "optimistic_h200_hbm_bytes_per_step": "max(0, batch_read_bytes_per_step - 50 * 1024^2)",
            "bandwidth_floor_seconds_per_request": "sum(hbm_bytes_per_step) / bandwidth_bytes_per_second / batch",
            "new_kv_write_bytes_per_request_per_step": "60 * 8192; excluded from primary read-only falsifier",
            "linears_head_average_batch_step_seconds": "measured_seconds_per_request * batch / 358",
            "residual_average_batch_step_seconds": "(whole_service_ceiling_seconds_per_request - measured_seconds_per_request) * batch / 358",
            "qkv_projection": "measured stock global-QKV p50 * 10 global layers * (20480-18432)/20480 * 358/batch",
        },
        "operating_points": operating_points,
        "decision": {
            "c16": operating_points[0]["primary_classification"],
            "c32": operating_points[1]["primary_classification"],
            "k_eq_v_specialization": "closed_below_5_percent_market_service_time",
            "batch_scaling_interpretation": "Raw KV bytes per request are identical at c16 and c32; batch-step traffic scales linearly. The fixed full-L2 credit amortizes less per request at c32, so the deliberately optimistic HBM floor is marginally higher per request there.",
            "evidence_boundary": "A preserved point only survives this compulsory-read lower bound. Real attention compute, achieved bandwidth, KV writes, paging, competing weight traffic, prefill, scheduler, and service overhead can only add work relative to the primary bound.",
        },
    }
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(json.dumps(artifact["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
