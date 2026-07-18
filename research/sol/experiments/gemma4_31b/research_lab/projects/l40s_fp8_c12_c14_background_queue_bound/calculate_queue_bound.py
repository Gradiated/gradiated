#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    "campaign": ROOT / "CAMPAIGN.md",
    "market": ROOT / "projects/exact_market_venue_decision_surface/MARKET_TARGET.json",
    "saturation": ROOT / "projects/l40s_saturation_economic_gate/SATURATION_GATE.json",
    "attention_kv": ROOT / "projects/l40s_fp8_attention_kv_residual_floor/ATTENTION_KV_RESIDUAL_FLOOR.json",
    "kv_contract": ROOT / "projects/fp8_kv_contract_reconciliation/KV_CONTRACT.json",
    "memory": ROOT / "projects/fp8_l40s_fit_economic_falsifier/MEMORY_ACCOUNTING.json",
    "prior_queue": ROOT / "projects/w4_background_batching_queue_bound/QUEUE_BOUND.json",
    "prior_queue_calculator": ROOT / "projects/w4_background_batching_queue_bound/queue_bound.py",
}
EXPECTED_HASHES = {
    "campaign": "39f80855336f43cec50f02f07fa02eb99925ba2fb24ff41b7eddd7f03f7ba232",
    "market": "5d636809dc25450050c565cdc108bf7e91eaa60ce07c027ca390c8011e3b8e51",
    "saturation": "690e0e457c6e8e9121b54fb7f88abc92c3dcc358e1d71accffddb083878d00d6",
    "attention_kv": "f38704b6ae0e47e389643062c239a492d430079bf80754d8819f9a36b79aef08",
    "kv_contract": "d495553dab98eac4d101802e668469fea3758ba378a8bd89641075a277a07802",
    "memory": "eaeb0586196cac27d45b32168b41565d701b5a952d64b13c414fcc76e6f9f5be",
    "prior_queue": "4c326c6e4893124435132f8a768cf54d0a0b28aed99800d971f7769c4a3c75ff",
    "prior_queue_calculator": "49292ee67f5cdaa8ed6df45a79339526f2175b2f533f2dc040d8d24c1f6e40e7",
}
MODEL = "google/gemma-4-31B-it"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
OUTPUT_TOKENS = 358
CONCURRENCIES = (12, 14)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def poisson_cdf(k: int, mean: float) -> float:
    term = math.exp(-mean)
    total = term
    for i in range(1, k + 1):
        term *= mean / i
        total += term
    return min(1.0, total)


def erlang_cdf(t: float, shape: int, rate: float) -> float:
    if shape <= 0:
        return 1.0
    return 1.0 - poisson_cdf(shape - 1, rate * t)


def erlang_quantile(probability: float, shape: int, rate: float) -> float:
    if shape <= 0:
        return 0.0
    lo, hi = 0.0, max(1.0, shape / rate)
    while erlang_cdf(hi, shape, rate) < probability:
        hi *= 2.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if erlang_cdf(mid, shape, rate) < probability:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def assert_inputs(data: dict) -> dict:
    market = data["market"]
    saturation = data["saturation"]
    attention = data["attention_kv"]
    kv = data["kv_contract"]
    checks = {
        "all_source_hashes": all(sha256(SOURCES[k]) == EXPECTED_HASHES[k] for k in SOURCES),
        "market_model": market["model"].casefold() == MODEL.casefold(),
        "market_revision": market["model_revision"] == REVISION,
        "market_workload": market["campaign_mix"]["prompt_tokens"] == 4214
        and market["campaign_mix"]["output_tokens"] == OUTPUT_TOKENS
        and market["campaign_mix"]["prompt_cache_fraction"] == 0.127,
        "attention_model": attention["identities"]["model"] == MODEL,
        "attention_revision": attention["identities"]["revision"] == REVISION,
        "attention_operating_points": tuple(x["concurrency"] for x in attention["operating_points"]) == CONCURRENCIES,
        "kv_model": kv["identities"]["model"] == MODEL,
        "kv_revision": kv["identities"]["model_revision"] == REVISION,
        "planning_rate_consistent": math.isclose(
            saturation["economic_surface"]["planning_base"]["DeepInfra_fp8"]["required_completed_requests_per_second"]["planning"],
            attention["service_ceilings"]["planning_base"]["DeepInfra_fp8"]["required_completed_requests_per_second"],
        ),
        "conservative_rate_consistent": math.isclose(
            saturation["economic_surface"]["conservative"]["DeepInfra_fp8"]["required_completed_requests_per_second"]["planning"],
            attention["service_ceilings"]["conservative"]["DeepInfra_fp8"]["required_completed_requests_per_second"],
        ),
        "fp8_kv_non_kv_base": math.isclose(kv["logical_residency_gib"]["non_kv_allowance"]["base"], 39.35),
    }
    if not all(checks.values()):
        raise RuntimeError(f"identity assertion failed: {checks}")
    return checks


