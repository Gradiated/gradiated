#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any


SHAPES = (
    ("sliding_qkv", 5376, 16384, 50),
    ("sliding_o", 8192, 5376, 50),
    ("global_qkv_k_eq_v_materialized", 5376, 20480, 10),
    ("global_o", 16384, 5376, 10),
    ("gate_up", 5376, 43008, 60),
    ("down", 21504, 5376, 60),
)
FILES = {
    "candidate_source_sha256": "m32_static_persistent_extension.cu",
    "build_script_sha256": "m32_static_scheduler_build.py",
    "runner_sha256": "b200_m32_static_scheduler_component.py",
    "owner_sha256": "b200_m32_static_scheduler_owner.py",
    "dockerfile_sha256": "m32_static_scheduler.Dockerfile",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def shape_record(name: str, k: int, n: int, multiplicity: int) -> dict[str, Any]:
    m = 32
    useful_flops = 2 * m * n * k
    activation_bytes = m * k
    weight_bytes = k * n
    output_bytes = 2 * m * n
    scale_bytes = 4 * (m + 1)
    compulsory_bytes = (
        activation_bytes + weight_bytes + output_bytes + scale_bytes
    )
    output_tiles = math.ceil(n / 128)
    cluster_padded_tiles = math.ceil(output_tiles / 4) * 4
    return {
        "name": name,
        "m": m,
        "k": k,
        "n": n,
        "multiplicity_per_decode_step": multiplicity,
        "useful_flops": useful_flops,
        "compulsory_bytes_lower_bound": compulsory_bytes,
        "compulsory_weight_bytes": weight_bytes,
        "arithmetic_intensity_flop_per_compulsory_byte": (
            useful_flops / compulsory_bytes
        ),
        "stock_and_candidate_output_tiles": output_tiles,
        "stock_and_candidate_cluster_padded_tiles": cluster_padded_tiles,
        "cluster_padding_tiles": cluster_padded_tiles - output_tiles,
        "tile_mnk_after_swap_ab": [128, 64, 256],
        "cluster_mnk_after_swap_ab": [4, 1, 1],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).parent)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "B200_FP8_M32_NEXT_MECHANISM.json",
    )
    args = parser.parse_args()
    root = args.project_root.resolve()
    hashes = {
        field: sha256(root / filename) for field, filename in FILES.items()
    }
    source = (root / "m32_static_persistent_extension.cu").read_text()
    runner = (root / "b200_m32_static_scheduler_component.py").read_text()
    owner = (root / "b200_m32_static_scheduler_owner.py").read_text()
    if "StaticPersistentScheduler" not in source:
        raise RuntimeError("candidate_scheduler_missing")
    if "M16SwapAB" in source or "m <= 32" in source:
        raise RuntimeError("candidate_replays_m16_cutoff")
    if "use_per_token_if_dynamic=True" not in runner:
        raise RuntimeError("production_activation_quantizer_missing")
    if "repair-handshake" not in owner or "repair_wait" not in owner:
        raise RuntimeError("owner_not_repair_capable")

    shapes = [shape_record(*shape) for shape in SHAPES]
    stock_tiles = sum(
        shape["multiplicity_per_decode_step"]
        * shape["stock_and_candidate_output_tiles"]
        for shape in shapes
    )
    padded_tiles = sum(
        shape["multiplicity_per_decode_step"]
        * shape["cluster_padding_tiles"]
        for shape in shapes
    )
    value = {
        "schema_version": 1,
        "classification": (
            "offline_hash_bound_executable_sm100_m32_candidate_unmeasured"
        ),
        "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "question": (
            "Does replacing only CUTLASS 4.2.1 SM100 dynamic persistent CLC "
            "work acquisition with the static persistent scheduler reduce "
            "the exact Gemma 4 M32 FP8 path while preserving every operand, "
            "tile, cluster, mainloop, epilogue, and output bit?"
        ),
        "scope": {
            "gpu_claimed": False,
            "provider_lifecycle_mutated": False,
            "actual_spend_this_phase_usd": 0.0,
            "semantic_class": "semantics_preserving_scheduler_only",
            "target_accelerator": "NVIDIA B200 SXM, sm_100f",
            "model": "google/gemma-4-31B-it",
            "model_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "endpoint_service_seconds_per_request": 0.633995593312477,
            "campaign_target_seconds_per_request": 0.500119281574996,
        },
        "authoritative_identities": {
            "vllm_commit": "6d4a8e6d204a9b2827544003b26321fff62923da",
            "vllm_version": "0.19.1.dev6+g6d4a8e6d2",
            "vllm_base_image": (
                "docker.io/vllm/vllm-openai:gemma4@sha256:"
                "952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
            ),
            "pinned_dispatcher": (
                "csrc/quantization/w8a8/cutlass/c3x/"
                "scaled_mm_sm100_fp8_dispatch.cuh"
            ),
            "pinned_dispatcher_sha256":
                "492ab8232db9f04605e5cd50417ee00902b4476181540f3c223f470d1ced14cf",
            "cutlass_revision": "v4.2.1",
            "cutlass_scheduler_source": (
                "include/cutlass/gemm/kernel/tile_scheduler.hpp"
            ),
            "cutlass_scheduler_source_sha256":
                "ae25f8ab4b75b895a8419f055dbcf1712b1bef9e4d9b5f64eba176901f2672a1",
            "cutlass_source_url": (
                "https://github.com/NVIDIA/cutlass/blob/v4.2.1/"
                "include/cutlass/gemm/kernel/tile_scheduler.hpp"
            ),
            "qualified_endpoint_terminal_sha256":
                "4930d9666167e20096f0343736db6d0ed721ea30fad68f5fc4010ccfeeee9acf",
            "residual_discriminator_sha256":
                "59a91ecd82e55c388f02b3a948c6650d8f260c0d1d92202513059441d9c32415",
            "consumed_m16_terminal": (
                "artifacts/b200-m32-dispatch-patched-cuda13-repair-"
                "20260728t1922z/SM100_TERMINAL.json"
            ),
            "consumed_m16_terminal_sha256":
                "5497ed5b0c669c525077334cbb5d6610b77de02582321acf2bf4e032f6328a8b",
        },
        "consumed_m16_evidence": {
            "classification": "component_negative_stop",
            "weighted_stock_quant_and_gemm_p50_ms": 14.33119960129261,
            "weighted_m16_quant_and_gemm_p50_ms": 14.837440215051174,
            "weighted_gain_fraction": -0.0353243711512401,
            "projected_endpoint_saving_seconds_per_request":
                -0.005663566866423934,
            "interpretation": (
                "The exact-output M16 128x32x128 SwapAB cutoff regressed five "
                "families and is consumed. This candidate does not select, "
                "instantiate, rebuild, or replay that config."
            ),
        },
        "causal_limiter": {
            "evidence_class": "source_backed_hypothesis_unmeasured_on_target",
            "chain": [
                (
                    "Pinned vLLM selects sm100_fp8_config_M64_swap_ab for all "
                    "six M32 K>=4096 families."
                ),
                (
                    "Its GemmUniversal fourth template argument is void; "
                    "CUTLASS 4.2.1 resolves void on Sm100 to "
                    "PersistentTileSchedulerSm100, the dynamic Cluster Launch "
                    "Control scheduler."
                ),
                (
                    "Each family is a uniform dense GEMM with fixed K and "
                    "42-336 output tiles before cluster padding; there is no "
                    "routing, sparsity, or variable per-tile work for dynamic "
                    "assignment to balance."
                ),
                (
                    "Warm stock family medians are only 0.0375-0.0838 ms, so "
                    "CLC query/response and dynamic work bookkeeping can be a "
                    "measurable part of one invocation even though compulsory "
                    "FP8 weight traffic remains dominant."
                ),
                (
                    "StaticPersistentTileScheduler100 removes dynamic work "
                    "acquisition while retaining exactly the stock tile, "
                    "cluster, K reduction, mainloop, epilogue, and SwapAB "
                    "orientation."
                ),
            ],
            "physical_model": {
                "weighted_output_tiles_per_decode_step": stock_tiles,
                "weighted_cluster_padding_tiles_per_decode_step":
                    padded_tiles,
                "weighted_cluster_padding_fraction": padded_tiles / stock_tiles,
                "dynamic_balance_value": (
                    "low: all CTAs within a family have the same K and dense "
                    "work; only edge predicates differ"
                ),
                "unchanged_costs": [
                    "useful tensor-core FLOPs",
                    "tile and K-stage counts",
                    "compulsory activation, weight, scale, and output bytes",
                    "workspace and output layout",
                    "activation quantization kernel",
                ],
                "falsifier": (
                    "Static scheduling is flat/slower while dynamic-scheduler "
                    "activity is not on the critical path, or loss of dynamic "
                    "load balance offsets removed CLC bookkeeping."
                ),
            },
        },
        "mechanism": {
            "name": "m32_static_persistent_same_tile",
            "candidate_source": "m32_static_persistent_extension.cu",
            "candidate_symbol": "M32StaticPersistentGemm::GemmKernel",
            "stock_scheduler_tag": "void",
            "stock_scheduler_resolves_to":
                "cutlass::gemm::PersistentTileSchedulerSm100",
            "candidate_scheduler_tag":
                "cutlass::gemm::StaticPersistentScheduler",
            "candidate_scheduler_resolves_to":
                "cutlass::gemm::StaticPersistentTileScheduler100",
            "stock_and_candidate_tile_mnk": [128, 64, 256],
            "stock_and_candidate_cluster_mnk": [4, 1, 1],
            "stock_and_candidate_swap_ab": True,
            "stock_and_candidate_accumulator": "FP32",
            "stock_and_candidate_output": "BF16",
            "stock_and_candidate_epilogue": "c3x::ScaledEpilogue",
            "mainloop_identity_enforced_at_runtime": True,
            "epilogue_identity_enforced_at_runtime": True,
            "material_distinction_from_m16": (
                "scheduler decomposition only; no M<=32 cutoff, no "
                "128x32x128 instantiation, and no M16 symbol"
            ),
        },
        "production_geometry": {
            "m": 32,
            "decode_steps": 358,
            "concurrency": 32,
            "fp8_gemms_per_decode_step": 240,
            "fp8_gemms_over_completion": 85920,
            "all_k_and_n_multiple_of_128": True,
            "families": shapes,
        },
        "oracle": {
            "runner": "b200_m32_static_scheduler_component.py",
            "expected_families": [shape[0] for shape in SHAPES],
            "expected_rows": 6,
            "stock_consumer": "vllm._custom_ops.cutlass_scaled_mm",
            "candidate_consumer":
                "m32_static_scheduler_ext.m32_static_persistent",
            "activation_producer": (
                "QuantFP8.forward_cuda -> ops.scaled_fp8_quant("
                "scale=None,use_per_token_if_dynamic=True)"
            ),
            "activation_scale_layout": "FP32 [M,1] or [M], one per token",
            "weight_producer": (
                "Fp8OnlineLinearMethod.process_weights_after_loading -> "
                "ops.scaled_fp8_quant(weight_NK,scale=None).t()"
            ),
            "weight_scale_layout": "FP32 scalar, one per tensor",
            "weight_storage_orientation":
                "KxN column-major view, stride(0)=1, storage_offset=0",
            "scale_convention": (
                "forward scales; quantizer multiplies by reciprocal, scaled-MM "
                "epilogue multiplies activation and weight scales"
            ),
            "identity": (
                "Stock and candidate receive the same in-process FP8 tensor "
                "objects and scale tensor objects; hashes, shapes, strides, "
                "storage offsets, dtypes, orientation, and producer symbols "
                "are persisted in every row."
            ),
            "numerical_gate": (
                "finite and bitwise-identical BF16 stock/candidate output for "
                "every family before that family's timing"
            ),
            "fault_attribution": (
                "stock and candidate first calls synchronize separately and "
                "atomically update INVOCATION_STATE.json"
            ),
        },
        "measurement": {
            "unit": "milliseconds per one M32 family invocation",
            "warmup": 5,
            "paired_repetitions": 31,
            "method": (
                "alternating stock/candidate order, profiler off, CUDA events, "
                "one event synchronization per call; every output consumed "
                "outside its event interval"
            ),
            "stage_checkpointing": (
                "each complete family writes ROW_<family>.json atomically; "
                "--resume skips complete rows and retries only the incomplete "
                "family"
            ),
            "primary_figure_of_merit":
                "multiplicity-weighted quant+GEMM median saved ms/decode step",
            "endpoint_projection": (
                "saving_s_per_request = 358 * weighted_saved_ms_per_step / "
                "1000 / 32"
            ),
        },
        "predicted_effect": {
            "evidence_class": "inferred_before_target_execution",
            "component_latency_gain_interval_fraction": [0.0, 0.05],
            "projected_endpoint_saving_seconds_per_request_interval": [
                0.0,
                0.004,
            ],
            "projected_candidate_service_seconds_per_request_interval": [
                0.629995593312477,
                0.633995593312477,
            ],
            "counter_predictions": {
                "sm__cycles_elapsed.avg": (
                    "1-5% lower for positive families; unchanged tensor work"
                ),
                "dram__bytes_read.sum": "within +/-2% of stock",
                "tensor_instruction_count": "identical within measurement error",
                "registers_shared_storage_and_spills": (
                    "same compiler resource footprint except scheduler state; "
                    "no new spills"
                ),
                "dynamic_clc_work_acquisition": (
                    "removed from candidate SASS/scheduler path"
                ),
            },
            "request_interpretation": (
                "This narrow scheduler cannot close the 0.133876 s/request "
                "campaign gap alone; a reproducible positive result is still "
                "stackable and identifies CLC overhead as a live residual."
            ),
        },
        "stop_rule": {
            "exactness": (
                "stop before timing on first nonfinite or non-bitwise family; "
                "persist that family and do not run later families"
            ),
            "negative": (
                "stop after the six-family component with no endpoint if any "
                "family regresses >5%, weighted quant+GEMM saving is <=0, or "
                "projected saving is <0.001 s/request"
            ),
            "positive": (
                "return to director for endpoint disposition only if all six "
                "families are bitwise equal, none regresses >5%, weighted "
                "quant+GEMM saving is positive, and projected saving is at "
                "least 0.001 s/request"
            ),
            "no_replay": (
                "complete family rows and any decision-bearing exactness or "
                "six-family terminal are consumed; repair only missing build, "
                "retrieval, or the incomplete family"
            ),
            "forbidden": [
                "M16 SwapAB rebuild or replay",
                "M<=32 cutoff change",
                "block-E4M3 or any operand/scale representation change",
                "provider create before a later director execution binding",
            ],
        },
        "lifecycle": {
            "claim_allowed_now": False,
            "director_gate": (
                "A later director must provision/revalidate an exact B200, "
                "register it in the shared pool, and issue a hash-bound "
                "execution binding with claim_allowed=true."
            ),
            "current_actual_spend_usd": 9.73,
            "authorized_cumulative_spend_usd": 16.0,
            "maximum_remaining_exposure_usd": 6.27,
            "maximum_provider_lifecycle_minutes_at_7p15_usd_per_hour":
                52.61538461538461,
            "maximum_claim_owner_minutes": 42,
            "provider_setup_cleanup_reserve_minutes": 10.615384615384613,
            "required_execution_binding": [
                "mechanism_sha256",
                "bench",
                "claim_start_by_utc",
                "deadline_utc",
                "release_by_utc",
                "remote_root",
                "claim_allowed=true",
            ],
            "owner": "b200_m32_static_scheduler_owner.py",
            "repair_contract": {
                "tool": "research/factory/tools/repair-handshake",
                "retains_claim_and_heartbeat": True,
                "fresh_repair_id_per_generation": True,
                "supported_retry_scopes": [
                    "source_stage",
                    "build",
                    "consumer:<incomplete-family>",
                    "retrieve",
                ],
                "completed_family_rows_are_never_replayed": True,
                "deadline_disposition": (
                    "retrieve diagnostics and release maintenance only at the "
                    "absolute deadline or an unsafe/unreachable guest"
                ),
            },
            "release_predicate": (
                "owner independently validates exactness-stop evidence or all "
                "six row identities, layout/provenance, numerical oracles, "
                "source/module hashes, timing fields, and terminal class"
            ),
            "terminal_release": (
                "available with derived image, immutable source, CUTLASS, "
                "compiled module, and artifacts resident; no server occupies "
                "the accelerator"
            ),
            "detached_launch": {
                "tool": "research/factory/tools/detached-owner",
                "unit_manager": "pid",
                "require_status_live_snapshot": True,
                "record_in_status_active_session": [
                    "absolute owner state path as unit",
                    "pid",
                    "start_ticks",
                    "unit_manager=pid",
                    "deadline_utc",
                    "artifact_root",
                ],
                "command_template": (
                    "research/factory/tools/detached-owner start "
                    "--unit-manager pid --state <absolute-owner-state> "
                    "--log <absolute-owner-log> --cwd /root/workspace -- "
                    "python3 <project>/b200_m32_static_scheduler_owner.py "
                    "--repo-root /root/workspace --project-root <project> "
                    "--mechanism <project>/B200_FP8_M32_NEXT_MECHANISM.json "
                    "--execution-binding <director-binding> --lab <lab> "
                    "--output <artifact-root> --ssh-key <provider-identity> "
                    "--known-hosts <inventory-known-hosts>"
                ),
            },
        },
        "artifact_hashes": hashes,
        "local_validation": {
            "runner_command": (
                "python3 b200_m32_static_scheduler_component.py "
                "--validate-only artifacts/m32-next-local/runner.json"
            ),
            "owner_command": (
                "python3 b200_m32_static_scheduler_owner.py --repo-root "
                "/root/workspace --project-root . --mechanism "
                "B200_FP8_M32_NEXT_MECHANISM.json --validate-only "
                "artifacts/m32-next-local/owner.json"
            ),
            "cuda_required_for_scientific_acceptance": True,
            "offline_validation_is_not_a_scientific_sample": True,
        },
    }
    atomic_json(args.output, value)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sha256": sha256(args.output),
                "classification": value["classification"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
