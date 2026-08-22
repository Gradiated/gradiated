#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Work:
    static_bf16_params: int
    routed_expert_params_per_expert: int
    routed_active_params: int
    total_params: int
    active_params: int
    flops: float
    bf16_flops: float
    mxfp4_flops: float
    weight_bytes: float
    kda_state_bytes: float
    kda_state_traffic_bytes: float
    mla_cache_read_bytes: float
    mla_cache_write_bytes: float
    attnres_traffic_bytes: float
    activation_spill_bytes: float
    network_bytes: float
    network_messages: int
    expected_unique_experts_per_layer: float
    operation_ledger: list[dict[str, Any]]


def _matrix(name: str, occurrences: int, params_each: int, precision: str) -> dict[str, Any]:
    return {
        "name": name,
        "occurrences": occurrences,
        "params_each": params_each,
        "active_params": occurrences * params_each,
        "flops_per_token": 2 * occurrences * params_each,
        "precision": precision,
        "dependency": "sequential_by_layer",
        "parallelism": "output_rows_and_reduction_tiles; batch tokens",
    }


def parameter_ledger(m: dict[str, Any]) -> list[dict[str, Any]]:
    h = m["hidden"]
    heads = m["attention_heads"]
    d = m["kda_head_dim"]
    proj = heads * d
    qdim = m["qk_nope_head_dim"] + m["qk_rope_head_dim"]
    kda = 3 * h * proj + h * d + d * proj + h * heads + h * proj + proj * h
    mla = (
        h * m["q_lora_rank"]
        + m["q_lora_rank"] * heads * qdim
        + h * (m["kv_lora_rank"] + m["qk_rope_head_dim"])
        + m["kv_lora_rank"] * heads * (m["qk_nope_head_dim"] + m["v_head_dim"])
        + h * heads * m["v_head_dim"]
        + heads * m["v_head_dim"] * h
    )
    dense_ffn = 3 * h * m["dense_intermediate"]
    latent = 2 * h * m["latent_moe_hidden"]
    shared = 3 * h * m["expert_intermediate"] * m["shared_experts"]
    router = h * m["experts"]
    expert = 3 * m["latent_moe_hidden"] * m["expert_intermediate"]
    lm_head = h * m["vocab"]
    embedding = lm_head
    ledger = [
        _matrix("kda_projections_gates_output", m["kda_layers"], kda, "bf16"),
        _matrix("mla_projections_gate_output", m["mla_layers"], mla, "bf16"),
        _matrix("first_dense_ffn", m["dense_layers"], dense_ffn, "bf16"),
        _matrix("latent_moe_down_up", m["layers"] - m["dense_layers"], latent, "bf16"),
        _matrix("shared_experts", m["layers"] - m["dense_layers"], shared, "bf16"),
        _matrix("routers", m["layers"] - m["dense_layers"], router, "bf16"),
        _matrix("lm_head", 1, lm_head, "bf16"),
        {
            **_matrix("token_embedding_resident_not_scanned", 1, embedding, "bf16"),
            "active_params": h,
            "flops_per_token": 0,
            "dependency": "first",
        },
        {
            **_matrix("routed_expert_inventory", (m["layers"] - m["dense_layers"]) * m["experts"], expert, "mxfp4"),
            "active_params": (m["layers"] - m["dense_layers"]) * m["experts_per_token"] * expert,
            "flops_per_token": 2 * (m["layers"] - m["dense_layers"]) * m["experts_per_token"] * expert,
            "parallelism": "selected experts, expert rows, reduction tiles, batch tokens",
        },
    ]
    return ledger


