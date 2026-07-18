#!/usr/bin/env python3
import hashlib
import json
import math
import os
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 40

PROJECT = Path(__file__).resolve().parent
ROOT = PROJECT.parents[6]

INPUTS = {
    "accelerator_inventory": (
        ROOT / "research/factory/data/accelerator_inventory.json",
        "bcb33ac6814400f6ab79faa7e44c0ced2d6fe2ac5d19dc43f4ee10b12d7ea6b8",
    ),
    "gpu_prices": (
        ROOT / "research/factory/data/gpu_prices.json",
        "3f403d67a92fc91be85bbd27dede85f5f91c3fd2df25ef8dcef2a344acbd1e01",
    ),
    "geometry": (
        PROJECT.parent / "exact_geometry_runtime_opportunities/GEOMETRY.json",
        "024450cd944c7827db442d8274e1e0cccae114ee3bbb2e0473704f2fbf0e3a72",
    ),
    "h100_m8": (
        PROJECT.parent
        / "h100_direct_fp8_linear_falsifier/artifacts/RECONCILED_TERMINAL.json",
        "26cace1bfa370e3b578935e44c16beeb7ec396d707d8b08e3253bd19ba4f6756",
    ),
    "h200_linears": (
        PROJECT.parent / "h200_bf16_exact_linear_floor/artifacts/RECONCILED_TERMINAL.json",
        "9f12b3ae4c8d82176f0ec9b09845c6e97ab1f278a458bd023adcbe433fd004fe",
    ),
    "h200_kv": (
        PROJECT.parent / "h200_bf16_kv_attention_bandwidth_floor/KV_ATTENTION_FLOOR.json",
        "8d0d1ef6bc39adef386a072947bc0ae820e3193af4d6e8b28c19bc6f59fcb442",
    ),
    "h200_prefill": (
        PROJECT.parent / "h200_c32_prefill_peak_compute_floor/PREFILL_COMPUTE_FLOOR.json",
        "342b650c2bf61615928a5525daa773023d643af6741202f98c3384503905b68a",
    ),
    "h100_attention": (
        PROJECT.parent / "h100_hybrid_attention_kernel_mechanism/MECHANISM.json",
        "3960c453e88b1a12e01351d2062dbaa7f8a800e63fe6674e997ddbbcfeebdda1",
    ),
    "tied_head_none": (
        PROJECT.parent / "tied_head_joint_onebyte_consumer_route/NONE.json",
        "152539e14f632e77efc6d0d1fcd51ce0b59ab5a508973eddff03c8b6b07b8d2e",
    ),
}

