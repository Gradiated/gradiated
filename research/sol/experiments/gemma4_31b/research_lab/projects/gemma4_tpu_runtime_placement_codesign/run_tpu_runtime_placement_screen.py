import argparse
import json
from pathlib import Path


TARGET_USD_PER_M_TOTAL_TOKENS = 0.109725
PROMPT_TOKENS = 4_214
OUTPUT_TOKENS = 358
CONCURRENCY = 32
CACHE_READ_FRACTION = 0.127
V6E_CHIPS = 8
V6E_USABLE_GIB_PER_CHIP = 31.25
PARAMETERS_TOTAL = 32_682_372_656
BF16_BYTES_PER_PARAMETER = 2
UTILIZATION = 0.90
RELIABILITY_CAPACITY_FACTOR = 1.10
FAILURE_RELOAD_FACTOR = 1.03
STORAGE_ORCHESTRATION_FACTOR = 1.02


def kv_cache_bytes(bytes_per_element):
    sequence_tokens = PROMPT_TOKENS + OUTPUT_TOKENS
    local = 50 * 2 * 16 * 256 * min(sequence_tokens, 1_024) * bytes_per_element
    global_attention = (
        10 * 2 * 4 * 512 * sequence_tokens * bytes_per_element
    )
    return {
        "local": local,
        "global": global_attention,
        "per_request": local + global_attention,
        "c32": (local + global_attention) * CONCURRENCY,
    }


def rate_scenario(chip_rate, reliability_factor=RELIABILITY_CAPACITY_FACTOR):
    raw_slice_rate = chip_rate * V6E_CHIPS
    all_in_hourly_rate = (
        raw_slice_rate
        * reliability_factor
        * FAILURE_RELOAD_FACTOR
        * STORAGE_ORCHESTRATION_FACTOR
        / UTILIZATION
    )
    tokens_per_request = PROMPT_TOKENS + OUTPUT_TOKENS
    max_service_seconds = (
        TARGET_USD_PER_M_TOTAL_TOKENS
        / 1_000_000
        * 3_600
        * CONCURRENCY
        * tokens_per_request
        / all_in_hourly_rate
    )
    required_requests_per_second = CONCURRENCY / max_service_seconds
    return {
        "chip_rate_usd_per_hour": chip_rate,
        "raw_v6e_8_rate_usd_per_hour": raw_slice_rate,
        "billable_utilization": UTILIZATION,
        "reliability_capacity_factor": reliability_factor,
        "failure_reload_factor": FAILURE_RELOAD_FACTOR,
        "storage_orchestration_factor": STORAGE_ORCHESTRATION_FACTOR,
        "effective_all_in_rate_usd_per_hour": all_in_hourly_rate,
        "max_service_seconds_at_c32": max_service_seconds,
        "required_requests_per_second": required_requests_per_second,
        "required_total_tokens_per_second": (
            required_requests_per_second * tokens_per_request
        ),
    }


