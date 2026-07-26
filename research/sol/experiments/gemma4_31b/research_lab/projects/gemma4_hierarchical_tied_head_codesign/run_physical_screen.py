#!/usr/bin/env python3
"""Exact-geometry, trace-backed screen for the hierarchical tied head."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from hierarchical_tied_head import (
    CLUSTERS,
    HIDDEN,
    ROUTES_PER_ROW,
    ROWS,
    VOCAB,
    run_reference_fixture,
)


PROJECT = Path(__file__).resolve().parent
PROJECTS = PROJECT.parent
CONFIG = (
    PROJECTS / "gemma4_hybrid_attention_placement_codesign/inputs/bound/config.json"
)
TRACE = (
    PROJECTS
    / "gemma4_h200_ngram_fixed_m384_executor_rewrite/inputs/trace/"
    "exact_c32_profile.trace.json.gz"
)
TRACE_ANALYSIS = (
    PROJECTS
    / "gemma4_h200_ngram_verification_critical_path/artifacts/"
    "ngram-critical-20260724t115729Z/TRACE_ANALYSIS_REPAIR.json"
)
LOGITS_SOURCE = (
    PROJECTS
    / "gemma4_h200_ngram_persistent_grouped_lm_head/inputs/bound/logits_processor.py"
)
SAMPLER_SOURCE = (
    PROJECTS
    / "gemma4_h200_fp8_tied_head_endpoint/iterations/"
    "graph-bound-endpoint-20260723t1930z/inputs/source/sampler.py"
)
NGRAM_SOURCE = (
    PROJECTS
    / "gemma4_h200_ngram_verification_critical_path/inputs/source/ngram_info.py"
)
OUTPUT = PROJECT / "HIERARCHICAL_TIED_HEAD_PHYSICAL_SCREEN.json"

EXPECTED_HASHES = {
    CONFIG: "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    TRACE: "37e2c73a57e8e63bd7ec0a3465cc1edded8b9dc63507d97e85a767306a97a48b",
    TRACE_ANALYSIS: "a22e25b3e911891d75e1008f22a03ad2a7d160584e1c83e660b8a3238602304f",
    LOGITS_SOURCE: "e5d0d3a8781e74c1c7fe7508eb89d2eb198cc42bcd5e2fa4258217c756fdaf14",
    SAMPLER_SOURCE: "85541951e1cf50d10c54978178e403ff9d4aa6f223e629ea91965735ba882a8f",
    NGRAM_SOURCE: "ffa88c663e1893c306710ac801da0693d8248ebcfd1a5bc705c157f90657af1c",
}

BASELINE_SECONDS = 0.625149101968745
TARGET_SECONDS = 0.500119281574996
PROFILE_WINDOW_US = 2_375_141.908203125
H200_HBM_BYTES_PER_SECOND = 4_800_000_000_000.0

HEAD_KERNEL = "nvjet_sm90_tst_512x32_64x3_2x1_v_bz_TNT"
MATERIALIZE_FRAGMENT = (
    "unrolled_elementwise_kernel<at::native::direct_copy_kernel_cuda"
    "(at::TensorIteratorBase&)::{lambda()#3}::operator()() const::"
    "{lambda()#7}::operator()()"
)
SOFTCAP_KERNEL = "softcap_inplace_logits_kernel"
ARGMAX_FRAGMENT = "ReduceOp<float, at::native::ArgMaxOps<float>"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bound_inputs() -> list[dict[str, Any]]:
    rows = []
    for path, expected in EXPECTED_HASHES.items():
        observed = sha256(path)
        if observed != expected:
            raise RuntimeError(f"bound input mismatch: {path}: {observed}")
        rows.append(
            {
                "path": str(path.relative_to(PROJECTS)),
                "sha256": observed,
                "expected_sha256": expected,
                "match": True,
            }
        )
    return rows


def trace_rows() -> tuple[dict[str, dict[str, float | int | str]], float]:
    with gzip.open(TRACE, "rt") as handle:
        trace = json.load(handle)

    patterns = {
        "dense_tied_head_gemm": HEAD_KERNEL,
        "bf16_to_fp32_materialization": MATERIALIZE_FRAGMENT,
        "full_vocab_softcap": SOFTCAP_KERNEL,
        "full_vocab_greedy_argmax": ARGMAX_FRAGMENT,
    }
    output = {}
    selected_intervals: list[tuple[float, float]] = []
    for label, pattern in patterns.items():
        events = [
            event
            for event in trace["traceEvents"]
            if event.get("ph") == "X"
            and event.get("cat") == "kernel"
            and pattern in str(event.get("name", ""))
            and "dur" in event
        ]
        output[label] = {
            "pattern": pattern,
            "calls": len(events),
            "summed_us": sum(float(event["dur"]) for event in events),
            "streams": sorted(
                {f"{event.get('pid')}:{event.get('tid')}" for event in events}
            ),
        }
        selected_intervals.extend(
            (float(event["ts"]), float(event["ts"]) + float(event["dur"]))
            for event in events
        )
    expected_counts = {
        "dense_tied_head_gemm": 180,
        "bf16_to_fp32_materialization": 180,
        "full_vocab_softcap": 180,
        "full_vocab_greedy_argmax": 15,
    }
    observed_counts = {key: value["calls"] for key, value in output.items()}
    if observed_counts != expected_counts:
        raise RuntimeError(f"trace attribution mismatch: {observed_counts}")
    selected_intervals.sort()
    interval_union_us = 0.0
    union_start = union_end = None
    for start, end in selected_intervals:
        if union_start is None:
            union_start, union_end = start, end
        elif start <= union_end:
            union_end = max(union_end, end)
        else:
            interval_union_us += union_end - union_start
            union_start, union_end = start, end
    if union_start is not None:
        interval_union_us += union_end - union_start
    return output, interval_union_us


def source_path_audit() -> dict[str, Any]:
    candidate = (PROJECT / "hierarchical_tied_head.py").read_text()
    logits = LOGITS_SOURCE.read_text()
    sampler = SAMPLER_SOURCE.read_text()
    ngram = NGRAM_SOURCE.read_text()
    required = {
        "candidate_coarse_projection": "coarse_scores = torch.matmul(" in candidate,
        "candidate_route_topk": "route_ids = torch.topk(" in candidate,
        "candidate_explicit_fine_gather": "tied_weight.index_select(" in candidate,
        "candidate_fine_score": "scores = torch.bmm(" in candidate,
        "candidate_softcap": "torch.tanh(scores / config.softcap)" in candidate,
        "candidate_sampler_boundary": "def candidate_sampler_forward(" in candidate,
        "candidate_ngram_boundary": "def candidate_greedy_verify(" in candidate,
        "candidate_stock_fallback": "materialize_stock_fallback" in candidate,
        "candidate_runtime_install": "logits_class._get_logits = candidate_get_logits"
        in candidate,
        "pinned_dense_head": "hidden_states.to(lm_head.weight.dtype), lm_head.weight.T"
        in logits,
        "pinned_softcap": "fused_softcap(logits, self.final_logit_softcapping)"
        in logits,
        "pinned_sampler_argmax": "batch_next_token_ids = torch.argmax(logits, -1)"
        in sampler,
        "pinned_sampler_softmax": "logits[:] = torch.softmax(logits, dim=-1)"
        in sampler,
        "pinned_ngram_argmax": "torch.argmax(logits_output.next_token_logits, dim=-1)"
        in ngram,
        "pinned_ngram_sampling_softmax": "target_probs = F.softmax(" in ngram,
    }
    if not all(required.values()):
        raise RuntimeError(f"source path audit failed: {required}")
    return required


def candidate_cost(
    trace: dict[str, dict[str, float | int | str]],
    clusters: int,
    routes: int,
    *,
    explicit_gather: bool,
    fallback_rate: float,
) -> dict[str, Any]:
    rows_per_cluster = VOCAB // clusters
    selected_rows = rows_per_cluster * routes
    dense_us = float(trace["dense_tied_head_gemm"]["summed_us"]) / 15
    softcap_us = float(trace["full_vocab_softcap"]["summed_us"]) / 15
    argmax_us = float(trace["full_vocab_greedy_argmax"]["summed_us"]) / 15
    fine_row_bytes = ROWS * selected_rows * HIDDEN * 2

    costs = {
        "coarse_projection_us": max(dense_us * clusters / VOCAB, 25.0),
        "route_topk_us": max(argmax_us * clusters / VOCAB, 20.0),
        "fine_row_explicit_gather_us": (
            2
            * fine_row_bytes
            / H200_HBM_BYTES_PER_SECOND
            * 1e6
            * 1.5
            if explicit_gather
            else 0.0
        ),
        "grouped_ragged_fine_score_us": (
            fine_row_bytes / H200_HBM_BYTES_PER_SECOND * 1e6 * 2.0
        ),
        "selected_row_softcap_us": max(softcap_us * selected_rows / VOCAB, 15.0),
        "compact_sampler_argmax_us": max(
            argmax_us * selected_rows / VOCAB, 15.0
        ),
        "scatter_index_semantics_us": 20.0,
        "fixed_graph_variant_dispatch_us": 25.0,
        "synchronization_us": 20.0,
    }
    supported_us = sum(costs.values())
    baseline_consumer_us = sum(
        float(value["summed_us"]) / 15 for value in trace.values()
    )
    dispatch_fallback_us = (
        (1.0 - fallback_rate) * supported_us
        + fallback_rate * (baseline_consumer_us + 35.0)
    )
    post_route_fallback_us = supported_us + fallback_rate * (
        baseline_consumer_us + 35.0
    )
    return {
        "clusters": clusters,
        "routes_per_row": routes,
        "rows_per_cluster": rows_per_cluster,
        "selected_rows_per_hidden": selected_rows,
        "selected_fraction": selected_rows / VOCAB,
        "explicit_gather": explicit_gather,
        "fine_row_bytes_per_verification_step": fine_row_bytes,
        "costs": costs,
        "supported_path_total_us_per_verification_step": supported_us,
        "fallback_rate": fallback_rate,
        "pre_dispatch_fallback_total_us_per_step": dispatch_fallback_us,
        "post_route_fallback_total_us_per_step": post_route_fallback_us,
        "baseline_consumer_us_per_step": baseline_consumer_us,
    }


def service_seconds(
    component_us: float, baseline_consumer_us: float, output_fraction: float
) -> float:
    retained_fraction = component_us / baseline_consumer_us
    return BASELINE_SECONDS - BASELINE_SECONDS * output_fraction * (
        1.0 - retained_fraction
    )


def main() -> None:
    inputs = bound_inputs()
    config = json.loads(CONFIG.read_text())["text_config"]
    if (
        config["hidden_size"] != HIDDEN
        or config["vocab_size"] != VOCAB
        or config["tie_word_embeddings"] is not True
        or config["final_logit_softcapping"] != 30.0
    ):
        raise RuntimeError("exact model geometry mismatch")

    trace, output_interval_union_us = trace_rows()
    audit = source_path_audit()
    fixture = run_reference_fixture()
    if not (
        fixture["softcapped_scores_finite"]
        and fixture["greedy_sampler_token"] == fixture["expected_token"]
        and fixture["row_index_preserves_payload"]
        and fixture["all_fixture_rows_reachable_once"]
        and fixture["fallback_dense_argmax"] == fixture["expected_token"]
    ):
        raise RuntimeError(f"consumer fixture failed: {fixture}")

    total_output_us = sum(float(value["summed_us"]) for value in trace.values())
    if abs(output_interval_union_us - total_output_us) > 0.001:
        raise RuntimeError(
            "identified output kernels overlap; summed time is not a wall-time join"
        )
    output_fraction = output_interval_union_us / PROFILE_WINDOW_US
    zero_cost_service = BASELINE_SECONDS * (1.0 - output_fraction)
    required_fraction = (BASELINE_SECONDS - TARGET_SECONDS) / BASELINE_SECONDS

    selected = candidate_cost(
        trace, CLUSTERS, ROUTES_PER_ROW, explicit_gather=True, fallback_rate=0.0
    )
    selected_service = service_seconds(
        selected["supported_path_total_us_per_verification_step"],
        selected["baseline_consumer_us_per_step"],
        output_fraction,
    )

    geometry_sensitivity = []
    for clusters, routes in (
        (512, 1),
        (1_024, 2),
        (2_048, 4),
        (2_048, 8),
        (4_096, 8),
        (4_096, 16),
    ):
        for explicit_gather in (False, True):
            row = candidate_cost(
                trace,
                clusters,
                routes,
                explicit_gather=explicit_gather,
                fallback_rate=0.0,
            )
            row["derived_service_seconds_per_request"] = service_seconds(
                row["supported_path_total_us_per_verification_step"],
                row["baseline_consumer_us_per_step"],
                output_fraction,
            )
            geometry_sensitivity.append(row)

    fallback_sensitivity = []
    for rate in (0.0, 0.01, 0.05, 0.10, 1.0):
        row = candidate_cost(
            trace, CLUSTERS, ROUTES_PER_ROW, explicit_gather=True, fallback_rate=rate
        )
        fallback_sensitivity.append(
            {
                "fallback_rate": rate,
                "pre_dispatch_service_seconds_per_request": service_seconds(
                    row["pre_dispatch_fallback_total_us_per_step"],
                    row["baseline_consumer_us_per_step"],
                    output_fraction,
                ),
                "post_route_service_seconds_per_request": service_seconds(
                    row["post_route_fallback_total_us_per_step"],
                    row["baseline_consumer_us_per_step"],
                    output_fraction,
                ),
            }
        )

    candidate_sha = sha256(PROJECT / "hierarchical_tied_head.py")
    runner_sha = sha256(Path(__file__))
    result = {
        "schema_version": 1,
        "classification": "typed_none",
        "typed_none_reason": "target_failure_after_complete_output_consumer_attribution",
        "question": (
            "Can a source-complete coarse-to-fine tied head preserve all 262144 "
            "rows and reach the locked 0.500119281574996 s/request target?"
        ),
        "decision": {
            "target_reached": False,
            "first_binding_failure": (
                f"The exact trace attributes only {100.0 * output_fraction:.15f}% "
                "of its "
                "window to every identified tied-head GEMM, BF16 materialization, "
                "softcap, and greedy argmax event. Even impossible zero-cost "
                f"removal of that whole consumer gives {zero_cost_service:.15f} "
                f"s/request, {zero_cost_service - TARGET_SECONDS:.15f} above target."
            ),
            "locked_baseline_seconds_per_request": BASELINE_SECONDS,
            "target_seconds_per_request": TARGET_SECONDS,
            "required_reduction_fraction": required_fraction,
            "impossible_zero_cost_output_consumer_seconds_per_request": zero_cost_service,
            "impossible_zero_cost_target_margin_seconds_per_request": (
                TARGET_SECONDS - zero_cost_service
            ),
            "selected_explicit_gather_service_seconds_per_request": selected_service,
            "selected_explicit_gather_target_margin_seconds_per_request": (
                TARGET_SECONDS - selected_service
            ),
        },
        "bound_inputs": {
            "checkpoint_identity": (
                "google/gemma-4-31B-it@"
                "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
            ),
            "runtime_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "files": inputs,
        },
        "geometry": {
            "hidden_size": HIDDEN,
            "vocab_size": VOCAB,
            "tied_word_embeddings": True,
            "tied_rows_retained": VOCAB,
            "verification_rows": ROWS,
            "concurrency": 32,
            "draft_depth": 12,
            "output_tokens_per_request": 358,
            "softcap": 30.0,
        },
        "implemented_mechanism": {
            "source": "hierarchical_tied_head.py",
            "source_sha256": candidate_sha,
            "runner": "run_physical_screen.py",
            "runner_sha256": runner_sha,
            "route": (
                "Learned 2048x5376 coarse projection, stable top-8 route, "
                "128 contiguous token rows per route, explicit per-hidden row "
                "gather, exact tied-row BF16 scoring, compact softcap and stable "
                "global-token argmax."
            ),
            "production_consumers": [
                "SGLang LogitsProcessor._get_logits",
                "NgramVerifyInput._greedy_verify",
                "NgramVerifyInput._sampling_verify stock fallback",
                "Sampler.forward greedy compact consumer",
                "Sampler.forward non-greedy/logprob/custom-processor stock fallback",
            ],
            "scatter_index_semantics": (
                "The compact payload carries global candidate token IDs beside "
                "scores; row slicing preserves both. Greedy consumers reduce "
                "scores and return the lowest global token ID on exact ties. "
                "Consumers requiring a dense distribution materialize the stock "
                "full tied head rather than scatter -inf proxy logits."
            ),
            "graph_variants": (
                "The exact M384 route has fixed [384,2048] coarse and "
                "[384,1024] candidate shapes; graph dispatch is charged. "
                "Unsupported shapes and consumers use the source-bound stock path."
            ),
            "source_path_audit": audit,
            "cpu_consumer_fixture": fixture,
        },
        "reachability_proof": {
            "partition": "token_id // 128",
            "clusters": CLUSTERS,
            "rows_per_cluster": VOCAB // CLUSTERS,
            "routes_per_hidden": ROUTES_PER_ROW,
            "covered_token_interval": [0, VOCAB - 1],
            "covered_rows": CLUSTERS * (VOCAB // CLUSTERS),
            "each_row_stored_once_in_unchanged_tied_weight": True,
            "each_token_has_one_mechanical_coarse_route": True,
            "vocabulary_deleted": False,
            "quality_or_dense_distribution_equivalence_claimed": False,
        },
        "trace_attribution": {
            "profile_window_us": PROFILE_WINDOW_US,
            "events": trace,
            "all_identified_output_consumer_summed_us": total_output_us,
            "all_identified_output_consumer_interval_union_us": output_interval_union_us,
            "summed_equals_interval_union_within_us": abs(
                output_interval_union_us - total_output_us
            ),
            "all_identified_output_consumer_fraction_of_window": output_fraction,
            "attribution_method": (
                "Direct exact-name CUDA event join in the hash-bound exact-c32 "
                "trace; 180 head/materialization/softcap calls equal 15 steps x "
                "12 depths, and 15 full-vocabulary argmax reductions equal the "
                "15 greedy verification steps. All 555 events execute on CUDA "
                "stream 0:37 without overlap; interval union, not an unexamined "
                "kernel sum, supplies the wall-time fraction."
            ),
            "conservative_transfer": (
                "The measured steady-state fraction is applied to the entire "
                "locked service denominator, including prefill and unprofiled "
                "regions where no head credit is established. This deliberately "
                "overcredits the intervention."
            ),
        },
        "physical_accounting": {
            "selected_design": selected,
            "cost_labels": {
                "trace_scaled": [
                    "coarse_projection_us",
                    "route_topk_us",
                    "selected_row_softcap_us",
                    "compact_sampler_argmax_us",
                ],
                "optimistic_h200_physical_floors": [
                    "fine_row_explicit_gather_us",
                    "grouped_ragged_fine_score_us",
                ],
                "charged_non_scaling_floors": [
                    "scatter_index_semantics_us",
                    "fixed_graph_variant_dispatch_us",
                    "synchronization_us",
                ],
            },
            "h200_hbm_vendor_prior_bytes_per_second": H200_HBM_BYTES_PER_SECOND,
            "fine_gather_charge": (
                "Explicit advanced-index gather charges tied-row read plus "
                "materialized-row write at 1.5x the impossible peak-bandwidth "
                "floor; fine scoring separately rereads rows at a 2x ragged "
                "inefficiency floor."
            ),
            "fallback_charge": (
                "Known unsupported requests dispatch directly to the measured "
                "stock consumer plus 35 us. A post-route incompatibility charges "
                "both the complete candidate route and the complete stock consumer."
            ),
            "unrelated_savings_credited": [],
        },
        "sensitivities": {
            "cluster_route_and_gather": geometry_sensitivity,
            "fallback": fallback_sensitivity,
            "universal_zero_candidate_cost_floor": {
                "candidate_component_us": 0.0,
                "service_seconds_per_request": zero_cost_service,
                "target_reached": zero_cost_service <= TARGET_SECONDS,
            },
        },
        "semantics_and_quality": {
            "intervention_class": "intentional_model_semantics_change",
            "quality_status": "unqualified",
            "learned_route_weights_available": False,
            "checkpoint_downloaded": False,
            "training_performed": False,
            "future_recovery_path": [
                "recover the exact checkpoint only under later authority",
                "learn or distill the coarse route while retaining the tied rows",
                "measure route recall and target-GPU component behavior",
                "run GPQA-Diamond, TauBench, tool-call, sampling, and logprob gates",
            ],
        },
        "limitations": [
            "No checkpoint bytes, learned route weights, GPU component timing, or endpoint measurement were available or authorized.",
            "Candidate cost rows are optimistic analytical floors, not transferable target-GPU measurements.",
            "The target failure is independent of route quality and candidate cost because it grants zero cost to the entire attributed output consumer.",
            "The mechanism must not be stacked with the separate prompt-state merge screen.",
        ],
        "resource_use": {
            "provider_contacted": False,
            "gpu_claimed": False,
            "checkpoint_downloaded": False,
            "actual_spend_usd": 0.0,
        },
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
