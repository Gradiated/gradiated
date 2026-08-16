use foundry_core::deployment_screen::{DeploymentScreenReport, DeploymentScreenResult};
use foundry_core::economic_frontier::{
    AcceleratorCostCase, AvailabilityCase, ECONOMIC_FRONTIER_REQUEST_SCHEMA_VERSION,
    EconomicFrontierClaimBlocker, EconomicFrontierError, EconomicFrontierPointStatus,
    EconomicFrontierRegionStatus, EconomicFrontierReport, EconomicFrontierRequest,
    FrontierEvidence, FrontierEvidenceKind, GrossMarginCase, SourceStackFeatureCoverage,
    ThroughputHaircutCase, TokenPriceBenchmark, UsefulLoadCase, WorkBoundCase, WorkloadMix,
    evaluate_economic_frontier,
};
use foundry_core::glm_storage::DeploymentCapacityStatus;
use serde::Serialize;

const SOURCE_SCREEN: &str =
    include_str!("../../../experiments/glm-5.2/h200-optimistic-deployment-screen-v1.json");
const CHECKED_CONFIG: &str =
    include_str!("../../../configs/glm-5.2-economic-robustness-frontier-v1.json");
const CHECKED_REPORT: &str =
    include_str!("../../../experiments/glm-5.2/economic-robustness-frontier-v1.json");

#[test]
fn frontier_math_reconciles_and_load_and_availability_are_applied_once() {
    let source = source_screen();
    let mut request = request(1, 1, &source);
    request.workload_mixes[0] = mix("canonical", 0.12, 0.82, 0.06);
    request.useful_load_cases[0].useful_load_factor = 0.5;
    request.availability_cases[0].availability_factor = 0.9;
    request.accelerator_cost_cases[0].accelerator_usd_per_device_hour = 7.0;
    request.accelerator_cost_cases[0].fixed_non_accelerator_usd_per_deployment_hour = 10.0;
    request.gross_margin_cases[0].required_gross_margin = 0.6;
    request.throughput_haircut_cases[0].throughput_haircut_factor = 0.75;
    request.work_bound_cases[0].uncached_input_work_units_per_token = 0.2;
    request.work_bound_cases[0].cached_input_work_units_per_token = 0.02;

    let report = evaluate_economic_frontier(&request, &source).unwrap();
    let point = &report.result.points[0];
    let source_peak = source
        .result
        .roofline_optimistic_committed_output_tokens_per_second
        * 20.0;
    let average_work = 0.12 * 0.2 + 0.82 * 0.02 + 0.06;
    let peak_billable = source_peak * 0.75 / average_work;
    let delivered = peak_billable * 0.5 * 0.9;
    let hourly_cost = 20.0 * 7.0 + 10.0;
    let blended_list_price = 0.12 * 1.4 + 0.82 * 0.14 + 0.06 * 4.4;
    let customer_price = blended_list_price * 0.8;
    let cogs_ceiling = customer_price * 0.4;
    let required_delivered = 1_000_000.0 * hourly_cost / (3_600.0 * cogs_ceiling);
    let headroom = delivered / required_delivered;

    assert_close(
        report
            .result
            .source
            .source_peak_committed_output_tokens_per_second_per_deployment,
        source_peak,
    );
    assert_close(point.average_work_units_per_billable_token, average_work);
    assert_close(point.modeled_peak_billable_tokens_per_second, peak_billable);
    assert_close(
        point.modeled_delivered_billable_tokens_per_second,
        delivered,
    );
    assert_close(
        point.modeled_delivered_billable_tokens_per_second
            / point.modeled_peak_billable_tokens_per_second,
        0.45,
    );
    assert_close(point.total_hourly_deployment_cost_usd, hourly_cost);
    assert_close(
        point.blended_benchmark_list_price_usd_per_million_tokens,
        blended_list_price,
    );
    assert_close(
        point.modeled_customer_price_usd_per_million_tokens,
        customer_price,
    );
    assert_close(
        point.maximum_cogs_usd_per_million_tokens_at_required_margin,
        cogs_ceiling,
    );
    assert_close(
        point.required_delivered_billable_tokens_per_second,
        required_delivered,
    );
    assert_close(point.modeled_headroom_ratio, headroom);
    assert_close(
        point.modeled_headroom_ratio,
        point.modeled_delivered_billable_tokens_per_second
            / point.required_delivered_billable_tokens_per_second,
    );
    assert_close(
        point.modeled_headroom_ratio,
        point.maximum_total_hourly_deployment_cost_usd / point.total_hourly_deployment_cost_usd,
    );
    assert_close(
        point.modeled_headroom_ratio,
        point.maximum_cogs_usd_per_million_tokens_at_required_margin
            / point.modeled_cogs_usd_per_million_delivered_tokens,
    );
    assert_close(
        point.modeled_headroom_ratio,
        point.source_peak_committed_output_tokens_per_second_per_deployment
            / point.minimum_source_peak_output_tokens_per_second,
    );
}

