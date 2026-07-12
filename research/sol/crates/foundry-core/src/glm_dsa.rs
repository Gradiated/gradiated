use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::spec::{HybridMoeMlaDsaSpec, ModelArchitecture, ModelSpec};

pub const GLM_DSA_SWEEP_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const GLM_DSA_SWEEP_REPORT_SCHEMA_VERSION: u32 = 1;
const GLM_5_2_MODEL_ID: &str = "zai-org/GLM-5.2";
const GLM_5_2_MODEL_REVISION: &str = "b4734de4facf877f85769a911abafc5283eab3d9";
const GLM_5_2_FULL_INDEXER_LAYER_IDS: [u32; 21] = [
    0, 1, 2, 6, 10, 14, 18, 22, 26, 30, 34, 38, 42, 46, 50, 54, 58, 62, 66, 70, 74,
];

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DsaEvidenceKind {
    PublishedSpecification,
    MeasuredHardware,
    ModeledAssumption,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DsaEvidence {
    pub kind: DsaEvidenceKind,
    pub source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DsaHardwareProfile {
    pub profile_id: String,
    pub scope_basis: String,
    pub hbm_bytes_per_second: f64,
    pub indexer_flops_per_second: f64,
    pub attention_flops_per_second: f64,
    pub topk_score_candidates_per_second: f64,
    pub evidence: DsaEvidence,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DsaIndexKeyCacheStorage {
    pub value_storage_bits_per_element: u32,
    pub metadata_bytes_per_token: u32,
    pub basis: String,
    pub evidence: DsaEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmDsaSweepRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub model: ModelSpec,
    pub batch_size: u32,
    pub context_tokens_per_request: Vec<u64>,
    pub selected_index_bytes: u32,
    pub full_indexer_layer_ids: Vec<u32>,
    pub index_key_cache_storage: DsaIndexKeyCacheStorage,
    pub hardware: Vec<DsaHardwareProfile>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DsaIndexingWork {
    pub full_indexer_layers: u32,
    pub shared_index_layers: u32,
    pub indexer_projection_flops: u64,
    pub index_score_scan_flops: u64,
    pub index_key_scan_bytes: u64,
    pub indexer_weight_bytes_per_step: u64,
    pub score_candidates: u64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DsaHardwareTiming {
    pub profile_id: String,
    pub evidence: DsaEvidence,
    pub modeled_serial_component_dense_attention_seconds: f64,
    pub modeled_serial_component_indexshare_hbm_handoff_seconds: f64,
    pub modeled_serial_component_indexshare_zero_hbm_handoff_upper_bound_seconds: f64,
    pub modeled_serial_component_same_geometry_every_layer_indexing_seconds: f64,
    pub component_time_ratio_dense_attention_over_indexshare_hbm_handoff: f64,
    pub component_time_ratio_same_geometry_every_layer_indexing_over_indexshare_hbm_handoff: f64,
    pub component_time_ratio_indexshare_hbm_handoff_over_zero_hbm_handoff_upper_bound: f64,
    pub indexshare_components: DsaTimingComponents,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DsaTimingComponents {
    pub modeled_serial_component_projection_roofline_seconds: f64,
    pub modeled_serial_component_scan_roofline_seconds: f64,
    pub modeled_serial_component_topk_seconds: f64,
    pub modeled_serial_component_sparse_attention_roofline_seconds: f64,
    pub modeled_serial_component_hbm_handoff_seconds: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DsaSweepPoint {
    pub context_tokens_per_request: u64,
    pub selected_tokens_per_request: u64,
    pub decode_query_tokens: u64,
    pub semantic_cache_bytes_per_layer_token: u64,
    pub index_key_bytes_per_full_indexer_token: u64,
    pub indexshare: DsaIndexingWork,
    pub same_geometry_every_layer_indexing_counterfactual: DsaIndexingWork,
    pub sparse_attention_flops: u64,
    pub sparse_cache_read_bytes: u64,
    pub dense_attention_flops: u64,
    pub dense_cache_read_bytes: u64,
    pub hbm_index_topk_write_bytes: u64,
    pub hbm_index_attention_read_bytes: u64,
    pub hbm_index_handoff_bytes: u64,
    pub zero_hbm_handoff_upper_bound_hbm_bytes: u64,
    pub indexshare_scan_reduction_fraction: f64,
    pub sparse_cache_read_reduction_fraction: f64,
    pub hardware: Vec<DsaHardwareTiming>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DsaClaimBlocker {
    ProjectionAndTopkWorkAreAnalyticalProxies,
    IrregularGatherEfficiencyNotCalibrated,
    HardwareTimingNotMeasured,
    PeakSerialRooflineAndUtilizationNotCalibrated,
    ResidencyAndDistributedMappingNotModeled,
    SramCapacityBandwidthAndLatencyNotModeled,
    RemainingModelWorkNotModeled,
    ServingAndContentionNotModeled,
    QualityContractNotProvided,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DsaClaimGate {
    pub end_to_end_latency_claim_permitted: bool,
    pub cost_per_token_claim_permitted: bool,
    pub quality_claim_permitted: bool,
    pub blockers: Vec<DsaClaimBlocker>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmDsaSweepResult {
    pub study_id: String,
    pub model_id: String,
    pub model_revision: String,
    pub batch_size: u32,
    pub layer_count: u32,
    pub full_indexer_layer_count: u32,
    pub shared_index_layer_count: u32,
    pub selected_token_count: u32,
    pub selected_index_bytes: u32,
    pub full_indexer_layer_ids: Vec<u32>,
    pub index_key_cache_storage: DsaIndexKeyCacheStorage,
    pub work_basis: String,
    pub points: Vec<DsaSweepPoint>,
    pub claims: DsaClaimGate,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmDsaSweepReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: GlmDsaSweepResult,
}

impl GlmDsaSweepReport {
    pub fn verify_content_id(&self) -> Result<bool, GlmDsaSweepError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

pub fn evaluate_glm_dsa_sweep(
    request: &GlmDsaSweepRequest,
) -> Result<GlmDsaSweepReport, GlmDsaSweepError> {
    let hybrid = validate_request(request)?;
    let points = request
        .context_tokens_per_request
        .iter()
        .map(|context| evaluate_point(request, hybrid, *context))
        .collect::<Result<Vec<_>, _>>()?;
    let result = GlmDsaSweepResult {
        study_id: request.study_id.clone(),
        model_id: request.model.model_id.clone(),
        model_revision: request.model.model_revision.clone(),
        batch_size: request.batch_size,
        layer_count: request.model.layer_count,
        full_indexer_layer_count: hybrid.dsa_indexer.full_layer_count,
        shared_index_layer_count: hybrid.dsa_indexer.shared_layer_count,
        selected_token_count: hybrid.dsa_indexer.selected_token_count,
        selected_index_bytes: request.selected_index_bytes,
        full_indexer_layer_ids: request.full_indexer_layer_ids.clone(),
        index_key_cache_storage: request.index_key_cache_storage.clone(),
        work_basis: format!(
            "Decode-step analytical operation and byte counts. Index projection uses two FLOPs per released indexer parameter; scan uses one multiply-add per query-head key element; top-k counts scored candidates. Attention uses absorbed MLA core arithmetic over semantic latent and rotary state; common per-step query and output absorption transforms are excluded. Main-cache traffic uses compressed semantic MLA state. Index-key traffic uses the independent typed storage scenario including per-token metadata. The HBM IndexShare handoff counts {} top-k writes plus {} attention reads for the supplied layer pattern; the zero-HBM-handoff upper bound removes only this HBM traffic and does not model SRAM movement. Allocator, scale metadata outside the typed index-key scenario, paging metadata, transaction amplification, distributed mapping, overlap, and utilization are excluded. Every-layer indexing is a same-geometry analytical counterfactual, not a GLM-5.1 deployment measurement.",
            hybrid.dsa_indexer.full_layer_count, request.model.layer_count
        ),
        points,
        claims: claim_gate(request),
    };
    let schema_version = GLM_DSA_SWEEP_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(GlmDsaSweepReport {
        schema_version,
        content_id,
        result,
    })
}

fn validate_request(
    request: &GlmDsaSweepRequest,
) -> Result<&HybridMoeMlaDsaSpec, GlmDsaSweepError> {
    if request.schema_version != GLM_DSA_SWEEP_REQUEST_SCHEMA_VERSION {
        return Err(GlmDsaSweepError::UnsupportedSchemaVersion {
            expected: GLM_DSA_SWEEP_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    validate_required("study_id", &request.study_id)?;
    request
        .model
        .validate()
        .map_err(|_| GlmDsaSweepError::InvalidModel)?;
    let ModelArchitecture::HybridMoeMlaDsa(hybrid) = &request.model.architecture else {
        return Err(GlmDsaSweepError::UnsupportedModelArchitecture);
    };
    if request.batch_size == 0 {
        return Err(GlmDsaSweepError::InvalidField("batch_size"));
    }
    if request.context_tokens_per_request.is_empty() {
        return Err(GlmDsaSweepError::InvalidField("context_tokens_per_request"));
    }
    let mut contexts = BTreeSet::new();
    for context in &request.context_tokens_per_request {
        if *context == 0
            || *context > u64::from(request.model.max_sequence_length)
            || !contexts.insert(*context)
        {
            return Err(GlmDsaSweepError::InvalidField("context_tokens_per_request"));
        }
    }
    if request.selected_index_bytes == 0 {
        return Err(GlmDsaSweepError::InvalidField("selected_index_bytes"));
    }
    let max_context = *contexts
        .last()
        .ok_or(GlmDsaSweepError::InvalidField("context_tokens_per_request"))?;
    let required_index_bits = u64::BITS - max_context.saturating_sub(1).leading_zeros();
    if u64::from(request.selected_index_bytes) * 8 < u64::from(required_index_bits) {
        return Err(GlmDsaSweepError::InvalidField("selected_index_bytes"));
    }
    if hybrid.dsa_indexer.query_head_dimension != hybrid.dsa_indexer.key_head_dimension {
        return Err(GlmDsaSweepError::InvalidField(
            "model.architecture.dsa_indexer.query_head_dimension",
        ));
    }
    if hybrid.dsa_indexer.key_head_count != 1 {
        return Err(GlmDsaSweepError::InvalidField(
            "model.architecture.dsa_indexer.key_head_count",
        ));
    }
    let expected_full_layer_count = usize::try_from(hybrid.dsa_indexer.full_layer_count)
        .map_err(|_| GlmDsaSweepError::ArithmeticOverflow)?;
    let expected_shared_layer_count = usize::try_from(hybrid.dsa_indexer.shared_layer_count)
        .map_err(|_| GlmDsaSweepError::ArithmeticOverflow)?;
    let actual_shared_layer_count = usize::try_from(request.model.layer_count)
        .map_err(|_| GlmDsaSweepError::ArithmeticOverflow)?
        .checked_sub(request.full_indexer_layer_ids.len());
    if request.full_indexer_layer_ids.len() != expected_full_layer_count
        || actual_shared_layer_count != Some(expected_shared_layer_count)
        || request
            .full_indexer_layer_ids
            .iter()
            .any(|layer_id| *layer_id >= request.model.layer_count)
        || request
            .full_indexer_layer_ids
            .windows(2)
            .any(|layers| layers[0] >= layers[1])
    {
        return Err(GlmDsaSweepError::InvalidField("full_indexer_layer_ids"));
    }
    if request.model.model_id == GLM_5_2_MODEL_ID
        && request.model.model_revision == GLM_5_2_MODEL_REVISION
        && request.full_indexer_layer_ids.as_slice() != GLM_5_2_FULL_INDEXER_LAYER_IDS
    {
        return Err(GlmDsaSweepError::InvalidField("full_indexer_layer_ids"));
    }
    if request
        .index_key_cache_storage
        .value_storage_bits_per_element
        == 0
    {
        return Err(GlmDsaSweepError::InvalidField(
            "index_key_cache_storage.value_storage_bits_per_element",
        ));
    }
    validate_required(
        "index_key_cache_storage.basis",
        &request.index_key_cache_storage.basis,
    )?;
    validate_required(
        "index_key_cache_storage.evidence.source_artifact_id",
        &request.index_key_cache_storage.evidence.source_artifact_id,
    )?;
    if request.hardware.is_empty() {
        return Err(GlmDsaSweepError::InvalidField("hardware"));
    }
    let mut profile_ids = BTreeSet::new();
    for profile in &request.hardware {
        validate_required("hardware.profile_id", &profile.profile_id)?;
        validate_required("hardware.scope_basis", &profile.scope_basis)?;
        validate_required(
            "hardware.evidence.source_artifact_id",
            &profile.evidence.source_artifact_id,
        )?;
        if !profile_ids.insert(profile.profile_id.as_str()) {
            return Err(GlmDsaSweepError::DuplicateHardwareProfile(
                profile.profile_id.clone(),
            ));
        }
        for (field, value) in [
            (
                "hardware.hbm_bytes_per_second",
                profile.hbm_bytes_per_second,
            ),
            (
                "hardware.indexer_flops_per_second",
                profile.indexer_flops_per_second,
            ),
            (
                "hardware.attention_flops_per_second",
                profile.attention_flops_per_second,
            ),
            (
                "hardware.topk_score_candidates_per_second",
                profile.topk_score_candidates_per_second,
            ),
        ] {
            if !value.is_finite() || value <= 0.0 {
                return Err(GlmDsaSweepError::InvalidField(field));
            }
        }
    }
    Ok(hybrid)
}

fn evaluate_point(
    request: &GlmDsaSweepRequest,
    hybrid: &HybridMoeMlaDsaSpec,
    context: u64,
) -> Result<DsaSweepPoint, GlmDsaSweepError> {
    let decode_query_tokens = u64::from(request.batch_size);
    let selected = context.min(u64::from(hybrid.dsa_indexer.selected_token_count));
    let semantic_elements = u64::from(hybrid.mla.semantic_kv_dimension)
        .checked_add(u64::from(hybrid.mla.rotary_kv_dimension))
        .ok_or(GlmDsaSweepError::ArithmeticOverflow)?;
    let semantic_cache_bytes_per_layer_token = packed_bytes(
        semantic_elements,
        u64::from(request.model.kv_precision.bits()),
    )?;
    let index_key_bytes_per_full_indexer_token = index_key_bytes_per_token(request, hybrid)?;
    let indexshare = indexing_work(
        request,
        hybrid,
        context,
        hybrid.dsa_indexer.full_layer_count,
    )?;
    let same_geometry_every_layer_indexing_counterfactual =
        indexing_work(request, hybrid, context, request.model.layer_count)?;
    let attention_flops_per_position = checked_product(&[
        2,
        u64::from(request.model.attention_head_count),
        u64::from(
            hybrid
                .mla
                .semantic_kv_dimension
                .checked_add(hybrid.mla.rotary_kv_dimension)
                .and_then(|qk| qk.checked_add(hybrid.mla.semantic_kv_dimension))
                .ok_or(GlmDsaSweepError::ArithmeticOverflow)?,
        ),
    ])?;
    let sparse_attention_flops = checked_product(&[
        decode_query_tokens,
        u64::from(request.model.layer_count),
        selected,
        attention_flops_per_position,
    ])?;
    let dense_attention_flops = checked_product(&[
        decode_query_tokens,
        u64::from(request.model.layer_count),
        context,
        attention_flops_per_position,
    ])?;
    let sparse_cache_read_bytes = checked_product(&[
        decode_query_tokens,
        u64::from(request.model.layer_count),
        selected,
        semantic_cache_bytes_per_layer_token,
    ])?;
    let dense_cache_read_bytes = checked_product(&[
        decode_query_tokens,
        u64::from(request.model.layer_count),
        context,
        semantic_cache_bytes_per_layer_token,
    ])?;
    let hbm_index_topk_write_bytes = checked_product(&[
        decode_query_tokens,
        u64::from(hybrid.dsa_indexer.full_layer_count),
        selected,
        u64::from(request.selected_index_bytes),
    ])?;
    let hbm_index_attention_read_bytes = checked_product(&[
        decode_query_tokens,
        u64::from(request.model.layer_count),
        selected,
        u64::from(request.selected_index_bytes),
    ])?;
    let hbm_index_handoff_bytes = hbm_index_topk_write_bytes
        .checked_add(hbm_index_attention_read_bytes)
        .ok_or(GlmDsaSweepError::ArithmeticOverflow)?;
    let hardware = request
        .hardware
        .iter()
        .map(|profile| {
            evaluate_timing(
                profile,
                &indexshare,
                &same_geometry_every_layer_indexing_counterfactual,
                sparse_attention_flops,
                sparse_cache_read_bytes,
                dense_attention_flops,
                dense_cache_read_bytes,
                hbm_index_handoff_bytes,
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    Ok(DsaSweepPoint {
        context_tokens_per_request: context,
        selected_tokens_per_request: selected,
        decode_query_tokens,
        semantic_cache_bytes_per_layer_token,
        index_key_bytes_per_full_indexer_token,
        indexshare,
        same_geometry_every_layer_indexing_counterfactual,
        sparse_attention_flops,
        sparse_cache_read_bytes,
        dense_attention_flops,
        dense_cache_read_bytes,
        hbm_index_topk_write_bytes,
        hbm_index_attention_read_bytes,
        hbm_index_handoff_bytes,
        zero_hbm_handoff_upper_bound_hbm_bytes: 0,
        indexshare_scan_reduction_fraction: f64::from(
            request.model.layer_count - hybrid.dsa_indexer.full_layer_count,
        ) / f64::from(request.model.layer_count),
        sparse_cache_read_reduction_fraction: 1.0 - selected as f64 / context as f64,
        hardware,
    })
}

fn indexing_work(
    request: &GlmDsaSweepRequest,
    hybrid: &HybridMoeMlaDsaSpec,
    context: u64,
    full_indexer_layers: u32,
) -> Result<DsaIndexingWork, GlmDsaSweepError> {
    let decode_query_tokens = u64::from(request.batch_size);
    let projection_parameters = request
        .model
        .dsa_indexer_parameters_per_full_layer()
        .ok_or(GlmDsaSweepError::ArithmeticOverflow)?;
    let indexer_projection_flops = checked_product(&[
        decode_query_tokens,
        u64::from(full_indexer_layers),
        projection_parameters,
        2,
    ])?;
    let scan_flops_per_context_token = checked_product(&[
        u64::from(hybrid.dsa_indexer.query_head_count),
        u64::from(hybrid.dsa_indexer.key_head_dimension),
        2,
    ])?;
    let index_score_scan_flops = checked_product(&[
        decode_query_tokens,
        u64::from(full_indexer_layers),
        context,
        scan_flops_per_context_token,
    ])?;
    let index_key_bytes = index_key_bytes_per_token(request, hybrid)?;
    let index_key_scan_bytes = checked_product(&[
        decode_query_tokens,
        u64::from(full_indexer_layers),
        context,
        index_key_bytes,
    ])?;
    let weight_bytes_per_indexer = packed_bytes(
        projection_parameters,
        u64::from(request.model.weight_precision.bits()),
    )?;
    let indexer_weight_bytes_per_step =
        checked_product(&[u64::from(full_indexer_layers), weight_bytes_per_indexer])?;
    let score_candidates =
        checked_product(&[decode_query_tokens, u64::from(full_indexer_layers), context])?;
    Ok(DsaIndexingWork {
        full_indexer_layers,
        shared_index_layers: request.model.layer_count - full_indexer_layers,
        indexer_projection_flops,
        index_score_scan_flops,
        index_key_scan_bytes,
        indexer_weight_bytes_per_step,
        score_candidates,
    })
}

fn index_key_bytes_per_token(
    request: &GlmDsaSweepRequest,
    hybrid: &HybridMoeMlaDsaSpec,
) -> Result<u64, GlmDsaSweepError> {
    let elements = checked_product(&[
        u64::from(hybrid.dsa_indexer.key_head_count),
        u64::from(hybrid.dsa_indexer.key_head_dimension),
    ])?;
    packed_bytes(
        elements,
        u64::from(
            request
                .index_key_cache_storage
                .value_storage_bits_per_element,
        ),
    )?
    .checked_add(u64::from(
        request.index_key_cache_storage.metadata_bytes_per_token,
    ))
    .ok_or(GlmDsaSweepError::ArithmeticOverflow)
}

#[allow(clippy::too_many_arguments)]
fn evaluate_timing(
    profile: &DsaHardwareProfile,
    indexshare: &DsaIndexingWork,
    every_layer: &DsaIndexingWork,
    sparse_attention_flops: u64,
    sparse_cache_read_bytes: u64,
    dense_attention_flops: u64,
    dense_cache_read_bytes: u64,
    hbm_handoff_bytes: u64,
) -> Result<DsaHardwareTiming, GlmDsaSweepError> {
    let components = timing_components(
        profile,
        indexshare,
        sparse_attention_flops,
        sparse_cache_read_bytes,
        hbm_handoff_bytes,
    );
    let indexshare_hbm = components.modeled_serial_component_projection_roofline_seconds
        + components.modeled_serial_component_scan_roofline_seconds
        + components.modeled_serial_component_topk_seconds
        + components.modeled_serial_component_sparse_attention_roofline_seconds
        + components.modeled_serial_component_hbm_handoff_seconds;
    let indexshare_zero_hbm_handoff_upper_bound =
        indexshare_hbm - components.modeled_serial_component_hbm_handoff_seconds;
    let every_components = timing_components(
        profile,
        every_layer,
        sparse_attention_flops,
        sparse_cache_read_bytes,
        0,
    );
    let every_layer_seconds = every_components.modeled_serial_component_projection_roofline_seconds
        + every_components.modeled_serial_component_scan_roofline_seconds
        + every_components.modeled_serial_component_topk_seconds
        + every_components.modeled_serial_component_sparse_attention_roofline_seconds;
    let dense_attention_seconds = roofline(
        dense_attention_flops,
        profile.attention_flops_per_second,
        dense_cache_read_bytes,
        profile.hbm_bytes_per_second,
    );
    if ![
        indexshare_hbm,
        indexshare_zero_hbm_handoff_upper_bound,
        every_layer_seconds,
        dense_attention_seconds,
    ]
    .iter()
    .all(|value| value.is_finite() && *value > 0.0)
    {
        return Err(GlmDsaSweepError::ArithmeticOverflow);
    }
    Ok(DsaHardwareTiming {
        profile_id: profile.profile_id.clone(),
        evidence: profile.evidence.clone(),
        modeled_serial_component_dense_attention_seconds: dense_attention_seconds,
        modeled_serial_component_indexshare_hbm_handoff_seconds: indexshare_hbm,
        modeled_serial_component_indexshare_zero_hbm_handoff_upper_bound_seconds:
            indexshare_zero_hbm_handoff_upper_bound,
        modeled_serial_component_same_geometry_every_layer_indexing_seconds: every_layer_seconds,
        component_time_ratio_dense_attention_over_indexshare_hbm_handoff: dense_attention_seconds
            / indexshare_hbm,
        component_time_ratio_same_geometry_every_layer_indexing_over_indexshare_hbm_handoff:
            every_layer_seconds / indexshare_hbm,
        component_time_ratio_indexshare_hbm_handoff_over_zero_hbm_handoff_upper_bound:
            indexshare_hbm / indexshare_zero_hbm_handoff_upper_bound,
        indexshare_components: components,
    })
}

fn timing_components(
    profile: &DsaHardwareProfile,
    indexing: &DsaIndexingWork,
    attention_flops: u64,
    cache_read_bytes: u64,
    hbm_handoff_bytes: u64,
) -> DsaTimingComponents {
    DsaTimingComponents {
        modeled_serial_component_projection_roofline_seconds: roofline(
            indexing.indexer_projection_flops,
            profile.indexer_flops_per_second,
            indexing.indexer_weight_bytes_per_step,
            profile.hbm_bytes_per_second,
        ),
        modeled_serial_component_scan_roofline_seconds: roofline(
            indexing.index_score_scan_flops,
            profile.indexer_flops_per_second,
            indexing.index_key_scan_bytes,
            profile.hbm_bytes_per_second,
        ),
        modeled_serial_component_topk_seconds: indexing.score_candidates as f64
            / profile.topk_score_candidates_per_second,
        modeled_serial_component_sparse_attention_roofline_seconds: roofline(
            attention_flops,
            profile.attention_flops_per_second,
            cache_read_bytes,
            profile.hbm_bytes_per_second,
        ),
        modeled_serial_component_hbm_handoff_seconds: hbm_handoff_bytes as f64
            / profile.hbm_bytes_per_second,
    }
}

fn roofline(flops: u64, flops_per_second: f64, bytes: u64, bytes_per_second: f64) -> f64 {
    (flops as f64 / flops_per_second).max(bytes as f64 / bytes_per_second)
}

fn claim_gate(request: &GlmDsaSweepRequest) -> DsaClaimGate {
    let mut blockers = vec![
        DsaClaimBlocker::ProjectionAndTopkWorkAreAnalyticalProxies,
        DsaClaimBlocker::IrregularGatherEfficiencyNotCalibrated,
    ];
    if request
        .hardware
        .iter()
        .any(|profile| profile.evidence.kind != DsaEvidenceKind::MeasuredHardware)
    {
        blockers.push(DsaClaimBlocker::HardwareTimingNotMeasured);
    }
    blockers.extend([
        DsaClaimBlocker::PeakSerialRooflineAndUtilizationNotCalibrated,
        DsaClaimBlocker::ResidencyAndDistributedMappingNotModeled,
        DsaClaimBlocker::SramCapacityBandwidthAndLatencyNotModeled,
        DsaClaimBlocker::RemainingModelWorkNotModeled,
        DsaClaimBlocker::ServingAndContentionNotModeled,
        DsaClaimBlocker::QualityContractNotProvided,
    ]);
    DsaClaimGate {
        end_to_end_latency_claim_permitted: false,
        cost_per_token_claim_permitted: false,
        quality_claim_permitted: false,
        blockers,
    }
}

fn checked_product(values: &[u64]) -> Result<u64, GlmDsaSweepError> {
    let product = values.iter().try_fold(1_u128, |product, value| {
        product.checked_mul(u128::from(*value))
    });
    product
        .and_then(|value| u64::try_from(value).ok())
        .ok_or(GlmDsaSweepError::ArithmeticOverflow)
}

fn packed_bytes(elements: u64, bits: u64) -> Result<u64, GlmDsaSweepError> {
    let total_bits = u128::from(elements)
        .checked_mul(u128::from(bits))
        .ok_or(GlmDsaSweepError::ArithmeticOverflow)?;
    u64::try_from(total_bits.div_ceil(8)).map_err(|_| GlmDsaSweepError::ArithmeticOverflow)
}

fn validate_required(field: &'static str, value: &str) -> Result<(), GlmDsaSweepError> {
    if value.trim().is_empty() {
        Err(GlmDsaSweepError::InvalidField(field))
    } else {
        Ok(())
    }
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a GlmDsaSweepResult,
}

fn report_content_id(
    schema_version: u32,
    result: &GlmDsaSweepResult,
) -> Result<String, GlmDsaSweepError> {
    let bytes = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|error| GlmDsaSweepError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum GlmDsaSweepError {
    #[error("unsupported GLM DSA sweep schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid GLM DSA sweep field {0}")]
    InvalidField(&'static str),
    #[error("the model specification is invalid")]
    InvalidModel,
    #[error("GLM DSA sweeps require a hybrid MoE/MLA/DSA model")]
    UnsupportedModelArchitecture,
    #[error("duplicate DSA hardware profile {0}")]
    DuplicateHardwareProfile(String),
    #[error("GLM DSA sweep arithmetic overflowed")]
    ArithmeticOverflow,
    #[error("GLM DSA sweep serialization failed: {0}")]
    Serialization(String),
}
