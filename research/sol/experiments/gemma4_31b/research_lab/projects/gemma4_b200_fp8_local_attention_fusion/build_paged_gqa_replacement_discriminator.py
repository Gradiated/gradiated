#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "B200_FP8_LOCAL_PAGED_GQA_REPLACEMENT_DISCRIMINATOR.json"

MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
VLLM_COMMIT = "6d4a8e6d204a9b2827544003b26321fff62923da"
FLASHINFER_TAG_COMMIT = "70b142b75b46aa56e7f675a8e6ec1a977352c91f"
IMAGE_DIGEST = (
    "docker.io/vllm/vllm-openai:gemma4@"
    "sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
)
CONSUMER_NAME = (
    "fmhaSm100fKernel_QkvBfloat16OBfloat16H256PagedKv"
    "SlidingOrChunkedCausalP16MultiCtasKvVarSeqQ8Kv128StaticSwapsAbForGen"
)

PROJECT_FILES = {
    "candidate/local_paged_gqa_fused.py": None,
    "candidate/check_correctness_b200.py": None,
    (
        "inputs/pinned/flashinfer-0.6.6/trtllm-gen-artifact/"
        "checksums.txt"
    ): "10a54e8c3175099481aed2739ae30fa0f782368c40f9ad1b423ed8353315d65b",
    (
        "inputs/pinned/flashinfer-0.6.6/trtllm-gen-artifact/"
        "include/flashInferMetaInfo.h"
    ): "c31ed20605e8e7caad4d8301fedccf681520275813126c4660f8f933954cd78b",
    (
        "inputs/pinned/flashinfer-0.6.6/trtllm-gen-artifact/"
        f"{CONSUMER_NAME}.cubin"
    ): "a5ae26d06e8463baf3e1dac3251633b70ece90ca612a10afa6b09925578fd9be",
    (
        "inputs/pinned/flashinfer-0.6.6/flashinfer/data/csrc/"
        "trtllm_fmha_kernel_launcher.cu"
    ): "56627ee688c8cde526add0a4922fa2b5c044ad4e63066133197d16fb3f5839ca",
    (
        "inputs/pinned/flashinfer-0.6.6/flashinfer/data/include/"
        "flashinfer/trtllm/fmha/fmhaKernels.cuh"
    ): "8bf3350bef0ed070e6102c6dceb4760aa8114d2ca5328f22c5027cf5587e50f9",
    (
        "inputs/pinned/vllm-6d4a8e6d/vllm/v1/"
        "attention/backends/flashinfer.py"
    ): "e22db5ddadbd550083438946c4452b3227d98020c6c34285dd4b6917b39e2aae",
    "inputs/pinned/vllm-6d4a8e6d/csrc/cache_kernels.cu": (
        "129d20f62f0b97d4bcc27830ebf527950750bed9ddf557f7b3f989b4152a94fa"
    ),
}

