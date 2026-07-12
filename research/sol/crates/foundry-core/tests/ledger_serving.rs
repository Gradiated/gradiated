use foundry_core::action_ledger::ActionLedger;
use foundry_core::glm_decode::GlmDecodeLoweringReport;
use foundry_core::ledger_roofline::LedgerRooflineReport;
use foundry_core::ledger_serving::{
    LEDGER_SERVING_REQUEST_SCHEMA_VERSION, LedgerServingClaimBlocker, LedgerServingError,
    LedgerServingSimulationRequest, simulate_exact_ledger_serving,
};
use foundry_core::workload::{
    AgentTurnClass, CanonicalTraceRequest, CanonicalTraceV2, ClassSloObjective,
    ModelTokenizerIdentity, PercentileSloObjective, TimestampBasis, TraceProvenance,
    WORKLOAD_SCHEMA_VERSION, WorkloadContractV2,
};
use std::fs;
use std::path::Path;

#[test]
fn one_exact_quantum_replays_arrivals_and_fairly_allocates_commits() {
    let report = simulate_exact_ledger_serving(&request()).unwrap();

    assert!(report.verify_content_id().unwrap());
    assert_eq!(report.result.quantum.batch_size, 8);
    assert_eq!(report.result.quantum.aggregate_context_tokens, 131_072);
    assert_eq!(report.result.quantum.candidate_tokens, 16);
    assert_eq!(report.result.quantum.committed_tokens, 12);
    assert_eq!(report.result.quantum.quantum_invocations, 1);
    assert_eq!(report.result.aggregate.padded_request_slots, 0);
    assert_eq!(report.result.aggregate.wasted_committed_token_slots, 0);
    assert_eq!(report.result.aggregate.uncommitted_candidate_token_slots, 4);
    assert_eq!(
        report
            .result
            .requests
            .iter()
            .map(|request| request.delivered_tokens)
            .collect::<Vec<_>>(),
        vec![2, 2, 2, 2, 1, 1, 1, 1]
    );
    assert_eq!(
        report.result.requests[0].start_timestamp_microseconds,
        7_000
    );
    assert_eq!(
        report.result.requests[0].first_token_timestamp_microseconds,
        report.result.requests[0].completion_timestamp_microseconds
    );
    assert_eq!(report.result.requests[0].queue_microseconds, 7_000);
    assert_eq!(report.result.requests[7].queue_microseconds, 0);
    assert!(report.result.slo.meets_contract());
    assert!(report.result.aggregate.goodput_output_tokens_per_second > 0.0);
}

#[test]
fn unused_commit_capacity_is_reported_without_padding_the_exact_batch() {
    let mut request = request();
    for trace_request in &mut request.trace.requests {
        trace_request.output_tokens = 1;
    }

    let report = simulate_exact_ledger_serving(&request).unwrap();

    assert_eq!(report.result.aggregate.delivered_output_tokens, 8);
    assert_eq!(report.result.aggregate.wasted_committed_token_slots, 4);
    assert_eq!(report.result.aggregate.padded_request_slots, 0);
    assert_eq!(
        report
            .result
            .requests
            .iter()
            .map(|request| request.delivered_tokens)
            .collect::<Vec<_>>(),
        vec![1; 8]
    );
}

#[test]
fn exact_replay_rejects_prefill_shape_identity_and_repetition_gaps() {
    let mut uncached = request();
    uncached.trace.requests[0].prefix_reused_tokens -= 1;
    assert_eq!(
        simulate_exact_ledger_serving(&uncached),
        Err(LedgerServingError::UncachedInput { request_id: 1 })
    );

    let mut wrong_batch = request();
    wrong_batch.trace.requests.pop();
    assert_eq!(
        simulate_exact_ledger_serving(&wrong_batch),
        Err(LedgerServingError::BatchSizeMismatch {
            expected: 8,
            actual: 7,
        })
    );

    let mut wrong_context = request();
    wrong_context.trace.requests[0].input_tokens += 1;
    wrong_context.trace.requests[0].prefix_reused_tokens += 1;
    assert_eq!(
        simulate_exact_ledger_serving(&wrong_context),
        Err(LedgerServingError::ContextTokensMismatch {
            expected: 131_072,
            actual: 131_073,
        })
    );

    let mut repeated = request();
    repeated.trace.requests[0].output_tokens += 1;
    assert_eq!(
        simulate_exact_ledger_serving(&repeated),
        Err(LedgerServingError::AdditionalQuantumRequired {
            available_committed_tokens: 12,
            required_output_tokens: 13,
        })
    );

    let mut identity_mismatch = request();
    identity_mismatch.workload_contract.identity.model_revision = "different".into();
    identity_mismatch.trace.identity.model_revision = "different".into();
    assert_eq!(
        simulate_exact_ledger_serving(&identity_mismatch),
        Err(LedgerServingError::LedgerModelIdentityMismatch)
    );

    let mut missing_identity = request();
    missing_identity.trace.identity.tokenizer_revision.clear();
    assert!(matches!(
        simulate_exact_ledger_serving(&missing_identity),
        Err(LedgerServingError::Workload(_))
    ));
}

