#!/usr/bin/env python3

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
LAB_DIR = PROJECT_DIR.parent.parent

QUALIFIED_SECONDS = 0.625149101968745
TARGET_SECONDS = 0.500119281574996
TARGET_USD_PER_MILLION_TOKENS = 0.109725

BOUND_ARTIFACTS = {
    "model_config": {
        "path": "../gemma4_hybrid_attention_placement_codesign/inputs/bound/config.json",
        "sha256": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
        "evidence_labels": ["measured"],
        "role": "exact model geometry binding",
    },
    "c32_trace": {
        "path": "../gemma4_h200_ngram_fixed_m384_executor_rewrite/inputs/trace/exact_c32_profile.trace.json.gz",
        "sha256": "37e2c73a57e8e63bd7ec0a3465cc1edded8b9dc63507d97e85a767306a97a48b",
        "evidence_labels": ["measured"],
        "role": "exact c32 workload and telemetry binding",
    },
    "prompt_state_merge": {
        "path": "../gemma4_prompt_token_compaction_codesign/PROMPT_STATE_MERGE_PHYSICAL_SCREEN.json",
        "sha256": "fc87cbfcb3380d4d039f553687e58d5967ace2dd8e4ecc76f97cbe0a2cedbec8",
        "evidence_labels": ["source-complete", "measured", "analytical", "inferred"],
        "role": "model/runtime-change survivor",
    },
    "multi_resolution_global_kv": {
        "path": "../gemma4_multiresolution_global_kv_codesign/MULTIRESOLUTION_GLOBAL_KV_PHYSICAL_SCREEN.json",
        "sha256": "1d7d59a96a50f95b8cbadbb763ee072b5a4c462e1bb03f039dccda3905c84a30",
        "evidence_labels": ["source-complete", "measured", "analytical", "synthetic", "inferred"],
        "role": "model/runtime-change survivor",
    },
    "recurrent_local_attention": {
        "path": "../gemma4_recurrent_local_attention_codesign/RECURRENT_LOCAL_ATTENTION_PHYSICAL_SCREEN.json",
        "sha256": "708761c17bc605702d16058331493c01eab65417d7dc45fdea4a6ea4411fcf87",
        "evidence_labels": ["source-complete", "measured", "analytical", "synthetic", "inferred"],
        "role": "model/runtime-change survivor",
    },
    "b200": {
        "path": "../gemma4_b200_fp8_runtime_codesign/B200_FP8_RUNTIME_SCREEN.json",
        "sha256": "b6623bf5f4a81002fda5fbd9e34ac7f52af32083c32e8ff657c005850ccc4862",
        "evidence_labels": ["source-complete", "analytical", "vendor-reported", "inferred"],
        "role": "direct-placement survivor",
    },
    "mi355x": {
        "path": "../gemma4_mi355x_fp8_runtime_codesign/MI355X_FP8_RUNTIME_SCREEN.json",
        "sha256": "e1bad18d0d2e0d3e281c3502a3b4a25108d0841ac2da85e5fd0fadebe99cc500",
        "evidence_labels": ["source-complete", "measured", "analytical", "vendor-reported", "inferred"],
        "role": "direct-placement survivor",
    },
    "h100": {
        "path": "../h100_hybrid_attention_kernel_mechanism/H100_PINNED_VLLM_CONFIG_REPAIR.json",
        "sha256": "4ebee66bc22f7c88914fa9886175271ccdd822f6ce0d83ea2d6ff51418d9f4c3",
        "evidence_labels": ["source-complete", "measured"],
        "role": "direct-placement survivor",
    },
    "trainium2": {
        "path": "../gemma4_trainium2_runtime_codesign/TRAINIUM2_RUNTIME_PLACEMENT_SCREEN.json",
        "sha256": "46a81e09e0a052842e9998dcd662c6ac0a7ce6673f4d391f4525d906b226cf3d",
        "evidence_labels": ["measured", "analytical", "vendor-reported", "inferred"],
        "role": "typed negative; excluded from ranking",
    },
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(identity):
    return json.loads((PROJECT_DIR / BOUND_ARTIFACTS[identity]["path"]).read_text())


def verify_bindings():
    verified = {}
    for identity, contract in BOUND_ARTIFACTS.items():
        path = (PROJECT_DIR / contract["path"]).resolve()
        observed = sha256(path)
        if observed != contract["sha256"]:
            raise ValueError(
                f"{identity}: expected sha256 {contract['sha256']}, observed {observed}"
            )
        verified[identity] = {
            "path": str(path.relative_to(LAB_DIR)),
            "sha256": observed,
            "verified": True,
            "evidence_labels": contract["evidence_labels"],
            "role": contract["role"],
        }
    return verified


def assert_source_contracts(prompt, global_kv, recurrent, b200, mi355x, h100, trainium2):
    checks = {
        "prompt_state_source_complete": prompt["classification"]
        == "source_complete_physical_candidate",
        "global_kv_source_complete": global_kv["classification"]
        == "source_complete_physical_candidate",
        "recurrent_local_source_complete": recurrent["classification"]
        == "source_complete_physical_candidate",
        "b200_source_complete": b200["decision"]["result"]
        == "source_complete_b200_candidate",
        "mi355x_source_complete": mi355x["classification"]
        == "source_complete_mi355x_candidate",
        "h100_science_unconsumed": h100["scientific_replay"] is False,
        "trainium2_typed_none": trainium2["classification"] == "typed_none",
        "prompt_target_bound": prompt["physical_accounting"]["locked_target_seconds_per_request"]
        == TARGET_SECONDS,
        "global_target_bound": global_kv["physical_accounting"]["target_seconds_per_request"]
        == TARGET_SECONDS,
        "recurrent_target_bound": recurrent["physical_accounting"]["target_seconds_per_request"]
        == TARGET_SECONDS,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"source contract checks failed: {', '.join(failed)}")
    return checks


def unpriced_envelope(reason, storage):
    return {
        "envelope_status": "unpriced_external_input",
        "wall_clock_minutes_max": None,
        "accelerator_hours_max": None,
        "storage_gib_max": None,
        "spend_usd_max": None,
        "known_storage_requirement": storage,
        "reason": reason,
        "fundable_as_next_lifecycle": False,
    }


def build_frontier():
    bindings = verify_bindings()
    prompt = load_json("prompt_state_merge")
    global_kv = load_json("multi_resolution_global_kv")
    recurrent = load_json("recurrent_local_attention")
    b200 = load_json("b200")
    mi355x = load_json("mi355x")
    h100 = load_json("h100")
    trainium2 = load_json("trainium2")
    checks = assert_source_contracts(
        prompt, global_kv, recurrent, b200, mi355x, h100, trainium2
    )

    b200_decision = b200["decision"]
    b200_falsifier = b200["later_b200_falsifier"]
    mi_screen = mi355x["physical_cost_screen"]
    mi_base = mi_screen["hurdles"]["production_base_2_60"]
    mi_falsifier = mi355x["later_exact_shape_falsifier"]
    prompt_physical = prompt["physical_accounting"]
    global_decision = global_kv["decision"]
    recurrent_decision = recurrent["decision"]

    direct_placement = [
        {
            "rank": 1,
            "survivor": "mi355x",
            "scope": "single MI355X/gfx950 TP1; online per-tensor OCP E4M3FN transformer linears, FP8 KV, BF16 tied head",
            "exact_consumer_reached": "Local CPU source discriminator reached ROCmFP8ScaledMMLinearKernel -> torch._scaled_mm/hipBLASLt and AITER flash/unified hybrid-attention dispatch; target GPU remains unexecuted.",
            "evidence_boundary": mi_screen["evidence_boundary"],
            "own_price_normalized_accounting": {
                "planning_rate_usd_per_accelerator_hour": 2.60,
                "hurdle_seconds_per_request": mi_base["hurdle_seconds_per_request"],
                "analytical_seconds_per_request": mi_base["screen_seconds_per_request"],
                "margin_seconds_per_request": mi_base["margin_seconds_per_request"],
                "margin_fraction_of_hurdle": mi_base["margin_seconds_per_request"]
                / mi_base["hurdle_seconds_per_request"],
                "sensitivity": {
                    "passes_at_usd_per_hour": [2.40, 2.60],
                    "fails_at_usd_per_hour": [2.75, 2.95],
                    "minimum_fp8_math_efficiency": mi_screen[
                        "stress_thresholds_holding_other_assumptions_fixed"
                    ]["minimum_fp8_math_efficiency_to_clear_base"],
                    "minimum_hbm_efficiency": mi_screen[
                        "stress_thresholds_holding_other_assumptions_fixed"
                    ]["minimum_hbm_efficiency_to_clear_base"],
                },
                "stacked_gain_credit": False,
            },
            "gates": {
                "compilation": "Compile exact gfx950 scaled-mm and local d256/global d512 AITER calls.",
                "target_hardware": "One MI355X/gfx950 TP1.",
                "checkpoint": "Not required for the synthetic exact-shape falsifier; a later endpoint requires the exact checkpoint.",
                "training": "None for placement.",
                "quality": "Component numerical gates first; exact served checkpoint GPQA-Diamond, TauBench, tool-call and reliability gates remain before promotion.",
                "production": "A pass is conditional on a scope-matched production rate no higher than $2.60/hour under this artifact's accounting.",
            },
            "minimum_credible_falsifier": {
                "action": "Run the bound online-quantized exact transformer shapes at M32/M384, local d256 and global d512 FP8-KV attention, and BF16 tied-head baseline on one MI355X.",
                "invalidation_rule": "Close or demote on any fallback, global d512 compile/resource failure, numerical failure, component aggregate above 0.545847226968745 s/request, or whole-request reconstruction above 0.625149101968745 s/request.",
                "envelope_status": "finite_bound_artifact",
                "wall_clock_minutes_max": mi_falsifier["wall_clock_bound_minutes"],
                "accelerator_hours_max": mi_falsifier["wall_clock_bound_minutes"] / 60,
                "storage_gib_max": 8.0,
                "spend_usd_max": mi_falsifier[
                    "maximum_provider_spend_usd_if_later_authorized_at_2_95_per_hour"
                ],
                "setup_and_cleanup_included": True,
            },
            "decision_value": "Highest next-dollar discriminator: the finite falsifier is 60.7% cheaper and 20% shorter than B200, while directly testing the source screen's highest uncertainty, global d512 compile/resource behavior.",
        },
        {
            "rank": 2,
            "survivor": "b200",
            "scope": "single NVIDIA B200 SXM/SM100; dynamic E4M3 transformer linears and E4M3 KV with BF16 tied head",
            "exact_consumer_reached": "Pinned source maps the exact production input to CUTLASS SM100 FP8 linears and FlashInfer TRTLLM-generation d256/d512 FP8-KV attention.",
            "evidence_boundary": b200["evidence_boundary"],
            "own_price_normalized_accounting": {
                "planning_rate_usd_per_accelerator_hour": 5.15,
                "hurdle_seconds_per_request": b200_decision[
                    "production_hurdle_seconds_per_request"
                ],
                "analytical_seconds_per_request": b200_decision[
                    "headline_seconds_per_request"
                ],
                "margin_seconds_per_request": b200_decision[
                    "margin_seconds_per_request"
                ],
                "margin_fraction_of_hurdle": b200_decision[
                    "margin_fraction_of_hurdle"
                ],
                "sensitivity": {
                    "passes_at_hbm_fraction": [0.75, 0.70],
                    "fails_at_hbm_fraction": [0.65],
                    "minimum_streaming_hbm_fraction": 0.75,
                    "minimum_prefill_dense_fp8_fraction": 0.65,
                },
                "stacked_gain_credit": False,
            },
            "gates": {
                "compilation": "Resolve immutable SM100 CUTLASS and FlashInfer TRTLLM-generation cubins before scientific entry.",
                "target_hardware": "One full B200 SXM/SM100.",
                "checkpoint": "Not required for the synthetic exact-shape falsifier; exact checkpoint is required later for endpoint and quality.",
                "training": "None for placement.",
                "quality": "Component FP32-oracle gates first; exact served checkpoint GPQA-Diamond, TauBench and feature gates remain.",
                "production": "Require <=0.31560925536286155 s/request at the artifact's $5.15/hour planning rate.",
            },
            "minimum_credible_falsifier": {
                "action": b200_falsifier["candidate"],
                "invalidation_rule": b200_falsifier["stop_rule"],
                "envelope_status": "finite_bound_artifact",
                "wall_clock_minutes_max": b200_falsifier["wall_clock_minutes_max"],
                "accelerator_hours_max": b200_falsifier["wall_clock_minutes_max"]
                / 60,
                "storage_gib_max": 8.0,
                "spend_usd_max": b200_falsifier["future_provider_spend_usd_max"],
                "setup_and_cleanup_included": True,
            },
            "decision_value": "More robust analytical placement than MI355X, but its falsifier costs 2.54x more and is five minutes longer; fund after MI355X unless a B200 bench is already warm at zero incremental lifecycle cost.",
        },
        {
            "rank": 3,
            "survivor": "h100_registered_attention",
            "scope": h100["repair_scope"],
            "exact_consumer_reached": "The repaired ModelConfig proxy passed 17 local unit tests and can be passed to VllmConfig; no scientific replay or target-H100 result exists.",
            "evidence_boundary": "Measured adapter repair only. The bound artifact contains no price-normalized hurdle, target timing, provider envelope, or numerical sample.",
            "own_price_normalized_accounting": {
                "planning_rate_usd_per_accelerator_hour": None,
                "hurdle_seconds_per_request": None,
                "analytical_seconds_per_request": None,
                "margin_seconds_per_request": None,
                "stacked_gain_credit": False,
                "typed_missing_evidence": "No H100 economic or performance row is present in the bound artifact.",
            },
            "gates": {
                "compilation": "Open on the pinned runtime.",
                "target_hardware": "Open; exact H100 registered-Attention arm remains unconsumed.",
                "checkpoint": "Not established by the bound repair artifact.",
                "training": "None implied by the adapter repair.",
                "quality": "Open.",
                "production": "Open; no bound hurdle.",
            },
            "minimum_credible_falsifier": {
                "action": "Execute the repaired pinned VllmConfig through the exact registered-Attention component and persist one numerical/timing result.",
                "invalidation_rule": "Demote if the repaired config cannot reach the exact consumer or fails its as-yet-unbound numerical/economic gate.",
                **unpriced_envelope(
                    "The only admitted H100 artifact is a config repair and does not bind a rate, hurdle, runtime duration, or storage plan.",
                    "Pinned runtime plus exact component inputs; quantity unbound.",
                ),
            },
            "decision_value": "Not fundable from the admitted evidence because a reservation cannot be conservatively sized.",
        },
    ]

    model_runtime_change = [
        {
            "rank": 1,
            "survivor": "recurrent_local_attention",
            "scope": "Intentional replacement of 50 local softmax-attention layers with rank-64 positive-feature recurrence; no placement transfer.",
            "exact_consumer_reached": "Source-complete one-pass Triton consumer and pure-Python FP64 information-path fixture; target CUDA compilation and timing are absent.",
            "target_accounting": {
                "qualified_seconds_per_request": QUALIFIED_SECONDS,
                "target_seconds_per_request": TARGET_SECONDS,
                "analytical_seconds_per_request": recurrent_decision[
                    "derived_service_seconds_per_request"
                ],
                "margin_seconds_per_request": recurrent_decision[
                    "target_margin_seconds_per_request"
                ],
                "sensitivity": {
                    "maximum_fallback_rate": recurrent["sensitivities"][
                        "maximum_fallback_rate_before_target_failure"
                    ],
                    "rank_64_one_pass_required": True,
                    "rank_96_fails": True,
                    "second_consumer_pass_fails": True,
                    "fixed_overhead_9ms_fails": True,
                },
                "stacked_gain_credit": False,
            },
            "gates": {
                "compilation": "Exact c32 one-pass target-H200 compile open.",
                "target_hardware": "Component correctness and profiler-off timing open.",
                "checkpoint": "Exact checkpoint required for projection training and endpoint.",
                "training": "Per-layer positive feature projections are untrained; distillation/training required.",
                "quality": "GPQA-Diamond, TauBench, tool calls, long-context retrieval and fallback calibration open.",
                "production": "Only after standalone locked endpoint <=0.500119281574996 s/request without other survivor credit.",
            },
            "minimum_credible_falsifier": {
                "action": "Train or distill rank-64 projections, then compile and measure the one-pass exact-c32 component before endpoint quality.",
                "invalidation_rule": "Close on rank >64 requirement, second consumer pass, fallback >15.508%, fixed overhead above the sensitivity boundary, failed component numerical result, or unrecoverable quality loss.",
                **unpriced_envelope(
                    "The bound artifact specifies training but contains no dataset, training-compute, checkpoint-storage, or provider-rate envelope.",
                    "Exact checkpoint, training corpus, optimizer state, distilled checkpoint, and component logs.",
                ),
            },
            "decision_value": "Best model-change margin, but it cannot precede a finite placement falsifier because learned projections and quality recovery are uncosted.",
        },
        {
            "rank": 2,
            "survivor": "prompt_state_merge",
            "scope": "Intentional two-tier prompt semantics change after layer 5 to 1,152 protected or merged states; no placement transfer.",
            "exact_consumer_reached": "Source-complete split runtime through late layers and rebuilt attention metadata; hidden-state quality and target-GPU execution are absent.",
            "target_accounting": {
                "qualified_seconds_per_request": QUALIFIED_SECONDS,
                "target_seconds_per_request": TARGET_SECONDS,
                "analytical_seconds_per_request": prompt_physical[
                    "conservative_candidate_service_seconds_per_request"
                ],
                "margin_seconds_per_request": prompt_physical[
                    "margin_to_target_seconds_per_request"
                ],
                "sensitivity": {
                    "maximum_total_incremental_overhead_seconds": prompt_physical[
                        "maximum_total_incremental_overhead_seconds_per_request"
                    ],
                    "maximum_passing_output_states": 1184,
                    "first_failing_output_states": 1200,
                    "protected_overflow_credit": False,
                },
                "stacked_gain_credit": False,
            },
            "gates": {
                "compilation": "One 134,848-token exact-c32 prefill cohort and compact late-layer graph open on H200.",
                "target_hardware": "15 ms overhead envelope and fit unmeasured.",
                "checkpoint": "Exact checkpoint and representative prompt bytes required.",
                "training": "Layer-5 scorer and boundary adapter distillation required.",
                "quality": "GPQA-Diamond, TauBench, retrieval, tools, formatting, multimodal, and fallback calibration open.",
                "production": "Standalone endpoint must remain <=0.500119281574996 s/request with no capacity credit.",
            },
            "minimum_credible_falsifier": {
                "action": "Materialize the exact checkpoint and representative prompts, measure protected-state overflow and scorer/merge semantics, then train the minimum boundary adapter before endpoint timing.",
                "invalidation_rule": "Demote immediately if >1,184 states are needed, total added overhead exceeds 16.417816 ms/request, the c32 cohort does not fit, or semantic recovery fails.",
                **unpriced_envelope(
                    "The bound artifact does not cost checkpoint access, training, representative prompt capture, or H200 endpoint time.",
                    "Exact checkpoint, prompts/hidden states, trained adapter, and endpoint artifacts.",
                ),
            },
            "decision_value": "Only 1.418 ms analytical margin and broad semantic recovery make it lower value than recurrent local attention.",
        },
        {
            "rank": 3,
            "survivor": "multi_resolution_global_kv",
            "scope": "Intentional global-attention summary representation; local attention remains stock and no other survivor savings are credited.",
            "exact_consumer_reached": "Source-complete fused grouped-query consumer audit; its information-path fixture records consumer execution unavailable on the coordinator.",
            "target_accounting": {
                "qualified_seconds_per_request": QUALIFIED_SECONDS,
                "target_seconds_per_request": TARGET_SECONDS,
                "analytical_seconds_per_request": global_decision[
                    "derived_service_seconds_per_request"
                ],
                "margin_seconds_per_request": global_decision[
                    "target_margin_seconds_per_request"
                ],
                "sensitivity": {
                    "maximum_fallback_rate": global_decision[
                        "maximum_fallback_rate_before_target_failure"
                    ],
                    "one_64_key_tile_required": True,
                    "second_tile_fails": True,
                },
                "stacked_gain_credit": False,
            },
            "gates": {
                "compilation": "Fused global kernel target-H200 compile open.",
                "target_hardware": "Component correctness, tile count and profiler-off timing open.",
                "checkpoint": "Exact checkpoint required for distillation and endpoint.",
                "training": "Per-layer summary K/V distillation required.",
                "quality": "GPQA-Diamond, TauBench, tools, long-context retrieval and exact fallback open.",
                "production": "Standalone endpoint must clear the locked target with one tile and fallback below 0.129%.",
            },
            "minimum_credible_falsifier": {
                "action": "Execute the real fused consumer at exact geometry, calibrate protected spans/fallback, and distill summary K/V before any endpoint claim.",
                "invalidation_rule": "Close or demote on a second compact tile, fallback >=0.128733%, consumer numerical failure, or target-H200 overhead above the 0.161 ms margin.",
                **unpriced_envelope(
                    "The bound artifact leaves target execution, checkpoint access, distillation, and quality unpriced.",
                    "Exact checkpoint, distilled summary parameters, component and quality artifacts.",
                ),
            },
            "decision_value": "A 0.161 ms analytical margin, sub-0.129% fallback tolerance, and unexecuted consumer make it the lowest-ranked survivor.",
        },
    ]

    recommended = {
        "lifecycle_id": "mi355x_exact_shape_compile_and_component_falsifier",
        "survivor": "mi355x",
        "authorization_state": "not_authorized; handoff only",
        "why_exactly_one": "It is the smallest finite target-hardware discriminator and does not require checkpoint download, training, or stacked gains.",
        "reservation_before_create": {
            "required": True,
            "required_reservation_usd": mi_falsifier[
                "maximum_provider_spend_usd_if_later_authorized_at_2_95_per_hour"
            ],
            "rule": "The director must reserve the full amount within campaign authority before any provider creation or paid bench use; a researcher may only claim a registered compatible lab bench.",
            "current_authorized_spend_usd": 0.0,
        },
        "resource_envelope": {
            "hardware": mi_falsifier["hardware"],
            "wall_clock_minutes_max": mi_falsifier["wall_clock_bound_minutes"],
            "accelerator_hours_max": mi_falsifier["wall_clock_bound_minutes"]
            / 60,
            "storage_gib_max": 8.0,
            "provider_spend_usd_max": mi_falsifier[
                "maximum_provider_spend_usd_if_later_authorized_at_2_95_per_hour"
            ],
            "checkpoint_download": False,
        },
        "setup": {
            "minutes_max": 5,
            "steps": [
                "Claim one compatible registered MI355X bench only after the positive reservation.",
                "Materialize and hash-bind the admitted runner/source bytes under this project before scientific entry; do not re-resolve mutable shared paths after claim.",
                "Bind vLLM 0164022c907014a27e81c514cd4dff6091904c2b and AITER 6c48c5fa0e7c299adcf1987c8f4817720ceab311.",
                "Prepare synthetic exact-shape BF16 weights/inputs; do not download the checkpoint.",
            ],
        },
        "sentinel": {
            "minutes_max": 4,
            "science_start_rule": "Write science_started only after identity/runtime validation and immediately before the first scaled-mm or AITER submission.",
            "calls": [
                "First exact M32 online-quantized scaled-mm call through the selected ROCm consumer.",
                "First exact global head512 AITER FP8-KV call, persisting compile/resource diagnostics and raw output.",
            ],
            "interpretation": "A complete numerical sentinel is a consumed component sample and is not replayed; launcher or observer defects without an interpretable result are repaired in place under the same claim.",
        },
        "measurement": {
            "minutes_max": 7,
            "arms": mi_falsifier["arms"],
            "timing": mi_falsifier["timing"],
            "numerical_gate": mi_falsifier["oracle"],
            "economic_gate": mi_falsifier["numerical_gate"],
            "no_stacked_gains": True,
        },
        "terminal": {
            "minutes_max": 2,
            "pass": "All exact consumers execute without fallback, numerical gates pass, component aggregate <=0.545847226968745 s/request, and reconstructed whole request <=0.625149101968745 s/request.",
            "fail": "Persist an interpretable component result that violates any numerical, fallback, compile/resource, component-time, or whole-request gate.",
            "invalid_attempt": "Persist diagnostics and repair only the invalidated launcher/observer/consumer operation under the same claim; do not count or replay a complete result.",
        },
        "cleanup": {
            "minutes_max": 2,
            "steps": [
                "Retrieve compact terminal, raw stdout/stderr, science-start and per-arm result markers before release.",
                "Preserve compiled artifacts and caches and update the bench contents.",
                "Release an unoccupied healthy bench available; release maintenance if useful resident state cannot safely be inherited. Do not tear down the provider.",
            ],
        },
        "stop_rules": [
            "Do not create or claim anything without a positive director reservation and compatible registered bench.",
            "Do not continue past the 20-minute or $0.9833333333333333 bound.",
            "After an interpretable exact-shape sample, do not replay that arm.",
            "Stop scientific promotion on fallback, global d512 compile/resource failure, numerical failure, component aggregate above 0.545847226968745 s/request, or reconstructed service time above 0.625149101968745 s/request.",
            "A pass funds later exact-checkpoint endpoint and quality work; it is not itself a production or quality claim.",
        ],
    }

    frontier = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "ranked_validation_frontier",
        "question": "Which one preserved source-complete survivor should receive the next newly authorized lifecycle?",
        "decision": "Fund the MI355X exact-shape compile/component falsifier first when new authority and a compatible lab bench exist.",
        "campaign_targets": {
            "qualified_denominator_seconds_per_request": QUALIFIED_SECONDS,
            "locked_physical_target_seconds_per_request": TARGET_SECONDS,
            "locked_sustainable_usd_per_million_total_tokens": TARGET_USD_PER_MILLION_TOKENS,
            "quality_requirements": [
                "exact served model",
                "GPQA-Diamond",
                "TauBench",
                "tool-call/request path",
                "production representation and required behavior",
            ],
        },
        "binding_verification": {
            "all_verified": True,
            "artifacts": bindings,
            "source_contract_checks": checks,
        },
        "accounting_rules": {
            "placement_and_model_changes_separate": True,
            "cross_accelerator_seconds_compared": False,
            "placement_seconds_tied_to_own_price_hurdle": True,
            "stacked_gains_forbidden": True,
            "capacity_deletion_credit": False,
            "source_complete_is_not_measured_throughput": True,
        },
        "ranking_method": {
            "primary_order": [
                "scope admissibility and exact consumer path",
                "finite reservation and terminal envelope",
                "decision value per newly authorized dollar and wall-clock hour",
                "margin robustness and fallback/precision sensitivity",
                "checkpoint, training, quality, and recovery burden",
            ],
            "placement_and_model_runtime_rankings_are_not_cross-normalized": True,
        },
        "direct_placement_ledger": direct_placement,
        "model_runtime_change_ledger": model_runtime_change,
        "excluded_evidence": {
            "trainium2": {
                "classification": trainium2["classification"],
                "typed_boundary": trainium2["typed_none"],
                "committed_rate_hurdle_seconds_per_request": trainium2[
                    "pricing_and_all_in_economics"
                ]["break_even_service_seconds_per_request"],
                "ranking_eligible": False,
                "reason": "Current official source has no exact Gemma 4 producer/consumer path; hypothetical cost rows are not placement evidence.",
            },
            "conditional_depth": {
                "classification": "out_of_scope_preserved_evidence",
                "ranking_eligible": False,
                "reason": "The project contract excludes conditional-depth and capacity-deletion credit; no gain is transferred to a survivor.",
            },
        },
        "recommended_next_lifecycle": recommended,
        "offline_prerequisite": None,
        "lower_ranked_next_dollar_reasons": [
            {
                "survivor": "b200",
                "reason": "Its finite falsifier is 2.54x more expensive and five minutes longer than MI355X; retain it second because its analytical margin is more robust.",
            },
            {
                "survivor": "h100_registered_attention",
                "reason": "The bound repair proves adapter integration only and does not contain a conservative rate, hurdle, duration, storage, or spend envelope.",
            },
            {
                "survivor": "recurrent_local_attention",
                "reason": "The physical margin is useful, but learned projections, checkpoint access, training, and quality recovery have no finite bound.",
            },
            {
                "survivor": "prompt_state_merge",
                "reason": "Its 1.418 ms analytical margin is fragile and it needs representative prompt capture, training, and broad semantic recovery.",
            },
            {
                "survivor": "multi_resolution_global_kv",
                "reason": "Its 0.161 ms margin, <0.129% fallback tolerance, one-tile dependency, and unexecuted consumer make it a poor next-dollar bet.",
            },
            {
                "survivor": "trainium2",
                "reason": "Typed current-runtime-source-incomplete; excluded from the survivor ranking.",
            },
        ],
        "resource_use_this_turn": {
            "actual_spend_usd": 0.0,
            "provider_contacted": False,
            "provider_resources_created": False,
            "gpu_or_accelerator_claimed": False,
            "checkpoint_downloaded": False,
            "prices_browsed": False,
            "benchmarks_rerun": False,
        },
    }
    validate_frontier(frontier)
    return frontier