UPSTREAM_NATIVE_SOURCE_HASHES = {
    "include/flashinfer/page.cuh":
        "6ad25f50ed08ea74495d8a8d172baf57266e53ce0d42b14dc9e979c1073c0468",
    "include/flashinfer/attention/decode.cuh":
        "019d673aa848a938798a2c58b34b9b5813a3f137962cbbd90ef7bd71f636f373",
    "include/flashinfer/attention/default_decode_params.cuh":
        "92388eb0b2c19cc01eb937d1dc7d45a46e512d25ac64e03cce91677f8cda6c4c",
    "include/flashinfer/attention/scheduler.cuh":
        "3fdc85c6b42d9c27fd688c614fef162bb523f3a95f095ba40dc53e3c52712c3b",
    "include/flashinfer/attention/variants.cuh":
        "90a228dd71b3ce8030d663e2b16f67f840fe4a3e99912f8b47774d3fd905a080",
    "csrc/batch_decode.cu":
        "9b0aa3da779d922af75d57f22d8c8bceb7722c2e4ded94637074b6baf567cd30",
    "csrc/batch_decode_jit_binding.cu":
        "fe1bad13e1ed242aa6b0e290bdb5a47388b2869a4305cfcbc952d5ec4b9def0a",
    "csrc/batch_decode_customize_config.jinja":
        "61c776b646b1351498f5cad2f7ff6256d0946fd88ed5ce5ce1e490a3d9d8f414",
    "flashinfer/jit/attention/modules.py":
        "dad408690a09545fe9d71e73ca59ad0b5b94de2f5f95caa10a96cfa7877ec0af",
    "flashinfer/decode.py":
        "882c71a2d5515b98ffb41e488b1e93b033f7ce92790493e63ad079b4dbb3402e",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bind_project_files() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for relative, expected in PROJECT_FILES.items():
        path = ROOT / relative
        observed = sha256(path)
        if expected is not None and observed != expected:
            raise ValueError(f"{relative}: {observed} != {expected}")
        result[relative] = {"sha256": observed, "bytes": path.stat().st_size}
    return result


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def build() -> dict[str, object]:
    project_bindings = bind_project_files()
    source_bundle = {
        "flashinfer_tag": "v0.6.6",
        "flashinfer_tag_commit": FLASHINFER_TAG_COMMIT,
        "upstream_source_hashes": UPSTREAM_NATIVE_SOURCE_HASHES,
        "project_files": project_bindings,
    }

    batch = 32
    qo_heads = 32
    kv_heads = 16
    head_dim = 256
    page_size = 16
    window_tokens = 1024
    element_bytes = 2
    kv_token_bytes = 2 * kv_heads * head_dim * element_bytes
    fresh_kv_bytes_per_call = batch * kv_token_bytes
    window_kv_bytes_per_call = batch * window_tokens * kv_token_bytes
    max_window_page_load_tokens = window_tokens + page_size - 1
    max_candidate_kv_bytes_per_call = (
        batch * max_window_page_load_tokens * kv_token_bytes
    )

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "classification": (
            "source_complete_uncompiled_unexecuted_sm100_local_paged_gqa_replacement"
        ),
        "decision": (
            "Admit one source-complete correctness candidate, not a benchmark-ready "
            "optimization. It replaces the opaque TRT-LLM Gen first consumer with "
            "FlashInfer v0.6.6 native paged-GQA CUDA source and performs the fresh "
            "K/V slot write inside the owning no-split decode CTA. The adapter passes "
            "only the final 65 page indices per request, so the native loop reads at "
            "most 1039 tokens and its sliding mask selects exactly the final 1024. "
            "Compilation, target-GPU correctness, and performance remain unmeasured."
        ),
        "authoritative_identity": {
            "model": {
                "id": "google/gemma-4-31B-it",
                "revision": MODEL_REVISION,
            },
            "runtime": {
                "image": IMAGE_DIGEST,
                "vllm_commit": VLLM_COMMIT,
                "flashinfer_version": "0.6.6",
                "flashinfer_tag_commit": FLASHINFER_TAG_COMMIT,
            },
            "hardware": {
                "required": "nvidia-b200-sxm",
                "target": "sm_100",
                "gpu_claimed": False,
                "cuda_executed": False,
            },
            "workload": {
                "identity": "c32/4214/358/text-only/non-reasoning",
                "concurrency": batch,
                "decode_steps": 358,
                "local_layers": 50,
                "local_attention_calls": 17900,
                "seq_lens_range_inclusive": [4214, 4571],
            },
        },
        "exact_pinned_first_consumer": {
            "flashinfer_artifact_root": (
                "f1ed60e5666a7620683a8c34a41c850a25029b35/fmha/trtllm-gen/"
            ),
            "artifact_checksums_sha256": (
                "10a54e8c3175099481aed2739ae30fa0f782368c40f9ad1b423ed8353315d65b"
            ),
            "metainfo_sha256": (
                "c31ed20605e8e7caad4d8301fedccf681520275813126c4660f8f933954cd78b"
            ),
            "selector_derivation": {
                "q_kv_o_dtype": ["bfloat16", "bfloat16", "bfloat16"],
                "qkv_layout": "PagedKv",
                "head_dim_qk": 256,
                "head_dim_v": 256,
                "max_q_len": 1,
                "gqa_group_size": 2,
                "tile_size_q": 8,
                "tile_size_kv": 128,
                "step_q": 8,
                "step_kv": 256,
                "head_dim_per_cta_v": 256,
                "page_size": 16,
                "mask": "SlidingOrChunkedCausal",
                "tile_scheduler": "Static",
                "multi_ctas_kv": True,
                "groups_heads_q": True,
                "groups_tokens_heads_q": True,
                "kernel_type": "SwapsMmaAbForGeneration",
                "sm_compatibility": "SM100f admitted on B200 SM100",
            },
            "function_name": CONSUMER_NAME,
            "cubin_file": f"{CONSUMER_NAME}.cubin",
            "cubin_bytes": 154568,
            "dynamic_shared_memory_bytes": 144992,
            "threads_per_cta": 512,
            "cubin_sha256": (
                "a5ae26d06e8463baf3e1dac3251633b70ece90ca612a10afa6b09925578fd9be"
            ),
            "device_source_available": False,
            "abi_inputs": [
                "query",
                "paged key cache",
                "paged value cache",
                "workspace",
                "block tables",
                "sequence lengths",
                "window_left",
                "output",
            ],
            "abi_excludes": ["fresh key", "fresh value", "slot mapping"],
        },
        "production_contract": {
            "producer": {
                "query": {
                    "shape": [batch, qo_heads, head_dim],
                    "dtype": "bfloat16",
                    "strides": [8192, 256, 1],
                    "position_transform": "already applied upstream",
                },
                "fresh_key": {
                    "shape": [batch, kv_heads, head_dim],
                    "dtype": "bfloat16",
                    "strides": [4096, 256, 1],
                },
                "fresh_value": {
                    "shape": [batch, kv_heads, head_dim],
                    "dtype": "bfloat16",
                    "strides": [4096, 256, 1],
                },
                "ownership": (
                    "one current decode token per request after the local layer QKV projection"
                ),
            },
            "slot_map": {
                "shape": [batch],
                "dtype": "int64",
                "physical_slot_formula": (
                    "physical_page * page_size + entry_in_page"
                ),
                "negative_semantics": "no cache mutation",
                "required_consistency": (
                    "nonnegative slot resolves to the request's final block-table "
                    "page and (seq_len-1)%16"
                ),
            },
            "cache": {
                "logical_shape": ["num_pages", 2, kv_heads, page_size, head_dim],
                "dtype": "bfloat16",
                "logical_layout": "HND",
                "element_strides": [131072, 65536, 256, 4096, 1],
                "physical_allocation": (
                    "interleaved NHD allocation exposed through an HND logical view"
                ),
                "block_tables": {
                    "shape": [batch, "max_blocks_per_request"],
                    "dtype": "int32",
                },
                "seq_lens": {
                    "shape": [batch],
                    "dtype": "int32",
                    "range_inclusive": [4214, 4571],
                },
                "page_size": page_size,
            },
            "attention": {
                "q_heads": qo_heads,
                "kv_heads": kv_heads,
                "gqa_group_size": 2,
                "head_dim": head_dim,
                "window_left": 1023,
                "visible_tokens": window_tokens,
                "attention_scale": 1.0,
                "logits_soft_cap": None,
                "position_encoding_inside_consumer": "none",
            },
            "output": {
                "shape": [batch, qo_heads, head_dim],
                "dtype": "bfloat16",
                "layout": "contiguous",
                "first_downstream_consumer": "local attention output projection",
            },
            "persistent_side_effect": (
                "the exact fresh BF16 K/V vectors occupy their physical slots for "
                "all later decode steps"
            ),
        },
        "source_complete_upstream_discrimination": [
            {
                "implementation": "FlashInfer v0.6.6 native BatchDecodeWithPagedKVCache",
                "source_complete": True,
                "paged_standard_gqa": True,
                "head_dim_256": True,
                "custom_cache_strides": True,
                "sliding_mask": True,
                "sm100_compilable_cuda_source": True,
                "fresh_kv_slot_side_effect": False,
                "disposition": "selected_as_candidate_base",
                "amendment": (
                    "custom AttentionVariant writes fresh K/V before the native "
                    "paged-GQA loop; page metadata is limited to the final 65 pages"
                ),
            },
            {
                "implementation": "FlashInfer v0.6.6 CUTLASS SM100 FMHA",
                "source_complete": True,
                "disposition": "typed_mechanism_rejection",
                "reason": (
                    "standard entry accepts contiguous ragged K/V only and dispatches "
                    "head dimensions 64, 128, or QK192/VO128; it has neither standard "
                    "paged GQA d256 nor the cache side-effect ABI"
                ),
            },
            {
                "implementation": "FlashInfer v0.6.6 Blackwell paged MLA",
                "source_complete": True,
                "disposition": "typed_mechanism_rejection",
                "reason": (
                    "paged SM100 source is the latent/rope MLA mechanism, not "
                    "16-head BF16 standard GQA with d256 K and V"
                ),
            },
            {
                "implementation": "FlashInfer/TensorRT-LLM fmha_v2 paged KV source",
                "source_complete": True,
                "disposition": "typed_mechanism_rejection",
                "reason": (
                    "source describes paged GQA and sliding masks but is not the "
                    "selected SM100 Gen implementation and exposes no fresh-KV slot ABI"
                ),
            },
        ],
        "candidate": {
            "name": "Gemma4LocalFusedAppendDecode",
            "source": "candidate/local_paged_gqa_fused.py",
            "harness": "candidate/check_correctness_b200.py",
            "intervention_boundary": (
                "inside the source-complete native paged-decode device CTA, before "
                "the first cache load"
            ),
            "launch_ownership": {
                "grid": ["batch=32", "kv_heads=16"],
                "block": ["x=32", "y=2", "z=2"],
                "blocks": 512,
                "threads_per_block": 128,
                "one_owner_per": ["request", "kv_head"],
                "split_kv": "forbidden and asserted false before invocation",
            },
            "cache_write": {
                "writers": "threadIdx.y==0 && threadIdx.z==0",
                "vector": "8 BF16 elements / 16 bytes per x thread",
                "barrier": "CTA sync before paged cache loads",
                "negative_slot": "no write, then same existing-cache attention semantics",
            },
            "page_metadata_adapter": {
                "operation": (
                    "slice the final min(65, logical_page_count) block-table indices "
                    "per request; do not move or rewrite cache bytes"
                ),
                "max_tokens_loaded_per_request": max_window_page_load_tokens,
                "mask_selects_exactly": window_tokens,
                "additional_device_kernel": False,
            },
            "first_consumer_ownership": [
                "query",
                "fresh key",
                "fresh value",
                "slot mapping",
                "paged cache mutation",
                "page indices and lengths",
                "window mask",
                "softmax and value reduction",
                "BF16 output",
            ],
            "status": {
                "source_complete": True,
                "compiled": False,
                "executed": False,
                "correctness_measured": False,
                "performance_measured": False,
                "production_integrated": False,
            },
        },
        "analytical_accounting": {
            "label": "derived_not_measured",
            "per_call": {
                "fresh_kv_cache_write_bytes": fresh_kv_bytes_per_call,
                "stock_exact_window_kv_read_bytes": window_kv_bytes_per_call,
                "candidate_max_page_rounded_kv_read_bytes": (
                    max_candidate_kv_bytes_per_call
                ),
                "candidate_max_page_rounding_overread_bytes": (
                    max_candidate_kv_bytes_per_call - window_kv_bytes_per_call
                ),
                "candidate_max_page_rounding_overread_fraction": (
                    max_candidate_kv_bytes_per_call / window_kv_bytes_per_call - 1
                ),
                "separate_append_launch_removed_if_correct": 1,
            },
            "full_workload": {
                "calls": 17900,
                "separate_append_launches_removed_if_correct": 17900,
                "fresh_kv_cache_write_bytes_preserved": (
                    fresh_kv_bytes_per_call * 17900
                ),
            },
            "warning": (
                "The source-complete CUDA-core path is not assumed faster than the "
                "opaque Blackwell tensor-core cubin. This accounting only proves the "
                "semantic boundary and bounds page-rounding traffic."
            ),
        },
        "smallest_target_gpu_correctness_plan": {
            "type": "one_hash_bound_component_pair_not_a_benchmark",
            "target": "one identity-verified NVIDIA B200 SM100",
            "bench_claim_now": False,
            "provider_operation_now": False,
            "endpoint_or_model_load": False,
            "bundle_manifest_sha256": canonical_hash(source_bundle),
            "source_bundle": source_bundle,
            "geometry": {
                "batch": batch,
                "q_heads": qo_heads,
                "kv_heads": kv_heads,
                "head_dim": head_dim,
                "dtype": "bfloat16",
                "page_size": page_size,
                "cache_strides": [131072, 65536, 256, 4096, 1],
                "seq_lens": (
                    "32 monotonic values spanning the exact inclusive 4214..4571 range"
                ),
                "window_left": 1023,
                "page_tables": (
                    "old prefix pages alias one sentinel; every final 65-page tail "
                    "is unique and observable"
                ),
            },
            "arms": [
                {
                    "name": "stock",
                    "operation": (
                        "pinned vLLM reshape_and_cache_flash, then the exact "
                        f"{CONSUMER_NAME} cubin"
                    ),
                },
                {
                    "name": "candidate",
                    "operation": (
                        "one JIT-built source-complete native decode invocation that "
                        "performs cache append and attention"
                    ),
                },
            ],
            "shared_inputs": (
                "bitwise-identical initial cache, Q, fresh K/V, slot map, block tables, "
                "sequence lengths, and scale"
            ),
            "decision_gates": {
                "candidate_finite": True,
                "output_allclose": {"rtol": 0.05, "atol": 0.03},
                "output_cosine_min": 0.999,
                "entire_cache_bitwise_equal": True,
                "split_kv": False,
            },
            "terminal_artifact": "CORRECTNESS_TERMINAL.json",
            "attempt_semantics": {
                "complete_comparison": "one consumed scientific sample",
                "compile_import_path_parser_or_comparator_failure": (
                    "invalid attempt; preserve artifact and repair only invalidated stage"
                ),
                "candidate_output_or_cache_mismatch": "scientific incorrect terminal",
            },
            "after_correctness_only": (
                "a distinct preregistered component timing pair may compare stock append+"
                "cubin against candidate; no endpoint replay is authorized here"
            ),
        },
        "economic_relevance": {
            "fixed_qualified_request_seconds": 0.625149101968745,
            "campaign_target_seconds": 0.500119281574996,
            "absolute_gap_seconds": 0.125029820393749,
            "promotion_rule": (
                "correctness is necessary but insufficient; later target-GPU component "
                "timing must show a material request-level bound before any integration"
            ),
        },
        "limits": [
            "No GPU was claimed and no CUDA was run.",
            "No benchmark result is claimed.",
            "No endpoint was replayed.",
            "No global K=V or M32 path was modified.",
            "No provider operation or paid mutation occurred.",
            "The candidate is source-complete against exact pinned upstream bytes but uncompiled.",
        ],
        "builder": {
            "path": Path(__file__).name,
            "sha256": sha256(Path(__file__)),
        },
    }


def main() -> None:
    payload = build()
    tmp = OUTPUT.with_suffix(OUTPUT.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    json.loads(tmp.read_text())
    os.replace(tmp, OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
