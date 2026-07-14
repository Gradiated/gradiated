from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .director import ResearchDirector
from .legacy import import_legacy_campaign
from .util import content_hash, file_hash


def _scout(
    identifier: str,
    *,
    slot: str,
    family: str,
    origin: str,
    mechanism: str,
    change: str,
    falsifier: str,
    fidelity: str,
    ceiling: float | str,
    cost: float,
    setup_key: str,
    impact: float,
    uncertainty: float,
    discrimination: float,
    readiness: float,
    transfer_penalty: float,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": identifier,
        "cycle": 1,
        "observation_ids": ["glm47-dense-residual-v1"],
        "slot": slot,
        "family": family,
        "origin": origin,
        "mechanism": mechanism,
        "change": change,
        "competing_explanations": [
            "dense device work is on the dependency-union critical path",
            "host scheduling, launch gaps, or overlap hides the apparent device work",
            "the current summed-duration ranking is distorted by observer semantics",
        ],
        "falsifier": falsifier,
        "next_fidelity": fidelity,
        "plausible_end_to_end_ceiling_fraction": ceiling,
        "estimated_cost_usd": cost,
        "estimated_minutes": 30 if cost else 15,
        "decision_impact": impact,
        "uncertainty": uncertainty,
        "discrimination_power": discrimination,
        "readiness": readiness,
        "transfer_penalty": transfer_penalty,
        "setup_key": setup_key,
        "novelty_key": identifier,
        "quality_risks": ["absolute quality suite is not yet calibrated", "paired diagnostic instability"],
    }


