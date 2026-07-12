use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::spec::{ModelArchitecture, ModelSpec};

pub const GLM_MTP_SWEEP_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const GLM_MTP_SWEEP_REPORT_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MtpEvidenceKind {
    MeasuredExactCheckpoint,
    MeasuredHardware,
    VendorMeasurement,
    ModeledAssumption,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MtpEvidence {
    pub kind: MtpEvidenceKind,
    pub source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MtpWorkAssumptions {
    pub baseline_target_work_units_per_token: f64,
    pub draft_work_units_per_proposed_token: f64,
    pub verification_fixed_work_units_per_round: f64,
    pub verification_incremental_work_units_per_proposed_token: f64,
    pub scheduler_work_units_per_round: f64,
    pub evidence: MtpEvidence,
    pub basis: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MtpAcceptanceScenario {
    pub scenario_id: String,
    pub conditional_acceptance_probabilities: Vec<f64>,
    pub evidence: MtpEvidence,
    pub basis: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmMtpSweepRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub model: ModelSpec,
    pub work: MtpWorkAssumptions,
    pub scenarios: Vec<MtpAcceptanceScenario>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MtpDepthReport {
    pub proposal_depth: u32,
    pub expected_accepted_draft_tokens: f64,
    pub expected_committed_tokens_per_round: f64,
    pub expected_rejected_draft_tokens: f64,
    pub draft_work_units: f64,
    pub verification_work_units: f64,
    pub scheduler_work_units: f64,
    pub total_work_units: f64,
    pub work_units_per_committed_token: f64,
    pub target_equivalent_work_per_committed_token: f64,
    pub ideal_throughput_speedup: f64,
    pub ideal_work_reduction_fraction: f64,
    pub synchronization_round_reduction_fraction: f64,
    pub homogeneous_acceptance_break_even_probability: Option<f64>,
    pub beats_baseline: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MtpAcceptanceScenarioReport {
    pub scenario_id: String,
    pub conditional_acceptance_probabilities: Vec<f64>,
    pub evidence: MtpEvidence,
    pub basis: String,
    pub depths: Vec<MtpDepthReport>,
    pub best_proposal_depth: Option<u32>,
    pub best_ideal_throughput_speedup: f64,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MtpClaimBlocker {
    AcceptanceIsNotMeasuredExactCheckpoint,
    WorkIsNotMeasuredHardware,
    EndToEndServingNotMeasured,
    QualityContractNotProvided,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MtpClaimGate {
    pub end_to_end_latency_claim_permitted: bool,
    pub cost_per_token_claim_permitted: bool,
    pub quality_claim_permitted: bool,
    pub blockers: Vec<MtpClaimBlocker>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmMtpSweepResult {
    pub study_id: String,
    pub model_id: String,
    pub model_revision: String,
    pub mtp_layer_count: u32,
    pub mtp_shared_parameters: bool,
    pub mtp_shares_dsa_indices: bool,
    pub work: MtpWorkAssumptions,
    pub scenarios: Vec<MtpAcceptanceScenarioReport>,
    pub claims: MtpClaimGate,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmMtpSweepReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: GlmMtpSweepResult,
}

impl GlmMtpSweepReport {
    pub fn verify_content_id(&self) -> Result<bool, GlmMtpSweepError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

pub fn evaluate_glm_mtp_sweep(
    request: &GlmMtpSweepRequest,
) -> Result<GlmMtpSweepReport, GlmMtpSweepError> {
    let mtp = validate_request(request)?;
    let scenarios = request
        .scenarios
        .iter()
        .map(|scenario| evaluate_scenario(&request.work, scenario))
        .collect::<Result<Vec<_>, _>>()?;
    let result = GlmMtpSweepResult {
        study_id: request.study_id.clone(),
        model_id: request.model.model_id.clone(),
        model_revision: request.model.model_revision.clone(),
        mtp_layer_count: mtp.layer_count,
        mtp_shared_parameters: mtp.shared_parameters,
        mtp_shares_dsa_indices: mtp.shares_dsa_indices,
        work: request.work.clone(),
        scenarios,
        claims: claim_gate(request),
    };
    let schema_version = GLM_MTP_SWEEP_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(GlmMtpSweepReport {
        schema_version,
        content_id,
        result,
    })
}

fn validate_request(
    request: &GlmMtpSweepRequest,
) -> Result<crate::spec::MtpSpec, GlmMtpSweepError> {
    if request.schema_version != GLM_MTP_SWEEP_REQUEST_SCHEMA_VERSION {
        return Err(GlmMtpSweepError::UnsupportedSchemaVersion {
            expected: GLM_MTP_SWEEP_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    validate_required("study_id", &request.study_id)?;
    request
        .model
        .validate()
        .map_err(|_| GlmMtpSweepError::InvalidModel)?;
    let ModelArchitecture::HybridMoeMlaDsa(hybrid) = request.model.architecture else {
        return Err(GlmMtpSweepError::UnsupportedModelArchitecture);
    };
    validate_work(&request.work)?;
    if request.scenarios.is_empty() {
        return Err(GlmMtpSweepError::InvalidField("scenarios"));
    }
    let mut scenario_ids = BTreeSet::new();
    for scenario in &request.scenarios {
        validate_required("scenarios.scenario_id", &scenario.scenario_id)?;
        validate_required("scenarios.basis", &scenario.basis)?;
        validate_evidence("scenarios.evidence", &scenario.evidence)?;
        if !scenario_ids.insert(scenario.scenario_id.as_str()) {
            return Err(GlmMtpSweepError::DuplicateScenario(
                scenario.scenario_id.clone(),
            ));
        }
        if scenario.conditional_acceptance_probabilities.is_empty() {
            return Err(GlmMtpSweepError::InvalidField(
                "scenarios.conditional_acceptance_probabilities",
            ));
        }
        for probability in &scenario.conditional_acceptance_probabilities {
            if !probability.is_finite() || !(0.0..=1.0).contains(probability) {
                return Err(GlmMtpSweepError::InvalidField(
                    "scenarios.conditional_acceptance_probabilities",
                ));
            }
        }
    }
    Ok(hybrid.mtp)
}

fn validate_work(work: &MtpWorkAssumptions) -> Result<(), GlmMtpSweepError> {
    if !work.baseline_target_work_units_per_token.is_finite()
        || work.baseline_target_work_units_per_token <= 0.0
    {
        return Err(GlmMtpSweepError::InvalidField(
            "work.baseline_target_work_units_per_token",
        ));
    }
    for (field, value) in [
        (
            "work.draft_work_units_per_proposed_token",
            work.draft_work_units_per_proposed_token,
        ),
        (
            "work.verification_fixed_work_units_per_round",
            work.verification_fixed_work_units_per_round,
        ),
        (
            "work.verification_incremental_work_units_per_proposed_token",
            work.verification_incremental_work_units_per_proposed_token,
        ),
        (
            "work.scheduler_work_units_per_round",
            work.scheduler_work_units_per_round,
        ),
    ] {
        if !value.is_finite() || value < 0.0 {
            return Err(GlmMtpSweepError::InvalidField(field));
        }
    }
    if work.verification_fixed_work_units_per_round == 0.0
        && work.draft_work_units_per_proposed_token == 0.0
        && work.verification_incremental_work_units_per_proposed_token == 0.0
        && work.scheduler_work_units_per_round == 0.0
    {
        return Err(GlmMtpSweepError::InvalidField("work"));
    }
    validate_required("work.basis", &work.basis)?;
    validate_evidence("work.evidence", &work.evidence)
}

fn evaluate_scenario(
    work: &MtpWorkAssumptions,
    scenario: &MtpAcceptanceScenario,
) -> Result<MtpAcceptanceScenarioReport, GlmMtpSweepError> {
    let mut accepted_prefix_probability = 1.0;
    let mut expected_accepted = 0.0;
    let mut depths = Vec::with_capacity(scenario.conditional_acceptance_probabilities.len());
    let mut best_proposal_depth = None;
    let mut best_speedup = 1.0;
    for (index, conditional_probability) in scenario
        .conditional_acceptance_probabilities
        .iter()
        .enumerate()
    {
        accepted_prefix_probability *= conditional_probability;
        expected_accepted += accepted_prefix_probability;
        let proposal_depth =
            u32::try_from(index + 1).map_err(|_| GlmMtpSweepError::ArithmeticOverflow)?;
        let depth = evaluate_depth(work, proposal_depth, expected_accepted)?;
        if depth.ideal_throughput_speedup > best_speedup {
            best_speedup = depth.ideal_throughput_speedup;
            best_proposal_depth = Some(proposal_depth);
        }
        depths.push(depth);
    }
    Ok(MtpAcceptanceScenarioReport {
        scenario_id: scenario.scenario_id.clone(),
        conditional_acceptance_probabilities: scenario.conditional_acceptance_probabilities.clone(),
        evidence: scenario.evidence.clone(),
        basis: scenario.basis.clone(),
        depths,
        best_proposal_depth,
        best_ideal_throughput_speedup: best_speedup,
    })
}

fn evaluate_depth(
    work: &MtpWorkAssumptions,
    proposal_depth: u32,
    expected_accepted: f64,
) -> Result<MtpDepthReport, GlmMtpSweepError> {
    let depth = f64::from(proposal_depth);
    let expected_committed = 1.0 + expected_accepted;
    let draft_work = depth * work.draft_work_units_per_proposed_token;
    let verification_work = work.verification_fixed_work_units_per_round
        + depth * work.verification_incremental_work_units_per_proposed_token;
    let total_work = draft_work + verification_work + work.scheduler_work_units_per_round;
    let work_per_committed = total_work / expected_committed;
    let target_equivalent = work_per_committed / work.baseline_target_work_units_per_token;
    let speedup = 1.0 / target_equivalent;
    let work_reduction = 1.0 - target_equivalent;
    let sync_reduction = 1.0 - 1.0 / expected_committed;
    if ![
        expected_committed,
        draft_work,
        verification_work,
        total_work,
        work_per_committed,
        target_equivalent,
        speedup,
        work_reduction,
        sync_reduction,
    ]
    .iter()
    .all(|value| value.is_finite())
        || total_work <= 0.0
    {
        return Err(GlmMtpSweepError::ArithmeticOverflow);
    }
    Ok(MtpDepthReport {
        proposal_depth,
        expected_accepted_draft_tokens: expected_accepted,
        expected_committed_tokens_per_round: expected_committed,
        expected_rejected_draft_tokens: depth - expected_accepted,
        draft_work_units: draft_work,
        verification_work_units: verification_work,
        scheduler_work_units: work.scheduler_work_units_per_round,
        total_work_units: total_work,
        work_units_per_committed_token: work_per_committed,
        target_equivalent_work_per_committed_token: target_equivalent,
        ideal_throughput_speedup: speedup,
        ideal_work_reduction_fraction: work_reduction,
        synchronization_round_reduction_fraction: sync_reduction,
        homogeneous_acceptance_break_even_probability: homogeneous_break_even(
            proposal_depth,
            total_work / work.baseline_target_work_units_per_token,
        ),
        beats_baseline: speedup > 1.0,
    })
}

fn homogeneous_break_even(proposal_depth: u32, required_committed_tokens: f64) -> Option<f64> {
    if required_committed_tokens <= 1.0 {
        return Some(0.0);
    }
    if required_committed_tokens > f64::from(proposal_depth) + 1.0 {
        return None;
    }
    let mut lower = 0.0;
    let mut upper = 1.0;
    for _ in 0..100 {
        let midpoint = (lower + upper) / 2.0;
        if homogeneous_expected_committed(proposal_depth, midpoint) < required_committed_tokens {
            lower = midpoint;
        } else {
            upper = midpoint;
        }
    }
    Some((lower + upper) / 2.0)
}

fn homogeneous_expected_committed(proposal_depth: u32, probability: f64) -> f64 {
    let mut accepted_prefix = 1.0;
    let mut committed = 1.0;
    for _ in 0..proposal_depth {
        accepted_prefix *= probability;
        committed += accepted_prefix;
    }
    committed
}

fn claim_gate(request: &GlmMtpSweepRequest) -> MtpClaimGate {
    let mut blockers = Vec::new();
    if request
        .scenarios
        .iter()
        .any(|scenario| scenario.evidence.kind != MtpEvidenceKind::MeasuredExactCheckpoint)
    {
        blockers.push(MtpClaimBlocker::AcceptanceIsNotMeasuredExactCheckpoint);
    }
    if request.work.evidence.kind != MtpEvidenceKind::MeasuredHardware {
        blockers.push(MtpClaimBlocker::WorkIsNotMeasuredHardware);
    }
    blockers.push(MtpClaimBlocker::EndToEndServingNotMeasured);
    blockers.push(MtpClaimBlocker::QualityContractNotProvided);
    MtpClaimGate {
        end_to_end_latency_claim_permitted: false,
        cost_per_token_claim_permitted: false,
        quality_claim_permitted: false,
        blockers,
    }
}

fn validate_evidence(field: &'static str, evidence: &MtpEvidence) -> Result<(), GlmMtpSweepError> {
    validate_required(field, &evidence.source_artifact_id)
}

fn validate_required(field: &'static str, value: &str) -> Result<(), GlmMtpSweepError> {
    if value.trim().is_empty() {
        Err(GlmMtpSweepError::InvalidField(field))
    } else {
        Ok(())
    }
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a GlmMtpSweepResult,
}

fn report_content_id(
    schema_version: u32,
    result: &GlmMtpSweepResult,
) -> Result<String, GlmMtpSweepError> {
    let bytes = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|error| GlmMtpSweepError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum GlmMtpSweepError {
    #[error("unsupported GLM MTP sweep schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid GLM MTP sweep field {0}")]
    InvalidField(&'static str),
    #[error("the model specification is invalid")]
    InvalidModel,
    #[error("GLM MTP sweeps require a hybrid MoE/MLA/DSA model")]
    UnsupportedModelArchitecture,
    #[error("duplicate MTP acceptance scenario {0}")]
    DuplicateScenario(String),
    #[error("GLM MTP sweep arithmetic overflowed")]
    ArithmeticOverflow,
    #[error("GLM MTP sweep serialization failed: {0}")]
    Serialization(String),
}
