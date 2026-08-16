use foundry_core::mtp::{
    GLM_MTP_SWEEP_REQUEST_SCHEMA_VERSION, GlmMtpSweepReport, GlmMtpSweepRequest,
    MtpAcceptanceScenario, MtpClaimBlocker, MtpEvidence, MtpEvidenceKind, MtpWorkAssumptions,
    evaluate_glm_mtp_sweep,
};
use foundry_core::spec::{ModelArchitecture, glm_5_2_bf16_reference};
use std::fs;
use std::path::Path;

#[test]
fn conditional_acceptance_is_converted_to_committed_tokens_and_work() {
    let report = evaluate_glm_mtp_sweep(&request(vec![scenario(
        "steady-80pct",
        vec![0.8, 0.8, 0.8],
    )]))
    .unwrap();
    let scenario = &report.result.scenarios[0];
    let depth_two = &scenario.depths[1];

    assert_close(depth_two.expected_accepted_draft_tokens, 1.44);
    assert_close(depth_two.expected_committed_tokens_per_round, 2.44);
    assert_close(depth_two.expected_rejected_draft_tokens, 0.56);
    assert_close(depth_two.draft_work_units, 0.30);
    assert_close(depth_two.verification_work_units, 0.90);
    assert_close(depth_two.scheduler_work_units, 0.02);
    assert_close(depth_two.total_work_units, 1.22);
    assert_close(depth_two.work_units_per_committed_token, 0.5);
    assert_close(depth_two.ideal_throughput_speedup, 2.0);
    assert_close(depth_two.ideal_work_reduction_fraction, 0.5);
    assert_close(
        depth_two.synchronization_round_reduction_fraction,
        1.0 - 1.0 / 2.44,
    );
    assert_close(
        depth_two
            .homogeneous_acceptance_break_even_probability
            .unwrap(),
        0.185_565_460_040_104_4,
    );
    assert_eq!(scenario.best_proposal_depth, Some(3));
    assert!(scenario.best_ideal_throughput_speedup > 2.0);
}

#[test]
fn no_speculative_depth_is_selected_when_every_depth_regresses() {
    let report = evaluate_glm_mtp_sweep(&request(vec![scenario(
        "zero-acceptance",
        vec![0.0, 0.0, 0.0],
    )]))
    .unwrap();
    let scenario = &report.result.scenarios[0];

    assert_eq!(scenario.best_proposal_depth, None);
    assert_close(scenario.best_ideal_throughput_speedup, 1.0);
    assert!(scenario.depths.iter().all(|depth| !depth.beats_baseline));
}

#[test]
fn modeled_inputs_never_unlock_end_to_end_cost_or_quality_claims() {
    let report =
        evaluate_glm_mtp_sweep(&request(vec![scenario("modeled", vec![0.8, 0.8, 0.8])])).unwrap();

    assert!(!report.result.claims.end_to_end_latency_claim_permitted);
    assert!(!report.result.claims.cost_per_token_claim_permitted);
    assert!(!report.result.claims.quality_claim_permitted);
    assert!(
        report
            .result
            .claims
            .blockers
            .contains(&MtpClaimBlocker::AcceptanceIsNotMeasuredExactCheckpoint)
    );
    assert!(
        report
            .result
            .claims
            .blockers
            .contains(&MtpClaimBlocker::WorkIsNotMeasuredHardware)
    );
    assert!(
        report
            .result
            .claims
            .blockers
            .contains(&MtpClaimBlocker::EndToEndServingNotMeasured)
    );
    assert!(
        report
            .result
            .claims
            .blockers
            .contains(&MtpClaimBlocker::QualityContractNotProvided)
    );
}

#[test]
fn requests_require_valid_hybrid_mtp_models_unique_scenarios_and_probabilities() {
    let mut invalid_model = request(vec![scenario("valid", vec![0.8])]);
    invalid_model.model.architecture = ModelArchitecture::DenseDecoder;
    assert!(evaluate_glm_mtp_sweep(&invalid_model).is_err());

    let mut invalid_probability = request(vec![scenario("invalid", vec![1.01])]);
    assert!(evaluate_glm_mtp_sweep(&invalid_probability).is_err());
    invalid_probability.scenarios[0].conditional_acceptance_probabilities = vec![f64::NAN];
    assert!(evaluate_glm_mtp_sweep(&invalid_probability).is_err());

    let duplicate = request(vec![
        scenario("duplicate", vec![0.8]),
        scenario("duplicate", vec![0.7]),
    ]);
    assert!(evaluate_glm_mtp_sweep(&duplicate).is_err());
}

#[test]
fn report_identity_is_stable_and_detects_tampering() {
    let request = request(vec![scenario("steady", vec![0.8, 0.7])]);
    let first = evaluate_glm_mtp_sweep(&request).unwrap();
    let second = evaluate_glm_mtp_sweep(&request).unwrap();

    assert_eq!(first.content_id, second.content_id);
    assert!(first.verify_content_id().unwrap());
    let mut tampered = first;
    tampered.result.scenarios[0].depths[0].total_work_units += 1.0;
    assert!(!tampered.verify_content_id().unwrap());
}

#[test]
fn checked_in_glm_mtp_study_round_trips_exactly() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let request: GlmMtpSweepRequest =
        serde_json::from_slice(&fs::read(root.join("configs/glm-5.2-mtp-sweep-v1.json")).unwrap())
            .unwrap();
    let stored: GlmMtpSweepReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/mtp-sweep-v1.json")).unwrap(),
    )
    .unwrap();
    let evaluated = evaluate_glm_mtp_sweep(&request).unwrap();

    assert_eq!(evaluated, stored);
    assert!(stored.verify_content_id().unwrap());
    assert_eq!(stored.result.scenarios.len(), 3);
    assert!(
        stored
            .result
            .scenarios
            .iter()
            .all(|scenario| scenario.depths.len() == 4)
    );
    assert!(!stored.result.claims.cost_per_token_claim_permitted);
}

fn request(scenarios: Vec<MtpAcceptanceScenario>) -> GlmMtpSweepRequest {
    let model = glm_5_2_bf16_reference();
    assert!(matches!(
        model.architecture,
        ModelArchitecture::HybridMoeMlaDsa(_)
    ));
    GlmMtpSweepRequest {
        schema_version: GLM_MTP_SWEEP_REQUEST_SCHEMA_VERSION,
        study_id: "glm-5.2-mtp-test".into(),
        model,
        work: MtpWorkAssumptions {
            baseline_target_work_units_per_token: 1.0,
            draft_work_units_per_proposed_token: 0.15,
            verification_fixed_work_units_per_round: 0.80,
            verification_incremental_work_units_per_proposed_token: 0.05,
            scheduler_work_units_per_round: 0.02,
            evidence: MtpEvidence {
                kind: MtpEvidenceKind::ModeledAssumption,
                source_artifact_id: "modeled-mtp-work-v1".into(),
            },
            basis: "Normalized target-decode work units for a deterministic test".into(),
        },
        scenarios,
    }
}

fn scenario(id: &str, probabilities: Vec<f64>) -> MtpAcceptanceScenario {
    MtpAcceptanceScenario {
        scenario_id: id.into(),
        conditional_acceptance_probabilities: probabilities,
        evidence: MtpEvidence {
            kind: MtpEvidenceKind::ModeledAssumption,
            source_artifact_id: format!("{id}-acceptance-v1"),
        },
        basis: "Synthetic conditional acceptance probabilities".into(),
    }
}

fn assert_close(actual: f64, expected: f64) {
    assert!((actual - expected).abs() < 1e-12, "{actual} != {expected}");
}