def build_screen(observed_at_utc):
    bf16_kv = kv_cache_bytes(2)
    fp8_kv = kv_cache_bytes(1)
    exact_bf16_weight_upper_bound = PARAMETERS_TOTAL * BF16_BYTES_PER_PARAMETER
    one_year = rate_scenario(1.89)
    adjacent_output_tokens_per_second = 1_206
    adjacent_requests_per_second = adjacent_output_tokens_per_second / 512
    adjacent_total_tokens_per_second = adjacent_requests_per_second * (4_096 + 512)
    adjacent_cost = (
        one_year["effective_all_in_rate_usd_per_hour"]
        / (adjacent_total_tokens_per_second * 3_600)
        * 1_000_000
    )
    source_commit = "7bad4320f34af24e5049f9d87b1a89ab4bcf68cc"
    raw_root = (
        "https://raw.githubusercontent.com/vllm-project/tpu-inference/"
        f"{source_commit}/"
    )
    return {
        "schema_version": 1,
        "artifact": "TPU_RUNTIME_PLACEMENT_SCREEN",
        "observed_at_utc": observed_at_utc,
        "decision": "typed_none",
        "economic_target_usd_per_m_total_tokens": TARGET_USD_PER_M_TOTAL_TOKENS,
        "execution_contract": {
            "decision": (
                "Admit only a current, exact pinned-model TPU v6e producer and "
                "consumer with c32 4214/358 target-hardware evidence below the "
                "all-in economic target."
            ),
            "hypothesis": (
                "An official Google-native XLA placement on a purchasable v6e "
                "slice may provide enough exact-workload throughput per dollar."
            ),
            "scope": (
                "Public source and measurement inspection plus deterministic "
                "capacity and economic calculations; no checkpoint, TPU, paid "
                "API, provider mutation, or Google contact."
            ),
            "quality_gate": (
                "The model revision, 60-layer hybrid graph, KV/cache path, tied "
                "head, softcap, sampler, topology, rate, c32 workload, and "
                "target-v6e throughput must all be bound. Another checkpoint, "
                "runtime, workload, or accelerator cannot supply performance."
            ),
            "slo": "cost <= $0.109725/M total tokens after all material overhead",
            "budget": {
                "provider_api_usd": 0,
                "local_cpu_hours_max": 4,
                "new_storage_gib_max": 2,
                "wall_minutes_max": 90,
            },
            "artifact_contract": (
                "Emit source_bound_tpu_measurement_candidate or typed_none in "
                "TPU_RUNTIME_PLACEMENT_SCREEN.json."
            ),
        },
        "exact_model_binding": {
            "model": "google/gemma-4-31B-it",
            "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "config_sha256": (
                "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1"
            ),
            "hf_api_parameter_count": {
                "bf16": 31_273_088_876,
                "total": PARAMETERS_TOTAL,
            },
            "architecture": {
                "layers": 60,
                "layer_schedule": "five sliding_attention then one full_attention, repeated",
                "sliding_layers": 50,
                "full_attention_layers": 10,
                "hidden_size": 5_376,
                "intermediate_size": 21_504,
                "query_heads": 32,
                "local_kv_heads": 16,
                "local_head_dim": 256,
                "local_causal_horizon_tokens": 1_024,
                "global_kv_heads": 4,
                "global_head_dim": 512,
                "global_attention_k_equals_v": True,
                "kv_shared_layers": 0,
                "vocab_rows": 262_144,
                "tie_word_embeddings": True,
                "final_logit_softcap": 30.0,
                "local_rope_theta": 10_000.0,
                "global_rope_theta": 1_000_000.0,
                "global_partial_rotary_factor": 0.25,
            },
            "evidence_class": "source_bound",
        },
        "runtime_binding": {
            "project": "vllm-project/tpu-inference",
            "commit": source_commit,
            "backend": "JAX/Flax NNX lowered by XLA through vLLM TPU",
            "producer": {
                "module": "Gemma4ForConditionalGeneration",
                "path": "tpu_inference/models/jax/gemma4_mm.py",
                "sha256": (
                    "2ab723eac3d94f52c5a7ec444d00a54e160e172d6173c32307f1600907b34932"
                ),
                "function": (
                    "JaxAutoWeightsLoader consumes Hugging Face safetensors; "
                    "Gemma4Model produces hidden states and paged KV updates."
                ),
            },
            "decision_bearing_consumer": {
                "model_path": "tpu_inference/models/jax/gemma4.py",
                "model_path_sha256": (
                    "5b93b3b3dd5d42374c0115a4523661ed584191fb0cb9fc9639ae2248b3896fbd"
                ),
                "runner_path": "tpu_inference/runner/tpu_runner.py",
                "runner_path_sha256": (
                    "8d1e8d996e734212fe03244b4355d595f16b6aa6d8fa0da5686b3c84d12e2c66"
                ),
                "sampler_path": "tpu_inference/layers/jax/sample/sampling.py",
                "sampler_path_sha256": (
                    "ab39ca28ff2946c918f3d36e8d83b660653dbe7e3b4db4b94e4c7a561a91198a"
                ),
                "path": (
                    "hybrid paged attention -> final RMSNorm -> tied "
                    "embed_tokens.decode vocabulary head -> tanh softcap 30 -> "
                    "TPU greedy or categorical sampler"
                ),
            },
            "source_bound_capabilities": {
                "hybrid_local_global_schedule": True,
                "heterogeneous_head_dimensions": True,
                "local_sliding_cache": True,
                "global_k_equals_v": True,
                "kv_quantization": True,
                "tied_vocab_head": True,
                "final_softcap": True,
                "sampling": True,
            },
            "evidence_class": "source_bound",
        },
        "topology": {
            "accelerator": "Cloud TPU v6e Trillium",
            "slice": "v6e-8",
            "topology": "2x4",
            "machine_type": "ct6e-standard-8t",
            "chips": V6E_CHIPS,
            "hosts": 1,
            "vms": 1,
            "scope": "single-host, inference-optimized",
            "hbm_gib_per_chip_conservative": V6E_USABLE_GIB_PER_CHIP,
            "hbm_gib_total_conservative": V6E_USABLE_GIB_PER_CHIP * V6E_CHIPS,
            "official_smallest_source_bound_functional_slice": "v6e-8 TP8",
            "v6e_4_sensitivity": (
                "Nominal aggregate HBM can hold BF16 weights plus analytical "
                "c32 KV, and the daily FP8 recipe expresses TP4 replicas, but "
                "no current successful exact-workload v6e-4 result binds "
                "executable buffers or service capacity. It is not admitted."
            ),
            "evidence_class": "official_documentation_and_source_bound",
        },
        "capacity": {
            "exact_bf16_weight_upper_bound_bytes": exact_bf16_weight_upper_bound,
            "exact_bf16_weight_upper_bound_gib": (
                exact_bf16_weight_upper_bound / 2**30
            ),
            "bf16_kv_cache_bytes_per_request": bf16_kv["per_request"],
            "bf16_kv_cache_gib_per_request": bf16_kv["per_request"] / 2**30,
            "c32_bf16_kv_cache_bytes": bf16_kv["c32"],
            "c32_bf16_kv_cache_gib": bf16_kv["c32"] / 2**30,
            "c32_fp8_kv_cache_bytes": fp8_kv["c32"],
            "c32_fp8_kv_cache_gib": fp8_kv["c32"] / 2**30,
            "conservative_kv_accounting": (
                "All 50 local layers retain 1024 tokens and all 10 global "
                "layers retain 4572 tokens. K and V cache storage are both "
                "charged even though global projection weights satisfy K=V."
            ),
            "nominal_v6e_8_hbm_headroom_after_bf16_weights_and_c32_bf16_kv_gib": (
                V6E_USABLE_GIB_PER_CHIP * V6E_CHIPS
                - exact_bf16_weight_upper_bound / 2**30
                - bf16_kv["c32"] / 2**30
            ),
            "runtime_capacity_gate": "not_proven",
            "runtime_capacity_evidence": {
                "release_unit_and_correctness": (
                    "passing on v6e-8 TP8 with max-num-batched-tokens=4096 and "
                    "max-model-len=4096"
                ),
                "release_performance_benchmark": (
                    "skipped on v6e with literal result 'not enough HBM'"
                ),
                "target_request_tokens": PROMPT_TOKENS + OUTPUT_TOKENS,
                "target_concurrency": CONCURRENCY,
                "interpretation": (
                    "Static aggregate HBM arithmetic cannot override the "
                    "current runtime's executable and benchmark allocation."
                ),
            },
            "evidence_class": "derived_capacity_with_source_bound_runtime_limit",
        },
        "pricing": {
            "region": "us-east1",
            "currency": "USD",
            "billing_unit": "per v6e chip-hour",
            "rates": {
                "on_demand": 2.70,
                "dws_flex_start": 1.35,
                "dws_calendar_mode": 1.89,
                "one_year_commitment": 1.89,
                "three_year_commitment": 1.22,
            },
            "production_planning_basis": (
                "one-year commitment at $1.89/chip-hour, amortized only across "
                "a fully used 32+ core/chip fleet; four v6e-8 slices is the "
                "minimum fleet interpretation from the official usage table"
            ),
            "experiment_basis": (
                "on-demand $2.70/chip-hour; no experiment was run and actual spend is $0"
            ),
            "three_year_sensitivity": (
                "listed only as sensitivity because the official usage table "
                "positions three-year commitments for 512+ cores"
            ),
            "evidence_class": "current_official_rate",
        },
        "workload": {
            "concurrency": CONCURRENCY,
            "prompt_tokens": PROMPT_TOKENS,
            "fresh_input_tokens": PROMPT_TOKENS * (1 - CACHE_READ_FRACTION),
            "cache_read_tokens": PROMPT_TOKENS * CACHE_READ_FRACTION,
            "output_tokens": OUTPUT_TOKENS,
            "total_tokens_per_request": PROMPT_TOKENS + OUTPUT_TOKENS,
            "stage_cost_status": {
                "fresh_input": "unmeasured_on_target_tpu",
                "cache_read": "unmeasured_on_target_tpu",
                "output": "unmeasured_on_target_tpu",
                "blend": "unmeasured_on_target_tpu",
            },
        },
        "economics": {
            "overhead_model": {
                "billable_utilization": {
                    "value": UTILIZATION,
                    "class": "campaign_derived",
                },
                "reliability_capacity_factor": {
                    "value": RELIABILITY_CAPACITY_FACTOR,
                    "class": "conservative_inferred",
                },
                "failure_reload_factor": {
                    "value": FAILURE_RELOAD_FACTOR,
                    "class": "conservative_inferred",
                },
                "storage_orchestration_factor": {
                    "value": STORAGE_ORCHESTRATION_FACTOR,
                    "class": "conservative_inferred",
                },
            },
            "slice_rate_scenarios": {
                "on_demand": rate_scenario(2.70),
                "one_year_fleet_amortized": one_year,
                "one_year_minimum_fleet_plus_one_discrete_reserve": rate_scenario(
                    1.89, reliability_factor=1.25
                ),
                "three_year_large_fleet_sensitivity": rate_scenario(1.22),
            },
            "interpretation": (
                "The planning hurdle is 2.976630497 s/request at c32, "
                "10.750411 requests/s, or 49150.877 total tokens/s per active "
                "v6e-8 slice under the amortized one-year fleet case. No "
                "admissible exact target-TPU measurement supplies that rate."
            ),
        },
        "non_qualifying_adjacent_measurement": {
            "source": "arXiv:2605.25645v3 and h2loop/gemma-tpu",
            "hardware": "v6e-8 TP8",
            "runtime": "vLLM TPU 0.19.0 image",
            "checkpoint": (
                "Gemma 4 31B / merged LoRA lineage; exact pinned instruction "
                "revision is not bound"
            ),
            "workload": {
                "input_tokens": 4_096,
                "output_tokens": 512,
                "prompts": 30,
                "qps_sweep": "1 through 64",
            },
            "measured_peak_output_tokens_per_second": (
                adjacent_output_tokens_per_second
            ),
            "derived_requests_per_second": adjacent_requests_per_second,
            "derived_total_tokens_per_second_for_its_own_workload": (
                adjacent_total_tokens_per_second
            ),
            "planning_all_in_cost_usd_per_m_total_tokens": adjacent_cost,
            "multiple_of_target_cost": (
                adjacent_cost / TARGET_USD_PER_M_TOTAL_TOKENS
            ),
            "used_for_candidate": False,
            "reason_not_transferable": (
                "Different checkpoint identity, older runtime, different "
                "input/output geometry, no campaign cache split, and no c32 "
                "target trace. The paper also reports inconsistent prose/table "
                "labels for TPU KV dtype. This is sensitivity only."
            ),
            "evidence_class": "measured_adjacent_non_qualifying",
        },
        "official_runtime_discriminator": {
            "release_model_job_sha256": (
                "a2d3d69a7ccc892b60d6078da335e25a86ce80bba06fd6f2949a4c562ca5d1bd"
            ),
            "release_matrix_sha256": (
                "46937fe68507a7ab336544e25de1e27f21114c1cd4a94031683cfea7a0a9e356"
            ),
            "nightly_matrix_sha256": (
                "7c9cf4bc46f465437fa53bccce12077e095b4b94195de2cfcb1308b43a39cacf"
            ),
            "daily_fp8_recipe_sha256": (
                "1334d4a94cdd85ceca182937060b28c3b208c0ef22977b7a276da0b3aeb0c9f2"
            ),
            "result": (
                "Both release and nightly v6e/vLLM matrices mark Gemma 4 31B "
                "unit and correctness passing but benchmark 'not enough HBM'. "
                "The daily FP8 recipe defines v6e-8 DP2/TP4 at 1024/500 and "
                "does not publish a passing campaign-workload result."
            ),
        },
        "typed_none": {
            "code": "missing_scope_matched_target_tpu_performance_measurement",
            "first_decisive_gate": "performance",
            "detail": (
                "A real current exact Gemma 4 TPU producer/consumer and "
                "purchasable v6e-8 topology are source-bound, but the current "
                "official stable and nightly v6e matrices publish no "
                "performance result for Gemma 4 31B and explicitly record "
                "'not enough HBM'. Their passing correctness run stops at "
                "4096 tokens, below the 4572-token target request, and no "
                "public result binds the pinned revision, c32, 4214/358, "
                "12.7% cache split, complete service time, and all-in cost."
            ),
            "secondary_unresolved_gate": (
                "Executable/compiler-buffer and c32 KV capacity remain "
                "unmeasured despite favorable nominal aggregate HBM arithmetic."
            ),
            "candidate": None,
            "reopen_condition": (
                "One exact current v6e lifecycle must load revision "
                "b9ea41a2887d8607f594846523f94c6cc75ac8a4, execute the bound "
                "JAX/vLLM consumer at c32 with 4214/358 and cache accounting, "
                "and measure <=2.976630497 s/request under the amortized "
                "one-year case, with stage telemetry and reliability costs."
            ),
        },
        "sources": [
            {
                "id": "google_tpu_pricing",
                "url": "https://cloud.google.com/tpu/pricing",
                "claim": (
                    "Current per-chip-hour Trillium rates and one-/three-year "
                    "usage positioning."
                ),
                "retrieved_at_utc": observed_at_utc,
                "type": "official_documentation",
            },
            {
                "id": "google_tpu_v6e_topology",
                "url": "https://cloud.google.com/tpu/docs/v6e",
                "claim": (
                    "2x4 v6e-8 is an eight-chip, one-host, one-VM "
                    "inference-optimized supported configuration."
                ),
                "retrieved_at_utc": observed_at_utc,
                "type": "official_documentation",
            },
            {
                "id": "exact_hf_revision_metadata",
                "url": (
                    "https://huggingface.co/api/models/google/gemma-4-31B-it/"
                    "revision/b9ea41a2887d8607f594846523f94c6cc75ac8a4"
                ),
                "claim": "Exact revision, parameter metadata, and config identity.",
                "retrieved_at_utc": observed_at_utc,
                "type": "official_model_repository",
            },
            {
                "id": "tpu_inference_gemma4_model",
                "url": raw_root + "tpu_inference/models/jax/gemma4.py",
                "claim": "Exact hybrid text producer, KV/cache, tied head, and softcap.",
                "retrieved_at_utc": observed_at_utc,
                "type": "official_runtime_source",
            },
            {
                "id": "tpu_inference_gemma4_mm_loader",
                "url": raw_root + "tpu_inference/models/jax/gemma4_mm.py",
                "claim": "Actual Hugging Face weight loader and text model consumer.",
                "retrieved_at_utc": observed_at_utc,
                "type": "official_runtime_source",
            },
            {
                "id": "tpu_inference_sampler",
                "url": raw_root + "tpu_inference/layers/jax/sample/sampling.py",
                "claim": "TPU greedy and categorical sampling implementation.",
                "retrieved_at_utc": observed_at_utc,
                "type": "official_runtime_source",
            },
            {
                "id": "tpu_inference_model_ci",
                "url": raw_root + ".buildkite/models/google_gemma-4-31B-it.yml",
                "claim": (
                    "v6e-8 TP8 correctness invocation and explicit v6e "
                    "performance skip as not enough HBM."
                ),
                "retrieved_at_utc": observed_at_utc,
                "type": "official_runtime_ci",
            },
            {
                "id": "tpu_inference_release_matrix",
                "url": (
                    raw_root
                    + "support_matrices/release/v6e/vllm/model_support_matrix.csv"
                ),
                "claim": (
                    "Gemma 4 31B unit and correctness pass; performance not "
                    "enough HBM."
                ),
                "retrieved_at_utc": observed_at_utc,
                "type": "official_runtime_ci",
            },
            {
                "id": "adjacent_public_measurement",
                "url": "https://arxiv.org/html/2605.25645",
                "claim": (
                    "Measured but non-qualifying v6e-8 Gemma 4 31B adjacent "
                    "workloads and runtime."
                ),
                "retrieved_at_utc": observed_at_utc,
                "type": "measured_research_report",
            },
            {
                "id": "adjacent_measurement_artifacts",
                "url": (
                    "https://github.com/h2loop/gemma-tpu/tree/"
                    "a0dd038badde5293353d11c9f49bd7f3edd1e822/inference"
                ),
                "claim": "Associated inference setup, benchmark client, and raw summary.",
                "retrieved_at_utc": observed_at_utc,
                "type": "measured_research_artifact",
            },
        ],
        "actions_forbidden_and_not_taken": [
            "checkpoint_download",
            "hardware_claim",
            "paid_api",
            "provider_resource_creation",
            "google_contact",
        ],
        "actual_spend_usd": 0.0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--observed-at-utc", required=True)
    parser.add_argument(
        "--output", type=Path, default=Path("TPU_RUNTIME_PLACEMENT_SCREEN.json")
    )
    args = parser.parse_args()
    result = build_screen(args.observed_at_utc)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
