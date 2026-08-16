use foundry_core::glm_pd_serving::{
    AggregatedControl, ByteStageProfile, DisaggregatedSweep, ExplicitRateEffect, FixedFleetBudget,
    GLM_PD_SERVING_REQUEST_SCHEMA_VERSION, GlmPdServingRequest, MechanismTarget,
    MechanismTargetRole, NeutralServiceRateProfile, PdPoolSplit, SchedulingContract,
    SchedulingDiscipline, ServiceStage, StageRateEffects, TokenStageProfile, TransferEndpoint,
    evaluate_glm_pd_serving,
};
use foundry_core::glm_storage::{ByteBounds, EnvelopeEvidence, EnvelopeEvidenceKind};
use foundry_core::ledger_roofline::{HardwareTimingEvidence, HardwareTimingEvidenceKind};
use foundry_core::workload::{
    AgentTurnClass, CanonicalTraceRequest, CanonicalTraceV2, ClassSloObjective,
    ModelTokenizerIdentity, PercentileSloObjective, TimestampBasis, TraceProvenance,
    WORKLOAD_SCHEMA_VERSION, WorkloadContractV2,
};
use std::fs;
use std::path::Path;

#[test]
fn neutral_interference_and_slow_transfer_controls_match_the_hand_calculation() {
    let report = evaluate_glm_pd_serving(&request()).unwrap();

    let neutral_aggregated = case(&report, "aggregated:neutral");
    let neutral_pd = case(&report, "pd:neutral:one-one-one:delta_lower");
    assert_eq!(completions(neutral_aggregated), vec![30, 125, 170]);
    assert_eq!(completions(neutral_pd), vec![40, 130, 170]);
    assert_eq!(neutral_aggregated.aggregate.duration_microseconds, 170);
    assert_eq!(neutral_pd.aggregate.duration_microseconds, 170);
    assert_eq!(
        neutral_pd.aggregate.output_tokens_per_second,
        35_294.117647058825
    );

    let interference_aggregated = case(&report, "aggregated:interference");
    let interference_pd = case(&report, "pd:interference:one-one-one:delta_lower");
    assert_eq!(completions(interference_aggregated), vec![60, 150, 190]);
    assert_eq!(completions(interference_pd), vec![40, 130, 170]);
    assert_eq!(ttfts(interference_aggregated), vec![0.04, 0.03, 0.02]);
    assert_eq!(tpots(interference_aggregated), vec![0.02; 3]);
    assert!(
        interference_pd.aggregate.output_tokens_per_second
            > interference_aggregated.aggregate.output_tokens_per_second
    );
    assert!(
        interference_pd.aggregate.cost_per_million_output_tokens_usd
            < interference_aggregated
                .aggregate
                .cost_per_million_output_tokens_usd
    );

    let slow_pd = case(&report, "pd:slow-transfer:one-one-one:delta_lower");
    assert_eq!(completions(slow_pd), vec![230, 330, 170]);
    assert_eq!(ttfts(slow_pd), vec![0.22, 0.22, 0.01]);
    assert_eq!(tpots(slow_pd), vec![0.01; 3]);
    assert_eq!(slow_pd.requests[1].kv_transfer_queue_microseconds, 105);
    assert_eq!(slow_pd.aggregate.duration_microseconds, 330);
    assert_eq!(
        slow_pd.aggregate.goodput_output_tokens_per_second,
        6_060.606060606061
    );
    assert!(
        slow_pd.aggregate.output_tokens_per_second
            < interference_aggregated.aggregate.output_tokens_per_second
    );
    assert!(
        slow_pd
            .aggregate
            .slo_goodput_cost_per_million_output_tokens_usd
            .unwrap()
            > interference_pd
                .aggregate
                .slo_goodput_cost_per_million_output_tokens_usd
                .unwrap()
    );
}

#[test]
fn prefix_reuse_controls_uncached_prefill_and_delta_vs_full_transfer() {
    let mut request = request();
    request.disaggregated.transfer_endpoints =
        vec![TransferEndpoint::DeltaLower, TransferEndpoint::FullUpper];

    let report = evaluate_glm_pd_serving(&request).unwrap();
    let delta = case(&report, "pd:neutral:one-one-one:delta_lower");
    let full = case(&report, "pd:neutral:one-one-one:full_upper");

    assert_eq!(
        delta
            .requests
            .iter()
            .map(|request| request.uncached_input_tokens)
            .collect::<Vec<_>>(),
        vec![10, 5, 0]
    );
    assert_eq!(
        delta
            .requests
            .iter()
            .map(|request| request.kv_transfer_bytes)
            .collect::<Vec<_>>(),
        vec![100, 50, 0]
    );
    assert_eq!(
        full.requests
            .iter()
            .map(|request| request.kv_transfer_bytes)
            .collect::<Vec<_>>(),
        vec![100, 100, 100]
    );
    assert!(delta.requests[2].prefill.is_none());
    assert!(delta.requests[2].kv_transfer.is_none());
}

