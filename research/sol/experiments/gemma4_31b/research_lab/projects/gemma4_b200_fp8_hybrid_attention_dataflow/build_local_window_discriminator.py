#!/usr/bin/env python3

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from local_window_kv_oracle import run_oracle

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "B200_FP8_LOCAL_WINDOW_KV_DISCRIMINATOR.json"
FLASHINFER = ROOT / "inputs/pinned_runtime/v1/attention/backends/flashinfer.py"
GPU_RUNNER = ROOT / "inputs/pinned_runtime/v1/worker/gpu_model_runner.py"

EXPECTED_LOCAL_HASHES = {
    FLASHINFER: "e22db5ddadbd550083438946c4452b3227d98020c6c34285dd4b6917b39e2aae",
    GPU_RUNNER: "3afc290d3df1be3df1b89b9b35942695f5896c7729f608d6c44580899212c301",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_source_facts(source: str, fragments: list[str]) -> None:
    missing = [fragment for fragment in fragments if fragment not in source]
    if missing:
        raise AssertionError(f"pinned source facts missing: {missing}")


def build() -> dict:
    for path, expected in EXPECTED_LOCAL_HASHES.items():
        actual = sha256(path)
        if actual != expected:
            raise AssertionError(f"{path}: expected {expected}, got {actual}")

    flashinfer_source = FLASHINFER.read_text()
    runner_source = GPU_RUNNER.read_text()
    require_source_facts(
        flashinfer_source,
        [
            'return "HND"',
            "self.use_trtllm_decode_attention = can_use_trtllm",
            "block_tables=block_table_tensor[:num_decodes]",
            "seq_lens=seq_lens[:num_decodes]",
            "trtllm_batch_decode_with_kv_cache(",
            "window_left=self.window_left",
            "torch.ops._C_cache_ops.reshape_and_cache_flash(",
            "slot_mapping's shape to determine the number of",
        ],
    )
    require_source_facts(
        runner_source,
        [
            "self.input_batch.block_table.compute_slot_mapping(",
            "slot_mapping[num_tokens_unpadded:num_tokens_padded].fill_(-1)",
            "for kv_cache_gid, kv_cache_group in enumerate(kv_cache_groups):",
            "for layer_name in attn_group.layer_names:",
        ],
    )

    seq_lens = list(range(4214, 4572))
    full_pages = [math.ceil(seq_len / 16) for seq_len in seq_lens]
    window_pages = [
        math.ceil(seq_len / 16) - math.floor((seq_len - 1024) / 16)
        for seq_len in seq_lens
    ]
    steps = len(seq_lens)
    concurrency = 32
    local_layers = 50
    local_groups = 5
    layers_per_group = 10
    local_calls = steps * local_layers
    group_steps = steps * local_groups
    full_group_page_refs = sum(full_pages) * concurrency * local_groups
    window_group_page_refs = sum(window_pages) * concurrency * local_groups
    full_consumer_page_refs = full_group_page_refs * layers_per_group
    window_consumer_page_refs = window_group_page_refs * layers_per_group
    page_ref_delta = full_consumer_page_refs - window_consumer_page_refs
    fixed_compact_entries = 65 * concurrency * group_steps
    seq_len_values = concurrency * group_steps
    rejected_compaction_bytes = (
        window_group_page_refs * 4
        + fixed_compact_entries * 4
        + seq_len_values * 4
        + seq_len_values * 4
    )
    local_kv_read_bytes = (
        concurrency * 1024 * 16_384 * local_layers * steps
    )
    local_kv_write_bytes = concurrency * 16_384 * local_layers * steps
    oracle = run_oracle()
    if oracle["production"]["sum_pages"] != sum(window_pages):
        raise AssertionError("oracle and accounting disagree")

    artifact = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "classification": (
            "typed_rejection_external_local_window_page_table_compaction"
        ),
        "decision": (
            "Reject external 64-65-page table materialization as the next B200 "
            "component. It preserves visible-token addressing but removes no "
            "mandatory BF16 KV bytes or attention/append submissions, while the "
            "SM100-preferred TRT-LLM route already receives window_left=1023 and "
            "would pay 1,790 new compaction launches."
        ),
        "authoritative_identities": {
            "model": {
                "id": "google/gemma-4-31B-it",
                "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            },
            "runtime": {
                "image": (
                    "docker.io/vllm/vllm-openai:gemma4@sha256:"
                    "952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
                ),
                "vllm_commit": "6d4a8e6d204a9b2827544003b26321fff62923da",
                "flashinfer_version": "0.6.6",
                "local_source_hashes": {
                    str(FLASHINFER.relative_to(ROOT)): sha256(FLASHINFER),
                    str(GPU_RUNNER.relative_to(ROOT)): sha256(GPU_RUNNER),
                },
                "inspected_pinned_source_hashes": {
                    "vllm/utils/flashinfer.py": (
                        "6fcb18fbe2487a3fcbc2a4a4a09b2df96be9719dd752681cf2f08ba6113fa93d"
                    ),
                    "vllm/model_executor/layers/attention/attention.py": (
                        "2e45ac35100a1396bd03f9fe8d7f3e4dd41f3dc0a78b3bc7e5e118b536a0fe3c"
                    ),
                    "flashinfer-0.6.6/flashinfer/decode.py": (
                        "882c71a2d5515b98ffb41e488b1e93b033f7ce92790493e63ad079b4dbb3402e"
                    ),
                },
            },
            "hardware": {
                "id": "nvidia-b200-sxm",
                "programming_target": "sm_100",
                "executed": False,
            },
            "workload": {
                "identity": "c32/4214/358/text-only/non-reasoning",
                "concurrency": concurrency,
                "prompt_tokens_per_request": 4214,
                "decode_steps": steps,
                "sequence_lengths_inclusive": [4214, 4571],
                "tensor_parallel_size": 1,
            },
        },
        "exact_local_geometry": {
            "layers": {
                "local": local_layers,
                "local_groups": local_groups,
                "layers_per_group": layers_per_group,
            },
            "attention": {
                "query_heads": 32,
                "kv_heads": 16,
                "gqa_queries_per_kv_head": 2,
                "head_dim": 256,
                "sliding_window_tokens": 1024,
                "window_left": 1023,
                "query_shape_per_decode_call": [32, 32, 256],
                "key_value_shape_each_per_append_call": [32, 16, 256],
            },
            "paged_kv": {
                "dtype": "bfloat16",
                "element_bytes": 2,
                "consumer_layout": "HND",
                "consumer_shape_per_layer": [
                    "num_blocks",
                    2,
                    16,
                    16,
                    256,
                ],
                "consumer_element_strides": [
                    131072,
                    65536,
                    256,
                    4096,
                    1,
                ],
                "block_tokens": 16,
                "bytes_per_token_per_layer_k_plus_v": 16384,
                "bytes_per_page_per_layer": 262144,
                "full_pages_per_request_per_step": {
                    "min": min(full_pages),
                    "max": max(full_pages),
                    "sum": sum(full_pages),
                },
                "window_intersecting_pages_per_request_per_step": {
                    "min": min(window_pages),
                    "max": max(window_pages),
                    "count_64": window_pages.count(64),
                    "count_65": window_pages.count(65),
                    "sum": sum(window_pages),
                },
                "valid_window_page_references_five_groups_c32": (
                    window_group_page_refs
                ),
            },
            "calls_over_completion": {
                "local_attention_first_consumer": local_calls,
                "local_kv_append": local_calls,
                "local_group_metadata_builds": group_steps,
            },
        },
        "production_dataflow": {
            "slot_producer": (
                "GPUModelRunner._prepare_inputs -> BlockTable.compute_slot_mapping"
            ),
            "append": (
                "Attention.forward -> unified_kv_cache_update -> "
                "FlashInferImpl.do_kv_cache_update -> "
                "torch.ops._C_cache_ops.reshape_and_cache_flash"
            ),
            "ordering": (
                "kv_cache_dummy_dep orders the append before attention; the "
                "absolute slot_mapping is not rebased"
            ),
            "metadata_producer": (
                "FlashInferMetadataBuilder.build -> TRTLLMDecode(block_tables, "
                "seq_lens, max_seq_len)"
            ),
            "first_consumer": (
                "FlashInferImpl.forward -> "
                "flashinfer.decode.trtllm_batch_decode_with_kv_cache -> "
                "trtllm_paged_attention_decode"
            ),
            "sm100_route": (
                "vLLM prefers TRT-LLM decode when SM100 support and NVIDIA "
                "artifactory cubins are available; native FlashInfer remains "
                "the source fallback"
            ),
            "consumer_contract": (
                "HND BF16 cache, full block table, absolute seq_lens, and "
                "window_left=1023"
            ),
        },
        "correctness_oracle": {
            "path": "local_window_kv_oracle.py",
            "sha256": sha256(ROOT / "local_window_kv_oracle.py"),
            "result": oracle,
            "interpretation": (
                "Slicing at floor((seq_len-1024)/16) and subtracting the same "
                "whole-page offset from seq_len preserves every visible "
                "(physical_page_id, token_offset). Zero-length padded requests "
                "remain empty, and negative append slots remain unchanged."
            ),
        },
        "non_overlapping_launch_accounting": {
            "evidence_class": "exact_source_invocations_not_measured_internal_kernels",
            "baseline": {
                "append_op_submissions": local_calls,
                "attention_consumer_submissions": local_calls,
                "local_group_metadata_builds": group_steps,
                "trtllm_external_compaction_launches": 0,
                "native_flashinfer_page_index_copy_launches_if_fallback": group_steps,
            },
            "rejected_external_compaction_delta": {
                "append_op_submissions": 0,
                "attention_consumer_submissions": 0,
                "trtllm_compaction_launches": group_steps,
                "native_flashinfer_compaction_launches": 0,
            },
            "opaque_internal_kernel_launches": (
                "not claimed without CUDA execution; one Python consumer call "
                "is not asserted to equal one device kernel"
            ),
        },
        "non_overlapping_byte_accounting": {
            "mandatory_bf16_kv": {
                "local_attention_read_bytes": local_kv_read_bytes,
                "local_append_write_bytes": local_kv_write_bytes,
                "candidate_delta_read_bytes": 0,
                "candidate_delta_write_bytes": 0,
            },
            "page_id_metadata": {
                "full_table_addressable_references_five_groups_c32": (
                    full_group_page_refs
                ),
                "window_valid_references_five_groups_c32": window_group_page_refs,
                "native_page_list_copy_bytes_baseline": full_group_page_refs * 4,
                "native_page_list_copy_bytes_compacted": window_group_page_refs * 4,
                "native_page_list_copy_bytes_removed": (
                    full_group_page_refs - window_group_page_refs
                )
                * 4,
                "consumer_page_id_reference_upper_bound": {
                    "baseline": full_consumer_page_refs,
                    "compacted": window_consumer_page_refs,
                    "removed_references": page_ref_delta,
                    "removed_bytes_if_every_addressable_id_were_read": (
                        page_ref_delta * 4
                    ),
                    "upper_bound_fraction_of_mandatory_kv_reads": (
                        page_ref_delta * 4 / local_kv_read_bytes
                    ),
                    "warning": (
                        "The SM100 cubin already receives window_left and may "
                        "skip old page IDs internally; this is not a measured "
                        "or source-proven DRAM reduction."
                    ),
                },
                "rejected_trtllm_materialization_traffic_bytes": (
                    rejected_compaction_bytes
                ),
            },
            "exclusions": {
                "query_projection_bytes": "not counted",
                "global_attention_or_kv_bytes": "not counted",
                "prior_global_k_eq_v_bytes": "not counted",
                "M32_dispatch_or_RMSNorm_FP8_bytes": "not counted",
            },
        },
        "typed_rejection": {
            "mechanism": (
                "materialize a contiguous last-65-page table and rebase seq_lens "
                "before the unchanged local attention consumer"
            ),
            "code": "adds_recurring_launch_without_proven_consumer_work_removal",
            "semantic_status": "preserving_by_oracle",
            "physical_status": "rejected",
            "reasons": [
                (
                    "The unchanged consumer already receives window_left=1023, "
                    "so external truncation removes no mandatory score/KV work."
                ),
                (
                    "The SM100-preferred TRT-LLM path passes the block table "
                    "directly and requires a new contiguous materialization; "
                    "a column slice alone violates its strict-contiguity guard."
                ),
                (
                    "One compaction per five local groups per step adds 1,790 "
                    "launches and 30,229,760 explicit metadata bytes."
                ),
                (
                    "The most generous 481,292,800-byte page-ID upper bound is "
                    "only 0.0050083% of mandatory local KV reads and is not a "
                    "source-proven consumer DRAM reduction."
                ),
                (
                    "The native fallback can shrink its existing page-list copy "
                    "without another launch, but that does not establish an exact "
                    "SM100 production win and removes no attention or append call."
                ),
            ],
            "b200_component_recommendation": "do_not_reserve_for_this_mechanism",
        },
        "scope_compliance": {
            "gpu_claimed": False,
            "cuda_executed": False,
            "endpoint_requests": 0,
            "provider_operations": False,
            "provider_spend_usd": 0.0,
            "prior_contiguous_local_kv_candidate_replayed": False,
            "m32_dispatch_modified": False,
            "global_k_eq_v_patch_modified": False,
            "rmsnorm_fp8_fusion_modified": False,
        },
        "next_materially_distinct_boundary": {
            "name": "local_attention_kernel_internal_window_start",
            "requirement": (
                "Only reconsider page traversal with hash-bound FlashInfer "
                "TRT-LLM cubin/source evidence or target counters proving that "
                "old pages are actually traversed. Otherwise move to a distinct "
                "local-attention computation/fusion boundary."
            ),
        },
        "generator": {
            "path": "build_local_window_discriminator.py",
            "sha256": sha256(Path(__file__).resolve()),
        },
    }
    return artifact


def main() -> None:
    artifact = build()
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, OUTPUT)
    print(json.dumps({"output": str(OUTPUT), "sha256": sha256(OUTPUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
