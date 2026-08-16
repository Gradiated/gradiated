#!/usr/bin/env python3
"""Build the zero-spend Gemma 4 31B Gaudi3 placement discriminator.

This program intentionally consumes only small, public metadata snapshots.
It does not download model weights, call paid APIs, or touch an accelerator.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any


getcontext().prec = 40

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "artifacts" / "evidence"
OUTPUT = ROOT / "GAUDI3_RUNTIME_PLACEMENT_SCREEN.json"

MODEL_ID = "google/gemma-4-31B-it"
MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
TARGET_USD_PER_M_TOTAL = Decimal("0.109725")
PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358
TOTAL_TOKENS = PROMPT_TOKENS + OUTPUT_TOKENS
CACHE_FRACTION = Decimal("0.127")
CONCURRENCY = 32

PROFILE = "gx3d-160x1792x8gaudi3"
HPUS_PER_NODE = 8
HPU_HBM_BYTES = Decimal(128_000_000_000)
TP = 2
REPLICAS = HPUS_PER_NODE // TP

VLLM_GAUDI_COMMIT = "ae952098bd0485a29d2b675065b89ad3c5b75674"
VLLM_COMMIT = "8def3cdde2a0acf0019447d8fcfc57e4df6bcfc2"


def read_json(name: str) -> Any:
    with (EVIDENCE / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def number(value: Decimal) -> float:
    return float(value)


def source(path: str, url: str, classification: str = "source_backed") -> dict[str, Any]:
    local = EVIDENCE / path
    return {
        "classification": classification,
        "url": url,
        "local_snapshot": f"artifacts/evidence/{path}",
        "sha256": sha256(local),
    }


def usd_price(metric: dict[str, Any]) -> Decimal:
    for amount in metric["amounts"]:
        if amount.get("country") == "USD" and amount.get("currency") == "USD":
            return Decimal(str(amount["prices"][0]["price"]))
    raise AssertionError(f"USD price missing for {metric['metric_id']}")


def metric(resource: dict[str, Any], metric_id: str) -> dict[str, Any]:
    found = [item for item in resource["metrics"] if item["metric_id"] == metric_id]
    if len(found) != 1:
        raise AssertionError(
            f"expected one {metric_id} metric in {resource['deployment_location']}"
        )
    return found[0]


def hurdle(rate: Decimal, extra_all_in_multiplier: Decimal) -> dict[str, Any]:
    # Cost/M = rate * seconds/request * 1e6 /
    #          (tokens/request * 3600 * utilization).
    at_100 = (
        TARGET_USD_PER_M_TOTAL
        * Decimal(TOTAL_TOKENS)
        * Decimal(3600)
        / (rate * Decimal(1_000_000))
    )
    at_90 = at_100 * Decimal("0.90")
    compute_only_under_all_in = at_90 / extra_all_in_multiplier
    return {
        "node_rate_usd_per_hour": number(rate),
        "target_usd_per_m_total_tokens": number(TARGET_USD_PER_M_TOTAL),
        "maximum_node_aggregate_service_seconds_per_request_at_100pct_utilization": number(
            at_100
        ),
        "maximum_node_aggregate_service_seconds_per_request_at_90pct_utilization": number(
            at_90
        ),
        "maximum_measured_compute_seconds_per_request_after_10pct_noncompute_reserve": number(
            compute_only_under_all_in
        ),
        "minimum_node_aggregate_requests_per_second_after_reserve": number(
            Decimal(1) / compute_only_under_all_in
        ),
        "minimum_node_aggregate_total_tokens_per_second_after_reserve": number(
            Decimal(TOTAL_TOKENS) / compute_only_under_all_in
        ),
        "maximum_per_tp2_replica_service_seconds_per_request_after_reserve": number(
            compute_only_under_all_in * Decimal(REPLICAS)
        ),
        "maximum_per_tp2_replica_c32_batch_seconds_after_reserve": number(
            compute_only_under_all_in * Decimal(REPLICAS) * Decimal(CONCURRENCY)
        ),
    }


def main() -> None:
    config = read_json("gemma4_31b_config.json")
    text = config["text_config"]
    model = read_json("hf_model_revision.json")
    index = read_json("model.safetensors.index.json")
    pull = read_json("pr1619.json")
    jobs = read_json("pr1619_success_jobs.json")["jobs"]
    catalog = read_json("ibm_globalcatalog_gaudi3_plan.json")
    pricing = read_json("ibm_globalcatalog_gaudi3_deployment_pricing.json")
    profile_html = (EVIDENCE / "ibm_gaudi3_profile.html").read_text(
        encoding="utf-8"
    )

    assert model["id"] == MODEL_ID
    assert model["sha"] == MODEL_REVISION
    assert config["architectures"] == ["Gemma4ForConditionalGeneration"]
    assert config["dtype"] == "bfloat16"
    assert text["num_hidden_layers"] == 60
    assert len(text["layer_types"]) == 60
    assert all(
        layer == ("full_attention" if (position + 1) % 6 == 0 else "sliding_attention")
        for position, layer in enumerate(text["layer_types"])
    )
    assert text["layer_types"].count("sliding_attention") == 50
    assert text["layer_types"].count("full_attention") == 10
    assert text["sliding_window"] == 1024
    assert text["num_attention_heads"] == 32
    assert text["head_dim"] == 256
    assert text["num_key_value_heads"] == 16
    assert text["global_head_dim"] == 512
    assert text["num_global_key_value_heads"] == 4
    assert text["attention_k_eq_v"] is True
    assert text["vocab_size"] == 262144
    assert text["tie_word_embeddings"] is True
    assert config["tie_word_embeddings"] is True
    assert text["final_logit_softcapping"] == 30.0

    assert pull["merge_commit_sha"] == VLLM_GAUDI_COMMIT
    exact_jobs = [
        job
        for job in jobs
        if job["name"] == "e2e (run_gsm8k_gemma4_31b_test)"
    ]
    assert len(exact_jobs) == 1
    exact_job = exact_jobs[0]
    assert exact_job["conclusion"] == "success"
    assert exact_job["runner_name"] == "aicf-gaudi2-14"

    assert catalog["id"] == "b029541d-cd56-42c5-a922-7288ed9b465f"
    assert catalog["active"] is True
    assert catalog["disabled"] is False
    assert catalog["kind"] == "plan"
    assert catalog["name"] == PROFILE
    assert PROFILE in profile_html
    assert "128 GB" in profile_html

    on_demand_id = f"part-is.instance-hours-{PROFILE}"
    spot_id = f"part-is.spot-{PROFILE}"
    regions: dict[str, dict[str, Any]] = {}
    for resource in pricing["resources"]:
        region = resource["deployment_location"]
        regions[region] = {
            "on_demand_usd_per_node_hour": number(
                usd_price(metric(resource, on_demand_id))
            ),
            "spot_usd_per_node_hour": number(usd_price(metric(resource, spot_id))),
            "effective_from": resource["effective_from"],
            "effective_until": resource["effective_until"],
            "billing_origin": resource["origin"],
        }
    cheapest_region = min(
        regions, key=lambda region: regions[region]["on_demand_usd_per_node_hour"]
    )
    planning_rate = Decimal(
        str(regions[cheapest_region]["on_demand_usd_per_node_hour"])
    )

    weight_bytes = int(index["metadata"]["total_size"])
    # KV bytes use BF16 K and V. Sliding layers retain the 1024-token horizon;
    # global layers retain the full prompt+decode request state.
    local_kv_bytes = (
        50
        * CONCURRENCY
        * 1024
        * text["num_key_value_heads"]
        * text["head_dim"]
        * 2
        * 2
    )
    global_kv_bytes = (
        10
        * CONCURRENCY
        * TOTAL_TOKENS
        * text["num_global_key_value_heads"]
        * text["global_head_dim"]
        * 2
        * 2
    )
    replica_kv_bytes = local_kv_bytes + global_kv_bytes
    raw_per_hpu_gib = (
        Decimal(weight_bytes + replica_kv_bytes) / Decimal(TP) / Decimal(2**30)
    )

    cached_prompt = Decimal(PROMPT_TOKENS) * CACHE_FRACTION
    fresh_prompt = Decimal(PROMPT_TOKENS) - cached_prompt
    blend = {
        "fresh_input": fresh_prompt,
        "cache_read": cached_prompt,
        "output": Decimal(OUTPUT_TOKENS),
    }
    phase_budget = {
        name: {
            "tokens_per_request": number(tokens),
            "fraction_of_total_tokens": number(tokens / Decimal(TOTAL_TOKENS)),
            "maximum_blended_contribution_usd_per_m_total_tokens": number(
                TARGET_USD_PER_M_TOTAL * tokens / Decimal(TOTAL_TOKENS)
            ),
            "target_gaudi3_measured_phase_seconds": None,
            "target_gaudi3_measured_phase_cost_usd_per_m_total_tokens": None,
        }
        for name, tokens in blend.items()
    }

    extra_all_in_multiplier = Decimal("1.10")
    selected_hurdle = hurdle(planning_rate, extra_all_in_multiplier)

    result = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": "typed_none",
        "reason_code": "missing_scope_matched_target_gaudi3_performance_measurement",
        "first_decisive_missing_gate": {
            "gate": "performance",
            "classification": "source_bound_negative",
            "finding": (
                "The exact Gemma 4 31B HPU producer/consumer has a passing TP2 "
                "correctness job on Gaudi2, but no public or in-scope result "
                "measures the bound c32 4214+358-token workload, its 12.7% cache "
                "read, or any conservative service-time bound on Gaudi3."
            ),
            "why_none": (
                "The project forbids transferring Gaudi2 correctness, another "
                "workload, or chip peaks into Gaudi3 throughput. Therefore actual "
                "cost per million tokens and the three phase costs remain null."
            ),
        },
        "model_binding": {
            "classification": "source_backed",
            "model_id": MODEL_ID,
            "revision": MODEL_REVISION,
            "text_only_non_reasoning": True,
            "checkpoint_downloaded": False,
            "public_metadata_only": True,
            "checkpoint_weight_bytes_from_index": weight_bytes,
            "checkpoint_weight_gib": number(Decimal(weight_bytes) / Decimal(2**30)),
            "parameters_from_index": index["metadata"]["total_parameters"],
            "geometry": {
                "layers": 60,
                "schedule": "5 sliding_attention then 1 full_attention, repeated 10x",
                "sliding_layers": 50,
                "global_layers": 10,
                "sliding_window_tokens": 1024,
                "query_heads": 32,
                "local_kv_heads": 16,
                "local_head_dim": 256,
                "global_kv_heads": 4,
                "global_head_dim": 512,
                "attention_k_eq_v": True,
                "vocab_rows": 262144,
                "tied_embeddings": True,
                "final_logit_softcap": 30.0,
            },
            "sources": [
                source(
                    "hf_model_revision.json",
                    f"https://huggingface.co/api/models/{MODEL_ID}/revision/{MODEL_REVISION}",
                ),
                source(
                    "gemma4_31b_config.json",
                    f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}/config.json",
                ),
                source(
                    "model.safetensors.index.json",
                    f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}/model.safetensors.index.json",
                ),
            ],
        },
        "runtime_binding": {
            "classification": "source_backed_exact_consumer_with_gaudi2_only_execution",
            "tested_pair": {
                "vllm_gaudi_commit": VLLM_GAUDI_COMMIT,
                "vllm_commit": VLLM_COMMIT,
                "synapseai_stack": (
                    "PR landed on the vLLM-Gaudi line; current project docs bind "
                    "the maintained v1.24.1 / PyTorch 2.11 / vLLM 0.24 line, but "
                    "the exact CI job is the execution evidence used here."
                ),
            },
            "producer": {
                "component": "vLLM Gemma4ForConditionalGeneration weight loader",
                "source_file": "vllm/model_executor/models/gemma4.py",
                "sha256_at_tested_vllm_commit": "f101ae257cfe4c71e90ced922da04228468dbb84c01af00a0b48fa681f873a0f",
                "role": (
                    "loads the exact hybrid architecture, remaps language_model "
                    "weights, duplicates full-attention K into V when required, "
                    "skips non-text towers, and honors tied embeddings"
                ),
            },
            "decision_bearing_consumers": [
                {
                    "component": "HPU attention backend",
                    "source_file": "vllm_gaudi/attention/backends/hpu_attn.py",
                    "sha256_at_merge_commit": "8ff50bff1548367361aaa2b179d2a3ce1c5b928400240977040a07b4da5a0f5e",
                    "role": "hybrid full/sliding attention and KV-sharing consumer",
                },
                {
                    "component": "HPU paged attention",
                    "source_file": "vllm_gaudi/attention/ops/hpu_paged_attn.py",
                    "sha256_at_merge_commit": "10625a7fff7bf9eaf5d94089ba5ad45ffda43e88ad0ead7cf8795266fa87fd67",
                    "role": "paged KV-cache read consumer",
                },
                {
                    "component": "HPU v1 model runner",
                    "source_file": "vllm_gaudi/v1/worker/hpu_model_runner.py",
                    "sha256_at_merge_commit": "c2df950b44e2d20cf00183b21a40c389bd3f776cbbf14228cb25f8be19f55796",
                    "role": "heterogeneous KV-cache allocation and graph execution",
                },
                {
                    "component": "upstream logits processor and sampler",
                    "source_files": [
                        "vllm/model_executor/layers/logits_processor.py",
                        "vllm/v1/sample/sampler.py",
                    ],
                    "sha256_at_tested_vllm_commit": [
                        "b2b17669a923a57d34c0a0b94902c4e7742f88a73e57ca9b881c84207fceaded",
                        "315af950ef4c35fced53dc3a5df49a80af20b47e417e8f12bf315f535769bab2",
                    ],
                    "role": "tied-vocabulary logits, softcap path, and token sampling",
                },
            ],
            "execution_evidence": {
                "job_name": exact_job["name"],
                "job_url": exact_job["html_url"],
                "runner": exact_job["runner_name"],
                "accelerator": "Gaudi2 (inferred directly from runner name)",
                "tensor_parallel": 2,
                "test": "GSM8K limit=256, 5-shot",
                "reported_exact_match": 0.926,
                "conclusion": exact_job["conclusion"],
                "started_at": exact_job["started_at"],
                "completed_at": exact_job["completed_at"],
                "is_target_gaudi3_measurement": False,
                "is_scope_matched_performance_measurement": False,
            },
            "sources": [
                source("pr1619.json", pull["html_url"]),
                source(
                    "pr1619_success_jobs.json",
                    exact_job["html_url"],
                    "measured_ci_metadata",
                ),
            ],
        },
        "purchasable_topology": {
            "classification": "source_backed_topology_and_current_public_rate",
            "provider": "IBM Cloud VPC",
            "profile": PROFILE,
            "smallest_public_profile_found": "one complete eight-Gaudi3 instance",
            "accelerators": {
                "count": HPUS_PER_NODE,
                "type": "Intel Gaudi 3 OAM",
                "hbm_vendor_gb_each": 128,
                "hbm_bytes_assumed_each": int(HPU_HBM_BYTES),
                "hbm_gib_equivalent_each": number(
                    HPU_HBM_BYTES / Decimal(2**30)
                ),
            },
            "host": {
                "vcpu": 160,
                "memory_gib": 1792,
                "network_gbps": 200,
                "local_nvme": "8 x 3.2 TB",
                "internal_ai_fabric": "21 x 200 GbE",
            },
            "published_zones": [
                "us-south-dal12-a",
                "us-east-wdc06-a",
                "us-east-wdc07-a",
                "eu-de-fra02-a",
            ],
            "availability_caveat": (
                "The profile is public and active in the catalog, but actual "
                "account quota and instantaneous capacity were not tested; no "
                "login, provider contact, or resource mutation was allowed."
            ),
            "current_public_rates": {
                "currency": "USD",
                "billing_unit": "complete profile hour",
                "regions": regions,
                "selected_conservative_on_demand_region": cheapest_region,
                "selected_on_demand_usd_per_node_hour": number(planning_rate),
                "spot_excluded_from_sustainable_case": True,
                "credible_public_12_to_24_month_committed_rate": None,
                "committed_rate_note": (
                    "The public reservation metric does not expose a usable "
                    "nonzero committed price. The sustainable screen therefore "
                    "uses current on-demand, not spot or an introductory discount."
                ),
            },
            "sources": [
                source(
                    "ibm_gaudi3_profile.html",
                    "https://cloud.ibm.com/docs/vpc?interface=ui&topic=vpc-accelerated-profile-family",
                ),
                source(
                    "ibm_globalcatalog_gaudi3_plan.json",
                    "https://globalcatalog.cloud.ibm.com/api/v1/b029541d-cd56-42c5-a922-7288ed9b465f",
                ),
                source(
                    "ibm_globalcatalog_gaudi3_deployment_pricing.json",
                    (
                        "https://globalcatalog.cloud.ibm.com/api/v1/"
                        "b029541d-cd56-42c5-a922-7288ed9b465f/pricing/deployment"
                        "?account=global&deployment_region=eu-de"
                    ),
                ),
            ],
        },
        "capacity_screen": {
            "classification": "analytical_raw_state_bound_not_compiled_fit",
            "placement": {
                "tensor_parallel_per_replica": TP,
                "replicas_per_eight_hpu_node": REPLICAS,
                "concurrency_per_replica": CONCURRENCY,
                "node_concurrency": REPLICAS * CONCURRENCY,
                "precision": "BF16",
                "why_tp2": "the exact merged Gemma 4 31B HPU test used TP2",
            },
            "raw_state": {
                "weights_per_replica_bytes": weight_bytes,
                "weights_per_replica_gib": number(
                    Decimal(weight_bytes) / Decimal(2**30)
                ),
                "c32_local_kv_bytes": local_kv_bytes,
                "c32_local_kv_gib": number(
                    Decimal(local_kv_bytes) / Decimal(2**30)
                ),
                "c32_global_kv_bytes": global_kv_bytes,
                "c32_global_kv_gib": number(
                    Decimal(global_kv_bytes) / Decimal(2**30)
                ),
                "c32_total_kv_per_replica_bytes": replica_kv_bytes,
                "c32_total_kv_per_replica_gib": number(
                    Decimal(replica_kv_bytes) / Decimal(2**30)
                ),
                "raw_weights_plus_kv_per_hpu_gib_under_even_tp2": number(
                    raw_per_hpu_gib
                ),
                "raw_hbm_remaining_per_hpu_gib": number(
                    HPU_HBM_BYTES / Decimal(2**30) - raw_per_hpu_gib
                ),
            },
            "interpretation": (
                "BF16 weights plus conservative full-request c32 KV are "
                "analytically plausible at TP2. This does not prove that the "
                "Gaudi3 compiler, graph workspaces, bucketing, fragmentation, "
                "and runtime buffers fit or remain performant."
            ),
            "fp8_status": (
                "Gaudi3 has an FP8 path, but no exact revision-matched Gemma 4 "
                "31B FP8 producer, quality result, or target-workload performance "
                "sample was found; FP8 is excluded from the qualifying bound."
            ),
        },
        "workload_economics": {
            "classification": "analytical_hurdle_with_missing_measured_numerator",
            "workload": {
                "concurrency_per_replica": CONCURRENCY,
                "prompt_tokens_per_request": PROMPT_TOKENS,
                "output_tokens_per_request": OUTPUT_TOKENS,
                "total_tokens_per_request": TOTAL_TOKENS,
                "reported_prompt_cache_fraction": number(CACHE_FRACTION),
                "phase_budget": phase_budget,
            },
            "all_in_policy": {
                "utilization": 0.90,
                "additional_noncompute_multiplier": number(extra_all_in_multiplier),
                "additional_reserve_breakdown": {
                    "failures_and_reloads": 0.03,
                    "storage_boot_observability_and_orchestration": 0.02,
                    "replica_and_reliability_reserve": 0.05,
                },
                "classification": "conservative_analytical_planning_assumption",
            },
            "selected_on_demand_hurdle": selected_hurdle,
            "regional_and_spot_sensitivity": {
                region: {
                    "on_demand": hurdle(
                        Decimal(str(values["on_demand_usd_per_node_hour"])),
                        extra_all_in_multiplier,
                    ),
                    "spot_nonqualifying_sensitivity": hurdle(
                        Decimal(str(values["spot_usd_per_node_hour"])),
                        extra_all_in_multiplier,
                    ),
                }
                for region, values in regions.items()
            },
            "measured_target_gaudi3": {
                "fresh_input_seconds_per_request": None,
                "cache_read_seconds_per_request": None,
                "output_seconds_per_request": None,
                "total_service_seconds_per_request": None,
                "requests_per_second": None,
                "total_tokens_per_second": None,
                "failures_or_reloads": None,
                "cost_usd_per_m_total_tokens": None,
                "qualifies_below_target": False,
            },
        },
        "additional_unclosed_gates": [
            {
                "gate": "compiled_capacity",
                "finding": "raw BF16 state fits analytically, but exact Gaudi3 compiled/runtime fit is unmeasured",
            },
            {
                "gate": "fp8_representation_quality_and_performance",
                "finding": "no exact target-Gaudi3 FP8 producer/quality/performance binding was found",
            },
            {
                "gate": "medium_term_price",
                "finding": "no usable public 12–24 month committed price was exposed; on-demand is the conservative ceiling",
            },
            {
                "gate": "instantaneous_capacity",
                "finding": "published zones are source-bound, but quota and live capacity are untested",
            },
        ],
        "finite_reopen_measurement": {
            "required_hardware": (
                f"one provider-allocated IBM Cloud {PROFILE} node, only after "
                "campaign spend authorization and lab-pool registration"
            ),
            "required_runtime": {
                "model": MODEL_ID,
                "revision": MODEL_REVISION,
                "starting_pair": {
                    "vllm_gaudi_commit": VLLM_GAUDI_COMMIT,
                    "vllm_commit": VLLM_COMMIT,
                },
                "topology": "four TP2 replicas across eight Gaudi3 HPUs",
                "precision": "BF16 first; FP8 is a separate quality-bearing arm",
            },
            "required_workload": {
                "per_replica_concurrency": CONCURRENCY,
                "prompt_tokens": PROMPT_TOKENS,
                "output_tokens": OUTPUT_TOKENS,
                "prompt_cache_fraction": number(CACHE_FRACTION),
                "measure_separately": [
                    "fresh input/prefill",
                    "cache read",
                    "output/decode",
                    "reloads/failures",
                ],
            },
            "pass_condition_at_selected_on_demand_rate": selected_hurdle,
            "one_lifecycle_only": True,
            "current_execution_authority": (
                "none: project spend is zero, the shared bench inventory is "
                "empty, and provider mutation is forbidden"
            ),
        },
        "resource_accounting": {
            "provider_spend_usd": 0.0,
            "checkpoint_downloaded": False,
            "hardware_claimed": False,
            "paid_api_used": False,
            "provider_contacted": False,
            "resources_created": False,
        },
    }

    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "decision": result["decision"],
                "reason_code": result["reason_code"],
                "selected_rate_usd_per_node_hour": number(planning_rate),
                "required_node_total_tokens_per_second": selected_hurdle[
                    "minimum_node_aggregate_total_tokens_per_second_after_reserve"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