#[test]
fn split_sweep_penalizes_the_wrong_stage_allocation() {
    let mut prefill_heavy = request();
    prefill_heavy.budget.total_device_slots = 4;
    prefill_heavy.aggregated.worker_count = 4;
    prefill_heavy.disaggregated.splits = vec![
        split("prefill-heavy", 2, 1, 1),
        split("decode-heavy", 1, 1, 2),
    ];
    prefill_heavy.effect_scenarios = vec![effects("neutral", 10_000, 10_000, 10_000)];
    prefill_heavy.trace.requests = burst_requests(100, 1, 0);
    prefill_heavy.service_rates.kv_transfer.bytes_per_second = 1_000_000_000;

    let prefill_report = evaluate_glm_pd_serving(&prefill_heavy).unwrap();
    assert!(
        case(&prefill_report, "pd:neutral:prefill-heavy:delta_lower")
            .aggregate
            .duration_microseconds
            < case(&prefill_report, "pd:neutral:decode-heavy:delta_lower")
                .aggregate
                .duration_microseconds
    );

    let mut decode_heavy = prefill_heavy;
    decode_heavy.trace.requests = burst_requests(1, 100, 1);
    let decode_report = evaluate_glm_pd_serving(&decode_heavy).unwrap();
    assert!(
        case(&decode_report, "pd:neutral:decode-heavy:delta_lower")
            .aggregate
            .duration_microseconds
            < case(&decode_report, "pd:neutral:prefill-heavy:delta_lower")
                .aggregate
                .duration_microseconds
    );
}

#[test]
fn context_bands_are_applied_only_to_the_tokens_inside_each_band() {
    let mut request = request();
    request.service_rates.prefill.context_bands = vec![
        foundry_core::glm_pd_serving::ContextTokenRateBand {
            max_context_tokens_inclusive: 5,
            tokens_per_second: 1_000_000,
            evidence: modeled("prefill-short"),
        },
        foundry_core::glm_pd_serving::ContextTokenRateBand {
            max_context_tokens_inclusive: 1_000,
            tokens_per_second: 500_000,
            evidence: modeled("prefill-long"),
        },
    ];
    request.effect_scenarios = vec![effects("neutral", 10_000, 10_000, 10_000)];

    let report = evaluate_glm_pd_serving(&request).unwrap();
    let aggregated = case(&report, "aggregated:neutral");

    assert_eq!(
        aggregated.requests[0]
            .prefill
            .as_ref()
            .unwrap()
            .service_microseconds,
        15
    );
    assert_eq!(
        aggregated.requests[1]
            .prefill
            .as_ref()
            .unwrap()
            .service_microseconds,
        10
    );
}

#[test]
fn fixed_budget_determinism_and_claims_fail_closed() {
    let first = evaluate_glm_pd_serving(&request()).unwrap();
    let second = evaluate_glm_pd_serving(&request()).unwrap();

    assert_eq!(first, second);
    assert!(first.verify_content_id().unwrap());
    assert!(first.result.cases.iter().all(|case| {
        case.allocation.total_device_slots == 3 && case.aggregate.hourly_budget_usd == 30.0
    }));
    assert!(!first.result.claims.end_to_end_latency_claim_permitted);
    assert!(!first.result.claims.slo_claim_permitted);
    assert!(!first.result.claims.cost_per_token_claim_permitted);
}

#[test]
fn invalid_semantics_budget_evidence_and_band_coverage_fail_closed() {
    let mut continuous = request();
    continuous.scheduling.continuous_batching = true;
    assert!(evaluate_glm_pd_serving(&continuous).is_err());

    let mut bad_batch = request();
    bad_batch.scheduling.decode_batch_size = 2;
    assert!(evaluate_glm_pd_serving(&bad_batch).is_err());

    let mut bad_budget = request();
    bad_budget.disaggregated.splits[0].decode_workers = 2;
    assert!(evaluate_glm_pd_serving(&bad_budget).is_err());

    let mut missing_context = request();
    missing_context.service_rates.decode.context_bands[0].max_context_tokens_inclusive = 10;
    assert!(evaluate_glm_pd_serving(&missing_context).is_err());

    let mut provider_as_rate = request();
    provider_as_rate.service_rates.prefill.context_bands[0]
        .evidence
        .source_artifact_id = provider_as_rate.mechanism_targets[0]
        .source_artifact_id
        .clone();
    assert!(evaluate_glm_pd_serving(&provider_as_rate).is_err());

    let mut identity = request();
    identity.trace.identity.model_revision = "different".into();
    assert!(evaluate_glm_pd_serving(&identity).is_err());
}

