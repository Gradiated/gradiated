from __future__ import annotations

import csv
import itertools
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


KV260_LIMITS = {
    "logic_cells": 256_000,
    "dsp_slices": 1_200,
    "bram18k": 144,
    "uram_blocks": 64,
}


@dataclass(frozen=True)
class KDAWorkload:
    name: str = "kda_decode_head"
    head_dim: int = 128
    qkv_matrices: int = 3
    state_update_macs: int = 4
    gate_kernel: int = 2
    weight_bytes_per_value: float = 0.5
    activation_bytes_per_value: float = 2.0


@dataclass(frozen=True)
class Architecture:
    name: str
    kind: str
    mac_units: int
    clock_mhz: int
    external_bandwidth_gbps: float
    local_bandwidth_gbps: float
    sram_kb: int
    fused: bool
    local_state: bool
    weights_local: bool
    double_buffered: bool
    compute_efficiency: float
    memory_efficiency: float
    vector_lanes: int
    launch_overhead_ns: float
    static_power_w: float


def workload_counts(workload: KDAWorkload) -> dict[str, float]:
    d = workload.head_dim
    projection_macs = (workload.qkv_matrices + 1) * d * d
    state_update_macs = workload.state_update_macs * d * d
    state_readout_macs = d * d
    gate_ops = 2 * d * max(workload.gate_kernel - 1, 1)
    state_bytes = 2 * d * d * workload.activation_bytes_per_value
    projection_weight_bytes = (
        (workload.qkv_matrices + 1) * d * d * workload.weight_bytes_per_value
    )
    input_output_bytes = 2 * d * workload.activation_bytes_per_value
    intermediate_bytes = 5 * d * workload.activation_bytes_per_value
    return {
        "projection_macs": float(projection_macs),
        "state_update_macs": float(state_update_macs),
        "state_readout_macs": float(state_readout_macs),
        "macs": float(projection_macs + state_update_macs + state_readout_macs),
        "vector_ops": float(gate_ops),
        "state_bytes": float(state_bytes),
        "projection_weight_bytes": float(projection_weight_bytes),
        "input_output_bytes": float(input_output_bytes),
        "intermediate_bytes": float(intermediate_bytes),
    }


def required_local_bytes(workload: KDAWorkload, architecture: Architecture) -> float:
    counts = workload_counts(workload)
    local = 0.0
    if architecture.local_state:
        local += counts["state_bytes"]
    if architecture.weights_local:
        local += counts["projection_weight_bytes"]
    return local


def resource_estimate(workload: KDAWorkload, architecture: Architecture) -> dict[str, int]:
    del workload
    if architecture.kind != "fpga":
        return {"logic_cells": 0, "dsp_slices": 0, "bram18k": 0, "uram_blocks": 0}

    logic_cells = (
        5_000
        + architecture.mac_units * 400
        + architecture.sram_kb * 4
        + (4_000 if architecture.fused else 0)
        + (2_000 if architecture.double_buffered else 0)
    )
    bram18k = math.ceil(architecture.sram_kb / 2.25)
    uram_blocks = math.ceil(max(architecture.sram_kb - 256, 0) / 36)
    return {
        "logic_cells": logic_cells,
        "dsp_slices": architecture.mac_units,
        "bram18k": bram18k,
        "uram_blocks": uram_blocks,
    }


