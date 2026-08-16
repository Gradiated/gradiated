#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
PROJECTS = PROJECT.parent
LAB = PROJECTS.parent
WORKSPACE = Path("/root/workspace")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path: Path, *, label: str = "direct") -> dict:
    return {
        "path": str(path.relative_to(PROJECT) if path.is_relative_to(PROJECT) else path),
        "sha256": sha256(path),
        "evidence": label,
    }


def main() -> int:
    numerical_path = PROJECT / "artifacts/OFFLINE_NUMERICAL_FINAL.json"
    numerical = json.loads(numerical_path.read_text())
    implementation_names = [
        "local_kv4_outlier_reference.py",
        "local_kv4_outlier_cuda.cu",
        "local_kv4_outlier_bindings.cpp",
        "sglang_local_kv4_outlier.py",
        "run_l40s_component.py",
        "offline_experiment.py",
        "test_local_kv4_outlier.py",
        "build_terminal.py",
    ]
    source_names = [
        "attention_backend_setup.py",
        "decode_attention.py",
        "extend_attention.py",
        "fp4_kv_cache_quant_method.py",
        "kv_cache_builder.py",
        "kv_cache_configurator.py",
        "kv_pool_runtime.py",
        "memory_pool.py",
        "swa_memory_pool.py",
        "triton_backend.py",
    ]
    workload_root = (
        PROJECTS
        / "gemma4_prefill_cuda_graph_padding_rebase/inputs/workload"
    )
    predecessor = (
        PROJECTS
        / "gemma4_l40s_current_runtime_fp8_endpoint_rebase/L40S_CURRENT_RUNTIME_FP8_REBASE_OFFLINE_TERMINAL.json"
    )
    closed_h200 = (
        PROJECTS
        / "gemma4_h200_local_kv_int4_endpoint/artifacts/local-int4-component-20260723t1337z/repair1/retrieved/COMPONENT_TERMINAL.json"
    )
    expired_l40s = (
        PROJECTS
        / "gemma4_l40s_qserve_kv4_attention_component/artifacts/kv4-l40s-resident-retrieve-20260724t0722z/retrieved/ERROR_TERMINAL.json"
    )
    terminal = {
        "schema_version": 1,
        "kind": "l40s_local_kv4_outlier_offline_terminal",
        "project": PROJECT.name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": "none",
        "pass": False,
        "classification": "typed_none_complete_memory_fit",
        "actual_spend_usd": 0.0,
        "scope": {
            "mode": "offline_only",
            "gpu_pool_claimed": False,
            "ssh_used": False,
            "provider_or_endpoint_used": False,
            "cuda_invoked": False,
            "checkpoint_shards_read_or_copied": False,
            "representation_parameters_changed": False,
            "closed_h200_kernel_ported_or_replayed": False,
            "expired_l40s_packet_replayed": False,
        },
        "identities": {
            "runtime": {
                "repository": "https://github.com/sgl-project/sglang",
                "commit": "c6a6200a1a778a799ba61c395ac292317f01ebc9",
                "attention_backend": "Triton current-runtime seam with custom CUDA SM89 local consumer",
            },
            "model": {
                "id": "google/gemma-4-31B-it",
                "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "local_layers": 50,
                "global_layers": 10,
            },
            "hardware": {
                "model": "NVIDIA L40S",
                "architecture": "Ada Lovelace SM89",
                "sms": 142,
                "l2_mb": 96,
                "memory_bandwidth_gb_s_vendor": 864.0,
                "measured_exposed_mib": 46068,
                "measured_exposed_bytes": 48305799168,
            },
            "workload": {
                "concurrency": 32,
                "prompt_tokens_per_request": 4214,
                "output_tokens_per_request": 358,
                "shared_prefix_tokens": 535,
                "fresh_tokens_per_request": 3679,
                "tp": 1,
                "page_size": 1,
                "local_window": 1024,
            },
        },
        "direct_bindings": {
            "project": binding(PROJECT / "PROJECT.md"),
            "predecessor_memory_terminal": binding(predecessor),
            "closed_h200_no_sidecar_terminal": binding(closed_h200),
            "expired_l40s_pre_science_diagnostic": binding(expired_l40s),
            "campaign": binding(LAB / "CAMPAIGN.md"),
            "model_config": binding(workload_root / "MODEL_CONFIG.json"),
            "workload": binding(workload_root / "WORKLOAD.json"),
            "launch": binding(workload_root / "LAUNCH.json"),
            "qualified_terminal": binding(workload_root / "QUALIFIED_TERMINAL.json"),
            "accelerator_inventory": binding(
                WORKSPACE / "research/factory/data/accelerator_inventory.json"
            ),
            "gpu_prices": binding(
                WORKSPACE / "research/factory/data/gpu_prices.json"
            ),
            "checkpoint_index_metadata": {
                "sha256": "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2",
                "total_tensor_bytes": 62546177752,
                "evidence": "inherited from direct-hashed CHECKPOINT_TERMINAL; no shard or index bytes read this turn",
            },
        },
        "selected_runtime_source_hashes": {
            name: sha256(PROJECT / "inputs/sglang" / name) for name in source_names
        },
        "implementation": {
            "state": "source_complete_unexecuted",
            "hashes": {
                name: sha256(PROJECT / name) for name in implementation_names
            },
            "numerical_artifact": binding(numerical_path),
            "producer": {
                "input": "finite BF16 [tokens,16,256] K or V after the unchanged QK-norm/RoPE boundary",
                "grid": "one 256-thread CTA per token and KV head vector",
                "negative_slot": "return before reading source K/V or writing cache",
                "output": "one contiguous uint8[144] row at [physical_slot,kv_head]",
            },
            "consumer": {
                "symbol": "local_kv4_outlier_paged_attention / paged_attention_kernel",
                "input": "BF16 flattened q, current-runtime qo_indptr/window_kv_indptr/window_kv_indices, and packed K/V rows",
                "output": "unchanged BF16 attention output [queries,32,256]",
                "fusion": "unpacks base and applies four residual corrections at each K/V load inside one online-softmax pass; no dequantized cache or output intermediate",
                "online_softmax": "FP32 running maximum, sum, and per-channel accumulator with prior-state rescaling",
            },
            "runtime_adapter": {
                "quant_method": "LocalKV4OutlierKVCacheMethod owns only SWAKVPool.swa_kv_pool",
                "global_isolation": "SWAKVPool.full_kv_pool remains the selected unquantized E5M2 method; global backend calls are untouched",
                "dispatch": "is_local_kv4_layer gates only mapped SWA layers; raw_local_buffers rejects global layers",
            },
            "execution_status": "CPU oracle and static source contracts passed; CUDA compile, registers, spills, timing, and runtime dispatch are unmeasured by explicit project prohibition",
        },
        "representation_contract": {
            "scope": "local K and V only; 50 layers, 16 KV heads, D256",
            "bytes_per_k_or_v_vector": 144,
            "layout": {
                "0:128": "128 packed bytes; even channel in low nibble, odd channel in high nibble; signed two's-complement INT4 with -8 unused",
                "128:136": "four little-endian BF16 scales, group order 0..3",
                "136:140": "four uint8 channel indices in residual-rank order",
                "140:144": "four E5M2 residual bytes in matching rank order",
            },
            "quantization": {
                "source_rounding": "producer consumes the existing finite BF16 K/V value",
                "groups": "four contiguous groups of 64 channels",
                "scale": "BF16 round-to-nearest-even(second-largest absolute group value / 7); zero group stores scale 0",
                "base_code": "round-to-nearest-even(x/scale), clipped to symmetric [-7,7]",
                "residual": "BF16 source minus FP32(BF16 scale)*signed code",
                "selection": "global top four by descending absolute residual, lowest channel wins ties",
                "residual_dtype": "finite E5M2 round-to-nearest-even, satfinite at +/-57344",
                "zero_vector": "all codes/scales/residual bytes zero; deterministic sidecar indices 0,1,2,3",
                "nonfinite": "producer rejects nonfinite K/V; no nonfinite payload is admitted",
            },
            "ownership": {
                "page_size": 1,
                "slot_address": "runtime physical slot indexes the leading cache dimension directly",
                "request_isolation": "window_kv_indptr partitions window_kv_indices by request; consumer never derives or crosses ownership",
                "gqa": "query head // 2 selects one of 16 KV heads",
                "causal_extend": "visible KV stop is prefix length plus current ragged query offset plus one",
                "window": "selected runtime supplies prefiltered 1024-token window indices; consumer rejects any window value other than 1024",
                "graph_padding": "negative producer or consumer slot is a no-op",
                "transition_reuse": "prefill-produced rows remain in the same SWA physical slots and are read directly at first and later decode",
            },
            "unchanged": [
                "10 global layers and their D512 E5M2 K/V pools",
                "all transformer weights and dynamic-FP8/E4M3 linear path",
                "full-attention consumer",
                "logits, sampler, tokenizer, request workload, output contract",
            ],
        },
        "shape_contract": {
            "prefill": {
                "logical_q": "[32,4214,32,256] flattened into current dynamic chunks",
                "source_kv": "[T,16,256] per active chunk",
                "chunked_prefill_size": 2048,
                "max_prefill_tokens": 16384,
                "packed_local_pool_per_layer": "[32769,16,144] K and V including page-one padding",
                "output": "[T,32,256]",
            },
            "decode": {
                "q": "[32,32,256]",
                "kv_indices": "32 ragged rows of exactly 1024 local slots at steady state",
                "packed_local_pool_per_layer": "[32769,16,144] K and V",
                "output": "[32,32,256]",
                "grid": "1024 CTAs; 7.2113 one-CTA-per-SM waves over 142 SMs before occupancy",
            },
            "global_unchanged": {
                "q_heads": 32,
                "kv_heads": 4,
                "head_dim": 512,
                "pool_tokens_lower_bound": 129687,
                "dtype": "E5M2",
            },
        },
        "numerical": {
            "evidence_label": numerical["evidence_label"],
            "vector_fixture": numerical["vector"],
            "exact_d256_window1024_decode": numerical["exact_decode"],
            "focused_boundaries": numerical["boundaries"],
            "comparison_to_closed_h200": {
                "closed_no_sidecar_relative_l2": 0.10750669240951538,
                "candidate_synthetic_complete_output_relative_l2": numerical[
                    "exact_decode"
                ]["residual_corrected_attention_output"]["relative_l2"],
                "interpretation": "corrected synthetic complete-output error is 47.7% lower than the closed no-sidecar measured figure, but cross-hardware/data transfer is not claimed; target runtime validation would still be required",
            },
            "iterations": [
                {
                    "artifact": "artifacts/OFFLINE_NUMERICAL.json",
                    "sha256": sha256(PROJECT / "artifacts/OFFLINE_NUMERICAL.json"),
                    "mechanism": "max/7 group scale",
                    "result": "valid numerical negative: complete-output relative L2 0.143934; sidecar improved only 7.9%",
                },
                {
                    "artifact": "artifacts/OFFLINE_NUMERICAL_V2.json",
                    "sha256": sha256(PROJECT / "artifacts/OFFLINE_NUMERICAL_V2.json"),
                    "mechanism": "second-largest/7 robust group scale",
                    "result": "valid numerical positive: complete-output relative L2 0.056208; sidecar improved 92.1%",
                },
            ],
        },
        "memory": numerical["memory"],
        "physical_model": numerical["physical"],
        "whole_request_relevance": {
            "local_layers": 50,
            "local_pool_bytes_saved_vs_e5m2": 5872025600,
            "local_vector_payload_reduction_fraction": 0.4375,
            "decode_one_local_layer_c32_bytes_saved": 117440512,
            "conservative_service_time": {
                "lower_seconds_per_request": 0.0,
                "upper_seconds_per_request": "infinity",
                "reason": "no target compile or timing; byte reduction cannot be transferred to latency",
            },
            "placement": "rejected before performance because the unchanged static allocator contract cannot admit exact c32",
        },
        "focused_checks": [
            {
                "command": "python3 -m py_compile local_kv4_outlier_reference.py offline_experiment.py test_local_kv4_outlier.py sglang_local_kv4_outlier.py run_l40s_component.py build_terminal.py",
                "result": "pass",
            },
            {
                "command": ".venv/bin/python -m unittest -v test_local_kv4_outlier.py",
                "result": "pass",
                "tests": 6,
            },
            {
                "command": ".venv/bin/python offline_experiment.py --output artifacts/OFFLINE_NUMERICAL_FINAL.json",
                "result": "pass",
                "seed": 20260727,
            },
        ],
        "later_l40s_component": {
            "type": "none",
            "command": None,
            "reason": "PROJECT.md requires typed none when complete accounting cannot fit. The unchanged 0.85 static contract has a candidate-favorable 4,017,448,756-byte deficit before omitted checkpoint tensors and FP8 scales; a component cannot change that placement decision.",
            "runner_status": "run_l40s_component.py is retained as unexecuted implementation evidence, not as an authorized or recommended lifecycle command",
        },
        "uncertainty": [
            "Numerical evidence is deterministic synthetic BF16, not checkpoint-derived activation data.",
            "CUDA source was not compiled or executed; registers, spills, occupancy, latency, and actual counter movement are unmeasured.",
            "Scope-adjacent L40S context/graph telemetry is rounded and is contained inside the allocator reserve rather than used to prove source-matched allocation.",
            "Other checkpoint tensors and FP8 scales are interval-bounded; the fit negative uses their zero lower bounds.",
            "No endpoint or quality result exists; GPQA-Diamond, TauBench, tool calling, and model semantics remain untested.",
        ],
        "falsification_conditions": [
            "Any direct hash or frozen geometry mismatch invalidates the packet.",
            "Producer bytes differ from the BF16-scale/signed-nibble/E5M2 contract.",
            "SM89 candidate output fails the high-precision oracle, request isolation, transition, or graph-padding checks.",
            "Compiled resource use spills or target producer-plus-consumer latency does not beat actual E5M2.",
            "A director-authorized launch change removes the 0.85 static reserve without violating endpoint reliability; that would be a new representation-placement question, not this terminal.",
        ],
        "terminal_reasons": [
            "The fixed representation is numerically promising in the checkpoint-free oracle.",
            "The fixed representation removes exactly 5,872,025,600 local-cache bytes before page padding.",
            "Even its candidate-favorable static lower bound exceeds the unchanged 0.85 static allocation region by 4,017,448,756 bytes.",
            "No GPU, provider, endpoint, or later component is scientifically justified under this project's frozen placement contract.",
        ],
        "next_action": "Close this zero-GPU project as typed none. Do not request the pending campaign remainder or claim an L40S for this representation. A successor would require an explicit director-approved change to the endpoint memory-reserve contract or another independent resident-byte reduction.",
    }
    output = PROJECT / "L40S_LOCAL_KV4_OUTLIER_OFFLINE_TERMINAL.json"
    output.write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"path": str(output), "sha256": sha256(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