def memory_rows(kv: dict) -> list[dict]:
    residency = kv["logical_residency_gib"]
    base = residency["non_kv_allowance"]["base"]
    envelope = residency["non_kv_allowance"]["usable_l40s_envelope"]
    primary = residency["primary_input_4214"]["kv"]
    peak = residency["primary_peak_4572"]["kv"]
    rows = []
    for c in CONCURRENCIES:
        input_total = base + c * primary
        peak_total = base + c * peak
        rows.append(
            {
                "concurrency": c,
                "non_kv_base_gib": base,
                "usable_envelope_gib": envelope,
                "input_kv_gib_per_sequence": primary,
                "peak_kv_gib_per_sequence": peak,
                "input_total_gib": input_total,
                "input_headroom_gib": envelope - input_total,
                "peak_total_gib": peak_total,
                "peak_headroom_gib": envelope - peak_total,
                "logical_fit": peak_total <= envelope,
                "fit_interpretation": "allocator_sensitive" if envelope - peak_total < 0.5 else "logical_fit_requires_runtime_confirmation",
            }
        )
    return rows


def build_result(data: dict, checks: dict) -> dict:
    market = data["market"]
    saturation = data["saturation"]
    attention = data["attention_kv"]
    kv = data["kv_contract"]
    strict_planning = saturation["economic_surface"]["planning_base"]["DeepInfra_fp8"]["required_completed_requests_per_second"]["planning"]
    strict_conservative = saturation["economic_surface"]["conservative"]["DeepInfra_fp8"]["required_completed_requests_per_second"]["planning"]
    planning_ceiling = 1.0 / strict_planning
    conservative_ceiling = 1.0 / strict_conservative
    multipliers = sorted({1.0, 1.25, 1.5, strict_conservative / strict_planning, 1.75, 2.0})
    arrival_rates = [strict_planning * x for x in multipliers]
    service_assumptions = sorted(
        {
            0.7 / strict_conservative,
            0.85 / strict_planning,
            conservative_ceiling,
            1.0,
            planning_ceiling,
        }
    )
    queue_rows = []
    for arrival in arrival_rates:
        for c in CONCURRENCIES:
            first_fill_shape = c - 1
            queue_rows.append(
                {
                    "arrival_rate_requests_per_second": arrival,
                    "arrival_multiplier_of_strict_planning": arrival / strict_planning,
                    "concurrency": c,
                    "little_law_minimum_mean_decode_residence_seconds_for_average_M_equals_c": c / arrival,
                    "little_law_note": "This is a necessary mean decode-residence lower bound for natural continuous batching; queue and prefill time do not count toward decode residency.",
                    "poisson_synchronized_pooling": {
                        "mean_seconds_from_first_arrival_to_full_batch": first_fill_shape / arrival,
                        "p50_seconds_from_first_arrival_to_full_batch": erlang_quantile(0.50, first_fill_shape, arrival),
                        "p95_seconds_from_first_arrival_to_full_batch": erlang_quantile(0.95, first_fill_shape, arrival),
                        "mean_request_wait_within_full_batch_seconds": (c - 1) / (2.0 * arrival),
                        "mean_seconds_from_empty_until_c_arrivals": c / arrival,
                        "p95_seconds_from_empty_until_c_arrivals": erlang_quantile(0.95, c, arrival),
                        "boundary": "Poisson/Erlang sensitivity only; production burstiness and routing must be measured.",
                    },
                    "multiplexed_arrival_needed_by_mean_decode_residence_target": {
                        str(seconds): c / seconds for seconds in (5, 10, 15, 20, 30, 60)
                    },
                    "stable_utilization_service_limits_seconds_per_request": {
                        str(utilization): utilization / arrival for utilization in (0.70, 0.85, 0.90)
                    },
                }
            )
    decode_fraction_assumptions = (0.50, 0.75, 0.90, 1.00)
    service_rows = []
    for arrival in arrival_rates:
        for c in CONCURRENCIES:
            for service in service_assumptions:
                for decode_fraction in decode_fraction_assumptions:
                    utilization = arrival * service
                    decode_service = service * decode_fraction
                    decode_wall = c * decode_service
                    total_batch_service_wall = c * service
                    pool = (c - 1) / (2.0 * arrival)
                    service_rows.append(
                        {
                        "arrival_rate_requests_per_second": arrival,
                        "arrival_multiplier_of_strict_planning": arrival / strict_planning,
                        "concurrency": c,
                        "normalized_full_batch_whole_service_seconds_per_request_assumption": service,
                        "decode_fraction_of_whole_service_assumption": decode_fraction,
                        "normalized_full_batch_decode_service_seconds_per_request_assumption": decode_service,
                        "capacity_requests_per_second": 1.0 / service,
                        "utilization": utilization,
                        "stable": utilization < 1.0,
                        "stable_headroom_fraction": 1.0 - utilization,
                        "full_batch_decode_step_seconds_assuming_linear_normalization": decode_service * c / OUTPUT_TOKENS,
                        "synchronized_full_batch_decode_wall_seconds": decode_wall,
                        "synchronized_full_batch_total_gpu_service_wall_seconds": total_batch_service_wall,
                        "synchronized_mean_completion_seconds_including_poisson_pooling": pool + total_batch_service_wall,
                        "synchronized_first_request_p95_completion_seconds": erlang_quantile(0.95, c - 1, arrival) + total_batch_service_wall,
                        "per_sequence_output_tokens_per_second_during_synchronized_batch": OUTPUT_TOKENS / decode_wall,
                        "natural_unsynchronized_mean_resident_decode_sequences_linear_cap_sensitivity": min(float(c), arrival * decode_wall),
                        "natural_unsynchronized_mean_batch_fraction_of_cap_linear_cap_sensitivity": min(1.0, arrival * decode_service),
                        "synchronized_active_decode_batch": c,
                        "synchronized_batch_service_duty_cycle": min(1.0, utilization),
                        "synchronized_decode_gpu_duty_cycle": min(1.0, arrival * decode_service),
                        "boundary": "Whole service and decode share are parameters, not measured endpoint values; smaller-M efficiency, prefill/decode overlap, preemption and scheduler behavior can invalidate linear scaling.",
                        }
                    )
    replica_rows = []
    for replicas in (1, 2, 4):
        for arrival in arrival_rates:
            per_replica = arrival / replicas
            for c in CONCURRENCIES:
                replica_rows.append(
                    {
                        "replicas": replicas,
                        "fixed_total_arrival_requests_per_second": arrival,
                        "balanced_per_replica_arrival_requests_per_second": per_replica,
                        "concurrency": c,
                        "minimum_mean_decode_residence_seconds_per_replica": c / per_replica,
                        "mean_full_batch_pool_from_first_arrival_seconds_per_replica": (c - 1) / per_replica,
                        "economics_correct_total_hurdle_requests_per_second": replicas * strict_planning,
                        "economics_note": "At fixed total traffic, extra replicas increase cost/request and dilute batching. Holding cost competitiveness requires total completed traffic to scale with replica count, restoring the same per-replica hurdle.",
                    }
                )
    aa = market["artificial_analysis_methodology_view"]
    ten_kv = kv["logical_residency_gib"]["aa_10k"]["kv"]
    base = kv["logical_residency_gib"]["non_kv_allowance"]["base"]
    envelope = kv["logical_residency_gib"]["non_kv_allowance"]["usable_l40s_envelope"]
    tenk_rows = []
    for arrival in arrival_rates:
        interval = 1.0 / arrival
        ttft_sensitivities = {}
        for ttft in (0.0, 0.5, 1.0, float(aa["performance_examples"]["Parasail_ttft_seconds"])):
            remaining = interval - ttft
            ttft_sensitivities[str(ttft)] = None if remaining <= 0 else OUTPUT_TOKENS / remaining
        tenk_rows.append(
            {
                "arrival_rate_sensitivity_requests_per_second": arrival,
                "single_stream_max_mean_completion_seconds": interval,
                "required_output_tokens_per_second_by_ttft_seconds": ttft_sensitivities,
                "note": "Methodology sensitivity only; the 10K c1 stream is not substituted into campaign economics or pooled with primary traffic.",
            }
        )
    parasail_completion = aa["performance_examples"]["Parasail_ttft_seconds"] + OUTPUT_TOKENS / aa["performance_examples"]["Parasail_output_tps"]
    result = {
        "schema_version": 1,
        "result_type": "background_batching_credible_region",
        "status": "complete",
        "evidence_type": "derived_analytical_queue_bound_with_poisson_pooling_sensitivity",
        "scope": "Offline c12/c14 queue, batching, memory and telemetry-merge bounds; not endpoint throughput, latency acceptance, reliability, quality, or achieved kernel evidence.",
        "identities": {
            "model": MODEL,
            "revision": REVISION,
            "workload": market["campaign_mix"],
            "operating_concurrencies": list(CONCURRENCIES),
            "strict_planning_hurdle_requests_per_second": strict_planning,
            "strict_conservative_hurdle_requests_per_second": strict_conservative,
            "planning_whole_service_ceiling_seconds_per_request": planning_ceiling,
            "conservative_whole_service_ceiling_seconds_per_request": conservative_ceiling,
            "attention_kv_residual_seconds_per_request": attention["decision"]["primary_thresholds"]["c12"]["residual_floor_seconds_per_request"],
            "strict_market_cost_usd_per_request": saturation["target_costs_usd_per_request"]["DeepInfra_fp8"],
            "l40s_planning_rate_usd_per_gpu_hour": saturation["planning_rate_usd_per_gpu_hour"],
            "l40s_production_rate_range_usd_per_gpu_hour": saturation["production_rate_range_usd_per_gpu_hour"],
            "all_in_scenario_factors": saturation["scenario_factors"],
        },
        "semantic_identity_assertions": checks,
        "assumptions": {
            "natural_continuous_batching": "Little's Law applies to decode-resident sequences: mean instantaneous decode batch L_decode=lambda_completed*W_decode. Queue wait and prefill do not inflate L_decode.",
            "synchronized_pooling": "Poisson arrivals, identical 358-token completions, gated start at c; full batches are active only for a duty cycle and do not imply average resident concurrency c over billed wall time.",
            "service_parameter": "S is normalized GPU service seconds/request at full batch c. Under the linear sensitivity, batch-step time=S*c/358, batch decode wall=S*c, and capacity=1/S.",
            "no_interactive_slo": "No hard completion-time acceptance threshold is imposed. Product owners must decide whether the observed background completion distribution is usable.",
        },
        "arrival_grid": {
            "definition": "strict planning rate through exactly 2x, with strict conservative hurdle inserted",
            "multipliers": multipliers,
            "requests_per_second": arrival_rates,
        },
        "memory_capacity": {
            "rows": memory_rows(kv),
            "boundary": "Logical FP8-KV accounting only; allocator fragmentation, workspaces, captured graphs and actual peak reserved bytes remain endpoint telemetry requirements.",
        },
        "queue_curves": queue_rows,
        "service_time_sensitivities": {
            "normalized_seconds_per_request_grid": service_assumptions,
            "decode_fraction_of_whole_service_grid": list(decode_fraction_assumptions),
            "rows": service_rows,
        },
        "replica_sensitivities": replica_rows,
        "aa_10k_c1_sensitivity": {
            "logical_kv_gib": ten_kv,
            "logical_total_gib": base + ten_kv,
            "logical_headroom_gib": envelope - (base + ten_kv),
            "rows": tenk_rows,
            "venue_mismatched_reference": {
                "provider": aa["lowest_price_provider"],
                "reported_output_tokens_per_second": aa["performance_examples"]["Parasail_output_tps"],
                "reported_ttft_seconds": aa["performance_examples"]["Parasail_ttft_seconds"],
                "derived_completion_seconds_for_358_output_tokens": parasail_completion,
                "derived_sequential_requests_per_second": 1.0 / parasail_completion,
                "transfer_prohibited": True,
            },
        },
        "decision": {
            "classification": "background_batching_credible_region",
            "why_nonempty": "At the strict planning hurdle, natural c12/c14 requires mean decode residence of about 16.7/19.5 seconds; synchronized pooling can instead expose full active batches with explicit fill delay. These durations are not ruled unusable because the campaign permits background latency tradeoffs.",
            "c12": "Preferred robust logical-capacity point: positive peak-context headroom near 0.83 GiB, still requiring actual allocator and endpoint telemetry.",
            "c14": "Conditional allocator-sensitive point: positive logical peak-context headroom only about 0.07 GiB; reject if actual peak reserved crosses the bound.",
            "not_proven": "No measured service time, batch distribution, queue stability, completion usability, failure rate, or commercial endpoint result is claimed.",
            "unusable_region": "For any externally chosen mean decode-residence ceiling T, natural c requires aggregate arrival lambda>=c/T. If this fails and synchronized pooling's observed completion distribution is unacceptable, that c is unusable at that traffic. Any service row with lambda*S>=1 is unstable.",
        },
        "later_endpoint_telemetry_merge_contract": {
            "identity_fields": [
                "model_id", "model_revision", "runtime_image_digest", "runtime_source_revision", "representation",
                "tokenizer_hash", "request_corpus_hash", "prompt_tokens", "output_tokens", "cache_read_tokens",
                "max_num_seqs", "max_num_batched_tokens", "scheduler_config_hash", "sampling_config_hash",
            ],
            "steady_interval_fields": [
                "steady_start_monotonic_ns", "steady_end_monotonic_ns", "warmup_exclusion_rule",
                "arrivals", "admissions", "completions", "failures", "cancellations", "reloads",
                "queue_depth_start", "queue_depth_end", "gpu_active_seconds", "metered_seconds",
            ],
            "request_record_fields": [
                "request_id_hash", "arrival_ns", "admit_ns", "prefill_start_ns", "first_token_ns", "last_token_ns",
                "prompt_tokens", "cached_prompt_tokens", "output_tokens", "terminal_status", "replica_id",
            ],
            "scheduler_sample_fields": [
                "sample_start_ns", "sample_end_ns", "replica_id", "num_running", "num_waiting",
                "decode_sequences", "decode_tokens_scheduled", "prefill_sequences", "prefill_tokens_scheduled",
                "scheduler_step_id", "pooling_or_admission_gate_state",
            ],
            "overlap_fields": [
                "prefill_interval_union_ns", "decode_interval_union_ns", "prefill_decode_overlap_ns",
                "chunked_prefill_enabled", "prefill_chunk_token_histogram",
            ],
            "latency_outputs": [
                "queue_wait_mean_p50_p95", "ttft_mean_p50_p95", "tpot_mean_p50_p95",
                "decode_residence_mean_p50_p95", "completion_mean_p50_p95",
            ],
            "batch_outputs": [
                "decode_batch_step_count_histogram", "decode_batch_time_weighted_histogram", "decode_batch_token_weighted_histogram",
                "mean_decode_batch_time_weighted", "mean_decode_batch_token_weighted",
                "fraction_decode_active_time_at_c_minus_1_or_higher",
            ],
            "capacity_and_reliability_fields": [
                "peak_allocated_bytes", "peak_reserved_bytes", "kv_cache_bytes", "workspace_bytes",
                "oom_count", "reload_count", "failure_reason_counts", "health_probe_failures",
            ],
            "merge_formulas": {
                "completed_arrival_rate": "1e9*completions/(steady_end_monotonic_ns-steady_start_monotonic_ns)",
                "mean_decode_resident_from_samples": "sum(sample_duration*decode_sequences)/sum(sample_duration)",
                "little_law_check": "mean_decode_resident ~= completed_arrival_rate*mean_decode_residence_seconds after accounting for interval censoring",
                "queue_drift": "1e9*(queue_depth_end-queue_depth_start)/(steady_end_monotonic_ns-steady_start_monotonic_ns)",
                "prefill_decode_overlap_fraction": "prefill_decode_overlap_ns/decode_interval_union_ns",
                "observed_service_seconds_per_request": "gpu_active_seconds/completions; also report metered_seconds/completions for economics",
                "component_plus_residual_pre_endpoint_screen": "identity_matched_component_seconds_per_request + 0.1646315388888889; never substitute this for measured endpoint service",
                "batch_distribution_component_projection": "sum_M(decode_batch_step_count[M]*component_step_seconds[M])/completions, only when identity-matched component timings exist for every observed M; otherwise the measured endpoint service controls",
            },
            "typed_merge_rule": "Return credible only when identities match, all completed requests are accounted, queue drift is nonpositive within a preregistered sampling uncertainty, lambda*S<1, Little's-Law residual is explained by censoring, memory stays within 44.704 GiB, and the externally chosen background completion/reliability acceptance passes. Otherwise return unusable with the failed field, or none when required telemetry is absent.",
        },
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("QUEUE_BOUND.json"))
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("SOURCE_MANIFEST.json"))
    args = parser.parse_args()
    observed = {name: sha256(path) for name, path in SOURCES.items()}
    data = {name: json.loads(path.read_text()) for name, path in SOURCES.items() if path.suffix == ".json"}
    checks = assert_inputs(data)
    result = build_result(data, checks)
    script = Path(__file__)
    manifest = {
        "schema_version": 1,
        "sources": {
            name: {"path": str(path), "sha256": observed[name], "expected_sha256": EXPECTED_HASHES[name]}
            for name, path in SOURCES.items()
        },
        "calculator": {"path": str(script), "sha256": sha256(script)},
        "semantic_identity_assertions": checks,
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"result_type": result["result_type"], "queue_rows": len(result["queue_curves"]), "service_rows": len(result["service_time_sensitivities"]["rows"]), "manifest": str(args.manifest), "out": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
