#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "B200_FP8_LOCAL_ATTENTION_FUSION_DISCRIMINATOR.json"

MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
VLLM_COMMIT = "6d4a8e6d204a9b2827544003b26321fff62923da"
IMAGE_DIGEST = (
    "docker.io/vllm/vllm-openai:gemma4@"
    "sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
)
PREDECESSOR_SHA256 = "39cf154a24e8bf13d654f11d0a200952b1fc666384a7fe404761fea06d084c43"

SOURCE_HASHES = {
    "inputs/pinned/vllm-6d4a8e6d/csrc/cache.h": (
        "60cfc5e366b524b74843792c9b539497fb77a397f94d78e14fcf55d8b1e74192"
    ),
    "inputs/pinned/vllm-6d4a8e6d/csrc/cache_kernels.cu": (
        "129d20f62f0b97d4bcc27830ebf527950750bed9ddf557f7b3f989b4152a94fa"
    ),
    (
        "inputs/pinned/vllm-6d4a8e6d/vllm/model_executor/"
        "layers/attention/attention.py"
    ): "2e45ac35100a1396bd03f9fe8d7f3e4dd41f3dc0a78b3bc7e5e118b536a0fe3c",
    (
        "inputs/pinned/vllm-6d4a8e6d/vllm/v1/"
        "attention/backends/flashinfer.py"
    ): "e22db5ddadbd550083438946c4452b3227d98020c6c34285dd4b6917b39e2aae",
    "inputs/pinned/flashinfer-0.6.6/flashinfer/decode.py": (
        "882c71a2d5515b98ffb41e488b1e93b033f7ce92790493e63ad079b4dbb3402e"
    ),
    (
        "inputs/pinned/flashinfer-0.6.6/flashinfer/data/csrc/"
        "trtllm_fmha_kernel_launcher.cu"
    ): "56627ee688c8cde526add0a4922fa2b5c044ad4e63066133197d16fb3f5839ca",
    (
        "inputs/pinned/flashinfer-0.6.6/flashinfer/data/include/"
        "flashinfer/trtllm/fmha/fmhaRunner.cuh"
    ): "e3bfbcad53e4c9b39bc820e17eb5e3896121591cd28618775c310725124e4b90",
    (
        "inputs/pinned/flashinfer-0.6.6/flashinfer/data/include/"
        "flashinfer/trtllm/fmha/fmhaRunnerParams.h"
    ): "e05b0f40e73d87b97d74dfdb2c18775f6f72b44e487296be6a61a46c34b63495",
    (
        "inputs/pinned/flashinfer-0.6.6/flashinfer/data/include/"
        "flashinfer/trtllm/fmha/fmhaKernels.cuh"
    ): "8bf3350bef0ed070e6102c6dceb4760aa8114d2ca5328f22c5027cf5587e50f9",
    (
        "inputs/pinned/flashinfer-0.6.6/flashinfer/data/include/"
        "flashinfer/trtllm/fmha/kernelParams.h"
    ): "df7ec06f707309404bf6670a63de76c24dd5df253913ce74aba811ba895659db",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bind_sources() -> dict[str, dict[str, object]]:
    bindings = {}
    for relative_path, expected_hash in SOURCE_HASHES.items():
        path = ROOT / relative_path
        observed_hash = sha256(path)
        if observed_hash != expected_hash:
            raise ValueError(
                f"source hash mismatch for {relative_path}: "
                f"{observed_hash} != {expected_hash}"
            )
        bindings[relative_path] = {
            "sha256": observed_hash,
            "bytes": path.stat().st_size,
        }
    return bindings


def build() -> dict[str, object]:
    decode_steps = 358
    local_layers = 50
    batch = 32
    query_heads = 32
    kv_heads = 16
    head_dim = 256
    element_bytes = 2
    window_tokens = 1024
    calls = decode_steps * local_layers

    kv_bytes_per_token = kv_heads * head_dim * 2 * element_bytes
    current_kv_bytes = calls * batch * kv_bytes_per_token
    baseline_attention_kv_read_bytes = (
        calls * batch * window_tokens * kv_bytes_per_token
    )
    fused_historical_kv_read_bytes = (
        calls * batch * (window_tokens - 1) * kv_bytes_per_token
    )
    baseline_kv_path_bytes = (
        current_kv_bytes
        + current_kv_bytes
        + baseline_attention_kv_read_bytes
    )
    fused_kv_path_bytes = (
        current_kv_bytes + current_kv_bytes + fused_historical_kv_read_bytes
    )
    query_or_output_bytes = (
        calls * batch * query_heads * head_dim * element_bytes
    )

    source_bindings = bind_sources()
    generator_hash = sha256(Path(__file__))

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "classification": (
            "typed_rejection_production_trtllm_local_append_decode_fusion"
        ),
        "decision": (
            "Reject a wrapper- or launcher-only append+decode fusion for the "
            "exact SM100 production path. The only intervention that removes "
            "the source-proven append launch must add fresh K/V and slot mapping "
            "to the TRT-LLM device kernel itself or replace that kernel. "
            "FlashInfer 0.6.6 loads the selected implementation as a hash-checked "
            "external cubin, so the pinned source packet contains no editable "
            "device implementation to bind or validate."
        ),
        "authoritative_identities": {
            "model": {
                "id": "google/gemma-4-31B-it",
                "revision": MODEL_REVISION,
            },
            "runtime": {
                "image": IMAGE_DIGEST,
                "vllm_commit": VLLM_COMMIT,
                "flashinfer_version": "0.6.6",
                "source_bindings": source_bindings,
            },
            "hardware": {
                "id": "nvidia-b200-sxm",
                "programming_target": "sm_100",
                "executed": False,
            },
            "workload": {
                "identity": "c32/4214/358/text-only/non-reasoning",
                "concurrency": batch,
                "prompt_tokens_per_request": 4214,
                "decode_steps": decode_steps,
                "sequence_lengths_inclusive": [4214, 4571],
                "tensor_parallel_size": 1,
            },
            "named_predecessor": {
                "path": (
                    "../gemma4_b200_fp8_hybrid_attention_dataflow/"
                    "B200_FP8_LOCAL_WINDOW_KV_DISCRIMINATOR.json"
                ),
                "sha256": PREDECESSOR_SHA256,
                "consumed_once": True,
            },
        },
        "exact_production_input_to_first_consumer": {
            "phase": "decode",
            "multiplicity": {
                "local_layers": local_layers,
                "decode_steps": decode_steps,
                "local_attention_calls": calls,
            },
            "inputs_per_call": {
                "query": {
                    "shape": [batch, query_heads, head_dim],
                    "dtype": "bfloat16",
                    "layout": "contiguous",
                },
                "fresh_key": {
                    "shape": [batch, kv_heads, head_dim],
                    "dtype": "bfloat16",
                    "layout": "contiguous",
                },
                "fresh_value": {
                    "shape": [batch, kv_heads, head_dim],
                    "dtype": "bfloat16",
                    "layout": "contiguous",
                },
                "slot_mapping": {
                    "shape": [batch],
                    "dtype": "int64",
                    "negative_value_semantics": "padded token is a no-op",
                },
                "paged_kv_cache": {
                    "logical_shape": ["num_blocks", 2, kv_heads, 16, head_dim],
                    "element_strides": [131072, 65536, 256, 4096, 1],
                    "dtype": "bfloat16",
                    "layout_contract": "HND logical view over interleaved allocation",
                },
                "block_tables": {
                    "shape": [batch, "max_blocks_per_sequence"],
                    "dtype": "int32",
                    "visible_pages_per_request": [64, 65],
                },
                "seq_lens": {
                    "shape": [batch],
                    "dtype": "int32",
                    "range_inclusive": [4214, 4571],
                },
                "window_left": 1023,
                "attention_scale": 1.0,
                "attention_logit_soft_cap": None,
            },
            "source_proven_order": [
                {
                    "ordinal": 1,
                    "symbol": "vllm.unified_kv_cache_update",
                    "effect": (
                        "passes fresh K/V and the layer slot mapping to "
                        "FlashInferImpl.do_kv_cache_update"
                    ),
                },
                {
                    "ordinal": 2,
                    "symbol": "vllm::reshape_and_cache_flash_kernel",
                    "effect": (
                        "one explicit CUDA launch with grid.x=num_actual_tokens; "
                        "reads slot_mapping and writes fresh K/V into paged cache"
                    ),
                    "launch_geometry": {"grid_x": batch, "block_x": 512},
                },
                {
                    "ordinal": 3,
                    "symbol": "kv_cache_dummy_dep",
                    "effect": "orders cache mutation before attention",
                },
                {
                    "ordinal": 4,
                    "symbol": (
                        "flashinfer.decode.trtllm_batch_decode_with_kv_cache"
                    ),
                    "effect": (
                        "passes Q, paged K/V, block tables, seq_lens, and "
                        "window_left=1023 to the SM100 TRT-LLM runner"
                    ),
                },
                {
                    "ordinal": 5,
                    "symbol": "TllmGenFmhaKernel::loadKernel",
                    "effect": (
                        "loads the selected hash-checked external cubin and "
                        "launches the first decision-bearing local-attention consumer"
                    ),
                },
            ],
            "first_consumer": {
                "symbol": "TRT-LLM Gen FMHA cubin selected by TllmGenFmhaKernel",
                "inputs_present": [
                    "query",
                    "paged key cache",
                    "paged value cache",
                    "block tables",
                    "sequence lengths",
                    "window_left",
                ],
                "inputs_absent": ["fresh key", "fresh value", "slot_mapping"],
                "device_source_present_in_pinned_packet": False,
            },
        },
        "mechanism_examined": {
            "name": "fuse fresh-KV append into local TRT-LLM decode",
            "semantic_change": False,
            "required_device_behavior": [
                "For each nonnegative slot, write fresh BF16 K/V to its exact "
                "physical cache slot for future layers/steps.",
                "For both GQA query heads sharing a KV head, consume the fresh "
                "K/V directly for the current position instead of rereading it "
                "from the just-written cache.",
                "Consume exactly the preceding 1,023 tokens plus the current "
                "token and preserve online-softmax FP32 state and BF16 output.",
            ],
            "host_only_merge_is_not_the_intervention": (
                "Combining both calls under one Python/custom-op wrapper still "
                "launches reshape_and_cache_flash_kernel followed by the opaque "
                "FMHA cubin and removes no device work."
            ),
        },
        "non_overlapping_launch_accounting": {
            "evidence_class": "source-proven_host_submissions_and_append_kernel_launch",
            "baseline": {
                "local_append_op_submissions": calls,
                "source_proven_standalone_append_kernel_launches": calls,
                "attention_consumer_submissions": calls,
                "opaque_attention_internal_launches": "not claimed",
            },
            "true_device_fusion_counterfactual": {
                "local_append_op_submissions": 0,
                "standalone_append_kernel_launches": 0,
                "attention_consumer_submissions": calls,
                "opaque_or_replacement_attention_internal_launches": (
                    "must be measured on SM100"
                ),
                "source_proven_standalone_launch_delta": -calls,
            },
            "wrapper_only_candidate": {
                "source_proven_standalone_launch_delta": 0,
                "reason": "it cannot change the two device entrypoints",
            },
        },
        "non_overlapping_byte_accounting": {
            "scope": (
                "BF16 local K/V path from fresh K/V producer through the first "
                "attention consumer; query/output and metadata are reported "
                "separately and are unchanged"
            ),
            "per_token": {
                "fresh_or_cached_k_plus_v_bytes": kv_bytes_per_token,
                "query_or_output_bytes": query_heads * head_dim * element_bytes,
            },
            "baseline": {
                "fresh_kv_source_reads_for_append": current_kv_bytes,
                "fresh_kv_cache_writes": current_kv_bytes,
                "window_kv_cache_reads": baseline_attention_kv_read_bytes,
                "total_kv_path_bytes": baseline_kv_path_bytes,
                "query_reads": query_or_output_bytes,
                "attention_output_writes": query_or_output_bytes,
                "slot_mapping_reads": calls * batch * 8,
                "seq_len_reads_upper_bound_once_per_call": calls * batch * 4,
            },
            "true_device_fusion_counterfactual": {
                "fresh_kv_source_reads_for_compute_and_store": current_kv_bytes,
                "fresh_kv_cache_writes": current_kv_bytes,
                "historical_1023_token_kv_cache_reads": (
                    fused_historical_kv_read_bytes
                ),
                "total_kv_path_bytes": fused_kv_path_bytes,
                "query_reads": query_or_output_bytes,
                "attention_output_writes": query_or_output_bytes,
                "slot_mapping_reads": calls * batch * 8,
                "seq_len_reads_upper_bound_once_per_call": calls * batch * 4,
            },
            "counterfactual_delta": {
                "compulsory_kv_bytes": -current_kv_bytes,
                "fraction_of_baseline_kv_path": (
                    -current_kv_bytes / baseline_kv_path_bytes
                ),
                "mandatory_cache_write_bytes": 0,
                "historical_window_cache_read_bytes": 0,
                "query_or_output_bytes": 0,
                "metadata_bytes": 0,
            },
            "exclusions": {
                "page_table_compaction": "not replayed and no bytes credited",
                "global_attention_or_global_k_eq_v": "not counted",
                "M32_or_residual_hotpath": "not counted",
                "opaque_attention_workspace_or_reduction_traffic": (
                    "not claimed without target execution"
                ),
            },
        },
        "physical_hypothesis": {
            "causal_change": (
                "Move the source-proven cache store into the first attention "
                "consumer and bypass the current-token cache reread."
            ),
            "predicted_sm100_counter_change_if_implemented": {
                "separate_append_kernel_launches": -calls,
                "compulsory_local_kv_bytes": -current_kv_bytes,
                "compulsory_local_kv_fraction": (
                    -current_kv_bytes / baseline_kv_path_bytes
                ),
                "attention_math_flops": 0,
                "cache_write_bytes": 0,
                "expected_direction": {
                    "gpu__time_duration": "decrease by removed append-kernel time",
                    "dram__bytes": "decrease by at most the current-token cache reread",
                    "sm__throughput": (
                        "no guaranteed direction; historical 1,023-token attention "
                        "work remains dominant"
                    ),
                },
            },
            "falsifier": (
                "A target trace showing the append is already absorbed into the "
                "same cubin, or a fused implementation whose output/cache oracle "
                "passes but whose total attention region does not fall beyond "
                "run-to-run noise."
            ),
        },
        "typed_rejection": {
            "code": "opaque_device_consumer_abi_excludes_fresh_kv_and_slot_mapping",
            "mechanism": "append plus TRT-LLM Gen paged decode fusion",
            "semantic_status": "well-defined_but_not_implemented",
            "implementation_status": "rejected_for_exact_pinned_production_consumer",
            "reasons": [
                "The exact vLLM backend declares forward_includes_kv_cache_update=false "
                "and invokes reshape_and_cache_flash before attention.",
                "The exact append implementation is one explicit CUDA kernel launch.",
                "The FlashInfer decode API and TllmGenFmhaRunnerParams expose cache "
                "pointers but no fresh-K/V or slot-mapping inputs.",
                "The SM100 runner selects and loads a hash-checked external cubin; "
                "the pinned source packet contains launcher/parameter code, not the "
                "device kernel needed to perform the fusion.",
                "A wrapper-only patch leaves both device launches intact, while a "
                "new replacement attention kernel would be a different unimplemented "
                "mechanism and cannot be called production-input-to-first-consumer "
                "ready without an exact SM100 correctness run.",
            ],
            "reopen_condition": (
                "Provide the exact hash-bound TRT-LLM Gen SM100 device source/cubin "
                "build path with an ABI that accepts fresh K/V plus slot mapping, "
                "or implement and target-execute a replacement paged GQA decode "
                "kernel that writes the cache and consumes every output."
            ),
            "b200_component_recommendation": "do_not_reserve_for_wrapper_fusion",
        },
        "scope_compliance": {
            "cuda_executed": False,
            "gpu_claimed": False,
            "endpoint_requests": 0,
            "provider_operations": False,
            "provider_spend_usd": 0.0,
            "external_page_compaction_replayed": False,
            "global_k_eq_v_modified": False,
            "m32_modified": False,
        },
        "generator": {
            "path": Path(__file__).name,
            "sha256": generator_hash,
        },
    }


def main() -> None:
    payload = build()
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, OUTPUT)


if __name__ == "__main__":
    main()