#[test]
fn checked_in_glm_serving_control_round_trips_exactly() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let request: GlmPdServingRequest = serde_json::from_slice(
        &fs::read(root.join("configs/glm-5.2-pd-serving-control-v1.json")).unwrap(),
    )
    .unwrap();
    let stored: foundry_core::glm_pd_serving::GlmPdServingReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/pd-serving-control-v1.json")).unwrap(),
    )
    .unwrap();

    let evaluated = evaluate_glm_pd_serving(&request).unwrap();

    assert_eq!(evaluated, stored);
    assert!(stored.verify_content_id().unwrap());
    assert!(stored.result.cases.iter().any(|case| {
        case.layout == foundry_core::glm_pd_serving::ServingLayout::Disaggregated
            && case.aggregate.output_tokens_per_second
                < stored.result.cases[0].aggregate.output_tokens_per_second
    }));
}

fn request() -> GlmPdServingRequest {
    let identity = ModelTokenizerIdentity {
        model_id: "synthetic/GLM-5.2-serving-control".into(),
        model_revision: "synthetic-revision-v1".into(),
        tokenizer_id: "synthetic/GLM-5.2-serving-control".into(),
        tokenizer_revision: "synthetic-revision-v1".into(),
    };
    GlmPdServingRequest {
        schema_version: GLM_PD_SERVING_REQUEST_SCHEMA_VERSION,
        study_id: "synthetic-glm-pd-serving-test".into(),
        workload_contract: WorkloadContractV2 {
            schema_version: WORKLOAD_SCHEMA_VERSION,
            contract_id: "synthetic-glm-pd-serving-contract".into(),
            identity: identity.clone(),
            class_objectives: AgentTurnClass::ALL.into_iter().map(objective).collect(),
        },
        trace: CanonicalTraceV2 {
            schema_version: WORKLOAD_SCHEMA_VERSION,
            trace_id: "synthetic-glm-pd-serving-trace".into(),
            provenance: TraceProvenance::Synthetic {
                generator_id: "foundry-glm-pd-serving-test".into(),
                seed: 20_260_712,
            },
            timestamp_basis: TimestampBasis::RelativeMicroseconds,
            identity,
            requests: vec![
                trace_request(1, AgentTurnClass::Tool, 0, 10, 2, 0),
                trace_request(2, AgentTurnClass::Coding, 100, 10, 2, 5),
                trace_request(3, AgentTurnClass::LongAgent, 150, 10, 2, 10),
            ],
        },
        budget: FixedFleetBudget {
            total_device_slots: 3,
            usd_per_device_hour: 10.0,
            evidence: modeled("synthetic-fixed-fleet-budget"),
        },
        scheduling: SchedulingContract {
            discipline: SchedulingDiscipline::Fifo,
            continuous_batching: false,
            prefill_batch_size: 1,
            decode_batch_size: 1,
            decode_quantum_tokens: 1,
            aggregated_stage_priority: vec![ServiceStage::Prefill, ServiceStage::Decode],
        },
        service_rates: NeutralServiceRateProfile {
            prefill: TokenStageProfile {
                fixed_job_microseconds: 0,
                context_bands: vec![foundry_core::glm_pd_serving::ContextTokenRateBand {
                    max_context_tokens_inclusive: 1_000,
                    tokens_per_second: 1_000_000,
                    evidence: modeled("synthetic-prefill-rate"),
                }],
            },
            decode: TokenStageProfile {
                fixed_job_microseconds: 0,
                context_bands: vec![foundry_core::glm_pd_serving::ContextTokenRateBand {
                    max_context_tokens_inclusive: 1_000,
                    tokens_per_second: 100_000,
                    evidence: modeled("synthetic-decode-rate"),
                }],
            },
            kv_transfer: ByteStageProfile {
                fixed_job_microseconds: 0,
                bytes_per_second: 10_000_000,
                evidence: modeled("synthetic-kv-transfer-rate"),
            },
        },
        kv_transfer: foundry_core::glm_pd_serving::KvTransferEnvelope {
            bytes_per_token: ByteBounds::exact(10),
            evidence: EnvelopeEvidence {
                kind: EnvelopeEvidenceKind::ModeledAssumption,
                source_artifact_id: "synthetic-kv-bytes-per-token".into(),
            },
            basis: "synthetic exact bytes per token for event accounting".into(),
        },
        aggregated: AggregatedControl { worker_count: 3 },
        disaggregated: DisaggregatedSweep {
            splits: vec![split("one-one-one", 1, 1, 1)],
            transfer_endpoints: vec![TransferEndpoint::DeltaLower],
        },
        effect_scenarios: vec![
            effects("neutral", 10_000, 10_000, 10_000),
            effects("interference", 5_000, 10_000, 10_000),
            StageRateEffects {
                effect_id: "slow-transfer".into(),
                aggregated_prefill: effect(5_000, "aggregate-prefill-interference"),
                aggregated_decode: effect(5_000, "aggregate-decode-interference"),
                disaggregated_prefill: effect(10_000, "pd-prefill-neutral"),
                disaggregated_transfer: effect(500, "pd-transfer-slow-negative-control"),
                disaggregated_decode: effect(10_000, "pd-decode-neutral"),
            },
        ],
        mechanism_targets: vec![
            MechanismTarget {
                target_id: "baseten-pd-mechanism".into(),
                source_artifact_id:
                    "https://www.baseten.co/blog/how-we-built-the-worlds-fastest-api-for-glm-52/"
                        .into(),
                mechanism: "prefill-decode separation with KV transfer".into(),
                role: MechanismTargetRole::MechanismOnly,
            },
            MechanismTarget {
                target_id: "fireworks-pd-mechanism".into(),
                source_artifact_id: "https://fireworks.ai/blog/glm-5p2-fast".into(),
                mechanism: "prefill-decode separation and tiered prefix state".into(),
                role: MechanismTargetRole::MechanismOnly,
            },
        ],
    }
}