def validate_frontier(frontier):
    if frontier["classification"] not in {
        "ranked_validation_frontier",
        "typed_none",
    }:
        raise ValueError("invalid classification")
    recommended = frontier.get("recommended_next_lifecycle")
    if recommended is None:
        if frontier["classification"] != "typed_none":
            raise ValueError("ranked frontier must have exactly one lifecycle")
    elif not isinstance(recommended, dict) or not recommended.get("lifecycle_id"):
        raise ValueError("recommended lifecycle must be one object")
    if frontier["offline_prerequisite"] is not None and not isinstance(
        frontier["offline_prerequisite"], dict
    ):
        raise ValueError("offline prerequisite must be null or one object")
    direct = {row["survivor"] for row in frontier["direct_placement_ledger"]}
    model = {row["survivor"] for row in frontier["model_runtime_change_ledger"]}
    if direct & model:
        raise ValueError("placement and model ledgers overlap")
    if any(
        row["own_price_normalized_accounting"]["stacked_gain_credit"]
        for row in frontier["direct_placement_ledger"]
    ):
        raise ValueError("stacked placement gain")
    if any(
        row["target_accounting"]["stacked_gain_credit"]
        for row in frontier["model_runtime_change_ledger"]
    ):
        raise ValueError("stacked model/runtime gain")
    if frontier["resource_use_this_turn"]["actual_spend_usd"] != 0.0:
        raise ValueError("offline discriminator must spend zero")
    if frontier["excluded_evidence"]["trainium2"]["ranking_eligible"]:
        raise ValueError("Trainium2 must remain excluded")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_DIR / "SURVIVOR_VALIDATION_FRONTIER.json",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    frontier = build_frontier()
    if args.check:
        existing = json.loads(args.output.read_text())
        existing.pop("generated_at_utc", None)
        frontier.pop("generated_at_utc", None)
        if existing != frontier:
            raise SystemExit(f"{args.output} is stale")
        return
    args.output.write_text(json.dumps(frontier, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
