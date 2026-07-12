use foundry_core::deployment_screen::{
    BreakEvenHurdleScope, DEPLOYMENT_SCREEN_REQUEST_SCHEMA_VERSION, DeploymentClaimBlocker,
    DeploymentRejectionReason, DeploymentScreenError, DeploymentScreenReport,
    DeploymentScreenRequest, RooflineTimingScope, evaluate_deployment_screen,
};
use foundry_core::glm_storage::{
    DeploymentCapacityStatus, GLM_STORAGE_ENVELOPE_REQUEST_SCHEMA_VERSION,
    GlmStorageEnvelopeReport, GlmStorageEnvelopeRequest, evaluate_glm_storage_envelope,
};
use foundry_core::ledger_roofline::{LedgerRooflineClaimBlocker, LedgerRooflineReport};

const STORAGE_REPORT: &str = include_str!("../../../experiments/glm-5.2/storage-envelope-v1.json");
const STORAGE_CONFIG: &str = include_str!("../../../configs/glm-5.2-storage-envelope-v1.json");
const ROOFLINE_REPORT: &str =
    include_str!("../../../experiments/glm-5.2/decode-ledger-roofline-v1.json");
const OPTIMISTIC_SCREEN_CONFIG: &str =
    include_str!("../../../configs/glm-5.2-h200-optimistic-deployment-screen-v1.json");
const LOWER_WORK_ROOFLINE_REPORT: &str = include_str!(
    "../../../experiments/glm-5.2/whole-decode-lower-bound-throughput-counterfactual-v1.json"
);
const OPTIMISTIC_SCREEN_REPORT: &str =
    include_str!("../../../experiments/glm-5.2/h200-optimistic-deployment-screen-v1.json");

#[test]
fn optimistic_whole_deployment_bound_can_clear_hurdle_without_implying_viability() {
    let storage = storage_report();
    let roofline = roofline_report();
    let request = request(&storage, &roofline);

    let first = evaluate_deployment_screen(&request, &storage, &roofline).unwrap();
    let second = evaluate_deployment_screen(&request, &storage, &roofline).unwrap();

    assert_eq!(first, second);
    assert!(first.verify_content_id().unwrap());
    assert_eq!(
        first.result.capacity_status,
        DeploymentCapacityStatus::Feasible
    );
    assert!(first.result.optimistic_hurdle_cleared);
    assert!(!first.result.candidate_rejected);
    assert!(first.result.rejection_reasons.is_empty());
    assert_eq!(
        first
            .result
            .optimistic_effective_billable_tokens_per_second_upper_bound,
        selected_roofline_tokens_per_second(&roofline)
            * request.billable_tokens_per_committed_output_token
            * request.useful_load_factor
            * request.availability_factor
    );
    assert_eq!(
        first
            .result
            .required_billable_tokens_per_second_for_deployment,
        selected_break_even_hurdle(&storage)
    );
    assert!(first.result.optimistic_headroom_ratio > 1.0);
    assert!(!first.result.claims.business_viability_claim_permitted);
    assert!(!first.result.claims.end_to_end_cost_claim_permitted);
    assert!(!first.result.claims.provider_comparison_claim_permitted);
    assert!(
        first
            .result
            .claims
            .blockers
            .contains(&DeploymentClaimBlocker::OptimisticRejectionBoundOnly)
    );
    assert!(
        first
            .result
            .claims
            .blockers
            .contains(&DeploymentClaimBlocker::InputPrefillWorkTreatedAsFree)
    );
    assert!(
        first
            .result
            .claims
            .blockers
            .contains(&DeploymentClaimBlocker::LedgerContainsModeledWork)
    );
    assert!(
        first
            .result
            .claims
            .blockers
            .contains(&DeploymentClaimBlocker::HardwareTimingIsModeledOrUncalibrated)
    );
}

#[test]
fn optimistic_bound_below_break_even_rejects_candidate() {
    let storage = storage_report();
    let roofline = roofline_report();
    let mut request = request(&storage, &roofline);
    request.billable_tokens_per_committed_output_token = 1.0;
    request.useful_load_factor = 1.0e-12;
    request.break_even_hurdle_scope = BreakEvenHurdleScope::RequiredDeliveredThroughput;

    let report = evaluate_deployment_screen(&request, &storage, &roofline).unwrap();

    assert!(!report.result.optimistic_hurdle_cleared);
    assert!(report.result.candidate_rejected);
    assert_eq!(
        report.result.rejection_reasons,
        vec![DeploymentRejectionReason::OptimisticThroughputBelowBreakEven]
    );
}

