#!/usr/bin/env python3
"""Verify immutable inputs and persist the grouped LM-head causal model."""

from __future__ import annotations

import hashlib
import json
import pathlib


PROJECT = pathlib.Path(__file__).resolve().parent
DEPTHS = 12
BATCH = 32
HIDDEN = 5376
VOCAB = 262144
BYTES_PER_BF16 = 2
H200_HBM_BYTES_PER_SECOND = 4.8e12
H200_BF16_FLOPS_PER_SECOND = 989.5e12
OBSERVED_180_CALL_US = 124664.39399999999
OBSERVED_STEPS = 15
TRACE_WINDOW_US = 2375141.908203125
DIRECTOR_BINDING_SHA256 = (
    "150c2227624c42783aa5728ed107604db317aef504368b74b9730e01f99e1fec"
)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    director_binding = PROJECT / "DIRECTOR_BINDING.json"
    observed_director_binding = sha256(director_binding)
    if observed_director_binding != DIRECTOR_BINDING_SHA256:
        raise RuntimeError(
            f"director_binding_hash_mismatch:{observed_director_binding}"
        )
    binding = json.loads(director_binding.read_text())
    binding_rows = []
    for item in binding["bound_evidence"]:
        external = (PROJECT / item["path"]).resolve()
        observed = sha256(external)
        if observed != item["sha256"]:
            raise RuntimeError(f"bound_hash_mismatch:{external}:{observed}")
        local_names = {
            "INTERVENTION_BINDING.json": "INTERVENTION_BINDING.json",
            "LATEST_TERMINAL.json": "QUALIFIED_LATEST_TERMINAL.json",
            "decode_equivalent_lm_head.py": "decode_equivalent_lm_head.py",
            "FINAL_TERMINAL.json": "CRITICAL_PATH_FINAL_TERMINAL.json",
            "TRACE_ANALYSIS_REPAIR.json": "TRACE_ANALYSIS_REPAIR.json",
        }
        local = PROJECT / "inputs/bound" / local_names[external.name]
        if sha256(local) != observed:
            raise RuntimeError(f"materialized_hash_mismatch:{local}")
        binding_rows.append(
            {
                "external_path": str(external),
                "project_local_path": str(local.relative_to(PROJECT)),
                "sha256": observed,
            }
        )

    weight_bytes = HIDDEN * VOCAB * BYTES_PER_BF16
    activation_bytes = DEPTHS * BATCH * HIDDEN * BYTES_PER_BF16
    output_bytes = DEPTHS * BATCH * VOCAB * BYTES_PER_BF16
    useful_flops = 2 * DEPTHS * BATCH * HIDDEN * VOCAB
    sequential_compulsory_bytes = DEPTHS * weight_bytes + activation_bytes + output_bytes
    ideal_reuse_bytes = weight_bytes + activation_bytes + output_bytes
    observed_step_us = OBSERVED_180_CALL_US / OBSERVED_STEPS
    compile_result = PROJECT / "artifacts/SM90_COMPILE_RESULT.json"
    compiled = json.loads(compile_result.read_text())
    if compiled["name"] != "depth_interleaved_grouped_lm_head":
        raise RuntimeError(f"candidate_compile_symbol:{compiled['name']}")
    auxiliary_inputs = [
        "inputs/bound/CHECKPOINT_MANIFEST.json",
        "inputs/bound/logits_processor.py",
        "inputs/bound/forward_batch_info.py",
        "inputs/bound/endpoint_entrypoint.py",
        "inputs/bound/exact_runner.py",
        "inputs/bound/model.safetensors.index.json",
        "inputs/bound/config.json",
    ]
    result = {
        "schema_version": 1,
        "classification": "analytical_and_source_bound_offline_evidence",
        "all_director_hashes_match": True,
        "director_binding_sha256": observed_director_binding,
        "binding_rows": binding_rows,
        "auxiliary_project_local_inputs": [
            {"path": path, "sha256": sha256(PROJECT / path)}
            for path in auxiliary_inputs
        ],
        "production_geometry": {
            "depths": DEPTHS,
            "batch": BATCH,
            "hidden": HIDDEN,
            "vocab": VOCAB,
            "dtype": "BF16",
            "weight_bytes": weight_bytes,
            "activation_bytes": activation_bytes,
            "output_bytes": output_bytes,
            "useful_flops_per_verification_step": useful_flops,
        },
        "measured_baseline": {
            "kernel": "nvjet_sm90_tst_512x32_64x3_2x1_v_bz_TNT",
            "calls": 180,
            "steps": OBSERVED_STEPS,
            "summed_us": OBSERVED_180_CALL_US,
            "us_per_step": observed_step_us,
            "lm_head_fraction_of_profile_window": (
                OBSERVED_180_CALL_US / TRACE_WINDOW_US
            ),
        },
        "physical_model": {
            "h200_sms": 132,
            "h200_l2_bytes": 60 * 1024 * 1024,
            "h200_hbm_bytes_per_second_vendor_prior": H200_HBM_BYTES_PER_SECOND,
            "h200_bf16_flops_per_second_vendor_prior": H200_BF16_FLOPS_PER_SECOND,
            "sequential_compulsory_bytes": sequential_compulsory_bytes,
            "ideal_depth_reuse_bytes": ideal_reuse_bytes,
            "sequential_arithmetic_intensity_flop_per_byte": (
                useful_flops / sequential_compulsory_bytes
            ),
            "ideal_reuse_arithmetic_intensity_flop_per_byte": (
                useful_flops / ideal_reuse_bytes
            ),
            "sequential_hbm_floor_us": (
                sequential_compulsory_bytes / H200_HBM_BYTES_PER_SECOND * 1e6
            ),
            "ideal_reuse_hbm_floor_us": (
                ideal_reuse_bytes / H200_HBM_BYTES_PER_SECOND * 1e6
            ),
            "bf16_compute_floor_us": (
                useful_flops / H200_BF16_FLOPS_PER_SECOND * 1e6
            ),
        },
        "candidate": {
            "source": "grouped_lm_head.py",
            "source_sha256": sha256(PROJECT / "grouped_lm_head.py"),
            "oracle": "exact_consumer_component.py",
            "oracle_sha256": sha256(PROJECT / "exact_consumer_component.py"),
            "sm90_compile_result": str(compile_result.relative_to(PROJECT)),
            "sm90_compile_result_sha256": sha256(compile_result),
            "sm90_compiler_metadata": compiled["metadata"],
            "counter_probe": "counter_probe.py",
            "counter_probe_sha256": sha256(PROJECT / "counter_probe.py"),
            "conditional_endpoint": "endpoint_pair.py",
            "conditional_endpoint_sha256": sha256(PROJECT / "endpoint_pair.py"),
            "remote_experiment": "remote_experiment.py",
            "remote_experiment_sha256": sha256(PROJECT / "remote_experiment.py"),
            "durable_owner": "run_bench_owner.py",
            "durable_owner_sha256": sha256(PROJECT / "run_bench_owner.py"),
            "launches_per_step": 1,
            "program_order": "vocabulary block major, depth minor",
            "independent_numerical_domain": (
                "Each program owns one depth's [32,256] FP32 accumulator and "
                "runs the full K=5376 reduction; no depth is folded into M."
            ),
            "reuse_hypothesis": (
                "The 12 consecutive programs for a vocabulary tile request the "
                "same contiguous BF16 weight tile while it is resident in H200 L2."
            ),
            "predicted_counter": (
                "DRAM read bytes per 12-depth step fall below the 12x-weight "
                "baseline while candidate launches fall from 12 to one."
            ),
            "falsifiers": [
                "Any target argmax or accepted-prefix mismatch.",
                "Candidate replay changes top-two IDs or values.",
                "Warm candidate median is not below the 12-call control.",
                "Measured DRAM reads remain near 12 times the tied-weight bytes.",
            ],
        },
        "whole_request_bound": {
            "maximum_profile_window_fraction_if_lm_head_eliminated": (
                OBSERVED_180_CALL_US / TRACE_WINDOW_US
            ),
            "credible_positive_gate": (
                "A reproducibly faster exact component implies a positive bound; "
                "only the exact endpoint may establish transfer."
            ),
        },
    }
    atomic(PROJECT / "OFFLINE_CAUSAL_MODEL.json", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