#[test]
fn full_cartesian_sweep_has_exact_point_and_region_counts() {
    let source = source_screen();
    let request = request(2, 3, &source);

    let report = evaluate_economic_frontier(&request, &source).unwrap();

    assert_eq!(report.result.summary.point_count, 4_374);
    assert_eq!(report.result.summary.region_count, 54);
    assert_eq!(report.result.points.len(), 4_374);
    assert_eq!(report.result.regions.len(), 54);
    assert!(
        report
            .result
            .regions
            .iter()
            .all(|region| region.point_count == 81)
    );
}

#[test]
fn statuses_are_fail_closed_and_regions_only_describe_the_configured_sweep() {
    let mut source = source_screen();
    source.result.capacity_status = DeploymentCapacityStatus::Uncertain;
    rehash_source(&mut source);
    let request = request(1, 1, &source);

    let report = evaluate_economic_frontier(&request, &source).unwrap();

    assert_eq!(
        report.result.points[0].status,
        EconomicFrontierPointStatus::SourceCapacityNotFeasible
    );
    assert!(!report.result.points[0].modeled_required_margin_cleared);
    assert_eq!(
        report.result.regions[0].status,
        EconomicFrontierRegionStatus::NoMarginClearance
    );
    assert!(!report.result.claims.business_viability_claim_permitted);
    assert!(!report.result.claims.provider_comparison_claim_permitted);
    assert!(!report.result.claims.end_to_end_cost_claim_permitted);
}

#[test]
fn claim_gate_blocks_price_surface_from_becoming_a_performance_baseline() {
    let source = source_screen();
    let request = request(1, 1, &source);

    let report = evaluate_economic_frontier(&request, &source).unwrap();
    let blockers = &report.result.claims.blockers;

    assert!(
        blockers.contains(
            &EconomicFrontierClaimBlocker::SourceDoesNotProveCurrentIncumbentCombinedStack
        )
    );
    assert!(
        blockers.contains(
            &EconomicFrontierClaimBlocker::ProviderPriceBenchmarkIsNotPerformanceBaseline
        )
    );
    assert!(
        blockers
            .contains(&EconomicFrontierClaimBlocker::ProviderPricesArePublicListNotContractPrices)
    );
    assert!(
        blockers.contains(
            &EconomicFrontierClaimBlocker::SourcePeakThroughputIsOptimisticAndUncalibrated
        )
    );
}

#[test]
fn invalid_dimensions_and_artifact_identities_are_rejected() {
    let source = source_screen();

    let mut bad_mix = request(1, 1, &source);
    bad_mix.workload_mixes[0].output_share = 0.5;
    assert!(matches!(
        evaluate_economic_frontier(&bad_mix, &source),
        Err(EconomicFrontierError::InvalidField(_))
    ));

    let mut duplicate_id = request(1, 1, &source);
    duplicate_id
        .useful_load_cases
        .push(duplicate_id.useful_load_cases[0].clone());
    assert!(matches!(
        evaluate_economic_frontier(&duplicate_id, &source),
        Err(EconomicFrontierError::DuplicateCaseId(_))
    ));

    let mut invalid_factor = request(1, 1, &source);
    invalid_factor.availability_cases[0].availability_factor = 0.0;
    assert!(matches!(
        evaluate_economic_frontier(&invalid_factor, &source),
        Err(EconomicFrontierError::InvalidField(_))
    ));

    let mut invalid_margin = request(1, 1, &source);
    invalid_margin.gross_margin_cases[0].required_gross_margin = 1.0;
    assert!(matches!(
        evaluate_economic_frontier(&invalid_margin, &source),
        Err(EconomicFrontierError::InvalidField(_))
    ));

    let mut wrong_pin = request(1, 1, &source);
    wrong_pin.source_deployment_screen_content_id = "wrong".into();
    assert!(matches!(
        evaluate_economic_frontier(&wrong_pin, &source),
        Err(EconomicFrontierError::SourceArtifactIdentityMismatch)
    ));

    let mut tampered_source = source.clone();
    tampered_source
        .result
        .roofline_optimistic_committed_output_tokens_per_second += 1.0;
    assert!(matches!(
        evaluate_economic_frontier(&request(1, 1, &tampered_source), &tampered_source),
        Err(EconomicFrontierError::InvalidSourceArtifactIdentity)
    ));

    let mut value = serde_json::to_value(request(1, 1, &source)).unwrap();
    value["unknown"] = serde_json::json!(true);
    assert!(serde_json::from_value::<EconomicFrontierRequest>(value).is_err());
}

