#!/usr/bin/env python3

import argparse
import hashlib
import json
from decimal import Decimal, getcontext
from pathlib import Path


getcontext().prec = 28

PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = (
    PROJECT_DIR
    / "../gemma4_hybrid_attention_placement_codesign/inputs/bound/config.json"
).resolve()
TRACE_PATH = (
    PROJECT_DIR
    / "../gemma4_h200_ngram_fixed_m384_executor_rewrite/inputs/trace/exact_c32_profile.trace.json.gz"
).resolve()
EVIDENCE_PATH = PROJECT_DIR / "OFFICIAL_SOURCE_EVIDENCE.json"
OUTPUT_PATH = PROJECT_DIR / "TRAINIUM2_RUNTIME_PLACEMENT_SCREEN.json"

CONFIG_SHA256 = "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1"
TRACE_SHA256 = "37e2c73a57e8e63bd7ec0a3465cc1edded8b9dc63507d97e85a767306a97a48b"
MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
TARGET_USD_PER_MILLION = Decimal("0.109725")
PROMPT_TOKENS = Decimal("4214")
OUTPUT_TOKENS = Decimal("358")
TOTAL_TOKENS = PROMPT_TOKENS + OUTPUT_TOKENS
CACHE_READ_FRACTION = Decimal("0.127")
PLANNING_UTILIZATION = Decimal("0.90")
ALL_IN_SURCHARGE = Decimal("1.10")
SELECTED_INSTANCE_RATE = Decimal("32.32246")
SELECTED_REPLICAS = 16


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def exact(value: Decimal) -> float:
    return float(value)


def cost_per_million(
    service_seconds: Decimal,
    instance_rate: Decimal,
    replicas: int,
    utilization: Decimal,
    surcharge: Decimal,
) -> Decimal:
    per_replica_rate = instance_rate / Decimal(replicas)
    return (
        per_replica_rate
        * surcharge
        * service_seconds
        * Decimal(1_000_000)
        / (Decimal(3600) * TOTAL_TOKENS * utilization)
    )


def break_even_service_seconds(
    instance_rate: Decimal,
    replicas: int,
    utilization: Decimal,
    surcharge: Decimal,
) -> Decimal:
    per_replica_rate = instance_rate / Decimal(replicas)
    return (
        TARGET_USD_PER_MILLION
        * Decimal(3600)
        * TOTAL_TOKENS
        * utilization
        / (per_replica_rate * surcharge * Decimal(1_000_000))
    )


def source(evidence: dict, source_id: str) -> dict:
    for item in evidence["sources"]:
        if item["id"] == source_id:
            return item
    raise ValueError(f"missing source {source_id}")


