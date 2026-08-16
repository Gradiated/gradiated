use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::action_ledger::{
    ACTION_LEDGER_SCHEMA_VERSION, Action, ActionId, ActionLedger, ActionWork, Bytes, CacheAction,
    CacheKeySpace, CacheOperation, CollectiveKind, ComputeAction, ComputeClass, EvidenceKind,
    EvidenceProvenance, Flops, InferencePhase, LedgerError, LedgerProvenance, MemoryAction,
    MemoryPayload, MemoryTier, Messages, ModelProvenance, NetworkAction, NetworkPattern,
    Operations, PhaseProvenance, ProducerProvenance, SchedulerAction, SchedulerDecision,
    SynchronizationAction, SynchronizationKind,
};
use crate::glm_storage::{CheckpointPayloadEvidence, RoutedExpertStorageEvidence};
use crate::spec::{
    ActiveParameterCount, ModelArchitecture, ModelSpec, Precision, stored_weight_bytes,
};

pub const GLM_DECODE_LOWERING_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const GLM_DECODE_LOWERING_REPORT_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct OpenU64Bounds {
    pub lower: u64,
    pub upper: Option<u64>,
}

impl OpenU64Bounds {
    pub const fn closed(lower: u64, upper: u64) -> Self {
        Self {
            lower,
            upper: Some(upper),
        }
    }

    pub const fn exact(value: u64) -> Self {
        Self::closed(value, value)
    }

    fn validate(self, field: &'static str) -> Result<(), GlmDecodeLoweringError> {
        if self.upper.is_some_and(|upper| upper < self.lower) {
            Err(GlmDecodeLoweringError::InvalidField(field))
        } else {
            Ok(())
        }
    }

    fn checked_add(self, other: Self) -> Result<Self, GlmDecodeLoweringError> {
        Ok(Self {
            lower: self
                .lower
                .checked_add(other.lower)
                .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?,
            upper: match (self.upper, other.upper) {
                (Some(left), Some(right)) => Some(
                    left.checked_add(right)
                        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?,
                ),
                _ => None,
            },
        })
    }

