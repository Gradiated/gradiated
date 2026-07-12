use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::glm_storage::{
    DeploymentCapacityStatus, EnvelopeEvidenceKind, GLM_STORAGE_ENVELOPE_REPORT_SCHEMA_VERSION,
    GlmStorageEnvelopeError, GlmStorageEnvelopeReport, GlmVariantEnvelopeReport,
    HardwareVariantEnvelopeReport,
};
use crate::ledger_roofline::{
    HardwareRooflineReport, HardwareTimingEvidenceKind, LEDGER_ROOFLINE_REPORT_SCHEMA_VERSION,
    LedgerRooflineClaimBlocker, LedgerRooflineError, LedgerRooflineReport,
};

pub const DEPLOYMENT_SCREEN_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const DEPLOYMENT_SCREEN_REPORT_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum RooflineTimingScope {
    WholeDeployment,
    PerRank { rank_count: u32 },
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BreakEvenHurdleScope {
    RequiredPeakThroughputAlreadyLoadAdjusted,
    RequiredDeliveredThroughput,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DeploymentScreenRequest {
    pub schema_version: u32,
    pub screen_id: String,
    pub storage_report_content_id: String,
    pub roofline_report_content_id: String,
    pub variant_id: String,
    pub storage_hardware_id: String,
    pub roofline_hardware_id: String,
    pub timing_scope: RooflineTimingScope,
    pub break_even_hurdle_scope: BreakEvenHurdleScope,
    pub billable_tokens_per_committed_output_token: f64,
    pub useful_load_factor: f64,
    pub availability_factor: f64,
    pub input_prefill_work_included_in_roofline: bool,
    pub mapping_source_artifact_id: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DeploymentRejectionReason {
    CapacityInfeasible,
    CapacityUncertain,
    OptimisticThroughputBelowBreakEven,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DeploymentClaimBlocker {
    OptimisticRejectionBoundOnly,
    InputPrefillWorkTreatedAsFree,
    PerRankLinearScalingAssumption,
    LedgerContainsModeledWork,
    HardwareTimingIsModeledOrUncalibrated,
    StorageEnvelopeContainsModeledInputs,
    SharedResourceContentionIsNotModeled,
    ServingAndQueueingAreNotModeled,
    EndToEndCostModelIsAbsent,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DeploymentScreenClaimGate {
    pub business_viability_claim_permitted: bool,
    pub end_to_end_cost_claim_permitted: bool,
    pub provider_comparison_claim_permitted: bool,
    pub blockers: Vec<DeploymentClaimBlocker>,
    pub source_roofline_blockers: Vec<LedgerRooflineClaimBlocker>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DeploymentScreenResult {
    pub screen_id: String,
    pub storage_report_content_id: String,
    pub roofline_report_content_id: String,
    pub variant_id: String,
    pub storage_hardware_id: String,
    pub roofline_hardware_id: String,
    pub deployment_device_count: u32,
    pub timing_scope: RooflineTimingScope,
    pub break_even_hurdle_scope: BreakEvenHurdleScope,
    pub billable_tokens_per_committed_output_token: f64,
    pub useful_load_factor: f64,
    pub availability_factor: f64,
    pub input_prefill_work_included_in_roofline: bool,
    pub mapping_source_artifact_id: String,
    pub capacity_status: DeploymentCapacityStatus,
    pub roofline_optimistic_committed_output_tokens_per_second: f64,
    pub optimistic_peak_billable_tokens_per_second_upper_bound: f64,
    pub optimistic_effective_billable_tokens_per_second_upper_bound: f64,
    pub optimistic_billable_tokens_per_second_compared_to_hurdle: f64,
    pub required_billable_tokens_per_second_for_deployment: f64,
    pub optimistic_headroom_ratio: f64,
    pub optimistic_hurdle_cleared: bool,
    pub candidate_rejected: bool,
    pub rejection_reasons: Vec<DeploymentRejectionReason>,
    pub claims: DeploymentScreenClaimGate,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DeploymentScreenReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: DeploymentScreenResult,
}

impl DeploymentScreenReport {
    pub fn verify_content_id(&self) -> Result<bool, DeploymentScreenError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

pub fn evaluate_deployment_screen(
    request: &DeploymentScreenRequest,
    storage: &GlmStorageEnvelopeReport,
    roofline: &LedgerRooflineReport,
) -> Result<DeploymentScreenReport, DeploymentScreenError> {
    validate_request(request)?;
    validate_artifact_identities(request, storage, roofline)?;

    let variant = select_variant(storage, &request.variant_id)?;
    let storage_hardware = select_storage_hardware(variant, &request.storage_hardware_id)?;
    let roofline_hardware = select_roofline_hardware(roofline, &request.roofline_hardware_id)?;
    let scope_multiplier = timing_scope_multiplier(request.timing_scope, storage_hardware)?;
    let break_even = storage_hardware
        .break_even
        .as_ref()
        .ok_or(DeploymentScreenError::MissingBreakEvenHurdle)?;

    validate_positive(
        "roofline.optimistic_committed_tokens_per_second",
        roofline_hardware.optimistic_committed_tokens_per_second,
    )?;
    validate_positive(
        "storage.required_billable_tokens_per_second_for_deployment",
        break_even.required_billable_tokens_per_second_for_deployment,
    )?;
    if roofline.result.committed_tokens == 0 {
        return Err(DeploymentScreenError::InvalidField(
            "roofline.committed_tokens",
        ));
    }

    let optimistic_peak_bound = roofline_hardware.optimistic_committed_tokens_per_second
        * scope_multiplier
        * request.billable_tokens_per_committed_output_token;
    validate_positive(
        "optimistic_peak_billable_tokens_per_second_upper_bound",
        optimistic_peak_bound,
    )?;
    let optimistic_effective_bound =
        optimistic_peak_bound * request.useful_load_factor * request.availability_factor;
    validate_positive(
        "optimistic_effective_billable_tokens_per_second_upper_bound",
        optimistic_effective_bound,
    )?;
    let hurdle = break_even.required_billable_tokens_per_second_for_deployment;
    let optimistic_comparison_bound = match request.break_even_hurdle_scope {
        BreakEvenHurdleScope::RequiredPeakThroughputAlreadyLoadAdjusted => optimistic_peak_bound,
        BreakEvenHurdleScope::RequiredDeliveredThroughput => optimistic_effective_bound,
    };
    let optimistic_headroom_ratio = optimistic_comparison_bound / hurdle;
    validate_positive("optimistic_headroom_ratio", optimistic_headroom_ratio)?;
    let optimistic_hurdle_cleared = optimistic_comparison_bound >= hurdle;
    let rejection_reasons = rejection_reasons(
        storage_hardware.deployment_capacity_status,
        optimistic_hurdle_cleared,
    );
    let claims = claim_gate(
        request,
        variant,
        storage_hardware,
        roofline_hardware,
        roofline,
    );
    let result = DeploymentScreenResult {
        screen_id: request.screen_id.clone(),
        storage_report_content_id: storage.content_id.clone(),
        roofline_report_content_id: roofline.content_id.clone(),
        variant_id: request.variant_id.clone(),
        storage_hardware_id: request.storage_hardware_id.clone(),
        roofline_hardware_id: request.roofline_hardware_id.clone(),
        deployment_device_count: storage_hardware.deployment_device_count,
        timing_scope: request.timing_scope,
        break_even_hurdle_scope: request.break_even_hurdle_scope,
        billable_tokens_per_committed_output_token: request
            .billable_tokens_per_committed_output_token,
        useful_load_factor: request.useful_load_factor,
        availability_factor: request.availability_factor,
        input_prefill_work_included_in_roofline: request.input_prefill_work_included_in_roofline,
        mapping_source_artifact_id: request.mapping_source_artifact_id.clone(),
        capacity_status: storage_hardware.deployment_capacity_status,
        roofline_optimistic_committed_output_tokens_per_second: roofline_hardware
            .optimistic_committed_tokens_per_second,
        optimistic_peak_billable_tokens_per_second_upper_bound: optimistic_peak_bound,
        optimistic_effective_billable_tokens_per_second_upper_bound: optimistic_effective_bound,
        optimistic_billable_tokens_per_second_compared_to_hurdle: optimistic_comparison_bound,
        required_billable_tokens_per_second_for_deployment: hurdle,
        optimistic_headroom_ratio,
        optimistic_hurdle_cleared,
        candidate_rejected: !rejection_reasons.is_empty(),
        rejection_reasons,
        claims,
    };
    let schema_version = DEPLOYMENT_SCREEN_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(DeploymentScreenReport {
        schema_version,
        content_id,
        result,
    })
}

fn validate_request(request: &DeploymentScreenRequest) -> Result<(), DeploymentScreenError> {
    if request.schema_version != DEPLOYMENT_SCREEN_REQUEST_SCHEMA_VERSION {
        return Err(DeploymentScreenError::UnsupportedSchemaVersion {
            expected: DEPLOYMENT_SCREEN_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    for (field, value) in [
        ("screen_id", request.screen_id.as_str()),
        (
            "storage_report_content_id",
            request.storage_report_content_id.as_str(),
        ),
        (
            "roofline_report_content_id",
            request.roofline_report_content_id.as_str(),
        ),
        ("variant_id", request.variant_id.as_str()),
        ("storage_hardware_id", request.storage_hardware_id.as_str()),
        (
            "roofline_hardware_id",
            request.roofline_hardware_id.as_str(),
        ),
        (
            "mapping_source_artifact_id",
            request.mapping_source_artifact_id.as_str(),
        ),
    ] {
        validate_required(field, value)?;
    }
    if !request
        .billable_tokens_per_committed_output_token
        .is_finite()
        || request.billable_tokens_per_committed_output_token < 1.0
    {
        return Err(DeploymentScreenError::InvalidField(
            "billable_tokens_per_committed_output_token",
        ));
    }
    validate_factor("useful_load_factor", request.useful_load_factor)?;
    validate_factor("availability_factor", request.availability_factor)?;
    if let RooflineTimingScope::PerRank { rank_count: 0 } = request.timing_scope {
        return Err(DeploymentScreenError::InvalidField(
            "timing_scope.rank_count",
        ));
    }
    Ok(())
}

fn validate_artifact_identities(
    request: &DeploymentScreenRequest,
    storage: &GlmStorageEnvelopeReport,
    roofline: &LedgerRooflineReport,
) -> Result<(), DeploymentScreenError> {
    if storage.schema_version != GLM_STORAGE_ENVELOPE_REPORT_SCHEMA_VERSION {
        return Err(DeploymentScreenError::UnsupportedStorageSchemaVersion {
            expected: GLM_STORAGE_ENVELOPE_REPORT_SCHEMA_VERSION,
            actual: storage.schema_version,
        });
    }
    if roofline.schema_version != LEDGER_ROOFLINE_REPORT_SCHEMA_VERSION {
        return Err(DeploymentScreenError::UnsupportedRooflineSchemaVersion {
            expected: LEDGER_ROOFLINE_REPORT_SCHEMA_VERSION,
            actual: roofline.schema_version,
        });
    }
    if !storage
        .verify_content_id()
        .map_err(DeploymentScreenError::StorageArtifactVerification)?
    {
        return Err(DeploymentScreenError::InvalidStorageArtifactIdentity);
    }
    if !roofline
        .verify_content_id()
        .map_err(DeploymentScreenError::RooflineArtifactVerification)?
    {
        return Err(DeploymentScreenError::InvalidRooflineArtifactIdentity);
    }
    if request.storage_report_content_id != storage.content_id {
        return Err(DeploymentScreenError::StorageArtifactIdentityMismatch);
    }
    if request.roofline_report_content_id != roofline.content_id {
        return Err(DeploymentScreenError::RooflineArtifactIdentityMismatch);
    }
    Ok(())
}

fn select_variant<'a>(
    storage: &'a GlmStorageEnvelopeReport,
    variant_id: &str,
) -> Result<&'a GlmVariantEnvelopeReport, DeploymentScreenError> {
    let mut matches = storage
        .result
        .variants
        .iter()
        .filter(|variant| variant.variant_id == variant_id);
    let selected = matches
        .next()
        .ok_or_else(|| DeploymentScreenError::UnknownVariant(variant_id.into()))?;
    if matches.next().is_some() {
        return Err(DeploymentScreenError::DuplicateVariant(variant_id.into()));
    }
    Ok(selected)
}

fn select_storage_hardware<'a>(
    variant: &'a GlmVariantEnvelopeReport,
    hardware_id: &str,
) -> Result<&'a HardwareVariantEnvelopeReport, DeploymentScreenError> {
    let mut matches = variant
        .hardware
        .iter()
        .filter(|hardware| hardware.hardware_id == hardware_id);
    let selected = matches
        .next()
        .ok_or_else(|| DeploymentScreenError::UnknownStorageHardware(hardware_id.into()))?;
    if matches.next().is_some() {
        return Err(DeploymentScreenError::DuplicateStorageHardware(
            hardware_id.into(),
        ));
    }
    Ok(selected)
}

fn select_roofline_hardware<'a>(
    roofline: &'a LedgerRooflineReport,
    hardware_id: &str,
) -> Result<&'a HardwareRooflineReport, DeploymentScreenError> {
    let mut matches = roofline
        .result
        .hardware
        .iter()
        .filter(|hardware| hardware.hardware_id == hardware_id);
    let selected = matches
        .next()
        .ok_or_else(|| DeploymentScreenError::UnknownRooflineHardware(hardware_id.into()))?;
    if matches.next().is_some() {
        return Err(DeploymentScreenError::DuplicateRooflineHardware(
            hardware_id.into(),
        ));
    }
    Ok(selected)
}

fn timing_scope_multiplier(
    scope: RooflineTimingScope,
    storage_hardware: &HardwareVariantEnvelopeReport,
) -> Result<f64, DeploymentScreenError> {
    match scope {
        RooflineTimingScope::WholeDeployment => Ok(1.0),
        RooflineTimingScope::PerRank { rank_count } => {
            if rank_count != storage_hardware.deployment_device_count {
                return Err(DeploymentScreenError::RankCountMismatch {
                    expected: storage_hardware.deployment_device_count,
                    actual: rank_count,
                });
            }
            Ok(f64::from(rank_count))
        }
    }
}

fn rejection_reasons(
    capacity: DeploymentCapacityStatus,
    optimistic_hurdle_cleared: bool,
) -> Vec<DeploymentRejectionReason> {
    let mut reasons = Vec::new();
    match capacity {
        DeploymentCapacityStatus::Infeasible => {
            reasons.push(DeploymentRejectionReason::CapacityInfeasible)
        }
        DeploymentCapacityStatus::Uncertain => {
            reasons.push(DeploymentRejectionReason::CapacityUncertain)
        }
        DeploymentCapacityStatus::Feasible => {}
    }
    if !optimistic_hurdle_cleared {
        reasons.push(DeploymentRejectionReason::OptimisticThroughputBelowBreakEven);
    }
    reasons
}

fn claim_gate(
    request: &DeploymentScreenRequest,
    variant: &GlmVariantEnvelopeReport,
    storage_hardware: &HardwareVariantEnvelopeReport,
    roofline_hardware: &HardwareRooflineReport,
    roofline: &LedgerRooflineReport,
) -> DeploymentScreenClaimGate {
    let mut blockers = vec![
        DeploymentClaimBlocker::OptimisticRejectionBoundOnly,
        DeploymentClaimBlocker::EndToEndCostModelIsAbsent,
    ];
    if !request.input_prefill_work_included_in_roofline {
        blockers.push(DeploymentClaimBlocker::InputPrefillWorkTreatedAsFree);
    }
    if matches!(request.timing_scope, RooflineTimingScope::PerRank { .. }) {
        blockers.push(DeploymentClaimBlocker::PerRankLinearScalingAssumption);
    }
    if roofline
        .result
        .claims
        .blockers
        .contains(&LedgerRooflineClaimBlocker::LedgerContainsAssumptions)
    {
        blockers.push(DeploymentClaimBlocker::LedgerContainsModeledWork);
    }
    if roofline_hardware.evidence.kind == HardwareTimingEvidenceKind::ModeledAssumption
        || roofline
            .result
            .claims
            .blockers
            .contains(&LedgerRooflineClaimBlocker::HardwareTimingIsNotCalibrated)
    {
        blockers.push(DeploymentClaimBlocker::HardwareTimingIsModeledOrUncalibrated);
    }
    if storage_contains_modeled_inputs(variant, storage_hardware) {
        blockers.push(DeploymentClaimBlocker::StorageEnvelopeContainsModeledInputs);
    }
    if roofline
        .result
        .claims
        .blockers
        .contains(&LedgerRooflineClaimBlocker::SharedResourceContentionIsNotModeled)
    {
        blockers.push(DeploymentClaimBlocker::SharedResourceContentionIsNotModeled);
    }
    if roofline
        .result
        .claims
        .blockers
        .contains(&LedgerRooflineClaimBlocker::ServingAndQueueingAreNotModeled)
    {
        blockers.push(DeploymentClaimBlocker::ServingAndQueueingAreNotModeled);
    }
    DeploymentScreenClaimGate {
        business_viability_claim_permitted: false,
        end_to_end_cost_claim_permitted: false,
        provider_comparison_claim_permitted: false,
        blockers,
        source_roofline_blockers: roofline.result.claims.blockers.clone(),
    }
}

fn storage_contains_modeled_inputs(
    variant: &GlmVariantEnvelopeReport,
    hardware: &HardwareVariantEnvelopeReport,
) -> bool {
    variant
        .active_traffic
        .as_ref()
        .is_some_and(|traffic| traffic.evidence.kind == EnvelopeEvidenceKind::ModeledAssumption)
        || hardware.bandwidth.as_ref().is_some_and(|bandwidth| {
            bandwidth.traffic_evidence.kind == EnvelopeEvidenceKind::ModeledAssumption
                || bandwidth.bandwidth_evidence.kind == EnvelopeEvidenceKind::ModeledAssumption
        })
}

fn validate_required(field: &'static str, value: &str) -> Result<(), DeploymentScreenError> {
    if value.trim().is_empty() {
        Err(DeploymentScreenError::InvalidField(field))
    } else {
        Ok(())
    }
}

fn validate_factor(field: &'static str, value: f64) -> Result<(), DeploymentScreenError> {
    if value.is_finite() && value > 0.0 && value <= 1.0 {
        Ok(())
    } else {
        Err(DeploymentScreenError::InvalidField(field))
    }
}

fn validate_positive(field: &'static str, value: f64) -> Result<(), DeploymentScreenError> {
    if value.is_finite() && value > 0.0 {
        Ok(())
    } else {
        Err(DeploymentScreenError::InvalidField(field))
    }
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a DeploymentScreenResult,
}

fn report_content_id(
    schema_version: u32,
    result: &DeploymentScreenResult,
) -> Result<String, DeploymentScreenError> {
    let bytes = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|error| DeploymentScreenError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Debug, Error)]
pub enum DeploymentScreenError {
    #[error("unsupported deployment screen schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("unsupported storage report schema version {actual}; expected {expected}")]
    UnsupportedStorageSchemaVersion { expected: u32, actual: u32 },
    #[error("unsupported roofline report schema version {actual}; expected {expected}")]
    UnsupportedRooflineSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid deployment screen field {0}")]
    InvalidField(&'static str),
    #[error("storage artifact identity is invalid")]
    InvalidStorageArtifactIdentity,
    #[error("roofline artifact identity is invalid")]
    InvalidRooflineArtifactIdentity,
    #[error("storage artifact does not match the pinned content ID")]
    StorageArtifactIdentityMismatch,
    #[error("roofline artifact does not match the pinned content ID")]
    RooflineArtifactIdentityMismatch,
    #[error("unknown storage variant {0}")]
    UnknownVariant(String),
    #[error("duplicate storage variant {0}")]
    DuplicateVariant(String),
    #[error("unknown storage hardware {0}")]
    UnknownStorageHardware(String),
    #[error("duplicate storage hardware {0}")]
    DuplicateStorageHardware(String),
    #[error("unknown roofline hardware {0}")]
    UnknownRooflineHardware(String),
    #[error("duplicate roofline hardware {0}")]
    DuplicateRooflineHardware(String),
    #[error("per-rank timing rank count {actual} does not match deployment count {expected}")]
    RankCountMismatch { expected: u32, actual: u32 },
    #[error("selected storage deployment has no break-even throughput hurdle")]
    MissingBreakEvenHurdle,
    #[error("storage artifact verification failed: {0}")]
    StorageArtifactVerification(#[source] GlmStorageEnvelopeError),
    #[error("roofline artifact verification failed: {0}")]
    RooflineArtifactVerification(#[source] LedgerRooflineError),
    #[error("deployment screen serialization failed: {0}")]
    Serialization(String),
}