def evaluate(workload: KDAWorkload, architecture: Architecture) -> dict[str, Any]:
    counts = workload_counts(workload)
    resources = resource_estimate(workload, architecture)
    local_capacity_bytes = architecture.sram_kb * 1024.0
    local_required_bytes = required_local_bytes(workload, architecture)
    capacity_ok = local_required_bytes <= local_capacity_bytes
    resource_ok = all(resources[key] <= KV260_LIMITS[key] for key in resources)
    fits_kv260 = architecture.kind != "fpga" or (capacity_ok and resource_ok)

    external_bytes = counts["input_output_bytes"] + counts["intermediate_bytes"]
    if not architecture.weights_local:
        external_bytes += counts["projection_weight_bytes"]
    if not architecture.local_state:
        external_bytes += counts["state_bytes"]
    local_bytes = local_required_bytes
    if architecture.fused:
        external_bytes -= counts["intermediate_bytes"]

    clock_hz = architecture.clock_mhz * 1_000_000.0
    compute_seconds = (
        counts["macs"]
        / max(architecture.mac_units * architecture.compute_efficiency, 1.0)
        / clock_hz
    )
    vector_seconds = (
        counts["vector_ops"]
        / max(architecture.vector_lanes * architecture.compute_efficiency, 1.0)
        / clock_hz
    )
    external_seconds = external_bytes * 8.0 / (
        architecture.external_bandwidth_gbps
        * 1_000_000_000.0
        * architecture.memory_efficiency
    )
    local_seconds = 0.0
    if local_bytes:
        local_seconds = local_bytes * 8.0 / (
            architecture.local_bandwidth_gbps
            * 1_000_000_000.0
            * architecture.memory_efficiency
        )
    launch_seconds = (
        architecture.launch_overhead_ns
        * (1 if architecture.fused else 5)
        / 1_000_000_000.0
    )
    compute_path = compute_seconds + vector_seconds
    memory_path = external_seconds + local_seconds
    if architecture.double_buffered:
        latency_seconds = max(compute_path, memory_path) + launch_seconds
    else:
        latency_seconds = compute_path + memory_path + launch_seconds

    compute_utilisation = min(1.0, compute_path / max(latency_seconds, 1e-15))
    power_proxy_w = (
        architecture.static_power_w
        + 8.0 * architecture.mac_units / 256.0 * architecture.clock_mhz / 200.0 * compute_utilisation
        + external_bytes / max(latency_seconds, 1e-15) / 1e9 * 0.04
        + local_bytes / max(latency_seconds, 1e-15) / 1e9 * 0.01
    )
    energy_proxy_j = power_proxy_w * latency_seconds
    return {
        "name": architecture.name,
        "kind": architecture.kind,
        "model_kind": "analytical",
        "latency_us": latency_seconds * 1_000_000.0,
        "throughput_tokens_per_s": 1.0 / max(latency_seconds, 1e-15),
        "compute_us": compute_seconds * 1_000_000.0,
        "vector_us": vector_seconds * 1_000_000.0,
        "external_memory_us": external_seconds * 1_000_000.0,
        "local_memory_us": local_seconds * 1_000_000.0,
        "launch_us": launch_seconds * 1_000_000.0,
        "overlap_mode": "overlapped" if architecture.double_buffered else "serial",
        "external_bytes": external_bytes,
        "local_bytes": local_bytes,
        "required_local_bytes": local_required_bytes,
        "macs": counts["macs"],
        "compute_utilisation": compute_utilisation,
        "power_proxy_w": power_proxy_w,
        "energy_proxy_uj": energy_proxy_j * 1_000_000.0,
        "fits_kv260": fits_kv260,
        "capacity_ok": capacity_ok,
        "resource_ok": resource_ok,
        "fused": architecture.fused,
        "local_state": architecture.local_state,
        "weights_local": architecture.weights_local,
        "double_buffered": architecture.double_buffered,
        "mac_units": architecture.mac_units,
        "clock_mhz": architecture.clock_mhz,
        "external_bandwidth_gbps": architecture.external_bandwidth_gbps,
        "local_bandwidth_gbps": architecture.local_bandwidth_gbps,
        "sram_kb": architecture.sram_kb,
        **resources,
    }


def gpu_control() -> Architecture:
    return Architecture(
        name="generic_gpu_control",
        kind="gpu",
        mac_units=16_384,
        clock_mhz=1_500,
        external_bandwidth_gbps=64_000.0,
        local_bandwidth_gbps=200_000.0,
        sram_kb=2_048,
        fused=True,
        local_state=False,
        weights_local=False,
        double_buffered=True,
        compute_efficiency=0.35,
        memory_efficiency=0.70,
        vector_lanes=4_096,
        launch_overhead_ns=2_000.0,
        static_power_w=300.0,
    )


