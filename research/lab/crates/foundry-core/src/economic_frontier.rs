use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::deployment_screen::{
    DEPLOYMENT_SCREEN_REPORT_SCHEMA_VERSION, DeploymentClaimBlocker, DeploymentScreenError,
    DeploymentScreenReport, RooflineTimingScope,
};
use crate::glm_storage::DeploymentCapacityStatus;

pub const ECONOMIC_FRONTIER_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const ECONOMIC_FRONTIER_REPORT_SCHEMA_VERSION: u32 = 1;

const TOKENS_PER_MILLION: f64 = 1_000_000.0;
const SECONDS_PER_HOUR: f64 = 3_600.0;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum FrontierEvidenceKind {
    PublicListPrice,
    PinnedDerivedArtifact,
    ModeledAssumption,
    Measured,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FrontierEvidence {
    pub kind: FrontierEvidenceKind,
    pub source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TokenPriceBenchmark {
    pub benchmark_id: String,
    pub provider: String,
    pub serving_path: String,
    pub uncached_input_usd_per_million_tokens: f64,
    pub cached_input_usd_per_million_tokens: f64,
    pub output_usd_per_million_tokens: f64,
    pub evidence: FrontierEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WorkloadMix {
    pub mix_id: String,
    pub uncached_input_share: f64,
    pub cached_input_share: f64,
    pub output_share: f64,
    pub evidence: FrontierEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct UsefulLoadCase {
    pub case_id: String,
    pub useful_load_factor: f64,
    pub evidence: FrontierEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AvailabilityCase {
    pub case_id: String,
    pub availability_factor: f64,
    pub evidence: FrontierEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AcceleratorCostCase {
    pub case_id: String,
    pub accelerator_usd_per_device_hour: f64,
    pub fixed_non_accelerator_usd_per_deployment_hour: f64,
    pub evidence: FrontierEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GrossMarginCase {
    pub case_id: String,
    pub required_gross_margin: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ThroughputHaircutCase {
    pub case_id: String,
    pub throughput_haircut_factor: f64,
    pub evidence: FrontierEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WorkBoundCase {
    pub case_id: String,
    pub uncached_input_work_units_per_token: f64,
    pub cached_input_work_units_per_token: f64,
    pub evidence: FrontierEvidence,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SourceStackFeatureCoverage {
    pub shared_dsa: bool,
    pub qualified_nvfp4: bool,
    pub fp8_kv_cache: bool,
    pub kv_aware_routing: bool,
    pub prefill_decode_disaggregation: bool,
    pub mtp: bool,
    pub evidence: FrontierEvidence,
}

impl SourceStackFeatureCoverage {
    fn proves_current_incumbent_combined_stack(&self) -> bool {
        self.shared_dsa
            && self.qualified_nvfp4
            && self.fp8_kv_cache
            && self.kv_aware_routing
            && self.prefill_decode_disaggregation
            && self.mtp
            && self.evidence.kind == FrontierEvidenceKind::Measured
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomicFrontierRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub source_deployment_screen_content_id: String,
    pub benchmark_prices: Vec<TokenPriceBenchmark>,
    pub customer_price_fraction_of_benchmark: f64,
    pub customer_price_evidence: FrontierEvidence,
    pub workload_mixes: Vec<WorkloadMix>,
    pub useful_load_cases: Vec<UsefulLoadCase>,
    pub availability_cases: Vec<AvailabilityCase>,
    pub accelerator_cost_cases: Vec<AcceleratorCostCase>,
    pub gross_margin_cases: Vec<GrossMarginCase>,
    pub throughput_haircut_cases: Vec<ThroughputHaircutCase>,
    pub work_bound_cases: Vec<WorkBoundCase>,
    pub source_stack_feature_coverage: SourceStackFeatureCoverage,
    pub configured_headroom_threshold: f64,
    pub assumptions_source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomicFrontierSource {
    pub source_deployment_screen_content_id: String,
    pub source_screen_id: String,
    pub variant_id: String,
    pub storage_hardware_id: String,
    pub roofline_hardware_id: String,
    pub deployment_device_count: u32,
    pub capacity_status: DeploymentCapacityStatus,
    pub timing_scope: RooflineTimingScope,
    pub roofline_optimistic_committed_output_tokens_per_second_per_timing_scope: f64,
    pub source_peak_committed_output_tokens_per_second_per_deployment: f64,
    pub mapping_source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomicFrontierPointKey {
    pub benchmark_id: String,
    pub mix_id: String,
    pub useful_load_case_id: String,
    pub availability_case_id: String,
    pub accelerator_cost_case_id: String,
    pub gross_margin_case_id: String,
    pub throughput_haircut_case_id: String,
    pub work_bound_case_id: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EconomicFrontierPointStatus {
    SourceCapacityNotFeasible,
    BelowRequiredMargin,
    ClearsRequiredMarginBelowHeadroomThreshold,
    ClearsConfiguredHeadroomThreshold,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomicFrontierPoint {
    pub key: EconomicFrontierPointKey,
    pub source_peak_committed_output_tokens_per_second_per_deployment: f64,
    pub throughput_haircut_factor: f64,
    pub haircut_adjusted_peak_output_tokens_per_second: f64,
    pub average_work_units_per_billable_token: f64,
    pub modeled_peak_billable_tokens_per_second: f64,
    pub useful_load_factor: f64,
    pub availability_factor: f64,
    pub modeled_delivered_billable_tokens_per_second: f64,
    pub accelerator_usd_per_device_hour: f64,
    pub fixed_non_accelerator_usd_per_deployment_hour: f64,
    pub total_hourly_deployment_cost_usd: f64,
    pub blended_benchmark_list_price_usd_per_million_tokens: f64,
    pub customer_price_fraction_of_benchmark: f64,
    pub modeled_customer_price_usd_per_million_tokens: f64,
    pub required_gross_margin: f64,
    pub maximum_cogs_usd_per_million_tokens_at_required_margin: f64,
    pub modeled_cogs_usd_per_million_delivered_tokens: f64,
    pub modeled_gross_margin: f64,
    pub required_delivered_billable_tokens_per_second: f64,
    pub modeled_headroom_ratio: f64,
    pub maximum_total_hourly_deployment_cost_usd: f64,
    pub maximum_accelerator_usd_per_device_hour: Option<f64>,
    pub minimum_source_peak_output_tokens_per_second: f64,
    pub required_useful_load_availability_product: f64,
    pub minimum_required_throughput_haircut_factor: f64,
    pub maximum_average_work_units_per_billable_token: f64,
    pub modeled_required_margin_cleared: bool,
    pub status: EconomicFrontierPointStatus,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomicFrontierRegionKey {
    pub benchmark_id: String,
    pub mix_id: String,
    pub throughput_haircut_case_id: String,
    pub work_bound_case_id: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EconomicFrontierRegionStatus {
    NoMarginClearance,
    MixedMarginClearance,
    ClearsMarginAcrossSweepBelowHeadroomThreshold,
    ClearsHeadroomThresholdAcrossSweep,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomicFrontierRegion {
    pub key: EconomicFrontierRegionKey,
    pub point_count: u64,
    pub required_margin_clearance_count: u64,
    pub configured_headroom_clearance_count: u64,
    pub required_margin_clearance_fraction: f64,
    pub configured_headroom_clearance_fraction: f64,
    pub minimum_modeled_headroom_ratio: f64,
    pub maximum_modeled_headroom_ratio: f64,
    pub status: EconomicFrontierRegionStatus,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomicFrontierSummary {
    pub point_count: u64,
    pub region_count: u64,
    pub source_capacity_not_feasible_point_count: u64,
    pub below_required_margin_point_count: u64,
    pub clears_required_margin_below_threshold_point_count: u64,
    pub clears_configured_headroom_threshold_point_count: u64,
    pub no_margin_clearance_region_count: u64,
    pub mixed_margin_clearance_region_count: u64,
    pub clears_margin_across_sweep_below_threshold_region_count: u64,
    pub clears_headroom_threshold_across_sweep_region_count: u64,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EconomicFrontierClaimBlocker {
    SourceDeploymentScreenClaimsAreBlocked,
    SourcePeakThroughputIsOptimisticAndUncalibrated,
    SourceDoesNotProveCurrentIncumbentCombinedStack,
    ProviderPriceBenchmarkIsNotPerformanceBaseline,
    ProviderPricesArePublicListNotContractPrices,
    CustomerPriceFractionIsModeled,
    WorkloadMixesAreModeled,
    UsefulLoadAndAvailabilityAreModeled,
    AcceleratorCostsAreModeled,
    ThroughputHaircutsAreModeled,
    InputWorkBoundsAreModeled,
    SourceCapacityOrMappingIsNotValidatedEndToEnd,
    ServingSloAndQueueingAreNotValidated,
    QualityContractIsNotValidated,
    NreAndProviderProductOverheadAreExcluded,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomicFrontierClaimGate {
    pub business_viability_claim_permitted: bool,
    pub provider_comparison_claim_permitted: bool,
    pub end_to_end_cost_claim_permitted: bool,
    pub robustness_scope: String,
    pub blockers: Vec<EconomicFrontierClaimBlocker>,
    pub source_deployment_screen_blockers: Vec<DeploymentClaimBlocker>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomicFrontierResult {
    pub study_id: String,
    pub source: EconomicFrontierSource,
    pub benchmark_prices: Vec<TokenPriceBenchmark>,
    pub customer_price_fraction_of_benchmark: f64,
    pub customer_price_evidence: FrontierEvidence,
    pub workload_mixes: Vec<WorkloadMix>,
    pub useful_load_cases: Vec<UsefulLoadCase>,
    pub availability_cases: Vec<AvailabilityCase>,
    pub accelerator_cost_cases: Vec<AcceleratorCostCase>,
    pub gross_margin_cases: Vec<GrossMarginCase>,
    pub throughput_haircut_cases: Vec<ThroughputHaircutCase>,
    pub work_bound_cases: Vec<WorkBoundCase>,
    pub source_stack_feature_coverage: SourceStackFeatureCoverage,
    pub configured_headroom_threshold: f64,
    pub assumptions_source_artifact_id: String,
    pub work_basis: String,
    pub points: Vec<EconomicFrontierPoint>,
    pub regions: Vec<EconomicFrontierRegion>,
    pub summary: EconomicFrontierSummary,
    pub claims: EconomicFrontierClaimGate,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomicFrontierReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: EconomicFrontierResult,
}

impl EconomicFrontierReport {
    pub fn verify_content_id(&self) -> Result<bool, EconomicFrontierError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

pub fn evaluate_economic_frontier(
    request: &EconomicFrontierRequest,
    source: &DeploymentScreenReport,
) -> Result<EconomicFrontierReport, EconomicFrontierError> {
    validate_request(request)?;
    validate_source(request, source)?;
    let scope_multiplier = timing_scope_multiplier(source)?;
    let source_peak_output = source
        .result
        .roofline_optimistic_committed_output_tokens_per_second
        * scope_multiplier;
    validate_positive(
        "source_peak_committed_output_tokens_per_second_per_deployment",
        source_peak_output,
    )?;
    let source_result = EconomicFrontierSource {
        source_deployment_screen_content_id: source.content_id.clone(),
        source_screen_id: source.result.screen_id.clone(),
        variant_id: source.result.variant_id.clone(),
        storage_hardware_id: source.result.storage_hardware_id.clone(),
        roofline_hardware_id: source.result.roofline_hardware_id.clone(),
        deployment_device_count: source.result.deployment_device_count,
        capacity_status: source.result.capacity_status,
        timing_scope: source.result.timing_scope,
        roofline_optimistic_committed_output_tokens_per_second_per_timing_scope: source
            .result
            .roofline_optimistic_committed_output_tokens_per_second,
        source_peak_committed_output_tokens_per_second_per_deployment: source_peak_output,
        mapping_source_artifact_id: source.result.mapping_source_artifact_id.clone(),
    };
    let mut points = Vec::new();
    let mut regions = Vec::new();
    for benchmark in &request.benchmark_prices {
        for mix in &request.workload_mixes {
            for haircut in &request.throughput_haircut_cases {
                for work_bound in &request.work_bound_cases {
                    let region_start = points.len();
                    for useful_load in &request.useful_load_cases {
                        for availability in &request.availability_cases {
                            for cost in &request.accelerator_cost_cases {
                                for margin in &request.gross_margin_cases {
                                    points.push(evaluate_point(
                                        request,
                                        &source_result,
                                        benchmark,
                                        mix,
                                        useful_load,
                                        availability,
                                        cost,
                                        margin,
                                        haircut,
                                        work_bound,
                                    )?);
                                }
                            }
                        }
                    }
                    regions.push(summarize_region(
                        benchmark,
                        mix,
                        haircut,
                        work_bound,
                        &points[region_start..],
                    )?);
                }
            }
        }
    }
    let summary = summarize(&points, &regions)?;
    let claims = claim_gate(request, source);
    let result = EconomicFrontierResult {
        study_id: request.study_id.clone(),
        source: source_result,
        benchmark_prices: request.benchmark_prices.clone(),
        customer_price_fraction_of_benchmark: request.customer_price_fraction_of_benchmark,
        customer_price_evidence: request.customer_price_evidence.clone(),
        workload_mixes: request.workload_mixes.clone(),
        useful_load_cases: request.useful_load_cases.clone(),
        availability_cases: request.availability_cases.clone(),
        accelerator_cost_cases: request.accelerator_cost_cases.clone(),
        gross_margin_cases: request.gross_margin_cases.clone(),
        throughput_haircut_cases: request.throughput_haircut_cases.clone(),
        work_bound_cases: request.work_bound_cases.clone(),
        source_stack_feature_coverage: request.source_stack_feature_coverage.clone(),
        configured_headroom_threshold: request.configured_headroom_threshold,
        assumptions_source_artifact_id: request.assumptions_source_artifact_id.clone(),
        work_basis: "The source rate is an optimistic committed-output roofline bound expanded to the pinned deployment timing scope. A throughput haircut is applied once to source peak output. Work-bound weights convert output capacity to peak billable-token capacity. Useful load and availability are applied once, only when converting peak billable capacity to delivered billable capacity. The required throughput hurdle is delivered throughput and is never pre-adjusted by load or availability. Provider values are public token-price surfaces only, not performance baselines. Region labels describe only the configured modeled sweep and do not establish business viability or provider superiority.".into(),
        points,
        regions,
        summary,
        claims,
    };
    let schema_version = ECONOMIC_FRONTIER_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(EconomicFrontierReport {
        schema_version,
        content_id,
        result,
    })
}

#[allow(clippy::too_many_arguments)]
fn evaluate_point(
    request: &EconomicFrontierRequest,
    source: &EconomicFrontierSource,
    benchmark: &TokenPriceBenchmark,
    mix: &WorkloadMix,
    useful_load: &UsefulLoadCase,
    availability: &AvailabilityCase,
    cost: &AcceleratorCostCase,
    margin: &GrossMarginCase,
    haircut: &ThroughputHaircutCase,
    work_bound: &WorkBoundCase,
) -> Result<EconomicFrontierPoint, EconomicFrontierError> {
    let source_peak = source.source_peak_committed_output_tokens_per_second_per_deployment;
    let haircut_adjusted_peak_output = source_peak * haircut.throughput_haircut_factor;
    let average_work = mix.uncached_input_share * work_bound.uncached_input_work_units_per_token
        + mix.cached_input_share * work_bound.cached_input_work_units_per_token
        + mix.output_share;
    let modeled_peak_billable = haircut_adjusted_peak_output / average_work;
    let modeled_delivered_billable =
        modeled_peak_billable * useful_load.useful_load_factor * availability.availability_factor;
    let total_hourly_cost = f64::from(source.deployment_device_count)
        * cost.accelerator_usd_per_device_hour
        + cost.fixed_non_accelerator_usd_per_deployment_hour;
    let blended_benchmark_list_price = mix.uncached_input_share
        * benchmark.uncached_input_usd_per_million_tokens
        + mix.cached_input_share * benchmark.cached_input_usd_per_million_tokens
        + mix.output_share * benchmark.output_usd_per_million_tokens;
    let modeled_customer_price =
        blended_benchmark_list_price * request.customer_price_fraction_of_benchmark;
    let maximum_cogs = modeled_customer_price * (1.0 - margin.required_gross_margin);
    let modeled_cogs =
        TOKENS_PER_MILLION * total_hourly_cost / (SECONDS_PER_HOUR * modeled_delivered_billable);
    let modeled_gross_margin = 1.0 - modeled_cogs / modeled_customer_price;
    let required_delivered =
        TOKENS_PER_MILLION * total_hourly_cost / (SECONDS_PER_HOUR * maximum_cogs);
    let modeled_headroom = modeled_delivered_billable / required_delivered;
    let maximum_total_hourly_cost =
        modeled_delivered_billable * SECONDS_PER_HOUR * maximum_cogs / TOKENS_PER_MILLION;
    let remaining_accelerator_budget =
        maximum_total_hourly_cost - cost.fixed_non_accelerator_usd_per_deployment_hour;
    let maximum_accelerator_cost = (remaining_accelerator_budget >= 0.0)
        .then(|| remaining_accelerator_budget / f64::from(source.deployment_device_count));
    let load_availability = useful_load.useful_load_factor * availability.availability_factor;
    let minimum_source_peak_output =
        required_delivered * average_work / (haircut.throughput_haircut_factor * load_availability);
    let required_load_availability_product =
        required_delivered * average_work / haircut_adjusted_peak_output;
    let minimum_required_haircut =
        required_delivered * average_work / (source_peak * load_availability);
    let maximum_average_work =
        haircut_adjusted_peak_output * load_availability / required_delivered;
    validate_point_values(&[
        haircut_adjusted_peak_output,
        average_work,
        modeled_peak_billable,
        modeled_delivered_billable,
        total_hourly_cost,
        blended_benchmark_list_price,
        modeled_customer_price,
        maximum_cogs,
        modeled_cogs,
        required_delivered,
        modeled_headroom,
        maximum_total_hourly_cost,
        minimum_source_peak_output,
        required_load_availability_product,
        minimum_required_haircut,
        maximum_average_work,
    ])?;
    if !modeled_gross_margin.is_finite() {
        return Err(EconomicFrontierError::ArithmeticOverflow);
    }
    if maximum_accelerator_cost.is_some_and(|value| !value.is_finite()) {
        return Err(EconomicFrontierError::ArithmeticOverflow);
    }
    let capacity_feasible = source.capacity_status == DeploymentCapacityStatus::Feasible;
    let modeled_required_margin_cleared = capacity_feasible && modeled_headroom >= 1.0;
    let status = if !capacity_feasible {
        EconomicFrontierPointStatus::SourceCapacityNotFeasible
    } else if !modeled_required_margin_cleared {
        EconomicFrontierPointStatus::BelowRequiredMargin
    } else if modeled_headroom < request.configured_headroom_threshold {
        EconomicFrontierPointStatus::ClearsRequiredMarginBelowHeadroomThreshold
    } else {
        EconomicFrontierPointStatus::ClearsConfiguredHeadroomThreshold
    };
    Ok(EconomicFrontierPoint {
        key: EconomicFrontierPointKey {
            benchmark_id: benchmark.benchmark_id.clone(),
            mix_id: mix.mix_id.clone(),
            useful_load_case_id: useful_load.case_id.clone(),
            availability_case_id: availability.case_id.clone(),
            accelerator_cost_case_id: cost.case_id.clone(),
            gross_margin_case_id: margin.case_id.clone(),
            throughput_haircut_case_id: haircut.case_id.clone(),
            work_bound_case_id: work_bound.case_id.clone(),
        },
        source_peak_committed_output_tokens_per_second_per_deployment: source_peak,
        throughput_haircut_factor: haircut.throughput_haircut_factor,
        haircut_adjusted_peak_output_tokens_per_second: haircut_adjusted_peak_output,
        average_work_units_per_billable_token: average_work,
        modeled_peak_billable_tokens_per_second: modeled_peak_billable,
        useful_load_factor: useful_load.useful_load_factor,
        availability_factor: availability.availability_factor,
        modeled_delivered_billable_tokens_per_second: modeled_delivered_billable,
        accelerator_usd_per_device_hour: cost.accelerator_usd_per_device_hour,
        fixed_non_accelerator_usd_per_deployment_hour: cost
            .fixed_non_accelerator_usd_per_deployment_hour,
        total_hourly_deployment_cost_usd: total_hourly_cost,
        blended_benchmark_list_price_usd_per_million_tokens: blended_benchmark_list_price,
        customer_price_fraction_of_benchmark: request.customer_price_fraction_of_benchmark,
        modeled_customer_price_usd_per_million_tokens: modeled_customer_price,
        required_gross_margin: margin.required_gross_margin,
        maximum_cogs_usd_per_million_tokens_at_required_margin: maximum_cogs,
        modeled_cogs_usd_per_million_delivered_tokens: modeled_cogs,
        modeled_gross_margin,
        required_delivered_billable_tokens_per_second: required_delivered,
        modeled_headroom_ratio: modeled_headroom,
        maximum_total_hourly_deployment_cost_usd: maximum_total_hourly_cost,
        maximum_accelerator_usd_per_device_hour: maximum_accelerator_cost,
        minimum_source_peak_output_tokens_per_second: minimum_source_peak_output,
        required_useful_load_availability_product: required_load_availability_product,
        minimum_required_throughput_haircut_factor: minimum_required_haircut,
        maximum_average_work_units_per_billable_token: maximum_average_work,
        modeled_required_margin_cleared,
        status,
    })
}

fn summarize_region(
    benchmark: &TokenPriceBenchmark,
    mix: &WorkloadMix,
    haircut: &ThroughputHaircutCase,
    work_bound: &WorkBoundCase,
    points: &[EconomicFrontierPoint],
) -> Result<EconomicFrontierRegion, EconomicFrontierError> {
    if points.is_empty() {
        return Err(EconomicFrontierError::ArithmeticOverflow);
    }
    let point_count =
        u64::try_from(points.len()).map_err(|_| EconomicFrontierError::ArithmeticOverflow)?;
    let required_margin_clearance_count = u64::try_from(
        points
            .iter()
            .filter(|point| point.modeled_required_margin_cleared)
            .count(),
    )
    .map_err(|_| EconomicFrontierError::ArithmeticOverflow)?;
    let configured_headroom_clearance_count = u64::try_from(
        points
            .iter()
            .filter(|point| {
                point.status == EconomicFrontierPointStatus::ClearsConfiguredHeadroomThreshold
            })
            .count(),
    )
    .map_err(|_| EconomicFrontierError::ArithmeticOverflow)?;
    let minimum_modeled_headroom_ratio = points
        .iter()
        .map(|point| point.modeled_headroom_ratio)
        .reduce(f64::min)
        .ok_or(EconomicFrontierError::ArithmeticOverflow)?;
    let maximum_modeled_headroom_ratio = points
        .iter()
        .map(|point| point.modeled_headroom_ratio)
        .reduce(f64::max)
        .ok_or(EconomicFrontierError::ArithmeticOverflow)?;
    let status = if required_margin_clearance_count == 0 {
        EconomicFrontierRegionStatus::NoMarginClearance
    } else if required_margin_clearance_count < point_count {
        EconomicFrontierRegionStatus::MixedMarginClearance
    } else if configured_headroom_clearance_count < point_count {
        EconomicFrontierRegionStatus::ClearsMarginAcrossSweepBelowHeadroomThreshold
    } else {
        EconomicFrontierRegionStatus::ClearsHeadroomThresholdAcrossSweep
    };
    Ok(EconomicFrontierRegion {
        key: EconomicFrontierRegionKey {
            benchmark_id: benchmark.benchmark_id.clone(),
            mix_id: mix.mix_id.clone(),
            throughput_haircut_case_id: haircut.case_id.clone(),
            work_bound_case_id: work_bound.case_id.clone(),
        },
        point_count,
        required_margin_clearance_count,
        configured_headroom_clearance_count,
        required_margin_clearance_fraction: required_margin_clearance_count as f64
            / point_count as f64,
        configured_headroom_clearance_fraction: configured_headroom_clearance_count as f64
            / point_count as f64,
        minimum_modeled_headroom_ratio,
        maximum_modeled_headroom_ratio,
        status,
    })
}

fn summarize(
    points: &[EconomicFrontierPoint],
    regions: &[EconomicFrontierRegion],
) -> Result<EconomicFrontierSummary, EconomicFrontierError> {
    Ok(EconomicFrontierSummary {
        point_count: count(points.len())?,
        region_count: count(regions.len())?,
        source_capacity_not_feasible_point_count: count_status(
            points,
            EconomicFrontierPointStatus::SourceCapacityNotFeasible,
        )?,
        below_required_margin_point_count: count_status(
            points,
            EconomicFrontierPointStatus::BelowRequiredMargin,
        )?,
        clears_required_margin_below_threshold_point_count: count_status(
            points,
            EconomicFrontierPointStatus::ClearsRequiredMarginBelowHeadroomThreshold,
        )?,
        clears_configured_headroom_threshold_point_count: count_status(
            points,
            EconomicFrontierPointStatus::ClearsConfiguredHeadroomThreshold,
        )?,
        no_margin_clearance_region_count: count_region_status(
            regions,
            EconomicFrontierRegionStatus::NoMarginClearance,
        )?,
        mixed_margin_clearance_region_count: count_region_status(
            regions,
            EconomicFrontierRegionStatus::MixedMarginClearance,
        )?,
        clears_margin_across_sweep_below_threshold_region_count: count_region_status(
            regions,
            EconomicFrontierRegionStatus::ClearsMarginAcrossSweepBelowHeadroomThreshold,
        )?,
        clears_headroom_threshold_across_sweep_region_count: count_region_status(
            regions,
            EconomicFrontierRegionStatus::ClearsHeadroomThresholdAcrossSweep,
        )?,
    })
}

fn count_status(
    points: &[EconomicFrontierPoint],
    status: EconomicFrontierPointStatus,
) -> Result<u64, EconomicFrontierError> {
    count(points.iter().filter(|point| point.status == status).count())
}

fn count_region_status(
    regions: &[EconomicFrontierRegion],
    status: EconomicFrontierRegionStatus,
) -> Result<u64, EconomicFrontierError> {
    count(
        regions
            .iter()
            .filter(|region| region.status == status)
            .count(),
    )
}

fn count(value: usize) -> Result<u64, EconomicFrontierError> {
    u64::try_from(value).map_err(|_| EconomicFrontierError::ArithmeticOverflow)
}

fn validate_request(request: &EconomicFrontierRequest) -> Result<(), EconomicFrontierError> {
    if request.schema_version != ECONOMIC_FRONTIER_REQUEST_SCHEMA_VERSION {
        return Err(EconomicFrontierError::UnsupportedSchemaVersion {
            expected: ECONOMIC_FRONTIER_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    validate_required("study_id", &request.study_id)?;
    validate_required(
        "source_deployment_screen_content_id",
        &request.source_deployment_screen_content_id,
    )?;
    validate_required(
        "assumptions_source_artifact_id",
        &request.assumptions_source_artifact_id,
    )?;
    validate_evidence("customer_price_evidence", &request.customer_price_evidence)?;
    validate_evidence(
        "source_stack_feature_coverage.evidence",
        &request.source_stack_feature_coverage.evidence,
    )?;
    validate_factor(
        "customer_price_fraction_of_benchmark",
        request.customer_price_fraction_of_benchmark,
    )?;
    if !request.configured_headroom_threshold.is_finite()
        || request.configured_headroom_threshold < 1.0
    {
        return Err(EconomicFrontierError::InvalidField(
            "configured_headroom_threshold",
        ));
    }
    validate_nonempty("benchmark_prices", &request.benchmark_prices)?;
    validate_nonempty("workload_mixes", &request.workload_mixes)?;
    validate_nonempty("useful_load_cases", &request.useful_load_cases)?;
    validate_nonempty("availability_cases", &request.availability_cases)?;
    validate_nonempty("accelerator_cost_cases", &request.accelerator_cost_cases)?;
    validate_nonempty("gross_margin_cases", &request.gross_margin_cases)?;
    validate_nonempty(
        "throughput_haircut_cases",
        &request.throughput_haircut_cases,
    )?;
    validate_nonempty("work_bound_cases", &request.work_bound_cases)?;
    let mut ids = BTreeSet::new();
    for benchmark in &request.benchmark_prices {
        insert_id(
            &mut ids,
            "benchmark_prices.benchmark_id",
            &benchmark.benchmark_id,
        )?;
        validate_required("benchmark_prices.provider", &benchmark.provider)?;
        validate_required("benchmark_prices.serving_path", &benchmark.serving_path)?;
        validate_positive(
            "benchmark_prices.uncached_input_usd_per_million_tokens",
            benchmark.uncached_input_usd_per_million_tokens,
        )?;
        validate_positive(
            "benchmark_prices.cached_input_usd_per_million_tokens",
            benchmark.cached_input_usd_per_million_tokens,
        )?;
        validate_positive(
            "benchmark_prices.output_usd_per_million_tokens",
            benchmark.output_usd_per_million_tokens,
        )?;
        validate_evidence("benchmark_prices.evidence", &benchmark.evidence)?;
    }
    ids.clear();
    for mix in &request.workload_mixes {
        insert_id(&mut ids, "workload_mixes.mix_id", &mix.mix_id)?;
        for (field, share) in [
            (
                "workload_mixes.uncached_input_share",
                mix.uncached_input_share,
            ),
            ("workload_mixes.cached_input_share", mix.cached_input_share),
            ("workload_mixes.output_share", mix.output_share),
        ] {
            validate_share(field, share)?;
        }
        let sum = mix.uncached_input_share + mix.cached_input_share + mix.output_share;
        if (sum - 1.0).abs() > 1.0e-9 || mix.output_share <= 0.0 {
            return Err(EconomicFrontierError::InvalidField("workload_mixes"));
        }
        validate_evidence("workload_mixes.evidence", &mix.evidence)?;
    }
    validate_factor_cases(request)?;
    Ok(())
}

fn validate_factor_cases(request: &EconomicFrontierRequest) -> Result<(), EconomicFrontierError> {
    let mut ids = BTreeSet::new();
    for case in &request.useful_load_cases {
        insert_id(&mut ids, "useful_load_cases.case_id", &case.case_id)?;
        validate_factor(
            "useful_load_cases.useful_load_factor",
            case.useful_load_factor,
        )?;
        validate_evidence("useful_load_cases.evidence", &case.evidence)?;
    }
    ids.clear();
    for case in &request.availability_cases {
        insert_id(&mut ids, "availability_cases.case_id", &case.case_id)?;
        validate_factor(
            "availability_cases.availability_factor",
            case.availability_factor,
        )?;
        validate_evidence("availability_cases.evidence", &case.evidence)?;
    }
    ids.clear();
    for case in &request.accelerator_cost_cases {
        insert_id(&mut ids, "accelerator_cost_cases.case_id", &case.case_id)?;
        validate_positive(
            "accelerator_cost_cases.accelerator_usd_per_device_hour",
            case.accelerator_usd_per_device_hour,
        )?;
        validate_non_negative(
            "accelerator_cost_cases.fixed_non_accelerator_usd_per_deployment_hour",
            case.fixed_non_accelerator_usd_per_deployment_hour,
        )?;
        validate_evidence("accelerator_cost_cases.evidence", &case.evidence)?;
    }
    ids.clear();
    for case in &request.gross_margin_cases {
        insert_id(&mut ids, "gross_margin_cases.case_id", &case.case_id)?;
        if !case.required_gross_margin.is_finite()
            || !(0.0..1.0).contains(&case.required_gross_margin)
        {
            return Err(EconomicFrontierError::InvalidField(
                "gross_margin_cases.required_gross_margin",
            ));
        }
    }
    ids.clear();
    for case in &request.throughput_haircut_cases {
        insert_id(&mut ids, "throughput_haircut_cases.case_id", &case.case_id)?;
        validate_factor(
            "throughput_haircut_cases.throughput_haircut_factor",
            case.throughput_haircut_factor,
        )?;
        validate_evidence("throughput_haircut_cases.evidence", &case.evidence)?;
    }
    ids.clear();
    for case in &request.work_bound_cases {
        insert_id(&mut ids, "work_bound_cases.case_id", &case.case_id)?;
        validate_non_negative(
            "work_bound_cases.uncached_input_work_units_per_token",
            case.uncached_input_work_units_per_token,
        )?;
        validate_non_negative(
            "work_bound_cases.cached_input_work_units_per_token",
            case.cached_input_work_units_per_token,
        )?;
        validate_evidence("work_bound_cases.evidence", &case.evidence)?;
    }
    Ok(())
}

fn validate_source(
    request: &EconomicFrontierRequest,
    source: &DeploymentScreenReport,
) -> Result<(), EconomicFrontierError> {
    if source.schema_version != DEPLOYMENT_SCREEN_REPORT_SCHEMA_VERSION {
        return Err(EconomicFrontierError::UnsupportedSourceSchemaVersion {
            expected: DEPLOYMENT_SCREEN_REPORT_SCHEMA_VERSION,
            actual: source.schema_version,
        });
    }
    if !source
        .verify_content_id()
        .map_err(EconomicFrontierError::SourceArtifactVerification)?
    {
        return Err(EconomicFrontierError::InvalidSourceArtifactIdentity);
    }
    if request.source_deployment_screen_content_id != source.content_id {
        return Err(EconomicFrontierError::SourceArtifactIdentityMismatch);
    }
    if source.result.deployment_device_count == 0 {
        return Err(EconomicFrontierError::InvalidField(
            "source.deployment_device_count",
        ));
    }
    validate_positive(
        "source.roofline_optimistic_committed_output_tokens_per_second",
        source
            .result
            .roofline_optimistic_committed_output_tokens_per_second,
    )
}

fn timing_scope_multiplier(source: &DeploymentScreenReport) -> Result<f64, EconomicFrontierError> {
    match source.result.timing_scope {
        RooflineTimingScope::WholeDeployment => Ok(1.0),
        RooflineTimingScope::PerRank { rank_count } => {
            if rank_count == 0 || rank_count != source.result.deployment_device_count {
                return Err(EconomicFrontierError::SourceRankCountMismatch {
                    expected: source.result.deployment_device_count,
                    actual: rank_count,
                });
            }
            Ok(f64::from(rank_count))
        }
    }
}

fn claim_gate(
    request: &EconomicFrontierRequest,
    source: &DeploymentScreenReport,
) -> EconomicFrontierClaimGate {
    let mut blockers = vec![
        EconomicFrontierClaimBlocker::SourcePeakThroughputIsOptimisticAndUncalibrated,
        EconomicFrontierClaimBlocker::ProviderPriceBenchmarkIsNotPerformanceBaseline,
        EconomicFrontierClaimBlocker::ProviderPricesArePublicListNotContractPrices,
        EconomicFrontierClaimBlocker::ServingSloAndQueueingAreNotValidated,
        EconomicFrontierClaimBlocker::QualityContractIsNotValidated,
        EconomicFrontierClaimBlocker::NreAndProviderProductOverheadAreExcluded,
    ];
    if !source.result.claims.blockers.is_empty() {
        blockers.push(EconomicFrontierClaimBlocker::SourceDeploymentScreenClaimsAreBlocked);
    }
    if !request
        .source_stack_feature_coverage
        .proves_current_incumbent_combined_stack()
    {
        blockers
            .push(EconomicFrontierClaimBlocker::SourceDoesNotProveCurrentIncumbentCombinedStack);
    }
    if request.customer_price_evidence.kind != FrontierEvidenceKind::Measured {
        blockers.push(EconomicFrontierClaimBlocker::CustomerPriceFractionIsModeled);
    }
    if request
        .workload_mixes
        .iter()
        .any(|case| case.evidence.kind == FrontierEvidenceKind::ModeledAssumption)
    {
        blockers.push(EconomicFrontierClaimBlocker::WorkloadMixesAreModeled);
    }
    if request
        .useful_load_cases
        .iter()
        .any(|case| case.evidence.kind == FrontierEvidenceKind::ModeledAssumption)
        || request
            .availability_cases
            .iter()
            .any(|case| case.evidence.kind == FrontierEvidenceKind::ModeledAssumption)
    {
        blockers.push(EconomicFrontierClaimBlocker::UsefulLoadAndAvailabilityAreModeled);
    }
    if request
        .accelerator_cost_cases
        .iter()
        .any(|case| case.evidence.kind == FrontierEvidenceKind::ModeledAssumption)
    {
        blockers.push(EconomicFrontierClaimBlocker::AcceleratorCostsAreModeled);
    }
    if request
        .throughput_haircut_cases
        .iter()
        .any(|case| case.evidence.kind == FrontierEvidenceKind::ModeledAssumption)
    {
        blockers.push(EconomicFrontierClaimBlocker::ThroughputHaircutsAreModeled);
    }
    if request
        .work_bound_cases
        .iter()
        .any(|case| case.evidence.kind == FrontierEvidenceKind::ModeledAssumption)
    {
        blockers.push(EconomicFrontierClaimBlocker::InputWorkBoundsAreModeled);
    }
    if source.result.capacity_status != DeploymentCapacityStatus::Feasible
        || matches!(
            source.result.timing_scope,
            RooflineTimingScope::PerRank { .. }
        )
    {
        blockers.push(EconomicFrontierClaimBlocker::SourceCapacityOrMappingIsNotValidatedEndToEnd);
    }
    EconomicFrontierClaimGate {
        business_viability_claim_permitted: false,
        provider_comparison_claim_permitted: false,
        end_to_end_cost_claim_permitted: false,
        robustness_scope: "Configured modeled sensitivity sweep only; region labels do not establish business viability or provider superiority.".into(),
        blockers,
        source_deployment_screen_blockers: source.result.claims.blockers.clone(),
    }
}

fn validate_point_values(values: &[f64]) -> Result<(), EconomicFrontierError> {
    if values.iter().all(|value| value.is_finite() && *value > 0.0) {
        Ok(())
    } else {
        Err(EconomicFrontierError::ArithmeticOverflow)
    }
}

fn validate_evidence(
    field: &'static str,
    evidence: &FrontierEvidence,
) -> Result<(), EconomicFrontierError> {
    validate_required(field, &evidence.source_artifact_id)
}

fn insert_id<'a>(
    ids: &mut BTreeSet<&'a str>,
    field: &'static str,
    id: &'a str,
) -> Result<(), EconomicFrontierError> {
    validate_required(field, id)?;
    if ids.insert(id) {
        Ok(())
    } else {
        Err(EconomicFrontierError::DuplicateCaseId(id.into()))
    }
}

fn validate_nonempty<T>(field: &'static str, values: &[T]) -> Result<(), EconomicFrontierError> {
    if values.is_empty() {
        Err(EconomicFrontierError::InvalidField(field))
    } else {
        Ok(())
    }
}

fn validate_required(field: &'static str, value: &str) -> Result<(), EconomicFrontierError> {
    if value.trim().is_empty() {
        Err(EconomicFrontierError::InvalidField(field))
    } else {
        Ok(())
    }
}

fn validate_positive(field: &'static str, value: f64) -> Result<(), EconomicFrontierError> {
    if value.is_finite() && value > 0.0 {
        Ok(())
    } else {
        Err(EconomicFrontierError::InvalidField(field))
    }
}

fn validate_non_negative(field: &'static str, value: f64) -> Result<(), EconomicFrontierError> {
    if value.is_finite() && value >= 0.0 {
        Ok(())
    } else {
        Err(EconomicFrontierError::InvalidField(field))
    }
}

fn validate_factor(field: &'static str, value: f64) -> Result<(), EconomicFrontierError> {
    if value.is_finite() && value > 0.0 && value <= 1.0 {
        Ok(())
    } else {
        Err(EconomicFrontierError::InvalidField(field))
    }
}

fn validate_share(field: &'static str, value: f64) -> Result<(), EconomicFrontierError> {
    if value.is_finite() && (0.0..=1.0).contains(&value) {
        Ok(())
    } else {
        Err(EconomicFrontierError::InvalidField(field))
    }
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a EconomicFrontierResult,
}

fn report_content_id(
    schema_version: u32,
    result: &EconomicFrontierResult,
) -> Result<String, EconomicFrontierError> {
    let bytes = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|error| EconomicFrontierError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Debug, Error)]
pub enum EconomicFrontierError {
    #[error("unsupported economic frontier schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("unsupported deployment screen schema version {actual}; expected {expected}")]
    UnsupportedSourceSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid economic frontier field {0}")]
    InvalidField(&'static str),
    #[error("duplicate economic frontier case ID {0}")]
    DuplicateCaseId(String),
    #[error("source deployment screen identity is invalid")]
    InvalidSourceArtifactIdentity,
    #[error("source deployment screen does not match the pinned content ID")]
    SourceArtifactIdentityMismatch,
    #[error("source deployment screen verification failed: {0}")]
    SourceArtifactVerification(#[source] DeploymentScreenError),
    #[error("source rank count {actual} does not match deployment device count {expected}")]
    SourceRankCountMismatch { expected: u32, actual: u32 },
    #[error("economic frontier arithmetic overflowed or produced a non-positive value")]
    ArithmeticOverflow,
    #[error("economic frontier serialization failed: {0}")]
    Serialization(String),
}
