use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::glm_decode::GlmDecodeLoweringReport;
use crate::glm_mapping_context_frontier::{
    ContextConcurrencyPoint, ExactMappingResidencyInputs, FrontierCapacityRelation,
    GlmMappingContextFrontierError, GlmMappingContextFrontierRequest, PartialPolicy,
    evaluate_exact_mapping_residency_grid,
};
use crate::glm_parallel_mapping::{CapacityStatus, GlmParallelMappingReport};
use crate::glm_storage::GlmStorageEnvelopeReport;
use crate::public_agentic_proxy::{PublicAgenticProxyError, PublicAgenticProxyReport};

pub const GLM_AGENTIC_MAPPING_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const GLM_AGENTIC_MAPPING_REPORT_SCHEMA_VERSION: u32 = 1;

const FIXED_CONCURRENCY_POINTS: [u32; 5] = [1, 8, 16, 32, 64];
const RETARGETING_NOTICE: &str = "The synthetic proxy is retargeted to GLM token geometry only. Prompt text, tokenizer equivalence, output lengths, arrival timing, tool delays, dynamic-prefix cache behavior, and proxy SLO tiers are not evaluated or asserted for GLM.";

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PinnedRequestFile {
    pub path: PathBuf,
    pub file_blake3: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PinnedReportFile {
    pub path: PathBuf,
    pub file_blake3: String,
    pub report_content_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmAgenticMappingSources {
    pub proxy: PinnedReportFile,
    pub frontier_request: PinnedRequestFile,
    pub storage: PinnedReportFile,
    pub mapping_16k: PinnedReportFile,
    pub mapping_90k: PinnedReportFile,
    pub lowering_16k: PinnedReportFile,
    pub lowering_90k: PinnedReportFile,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmAgenticSourceFileHashes {
    pub proxy: String,
    pub frontier_request: String,
    pub storage: String,
    pub mapping_16k: String,
    pub mapping_90k: String,
    pub lowering_16k: String,
    pub lowering_90k: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmAgenticRetargeting {
    pub source_model_id: String,
    pub source_model_revision: String,
    pub source_tokenizer_id: String,
    pub source_tokenizer_revision: String,
    pub target_model_id: String,
    pub target_model_revision: String,
    pub token_count_retarget_only: bool,
    pub prompt_or_tokenizer_equivalence_claimed: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmAgenticMappingClaims {
    pub quality_claim_permitted: bool,
    pub latency_claim_permitted: bool,
    pub throughput_claim_permitted: bool,
    pub slo_claim_permitted: bool,
    pub network_effect_claim_permitted: bool,
    pub energy_claim_permitted: bool,
    pub cost_claim_permitted: bool,
    pub provider_claim_permitted: bool,
    pub nvidia_performance_claim_permitted: bool,
    pub full_deployment_claim_permitted: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmAgenticMappingRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub sources: GlmAgenticMappingSources,
    pub retargeting: GlmAgenticRetargeting,
    pub concurrency_points: Vec<u32>,
    pub claims: GlmAgenticMappingClaims,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PartialPolicyCounts {
    pub coupled_robust_lower: u64,
    pub overlap_or_metric_disagreement: u64,
    pub decoupled_robust_lower: u64,
}

impl PartialPolicyCounts {
    pub const fn total(&self) -> u64 {
        self.coupled_robust_lower
            + self.overlap_or_metric_disagreement
            + self.decoupled_robust_lower
    }

    fn add(&mut self, policy: PartialPolicy, weight: u64) -> Result<(), GlmAgenticMappingError> {
        let count = match policy {
            PartialPolicy::CoupledRobustLower => &mut self.coupled_robust_lower,
            PartialPolicy::BoundsOverlapOrMetricDisagreement => {
                &mut self.overlap_or_metric_disagreement
            }
            PartialPolicy::DecoupledRobustLower => &mut self.decoupled_robust_lower,
        };
        *count = count
            .checked_add(weight)
            .ok_or(GlmAgenticMappingError::ArithmeticOverflow)?;
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CapacityStatusCounts {
    pub feasible: u64,
    pub uncertain: u64,
    pub infeasible: u64,
}

impl CapacityStatusCounts {
    pub const fn total(&self) -> u64 {
        self.feasible + self.uncertain + self.infeasible
    }

    fn add(&mut self, status: CapacityStatus, weight: u64) -> Result<(), GlmAgenticMappingError> {
        let count = match status {
            CapacityStatus::Feasible => &mut self.feasible,
            CapacityStatus::Uncertain => &mut self.uncertain,
            CapacityStatus::Infeasible => &mut self.infeasible,
        };
        *count = count
            .checked_add(weight)
            .ok_or(GlmAgenticMappingError::ArithmeticOverflow)?;
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CapacityRelationCounts {
    pub both_plans_proven_feasible: u64,
    pub coupled_only_proven_feasible: u64,
    pub decoupled_only_proven_feasible: u64,
    pub neither_plan_proven_feasible: u64,
}

impl CapacityRelationCounts {
    pub const fn total(&self) -> u64 {
        self.both_plans_proven_feasible
            + self.coupled_only_proven_feasible
            + self.decoupled_only_proven_feasible
            + self.neither_plan_proven_feasible
    }

    fn add(
        &mut self,
        relation: FrontierCapacityRelation,
        weight: u64,
    ) -> Result<(), GlmAgenticMappingError> {
        let count = match relation {
            FrontierCapacityRelation::BothPlansProvenFeasible => {
                &mut self.both_plans_proven_feasible
            }
            FrontierCapacityRelation::BaselineOnlyProvenFeasible => {
                &mut self.coupled_only_proven_feasible
            }
            FrontierCapacityRelation::CandidateOnlyProvenFeasible => {
                &mut self.decoupled_only_proven_feasible
            }
            FrontierCapacityRelation::NeitherPlanProvenFeasible => {
                &mut self.neither_plan_proven_feasible
            }
        };
        *count = count
            .checked_add(weight)
            .ok_or(GlmAgenticMappingError::ArithmeticOverflow)?;
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WeightedExactContext {
    pub context_tokens_per_request: u64,
    pub request_count: u64,
    pub semantic_cache_bytes_per_request: u64,
    pub points: Vec<ContextConcurrencyPoint>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RequestWeightedConcurrency {
    pub concurrent_requests: u32,
    pub request_count: u64,
    pub partial_policy: PartialPolicyCounts,
    pub baseline_full_capacity: CapacityStatusCounts,
    pub candidate_full_capacity: CapacityStatusCounts,
    pub capacity_relation: CapacityRelationCounts,
    pub either_plan_uncertain_requests: u64,
    pub both_plans_uncertain_requests: u64,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum GlmAgenticMappingBlocker {
    ProxyIsSyntheticGeometryOnly,
    TokenizerEquivalenceNotEstablished,
    PrefixReuseAndToolTimingExcluded,
    OutputAndArrivalFieldsExcluded,
    ContextDependentComputeNotDerived,
    NetworkTimingNotEvaluated,
    FullCapacityContainsBounds,
    QualityNotEvaluated,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmAgenticMappingResult {
    pub study_id: String,
    pub scope: String,
    pub retargeting_notice: String,
    pub sources: GlmAgenticMappingSources,
    pub source_file_hashes: GlmAgenticSourceFileHashes,
    pub source_file_hashes_verified: bool,
    pub retargeting: GlmAgenticRetargeting,
    pub target_variant_id: String,
    pub target_device_profile_id: String,
    pub baseline_plan_id: String,
    pub candidate_plan_id: String,
    pub unique_context_tokens: Vec<u64>,
    pub concurrency_points: Vec<u32>,
    pub proxy_request_count: u64,
    pub exact_context_evaluation_count: u64,
    pub request_weighted_evaluation_count: u64,
    pub exact_contexts: Vec<WeightedExactContext>,
    pub request_weighted: Vec<RequestWeightedConcurrency>,
    pub blockers: Vec<GlmAgenticMappingBlocker>,
    pub claims: GlmAgenticMappingClaims,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmAgenticMappingReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: GlmAgenticMappingResult,
}

impl GlmAgenticMappingReport {
    pub fn verify_content_id(&self) -> Result<bool, GlmAgenticMappingError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

pub struct GlmAgenticMappingInputs<'a> {
    pub source_file_hashes: &'a GlmAgenticSourceFileHashes,
    pub proxy: &'a PublicAgenticProxyReport,
    pub frontier_request: &'a GlmMappingContextFrontierRequest,
    pub storage: &'a GlmStorageEnvelopeReport,
    pub mapping_16k: &'a GlmParallelMappingReport,
    pub mapping_90k: &'a GlmParallelMappingReport,
    pub lowering_16k: &'a GlmDecodeLoweringReport,
    pub lowering_90k: &'a GlmDecodeLoweringReport,
}

pub fn evaluate_glm_agentic_mapping_screen(
    request: &GlmAgenticMappingRequest,
    inputs: &GlmAgenticMappingInputs<'_>,
) -> Result<GlmAgenticMappingReport, GlmAgenticMappingError> {
    validate_request(request)?;
    validate_file_hashes(request, inputs.source_file_hashes)?;
    validate_sources(
        request,
        inputs.proxy,
        inputs.storage,
        inputs.mapping_16k,
        inputs.mapping_90k,
        inputs.lowering_16k,
        inputs.lowering_90k,
    )?;
    validate_retargeting(
        request,
        inputs.proxy,
        inputs.mapping_16k,
        inputs.mapping_90k,
    )?;
    let context_weights = inputs.proxy.result.trace.requests.iter().try_fold(
        BTreeMap::<u64, u64>::new(),
        |mut counts, trace_request| {
            let count = counts
                .entry(u64::from(trace_request.input_tokens))
                .or_default();
            *count = count
                .checked_add(1)
                .ok_or(GlmAgenticMappingError::ArithmeticOverflow)?;
            Ok::<_, GlmAgenticMappingError>(counts)
        },
    )?;
    let unique_context_tokens = context_weights.keys().copied().collect::<Vec<_>>();
    let exact = evaluate_exact_mapping_residency_grid(
        inputs.frontier_request,
        &ExactMappingResidencyInputs {
            storage: inputs.storage,
            mapping_16k: inputs.mapping_16k,
            mapping_90k: inputs.mapping_90k,
            lowering_16k: inputs.lowering_16k,
            lowering_90k: inputs.lowering_90k,
        },
        &unique_context_tokens,
        &request.concurrency_points,
    )?;
    let exact_contexts = exact
        .into_iter()
        .map(|context| WeightedExactContext {
            context_tokens_per_request: context.context_tokens_per_request,
            request_count: context_weights[&context.context_tokens_per_request],
            semantic_cache_bytes_per_request: context.semantic_cache_bytes_per_request,
            points: context.points,
        })
        .collect::<Vec<_>>();
    let proxy_request_count = u64::try_from(inputs.proxy.result.trace.requests.len())
        .map_err(|_| GlmAgenticMappingError::CountOverflow)?;
    let request_weighted = request
        .concurrency_points
        .iter()
        .map(|concurrency| aggregate_concurrency(*concurrency, &exact_contexts))
        .collect::<Result<Vec<_>, _>>()?;
    if request_weighted.iter().any(|aggregate| {
        aggregate.request_count != proxy_request_count
            || aggregate.partial_policy.total() != proxy_request_count
            || aggregate.baseline_full_capacity.total() != proxy_request_count
            || aggregate.candidate_full_capacity.total() != proxy_request_count
            || aggregate.capacity_relation.total() != proxy_request_count
    }) {
        return Err(GlmAgenticMappingError::AggregationMismatch);
    }
    let exact_context_evaluation_count = u64::try_from(unique_context_tokens.len())
        .map_err(|_| GlmAgenticMappingError::CountOverflow)?
        .checked_mul(
            u64::try_from(request.concurrency_points.len())
                .map_err(|_| GlmAgenticMappingError::CountOverflow)?,
        )
        .ok_or(GlmAgenticMappingError::ArithmeticOverflow)?;
    let request_weighted_evaluation_count = proxy_request_count
        .checked_mul(
            u64::try_from(request.concurrency_points.len())
                .map_err(|_| GlmAgenticMappingError::CountOverflow)?,
        )
        .ok_or(GlmAgenticMappingError::ArithmeticOverflow)?;
    let result = GlmAgenticMappingResult {
        study_id: request.study_id.clone(),
        scope: "exact_partial_residency_and_full_capacity_bound_arithmetic_only".into(),
        retargeting_notice: RETARGETING_NOTICE.into(),
        sources: request.sources.clone(),
        source_file_hashes: inputs.source_file_hashes.clone(),
        source_file_hashes_verified: true,
        retargeting: request.retargeting.clone(),
        target_variant_id: inputs.frontier_request.variant_id.clone(),
        target_device_profile_id: inputs.frontier_request.device_profile_id.clone(),
        baseline_plan_id: inputs.frontier_request.baseline_plan_id.clone(),
        candidate_plan_id: inputs.frontier_request.candidate_plan_id.clone(),
        unique_context_tokens,
        concurrency_points: request.concurrency_points.clone(),
        proxy_request_count,
        exact_context_evaluation_count,
        request_weighted_evaluation_count,
        exact_contexts,
        request_weighted,
        blockers: vec![
            GlmAgenticMappingBlocker::ProxyIsSyntheticGeometryOnly,
            GlmAgenticMappingBlocker::TokenizerEquivalenceNotEstablished,
            GlmAgenticMappingBlocker::PrefixReuseAndToolTimingExcluded,
            GlmAgenticMappingBlocker::OutputAndArrivalFieldsExcluded,
            GlmAgenticMappingBlocker::ContextDependentComputeNotDerived,
            GlmAgenticMappingBlocker::NetworkTimingNotEvaluated,
            GlmAgenticMappingBlocker::FullCapacityContainsBounds,
            GlmAgenticMappingBlocker::QualityNotEvaluated,
        ],
        claims: request.claims.clone(),
    };
    let schema_version = GLM_AGENTIC_MAPPING_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(GlmAgenticMappingReport {
        schema_version,
        content_id,
        result,
    })
}

fn validate_request(request: &GlmAgenticMappingRequest) -> Result<(), GlmAgenticMappingError> {
    if request.schema_version != GLM_AGENTIC_MAPPING_REQUEST_SCHEMA_VERSION {
        return Err(GlmAgenticMappingError::UnsupportedSchemaVersion {
            expected: GLM_AGENTIC_MAPPING_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    validate_text("study_id", &request.study_id)?;
    if request.concurrency_points != FIXED_CONCURRENCY_POINTS {
        return Err(GlmAgenticMappingError::InvalidField("concurrency_points"));
    }
    for pin in [
        &request.sources.proxy,
        &request.sources.storage,
        &request.sources.mapping_16k,
        &request.sources.mapping_90k,
        &request.sources.lowering_16k,
        &request.sources.lowering_90k,
    ] {
        validate_path(&pin.path)?;
        validate_hash("sources.file_blake3", &pin.file_blake3)?;
        validate_hash("sources.report_content_id", &pin.report_content_id)?;
    }
    validate_path(&request.sources.frontier_request.path)?;
    validate_hash(
        "sources.frontier_request.file_blake3",
        &request.sources.frontier_request.file_blake3,
    )?;
    let claims = &request.claims;
    if claims.quality_claim_permitted
        || claims.latency_claim_permitted
        || claims.throughput_claim_permitted
        || claims.slo_claim_permitted
        || claims.network_effect_claim_permitted
        || claims.energy_claim_permitted
        || claims.cost_claim_permitted
        || claims.provider_claim_permitted
        || claims.nvidia_performance_claim_permitted
        || claims.full_deployment_claim_permitted
    {
        return Err(GlmAgenticMappingError::ClaimGatePromoted);
    }
    if !request.retargeting.token_count_retarget_only
        || request.retargeting.prompt_or_tokenizer_equivalence_claimed
    {
        return Err(GlmAgenticMappingError::InvalidField("retargeting"));
    }
    for (field, value) in [
        (
            "retargeting.source_model_id",
            request.retargeting.source_model_id.as_str(),
        ),
        (
            "retargeting.source_model_revision",
            request.retargeting.source_model_revision.as_str(),
        ),
        (
            "retargeting.source_tokenizer_id",
            request.retargeting.source_tokenizer_id.as_str(),
        ),
        (
            "retargeting.source_tokenizer_revision",
            request.retargeting.source_tokenizer_revision.as_str(),
        ),
        (
            "retargeting.target_model_id",
            request.retargeting.target_model_id.as_str(),
        ),
        (
            "retargeting.target_model_revision",
            request.retargeting.target_model_revision.as_str(),
        ),
    ] {
        validate_text(field, value)?;
    }
    Ok(())
}

fn validate_file_hashes(
    request: &GlmAgenticMappingRequest,
    hashes: &GlmAgenticSourceFileHashes,
) -> Result<(), GlmAgenticMappingError> {
    let expected = [
        request.sources.proxy.file_blake3.as_str(),
        request.sources.frontier_request.file_blake3.as_str(),
        request.sources.storage.file_blake3.as_str(),
        request.sources.mapping_16k.file_blake3.as_str(),
        request.sources.mapping_90k.file_blake3.as_str(),
        request.sources.lowering_16k.file_blake3.as_str(),
        request.sources.lowering_90k.file_blake3.as_str(),
    ];
    let actual = [
        hashes.proxy.as_str(),
        hashes.frontier_request.as_str(),
        hashes.storage.as_str(),
        hashes.mapping_16k.as_str(),
        hashes.mapping_90k.as_str(),
        hashes.lowering_16k.as_str(),
        hashes.lowering_90k.as_str(),
    ];
    if actual.iter().any(|value| !is_lower_hex_256(value)) || expected != actual {
        return Err(GlmAgenticMappingError::SourceFileHashMismatch);
    }
    Ok(())
}

fn validate_sources(
    request: &GlmAgenticMappingRequest,
    proxy: &PublicAgenticProxyReport,
    storage: &GlmStorageEnvelopeReport,
    mapping_16k: &GlmParallelMappingReport,
    mapping_90k: &GlmParallelMappingReport,
    lowering_16k: &GlmDecodeLoweringReport,
    lowering_90k: &GlmDecodeLoweringReport,
) -> Result<(), GlmAgenticMappingError> {
    if !proxy.verify_content_id()?
        || proxy.content_id != request.sources.proxy.report_content_id
        || !storage
            .verify_content_id()
            .map_err(|_| GlmAgenticMappingError::InvalidSource)?
        || storage.content_id != request.sources.storage.report_content_id
        || !mapping_16k
            .verify_content_id()
            .map_err(|_| GlmAgenticMappingError::InvalidSource)?
        || mapping_16k.content_id != request.sources.mapping_16k.report_content_id
        || !mapping_90k
            .verify_content_id()
            .map_err(|_| GlmAgenticMappingError::InvalidSource)?
        || mapping_90k.content_id != request.sources.mapping_90k.report_content_id
        || !lowering_16k
            .verify_content_id()
            .map_err(|_| GlmAgenticMappingError::InvalidSource)?
        || lowering_16k.content_id != request.sources.lowering_16k.report_content_id
        || !lowering_90k
            .verify_content_id()
            .map_err(|_| GlmAgenticMappingError::InvalidSource)?
        || lowering_90k.content_id != request.sources.lowering_90k.report_content_id
    {
        return Err(GlmAgenticMappingError::InvalidSource);
    }
    proxy
        .result
        .trace
        .validate()
        .map_err(|_| GlmAgenticMappingError::InvalidSource)?;
    if proxy.result.public_basis.private_test_set_used
        || proxy.result.claim_gates.aa_agentperf_score_claim_permitted
        || proxy
            .result
            .claim_gates
            .measured_performance_claim_permitted
        || proxy.result.claim_gates.nvidia_performance_claim_permitted
        || proxy
            .result
            .claim_gates
            .provider_performance_claim_permitted
        || proxy.result.claim_gates.cost_claim_permitted
    {
        return Err(GlmAgenticMappingError::InvalidSource);
    }
    Ok(())
}

fn validate_retargeting(
    request: &GlmAgenticMappingRequest,
    proxy: &PublicAgenticProxyReport,
    mapping_16k: &GlmParallelMappingReport,
    mapping_90k: &GlmParallelMappingReport,
) -> Result<(), GlmAgenticMappingError> {
    let source = &proxy.result.trace.identity;
    let target = &request.retargeting;
    if target.source_model_id != source.model_id
        || target.source_model_revision != source.model_revision
        || target.source_tokenizer_id != source.tokenizer_id
        || target.source_tokenizer_revision != source.tokenizer_revision
        || target.target_model_id != mapping_16k.result.checkpoint_model_id
        || target.target_model_revision != mapping_16k.result.checkpoint_revision
        || target.target_model_id != mapping_90k.result.checkpoint_model_id
        || target.target_model_revision != mapping_90k.result.checkpoint_revision
    {
        return Err(GlmAgenticMappingError::RetargetingMismatch);
    }
    Ok(())
}

fn aggregate_concurrency(
    concurrency: u32,
    contexts: &[WeightedExactContext],
) -> Result<RequestWeightedConcurrency, GlmAgenticMappingError> {
    let mut aggregate = RequestWeightedConcurrency {
        concurrent_requests: concurrency,
        request_count: 0,
        partial_policy: PartialPolicyCounts::default(),
        baseline_full_capacity: CapacityStatusCounts::default(),
        candidate_full_capacity: CapacityStatusCounts::default(),
        capacity_relation: CapacityRelationCounts::default(),
        either_plan_uncertain_requests: 0,
        both_plans_uncertain_requests: 0,
    };
    for context in contexts {
        let point = context
            .points
            .iter()
            .find(|point| point.concurrent_requests == concurrency)
            .ok_or(GlmAgenticMappingError::AggregationMismatch)?;
        let weight = context.request_count;
        aggregate.request_count = aggregate
            .request_count
            .checked_add(weight)
            .ok_or(GlmAgenticMappingError::ArithmeticOverflow)?;
        aggregate.partial_policy.add(point.partial_policy, weight)?;
        aggregate
            .baseline_full_capacity
            .add(point.baseline_full_capacity.capacity_status, weight)?;
        aggregate
            .candidate_full_capacity
            .add(point.candidate_full_capacity.capacity_status, weight)?;
        aggregate
            .capacity_relation
            .add(point.full_capacity_relation, weight)?;
        let baseline_uncertain =
            point.baseline_full_capacity.capacity_status == CapacityStatus::Uncertain;
        let candidate_uncertain =
            point.candidate_full_capacity.capacity_status == CapacityStatus::Uncertain;
        if baseline_uncertain || candidate_uncertain {
            aggregate.either_plan_uncertain_requests = aggregate
                .either_plan_uncertain_requests
                .checked_add(weight)
                .ok_or(GlmAgenticMappingError::ArithmeticOverflow)?;
        }
        if baseline_uncertain && candidate_uncertain {
            aggregate.both_plans_uncertain_requests = aggregate
                .both_plans_uncertain_requests
                .checked_add(weight)
                .ok_or(GlmAgenticMappingError::ArithmeticOverflow)?;
        }
    }
    Ok(aggregate)
}

fn validate_path(path: &Path) -> Result<(), GlmAgenticMappingError> {
    if path.as_os_str().is_empty() || path.is_absolute() {
        Err(GlmAgenticMappingError::InvalidField("sources.path"))
    } else {
        Ok(())
    }
}

fn validate_hash(field: &'static str, value: &str) -> Result<(), GlmAgenticMappingError> {
    if is_lower_hex_256(value) {
        Ok(())
    } else {
        Err(GlmAgenticMappingError::InvalidField(field))
    }
}

fn validate_text(field: &'static str, value: &str) -> Result<(), GlmAgenticMappingError> {
    if value.trim().is_empty() {
        Err(GlmAgenticMappingError::InvalidField(field))
    } else {
        Ok(())
    }
}

fn is_lower_hex_256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn report_content_id(
    schema_version: u32,
    result: &GlmAgenticMappingResult,
) -> Result<String, GlmAgenticMappingError> {
    Ok(
        blake3::hash(&serde_json::to_vec(&(schema_version, result))?)
            .to_hex()
            .to_string(),
    )
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum GlmAgenticMappingError {
    #[error("unsupported GLM agentic mapping schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid GLM agentic mapping field {0}")]
    InvalidField(&'static str),
    #[error("a prohibited GLM agentic mapping claim gate was promoted")]
    ClaimGatePromoted,
    #[error("a source file BLAKE3 pin did not match")]
    SourceFileHashMismatch,
    #[error("a source report or content ID was invalid")]
    InvalidSource,
    #[error("the synthetic proxy retargeting identity did not match GLM")]
    RetargetingMismatch,
    #[error("request-weighted GLM agentic mapping aggregation did not reconcile")]
    AggregationMismatch,
    #[error("GLM agentic mapping count exceeds the supported range")]
    CountOverflow,
    #[error("GLM agentic mapping arithmetic overflow")]
    ArithmeticOverflow,
    #[error(transparent)]
    ExactResidency(#[from] GlmMappingContextFrontierError),
    #[error(transparent)]
    Proxy(#[from] PublicAgenticProxyError),
    #[error("GLM agentic mapping serialization failed: {0}")]
    Serialization(String),
}

impl From<serde_json::Error> for GlmAgenticMappingError {
    fn from(error: serde_json::Error) -> Self {
        Self::Serialization(error.to_string())
    }
}
