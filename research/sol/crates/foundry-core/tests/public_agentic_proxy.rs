use foundry_core::public_agentic_proxy::{
    PublicAgenticProxyRequest, generate_public_agentic_proxy,
};
use foundry_core::workload::TraceProvenance;

fn request() -> PublicAgenticProxyRequest {
    serde_json::from_str(include_str!(
        "../../../configs/workloads/aa-agentperf-public-proxy-v1.json"
    ))
    .unwrap()
}

#[test]
fn generates_deterministic_public_geometry_as_a_synthetic_trace() {
    let first = generate_public_agentic_proxy(&request()).unwrap();
    let second = generate_public_agentic_proxy(&request()).unwrap();

    assert_eq!(first, second);
    assert!(first.verify_content_id().unwrap());
    assert!(first.result.trace.validate().is_ok());
    assert!(first.result.workload_contract.validate().is_ok());
    assert!(matches!(
        first.result.trace.provenance,
        TraceProvenance::Synthetic { .. }
    ));
    assert_eq!(first.result.summary.session_count, 8);
    assert_eq!(first.result.summary.request_count, 64);
    assert_eq!(first.result.summary.minimum_input_tokens, 5_000);
    assert_eq!(first.result.summary.maximum_input_tokens, 131_000);
    assert_eq!(first.result.summary.mean_input_tokens, 27_000.0);
    assert_eq!(first.result.summary.median_tool_delay_milliseconds, 1_000);
    assert_eq!(first.result.summary.peak_active_session_windows, 8);
    assert_eq!(first.result.summary.dynamic_prefix_session_count, 8);
    assert_eq!(first.result.sessions.len(), 8);
    assert!(
        first
            .result
            .sessions
            .iter()
            .all(|session| session.turns.len() == 8)
    );
    assert_eq!(first.result.slo_tiers.len(), 3);
    assert!(
        first
            .result
            .disclaimer
            .contains("not AA-AgentPerf's private test set")
    );
    assert!(
        first
            .result
            .synthetic_assumption_notice
            .contains("SLO tiers")
    );
    assert!(!first.result.claim_gates.aa_agentperf_score_claim_permitted);
    assert!(
        !first
            .result
            .claim_gates
            .measured_performance_claim_permitted
    );
    assert!(!first.result.claim_gates.nvidia_performance_claim_permitted);
    assert!(
        !first
            .result
            .claim_gates
            .provider_performance_claim_permitted
    );
    assert!(!first.result.claim_gates.cost_claim_permitted);
}

#[test]
fn rejects_public_geometry_drift_and_promoted_claims() {
    let mut drifted = request();
    drifted.public_basis.maximum_input_tokens = 130_999;
    assert!(generate_public_agentic_proxy(&drifted).is_err());

    let mut promoted = request();
    promoted.claim_gates.nvidia_performance_claim_permitted = true;
    assert!(generate_public_agentic_proxy(&promoted).is_err());
}
