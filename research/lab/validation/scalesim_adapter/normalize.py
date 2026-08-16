from __future__ import annotations

import argparse
import configparser
import csv
import hashlib
import json
import math
from pathlib import Path


REQUEST_SCHEMA_VERSION = "inference-foundry.scalesim-v3-smoke-request.v1"
PROBE_SCHEMA_VERSION = "inference-foundry.scalesim-v3-probe.v1"
REPORT_SCHEMA_VERSION = "inference-foundry.scalesim-v3-smoke-report.v1"
PROCESS_SCHEMA_VERSION = "inference-foundry.scalesim-v3-process.v1"
TYPE_BITS = {"bf16": 16, "fp16": 16, "fp32": 32}

COMPUTE_HEADER = [
    "LayerID",
    "Total Cycles (incl. prefetch)",
    "Total Cycles",
    "Stall Cycles",
    "Overall Util %",
    "Mapping Efficiency %",
    "Compute Util %",
]
BANDWIDTH_HEADER = [
    "LayerID",
    "Avg IFMAP SRAM BW",
    "Avg FILTER SRAM BW",
    "Avg OFMAP SRAM BW",
    "Avg IFMAP DRAM BW",
    "Avg FILTER DRAM BW",
    "Avg OFMAP DRAM BW",
]
ACCESS_HEADER = [
    "LayerID",
    "SRAM IFMAP Start Cycle",
    "SRAM IFMAP Stop Cycle",
    "SRAM IFMAP Reads",
    "SRAM Filter Start Cycle",
    "SRAM Filter Stop Cycle",
    "SRAM Filter Reads",
    "SRAM OFMAP Start Cycle",
    "SRAM OFMAP Stop Cycle",
    "SRAM OFMAP Writes",
    "DRAM IFMAP Start Cycle",
    "DRAM IFMAP Stop Cycle",
    "DRAM IFMAP Reads",
    "DRAM Filter Start Cycle",
    "DRAM Filter Stop Cycle",
    "DRAM Filter Reads",
    "DRAM OFMAP Start Cycle",
    "DRAM OFMAP Stop Cycle",
    "DRAM OFMAP Writes",
]


def build_report(request_path: Path, raw_root: Path) -> dict[str, object]:
    request = _load_object(request_path)
    _require_schema(request, REQUEST_SCHEMA_VERSION, "request")
    probe_path = raw_root / "probe.json"
    probe = _load_object(probe_path)
    _require_schema(probe, PROBE_SCHEMA_VERSION, "probe")
    tool = _require_object(request, "tool")
    _validate_probe(tool, probe)
    workloads = _indexed_objects(request, "workloads")
    architectures = _indexed_objects(request, "architectures")
    cases = [
        _normalize_case(request_path, raw_root, workload, architecture)
        for workload in workloads.values()
        for architecture in architectures.values()
    ]
    if not cases:
        raise ValueError("request must contain at least one simulation case")
    report: dict[str, object] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "native_sweep_succeeded",
        "request_id": _nonempty_string(request.get("request_id"), "request_id"),
        "source_identity": {
            "request_sha256": _sha256_file(request_path),
            "probe_sha256": _sha256_file(probe_path),
        },
        "tool_identity": {
            **tool,
            "executed_source_sha256": _nonempty_string(
                probe.get("scale_sim_source_sha256"), "probe scale_sim_source_sha256"
            ),
        },
        "current_main_probe": _require_object(request, "current_main_probe"),
        "environment": {
            "python": _nonempty_string(probe.get("python"), "probe python"),
            "platform": _nonempty_string(probe.get("platform"), "probe platform"),
        },
        "adapter_identity": _adapter_identity(),
        "sweep": {
            "workload_count": len(workloads),
            "architecture_count": len(architectures),
            "case_count": len(cases),
        },
        "cases": cases,
        "same_oracle_cycle_frontier": _cycle_frontier(cases),
        "sweep_analysis": _sweep_analysis(cases),
        "claims": {
            "exact_topology_claim_permitted": True,
            "native_simulator_execution_claim_permitted": True,
            "native_cycle_count_claim_permitted": True,
            "native_utilization_claim_permitted": True,
            "native_access_count_claim_permitted": True,
            "same_oracle_cycle_ratio_claim_permitted": True,
            "bf16_arithmetic_claim_permitted": False,
            "wall_clock_latency_claim_permitted": False,
            "gpu_latency_claim_permitted": False,
            "gpu_performance_claim_permitted": False,
            "energy_claim_permitted": False,
            "area_claim_permitted": False,
            "cost_claim_permitted": False,
            "whole_model_claim_permitted": False,
            "glm_nvfp4_execution_claim_permitted": False,
            "provider_comparison_claim_permitted": False,
            "model_specific_hardware_advantage_claim_permitted": False,
            "sram_capacity_benefit_claim_permitted": False,
            "blockers": [
                "scale_sim_dense_elements_do_not_encode_bf16_arithmetic",
                "calc_bandwidth_mode_is_not_a_calibrated_memory_system",
                "cycles_have_no_bound_clock_frequency_or_gpu_runtime_calibration",
                "single_gemms_do_not_model_serving_or_whole_model_execution",
                "energy_area_and_cost_backends_are_not_executed",
            ],
        },
    }
    stable = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    report["content_identity_sha256"] = hashlib.sha256(stable).hexdigest()
    return report


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize a pinned SCALE-Sim v3 sweep."
    )
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    try:
        report = build_report(args.request, args.raw_root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
        temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(args.output)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "content_id": report["content_identity_sha256"],
                "output": str(args.output),
                "status": report["status"],
            },
            sort_keys=True,
        )
    )
    return 0