fn objective(class: AgentTurnClass) -> ClassSloObjective {
    ClassSloObjective {
        class,
        ttft: PercentileSloObjective {
            percentile: 95.0,
            maximum_milliseconds: 0.1,
        },
        tpot: PercentileSloObjective {
            percentile: 95.0,
            maximum_milliseconds: 0.025,
        },
    }
}

fn trace_request(
    request_id: u64,
    class: AgentTurnClass,
    arrival_timestamp_microseconds: u64,
    input_tokens: u32,
    output_tokens: u32,
    prefix_reused_tokens: u32,
) -> CanonicalTraceRequest {
    CanonicalTraceRequest {
        request_id,
        class,
        arrival_timestamp_microseconds,
        input_tokens,
        output_tokens,
        prefix_reused_tokens,
    }
}

fn burst_requests(
    input_tokens: u32,
    output_tokens: u32,
    prefix_reused_tokens: u32,
) -> Vec<CanonicalTraceRequest> {
    (0_u64..6)
        .map(|index| {
            trace_request(
                index + 1,
                AgentTurnClass::ALL[index as usize % AgentTurnClass::ALL.len()],
                0,
                input_tokens,
                output_tokens,
                prefix_reused_tokens,
            )
        })
        .collect()
}

fn split(id: &str, prefill: u32, transfer: u32, decode: u32) -> PdPoolSplit {
    PdPoolSplit {
        split_id: id.into(),
        prefill_workers: prefill,
        transfer_workers: transfer,
        decode_workers: decode,
    }
}

fn effects(id: &str, aggregated: u32, pd_transfer: u32, pd_other: u32) -> StageRateEffects {
    StageRateEffects {
        effect_id: id.into(),
        aggregated_prefill: effect(aggregated, &format!("{id}-aggregated-prefill")),
        aggregated_decode: effect(aggregated, &format!("{id}-aggregated-decode")),
        disaggregated_prefill: effect(pd_other, &format!("{id}-pd-prefill")),
        disaggregated_transfer: effect(pd_transfer, &format!("{id}-pd-transfer")),
        disaggregated_decode: effect(pd_other, &format!("{id}-pd-decode")),
    }
}

fn effect(multiplier_basis_points: u32, source: &str) -> ExplicitRateEffect {
    ExplicitRateEffect {
        multiplier_basis_points,
        evidence: modeled(source),
        basis: source.into(),
    }
}

fn modeled(source: &str) -> HardwareTimingEvidence {
    HardwareTimingEvidence {
        kind: HardwareTimingEvidenceKind::ModeledAssumption,
        source_artifact_id: source.into(),
    }
}

fn case<'a>(
    report: &'a foundry_core::glm_pd_serving::GlmPdServingReport,
    case_id: &str,
) -> &'a foundry_core::glm_pd_serving::ServingCaseReport {
    report
        .result
        .cases
        .iter()
        .find(|case| case.case_id == case_id)
        .unwrap()
}

fn completions(case: &foundry_core::glm_pd_serving::ServingCaseReport) -> Vec<u64> {
    case.requests
        .iter()
        .map(|request| request.completion_timestamp_microseconds)
        .collect()
}

fn ttfts(case: &foundry_core::glm_pd_serving::ServingCaseReport) -> Vec<f64> {
    case.requests
        .iter()
        .map(|request| request.ttft_milliseconds)
        .collect()
}

fn tpots(case: &foundry_core::glm_pd_serving::ServingCaseReport) -> Vec<f64> {
    case.requests
        .iter()
        .map(|request| request.tpot_milliseconds)
        .collect()
}
