use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::glm_storage::{
    CheckpointPayloadEvidence, EnvelopeEvidence, GlmStorageEnvelopeReport,
    GlmVariantEnvelopeReport, HardwareVariantEnvelopeReport, MemoryResidencyAssumptions,
};

pub const GLM_RESIDENCY_FRONTIER_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const GLM_RESIDENCY_FRONTIER_REPORT_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SemanticCacheFormatOverride {
    pub source_format_id: String,
    pub override_format_id: String,
    pub override_bytes_per_token: u64,
    pub evidence: EnvelopeEvidence,
    pub basis: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TargetCapacityTopology {
    pub topology_id: String,
    pub device_capacity_evidence: EnvelopeEvidence,
    pub topology_evidence: EnvelopeEvidence,
    pub basis: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmResidencyFrontierRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub storage_report_content_id: String,
    pub variant_id: String,
    pub device_profile_id: String,
    pub target_device_count: u32,
    pub semantic_cache: SemanticCacheFormatOverride,
    pub target: TargetCapacityTopology,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum FrontierCacheBound {
    Lower,
    Upper,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SemanticCacheComparison {
    pub source_format_id: String,
    pub override_format_id: String,
    pub source_bytes_per_token: u64,
    pub override_bytes_per_token: u64,
    pub reduction_bytes_per_token: u64,
    pub source_total_bytes: u64,
    pub override_total_bytes: u64,
    pub total_reduction_bytes: u64,
    pub evidence: EnvelopeEvidence,
    pub basis: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SequenceConcurrencyBoundary {
    pub reserved_tokens_per_sequence: u32,
    pub maximum_feasible_sequences: Option<u64>,
    pub total_resident_bytes_at_maximum: Option<u64>,
    pub first_infeasible_sequences: u64,
    pub total_resident_bytes_at_first_infeasible: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FragmentationBoundary {
    pub maximum_feasible_basis_points: Option<u32>,
    pub total_resident_bytes_at_maximum: Option<u64>,
    pub first_infeasible_basis_points: u32,
    pub total_resident_bytes_at_first_infeasible: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ResidencyBoundFrontier {
    pub cache_bound: FrontierCacheBound,
    pub extra_cache_bytes_per_token: u64,
    pub indexer_cache_bytes_per_token: u64,
    pub cache_bytes_per_reserved_token: u64,
    pub source_unfragmented_resident_bytes: u64,
    pub source_fragmentation_overhead_bytes: u64,
    pub source_total_resident_bytes: u64,
    pub override_unfragmented_resident_bytes: u64,
    pub override_fragmentation_overhead_bytes: u64,
    pub override_total_resident_bytes: u64,
    pub source_to_override_total_resident_reduction_bytes: u64,
    pub aggregate_capacity_feasible: bool,
    pub capacity_headroom_bytes: u64,
    pub total_resident_reduction_required_bytes: u64,
    pub maximum_unfragmented_resident_bytes: u64,
    pub unfragmented_reduction_required_bytes: u64,
    pub maximum_reserved_token_slots: Option<u64>,
    pub maximum_reserved_tokens_per_sequence: Option<u64>,
    pub sequence_boundary: SequenceConcurrencyBoundary,
    pub fragmentation_boundary: FragmentationBoundary,
    pub maximum_fixed_runtime_bytes: Option<u64>,
    pub maximum_fixed_runtime_and_nonsemantic_cache_bytes: Option<u64>,
    pub maximum_extra_cache_bytes_per_token: Option<u64>,
    pub maximum_extra_cache_bytes_per_token_at_zero_fixed_runtime: Option<u64>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum FrontierClaimBlocker {
    AggregateCapacityOnly,
    TargetExecutionTopologyNotValidated,
    ModelFormatKernelSupportNotValidated,
    RuntimeWorkspaceIsModeled,
    CacheLayoutMetadataIsBounded,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ResidencyFrontierClaimGate {
    pub aggregate_capacity_arithmetic_permitted: bool,
    pub executable_topology_permitted: bool,
    pub model_format_kernel_support_permitted: bool,
    pub end_to_end_serving_permitted: bool,
    pub cost_per_token_permitted: bool,
    pub blockers: Vec<FrontierClaimBlocker>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmResidencyFrontierResult {
    pub study_id: String,
    pub storage_report_content_id: String,
    pub model_id: String,
    pub model_revision: String,
    pub variant_id: String,
    pub checkpoint: CheckpointPayloadEvidence,
    pub residency_source_artifact_id: String,
    pub device_profile_id: String,
    pub usable_memory_bytes_per_device: u64,
    pub target_device_count: u32,
    pub target_capacity_bytes: u64,
    pub target: TargetCapacityTopology,
    pub semantic_cache: SemanticCacheComparison,
    pub frontiers: Vec<ResidencyBoundFrontier>,
    pub claims: ResidencyFrontierClaimGate,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmResidencyFrontierReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: GlmResidencyFrontierResult,
}

impl GlmResidencyFrontierReport {
    pub fn verify_content_id(&self) -> Result<bool, GlmResidencyFrontierError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

pub fn evaluate_glm_residency_frontier(
    request: &GlmResidencyFrontierRequest,
    storage: &GlmStorageEnvelopeReport,
) -> Result<GlmResidencyFrontierReport, GlmResidencyFrontierError> {
    let selected = validate_request(request, storage)?;
    let assumptions = &storage.result.residency_assumptions;
    let target_capacity_bytes = selected
        .hardware
        .usable_memory_bytes_per_device
        .checked_mul(u64::from(request.target_device_count))
        .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?;
    let replicated_token_slots = selected
        .variant
        .residency
        .reserved_token_slots
        .checked_mul(u64::from(assumptions.cache_replication_factor))
        .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?;
    let source_semantic_total = storage
        .result
        .semantic_mla_cache_bytes_per_token
        .checked_mul(replicated_token_slots)
        .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?;
    let override_semantic_total = request
        .semantic_cache
        .override_bytes_per_token
        .checked_mul(replicated_token_slots)
        .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?;
    let semantic_cache = SemanticCacheComparison {
        source_format_id: request.semantic_cache.source_format_id.clone(),
        override_format_id: request.semantic_cache.override_format_id.clone(),
        source_bytes_per_token: storage.result.semantic_mla_cache_bytes_per_token,
        override_bytes_per_token: request.semantic_cache.override_bytes_per_token,
        reduction_bytes_per_token: storage
            .result
            .semantic_mla_cache_bytes_per_token
            .checked_sub(request.semantic_cache.override_bytes_per_token)
            .ok_or(GlmResidencyFrontierError::SemanticCacheOverrideIsNotReduction)?,
        source_total_bytes: source_semantic_total,
        override_total_bytes: override_semantic_total,
        total_reduction_bytes: source_semantic_total
            .checked_sub(override_semantic_total)
            .ok_or(GlmResidencyFrontierError::SemanticCacheOverrideIsNotReduction)?,
        evidence: request.semantic_cache.evidence.clone(),
        basis: request.semantic_cache.basis.clone(),
    };
    let frontiers = [FrontierCacheBound::Lower, FrontierCacheBound::Upper]
        .into_iter()
        .map(|bound| {
            evaluate_bound(
                selected.variant,
                assumptions,
                storage.result.semantic_mla_cache_bytes_per_token,
                request.semantic_cache.override_bytes_per_token,
                target_capacity_bytes,
                bound,
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    let result = GlmResidencyFrontierResult {
        study_id: request.study_id.clone(),
        storage_report_content_id: storage.content_id.clone(),
        model_id: storage.result.model_id.clone(),
        model_revision: storage.result.model_revision.clone(),
        variant_id: selected.variant.variant_id.clone(),
        checkpoint: selected.variant.checkpoint.clone(),
        residency_source_artifact_id: assumptions.source_artifact_id.clone(),
        device_profile_id: selected.hardware.hardware_id.clone(),
        usable_memory_bytes_per_device: selected.hardware.usable_memory_bytes_per_device,
        target_device_count: request.target_device_count,
        target_capacity_bytes,
        target: request.target.clone(),
        semantic_cache,
        frontiers,
        claims: claim_gate(),
    };
    let schema_version = GLM_RESIDENCY_FRONTIER_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(GlmResidencyFrontierReport {
        schema_version,
        content_id,
        result,
    })
}

struct SelectedInputs<'a> {
    variant: &'a GlmVariantEnvelopeReport,
    hardware: &'a HardwareVariantEnvelopeReport,
}

fn validate_request<'a>(
    request: &GlmResidencyFrontierRequest,
    storage: &'a GlmStorageEnvelopeReport,
) -> Result<SelectedInputs<'a>, GlmResidencyFrontierError> {
    if request.schema_version != GLM_RESIDENCY_FRONTIER_REQUEST_SCHEMA_VERSION {
        return Err(GlmResidencyFrontierError::UnsupportedSchemaVersion {
            expected: GLM_RESIDENCY_FRONTIER_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    for (field, value) in [
        ("study_id", request.study_id.as_str()),
        (
            "storage_report_content_id",
            request.storage_report_content_id.as_str(),
        ),
        ("variant_id", request.variant_id.as_str()),
        ("device_profile_id", request.device_profile_id.as_str()),
        (
            "semantic_cache.source_format_id",
            request.semantic_cache.source_format_id.as_str(),
        ),
        (
            "semantic_cache.override_format_id",
            request.semantic_cache.override_format_id.as_str(),
        ),
        (
            "semantic_cache.basis",
            request.semantic_cache.basis.as_str(),
        ),
        ("target.topology_id", request.target.topology_id.as_str()),
        ("target.basis", request.target.basis.as_str()),
        (
            "semantic_cache.evidence.source_artifact_id",
            request.semantic_cache.evidence.source_artifact_id.as_str(),
        ),
        (
            "target.device_capacity_evidence.source_artifact_id",
            request
                .target
                .device_capacity_evidence
                .source_artifact_id
                .as_str(),
        ),
        (
            "target.topology_evidence.source_artifact_id",
            request.target.topology_evidence.source_artifact_id.as_str(),
        ),
    ] {
        if value.trim().is_empty() {
            return Err(GlmResidencyFrontierError::InvalidField(field));
        }
    }
    if request.target_device_count == 0 || request.semantic_cache.override_bytes_per_token == 0 {
        return Err(GlmResidencyFrontierError::InvalidField("request"));
    }
    if !storage
        .verify_content_id()
        .map_err(|error| GlmResidencyFrontierError::Storage(error.to_string()))?
    {
        return Err(GlmResidencyFrontierError::InvalidStorageReportContentId);
    }
    if request.storage_report_content_id != storage.content_id {
        return Err(GlmResidencyFrontierError::StorageReportContentIdMismatch);
    }
    if request.semantic_cache.override_bytes_per_token
        >= storage.result.semantic_mla_cache_bytes_per_token
    {
        return Err(GlmResidencyFrontierError::SemanticCacheOverrideIsNotReduction);
    }
    let variant = storage
        .result
        .variants
        .iter()
        .find(|variant| variant.variant_id == request.variant_id)
        .ok_or_else(|| GlmResidencyFrontierError::MissingVariant(request.variant_id.clone()))?;
    let hardware = variant
        .hardware
        .iter()
        .find(|hardware| hardware.hardware_id == request.device_profile_id)
        .ok_or_else(|| {
            GlmResidencyFrontierError::MissingDeviceProfile(request.device_profile_id.clone())
        })?;
    Ok(SelectedInputs { variant, hardware })
}

fn evaluate_bound(
    variant: &GlmVariantEnvelopeReport,
    assumptions: &MemoryResidencyAssumptions,
    source_semantic_bytes_per_token: u64,
    override_semantic_bytes_per_token: u64,
    capacity: u64,
    bound: FrontierCacheBound,
) -> Result<ResidencyBoundFrontier, GlmResidencyFrontierError> {
    let extra = select_bound(assumptions.extra_cache_bytes_per_token, bound);
    let indexer = select_bound(assumptions.indexer_cache_bytes_per_token, bound);
    let replication = u64::from(assumptions.cache_replication_factor);
    let source_cache_per_slot = checked_sum(&[source_semantic_bytes_per_token, extra, indexer])?
        .checked_mul(replication)
        .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?;
    let override_cache_per_slot =
        checked_sum(&[override_semantic_bytes_per_token, extra, indexer])?
            .checked_mul(replication)
            .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?;
    let slots = variant.residency.reserved_token_slots;
    let checkpoint = variant.residency.checkpoint_resident_bytes;
    let fixed = variant.residency.fixed_runtime_bytes;
    let fragmentation_basis_points = assumptions.fragmentation_overhead_basis_points;
    let source_unfragmented =
        resident_unfragmented(checkpoint, fixed, slots, source_cache_per_slot)?;
    let source_fragmentation = fragmentation(source_unfragmented, fragmentation_basis_points)?;
    let source_total = source_unfragmented
        .checked_add(source_fragmentation)
        .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?;
    let expected_source_unfragmented =
        select_bound(variant.residency.unfragmented_resident_bytes, bound);
    let expected_source_fragmentation =
        select_bound(variant.residency.fragmentation_overhead_bytes, bound);
    let expected_source_total = select_bound(variant.residency.total_resident_bytes, bound);
    if source_unfragmented != expected_source_unfragmented
        || source_fragmentation != expected_source_fragmentation
        || source_total != expected_source_total
    {
        return Err(GlmResidencyFrontierError::StorageResidencyMismatch(bound));
    }
    let override_unfragmented =
        resident_unfragmented(checkpoint, fixed, slots, override_cache_per_slot)?;
    let override_fragmentation = fragmentation(override_unfragmented, fragmentation_basis_points)?;
    let override_total = override_unfragmented
        .checked_add(override_fragmentation)
        .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?;
    let maximum_unfragmented = maximum_unfragmented(capacity, fragmentation_basis_points)?;
    let maximum_slots = maximum_slots(
        checkpoint,
        fixed,
        override_cache_per_slot,
        maximum_unfragmented,
    )?;
    let maximum_reserved_tokens_per_sequence =
        maximum_slots.map(|maximum| maximum / u64::from(assumptions.concurrent_sequences));
    let sequence_boundary = sequence_boundary(
        checkpoint,
        fixed,
        override_cache_per_slot,
        fragmentation_basis_points,
        maximum_slots,
        assumptions.reserved_tokens_per_sequence,
    )?;
    let fragmentation_boundary = fragmentation_boundary(override_unfragmented, capacity)?;
    let selected_nonsemantic_per_slot = checked_sum(&[extra, indexer])?
        .checked_mul(replication)
        .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?;
    let semantic_per_slot = override_semantic_bytes_per_token
        .checked_mul(replication)
        .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?;
    let maximum_fixed_runtime_and_nonsemantic_cache_bytes = budget_after(
        maximum_unfragmented,
        checked_sum(&[
            checkpoint,
            slots
                .checked_mul(semantic_per_slot)
                .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?,
        ])?,
    );
    let maximum_fixed_runtime_bytes = budget_after(
        maximum_unfragmented,
        checked_sum(&[
            checkpoint,
            slots
                .checked_mul(
                    semantic_per_slot
                        .checked_add(selected_nonsemantic_per_slot)
                        .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?,
                )
                .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?,
        ])?,
    );
    let maximum_extra_cache_bytes_per_token = maximum_extra_per_token(
        maximum_unfragmented,
        checkpoint,
        fixed,
        slots,
        replication,
        override_semantic_bytes_per_token,
        indexer,
    )?;
    let maximum_extra_cache_bytes_per_token_at_zero_fixed_runtime = maximum_extra_per_token(
        maximum_unfragmented,
        checkpoint,
        0,
        slots,
        replication,
        override_semantic_bytes_per_token,
        indexer,
    )?;
    Ok(ResidencyBoundFrontier {
        cache_bound: bound,
        extra_cache_bytes_per_token: extra,
        indexer_cache_bytes_per_token: indexer,
        cache_bytes_per_reserved_token: override_cache_per_slot,
        source_unfragmented_resident_bytes: source_unfragmented,
        source_fragmentation_overhead_bytes: source_fragmentation,
        source_total_resident_bytes: source_total,
        override_unfragmented_resident_bytes: override_unfragmented,
        override_fragmentation_overhead_bytes: override_fragmentation,
        override_total_resident_bytes: override_total,
        source_to_override_total_resident_reduction_bytes: source_total
            .checked_sub(override_total)
            .ok_or(GlmResidencyFrontierError::SemanticCacheOverrideIsNotReduction)?,
        aggregate_capacity_feasible: override_total <= capacity,
        capacity_headroom_bytes: capacity.saturating_sub(override_total),
        total_resident_reduction_required_bytes: override_total.saturating_sub(capacity),
        maximum_unfragmented_resident_bytes: maximum_unfragmented,
        unfragmented_reduction_required_bytes: override_unfragmented
            .saturating_sub(maximum_unfragmented),
        maximum_reserved_token_slots: maximum_slots,
        maximum_reserved_tokens_per_sequence,
        sequence_boundary,
        fragmentation_boundary,
        maximum_fixed_runtime_bytes,
        maximum_fixed_runtime_and_nonsemantic_cache_bytes,
        maximum_extra_cache_bytes_per_token,
        maximum_extra_cache_bytes_per_token_at_zero_fixed_runtime,
    })
}

fn select_bound(bounds: crate::glm_storage::ByteBounds, bound: FrontierCacheBound) -> u64 {
    match bound {
        FrontierCacheBound::Lower => bounds.lower,
        FrontierCacheBound::Upper => bounds.upper,
    }
}

fn checked_sum(values: &[u64]) -> Result<u64, GlmResidencyFrontierError> {
    values.iter().try_fold(0_u64, |sum, value| {
        sum.checked_add(*value)
            .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)
    })
}

fn resident_unfragmented(
    checkpoint: u64,
    fixed: u64,
    slots: u64,
    cache_per_slot: u64,
) -> Result<u64, GlmResidencyFrontierError> {
    checked_sum(&[
        checkpoint,
        fixed,
        slots
            .checked_mul(cache_per_slot)
            .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?,
    ])
}

fn fragmentation(bytes: u64, basis_points: u32) -> Result<u64, GlmResidencyFrontierError> {
    let numerator = u128::from(bytes)
        .checked_mul(u128::from(basis_points))
        .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?;
    u64::try_from(numerator.div_ceil(10_000))
        .map_err(|_| GlmResidencyFrontierError::ArithmeticOverflow)
}

fn total_with_fragmentation(
    unfragmented: u64,
    basis_points: u32,
) -> Result<u64, GlmResidencyFrontierError> {
    unfragmented
        .checked_add(fragmentation(unfragmented, basis_points)?)
        .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)
}

fn maximum_unfragmented(
    capacity: u64,
    basis_points: u32,
) -> Result<u64, GlmResidencyFrontierError> {
    let mut lower = 0_u64;
    let mut upper = capacity;
    while lower < upper {
        let middle = lower + (upper - lower).div_ceil(2);
        if total_with_fragmentation(middle, basis_points)? <= capacity {
            lower = middle;
        } else {
            upper = middle - 1;
        }
    }
    Ok(lower)
}

fn maximum_slots(
    checkpoint: u64,
    fixed: u64,
    cache_per_slot: u64,
    maximum_unfragmented: u64,
) -> Result<Option<u64>, GlmResidencyFrontierError> {
    let base = checkpoint
        .checked_add(fixed)
        .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?;
    Ok(maximum_unfragmented
        .checked_sub(base)
        .map(|available| available / cache_per_slot))
}

fn sequence_boundary(
    checkpoint: u64,
    fixed: u64,
    cache_per_slot: u64,
    fragmentation_basis_points: u32,
    maximum_slots: Option<u64>,
    reserved_tokens_per_sequence: u32,
) -> Result<SequenceConcurrencyBoundary, GlmResidencyFrontierError> {
    let tokens = u64::from(reserved_tokens_per_sequence);
    let maximum_feasible_sequences = maximum_slots.map(|slots| slots / tokens);
    let total_resident_bytes_at_maximum = maximum_feasible_sequences
        .map(|sequences| {
            resident_total_for_slots(
                checkpoint,
                fixed,
                sequences
                    .checked_mul(tokens)
                    .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?,
                cache_per_slot,
                fragmentation_basis_points,
            )
        })
        .transpose()?;
    let first_infeasible_sequences = match maximum_feasible_sequences {
        Some(maximum) => maximum
            .checked_add(1)
            .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?,
        None => 0,
    };
    let total_resident_bytes_at_first_infeasible = resident_total_for_slots(
        checkpoint,
        fixed,
        first_infeasible_sequences
            .checked_mul(tokens)
            .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?,
        cache_per_slot,
        fragmentation_basis_points,
    )?;
    Ok(SequenceConcurrencyBoundary {
        reserved_tokens_per_sequence,
        maximum_feasible_sequences,
        total_resident_bytes_at_maximum,
        first_infeasible_sequences,
        total_resident_bytes_at_first_infeasible,
    })
}

fn resident_total_for_slots(
    checkpoint: u64,
    fixed: u64,
    slots: u64,
    cache_per_slot: u64,
    fragmentation_basis_points: u32,
) -> Result<u64, GlmResidencyFrontierError> {
    total_with_fragmentation(
        resident_unfragmented(checkpoint, fixed, slots, cache_per_slot)?,
        fragmentation_basis_points,
    )
}

fn fragmentation_boundary(
    unfragmented: u64,
    capacity: u64,
) -> Result<FragmentationBoundary, GlmResidencyFrontierError> {
    let maximum = if unfragmented > capacity {
        None
    } else {
        let numerator = u128::from(capacity - unfragmented)
            .checked_mul(10_000)
            .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?;
        Some(
            u32::try_from(numerator / u128::from(unfragmented))
                .map_err(|_| GlmResidencyFrontierError::ArithmeticOverflow)?,
        )
    };
    let total_resident_bytes_at_maximum = maximum
        .map(|basis_points| total_with_fragmentation(unfragmented, basis_points))
        .transpose()?;
    let first_infeasible_basis_points = match maximum {
        Some(basis_points) => basis_points
            .checked_add(1)
            .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?,
        None => 0,
    };
    let total_resident_bytes_at_first_infeasible =
        total_with_fragmentation(unfragmented, first_infeasible_basis_points)?;
    Ok(FragmentationBoundary {
        maximum_feasible_basis_points: maximum,
        total_resident_bytes_at_maximum,
        first_infeasible_basis_points,
        total_resident_bytes_at_first_infeasible,
    })
}

fn budget_after(maximum: u64, base: u64) -> Option<u64> {
    maximum.checked_sub(base)
}

fn maximum_extra_per_token(
    maximum_unfragmented: u64,
    checkpoint: u64,
    fixed: u64,
    slots: u64,
    replication: u64,
    semantic_bytes_per_token: u64,
    indexer_bytes_per_token: u64,
) -> Result<Option<u64>, GlmResidencyFrontierError> {
    let fixed_base = checked_sum(&[
        checkpoint,
        fixed,
        slots
            .checked_mul(
                semantic_bytes_per_token
                    .checked_add(indexer_bytes_per_token)
                    .and_then(|bytes| bytes.checked_mul(replication))
                    .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?,
            )
            .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?,
    ])?;
    let denominator = slots
        .checked_mul(replication)
        .ok_or(GlmResidencyFrontierError::ArithmeticOverflow)?;
    Ok(maximum_unfragmented
        .checked_sub(fixed_base)
        .map(|available| available / denominator))
}

fn claim_gate() -> ResidencyFrontierClaimGate {
    ResidencyFrontierClaimGate {
        aggregate_capacity_arithmetic_permitted: true,
        executable_topology_permitted: false,
        model_format_kernel_support_permitted: false,
        end_to_end_serving_permitted: false,
        cost_per_token_permitted: false,
        blockers: vec![
            FrontierClaimBlocker::AggregateCapacityOnly,
            FrontierClaimBlocker::TargetExecutionTopologyNotValidated,
            FrontierClaimBlocker::ModelFormatKernelSupportNotValidated,
            FrontierClaimBlocker::RuntimeWorkspaceIsModeled,
            FrontierClaimBlocker::CacheLayoutMetadataIsBounded,
        ],
    }
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a GlmResidencyFrontierResult,
}

fn report_content_id(
    schema_version: u32,
    result: &GlmResidencyFrontierResult,
) -> Result<String, GlmResidencyFrontierError> {
    let bytes = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|error| GlmResidencyFrontierError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum GlmResidencyFrontierError {
    #[error("unsupported GLM residency frontier schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid GLM residency frontier field {0}")]
    InvalidField(&'static str),
    #[error("storage report is invalid: {0}")]
    Storage(String),
    #[error("storage report content identity is invalid")]
    InvalidStorageReportContentId,
    #[error("storage report content identity differs from the request pin")]
    StorageReportContentIdMismatch,
    #[error("storage report does not contain variant {0}")]
    MissingVariant(String),
    #[error("storage report does not contain device profile {0}")]
    MissingDeviceProfile(String),
    #[error("semantic cache override is not a reduction")]
    SemanticCacheOverrideIsNotReduction,
    #[error("storage report residency does not reconcile for {0:?} cache bounds")]
    StorageResidencyMismatch(FrontierCacheBound),
    #[error("GLM residency frontier arithmetic overflowed")]
    ArithmeticOverflow,
    #[error("GLM residency frontier serialization failed: {0}")]
    Serialization(String),
}