def _normalize_case(
    request_path: Path,
    raw_root: Path,
    workload: dict[str, object],
    architecture: dict[str, object],
) -> dict[str, object]:
    workload_id = _safe_id(workload.get("id"), "workload id")
    architecture_id = _safe_id(architecture.get("id"), "architecture id")
    case_root = raw_root / workload_id / architecture_id
    input_root = case_root / "input"
    output_root = case_root / "output" / f"{workload_id}__{architecture_id}"
    process = _load_object(case_root / "process.json")
    _require_schema(process, PROCESS_SCHEMA_VERSION, "process")
    if (
        process.get("status") != "succeeded"
        or _integer(process.get("exit_code"), "process exit_code") != 0
    ):
        raise ValueError(f"process did not succeed for {workload_id}/{architecture_id}")
    dimensions = _dimensions(workload)
    tensor_types = _tensor_types(workload)
    _validate_topology(input_root / "topology.csv", workload_id, dimensions)
    _validate_layout(input_root / "layout.csv", workload_id)
    _validate_config(
        input_root / "config.cfg", workload_id, architecture_id, architecture
    )
    compute = _parse_compute(output_root / "COMPUTE_REPORT.csv")
    bandwidth = _parse_bandwidth(output_root / "BANDWIDTH_REPORT.csv")
    accesses = _parse_accesses(output_root / "DETAILED_ACCESS_REPORT.csv")
    accounting = _logical_accounting(dimensions, tensor_types)
    source_contract = _require_object(workload, "source_contract")
    _verify_source_contract(
        request_path, source_contract, workload, dimensions, tensor_types, accounting
    )
    return {
        "case_id": f"{workload_id}/{architecture_id}",
        "workload": {
            "id": workload_id,
            "model_id": _nonempty_string(workload.get("model_id"), "model_id"),
            "operator": _nonempty_string(workload.get("operator"), "operator"),
            "dimensions": dimensions,
            "tensor_types": tensor_types,
            "source_contract": source_contract,
            "semantic_limit": _nonempty_string(
                workload.get("semantic_limit"), "semantic_limit"
            ),
        },
        "architecture": _normalized_architecture(architecture),
        "logical_accounting": accounting,
        "native_result": {
            **compute,
            "bandwidth": bandwidth,
            "sram_accesses": accesses["sram"],
            "dram_accesses": accesses["dram"],
            "access_windows": accesses["windows"],
            "access_semantics": "native_scale_sim_element_access_counts_not_foundry_logical_bytes",
        },
        "raw_artifacts": _raw_artifacts(case_root),
    }


def _dimensions(workload: dict[str, object]) -> dict[str, int]:
    dimensions = _require_object(workload, "dimensions")
    normalized = {
        key: _positive_integer(dimensions.get(key), f"dimensions.{key}")
        for key in ("batch", "m", "n", "k")
    }
    if normalized["batch"] != 1:
        raise ValueError(
            "SCALE-Sim smoke contract currently requires batch equal to one"
        )
    return normalized


