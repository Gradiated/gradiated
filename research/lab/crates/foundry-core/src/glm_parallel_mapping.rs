use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::glm_decode::{
    DecodeRouteInput, GlmDecodeLoweringReport, GlmDecodeLoweringRequest,
    evaluate_glm_decode_lowering,
};
use crate::glm_dsa::GlmDsaSweepReport;
use crate::glm_moe_route::{GLM_MOE_LAYER_COUNT, GlmMoeRouteReport};
use crate::glm_storage::{
    ByteBounds, GlmStorageEnvelopeReport, GlmVariantEnvelopeReport, HardwareVariantEnvelopeReport,
};

pub const GLM_PARALLEL_MAPPING_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const GLM_PARALLEL_MAPPING_REPORT_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MappingSourcePins {
    pub storage_report_content_id: String,
    pub route_report_content_id: String,
    pub dsa_report_content_id: String,
    pub lowering_report_content_id: String,
    pub lower_action_ledger_content_id: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MappingEvidenceKind {
    PublishedMechanism,
    PublishedSpecification,
    AnalyticalBound,
    ModeledAssumption,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MappingEvidence {
    pub kind: MappingEvidenceKind,
    pub source_artifact_id: String,
    pub basis: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SemanticCacheScenario {
    pub format_id: String,
    pub bytes_per_token: u64,
    pub evidence: MappingEvidence,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TopologyDomain {
    pub domain_id: String,
    pub ordered_device_ids: Vec<u32>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PhysicalTopologyFixture {
    pub topology_id: String,
    pub device_count: u32,
    pub domains: Vec<TopologyDomain>,
    pub evidence: MappingEvidence,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NetworkWorkloadRequest {
    pub integer_repetitions: u32,
    pub attention_collectives_per_layer: u32,
    pub moe_collectives_per_layer: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ResidencySweepRequest {
    pub context_tokens_per_request: u64,
    pub concurrency_points: Vec<u32>,
    pub crossover_min_concurrency: u32,
    pub crossover_max_concurrency: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DeviceGroup {
    pub group_id: String,
    pub ordered_device_ids: Vec<u32>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum AttentionParallelism {
    TensorParallel,
    DataParallelLocal,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExpertParallelism {
    TensorParallel,
    ExpertParallel,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SemanticCachePlacement {
    AttentionGroupLocal,
    ReplicatedAcrossAllDevices,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum NonRoutedWeightMapping {
    AttentionGroupsExact,
    OpaqueGlobalShardToAttentionReplication,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExpertNetworkModel {
    TensorParallelCollective,
    PinnedLowererRoute,
    ZeroRemoteAnalyticalLowerBound,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ParallelPlan {
    pub plan_id: String,
    pub attention_parallelism: AttentionParallelism,
    pub attention_groups: Vec<DeviceGroup>,
    pub expert_parallelism: ExpertParallelism,
    pub expert_groups: Vec<DeviceGroup>,
    pub semantic_cache_placement: SemanticCachePlacement,
    pub non_routed_weight_mapping: NonRoutedWeightMapping,
    pub expert_network_model: ExpertNetworkModel,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PartialComparisonRequest {
    pub baseline_plan_id: String,
    pub candidate_plan_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmParallelMappingRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub sources: MappingSourcePins,
    pub mechanism_evidence: Vec<MappingEvidence>,
    pub variant_id: String,
    pub device_profile_id: String,
    pub semantic_cache: SemanticCacheScenario,
    pub topology: PhysicalTopologyFixture,
    pub network_workload: NetworkWorkloadRequest,
    pub residency_sweep: ResidencySweepRequest,
    pub plans: Vec<ParallelPlan>,
    pub partial_comparison: PartialComparisonRequest,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct U64Bounds {
    pub lower: u64,
    pub upper: u64,
}

impl U64Bounds {
    const fn exact(value: u64) -> Self {
        Self {
            lower: value,
            upper: value,
        }
    }

    fn checked_add(self, other: Self) -> Result<Self, GlmParallelMappingError> {
        Ok(Self {
            lower: checked_add(self.lower, other.lower)?,
            upper: checked_add(self.upper, other.upper)?,
        })
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SignedBounds {
    pub lower: i128,
    pub upper: i128,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NetworkWorkloadReport {
    pub source_lowering_id: String,
    pub batch_size_per_repetition: u32,
    pub context_tokens_per_request: u64,
    pub candidate_tokens_per_repetition: u64,
    pub integer_repetitions: u32,
    pub aggregate_batch_size: u64,
    pub aggregate_candidate_tokens: u64,
    pub hidden_payload_bytes_per_repetition: u64,
    pub token_count_scope: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum NetworkActionKind {
    AttentionTensorParallel,
    MoeTensorParallel,
    ExpertDispatch,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CrossDomainAccounting {
    Exact,
    UnresolvedWithoutPartitionedFlowHistogram,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NetworkActionReport {
    pub kind: NetworkActionKind,
    pub layer_count: u32,
    pub collectives_or_route_repetitions: u64,
    pub endpoint_payload_bytes: U64Bounds,
    pub endpoint_message_count: U64Bounds,
    pub network_hop_payload_bytes: U64Bounds,
    pub network_hop_message_count: U64Bounds,
    pub cross_domain_payload_bytes: U64Bounds,
    pub cross_domain_message_count: U64Bounds,
    pub cross_domain_accounting: CrossDomainAccounting,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NetworkTotals {
    pub endpoint_payload_bytes: U64Bounds,
    pub endpoint_message_count: U64Bounds,
    pub network_hop_payload_bytes: U64Bounds,
    pub network_hop_message_count: U64Bounds,
    pub cross_domain_payload_bytes: U64Bounds,
    pub cross_domain_message_count: U64Bounds,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ParallelNetworkReport {
    pub actions: Vec<NetworkActionReport>,
    pub total: NetworkTotals,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PartialResidencyScope {
    RoutedWeightsPlusSemanticCacheOnly,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PartialResidencyReport {
    pub scope: PartialResidencyScope,
    pub routed_weight_bytes_on_max_device: ByteBounds,
    pub semantic_cache_copies_on_max_device: u32,
    pub semantic_cache_bytes_on_max_device: u64,
    pub total_bytes_on_max_device: ByteBounds,
    pub cluster_total_bytes: ByteBounds,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CapacityStatus {
    Feasible,
    Uncertain,
    Infeasible,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FullMappedResidencyReport {
    pub checkpoint_weight_bytes_on_max_device: ByteBounds,
    pub semantic_cache_bytes_on_max_device: u64,
    pub extra_and_indexer_cache_bytes_on_max_device: ByteBounds,
    pub fixed_runtime_bytes_on_device: u64,
    pub unfragmented_bytes_on_max_device: ByteBounds,
    pub fragmentation_overhead_bytes_on_max_device: ByteBounds,
    pub total_bytes_on_max_device: ByteBounds,
    pub usable_memory_bytes_per_device: u64,
    pub capacity_status: CapacityStatus,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ResidencyPoint {
    pub concurrent_requests: u32,
    pub context_tokens_per_request: u64,
    pub partial: PartialResidencyReport,
    pub full: FullMappedResidencyReport,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ParallelPlanReport {
    pub plan_id: String,
    pub attention_parallelism: AttentionParallelism,
    pub attention_groups: Vec<DeviceGroup>,
    pub expert_parallelism: ExpertParallelism,
    pub expert_groups: Vec<DeviceGroup>,
    pub semantic_cache_placement: SemanticCachePlacement,
    pub non_routed_weight_mapping: NonRoutedWeightMapping,
    pub expert_network_model: ExpertNetworkModel,
    pub routed_weight_replication_factor: u32,
    pub non_routed_weight_replication_factor: u32,
    pub network: ParallelNetworkReport,
    pub residency: Vec<ResidencyPoint>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Dominance {
    BaselineLower,
    BoundsOverlap,
    CandidateLower,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PartialResidencyComparison {
    pub concurrent_requests: u32,
    pub candidate_minus_baseline_cluster_total_bytes: SignedBounds,
    pub cluster_total_partial_dominance: Dominance,
    pub candidate_minus_baseline_max_device_bytes: SignedBounds,
    pub max_device_partial_dominance: Dominance,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DominanceRegion {
    pub start_concurrency: u32,
    pub end_concurrency: u32,
    pub dominance: Dominance,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PartialCrossoverReport {
    pub baseline_plan_id: String,
    pub candidate_plan_id: String,
    pub search_min_concurrency: u32,
    pub search_max_concurrency: u32,
    pub cluster_total_regions: Vec<DominanceRegion>,
    pub max_device_regions: Vec<DominanceRegion>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NetworkComparison {
    pub baseline_plan_id: String,
    pub candidate_plan_id: String,
    pub candidate_minus_baseline_network_hop_payload_bytes: SignedBounds,
    pub network_hop_payload_dominance: Dominance,
    pub candidate_minus_baseline_network_hop_message_count: SignedBounds,
    pub network_hop_message_dominance: Dominance,
    pub candidate_minus_baseline_cross_domain_payload_bytes: SignedBounds,
    pub cross_domain_payload_dominance: Dominance,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ClaimBlocker {
    RouteHistogramIsSynthetic,
    CheckpointExpertLayoutIsOpaque,
    CacheScaleAndMetadataAreExcluded,
    CollectiveTimingIsNotCalibrated,
    CrossDomainLinkPerformanceIsNotMeasured,
    RuntimeDistributionIsModeled,
    ServingAndContentionAreNotModeled,
    QualityContractIsNotProvided,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ParallelMappingClaimGate {
    pub partial_residency_accounting_permitted: bool,
    pub modeled_capacity_arithmetic_permitted: bool,
    pub end_to_end_latency_claim_permitted: bool,
    pub throughput_claim_permitted: bool,
    pub cost_per_token_claim_permitted: bool,
    pub quality_claim_permitted: bool,
    pub blockers: Vec<ClaimBlocker>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmParallelMappingResult {
    pub study_id: String,
    pub sources: MappingSourcePins,
    pub mechanism_evidence: Vec<MappingEvidence>,
    pub variant_id: String,
    pub checkpoint_model_id: String,
    pub checkpoint_revision: String,
    pub checkpoint_payload_bytes: u64,
    pub routed_expert_resident_bytes: ByteBounds,
    pub source_semantic_cache_bytes_per_token: u64,
    pub semantic_cache: SemanticCacheScenario,
    pub topology: PhysicalTopologyFixture,
    pub device_profile_id: String,
    pub usable_memory_bytes_per_device: u64,
    pub network_workload: NetworkWorkloadReport,
    pub residency_context_tokens_per_request: u64,
    pub plans: Vec<ParallelPlanReport>,
    pub network_comparison: NetworkComparison,
    pub partial_comparisons: Vec<PartialResidencyComparison>,
    pub partial_crossover: PartialCrossoverReport,
    pub claims: ParallelMappingClaimGate,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmParallelMappingReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: GlmParallelMappingResult,
}

impl GlmParallelMappingReport {
    pub fn verify_content_id(&self) -> Result<bool, GlmParallelMappingError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

struct ValidatedInputs<'a> {
    variant: &'a GlmVariantEnvelopeReport,
    hardware: &'a HardwareVariantEnvelopeReport,
    routed: ByteBounds,
    source_semantic_bytes_per_token: u64,
    runtime_bytes_per_device: u64,
    attention_layer_count: u32,
    network_workload: NetworkWorkloadReport,
    device_domains: BTreeMap<u32, String>,
}

pub fn evaluate_glm_parallel_mapping(
    request: &GlmParallelMappingRequest,
    storage: &GlmStorageEnvelopeReport,
    route: &GlmMoeRouteReport,
    dsa: &GlmDsaSweepReport,
    lowering_request: &GlmDecodeLoweringRequest,
    lowering: &GlmDecodeLoweringReport,
) -> Result<GlmParallelMappingReport, GlmParallelMappingError> {
    let validated = validate_inputs(request, storage, route, dsa, lowering_request, lowering)?;
    let plans = request
        .plans
        .iter()
        .map(|plan| evaluate_plan(request, plan, storage, lowering, &validated))
        .collect::<Result<Vec<_>, _>>()?;
    let baseline = find_plan(&plans, &request.partial_comparison.baseline_plan_id)?;
    let candidate = find_plan(&plans, &request.partial_comparison.candidate_plan_id)?;
    let partial_comparisons = request
        .residency_sweep
        .concurrency_points
        .iter()
        .map(|concurrency| {
            compare_partial(request, baseline, candidate, validated.routed, *concurrency)
        })
        .collect::<Result<Vec<_>, _>>()?;
    let network_comparison = compare_network(baseline, candidate)?;
    let partial_crossover = evaluate_crossover(request, baseline, candidate, validated.routed)?;
    let result = GlmParallelMappingResult {
        study_id: request.study_id.clone(),
        sources: request.sources.clone(),
        mechanism_evidence: request.mechanism_evidence.clone(),
        variant_id: request.variant_id.clone(),
        checkpoint_model_id: validated.variant.checkpoint.model_id.clone(),
        checkpoint_revision: validated.variant.checkpoint.checkpoint_revision.clone(),
        checkpoint_payload_bytes: validated.variant.checkpoint.payload_bytes,
        routed_expert_resident_bytes: validated.routed,
        source_semantic_cache_bytes_per_token: validated.source_semantic_bytes_per_token,
        semantic_cache: request.semantic_cache.clone(),
        topology: request.topology.clone(),
        device_profile_id: request.device_profile_id.clone(),
        usable_memory_bytes_per_device: validated.hardware.usable_memory_bytes_per_device,
        network_workload: validated.network_workload,
        residency_context_tokens_per_request: request.residency_sweep.context_tokens_per_request,
        plans,
        network_comparison,
        partial_comparisons,
        partial_crossover,
        claims: claim_gate(),
    };
    let schema_version = GLM_PARALLEL_MAPPING_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(GlmParallelMappingReport {
        schema_version,
        content_id,
        result,
    })
}

fn validate_inputs<'a>(
    request: &GlmParallelMappingRequest,
    storage: &'a GlmStorageEnvelopeReport,
    route: &GlmMoeRouteReport,
    dsa: &GlmDsaSweepReport,
    lowering_request: &GlmDecodeLoweringRequest,
    lowering: &GlmDecodeLoweringReport,
) -> Result<ValidatedInputs<'a>, GlmParallelMappingError> {
    if request.schema_version != GLM_PARALLEL_MAPPING_REQUEST_SCHEMA_VERSION {
        return Err(GlmParallelMappingError::UnsupportedSchemaVersion {
            expected: GLM_PARALLEL_MAPPING_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    for (field, value) in [
        ("study_id", request.study_id.as_str()),
        ("variant_id", request.variant_id.as_str()),
        ("device_profile_id", request.device_profile_id.as_str()),
        (
            "semantic_cache.format_id",
            request.semantic_cache.format_id.as_str(),
        ),
        (
            "topology.topology_id",
            request.topology.topology_id.as_str(),
        ),
        (
            "partial_comparison.baseline_plan_id",
            request.partial_comparison.baseline_plan_id.as_str(),
        ),
        (
            "partial_comparison.candidate_plan_id",
            request.partial_comparison.candidate_plan_id.as_str(),
        ),
    ] {
        validate_required(field, value)?;
    }
    validate_sources(request, storage, route, dsa, lowering_request, lowering)?;
    validate_evidence("semantic_cache.evidence", &request.semantic_cache.evidence)?;
    if request.mechanism_evidence.is_empty() {
        return Err(GlmParallelMappingError::InvalidField("mechanism_evidence"));
    }
    for evidence in &request.mechanism_evidence {
        validate_evidence("mechanism_evidence", evidence)?;
    }
    let variant = storage
        .result
        .variants
        .iter()
        .find(|variant| variant.variant_id == request.variant_id)
        .ok_or(GlmParallelMappingError::VariantNotFound)?;
    let hardware = variant
        .hardware
        .iter()
        .find(|hardware| hardware.hardware_id == request.device_profile_id)
        .ok_or(GlmParallelMappingError::DeviceProfileNotFound)?;
    if variant.checkpoint != lowering.result.checkpoint.checkpoint
        || request.variant_id != lowering.result.checkpoint.variant_id
    {
        return Err(GlmParallelMappingError::CheckpointIdentityMismatch);
    }
    let routed = lowering
        .result
        .weights
        .routed_expert_resident_byte_bounds
        .and_then(|bounds| {
            bounds
                .upper
                .map(|upper| ByteBounds::new(bounds.lower, upper))
        })
        .ok_or(GlmParallelMappingError::ClosedRoutedExpertBoundsRequired)?;
    if routed != variant.routed_experts.resident_storage_bytes {
        return Err(GlmParallelMappingError::RoutedExpertBoundsMismatch);
    }
    let checkpoint_payload = variant.checkpoint.payload_bytes;
    let expected_non_routed_upper = checkpoint_payload
        .checked_sub(routed.lower)
        .ok_or(GlmParallelMappingError::ArithmeticOverflow)?;
    let non_routed = lowering
        .result
        .weights
        .non_routed_resident_byte_bounds
        .ok_or(GlmParallelMappingError::ClosedNonRoutedBoundsRequired)?;
    if non_routed.lower != 0
        || non_routed.upper != Some(expected_non_routed_upper)
        || routed.upper != checkpoint_payload
    {
        return Err(GlmParallelMappingError::CheckpointCorrelationMismatch);
    }
    let source_semantic_bytes_per_token = validate_semantic_cache(request, storage, dsa)?;
    let device_domains = validate_topology(request, hardware)?;
    validate_residency_sweep(request, lowering_request)?;
    validate_plans(request, lowering)?;
    let fixed_runtime = storage.result.residency_assumptions.fixed_runtime_bytes;
    if fixed_runtime % u64::from(request.topology.device_count) != 0 {
        return Err(GlmParallelMappingError::RuntimeDoesNotDistributeExactly);
    }
    validate_weight_divisibility(request, checkpoint_payload, routed)?;
    let network_workload = network_workload(request, lowering_request)?;
    Ok(ValidatedInputs {
        variant,
        hardware,
        routed,
        source_semantic_bytes_per_token,
        runtime_bytes_per_device: fixed_runtime / u64::from(request.topology.device_count),
        attention_layer_count: dsa.result.layer_count,
        network_workload,
        device_domains,
    })
}

fn validate_sources(
    request: &GlmParallelMappingRequest,
    storage: &GlmStorageEnvelopeReport,
    route: &GlmMoeRouteReport,
    dsa: &GlmDsaSweepReport,
    lowering_request: &GlmDecodeLoweringRequest,
    lowering: &GlmDecodeLoweringReport,
) -> Result<(), GlmParallelMappingError> {
    if !storage
        .verify_content_id()
        .map_err(|_| GlmParallelMappingError::InvalidStorageReportContentId)?
    {
        return Err(GlmParallelMappingError::InvalidStorageReportContentId);
    }
    if !route
        .verify_content_id()
        .map_err(|_| GlmParallelMappingError::InvalidRouteReportContentId)?
    {
        return Err(GlmParallelMappingError::InvalidRouteReportContentId);
    }
    if !dsa
        .verify_content_id()
        .map_err(|_| GlmParallelMappingError::InvalidDsaReportContentId)?
    {
        return Err(GlmParallelMappingError::InvalidDsaReportContentId);
    }
    if !lowering
        .verify_content_id()
        .map_err(|_| GlmParallelMappingError::InvalidLoweringReportContentId)?
    {
        return Err(GlmParallelMappingError::InvalidLoweringReportContentId);
    }
    if request.sources.storage_report_content_id != storage.content_id {
        return Err(GlmParallelMappingError::StorageReportContentIdMismatch);
    }
    if request.sources.route_report_content_id != route.content_id {
        return Err(GlmParallelMappingError::RouteReportContentIdMismatch);
    }
    if request.sources.dsa_report_content_id != dsa.content_id {
        return Err(GlmParallelMappingError::DsaReportContentIdMismatch);
    }
    if request.sources.lowering_report_content_id != lowering.content_id {
        return Err(GlmParallelMappingError::LoweringReportContentIdMismatch);
    }
    let lower_ledger_id = lowering
        .result
        .lower_bound_ledger
        .content_id()
        .map_err(|_| GlmParallelMappingError::InvalidLowerActionLedgerContentId)?;
    if lower_ledger_id.as_str() != lowering.result.lower_bound_ledger_content_id
        || request.sources.lower_action_ledger_content_id != lower_ledger_id.as_str()
    {
        return Err(GlmParallelMappingError::LowerActionLedgerContentIdMismatch);
    }
    let evaluated = evaluate_glm_decode_lowering(lowering_request)
        .map_err(|_| GlmParallelMappingError::LoweringRequestDoesNotReproduceReport)?;
    if &evaluated != lowering {
        return Err(GlmParallelMappingError::LoweringRequestDoesNotReproduceReport);
    }
    validate_route_selection(lowering_request, lowering, route)
}

fn validate_route_selection(
    lowering_request: &GlmDecodeLoweringRequest,
    lowering: &GlmDecodeLoweringReport,
    route: &GlmMoeRouteReport,
) -> Result<(), GlmParallelMappingError> {
    let DecodeRouteInput::PinnedRouteReportSelection(selection) = &lowering_request.route else {
        return Err(GlmParallelMappingError::PinnedRouteSelectionRequired);
    };
    if selection.report_content_id != route.content_id {
        return Err(GlmParallelMappingError::RouteReportContentIdMismatch);
    }
    let scenario = route
        .result
        .scenarios
        .iter()
        .find(|scenario| scenario.scenario_id == selection.scenario_id)
        .ok_or(GlmParallelMappingError::RouteSelectionNotFound)?;
    let topology = scenario
        .topologies
        .iter()
        .find(|topology| topology.topology_id == selection.topology_id)
        .ok_or(GlmParallelMappingError::RouteSelectionNotFound)?;
    let strategy = topology
        .strategies
        .iter()
        .find(|strategy| strategy.strategy_id == selection.strategy_id)
        .ok_or(GlmParallelMappingError::RouteSelectionNotFound)?;
    let traffic = &strategy.traffic;
    if selection.sample_total_dispatches != traffic.total_dispatches
        || selection.sample_remote_dispatches != traffic.remote_dispatches
        || selection.sample_endpoint_payload_bytes != traffic.endpoint_payload_bytes_lower_bound
        || selection.sample_endpoint_message_count != traffic.endpoint_message_count_lower_bound
        || selection.sample_network_hop_payload_bytes
            != traffic.network_hop_payload_bytes_lower_bound
        || selection.sample_network_hop_message_count
            != traffic.network_hop_message_count_lower_bound
        || selection.participants != topology.device_count
        || lowering.result.route.participants != topology.device_count
    {
        return Err(GlmParallelMappingError::RouteSelectionLedgerMismatch);
    }
    Ok(())
}

fn validate_semantic_cache(
    request: &GlmParallelMappingRequest,
    storage: &GlmStorageEnvelopeReport,
    dsa: &GlmDsaSweepReport,
) -> Result<u64, GlmParallelMappingError> {
    if dsa.result.points.is_empty() {
        return Err(GlmParallelMappingError::DsaSemanticGeometryMismatch);
    }
    let per_layer = dsa.result.points[0].semantic_cache_bytes_per_layer_token;
    if dsa
        .result
        .points
        .iter()
        .any(|point| point.semantic_cache_bytes_per_layer_token != per_layer)
    {
        return Err(GlmParallelMappingError::DsaSemanticGeometryMismatch);
    }
    let source = per_layer
        .checked_mul(u64::from(dsa.result.layer_count))
        .ok_or(GlmParallelMappingError::ArithmeticOverflow)?;
    if source != storage.result.semantic_mla_cache_bytes_per_token
        || request.semantic_cache.bytes_per_token == 0
        || request.semantic_cache.bytes_per_token > source
    {
        return Err(GlmParallelMappingError::DsaSemanticGeometryMismatch);
    }
    Ok(source)
}

fn validate_topology(
    request: &GlmParallelMappingRequest,
    hardware: &HardwareVariantEnvelopeReport,
) -> Result<BTreeMap<u32, String>, GlmParallelMappingError> {
    validate_evidence("topology.evidence", &request.topology.evidence)?;
    if request.topology.device_count == 0
        || request.topology.device_count != hardware.deployment_device_count
        || request.topology.domains.is_empty()
    {
        return Err(GlmParallelMappingError::TopologyDeviceMismatch);
    }
    let mut domains = BTreeMap::new();
    let mut domain_ids = BTreeSet::new();
    for domain in &request.topology.domains {
        validate_required("topology.domains.domain_id", &domain.domain_id)?;
        if domain.ordered_device_ids.is_empty() || !domain_ids.insert(domain.domain_id.as_str()) {
            return Err(GlmParallelMappingError::InvalidTopologyPartition);
        }
        for device in &domain.ordered_device_ids {
            if *device >= request.topology.device_count
                || domains.insert(*device, domain.domain_id.clone()).is_some()
            {
                return Err(GlmParallelMappingError::InvalidTopologyPartition);
            }
        }
    }
    if domains.len()
        != usize::try_from(request.topology.device_count)
            .map_err(|_| GlmParallelMappingError::ArithmeticOverflow)?
    {
        return Err(GlmParallelMappingError::InvalidTopologyPartition);
    }
    Ok(domains)
}

fn validate_residency_sweep(
    request: &GlmParallelMappingRequest,
    lowering_request: &GlmDecodeLoweringRequest,
) -> Result<(), GlmParallelMappingError> {
    let sweep = &request.residency_sweep;
    if sweep.context_tokens_per_request == 0
        || sweep.context_tokens_per_request != lowering_request.workload.context_tokens_per_request
        || sweep.concurrency_points.is_empty()
        || sweep.crossover_min_concurrency == 0
        || sweep.crossover_min_concurrency > sweep.crossover_max_concurrency
    {
        return Err(GlmParallelMappingError::InvalidField("residency_sweep"));
    }
    let mut points = BTreeSet::new();
    if sweep
        .concurrency_points
        .iter()
        .any(|point| *point == 0 || !points.insert(*point))
    {
        return Err(GlmParallelMappingError::InvalidField(
            "residency_sweep.concurrency_points",
        ));
    }
    Ok(())
}

fn validate_plans(
    request: &GlmParallelMappingRequest,
    lowering: &GlmDecodeLoweringReport,
) -> Result<(), GlmParallelMappingError> {
    if request.plans.is_empty()
        || request.network_workload.integer_repetitions == 0
        || request.network_workload.attention_collectives_per_layer == 0
        || request.network_workload.moe_collectives_per_layer == 0
    {
        return Err(GlmParallelMappingError::InvalidField("plans"));
    }
    let mut plan_ids = BTreeSet::new();
    for plan in &request.plans {
        validate_required("plans.plan_id", &plan.plan_id)?;
        if !plan_ids.insert(plan.plan_id.as_str()) {
            return Err(GlmParallelMappingError::DuplicatePlan(plan.plan_id.clone()));
        }
        validate_groups(
            &plan.plan_id,
            "attention_groups",
            &plan.attention_groups,
            request.topology.device_count,
        )?;
        validate_groups(
            &plan.plan_id,
            "expert_groups",
            &plan.expert_groups,
            request.topology.device_count,
        )?;
        if plan.attention_parallelism == AttentionParallelism::DataParallelLocal
            && plan
                .attention_groups
                .iter()
                .any(|group| group.ordered_device_ids.len() != 1)
        {
            return Err(GlmParallelMappingError::InvalidPlan(plan.plan_id.clone()));
        }
        match (plan.expert_parallelism, plan.expert_network_model) {
            (ExpertParallelism::TensorParallel, ExpertNetworkModel::TensorParallelCollective)
            | (ExpertParallelism::ExpertParallel, ExpertNetworkModel::PinnedLowererRoute)
            | (
                ExpertParallelism::ExpertParallel,
                ExpertNetworkModel::ZeroRemoteAnalyticalLowerBound,
            ) => {}
            _ => return Err(GlmParallelMappingError::InvalidPlan(plan.plan_id.clone())),
        }
        if plan.expert_parallelism == ExpertParallelism::ExpertParallel {
            let participants = usize::try_from(lowering.result.route.participants)
                .map_err(|_| GlmParallelMappingError::ArithmeticOverflow)?;
            if plan
                .expert_groups
                .iter()
                .any(|group| group.ordered_device_ids.len() != participants)
            {
                return Err(GlmParallelMappingError::InvalidPlan(plan.plan_id.clone()));
            }
        }
        for group_count in network_group_counts(plan) {
            if request.network_workload.integer_repetitions % group_count != 0 {
                return Err(
                    GlmParallelMappingError::WorkRepetitionsDoNotPartitionExpertGroups {
                        plan_id: plan.plan_id.clone(),
                    },
                );
            }
        }
    }
    if !plan_ids.contains(request.partial_comparison.baseline_plan_id.as_str())
        || !plan_ids.contains(request.partial_comparison.candidate_plan_id.as_str())
        || request.partial_comparison.baseline_plan_id
            == request.partial_comparison.candidate_plan_id
    {
        return Err(GlmParallelMappingError::InvalidField("partial_comparison"));
    }
    Ok(())
}

fn validate_groups(
    plan_id: &str,
    field: &'static str,
    groups: &[DeviceGroup],
    device_count: u32,
) -> Result<(), GlmParallelMappingError> {
    if groups.is_empty() {
        return Err(GlmParallelMappingError::InvalidPlan(plan_id.into()));
    }
    let expected_size = groups[0].ordered_device_ids.len();
    let mut group_ids = BTreeSet::new();
    let mut devices = BTreeSet::new();
    for group in groups {
        if group.group_id.is_empty()
            || group.ordered_device_ids.is_empty()
            || group.ordered_device_ids.len() != expected_size
            || !group_ids.insert(group.group_id.as_str())
        {
            return Err(GlmParallelMappingError::InvalidPlan(plan_id.into()));
        }
        for device in &group.ordered_device_ids {
            if *device >= device_count || !devices.insert(*device) {
                return Err(GlmParallelMappingError::InvalidPlan(plan_id.into()));
            }
        }
    }
    if devices.len()
        != usize::try_from(device_count).map_err(|_| GlmParallelMappingError::ArithmeticOverflow)?
    {
        return Err(GlmParallelMappingError::InvalidField(field));
    }
    Ok(())
}

fn network_group_counts(plan: &ParallelPlan) -> Vec<u32> {
    let mut counts = Vec::new();
    if plan.attention_parallelism == AttentionParallelism::TensorParallel {
        counts.push(plan.attention_groups.len() as u32);
    }
    counts.push(plan.expert_groups.len() as u32);
    counts
}

fn validate_weight_divisibility(
    request: &GlmParallelMappingRequest,
    checkpoint_payload: u64,
    routed: ByteBounds,
) -> Result<(), GlmParallelMappingError> {
    for plan in &request.plans {
        let attention_degree = group_degree(&plan.attention_groups)?;
        let expert_degree = group_degree(&plan.expert_groups)?;
        let non_routed_degrees = match plan.non_routed_weight_mapping {
            NonRoutedWeightMapping::AttentionGroupsExact => {
                vec![attention_degree]
            }
            NonRoutedWeightMapping::OpaqueGlobalShardToAttentionReplication => {
                vec![request.topology.device_count, attention_degree]
            }
        };
        for bytes in [routed.lower, routed.upper] {
            let non_routed = checkpoint_payload
                .checked_sub(bytes)
                .ok_or(GlmParallelMappingError::ArithmeticOverflow)?;
            if bytes % u64::from(expert_degree) != 0
                || non_routed_degrees
                    .iter()
                    .any(|degree| non_routed % u64::from(*degree) != 0)
            {
                return Err(GlmParallelMappingError::WeightBoundsDoNotShardExactly {
                    plan_id: plan.plan_id.clone(),
                });
            }
        }
    }
    Ok(())
}

fn network_workload(
    request: &GlmParallelMappingRequest,
    lowering_request: &GlmDecodeLoweringRequest,
) -> Result<NetworkWorkloadReport, GlmParallelMappingError> {
    let workload = &lowering_request.workload;
    let payload_elements = workload
        .candidate_tokens
        .checked_mul(u64::from(lowering_request.model.hidden_size))
        .ok_or(GlmParallelMappingError::ArithmeticOverflow)?;
    let payload_bits = payload_elements
        .checked_mul(u64::from(
            lowering_request.network_activation_precision.bits(),
        ))
        .ok_or(GlmParallelMappingError::ArithmeticOverflow)?;
    if payload_bits % 8 != 0 {
        return Err(GlmParallelMappingError::ActivationPayloadIsNotByteAligned);
    }
    let repetitions = u64::from(request.network_workload.integer_repetitions);
    Ok(NetworkWorkloadReport {
        source_lowering_id: lowering_request.lowering_id.clone(),
        batch_size_per_repetition: workload.batch_size,
        context_tokens_per_request: workload.context_tokens_per_request,
        candidate_tokens_per_repetition: workload.candidate_tokens,
        integer_repetitions: request.network_workload.integer_repetitions,
        aggregate_batch_size: checked_mul(u64::from(workload.batch_size), repetitions)?,
        aggregate_candidate_tokens: checked_mul(workload.candidate_tokens, repetitions)?,
        hidden_payload_bytes_per_repetition: payload_bits / 8,
        token_count_scope: "each repetition is the exact aggregate-across-batch lowerer workload; repetitions are integer work units and are never fractional route scaling".into(),
    })
}

fn evaluate_plan(
    request: &GlmParallelMappingRequest,
    plan: &ParallelPlan,
    storage: &GlmStorageEnvelopeReport,
    lowering: &GlmDecodeLoweringReport,
    validated: &ValidatedInputs<'_>,
) -> Result<ParallelPlanReport, GlmParallelMappingError> {
    let network = evaluate_network(request, plan, lowering, validated)?;
    let residency = request
        .residency_sweep
        .concurrency_points
        .iter()
        .map(|concurrency| evaluate_residency(request, plan, storage, validated, *concurrency))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(ParallelPlanReport {
        plan_id: plan.plan_id.clone(),
        attention_parallelism: plan.attention_parallelism,
        attention_groups: plan.attention_groups.clone(),
        expert_parallelism: plan.expert_parallelism,
        expert_groups: plan.expert_groups.clone(),
        semantic_cache_placement: plan.semantic_cache_placement,
        non_routed_weight_mapping: plan.non_routed_weight_mapping,
        expert_network_model: plan.expert_network_model,
        routed_weight_replication_factor: plan.expert_groups.len() as u32,
        non_routed_weight_replication_factor: plan.attention_groups.len() as u32,
        network,
        residency,
    })
}

fn evaluate_network(
    request: &GlmParallelMappingRequest,
    plan: &ParallelPlan,
    lowering: &GlmDecodeLoweringReport,
    validated: &ValidatedInputs<'_>,
) -> Result<ParallelNetworkReport, GlmParallelMappingError> {
    let mut actions = Vec::new();
    if plan.attention_parallelism == AttentionParallelism::TensorParallel {
        actions.push(ring_action(
            NetworkActionKind::AttentionTensorParallel,
            validated.attention_layer_count,
            request.network_workload.attention_collectives_per_layer,
            request.network_workload.integer_repetitions,
            validated
                .network_workload
                .hidden_payload_bytes_per_repetition,
            &plan.attention_groups,
            &validated.device_domains,
        )?);
    }
    match plan.expert_network_model {
        ExpertNetworkModel::TensorParallelCollective => actions.push(ring_action(
            NetworkActionKind::MoeTensorParallel,
            GLM_MOE_LAYER_COUNT,
            request.network_workload.moe_collectives_per_layer,
            request.network_workload.integer_repetitions,
            validated
                .network_workload
                .hidden_payload_bytes_per_repetition,
            &plan.expert_groups,
            &validated.device_domains,
        )?),
        ExpertNetworkModel::PinnedLowererRoute => actions.push(route_action(
            request.network_workload.integer_repetitions,
            &plan.expert_groups,
            &validated.device_domains,
            lowering,
        )?),
        ExpertNetworkModel::ZeroRemoteAnalyticalLowerBound => {
            actions.push(NetworkActionReport {
                kind: NetworkActionKind::ExpertDispatch,
                layer_count: GLM_MOE_LAYER_COUNT,
                collectives_or_route_repetitions: u64::from(
                    request.network_workload.integer_repetitions,
                ),
                endpoint_payload_bytes: U64Bounds::exact(0),
                endpoint_message_count: U64Bounds::exact(0),
                network_hop_payload_bytes: U64Bounds::exact(0),
                network_hop_message_count: U64Bounds::exact(0),
                cross_domain_payload_bytes: U64Bounds::exact(0),
                cross_domain_message_count: U64Bounds::exact(0),
                cross_domain_accounting: CrossDomainAccounting::Exact,
            });
        }
    }
    let zero = U64Bounds::exact(0);
    let total = actions.iter().try_fold(
        NetworkTotals {
            endpoint_payload_bytes: zero,
            endpoint_message_count: zero,
            network_hop_payload_bytes: zero,
            network_hop_message_count: zero,
            cross_domain_payload_bytes: zero,
            cross_domain_message_count: zero,
        },
        |total, action| {
            Ok::<_, GlmParallelMappingError>(NetworkTotals {
                endpoint_payload_bytes: total
                    .endpoint_payload_bytes
                    .checked_add(action.endpoint_payload_bytes)?,
                endpoint_message_count: total
                    .endpoint_message_count
                    .checked_add(action.endpoint_message_count)?,
                network_hop_payload_bytes: total
                    .network_hop_payload_bytes
                    .checked_add(action.network_hop_payload_bytes)?,
                network_hop_message_count: total
                    .network_hop_message_count
                    .checked_add(action.network_hop_message_count)?,
                cross_domain_payload_bytes: total
                    .cross_domain_payload_bytes
                    .checked_add(action.cross_domain_payload_bytes)?,
                cross_domain_message_count: total
                    .cross_domain_message_count
                    .checked_add(action.cross_domain_message_count)?,
            })
        },
    )?;
    Ok(ParallelNetworkReport { actions, total })
}

fn ring_action(
    kind: NetworkActionKind,
    layer_count: u32,
    collectives_per_layer: u32,
    integer_repetitions: u32,
    payload_bytes: u64,
    groups: &[DeviceGroup],
    device_domains: &BTreeMap<u32, String>,
) -> Result<NetworkActionReport, GlmParallelMappingError> {
    let degree = u64::from(group_degree(groups)?);
    let collective_count = checked_mul(
        checked_mul(u64::from(layer_count), u64::from(collectives_per_layer))?,
        u64::from(integer_repetitions),
    )?;
    let bytes_per_collective = checked_mul(
        checked_mul(
            2,
            degree
                .checked_sub(1)
                .ok_or(GlmParallelMappingError::ArithmeticOverflow)?,
        )?,
        payload_bytes,
    )?;
    let messages_per_collective = checked_mul(
        checked_mul(2, degree)?,
        degree
            .checked_sub(1)
            .ok_or(GlmParallelMappingError::ArithmeticOverflow)?,
    )?;
    let payload_total = checked_mul(bytes_per_collective, collective_count)?;
    let message_total = checked_mul(messages_per_collective, collective_count)?;
    let repetitions_per_group = u64::from(integer_repetitions)
        .checked_div(
            u64::try_from(groups.len()).map_err(|_| GlmParallelMappingError::ArithmeticOverflow)?,
        )
        .ok_or(GlmParallelMappingError::ArithmeticOverflow)?;
    let cross_edges = groups.iter().try_fold(0_u64, |sum, group| {
        checked_add(sum, cross_domain_ring_edges(group, device_domains)?)
    })?;
    let edge_payload_numerator = checked_mul(
        checked_mul(
            2,
            degree
                .checked_sub(1)
                .ok_or(GlmParallelMappingError::ArithmeticOverflow)?,
        )?,
        payload_bytes,
    )?;
    if edge_payload_numerator % degree != 0 {
        return Err(GlmParallelMappingError::RingChunkDoesNotDivideExactly);
    }
    let cross_collective_multiplier = checked_mul(
        checked_mul(u64::from(layer_count), u64::from(collectives_per_layer))?,
        repetitions_per_group,
    )?;
    let cross_payload = checked_mul(
        checked_mul(edge_payload_numerator / degree, cross_edges)?,
        cross_collective_multiplier,
    )?;
    let cross_messages = checked_mul(
        checked_mul(
            checked_mul(
                2,
                degree
                    .checked_sub(1)
                    .ok_or(GlmParallelMappingError::ArithmeticOverflow)?,
            )?,
            cross_edges,
        )?,
        cross_collective_multiplier,
    )?;
    Ok(NetworkActionReport {
        kind,
        layer_count,
        collectives_or_route_repetitions: collective_count,
        endpoint_payload_bytes: U64Bounds::exact(payload_total),
        endpoint_message_count: U64Bounds::exact(message_total),
        network_hop_payload_bytes: U64Bounds::exact(payload_total),
        network_hop_message_count: U64Bounds::exact(message_total),
        cross_domain_payload_bytes: U64Bounds::exact(cross_payload),
        cross_domain_message_count: U64Bounds::exact(cross_messages),
        cross_domain_accounting: CrossDomainAccounting::Exact,
    })
}

fn route_action(
    integer_repetitions: u32,
    groups: &[DeviceGroup],
    device_domains: &BTreeMap<u32, String>,
    lowering: &GlmDecodeLoweringReport,
) -> Result<NetworkActionReport, GlmParallelMappingError> {
    let route = &lowering.result.route;
    let repetitions = u64::from(integer_repetitions);
    let endpoint_payload_bytes = scale_open_bounds(
        route.endpoint_payload_bytes.lower,
        route.endpoint_payload_bytes.upper,
        repetitions,
    )?;
    let endpoint_message_count = scale_open_bounds(
        route.endpoint_message_count.lower,
        route.endpoint_message_count.upper,
        repetitions,
    )?;
    let network_hop_payload_bytes = scale_open_bounds(
        route.network_hop_payload_bytes.lower,
        route.network_hop_payload_bytes.upper,
        repetitions,
    )?;
    let network_hop_message_count = scale_open_bounds(
        route.network_hop_message_count.lower,
        route.network_hop_message_count.upper,
        repetitions,
    )?;
    let groups_are_domain_local = groups
        .iter()
        .all(|group| group_is_domain_local(group, device_domains));
    let (cross_domain_payload_bytes, cross_domain_message_count, cross_domain_accounting) =
        if groups_are_domain_local {
            (
                U64Bounds::exact(0),
                U64Bounds::exact(0),
                CrossDomainAccounting::Exact,
            )
        } else {
            (
                U64Bounds {
                    lower: 0,
                    upper: network_hop_payload_bytes.upper,
                },
                U64Bounds {
                    lower: 0,
                    upper: network_hop_message_count.upper,
                },
                CrossDomainAccounting::UnresolvedWithoutPartitionedFlowHistogram,
            )
        };
    Ok(NetworkActionReport {
        kind: NetworkActionKind::ExpertDispatch,
        layer_count: GLM_MOE_LAYER_COUNT,
        collectives_or_route_repetitions: repetitions,
        endpoint_payload_bytes,
        endpoint_message_count,
        network_hop_payload_bytes,
        network_hop_message_count,
        cross_domain_payload_bytes,
        cross_domain_message_count,
        cross_domain_accounting,
    })
}

fn evaluate_residency(
    request: &GlmParallelMappingRequest,
    plan: &ParallelPlan,
    storage: &GlmStorageEnvelopeReport,
    validated: &ValidatedInputs<'_>,
    concurrent_requests: u32,
) -> Result<ResidencyPoint, GlmParallelMappingError> {
    let context = request.residency_sweep.context_tokens_per_request;
    let semantic_per_request = checked_mul(request.semantic_cache.bytes_per_token, context)?;
    let cache_copies_on_max_device = cache_copies_on_max_device(plan, concurrent_requests)?;
    let semantic_on_max = checked_mul(semantic_per_request, u64::from(cache_copies_on_max_device))?;
    let expert_degree = u64::from(group_degree(&plan.expert_groups)?);
    let routed_per_device = ByteBounds::new(
        validated.routed.lower / expert_degree,
        validated.routed.upper / expert_degree,
    );
    let partial_on_max = byte_bounds_add(routed_per_device, ByteBounds::exact(semantic_on_max))?;
    let routed_cluster = ByteBounds::new(
        checked_mul(validated.routed.lower, plan.expert_groups.len() as u64)?,
        checked_mul(validated.routed.upper, plan.expert_groups.len() as u64)?,
    );
    let cluster_cache_copies =
        cluster_cache_copies(plan, concurrent_requests, request.topology.device_count)?;
    let cluster_semantic = checked_mul(semantic_per_request, cluster_cache_copies)?;
    let partial_cluster = byte_bounds_add(routed_cluster, ByteBounds::exact(cluster_semantic))?;
    let partial = PartialResidencyReport {
        scope: PartialResidencyScope::RoutedWeightsPlusSemanticCacheOnly,
        routed_weight_bytes_on_max_device: routed_per_device,
        semantic_cache_copies_on_max_device: cache_copies_on_max_device,
        semantic_cache_bytes_on_max_device: semantic_on_max,
        total_bytes_on_max_device: partial_on_max,
        cluster_total_bytes: partial_cluster,
    };
    let checkpoint_weights = checkpoint_weight_bounds_on_max_device(
        validated.variant.checkpoint.payload_bytes,
        validated.routed,
        group_degree(&plan.expert_groups)?,
        group_degree(&plan.attention_groups)?,
        request.topology.device_count,
        plan.non_routed_weight_mapping,
    )?;
    let assumptions = &storage.result.residency_assumptions;
    let extra_per_token = byte_bounds_add(
        assumptions.extra_cache_bytes_per_token,
        assumptions.indexer_cache_bytes_per_token,
    )?;
    let cached_tokens_on_max = checked_mul(context, u64::from(cache_copies_on_max_device))?;
    let extra_and_indexer = byte_bounds_mul(extra_per_token, cached_tokens_on_max)?;
    let lower_unfragmented = checked_add(
        checked_add(
            checked_add(checkpoint_weights.lower, semantic_on_max)?,
            extra_and_indexer.lower,
        )?,
        validated.runtime_bytes_per_device,
    )?;
    let upper_unfragmented = checked_add(
        checked_add(
            checked_add(checkpoint_weights.upper, semantic_on_max)?,
            extra_and_indexer.upper,
        )?,
        validated.runtime_bytes_per_device,
    )?;
    let unfragmented = ByteBounds::new(lower_unfragmented, upper_unfragmented);
    let fragmentation = ByteBounds::new(
        basis_point_overhead(
            unfragmented.lower,
            assumptions.fragmentation_overhead_basis_points,
        )?,
        basis_point_overhead(
            unfragmented.upper,
            assumptions.fragmentation_overhead_basis_points,
        )?,
    );
    let total = byte_bounds_add(unfragmented, fragmentation)?;
    let capacity_status = if total.upper <= validated.hardware.usable_memory_bytes_per_device {
        CapacityStatus::Feasible
    } else if total.lower > validated.hardware.usable_memory_bytes_per_device {
        CapacityStatus::Infeasible
    } else {
        CapacityStatus::Uncertain
    };
    let full = FullMappedResidencyReport {
        checkpoint_weight_bytes_on_max_device: checkpoint_weights,
        semantic_cache_bytes_on_max_device: semantic_on_max,
        extra_and_indexer_cache_bytes_on_max_device: extra_and_indexer,
        fixed_runtime_bytes_on_device: validated.runtime_bytes_per_device,
        unfragmented_bytes_on_max_device: unfragmented,
        fragmentation_overhead_bytes_on_max_device: fragmentation,
        total_bytes_on_max_device: total,
        usable_memory_bytes_per_device: validated.hardware.usable_memory_bytes_per_device,
        capacity_status,
    };
    Ok(ResidencyPoint {
        concurrent_requests,
        context_tokens_per_request: context,
        partial,
        full,
    })
}

fn checkpoint_weight_bounds_on_max_device(
    checkpoint_payload: u64,
    routed: ByteBounds,
    expert_degree: u32,
    attention_degree: u32,
    device_count: u32,
    mapping: NonRoutedWeightMapping,
) -> Result<ByteBounds, GlmParallelMappingError> {
    let (lower_non_routed_degree, upper_non_routed_degree) = match mapping {
        NonRoutedWeightMapping::AttentionGroupsExact => (attention_degree, attention_degree),
        NonRoutedWeightMapping::OpaqueGlobalShardToAttentionReplication => {
            (device_count, attention_degree)
        }
    };
    let lower_weights = [routed.lower, routed.upper]
        .into_iter()
        .map(|routed_bytes| {
            let non_routed = checkpoint_payload
                .checked_sub(routed_bytes)
                .ok_or(GlmParallelMappingError::ArithmeticOverflow)?;
            checked_add(
                routed_bytes / u64::from(expert_degree),
                non_routed / u64::from(lower_non_routed_degree),
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    let upper_weights = [routed.lower, routed.upper]
        .into_iter()
        .map(|routed_bytes| {
            let non_routed = checkpoint_payload
                .checked_sub(routed_bytes)
                .ok_or(GlmParallelMappingError::ArithmeticOverflow)?;
            checked_add(
                routed_bytes / u64::from(expert_degree),
                non_routed / u64::from(upper_non_routed_degree),
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    Ok(ByteBounds::new(
        *lower_weights
            .iter()
            .min()
            .ok_or(GlmParallelMappingError::ArithmeticOverflow)?,
        *upper_weights
            .iter()
            .max()
            .ok_or(GlmParallelMappingError::ArithmeticOverflow)?,
    ))
}

fn compare_partial(
    request: &GlmParallelMappingRequest,
    baseline: &ParallelPlanReport,
    candidate: &ParallelPlanReport,
    routed: ByteBounds,
    concurrent_requests: u32,
) -> Result<PartialResidencyComparison, GlmParallelMappingError> {
    let semantic_per_request = checked_mul(
        request.semantic_cache.bytes_per_token,
        request.residency_sweep.context_tokens_per_request,
    )?;
    let cluster_delta = paired_cluster_delta(
        baseline,
        candidate,
        routed,
        concurrent_requests,
        semantic_per_request,
        request.topology.device_count,
    )?;
    let max_device_delta = paired_max_device_delta(
        baseline,
        candidate,
        routed,
        concurrent_requests,
        semantic_per_request,
    )?;
    Ok(PartialResidencyComparison {
        concurrent_requests,
        candidate_minus_baseline_cluster_total_bytes: cluster_delta,
        cluster_total_partial_dominance: dominance(cluster_delta),
        candidate_minus_baseline_max_device_bytes: max_device_delta,
        max_device_partial_dominance: dominance(max_device_delta),
    })
}

fn compare_network(
    baseline: &ParallelPlanReport,
    candidate: &ParallelPlanReport,
) -> Result<NetworkComparison, GlmParallelMappingError> {
    let payload = independent_delta(
        baseline.network.total.network_hop_payload_bytes,
        candidate.network.total.network_hop_payload_bytes,
    )?;
    let messages = independent_delta(
        baseline.network.total.network_hop_message_count,
        candidate.network.total.network_hop_message_count,
    )?;
    let cross_domain = independent_delta(
        baseline.network.total.cross_domain_payload_bytes,
        candidate.network.total.cross_domain_payload_bytes,
    )?;
    Ok(NetworkComparison {
        baseline_plan_id: baseline.plan_id.clone(),
        candidate_plan_id: candidate.plan_id.clone(),
        candidate_minus_baseline_network_hop_payload_bytes: payload,
        network_hop_payload_dominance: dominance(payload),
        candidate_minus_baseline_network_hop_message_count: messages,
        network_hop_message_dominance: dominance(messages),
        candidate_minus_baseline_cross_domain_payload_bytes: cross_domain,
        cross_domain_payload_dominance: dominance(cross_domain),
    })
}

fn independent_delta(
    baseline: U64Bounds,
    candidate: U64Bounds,
) -> Result<SignedBounds, GlmParallelMappingError> {
    let lower = i128::from(candidate.lower)
        .checked_sub(i128::from(baseline.upper))
        .ok_or(GlmParallelMappingError::ArithmeticOverflow)?;
    let upper = i128::from(candidate.upper)
        .checked_sub(i128::from(baseline.lower))
        .ok_or(GlmParallelMappingError::ArithmeticOverflow)?;
    Ok(SignedBounds { lower, upper })
}

fn evaluate_crossover(
    request: &GlmParallelMappingRequest,
    baseline: &ParallelPlanReport,
    candidate: &ParallelPlanReport,
    routed: ByteBounds,
) -> Result<PartialCrossoverReport, GlmParallelMappingError> {
    let mut cluster_total_regions = Vec::new();
    let mut max_device_regions = Vec::new();
    for concurrency in request.residency_sweep.crossover_min_concurrency
        ..=request.residency_sweep.crossover_max_concurrency
    {
        let comparison = compare_partial(request, baseline, candidate, routed, concurrency)?;
        extend_region(
            &mut cluster_total_regions,
            concurrency,
            comparison.cluster_total_partial_dominance,
        );
        extend_region(
            &mut max_device_regions,
            concurrency,
            comparison.max_device_partial_dominance,
        );
    }
    Ok(PartialCrossoverReport {
        baseline_plan_id: baseline.plan_id.clone(),
        candidate_plan_id: candidate.plan_id.clone(),
        search_min_concurrency: request.residency_sweep.crossover_min_concurrency,
        search_max_concurrency: request.residency_sweep.crossover_max_concurrency,
        cluster_total_regions,
        max_device_regions,
    })
}

fn paired_cluster_delta(
    baseline: &ParallelPlanReport,
    candidate: &ParallelPlanReport,
    routed: ByteBounds,
    concurrent_requests: u32,
    semantic_per_request: u64,
    device_count: u32,
) -> Result<SignedBounds, GlmParallelMappingError> {
    let baseline_cache = cluster_cache_copies_report(baseline, concurrent_requests, device_count)?;
    let candidate_cache =
        cluster_cache_copies_report(candidate, concurrent_requests, device_count)?;
    paired_delta(routed, |routed_bytes| {
        let baseline_weights = checked_mul(
            routed_bytes,
            u64::from(baseline.routed_weight_replication_factor),
        )?;
        let candidate_weights = checked_mul(
            routed_bytes,
            u64::from(candidate.routed_weight_replication_factor),
        )?;
        signed_sum(
            candidate_weights,
            baseline_weights,
            candidate_cache,
            baseline_cache,
            semantic_per_request,
        )
    })
}

fn paired_max_device_delta(
    baseline: &ParallelPlanReport,
    candidate: &ParallelPlanReport,
    routed: ByteBounds,
    concurrent_requests: u32,
    semantic_per_request: u64,
) -> Result<SignedBounds, GlmParallelMappingError> {
    let baseline_degree = u64::from(group_degree(&baseline.expert_groups)?);
    let candidate_degree = u64::from(group_degree(&candidate.expert_groups)?);
    let baseline_cache = u64::from(cache_copies_on_max_device_report(
        baseline,
        concurrent_requests,
    )?);
    let candidate_cache = u64::from(cache_copies_on_max_device_report(
        candidate,
        concurrent_requests,
    )?);
    paired_delta(routed, |routed_bytes| {
        signed_sum(
            routed_bytes / candidate_degree,
            routed_bytes / baseline_degree,
            candidate_cache,
            baseline_cache,
            semantic_per_request,
        )
    })
}

fn paired_delta<F>(routed: ByteBounds, evaluate: F) -> Result<SignedBounds, GlmParallelMappingError>
where
    F: Fn(u64) -> Result<i128, GlmParallelMappingError>,
{
    let values = [evaluate(routed.lower)?, evaluate(routed.upper)?];
    Ok(SignedBounds {
        lower: *values
            .iter()
            .min()
            .ok_or(GlmParallelMappingError::ArithmeticOverflow)?,
        upper: *values
            .iter()
            .max()
            .ok_or(GlmParallelMappingError::ArithmeticOverflow)?,
    })
}

fn signed_sum(
    candidate_weight: u64,
    baseline_weight: u64,
    candidate_cache_copies: u64,
    baseline_cache_copies: u64,
    semantic_per_request: u64,
) -> Result<i128, GlmParallelMappingError> {
    let weight_delta = i128::from(candidate_weight) - i128::from(baseline_weight);
    let cache_copy_delta = i128::from(candidate_cache_copies) - i128::from(baseline_cache_copies);
    weight_delta
        .checked_add(
            cache_copy_delta
                .checked_mul(i128::from(semantic_per_request))
                .ok_or(GlmParallelMappingError::ArithmeticOverflow)?,
        )
        .ok_or(GlmParallelMappingError::ArithmeticOverflow)
}

fn dominance(bounds: SignedBounds) -> Dominance {
    if bounds.lower > 0 {
        Dominance::BaselineLower
    } else if bounds.upper < 0 {
        Dominance::CandidateLower
    } else {
        Dominance::BoundsOverlap
    }
}

fn extend_region(regions: &mut Vec<DominanceRegion>, concurrency: u32, value: Dominance) {
    if let Some(last) = regions.last_mut()
        && last.dominance == value
        && last.end_concurrency.checked_add(1) == Some(concurrency)
    {
        last.end_concurrency = concurrency;
        return;
    }
    regions.push(DominanceRegion {
        start_concurrency: concurrency,
        end_concurrency: concurrency,
        dominance: value,
    });
}

fn find_plan<'a>(
    plans: &'a [ParallelPlanReport],
    plan_id: &str,
) -> Result<&'a ParallelPlanReport, GlmParallelMappingError> {
    plans
        .iter()
        .find(|plan| plan.plan_id == plan_id)
        .ok_or_else(|| GlmParallelMappingError::PlanNotFound(plan_id.into()))
}

fn group_degree(groups: &[DeviceGroup]) -> Result<u32, GlmParallelMappingError> {
    let degree = groups
        .first()
        .ok_or(GlmParallelMappingError::ArithmeticOverflow)?
        .ordered_device_ids
        .len();
    u32::try_from(degree).map_err(|_| GlmParallelMappingError::ArithmeticOverflow)
}

fn cache_copies_on_max_device(
    plan: &ParallelPlan,
    concurrent_requests: u32,
) -> Result<u32, GlmParallelMappingError> {
    match plan.semantic_cache_placement {
        SemanticCachePlacement::ReplicatedAcrossAllDevices => Ok(concurrent_requests),
        SemanticCachePlacement::AttentionGroupLocal => Ok(concurrent_requests.div_ceil(
            u32::try_from(plan.attention_groups.len())
                .map_err(|_| GlmParallelMappingError::ArithmeticOverflow)?,
        )),
    }
}

fn cache_copies_on_max_device_report(
    plan: &ParallelPlanReport,
    concurrent_requests: u32,
) -> Result<u32, GlmParallelMappingError> {
    match plan.semantic_cache_placement {
        SemanticCachePlacement::ReplicatedAcrossAllDevices => Ok(concurrent_requests),
        SemanticCachePlacement::AttentionGroupLocal => Ok(concurrent_requests.div_ceil(
            u32::try_from(plan.attention_groups.len())
                .map_err(|_| GlmParallelMappingError::ArithmeticOverflow)?,
        )),
    }
}

fn cluster_cache_copies(
    plan: &ParallelPlan,
    concurrent_requests: u32,
    device_count: u32,
) -> Result<u64, GlmParallelMappingError> {
    let multiplier = match plan.semantic_cache_placement {
        SemanticCachePlacement::ReplicatedAcrossAllDevices => device_count,
        SemanticCachePlacement::AttentionGroupLocal => group_degree(&plan.attention_groups)?,
    };
    checked_mul(u64::from(concurrent_requests), u64::from(multiplier))
}

fn cluster_cache_copies_report(
    plan: &ParallelPlanReport,
    concurrent_requests: u32,
    device_count: u32,
) -> Result<u64, GlmParallelMappingError> {
    let multiplier = match plan.semantic_cache_placement {
        SemanticCachePlacement::ReplicatedAcrossAllDevices => device_count,
        SemanticCachePlacement::AttentionGroupLocal => group_degree(&plan.attention_groups)?,
    };
    checked_mul(u64::from(concurrent_requests), u64::from(multiplier))
}

fn cross_domain_ring_edges(
    group: &DeviceGroup,
    domains: &BTreeMap<u32, String>,
) -> Result<u64, GlmParallelMappingError> {
    if group.ordered_device_ids.len() < 2 {
        return Ok(0);
    }
    let mut edges = 0_u64;
    for pair in group.ordered_device_ids.windows(2) {
        if domains.get(&pair[0]) != domains.get(&pair[1]) {
            edges = checked_add(edges, 1)?;
        }
    }
    let first = group
        .ordered_device_ids
        .first()
        .ok_or(GlmParallelMappingError::ArithmeticOverflow)?;
    let last = group
        .ordered_device_ids
        .last()
        .ok_or(GlmParallelMappingError::ArithmeticOverflow)?;
    if domains.get(first) != domains.get(last) {
        edges = checked_add(edges, 1)?;
    }
    Ok(edges)
}

fn group_is_domain_local(group: &DeviceGroup, domains: &BTreeMap<u32, String>) -> bool {
    let mut group_domains = group
        .ordered_device_ids
        .iter()
        .filter_map(|device| domains.get(device));
    let first = group_domains.next();
    first.is_some() && group_domains.all(|domain| Some(domain) == first)
}

fn scale_open_bounds(
    lower: u64,
    upper: Option<u64>,
    multiplier: u64,
) -> Result<U64Bounds, GlmParallelMappingError> {
    Ok(U64Bounds {
        lower: checked_mul(lower, multiplier)?,
        upper: checked_mul(
            upper.ok_or(GlmParallelMappingError::ClosedRouteBoundsRequired)?,
            multiplier,
        )?,
    })
}

fn byte_bounds_add(
    left: ByteBounds,
    right: ByteBounds,
) -> Result<ByteBounds, GlmParallelMappingError> {
    Ok(ByteBounds::new(
        checked_add(left.lower, right.lower)?,
        checked_add(left.upper, right.upper)?,
    ))
}

fn byte_bounds_mul(
    bounds: ByteBounds,
    multiplier: u64,
) -> Result<ByteBounds, GlmParallelMappingError> {
    Ok(ByteBounds::new(
        checked_mul(bounds.lower, multiplier)?,
        checked_mul(bounds.upper, multiplier)?,
    ))
}

fn basis_point_overhead(bytes: u64, basis_points: u32) -> Result<u64, GlmParallelMappingError> {
    let numerator = u128::from(bytes)
        .checked_mul(u128::from(basis_points))
        .ok_or(GlmParallelMappingError::ArithmeticOverflow)?;
    u64::try_from(numerator.div_ceil(10_000))
        .map_err(|_| GlmParallelMappingError::ArithmeticOverflow)
}

fn checked_add(left: u64, right: u64) -> Result<u64, GlmParallelMappingError> {
    left.checked_add(right)
        .ok_or(GlmParallelMappingError::ArithmeticOverflow)
}

fn checked_mul(left: u64, right: u64) -> Result<u64, GlmParallelMappingError> {
    left.checked_mul(right)
        .ok_or(GlmParallelMappingError::ArithmeticOverflow)
}

fn validate_evidence(
    field: &'static str,
    evidence: &MappingEvidence,
) -> Result<(), GlmParallelMappingError> {
    validate_required(field, &evidence.source_artifact_id)?;
    validate_required(field, &evidence.basis)
}

fn validate_required(field: &'static str, value: &str) -> Result<(), GlmParallelMappingError> {
    if value.trim().is_empty() {
        Err(GlmParallelMappingError::InvalidField(field))
    } else {
        Ok(())
    }
}

fn claim_gate() -> ParallelMappingClaimGate {
    ParallelMappingClaimGate {
        partial_residency_accounting_permitted: true,
        modeled_capacity_arithmetic_permitted: true,
        end_to_end_latency_claim_permitted: false,
        throughput_claim_permitted: false,
        cost_per_token_claim_permitted: false,
        quality_claim_permitted: false,
        blockers: vec![
            ClaimBlocker::RouteHistogramIsSynthetic,
            ClaimBlocker::CheckpointExpertLayoutIsOpaque,
            ClaimBlocker::CacheScaleAndMetadataAreExcluded,
            ClaimBlocker::CollectiveTimingIsNotCalibrated,
            ClaimBlocker::CrossDomainLinkPerformanceIsNotMeasured,
            ClaimBlocker::RuntimeDistributionIsModeled,
            ClaimBlocker::ServingAndContentionAreNotModeled,
            ClaimBlocker::QualityContractIsNotProvided,
        ],
    }
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a GlmParallelMappingResult,
}

fn report_content_id(
    schema_version: u32,
    result: &GlmParallelMappingResult,
) -> Result<String, GlmParallelMappingError> {
    let bytes = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|_| GlmParallelMappingError::SerializationFailed)?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Clone, Debug, Error, Eq, PartialEq)]
pub enum GlmParallelMappingError {
    #[error("unsupported schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid field {0}")]
    InvalidField(&'static str),
    #[error("storage report content ID is invalid")]
    InvalidStorageReportContentId,
    #[error("route report content ID is invalid")]
    InvalidRouteReportContentId,
    #[error("DSA report content ID is invalid")]
    InvalidDsaReportContentId,
    #[error("lowering report content ID is invalid")]
    InvalidLoweringReportContentId,
    #[error("lower action ledger content ID is invalid")]
    InvalidLowerActionLedgerContentId,
    #[error("storage report content ID pin does not match")]
    StorageReportContentIdMismatch,
    #[error("route report content ID pin does not match")]
    RouteReportContentIdMismatch,
    #[error("DSA report content ID pin does not match")]
    DsaReportContentIdMismatch,
    #[error("lowering report content ID pin does not match")]
    LoweringReportContentIdMismatch,
    #[error("lower action ledger content ID pin does not match")]
    LowerActionLedgerContentIdMismatch,
    #[error("lowering request does not reproduce the pinned report")]
    LoweringRequestDoesNotReproduceReport,
    #[error("a pinned route selection is required")]
    PinnedRouteSelectionRequired,
    #[error("route selection was not found")]
    RouteSelectionNotFound,
    #[error("route selection ledger does not match")]
    RouteSelectionLedgerMismatch,
    #[error("variant was not found")]
    VariantNotFound,
    #[error("device profile was not found")]
    DeviceProfileNotFound,
    #[error("checkpoint identity does not match")]
    CheckpointIdentityMismatch,
    #[error("closed routed expert bounds are required")]
    ClosedRoutedExpertBoundsRequired,
    #[error("closed non-routed bounds are required")]
    ClosedNonRoutedBoundsRequired,
    #[error("routed expert bounds do not match")]
    RoutedExpertBoundsMismatch,
    #[error("checkpoint correlation does not match")]
    CheckpointCorrelationMismatch,
    #[error("DSA semantic geometry does not match")]
    DsaSemanticGeometryMismatch,
    #[error("topology device count does not match")]
    TopologyDeviceMismatch,
    #[error("topology domains do not partition devices exactly")]
    InvalidTopologyPartition,
    #[error("duplicate plan {0}")]
    DuplicatePlan(String),
    #[error("invalid plan {0}")]
    InvalidPlan(String),
    #[error("plan {0} was not found")]
    PlanNotFound(String),
    #[error("work repetitions do not partition the network groups in {plan_id}")]
    WorkRepetitionsDoNotPartitionExpertGroups { plan_id: String },
    #[error("weight bounds do not shard exactly in {plan_id}")]
    WeightBoundsDoNotShardExactly { plan_id: String },
    #[error("runtime bytes do not distribute exactly")]
    RuntimeDoesNotDistributeExactly,
    #[error("activation payload is not byte aligned")]
    ActivationPayloadIsNotByteAligned,
    #[error("ring chunks do not divide exactly")]
    RingChunkDoesNotDivideExactly,
    #[error("closed route bounds are required")]
    ClosedRouteBoundsRequired,
    #[error("arithmetic overflow")]
    ArithmeticOverflow,
    #[error("report serialization failed")]
    SerializationFailed,
}