def build_work(m: dict[str, Any], batch: int, context: int, machine: dict[str, Any]) -> Work:
    ledger = parameter_ledger(m)
    routed = next(row for row in ledger if row["name"] == "routed_expert_inventory")
    embedding = next(row for row in ledger if row["name"] == "token_embedding_resident_not_scanned")
    static_rows = [row for row in ledger if row["precision"] == "bf16" and row is not embedding]
    static_params = sum(row["occurrences"] * row["params_each"] for row in static_rows)
    routed_total_params = routed["occurrences"] * routed["params_each"]
    total_params = static_params + embedding["params_each"] + routed_total_params
    routed_active_params = routed["active_params"]
    active_params = static_params + m["hidden"] + routed_active_params
    bf16_flops = 2.0 * static_params * batch
    mxfp4_flops = 2.0 * routed_active_params * batch
    mla_context_flops = batch * 4 * context * m["mla_layers"] * m["attention_heads"] * m["v_head_dim"]
    elementwise_flops = batch * (
        m["kda_layers"] * m["attention_heads"] * m["kda_head_dim"] ** 2 * 4
        + m["layers"] * m["hidden"] * 30
    ) + mla_context_flops
    unique_experts = m["experts"] * (1.0 - (1.0 - m["experts_per_token"] / m["experts"]) ** batch)
    expert_storage_bytes = routed["params_each"] * (
        0.5 + m["mxfp4_scale_bytes"] / m["mxfp4_group_size"]
    )
    weight_bytes = (
        static_params * m["bf16_bytes"]
        + unique_experts * expert_storage_bytes * (m["layers"] - m["dense_layers"])
        + batch * m["hidden"] * m["bf16_bytes"]
    )
    kda_state_per_request = (
        m["kda_layers"] * m["attention_heads"] * m["kda_head_dim"] ** 2 * m["kda_state_bytes_per_element"]
    )
    kda_conv_per_request = (
        m["kda_layers"]
        * 3
        * m["attention_heads"]
        * m["kda_head_dim"]
        * (m["kda_conv_kernel"] - 1)
        * m["bf16_bytes"]
    )
    kda_state_bytes = batch * (kda_state_per_request + kda_conv_per_request)
    state_sram = machine["chips"] * machine["sram_mb_per_chip"] * 1_000_000 * machine["state_sram_fraction"]
    state_hit = min(1.0, state_sram / max(kda_state_bytes, 1.0))
    kda_state_traffic = 2.0 * kda_state_bytes * (1.0 - state_hit)
    mla_entry = (m["kv_lora_rank"] + m["qk_rope_head_dim"]) * m["mla_cache_bytes_per_element"]
    mla_read = batch * context * m["mla_layers"] * mla_entry
    mla_write = batch * m["mla_layers"] * mla_entry
    attnres = batch * m["layers"] * 2 * m["attnres_sources"] * m["hidden"] * m["bf16_bytes"]
    activation_spill = (
        batch
        * m["layers"]
        * m["hidden"]
        * m["bf16_bytes"]
        * max(0.0, machine["kernels_per_layer"] - 1.0)
        * 2.0
    )
    stages = mode_stages(machine["mode"])
    tp = machine["chips"] // stages
    if tp > 1:
        collective_factor = 2.0 * (tp - 1) / tp
        collective_bytes = batch * m["layers"] * 2 * m["hidden"] * m["bf16_bytes"] * collective_factor
        collective_messages = m["layers"] * 2
    else:
        collective_bytes = 0.0
        collective_messages = 0
    if machine["mode"] == "tensor_expert_parallel":
        unique_destinations = machine["chips"] * (1.0 - (1.0 - 1.0 / machine["chips"]) ** m["experts_per_token"])
        dispatch_bytes = (
            batch
            * (m["layers"] - m["dense_layers"])
            * unique_destinations
            * m["latent_moe_hidden"]
            * m["mxfp8_bytes"]
            * 2
        )
        dispatch_messages = (m["layers"] - m["dense_layers"]) * 2
    else:
        dispatch_bytes = 0.0
        dispatch_messages = 0
    pipeline_bytes = max(0, stages - 1) * batch * m["hidden"] * m["bf16_bytes"]
    network_bytes = collective_bytes + dispatch_bytes + pipeline_bytes
    network_messages = collective_messages + dispatch_messages + max(0, stages - 1)
    ledger.extend(
        [
            {
                "name": "kda_recurrent_update",
                "occurrences": m["kda_layers"],
                "flops_per_token": m["kda_layers"] * m["attention_heads"] * m["kda_head_dim"] ** 2 * 4,
                "state_bytes_per_request": kda_state_per_request + kda_conv_per_request,
                "hbm_read_write_bytes_per_batch": kda_state_traffic,
                "dependency": "after KDA projections; before output projection",
                "parallelism": "heads and 128x128 state tiles",
                "sram_required_to_avoid_transfer_bytes": kda_state_bytes,
            },
            {
                "name": "mla_context_attention",
                "occurrences": m["mla_layers"],
                "flops_per_token": 4 * context * m["mla_layers"] * m["attention_heads"] * m["v_head_dim"],
                "hbm_read_bytes_per_batch": mla_read,
                "hbm_write_bytes_per_batch": mla_write,
                "dependency": "after MLA projections; sequential by layer",
                "parallelism": "heads, context tiles, batch tokens",
            },
            {
                "name": "attention_residual_mix",
                "occurrences": m["layers"] * 2,
                "flops_per_token": m["layers"] * 2 * m["attnres_sources"] * m["hidden"] * 3,
                "logical_read_write_bytes_per_batch": attnres,
                "dependency": "before each attention and FFN sublayer",
                "parallelism": "hidden lanes and batch tokens",
                "sram_required_to_avoid_transfer_bytes": batch * m["attnres_sources"] * m["hidden"] * m["bf16_bytes"],
            },
        ]
    )
    return Work(
        static_bf16_params=static_params,
        routed_expert_params_per_expert=routed["params_each"],
        routed_active_params=routed_active_params,
        total_params=total_params,
        active_params=active_params,
        flops=bf16_flops + mxfp4_flops + elementwise_flops,
        bf16_flops=bf16_flops + elementwise_flops,
        mxfp4_flops=mxfp4_flops,
        weight_bytes=weight_bytes,
        kda_state_bytes=kda_state_bytes,
        kda_state_traffic_bytes=kda_state_traffic,
        mla_cache_read_bytes=mla_read,
        mla_cache_write_bytes=mla_write,
        attnres_traffic_bytes=attnres,
        activation_spill_bytes=activation_spill,
        network_bytes=network_bytes,
        network_messages=network_messages,
        expected_unique_experts_per_layer=unique_experts,
        operation_ledger=ledger,
    )