def _tensor_types(workload: dict[str, object]) -> dict[str, str]:
    tensor_types = _require_object(workload, "tensor_types")
    normalized = {
        key: _nonempty_string(tensor_types.get(key), f"tensor_types.{key}")
        for key in ("input", "weight", "output", "accumulator")
    }
    for key, scalar_type in normalized.items():
        if scalar_type not in TYPE_BITS:
            raise ValueError(
                f"unsupported logical tensor type for {key}: {scalar_type}"
            )
    return normalized


def _logical_accounting(
    dimensions: dict[str, int], tensor_types: dict[str, str]
) -> dict[str, int]:
    batch = dimensions["batch"]
    m = dimensions["m"]
    n = dimensions["n"]
    k = dimensions["k"]
    multiply_accumulates = batch * m * n * k
    input_elements = batch * m * k
    weight_elements = n * k
    output_elements = batch * m * n
    input_bytes = _packed_bytes(input_elements, tensor_types["input"])
    weight_bytes = _packed_bytes(weight_elements, tensor_types["weight"])
    output_bytes = _packed_bytes(output_elements, tensor_types["output"])
    return {
        "multiply_accumulates": multiply_accumulates,
        "flops": multiply_accumulates * 2,
        "input_elements": input_elements,
        "weight_elements": weight_elements,
        "output_elements": output_elements,
        "input_bytes": input_bytes,
        "weight_bytes": weight_bytes,
        "output_bytes": output_bytes,
        "total_tensor_bytes": input_bytes + weight_bytes + output_bytes,
    }


def _validate_topology(
    path: Path, workload_id: str, dimensions: dict[str, int]
) -> None:
    header, rows = _read_csv(path)
    if header != ["Layer Name", "M", "N", "K"] or len(rows) != 1:
        raise ValueError(f"invalid topology schema for {workload_id}")
    row = rows[0]
    if len(row) != 4 or row[0] != workload_id:
        raise ValueError(f"invalid topology row for {workload_id}")
    observed = {
        key: _positive_integer(value, f"topology {key}")
        for key, value in zip(("m", "n", "k"), row[1:], strict=True)
    }
    expected = {key: dimensions[key] for key in ("m", "n", "k")}
    if observed != expected:
        raise ValueError(
            f"topology dimensions do not match declared GEMM for {workload_id}: {observed} != {expected}"
        )


def _validate_layout(path: Path, workload_id: str) -> None:
    header, rows = _read_csv(path)
    if (
        not header
        or header[0] != "Layer name"
        or len(rows) != 1
        or rows[0][0] != workload_id
    ):
        raise ValueError(
            f"invalid disabled custom-layout placeholder for {workload_id}"
        )


def _validate_config(
    path: Path,
    workload_id: str,
    architecture_id: str,
    architecture: dict[str, object],
) -> None:
    parser = configparser.ConfigParser()
    with path.open(encoding="utf-8") as source:
        parser.read_file(source)
    expected_run_name = f"{workload_id}__{architecture_id}"
    if parser.get("general", "run_name") != expected_run_name:
        raise ValueError(f"config run_name mismatch for {expected_run_name}")
    checks = {
        "arrayheight": _positive_integer(
            architecture.get("array_height"), "array_height"
        ),
        "arraywidth": _positive_integer(architecture.get("array_width"), "array_width"),
        "ifmapsramszkb": _positive_integer(
            architecture.get("ifmap_sram_kb"), "ifmap_sram_kb"
        ),
        "filtersramszkb": _positive_integer(
            architecture.get("filter_sram_kb"), "filter_sram_kb"
        ),
        "ofmapsramszkb": _positive_integer(
            architecture.get("ofmap_sram_kb"), "ofmap_sram_kb"
        ),
    }
    for key, expected in checks.items():
        if parser.getint("architecture_presets", key) != expected:
            raise ValueError(f"config {key} mismatch for {expected_run_name}")
    expected_dataflow = _nonempty_string(architecture.get("dataflow"), "dataflow")
    if expected_dataflow not in {"ws", "is", "os"}:
        raise ValueError(f"unsupported dataflow: {expected_dataflow}")
    if parser.get("architecture_presets", "dataflow").strip() != expected_dataflow:
        raise ValueError(f"config dataflow mismatch for {expected_run_name}")
    expected_bandwidth = _nonempty_string(
        architecture.get("interface_bandwidth"), "interface_bandwidth"
    )
    if expected_bandwidth != "CALC":
        raise ValueError("SCALE-Sim smoke contract only permits CALC bandwidth mode")
    if parser.get("run_presets", "interfacebandwidth").strip() != expected_bandwidth:
        raise ValueError(f"config interface bandwidth mismatch for {expected_run_name}")
    if parser.getboolean("run_presets", "useramulatortrace"):
        raise ValueError("Ramulator execution is outside this smoke contract")
    if (
        parser.has_option("run_presets", "timelinearmodel")
        and parser.get("run_presets", "timelinearmodel").strip() != "None"
    ):
        raise ValueError("time linear model must remain disabled")
    if parser.getboolean("layout", "ifmapcustomlayout") or parser.getboolean(
        "layout", "filtercustomlayout"
    ):
        raise ValueError("custom layout execution is outside this smoke contract")
    if parser.getboolean("sparsity", "sparsitysupport"):
        raise ValueError("sparse execution is outside this dense smoke contract")


