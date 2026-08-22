#!/usr/bin/env python3

import hashlib
import json
import os
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
ENDPOINT = LAB / "projects" / "gemma4_b200_dynamic_fp8_endpoint"
TERMINAL = (
    ENDPOINT
    / "artifacts"
    / "b200-dynamic-fp8-repair2-20260728t1517z"
    / "final-retrieval"
    / "handoff"
    / "DYNAMIC_FP8_TERMINAL.json"
)
CONFIG = ENDPOINT / "inputs" / "bf16-source" / "config.json"
INVENTORY = PROJECT.parents[5] / "factory" / "data" / "accelerator_inventory.json"
SOURCE = PROJECT / "evidence" / "pinned_runtime"
PATCH = PROJECT / "M32_DISPATCH.patch"
OUTPUT = PROJECT / "B200_FP8_RESIDUAL_DISCRIMINATOR.json"

IMAGE = (
    "docker.io/vllm/vllm-openai:gemma4@"
    "sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
)
VLLM_COMMIT = "6d4a8e6d204a9b2827544003b26321fff62923da"
TARGET_SERVICE_SECONDS = 0.500119281574996
EXPECTED_TERMINAL_SHA256 = (
    "4930d9666167e20096f0343736db6d0ed721ea30fad68f5fc4010ccfeeee9acf"
)
EXPECTED_SOURCE_HASHES = {
    "ScaledMMLinearKernel.py": "8618ebb23f1b7e14a4ad2534a4c19c32adf52b30b925b8453a18085a174d4471",
    "cutlass.py": "e212907776b61fd6618e6b812cee9a471ca83140a4710ca447bc6c11cc1d8488",
    "fp8.py": "f2612966aaefa1dd4596a50da361628f64cd590eb3e6bbf6e1b4cfa488334d7e",
    "gemma4.py": "e16b28577c7cdca4876d26636564ed411fc7ce4a25b724456ee906d8129eed20",
    "scaled_mm_sm100_fp8_dispatch.cuh": (
        "492ab8232db9f04605e5cd50417ee00902b4476181540f3c223f470d1ced14cf"
    ),
    "vocab_parallel_embedding.py": (
        "9dff6cab7c17798991cc48e854f275a6b596cc637e5694f166c20cdc68d31879"
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    with path.open() as stream:
        return json.load(stream)


def require_source_contract() -> tuple[str, str]:
    observed = {path.name: sha256(path) for path in sorted(SOURCE.iterdir())}
    if observed != EXPECTED_SOURCE_HASHES:
        raise RuntimeError(
            f"pinned_source_hash_mismatch:{observed}:{EXPECTED_SOURCE_HASHES}"
        )

    gemma = (SOURCE / "gemma4.py").read_text()
    fp8 = (SOURCE / "fp8.py").read_text()
    scaled_mm = (SOURCE / "ScaledMMLinearKernel.py").read_text()
    cutlass = (SOURCE / "cutlass.py").read_text()
    dispatcher_path = SOURCE / "scaled_mm_sm100_fp8_dispatch.cuh"
    dispatcher = dispatcher_path.read_text()

    required = {
        "gemma4.py": [
            "self.act_fn = GeluAndMul(approximate=\"tanh\")",
            "qkv, _ = self.qkv_proj(hidden_states)",
            "attn_output = self.attn(q, k, v)",
            "x, _ = self.down_proj(x)",
        ],
        "fp8.py": [
            "activation_quant_key = kFp8DynamicTokenSym",
            "return self.fp8_linear.apply_weights(layer, x, bias)",
        ],
        "ScaledMMLinearKernel.py": [
            "x_2d_q, x_s = self.quant_fp8(",
            "return self.apply_scaled_mm(",
        ],
        "cutlass.py": ["output = ops.cutlass_scaled_mm("],
        "scaled_mm_sm100_fp8_dispatch.cuh": [
            "using TileShape = Shape<_128, _64, _256>;",
            "using TileShape = Shape<_128, _32, _128>;",
            "if (m <= 16) {",
        ],
    }
    sources = {
        "gemma4.py": gemma,
        "fp8.py": fp8,
        "ScaledMMLinearKernel.py": scaled_mm,
        "cutlass.py": cutlass,
        "scaled_mm_sm100_fp8_dispatch.cuh": dispatcher,
    }
    for name, tokens in required.items():
        missing = [token for token in tokens if token not in sources[name]]
        if missing:
            raise RuntimeError(f"source_contract_missing:{name}:{missing}")

    before = """  if (m <= 16) {
    // m in [1, 16]
"""
    after = """  if (m <= 32) {
    // The 128x32x128 swapped-AB tile exactly covers c32 decode without the
    // 50% M-tail of the 128x64x256 path.
"""
    if dispatcher.count(before) != 1:
        raise RuntimeError("patch_target_not_unique")
    patched = dispatcher.replace(before, after)
    return sha256(dispatcher_path), hashlib.sha256(patched.encode()).hexdigest()


def layer_shapes(config: dict) -> list[dict]:
    text = config["text_config"]
    hidden = text["hidden_size"]
    intermediate = text["intermediate_size"]
    q_heads = text["num_attention_heads"]
    local_dim = text["head_dim"]
    local_kv_heads = text["num_key_value_heads"]
    global_dim = text["global_head_dim"]
    global_kv_heads = text["num_global_key_value_heads"]
    layers = text["layer_types"]
    local_layers = layers.count("sliding_attention")
    global_layers = layers.count("full_attention")
    return [
        {
            "name": "sliding_qkv",
            "m": 32,
            "k": hidden,
            "n": q_heads * local_dim + 2 * local_kv_heads * local_dim,
            "multiplicity_per_decode_step": local_layers,
        },
        {
            "name": "sliding_o",
            "m": 32,
            "k": q_heads * local_dim,
            "n": hidden,
            "multiplicity_per_decode_step": local_layers,
        },
        {
            "name": "global_qkv_k_eq_v_materialized",
            "m": 32,
            "k": hidden,
            "n": q_heads * global_dim + 2 * global_kv_heads * global_dim,
            "multiplicity_per_decode_step": global_layers,
        },
        {
            "name": "global_o",
            "m": 32,
            "k": q_heads * global_dim,
            "n": hidden,
            "multiplicity_per_decode_step": global_layers,
        },
        {
            "name": "gate_up",
            "m": 32,
            "k": hidden,
            "n": 2 * intermediate,
            "multiplicity_per_decode_step": len(layers),
        },
        {
            "name": "down",
            "m": 32,
            "k": intermediate,
            "n": hidden,
            "multiplicity_per_decode_step": len(layers),
        },
    ]


def analytical_accounting(config: dict, endpoint: dict, shapes: list[dict]) -> dict:
    text = config["text_config"]
    concurrency = endpoint["complete_requests"]
    rows = endpoint["rows"]
    if len(rows) != concurrency or any(row["error"] is not None for row in rows):
        raise RuntimeError("candidate_rows_incomplete")
    if len({row["prompt_tokens"] for row in rows}) != 1:
        raise RuntimeError("candidate_prompt_geometry_not_uniform")
    if len({row["completion_tokens"] for row in rows}) != 1:
        raise RuntimeError("candidate_decode_geometry_not_uniform")
    prompt_tokens_per_request = endpoint["rows"][0]["prompt_tokens"]
    decode_tokens_per_request = endpoint["rows"][0]["completion_tokens"]
    prompt_tokens = concurrency * prompt_tokens_per_request
    decode_tokens = concurrency * decode_tokens_per_request
    decode_steps = decode_tokens_per_request
    layers = text["num_hidden_layers"]
    local_layers = text["layer_types"].count("sliding_attention")
    global_layers = text["layer_types"].count("full_attention")
    q_heads = text["num_attention_heads"]
    local_dim = text["head_dim"]
    global_dim = text["global_head_dim"]
    local_kv_heads = text["num_key_value_heads"]
    global_kv_heads = text["num_global_key_value_heads"]
    window = text["sliding_window"]
    hidden = text["hidden_size"]
    intermediate = text["intermediate_size"]
    vocab = text["vocab_size"]

    params = sum(
        shape["k"] * shape["n"] * shape["multiplicity_per_decode_step"]
        for shape in shapes
    )
    fp8_peak_flops_s = 4_500e12
    bf16_peak_flops_s = 2_250e12
    hbm_bytes_s = 8_000e9

    prefill_linear_flops = 2 * params * prompt_tokens
    prefill_linear_weight_bytes = params
    decode_linear_flops = 2 * params * decode_tokens
    decode_linear_weight_bytes = params * decode_steps

    local_prefill_pairs = (
        window * (window + 1) // 2
        + (prompt_tokens_per_request - window) * window
    )
    global_prefill_pairs = (
        prompt_tokens_per_request * (prompt_tokens_per_request + 1) // 2
    )
    local_decode_pairs_per_request = decode_steps * window
    global_decode_pairs_per_request = sum(
        prompt_tokens_per_request + step for step in range(decode_steps)
    )

    prefill_attention_flops = concurrency * (
        local_layers * 4 * q_heads * local_dim * local_prefill_pairs
        + global_layers * 4 * q_heads * global_dim * global_prefill_pairs
    )
    decode_attention_flops = concurrency * (
        local_layers * 4 * q_heads * local_dim * local_decode_pairs_per_request
        + global_layers * 4 * q_heads * global_dim * global_decode_pairs_per_request
    )
    prefill_kv_bytes = concurrency * (
        local_layers
        * 2
        * local_kv_heads
        * local_dim
        * 2
        * prompt_tokens_per_request
        + global_layers
        * 2
        * global_kv_heads
        * global_dim
        * 2
        * prompt_tokens_per_request
    )
    decode_kv_read_bytes = concurrency * (
        local_layers
        * 2
        * local_kv_heads
        * local_dim
        * 2
        * local_decode_pairs_per_request
        + global_layers
        * 2
        * global_kv_heads
        * global_dim
        * 2
        * global_decode_pairs_per_request
    )
    decode_kv_write_bytes = concurrency * decode_steps * (
        local_layers * 2 * local_kv_heads * local_dim * 2
        + global_layers * 2 * global_kv_heads * global_dim * 2
    )

    head_params = vocab * hidden
    head_flops = 2 * head_params * decode_tokens
    head_weight_bytes = 2 * head_params * decode_steps

    nonlinear_logical_bytes_per_token_layer = 32 * hidden + 6 * intermediate
    prefill_nonlinear_bytes = (
        nonlinear_logical_bytes_per_token_layer * prompt_tokens * layers
    )
    decode_nonlinear_bytes = (
        nonlinear_logical_bytes_per_token_layer * decode_tokens * layers
    )

    def roofline_floor(flops: int, bytes_: int, peak_flops_s: float) -> float:
        return max(flops / peak_flops_s, bytes_ / hbm_bytes_s)

    categories = [
        {
            "name": "prefill_fp8_transformer_linears",
            "phase": "prefill",
            "time_seconds": None,
            "useful_flops": prefill_linear_flops,
            "compulsory_weight_bytes_lower_bound": prefill_linear_weight_bytes,
            "ideal_roofline_seconds_lower_bound": roofline_floor(
                prefill_linear_flops,
                prefill_linear_weight_bytes,
                fp8_peak_flops_s,
            ),
            "evidence": "derived",
        },
        {
            "name": "prefill_hybrid_attention_and_kv",
            "phase": "prefill",
            "time_seconds": None,
            "useful_attention_flops": prefill_attention_flops,
            "logical_kv_read_write_bytes_lower_bound": prefill_kv_bytes,
            "ideal_roofline_seconds_lower_bound": roofline_floor(
                prefill_attention_flops, prefill_kv_bytes, bf16_peak_flops_s
            ),
            "evidence": "derived",
        },
        {
            "name": "prefill_norm_activation_residual",
            "phase": "prefill",
            "time_seconds": None,
            "logical_tensor_bytes": prefill_nonlinear_bytes,
            "compulsory_hbm_bytes_lower_bound": 0,
            "ideal_roofline_seconds_lower_bound": 0.0,
            "evidence": "derived_logical_bytes_actual_hbm_unknown_due_compilation",
        },
        {
            "name": "decode_fp8_transformer_linears",
            "phase": "decode",
            "time_seconds": None,
            "useful_flops": decode_linear_flops,
            "compulsory_weight_bytes_lower_bound": decode_linear_weight_bytes,
            "gemm_calls": decode_steps
            * sum(shape["multiplicity_per_decode_step"] for shape in shapes),
            "activation_quant_calls": decode_steps
            * sum(shape["multiplicity_per_decode_step"] for shape in shapes),
            "ideal_roofline_seconds_lower_bound": roofline_floor(
                decode_linear_flops, decode_linear_weight_bytes, fp8_peak_flops_s
            ),
            "evidence": "derived",
            "intervention_target": True,
        },
        {
            "name": "decode_hybrid_attention_and_kv",
            "phase": "decode",
            "time_seconds": None,
            "useful_attention_flops": decode_attention_flops,
            "logical_kv_read_bytes_lower_bound": decode_kv_read_bytes,
            "logical_kv_write_bytes": decode_kv_write_bytes,
            "ideal_roofline_seconds_lower_bound": roofline_floor(
                decode_attention_flops,
                decode_kv_read_bytes + decode_kv_write_bytes,
                bf16_peak_flops_s,
            ),
            "evidence": "derived_assuming_bf16_kv_from_auto_dtype",
        },
        {
            "name": "decode_norm_activation_residual",
            "phase": "decode",
            "time_seconds": None,
            "logical_tensor_bytes": decode_nonlinear_bytes,
            "compulsory_hbm_bytes_lower_bound": 0,
            "ideal_roofline_seconds_lower_bound": 0.0,
            "evidence": "derived_logical_bytes_actual_hbm_unknown_due_compilation",
        },
        {
            "name": "decode_bf16_tied_lm_head_and_sampling",
            "phase": "decode",
            "time_seconds": None,
            "useful_head_flops": head_flops,
            "compulsory_head_weight_bytes_lower_bound": head_weight_bytes,
            "ideal_roofline_seconds_lower_bound": roofline_floor(
                head_flops, head_weight_bytes, bf16_peak_flops_s
            ),
            "evidence": (
                "source_backed_fp8_config_does_not_match_ParallelLMHead_and_"
                "Gemma4_ties_BF16_embedding_weight"
            ),
        },
        {
            "name": "kernel_launch_cuda_graph_scheduler_and_cpu_gaps",
            "phase": "cross_phase",
            "time_seconds": None,
            "bytes": 0,
            "ideal_roofline_seconds_lower_bound": 0.0,
            "evidence": "unmeasured_remainder",
        },
    ]
    ideal_sum = sum(
        category["ideal_roofline_seconds_lower_bound"] for category in categories
    )
    measured_batch = endpoint["batch_seconds"]
    return {
        "identity": (
            "T_batch=sum(category_time); categories are mutually exclusive "
            "critical-path intervals, not summed overlapping kernel durations"
        ),
        "measured_batch_seconds": measured_batch,
        "measured_service_seconds_per_request": endpoint[
            "service_seconds_per_request"
        ],
        "token_geometry": {
            "concurrency": concurrency,
            "prompt_tokens_per_request": prompt_tokens_per_request,
            "completion_tokens_per_request": decode_tokens_per_request,
            "aggregate_prefill_tokens": prompt_tokens,
            "aggregate_decode_tokens": decode_tokens,
            "decode_steps_at_m32": decode_steps,
        },
        "vendor_peak_priors": {
            "fp8_flops_per_second": fp8_peak_flops_s,
            "bf16_flops_per_second": bf16_peak_flops_s,
            "hbm_bytes_per_second": hbm_bytes_s,
            "transferability": "lower_bound_priors_not_workload_measurements",
        },
        "categories": categories,
        "sum_ideal_roofline_lower_bounds_seconds": ideal_sum,
        "unattributed_efficiency_and_gap_slack_seconds": measured_batch - ideal_sum,
        "uncertainty": {
            "time_partition": (
                "No TTFT/ITL trace or profiler was retained, so individual "
                "category times are intentionally null."
            ),
            "kv_dtype": (
                "Launcher omitted --kv-cache-dtype and used --dtype bfloat16; "
                "BF16 KV is inferred from the auto default, not dynamically observed."
            ),
            "logical_bytes": (
                "Attention and nonlinear logical bytes are not asserted as HBM "
                "transactions because cache reuse and torch.compile fusion are unmeasured."
            ),
        },
    }


def main() -> None:
    endpoint = read_json(TERMINAL)
    config = read_json(CONFIG)
    inventory = read_json(INVENTORY)
    pre_patch_hash, post_patch_hash = require_source_contract()

    observed_terminal_hash = sha256(TERMINAL)
    if observed_terminal_hash != EXPECTED_TERMINAL_SHA256:
        raise RuntimeError(
            "absolute_fp8_terminal_hash_mismatch:"
            f"{EXPECTED_TERMINAL_SHA256}:{observed_terminal_hash}"
        )

    b200 = next(
        accelerator
        for accelerator in inventory["accelerators"]
        if accelerator["id"] == "nvidia-b200-sxm"
    )
    b200_architecture = inventory["architecture_profiles"][
        b200["architecture_profile_id"]
    ]
    shapes = layer_shapes(config)
    accounting = analytical_accounting(config, endpoint, shapes)
    measured_batch = endpoint["batch_seconds"]
    target_service = TARGET_SERVICE_SECONDS
    target_batch = target_service * endpoint["complete_requests"]
    required_batch_saving = measured_batch - target_batch
    maximum_tile_efficiency_gain = 0.5
    required_stock_decode_gemm_time = (
        required_batch_saving / maximum_tile_efficiency_gain
    )

    result = {
        "schema_version": 1,
        "classification": "offline_hash_bound_m32_dispatch_candidate_unmeasured",
        "decision": (
            "retain one exact-shape B200 discriminator after the c64 saturation arm; "
            "do not claim endpoint improvement from this offline result"
        ),
        "scope": {
            "researcher_profile": "deep",
            "gpu_claimed": False,
            "provider_operations": False,
            "endpoint_requests_submitted": False,
            "scientific_sample_consumed": False,
            "actual_spend_usd": 0.0,
        },
        "authoritative_identities": {
            "endpoint_terminal": {
                "path": str(TERMINAL.relative_to(LAB)),
                "sha256": observed_terminal_hash,
                "classification": endpoint["classification"],
                "candidate_batch_seconds": measured_batch,
                "candidate_service_seconds_per_request": endpoint[
                    "service_seconds_per_request"
                ],
                "target_seconds_per_request": target_service,
            },
            "runtime": {
                "image": IMAGE,
                "vllm_version": "0.19.1.dev6+g6d4a8e6d2",
                "vllm_commit": VLLM_COMMIT,
                "installed_source_hashes": EXPECTED_SOURCE_HASHES,
                "source_provenance": {
                    "python": "copied from the immutable local image",
                    "dispatcher": (
                        "https://github.com/vllm-project/vllm/blob/"
                        f"{VLLM_COMMIT}/csrc/quantization/w8a8/cutlass/c3x/"
                        "scaled_mm_sm100_fp8_dispatch.cuh"
                    ),
                },
            },
            "model": {
                "id": "google/gemma-4-31B-it",
                "revision": endpoint["identity"]["checkpoint_revision"],
                "config_sha256": sha256(CONFIG),
                "layers": config["text_config"]["num_hidden_layers"],
                "sliding_layers": config["text_config"]["layer_types"].count(
                    "sliding_attention"
                ),
                "global_layers": config["text_config"]["layer_types"].count(
                    "full_attention"
                ),
            },
            "hardware": {
                "id": "nvidia-b200-sxm",
                "programming_target": b200_architecture["programming_target"],
                "hbm_bandwidth_gb_s_vendor_reported": b200["memory"][
                    "bandwidth_gb_s"
                ],
                "fp8_tflops_vendor_reported": b200["peak_math"]["fp8_tflops"],
                "bf16_tflops_vendor_reported": b200["peak_math"]["bf16_tflops"],
                "inventory_sha256": sha256(INVENTORY),
            },
        },
        "causal_chain": [
            {
                "order": 1,
                "evidence": "measured",
                "claim": (
                    "The bound c32 runtime-FP8 endpoint completed 32 requests in "
                    f"{measured_batch:.12f} seconds."
                ),
            },
            {
                "order": 2,
                "evidence": "source_backed_plus_endpoint_path_proof",
                "claim": (
                    "Fp8OnlineLinearMethod selects dynamic per-token activation "
                    "quantization and CutlassFP8ScaledMMLinearKernel; the endpoint "
                    "proved that selected consumer executed."
                ),
                "symbols": [
                    "Fp8OnlineLinearMethod",
                    "FP8ScaledMMLinearKernel.apply_weights",
                    "QuantFP8",
                    "CutlassFP8ScaledMMLinearKernel.apply_scaled_mm",
                    "vllm._custom_ops.cutlass_scaled_mm",
                    "cutlass_gemm_sm100_fp8_dispatch",
                ],
            },
            {
                "order": 3,
                "evidence": "derived_from_exact_workload_and_model_source",
                "claim": (
                    "All 32 requests returned 358 tokens, so the steady decode "
                    "transformer linears have M=32 for 358 steps. Six unique "
                    "128-aligned Gemma shapes execute 240 FP8 GEMMs per step."
                ),
            },
            {
                "order": 4,
                "evidence": "source_backed",
                "claim": (
                    "The pinned SM100 dispatcher maps 17<=M<=64 and K>=4096 to "
                    "the swapped-AB 128x64x256 tile, while an already-compiled "
                    "128x32x128 swapped-AB kernel is reserved for M<=16."
                ),
            },
            {
                "order": 5,
                "evidence": "analytical_physical_hypothesis",
                "claim": (
                    "At exact M32, routing to the 128x32x128 kernel removes the "
                    "only systematic M-tail across all six shapes without changing "
                    "quantization, weights, layout, output dtype, grid ownership, "
                    "or model semantics."
                ),
            },
        ],
        "production_geometry": {
            "shapes": shapes,
            "all_n_and_k_multiple_of_128": all(
                shape["n"] % 128 == 0 and shape["k"] % 128 == 0
                for shape in shapes
            ),
            "fp8_gemms_per_decode_step": sum(
                shape["multiplicity_per_decode_step"] for shape in shapes
            ),
            "fp8_gemms_over_completion": sum(
                shape["multiplicity_per_decode_step"] for shape in shapes
            )
            * endpoint["rows"][0]["completion_tokens"],
        },
        "non_overlapping_accounting": accounting,
        "implementation": {
            "type": "source_patch_reusing_already_compiled_kernel",
            "path": PATCH.name,
            "sha256": sha256(PATCH),
            "generator_path": Path(__file__).name,
            "generator_sha256": sha256(Path(__file__)),
            "target_source_path": (
                "csrc/quantization/w8a8/cutlass/c3x/"
                "scaled_mm_sm100_fp8_dispatch.cuh"
            ),
            "target_source_pre_sha256": pre_patch_hash,
            "target_source_post_sha256": post_patch_hash,
            "offline_patch_apply_check": "passed",
            "semantic_class": "semantics_preserving_dispatch_only",
            "change": (
                "Route M<=32 to Cutlass3xGemmM16SwapAB instead of reserving "
                "that 128x32x128 kernel for M<=16."
            ),
        },
        "predicted_effect": {
            "counter_movement": {
                "m_tile_rows": {"stock": 64, "candidate": 32},
                "k_tile": {"stock": 256, "candidate": 128},
                "m_tile_useful_fraction_at_m32": {
                    "stock": 0.5,
                    "candidate": 1.0,
                },
                "dram_weight_bytes": "unchanged",
                "activation_quant_kernel": "unchanged",
                "expected_if_hypothesis_true": (
                    "fewer tensor instructions and cycles per useful output; "
                    "similar DRAM bytes; no new spills or workspace"
                ),
                "falsifier": (
                    "No material weighted warm-latency reduction, or latency "
                    "tracks unchanged DRAM traffic despite the removed tile tail."
                ),
            },
            "endpoint_formula": (
                "candidate_service_s = "
                f"({measured_batch:.15f} - gain_fraction * "
                "measured_stock_decode_fp8_gemm_seconds) / 32"
            ),
            "analytical_gain_fraction_interval": [0.0, 0.5],
            "interval_reason": (
                "Zero is the HBM-bound limit; 0.5 is the ideal removal of the "
                "50% M tile tail. Quantization, attention, head, nonlinear, and "
                "scheduler intervals are not changed."
            ),
            "target_batch_seconds": target_batch,
            "required_batch_saving_seconds": required_batch_saving,
            "stock_decode_fp8_gemm_seconds_required_to_close_target_at_ideal_gain": (
                required_stock_decode_gemm_time
            ),
            "required_stock_decode_fp8_gemm_fraction_of_measured_batch": (
                required_stock_decode_gemm_time / measured_batch
            ),
            "claim": (
                "The patch is decision-relevant but has no offline endpoint "
                "speedup claim; exact component time decides whether the ideal "
                "tail benefit survives the unchanged HBM traffic."
            ),
        },
        "smallest_future_gpu_measurement": {
            "venue": (
                "one retained or newly assigned nvidia-b200-sxm bench after the "
                "higher-priority c64 saturation result; no project-owned provider"
            ),
            "producer_consumer": (
                "QuantFP8 dynamic per-token E4M3 -> "
                "CutlassFP8ScaledMMLinearKernel.apply_scaled_mm -> BF16 output "
                "consumed by a BF16 numerical oracle"
            ),
            "arms": [
                "stock pinned source and binary",
                "same pinned source rebuilt with M32_DISPATCH.patch",
            ],
            "shapes": [shape["name"] for shape in shapes],
            "timing": (
                "profiler-off, warm CUDA-event distributions for quant+GEMM and "
                "GEMM-only; weight by production multiplicity"
            ),
            "correctness": (
                "consume every BF16 output; finite, cosine>=0.99999, normalized "
                "RMSE<=0.005, max_abs<=0.01 against stock/dequantized FP32"
            ),
            "path_proof": (
                "persist source/shared-object hashes and the selected M32 kernel "
                "marker before timing"
            ),
            "counters_only_if_timing_discriminates": [
                "tensor instructions or tensor-pipe active cycles",
                "DRAM bytes",
                "kernel cycles",
                "registers and spills",
            ],
            "endpoint_projection": (
                "delta_batch_s = 358 * sum_shape("
                "multiplicity * (stock_p50_s - candidate_p50_s)); "
                "delta_service_s = delta_batch_s / 32"
            ),
            "stop_condition": (
                "Reject this mechanism without endpoint replay if correctness "
                "fails, any high-multiplicity shape regresses >5%, weighted "
                "quant+GEMM p50 improves <10%, or projected service saving is "
                "<0.005 s/request. Otherwise patch the retained runtime and run "
                "one matched c32 endpoint arm; do not replay a valid component sample."
            ),
        },
        "typed_rejections": [
            {
                "mechanism": "gelu_and_mul_plus_dynamic_fp8_quant_fusion",
                "classification": "analytical_whole_request_insufficient_as_primary",
                "reason": (
                    "It can remove BF16 intermediate traffic and one launch per "
                    "MLP, but cannot alter 10.524 TB of decode transformer weight "
                    "streaming, 13.732 TB of logical decode KV traffic, attention, "
                    "or the BF16 tied head. Keep it stackable, not the primary "
                    "residual discriminator."
                ),
            },
            {
                "mechanism": "dynamic_fp8_tied_lm_head",
                "classification": "analytical_whole_request_insufficient_as_primary",
                "reason": (
                    "The source proves the tied head remains BF16, but its 1.009 TB "
                    "decode weight stream is less than one tenth of the 10.524 TB "
                    "transformer-linear stream and cannot alone explain the residual."
                ),
            },
        ],
    }

    temporary = OUTPUT.with_suffix(".json.tmp")
    with temporary.open("w") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    with temporary.open() as stream:
        json.load(stream)
    temporary.replace(OUTPUT)


if __name__ == "__main__":
    main()