def mode_stages(mode: str) -> int:
    return {"tensor_expert_parallel": 1, "tp2_pp4": 4, "pipeline8": 8}[mode]


def cache_capacity_bytes(m: dict[str, Any], context: int) -> float:
    kda = m["kda_layers"] * m["attention_heads"] * m["kda_head_dim"] ** 2 * m["kda_state_bytes_per_element"]
    conv = (
        m["kda_layers"] * 3 * m["attention_heads"] * m["kda_head_dim"] * (m["kda_conv_kernel"] - 1) * m["bf16_bytes"]
    )
    mla = context * m["mla_layers"] * (m["kv_lora_rank"] + m["qk_rope_head_dim"]) * m["mla_cache_bytes_per_element"]
    attnres = m["attnres_sources"] * m["hidden"] * m["bf16_bytes"]
    return kda + conv + mla + attnres


def raw_evaluate(m: dict[str, Any], machine: dict[str, Any], concurrency: int, context: int) -> dict[str, Any]:
    stages = mode_stages(machine["mode"])
    microbatches = min(stages, concurrency)
    microbatch = math.ceil(concurrency / microbatches)
    work = build_work(m, microbatch, context, machine)
    chips_per_stage = machine["chips"] / stages
    stage_fraction = 1.0 / stages
    hbm_bytes = (
        work.weight_bytes
        + work.kda_state_traffic_bytes
        + work.mla_cache_read_bytes
        + work.mla_cache_write_bytes
        + work.activation_spill_bytes
    ) * stage_fraction
    sram_bytes = (2.0 * work.kda_state_bytes + work.attnres_traffic_bytes) * stage_fraction
    bf16_seconds = work.bf16_flops * stage_fraction / (
        chips_per_stage * machine["bf16_pf_per_chip"] * 1e15 * machine["compute_efficiency_decode"]
    )
    mxfp4_seconds = work.mxfp4_flops * stage_fraction / (
        chips_per_stage * machine["mxfp4_pf_per_chip"] * 1e15 * machine["compute_efficiency_decode"]
    )
    compute_seconds = bf16_seconds + mxfp4_seconds
    hbm_seconds = hbm_bytes / (
        chips_per_stage * machine["hbm_tb_s_per_chip"] * 1e12 * machine["hbm_efficiency"]
    )
    sram_seconds = sram_bytes / (chips_per_stage * machine["sram_tb_s_per_chip"] * 1e12)
    network_seconds = work.network_bytes * stage_fraction / (
        max(1.0, chips_per_stage) * machine["fabric_tb_s_per_chip"] * 1e12 * machine["fabric_efficiency"]
    ) + work.network_messages * stage_fraction * machine["collective_latency_us"] * 1e-6
    launches = m["layers"] * machine["kernels_per_layer"] * stage_fraction + 1
    launch_seconds = launches * machine["launch_latency_us"] * 1e-6
    stage_seconds = max(compute_seconds, hbm_seconds, sram_seconds) + network_seconds + launch_seconds
    steady_tpot_seconds = stages * stage_seconds
    total_capacity = machine["chips"] * machine["hbm_gb_per_chip"] * 1e9 * 0.90
    required_capacity = m["checkpoint_bytes"] + concurrency * cache_capacity_bytes(m, context)
    feasible = required_capacity <= total_capacity
    throughput = concurrency / steady_tpot_seconds if feasible else 0.0
    return {
        "machine": machine["id"],
        "mode": machine["mode"],
        "evidence": machine["evidence"],
        "concurrency": concurrency,
        "microbatch": microbatch,
        "pipeline_stages": stages,
        "context_tokens": context,
        "feasible_capacity": feasible,
        "required_capacity_gb": required_capacity / 1e9,
        "usable_capacity_gb": total_capacity / 1e9,
        "expected_unique_experts_per_layer": work.expected_unique_experts_per_layer,
        "flops_per_output_token": work.flops / microbatch,
        "weight_bytes_per_output_token": work.weight_bytes / microbatch,
        "mla_cache_read_bytes_per_output_token": work.mla_cache_read_bytes / microbatch,
        "kda_state_bytes_per_request": work.kda_state_bytes / microbatch,
        "kda_hbm_traffic_bytes_per_output_token": work.kda_state_traffic_bytes / microbatch,
        "arithmetic_intensity_flops_per_hbm_byte": work.flops
        / max(1.0, work.weight_bytes + work.kda_state_traffic_bytes + work.mla_cache_read_bytes),
        "resource_seconds_per_stage": {
            "compute": compute_seconds,
            "hbm": hbm_seconds,
            "sram": sram_seconds,
            "network": network_seconds,
            "launch": launch_seconds,
        },
        "raw_tpot_ms": steady_tpot_seconds * 1e3,
        "raw_output_tokens_per_second": throughput,
        "bottleneck": max(
            (("compute", compute_seconds), ("hbm", hbm_seconds), ("sram", sram_seconds)),
            key=lambda row: row[1],
        )[0],
    }