def _normalized_architecture(architecture: dict[str, object]) -> dict[str, object]:
    return {
        "id": _safe_id(architecture.get("id"), "architecture id"),
        "array_height": _positive_integer(
            architecture.get("array_height"), "array_height"
        ),
        "array_width": _positive_integer(
            architecture.get("array_width"), "array_width"
        ),
        "ifmap_sram_kb": _positive_integer(
            architecture.get("ifmap_sram_kb"), "ifmap_sram_kb"
        ),
        "filter_sram_kb": _positive_integer(
            architecture.get("filter_sram_kb"), "filter_sram_kb"
        ),
        "ofmap_sram_kb": _positive_integer(
            architecture.get("ofmap_sram_kb"), "ofmap_sram_kb"
        ),
        "dataflow": _nonempty_string(architecture.get("dataflow"), "dataflow"),
        "interface_bandwidth": _nonempty_string(
            architecture.get("interface_bandwidth"), "interface_bandwidth"
        ),
        "role": _nonempty_string(
            architecture.get("role", "base_array_dataflow_sweep"), "architecture role"
        ),
    }


def _parse_compute(path: Path) -> dict[str, object]:
    row = _single_report_row(path, COMPUTE_HEADER)
    result = {
        "total_cycles_including_prefetch": _positive_integer(
            row[1], "total cycles including prefetch"
        ),
        "total_cycles": _positive_integer(row[2], "total cycles"),
        "stall_cycles": _nonnegative_integer(row[3], "stall cycles"),
        "overall_utilization_percent": _percentage(row[4], "overall utilization"),
        "mapping_efficiency_percent": _percentage(row[5], "mapping efficiency"),
        "compute_utilization_percent": _percentage(row[6], "compute utilization"),
    }
    if result["total_cycles_including_prefetch"] < result["total_cycles"]:
        raise ValueError(f"{path.name} prefetch cycle accounting is invalid")
    return result


def _parse_bandwidth(path: Path) -> dict[str, float]:
    row = _single_report_row(path, BANDWIDTH_HEADER)
    names = [
        "average_ifmap_sram_words_per_cycle",
        "average_filter_sram_words_per_cycle",
        "average_ofmap_sram_words_per_cycle",
        "average_ifmap_dram_words_per_cycle",
        "average_filter_dram_words_per_cycle",
        "average_ofmap_dram_words_per_cycle",
    ]
    return {
        name: _nonnegative_float(value, name)
        for name, value in zip(names, row[1:], strict=True)
    }


