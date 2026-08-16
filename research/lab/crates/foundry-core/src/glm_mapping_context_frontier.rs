use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::glm_decode::{GlmDecodeLoweringReport, OpenU64Bounds};
use crate::glm_parallel_mapping::{
    CapacityStatus, Dominance, FullMappedResidencyReport, NetworkComparison,
    NonRoutedWeightMapping, ParallelNetworkReport, ParallelPlanReport, PartialResidencyComparison,
    PartialResidencyReport, PartialResidencyScope, ResidencyPoint, SemanticCachePlacement,
    SignedBounds,
};
use crate::glm_storage::{
    ByteBounds, GlmStorageEnvelopeReport, GlmVariantEnvelopeReport, HardwareVariantEnvelopeReport,
};

pub const GLM_MAPPING_CONTEXT_FRONTIER_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const GLM_MAPPING_CONTEXT_FRONTIER_REPORT_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MappingControlPin {
    pub context_tokens_per_request: u64,
    pub mapping_report_content_id: String,
    pub lowering_report_content_id: String,
    pub lower_action_ledger_content_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MappingContextFrontierSourcePins {
    pub storage_report_content_id: String,
    pub controls: Vec<MappingControlPin>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmMappingContextFrontierRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub sources: MappingContextFrontierSourcePins,
    pub variant_id: String,
    pub device_profile_id: String,
    pub baseline_plan_id: String,
    pub candidate_plan_id: String,
    pub context_points: Vec<u64>,
    pub concurrency_min: u32,
    pub concurrency_max: u32,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum FrontierScope {
    ResidencyOnly,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PartialPolicy {
    CoupledRobustLower,
    BoundsOverlapOrMetricDisagreement,
    DecoupledRobustLower,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PartialPolicyRegion {
    pub start_concurrency: u32,
    pub end_concurrency: u32,
    pub policy: PartialPolicy,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum FrontierCapacityRelation {
    BothPlansProvenFeasible,
    BaselineOnlyProvenFeasible,
    CandidateOnlyProvenFeasible,
    NeitherPlanProvenFeasible,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CapacityRelationRegion {
    pub start_concurrency: u32,
    pub end_concurrency: u32,
    pub relation: FrontierCapacityRelation,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CapacityStatusRegion {
    pub start_concurrency: u32,
    pub end_concurrency: u32,
    pub status: CapacityStatus,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FullCapacityPoint {
    pub total_bytes_on_max_device: ByteBounds,
    pub capacity_status: CapacityStatus,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ContextConcurrencyPoint {
    pub concurrent_requests: u32,
    pub partial_comparison: PartialResidencyComparison,
    pub partial_policy: PartialPolicy,
    pub baseline_full_capacity: FullCapacityPoint,
    pub candidate_full_capacity: FullCapacityPoint,
    pub full_capacity_relation: FrontierCapacityRelation,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ContextPolicyFrontier {
    pub context_tokens_per_request: u64,
    pub semantic_cache_bytes_per_request: u64,
    pub partial_policy_regions: Vec<PartialPolicyRegion>,
    pub baseline_capacity_status_regions: Vec<CapacityStatusRegion>,
    pub candidate_capacity_status_regions: Vec<CapacityStatusRegion>,
    pub capacity_relation_regions: Vec<CapacityRelationRegion>,
    pub points: Vec<ContextConcurrencyPoint>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExactContextResidencyGrid {
    pub context_tokens_per_request: u64,
    pub semantic_cache_bytes_per_request: u64,
    pub points: Vec<ContextConcurrencyPoint>,
}

pub struct ExactMappingResidencyInputs<'a> {
    pub storage: &'a GlmStorageEnvelopeReport,
    pub mapping_16k: &'a crate::glm_parallel_mapping::GlmParallelMappingReport,
    pub mapping_90k: &'a crate::glm_parallel_mapping::GlmParallelMappingReport,
    pub lowering_16k: &'a GlmDecodeLoweringReport,
    pub lowering_90k: &'a GlmDecodeLoweringReport,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AnchorRegressionWitness {
    pub context_tokens_per_request: u64,
    pub mapping_report_content_id: String,
    pub lowering_report_content_id: String,
    pub lower_action_ledger_content_id: String,
    pub stored_concurrency_points: Vec<u32>,
    pub reproduced_stored_point_count: u32,
    pub reproduced_partial_comparison_count: u32,
    pub all_stored_points_reproduced_exactly: bool,
    pub witness_concurrency: u32,
    pub baseline_witness: ResidencyPoint,
    pub candidate_witness: ResidencyPoint,
    pub witness_partial_comparison: PartialResidencyComparison,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ContextInvariantNetworkControl {
    pub anchor_context_tokens: Vec<u64>,
    pub exactly_equal_across_anchors: bool,
    pub contract: String,
    pub baseline_plan_id: String,
    pub candidate_plan_id: String,
    pub baseline: ParallelNetworkReport,
    pub candidate: ParallelNetworkReport,
    pub comparison: NetworkComparison,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExcludedLowererWorkWitness {
    pub context_tokens_per_request: u64,
    pub lowering_report_content_id: String,
    pub aggregate_batch_bf16_semantic_kv_resident_bytes: u64,
    pub attention_flops: OpenU64Bounds,
    pub dsa_indexer_flops: OpenU64Bounds,
    pub total_flops: OpenU64Bounds,
    pub non_flop_operations: OpenU64Bounds,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MappingContextFrontierBlocker {
    ContextDependentLowererWorkNotDerived,
    RouteHistogramIsSynthetic,
    CheckpointExpertLayoutIsOpaque,
    CacheScaleAndMetadataAreBoundedNotMeasured,
    RuntimeAndFragmentationAreModeled,
    ServingAndContentionAreNotModeled,
    QualityContractIsNotProvided,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MappingContextFrontierClaimGate {
    pub residency_accounting_permitted: bool,
    pub modeled_capacity_arithmetic_permitted: bool,
    pub end_to_end_latency_claim_permitted: bool,
    pub throughput_claim_permitted: bool,
    pub cost_per_token_claim_permitted: bool,
    pub quality_claim_permitted: bool,
    pub blockers: Vec<MappingContextFrontierBlocker>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmMappingContextFrontierResult {
    pub study_id: String,
    pub scope: FrontierScope,
    pub scope_basis: String,
    pub partial_policy_contract: String,
    pub full_capacity_contract: String,
    pub sources: MappingContextFrontierSourcePins,
    pub variant_id: String,
    pub checkpoint_model_id: String,
    pub checkpoint_revision: String,
    pub checkpoint_payload_bytes: u64,
    pub routed_expert_resident_bytes: ByteBounds,
    pub device_profile_id: String,
    pub topology_id: String,
    pub device_count: u32,
    pub usable_memory_bytes_per_device: u64,
    pub semantic_cache_format_id: String,
    pub semantic_cache_bytes_per_token: u64,
    pub baseline_plan_id: String,
    pub candidate_plan_id: String,
    pub anchor_regression_witnesses: Vec<AnchorRegressionWitness>,
    pub context_invariant_network_control: ContextInvariantNetworkControl,
    pub excluded_context_dependent_lowerer_work: Vec<ExcludedLowererWorkWitness>,
    pub frontiers: Vec<ContextPolicyFrontier>,
    pub claims: MappingContextFrontierClaimGate,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmMappingContextFrontierReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: GlmMappingContextFrontierResult,
}

impl GlmMappingContextFrontierReport {
    pub fn verify_content_id(&self) -> Result<bool, GlmMappingContextFrontierError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

struct ValidatedInputs<'a> {
    variant: &'a GlmVariantEnvelopeReport,
    hardware: &'a HardwareVariantEnvelopeReport,
    baseline: &'a ParallelPlanReport,
    candidate: &'a ParallelPlanReport,
    semantic_cache_bytes_per_token: u64,
    device_count: u32,
}

struct Control<'a> {
    pin: &'a MappingControlPin,
    mapping: &'a crate::glm_parallel_mapping::GlmParallelMappingReport,
    lowering: &'a GlmDecodeLoweringReport,
}

pub fn evaluate_glm_mapping_context_frontier(
    request: &GlmMappingContextFrontierRequest,
    storage: &GlmStorageEnvelopeReport,
    mapping_16k: &crate::glm_parallel_mapping::GlmParallelMappingReport,
    mapping_90k: &crate::glm_parallel_mapping::GlmParallelMappingReport,
    lowering_16k: &GlmDecodeLoweringReport,
    lowering_90k: &GlmDecodeLoweringReport,
) -> Result<GlmMappingContextFrontierReport, GlmMappingContextFrontierError> {
    let (controls, validated) = validate_exact_inputs(
        request,
        storage,
        mapping_16k,
        mapping_90k,
        lowering_16k,
        lowering_90k,
    )?;
    let anchor_regression_witnesses = controls
        .iter()
        .map(|control| reproduce_anchor(request, storage, &validated, control))
        .collect::<Result<Vec<_>, _>>()?;
    let context_invariant_network_control = network_control(request, &controls, &validated)?;
    let excluded_context_dependent_lowerer_work = controls
        .iter()
        .map(|control| ExcludedLowererWorkWitness {
            context_tokens_per_request: control.pin.context_tokens_per_request,
            lowering_report_content_id: control.lowering.content_id.clone(),
            aggregate_batch_bf16_semantic_kv_resident_bytes: control
                .lowering
                .result
                .semantic_kv_resident_bytes,
            attention_flops: control.lowering.result.compute.attention_flops,
            dsa_indexer_flops: control.lowering.result.compute.dsa_indexer_flops,
            total_flops: control.lowering.result.compute.total_flops,
            non_flop_operations: control.lowering.result.compute.non_flop_operations,
        })
        .collect();
    let frontiers = request
        .context_points
        .iter()
        .map(|context| evaluate_context(request, storage, &validated, *context))
        .collect::<Result<Vec<_>, _>>()?;
    let result = GlmMappingContextFrontierResult {
        study_id: request.study_id.clone(),
        scope: FrontierScope::ResidencyOnly,
        scope_basis: "The pinned lowerers change context-dependent attention, DSA, KV-read, and non-flop work between 16,384 and 90,000 tokens. Only semantic KV residency is exactly linear and both mapping anchors reproduce the same storage algebra, so no latency, throughput, network interpolation, or cost extrapolation is performed.".into(),
        partial_policy_contract: "A robust-lower policy requires strict paired-bound dominance for both cluster-total and max-device routed-weight-plus-semantic-KV residency. Any overlap or disagreement remains unresolved, and this partial policy never selects a deployable plan.".into(),
        full_capacity_contract: "Full-capacity totals preserve the pinned checkpoint correlation, per-device runtime, extra-cache and indexer bounds, ceiling-rounded fragmentation, and usable-memory bound. Uncertain is never treated as feasible, and capacity relations report proof status rather than select a plan.".into(),
        sources: request.sources.clone(),
        variant_id: request.variant_id.clone(),
        checkpoint_model_id: validated.variant.checkpoint.model_id.clone(),
        checkpoint_revision: validated.variant.checkpoint.checkpoint_revision.clone(),
        checkpoint_payload_bytes: validated.variant.checkpoint.payload_bytes,
        routed_expert_resident_bytes: validated.variant.routed_experts.resident_storage_bytes,
        device_profile_id: request.device_profile_id.clone(),
        topology_id: mapping_16k.result.topology.topology_id.clone(),
        device_count: validated.device_count,
        usable_memory_bytes_per_device: validated.hardware.usable_memory_bytes_per_device,
        semantic_cache_format_id: mapping_16k.result.semantic_cache.format_id.clone(),
        semantic_cache_bytes_per_token: validated.semantic_cache_bytes_per_token,
        baseline_plan_id: request.baseline_plan_id.clone(),
        candidate_plan_id: request.candidate_plan_id.clone(),
        anchor_regression_witnesses,
        context_invariant_network_control,
        excluded_context_dependent_lowerer_work,
        frontiers,
        claims: claim_gate(),
    };
    let schema_version = GLM_MAPPING_CONTEXT_FRONTIER_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(GlmMappingContextFrontierReport {
        schema_version,
        content_id,
        result,
    })
}

pub fn evaluate_exact_mapping_residency_grid(
    control_request: &GlmMappingContextFrontierRequest,
    inputs: &ExactMappingResidencyInputs<'_>,
    context_points: &[u64],
    concurrency_points: &[u32],
) -> Result<Vec<ExactContextResidencyGrid>, GlmMappingContextFrontierError> {
    if context_points.is_empty()
        || concurrency_points.is_empty()
        || context_points.contains(&0)
        || concurrency_points.contains(&0)
        || !strictly_increasing(context_points)
        || !strictly_increasing(concurrency_points)
    {
        return Err(GlmMappingContextFrontierError::InvalidField(
            "exact_context_concurrency_grid",
        ));
    }
    let (controls, validated) = validate_exact_inputs(
        control_request,
        inputs.storage,
        inputs.mapping_16k,
        inputs.mapping_90k,
        inputs.lowering_16k,
        inputs.lowering_90k,
    )?;
    for control in &controls {
        reproduce_anchor(control_request, inputs.storage, &validated, control)?;
    }
    network_control(control_request, &controls, &validated)?;
    context_points
        .iter()
        .map(|context| {
            let points = concurrency_points
                .iter()
                .map(|concurrency| {
                    evaluate_context_concurrency_point(
                        *context,
                        *concurrency,
                        inputs.storage,
                        &validated,
                    )
                })
                .collect::<Result<Vec<_>, _>>()?;
            Ok(ExactContextResidencyGrid {
                context_tokens_per_request: *context,
                semantic_cache_bytes_per_request: checked_mul(
                    validated.semantic_cache_bytes_per_token,
                    *context,
                )?,
                points,
            })
        })
        .collect()
}

fn validate_exact_inputs<'a>(
    request: &'a GlmMappingContextFrontierRequest,
    storage: &'a GlmStorageEnvelopeReport,
    mapping_16k: &'a crate::glm_parallel_mapping::GlmParallelMappingReport,
    mapping_90k: &'a crate::glm_parallel_mapping::GlmParallelMappingReport,
    lowering_16k: &'a GlmDecodeLoweringReport,
    lowering_90k: &'a GlmDecodeLoweringReport,
) -> Result<([Control<'a>; 2], ValidatedInputs<'a>), GlmMappingContextFrontierError> {
    validate_request(request)?;
    validate_storage(request, storage)?;
    let controls = [
        Control {
            pin: &request.sources.controls[0],
            mapping: mapping_16k,
            lowering: lowering_16k,
        },
        Control {
            pin: &request.sources.controls[1],
            mapping: mapping_90k,
            lowering: lowering_90k,
        },
    ];
    for control in &controls {
        validate_control_identity(request, storage, control)?;
    }
    validate_shared_geometry(request, &controls)?;
    let validated = validate_storage_geometry(request, storage, mapping_16k)?;
    validate_lowerer_geometry(storage, &controls)?;
    Ok((controls, validated))
}

fn strictly_increasing<T: Ord>(values: &[T]) -> bool {
    values.windows(2).all(|pair| pair[0] < pair[1])
}

fn validate_request(
    request: &GlmMappingContextFrontierRequest,
) -> Result<(), GlmMappingContextFrontierError> {
    if request.schema_version != GLM_MAPPING_CONTEXT_FRONTIER_REQUEST_SCHEMA_VERSION {
        return Err(GlmMappingContextFrontierError::UnsupportedSchemaVersion {
            expected: GLM_MAPPING_CONTEXT_FRONTIER_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    for (field, value) in [
        ("study_id", request.study_id.as_str()),
        ("variant_id", request.variant_id.as_str()),
        ("device_profile_id", request.device_profile_id.as_str()),
        ("baseline_plan_id", request.baseline_plan_id.as_str()),
        ("candidate_plan_id", request.candidate_plan_id.as_str()),
        (
            "sources.storage_report_content_id",
            request.sources.storage_report_content_id.as_str(),
        ),
    ] {
        if value.trim().is_empty() {
            return Err(GlmMappingContextFrontierError::InvalidField(field));
        }
    }
    if request.baseline_plan_id == request.candidate_plan_id
        || request.sources.controls.len() != 2
        || request.sources.controls[0].context_tokens_per_request != 16_384
        || request.sources.controls[1].context_tokens_per_request != 90_000
        || request.context_points.is_empty()
        || request.concurrency_min == 0
        || request.concurrency_min > request.concurrency_max
    {
        return Err(GlmMappingContextFrontierError::InvalidField("frontier"));
    }
    let expected_contexts = [
        16_384, 32_768, 65_536, 90_000, 131_072, 262_144, 524_288, 1_048_576,
    ];
    if request.context_points.as_slice() != expected_contexts
        || request.concurrency_min != 1
        || request.concurrency_max != 96
    {
        return Err(GlmMappingContextFrontierError::InvalidField(
            "context_concurrency_grid",
        ));
    }
    for control in &request.sources.controls {
        if control.mapping_report_content_id.trim().is_empty()
            || control.lowering_report_content_id.trim().is_empty()
            || control.lower_action_ledger_content_id.trim().is_empty()
        {
            return Err(GlmMappingContextFrontierError::InvalidField(
                "sources.controls",
            ));
        }
    }
    Ok(())
}

fn validate_storage(
    request: &GlmMappingContextFrontierRequest,
    storage: &GlmStorageEnvelopeReport,
) -> Result<(), GlmMappingContextFrontierError> {
    if !storage
        .verify_content_id()
        .map_err(|_| GlmMappingContextFrontierError::InvalidStorageReportContentId)?
    {
        return Err(GlmMappingContextFrontierError::InvalidStorageReportContentId);
    }
    if request.sources.storage_report_content_id != storage.content_id {
        return Err(GlmMappingContextFrontierError::StorageReportContentIdMismatch);
    }
    Ok(())
}

fn validate_control_identity(
    request: &GlmMappingContextFrontierRequest,
    storage: &GlmStorageEnvelopeReport,
    control: &Control<'_>,
) -> Result<(), GlmMappingContextFrontierError> {
    let context = control.pin.context_tokens_per_request;
    if !control.mapping.verify_content_id().map_err(|_| {
        GlmMappingContextFrontierError::InvalidMappingReportContentId {
            context_tokens_per_request: context,
        }
    })? {
        return Err(
            GlmMappingContextFrontierError::InvalidMappingReportContentId {
                context_tokens_per_request: context,
            },
        );
    }
    if control.pin.mapping_report_content_id != control.mapping.content_id {
        return Err(
            GlmMappingContextFrontierError::MappingReportContentIdMismatch {
                context_tokens_per_request: context,
            },
        );
    }
    if !control.lowering.verify_content_id().map_err(|_| {
        GlmMappingContextFrontierError::InvalidLoweringReportContentId {
            context_tokens_per_request: context,
        }
    })? {
        return Err(
            GlmMappingContextFrontierError::InvalidLoweringReportContentId {
                context_tokens_per_request: context,
            },
        );
    }
    if control.pin.lowering_report_content_id != control.lowering.content_id
        || control.mapping.result.sources.lowering_report_content_id != control.lowering.content_id
    {
        return Err(
            GlmMappingContextFrontierError::LoweringReportContentIdMismatch {
                context_tokens_per_request: context,
            },
        );
    }
    if control.pin.lower_action_ledger_content_id
        != control.lowering.result.lower_bound_ledger_content_id
        || control
            .mapping
            .result
            .sources
            .lower_action_ledger_content_id
            != control.lowering.result.lower_bound_ledger_content_id
    {
        return Err(
            GlmMappingContextFrontierError::LowerActionLedgerContentIdMismatch {
                context_tokens_per_request: context,
            },
        );
    }
    if control.mapping.result.sources.storage_report_content_id != storage.content_id
        || control.mapping.result.variant_id != request.variant_id
        || control.mapping.result.device_profile_id != request.device_profile_id
        || control.mapping.result.residency_context_tokens_per_request != context
        || control
            .mapping
            .result
            .network_workload
            .context_tokens_per_request
            != context
    {
        return Err(GlmMappingContextFrontierError::ControlContextMismatch {
            context_tokens_per_request: context,
        });
    }
    Ok(())
}

fn validate_shared_geometry(
    request: &GlmMappingContextFrontierRequest,
    controls: &[Control<'_>; 2],
) -> Result<(), GlmMappingContextFrontierError> {
    let left = &controls[0].mapping.result;
    let right = &controls[1].mapping.result;
    if left.sources.storage_report_content_id != right.sources.storage_report_content_id
        || left.sources.route_report_content_id != right.sources.route_report_content_id
        || left.sources.dsa_report_content_id != right.sources.dsa_report_content_id
        || left.variant_id != right.variant_id
        || left.checkpoint_model_id != right.checkpoint_model_id
        || left.checkpoint_revision != right.checkpoint_revision
        || left.checkpoint_payload_bytes != right.checkpoint_payload_bytes
        || left.routed_expert_resident_bytes != right.routed_expert_resident_bytes
        || left.source_semantic_cache_bytes_per_token != right.source_semantic_cache_bytes_per_token
        || left.semantic_cache.format_id != right.semantic_cache.format_id
        || left.semantic_cache.bytes_per_token != right.semantic_cache.bytes_per_token
        || left.topology != right.topology
        || left.device_profile_id != right.device_profile_id
        || left.usable_memory_bytes_per_device != right.usable_memory_bytes_per_device
        || left.network_workload.batch_size_per_repetition
            != right.network_workload.batch_size_per_repetition
        || left.network_workload.candidate_tokens_per_repetition
            != right.network_workload.candidate_tokens_per_repetition
        || left.network_workload.integer_repetitions != right.network_workload.integer_repetitions
        || left.network_workload.aggregate_batch_size != right.network_workload.aggregate_batch_size
        || left.network_workload.aggregate_candidate_tokens
            != right.network_workload.aggregate_candidate_tokens
        || left.network_workload.hidden_payload_bytes_per_repetition
            != right.network_workload.hidden_payload_bytes_per_repetition
        || left.network_comparison != right.network_comparison
    {
        return Err(GlmMappingContextFrontierError::SharedGeometryMismatch);
    }
    for plan_id in [&request.baseline_plan_id, &request.candidate_plan_id] {
        let left_plan = find_plan(&left.plans, plan_id)?;
        let right_plan = find_plan(&right.plans, plan_id)?;
        if !same_plan_contract(left_plan, right_plan) {
            return Err(GlmMappingContextFrontierError::SharedGeometryMismatch);
        }
    }
    let left_lowering = &controls[0].lowering.result;
    let right_lowering = &controls[1].lowering.result;
    if left_lowering.model_id != right_lowering.model_id
        || left_lowering.model_revision != right_lowering.model_revision
        || left_lowering.checkpoint != right_lowering.checkpoint
        || left_lowering.active_parameters != right_lowering.active_parameters
        || !same_route_geometry(&left_lowering.route, &right_lowering.route)
        || left_lowering.weights != right_lowering.weights
        || left_lowering
            .compute
            .exact_routed_expert_flops_per_candidate_token
            != right_lowering
                .compute
                .exact_routed_expert_flops_per_candidate_token
        || left_lowering
            .compute
            .exact_shared_and_dense_ffn_flops_per_candidate_token
            != right_lowering
                .compute
                .exact_shared_and_dense_ffn_flops_per_candidate_token
        || left_lowering.compute.exact_ffn_flops_per_candidate_token
            != right_lowering.compute.exact_ffn_flops_per_candidate_token
        || left_lowering.compute.exact_routed_expert_flops
            != right_lowering.compute.exact_routed_expert_flops
        || left_lowering.compute.exact_shared_and_dense_ffn_flops
            != right_lowering.compute.exact_shared_and_dense_ffn_flops
        || left_lowering.compute.exact_ffn_flops != right_lowering.compute.exact_ffn_flops
        || find_plan(&left.plans, &request.baseline_plan_id).is_err()
        || find_plan(&left.plans, &request.candidate_plan_id).is_err()
    {
        return Err(GlmMappingContextFrontierError::SharedGeometryMismatch);
    }
    Ok(())
}

fn same_route_geometry(
    left: &crate::glm_decode::RouteAggregateLedger,
    right: &crate::glm_decode::RouteAggregateLedger,
) -> bool {
    left.total_dispatches == right.total_dispatches
        && left.unique_routed_expert_instances == right.unique_routed_expert_instances
        && left.remote_dispatches == right.remote_dispatches
        && left.endpoint_payload_bytes == right.endpoint_payload_bytes
        && left.endpoint_message_count == right.endpoint_message_count
        && left.network_hop_payload_bytes == right.network_hop_payload_bytes
        && left.network_hop_message_count == right.network_hop_message_count
        && left.participants == right.participants
        && left.evidence == right.evidence
        && left.route_report_selection == right.route_report_selection
}

fn same_plan_contract(left: &ParallelPlanReport, right: &ParallelPlanReport) -> bool {
    left.plan_id == right.plan_id
        && left.attention_parallelism == right.attention_parallelism
        && left.attention_groups == right.attention_groups
        && left.expert_parallelism == right.expert_parallelism
        && left.expert_groups == right.expert_groups
        && left.semantic_cache_placement == right.semantic_cache_placement
        && left.non_routed_weight_mapping == right.non_routed_weight_mapping
        && left.expert_network_model == right.expert_network_model
        && left.routed_weight_replication_factor == right.routed_weight_replication_factor
        && left.non_routed_weight_replication_factor == right.non_routed_weight_replication_factor
        && left.network == right.network
}

fn validate_storage_geometry<'a>(
    request: &GlmMappingContextFrontierRequest,
    storage: &'a GlmStorageEnvelopeReport,
    mapping: &'a crate::glm_parallel_mapping::GlmParallelMappingReport,
) -> Result<ValidatedInputs<'a>, GlmMappingContextFrontierError> {
    let variant = storage
        .result
        .variants
        .iter()
        .find(|variant| variant.variant_id == request.variant_id)
        .ok_or(GlmMappingContextFrontierError::VariantNotFound)?;
    let hardware = variant
        .hardware
        .iter()
        .find(|hardware| hardware.hardware_id == request.device_profile_id)
        .ok_or(GlmMappingContextFrontierError::DeviceProfileNotFound)?;
    if variant.checkpoint.model_id != mapping.result.checkpoint_model_id
        || variant.checkpoint.checkpoint_revision != mapping.result.checkpoint_revision
        || variant.checkpoint.payload_bytes != mapping.result.checkpoint_payload_bytes
        || variant.routed_experts.resident_storage_bytes
            != mapping.result.routed_expert_resident_bytes
        || storage.result.semantic_mla_cache_bytes_per_token
            != mapping.result.source_semantic_cache_bytes_per_token
        || hardware.deployment_device_count != mapping.result.topology.device_count
        || hardware.usable_memory_bytes_per_device != mapping.result.usable_memory_bytes_per_device
        || storage.result.residency_assumptions.fixed_runtime_bytes
            % u64::from(mapping.result.topology.device_count)
            != 0
    {
        return Err(GlmMappingContextFrontierError::StorageGeometryMismatch);
    }
    let baseline = find_plan(&mapping.result.plans, &request.baseline_plan_id)?;
    let candidate = find_plan(&mapping.result.plans, &request.candidate_plan_id)?;
    validate_plan_geometry(baseline, mapping.result.topology.device_count)?;
    validate_plan_geometry(candidate, mapping.result.topology.device_count)?;
    Ok(ValidatedInputs {
        variant,
        hardware,
        baseline,
        candidate,
        semantic_cache_bytes_per_token: mapping.result.semantic_cache.bytes_per_token,
        device_count: mapping.result.topology.device_count,
    })
}

fn validate_lowerer_geometry(
    storage: &GlmStorageEnvelopeReport,
    controls: &[Control<'_>; 2],
) -> Result<(), GlmMappingContextFrontierError> {
    for control in controls {
        let context = control.pin.context_tokens_per_request;
        let batch = u64::from(
            control
                .mapping
                .result
                .network_workload
                .batch_size_per_repetition,
        );
        let expected = checked_mul(
            checked_mul(storage.result.semantic_mla_cache_bytes_per_token, context)?,
            batch,
        )?;
        if control.lowering.result.semantic_kv_resident_bytes != expected
            || control.lowering.result.checkpoint.checkpoint.model_id
                != control.mapping.result.checkpoint_model_id
            || control
                .lowering
                .result
                .checkpoint
                .checkpoint
                .checkpoint_revision
                != control.mapping.result.checkpoint_revision
            || control.lowering.result.checkpoint.checkpoint.payload_bytes
                != control.mapping.result.checkpoint_payload_bytes
        {
            return Err(GlmMappingContextFrontierError::LowererGeometryMismatch {
                context_tokens_per_request: context,
            });
        }
    }
    Ok(())
}

fn validate_plan_geometry(
    plan: &ParallelPlanReport,
    device_count: u32,
) -> Result<(), GlmMappingContextFrontierError> {
    let attention_degree = group_degree(&plan.attention_groups)?;
    let expert_degree = group_degree(&plan.expert_groups)?;
    let attention_devices = checked_mul(
        u64::from(attention_degree),
        u64::try_from(plan.attention_groups.len())
            .map_err(|_| GlmMappingContextFrontierError::ArithmeticOverflow)?,
    )?;
    let expert_devices = checked_mul(
        u64::from(expert_degree),
        u64::try_from(plan.expert_groups.len())
            .map_err(|_| GlmMappingContextFrontierError::ArithmeticOverflow)?,
    )?;
    if attention_devices != u64::from(device_count)
        || expert_devices != u64::from(device_count)
        || plan.routed_weight_replication_factor
            != u32::try_from(plan.expert_groups.len())
                .map_err(|_| GlmMappingContextFrontierError::ArithmeticOverflow)?
        || plan.non_routed_weight_replication_factor
            != u32::try_from(plan.attention_groups.len())
                .map_err(|_| GlmMappingContextFrontierError::ArithmeticOverflow)?
    {
        return Err(GlmMappingContextFrontierError::InvalidPlanGeometry(
            plan.plan_id.clone(),
        ));
    }
    Ok(())
}

fn reproduce_anchor(
    request: &GlmMappingContextFrontierRequest,
    storage: &GlmStorageEnvelopeReport,
    validated: &ValidatedInputs<'_>,
    control: &Control<'_>,
) -> Result<AnchorRegressionWitness, GlmMappingContextFrontierError> {
    let context = control.pin.context_tokens_per_request;
    let stored_baseline = find_plan(&control.mapping.result.plans, &request.baseline_plan_id)?;
    let stored_candidate = find_plan(&control.mapping.result.plans, &request.candidate_plan_id)?;
    let stored_concurrency_points = stored_baseline
        .residency
        .iter()
        .map(|point| point.concurrent_requests)
        .collect::<Vec<_>>();
    if stored_candidate
        .residency
        .iter()
        .map(|point| point.concurrent_requests)
        .collect::<Vec<_>>()
        != stored_concurrency_points
    {
        return Err(GlmMappingContextFrontierError::AnchorDoesNotReproduce {
            context_tokens_per_request: context,
        });
    }
    for concurrency in &stored_concurrency_points {
        let baseline = evaluate_residency(
            context,
            *concurrency,
            validated.baseline,
            storage,
            validated,
        )?;
        let candidate = evaluate_residency(
            context,
            *concurrency,
            validated.candidate,
            storage,
            validated,
        )?;
        if find_residency(stored_baseline, *concurrency)? != &baseline
            || find_residency(stored_candidate, *concurrency)? != &candidate
        {
            return Err(GlmMappingContextFrontierError::AnchorDoesNotReproduce {
                context_tokens_per_request: context,
            });
        }
    }
    for stored in &control.mapping.result.partial_comparisons {
        let reproduced = compare_partial(
            context,
            stored.concurrent_requests,
            validated.baseline,
            validated.candidate,
            validated,
        )?;
        if stored != &reproduced {
            return Err(GlmMappingContextFrontierError::AnchorDoesNotReproduce {
                context_tokens_per_request: context,
            });
        }
    }
    let witness_concurrency = 16;
    Ok(AnchorRegressionWitness {
        context_tokens_per_request: context,
        mapping_report_content_id: control.mapping.content_id.clone(),
        lowering_report_content_id: control.lowering.content_id.clone(),
        lower_action_ledger_content_id: control
            .lowering
            .result
            .lower_bound_ledger_content_id
            .clone(),
        stored_concurrency_points: stored_concurrency_points.clone(),
        reproduced_stored_point_count: u32::try_from(stored_concurrency_points.len())
            .map_err(|_| GlmMappingContextFrontierError::ArithmeticOverflow)?,
        reproduced_partial_comparison_count: u32::try_from(
            control.mapping.result.partial_comparisons.len(),
        )
        .map_err(|_| GlmMappingContextFrontierError::ArithmeticOverflow)?,
        all_stored_points_reproduced_exactly: true,
        witness_concurrency,
        baseline_witness: find_residency(stored_baseline, witness_concurrency)?.clone(),
        candidate_witness: find_residency(stored_candidate, witness_concurrency)?.clone(),
        witness_partial_comparison: control
            .mapping
            .result
            .partial_comparisons
            .iter()
            .find(|point| point.concurrent_requests == witness_concurrency)
            .ok_or(GlmMappingContextFrontierError::AnchorDoesNotReproduce {
                context_tokens_per_request: context,
            })?
            .clone(),
    })
}

fn network_control(
    request: &GlmMappingContextFrontierRequest,
    controls: &[Control<'_>; 2],
    validated: &ValidatedInputs<'_>,
) -> Result<ContextInvariantNetworkControl, GlmMappingContextFrontierError> {
    let baseline_90k = find_plan(&controls[1].mapping.result.plans, &request.baseline_plan_id)?;
    let candidate_90k = find_plan(
        &controls[1].mapping.result.plans,
        &request.candidate_plan_id,
    )?;
    if validated.baseline.network != baseline_90k.network
        || validated.candidate.network != candidate_90k.network
        || controls[0].mapping.result.network_comparison
            != controls[1].mapping.result.network_comparison
    {
        return Err(GlmMappingContextFrontierError::NetworkControlMismatch);
    }
    Ok(ContextInvariantNetworkControl {
        anchor_context_tokens: controls
            .iter()
            .map(|control| control.pin.context_tokens_per_request)
            .collect(),
        exactly_equal_across_anchors: true,
        contract: "The exact decode work unit keeps batch size, candidate tokens, activation precision, integer repetitions, route selection, plans, and topology fixed. Both anchors produce byte-identical network reports, which are stated once and are not scaled or interpolated by context or residency concurrency.".into(),
        baseline_plan_id: request.baseline_plan_id.clone(),
        candidate_plan_id: request.candidate_plan_id.clone(),
        baseline: validated.baseline.network.clone(),
        candidate: validated.candidate.network.clone(),
        comparison: controls[0].mapping.result.network_comparison.clone(),
    })
}

fn evaluate_context(
    request: &GlmMappingContextFrontierRequest,
    storage: &GlmStorageEnvelopeReport,
    validated: &ValidatedInputs<'_>,
    context: u64,
) -> Result<ContextPolicyFrontier, GlmMappingContextFrontierError> {
    let semantic_cache_bytes_per_request =
        checked_mul(validated.semantic_cache_bytes_per_token, context)?;
    let mut points = Vec::new();
    let mut partial_policy_regions = Vec::new();
    let mut baseline_capacity_status_regions = Vec::new();
    let mut candidate_capacity_status_regions = Vec::new();
    let mut capacity_relation_regions = Vec::new();
    for concurrent_requests in request.concurrency_min..=request.concurrency_max {
        let point =
            evaluate_context_concurrency_point(context, concurrent_requests, storage, validated)?;
        extend_partial_region(
            &mut partial_policy_regions,
            concurrent_requests,
            point.partial_policy,
        );
        extend_capacity_region(
            &mut capacity_relation_regions,
            concurrent_requests,
            point.full_capacity_relation,
        );
        extend_capacity_status_region(
            &mut baseline_capacity_status_regions,
            concurrent_requests,
            point.baseline_full_capacity.capacity_status,
        );
        extend_capacity_status_region(
            &mut candidate_capacity_status_regions,
            concurrent_requests,
            point.candidate_full_capacity.capacity_status,
        );
        points.push(point);
    }
    Ok(ContextPolicyFrontier {
        context_tokens_per_request: context,
        semantic_cache_bytes_per_request,
        partial_policy_regions,
        baseline_capacity_status_regions,
        candidate_capacity_status_regions,
        capacity_relation_regions,
        points,
    })
}

fn evaluate_context_concurrency_point(
    context: u64,
    concurrent_requests: u32,
    storage: &GlmStorageEnvelopeReport,
    validated: &ValidatedInputs<'_>,
) -> Result<ContextConcurrencyPoint, GlmMappingContextFrontierError> {
    let baseline = evaluate_residency(
        context,
        concurrent_requests,
        validated.baseline,
        storage,
        validated,
    )?;
    let candidate = evaluate_residency(
        context,
        concurrent_requests,
        validated.candidate,
        storage,
        validated,
    )?;
    let partial_comparison = compare_partial(
        context,
        concurrent_requests,
        validated.baseline,
        validated.candidate,
        validated,
    )?;
    let partial_policy = partial_policy(&partial_comparison);
    let full_capacity_relation = capacity_relation(
        baseline.full.capacity_status,
        candidate.full.capacity_status,
    );
    Ok(ContextConcurrencyPoint {
        concurrent_requests,
        partial_comparison,
        partial_policy,
        baseline_full_capacity: FullCapacityPoint {
            total_bytes_on_max_device: baseline.full.total_bytes_on_max_device,
            capacity_status: baseline.full.capacity_status,
        },
        candidate_full_capacity: FullCapacityPoint {
            total_bytes_on_max_device: candidate.full.total_bytes_on_max_device,
            capacity_status: candidate.full.capacity_status,
        },
        full_capacity_relation,
    })
}

fn evaluate_residency(
    context: u64,
    concurrent_requests: u32,
    plan: &ParallelPlanReport,
    storage: &GlmStorageEnvelopeReport,
    validated: &ValidatedInputs<'_>,
) -> Result<ResidencyPoint, GlmMappingContextFrontierError> {
    let semantic_per_request = checked_mul(validated.semantic_cache_bytes_per_token, context)?;
    let cache_copies = cache_copies_on_max_device(plan, concurrent_requests)?;
    let semantic_on_max = checked_mul(semantic_per_request, u64::from(cache_copies))?;
    let routed = validated.variant.routed_experts.resident_storage_bytes;
    let expert_degree = u64::from(group_degree(&plan.expert_groups)?);
    let routed_per_device =
        ByteBounds::new(routed.lower / expert_degree, routed.upper / expert_degree);
    let partial_on_max = add_bounds(routed_per_device, ByteBounds::exact(semantic_on_max))?;
    let routed_cluster = ByteBounds::new(
        checked_mul(
            routed.lower,
            u64::from(plan.routed_weight_replication_factor),
        )?,
        checked_mul(
            routed.upper,
            u64::from(plan.routed_weight_replication_factor),
        )?,
    );
    let cluster_cache_copies =
        cluster_cache_copies(plan, concurrent_requests, validated.device_count)?;
    let cluster_semantic = checked_mul(semantic_per_request, cluster_cache_copies)?;
    let partial = PartialResidencyReport {
        scope: PartialResidencyScope::RoutedWeightsPlusSemanticCacheOnly,
        routed_weight_bytes_on_max_device: routed_per_device,
        semantic_cache_copies_on_max_device: cache_copies,
        semantic_cache_bytes_on_max_device: semantic_on_max,
        total_bytes_on_max_device: partial_on_max,
        cluster_total_bytes: add_bounds(routed_cluster, ByteBounds::exact(cluster_semantic))?,
    };
    let checkpoint_weights = checkpoint_weight_bounds_on_max_device(
        validated.variant.checkpoint.payload_bytes,
        routed,
        group_degree(&plan.expert_groups)?,
        group_degree(&plan.attention_groups)?,
        validated.device_count,
        plan.non_routed_weight_mapping,
    )?;
    let assumptions = &storage.result.residency_assumptions;
    let extra_per_token = add_bounds(
        assumptions.extra_cache_bytes_per_token,
        assumptions.indexer_cache_bytes_per_token,
    )?;
    let cached_tokens = checked_mul(context, u64::from(cache_copies))?;
    let extra_and_indexer = mul_bounds(extra_per_token, cached_tokens)?;
    let runtime = assumptions.fixed_runtime_bytes / u64::from(validated.device_count);
    let unfragmented = add_bounds(
        add_bounds(checkpoint_weights, ByteBounds::exact(semantic_on_max))?,
        add_bounds(extra_and_indexer, ByteBounds::exact(runtime))?,
    )?;
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
    let total = add_bounds(unfragmented, fragmentation)?;
    let usable = validated.hardware.usable_memory_bytes_per_device;
    let capacity_status = if total.upper <= usable {
        CapacityStatus::Feasible
    } else if total.lower > usable {
        CapacityStatus::Infeasible
    } else {
        CapacityStatus::Uncertain
    };
    Ok(ResidencyPoint {
        concurrent_requests,
        context_tokens_per_request: context,
        partial,
        full: FullMappedResidencyReport {
            checkpoint_weight_bytes_on_max_device: checkpoint_weights,
            semantic_cache_bytes_on_max_device: semantic_on_max,
            extra_and_indexer_cache_bytes_on_max_device: extra_and_indexer,
            fixed_runtime_bytes_on_device: runtime,
            unfragmented_bytes_on_max_device: unfragmented,
            fragmentation_overhead_bytes_on_max_device: fragmentation,
            total_bytes_on_max_device: total,
            usable_memory_bytes_per_device: usable,
            capacity_status,
        },
    })
}

fn compare_partial(
    context: u64,
    concurrent_requests: u32,
    baseline: &ParallelPlanReport,
    candidate: &ParallelPlanReport,
    validated: &ValidatedInputs<'_>,
) -> Result<PartialResidencyComparison, GlmMappingContextFrontierError> {
    let semantic_per_request = checked_mul(validated.semantic_cache_bytes_per_token, context)?;
    let routed = validated.variant.routed_experts.resident_storage_bytes;
    let baseline_cluster_cache =
        cluster_cache_copies(baseline, concurrent_requests, validated.device_count)?;
    let candidate_cluster_cache =
        cluster_cache_copies(candidate, concurrent_requests, validated.device_count)?;
    let cluster_delta = paired_delta(routed, |routed_bytes| {
        signed_sum(
            checked_mul(
                routed_bytes,
                u64::from(candidate.routed_weight_replication_factor),
            )?,
            checked_mul(
                routed_bytes,
                u64::from(baseline.routed_weight_replication_factor),
            )?,
            candidate_cluster_cache,
            baseline_cluster_cache,
            semantic_per_request,
        )
    })?;
    let baseline_degree = u64::from(group_degree(&baseline.expert_groups)?);
    let candidate_degree = u64::from(group_degree(&candidate.expert_groups)?);
    let baseline_cache = u64::from(cache_copies_on_max_device(baseline, concurrent_requests)?);
    let candidate_cache = u64::from(cache_copies_on_max_device(candidate, concurrent_requests)?);
    let max_device_delta = paired_delta(routed, |routed_bytes| {
        signed_sum(
            routed_bytes / candidate_degree,
            routed_bytes / baseline_degree,
            candidate_cache,
            baseline_cache,
            semantic_per_request,
        )
    })?;
    Ok(PartialResidencyComparison {
        concurrent_requests,
        candidate_minus_baseline_cluster_total_bytes: cluster_delta,
        cluster_total_partial_dominance: dominance(cluster_delta),
        candidate_minus_baseline_max_device_bytes: max_device_delta,
        max_device_partial_dominance: dominance(max_device_delta),
    })
}

fn checkpoint_weight_bounds_on_max_device(
    checkpoint_payload: u64,
    routed: ByteBounds,
    expert_degree: u32,
    attention_degree: u32,
    device_count: u32,
    mapping: NonRoutedWeightMapping,
) -> Result<ByteBounds, GlmMappingContextFrontierError> {
    let (lower_non_routed_degree, upper_non_routed_degree) = match mapping {
        NonRoutedWeightMapping::AttentionGroupsExact => (attention_degree, attention_degree),
        NonRoutedWeightMapping::OpaqueGlobalShardToAttentionReplication => {
            (device_count, attention_degree)
        }
    };
    let lower = [routed.lower, routed.upper]
        .into_iter()
        .map(|routed_bytes| {
            let non_routed = checkpoint_payload
                .checked_sub(routed_bytes)
                .ok_or(GlmMappingContextFrontierError::ArithmeticOverflow)?;
            checked_add(
                routed_bytes / u64::from(expert_degree),
                non_routed / u64::from(lower_non_routed_degree),
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    let upper = [routed.lower, routed.upper]
        .into_iter()
        .map(|routed_bytes| {
            let non_routed = checkpoint_payload
                .checked_sub(routed_bytes)
                .ok_or(GlmMappingContextFrontierError::ArithmeticOverflow)?;
            checked_add(
                routed_bytes / u64::from(expert_degree),
                non_routed / u64::from(upper_non_routed_degree),
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    Ok(ByteBounds::new(
        *lower
            .iter()
            .min()
            .ok_or(GlmMappingContextFrontierError::ArithmeticOverflow)?,
        *upper
            .iter()
            .max()
            .ok_or(GlmMappingContextFrontierError::ArithmeticOverflow)?,
    ))
}

fn cache_copies_on_max_device(
    plan: &ParallelPlanReport,
    concurrent_requests: u32,
) -> Result<u32, GlmMappingContextFrontierError> {
    match plan.semantic_cache_placement {
        SemanticCachePlacement::ReplicatedAcrossAllDevices => Ok(concurrent_requests),
        SemanticCachePlacement::AttentionGroupLocal => Ok(concurrent_requests.div_ceil(
            u32::try_from(plan.attention_groups.len())
                .map_err(|_| GlmMappingContextFrontierError::ArithmeticOverflow)?,
        )),
    }
}

fn cluster_cache_copies(
    plan: &ParallelPlanReport,
    concurrent_requests: u32,
    device_count: u32,
) -> Result<u64, GlmMappingContextFrontierError> {
    let multiplier = match plan.semantic_cache_placement {
        SemanticCachePlacement::ReplicatedAcrossAllDevices => device_count,
        SemanticCachePlacement::AttentionGroupLocal => group_degree(&plan.attention_groups)?,
    };
    checked_mul(u64::from(concurrent_requests), u64::from(multiplier))
}

fn paired_delta<F>(
    routed: ByteBounds,
    evaluate: F,
) -> Result<SignedBounds, GlmMappingContextFrontierError>
where
    F: Fn(u64) -> Result<i128, GlmMappingContextFrontierError>,
{
    let values = [evaluate(routed.lower)?, evaluate(routed.upper)?];
    Ok(SignedBounds {
        lower: *values
            .iter()
            .min()
            .ok_or(GlmMappingContextFrontierError::ArithmeticOverflow)?,
        upper: *values
            .iter()
            .max()
            .ok_or(GlmMappingContextFrontierError::ArithmeticOverflow)?,
    })
}

fn signed_sum(
    candidate_weight: u64,
    baseline_weight: u64,
    candidate_cache_copies: u64,
    baseline_cache_copies: u64,
    semantic_per_request: u64,
) -> Result<i128, GlmMappingContextFrontierError> {
    let weight_delta = i128::from(candidate_weight) - i128::from(baseline_weight);
    let cache_delta = i128::from(candidate_cache_copies) - i128::from(baseline_cache_copies);
    weight_delta
        .checked_add(
            cache_delta
                .checked_mul(i128::from(semantic_per_request))
                .ok_or(GlmMappingContextFrontierError::ArithmeticOverflow)?,
        )
        .ok_or(GlmMappingContextFrontierError::ArithmeticOverflow)
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

fn partial_policy(comparison: &PartialResidencyComparison) -> PartialPolicy {
    match (
        comparison.cluster_total_partial_dominance,
        comparison.max_device_partial_dominance,
    ) {
        (Dominance::BaselineLower, Dominance::BaselineLower) => PartialPolicy::CoupledRobustLower,
        (Dominance::CandidateLower, Dominance::CandidateLower) => {
            PartialPolicy::DecoupledRobustLower
        }
        _ => PartialPolicy::BoundsOverlapOrMetricDisagreement,
    }
}

fn capacity_relation(
    baseline: CapacityStatus,
    candidate: CapacityStatus,
) -> FrontierCapacityRelation {
    match (
        baseline == CapacityStatus::Feasible,
        candidate == CapacityStatus::Feasible,
    ) {
        (true, true) => FrontierCapacityRelation::BothPlansProvenFeasible,
        (true, false) => FrontierCapacityRelation::BaselineOnlyProvenFeasible,
        (false, true) => FrontierCapacityRelation::CandidateOnlyProvenFeasible,
        (false, false) => FrontierCapacityRelation::NeitherPlanProvenFeasible,
    }
}

fn extend_partial_region(
    regions: &mut Vec<PartialPolicyRegion>,
    concurrency: u32,
    policy: PartialPolicy,
) {
    if let Some(last) = regions.last_mut()
        && last.policy == policy
        && last.end_concurrency.checked_add(1) == Some(concurrency)
    {
        last.end_concurrency = concurrency;
        return;
    }
    regions.push(PartialPolicyRegion {
        start_concurrency: concurrency,
        end_concurrency: concurrency,
        policy,
    });
}

fn extend_capacity_region(
    regions: &mut Vec<CapacityRelationRegion>,
    concurrency: u32,
    relation: FrontierCapacityRelation,
) {
    if let Some(last) = regions.last_mut()
        && last.relation == relation
        && last.end_concurrency.checked_add(1) == Some(concurrency)
    {
        last.end_concurrency = concurrency;
        return;
    }
    regions.push(CapacityRelationRegion {
        start_concurrency: concurrency,
        end_concurrency: concurrency,
        relation,
    });
}

fn extend_capacity_status_region(
    regions: &mut Vec<CapacityStatusRegion>,
    concurrency: u32,
    status: CapacityStatus,
) {
    if let Some(last) = regions.last_mut()
        && last.status == status
        && last.end_concurrency.checked_add(1) == Some(concurrency)
    {
        last.end_concurrency = concurrency;
        return;
    }
    regions.push(CapacityStatusRegion {
        start_concurrency: concurrency,
        end_concurrency: concurrency,
        status,
    });
}

fn group_degree(
    groups: &[crate::glm_parallel_mapping::DeviceGroup],
) -> Result<u32, GlmMappingContextFrontierError> {
    u32::try_from(
        groups
            .first()
            .ok_or(GlmMappingContextFrontierError::ArithmeticOverflow)?
            .ordered_device_ids
            .len(),
    )
    .map_err(|_| GlmMappingContextFrontierError::ArithmeticOverflow)
}

fn find_plan<'a>(
    plans: &'a [ParallelPlanReport],
    plan_id: &str,
) -> Result<&'a ParallelPlanReport, GlmMappingContextFrontierError> {
    plans
        .iter()
        .find(|plan| plan.plan_id == plan_id)
        .ok_or_else(|| GlmMappingContextFrontierError::PlanNotFound(plan_id.into()))
}

fn find_residency(
    plan: &ParallelPlanReport,
    concurrency: u32,
) -> Result<&ResidencyPoint, GlmMappingContextFrontierError> {
    plan.residency
        .iter()
        .find(|point| point.concurrent_requests == concurrency)
        .ok_or(GlmMappingContextFrontierError::AnchorDoesNotReproduce {
            context_tokens_per_request: 0,
        })
}

fn add_bounds(
    left: ByteBounds,
    right: ByteBounds,
) -> Result<ByteBounds, GlmMappingContextFrontierError> {
    Ok(ByteBounds::new(
        checked_add(left.lower, right.lower)?,
        checked_add(left.upper, right.upper)?,
    ))
}

fn mul_bounds(
    bounds: ByteBounds,
    multiplier: u64,
) -> Result<ByteBounds, GlmMappingContextFrontierError> {
    Ok(ByteBounds::new(
        checked_mul(bounds.lower, multiplier)?,
        checked_mul(bounds.upper, multiplier)?,
    ))
}

fn basis_point_overhead(
    bytes: u64,
    basis_points: u32,
) -> Result<u64, GlmMappingContextFrontierError> {
    let numerator = u128::from(bytes)
        .checked_mul(u128::from(basis_points))
        .ok_or(GlmMappingContextFrontierError::ArithmeticOverflow)?;
    u64::try_from(numerator.div_ceil(10_000))
        .map_err(|_| GlmMappingContextFrontierError::ArithmeticOverflow)
}

fn checked_add(left: u64, right: u64) -> Result<u64, GlmMappingContextFrontierError> {
    left.checked_add(right)
        .ok_or(GlmMappingContextFrontierError::ArithmeticOverflow)
}

fn checked_mul(left: u64, right: u64) -> Result<u64, GlmMappingContextFrontierError> {
    left.checked_mul(right)
        .ok_or(GlmMappingContextFrontierError::ArithmeticOverflow)
}

fn claim_gate() -> MappingContextFrontierClaimGate {
    MappingContextFrontierClaimGate {
        residency_accounting_permitted: true,
        modeled_capacity_arithmetic_permitted: true,
        end_to_end_latency_claim_permitted: false,
        throughput_claim_permitted: false,
        cost_per_token_claim_permitted: false,
        quality_claim_permitted: false,
        blockers: vec![
            MappingContextFrontierBlocker::ContextDependentLowererWorkNotDerived,
            MappingContextFrontierBlocker::RouteHistogramIsSynthetic,
            MappingContextFrontierBlocker::CheckpointExpertLayoutIsOpaque,
            MappingContextFrontierBlocker::CacheScaleAndMetadataAreBoundedNotMeasured,
            MappingContextFrontierBlocker::RuntimeAndFragmentationAreModeled,
            MappingContextFrontierBlocker::ServingAndContentionAreNotModeled,
            MappingContextFrontierBlocker::QualityContractIsNotProvided,
        ],
    }
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a GlmMappingContextFrontierResult,
}

fn report_content_id(
    schema_version: u32,
    result: &GlmMappingContextFrontierResult,
) -> Result<String, GlmMappingContextFrontierError> {
    let bytes = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|_| GlmMappingContextFrontierError::SerializationFailed)?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Clone, Debug, Error, Eq, PartialEq)]
pub enum GlmMappingContextFrontierError {
    #[error("unsupported schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid field {0}")]
    InvalidField(&'static str),
    #[error("storage report content ID is invalid")]
    InvalidStorageReportContentId,
    #[error("storage report content ID pin does not match")]
    StorageReportContentIdMismatch,
    #[error("mapping report content ID is invalid for context {context_tokens_per_request}")]
    InvalidMappingReportContentId { context_tokens_per_request: u64 },
    #[error(
        "mapping report content ID pin does not match for context {context_tokens_per_request}"
    )]
    MappingReportContentIdMismatch { context_tokens_per_request: u64 },
    #[error("lowering report content ID is invalid for context {context_tokens_per_request}")]
    InvalidLoweringReportContentId { context_tokens_per_request: u64 },
    #[error(
        "lowering report content ID pin does not match for context {context_tokens_per_request}"
    )]
    LoweringReportContentIdMismatch { context_tokens_per_request: u64 },
    #[error(
        "lower action ledger content ID pin does not match for context {context_tokens_per_request}"
    )]
    LowerActionLedgerContentIdMismatch { context_tokens_per_request: u64 },
    #[error("control context does not match {context_tokens_per_request}")]
    ControlContextMismatch { context_tokens_per_request: u64 },
    #[error("the two controls do not share exact geometry and topology")]
    SharedGeometryMismatch,
    #[error("storage geometry does not match the mapping controls")]
    StorageGeometryMismatch,
    #[error("lowerer geometry does not match context {context_tokens_per_request}")]
    LowererGeometryMismatch { context_tokens_per_request: u64 },
    #[error("variant was not found")]
    VariantNotFound,
    #[error("device profile was not found")]
    DeviceProfileNotFound,
    #[error("plan {0} was not found")]
    PlanNotFound(String),
    #[error("plan {0} has invalid geometry")]
    InvalidPlanGeometry(String),
    #[error("anchor does not reproduce exactly for context {context_tokens_per_request}")]
    AnchorDoesNotReproduce { context_tokens_per_request: u64 },
    #[error("network controls do not match exactly")]
    NetworkControlMismatch,
    #[error("arithmetic overflow")]
    ArithmeticOverflow,
    #[error("report serialization failed")]
    SerializationFailed,
}