#[test]
fn ledger_roofline_and_hardware_identity_are_bound_fail_closed() {
    let mut tampered = request();
    tampered.roofline.result.committed_tokens += 1;
    assert_eq!(
        simulate_exact_ledger_serving(&tampered),
        Err(LedgerServingError::InvalidRooflineContentId)
    );

    let mut wrong_ledger = request();
    wrong_ledger.ledger.provenance.phase.context_tokens += 1;
    assert_eq!(
        simulate_exact_ledger_serving(&wrong_ledger),
        Err(LedgerServingError::LedgerContentIdMismatch)
    );

    let mut missing_hardware = request();
    missing_hardware.hardware_id = "absent".into();
    assert_eq!(
        simulate_exact_ledger_serving(&missing_hardware),
        Err(LedgerServingError::MissingHardware("absent".into()))
    );
}

#[test]
fn counterfactual_queue_metrics_never_unlock_claims() {
    let report = simulate_exact_ledger_serving(&request()).unwrap();
    let claims = &report.result.claims;

    assert!(!claims.end_to_end_latency_claim_permitted);
    assert!(!claims.slo_claim_permitted);
    assert!(!claims.cost_per_token_claim_permitted);
    assert_eq!(
        claims.blockers,
        vec![
            LedgerServingClaimBlocker::PrefillNotModeled,
            LedgerServingClaimBlocker::PrefixCacheRestoreNotModeled,
            LedgerServingClaimBlocker::SharedResourceContentionNotModeled,
            LedgerServingClaimBlocker::DecodeQuantumTableNotModeled,
            LedgerServingClaimBlocker::IntraQuantumTokenTimingNotModeled,
        ]
    );
}

fn request() -> LedgerServingSimulationRequest {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let lowering: GlmDecodeLoweringReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/whole-decode-lowering-v1.json")).unwrap(),
    )
    .unwrap();
    let roofline: LedgerRooflineReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/whole-decode-ledger-roofline-v1.json")).unwrap(),
    )
    .unwrap();
    let ledger: ActionLedger = lowering.result.hardware_study_ledger.unwrap();
    let identity = ModelTokenizerIdentity {
        model_id: "zai-org/GLM-5.2".into(),
        model_revision: "b4734de4facf877f85769a911abafc5283eab3d9".into(),
        tokenizer_id: "zai-org/GLM-5.2".into(),
        tokenizer_revision: "b4734de4facf877f85769a911abafc5283eab3d9".into(),
    };
    LedgerServingSimulationRequest {
        schema_version: LEDGER_SERVING_REQUEST_SCHEMA_VERSION,
        simulation_id: "glm-5.2-exact-single-decode-quantum-test".into(),
        workload_contract: WorkloadContractV2 {
            schema_version: WORKLOAD_SCHEMA_VERSION,
            contract_id: "glm-5.2-exact-single-decode-quantum-slo-test".into(),
            identity: identity.clone(),
            class_objectives: vec![
                objective(AgentTurnClass::Tool),
                objective(AgentTurnClass::Coding),
                objective(AgentTurnClass::LongAgent),
            ],
        },
        trace: CanonicalTraceV2 {
            schema_version: WORKLOAD_SCHEMA_VERSION,
            trace_id: "glm-5.2-exact-single-decode-quantum-trace-test".into(),
            provenance: TraceProvenance::Synthetic {
                generator_id: "foundry-ledger-serving-test".into(),
                seed: 20_260_712,
            },
            timestamp_basis: TimestampBasis::RelativeMicroseconds,
            identity,
            requests: (0_u64..8)
                .map(|index| CanonicalTraceRequest {
                    request_id: index + 1,
                    class: match index % 3 {
                        0 => AgentTurnClass::Tool,
                        1 => AgentTurnClass::Coding,
                        _ => AgentTurnClass::LongAgent,
                    },
                    arrival_timestamp_microseconds: index * 1_000,
                    input_tokens: 16_384,
                    output_tokens: if index < 4 { 2 } else { 1 },
                    prefix_reused_tokens: 16_384,
                })
                .collect(),
        },
        ledger,
        roofline,
        hardware_id: "h200-like-modeled".into(),
    }
}

fn objective(class: AgentTurnClass) -> ClassSloObjective {
    ClassSloObjective {
        class,
        ttft: PercentileSloObjective {
            percentile: 95.0,
            maximum_milliseconds: 1_000.0,
        },
        tpot: PercentileSloObjective {
            percentile: 95.0,
            maximum_milliseconds: 100.0,
        },
    }
}