def bootstrap_glm47(root: str | Path, campaign_dir: str | Path, *, program_id: str = "glm-4.7-flash") -> dict[str, Any]:
    root = Path(root)
    campaign = Path(campaign_dir)
    decision_path = campaign / "DECISION_CONTINUE_NARROWLY_SPLIT8_STOP_2026-07-14.json"
    status_path = campaign / "CAMPAIGN_STATUS.json"
    ledger_path = campaign / "CAMPAIGN_LEDGER.jsonl"
    trace_delta_path = campaign / "analysis/SPLIT8_TRACE_DELTA_V24R2_V25R1.json"
    preregistration_path = campaign / "allocations/nebius_l40s_vllm_awq_splits_ab_v24/preregistration.json"
    tokenizer_binding_path = campaign / "workloads/TOKENIZER_BINDINGS.json"
    quality_policy_path = campaign / "quality/policy.json"

    director = ResearchDirector(root, program_id)
    import_summary = import_legacy_campaign(ledger_path, status_path, decision_path, director.store)
    decision = json.loads(decision_path.read_text())
    trace_delta = json.loads(trace_delta_path.read_text())
    preregistration = json.loads(preregistration_path.read_text())
    stock = preregistration["stock_control"]
    workload = preregistration["workload_geometry"]

    baseline = {
        "schema_version": 1,
        "id": "glm47-l40s-vllm-awq-split4-v28",
        "model_revision": stock["checkpoint_revision"],
        "checkpoint_manifest_sha256": content_hash({
            "revision": stock["checkpoint_revision"],
            "source_experiment": stock["experiment_id"],
        }),
        "tokenizer_manifest_sha256": file_hash(tokenizer_binding_path),
        "runtime_manifest_sha256": content_hash({
            "runtime": stock["runtime"],
            "source_hashes": preregistration["source_hashes"],
        }),
        "workload_manifest_sha256": content_hash(workload),
        "quality_policy_sha256": file_hash(quality_policy_path),
        "slo_policy_sha256": content_hash({
            "slo": preregistration["slo"],
            "trace_gate": preregistration["trace_gate"],
        }),
        "cost_denominator": "paired-diagnostic-and-slo-eligible-output-tokens; absolute quality claim prohibited",
    }
    director.freeze_baseline(baseline)

    dense = next(row for row in trace_delta["families"] if row["family"] == "dense_gemm_gemv")
    dense_summed_fraction = dense["candidate_duration_ms"] / trace_delta["candidate_kernel_duration_sum_ms"]
    observation = {
        "schema_version": 1,
        "id": "glm47-dense-residual-v1",
        "cycle": 1,
        "evidence_class": "measured",
        "summary": decision["residual_bottleneck"],
        "scope": {
            "model": "GLM-4.7-Flash",
            "revision": stock["checkpoint_revision"],
            "workload": "fixed 8192-input c8 decode",
            "phase": "decode",
            "concurrency": "8",
            "software": stock["runtime"],
            "hardware": "Nebius L40S SM89",
        },
        "metrics": [
            {
                "name": "dense_gemm_gemv_summed_decode_fraction",
                "value": dense_summed_fraction,
                "unit": "fraction",
                "time_semantics": "summed_component_duration",
                "coverage": 1.0,
            },
            {
                "name": "decode_annotation_span_delta_after_mla_work_reduction",
                "value": trace_delta["region_duration_relative_delta"],
                "unit": "fraction",
                "time_semantics": "proxy",
                "coverage": 1.0,
            },
        ],
        "instrumentation_gaps": [
            {
                "signal": "dense_kernel_resource_counters",
                "decision_blocked": "separate memory, occupancy, instruction, and launch limits inside dense GEMM/GEMV",
                "next_probe": "capture a short exact-shape Nsight Compute or equivalent counter run after local feasibility checks",
            },
            {
                "signal": "request_dependency_union",
                "decision_blocked": "establish whether dense device work is on the request critical path rather than overlapped",
                "next_probe": "correlate request, scheduler iteration, CUDA range, stream, and kernel dependencies with at least 95% coverage",
            },
            {
                "signal": "host_scheduler_launch_timeline",
                "decision_blocked": "separate host scheduling and launch gaps from device resource limits",
                "next_probe": "run the preregistered observer-off/on trace with host, scheduler, DCGM, and CUDA correlation",
            },
        ],
        "artifact_refs": [
            director.artifacts.put_file(decision_path),
            director.artifacts.put_file(trace_delta_path),
        ],
    }
    director.record_observation(observation)
    scouts = [
        _scout(
            "glm47-dense-resource-signature",
            slot="bottleneck_adjacent",
            family="dense_gemm_gemv",
            origin="trace_local",
            mechanism="Measure whether dense GEMM/GEMV is dependency-critical and memory-, occupancy-, or launch-limited.",
            change="Profiler-off/on Nsight Systems plus bounded DCGM/host/scheduler phase capture; no model change.",
            falsifier="Dense work is not on the dependency-union critical path or observer overhead exceeds the diagnostic bound.",
            fidelity="matched_server",
            ceiling="unknown",
            cost=0.30,
            setup_key="l40s:vllm:glm47:observer",
            impact=1.0,
            uncertainty=1.0,
            discrimination=1.0,
            readiness=0.9,
            transfer_penalty=0.05,
        ),
        _scout(
            "glm47-dense-layout-falsifier",
            slot="bottleneck_adjacent",
            family="dense_gemm_gemv",
            origin="first_principles",
            mechanism="Test whether the decode GEMV shape/layout leaves reusable weight traffic or launch overhead.",
            change="Exact-shape no-weights replay comparing stock layout with one source-pinned fused or batched layout candidate.",
            falsifier="Independent oracle fails, resource ceiling is below 5%, or exact-shape timing is not stable.",
            fidelity="exact_shape",
            ceiling=0.10,
            cost=0.16,
            setup_key="l40s:vllm-image:microbench",
            impact=0.85,
            uncertainty=0.8,
            discrimination=0.9,
            readiness=0.6,
            transfer_penalty=0.35,
        ),
        _scout(
            "glm47-host-scheduler-critical-path",
            slot="cross_stack",
            family="host_scheduler",
            origin="literature_recombination",
            mechanism="The saved MLA work is hidden by host scheduling, graph replay, synchronization, or launch dependencies.",
            change="Correlate vLLM scheduler iterations, CPU runnable gaps, CUDA graph launches, and request dependency-union intervals.",
            falsifier="Host and launch intervals do not overlap the flat decode annotation span or explain its variance.",
            fidelity="matched_server",
            ceiling="unknown",
            cost=0.25,
            setup_key="l40s:vllm:glm47:observer",
            impact=0.9,
            uncertainty=1.0,
            discrimination=0.95,
            readiness=0.85,
            transfer_penalty=0.1,
        ),
        _scout(
            "glm47-layer-selective-representation",
            slot="model_architecture",
            family="model_representation",
            origin="cross_model_analogy",
            mechanism="Apply precision or layout changes only to layers whose dense/MoE resource signature dominates, preserving sensitive layers.",
            change="Simulate a layer-selective representation policy, then run reduced replay and paired quality before any full-server arm.",
            falsifier="Analytical bytes/FLOPs ceiling is below 5% or paired quality risk cannot be bounded off GPU.",
            fidelity="simulation",
            ceiling=0.20,
            cost=0.0,
            setup_key="cpu:glm47:representation-sim",
            impact=0.9,
            uncertainty=0.9,
            discrimination=0.8,
            readiness=0.45,
            transfer_penalty=0.45,
        ),
        _scout(
            "glm47-quality-and-observer-skeptic",
            slot="adversarial",
            family="measurement_validity",
            origin="adversarial",
            mechanism="The unstable compact quality case or observer perturbation can reverse candidate ordering and invalidate economics.",
            change="Calibrate a prospective expanded quality suite off GPU and measure profiler-off/on perturbation before candidate selection.",
            falsifier="The expanded suite is stable on stock replays and observer-on/off remains inside preregistered tolerances.",
            fidelity="reduced_replay",
            ceiling="unknown",
            cost=0.0,
            setup_key="cpu:glm47:quality-calibration",
            impact=1.0,
            uncertainty=1.0,
            discrimination=1.0,
            readiness=1.0,
            transfer_penalty=0.0,
        ),
    ]
    director.propose_scouts(scouts)
    selection = director.select_portfolio(1)
    state_path = director.write_state()
    context_path = director.write_coordinator_context()
    return {
        "import": import_summary,
        "baseline": baseline,
        "observation": observation,
        "portfolio": selection,
        "state_path": str(state_path),
        "context_path": str(context_path),
        "state": director.state(),
    }