def fpga_architectures() -> Iterable[Architecture]:
    for mac_units, clock_mhz, sram_kb, external_bw, local_bw, fused, local_state, weights_local, double_buffered in itertools.product(
        (64, 128, 256, 512),
        (100, 150, 200, 250),
        (32, 64, 128, 256, 512),
        (32.0, 64.0, 128.0),
        (16.0, 32.0, 64.0),
        (False, True),
        (False, True),
        (False, True),
        (False, True),
    ):
        name = (
            f"fpga_m{mac_units}_f{clock_mhz}_s{sram_kb}_x{int(external_bw)}"
            f"_l{int(local_bw)}_fuse{int(fused)}_state{int(local_state)}"
            f"_weights{int(weights_local)}_db{int(double_buffered)}"
        )
        yield Architecture(
            name=name,
            kind="fpga",
            mac_units=mac_units,
            clock_mhz=clock_mhz,
            external_bandwidth_gbps=external_bw,
            local_bandwidth_gbps=local_bw,
            sram_kb=sram_kb,
            fused=fused,
            local_state=local_state,
            weights_local=weights_local,
            double_buffered=double_buffered,
            compute_efficiency=0.70 if fused else 0.60,
            memory_efficiency=0.75 if double_buffered else 0.55,
            vector_lanes=max(4, mac_units // 8),
            launch_overhead_ns=0.0,
            static_power_w=1.5 + mac_units / 256.0,
        )


def dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    metrics = ("latency_us", "energy_proxy_uj", "logic_cells", "dsp_slices")
    no_worse = all(left[key] <= right[key] for key in metrics)
    strictly_better = any(left[key] < right[key] for key in metrics)
    return no_worse and strictly_better


def pareto_frontier(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = [row for row in rows if row["kind"] == "fpga" and row["fits_kv260"]]
    frontier = [row for row in eligible if not any(dominates(other, row) for other in eligible)]
    return sorted(frontier, key=lambda row: (row["latency_us"], row["energy_proxy_uj"]))


def run_sweep(workload: KDAWorkload | None = None) -> dict[str, Any]:
    workload = workload or KDAWorkload()
    architectures = [gpu_control(), *fpga_architectures()]
    rows = [evaluate(workload, architecture) for architecture in architectures]
    candidates = [row for row in rows if row["kind"] == "fpga" and row["fits_kv260"]]
    frontier = pareto_frontier(rows)
    fastest = min(candidates, key=lambda row: row["latency_us"])
    lowest_energy = min(candidates, key=lambda row: row["energy_proxy_uj"])
    balanced = min(
        candidates,
        key=lambda row: (
            row["latency_us"] / fastest["latency_us"]
            + row["energy_proxy_uj"] / lowest_energy["energy_proxy_uj"]
        ),
    )
    return {
        "experiment": {
            "name": "kimi_k3_kda_fpga_sweep",
            "evidence_class": "analytical",
            "scope": "one 128x128 KDA decode head",
            "purpose": "screen dataflow candidates before RTL and KV260 mapping",
            "transfer_limit": "does not predict advanced-node ASIC or GPU product performance",
        },
        "workload": asdict(workload),
        "workload_counts": workload_counts(workload),
        "candidate_count": len(candidates),
        "all_row_count": len(rows),
        "kv260_limits": KV260_LIMITS,
        "controls": [row for row in rows if row["kind"] == "gpu"],
        "best_latency": fastest,
        "best_energy": lowest_energy,
        "best_balanced": balanced,
        "pareto_frontier": frontier[:50],
        "rows": rows,
    }


def write_outputs(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_result = dict(result)
    rows = json_result.pop("rows")
    (output_dir / "summary.json").write_text(json.dumps(json_result, indent=2) + "\n")
    fieldnames = list(rows[0].keys())
    with (output_dir / "sweep.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_summary(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())