#[test]
fn report_identity_is_stable_and_detects_tampering() {
    let source = source_screen();
    let request = request(1, 1, &source);

    let first = evaluate_economic_frontier(&request, &source).unwrap();
    let second = evaluate_economic_frontier(&request, &source).unwrap();

    assert_eq!(first, second);
    assert!(first.verify_content_id().unwrap());
    let mut tampered = first;
    tampered.result.points[0].modeled_headroom_ratio += 1.0;
    assert!(!tampered.verify_content_id().unwrap());
}

#[test]
fn checked_frontier_round_trips_without_permitting_business_claims() {
    let source = source_screen();
    let request: EconomicFrontierRequest = serde_json::from_str(CHECKED_CONFIG).unwrap();
    let stored: EconomicFrontierReport = serde_json::from_str(CHECKED_REPORT).unwrap();

    let evaluated = evaluate_economic_frontier(&request, &source).unwrap();

    assert_eq!(evaluated, stored);
    assert!(stored.verify_content_id().unwrap());
    assert_eq!(stored.result.summary.point_count, 4_374);
    assert_eq!(stored.result.summary.region_count, 54);
    assert!(!stored.result.claims.business_viability_claim_permitted);
    assert!(!stored.result.claims.provider_comparison_claim_permitted);
    assert!(!stored.result.claims.end_to_end_cost_claim_permitted);
}

fn request(
    benchmark_count: usize,
    cases_per_dimension: usize,
    source: &DeploymentScreenReport,
) -> EconomicFrontierRequest {
    EconomicFrontierRequest {
        schema_version: ECONOMIC_FRONTIER_REQUEST_SCHEMA_VERSION,
        study_id: "glm-5.2-economic-frontier-test".into(),
        source_deployment_screen_content_id: source.content_id.clone(),
        benchmark_prices: benchmarks(benchmark_count),
        customer_price_fraction_of_benchmark: 0.8,
        customer_price_evidence: modeled("customer-price-fraction"),
        workload_mixes: workload_mixes(cases_per_dimension),
        useful_load_cases: useful_load_cases(cases_per_dimension),
        availability_cases: availability_cases(cases_per_dimension),
        accelerator_cost_cases: accelerator_cost_cases(cases_per_dimension),
        gross_margin_cases: gross_margin_cases(cases_per_dimension),
        throughput_haircut_cases: throughput_haircut_cases(cases_per_dimension),
        work_bound_cases: work_bound_cases(cases_per_dimension),
        source_stack_feature_coverage: SourceStackFeatureCoverage {
            shared_dsa: false,
            qualified_nvfp4: false,
            fp8_kv_cache: false,
            kv_aware_routing: false,
            prefill_decode_disaggregation: false,
            mtp: false,
            evidence: modeled("source-stack-coverage"),
        },
        configured_headroom_threshold: 1.25,
        assumptions_source_artifact_id: "economic-frontier-test-assumptions".into(),
    }
}

fn benchmarks(count: usize) -> Vec<TokenPriceBenchmark> {
    [
        TokenPriceBenchmark {
            benchmark_id: "fireworks-standard".into(),
            provider: "Fireworks".into(),
            serving_path: "standard".into(),
            uncached_input_usd_per_million_tokens: 1.4,
            cached_input_usd_per_million_tokens: 0.14,
            output_usd_per_million_tokens: 4.4,
            evidence: public_price("fireworks-price"),
        },
        TokenPriceBenchmark {
            benchmark_id: "baseten-model-api".into(),
            provider: "Baseten".into(),
            serving_path: "model_api".into(),
            uncached_input_usd_per_million_tokens: 1.4,
            cached_input_usd_per_million_tokens: 0.26,
            output_usd_per_million_tokens: 4.4,
            evidence: public_price("baseten-price"),
        },
    ][..count]
        .to_vec()
}