SHAPES = [
    ("sliding_qkv", 5376, 16384, 50),
    ("global_qkv", 5376, 20480, 10),
    ("sliding_output", 8192, 5376, 50),
    ("global_output", 16384, 5376, 10),
    ("merged_gate_up", 5376, 43008, 60),
    ("down", 21504, 5376, 60),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tile(m: int) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    if m <= 16:
        return (128, 128, 256), (1, 1, 1)
    if m <= 256:
        return (256, 128, 256), (2, 1, 1)
    return (256, 256, 256), (2, 1, 1)


def exact_rows() -> list[dict[str, object]]:
    rows = []
    l2 = Decimal(126_000_000)
    for name, k, n, multiplicity in SHAPES:
        parameters = k * n
        nvfp4_bytes = Decimal(parameters) * Decimal(9) / Decimal(16)
        for m in (8, 16, 32, 3679):
            tile_shape, cluster = tile(m)
            clusters = math.ceil(m / tile_shape[0]) * math.ceil(n / tile_shape[1])
            total_bytes = (
                nvfp4_bytes
                + Decimal(m * k) * Decimal(9) / Decimal(16)
                + Decimal(2 * m * n)
            )
            flops = Decimal(2 * m * parameters)
            rows.append(
                {
                    "case": name,
                    "m": m,
                    "k": k,
                    "n": n,
                    "multiplicity": multiplicity,
                    "padding": {"k_elements": 0, "n_elements": 0},
                    "source_selected_tile_mnk": list(tile_shape),
                    "source_selected_cluster_mnk": list(cluster),
                    "logical_clusters": clusters,
                    "logical_sm_slots": clusters * cluster[0],
                    "nvfp4_weight_and_scale_bytes": int(nvfp4_bytes),
                    "weight_exceeds_reported_126mb_l2": nvfp4_bytes > l2,
                    "analytical_flop_per_payload_byte": float(flops / total_bytes),
                }
            )
    return rows


def main() -> int:
    observed_inputs = {}
    for name, (path, expected) in INPUTS.items():
        observed = sha256(path)
        if observed != expected:
            raise RuntimeError(f"input hash mismatch for {name}: {observed}")
        observed_inputs[name] = {"path": str(path), "sha256": observed}

    inventory = json.loads(INPUTS["accelerator_inventory"][0].read_text())
    prices = json.loads(INPUTS["gpu_prices"][0].read_text())
    h100 = next(row for row in inventory["accelerators"] if row["id"] == "nvidia-h100-sxm")
    b200 = next(row for row in inventory["accelerators"] if row["id"] == "nvidia-b200-sxm")
    h100_price_row = next(row for row in prices["accelerators"] if row["id"] == "nvidia-h100-sxm")
    b200_price_row = next(row for row in prices["accelerators"] if row["id"] == "nvidia-b200-sxm")
    h100_price = Decimal(str(h100_price_row["production_planning_usd_per_gpu_hour"]))
    b200_price = Decimal(str(b200_price_row["production_planning_usd_per_gpu_hour"]))
    premium = b200_price / h100_price
    h100_service_ceiling = Decimal("0.5479752315195353")
    b200_service_ceiling = h100_service_ceiling / premium
    total_parameters = sum(Decimal(k * n * multiplicity) for _, k, n, multiplicity in SHAPES)
    nvfp4_architecture_weight_bytes = total_parameters * Decimal(9) / Decimal(16)
    fresh_prompt_tokens = Decimal(4214) * (Decimal(1) - Decimal("0.127"))
    linear_flops_per_fresh_token = total_parameters * Decimal(2)
    prefill_flops = linear_flops_per_fresh_token * fresh_prompt_tokens
    b200_fp4_peak = Decimal(str(b200["peak_math"]["fp4_tflops"])) * Decimal(10) ** 12
    b200_bandwidth = Decimal(str(b200["memory"]["bandwidth_gb_s"])) * Decimal(10) ** 9
    h100_fp8_peak = Decimal(str(h100["peak_math"]["fp8_tflops"])) * Decimal(10) ** 12
    h100_bandwidth = Decimal(str(h100["memory"]["bandwidth_gb_s"])) * Decimal(10) ** 9
    decode_floors = {}
    for concurrency in (8, 16, 32):
        decode_floors[str(concurrency)] = float(
            nvfp4_architecture_weight_bytes * Decimal(358) / Decimal(concurrency) / b200_bandwidth
        )
    rows = exact_rows()
    artifact = {
        "schema_version": 1,
        "terminal": "content_bound_direct_b200_nvfp4_linear_falsifier",
        "decision": "nominate_one_b200_nvfp4_linear_component_falsifier",
        "evidence_boundary": "Source-backed and analytically measured at $0. No B200, CUDA, checkpoint, provider, compilation, achieved timing, endpoint, or quality claim.",
        "identities": {
            "model": "google/gemma-4-31B-it",
            "model_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "workload": {"prompt_tokens": 4214, "fresh_prompt_tokens": float(fresh_prompt_tokens), "output_tokens": 358, "decode_concurrency": [8, 16, 32]},
            "runtime_image": "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79",
            "runtime_vllm": "0.19.1.dev6+g6d4a8e6d2",
            "runtime_vllm_commit": "6d4a8e6d204a9b2827544003b26321fff62923da",
            "accelerator": "NVIDIA B200 SXM, compute capability 10.0",
        },
        "source_trace": {
            "official_repository": "https://github.com/vllm-project/vllm/tree/6d4a8e6d204a9b2827544003b26321fff62923da",
            "files": [
                {"path": "vllm/model_executor/layers/quantization/compressed_tensors/schemes/compressed_tensors_w4a4_nvfp4.py", "sha256": "02d183b951b410801c51e76720603248102e9643711022db9a5415c932e0ec8a", "role": "group-16 NVFP4 weights and apply_nvfp4_linear consumer"},
                {"path": "vllm/model_executor/layers/quantization/utils/nvfp4_utils.py", "sha256": "ab81bb72b86b8deec2892f89660cb5465039a325c03411a68bac4329cb53d196", "role": "SM100 CUTLASS backend selection, activation quantization, padded layout, actual apply"},
                {"path": "vllm/_custom_ops.py", "sha256": "8990c0c4de5dadbb2d1ff57f02d6a7f9133df29bb9070179ada3363461b40093", "role": "scaled_fp4_quant and cutlass_scaled_fp4_mm Python calls"},
                {"path": "csrc/quantization/fp4/nvfp4_scaled_mm_entry.cu", "sha256": "ceb6b8f3fedbcb17cbcf074cb88d6e3b4c16f6f736976f82bce7377d803cc17e", "role": "requires CUDA >=12.8 and CC >=100, dispatches SM100"},
                {"path": "csrc/quantization/fp4/nvfp4_scaled_mm_kernels.cu", "sha256": "079ef2689cc17caf2d3ecb28d67013e3a484dcf66cf17220c1676696d4f6744c", "role": "OpClassBlockScaledTensorOp and exact M-dependent tile/cluster selection"},
                {"path": "vllm/model_executor/layers/quantization/utils/nvfp4_emulation_utils.py", "sha256": "ac5a5858d980d430f8239dfa6f45341608c1e330550d2a4de9ca5e95d8ecb2fc", "role": "independent pinned dequantized-quantized oracle"},
                {"path": "benchmarks/kernels/benchmark_nvfp4_gemm.py", "sha256": "667f935dceac3acba4bfd808b8c02ac7bcf5d525f2c044ee78cd291da5b1b80d", "role": "official checkpoint-free BF16 versus on-the-fly NVFP4 program path"},
            ],
            "actual_call_chain": ["scaled_fp4_quant(BF16 activation, calibrated global scale)", "cutlass_scaled_fp4_mm", "torch.ops._C.cutlass_scaled_fp4_mm", "SM100 CUTLASS OpClassBlockScaledTensorOp"],
            "format": "E2M1 FP4 values packed two per byte plus one FP8 E4M3 scale per 16 values and FP32 global scales",
            "alignment": "K and N must be divisible by 32; all six exact Gemma shapes are divisible by 256, so no K/N padding is required.",
        },
        "exact_geometry_and_tiles": {
            "shapes": [{"name": name, "k": k, "n": n, "multiplicity": multiplicity} for name, k, n, multiplicity in SHAPES],
            "rows": rows,
            "decode_interpretation": "M8/M16 select 128x128x256 one-SM tiles; several N=5376 shapes expose only 42 CTAs and can underfill an unknown B200 SM count. M32 selects 256x128x256 two-SM clusters. Grid size, not aligned K/N, is the decode risk.",
            "prefill_interpretation": "M3679 selects 256x256x256 two-SM clusters and 630-5040 logical SM slots across the six shapes; it has ample parallel work and is the TCGen05/compute discriminator.",
            "resource_unknowns": "The shared inventory intentionally leaves B200 SM count null, while CUTLASS uses auto schedules and stage-count carveout. The direct sentinel must record cudaDeviceProp.multiProcessorCount, compiled registers/shared memory, cudaOccupancyMaxActiveClusters, achieved active warps, cluster occupancy, and waves. No occupancy percentage is inferred from source alone.",
            "cache": "Five NVFP4 matrices fit the reported 126 MB L2 individually; merged_gate_up is 130,056,192 bytes and does not. Cold/rotating-buffer timing is mandatory; warm isolated timing cannot drive economics.",
        },
        "causal_hypothesis": {
            "change": "Use the pinned SM100 native NVFP4 W4A4 linear path for the six dense transformer projections, retaining exact model widths and layer multiplicities.",
            "physical_resource": "Decode weight HBM bytes and prefill block-scaled Tensor Core time.",
            "decode": "NVFP4 reduces logical weight+block-scale payload to 0.5625 byte/parameter. Combined with B200/H100 bandwidth ratio, its ideal weight-stream ratio versus H100 one-byte FP8 is about 4.25x, but M<=32 grid/cluster underfill and activation quantization can erase it.",
            "prefill": "The prompt-heavy M3679 row has sufficient grid size; B200 FP4 versus H100 FP8 vendor-peak ratio is about 4.55x, making TCGen05 utilization rather than HBM the discriminator.",
            "head": "The exact tied 262144x5376 embedding/head still has no pinned joint quantized consumer and must remain a separately measured BF16 residual. B200 BF16 compute/bandwidth priors exceed H100 by only 2.27x/2.39x, just 1.24x/1.30x after price normalization.",
            "attention": "Both chips already have FP8 paged-KV source paths. B200's 2.39x bandwidth prior leaves only 1.30x price-normalized headroom, and head_dim 512 backend selection remains runtime-dependent; attention is not the first unique B200 test.",
        },
        "economic_screen": {
            "planning_rate_usd_per_gpu_hour": {"b200": float(b200_price), "h100": float(h100_price)},
            "price_premium_b200_over_h100": float(premium),
            "required_b200_throughput_ratio": float(premium),
            "h100_planning_service_ceiling_seconds_per_request": float(h100_service_ceiling),
            "b200_equivalent_service_ceiling_seconds_per_request": float(b200_service_ceiling),
            "b200_required_requests_per_second": float(Decimal(1) / b200_service_ceiling),
            "vendor_prior_ratios": {
                "b200_over_h100_hbm_bandwidth": float(b200_bandwidth / h100_bandwidth),
                "b200_over_h100_bf16_peak": float(Decimal(str(b200["peak_math"]["bf16_tflops"])) / Decimal(str(h100["peak_math"]["bf16_tflops"]))),
                "b200_fp4_over_h100_fp8_peak": float(b200_fp4_peak / h100_fp8_peak),
                "nvfp4_b200_over_fp8_h100_ideal_decode_weight_stream": float((b200_bandwidth / h100_bandwidth) / Decimal("0.5625")),
            },
            "impossible_ideal_b200_nvfp4_linear_floors_seconds_per_request": {
                "prefill_at_fresh_mix": float(prefill_flops / b200_fp4_peak),
                "decode_weight_only_by_concurrency": decode_floors,
                "prefill_plus_decode": {key: float(prefill_flops / b200_fp4_peak + Decimal(str(value))) for key, value in decode_floors.items()},
            },
            "interpretation": "The impossible ideal floors leave material room below 0.2979 s/request, so price physics does not justify typed none. They are admission priors only, not achieved throughput.",
        },
        "prior_measured_boundary": {
            "h100_m8_descriptive": {"case": "sliding_qkv", "m": 8, "fp8_cuda_event_p50_ms": 0.04806400090456009, "bf16_cuda_event_p50_ms": 0.07209599763154984, "price_normalized_b200_nvfp4_descriptive_hurdle_ms": float(Decimal("0.04806400090456009") / premium), "claim": "one valid descriptive row only; no H100 sweep or economic aggregate transfers"},
            "h200": "Measured BF16 linears+head close c1/c4/c8 and preserve only c32; the exact prefill peak floor plus QK/AV sensitivity leaves 0.01683-0.02233 s/request for decode attention and all other omissions at c32.",
            "attention": "Corrected exact H100 BF16 KV reads are 429,132,595,200 bytes/request; FP8 can save half, but this mechanism is shared with B200 rather than Blackwell-unique.",
        },
        "direct_falsifier": {
            "type": "checkpoint_free_exact_shape_b200_native_nvfp4_linear_component",
            "program": {"repository": "https://github.com/vllm-project/vllm", "commit": "6d4a8e6d204a9b2827544003b26321fff62923da", "path": "benchmarks/kernels/benchmark_nvfp4_gemm.py", "required_callable": "build_nvfp4_runner with VLLM_NVFP4_GEMM_BACKEND=cutlass", "required_evaluator": "the row, oracle, cold-cache, counter, and economic contract in this artifact; the stock upstream plot alone is insufficient"},
            "provider_requirement": "One full NVIDIA B200 SXM (SM100) in an immutable image that reports the pinned vLLM/source hashes. Use a shared durable controller; no provider create is authorized by this $0 project. Record the actual metered B200 rate separately from the $5.15 planning rate.",
            "primary": "Atomically retrieve sliding_qkv M8 before the sweep. Require SM100, CUDA>=12.8, cutlass_scaled_mm_supports_fp4(100), exact source hashes, actual scaled_fp4_quant plus cutlass_scaled_fp4_mm calls, nonempty output, both oracles, positive stable warm/cold timing, allocator, and compiled resource fields.",
            "rows": "After primary pass, run exactly 24 unique rows: six exact K/N shapes at M8/M16/M32/M3679. Materialize each BF16 weight once; prequantize its NVFP4 weight outside timing; time on-the-fly activation quantization plus actual NVFP4 GEMM and matched BF16 linear. Randomize paired order, 20 warmups and at least 50 repetitions, CUDA events plus synchronized wall.",
            "comparators": ["same-B200 torch BF16 linear from the same original BF16 X/W", "dequantized-quantized NVFP4 reference from pinned dequantize_to_dtype", "prior H100 sliding_qkv M8 is descriptive only and cannot replace same-B200 BF16"],
            "oracles": {"kernel": "timed NVFP4 versus dequantized NVFP4 reference: finite/nontrivial, cosine>=0.999, normalized RMSE<=0.03", "representation": "dequantized NVFP4 versus original BF16 timed output: finite/nontrivial, cosine>=0.98, normalized RMSE<=0.20", "consumption": "every timed output contributes to the oracle; an all-zero fixture is rejected"},
            "cache_and_timing": "Report warm and >2x126MB rotating-buffer cold p50/p95. Economic aggregation uses cold CUDA interval time only. Setup, weight quantization, allocation, eviction, and profiler overhead remain outside the timed interval; activation quantization remains inside because the pinned consumer does it online.",
            "profile_rows": ["merged_gate_up M8", "merged_gate_up M3679"],
            "required_counters": ["dram__bytes_read.sum", "lts__t_bytes.sum", "sm__warps_active.avg.pct_of_peak_sustained_active", "SM100 tensor-pipe activity", "kernel launch count and interval-union time", "LaunchStats/Occupancy registers, static+dynamic shared memory, active clusters, blocks, warps, waves"],
            "economic_aggregation": f"For c in {{8,16,32}}, sum cold NVFP4 p50 over six shapes times multiplicity times 358/c, then add the M3679 cold p50 times multiplicity exactly once. Do not divide prefill by concurrency. Compare the linear-only result with {float(b200_service_ceiling):.15f} s/request; head, attention, norms, sampling, scheduler, service, and reliability are omitted and can only add time.",
            "stop_rules": ["Identity, compiled SM100 support, actual call, oracle, timing, or required-row failure is a typed unsupported/kernel/representation negative and stops without an economic aggregate.", "If every valid c8/c16/c32 NVFP4 linear floor exceeds the B200 service ceiling, falsify B200 native-NVFP4 economics directly.", "If any floor is below the ceiling, report component plausibility only; do not claim endpoint economics or quality. The next gate would require an exact-revision NVFP4 producer/quality path plus actual BF16 tied head and paged attention in a complete-request endpoint.", "If DRAM bytes do not fall near the 0.5625-byte/parameter mechanism on the cold M8 profile, or TCGen05 activity is low at M3679, reject the stated mechanism even if elapsed time happens to improve."],
        },
        "rejected_alternatives": [
            {"route": "Blackwell Marlin W4", "reason": "Pinned source chooses native NVFP4 CUTLASS on SM100; Marlin is the non-native fallback and does not exercise TCGen05 block-scaled FP4."},
            {"route": "quantized tied head", "reason": "No pinned joint embedding/output low-precision consumer exists; output-only duplication violates tied storage semantics."},
            {"route": "cross-layer five-local/one-global fusion", "reason": "Source-falsified: attention calls are separated by projection, residual, norm, and MLP dependencies."},
            {"route": "BF16/FP8 peak-only B200 endpoint", "reason": "The 2.27-2.39x priors barely clear the 1.839x premium and cannot establish exact small-M realization; no direct test is justified without the NVFP4-specific margin."},
        ],
        "resources": {"provider_mutations": 0, "gpu_seconds": 0, "spend_usd": 0, "local_analysis": "deterministic integer/Decimal geometry, grid, payload, roofline, and price calculations"},
        "inputs": observed_inputs,
    }
    output = PROJECT / "MECHANISM.json"
    temporary = output.with_suffix(".json.tmp")
    with temporary.open("w") as handle:
        json.dump(artifact, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(output)
    print(json.dumps({"artifact": str(output), "sha256": sha256(output), "rows": len(rows), "decision": artifact["decision"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
