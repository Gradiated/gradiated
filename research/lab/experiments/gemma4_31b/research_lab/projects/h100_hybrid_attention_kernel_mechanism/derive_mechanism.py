#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
REPO = PROJECT.parents[6]

PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358
LOCAL_LAYERS = 50
GLOBAL_LAYERS = 10
LOCAL_WINDOW = 1024
QUERY_HEADS = 32
LOCAL_KV_HEADS = 16
LOCAL_HEAD_DIM = 256
GLOBAL_KV_HEADS = 4
GLOBAL_HEAD_DIM = 512
BF16_BYTES = 2
FP8_BYTES = 1
H100_HBM_BYTES_PER_SECOND = 3.35e12
H100_BF16_FLOPS_PER_SECOND = 989.5e12
H100_L2_BYTES = 50 * 1024**2
PLANNING_RPS = 1.8249
PROMOTION_FRACTION = 0.05


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def kv_bytes_per_token(kv_heads: int, head_dim: int, element_bytes: int) -> int:
    return 2 * kv_heads * head_dim * element_bytes


def main() -> None:
    positions = list(range(PROMPT_TOKENS, PROMPT_TOKENS + OUTPUT_TOKENS))
    local_bf16_per_layer_token = kv_bytes_per_token(
        LOCAL_KV_HEADS, LOCAL_HEAD_DIM, BF16_BYTES
    )
    global_bf16_per_layer_token = kv_bytes_per_token(
        GLOBAL_KV_HEADS, GLOBAL_HEAD_DIM, BF16_BYTES
    )
    local_fp8_per_layer_token = kv_bytes_per_token(
        LOCAL_KV_HEADS, LOCAL_HEAD_DIM, FP8_BYTES
    )
    global_fp8_per_layer_token = kv_bytes_per_token(
        GLOBAL_KV_HEADS, GLOBAL_HEAD_DIM, FP8_BYTES
    )

    local_bf16 = (
        len(positions) * LOCAL_LAYERS * LOCAL_WINDOW * local_bf16_per_layer_token
    )
    global_bf16 = sum(
        GLOBAL_LAYERS * position * global_bf16_per_layer_token
        for position in positions
    )
    local_fp8 = (
        len(positions) * LOCAL_LAYERS * LOCAL_WINDOW * local_fp8_per_layer_token
    )
    global_fp8 = sum(
        GLOBAL_LAYERS * position * global_fp8_per_layer_token
        for position in positions
    )
    bf16_bytes = local_bf16 + global_bf16
    fp8_bytes = local_fp8 + global_fp8
    bytes_saved = bf16_bytes - fp8_bytes

    attention_flops = sum(
        LOCAL_LAYERS * 4 * QUERY_HEADS * LOCAL_HEAD_DIM * LOCAL_WINDOW
        + GLOBAL_LAYERS * 4 * QUERY_HEADS * GLOBAL_HEAD_DIM * position
        for position in positions
    )
    service_seconds = 1 / PLANNING_RPS
    hurdle_seconds = service_seconds * PROMOTION_FRACTION
    full_l2_credit = H100_L2_BYTES * len(positions)
    conservative_saved_hbm_bytes = bytes_saved - full_l2_credit

    frontier = LAB / "projects/gemma4_hardware_kernel_frontier/FRONTIER.json"
    geometry = LAB / "projects/exact_geometry_runtime_opportunities/GEOMETRY.json"
    config = (
        LAB
        / "projects/exact_bf16_mtp_h100_frontier/artifacts/preflight-20260717T000000Z/hf-config.json"
    )
    prior_floor = LAB / "projects/h200_bf16_kv_attention_bandwidth_floor/KV_ATTENTION_FLOOR.json"
    inventory = REPO / "research/factory/data/accelerator_inventory.json"

    selected_points = []
    for concurrency in (8, 16, 32):
        rows = []
        for label, position in (
            ("first", 4214),
            ("median_high", 4393),
            ("last", 4571),
        ):
            bf16_step = concurrency * (
                LOCAL_LAYERS * LOCAL_WINDOW * local_bf16_per_layer_token
                + GLOBAL_LAYERS * position * global_bf16_per_layer_token
            )
            fp8_step = bf16_step // 2
            rows.append(
                {
                    "label": label,
                    "context_tokens": position,
                    "bf16_batch_step_kv_read_bytes": bf16_step,
                    "fp8_batch_step_kv_read_bytes": fp8_step,
                    "byte_reduction_fraction": 0.5,
                    "bf16_working_set_over_l2": bf16_step / H100_L2_BYTES,
                }
            )
        selected_points.append({"concurrency": concurrency, "rows": rows})

    artifact = {
        "schema_version": 1,
        "generated_at_utc": "2026-07-17T15:17:54Z",
        "terminal": "content_bound_exact_shape_fp8_kv_falsifier",
        "decision": "retain_fp8_paged_kv_mechanism_reject_cross_layer_hybrid_fusion",
        "decision_question": (
            "Can one pinned-source H100 paged-attention dataflow change plausibly "
            "save at least 5% whole-request cost and be falsified checkpoint-free?"
        ),
        "identities": {
            "model": "google/gemma-4-31B-it",
            "model_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "vllm_source_revision": "ab0a20d15129b322f911db578b50c6b35b3167e7",
            "workload": {
                "prompt_tokens": PROMPT_TOKENS,
                "output_tokens": OUTPUT_TOKENS,
                "decode_contexts_inclusive": [positions[0], positions[-1]],
            },
            "geometry": {
                "layers": 60,
                "pattern": "five sliding_attention then one full_attention, repeated",
                "local": {
                    "layers": LOCAL_LAYERS,
                    "query_heads": QUERY_HEADS,
                    "kv_heads": LOCAL_KV_HEADS,
                    "head_dim": LOCAL_HEAD_DIM,
                    "window_tokens": LOCAL_WINDOW,
                    "bf16_k_plus_v_bytes_per_cached_token_per_layer": local_bf16_per_layer_token,
                },
                "global": {
                    "layers": GLOBAL_LAYERS,
                    "query_heads": QUERY_HEADS,
                    "kv_heads": GLOBAL_KV_HEADS,
                    "head_dim": GLOBAL_HEAD_DIM,
                    "attention_k_eq_v_weights": True,
                    "bf16_k_plus_v_bytes_per_cached_token_per_layer": global_bf16_per_layer_token,
                },
            },
            "h100_sxm": {
                "sms": 132,
                "l2_bytes": H100_L2_BYTES,
                "hbm_bandwidth_bytes_per_second_vendor_peak": H100_HBM_BYTES_PER_SECOND,
                "bf16_tensor_flops_per_second_vendor_peak": H100_BF16_FLOPS_PER_SECOND,
                "register_file_bytes_per_sm": 256 * 1024,
                "shared_memory_bytes_per_sm": 228 * 1024,
            },
        },
        "pinned_source_trace": {
            "image_boundary": {
                "frontier_source_revision": "ab0a20d15129b322f911db578b50c6b35b3167e7",
                "cached_immutable_image": "vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79",
                "cached_image_observed_vllm": "0.19.1.dev6+g6d4a8e6d2",
                "interpretation": (
                    "The cached image is useful source-level corroboration but is not an "
                    "execution-equivalent binding for the frontier revision; a later GPU "
                    "falsifier must bind one immutable image to the named source revision."
                ),
            },
            "source_files": [
                {
                    "path": "vllm/model_executor/models/gemma4.py",
                    "sha256": "3d63af0ad265d56e09e3244a08102767efb6579a553db2c8213aa8912660b093",
                    "observation": (
                        "Each layer performs QKV projection, Q/K/V normalization and RoPE, "
                        "then its own Attention call before o_proj; local/global layers are "
                        "not adjacent attention calls and cannot be fused across the MLP/residual boundary."
                    ),
                },
                {
                    "path": "vllm/model_executor/layers/attention/attention.py",
                    "sha256": "25d708c4075e87ae7af8e8855dd8f5652ff0fdef2f11ec794ec7a7e12d25c2e7",
                    "observation": (
                        "cache_config.cache_dtype selects BF16/FP8; unified_kv_cache_update "
                        "writes paged K and V before unified_attention_with_output consumes the page table."
                    ),
                },
                {
                    "path": "vllm/platforms/cuda.py",
                    "sha256": "4db2316b8c06f372e41c1b82dd85ea24c431f1ce8b544472eb51a84764c81d1d",
                    "observation": "SM90 backend priority is FlashAttention, FlashInfer, Triton, Flex.",
                },
                {
                    "path": "vllm/v1/attention/backends/flash_attn.py",
                    "sha256": "7b5fac9b635b4dc138f24a07277569ab92e59ffd0a88a1d4c5d326039a880a51",
                    "observation": (
                        "Paged FlashAttention consumes block_table/seqused_k; FA3 on SM90 "
                        "accepts FP8 KV and head_size<=256, while head_size 512 requires FA4."
                    ),
                },
                {
                    "path": "vllm/v1/attention/backends/triton_attn.py",
                    "sha256": "20b4dd5f8c15cd2d6f9598268368f5fc572f2c980eb75327c5992100c49ff3ed",
                    "observation": (
                        "Triton paged attention supports head_size>=32 and FP8 on SM89+; "
                        "global 4x512 therefore has an SM90 fallback when FA4 is absent."
                    ),
                },
                {
                    "path": "vllm/v1/attention/ops/triton_unified_attention.py",
                    "sha256": "992a2bc892e2e2b43fbd3c8163816ccf7e97ced56cb542bd827adb0ddb2df9fa",
                    "observation": (
                        "The kernel follows block_table physical pages, loads K and V, "
                        "dequantizes quantized caches inline, and uses 16-way segmented softmax "
                        "when the decode grid is below its threshold."
                    ),
                },
            ],
            "hierarchy": [
                "Q/K/V are produced per decoder layer and normalized; new K/V are quantized and written to paged HBM cache slots.",
                "The scheduler supplies slot_mapping, block_table, sequence lengths, and query offsets to the layer backend.",
                "Local 16x256 pages are window-pruned to 1024 tokens; global 4x512 pages traverse the full 4214..4571 context.",
                "FlashAttention or Triton gathers physical pages through L2 into SM registers/shared-memory tiles, performs QK/softmax/AV, and writes BF16 attention output.",
                "The 50 MiB L2 is only 1.4% to 17.5% of one selected c8..c32 batch-step KV working set, so the exact paged reads cannot reside there as a whole.",
            ],
        },
        "mechanism": {
            "change": (
                "Use the pinned runtime's actual FP8 E4M3 KV producer and the same paged "
                "FlashAttention/Triton consumers for all 50 local and 10 global layers; "
                "do not change window, page table, heads, dimensions, layer pattern, or scheduling."
            ),
            "physical_resource": "HBM bytes per decoded request",
            "why_h100": (
                "SM90 natively supports FP8, both pinned paged consumers expose an FP8 path, "
                "and exact attention arithmetic intensity is far below H100's BF16 roofline balance."
            ),
            "semantics": "quantized-KV semantics change; checkpoint-free component accuracy is required before any endpoint claim",
        },
        "derived_discriminator": {
            "evidence_type": "exact_geometry_analytical_h100_peak_bound",
            "bf16_kv_read_bytes_per_request": bf16_bytes,
            "bf16_local_kv_read_bytes_per_request": local_bf16,
            "bf16_global_kv_read_bytes_per_request": global_bf16,
            "fp8_kv_read_bytes_per_request": fp8_bytes,
            "kv_bytes_saved_per_request": bytes_saved,
            "byte_reduction_fraction": bytes_saved / bf16_bytes,
            "exact_qk_av_flops_per_request": attention_flops,
            "bf16_arithmetic_intensity_flop_per_byte": attention_flops / bf16_bytes,
            "fp8_arithmetic_intensity_flop_per_byte": attention_flops / fp8_bytes,
            "h100_bf16_roofline_balance_flop_per_byte": (
                H100_BF16_FLOPS_PER_SECOND / H100_HBM_BYTES_PER_SECOND
            ),
            "bf16_peak_compute_floor_seconds_per_request": (
                attention_flops / H100_BF16_FLOPS_PER_SECOND
            ),
            "bf16_peak_hbm_floor_seconds_per_request": bf16_bytes
            / H100_HBM_BYTES_PER_SECOND,
            "fp8_peak_hbm_floor_seconds_per_request": fp8_bytes
            / H100_HBM_BYTES_PER_SECOND,
            "peak_hbm_floor_reduction_seconds_per_request": bytes_saved
            / H100_HBM_BYTES_PER_SECOND,
            "conservative_full_l2_credit_to_bf16_saved_hbm_seconds": (
                conservative_saved_hbm_bytes / H100_HBM_BYTES_PER_SECOND
            ),
            "planning_service_seconds_per_request": service_seconds,
            "five_percent_hurdle_seconds_per_request": hurdle_seconds,
            "peak_hbm_floor_reduction_fraction_of_planning_service": (
                bytes_saved / H100_HBM_BYTES_PER_SECOND / service_seconds
            ),
            "conservative_l2_credited_reduction_fraction_of_planning_service": (
                conservative_saved_hbm_bytes
                / H100_HBM_BYTES_PER_SECOND
                / service_seconds
            ),
            "clears_five_percent_hurdle_optimistically": (
                conservative_saved_hbm_bytes / H100_HBM_BYTES_PER_SECOND
                >= hurdle_seconds
            ),
            "selected_exact_shape_rows": selected_points,
            "correction_to_prior_floor": {
                "prior_bf16_bytes_per_token_per_layer_constant": 8192,
                "local_required_bf16_bytes_per_token_per_layer": local_bf16_per_layer_token,
                "global_required_bf16_bytes_per_token_per_layer": global_bf16_per_layer_token,
                "prior_total_read_bytes_per_request": 278976512000,
                "correct_total_read_bytes_per_request": bf16_bytes,
                "correction_factor": bf16_bytes / 278976512000,
                "reason": (
                    "Local K and V each contain 16*256 BF16 scalars; only global "
                    "4*512 K plus V equals 8192 bytes per token per layer."
                ),
            },
        },
        "checkpoint_free_exact_shape_measurement": {
            "type": "content_bound_contract_not_provider_launcher",
            "hardware": "one full NVIDIA H100 SXM, TP=1",
            "arms": ["BF16 paged KV", "FP8 E4M3 paged KV"],
            "required_runtime_binding": (
                "One immutable image must report the named vLLM revision or exact six-file "
                "hash set; construct actual local/global Attention modules and record selected "
                "backend classes before timing."
            ),
            "producer_consumer": (
                "Invoke unified_kv_cache_update with deterministic nonzero K/V, then the actual "
                "selected paged backend using block_table, slot_mapping, and seqused_k; a dense "
                "varlen stand-in or direct kernel fixture without the cache producer fails."
            ),
            "points": {
                "concurrency": [8, 16, 32],
                "local": {"context": 1024, "q_heads": 32, "kv_heads": 16, "head_dim": 256},
                "global_contexts": [4214, 4393, 4571],
                "global": {"q_heads": 32, "kv_heads": 4, "head_dim": 512},
                "block_size": 16,
            },
            "timing": "20 warmups then 100 randomized paired repetitions per row; alternate arm order; CUDA events plus synchronized wall time; setup and allocation excluded",
            "oracle": (
                "The timed output is consumed; compare FP8 output against the same nonzero BF16 "
                "paged output with cosine similarity >=0.99 and normalized RMSE <=0.05 on every row."
            ),
            "minimal_counters": [
                "dram__bytes_read.sum over the exact NVTX attention range",
                "lts__t_bytes.sum over the same range",
                "sm__cycles_elapsed.avg and achieved_active_warps",
                "kernel launch count and interval-union elapsed time",
            ],
            "acceptance": {
                "mechanism": "FP8 DRAM read bytes <=60% of BF16 at every row and byte reduction increases with context while launch count is unchanged",
                "component": "FP8 p50 interval-union attention time is >=10% lower at every engine-valid selected point",
                "whole_request": (
                    "Architecture-weight 50 local layers*358 steps and 10 global layers over "
                    "all contexts 4214..4571; measured saving must be >=0.0273987616 s/request."
                ),
                "reject_as_compute_or_launch_limited": (
                    "DRAM bytes fall but elapsed saving stays below the whole-request hurdle, "
                    "or speedup is context-invariant and explained by launch count/cycles instead."
                ),
            },
        },
        "rejected_mechanisms": [
            {
                "name": "single fused five-local/one-global attention kernel",
                "classification": "source_falsified",
                "reason": (
                    "The six attention calls occur in six different decoder layers with "
                    "o_proj, residual/norm, and MLP dependencies between them; their K/V caches "
                    "also belong to different layers. There is no scheduler-adjacent six-call boundary."
                ),
            },
            {
                "name": "K-equals-V one-copy global cache",
                "classification": "source_falsified",
                "reason": (
                    "The source duplicates projection weights but applies different K norm+RoPE "
                    "and V norm before cache update, and the paged consumer reads distinct K/V arrays."
                ),
            },
        ],
        "evidence": [
            {"path": str(frontier), "sha256": sha256(frontier), "type": "director-derived"},
            {"path": str(geometry), "sha256": sha256(geometry), "type": "measured-metadata"},
            {"path": str(config), "sha256": sha256(config), "type": "measured-official-config"},
            {"path": str(inventory), "sha256": sha256(inventory), "type": "vendor-reported-prior"},
            {"path": str(prior_floor), "sha256": sha256(prior_floor), "type": "derived-prior-corrected-here"},
        ],
        "evidence_boundary": (
            "No GPU, checkpoint, provider, compilation, or H100 throughput measurement was used. "
            "The >=5% result is an exact-shape byte/roofline plausibility bound and a falsifier, "
            "not achieved speed, quality, endpoint throughput, or economic acceptance."
        ),
    }
    output = PROJECT / "MECHANISM.json"
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
