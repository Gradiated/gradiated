use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};
use thiserror::Error;

pub const CLAIM_COMPOSITION_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ClaimMetric {
    Quality,
    WeightBytes,
    KvBytes,
    NetworkBytes,
    SimulatorCycles,
    Latency,
    Throughput,
    Energy,
    InputCostPerMillionTokens,
    OutputCostPerMillionTokens,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceClass {
    MeasuredEndToEnd,
    MeasuredComponent,
    MeasuredQuality,
    ExternalSimulator,
    Analytical,
    VendorReported,
    Inferred,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ClaimScope {
    pub model_id: String,
    pub model_revision: String,
    pub workload_id: String,
    pub quality_contract_id: String,
    pub slo_contract_id: String,
    pub baseline_stack_id: String,
    pub candidate_stack_id: String,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RelativeEffect {
    pub lower: f64,
    pub upper: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ClaimEvidence {
    pub evidence_id: String,
    pub source_artifact_id: String,
    pub scope: ClaimScope,
    pub intervention_ids: Vec<String>,
    pub metric: ClaimMetric,
    pub relative_effect: RelativeEffect,
    pub evidence_class: EvidenceClass,
    pub claim_permitted: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CompositionRequest {
    pub schema_version: u32,
    pub composition_id: String,
    pub scope: ClaimScope,
    pub requested_intervention_ids: Vec<String>,
    pub objective: ClaimMetric,
    pub evidence: Vec<ClaimEvidence>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CompositionExclusionReason {
    ScopeMismatch,
    MetricMismatch,
    InterventionSetMismatch,
    ClaimNotPermitted,
    EvidenceClassInsufficient,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CompositionExclusion {
    pub evidence_id: String,
    pub reasons: Vec<CompositionExclusionReason>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CompositionBlocker {
    NoExactJointEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CompositionReport {
    pub schema_version: u32,
    pub content_id: String,
    pub request_content_id: String,
    pub composition_id: String,
    pub scope: ClaimScope,
    pub requested_intervention_ids: Vec<String>,
    pub objective: ClaimMetric,
    pub evidence_count: u64,
    pub admissible_evidence_ids: Vec<String>,
    pub exclusions: Vec<CompositionExclusion>,
    pub blockers: Vec<CompositionBlocker>,
    pub relative_effect: Option<RelativeEffect>,
    pub combined_claim_permitted: bool,
    pub conclusion: String,
}

impl CompositionReport {
    pub fn verify_content_id(&self) -> Result<bool, CompositionError> {
        Ok(self.content_id == report_content_id(self)?)
    }
}

pub fn evaluate_claim_composition(
    request: &CompositionRequest,
) -> Result<CompositionReport, CompositionError> {
    request.validate()?;
    let requested = canonical_ids(&request.requested_intervention_ids)?;
    let request_content_id = request_content_id(request)?;
    let mut admissible = Vec::new();
    let mut exclusions = Vec::new();
    for evidence in &request.evidence {
        let mut reasons = BTreeSet::new();
        if evidence.scope != request.scope {
            reasons.insert(CompositionExclusionReason::ScopeMismatch);
        }
        if evidence.metric != request.objective {
            reasons.insert(CompositionExclusionReason::MetricMismatch);
        }
        if canonical_ids(&evidence.intervention_ids)? != requested {
            reasons.insert(CompositionExclusionReason::InterventionSetMismatch);
        }
        if !evidence.claim_permitted {
            reasons.insert(CompositionExclusionReason::ClaimNotPermitted);
        }
        if !evidence_class_supports(evidence.evidence_class, request.objective) {
            reasons.insert(CompositionExclusionReason::EvidenceClassInsufficient);
        }
        if reasons.is_empty() {
            admissible.push(evidence);
        } else {
            exclusions.push(CompositionExclusion {
                evidence_id: evidence.evidence_id.clone(),
                reasons: reasons.into_iter().collect(),
            });
        }
    }
    if admissible.len() > 1 {
        return Err(CompositionError::AmbiguousExactEvidence(
            admissible
                .iter()
                .map(|evidence| evidence.evidence_id.clone())
                .collect(),
        ));
    }
    let relative_effect = admissible.first().map(|evidence| evidence.relative_effect);
    let combined_claim_permitted = relative_effect.is_some();
    let blockers = if combined_claim_permitted {
        Vec::new()
    } else {
        vec![CompositionBlocker::NoExactJointEvidence]
    };
    let conclusion = if combined_claim_permitted {
        "An exact scope-matched joint end-to-end artifact permits this objective claim.".into()
    } else {
        "Marginal, cross-model, component, simulated, analytical, or claim-locked effects cannot be multiplied into this objective.".into()
    };
    let mut report = CompositionReport {
        schema_version: CLAIM_COMPOSITION_SCHEMA_VERSION,
        content_id: String::new(),
        request_content_id,
        composition_id: request.composition_id.clone(),
        scope: request.scope.clone(),
        requested_intervention_ids: requested.into_iter().collect(),
        objective: request.objective,
        evidence_count: u64::try_from(request.evidence.len())
            .map_err(|_| CompositionError::CountOverflow)?,
        admissible_evidence_ids: admissible
            .iter()
            .map(|evidence| evidence.evidence_id.clone())
            .collect(),
        exclusions,
        blockers,
        relative_effect,
        combined_claim_permitted,
        conclusion,
    };
    report.content_id = report_content_id(&report)?;
    Ok(report)
}

impl CompositionRequest {
    fn validate(&self) -> Result<(), CompositionError> {
        if self.schema_version != CLAIM_COMPOSITION_SCHEMA_VERSION {
            return Err(CompositionError::UnsupportedSchemaVersion {
                expected: CLAIM_COMPOSITION_SCHEMA_VERSION,
                actual: self.schema_version,
            });
        }
        validate_text("composition_id", &self.composition_id)?;
        self.scope.validate()?;
        canonical_ids(&self.requested_intervention_ids)?;
        if self.evidence.is_empty() {
            return Err(CompositionError::InvalidField("evidence"));
        }
        let mut evidence_ids = BTreeSet::new();
        for evidence in &self.evidence {
            evidence.validate()?;
            if !evidence_ids.insert(evidence.evidence_id.as_str()) {
                return Err(CompositionError::DuplicateEvidenceId(
                    evidence.evidence_id.clone(),
                ));
            }
        }
        Ok(())
    }
}

impl ClaimScope {
    fn validate(&self) -> Result<(), CompositionError> {
        for (field, value) in [
            ("scope.model_id", self.model_id.as_str()),
            ("scope.model_revision", self.model_revision.as_str()),
            ("scope.workload_id", self.workload_id.as_str()),
            (
                "scope.quality_contract_id",
                self.quality_contract_id.as_str(),
            ),
            ("scope.slo_contract_id", self.slo_contract_id.as_str()),
            ("scope.baseline_stack_id", self.baseline_stack_id.as_str()),
            ("scope.candidate_stack_id", self.candidate_stack_id.as_str()),
        ] {
            validate_text(field, value)?;
        }
        Ok(())
    }
}

impl ClaimEvidence {
    fn validate(&self) -> Result<(), CompositionError> {
        validate_text("evidence.evidence_id", &self.evidence_id)?;
        validate_text("evidence.source_artifact_id", &self.source_artifact_id)?;
        self.scope.validate()?;
        canonical_ids(&self.intervention_ids)?;
        self.relative_effect.validate()
    }
}

impl RelativeEffect {
    fn validate(&self) -> Result<(), CompositionError> {
        if !self.lower.is_finite()
            || !self.upper.is_finite()
            || self.lower > self.upper
            || self.upper > 1.0
        {
            return Err(CompositionError::InvalidField("evidence.relative_effect"));
        }
        Ok(())
    }
}

fn evidence_class_supports(class: EvidenceClass, metric: ClaimMetric) -> bool {
    match metric {
        ClaimMetric::Quality => matches!(
            class,
            EvidenceClass::MeasuredQuality | EvidenceClass::MeasuredEndToEnd
        ),
        ClaimMetric::WeightBytes
        | ClaimMetric::KvBytes
        | ClaimMetric::NetworkBytes
        | ClaimMetric::SimulatorCycles => matches!(
            class,
            EvidenceClass::MeasuredComponent
                | EvidenceClass::ExternalSimulator
                | EvidenceClass::MeasuredEndToEnd
        ),
        ClaimMetric::Latency
        | ClaimMetric::Throughput
        | ClaimMetric::Energy
        | ClaimMetric::InputCostPerMillionTokens
        | ClaimMetric::OutputCostPerMillionTokens => {
            matches!(class, EvidenceClass::MeasuredEndToEnd)
        }
    }
}

fn canonical_ids(values: &[String]) -> Result<BTreeSet<String>, CompositionError> {
    if values.is_empty() {
        return Err(CompositionError::InvalidField("intervention_ids"));
    }
    let mut canonical = BTreeSet::new();
    for value in values {
        validate_text("intervention_ids", value)?;
        if !canonical.insert(value.clone()) {
            return Err(CompositionError::DuplicateInterventionId(value.clone()));
        }
    }
    Ok(canonical)
}

fn validate_text(field: &'static str, value: &str) -> Result<(), CompositionError> {
    if value.trim().is_empty() {
        Err(CompositionError::InvalidField(field))
    } else {
        Ok(())
    }
}

fn report_content_id(report: &CompositionReport) -> Result<String, CompositionError> {
    let document = (
        report.schema_version,
        report.request_content_id.as_str(),
        report.composition_id.as_str(),
        &report.scope,
        &report.requested_intervention_ids,
        report.objective,
        report.evidence_count,
        &report.admissible_evidence_ids,
        &report.exclusions,
        &report.blockers,
        report.relative_effect,
        report.combined_claim_permitted,
        report.conclusion.as_str(),
    );
    Ok(blake3::hash(&serde_json::to_vec(&document)?)
        .to_hex()
        .to_string())
}

fn request_content_id(request: &CompositionRequest) -> Result<String, CompositionError> {
    let requested_intervention_ids = canonical_ids(&request.requested_intervention_ids)?
        .into_iter()
        .collect::<Vec<_>>();
    let mut evidence = request.evidence.clone();
    for record in &mut evidence {
        record.intervention_ids = canonical_ids(&record.intervention_ids)?
            .into_iter()
            .collect();
    }
    evidence.sort_by(|left, right| left.evidence_id.cmp(&right.evidence_id));
    let document = (
        request.schema_version,
        request.composition_id.as_str(),
        &request.scope,
        requested_intervention_ids,
        request.objective,
        evidence,
    );
    Ok(blake3::hash(&serde_json::to_vec(&document)?)
        .to_hex()
        .to_string())
}

#[derive(Debug, Error)]
pub enum CompositionError {
    #[error("unsupported claim composition schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid claim composition field {0}")]
    InvalidField(&'static str),
    #[error("duplicate claim evidence id {0}")]
    DuplicateEvidenceId(String),
    #[error("duplicate intervention id {0}")]
    DuplicateInterventionId(String),
    #[error("multiple exact joint evidence records are ambiguous: {0:?}")]
    AmbiguousExactEvidence(Vec<String>),
    #[error("claim composition count exceeds the supported range")]
    CountOverflow,
    #[error("claim composition serialization failed: {0}")]
    Serialization(#[from] serde_json::Error),
}