#[test]
fn load_and_availability_are_applied_on_exactly_one_side_of_the_hurdle() {
    let storage = storage_report();
    let roofline = roofline_report();
    let hurdle = selected_break_even_hurdle(&storage);
    let useful_load = 0.65;
    let availability = 0.98;
    let peak_rate_per_usd_hour = selected_break_even_rate_per_usd_hour(&storage);
    let delivered_rate_per_usd_hour = peak_rate_per_usd_hour * useful_load * availability;
    assert!((delivered_rate_per_usd_hour - 1_534.888_854_304_064_8).abs() < 1.0e-9);

    let mut request = request(&storage, &roofline);
    request.useful_load_factor = useful_load;
    request.availability_factor = availability;
    request.billable_tokens_per_committed_output_token =
        hurdle * 1.1 / selected_roofline_tokens_per_second(&roofline);
    request.break_even_hurdle_scope =
        BreakEvenHurdleScope::RequiredPeakThroughputAlreadyLoadAdjusted;

    let peak_scoped = evaluate_deployment_screen(&request, &storage, &roofline).unwrap();

    assert!(
        peak_scoped
            .result
            .optimistic_peak_billable_tokens_per_second_upper_bound
            > hurdle
    );
    assert!(
        peak_scoped
            .result
            .optimistic_effective_billable_tokens_per_second_upper_bound
            < hurdle
    );
    assert_eq!(
        peak_scoped
            .result
            .optimistic_billable_tokens_per_second_compared_to_hurdle,
        peak_scoped
            .result
            .optimistic_peak_billable_tokens_per_second_upper_bound
    );
    assert!(peak_scoped.result.optimistic_hurdle_cleared);

    request.break_even_hurdle_scope = BreakEvenHurdleScope::RequiredDeliveredThroughput;
    let delivered_scoped = evaluate_deployment_screen(&request, &storage, &roofline).unwrap();

    assert_eq!(
        delivered_scoped
            .result
            .optimistic_billable_tokens_per_second_compared_to_hurdle,
        delivered_scoped
            .result
            .optimistic_effective_billable_tokens_per_second_upper_bound
    );
    assert!(!delivered_scoped.result.optimistic_hurdle_cleared);
}

#[test]
fn uncertain_and_infeasible_capacity_fail_closed() {
    for (device_count, expected_status, expected_reason) in [
        (
            16,
            DeploymentCapacityStatus::Uncertain,
            DeploymentRejectionReason::CapacityUncertain,
        ),
        (
            1,
            DeploymentCapacityStatus::Infeasible,
            DeploymentRejectionReason::CapacityInfeasible,
        ),
    ] {
        let storage = storage_report_with_h200_device_count(device_count);
        let roofline = roofline_report();
        let mut request = request(&storage, &roofline);
        set_passing_billable_ratio(&mut request, &storage, &roofline, 1.0);

        let report = evaluate_deployment_screen(&request, &storage, &roofline).unwrap();

        assert_eq!(report.result.capacity_status, expected_status);
        assert!(report.result.optimistic_hurdle_cleared);
        assert!(report.result.candidate_rejected);
        assert_eq!(report.result.rejection_reasons, vec![expected_reason]);
    }
}

#[test]
fn per_rank_scope_requires_exact_deployment_mapping_and_is_explicitly_optimistic() {
    let storage = storage_report();
    let roofline = roofline_report();
    let mut request = request(&storage, &roofline);
    request.timing_scope = RooflineTimingScope::PerRank { rank_count: 20 };

    let report = evaluate_deployment_screen(&request, &storage, &roofline).unwrap();

    assert_eq!(
        report
            .result
            .optimistic_effective_billable_tokens_per_second_upper_bound,
        selected_roofline_tokens_per_second(&roofline)
            * 20.0
            * request.billable_tokens_per_committed_output_token
            * request.useful_load_factor
            * request.availability_factor
    );
    assert!(
        report
            .result
            .claims
            .blockers
            .contains(&DeploymentClaimBlocker::PerRankLinearScalingAssumption)
    );

    request.timing_scope = RooflineTimingScope::PerRank { rank_count: 19 };
    assert!(matches!(
        evaluate_deployment_screen(&request, &storage, &roofline),
        Err(DeploymentScreenError::RankCountMismatch {
            expected: 20,
            actual: 19
        })
    ));
}