fn workload_mixes(count: usize) -> Vec<WorkloadMix> {
    [
        mix("canonical", 0.12, 0.82, 0.06),
        mix("cache-poor", 0.47, 0.47, 0.06),
        mix("shorter-agent", 0.05, 0.15, 0.8),
    ][..count]
        .to_vec()
}

fn useful_load_cases(count: usize) -> Vec<UsefulLoadCase> {
    [0.4, 0.65, 0.8][..count]
        .iter()
        .enumerate()
        .map(|(index, value)| UsefulLoadCase {
            case_id: format!("load-{index}"),
            useful_load_factor: *value,
            evidence: modeled("useful-load"),
        })
        .collect()
}

fn availability_cases(count: usize) -> Vec<AvailabilityCase> {
    [0.95, 0.98, 0.995][..count]
        .iter()
        .enumerate()
        .map(|(index, value)| AvailabilityCase {
            case_id: format!("availability-{index}"),
            availability_factor: *value,
            evidence: modeled("availability"),
        })
        .collect()
}

fn accelerator_cost_cases(count: usize) -> Vec<AcceleratorCostCase> {
    [3.0, 7.0, 10.0][..count]
        .iter()
        .enumerate()
        .map(|(index, value)| AcceleratorCostCase {
            case_id: format!("cost-{index}"),
            accelerator_usd_per_device_hour: *value,
            fixed_non_accelerator_usd_per_deployment_hour: 0.0,
            evidence: modeled("accelerator-cost"),
        })
        .collect()
}

fn gross_margin_cases(count: usize) -> Vec<GrossMarginCase> {
    [0.5, 0.6, 0.7][..count]
        .iter()
        .enumerate()
        .map(|(index, value)| GrossMarginCase {
            case_id: format!("margin-{index}"),
            required_gross_margin: *value,
        })
        .collect()
}

fn throughput_haircut_cases(count: usize) -> Vec<ThroughputHaircutCase> {
    [0.5, 0.75, 1.0][..count]
        .iter()
        .enumerate()
        .map(|(index, value)| ThroughputHaircutCase {
            case_id: format!("haircut-{index}"),
            throughput_haircut_factor: *value,
            evidence: modeled("throughput-haircut"),
        })
        .collect()
}

fn work_bound_cases(count: usize) -> Vec<WorkBoundCase> {
    [(0.0, 0.0), (0.1, 0.01), (0.25, 0.05)][..count]
        .iter()
        .enumerate()
        .map(|(index, (uncached, cached))| WorkBoundCase {
            case_id: format!("work-{index}"),
            uncached_input_work_units_per_token: *uncached,
            cached_input_work_units_per_token: *cached,
            evidence: modeled("work-bound"),
        })
        .collect()
}

fn mix(id: &str, uncached: f64, cached: f64, output: f64) -> WorkloadMix {
    WorkloadMix {
        mix_id: id.into(),
        uncached_input_share: uncached,
        cached_input_share: cached,
        output_share: output,
        evidence: modeled("workload-mix"),
    }
}

fn modeled(source: &str) -> FrontierEvidence {
    FrontierEvidence {
        kind: FrontierEvidenceKind::ModeledAssumption,
        source_artifact_id: source.into(),
    }
}

fn public_price(source: &str) -> FrontierEvidence {
    FrontierEvidence {
        kind: FrontierEvidenceKind::PublicListPrice,
        source_artifact_id: source.into(),
    }
}

fn source_screen() -> DeploymentScreenReport {
    serde_json::from_str(SOURCE_SCREEN).unwrap()
}

fn rehash_source(source: &mut DeploymentScreenReport) {
    #[derive(Serialize)]
    struct HashableSource<'a> {
        schema_version: u32,
        result: &'a DeploymentScreenResult,
    }

    let bytes = serde_json::to_vec(&HashableSource {
        schema_version: source.schema_version,
        result: &source.result,
    })
    .unwrap();
    source.content_id = blake3::hash(&bytes).to_hex().to_string();
}

fn assert_close(actual: f64, expected: f64) {
    let scale = actual.abs().max(expected.abs()).max(1.0);
    assert!(
        (actual - expected).abs() <= 1.0e-12 * scale,
        "{actual} != {expected}"
    );
}
