use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::spec::{ModelArchitecture, ModelSpec, stored_weight_bytes};

pub const GLM_STORAGE_ENVELOPE_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const GLM_STORAGE_ENVELOPE_REPORT_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ByteBounds {
    pub lower: u64,
    pub upper: u64,
}

impl ByteBounds {
    pub const fn new(lower: u64, upper: u64) -> Self {
        Self { lower, upper }
    }

    pub const fn exact(bytes: u64) -> Self {
        Self::new(bytes, bytes)
    }

    fn validate(self, field: &'static str) -> Result<(), GlmStorageEnvelopeError> {
        if self.lower > self.upper {
            Err(GlmStorageEnvelopeError::InvalidField(field))
        } else {
            Ok(())
        }
    }

    fn checked_add(self, other: Self) -> Result<Self, GlmStorageEnvelopeError> {
        Ok(Self {
            lower: self
                .lower
                .checked_add(other.lower)
                .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?,
            upper: self
                .upper
                .checked_add(other.upper)
                .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?,
        })
    }

    fn checked_mul(self, multiplier: u64) -> Result<Self, GlmStorageEnvelopeError> {
        Ok(Self {
            lower: self
                .lower
                .checked_mul(multiplier)
                .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?,
            upper: self
                .upper
                .checked_mul(multiplier)
                .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?,
        })
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CountBounds {
    pub lower: u32,
    pub upper: u32,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FloatBounds {
    pub lower: f64,
    pub upper: f64,
}

impl FloatBounds {
    pub const fn new(lower: f64, upper: f64) -> Self {
        Self { lower, upper }
    }

    fn validate_positive(self, field: &'static str) -> Result<(), GlmStorageEnvelopeError> {
        if self.lower.is_finite()
            && self.upper.is_finite()
            && self.lower > 0.0
            && self.lower <= self.upper
        {
            Ok(())
        } else {
            Err(GlmStorageEnvelopeError::InvalidField(field))
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EnvelopeEvidenceKind {
    MeasuredHardware,
    PublishedSpecification,
    AnalyticalBound,
    ModeledAssumption,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EnvelopeEvidence {
    pub kind: EnvelopeEvidenceKind,
    pub source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CheckpointPayloadEvidence {
    pub model_id: String,
    pub checkpoint_revision: String,
    pub payload_bytes: u64,
    pub source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum RoutedExpertStorageEvidence {
    ModelSpecExact {
        source_artifact_id: String,
    },
    OpaqueAggregateBounds {
        bytes: ByteBounds,
        source_artifact_id: String,
        lower_bound_basis: String,
        upper_bound_basis: String,
    },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ActiveTrafficEnvelope {
    pub routed_expert_weight_bytes_per_output_token: ByteBounds,
    pub non_routed_weight_bytes_per_output_token: ByteBounds,
    pub indexer_bytes_per_output_token: ByteBounds,
    pub evidence: EnvelopeEvidence,
    pub basis: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmCheckpointVariant {
    pub variant_id: String,
    pub checkpoint: CheckpointPayloadEvidence,
    pub routed_expert_storage: RoutedExpertStorageEvidence,
    pub active_traffic: Option<ActiveTrafficEnvelope>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MemoryResidencyAssumptions {
    pub checkpoint_replication_factor: u32,
    pub concurrent_sequences: u32,
    pub reserved_tokens_per_sequence: u32,
    pub cache_replication_factor: u32,
    pub extra_cache_bytes_per_token: ByteBounds,
    pub indexer_cache_bytes_per_token: ByteBounds,
    pub fixed_runtime_bytes: u64,
    pub fragmentation_overhead_basis_points: u32,
    pub source_artifact_id: String,
    pub basis: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MemoryBandwidthAssumption {
    pub peak_bytes_per_second_per_device: u64,
    pub efficiency_basis_points: u32,
    pub evidence: EnvelopeEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DeviceCostAssumption {
    pub usd_per_device_hour: f64,
    pub source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HardwareEnvelopeAssumption {
    pub hardware_id: String,
    pub deployment_device_count: u32,
    pub device_memory_bytes: u64,
    pub reserved_device_memory_bytes: u64,
    pub memory_source_artifact_id: String,
    pub bandwidth: MemoryBandwidthAssumption,
    pub cost: DeviceCostAssumption,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BreakEvenThroughputAssumption {
    pub required_billable_tokens_per_second_per_usd_of_hourly_system_cost: f64,
    pub source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MeasuredServingClaimEvidence {
    pub variant_id: String,
    pub hardware_id: String,
    pub output_tokens_per_second: FloatBounds,
    pub end_to_end_latency_seconds_per_output_token: FloatBounds,
    pub source_artifact_id: String,
    pub route_traffic_source_artifact_id: String,
    pub bandwidth_source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmStorageEnvelopeRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub model: ModelSpec,
    pub residency: MemoryResidencyAssumptions,
    pub variants: Vec<GlmCheckpointVariant>,
    pub hardware: Vec<HardwareEnvelopeAssumption>,
    pub break_even: Option<BreakEvenThroughputAssumption>,
    #[serde(default)]
    pub measured_serving_evidence: Vec<MeasuredServingClaimEvidence>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RoutedExpertLedger {
    pub resident_parameter_count: u64,
    pub active_parameter_count_per_token: u64,
    pub resident_storage_bytes: ByteBounds,
    pub per_layer_expert_storage_bytes: Option<ByteBounds>,
    pub active_storage_footprint_bytes_per_token: Option<ByteBounds>,
    pub storage_evidence: RoutedExpertStorageEvidence,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ActiveTrafficEnvelopeReport {
    pub routed_expert_weight_bytes_per_output_token: ByteBounds,
    pub non_routed_weight_bytes_per_output_token: ByteBounds,
    pub indexer_bytes_per_output_token: ByteBounds,
    pub total_bytes_per_output_token: ByteBounds,
    pub evidence: EnvelopeEvidence,
    pub basis: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ResidencyLedger {
    pub checkpoint_payload_bytes: u64,
    pub checkpoint_resident_bytes: u64,
    pub reserved_token_slots: u64,
    pub semantic_mla_cache_bytes: u64,
    pub extra_cache_bytes: ByteBounds,
    pub indexer_cache_bytes: ByteBounds,
    pub fixed_runtime_bytes: u64,
    pub unfragmented_resident_bytes: ByteBounds,
    pub fragmentation_overhead_bytes: ByteBounds,
    pub total_resident_bytes: ByteBounds,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DeploymentCapacityStatus {
    Infeasible,
    Uncertain,
    Feasible,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExpertPlacementReport {
    pub minimum_devices_for_routed_expert_storage: CountBounds,
    pub uniform_layer_expert_slots_per_device: Option<u64>,
    pub minimum_devices_for_uniform_layer_experts: Option<u32>,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct OpenFloatBounds {
    pub lower: f64,
    pub upper: Option<f64>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BandwidthEnvelopeReport {
    pub effective_aggregate_bytes_per_second: u64,
    pub traffic_bytes_per_output_token: ByteBounds,
    pub bandwidth_limited_output_tokens_per_second: OpenFloatBounds,
    pub traffic_evidence: EnvelopeEvidence,
    pub bandwidth_evidence: EnvelopeEvidence,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EndToEndClaimBlocker {
    MissingMeasuredServingEvidence,
    RouteTrafficIsNotMeasured,
    MemoryBandwidthIsNotMeasured,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EndToEndClaimReport {
    pub end_to_end_latency_seconds_per_output_token: Option<FloatBounds>,
    pub cost_per_million_output_tokens_usd: Option<FloatBounds>,
    pub measured_output_tokens_per_second: Option<FloatBounds>,
    pub source_artifact_id: Option<String>,
    pub blockers: Vec<EndToEndClaimBlocker>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BreakEvenDeploymentReport {
    pub required_billable_tokens_per_second_for_deployment: f64,
    pub required_billable_tokens_per_second_at_minimum_residency: FloatBounds,
    pub assumption: BreakEvenThroughputAssumption,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HardwareVariantEnvelopeReport {
    pub hardware_id: String,
    pub deployment_device_count: u32,
    pub usable_memory_bytes_per_device: u64,
    pub minimum_devices_for_checkpoint_payload: u32,
    pub minimum_devices_for_total_residency: CountBounds,
    pub deployment_capacity_status: DeploymentCapacityStatus,
    pub minimum_hourly_cost_usd: FloatBounds,
    pub deployment_hourly_cost_usd: f64,
    pub expert_placement: ExpertPlacementReport,
    pub bandwidth: Option<BandwidthEnvelopeReport>,
    pub claims: EndToEndClaimReport,
    pub break_even: Option<BreakEvenDeploymentReport>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmVariantEnvelopeReport {
    pub variant_id: String,
    pub checkpoint: CheckpointPayloadEvidence,
    pub routed_experts: RoutedExpertLedger,
    pub active_traffic: Option<ActiveTrafficEnvelopeReport>,
    pub residency: ResidencyLedger,
    pub hardware: Vec<HardwareVariantEnvelopeReport>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmStorageEnvelopeResult {
    pub study_id: String,
    pub model_id: String,
    pub model_revision: String,
    pub semantic_mla_cache_bytes_per_token: u64,
    pub routed_expert_parameter_count: u64,
    pub active_routed_expert_parameter_count_per_token: u64,
    pub routed_expert_layer_instance_count: u64,
    pub active_routed_expert_layer_instances_per_token: u64,
    pub residency_assumptions: MemoryResidencyAssumptions,
    pub variants: Vec<GlmVariantEnvelopeReport>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmStorageEnvelopeReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: GlmStorageEnvelopeResult,
}

impl GlmStorageEnvelopeReport {
    pub fn verify_content_id(&self) -> Result<bool, GlmStorageEnvelopeError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

struct ValidatedModel<'a> {
    model: &'a ModelSpec,
    semantic_cache_bytes_per_token: u64,
    routed_parameter_count: u64,
    active_routed_parameter_count: u64,
    routed_expert_layer_instances: u64,
    active_routed_expert_layer_instances: u64,
    parameters_per_layer_expert: u64,
}

pub fn evaluate_glm_storage_envelope(
    request: &GlmStorageEnvelopeRequest,
) -> Result<GlmStorageEnvelopeReport, GlmStorageEnvelopeError> {
    let validated = validate_request(request)?;
    let serving_evidence = request
        .measured_serving_evidence
        .iter()
        .map(|evidence| {
            (
                (evidence.variant_id.as_str(), evidence.hardware_id.as_str()),
                evidence,
            )
        })
        .collect::<BTreeMap<_, _>>();
    let variants = request
        .variants
        .iter()
        .map(|variant| evaluate_variant(request, &validated, variant, &serving_evidence))
        .collect::<Result<Vec<_>, _>>()?;
    let result = GlmStorageEnvelopeResult {
        study_id: request.study_id.clone(),
        model_id: request.model.model_id.clone(),
        model_revision: request.model.model_revision.clone(),
        semantic_mla_cache_bytes_per_token: validated.semantic_cache_bytes_per_token,
        routed_expert_parameter_count: validated.routed_parameter_count,
        active_routed_expert_parameter_count_per_token: validated.active_routed_parameter_count,
        routed_expert_layer_instance_count: validated.routed_expert_layer_instances,
        active_routed_expert_layer_instances_per_token: validated
            .active_routed_expert_layer_instances,
        residency_assumptions: request.residency.clone(),
        variants,
    };
    let schema_version = GLM_STORAGE_ENVELOPE_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(GlmStorageEnvelopeReport {
        schema_version,
        content_id,
        result,
    })
}

fn validate_request(
    request: &GlmStorageEnvelopeRequest,
) -> Result<ValidatedModel<'_>, GlmStorageEnvelopeError> {
    if request.schema_version != GLM_STORAGE_ENVELOPE_REQUEST_SCHEMA_VERSION {
        return Err(GlmStorageEnvelopeError::UnsupportedSchemaVersion {
            expected: GLM_STORAGE_ENVELOPE_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    validate_required("study_id", &request.study_id)?;
    request
        .model
        .validate()
        .map_err(|_| GlmStorageEnvelopeError::InvalidModel)?;
    let ModelArchitecture::HybridMoeMlaDsa(hybrid) = request.model.architecture else {
        return Err(GlmStorageEnvelopeError::UnsupportedModelArchitecture);
    };
    let semantic_cache_bytes_per_token = request
        .model
        .semantic_kv_bytes_per_token()
        .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
    let routed_parameter_count = request
        .model
        .routed_expert_parameter_count()
        .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
    let active_routed_parameter_count = request
        .model
        .active_routed_expert_parameter_count()
        .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
    let routed_expert_layer_instances = u64::from(hybrid.moe_layer_count)
        .checked_mul(u64::from(hybrid.moe.routed_expert_count))
        .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
    let active_routed_expert_layer_instances = u64::from(hybrid.moe_layer_count)
        .checked_mul(u64::from(hybrid.moe.routed_experts_per_token))
        .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
    let parameters_per_layer_expert = routed_parameter_count
        .checked_div(routed_expert_layer_instances)
        .filter(|_| routed_parameter_count % routed_expert_layer_instances == 0)
        .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
    validate_residency(&request.residency)?;
    if request.variants.is_empty() {
        return Err(GlmStorageEnvelopeError::InvalidField("variants"));
    }
    let mut variant_ids = BTreeSet::new();
    for variant in &request.variants {
        if !variant_ids.insert(variant.variant_id.as_str()) {
            return Err(GlmStorageEnvelopeError::DuplicateVariant(
                variant.variant_id.clone(),
            ));
        }
        validate_variant(request, variant, routed_parameter_count)?;
    }
    if request.hardware.is_empty() {
        return Err(GlmStorageEnvelopeError::InvalidField("hardware"));
    }
    let mut hardware_ids = BTreeSet::new();
    for hardware in &request.hardware {
        if !hardware_ids.insert(hardware.hardware_id.as_str()) {
            return Err(GlmStorageEnvelopeError::DuplicateHardware(
                hardware.hardware_id.clone(),
            ));
        }
        validate_hardware(hardware)?;
    }
    if let Some(break_even) = &request.break_even {
        validate_required(
            "break_even.source_artifact_id",
            &break_even.source_artifact_id,
        )?;
        if !break_even
            .required_billable_tokens_per_second_per_usd_of_hourly_system_cost
            .is_finite()
            || break_even.required_billable_tokens_per_second_per_usd_of_hourly_system_cost <= 0.0
        {
            return Err(GlmStorageEnvelopeError::InvalidField(
                "break_even.required_billable_tokens_per_second_per_usd_of_hourly_system_cost",
            ));
        }
    }
    validate_measured_serving_evidence(request)?;
    Ok(ValidatedModel {
        model: &request.model,
        semantic_cache_bytes_per_token,
        routed_parameter_count,
        active_routed_parameter_count,
        routed_expert_layer_instances,
        active_routed_expert_layer_instances,
        parameters_per_layer_expert,
    })
}

fn validate_residency(
    residency: &MemoryResidencyAssumptions,
) -> Result<(), GlmStorageEnvelopeError> {
    if residency.checkpoint_replication_factor == 0
        || residency.concurrent_sequences == 0
        || residency.reserved_tokens_per_sequence == 0
        || residency.cache_replication_factor == 0
        || residency.fragmentation_overhead_basis_points > 10_000
    {
        return Err(GlmStorageEnvelopeError::InvalidField("residency"));
    }
    validate_required(
        "residency.source_artifact_id",
        &residency.source_artifact_id,
    )?;
    validate_required("residency.basis", &residency.basis)?;
    residency
        .extra_cache_bytes_per_token
        .validate("residency.extra_cache_bytes_per_token")?;
    residency
        .indexer_cache_bytes_per_token
        .validate("residency.indexer_cache_bytes_per_token")
}

fn validate_variant(
    request: &GlmStorageEnvelopeRequest,
    variant: &GlmCheckpointVariant,
    routed_parameter_count: u64,
) -> Result<(), GlmStorageEnvelopeError> {
    validate_required("variants.variant_id", &variant.variant_id)?;
    for (field, value) in [
        (
            "variants.checkpoint.model_id",
            variant.checkpoint.model_id.as_str(),
        ),
        (
            "variants.checkpoint.checkpoint_revision",
            variant.checkpoint.checkpoint_revision.as_str(),
        ),
        (
            "variants.checkpoint.source_artifact_id",
            variant.checkpoint.source_artifact_id.as_str(),
        ),
    ] {
        validate_required(field, value)?;
    }
    if variant.checkpoint.payload_bytes == 0 {
        return Err(GlmStorageEnvelopeError::InvalidField(
            "variants.checkpoint.payload_bytes",
        ));
    }
    match &variant.routed_expert_storage {
        RoutedExpertStorageEvidence::ModelSpecExact { source_artifact_id } => {
            validate_required(
                "variants.routed_expert_storage.source_artifact_id",
                source_artifact_id,
            )?;
            if variant.checkpoint.model_id != request.model.model_id
                || variant.checkpoint.checkpoint_revision != request.model.model_revision
                || request.model.weight_bytes() != Some(variant.checkpoint.payload_bytes)
            {
                return Err(GlmStorageEnvelopeError::ModelSpecPayloadMismatch(
                    variant.variant_id.clone(),
                ));
            }
            let ModelArchitecture::HybridMoeMlaDsa(hybrid) = request.model.architecture else {
                return Err(GlmStorageEnvelopeError::UnsupportedModelArchitecture);
            };
            if hybrid.moe.routed_expert_quantized_weight_storage.is_some() {
                return Err(GlmStorageEnvelopeError::OpaqueExpertLayoutRequired(
                    variant.variant_id.clone(),
                ));
            }
            let routed_bytes = stored_weight_bytes(
                routed_parameter_count,
                hybrid.moe.routed_expert_weight_precision,
                None,
            )
            .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
            if routed_bytes > variant.checkpoint.payload_bytes {
                return Err(GlmStorageEnvelopeError::ExpertStorageExceedsPayload(
                    variant.variant_id.clone(),
                ));
            }
        }
        RoutedExpertStorageEvidence::OpaqueAggregateBounds {
            bytes,
            source_artifact_id,
            lower_bound_basis,
            upper_bound_basis,
        } => {
            bytes.validate("variants.routed_expert_storage.bytes")?;
            for (field, value) in [
                (
                    "variants.routed_expert_storage.source_artifact_id",
                    source_artifact_id.as_str(),
                ),
                (
                    "variants.routed_expert_storage.lower_bound_basis",
                    lower_bound_basis.as_str(),
                ),
                (
                    "variants.routed_expert_storage.upper_bound_basis",
                    upper_bound_basis.as_str(),
                ),
            ] {
                validate_required(field, value)?;
            }
            if bytes.upper > variant.checkpoint.payload_bytes {
                return Err(GlmStorageEnvelopeError::ExpertStorageExceedsPayload(
                    variant.variant_id.clone(),
                ));
            }
        }
    }
    if let Some(traffic) = &variant.active_traffic {
        traffic
            .routed_expert_weight_bytes_per_output_token
            .validate("variants.active_traffic.routed_expert_weight_bytes_per_output_token")?;
        traffic
            .non_routed_weight_bytes_per_output_token
            .validate("variants.active_traffic.non_routed_weight_bytes_per_output_token")?;
        traffic
            .indexer_bytes_per_output_token
            .validate("variants.active_traffic.indexer_bytes_per_output_token")?;
        validate_evidence("variants.active_traffic.evidence", &traffic.evidence)?;
        validate_required("variants.active_traffic.basis", &traffic.basis)?;
        let total = traffic
            .routed_expert_weight_bytes_per_output_token
            .checked_add(traffic.non_routed_weight_bytes_per_output_token)?
            .checked_add(traffic.indexer_bytes_per_output_token)?;
        if total.upper == 0 {
            return Err(GlmStorageEnvelopeError::InvalidField(
                "variants.active_traffic",
            ));
        }
    }
    Ok(())
}

fn validate_hardware(hardware: &HardwareEnvelopeAssumption) -> Result<(), GlmStorageEnvelopeError> {
    validate_required("hardware.hardware_id", &hardware.hardware_id)?;
    validate_required(
        "hardware.memory_source_artifact_id",
        &hardware.memory_source_artifact_id,
    )?;
    validate_required(
        "hardware.cost.source_artifact_id",
        &hardware.cost.source_artifact_id,
    )?;
    validate_evidence("hardware.bandwidth.evidence", &hardware.bandwidth.evidence)?;
    if hardware.deployment_device_count == 0
        || hardware.device_memory_bytes == 0
        || hardware.reserved_device_memory_bytes >= hardware.device_memory_bytes
        || hardware.bandwidth.peak_bytes_per_second_per_device == 0
        || hardware.bandwidth.efficiency_basis_points == 0
        || hardware.bandwidth.efficiency_basis_points > 10_000
        || !hardware.cost.usd_per_device_hour.is_finite()
        || hardware.cost.usd_per_device_hour <= 0.0
    {
        return Err(GlmStorageEnvelopeError::InvalidField("hardware"));
    }
    Ok(())
}

fn validate_measured_serving_evidence(
    request: &GlmStorageEnvelopeRequest,
) -> Result<(), GlmStorageEnvelopeError> {
    let variants = request
        .variants
        .iter()
        .map(|variant| (variant.variant_id.as_str(), variant))
        .collect::<BTreeMap<_, _>>();
    let hardware = request
        .hardware
        .iter()
        .map(|hardware| (hardware.hardware_id.as_str(), hardware))
        .collect::<BTreeMap<_, _>>();
    let mut pairs = BTreeSet::new();
    for evidence in &request.measured_serving_evidence {
        let pair = (evidence.variant_id.as_str(), evidence.hardware_id.as_str());
        if !pairs.insert(pair) {
            return Err(GlmStorageEnvelopeError::DuplicateServingEvidence {
                variant_id: evidence.variant_id.clone(),
                hardware_id: evidence.hardware_id.clone(),
            });
        }
        let variant = variants.get(evidence.variant_id.as_str()).ok_or_else(|| {
            GlmStorageEnvelopeError::UnknownServingEvidenceVariant(evidence.variant_id.clone())
        })?;
        let hardware = hardware.get(evidence.hardware_id.as_str()).ok_or_else(|| {
            GlmStorageEnvelopeError::UnknownServingEvidenceHardware(evidence.hardware_id.clone())
        })?;
        evidence
            .output_tokens_per_second
            .validate_positive("measured_serving_evidence.output_tokens_per_second")?;
        evidence
            .end_to_end_latency_seconds_per_output_token
            .validate_positive(
                "measured_serving_evidence.end_to_end_latency_seconds_per_output_token",
            )?;
        for (field, value) in [
            (
                "measured_serving_evidence.source_artifact_id",
                evidence.source_artifact_id.as_str(),
            ),
            (
                "measured_serving_evidence.route_traffic_source_artifact_id",
                evidence.route_traffic_source_artifact_id.as_str(),
            ),
            (
                "measured_serving_evidence.bandwidth_source_artifact_id",
                evidence.bandwidth_source_artifact_id.as_str(),
            ),
        ] {
            validate_required(field, value)?;
        }
        let traffic = variant.active_traffic.as_ref().ok_or_else(|| {
            GlmStorageEnvelopeError::ServingEvidenceMissingRouteTraffic(evidence.variant_id.clone())
        })?;
        if traffic.evidence.kind != EnvelopeEvidenceKind::MeasuredHardware
            || traffic.evidence.source_artifact_id != evidence.route_traffic_source_artifact_id
        {
            return Err(GlmStorageEnvelopeError::ServingEvidenceRouteMismatch(
                evidence.variant_id.clone(),
            ));
        }
        if hardware.bandwidth.evidence.kind != EnvelopeEvidenceKind::MeasuredHardware
            || hardware.bandwidth.evidence.source_artifact_id
                != evidence.bandwidth_source_artifact_id
        {
            return Err(GlmStorageEnvelopeError::ServingEvidenceBandwidthMismatch(
                evidence.hardware_id.clone(),
            ));
        }
    }
    Ok(())
}

fn evaluate_variant(
    request: &GlmStorageEnvelopeRequest,
    model: &ValidatedModel<'_>,
    variant: &GlmCheckpointVariant,
    serving_evidence: &BTreeMap<(&str, &str), &MeasuredServingClaimEvidence>,
) -> Result<GlmVariantEnvelopeReport, GlmStorageEnvelopeError> {
    let routed_experts = routed_expert_ledger(model, variant)?;
    let active_traffic = variant
        .active_traffic
        .as_ref()
        .map(active_traffic_report)
        .transpose()?;
    let residency = residency_ledger(
        variant.checkpoint.payload_bytes,
        model.semantic_cache_bytes_per_token,
        &request.residency,
    )?;
    let hardware = request
        .hardware
        .iter()
        .map(|hardware| {
            evaluate_hardware(
                request,
                model,
                variant,
                &routed_experts,
                active_traffic.as_ref(),
                &residency,
                hardware,
                serving_evidence
                    .get(&(variant.variant_id.as_str(), hardware.hardware_id.as_str()))
                    .copied(),
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    Ok(GlmVariantEnvelopeReport {
        variant_id: variant.variant_id.clone(),
        checkpoint: variant.checkpoint.clone(),
        routed_experts,
        active_traffic,
        residency,
        hardware,
    })
}

fn routed_expert_ledger(
    model: &ValidatedModel<'_>,
    variant: &GlmCheckpointVariant,
) -> Result<RoutedExpertLedger, GlmStorageEnvelopeError> {
    let (resident_storage_bytes, per_layer_expert_storage_bytes, active_storage_footprint) =
        match &variant.routed_expert_storage {
            RoutedExpertStorageEvidence::ModelSpecExact { .. } => {
                let ModelArchitecture::HybridMoeMlaDsa(hybrid) = model.model.architecture else {
                    return Err(GlmStorageEnvelopeError::UnsupportedModelArchitecture);
                };
                let resident = stored_weight_bytes(
                    model.routed_parameter_count,
                    hybrid.moe.routed_expert_weight_precision,
                    None,
                )
                .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
                let per_layer = stored_weight_bytes(
                    model.parameters_per_layer_expert,
                    hybrid.moe.routed_expert_weight_precision,
                    None,
                )
                .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
                let active = per_layer
                    .checked_mul(model.active_routed_expert_layer_instances)
                    .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
                (
                    ByteBounds::exact(resident),
                    Some(ByteBounds::exact(per_layer)),
                    Some(ByteBounds::exact(active)),
                )
            }
            RoutedExpertStorageEvidence::OpaqueAggregateBounds { bytes, .. } => {
                (*bytes, None, None)
            }
        };
    Ok(RoutedExpertLedger {
        resident_parameter_count: model.routed_parameter_count,
        active_parameter_count_per_token: model.active_routed_parameter_count,
        resident_storage_bytes,
        per_layer_expert_storage_bytes,
        active_storage_footprint_bytes_per_token: active_storage_footprint,
        storage_evidence: variant.routed_expert_storage.clone(),
    })
}

fn active_traffic_report(
    traffic: &ActiveTrafficEnvelope,
) -> Result<ActiveTrafficEnvelopeReport, GlmStorageEnvelopeError> {
    let total = traffic
        .routed_expert_weight_bytes_per_output_token
        .checked_add(traffic.non_routed_weight_bytes_per_output_token)?
        .checked_add(traffic.indexer_bytes_per_output_token)?;
    Ok(ActiveTrafficEnvelopeReport {
        routed_expert_weight_bytes_per_output_token: traffic
            .routed_expert_weight_bytes_per_output_token,
        non_routed_weight_bytes_per_output_token: traffic.non_routed_weight_bytes_per_output_token,
        indexer_bytes_per_output_token: traffic.indexer_bytes_per_output_token,
        total_bytes_per_output_token: total,
        evidence: traffic.evidence.clone(),
        basis: traffic.basis.clone(),
    })
}

fn residency_ledger(
    checkpoint_payload_bytes: u64,
    semantic_cache_bytes_per_token: u64,
    assumptions: &MemoryResidencyAssumptions,
) -> Result<ResidencyLedger, GlmStorageEnvelopeError> {
    let checkpoint_resident_bytes = checkpoint_payload_bytes
        .checked_mul(u64::from(assumptions.checkpoint_replication_factor))
        .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
    let reserved_token_slots = u64::from(assumptions.concurrent_sequences)
        .checked_mul(u64::from(assumptions.reserved_tokens_per_sequence))
        .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
    let replicated_token_slots = reserved_token_slots
        .checked_mul(u64::from(assumptions.cache_replication_factor))
        .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
    let semantic_mla_cache_bytes = semantic_cache_bytes_per_token
        .checked_mul(replicated_token_slots)
        .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
    let extra_cache_bytes = assumptions
        .extra_cache_bytes_per_token
        .checked_mul(replicated_token_slots)?;
    let indexer_cache_bytes = assumptions
        .indexer_cache_bytes_per_token
        .checked_mul(replicated_token_slots)?;
    let fixed = ByteBounds::exact(
        checkpoint_resident_bytes
            .checked_add(semantic_mla_cache_bytes)
            .and_then(|bytes| bytes.checked_add(assumptions.fixed_runtime_bytes))
            .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?,
    );
    let unfragmented_resident_bytes = fixed
        .checked_add(extra_cache_bytes)?
        .checked_add(indexer_cache_bytes)?;
    let fragmentation_overhead_bytes = ByteBounds {
        lower: basis_point_overhead(
            unfragmented_resident_bytes.lower,
            assumptions.fragmentation_overhead_basis_points,
        )?,
        upper: basis_point_overhead(
            unfragmented_resident_bytes.upper,
            assumptions.fragmentation_overhead_basis_points,
        )?,
    };
    let total_resident_bytes =
        unfragmented_resident_bytes.checked_add(fragmentation_overhead_bytes)?;
    Ok(ResidencyLedger {
        checkpoint_payload_bytes,
        checkpoint_resident_bytes,
        reserved_token_slots,
        semantic_mla_cache_bytes,
        extra_cache_bytes,
        indexer_cache_bytes,
        fixed_runtime_bytes: assumptions.fixed_runtime_bytes,
        unfragmented_resident_bytes,
        fragmentation_overhead_bytes,
        total_resident_bytes,
    })
}

#[allow(clippy::too_many_arguments)]
fn evaluate_hardware(
    request: &GlmStorageEnvelopeRequest,
    model: &ValidatedModel<'_>,
    variant: &GlmCheckpointVariant,
    routed_experts: &RoutedExpertLedger,
    active_traffic: Option<&ActiveTrafficEnvelopeReport>,
    residency: &ResidencyLedger,
    hardware: &HardwareEnvelopeAssumption,
    serving_evidence: Option<&MeasuredServingClaimEvidence>,
) -> Result<HardwareVariantEnvelopeReport, GlmStorageEnvelopeError> {
    let usable = hardware
        .device_memory_bytes
        .checked_sub(hardware.reserved_device_memory_bytes)
        .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
    let minimum_devices_for_checkpoint_payload =
        required_devices(residency.checkpoint_resident_bytes, usable)?;
    let minimum_devices_for_total_residency =
        required_device_bounds(residency.total_resident_bytes, usable)?;
    let deployment_capacity_status =
        if hardware.deployment_device_count < minimum_devices_for_total_residency.lower {
            DeploymentCapacityStatus::Infeasible
        } else if hardware.deployment_device_count >= minimum_devices_for_total_residency.upper {
            DeploymentCapacityStatus::Feasible
        } else {
            DeploymentCapacityStatus::Uncertain
        };
    let minimum_hourly_cost_usd = FloatBounds {
        lower: f64::from(minimum_devices_for_total_residency.lower)
            * hardware.cost.usd_per_device_hour,
        upper: f64::from(minimum_devices_for_total_residency.upper)
            * hardware.cost.usd_per_device_hour,
    };
    let deployment_hourly_cost_usd =
        f64::from(hardware.deployment_device_count) * hardware.cost.usd_per_device_hour;
    let expert_placement = expert_placement(model, routed_experts, usable)?;
    let bandwidth = active_traffic
        .map(|traffic| bandwidth_envelope(hardware, traffic))
        .transpose()?;
    let claims = end_to_end_claims(
        variant,
        hardware,
        active_traffic,
        serving_evidence,
        deployment_hourly_cost_usd,
    )?;
    let break_even = request.break_even.as_ref().map(|assumption| {
        let rate = assumption.required_billable_tokens_per_second_per_usd_of_hourly_system_cost;
        BreakEvenDeploymentReport {
            required_billable_tokens_per_second_for_deployment: deployment_hourly_cost_usd * rate,
            required_billable_tokens_per_second_at_minimum_residency: FloatBounds {
                lower: minimum_hourly_cost_usd.lower * rate,
                upper: minimum_hourly_cost_usd.upper * rate,
            },
            assumption: assumption.clone(),
        }
    });
    Ok(HardwareVariantEnvelopeReport {
        hardware_id: hardware.hardware_id.clone(),
        deployment_device_count: hardware.deployment_device_count,
        usable_memory_bytes_per_device: usable,
        minimum_devices_for_checkpoint_payload,
        minimum_devices_for_total_residency,
        deployment_capacity_status,
        minimum_hourly_cost_usd,
        deployment_hourly_cost_usd,
        expert_placement,
        bandwidth,
        claims,
        break_even,
    })
}

fn expert_placement(
    model: &ValidatedModel<'_>,
    routed_experts: &RoutedExpertLedger,
    usable_bytes_per_device: u64,
) -> Result<ExpertPlacementReport, GlmStorageEnvelopeError> {
    let minimum_devices_for_routed_expert_storage = required_device_bounds(
        routed_experts.resident_storage_bytes,
        usable_bytes_per_device,
    )?;
    let (uniform_layer_expert_slots_per_device, minimum_devices_for_uniform_layer_experts) =
        if let Some(per_expert) = routed_experts.per_layer_expert_storage_bytes {
            if per_expert.lower != per_expert.upper || per_expert.lower == 0 {
                return Err(GlmStorageEnvelopeError::ArithmeticOverflow);
            }
            let slots = usable_bytes_per_device / per_expert.lower;
            if slots == 0 {
                (Some(0), None)
            } else {
                (
                    Some(slots),
                    Some(required_devices(
                        model.routed_expert_layer_instances,
                        slots,
                    )?),
                )
            }
        } else {
            (None, None)
        };
    Ok(ExpertPlacementReport {
        minimum_devices_for_routed_expert_storage,
        uniform_layer_expert_slots_per_device,
        minimum_devices_for_uniform_layer_experts,
    })
}

fn bandwidth_envelope(
    hardware: &HardwareEnvelopeAssumption,
    traffic: &ActiveTrafficEnvelopeReport,
) -> Result<BandwidthEnvelopeReport, GlmStorageEnvelopeError> {
    let effective_aggregate_bytes_per_second = checked_scaled_basis_points(
        hardware
            .bandwidth
            .peak_bytes_per_second_per_device
            .checked_mul(u64::from(hardware.deployment_device_count))
            .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?,
        hardware.bandwidth.efficiency_basis_points,
    )?;
    let bandwidth_limited_output_tokens_per_second = OpenFloatBounds {
        lower: effective_aggregate_bytes_per_second as f64
            / traffic.total_bytes_per_output_token.upper as f64,
        upper: (traffic.total_bytes_per_output_token.lower > 0).then(|| {
            effective_aggregate_bytes_per_second as f64
                / traffic.total_bytes_per_output_token.lower as f64
        }),
    };
    Ok(BandwidthEnvelopeReport {
        effective_aggregate_bytes_per_second,
        traffic_bytes_per_output_token: traffic.total_bytes_per_output_token,
        bandwidth_limited_output_tokens_per_second,
        traffic_evidence: traffic.evidence.clone(),
        bandwidth_evidence: hardware.bandwidth.evidence.clone(),
    })
}

fn end_to_end_claims(
    variant: &GlmCheckpointVariant,
    hardware: &HardwareEnvelopeAssumption,
    active_traffic: Option<&ActiveTrafficEnvelopeReport>,
    serving_evidence: Option<&MeasuredServingClaimEvidence>,
    deployment_hourly_cost_usd: f64,
) -> Result<EndToEndClaimReport, GlmStorageEnvelopeError> {
    if let Some(evidence) = serving_evidence {
        let cost = FloatBounds {
            lower: deployment_hourly_cost_usd * 1_000_000.0
                / (3_600.0 * evidence.output_tokens_per_second.upper),
            upper: deployment_hourly_cost_usd * 1_000_000.0
                / (3_600.0 * evidence.output_tokens_per_second.lower),
        };
        return Ok(EndToEndClaimReport {
            end_to_end_latency_seconds_per_output_token: Some(
                evidence.end_to_end_latency_seconds_per_output_token,
            ),
            cost_per_million_output_tokens_usd: Some(cost),
            measured_output_tokens_per_second: Some(evidence.output_tokens_per_second),
            source_artifact_id: Some(evidence.source_artifact_id.clone()),
            blockers: Vec::new(),
        });
    }
    let mut blockers = vec![EndToEndClaimBlocker::MissingMeasuredServingEvidence];
    if active_traffic
        .is_none_or(|traffic| traffic.evidence.kind != EnvelopeEvidenceKind::MeasuredHardware)
    {
        blockers.push(EndToEndClaimBlocker::RouteTrafficIsNotMeasured);
    }
    if hardware.bandwidth.evidence.kind != EnvelopeEvidenceKind::MeasuredHardware {
        blockers.push(EndToEndClaimBlocker::MemoryBandwidthIsNotMeasured);
    }
    let _ = variant;
    Ok(EndToEndClaimReport {
        end_to_end_latency_seconds_per_output_token: None,
        cost_per_million_output_tokens_usd: None,
        measured_output_tokens_per_second: None,
        source_artifact_id: None,
        blockers,
    })
}

fn required_device_bounds(
    bytes: ByteBounds,
    usable_bytes_per_device: u64,
) -> Result<CountBounds, GlmStorageEnvelopeError> {
    Ok(CountBounds {
        lower: required_devices(bytes.lower, usable_bytes_per_device)?,
        upper: required_devices(bytes.upper, usable_bytes_per_device)?,
    })
}

fn required_devices(
    required: u64,
    capacity_per_device: u64,
) -> Result<u32, GlmStorageEnvelopeError> {
    if capacity_per_device == 0 {
        return Err(GlmStorageEnvelopeError::ArithmeticOverflow);
    }
    let devices = required.div_ceil(capacity_per_device);
    u32::try_from(devices).map_err(|_| GlmStorageEnvelopeError::ArithmeticOverflow)
}

fn basis_point_overhead(bytes: u64, basis_points: u32) -> Result<u64, GlmStorageEnvelopeError> {
    let numerator = u128::from(bytes)
        .checked_mul(u128::from(basis_points))
        .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?;
    u64::try_from(numerator.div_ceil(10_000))
        .map_err(|_| GlmStorageEnvelopeError::ArithmeticOverflow)
}

fn checked_scaled_basis_points(
    value: u64,
    basis_points: u32,
) -> Result<u64, GlmStorageEnvelopeError> {
    let scaled = u128::from(value)
        .checked_mul(u128::from(basis_points))
        .ok_or(GlmStorageEnvelopeError::ArithmeticOverflow)?
        / 10_000;
    u64::try_from(scaled).map_err(|_| GlmStorageEnvelopeError::ArithmeticOverflow)
}

fn validate_evidence(
    field: &'static str,
    evidence: &EnvelopeEvidence,
) -> Result<(), GlmStorageEnvelopeError> {
    validate_required(field, &evidence.source_artifact_id)
}

fn validate_required(field: &'static str, value: &str) -> Result<(), GlmStorageEnvelopeError> {
    if value.trim().is_empty() {
        Err(GlmStorageEnvelopeError::InvalidField(field))
    } else {
        Ok(())
    }
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a GlmStorageEnvelopeResult,
}

fn report_content_id(
    schema_version: u32,
    result: &GlmStorageEnvelopeResult,
) -> Result<String, GlmStorageEnvelopeError> {
    let bytes = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|error| GlmStorageEnvelopeError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum GlmStorageEnvelopeError {
    #[error("unsupported GLM storage envelope schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid GLM storage envelope field {0}")]
    InvalidField(&'static str),
    #[error("the model specification is invalid")]
    InvalidModel,
    #[error("GLM storage envelopes require a hybrid MoE/MLA/DSA model")]
    UnsupportedModelArchitecture,
    #[error("duplicate checkpoint variant {0}")]
    DuplicateVariant(String),
    #[error("duplicate hardware assumption {0}")]
    DuplicateHardware(String),
    #[error("variant {0} exact model storage does not match its pinned checkpoint payload")]
    ModelSpecPayloadMismatch(String),
    #[error("variant {0} requires opaque expert storage evidence")]
    OpaqueExpertLayoutRequired(String),
    #[error("variant {0} routed-expert storage exceeds its exact checkpoint payload")]
    ExpertStorageExceedsPayload(String),
    #[error("duplicate measured serving evidence for {variant_id} on {hardware_id}")]
    DuplicateServingEvidence {
        variant_id: String,
        hardware_id: String,
    },
    #[error("measured serving evidence references unknown variant {0}")]
    UnknownServingEvidenceVariant(String),
    #[error("measured serving evidence references unknown hardware {0}")]
    UnknownServingEvidenceHardware(String),
    #[error("measured serving evidence for {0} has no route-traffic evidence")]
    ServingEvidenceMissingRouteTraffic(String),
    #[error("measured serving evidence route pin differs for variant {0}")]
    ServingEvidenceRouteMismatch(String),
    #[error("measured serving evidence bandwidth pin differs for hardware {0}")]
    ServingEvidenceBandwidthMismatch(String),
    #[error("GLM storage envelope arithmetic overflowed")]
    ArithmeticOverflow,
    #[error("GLM storage envelope serialization failed: {0}")]
    Serialization(String),
}
