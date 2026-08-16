pub use crate::codesign::QualityEvidence;
use crate::codesign::{QualityGate, QualityTarget};
use crate::scale::{ScaleError, ScaleLabel, ScaleScenario};
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ValidatedModelConclusion {
    pub scenario: ScaleScenario,
    pub validation_basis: ValidationBasis,
    pub measured_cost_reduction_fraction: f64,
    pub quality: QualityEvidence,
    pub hardware_configuration_id: String,
    pub execution_mapping_id: String,
    pub evidence_artifacts: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ProjectedModelConclusion {
    pub scenario: ScaleScenario,
    pub projected_cost_reduction_fraction: EstimateRange,
    pub quality: QualityEvidence,
    pub hardware: TargetHardwareEvidence,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct EstimateRange {
    pub lower: f64,
    pub point: f64,
    pub upper: f64,
    pub confidence_level: f64,
}

impl EstimateRange {
    fn validate(&self, field: &'static str) -> Result<(), TransferError> {
        if !self.lower.is_finite()
            || !self.point.is_finite()
            || !self.upper.is_finite()
            || !self.confidence_level.is_finite()
            || self.lower > self.point
            || self.point > self.upper
            || self.confidence_level <= 0.0
            || self.confidence_level > 1.0
        {
            return Err(TransferError::InvalidEstimate(field));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ScalingDimension {
    TotalParameters,
    ActiveParametersPerToken,
    ContextLength,
    WeightMemory,
    KvMemory,
    PrefillCompute,
    DecodeCompute,
    MemoryBandwidth,
    InterconnectBandwidth,
    BatchConcurrency,
    Other(String),
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ScalingAssumption {
    pub dimension: ScalingDimension,
    pub source_value: f64,
    pub target: EstimateRange,
    pub unit: String,
    pub rationale: String,
    pub evidence_artifacts: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct TargetHardwareEvidence {
    pub resized_for_target: bool,
    pub remapped_for_target: bool,
    pub sizing_artifacts: Vec<String>,
    pub mapping_artifacts: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ScaleTransferReport {
    pub source: ValidatedModelConclusion,
    pub target: ProjectedModelConclusion,
    pub scaling_assumptions: Vec<ScalingAssumption>,
    pub materiality_threshold_fraction: f64,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ValidationBasis {
    MeasuredHardware,
    CalibratedSimulation,
}

impl ScaleTransferReport {
    pub fn validate(&self) -> Result<(), TransferError> {
        self.source.scenario.validate()?;
        self.target.scenario.validate()?;
        if !matches!(
            self.source.scenario.label,
            ScaleLabel::ReferenceFixture { .. }
        ) {
            return Err(TransferError::SourceMustBeReference);
        }
        let derived_from = match &self.target.scenario.label {
            ScaleLabel::SyntheticProjection { derived_from, .. } => derived_from,
            ScaleLabel::ReferenceFixture { .. } => {
                return Err(TransferError::TargetMustBeProjection);
            }
        };
        if derived_from != self.source.scenario.display_name() {
            return Err(TransferError::ProjectionProvenanceMismatch);
        }
        if self.source.scenario.contract != self.target.scenario.contract {
            return Err(TransferError::ScaleContractMismatch);
        }
        validate_reduction(
            "source.measured_cost_reduction_fraction",
            self.source.measured_cost_reduction_fraction,
        )?;
        self.target
            .projected_cost_reduction_fraction
            .validate("target.projected_cost_reduction_fraction")?;
        if self.target.projected_cost_reduction_fraction.upper > 1.0 {
            return Err(TransferError::InvalidEstimate(
                "target.projected_cost_reduction_fraction",
            ));
        }
        validate_quality(&self.source.quality, "source.quality")?;
        validate_quality(&self.target.quality, "target.quality")?;
        let source_quality_target = QualityTarget::for_scale_scenario(&self.source.scenario)
            .map_err(|error| TransferError::QualityIdentity(error.to_string()))?;
        if !self
            .source
            .quality
            .gate_for(&source_quality_target)
            .permits_economic_conclusion()
        {
            return Err(TransferError::SourceQualityNotValidated);
        }
        if self.source.hardware_configuration_id.trim().is_empty()
            || self.source.execution_mapping_id.trim().is_empty()
            || self.source.evidence_artifacts.is_empty()
            || self
                .source
                .evidence_artifacts
                .iter()
                .any(|artifact| artifact.trim().is_empty())
        {
            return Err(TransferError::MissingSourceEvidence);
        }
        if self.scaling_assumptions.is_empty() {
            return Err(TransferError::MissingScalingAssumptions);
        }
        for (index, assumption) in self.scaling_assumptions.iter().enumerate() {
            assumption.validate(index)?;
        }
        if !self.materiality_threshold_fraction.is_finite()
            || !(0.0..1.0).contains(&self.materiality_threshold_fraction)
        {
            return Err(TransferError::InvalidMaterialityThreshold);
        }
        Ok(())
    }

    pub fn materiality_assessment(&self) -> Result<MaterialityAssessment, TransferError> {
        self.validate()?;
        let mut blockers = Vec::new();
        if !self.target.hardware.resized_for_target {
            blockers.push(MaterialityBlocker::HardwareNotResized);
        }
        if !self.target.hardware.remapped_for_target {
            blockers.push(MaterialityBlocker::ExecutionNotRemapped);
        }
        if self.target.hardware.resized_for_target
            && !has_evidence(&self.target.hardware.sizing_artifacts)
        {
            blockers.push(MaterialityBlocker::SizingEvidenceMissing);
        }
        if self.target.hardware.remapped_for_target
            && !has_evidence(&self.target.hardware.mapping_artifacts)
        {
            blockers.push(MaterialityBlocker::MappingEvidenceMissing);
        }
        let target_quality_target = QualityTarget::for_scale_scenario(&self.target.scenario)
            .map_err(|error| TransferError::QualityIdentity(error.to_string()))?;
        match self.target.quality.gate_for(&target_quality_target) {
            QualityGate::MeasuredPassed => {}
            QualityGate::ContractFailed => {
                blockers.push(MaterialityBlocker::QualityContractFailed);
            }
            QualityGate::ScopeMismatch => {
                blockers.push(MaterialityBlocker::QualityEvidenceScopeMismatch);
            }
            QualityGate::InvalidEvidence => {
                blockers.push(MaterialityBlocker::QualityEvidenceInvalid);
            }
            QualityGate::Unvalidated | QualityGate::Surrogate => {
                blockers.push(MaterialityBlocker::QualityUnmeasured);
            }
        }
        if !blockers.is_empty() {
            return Err(TransferError::MaterialityBlocked { blockers });
        }
        let conservative_reduction_fraction = self.target.projected_cost_reduction_fraction.lower;
        Ok(MaterialityAssessment {
            decision: if conservative_reduction_fraction >= self.materiality_threshold_fraction {
                MaterialityDecision::ProjectedMaterial
            } else {
                MaterialityDecision::ProjectedNotMaterial
            },
            conservative_reduction_fraction,
            threshold_fraction: self.materiality_threshold_fraction,
        })
    }

    pub fn render_markdown(&self) -> Result<String, TransferError> {
        self.validate()?;
        let projection = self.target.projected_cost_reduction_fraction;
        let mut markdown = format!(
            "# Model-scale transfer report\n\n- VALIDATED: {}\n- PROJECTED, NOT VALIDATED: {}\n\nThe target conclusion is a scale projection and must not be represented as measured target-model performance.\n\n## Source evidence\n\n- Validation basis: `{:?}`\n- Measured cost reduction: {:.2}%\n- Hardware configuration: `{}`\n- Execution mapping: `{}`\n- Evidence: {}\n\n## Target projection\n\n- Cost-reduction interval: {:.2}% to {:.2}%\n- Point estimate: {:.2}%\n- Confidence level: {:.1}%\n- Hardware re-sized: {}\n- Execution remapped: {}\n\n## Scaling assumptions\n\n| Dimension | Source | Target interval | Unit | Confidence | Rationale | Evidence |\n| --- | ---: | ---: | --- | ---: | --- | --- |\n",
            self.source.scenario.display_name(),
            self.target.scenario.display_name(),
            self.source.validation_basis,
            self.source.measured_cost_reduction_fraction * 100.0,
            self.source.hardware_configuration_id,
            self.source.execution_mapping_id,
            self.source.evidence_artifacts.join(", "),
            projection.lower * 100.0,
            projection.upper * 100.0,
            projection.point * 100.0,
            projection.confidence_level * 100.0,
            yes_no(self.target.hardware.resized_for_target),
            yes_no(self.target.hardware.remapped_for_target),
        );
        for assumption in &self.scaling_assumptions {
            markdown.push_str(&format!(
                "| {} | {:.3} | {:.3}–{:.3} | {} | {:.1}% | {} | {} |\n",
                dimension_name(&assumption.dimension),
                assumption.source_value,
                assumption.target.lower,
                assumption.target.upper,
                assumption.unit,
                assumption.target.confidence_level * 100.0,
                assumption.rationale,
                assumption.evidence_artifacts.join(", "),
            ));
        }
        markdown.push_str("\n## Materiality\n\n");
        match self.materiality_assessment() {
            Ok(assessment) => markdown.push_str(&format!(
                "{:?}: conservative reduction {:.2}% versus {:.2}% threshold.\n",
                assessment.decision,
                assessment.conservative_reduction_fraction * 100.0,
                assessment.threshold_fraction * 100.0,
            )),
            Err(TransferError::MaterialityBlocked { blockers }) => markdown.push_str(&format!(
                "BLOCKED: {}.\n",
                blockers
                    .iter()
                    .map(blocker_name)
                    .collect::<Vec<_>>()
                    .join(", ")
            )),
            Err(error) => return Err(error),
        }
        Ok(markdown)
    }
}

impl ScalingAssumption {
    fn validate(&self, index: usize) -> Result<(), TransferError> {
        if !self.source_value.is_finite()
            || self.source_value < 0.0
            || matches!(&self.dimension, ScalingDimension::Other(name) if name.trim().is_empty())
            || self.unit.trim().is_empty()
            || self.rationale.trim().is_empty()
            || !has_evidence(&self.evidence_artifacts)
        {
            return Err(TransferError::InvalidScalingAssumption(index));
        }
        self.target
            .validate("scaling_assumptions.target")
            .map_err(|_| TransferError::InvalidScalingAssumption(index))?;
        if self.target.lower < 0.0 {
            return Err(TransferError::InvalidScalingAssumption(index));
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MaterialityDecision {
    ProjectedMaterial,
    ProjectedNotMaterial,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct MaterialityAssessment {
    pub decision: MaterialityDecision,
    pub conservative_reduction_fraction: f64,
    pub threshold_fraction: f64,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MaterialityBlocker {
    HardwareNotResized,
    ExecutionNotRemapped,
    SizingEvidenceMissing,
    MappingEvidenceMissing,
    QualityUnmeasured,
    QualityContractFailed,
    QualityEvidenceScopeMismatch,
    QualityEvidenceInvalid,
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum TransferError {
    #[error("invalid scale scenario: {0}")]
    InvalidScaleScenario(#[from] ScaleError),
    #[error("validated transfer source must be a reference fixture")]
    SourceMustBeReference,
    #[error("transfer target must be explicitly marked as a synthetic projection")]
    TargetMustBeProjection,
    #[error("transfer target projection provenance does not match the validated source")]
    ProjectionProvenanceMismatch,
    #[error("source and target scale contracts differ")]
    ScaleContractMismatch,
    #[error("invalid transfer estimate {0}")]
    InvalidEstimate(&'static str),
    #[error("source quality has not been measured and passed")]
    SourceQualityNotValidated,
    #[error("quality evidence field {0} is invalid")]
    InvalidQualityEvidence(&'static str),
    #[error("quality target identity failed: {0}")]
    QualityIdentity(String),
    #[error("validated source evidence is missing")]
    MissingSourceEvidence,
    #[error("scale transfer requires explicit scaling assumptions")]
    MissingScalingAssumptions,
    #[error("scaling assumption {0} is invalid")]
    InvalidScalingAssumption(usize),
    #[error("materiality threshold must be finite and in [0, 1)")]
    InvalidMaterialityThreshold,
    #[error("materiality claim blocked by {blockers:?}")]
    MaterialityBlocked { blockers: Vec<MaterialityBlocker> },
}

fn validate_reduction(field: &'static str, value: f64) -> Result<(), TransferError> {
    if !value.is_finite() || value > 1.0 {
        Err(TransferError::InvalidEstimate(field))
    } else {
        Ok(())
    }
}

fn validate_quality(quality: &QualityEvidence, field: &'static str) -> Result<(), TransferError> {
    match quality {
        QualityEvidence::Unvalidated => Ok(()),
        QualityEvidence::Surrogate {
            predicted_delta,
            uncertainty,
        } if predicted_delta.is_finite() && uncertainty.is_finite() && *uncertainty >= 0.0 => {
            Ok(())
        }
        QualityEvidence::Measured { scope, .. }
            if !matches!(
                quality.gate_for(&scope.target),
                QualityGate::InvalidEvidence
            ) =>
        {
            Ok(())
        }
        _ => Err(TransferError::InvalidQualityEvidence(field)),
    }
}

fn has_evidence(artifacts: &[String]) -> bool {
    !artifacts.is_empty() && artifacts.iter().all(|artifact| !artifact.trim().is_empty())
}

fn yes_no(value: bool) -> &'static str {
    if value { "yes" } else { "no" }
}

fn dimension_name(dimension: &ScalingDimension) -> &str {
    match dimension {
        ScalingDimension::TotalParameters => "total_parameters",
        ScalingDimension::ActiveParametersPerToken => "active_parameters_per_token",
        ScalingDimension::ContextLength => "context_length",
        ScalingDimension::WeightMemory => "weight_memory",
        ScalingDimension::KvMemory => "kv_memory",
        ScalingDimension::PrefillCompute => "prefill_compute",
        ScalingDimension::DecodeCompute => "decode_compute",
        ScalingDimension::MemoryBandwidth => "memory_bandwidth",
        ScalingDimension::InterconnectBandwidth => "interconnect_bandwidth",
        ScalingDimension::BatchConcurrency => "batch_concurrency",
        ScalingDimension::Other(name) => name,
    }
}

fn blocker_name(blocker: &MaterialityBlocker) -> &'static str {
    match blocker {
        MaterialityBlocker::HardwareNotResized => "hardware was not re-sized",
        MaterialityBlocker::ExecutionNotRemapped => "execution was not remapped",
        MaterialityBlocker::SizingEvidenceMissing => "hardware sizing evidence is missing",
        MaterialityBlocker::MappingEvidenceMissing => "mapping evidence is missing",
        MaterialityBlocker::QualityUnmeasured => "target quality is unmeasured",
        MaterialityBlocker::QualityContractFailed => "target quality contract failed",
        MaterialityBlocker::QualityEvidenceScopeMismatch => {
            "target quality evidence scope does not match the target model"
        }
        MaterialityBlocker::QualityEvidenceInvalid => "target quality evidence is invalid",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::codesign::MeasuredQualityScope;
    use crate::scale::{qwen3_8b_reference, synthetic_glm_class_projection};

    #[test]
    fn report_distinguishes_validated_source_from_projected_target() {
        let report = report();

        let markdown = report.render_markdown().unwrap();

        assert!(markdown.contains("VALIDATED: Qwen3-8B reference"));
        assert!(markdown.contains("PROJECTED, NOT VALIDATED: Synthetic GLM-class MoE"));
        assert!(markdown.contains("active_parameters_per_token"));
        assert!(markdown.contains("25.00% to 55.00%"));
    }

    #[test]
    fn materiality_is_blocked_without_target_hardware_resizing_and_remapping() {
        let mut report = report();
        report.target.hardware.resized_for_target = false;
        report.target.hardware.remapped_for_target = false;

        let error = report.materiality_assessment().unwrap_err();

        assert_eq!(
            error,
            TransferError::MaterialityBlocked {
                blockers: vec![
                    MaterialityBlocker::HardwareNotResized,
                    MaterialityBlocker::ExecutionNotRemapped,
                ],
            }
        );
    }

    #[test]
    fn materiality_is_blocked_when_target_quality_is_unmeasured() {
        let mut report = report();
        report.target.quality = QualityEvidence::Unvalidated;

        let error = report.materiality_assessment().unwrap_err();

        assert_eq!(
            error,
            TransferError::MaterialityBlocked {
                blockers: vec![MaterialityBlocker::QualityUnmeasured],
            }
        );
    }

    #[test]
    fn source_model_quality_cannot_validate_the_projected_target_model() {
        let mut report = report();
        report.target.quality = report.source.quality.clone();

        let error = report.materiality_assessment().unwrap_err();

        assert_eq!(
            error,
            TransferError::MaterialityBlocked {
                blockers: vec![MaterialityBlocker::QualityEvidenceScopeMismatch],
            }
        );
    }

    #[test]
    fn conservative_projection_bound_determines_materiality() {
        let report = report();

        let assessment = report.materiality_assessment().unwrap();

        assert_eq!(assessment.decision, MaterialityDecision::ProjectedMaterial);
        assert_eq!(assessment.conservative_reduction_fraction, 0.25);
        assert_eq!(assessment.threshold_fraction, 0.20);
        assert!(report.scaling_assumptions[0].target.confidence_level < 1.0);
    }

    #[test]
    fn uncertainty_intervals_must_be_ordered_and_bounded() {
        let mut report = report();
        report.target.projected_cost_reduction_fraction.lower = 0.6;

        assert_eq!(
            report.validate(),
            Err(TransferError::InvalidEstimate(
                "target.projected_cost_reduction_fraction"
            ))
        );
    }

    #[test]
    fn target_projection_provenance_must_match_the_validated_source() {
        let mut report = report();
        let ScaleLabel::SyntheticProjection { derived_from, .. } =
            &mut report.target.scenario.label
        else {
            unreachable!()
        };
        *derived_from = "unrelated source".into();

        assert_eq!(
            report.validate(),
            Err(TransferError::ProjectionProvenanceMismatch)
        );
    }

    fn report() -> ScaleTransferReport {
        let source_scenario = qwen3_8b_reference();
        let target_scenario = synthetic_glm_class_projection(&source_scenario).unwrap();
        let source_quality = measured_quality(&source_scenario, "qwen-quality-run", -0.01);
        let target_quality = measured_quality(&target_scenario, "glm-quality-run", 0.0);
        ScaleTransferReport {
            source: ValidatedModelConclusion {
                scenario: source_scenario,
                validation_basis: ValidationBasis::CalibratedSimulation,
                measured_cost_reduction_fraction: 0.30,
                quality: source_quality,
                hardware_configuration_id: "qwen-asic-v0".into(),
                execution_mapping_id: "qwen-mapping-v0".into(),
                evidence_artifacts: vec!["qwen-simulation-run".into()],
            },
            target: ProjectedModelConclusion {
                scenario: target_scenario,
                projected_cost_reduction_fraction: EstimateRange {
                    lower: 0.25,
                    point: 0.40,
                    upper: 0.55,
                    confidence_level: 0.80,
                },
                quality: target_quality,
                hardware: TargetHardwareEvidence {
                    resized_for_target: true,
                    remapped_for_target: true,
                    sizing_artifacts: vec!["glm-sizing-run".into()],
                    mapping_artifacts: vec!["glm-mapping-run".into()],
                },
            },
            scaling_assumptions: vec![ScalingAssumption {
                dimension: ScalingDimension::ActiveParametersPerToken,
                source_value: 8_000_000_000.0,
                target: EstimateRange {
                    lower: 28_000_000_000.0,
                    point: 32_000_000_000.0,
                    upper: 36_000_000_000.0,
                    confidence_level: 0.75,
                },
                unit: "parameters".into(),
                rationale: "Only routed experts are active for each target token".into(),
                evidence_artifacts: vec!["glm-architecture".into()],
            }],
            materiality_threshold_fraction: 0.20,
        }
    }

    fn measured_quality(
        scenario: &ScaleScenario,
        report_id: &str,
        worst_metric_delta: f64,
    ) -> QualityEvidence {
        QualityEvidence::Measured {
            scope: MeasuredQualityScope {
                target: QualityTarget::for_scale_scenario(scenario).unwrap(),
                report_id: report_id.into(),
            },
            passed: true,
            worst_metric_delta,
        }
    }
}