def calibrate(spec: dict[str, Any], machines: dict[str, dict[str, Any]]) -> dict[str, float]:
    cal = spec["calibration"]
    control = machines[cal["machine"]]
    row = raw_evaluate(spec["model"], control, cal["batch"], cal["context_tokens"])
    raw_tps = row["raw_output_tokens_per_second"]
    return {
        cal["machine"]: raw_tps / cal["measured_output_tokens_per_second"]
    }


def ownership_hourly_cost(machine: dict[str, Any], economics: dict[str, Any], capex_usd: float | None = None) -> float | None:
    capex = machine.get("target_capex_usd") if capex_usd is None else capex_usd
    if capex is None:
        return None
    productive_hours = economics["asset_life_years"] * 8760.0 * economics["productive_utilization"]
    annual_productive_hours = 8760.0 * economics["productive_utilization"]
    capital = capex / productive_hours
    maintenance = (
        capex * economics["annual_maintenance_fraction_of_capex"] / annual_productive_hours
    )
    electricity = (
        machine["system_power_w"]
        / 1000.0
        * economics["pue"]
        * economics["electricity_usd_per_kwh"]
    )
    return capital + maintenance + electricity + economics["other_active_usd_per_hour"]


def max_capex_for_hourly_cost(machine: dict[str, Any], economics: dict[str, Any], hourly_cost: float) -> float:
    non_capital = (
        machine["system_power_w"]
        / 1000.0
        * economics["pue"]
        * economics["electricity_usd_per_kwh"]
        + economics["other_active_usd_per_hour"]
    )
    coefficient = 1.0 / (
        economics["asset_life_years"] * 8760.0 * economics["productive_utilization"]
    ) + economics["annual_maintenance_fraction_of_capex"] / (
        8760.0 * economics["productive_utilization"]
    )
    return max(0.0, (hourly_cost - non_capital) / coefficient)