def build_screen() -> dict:
    observed_config_sha = sha256(CONFIG_PATH)
    observed_trace_sha = sha256(TRACE_PATH)
    if observed_config_sha != CONFIG_SHA256:
        raise ValueError(f"config digest mismatch: {observed_config_sha}")
    if observed_trace_sha != TRACE_SHA256:
        raise ValueError(f"trace digest mismatch: {observed_trace_sha}")

    config = json.loads(CONFIG_PATH.read_text())
    evidence = json.loads(EVIDENCE_PATH.read_text())
    text = config["text_config"]
    layer_types = text["layer_types"]
    local_layers = layer_types.count("sliding_attention")
    global_layers = layer_types.count("full_attention")
    if (local_layers, global_layers) != (50, 10):
        raise ValueError(f"unexpected layer split: {(local_layers, global_layers)}")

    hidden = text["hidden_size"]
    intermediate = text["intermediate_size"]
    vocab = text["vocab_size"]
    local_head_dim = text["head_dim"]
    global_head_dim = text["global_head_dim"]
    q_heads = text["num_attention_heads"]
    local_kv_heads = text["num_key_value_heads"]
    global_kv_heads = text["num_global_key_value_heads"]

    embedding_params = vocab * hidden
    local_attention_params = hidden * (
        q_heads * local_head_dim
        + local_kv_heads * local_head_dim
        + local_kv_heads * local_head_dim
        + q_heads * local_head_dim
    )
    global_attention_params = hidden * (
        q_heads * global_head_dim
        + global_kv_heads * global_head_dim
        + q_heads * global_head_dim
    )
    mlp_params_per_layer = 3 * hidden * intermediate
    norm_params = (
        text["num_hidden_layers"] * 4 * hidden
        + hidden
        + 2 * (local_layers * local_head_dim + global_layers * global_head_dim)
    )
    analytical_text_params = (
        embedding_params
        + local_layers * local_attention_params
        + global_layers * global_attention_params
        + text["num_hidden_layers"] * mlp_params_per_layer
        + norm_params
    )
    transformer_params = analytical_text_params - embedding_params

    batch = 32
    total_context = int(PROMPT_TOKENS + OUTPUT_TOKENS)
    local_kv_elements = (
        local_layers
        * 2
        * local_kv_heads
        * local_head_dim
        * text["sliding_window"]
        * batch
    )
    global_kv_elements = (
        global_layers
        * 2
        * global_kv_heads
        * global_head_dim
        * total_context
        * batch
    )
    kv_elements = local_kv_elements + global_kv_elements
    gib = Decimal(2**30)
    fp8_weight_bf16_embedding_gib = Decimal(
        transformer_params + norm_params + 2 * embedding_params
    ) / gib
    bf16_weight_gib = Decimal(2 * analytical_text_params) / gib
    fp8_kv_gib = Decimal(kv_elements) / gib
    bf16_kv_gib = Decimal(2 * kv_elements) / gib
    duplicate_bf16_head_gib = Decimal(2 * embedding_params) / gib
    executable_runtime_reserve_gib = Decimal("10")

    selected_break_even = break_even_service_seconds(
        SELECTED_INSTANCE_RATE,
        SELECTED_REPLICAS,
        PLANNING_UTILIZATION,
        ALL_IN_SURCHARGE,
    )

    support_matrix = [
        {
            "requirement": "Gemma4ForConditionalGeneration registration and runnable model class",
            "status": "missing",
            "evidence": [
                "vllm_neuron_021_release",
                "nxdi_main_20260513",
            ],
            "detail": "Neither current vLLM-Neuron nor NxD Inference registers Gemma4.",
        },
        {
            "requirement": "60 dense layers at hidden 5,376 and intermediate 21,504",
            "status": "primitives_only",
            "evidence": [
                "nxdi_main_20260513",
                "huggingface_transformers_gemma4_reference",
            ],
            "detail": "Dense linear primitives exist, but no Gemma4 producer constructs or traces this exact stack.",
        },
        {
            "requirement": "Five 32Q/16KV head-dim-256 local layers then one 32Q/4KV head-dim-512 global layer",
            "status": "incompatible_stock_adapter",
            "evidence": [
                "nxdi_main_20260513",
                "huggingface_transformers_gemma4_reference",
            ],
            "detail": "The closest Gemma3 adapter carries one head_dim and one num_key_value_heads through all layers; it only removes the window every sixth layer.",
        },
        {
            "requirement": "Exact 1,024-token local cache plus full-length global cache with global K projection reused as V",
            "status": "incompatible_stock_adapter",
            "evidence": [
                "nxdi_main_20260513",
                "huggingface_transformers_gemma4_reference",
            ],
            "detail": "Generic per-layer cache-length support exists, but the Gemma3 producer does not implement Gemma4 per-layer head geometry or attention_k_eq_v.",
        },
        {
            "requirement": "FP8/cFP8 producer and linear consumers without hidden BF16 materialization",
            "status": "framework_only_unproven_for_gemma4",
            "evidence": [
                "vllm_neuron_021_release",
                "nxdi_main_20260513",
            ],
            "detail": "FP8 is advertised and kernels/configuration exist for supported models; there is no Gemma4 conversion, weight loader, compiled graph, or first-consumer proof.",
        },
        {
            "requirement": "FP8 KV cache for heterogeneous local/global shapes",
            "status": "framework_only_unproven_for_gemma4",
            "evidence": [
                "vllm_neuron_021_release",
                "nxdi_main_20260513",
            ],
            "detail": "The cache manager can store float8, but the available Gemma adapter does not construct the heterogeneous Gemma4 caches.",
        },
        {
            "requirement": "Tied 262,144 x 5,376 head",
            "status": "not_mechanically_tied_in_closest_adapter",
            "evidence": [
                "nxdi_main_20260513",
                "huggingface_transformers_gemma4_reference",
            ],
            "detail": "The reference ties lm_head.weight to the embedding; the Gemma3 Neuron adapter constructs a separate head and clones the embedding weight.",
        },
        {
            "requirement": "Final tanh logit softcap 30 and sampler",
            "status": "softcap_missing",
            "evidence": [
                "nxdi_main_20260513",
                "huggingface_transformers_gemma4_reference",
            ],
            "detail": "Sampling primitives exist, but no final_logit_softcapping consumer appears in the current Neuron model source.",
        },
        {
            "requirement": "c32 continuous batching, prefix-cache ownership, and compilation shapes",
            "status": "framework_only_unproven_for_gemma4",
            "evidence": [
                "vllm_neuron_021_release",
                "nxdi_main_20260513",
            ],
            "detail": "Continuous batching and prefix caching are framework features; chunked mixed prefill is unsupported, and no Gemma4 c32 compile or cache-ownership path exists.",
        },
    ]

    rate_sensitivities = []
    for name, rate in [
        ("3yr_ec2_instance_savings_all_upfront", Decimal("32.32246")),
        ("capacity_block_trn2_48xlarge", Decimal("35.7608")),
        ("3yr_compute_savings_all_upfront", Decimal("42.12236")),
        ("1yr_compute_savings_all_upfront", Decimal("63.18354")),
    ]:
        hurdle = break_even_service_seconds(
            rate, 16, PLANNING_UTILIZATION, ALL_IN_SURCHARGE
        )
        rate_sensitivities.append(
            {
                "rate_case": name,
                "instance_rate_usd_per_hour": exact(rate),
                "replicas": 16,
                "break_even_service_seconds_per_request": exact(hurdle),
                "required_total_tokens_per_second_per_replica": exact(
                    TOTAL_TOKENS / hurdle
                ),
            }
        )

    packing_sensitivities = []
    for replicas in [16, 8, 4]:
        hurdle = break_even_service_seconds(
            SELECTED_INSTANCE_RATE,
            replicas,
            PLANNING_UTILIZATION,
            ALL_IN_SURCHARGE,
        )
        packing_sensitivities.append(
            {
                "replicas_per_trn2_48xlarge": replicas,
                "chips_per_replica": 16 // replicas,
                "break_even_service_seconds_per_request": exact(hurdle),
                "required_total_tokens_per_second_per_replica": exact(
                    TOTAL_TOKENS / hurdle
                ),
            }
        )

    utilization_sensitivities = []
    for utilization in [Decimal("0.70"), Decimal("0.80"), Decimal("0.90")]:
        hurdle = break_even_service_seconds(
            SELECTED_INSTANCE_RATE,
            SELECTED_REPLICAS,
            utilization,
            ALL_IN_SURCHARGE,
        )
        utilization_sensitivities.append(
            {
                "planning_utilization": exact(utilization),
                "break_even_service_seconds_per_request": exact(hurdle),
            }
        )

    cache_sensitivities = []
    for fraction in [Decimal("0"), CACHE_READ_FRACTION, Decimal("0.25")]:
        cache_sensitivities.append(
            {
                "cache_read_fraction": exact(fraction),
                "fresh_prompt_tokens_per_request": exact(
                    PROMPT_TOKENS * (Decimal(1) - fraction)
                ),
                "cache_read_tokens_per_request": exact(PROMPT_TOKENS * fraction),
                "charged_total_tokens_per_request": exact(TOTAL_TOKENS),
                "service_time_effect": None,
                "reason": "No exact Gemma4 Neuron prefix-cache measurement exists.",
            }
        )

    hypothetical_costs = []
    for service_seconds in [
        Decimal("0.5"),
        Decimal("0.625149101968745"),
        Decimal("0.75"),
        Decimal("1.0"),
    ]:
        hypothetical_costs.append(
            {
                "service_seconds_per_request": exact(service_seconds),
                "usd_per_million_total_tokens": exact(
                    cost_per_million(
                        service_seconds,
                        SELECTED_INSTANCE_RATE,
                        SELECTED_REPLICAS,
                        PLANNING_UTILIZATION,
                        ALL_IN_SURCHARGE,
                    )
                ),
                "evidence_label": "derived_hypothetical_not_execution_evidence",
            }
        )

    screen = {
        "schema_version": 1,
        "generated_at_utc": evidence["retrieved_at_utc"],
        "classification": "typed_none",
        "typed_none": {
            "type": "current_runtime_source_incomplete",
            "primary_boundary": "No current official Neuron model class reaches exact Gemma4 heterogeneous attention, attention_k_eq_v, tied-head softcap, FP8/cFP8, cache, and sampler consumers.",
            "secondary_boundary": "Without that producer/consumer path there is no exact-model compile or scope-matched service-time prior, so a conservative all-in cost cannot be asserted below the target.",
            "not_a_hardware_claim": True,
            "reopen_condition": "A later official Neuron release or source-complete custom adapter must compile exact revision geometry and measure the bound c32 workload on Trn2.",
        },
        "bound_model": {
            "model_id": "google/gemma-4-31B-it",
            "revision": MODEL_REVISION,
            "config_path": str(CONFIG_PATH),
            "config_sha256": observed_config_sha,
            "architecture": config["architectures"][0],
            "text_geometry": {
                "layers": text["num_hidden_layers"],
                "local_layers": local_layers,
                "global_layers": global_layers,
                "hidden_size": hidden,
                "intermediate_size": intermediate,
                "q_heads": q_heads,
                "local_kv_heads": local_kv_heads,
                "global_kv_heads": global_kv_heads,
                "local_head_dim": local_head_dim,
                "global_head_dim": global_head_dim,
                "sliding_window": text["sliding_window"],
                "attention_k_eq_v": text["attention_k_eq_v"],
                "vocab_size": vocab,
                "tie_word_embeddings": text["tie_word_embeddings"],
                "final_logit_softcapping": text["final_logit_softcapping"],
            },
            "analytical_text_parameter_accounting": {
                "embedding_parameters_tied_once": embedding_params,
                "local_attention_parameters_per_layer": local_attention_params,
                "global_attention_parameters_per_layer": global_attention_params,
                "global_value_projection_parameters": 0,
                "mlp_parameters_per_layer": mlp_params_per_layer,
                "norm_parameters": norm_params,
                "total_text_parameters": analytical_text_params,
                "evidence_label": "derived_from_bound_config_and_reference_source",
                "exclusions": [
                    "Vision tower and any unused multimodal state.",
                    "Executable/compiler state and allocator overhead.",
                ],
            },
        },
        "bound_workload": {
            "trace_path": str(TRACE_PATH),
            "trace_sha256": observed_trace_sha,
            "background_concurrency": batch,
            "prompt_tokens_per_request": exact(PROMPT_TOKENS),
            "output_tokens_per_request": exact(OUTPUT_TOKENS),
            "total_tokens_per_request": exact(TOTAL_TOKENS),
            "cache_read_fraction": exact(CACHE_READ_FRACTION),
            "fresh_prompt_tokens_per_request": exact(
                PROMPT_TOKENS * (Decimal(1) - CACHE_READ_FRACTION)
            ),
            "cache_read_tokens_per_request": exact(
                PROMPT_TOKENS * CACHE_READ_FRACTION
            ),
            "planning_utilization": exact(PLANNING_UTILIZATION),
            "locked_qualified_service_seconds_per_request": 0.625149101968745,
            "locked_service_target_seconds_per_request_on_h200_basis": 0.500119281574996,
            "locked_target_usd_per_million_total_tokens": exact(
                TARGET_USD_PER_MILLION
            ),
        },
        "source_identities": {
            "evidence_manifest": str(EVIDENCE_PATH),
            "evidence_manifest_sha256": sha256(EVIDENCE_PATH),
            "vllm_neuron": {
                "commit": source(evidence, "vllm_neuron_021_release")["commit"],
                "tag": source(evidence, "vllm_neuron_021_release")["tag"],
            },
            "nxdi": {
                "commit": source(evidence, "nxdi_main_20260513")["commit"],
            },
            "transformers_gemma4_reference": {
                "commit": source(
                    evidence, "huggingface_transformers_gemma4_reference"
                )["commit"],
            },
            "neuron_sdk": "2.31",
            "official_source_ids": [
                item["id"] for item in evidence["sources"]
            ],
        },
        "runtime_producer_consumer_support_matrix": support_matrix,
        "adapter": {
            "implemented": False,
            "source_hashes": [],
            "reason": "A credible adapter must implement multiple model semantics and cross the proprietary Neuron compile/runtime boundary. An uncompiled registration shim would violate the source-complete gate.",
            "missing_components": [
                "Gemma4 per-layer configuration and registry integration.",
                "Heterogeneous GQA QKV and output projections.",
                "attention_k_eq_v global producer and transformed K/V consumers.",
                "Heterogeneous local/global KV cache allocation and ownership.",
                "Gemma4 weight conversion with mechanically tied head.",
                "Final logit softcap and sampler integration.",
                "FP8/cFP8 conversion and first-consumer proof without BF16 materialization.",
            ],
        },
        "hardware_and_placement": {
            "hardware": "AWS Trainium2",
            "physical_neuroncores_per_chip": 8,
            "logical_neuroncore_config": 2,
            "logical_neuroncores_per_chip": 4,
            "hbm_gib_per_logical_neuroncore": 24,
            "hbm_gib_per_chip": 96,
            "minimum_provisional_tp_degree": 4,
            "minimum_provisional_chips_per_replica": 1,
            "reason": "TP4 is the smallest supported LNC2 geometry with 96 GiB aggregate HBM and divides 32Q, 16 local KV, and 4 global KV heads.",
            "minimum_purchasable_topologies": [
                {
                    "instance_type": "trn2.3xlarge",
                    "chips": 1,
                    "provisional_replicas": 1,
                    "current_purchase_evidence": "Capacity Blocks in Melbourne and Sao Paulo only; no matching Savings Plan rate was found."
                },
                {
                    "instance_type": "trn2.48xlarge",
                    "chips": 16,
                    "provisional_max_replicas": 16,
                    "current_purchase_evidence": "Capacity Block and US East (Ohio) Savings Plan rates are published."
                }
            ],
            "replica_packing_classification": "mechanically_plausible_not_compiler_admitted",
            "failure_boundaries": [
                "A trn2.48xlarge host failure removes all sixteen provisional replicas.",
                "The 90% utilization cap and 4% reload/failure surcharge are charged; no unpriced fractional chip is credited.",
                "A BF16-weight plus BF16-KV fallback exceeds one-chip HBM after the explicit runtime reserve and halves provisional packing to eight replicas."
            ],
        },
        "hbm_and_state_accounting": {
            "batch": batch,
            "local_cache_tokens_per_sequence": text["sliding_window"],
            "global_cache_tokens_per_sequence": total_context,
            "local_kv_elements": local_kv_elements,
            "global_kv_elements": global_kv_elements,
            "total_kv_elements": kv_elements,
            "fp8_dense_linears_plus_bf16_tied_embedding_gib": exact(
                fp8_weight_bf16_embedding_gib
            ),
            "bf16_weights_gib": exact(bf16_weight_gib),
            "fp8_kv_gib": exact(fp8_kv_gib),
            "bf16_kv_gib": exact(bf16_kv_gib),
            "closest_adapter_duplicate_bf16_head_additional_gib": exact(
                duplicate_bf16_head_gib
            ),
            "executable_runtime_reserve_gib": exact(
                executable_runtime_reserve_gib
            ),
            "reserve_evidence_label": "inferred_conservative_placeholder",
            "precision_cases": [
                {
                    "weights": "FP8 linears plus BF16 tied embedding",
                    "kv": "cFP8",
                    "total_with_reserve_gib": exact(
                        fp8_weight_bf16_embedding_gib
                        + fp8_kv_gib
                        + executable_runtime_reserve_gib
                    ),
                    "fits_one_96_gib_chip_analytically": True,
                },
                {
                    "weights": "BF16",
                    "kv": "cFP8",
                    "total_with_reserve_gib": exact(
                        bf16_weight_gib
                        + fp8_kv_gib
                        + executable_runtime_reserve_gib
                    ),
                    "fits_one_96_gib_chip_analytically": True,
                },
                {
                    "weights": "FP8 linears plus BF16 tied embedding",
                    "kv": "BF16",
                    "total_with_reserve_gib": exact(
                        fp8_weight_bf16_embedding_gib
                        + bf16_kv_gib
                        + executable_runtime_reserve_gib
                    ),
                    "fits_one_96_gib_chip_analytically": True,
                },
                {
                    "weights": "BF16",
                    "kv": "BF16",
                    "total_with_reserve_gib": exact(
                        bf16_weight_gib
                        + bf16_kv_gib
                        + executable_runtime_reserve_gib
                    ),
                    "fits_one_96_gib_chip_analytically": False,
                    "minimum_provisional_chips": 2,
                },
            ],
            "not_included": [
                "Vision tower or other multimodal resident state.",
                "Measured NEFF executable size.",
                "Allocator fragmentation measured on target hardware.",
            ],
        },
        "pricing_and_all_in_economics": {
            "ordinary_ondemand_rate_usd_per_hour": None,
            "ordinary_ondemand_rate_status": "not_published_in_current_official_us_east_2_bulk_offer",
            "selected_production_planning_rate": {
                "instance_type": "trn2.48xlarge",
                "region": "US East (Ohio)",
                "plan": "3 year EC2 Instance Savings Plan, All Upfront",
                "instance_rate_usd_per_hour": exact(SELECTED_INSTANCE_RATE),
                "provisional_replicas": SELECTED_REPLICAS,
                "rate_per_provisional_replica_usd_per_hour": exact(
                    SELECTED_INSTANCE_RATE / Decimal(SELECTED_REPLICAS)
                ),
                "source_id": "aws_compute_savings_plan_index_20260723171525",
            },
            "all_in_surcharge": {
                "multiplier": exact(ALL_IN_SURCHARGE),
                "orchestration_and_host_services_fraction": 0.04,
                "compiled_artifact_storage_and_reload_fraction": 0.02,
                "failure_reload_and_capacity_fragmentation_fraction": 0.04,
                "network_egress": "Not separately material for token text payloads; fail closed if multimodal or cross-AZ traffic is required.",
                "evidence_label": "inferred_conservative_accounting",
            },
            "planning_utilization": exact(PLANNING_UTILIZATION),
            "break_even_service_seconds_per_request": exact(selected_break_even),
            "required_total_tokens_per_second_per_replica": exact(
                TOTAL_TOKENS / selected_break_even
            ),
            "conservative_service_seconds_per_request": None,
            "conservative_usd_per_million_total_tokens": None,
            "why_cost_is_null": "No exact Gemma4 Neuron runtime producer/consumer or scope-matched service prior exists.",
            "hypothetical_cost_rows": hypothetical_costs,
            "vendor_execution_prior_excluded_from_cost": {
                "source_id": "aws_neuron_llama33_70b_trn2_prior",
                "scope_transfer_allowed": False,
            },
        },
        "sensitivities": {
            "rate": rate_sensitivities,
            "replica_packing": packing_sensitivities,
            "utilization": utilization_sensitivities,
            "cache": cache_sensitivities,
            "precision_fallback": [
                {
                    "case": "BF16 weights and BF16 KV",
                    "effect": "Analytical one-chip HBM failure; at most eight replicas per trn2.48xlarge and a 0.3657208467 s/request break-even hurdle.",
                },
                {
                    "case": "Closest Gemma3 adapter clones tied head",
                    "effect": f"Adds {exact(duplicate_bf16_head_gib):.6f} GiB per replica and violates the exact tied-head mechanism.",
                },
                {
                    "case": "FP8/cFP8 framework claim without Gemma4 consumer",
                    "effect": "Cannot be credited as capacity or performance until compile and first-consumer evidence exists.",
                },
            ],
            "compilation_shapes": [
                "The bound path needs c32 prompt-heavy continuous batching and 1,024-token local/full-global cache shapes.",
                "Current vLLM-Neuron reports chunked mixed prefill unsupported.",
                "Compile buckets, executable state, and dynamic request padding are unmeasured for Gemma4 and may reduce packing or throughput.",
            ],
        },
        "evidence_labels": {
            "measured": [
                "Bound file digests.",
                "Official repository revisions and source-file digests.",
                "Official public price-list retrieval, byte count, and absent On-Demand SKU match.",
            ],
            "vendor_reported": [
                "Trainium2 hardware specifications and peaks.",
                "Llama-3.3-70B Trn2 tutorial performance prior, excluded from transfer.",
            ],
            "derived": [
                "Exact text parameter count.",
                "Exact workload KV element count.",
                "HBM arithmetic and economic break-even hurdles.",
            ],
            "inferred": [
                "10 GiB executable/runtime reserve.",
                "10% all-in surcharge allocation.",
                "Provisional one-chip TP4 placement and sixteen-replica packing.",
            ],
            "measured_target_hardware": [],
        },
        "remaining_gates": {
            "compile": "Open: exact Gemma4 source must compile through Neuron 2.31+.",
            "target_hardware": "Open: no Trn2 invocation was authorized or run.",
            "performance": "Open: exact c32 service time must be <= the applicable break-even hurdle.",
            "precision": "Open: FP8/cFP8 producer and first consumers must prove no hidden BF16 materialization.",
            "cache": "Open: heterogeneous local/global cache ownership, prefix reuse, and c32 padding must execute correctly.",
            "quality": "Open: exact revision outputs and campaign quality gates are unrun.",
            "production_availability": "Open: ordinary On-Demand rate is not public in the current bulk offer; Savings Plan and Capacity Block availability do not guarantee capacity.",
        },
        "resource_use": {
            "actual_spend_usd": 0.0,
            "authorized_spend_usd": 0.0,
            "gpu_or_neuron_bench_claimed": False,
            "provider_resources_created": False,
            "provider_contacted": False,
            "checkpoint_downloaded": False,
        },
    }
    return screen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    screen = build_screen()
    rendered = json.dumps(screen, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not OUTPUT_PATH.exists():
            raise SystemExit(f"missing {OUTPUT_PATH}")
        if OUTPUT_PATH.read_text() != rendered:
            raise SystemExit(f"{OUTPUT_PATH} is stale; rerun without --check")
        print(f"verified {OUTPUT_PATH}")
        return
    OUTPUT_PATH.write_text(rendered)
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
