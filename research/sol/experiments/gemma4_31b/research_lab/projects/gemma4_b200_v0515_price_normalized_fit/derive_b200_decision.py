#!/usr/bin/env python3
import hashlib
import json
import math
from decimal import Decimal, getcontext
from pathlib import Path

from materialize_source_evidence import COMMIT, SOURCES


getcontext().prec = 40
ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[6]
GIB = 1 << 30
TARGET = Decimal("0.14")
RATE = Decimal("5.15")
UTILIZATION = Decimal("0.90")
REQUESTS = 791
MODEL = "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def selected(rows, identifier):
    matches = [row for row in rows if row["id"] == identifier]
    require(len(matches) == 1, f"expected_one:{identifier}")
    return matches[0]


def atomic(path, value):
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    part.replace(path)


def decimal_text(value):
    return format(value, "f")


def workload(rows, begin, end):
    arm = rows[begin:end]
    require([row["i"] for row in arm] == list(range(begin, end)), "request_ids")
    first_arrival = Decimal(str(arm[0]["scheduled_s"]))
    last_arrival = Decimal(str(arm[-1]["scheduled_s"]))
    return {
        "begin": begin,
        "end_exclusive": end,
        "requests": len(arm),
        "prompt_tokens": sum(row["usage"]["prompt_tokens"] for row in arm),
        "completion_tokens": sum(
            row["usage"]["completion_tokens"] for row in arm
        ),
        "total_tokens": sum(row["usage"]["total_tokens"] for row in arm),
        "first_bound_arrival_seconds": decimal_text(first_arrival),
        "last_bound_arrival_seconds": decimal_text(last_arrival),
        "bound_arrival_span_seconds": decimal_text(last_arrival - first_arrival),
    }


def economics(arm):
    tokens = Decimal(arm["total_tokens"])
    count = Decimal(arm["requests"])
    span = Decimal(arm["bound_arrival_span_seconds"])
    raw_elapsed = TARGET * tokens * Decimal(3600) / (RATE * Decimal(1_000_000))
    sustainable_elapsed = raw_elapsed * UTILIZATION
    arrival_floor_cost = RATE * span / Decimal(3600) / tokens * Decimal(1_000_000)
    return {
        **arm,
        "raw_elapsed_ceiling_seconds": decimal_text(raw_elapsed),
        "raw_service_ceiling_seconds_per_request": decimal_text(
            raw_elapsed / count
        ),
        "sustainable_90pct_elapsed_ceiling_seconds": decimal_text(
            sustainable_elapsed
        ),
        "sustainable_90pct_service_ceiling_seconds_per_request": decimal_text(
            sustainable_elapsed / count
        ),
        "zero_latency_arrival_floor_seconds": decimal_text(span),
        "zero_latency_arrival_floor_service_seconds_per_request": decimal_text(
            span / count
        ),
        "zero_latency_arrival_floor_cost_usd_per_million_total_tokens": (
            decimal_text(arrival_floor_cost)
        ),
        "zero_latency_arrival_floor_sustainable_cost_usd_per_million_total_tokens": (
            decimal_text(arrival_floor_cost / UTILIZATION)
        ),
        "raw_elapsed_gate_possible": span <= raw_elapsed,
        "sustainable_elapsed_gate_possible": span <= sustainable_elapsed,
        "raw_required_arrival_time_scale": decimal_text(raw_elapsed / span),
        "sustainable_required_arrival_time_scale": decimal_text(
            sustainable_elapsed / span
        ),
        "raw_arrival_floor_over_ceiling": decimal_text(span / raw_elapsed),
        "sustainable_arrival_floor_over_ceiling": decimal_text(
            span / sustainable_elapsed
        ),
    }


def source(path):
    return (ROOT / "evidence" / "official-v0.5.15" / path).read_text()


