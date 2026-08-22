#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib


PROJECT = pathlib.Path(__file__).resolve().parent


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def artifact(path: str) -> dict:
    target = PROJECT / path
    return {"path": path, "sha256": digest(target)}


def atomic_json(path: pathlib.Path, payload: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    temporary.replace(path)


def main() -> int:
    oracle = json.loads((PROJECT / "CPU_REFERENCE_ORACLE.json").read_text())
    bound = json.loads((PROJECT / "H200_PHYSICAL_BOUND.json").read_text())
    ranking = json.loads((PROJECT / "OPPORTUNITY_RANKING.json").read_text())
    binding = json.loads(
        (PROJECT / "evidence/PINNED_SOURCE_BINDING.json").read_text()
    )
    prior = json.loads(
        (PROJECT / "evidence/PRIOR_H200_COMPONENT_SNAPSHOT.json").read_text()
    )
    integration = json.loads(
        (PROJECT / "evidence/RUNTIME_INTEGRATION_CHECK.json").read_text()
    )
    if not oracle["pass"] or not oracle["rejected_two_round_falsified"]:
        raise RuntimeError("CPU oracle did not pass")
    if not bound["source_identity_pass"]:
        raise RuntimeError("pinned source identity did not pass")
    if not bound["resources"]["shared_memory_legal"]:
        raise RuntimeError("candidate is not physically legal on SM90")
    if ranking["opportunities"][0]["id"] != "corrected_c32_one_cta_fusion":
        raise RuntimeError("corrected candidate is not the ranked next measurement")
    if (
        integration["mode"] != "check"
        or not integration["pinned_source_identity_pass"]
        or integration["source_tree_mutated"]
    ):
        raise RuntimeError("runtime integration check did not pass safely")

    exact_row = next(
        row
        for row in oracle["rows"]
        if row["id"] == "representative_exact_width_21504"
    )
    payload = {
        "schema_version": 1,
        "id": "gemma4_h200_gelu_mul_fp8_quant_fusion",
        "status": "terminal",
        "classification": "source_complete_candidate_pending_exact_h200_falsification",
        "decision": "promote_corrected_c32_fusion_to_exact_consumer_h200_component_test",
        "pass": True,
        "terminal_scope": "zero_gpu_source_and_analytical_mechanism",
        "question_answer": "Yes at source and CPU-reference scope: the exact pinned producer can emit the dynamic per-token E4M3 tensor and [M,1] FP32 scale consumed by the unchanged down fp8_scaled_mm. Target-H200 correctness and performance remain unmeasured for the corrected source.",
        "binding": {
            "model": binding["model"],
            "runtime": binding["runtime"],
            "loaded_path": binding["loaded_path"],
            "measured_loaded_consumer": binding["measured_loaded_consumer"],
            "tensor_contract": binding["tensor_contract"],
            "source_identity_pass": bound["source_identity_pass"],
            "source_binding": artifact("evidence/PINNED_SOURCE_BINDING.json"),
        },
        "causal_finding": {
            "prior_failure_type": "semantic_implementation_defect_not_mechanism_negative",
            "defect": "The prior candidate rounded GELU(gate) to BF16 before multiplying by up. Pinned FlashInfer computes GELU(gate) * up in FP32 and performs one BF16 rounding on store.",
            "cpu_exact_width_activation_mismatches_from_rejected_form": exact_row[
                "rejected_two_round_activation_mismatches"
            ],
            "cpu_exact_width_e4m3_code_mismatches_from_rejected_form": exact_row[
                "rejected_two_round_code_mismatches"
            ],
            "cpu_exact_width_consumer_probe_mismatches_from_rejected_form": exact_row[
                "rejected_two_round_consumer_mismatches"
            ],
            "prior_h200_m32_output_relative_l2": prior["rows"][0][
                "output_relative_l2_error"
            ],
        },
        "candidate": {
            "mechanism": "One 256-thread CTA per admitted row evaluates one-rounding GELU(tanh)*up, retains 21,504 BF16 values in shared memory through amax, and writes only contiguous E4M3 plus FP32 scale.",
            "dispatch": "candidate for 1<=M<=128; exact stock fallback for M>128",
            "source": artifact("candidate/fused_gelu_mul_dynamic_fp8_sm90.cu"),
            "python_loader": artifact("candidate/gemma4_gelu_fp8.py"),
            "runtime_integration": artifact(
                "candidate/apply_runtime_integration.py"
            ),
            "runtime_integration_check_pass": True,
            "runtime_integration_check": artifact(
                "evidence/RUNTIME_INTEGRATION_CHECK.json"
            ),
            "gpu_contract": artifact("exact_consumer_gpu_contract.py"),
            "exact_consumer": "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
            "graph_capture_contract": binding["graph_capture"],
        },
        "cpu_oracle": {
            "classification": oracle["classification"],
            "pass": oracle["pass"],
            "cases": [
                {
                    "id": row["id"],
                    "elements": row["elements"],
                    "corrected_stock_activation_exact": row[
                        "corrected_stock_activation_exact"
                    ],
                    "corrected_stock_codes_exact": row[
                        "corrected_stock_codes_exact"
                    ],
                    "corrected_stock_scale_exact": row[
                        "corrected_stock_scale_exact"
                    ],
                    "corrected_stock_consumer_exact": row[
                        "corrected_stock_consumer_exact"
                    ],
                }
                for row in oracle["rows"]
            ],
            "artifact": artifact("CPU_REFERENCE_ORACLE.json"),
            "runner": artifact("cpu_reference_oracle.py"),
            "scope": "Dependency-free bit-level BF16/E4M3 reference with complete q/scale consumption and deterministic FP32 dot probes; not a CUDA execution claim.",
        },
        "h200_physical_bound": {
            "c32_stock_boundary_bytes": bound["bytes"]["stock"]["total"],
            "c32_candidate_boundary_bytes": bound["bytes"]["candidate"]["total"],
            "c32_removed_bytes": bound["bytes"]["removed"],
            "c32_removed_mib": bound["bytes"]["removed_mib"],
            "c32_removed_scope": bound["bytes"]["removed_scope"],
            "c32_compulsory_interface_removed_bytes": bound["bytes"][
                "compulsory_interface_removed"
            ],
            "c32_compulsory_interface_removed_mib": bound["bytes"][
                "compulsory_interface_removed_mib"
            ],
            "hbm_floor_savings_us": bound["bytes"]["hbm_floor_savings_us"],
            "compulsory_interface_hbm_floor_savings_us": bound["bytes"][
                "compulsory_interface_hbm_floor_savings_us"
            ],
            "launches_removed": bound["launch_and_waves"]["launches_removed"],
            "stock_grid_waves_per_sequential_launch": bound["launch_and_waves"][
                "stock"
            ][0]["grid_waves"],
            "candidate_grid_waves": bound["launch_and_waves"]["candidate"][
                "grid_waves"
            ],
            "candidate_shared_bytes_per_block": bound["resources"][
                "candidate_total_shared_bytes_per_block"
            ],
            "shared_memory_legal": bound["resources"]["shared_memory_legal"],
            "registers_per_thread": bound["resources"]["registers_per_thread"],
            "absolute_impossible_delete_upper_bound_s_per_request": bound[
                "whole_request"
            ]["absolute_upper_bound_s_per_request"],
            "absolute_impossible_delete_upper_bound_fraction": bound[
                "whole_request"
            ]["absolute_upper_bound_fraction_of_fixed_denominator"],
            "upper_bound_scope": bound["whole_request"]["bound_scope"],
            "artifact": artifact("H200_PHYSICAL_BOUND.json"),
            "runner": artifact("derive_h200_bound.py"),
        },
        "measured_diagnostic_evidence": {
            "scope": prior["scope_warning"],
            "prior_flawed_m32_boundary_delta_us": bound[
                "diagnostic_prior_h200"
            ]["m32"]["descriptive_boundary_delta_us"],
            "prior_flawed_m32_component_delta_us": bound[
                "diagnostic_prior_h200"
            ]["m32"]["descriptive_component_delta_us"],
            "prior_flawed_m2048_regression_fraction": bound[
                "diagnostic_prior_h200"
            ]["m2048"]["regression_fraction"],
            "decision": "The predicted c32 timing direction is plausible but no magnitude transfers. M>128 remains stock.",
            "snapshot": artifact("evidence/PRIOR_H200_COMPONENT_SNAPSHOT.json"),
        },
        "opportunity_register": {
            "ranked_next": ranking["opportunities"][0]["id"],
            "register": artifact("OPPORTUNITY_REGISTER.json"),
            "ranking": artifact("OPPORTUNITY_RANKING.json"),
        },
        "exact_h200_falsifier": {
            "rows": [1, 7, 31, 32, 33, 118],
            "required_weight_key": "model.language_model.layers.0.mlp.down_proj.weight",
            "required_weight_shape": [21504, 5376],
            "required_weight_stride": [1, 21504],
            "required_weight_scale_shape": [1, 5376],
            "required_checkpoint_identity": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4 materialized under this project's inputs/ with index and selected shard SHA-256 values in IMMUTABLE_MANIFEST.json before any bench claim",
            "required_activation_scale_shape_by_m": "[M,1]",
            "required_oracle": "bit-identical BF16 fp8_scaled_mm output with complete candidate output consumption",
            "required_timing": "profiler-off warm stock/candidate boundary and producer-plus-unchanged-consumer medians for every row; corrected candidate lower at all admitted M",
            "predicted_counter_movement": bound["predictions"],
            "compiler_gate": bound["resources"]["register_falsifier"],
            "falsifiers": bound["falsifier"],
        },
        "claims": {
            "source_complete": True,
            "cpu_reference_correct": True,
            "sm90_resource_analytically_legal": True,
            "target_gpu_executed": False,
            "corrected_candidate_performance_pass": None,
            "endpoint_executed": False,
            "endpoint_gain_claimed": False,
            "quality_claimed": False,
            "economic_target_achieved": False,
        },
        "execution_accounting": {
            "authorized_spend_usd": 0.0,
            "actual_spend_usd": 0.0,
            "bench_claimed": False,
            "cuda_invoked": False,
            "provider_mutated": False,
            "gpu_sample_consumed": False,
            "r5_inspected": False,
        },
        "next_action": "Only after a director authorizes positive spend and supplies an H200 lab bench, run the exact-consumer GPU contract once. If all corrected rows are bit-identical and component-positive, apply the source-identity-guarded runtime integration and run one matched fixed-denominator endpoint; otherwise terminalize the corrected decomposition without replay.",
    }
    atomic_json(PROJECT / "MECHANISM_TERMINAL.json", payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