    fn checked_mul(self, multiplier: u64) -> Result<Self, GlmDecodeLoweringError> {
        Ok(Self {
            lower: self
                .lower
                .checked_mul(multiplier)
                .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?,
            upper: self
                .upper
                .map(|upper| {
                    upper
                        .checked_mul(multiplier)
                        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)
                })
                .transpose()?,
        })
    }

    fn select(self, selection: BoundSelection) -> Option<u64> {
        match selection {
            BoundSelection::Lower => Some(self.lower),
            BoundSelection::Upper => self.upper,
        }
    }

    fn is_collapsed(self) -> bool {
        self.upper == Some(self.lower)
    }

    fn is_open(self) -> bool {
        self.upper.is_none()
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BoundSelection {
    Lower,
    Upper,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DecodeCheckpointVariant {
    pub variant_id: String,
    pub checkpoint: CheckpointPayloadEvidence,
    pub routed_expert_storage: RoutedExpertStorageEvidence,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DecodeTokenCountScope {
    AggregateAcrossBatch,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DecodeWorkload {
    pub batch_size: u32,
    pub context_tokens_per_request: u64,
    pub candidate_tokens: u64,
    pub committed_tokens: u64,
    pub token_count_scope: DecodeTokenCountScope,
    pub evidence_source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExplicitRouteAggregates {
    pub total_dispatches: u64,
    pub unique_routed_expert_instances: OpenU64Bounds,
    pub remote_dispatches: OpenU64Bounds,
    pub endpoint_payload_bytes: OpenU64Bounds,
    pub endpoint_message_count: OpenU64Bounds,
    pub network_hop_payload_bytes: OpenU64Bounds,
    pub network_hop_message_count: OpenU64Bounds,
    pub participants: u32,
    pub evidence: EvidenceProvenance,
    pub basis: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PinnedRouteReportSelection {
    pub report_content_id: String,
    pub scenario_id: String,
    pub topology_id: String,
    pub strategy_id: String,
    pub sample_total_dispatches: u64,
    pub sample_remote_dispatches: u64,
    pub sample_endpoint_payload_bytes: u64,
    pub sample_endpoint_message_count: u64,
    pub sample_network_hop_payload_bytes: u64,
    pub sample_network_hop_message_count: u64,
    pub unique_routed_expert_instances: OpenU64Bounds,
    pub participants: u32,
    pub evidence: EvidenceProvenance,
    pub basis: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(
    tag = "kind",
    content = "value",
    rename_all = "snake_case",
    deny_unknown_fields
)]
pub enum DecodeRouteInput {
    ExplicitAggregates(ExplicitRouteAggregates),
    PinnedRouteReportSelection(PinnedRouteReportSelection),
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BoundedDecodeWork {
    pub attention_flops: OpenU64Bounds,
    pub attention_non_flop_operations: OpenU64Bounds,
    pub attention_weight_bytes: OpenU64Bounds,
    pub activation_bytes: OpenU64Bounds,
    pub dsa_indexer_flops: OpenU64Bounds,
    pub dsa_indexer_weight_bytes: OpenU64Bounds,
    pub dsa_topk_non_flop_operations: OpenU64Bounds,
    pub other_non_ffn_flops: OpenU64Bounds,
    pub other_non_ffn_non_flop_operations: OpenU64Bounds,
    pub other_non_ffn_weight_bytes: OpenU64Bounds,
    pub evidence: EvidenceProvenance,
    pub basis: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum WeightCachePolicy {
    UniqueWeightsLoadedOncePerDecodeStep,
    NoWeightReuseAcrossCandidateTokens,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DecodeCacheState {
    pub semantic_kv_read_bytes: OpenU64Bounds,
    pub semantic_kv_write_bytes: OpenU64Bounds,
    pub dsa_index_lookup_bytes: OpenU64Bounds,
    pub dsa_index_store_bytes: OpenU64Bounds,
    pub dsa_index_lookup_hit: bool,
    pub weight_cache_policy: WeightCachePolicy,
    pub evidence: EvidenceProvenance,
    pub basis: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MtpDecodeWork {
    pub draft_tokens: u64,
    pub draft_flops: OpenU64Bounds,
    pub verification_flops: OpenU64Bounds,
    pub state_read_bytes: OpenU64Bounds,
    pub state_write_bytes: OpenU64Bounds,
    pub shares_dsa_indices: bool,
    pub synchronization_participants: u32,
    pub evidence: EvidenceProvenance,
    pub basis: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(
    tag = "kind",
    content = "value",
    rename_all = "snake_case",
    deny_unknown_fields
)]
pub enum MtpDecodeInput {
    Disabled(EvidenceProvenance),
    Enabled(MtpDecodeWork),
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmDecodeLoweringRequest {
    pub schema_version: u32,
    pub lowering_id: String,
    pub model: ModelSpec,
    pub checkpoint: DecodeCheckpointVariant,
    pub network_activation_precision: Precision,
    pub workload: DecodeWorkload,
    pub route: DecodeRouteInput,
    pub attention_dsa: BoundedDecodeWork,
    pub cache: DecodeCacheState,
    pub mtp: MtpDecodeInput,
    pub hardware_study_bound: BoundSelection,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ActiveParameterLedger {
    pub released_active_parameter_count: ActiveParameterCount,
    pub exact_whole_model_active_parameter_count: Option<u64>,
    pub exact_active_routed_expert_parameter_count_per_candidate_token: u64,
    pub exact_active_shared_and_dense_ffn_parameter_count_per_candidate_token: u64,
    pub exact_active_ffn_parameter_count_per_candidate_token: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RouteAggregateLedger {
    pub total_dispatches: u64,
    pub unique_routed_expert_instances: OpenU64Bounds,
    pub remote_dispatches: OpenU64Bounds,
    pub endpoint_payload_bytes: OpenU64Bounds,
    pub endpoint_message_count: OpenU64Bounds,
    pub network_hop_payload_bytes: OpenU64Bounds,
    pub network_hop_message_count: OpenU64Bounds,
    pub participants: u32,
    pub evidence: EvidenceProvenance,
    pub basis: String,
    pub route_report_selection: Option<RouteReportSelectionIdentity>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RouteReportSelectionIdentity {
    pub report_content_id: String,
    pub scenario_id: String,
    pub topology_id: String,
    pub strategy_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DecodeWeightLedger {
    pub checkpoint_payload_bytes: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub exact_routed_expert_resident_bytes: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub exact_shared_and_dense_ffn_resident_bytes: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub exact_ffn_resident_bytes: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub exact_non_ffn_resident_bytes: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub exact_dsa_indexer_resident_bytes: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub exact_active_routed_expert_weight_bytes_per_candidate_token: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub routed_expert_resident_byte_bounds: Option<OpenU64Bounds>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub average_routed_expert_storage_byte_bounds: Option<OpenU64Bounds>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub non_routed_resident_byte_bounds: Option<OpenU64Bounds>,
    pub routed_expert_hbm_read_bytes: OpenU64Bounds,
    pub shared_and_dense_ffn_hbm_read_bytes: OpenU64Bounds,
    pub total_ffn_hbm_read_bytes: OpenU64Bounds,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DecodeComputeLedger {
    pub exact_routed_expert_flops_per_candidate_token: u64,
    pub exact_shared_and_dense_ffn_flops_per_candidate_token: u64,
    pub exact_ffn_flops_per_candidate_token: u64,
    pub exact_routed_expert_flops: u64,
    pub exact_shared_and_dense_ffn_flops: u64,
    pub exact_ffn_flops: u64,
    pub attention_flops: OpenU64Bounds,
    pub dsa_indexer_flops: OpenU64Bounds,
    pub other_non_ffn_flops: OpenU64Bounds,
    pub mtp_flops: OpenU64Bounds,
    pub total_flops: OpenU64Bounds,
    pub non_flop_operations: OpenU64Bounds,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CompletenessBlocker {
    OpenWorkBounds,
    NonCollapsedWorkBounds,
    OpaqueCheckpointLayout,
    ApproximateWholeModelActiveParameters,
    MissingActionCalibration,
    LedgerContainsAssumptions,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DecodeCompletenessGate {
    pub work_bounds_collapsed: bool,
    pub all_actions_calibrated: bool,
    pub complete_hardware_timing_claim_permitted: bool,
    pub cost_per_token_claim_permitted: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub checkpoint_quality_claim_permitted: Option<bool>,
    pub blockers: Vec<CompletenessBlocker>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmDecodeLoweringResult {
    pub lowering_id: String,
    pub model_id: String,
    pub model_revision: String,
    pub checkpoint: DecodeCheckpointVariant,
    pub active_parameters: ActiveParameterLedger,
    pub route: RouteAggregateLedger,
    pub weights: DecodeWeightLedger,
    pub compute: DecodeComputeLedger,
    pub semantic_kv_resident_bytes: u64,
    pub lower_bound_ledger_content_id: String,
    pub upper_bound_ledger_content_id: Option<String>,
    pub lower_bound_ledger: ActionLedger,
    pub upper_bound_ledger: Option<ActionLedger>,
    pub hardware_study_bound: BoundSelection,
    pub hardware_study_ledger: Option<ActionLedger>,
    pub completeness: DecodeCompletenessGate,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmDecodeLoweringReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: GlmDecodeLoweringResult,
}

impl GlmDecodeLoweringReport {
    pub fn verify_content_id(&self) -> Result<bool, GlmDecodeLoweringError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

struct ValidatedModel {
    active_parameters: ActiveParameterLedger,
    routed_expert_instance_count: u64,
    weight_storage: ValidatedWeightStorage,
    routed_flops_per_token: u64,
    shared_dense_flops_per_token: u64,
    ffn_flops_per_token: u64,
    semantic_kv_bytes_per_token: u64,
}

enum ValidatedWeightStorage {
    Exact {
        per_layer_expert_storage_bytes: u64,
        routed_expert_resident_bytes: u64,
        shared_dense_resident_bytes: u64,
        ffn_resident_bytes: u64,
        non_ffn_resident_bytes: u64,
        dsa_indexer_resident_bytes: u64,
        active_routed_weight_bytes_per_token: u64,
    },
    Opaque {
        routed_expert_resident_byte_bounds: OpenU64Bounds,
        average_routed_expert_storage_byte_bounds: OpenU64Bounds,
        non_routed_resident_byte_bounds: OpenU64Bounds,
    },
}

enum ValidatedCheckpointLayout {
    Exact,
    Opaque {
        routed_expert_resident_byte_bounds: OpenU64Bounds,
    },
}

struct SelectedWork {
    attention_flops: u64,
    attention_non_flop_operations: u64,
    attention_weight_bytes: u64,
    activation_bytes: u64,
    dsa_indexer_flops: u64,
    dsa_indexer_weight_bytes: u64,
    dsa_topk_operations: u64,
    other_non_ffn_flops: u64,
    other_non_ffn_operations: u64,
    other_non_ffn_weight_bytes: u64,
    semantic_kv_read_bytes: u64,
    semantic_kv_write_bytes: u64,
    dsa_index_lookup_bytes: u64,
    dsa_index_store_bytes: u64,
    routed_weight_bytes: u64,
    shared_dense_weight_bytes: u64,
    opaque_ffn_weight_bytes: Option<u64>,
    network_bytes: u64,
    network_messages: u64,
    mtp_draft_flops: u64,
    mtp_verification_flops: u64,
    mtp_state_read_bytes: u64,
    mtp_state_write_bytes: u64,
}

pub fn evaluate_glm_decode_lowering(
    request: &GlmDecodeLoweringRequest,
) -> Result<GlmDecodeLoweringReport, GlmDecodeLoweringError> {
    let model = validate_request(request)?;
    let route = route_ledger(request, &model)?;
    let weights = weight_ledger(request, &model, &route)?;
    let compute = compute_ledger(request, &model)?;
    let semantic_kv_resident_bytes = model
        .semantic_kv_bytes_per_token
        .checked_mul(request.workload.context_tokens_per_request)
        .and_then(|bytes| bytes.checked_mul(u64::from(request.workload.batch_size)))
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let lower_bound_ledger =
        lower_ledger(request, &model, &route, &weights, BoundSelection::Lower)?
            .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let upper_bound_ledger =
        lower_ledger(request, &model, &route, &weights, BoundSelection::Upper)?;
    let lower_bound_ledger_content_id = lower_bound_ledger.content_id()?.as_str().to_owned();
    let upper_bound_ledger_content_id = upper_bound_ledger
        .as_ref()
        .map(ActionLedger::content_id)
        .transpose()?
        .map(|id| id.as_str().to_owned());
    let hardware_study_ledger = match request.hardware_study_bound {
        BoundSelection::Lower => Some(lower_bound_ledger.clone()),
        BoundSelection::Upper => upper_bound_ledger.clone(),
    };
    let completeness =
        completeness_gate(request, &route, &weights, &compute, &hardware_study_ledger);
    let result = GlmDecodeLoweringResult {
        lowering_id: request.lowering_id.clone(),
        model_id: request.model.model_id.clone(),
        model_revision: request.model.model_revision.clone(),
        checkpoint: request.checkpoint.clone(),
        active_parameters: model.active_parameters,
        route,
        weights,
        compute,
        semantic_kv_resident_bytes,
        lower_bound_ledger_content_id,
        upper_bound_ledger_content_id,
        lower_bound_ledger,
        upper_bound_ledger,
        hardware_study_bound: request.hardware_study_bound,
        hardware_study_ledger,
        completeness,
    };
    let schema_version = GLM_DECODE_LOWERING_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(GlmDecodeLoweringReport {
        schema_version,
        content_id,
        result,
    })
}

fn validate_request(
    request: &GlmDecodeLoweringRequest,
) -> Result<ValidatedModel, GlmDecodeLoweringError> {
    if request.schema_version != GLM_DECODE_LOWERING_REQUEST_SCHEMA_VERSION {
        return Err(GlmDecodeLoweringError::UnsupportedSchemaVersion {
            expected: GLM_DECODE_LOWERING_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    validate_required("lowering_id", &request.lowering_id)?;
    request
        .model
        .validate()
        .map_err(|_| GlmDecodeLoweringError::InvalidModel)?;
    let ModelArchitecture::HybridMoeMlaDsa(hybrid) = request.model.architecture else {
        return Err(GlmDecodeLoweringError::UnsupportedModelArchitecture);
    };
    if hybrid.moe_layer_count != 75
        || hybrid.moe.routed_expert_count != 256
        || hybrid.moe.routed_experts_per_token != 8
    {
        return Err(GlmDecodeLoweringError::UnsupportedGlmGeometry);
    }
    let ActiveParameterCount::Approximate { .. } = hybrid.active_parameter_count else {
        return Err(GlmDecodeLoweringError::ReleasedActiveCountMustRemainApproximate);
    };
    let checkpoint_layout = validate_checkpoint(request, &hybrid)?;
    validate_workload(&request.workload)?;
    validate_attention_dsa(&request.attention_dsa)?;
    validate_cache(&request.cache)?;
    validate_mtp(&request.mtp, hybrid.mtp.shares_dsa_indices)?;
    let routed_parameters = request
        .model
        .routed_expert_parameter_count()
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let active_routed_parameters = request
        .model
        .active_routed_expert_parameter_count()
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let shared_parameters = request
        .model
        .shared_expert_parameter_count()
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let dense_parameters = request
        .model
        .dense_mlp_parameter_count()
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let shared_dense_parameters = shared_parameters
        .checked_add(dense_parameters)
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let active_ffn_parameters = active_routed_parameters
        .checked_add(shared_dense_parameters)
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    if request
        .model
        .active_feed_forward_parameter_count_per_token()
        != Some(active_ffn_parameters)
    {
        return Err(GlmDecodeLoweringError::LedgerInvariantViolation);
    }
    let routed_expert_instance_count = u64::from(hybrid.moe_layer_count)
        .checked_mul(u64::from(hybrid.moe.routed_expert_count))
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let parameters_per_expert = routed_parameters
        .checked_div(routed_expert_instance_count)
        .filter(|_| routed_parameters % routed_expert_instance_count == 0)
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let weight_storage = match checkpoint_layout {
        ValidatedCheckpointLayout::Exact => {
            let per_layer_expert_storage_bytes = stored_weight_bytes(
                parameters_per_expert,
                hybrid.moe.routed_expert_weight_precision,
                None,
            )
            .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
            let routed_expert_resident_bytes = stored_weight_bytes(
                routed_parameters,
                hybrid.moe.routed_expert_weight_precision,
                None,
            )
            .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
            let shared_dense_resident_bytes = stored_weight_bytes(
                shared_dense_parameters,
                request.model.weight_precision,
                None,
            )
            .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
            let ffn_resident_bytes = routed_expert_resident_bytes
                .checked_add(shared_dense_resident_bytes)
                .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
            let non_ffn_resident_bytes = request
                .checkpoint
                .checkpoint
                .payload_bytes
                .checked_sub(ffn_resident_bytes)
                .ok_or(GlmDecodeLoweringError::LedgerInvariantViolation)?;
            let dsa_indexer_resident_bytes = stored_weight_bytes(
                request
                    .model
                    .dsa_indexer_parameter_count()
                    .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?,
                request.model.weight_precision,
                None,
            )
            .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
            if dsa_indexer_resident_bytes > non_ffn_resident_bytes {
                return Err(GlmDecodeLoweringError::LedgerInvariantViolation);
            }
            let active_routed_weight_bytes_per_token = stored_weight_bytes(
                active_routed_parameters,
                hybrid.moe.routed_expert_weight_precision,
                None,
            )
            .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
            ValidatedWeightStorage::Exact {
                per_layer_expert_storage_bytes,
                routed_expert_resident_bytes,
                shared_dense_resident_bytes,
                ffn_resident_bytes,
                non_ffn_resident_bytes,
                dsa_indexer_resident_bytes,
                active_routed_weight_bytes_per_token,
            }
        }
        ValidatedCheckpointLayout::Opaque {
            routed_expert_resident_byte_bounds,
        } => {
            let checkpoint_payload = request.checkpoint.checkpoint.payload_bytes;
            let non_routed_resident_byte_bounds = OpenU64Bounds::closed(
                checkpoint_payload
                    .checked_sub(
                        routed_expert_resident_byte_bounds
                            .upper
                            .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?,
                    )
                    .ok_or(GlmDecodeLoweringError::LedgerInvariantViolation)?,
                checkpoint_payload
                    .checked_sub(routed_expert_resident_byte_bounds.lower)
                    .ok_or(GlmDecodeLoweringError::LedgerInvariantViolation)?,
            );
            let routed_upper = routed_expert_resident_byte_bounds
                .upper
                .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
            let average_routed_expert_storage_byte_bounds = OpenU64Bounds::closed(
                routed_expert_resident_byte_bounds.lower / routed_expert_instance_count,
                routed_upper.div_ceil(routed_expert_instance_count),
            );
            ValidatedWeightStorage::Opaque {
                routed_expert_resident_byte_bounds,
                average_routed_expert_storage_byte_bounds,
                non_routed_resident_byte_bounds,
            }
        }
    };
    let routed_flops_per_token = active_routed_parameters
        .checked_mul(2)
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let shared_dense_flops_per_token = shared_dense_parameters
        .checked_mul(2)
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let ffn_flops_per_token = routed_flops_per_token
        .checked_add(shared_dense_flops_per_token)
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let semantic_kv_bytes_per_token = request
        .model
        .semantic_kv_bytes_per_token()
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    Ok(ValidatedModel {
        active_parameters: ActiveParameterLedger {
            released_active_parameter_count: hybrid.active_parameter_count,
            exact_whole_model_active_parameter_count: hybrid.active_parameter_count.exact(),
            exact_active_routed_expert_parameter_count_per_candidate_token:
                active_routed_parameters,
            exact_active_shared_and_dense_ffn_parameter_count_per_candidate_token:
                shared_dense_parameters,
            exact_active_ffn_parameter_count_per_candidate_token: active_ffn_parameters,
        },
        routed_expert_instance_count,
        weight_storage,
        routed_flops_per_token,
        shared_dense_flops_per_token,
        ffn_flops_per_token,
        semantic_kv_bytes_per_token,
    })
}

fn validate_checkpoint(
    request: &GlmDecodeLoweringRequest,
    hybrid: &crate::spec::HybridMoeMlaDsaSpec,
) -> Result<ValidatedCheckpointLayout, GlmDecodeLoweringError> {
    validate_required("checkpoint.variant_id", &request.checkpoint.variant_id)?;
    for (field, value) in [
        (
            "checkpoint.checkpoint.model_id",
            request.checkpoint.checkpoint.model_id.as_str(),
        ),
        (
            "checkpoint.checkpoint.checkpoint_revision",
            request.checkpoint.checkpoint.checkpoint_revision.as_str(),
        ),
        (
            "checkpoint.checkpoint.source_artifact_id",
            request.checkpoint.checkpoint.source_artifact_id.as_str(),
        ),
    ] {
        validate_required(field, value)?;
    }
    if request.checkpoint.checkpoint.model_id != request.model.model_id
        || request.checkpoint.checkpoint.checkpoint_revision != request.model.model_revision
        || request.checkpoint.checkpoint.payload_bytes == 0
    {
        return Err(GlmDecodeLoweringError::CheckpointModelMismatch);
    }
    match &request.checkpoint.routed_expert_storage {
        RoutedExpertStorageEvidence::ModelSpecExact { source_artifact_id } => {
            validate_required(
                "checkpoint.routed_expert_storage.source_artifact_id",
                source_artifact_id,
            )?;
            if request.model.weight_bytes() != Some(request.checkpoint.checkpoint.payload_bytes) {
                return Err(GlmDecodeLoweringError::CheckpointModelMismatch);
            }
            if request.model.quantized_weight_storage.is_some()
                || hybrid.moe.routed_expert_quantized_weight_storage.is_some()
            {
                return Err(GlmDecodeLoweringError::OpaqueCheckpointLayout);
            }
            Ok(ValidatedCheckpointLayout::Exact)
        }
        RoutedExpertStorageEvidence::OpaqueAggregateBounds {
            bytes,
            source_artifact_id,
            lower_bound_basis,
            upper_bound_basis,
        } => {
            for (field, value) in [
                (
                    "checkpoint.routed_expert_storage.source_artifact_id",
                    source_artifact_id.as_str(),
                ),
                (
                    "checkpoint.routed_expert_storage.lower_bound_basis",
                    lower_bound_basis.as_str(),
                ),
                (
                    "checkpoint.routed_expert_storage.upper_bound_basis",
                    upper_bound_basis.as_str(),
                ),
            ] {
                validate_required(field, value)?;
            }
            if bytes.lower > bytes.upper
                || bytes.upper > request.checkpoint.checkpoint.payload_bytes
            {
                return Err(GlmDecodeLoweringError::InvalidField(
                    "checkpoint.routed_expert_storage.bytes",
                ));
            }
            Ok(ValidatedCheckpointLayout::Opaque {
                routed_expert_resident_byte_bounds: OpenU64Bounds::closed(bytes.lower, bytes.upper),
            })
        }
    }
}

fn validate_workload(workload: &DecodeWorkload) -> Result<(), GlmDecodeLoweringError> {
    validate_required(
        "workload.evidence_source_artifact_id",
        &workload.evidence_source_artifact_id,
    )?;
    if workload.batch_size == 0
        || workload.context_tokens_per_request == 0
        || workload.candidate_tokens == 0
        || workload.committed_tokens == 0
        || workload.candidate_tokens < workload.committed_tokens
    {
        return Err(GlmDecodeLoweringError::InvalidField("workload"));
    }
    Ok(())
}

fn validate_attention_dsa(work: &BoundedDecodeWork) -> Result<(), GlmDecodeLoweringError> {
    for (field, bounds) in [
        ("attention_dsa.attention_flops", work.attention_flops),
        (
            "attention_dsa.attention_non_flop_operations",
            work.attention_non_flop_operations,
        ),
        (
            "attention_dsa.attention_weight_bytes",
            work.attention_weight_bytes,
        ),
        ("attention_dsa.activation_bytes", work.activation_bytes),
        ("attention_dsa.dsa_indexer_flops", work.dsa_indexer_flops),
        (
            "attention_dsa.dsa_indexer_weight_bytes",
            work.dsa_indexer_weight_bytes,
        ),
        (
            "attention_dsa.dsa_topk_non_flop_operations",
            work.dsa_topk_non_flop_operations,
        ),
        (
            "attention_dsa.other_non_ffn_flops",
            work.other_non_ffn_flops,
        ),
        (
            "attention_dsa.other_non_ffn_non_flop_operations",
            work.other_non_ffn_non_flop_operations,
        ),
        (
            "attention_dsa.other_non_ffn_weight_bytes",
            work.other_non_ffn_weight_bytes,
        ),
    ] {
        bounds.validate(field)?;
    }
    validate_evidence("attention_dsa.evidence", &work.evidence)?;
    validate_required("attention_dsa.basis", &work.basis)
}

fn validate_cache(cache: &DecodeCacheState) -> Result<(), GlmDecodeLoweringError> {
    for (field, bounds) in [
        ("cache.semantic_kv_read_bytes", cache.semantic_kv_read_bytes),
        (
            "cache.semantic_kv_write_bytes",
            cache.semantic_kv_write_bytes,
        ),
        ("cache.dsa_index_lookup_bytes", cache.dsa_index_lookup_bytes),
        ("cache.dsa_index_store_bytes", cache.dsa_index_store_bytes),
    ] {
        bounds.validate(field)?;
    }
    validate_evidence("cache.evidence", &cache.evidence)?;
    validate_required("cache.basis", &cache.basis)
}

fn validate_mtp(
    mtp: &MtpDecodeInput,
    model_shares_indices: bool,
) -> Result<(), GlmDecodeLoweringError> {
    match mtp {
        MtpDecodeInput::Disabled(evidence) => validate_evidence("mtp.evidence", evidence),
        MtpDecodeInput::Enabled(work) => {
            if work.draft_tokens == 0
                || work.synchronization_participants == 0
                || work.shares_dsa_indices != model_shares_indices
            {
                return Err(GlmDecodeLoweringError::InvalidField("mtp"));
            }
            for (field, bounds) in [
                ("mtp.draft_flops", work.draft_flops),
                ("mtp.verification_flops", work.verification_flops),
                ("mtp.state_read_bytes", work.state_read_bytes),
                ("mtp.state_write_bytes", work.state_write_bytes),
            ] {
                bounds.validate(field)?;
            }
            validate_evidence("mtp.evidence", &work.evidence)?;
            validate_required("mtp.basis", &work.basis)
        }
    }
}

fn route_ledger(
    request: &GlmDecodeLoweringRequest,
    model: &ValidatedModel,
) -> Result<RouteAggregateLedger, GlmDecodeLoweringError> {
    let expected_dispatches = request
        .workload
        .candidate_tokens
        .checked_mul(75)
        .and_then(|value| value.checked_mul(8))
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let ledger = match &request.route {
        DecodeRouteInput::ExplicitAggregates(route) => RouteAggregateLedger {
            total_dispatches: route.total_dispatches,
            unique_routed_expert_instances: route.unique_routed_expert_instances,
            remote_dispatches: route.remote_dispatches,
            endpoint_payload_bytes: route.endpoint_payload_bytes,
            endpoint_message_count: route.endpoint_message_count,
            network_hop_payload_bytes: route.network_hop_payload_bytes,
            network_hop_message_count: route.network_hop_message_count,
            participants: route.participants,
            evidence: route.evidence.clone(),
            basis: route.basis.clone(),
            route_report_selection: None,
        },
        DecodeRouteInput::PinnedRouteReportSelection(selection) => {
            validate_report_selection(selection, request)?;
            let remote_dispatches = scale_sample(
                selection.sample_remote_dispatches,
                expected_dispatches,
                selection.sample_total_dispatches,
            )?;
            let endpoint_payload_bytes = remote_dispatches.checked_mul(
                request
                    .traffic_bytes_per_remote_dispatch()
                    .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?,
            )?;
            let endpoint_message_count = scale_sample(
                selection.sample_endpoint_message_count,
                expected_dispatches,
                selection.sample_total_dispatches,
            )?;
            let network_hop_payload_bytes = scale_correlated_hop_sample(
                selection.sample_network_hop_payload_bytes,
                selection.sample_endpoint_payload_bytes,
                expected_dispatches,
                selection.sample_total_dispatches,
                endpoint_payload_bytes,
            )?;
            let network_hop_message_count = scale_correlated_hop_sample(
                selection.sample_network_hop_message_count,
                selection.sample_endpoint_message_count,
                expected_dispatches,
                selection.sample_total_dispatches,
                endpoint_message_count,
            )?;
            RouteAggregateLedger {
                total_dispatches: expected_dispatches,
                unique_routed_expert_instances: selection.unique_routed_expert_instances,
                remote_dispatches,
                endpoint_payload_bytes,
                endpoint_message_count,
                network_hop_payload_bytes,
                network_hop_message_count,
                participants: selection.participants,
                evidence: selection.evidence.clone(),
                basis: selection.basis.clone(),
                route_report_selection: Some(RouteReportSelectionIdentity {
                    report_content_id: selection.report_content_id.clone(),
                    scenario_id: selection.scenario_id.clone(),
                    topology_id: selection.topology_id.clone(),
                    strategy_id: selection.strategy_id.clone(),
                }),
            }
        }
    };
    validate_route_ledger(request, model, &ledger, expected_dispatches)?;
    Ok(ledger)
}

fn validate_report_selection(
    selection: &PinnedRouteReportSelection,
    request: &GlmDecodeLoweringRequest,
) -> Result<(), GlmDecodeLoweringError> {
    for (field, value) in [
        (
            "route.report_content_id",
            selection.report_content_id.as_str(),
        ),
        ("route.scenario_id", selection.scenario_id.as_str()),
        ("route.topology_id", selection.topology_id.as_str()),
        ("route.strategy_id", selection.strategy_id.as_str()),
        ("route.basis", selection.basis.as_str()),
    ] {
        validate_required(field, value)?;
    }
    if selection.report_content_id.len() != 64
        || !selection
            .report_content_id
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
        || selection.sample_total_dispatches == 0
        || selection.sample_remote_dispatches > selection.sample_total_dispatches
        || selection.participants < 2
    {
        return Err(GlmDecodeLoweringError::InvalidField("route"));
    }
    let bytes_per_remote = request
        .traffic_bytes_per_remote_dispatch()
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    if selection.sample_endpoint_payload_bytes
        != selection
            .sample_remote_dispatches
            .checked_mul(bytes_per_remote)
            .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?
        || selection.sample_network_hop_payload_bytes < selection.sample_endpoint_payload_bytes
        || selection.sample_endpoint_message_count == 0
        || selection.sample_network_hop_message_count < selection.sample_endpoint_message_count
    {
        return Err(GlmDecodeLoweringError::RouteTrafficMismatch);
    }
    selection
        .unique_routed_expert_instances
        .validate("route.unique_routed_expert_instances")?;
    validate_evidence("route.evidence", &selection.evidence)
}

impl GlmDecodeLoweringRequest {
    fn traffic_bytes_per_remote_dispatch(&self) -> Option<u64> {
        self.model.hybrid_spec()?;
        let round_trip_bits = u128::from(self.model.hidden_size)
            .checked_mul(u128::from(self.network_activation_precision.bits()))?
            .checked_mul(2)?;
        u64::try_from(round_trip_bits.checked_add(7)?.checked_div(8)?).ok()
    }
}

fn validate_route_ledger(
    request: &GlmDecodeLoweringRequest,
    model: &ValidatedModel,
    route: &RouteAggregateLedger,
    expected_dispatches: u64,
) -> Result<(), GlmDecodeLoweringError> {
    if route.total_dispatches != expected_dispatches || route.participants < 2 {
        return Err(GlmDecodeLoweringError::RouteTrafficMismatch);
    }
    for (field, bounds) in [
        (
            "route.unique_routed_expert_instances",
            route.unique_routed_expert_instances,
        ),
        ("route.remote_dispatches", route.remote_dispatches),
        ("route.endpoint_payload_bytes", route.endpoint_payload_bytes),
        ("route.endpoint_message_count", route.endpoint_message_count),
        (
            "route.network_hop_payload_bytes",
            route.network_hop_payload_bytes,
        ),
        (
            "route.network_hop_message_count",
            route.network_hop_message_count,
        ),
    ] {
        bounds.validate(field)?;
    }
    let minimum_unique = 75_u64
        .checked_mul(8)
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    if route.unique_routed_expert_instances.lower < minimum_unique
        || route
            .unique_routed_expert_instances
            .upper
            .is_some_and(|upper| {
                upper > route.total_dispatches || upper > model.routed_expert_instance_count
            })
        || route.remote_dispatches.lower > route.total_dispatches
        || route
            .remote_dispatches
            .upper
            .is_some_and(|upper| upper > route.total_dispatches)
    {
        return Err(GlmDecodeLoweringError::RouteTrafficMismatch);
    }
    let bytes_per_remote = request
        .traffic_bytes_per_remote_dispatch()
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let expected_endpoint = route.remote_dispatches.checked_mul(bytes_per_remote)?;
    if route.endpoint_payload_bytes != expected_endpoint
        || route.network_hop_payload_bytes.lower < route.endpoint_payload_bytes.lower
        || matches!(
            (
                route.network_hop_payload_bytes.upper,
                route.endpoint_payload_bytes.upper
            ),
            (Some(network), Some(endpoint)) if network < endpoint
        )
        || route.endpoint_message_count.lower == 0
        || route.network_hop_message_count.lower < route.endpoint_message_count.lower
    {
        return Err(GlmDecodeLoweringError::RouteTrafficMismatch);
    }
    validate_evidence("route.evidence", &route.evidence)?;
    validate_required("route.basis", &route.basis)
}

fn scale_sample(
    sample: u64,
    target_total: u64,
    sample_total: u64,
) -> Result<OpenU64Bounds, GlmDecodeLoweringError> {
    let numerator = u128::from(sample)
        .checked_mul(u128::from(target_total))
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let denominator = u128::from(sample_total);
    Ok(OpenU64Bounds::closed(
        u64::try_from(numerator / denominator)
            .map_err(|_| GlmDecodeLoweringError::ArithmeticOverflow)?,
        u64::try_from(numerator.div_ceil(denominator))
            .map_err(|_| GlmDecodeLoweringError::ArithmeticOverflow)?,
    ))
}

fn scale_correlated_hop_sample(
    sample_hop: u64,
    sample_endpoint: u64,
    target_total: u64,
    sample_total: u64,
    endpoint: OpenU64Bounds,
) -> Result<OpenU64Bounds, GlmDecodeLoweringError> {
    if sample_hop == sample_endpoint {
        return Ok(endpoint);
    }
    let mut hop = scale_sample(sample_hop, target_total, sample_total)?;
    hop.lower = hop.lower.max(endpoint.lower);
    hop.upper = match (hop.upper, endpoint.upper) {
        (Some(hop), Some(endpoint)) => Some(hop.max(endpoint)),
        _ => None,
    };
    Ok(hop)
}

fn weight_ledger(
    request: &GlmDecodeLoweringRequest,
    model: &ValidatedModel,
    route: &RouteAggregateLedger,
) -> Result<DecodeWeightLedger, GlmDecodeLoweringError> {
    match &model.weight_storage {
        ValidatedWeightStorage::Exact {
            per_layer_expert_storage_bytes,
            routed_expert_resident_bytes,
            shared_dense_resident_bytes,
            ffn_resident_bytes,
            non_ffn_resident_bytes,
            dsa_indexer_resident_bytes,
            active_routed_weight_bytes_per_token,
        } => {
            let routed_expert_hbm_read_bytes = match request.cache.weight_cache_policy {
                WeightCachePolicy::UniqueWeightsLoadedOncePerDecodeStep => route
                    .unique_routed_expert_instances
                    .checked_mul(*per_layer_expert_storage_bytes)?,
                WeightCachePolicy::NoWeightReuseAcrossCandidateTokens => OpenU64Bounds::exact(
                    active_routed_weight_bytes_per_token
                        .checked_mul(request.workload.candidate_tokens)
                        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?,
                ),
            };
            let shared_and_dense_ffn_hbm_read_bytes = match request.cache.weight_cache_policy {
                WeightCachePolicy::UniqueWeightsLoadedOncePerDecodeStep => {
                    OpenU64Bounds::exact(*shared_dense_resident_bytes)
                }
                WeightCachePolicy::NoWeightReuseAcrossCandidateTokens => OpenU64Bounds::exact(
                    shared_dense_resident_bytes
                        .checked_mul(request.workload.candidate_tokens)
                        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?,
                ),
            };
            let total_ffn_hbm_read_bytes =
                routed_expert_hbm_read_bytes.checked_add(shared_and_dense_ffn_hbm_read_bytes)?;
            Ok(DecodeWeightLedger {
                checkpoint_payload_bytes: request.checkpoint.checkpoint.payload_bytes,
                exact_routed_expert_resident_bytes: Some(*routed_expert_resident_bytes),
                exact_shared_and_dense_ffn_resident_bytes: Some(*shared_dense_resident_bytes),
                exact_ffn_resident_bytes: Some(*ffn_resident_bytes),
                exact_non_ffn_resident_bytes: Some(*non_ffn_resident_bytes),
                exact_dsa_indexer_resident_bytes: Some(*dsa_indexer_resident_bytes),
                exact_active_routed_expert_weight_bytes_per_candidate_token: Some(
                    *active_routed_weight_bytes_per_token,
                ),
                routed_expert_resident_byte_bounds: None,
                average_routed_expert_storage_byte_bounds: None,
                non_routed_resident_byte_bounds: None,
                routed_expert_hbm_read_bytes,
                shared_and_dense_ffn_hbm_read_bytes,
                total_ffn_hbm_read_bytes,
            })
        }
        ValidatedWeightStorage::Opaque {
            routed_expert_resident_byte_bounds,
            average_routed_expert_storage_byte_bounds,
            non_routed_resident_byte_bounds,
        } => {
            let pass_count = match request.cache.weight_cache_policy {
                WeightCachePolicy::UniqueWeightsLoadedOncePerDecodeStep => 1,
                WeightCachePolicy::NoWeightReuseAcrossCandidateTokens => {
                    request.workload.candidate_tokens
                }
            };
            let routed_upper = routed_expert_resident_byte_bounds
                .upper
                .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?
                .checked_mul(pass_count)
                .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
            let routed_lower = match request.cache.weight_cache_policy {
                WeightCachePolicy::UniqueWeightsLoadedOncePerDecodeStep
                    if route.unique_routed_expert_instances.lower
                        == model.routed_expert_instance_count =>
                {
                    routed_expert_resident_byte_bounds.lower
                }
                _ => 0,
            };
            let non_routed_upper = non_routed_resident_byte_bounds
                .upper
                .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?
                .checked_mul(pass_count)
                .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
            let routed_expert_hbm_read_bytes = OpenU64Bounds::closed(routed_lower, routed_upper);
            let shared_and_dense_ffn_hbm_read_bytes = OpenU64Bounds::closed(0, non_routed_upper);
            let uncapped_total =
                routed_expert_hbm_read_bytes.checked_add(shared_and_dense_ffn_hbm_read_bytes)?;
            let payload_pass_ceiling = request
                .checkpoint
                .checkpoint
                .payload_bytes
                .checked_mul(pass_count)
                .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
            let total_ffn_hbm_read_bytes = OpenU64Bounds::closed(
                uncapped_total.lower,
                uncapped_total
                    .upper
                    .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?
                    .min(payload_pass_ceiling),
            );
            Ok(DecodeWeightLedger {
                checkpoint_payload_bytes: request.checkpoint.checkpoint.payload_bytes,
                exact_routed_expert_resident_bytes: None,
                exact_shared_and_dense_ffn_resident_bytes: None,
                exact_ffn_resident_bytes: None,
                exact_non_ffn_resident_bytes: None,
                exact_dsa_indexer_resident_bytes: None,
                exact_active_routed_expert_weight_bytes_per_candidate_token: None,
                routed_expert_resident_byte_bounds: Some(*routed_expert_resident_byte_bounds),
                average_routed_expert_storage_byte_bounds: Some(
                    *average_routed_expert_storage_byte_bounds,
                ),
                non_routed_resident_byte_bounds: Some(*non_routed_resident_byte_bounds),
                routed_expert_hbm_read_bytes,
                shared_and_dense_ffn_hbm_read_bytes,
                total_ffn_hbm_read_bytes,
            })
        }
    }
}

fn compute_ledger(
    request: &GlmDecodeLoweringRequest,
    model: &ValidatedModel,
) -> Result<DecodeComputeLedger, GlmDecodeLoweringError> {
    let exact_routed_expert_flops = model
        .routed_flops_per_token
        .checked_mul(request.workload.candidate_tokens)
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let exact_shared_and_dense_ffn_flops = model
        .shared_dense_flops_per_token
        .checked_mul(request.workload.candidate_tokens)
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let exact_ffn_flops = exact_routed_expert_flops
        .checked_add(exact_shared_and_dense_ffn_flops)
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let mtp_flops = mtp_flops(&request.mtp)?;
    let total_flops = OpenU64Bounds::exact(exact_ffn_flops)
        .checked_add(request.attention_dsa.attention_flops)?
        .checked_add(request.attention_dsa.dsa_indexer_flops)?
        .checked_add(request.attention_dsa.other_non_ffn_flops)?
        .checked_add(mtp_flops)?;
    let non_flop_operations = request
        .attention_dsa
        .attention_non_flop_operations
        .checked_add(request.attention_dsa.dsa_topk_non_flop_operations)?
        .checked_add(request.attention_dsa.other_non_ffn_non_flop_operations)?;
    Ok(DecodeComputeLedger {
        exact_routed_expert_flops_per_candidate_token: model.routed_flops_per_token,
        exact_shared_and_dense_ffn_flops_per_candidate_token: model.shared_dense_flops_per_token,
        exact_ffn_flops_per_candidate_token: model.ffn_flops_per_token,
        exact_routed_expert_flops,
        exact_shared_and_dense_ffn_flops,
        exact_ffn_flops,
        attention_flops: request.attention_dsa.attention_flops,
        dsa_indexer_flops: request.attention_dsa.dsa_indexer_flops,
        other_non_ffn_flops: request.attention_dsa.other_non_ffn_flops,
        mtp_flops,
        total_flops,
        non_flop_operations,
    })
}

fn mtp_flops(mtp: &MtpDecodeInput) -> Result<OpenU64Bounds, GlmDecodeLoweringError> {
    match mtp {
        MtpDecodeInput::Disabled(_) => Ok(OpenU64Bounds::exact(0)),
        MtpDecodeInput::Enabled(work) => work.draft_flops.checked_add(work.verification_flops),
    }
}

fn lower_ledger(
    request: &GlmDecodeLoweringRequest,
    model: &ValidatedModel,
    route: &RouteAggregateLedger,
    weights: &DecodeWeightLedger,
    selection: BoundSelection,
) -> Result<Option<ActionLedger>, GlmDecodeLoweringError> {
    let Some(selected) = select_work(request, route, weights, selection) else {
        return Ok(None);
    };
    let exact_evidence = EvidenceProvenance {
        kind: EvidenceKind::DerivedFact,
        source_artifact_id: request.checkpoint.checkpoint.source_artifact_id.clone(),
    };
    let workload_evidence = EvidenceProvenance {
        kind: EvidenceKind::WorkloadTrace,
        source_artifact_id: request.workload.evidence_source_artifact_id.clone(),
    };
    let weight_traffic_evidence = EvidenceProvenance {
        kind: if route.evidence.kind == EvidenceKind::Assumption
            || request.cache.evidence.kind == EvidenceKind::Assumption
            || matches!(&model.weight_storage, ValidatedWeightStorage::Opaque { .. })
        {
            EvidenceKind::Assumption
        } else {
            EvidenceKind::DerivedFact
        },
        source_artifact_id: format!(
            "{}+{}+{}",
            route.evidence.source_artifact_id,
            request.cache.evidence.source_artifact_id,
            request.checkpoint.checkpoint.source_artifact_id
        ),
    };
    let mut actions = Vec::new();
    push_action(
        &mut actions,
        "decode_batch",
        &[],
        workload_evidence.clone(),
        ActionWork::Scheduler(SchedulerAction {
            decision: SchedulerDecision::BatchFormation,
            requests: request.workload.batch_size,
            tokens: request.workload.candidate_tokens,
        }),
    );
    push_memory_if_nonzero(
        &mut actions,
        "attention_weights_read",
        &["decode_batch"],
        request.attention_dsa.evidence.clone(),
        MemoryPayload::Weights,
        selected.attention_weight_bytes,
    );
    push_memory_if_nonzero(
        &mut actions,
        "semantic_kv_read",
        &["decode_batch"],
        request.cache.evidence.clone(),
        MemoryPayload::Kv,
        selected.semantic_kv_read_bytes,
    );
    push_memory_if_nonzero(
        &mut actions,
        "decode_activation_read",
        &["decode_batch"],
        request.attention_dsa.evidence.clone(),
        MemoryPayload::Activations,
        selected.activation_bytes,
    );
    push_compute_if_nonzero(
        &mut actions,
        "attention_compute",
        &[
            "attention_weights_read",
            "semantic_kv_read",
            "decode_activation_read",
            "decode_batch",
        ],
        request.attention_dsa.evidence.clone(),
        ComputeClass::AttentionScore,
        "bounded_glm_mla_attention_and_projection",
        selected.attention_flops,
        selected.attention_non_flop_operations,
    );
    push_memory_if_nonzero(
        &mut actions,
        "dsa_indexer_weights_read",
        &["decode_batch"],
        request.attention_dsa.evidence.clone(),
        MemoryPayload::Weights,
        selected.dsa_indexer_weight_bytes,
    );
    push_compute_if_nonzero(
        &mut actions,
        "dsa_indexer_compute",
        &["dsa_indexer_weights_read", "decode_batch"],
        request.attention_dsa.evidence.clone(),
        ComputeClass::MatrixMultiply,
        "bounded_glm_dsa_indexer",
        selected.dsa_indexer_flops,
        0,
    );
    push_compute_if_nonzero(
        &mut actions,
        "dsa_topk",
        &["dsa_indexer_compute", "decode_batch"],
        request.attention_dsa.evidence.clone(),
        ComputeClass::TopK,
        "bounded_glm_dsa_topk_selection",
        0,
        selected.dsa_topk_operations,
    );
    push_memory_if_nonzero(
        &mut actions,
        "other_non_ffn_weights_read",
        &["decode_batch"],
        request.attention_dsa.evidence.clone(),
        MemoryPayload::Weights,
        selected.other_non_ffn_weight_bytes,
    );
    push_compute_if_nonzero(
        &mut actions,
        "other_non_ffn_compute",
        &["other_non_ffn_weights_read", "decode_batch"],
        request.attention_dsa.evidence.clone(),
        ComputeClass::Elementwise,
        "bounded_glm_other_non_ffn_decode_work",
        selected.other_non_ffn_flops,
        selected.other_non_ffn_operations,
    );
    push_cache_if_nonzero(
        &mut actions,
        "dsa_index_lookup",
        &["dsa_topk", "decode_batch"],
        request.cache.evidence.clone(),
        CacheOperation::Lookup,
        CacheKeySpace::DsaIndices,
        selected.dsa_index_lookup_bytes,
        Some(request.cache.dsa_index_lookup_hit),
    );
    push_cache_if_nonzero(
        &mut actions,
        "dsa_index_store",
        &["dsa_topk", "decode_batch"],
        request.cache.evidence.clone(),
        CacheOperation::Store,
        CacheKeySpace::DsaIndices,
        selected.dsa_index_store_bytes,
        None,
    );
    push_action(
        &mut actions,
        "expert_route",
        &[
            "attention_compute",
            "dsa_index_lookup",
            "dsa_index_store",
            "dsa_topk",
            "other_non_ffn_compute",
            "decode_batch",
        ],
        route.evidence.clone(),
        ActionWork::Scheduler(SchedulerAction {
            decision: SchedulerDecision::ExpertRouting,
            requests: request.workload.batch_size,
            tokens: request.workload.candidate_tokens,
        }),
    );
    if let Some(opaque_ffn_weight_bytes) = selected.opaque_ffn_weight_bytes {
        push_memory_if_nonzero(
            &mut actions,
            "opaque_ffn_weights_read",
            &["expert_route"],
            weight_traffic_evidence,
            MemoryPayload::Weights,
            opaque_ffn_weight_bytes,
        );
    } else {
        push_memory_if_nonzero(
            &mut actions,
            "routed_expert_weights_read",
            &["expert_route"],
            weight_traffic_evidence.clone(),
            MemoryPayload::Weights,
            selected.routed_weight_bytes,
        );
        push_memory_if_nonzero(
            &mut actions,
            "shared_dense_ffn_weights_read",
            &["expert_route"],
            weight_traffic_evidence,
            MemoryPayload::Weights,
            selected.shared_dense_weight_bytes,
        );
    }
    push_network_if_nonzero(
        &mut actions,
        "moe_dispatch",
        &["expert_route"],
        route.evidence.clone(),
        route.participants,
        selected.network_bytes,
        selected.network_messages,
    );
    push_action(
        &mut actions,
        "expert_ready",
        &[
            "routed_expert_weights_read",
            "shared_dense_ffn_weights_read",
            "opaque_ffn_weights_read",
            "moe_dispatch",
            "expert_route",
        ],
        route.evidence.clone(),
        ActionWork::Synchronization(SynchronizationAction {
            kind: SynchronizationKind::Barrier,
            participants: route.participants,
        }),
    );
    push_action(
        &mut actions,
        "routed_expert_ffn",
        &["expert_ready"],
        exact_evidence.clone(),
        ActionWork::Compute(ComputeAction {
            class: ComputeClass::MatrixMultiply,
            label: "exact_glm_active_routed_expert_ffn".into(),
            flops: Flops::new(
                model
                    .routed_flops_per_token
                    .checked_mul(request.workload.candidate_tokens)
                    .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?,
            ),
            non_flop_operations: Operations::new(0),
        }),
    );
    push_action(
        &mut actions,
        "shared_dense_ffn",
        &["expert_ready"],
        exact_evidence.clone(),
        ActionWork::Compute(ComputeAction {
            class: ComputeClass::MatrixMultiply,
            label: "exact_glm_active_shared_and_dense_ffn".into(),
            flops: Flops::new(
                model
                    .shared_dense_flops_per_token
                    .checked_mul(request.workload.candidate_tokens)
                    .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?,
            ),
            non_flop_operations: Operations::new(0),
        }),
    );
    push_action(
        &mut actions,
        "ffn_complete",
        &["routed_expert_ffn", "shared_dense_ffn"],
        exact_evidence,
        ActionWork::Synchronization(SynchronizationAction {
            kind: SynchronizationKind::Event,
            participants: 2,
        }),
    );
    push_cache_if_nonzero(
        &mut actions,
        "semantic_kv_store",
        &["attention_compute", "decode_batch"],
        request.cache.evidence.clone(),
        CacheOperation::Store,
        CacheKeySpace::Kv,
        selected.semantic_kv_write_bytes,
        None,
    );
    let commit_dependency = match &request.mtp {
        MtpDecodeInput::Disabled(_) => "ffn_complete",
        MtpDecodeInput::Enabled(mtp) => {
            push_action(
                &mut actions,
                "mtp_draft_schedule",
                &["ffn_complete", "semantic_kv_store"],
                mtp.evidence.clone(),
                ActionWork::Scheduler(SchedulerAction {
                    decision: SchedulerDecision::MtpDraft,
                    requests: request.workload.batch_size,
                    tokens: mtp.draft_tokens,
                }),
            );
            push_memory_if_nonzero_with_payload(
                &mut actions,
                "mtp_state_read",
                &["mtp_draft_schedule"],
                mtp.evidence.clone(),
                MemoryTier::Hbm,
                MemoryTier::OnChip,
                MemoryPayload::MtpState,
                selected.mtp_state_read_bytes,
            );
            push_compute_if_nonzero(
                &mut actions,
                "mtp_draft_compute",
                &["mtp_state_read", "mtp_draft_schedule"],
                mtp.evidence.clone(),
                ComputeClass::MatrixMultiply,
                "bounded_glm_shared_parameter_mtp_draft",
                selected.mtp_draft_flops,
                0,
            );
            push_memory_if_nonzero_with_payload(
                &mut actions,
                "mtp_state_write",
                &["mtp_draft_compute", "mtp_draft_schedule"],
                mtp.evidence.clone(),
                MemoryTier::OnChip,
                MemoryTier::Hbm,
                MemoryPayload::MtpState,
                selected.mtp_state_write_bytes,
            );
            push_action(
                &mut actions,
                "mtp_verify_schedule",
                &["mtp_draft_compute", "mtp_state_write", "mtp_draft_schedule"],
                mtp.evidence.clone(),
                ActionWork::Scheduler(SchedulerAction {
                    decision: SchedulerDecision::MtpVerify,
                    requests: request.workload.batch_size,
                    tokens: request.workload.candidate_tokens,
                }),
            );
            push_compute_if_nonzero(
                &mut actions,
                "mtp_verify_compute",
                &["mtp_verify_schedule"],
                mtp.evidence.clone(),
                ComputeClass::MatrixMultiply,
                "bounded_glm_mtp_verification",
                selected.mtp_verification_flops,
                0,
            );
            push_action(
                &mut actions,
                "mtp_verify_ready",
                &["mtp_verify_compute", "mtp_verify_schedule"],
                mtp.evidence.clone(),
                ActionWork::Synchronization(SynchronizationAction {
                    kind: SynchronizationKind::Barrier,
                    participants: mtp.synchronization_participants,
                }),
            );
            "mtp_verify_ready"
        }
    };
    push_action(
        &mut actions,
        "token_commit",
        &[commit_dependency, "semantic_kv_store"],
        workload_evidence,
        ActionWork::Scheduler(SchedulerAction {
            decision: SchedulerDecision::TokenCommit,
            requests: request.workload.batch_size,
            tokens: request.workload.committed_tokens,
        }),
    );
    let aggregate_context = request
        .workload
        .context_tokens_per_request
        .checked_mul(u64::from(request.workload.batch_size))
        .ok_or(GlmDecodeLoweringError::ArithmeticOverflow)?;
    let ledger = ActionLedger {
        schema_version: ACTION_LEDGER_SCHEMA_VERSION,
        provenance: LedgerProvenance {
            producer: ProducerProvenance {
                name: "foundry-glm-decode-lowerer".into(),
                version: match selection {
                    BoundSelection::Lower => "1-lower-bound".into(),
                    BoundSelection::Upper => "1-upper-bound".into(),
                },
            },
            model: ModelProvenance {
                model_id: request.model.model_id.clone(),
                model_revision: request.model.model_revision.clone(),
            },
            phase: PhaseProvenance {
                phase: InferencePhase::Decode,
                batch_size: request.workload.batch_size,
                context_tokens: aggregate_context,
                candidate_tokens: request.workload.candidate_tokens,
                committed_tokens: request.workload.committed_tokens,
            },
        },
        actions,
    };
    ledger.validate()?;
    Ok(Some(ledger))
}

fn select_work(
    request: &GlmDecodeLoweringRequest,
    route: &RouteAggregateLedger,
    weights: &DecodeWeightLedger,
    selection: BoundSelection,
) -> Option<SelectedWork> {
    let opaque_ffn_weight_bytes = if matches!(
        &request.checkpoint.routed_expert_storage,
        RoutedExpertStorageEvidence::OpaqueAggregateBounds { .. }
    ) {
        Some(weights.total_ffn_hbm_read_bytes.select(selection)?)
    } else {
        None
    };
    let (mtp_draft_flops, mtp_verification_flops, mtp_state_read_bytes, mtp_state_write_bytes) =
        match &request.mtp {
            MtpDecodeInput::Disabled(_) => (0, 0, 0, 0),
            MtpDecodeInput::Enabled(work) => (
                work.draft_flops.select(selection)?,
                work.verification_flops.select(selection)?,
                work.state_read_bytes.select(selection)?,
                work.state_write_bytes.select(selection)?,
            ),
        };
    Some(SelectedWork {
        attention_flops: request.attention_dsa.attention_flops.select(selection)?,
        attention_non_flop_operations: request
            .attention_dsa
            .attention_non_flop_operations
            .select(selection)?,
        attention_weight_bytes: request
            .attention_dsa
            .attention_weight_bytes
            .select(selection)?,
        activation_bytes: request.attention_dsa.activation_bytes.select(selection)?,
        dsa_indexer_flops: request.attention_dsa.dsa_indexer_flops.select(selection)?,
        dsa_indexer_weight_bytes: request
            .attention_dsa
            .dsa_indexer_weight_bytes
            .select(selection)?,
        dsa_topk_operations: request
            .attention_dsa
            .dsa_topk_non_flop_operations
            .select(selection)?,
        other_non_ffn_flops: request
            .attention_dsa
            .other_non_ffn_flops
            .select(selection)?,
        other_non_ffn_operations: request
            .attention_dsa
            .other_non_ffn_non_flop_operations
            .select(selection)?,
        other_non_ffn_weight_bytes: request
            .attention_dsa
            .other_non_ffn_weight_bytes
            .select(selection)?,
        semantic_kv_read_bytes: request.cache.semantic_kv_read_bytes.select(selection)?,
        semantic_kv_write_bytes: request.cache.semantic_kv_write_bytes.select(selection)?,
        dsa_index_lookup_bytes: request.cache.dsa_index_lookup_bytes.select(selection)?,
        dsa_index_store_bytes: request.cache.dsa_index_store_bytes.select(selection)?,
        routed_weight_bytes: weights.routed_expert_hbm_read_bytes.select(selection)?,
        shared_dense_weight_bytes: weights
            .shared_and_dense_ffn_hbm_read_bytes
            .select(selection)?,
        opaque_ffn_weight_bytes,
        network_bytes: route.network_hop_payload_bytes.select(selection)?,
        network_messages: route.network_hop_message_count.select(selection)?,
        mtp_draft_flops,
        mtp_verification_flops,
        mtp_state_read_bytes,
        mtp_state_write_bytes,
    })
}

fn push_action(
    actions: &mut Vec<Action>,
    id: &str,
    dependencies: &[&str],
    evidence: EvidenceProvenance,
    work: ActionWork,
) {
    let dependencies = dependencies
        .iter()
        .filter(|dependency| {
            actions
                .iter()
                .any(|action| action.id.as_str() == **dependency)
        })
        .map(|dependency| ActionId::from(*dependency))
        .collect();
    actions.push(Action {
        id: ActionId::from(id),
        dependencies,
        evidence,
        work,
        measurements: None,
    });
}

#[allow(clippy::too_many_arguments)]
fn push_compute_if_nonzero(
    actions: &mut Vec<Action>,
    id: &str,
    dependencies: &[&str],
    evidence: EvidenceProvenance,
    class: ComputeClass,
    label: &str,
    flops: u64,
    operations: u64,
) {
    if flops == 0 && operations == 0 {
        return;
    }
    push_action(
        actions,
        id,
        dependencies,
        evidence,
        ActionWork::Compute(ComputeAction {
            class,
            label: label.into(),
            flops: Flops::new(flops),
            non_flop_operations: Operations::new(operations),
        }),
    );
}

fn push_memory_if_nonzero(
    actions: &mut Vec<Action>,
    id: &str,
    dependencies: &[&str],
    evidence: EvidenceProvenance,
    payload: MemoryPayload,
    bytes: u64,
) {
    push_memory_if_nonzero_with_payload(
        actions,
        id,
        dependencies,
        evidence,
        MemoryTier::Hbm,
        MemoryTier::OnChip,
        payload,
        bytes,
    );
}

#[allow(clippy::too_many_arguments)]
fn push_memory_if_nonzero_with_payload(
    actions: &mut Vec<Action>,
    id: &str,
    dependencies: &[&str],
    evidence: EvidenceProvenance,
    source: MemoryTier,
    destination: MemoryTier,
    payload: MemoryPayload,
    bytes: u64,
) {
    if bytes == 0 {
        return;
    }
    push_action(
        actions,
        id,
        dependencies,
        evidence,
        ActionWork::Memory(MemoryAction {
            source,
            destination,
            payload,
            bytes: Bytes::new(bytes),
        }),
    );
}

#[allow(clippy::too_many_arguments)]
fn push_cache_if_nonzero(
    actions: &mut Vec<Action>,
    id: &str,
    dependencies: &[&str],
    evidence: EvidenceProvenance,
    operation: CacheOperation,
    key_space: CacheKeySpace,
    bytes: u64,
    hit: Option<bool>,
) {
    if bytes == 0 {
        return;
    }
    push_action(
        actions,
        id,
        dependencies,
        evidence,
        ActionWork::Cache(CacheAction {
            operation,
            tier: MemoryTier::OnChip,
            key_space,
            bytes: Bytes::new(bytes),
            hit,
        }),
    );
}

fn push_network_if_nonzero(
    actions: &mut Vec<Action>,
    id: &str,
    dependencies: &[&str],
    evidence: EvidenceProvenance,
    participants: u32,
    bytes: u64,
    messages: u64,
) {
    if bytes == 0 || messages == 0 {
        return;
    }
    push_action(
        actions,
        id,
        dependencies,
        evidence,
        ActionWork::Network(NetworkAction {
            pattern: NetworkPattern::Collective {
                collective: CollectiveKind::AllToAll,
                participants,
            },
            source: "expert_parallel_group".into(),
            destination: "expert_parallel_group".into(),
            aggregate_bytes: Bytes::new(bytes),
            messages: Messages::new(messages),
        }),
    );
}

fn completeness_gate(
    request: &GlmDecodeLoweringRequest,
    route: &RouteAggregateLedger,
    weights: &DecodeWeightLedger,
    compute: &DecodeComputeLedger,
    hardware_ledger: &Option<ActionLedger>,
) -> DecodeCompletenessGate {
    let bounds = all_bounds(request, route, weights, compute);
    let has_open = bounds.iter().any(|bounds| bounds.is_open());
    let collapsed = bounds.iter().all(|bounds| bounds.is_collapsed());
    let all_actions_calibrated = hardware_ledger.as_ref().is_some_and(|ledger| {
        ledger.actions.iter().all(|action| {
            action.measurements.as_ref().is_some_and(|measurements| {
                measurements.latency.is_some()
                    && measurements.energy.is_some()
                    && measurements.cost.is_some()
            })
        })
    });
    let contains_assumptions = hardware_ledger.as_ref().is_none_or(|ledger| {
        ledger
            .actions
            .iter()
            .any(|action| action.evidence.kind == EvidenceKind::Assumption)
    });
    let opaque_checkpoint = matches!(
        &request.checkpoint.routed_expert_storage,
        RoutedExpertStorageEvidence::OpaqueAggregateBounds { .. }
    );
    let mut blockers = Vec::new();
    if has_open {
        blockers.push(CompletenessBlocker::OpenWorkBounds);
    }
    if !collapsed {
        blockers.push(CompletenessBlocker::NonCollapsedWorkBounds);
    }
    if opaque_checkpoint {
        blockers.push(CompletenessBlocker::OpaqueCheckpointLayout);
    }
    if request.model.exact_active_parameter_count().is_none() {
        blockers.push(CompletenessBlocker::ApproximateWholeModelActiveParameters);
    }
    if !all_actions_calibrated {
        blockers.push(CompletenessBlocker::MissingActionCalibration);
    }
    if contains_assumptions {
        blockers.push(CompletenessBlocker::LedgerContainsAssumptions);
    }
    let complete = blockers.is_empty();
    DecodeCompletenessGate {
        work_bounds_collapsed: collapsed,
        all_actions_calibrated,
        complete_hardware_timing_claim_permitted: complete,
        cost_per_token_claim_permitted: complete,
        checkpoint_quality_claim_permitted: opaque_checkpoint.then_some(false),
        blockers,
    }
}

fn all_bounds(
    request: &GlmDecodeLoweringRequest,
    route: &RouteAggregateLedger,
    weights: &DecodeWeightLedger,
    compute: &DecodeComputeLedger,
) -> Vec<OpenU64Bounds> {
    let mut bounds = vec![
        request.attention_dsa.attention_flops,
        request.attention_dsa.attention_non_flop_operations,
        request.attention_dsa.attention_weight_bytes,
        request.attention_dsa.activation_bytes,
        request.attention_dsa.dsa_indexer_flops,
        request.attention_dsa.dsa_indexer_weight_bytes,
        request.attention_dsa.dsa_topk_non_flop_operations,
        request.attention_dsa.other_non_ffn_flops,
        request.attention_dsa.other_non_ffn_non_flop_operations,
        request.attention_dsa.other_non_ffn_weight_bytes,
        request.cache.semantic_kv_read_bytes,
        request.cache.semantic_kv_write_bytes,
        request.cache.dsa_index_lookup_bytes,
        request.cache.dsa_index_store_bytes,
        route.unique_routed_expert_instances,
        route.remote_dispatches,
        route.endpoint_payload_bytes,
        route.endpoint_message_count,
        route.network_hop_payload_bytes,
        route.network_hop_message_count,
        weights.routed_expert_hbm_read_bytes,
        weights.shared_and_dense_ffn_hbm_read_bytes,
        weights.total_ffn_hbm_read_bytes,
        compute.total_flops,
        compute.non_flop_operations,
    ];
    if let MtpDecodeInput::Enabled(mtp) = &request.mtp {
        bounds.extend([
            mtp.draft_flops,
            mtp.verification_flops,
            mtp.state_read_bytes,
            mtp.state_write_bytes,
        ]);
    }
    bounds.extend(
        [
            weights.routed_expert_resident_byte_bounds,
            weights.average_routed_expert_storage_byte_bounds,
            weights.non_routed_resident_byte_bounds,
        ]
        .into_iter()
        .flatten(),
    );
    bounds
}

fn validate_evidence(
    field: &'static str,
    evidence: &EvidenceProvenance,
) -> Result<(), GlmDecodeLoweringError> {
    validate_required(field, &evidence.source_artifact_id)
}

fn validate_required(field: &'static str, value: &str) -> Result<(), GlmDecodeLoweringError> {
    if value.trim().is_empty() {
        Err(GlmDecodeLoweringError::InvalidField(field))
    } else {
        Ok(())
    }
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a GlmDecodeLoweringResult,
}

fn report_content_id(
    schema_version: u32,
    result: &GlmDecodeLoweringResult,
) -> Result<String, GlmDecodeLoweringError> {
    let bytes = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|error| GlmDecodeLoweringError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Debug, Error)]
pub enum GlmDecodeLoweringError {
    #[error("unsupported GLM decode lowering schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid GLM decode lowering field {0}")]
    InvalidField(&'static str),
    #[error("model specification is invalid")]
    InvalidModel,
    #[error("GLM decode lowering requires the hybrid MoE/MLA/DSA architecture")]
    UnsupportedModelArchitecture,
    #[error("GLM decode lowering requires 75 MoE layers, 256 experts, and top-8 routing")]
    UnsupportedGlmGeometry,
    #[error("released GLM active parameter count must remain approximate")]
    ReleasedActiveCountMustRemainApproximate,
    #[error("checkpoint identity or payload does not match the typed model")]
    CheckpointModelMismatch,
    #[error("checkpoint tensor layout is opaque and cannot support exact expert lowering")]
    OpaqueCheckpointLayout,
    #[error("route traffic does not reconcile with model geometry or payload assumptions")]
    RouteTrafficMismatch,
    #[error("decode lowerer internal ledgers did not reconcile")]
    LedgerInvariantViolation,
    #[error("decode lowerer arithmetic overflowed")]
    ArithmeticOverflow,
    #[error("action ledger failed: {0}")]
    Ledger(#[from] LedgerError),
    #[error("decode lowering serialization failed: {0}")]
    Serialization(String),
}