def main():
    binding = load(ROOT / "DIRECTOR_BINDING.json")
    verified_files = {}
    for raw_path, expected in binding["files"].items():
        path = Path(raw_path)
        require(path.is_file(), f"binding_file_missing:{path}")
        actual = digest(path)
        require(actual == expected, f"binding_hash_mismatch:{path}")
        verified_files[str(path)] = {
            "bytes": path.stat().st_size,
            "sha256": actual,
        }
    require(binding["identity"]["accelerator"] == "nvidia-b200-sxm", "accelerator")
    require(binding["identity"]["checkpoint"] == MODEL, "model")
    require(binding["identity"]["image"] == IMAGE, "image")
    require(binding["identity"]["runtime_commit"] == COMMIT, "commit")

    candidate_path = next(
        Path(path)
        for path in binding["files"]
        if path.endswith("candidate-v0.5.15/CANDIDATE_RUNTIME.json")
    )
    candidate = load(candidate_path)
    require(candidate["candidate"]["commit"] == COMMIT, "candidate_commit")
    require(candidate["candidate"]["official_image"] == IMAGE, "candidate_image")
    require(candidate["candidate"]["cuda_version"] == "12.9.1", "candidate_cuda")
    require(candidate["candidate"]["release"] == "v0.5.15", "candidate_release")
    require(all(candidate["source_contract"].values()), "candidate_source_contract")
    candidate_root = candidate_path.parent
    candidate_manifest = load(candidate_root / "SHA256SUMS.json")
    for relative, expected in candidate_manifest.items():
        path = candidate_root / relative
        require(path.is_file(), f"candidate_file_missing:{relative}")
        require(digest(path) == expected, f"candidate_hash_mismatch:{relative}")

    source_manifest = {}
    for relative, expected in SOURCES.items():
        path = ROOT / "evidence" / "official-v0.5.15" / relative
        require(path.is_file(), f"official_source_missing:{relative}")
        actual = digest(path)
        require(actual == expected, f"official_source_hash_mismatch:{relative}")
        source_manifest[relative] = {
            "bytes": path.stat().st_size,
            "sha256": actual,
            "upstream": (
                "https://github.com/sgl-project/sglang/blob/"
                f"{COMMIT}/{relative}"
            ),
        }

    dockerfile = (
        candidate_root / "source" / "docker" / "Dockerfile"
    ).read_text()
    fp8 = source("python/sglang/srt/layers/quantization/fp8.py")
    fp8_utils = source("python/sglang/srt/layers/quantization/fp8_utils.py")
    model_runner = source("python/sglang/srt/model_executor/model_runner.py")
    common = source("python/sglang/srt/utils/common.py")
    cmake = source("sgl-kernel/CMakeLists.txt")
    fp8_gemm = source("sgl-kernel/csrc/gemm/fp8_gemm_kernel.cu")
    load_utils = source("sgl-kernel/python/sgl_kernel/load_utils.py")
    gemma = (
        candidate_root
        / "source/python/sglang/srt/models/gemma4_causal.py"
    ).read_text()
    triton_backend = (
        candidate_root
        / "source/python/sglang/srt/layers/attention/triton_backend.py"
    ).read_text()
    speculative_hook = (
        candidate_root
        / "source/python/sglang/srt/arg_groups/speculative_hook.py"
    ).read_text()
    graph_runner = (
        candidate_root
        / "source/python/sglang/srt/model_executor/runner/"
        "decode_cuda_graph_runner.py"
    ).read_text()

    source_checks = {
        "image_accepts_cuda_12_9": (
            '12.9.1) CUINDEX=129' in dockerfile
            and "sglang_kernel-${SGL_KERNEL_VERSION}+cu129" in dockerfile
        ),
        "sm100_defined_for_cuda_12_8_or_newer": (
            "device_capability_majors=[10], cuda_version=(12, 8)" in common
        ),
        "sm100_common_ops_built": (
            '"-gencode=arch=compute_100a,code=sm_100a"' in cmake
            and "common_ops_sm100_build" in cmake
            and "sgl_kernel/sm100" in cmake
        ),
        "sm100_common_ops_loaded": (
            'ops_subdir = "sm100"' in load_utils
            and "compute_capability == 90" in load_utils
        ),
        "dynamic_fp8_online_quantization": (
            "If checkpoint not serialized fp8, quantize the weights." in fp8
            and "qweight, weight_scale = per_token_group_quant_fp8(" in fp8
            and "return apply_fp8_linear(" in fp8
        ),
        "dynamic_fp8_sm100_dispatch": (
            "if major >= 9:" in fp8_utils
            and "return cuda_version >= (12, 0)" in fp8_utils
            and "output = fp8_scaled_mm(" in fp8_utils
        ),
        "sm100_fp8_cutlass_kernel": (
            "cutlass::arch::Sm100" in fp8_gemm
            and "sm100_fp8_dispatch_shape" in fp8_gemm
            and "if (sm_version >= 100)" in fp8_gemm
        ),
        "sm100_m384_tile": (
            "using CTAShapeDefault = Shape<_256, _128, _64>;" in fp8_gemm
            and "using ClusterShapeDefault = Shape<_2, _2, _1>;" in fp8_gemm
            and "// m in (256, inf]" in fp8_gemm
        ),
        "fp8_e5m2_kv_dtype": (
            'self.server_args.kv_cache_dtype == "fp8_e5m2"' in model_runner
            and "self.kv_cache_dtype = torch.float8_e5m2" in model_runner
        ),
        "gemma_hybrid_attention": (
            'layer_type == "sliding_attention"' in gemma
            and "RadixAttention(" in gemma
            and "gemma_qkv_rmsnorm(" in gemma
        ),
        "triton_target_verify": (
            "forward_batch.forward_mode.is_target_verify()" in triton_backend
            and "self.extend_attention_fwd(" in triton_backend
        ),
        "native_ngram_depth_12": (
            "server_args.speculative_num_draft_tokens = 12" in speculative_hook
        ),
        "ngram_cuda_graph_capture": (
            "NgramVerifyInput" in graph_runner
            and "speculative_num_draft_tokens" in graph_runner
        ),
    }
    require(all(source_checks.values()), "official_sm100_source_trace")

    accelerator_inventory = load(
        WORKSPACE / "research/factory/data/accelerator_inventory.json"
    )
    b200 = selected(
        accelerator_inventory["accelerators"], "nvidia-b200-sxm"
    )
    require(b200["architecture_profile_id"] == "nvidia-sm100", "inventory_sm100")
    require(b200["memory"]["capacity_gb"] == 180, "inventory_capacity")
    require(b200["memory"]["bandwidth_gb_s"] == 8000, "inventory_bandwidth")
    require("fp8" in b200["numeric_formats"], "inventory_fp8")

    price_inventory = load(WORKSPACE / "research/factory/data/gpu_prices.json")
    b200_price = selected(price_inventory["accelerators"], "nvidia-b200-sxm")
    require(
        Decimal(str(b200_price["production_planning_usd_per_gpu_hour"]))
        == RATE,
        "planning_rate",
    )

    h100_path = next(
        Path(path)
        for path in binding["files"]
        if path.endswith("H100_FIT_HURDLE.json")
    )
    h100_fit = load(h100_path)
    require(h100_fit["binding_verified"] is True, "h100_chain_binding")
    require(
        h100_fit["memory"]["checkpoint_total_parameters"] == 32682372656,
        "parameters",
    )
    require(
        (
            h100_fit["memory"]["full_attention_layers"],
            h100_fit["memory"]["sliding_attention_layers"],
        )
        == (10, 50),
        "layer_geometry",
    )
    require(
        (
            h100_fit["memory"]["full_kv_bytes_per_token"],
            h100_fit["memory"]["swa_kv_bytes_per_token"],
        )
        == (40960, 409600),
        "kv_geometry",
    )

    capacity_gib = Decimal(180_000_000_000) / Decimal(GIB)
    static_fraction = Decimal("0.85")
    static_budget_gib = capacity_gib * static_fraction
    weight_gib = Decimal(
        str(h100_fit["memory"]["model_weight_runtime_gib_measured"])
    )
    non_weight_gib = Decimal(
        str(h100_fit["memory"]["pre_pool_non_weight_gib_measured"])
    )
    graph_gib = Decimal(
        str(h100_fit["memory"]["cuda_graph_gib_measured_same_shape"])
    )
    kv_budget_gib = static_budget_gib - weight_gib - non_weight_gib
    bytes_per_full_pool_token = Decimal(40960) + Decimal("0.8") * Decimal(409600)
    full_pool_floor = math.floor(
        kv_budget_gib * Decimal(GIB) / bytes_per_full_pool_token
    )
    swa_pool_floor = math.floor(Decimal(full_pool_floor) * Decimal("0.8"))
    full_context_floor = min(
        full_pool_floor // 4584,
        swa_pool_floor // 1036,
    )
    required_full_c32 = 32 * 4584
    required_swa_c32 = 32 * 1036
    post_graph_headroom_gib = capacity_gib - static_budget_gib - graph_gib
    fit_checks = {
        "full_pool_c32": full_pool_floor >= required_full_c32,
        "swa_pool_c32": swa_pool_floor >= required_swa_c32,
        "post_graph_headroom_at_least_16_gib": (
            post_graph_headroom_gib >= Decimal(16)
        ),
    }
    require(all(fit_checks.values()), "analytical_b200_fit")

    request_path = next(
        Path(path)
        for path in binding["files"]
        if path.endswith("candidate-v0.5.15/inputs/requests.jsonl")
    )
    rows = [json.loads(line) for line in request_path.read_text().splitlines()]
    endpoint = economics(workload(rows, 0, 791))
    post_calibration = economics(workload(rows, 32, 791))
    require(endpoint["total_tokens"] == 3616452, "endpoint_tokens")
    require(post_calibration["total_tokens"] == 3470148, "post_calibration_tokens")
    require(not endpoint["raw_elapsed_gate_possible"], "raw_must_be_impossible")
    require(
        not endpoint["sustainable_elapsed_gate_possible"],
        "sustainable_must_be_impossible",
    )
    require(
        not post_calibration["raw_elapsed_gate_possible"],
        "post_calibration_raw_must_be_impossible",
    )

    average_tokens = Decimal(endpoint["total_tokens"]) / Decimal(REQUESTS)
    parameters = Decimal(
        h100_fit["memory"]["checkpoint_total_parameters"]
    )
    dense_flops_per_request = Decimal(2) * parameters * average_tokens
    sustainable_service = Decimal(
        endpoint["sustainable_90pct_service_ceiling_seconds_per_request"]
    )
    raw_service = Decimal(
        endpoint["raw_service_ceiling_seconds_per_request"]
    )
    target_verify_m = 32 * 12
    sm100_tile_m = 256
    sm100_tile_n = 128
    projection_tiles = {
        "sliding_qkv_5376x16384": (
            math.ceil(target_verify_m / sm100_tile_m)
            * math.ceil(16384 / sm100_tile_n)
        ),
        "full_qkv_5376x20480": (
            math.ceil(target_verify_m / sm100_tile_m)
            * math.ceil(20480 / sm100_tile_n)
        ),
        "local_o_8192x5376": (
            math.ceil(target_verify_m / sm100_tile_m)
            * math.ceil(5376 / sm100_tile_n)
        ),
        "full_o_16384x5376": (
            math.ceil(target_verify_m / sm100_tile_m)
            * math.ceil(5376 / sm100_tile_n)
        ),
        "gate_up_5376x43008": (
            math.ceil(target_verify_m / sm100_tile_m)
            * math.ceil(43008 / sm100_tile_n)
        ),
        "down_21504x5376": (
            math.ceil(target_verify_m / sm100_tile_m)
            * math.ceil(5376 / sm100_tile_n)
        ),
    }

    support_fit = {
        "schema_version": 1,
        "result": "official_sm100_support_and_safe_analytical_fit",
        "binding_verified": True,
        "verified_files": verified_files,
        "official_source_manifest": source_manifest,
        "source_checks": source_checks,
        "identity": {
            "accelerator": "nvidia-b200-sxm",
            "architecture": "SM100 / compute capability 10.0",
            "checkpoint": MODEL,
            "image": IMAGE,
            "runtime_commit": COMMIT,
            "runtime_release": "v0.5.15",
            "runtime_cuda": "12.9.1",
            "sglang_kernel_version": "0.4.4",
        },
        "memory": {
            "capacity_inventory_gb": 180,
            "capacity_conservative_gib": decimal_text(capacity_gib),
            "static_fraction": decimal_text(static_fraction),
            "static_budget_conservative_gib": decimal_text(static_budget_gib),
            "model_weight_runtime_gib_same_shape_measured_h200": decimal_text(
                weight_gib
            ),
            "pre_pool_non_weight_gib_same_shape_measured_h200": decimal_text(
                non_weight_gib
            ),
            "cuda_graph_gib_same_shape_measured_h200": decimal_text(graph_gib),
            "kv_budget_conservative_gib": decimal_text(kv_budget_gib),
            "full_pool_token_floor": full_pool_floor,
            "swa_pool_token_floor": swa_pool_floor,
            "required_full_pool_tokens_for_c32": required_full_c32,
            "required_swa_pool_tokens_for_c32": required_swa_c32,
            "full_context_concurrency_floor": full_context_floor,
            "post_graph_headroom_conservative_gib": decimal_text(
                post_graph_headroom_gib
            ),
            "checks": fit_checks,
        },
        "physical_screen": {
            "evidence_boundary": (
                "Source-backed and analytical only; no B200 execution or "
                "transferred H100/H200 throughput."
            ),
            "target_verify_m_at_c32_depth12": target_verify_m,
            "sm100_default_m_gt_256_cta_shape": [256, 128, 64],
            "sm100_default_cluster_shape": [2, 2, 1],
            "logical_output_tiles_by_projection": projection_tiles,
            "average_total_tokens_per_request": decimal_text(average_tokens),
            "dense_flops_lower_bound_per_request": decimal_text(
                dense_flops_per_request
            ),
            "raw_required_effective_tflops": decimal_text(
                dense_flops_per_request / raw_service / Decimal(10**12)
            ),
            "sustainable_required_effective_tflops": decimal_text(
                dense_flops_per_request / sustainable_service / Decimal(10**12)
            ),
            "b200_fp8_peak_tflops_inventory": b200["peak_math"]["fp8_tflops"],
            "sustainable_required_fraction_of_fp8_peak": decimal_text(
                dense_flops_per_request
                / sustainable_service
                / (Decimal(b200["peak_math"]["fp8_tflops"]) * Decimal(10**12))
            ),
            "interpretation": (
                "Depth-12 c32 target verification produces M=384 and selects "
                "the official SM100 M>256 FP8 kernel. Compute physics alone "
                "does not reject the placement, but no achieved throughput is "
                "claimed and the bound arrival floor independently closes it."
            ),
        },
    }
    atomic(ROOT / "B200_SUPPORT_FIT.json", support_fit)

    raw_max_rate = (
        TARGET
        * Decimal(endpoint["total_tokens"])
        * Decimal(3600)
        / (
            Decimal(endpoint["zero_latency_arrival_floor_seconds"])
            * Decimal(1_000_000)
        )
    )
    decision = {
        "schema_version": 1,
        "decision": "typed_none",
        "classification": "bound_arrival_floor_exceeds_price_normalized_hurdle",
        "binding_verified": True,
        "gpu_claimed": False,
        "provider_mutated": False,
        "spend_usd": 0.0,
        "candidate_sample_consumed": False,
        "support_and_fit": {
            "official_sm100_support_source_proved": True,
            "analytical_memory_fit_safe": True,
            "b200_throughput_measured": False,
        },
        "economics": {
            "planning_usd_per_gpu_hour": decimal_text(RATE),
            "target_usd_per_million_total_tokens": decimal_text(TARGET),
            "sustainable_utilization": decimal_text(UTILIZATION),
            "endpoint_791": endpoint,
            "post_calibration_759": post_calibration,
            "maximum_planning_rate_at_zero_latency_raw": decimal_text(
                raw_max_rate
            ),
            "maximum_planning_rate_at_zero_latency_sustainable_90pct": (
                decimal_text(raw_max_rate * UTILIZATION)
            ),
        },
        "reason": (
            "The hash-bound arrival schedule is part of requests.jsonl. Its "
            "last request is released after both the raw and 90%-sustainable "
            "elapsed-cost ceilings, so no hardware speed can make the admitted "
            "endpoint pass without changing workload timing or price."
        ),
        "reopen_only_if": [
            (
                "A new director binding explicitly permits at least "
                f"{endpoint['sustainable_arrival_floor_over_ceiling']}x demand "
                "multiplexing/arrival compression while preserving request bytes "
                "and semantic gates."
            ),
            (
                "A matching committed B200 planning rate is at most "
                f"{decimal_text(raw_max_rate * UTILIZATION)} USD/GPU-hour for "
                "the 90%-sustainable gate."
            ),
            "The campaign changes the cost target or workload contract.",
        ],
        "artifacts": {
            "support_fit": "B200_SUPPORT_FIT.json",
            "official_source_root": "evidence/official-v0.5.15",
        },
    }
    atomic(ROOT / "TYPED_NONE.json", decision)


if __name__ == "__main__":
    main()