def speed_floor_pass(row: dict[str, Any], workload: dict[str, Any]) -> bool:
    speed = workload["decent_speed"]
    if not row["feasible_capacity"]:
        return False
    if row["concurrency"] == 1:
        return row["tpot_ms"] <= speed["c1_max_tpot_ms"]
    if row["concurrency"] == 128:
        return (
            row["tpot_ms"] <= speed["c128_max_tpot_ms"]
            and row["output_tokens_per_second"] >= speed["c128_min_output_tokens_per_second"]
        )
    return True


def evaluate(spec: dict[str, Any]) -> dict[str, Any]:
    m = spec["model"]
    machines = {machine["id"]: machine for machine in spec["machines"]}
    scales = calibrate(spec, machines)
    rows = []
    for machine in spec["machines"]:
        scale = scales.get(machine["id"], 1.0)
        for concurrency in spec["workload"]["concurrencies"]:
            row = raw_evaluate(m, machine, concurrency, spec["workload"]["decode_context_tokens"])
            row["calibration_latency_scale"] = scale
            row["tpot_ms"] = row["raw_tpot_ms"] * scale
            row["output_tokens_per_second"] = (
                row["raw_output_tokens_per_second"] / scale if row["feasible_capacity"] else 0.0
            )
            row["tokens_per_joule"] = row["output_tokens_per_second"] / machine["system_power_w"]
            row["speed_floor_pass"] = speed_floor_pass(row, spec["workload"])
            row["tiles_per_chip"] = machine.get("tiles_per_chip")
            row["sram_kb_per_tile"] = machine.get("sram_kb_per_tile")
            rows.append(row)
    control_id = spec["calibration"]["machine"]
    by_key = {(row["machine"], row["concurrency"]): row for row in rows}
    economics = spec["economics"]
    b300_cloud_hourly = (
        economics["b300_secure_cloud_usd_per_gpu_hour"] * economics["b300_cloud_gpu_count"]
    )
    for row in rows:
        machine = machines[row["machine"]]
        owned_hourly = ownership_hourly_cost(machine, economics)
        row["target_owned_hourly_cost_usd"] = owned_hourly
        row["target_owned_dollars_per_million_output_tokens"] = (
            owned_hourly / (row["output_tokens_per_second"] * 3600.0) * 1e6
            if owned_hourly is not None and row["output_tokens_per_second"] > 0
            else None
        )
        control = by_key[(control_id, row["concurrency"])]
        control_tps = control["output_tokens_per_second"]
        row["b300_secure_cloud_hourly_cost_usd"] = b300_cloud_hourly
        row["b300_secure_cloud_dollars_per_million_output_tokens"] = (
            b300_cloud_hourly / (control_tps * 3600.0) * 1e6 if control_tps > 0 else None
        )
        break_even_hourly = (
            b300_cloud_hourly * row["output_tokens_per_second"] / control_tps
            if control_tps > 0
            else 0.0
        )
        row["break_even_active_hourly_cost_vs_b300_cloud_usd"] = break_even_hourly
        row["break_even_capex_vs_b300_cloud_usd"] = max_capex_for_hourly_cost(
            machine, economics, break_even_hourly
        )
    comparisons = []
    for row in rows:
        if row["machine"] == control_id:
            continue
        control = by_key[(control_id, row["concurrency"])]
        comparisons.append(
            {
                "candidate": row["machine"],
                "concurrency": row["concurrency"],
                "throughput_ratio_vs_b300": row["output_tokens_per_second"] / control["output_tokens_per_second"]
                if control["output_tokens_per_second"] > 0
                else None,
                "raw_physical_throughput_ratio_vs_b300": row["raw_output_tokens_per_second"]
                / control["raw_output_tokens_per_second"]
                if control["raw_output_tokens_per_second"] > 0
                else None,
                "tokens_per_joule_ratio_vs_b300": row["tokens_per_joule"] / control["tokens_per_joule"]
                if control["tokens_per_joule"] > 0
                else None,
                "raw_physical_tokens_per_joule_ratio_vs_b300": (
                    row["raw_output_tokens_per_second"] / machines[row["machine"]]["system_power_w"]
                ) / (control["raw_output_tokens_per_second"] / machines[control_id]["system_power_w"])
                if control["raw_output_tokens_per_second"] > 0
                else None,
                "candidate_tpot_ms": row["tpot_ms"],
                "control_tpot_ms": control["tpot_ms"],
                "target_owned_dollars_per_million_output_tokens": row[
                    "target_owned_dollars_per_million_output_tokens"
                ],
                "b300_secure_cloud_dollars_per_million_output_tokens": row[
                    "b300_secure_cloud_dollars_per_million_output_tokens"
                ],
                "break_even_capex_vs_b300_cloud_usd": row["break_even_capex_vs_b300_cloud_usd"],
                "claim_class": "synthetic_model_comparison",
            }
        )
    sensitivity = []
    base = dict(machines["streamtile_e12_economy"])
    for field, values in {
        "hbm_efficiency": [0.55, 0.65, 0.72, 0.78, 0.82],
        "hbm_tb_s_per_chip": [2.0, 2.5, 3.0, 4.0, 5.33],
        "compute_efficiency_decode": [0.35, 0.50, 0.65, 0.72, 0.80],
        "sram_mb_per_chip": [72, 144, 288, 576],
        "fabric_tb_s_per_chip": [0.25, 0.5, 1.0, 2.0],
        "collective_latency_us": [0.2, 0.35, 0.75, 1.5],
        "launch_latency_us": [0.05, 0.08, 0.3, 1.0],
    }.items():
        for value in values:
            candidate = dict(base)
            candidate[field] = value
            row = raw_evaluate(m, candidate, 128, spec["workload"]["decode_context_tokens"])
            control = by_key[(control_id, 128)]
            sensitivity.append({
                "field": field,
                "value": value,
                "raw_output_tokens_per_second": row["raw_output_tokens_per_second"],
                "raw_physical_ratio_vs_b300": row["raw_output_tokens_per_second"] / control["raw_output_tokens_per_second"],
                "bottleneck": row["bottleneck"],
                "claim_class": "synthetic_one_factor_sensitivity",
            })
    objective_concurrency = economics["objective_concurrency"]
    cost_frontier = []
    for machine in spec["machines"]:
        if machine.get("target_capex_usd") is None:
            continue
        row = by_key[(machine["id"], objective_concurrency)]
        cost_frontier.append(
            {
                "machine": machine["id"],
                "target_capex_usd": machine["target_capex_usd"],
                "target_owned_hourly_cost_usd": row["target_owned_hourly_cost_usd"],
                "target_owned_dollars_per_million_output_tokens": row[
                    "target_owned_dollars_per_million_output_tokens"
                ],
                "output_tokens_per_second": row["output_tokens_per_second"],
                "tpot_ms": row["tpot_ms"],
                "speed_floor_pass": row["speed_floor_pass"],
                "feasible_capacity": row["feasible_capacity"],
                "break_even_capex_vs_b300_cloud_usd": row["break_even_capex_vs_b300_cloud_usd"],
                "claim_class": "synthetic_design_to_cost_scenario",
            }
        )
    admissible = [
        row
        for row in cost_frontier
        if row["speed_floor_pass"]
        and row["feasible_capacity"]
        and row["target_owned_dollars_per_million_output_tokens"] is not None
    ]
    selected = min(admissible, key=lambda row: row["target_owned_dollars_per_million_output_tokens"])
    ledger = parameter_ledger(m)
    analytical_total = sum(row["occurrences"] * row["params_each"] for row in ledger)
    expert_total = next(row for row in ledger if row["name"] == "routed_expert_inventory")["occurrences"] * next(
        row for row in ledger if row["name"] == "routed_expert_inventory"
    )["params_each"]
    return {
        "schema_version": 1,
        "evidence_class": "analytical_and_synthetic_with_one_vendor_measured_calibration_point",
        "model_identity": {"id": m["id"], "revision": m["revision"]},
        "parameter_reconciliation": {
            "analytical_total_params": analytical_total,
            "released_safetensors_total_params": 2_779_931_837_184,
            "relative_error": abs(analytical_total - 2_779_931_837_184) / 2_779_931_837_184,
            "analytical_routed_expert_params": expert_total,
            "released_u8_logical_params": 2_722_740_830_208,
            "routed_relative_error": abs(expert_total - 2_722_740_830_208) / 2_722_740_830_208,
        },
        "operation_ledger": ledger,
        "calibration": {
            "source": spec["calibration"]["source"],
            "measured_output_tokens_per_second": spec["calibration"]["measured_output_tokens_per_second"],
            "latency_scales": scales,
            "transfer_limit": "The scalar is fitted to B300 batch-one 8K decode only and is not applied to candidates.",
        },
        "economics": {
            **economics,
            "b300_secure_cloud_system_usd_per_hour": b300_cloud_hourly,
            "claim_boundary": (
                "B300 cloud price is observed. Candidate capex, utilization, maintenance, power, PUE, "
                "electricity, and other operating costs are scenario assumptions."
            ),
        },
        "cost_frontier_c128": cost_frontier,
        "selected_design_to_cost_point": selected,
        "rows": rows,
        "comparisons": comparisons,
        "sensitivity_c128": sensitivity,
        "limitations": [
            "No candidate silicon, RTL, compiler, timing closure, power trace, or serving endpoint has been measured.",
            "Uniform independent expert routing estimates unique weights; real skew and load imbalance are unknown.",
            "Peak bandwidth/compute efficiencies and candidate area/power/capex are synthetic assumptions.",
            "The model omits speculative decoding, prefill/decode overlap, failures, queueing, and detailed HBM timing.",
            "Pipeline results model balanced steady-state circular microbatches; layer imbalance and bubbles need event-level validation.",
            "The cost result is a design-to-cost scenario and cloud break-even, not an ASIC BOM or owned-NVIDIA comparison.",
            "Strict chip-wide BSP is not modeled; the candidate assumes hierarchical tile-group barriers plus asynchronous DMA.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    result = evaluate(spec)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(args.output),
        "parameter_reconciliation": result["parameter_reconciliation"],
        "calibration": result["calibration"],
        "rows": len(result["rows"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