def _parse_accesses(path: Path) -> dict[str, object]:
    row = _single_report_row(path, ACCESS_HEADER)
    values = row[1:]
    windows = {
        "sram_ifmap": _window(values[0], values[1], "sram ifmap"),
        "sram_filter": _window(values[3], values[4], "sram filter"),
        "sram_ofmap": _window(values[6], values[7], "sram ofmap"),
        "dram_ifmap": _window(values[9], values[10], "dram ifmap"),
        "dram_filter": _window(values[12], values[13], "dram filter"),
        "dram_ofmap": _window(values[15], values[16], "dram ofmap"),
    }
    return {
        "sram": {
            "ifmap_reads": _nonnegative_integer(values[2], "SRAM IFMAP reads"),
            "filter_reads": _nonnegative_integer(values[5], "SRAM filter reads"),
            "ofmap_writes": _nonnegative_integer(values[8], "SRAM OFMAP writes"),
        },
        "dram": {
            "ifmap_reads": _nonnegative_integer(values[11], "DRAM IFMAP reads"),
            "filter_reads": _nonnegative_integer(values[14], "DRAM filter reads"),
            "ofmap_writes": _nonnegative_integer(values[17], "DRAM OFMAP writes"),
        },
        "windows": windows,
    }


def _single_report_row(path: Path, expected_header: list[str]) -> list[str]:
    header, rows = _read_csv(path)
    if header != expected_header:
        raise ValueError(
            f"{path.name} header does not match pinned SCALE-Sim v3 schema"
        )
    if len(rows) != 1 or len(rows[0]) != len(expected_header):
        raise ValueError(f"{path.name} must contain exactly one complete layer row")
    if _integer(rows[0][0], f"{path.name} LayerID") != 0:
        raise ValueError(f"{path.name} LayerID must be zero")
    return rows[0]


def _read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8") as source:
        rows = [[value.strip() for value in row] for row in csv.reader(source)]
    normalized = [[value for value in row if value != ""] for row in rows if any(row)]
    if not normalized:
        raise ValueError(f"CSV file is empty: {path}")
    return normalized[0], normalized[1:]