#[test]
fn report_identity_pins_and_selected_ids_are_fail_closed() {
    let storage = storage_report();
    let roofline = roofline_report();

    let mut wrong_pin = request(&storage, &roofline);
    wrong_pin.storage_report_content_id = "wrong".into();
    assert!(matches!(
        evaluate_deployment_screen(&wrong_pin, &storage, &roofline),
        Err(DeploymentScreenError::StorageArtifactIdentityMismatch)
    ));

    let mut tampered = roofline.clone();
    tampered.result.hardware[0].optimistic_committed_tokens_per_second += 1.0;
    assert!(matches!(
        evaluate_deployment_screen(&request(&storage, &tampered), &storage, &tampered),
        Err(DeploymentScreenError::InvalidRooflineArtifactIdentity)
    ));

    for (variant_id, storage_hardware_id, roofline_hardware_id, expected) in [
        (
            "missing",
            "fireworks-h200-141gb-20x",
            "glm-dsa-moe-custom-upper-bound",
            0,
        ),
        (
            "glm-5.2-bf16",
            "missing",
            "glm-dsa-moe-custom-upper-bound",
            1,
        ),
        ("glm-5.2-bf16", "fireworks-h200-141gb-20x", "missing", 2),
    ] {
        let mut missing = request(&storage, &roofline);
        missing.variant_id = variant_id.into();
        missing.storage_hardware_id = storage_hardware_id.into();
        missing.roofline_hardware_id = roofline_hardware_id.into();
        let error = evaluate_deployment_screen(&missing, &storage, &roofline).unwrap_err();
        assert!(matches!(
            (expected, error),
            (0, DeploymentScreenError::UnknownVariant(_))
                | (1, DeploymentScreenError::UnknownStorageHardware(_))
                | (2, DeploymentScreenError::UnknownRooflineHardware(_))
        ));
    }
}

#[test]
fn mapping_factors_and_break_even_hurdle_are_required() {
    let storage = storage_report();
    let roofline = roofline_report();

    for update in [
        |request: &mut DeploymentScreenRequest| {
            request.billable_tokens_per_committed_output_token = 0.5
        },
        |request: &mut DeploymentScreenRequest| request.useful_load_factor = 0.0,
        |request: &mut DeploymentScreenRequest| request.useful_load_factor = 1.1,
        |request: &mut DeploymentScreenRequest| request.availability_factor = f64::NAN,
    ] {
        let mut invalid = request(&storage, &roofline);
        update(&mut invalid);
        assert!(matches!(
            evaluate_deployment_screen(&invalid, &storage, &roofline),
            Err(DeploymentScreenError::InvalidField(_))
        ));
    }

    let mut config: GlmStorageEnvelopeRequest = serde_json::from_str(STORAGE_CONFIG).unwrap();
    assert_eq!(
        config.schema_version,
        GLM_STORAGE_ENVELOPE_REQUEST_SCHEMA_VERSION
    );
    config.break_even = None;
    let no_hurdle = evaluate_glm_storage_envelope(&config).unwrap();
    let mut no_hurdle_request = request(&storage, &roofline);
    no_hurdle_request.storage_report_content_id = no_hurdle.content_id.clone();
    assert!(matches!(
        evaluate_deployment_screen(&no_hurdle_request, &no_hurdle, &roofline),
        Err(DeploymentScreenError::MissingBreakEvenHurdle)
    ));
}

#[test]
fn prefill_inclusion_removes_only_the_free_prefill_blocker() {
    let storage = storage_report();
    let roofline = roofline_report();
    let mut request = request(&storage, &roofline);
    request.input_prefill_work_included_in_roofline = true;

    let report = evaluate_deployment_screen(&request, &storage, &roofline).unwrap();

    assert!(
        !report
            .result
            .claims
            .blockers
            .contains(&DeploymentClaimBlocker::InputPrefillWorkTreatedAsFree)
    );
    assert!(
        report
            .result
            .claims
            .source_roofline_blockers
            .contains(&LedgerRooflineClaimBlocker::LedgerContainsAssumptions)
    );
    assert!(!report.result.claims.end_to_end_cost_claim_permitted);
    assert!(!report.result.claims.business_viability_claim_permitted);
}

#[test]
fn checked_optimistic_h200_screen_round_trips_and_does_not_imply_viability() {
    let storage = storage_report();
    let roofline: LedgerRooflineReport = serde_json::from_str(LOWER_WORK_ROOFLINE_REPORT).unwrap();
    let request: DeploymentScreenRequest = serde_json::from_str(OPTIMISTIC_SCREEN_CONFIG).unwrap();
    let stored: DeploymentScreenReport = serde_json::from_str(OPTIMISTIC_SCREEN_REPORT).unwrap();
    let evaluated = evaluate_deployment_screen(&request, &storage, &roofline).unwrap();

    assert_eq!(evaluated, stored);
    assert!(stored.verify_content_id().unwrap());
    assert!(stored.result.optimistic_hurdle_cleared);
    assert!(stored.result.optimistic_headroom_ratio > 1.08);
    assert!(stored.result.optimistic_headroom_ratio < 1.081);
    assert!(!stored.result.claims.business_viability_claim_permitted);
    assert!(!stored.result.claims.end_to_end_cost_claim_permitted);
    assert!(!stored.result.claims.provider_comparison_claim_permitted);
}

fn request(
    storage: &GlmStorageEnvelopeReport,
    roofline: &LedgerRooflineReport,
) -> DeploymentScreenRequest {
    let mut request = DeploymentScreenRequest {
        schema_version: DEPLOYMENT_SCREEN_REQUEST_SCHEMA_VERSION,
        screen_id: "glm-5.2-h200-custom-screen".into(),
        storage_report_content_id: storage.content_id.clone(),
        roofline_report_content_id: roofline.content_id.clone(),
        variant_id: "glm-5.2-bf16".into(),
        storage_hardware_id: "fireworks-h200-141gb-20x".into(),
        roofline_hardware_id: "glm-dsa-moe-custom-upper-bound".into(),
        timing_scope: RooflineTimingScope::WholeDeployment,
        break_even_hurdle_scope: BreakEvenHurdleScope::RequiredPeakThroughputAlreadyLoadAdjusted,
        billable_tokens_per_committed_output_token: 1.0,
        useful_load_factor: 0.9,
        availability_factor: 0.95,
        input_prefill_work_included_in_roofline: false,
        mapping_source_artifact_id: "deployment-screen-test-assumptions".into(),
    };
    set_passing_billable_ratio(&mut request, storage, roofline, 1.0);
    request
}

fn storage_report() -> GlmStorageEnvelopeReport {
    serde_json::from_str(STORAGE_REPORT).unwrap()
}

fn roofline_report() -> LedgerRooflineReport {
    serde_json::from_str(ROOFLINE_REPORT).unwrap()
}

fn storage_report_with_h200_device_count(device_count: u32) -> GlmStorageEnvelopeReport {
    let mut config: GlmStorageEnvelopeRequest = serde_json::from_str(STORAGE_CONFIG).unwrap();
    let hardware = config
        .hardware
        .iter_mut()
        .find(|hardware| hardware.hardware_id == "fireworks-h200-141gb-20x")
        .unwrap();
    hardware.deployment_device_count = device_count;
    evaluate_glm_storage_envelope(&config).unwrap()
}

fn selected_roofline_tokens_per_second(roofline: &LedgerRooflineReport) -> f64 {
    roofline
        .result
        .hardware
        .iter()
        .find(|hardware| hardware.hardware_id == "glm-dsa-moe-custom-upper-bound")
        .unwrap()
        .optimistic_committed_tokens_per_second
}

fn selected_break_even_hurdle(storage: &GlmStorageEnvelopeReport) -> f64 {
    storage
        .result
        .variants
        .iter()
        .find(|variant| variant.variant_id == "glm-5.2-bf16")
        .unwrap()
        .hardware
        .iter()
        .find(|hardware| hardware.hardware_id == "fireworks-h200-141gb-20x")
        .unwrap()
        .break_even
        .as_ref()
        .unwrap()
        .required_billable_tokens_per_second_for_deployment
}

fn selected_break_even_rate_per_usd_hour(storage: &GlmStorageEnvelopeReport) -> f64 {
    storage
        .result
        .variants
        .iter()
        .find(|variant| variant.variant_id == "glm-5.2-bf16")
        .unwrap()
        .hardware
        .iter()
        .find(|hardware| hardware.hardware_id == "fireworks-h200-141gb-20x")
        .unwrap()
        .break_even
        .as_ref()
        .unwrap()
        .assumption
        .required_billable_tokens_per_second_per_usd_of_hourly_system_cost
}

fn set_passing_billable_ratio(
    request: &mut DeploymentScreenRequest,
    storage: &GlmStorageEnvelopeReport,
    roofline: &LedgerRooflineReport,
    scope_multiplier: f64,
) {
    let hurdle_scope_multiplier = match request.break_even_hurdle_scope {
        BreakEvenHurdleScope::RequiredPeakThroughputAlreadyLoadAdjusted => 1.0,
        BreakEvenHurdleScope::RequiredDeliveredThroughput => {
            request.useful_load_factor * request.availability_factor
        }
    };
    let adjusted_tokens_per_second =
        selected_roofline_tokens_per_second(roofline) * scope_multiplier * hurdle_scope_multiplier;
    request.billable_tokens_per_committed_output_token =
        (selected_break_even_hurdle(storage) * 2.0 / adjusted_tokens_per_second).max(1.0);
}