def _cycle_frontier(cases: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for case in cases:
        workload = _require_object(case, "workload")
        grouped.setdefault(str(workload["id"]), []).append(case)
    frontier = []
    for workload_id, workload_cases in grouped.items():
        cycles = {
            str(_require_object(case, "architecture")["id"]): _positive_integer(
                _require_object(case, "native_result").get(
                    "total_cycles_including_prefetch"
                ),
                "frontier cycles",
            )
            for case in workload_cases
        }
        minimum = min(cycles.values())
        frontier.append(
            {
                "workload_id": workload_id,
                "minimum_total_cycles_including_prefetch": minimum,
                "minimum_architecture_ids": sorted(
                    architecture_id
                    for architecture_id, value in cycles.items()
                    if value == minimum
                ),
                "cycle_ratio_to_minimum": {
                    architecture_id: value / minimum
                    for architecture_id, value in sorted(cycles.items())
                },
            }
        )
    return sorted(frontier, key=lambda item: str(item["workload_id"]))


def _sweep_analysis(cases: list[dict[str, object]]) -> dict[str, object]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for case in cases:
        workload = _require_object(case, "workload")
        grouped.setdefault(str(workload["id"]), []).append(case)
    rankings: dict[str, list[str]] = {}
    sram_controls: list[dict[str, object]] = []
    for workload_id, workload_cases in sorted(grouped.items()):
        base_cases = [
            case
            for case in workload_cases
            if _require_object(case, "architecture").get("role")
            == "base_array_dataflow_sweep"
        ]
        rankings[workload_id] = [
            str(_require_object(case, "architecture")["id"])
            for case in sorted(
                base_cases,
                key=lambda item: (
                    _case_cycles(item, "total_cycles_including_prefetch"),
                    str(_require_object(item, "architecture")["id"]),
                ),
            )
        ]
        for control in workload_cases:
            control_architecture = _require_object(control, "architecture")
            if control_architecture.get("role") != "sram_control":
                continue
            baselines = [
                case
                for case in base_cases
                if _same_compute_architecture(
                    _require_object(case, "architecture"), control_architecture
                )
            ]
            if len(baselines) != 1:
                raise ValueError(
                    f"SRAM control requires one matching base architecture: {workload_id}"
                )
            baseline = baselines[0]
            control_native = _require_object(control, "native_result")
            baseline_native = _require_object(baseline, "native_result")
            control_dram = _require_object(control_native, "dram_accesses")
            baseline_dram = _require_object(baseline_native, "dram_accesses")
            sram_controls.append(
                {
                    "workload_id": workload_id,
                    "control_architecture_id": str(control_architecture["id"]),
                    "baseline_architecture_id": str(
                        _require_object(baseline, "architecture")["id"]
                    ),
                    "total_cycles_including_prefetch_ratio": _case_cycles(
                        control, "total_cycles_including_prefetch"
                    )
                    / _case_cycles(baseline, "total_cycles_including_prefetch"),
                    "total_cycles_ratio": _case_cycles(control, "total_cycles")
                    / _case_cycles(baseline, "total_cycles"),
                    "dram_filter_reads_ratio": _positive_integer(
                        control_dram.get("filter_reads"), "control DRAM filter reads"
                    )
                    / _positive_integer(
                        baseline_dram.get("filter_reads"), "baseline DRAM filter reads"
                    ),
                }
            )
    unique_rankings = {tuple(ranking) for ranking in rankings.values()}
    best_architectures = {ranking[0] for ranking in rankings.values() if ranking}
    return {
        "base_architecture_rankings": rankings,
        "base_architecture_rank_identical_across_workloads": len(unique_rankings) <= 1,
        "model_specific_best_base_architecture_observed": len(best_architectures) > 1,
        "sram_controls": sram_controls,
        "larger_sram_reduced_native_dram_filter_reads_observed": any(
            float(control["dram_filter_reads_ratio"]) < 1.0 for control in sram_controls
        ),
        "larger_sram_reduced_total_cycles_observed": any(
            float(control["total_cycles_including_prefetch_ratio"]) < 1.0
            for control in sram_controls
        ),
        "interpretation_scope": "same_pinned_scale_sim_oracle_only",
    }


def _case_cycles(case: dict[str, object], key: str) -> int:
    native = _require_object(case, "native_result")
    return _positive_integer(native.get(key), f"native_result.{key}")


def _same_compute_architecture(
    baseline: dict[str, object], control: dict[str, object]
) -> bool:
    return all(
        baseline.get(key) == control.get(key)
        for key in ("array_height", "array_width", "dataflow", "interface_bandwidth")
    )


def _validate_probe(tool: dict[str, object], probe: dict[str, object]) -> None:
    for key in ("revision", "version"):
        expected = _nonempty_string(tool.get(key), f"tool {key}")
        observed = _nonempty_string(probe.get(key), f"probe {key}")
        if observed != expected:
            raise ValueError(
                f"SCALE-Sim {key} mismatch: expected {expected}, found {observed}"
            )
    expected_license = _nonempty_string(
        tool.get("license_sha256"), "tool license_sha256"
    )
    observed_license = _nonempty_string(
        probe.get("license_sha256"), "probe license_sha256"
    )
    if observed_license != expected_license:
        raise ValueError("SCALE-Sim license hash mismatch")


def _verify_source_contract(
    request_path: Path,
    source_contract: dict[str, object],
    workload: dict[str, object],
    dimensions: dict[str, int],
    tensor_types: dict[str, str],
    accounting: dict[str, int],
) -> None:
    relative_path = _nonempty_string(
        source_contract.get("path"), "source contract path"
    )
    expected_sha256 = _nonempty_string(
        source_contract.get("sha256"), "source contract sha256"
    )
    _nonempty_string(source_contract.get("basis"), "source contract basis")
    path = (request_path.parent / relative_path).resolve()
    if _sha256_file(path) != expected_sha256:
        raise ValueError(f"source contract hash mismatch: {relative_path}")
    source = _load_object(path)
    kind = _nonempty_string(source_contract.get("kind"), "source contract kind")
    if kind == "timeloop_problem_export":
        expected_content_id = _nonempty_string(
            source_contract.get("content_id"), "source contract content_id"
        )
        if source.get("content_id") != expected_content_id:
            raise ValueError("source Timeloop export content ID mismatch")
        if _require_object(source, "problem_dimensions") != dimensions:
            raise ValueError("source Timeloop dimensions do not match workload")
        if _require_object(source, "tensor_types") != tensor_types:
            raise ValueError("source Timeloop tensor types do not match workload")
        source_accounting = _require_object(source, "accounting")
        for key, value in accounting.items():
            if key != "total_tensor_bytes" and source_accounting.get(key) != value:
                raise ValueError(f"source Timeloop accounting mismatch: {key}")
    elif kind == "glm_routed_expert_gate_bf16_reference":
        model = _require_object(source, "model")
        if model.get("model_id") != workload.get("model_id"):
            raise ValueError("source GLM model ID mismatch")
        expected_revision = _nonempty_string(
            source_contract.get("model_revision"), "source contract model_revision"
        )
        if model.get("model_revision") != expected_revision:
            raise ValueError("source GLM model revision mismatch")
        architecture = _require_object(model, "architecture")
        hybrid = _require_object(architecture, "hybrid_moe_mla_dsa")
        moe = _require_object(hybrid, "moe")
        if model.get("hidden_size") != dimensions["k"]:
            raise ValueError("source GLM hidden size does not match K")
        if moe.get("expert_intermediate_size") != dimensions["n"]:
            raise ValueError("source GLM expert intermediate size does not match N")
        if dimensions["batch"] != 1 or dimensions["m"] != 1:
            raise ValueError("GLM routed-expert smoke must model one dispatched token")
        if tensor_types != {
            "input": "bf16",
            "weight": "bf16",
            "output": "bf16",
            "accumulator": "fp32",
        }:
            raise ValueError(
                "GLM routed-expert reference must use BF16 logical tensors"
            )
        if (
            moe.get("routed_expert_weight_precision") != "bf16"
            or source.get("network_activation_precision") != "bf16"
        ):
            raise ValueError("source GLM precision does not match BF16 reference")
    else:
        raise ValueError(f"unsupported source contract kind: {kind}")


def _indexed_objects(
    document: dict[str, object], key: str
) -> dict[str, dict[str, object]]:
    value = document.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be an array")
    indexed: dict[str, dict[str, object]] = {}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{key} entries must be objects")
        identifier = _safe_id(item.get("id"), f"{key} id")
        if identifier in indexed:
            raise ValueError(f"duplicate {key} id: {identifier}")
        indexed[identifier] = item
    return indexed


def _raw_artifacts(root: Path) -> list[dict[str, object]]:
    return [
        {
            "path": str(path.relative_to(root)),
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _adapter_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parent
    return {
        "name": "inference-foundry/scalesim-v3-adapter",
        "version": "1",
        "normalizer_sha256": _sha256_file(root / "normalize.py"),
        "runner_sha256": _sha256_file(root / "run.py"),
        "driver_sha256": _sha256_file(root / "driver.py"),
    }


def _window(start: object, stop: object, label: str) -> dict[str, float]:
    start_value = _finite_float(start, f"{label} start cycle")
    stop_value = _finite_float(stop, f"{label} stop cycle")
    if stop_value < start_value:
        raise ValueError(f"{label} access window is invalid")
    return {"start_cycle": start_value, "stop_cycle": stop_value}


def _percentage(value: object, label: str) -> float:
    result = _nonnegative_float(value, label)
    if result > 100.0:
        raise ValueError(f"{label} must not exceed 100 percent")
    return result


def _packed_bytes(elements: int, scalar_type: str) -> int:
    return (elements * TYPE_BITS[scalar_type] + 7) // 8


def _safe_id(value: object, label: str) -> str:
    result = _nonempty_string(value, label)
    if any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-_."
        for character in result
    ):
        raise ValueError(f"{label} contains unsupported characters: {result}")
    if result in {".", ".."}:
        raise ValueError(f"{label} is not safe: {result}")
    return result


def _positive_integer(value: object, label: str) -> int:
    result = _integer(value, label)
    if result <= 0:
        raise ValueError(f"{label} must be positive")
    return result


def _nonnegative_integer(value: object, label: str) -> int:
    result = _integer(value, label)
    if result < 0:
        raise ValueError(f"{label} must be non-negative")
    return result


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError as error:
            raise ValueError(f"{label} must be an integer") from error
        if math.isfinite(parsed) and parsed.is_integer():
            return int(parsed)
    raise ValueError(f"{label} must be an integer")


def _nonnegative_float(value: object, label: str) -> float:
    result = _finite_float(value, label)
    if result < 0.0:
        raise ValueError(f"{label} must be non-negative")
    return result


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a finite number") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _load_object(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return document


def _require_schema(document: dict[str, object], expected: str, label: str) -> None:
    observed = str(document.get("schema_version", ""))
    if observed != expected:
        raise ValueError(f"unsupported {label} schema: {observed}")


def _require_object(document: dict[str, object], key: str) -> dict[str, object]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
