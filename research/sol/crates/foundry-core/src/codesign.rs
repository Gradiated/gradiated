use crate::scale::ScaleScenario;
use crate::spec::{ExperimentSpec, HardwareSpec, ModelSpec, Precision, QuantizedWeightStorageSpec};
use serde::{Deserialize, Serialize};
use thiserror::Error;

pub const BASELINE_VARIANT_NAME: &str = "baseline-model";

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(tag = "change", rename_all = "snake_case")]
pub enum ModelChange {
    WeightPrecision {
        precision: Precision,
        #[serde(default)]
        quantized_storage: Option<QuantizedWeightStorageSpec>,
    },
    KvPrecision {
        precision: Precision,
    },
    KvHeadCount {
        heads: u32,
    },
    IntermediateSize {
        size: u32,
    },
    StructuredParameterDensity {
        density: f64,
    },
    TieInputOutputEmbeddings,
    EquivalentRotation {
        family: String,
    },
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(tag = "evidence", rename_all = "snake_case", deny_unknown_fields)]
pub enum QualityEvidence {
    Unvalidated,
    Surrogate {
        predicted_delta: f64,
        uncertainty: f64,
    },
    Measured {
        scope: MeasuredQualityScope,
        passed: bool,
        worst_metric_delta: f64,
    },
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QualityVariantContext {
    pub name: String,
    pub changes: Vec<ModelChange>,
}

impl QualityVariantContext {
    pub fn baseline() -> Self {
        Self {
            name: BASELINE_VARIANT_NAME.into(),
            changes: Vec::new(),
        }
    }

    pub fn validate(&self) -> Result<(), QualityIdentityError> {
        if self.name.trim().is_empty()
            || (self.name == BASELINE_VARIANT_NAME) != self.changes.is_empty()
        {
            return Err(QualityIdentityError::InvalidField("variant"));
        }
        for change in &self.changes {
            match change {
                ModelChange::KvHeadCount { heads } if *heads == 0 => {
                    return Err(QualityIdentityError::InvalidField("variant.changes"));
                }
                ModelChange::IntermediateSize { size } if *size == 0 => {
                    return Err(QualityIdentityError::InvalidField("variant.changes"));
                }
                ModelChange::StructuredParameterDensity { density }
                    if !density.is_finite() || *density <= 0.0 || *density > 1.0 =>
                {
                    return Err(QualityIdentityError::InvalidField("variant.changes"));
                }
                ModelChange::EquivalentRotation { family } if family.trim().is_empty() => {
                    return Err(QualityIdentityError::InvalidField("variant.changes"));
                }
                _ => {}
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QualityTarget {
    pub model_id: String,
    pub model_revision: String,
    pub model_fingerprint: String,
    pub variant_name: String,
    pub change_fingerprint: String,
    pub suite_id: String,
}

impl QualityTarget {
    pub fn for_model(
        model: &ModelSpec,
        suite_id: &str,
        variant: &QualityVariantContext,
    ) -> Result<Self, QualityIdentityError> {
        variant.validate()?;
        let target = Self {
            model_id: model.model_id.clone(),
            model_revision: model.model_revision.clone(),
            model_fingerprint: fingerprint("model-spec-v1", model)?,
            variant_name: variant.name.clone(),
            change_fingerprint: fingerprint("model-changes-v1", &variant.changes)?,
            suite_id: suite_id.into(),
        };
        target.validate()?;
        Ok(target)
    }

    pub fn for_experiment(
        experiment: &ExperimentSpec,
        variant: &QualityVariantContext,
    ) -> Result<Self, QualityIdentityError> {
        Self::for_model(&experiment.model, &experiment.quality_suite_id, variant)
    }

    pub fn for_scale_scenario(scenario: &ScaleScenario) -> Result<Self, QualityIdentityError> {
        scenario
            .validate()
            .map_err(|error| QualityIdentityError::InvalidScaleScenario(error.to_string()))?;
        let target = Self {
            model_id: scenario.contract.model_id.clone(),
            model_revision: scenario.contract.model_revision.clone(),
            model_fingerprint: fingerprint(
                "scale-model-v1",
                &(&scenario.contract, &scenario.architecture),
            )?,
            variant_name: scenario.display_name().into(),
            change_fingerprint: fingerprint(
                "scale-variant-v1",
                &(&scenario.label, &scenario.architecture),
            )?,
            suite_id: scenario.contract.quality_contract_id.clone(),
        };
        target.validate()?;
        Ok(target)
    }

    pub fn validate(&self) -> Result<(), QualityIdentityError> {
        for (field, value) in [
            ("model_id", self.model_id.as_str()),
            ("model_revision", self.model_revision.as_str()),
            ("variant_name", self.variant_name.as_str()),
            ("suite_id", self.suite_id.as_str()),
        ] {
            if value.trim().is_empty() {
                return Err(QualityIdentityError::InvalidField(field));
            }
        }
        for (field, value) in [
            ("model_fingerprint", self.model_fingerprint.as_str()),
            ("change_fingerprint", self.change_fingerprint.as_str()),
        ] {
            if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
                return Err(QualityIdentityError::InvalidField(field));
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MeasuredQualityScope {
    pub target: QualityTarget,
    pub report_id: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum QualityGate {
    MeasuredPassed,
    ContractFailed,
    ScopeMismatch,
    InvalidEvidence,
    Surrogate,
    Unvalidated,
}

impl QualityGate {
    pub const fn permits_economic_conclusion(self) -> bool {
        matches!(self, Self::MeasuredPassed)
    }
}

impl QualityEvidence {
    pub fn gate_for(&self, expected: &QualityTarget) -> QualityGate {
        match self {
            Self::Unvalidated => QualityGate::Unvalidated,
            Self::Surrogate {
                predicted_delta,
                uncertainty,
            } => {
                if predicted_delta.is_finite() && uncertainty.is_finite() && *uncertainty >= 0.0 {
                    QualityGate::Surrogate
                } else {
                    QualityGate::InvalidEvidence
                }
            }
            Self::Measured {
                scope,
                passed,
                worst_metric_delta,
            } => {
                if expected.validate().is_err()
                    || scope.target.validate().is_err()
                    || scope.report_id.trim().is_empty()
                    || !worst_metric_delta.is_finite()
                {
                    QualityGate::InvalidEvidence
                } else if scope.target != *expected {
                    QualityGate::ScopeMismatch
                } else if *passed {
                    QualityGate::MeasuredPassed
                } else {
                    QualityGate::ContractFailed
                }
            }
        }
    }
}

fn fingerprint<T: Serialize>(domain: &str, value: &T) -> Result<String, QualityIdentityError> {
    let bytes = serde_json::to_vec(value)
        .map_err(|error| QualityIdentityError::Serialization(error.to_string()))?;
    let mut hasher = blake3::Hasher::new();
    hasher.update(domain.as_bytes());
    hasher.update(&[0]);
    hasher.update(&bytes);
    Ok(hasher.finalize().to_hex().to_string())
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum QualityIdentityError {
    #[error("quality identity field {0} is invalid")]
    InvalidField(&'static str),
    #[error("quality identity serialization failed: {0}")]
    Serialization(String),
    #[error("quality identity scale scenario is invalid: {0}")]
    InvalidScaleScenario(String),
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ModelVariant {
    pub name: String,
    pub changes: Vec<ModelChange>,
    pub quality: QualityEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct EffectiveModelVariant {
    pub name: String,
    pub model: ModelSpec,
    pub changes: Vec<ModelChange>,
    pub quality: QualityEvidence,
    pub requires_structured_sparse_execution: bool,
}

impl ModelVariant {
    pub fn apply(&self, base: &ModelSpec) -> Result<EffectiveModelVariant, CoDesignError> {
        if self.name.trim().is_empty() || self.changes.is_empty() {
            return Err(CoDesignError::InvalidVariant);
        }
        let mut model = base.clone();
        let mut density = 1.0_f64;
        let mut tied_embeddings = false;
        for change in &self.changes {
            match change {
                ModelChange::WeightPrecision {
                    precision,
                    quantized_storage,
                } => {
                    model.weight_precision = *precision;
                    model.quantized_weight_storage = *quantized_storage;
                }
                ModelChange::KvPrecision { precision } => {
                    model.kv_precision = *precision;
                }
                ModelChange::KvHeadCount { heads } => {
                    apply_kv_head_count(&mut model, *heads)?;
                }
                ModelChange::IntermediateSize { size } => {
                    apply_intermediate_size(&mut model, *size)?;
                }
                ModelChange::StructuredParameterDensity {
                    density: candidate_density,
                } => {
                    if !candidate_density.is_finite()
                        || *candidate_density <= 0.0
                        || *candidate_density > 1.0
                    {
                        return Err(CoDesignError::InvalidDensity(*candidate_density));
                    }
                    density *= candidate_density;
                }
                ModelChange::TieInputOutputEmbeddings => {
                    if !tied_embeddings {
                        let embedding_parameters = u64::from(model.vocabulary_size)
                            .checked_mul(u64::from(model.hidden_size))
                            .ok_or(CoDesignError::Overflow)?;
                        model.parameter_count = model
                            .parameter_count
                            .checked_sub(embedding_parameters)
                            .ok_or(CoDesignError::InvalidArchitectureChange)?;
                        tied_embeddings = true;
                    }
                }
                ModelChange::EquivalentRotation { family } => {
                    if family.trim().is_empty() {
                        return Err(CoDesignError::InvalidVariant);
                    }
                }
            }
        }
        model.parameter_count = ((model.parameter_count as f64) * density).ceil() as u64;
        if model.parameter_count == 0
            || model.kv_head_count == 0
            || model.attention_head_count % model.kv_head_count != 0
            || (model.weight_precision.bits() < 8 && model.quantized_weight_storage.is_none())
            || model.weight_bytes().is_none()
        {
            return Err(CoDesignError::InvalidArchitectureChange);
        }
        Ok(EffectiveModelVariant {
            name: self.name.clone(),
            model,
            changes: self.changes.clone(),
            quality: self.quality.clone(),
            requires_structured_sparse_execution: density < 1.0,
        })
    }
}

impl EffectiveModelVariant {
    pub fn pair_with_hardware(
        &self,
        base: &ExperimentSpec,
        hardware: &HardwareSpec,
    ) -> Result<CoDesignCandidate, CoDesignError> {
        if let Some(design) = &hardware.design {
            let supported = design
                .compute
                .arithmetic
                .iter()
                .any(|arithmetic| arithmetic.precision == self.model.weight_precision);
            if !supported {
                return Err(CoDesignError::UnsupportedPrecision(
                    self.model.weight_precision,
                ));
            }
        }
        let capacity = hardware
            .effective_memory_capacity_bytes()
            .ok_or(CoDesignError::MissingHardwareCapacity)?;
        let weights = self.model.weight_bytes().ok_or(CoDesignError::Overflow)?;
        if weights > capacity {
            return Err(CoDesignError::ModelDoesNotFit {
                weight_bytes: weights,
                capacity_bytes: capacity,
            });
        }
        let mut experiment = base.clone();
        experiment.experiment_name = format!("{}--{}", base.experiment_name, self.name);
        experiment.model = self.model.clone();
        experiment.hardware = hardware.clone();
        let quality_target = QualityTarget::for_model(
            &self.model,
            &base.quality_suite_id,
            &QualityVariantContext {
                name: self.name.clone(),
                changes: self.changes.clone(),
            },
        )
        .map_err(|error| CoDesignError::QualityIdentity(error.to_string()))?;
        Ok(CoDesignCandidate {
            name: self.name.clone(),
            changes: self.changes.clone(),
            experiment,
            quality: self.quality.clone(),
            quality_target,
            requires_structured_sparse_execution: self.requires_structured_sparse_execution,
        })
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct CoDesignCandidate {
    pub name: String,
    pub changes: Vec<ModelChange>,
    pub experiment: ExperimentSpec,
    pub quality: QualityEvidence,
    pub quality_target: QualityTarget,
    pub requires_structured_sparse_execution: bool,
}

impl CoDesignCandidate {
    pub fn permits_economic_conclusion(&self) -> bool {
        let expected = QualityTarget::for_experiment(
            &self.experiment,
            &QualityVariantContext {
                name: self.name.clone(),
                changes: self.changes.clone(),
            },
        );
        matches!(expected, Ok(target) if target == self.quality_target && self.quality.gate_for(&target).permits_economic_conclusion())
    }
}

fn apply_kv_head_count(model: &mut ModelSpec, heads: u32) -> Result<(), CoDesignError> {
    if heads == 0 || heads > model.attention_head_count || model.attention_head_count % heads != 0 {
        return Err(CoDesignError::InvalidArchitectureChange);
    }
    let old_projection = projection_parameters(model, model.kv_head_count)?;
    let new_projection = projection_parameters(model, heads)?;
    model.parameter_count =
        replace_parameter_component(model.parameter_count, old_projection, new_projection)?;
    model.kv_head_count = heads;
    Ok(())
}

fn apply_intermediate_size(model: &mut ModelSpec, size: u32) -> Result<(), CoDesignError> {
    if size == 0 {
        return Err(CoDesignError::InvalidArchitectureChange);
    }
    let old = ffn_parameters(
        model.hidden_size,
        model.intermediate_size,
        model.layer_count,
    )?;
    let new = ffn_parameters(model.hidden_size, size, model.layer_count)?;
    model.parameter_count = replace_parameter_component(model.parameter_count, old, new)?;
    model.intermediate_size = size;
    Ok(())
}

fn projection_parameters(model: &ModelSpec, kv_heads: u32) -> Result<u64, CoDesignError> {
    u64::from(kv_heads)
        .checked_mul(u64::from(model.head_dimension))
        .and_then(|value| value.checked_mul(u64::from(model.hidden_size)))
        .and_then(|value| value.checked_mul(2))
        .and_then(|value| value.checked_mul(u64::from(model.layer_count)))
        .ok_or(CoDesignError::Overflow)
}

fn ffn_parameters(hidden: u32, intermediate: u32, layers: u32) -> Result<u64, CoDesignError> {
    u64::from(hidden)
        .checked_mul(u64::from(intermediate))
        .and_then(|value| value.checked_mul(3))
        .and_then(|value| value.checked_mul(u64::from(layers)))
        .ok_or(CoDesignError::Overflow)
}

fn replace_parameter_component(
    total: u64,
    old_component: u64,
    new_component: u64,
) -> Result<u64, CoDesignError> {
    total
        .checked_sub(old_component)
        .and_then(|value| value.checked_add(new_component))
        .ok_or(CoDesignError::InvalidArchitectureChange)
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum CoDesignError {
    #[error("model variant must have a name and at least one change")]
    InvalidVariant,
    #[error("structured parameter density {0} is outside (0, 1]")]
    InvalidDensity(f64),
    #[error("model architecture change is invalid")]
    InvalidArchitectureChange,
    #[error("model architecture change exceeded numeric limits")]
    Overflow,
    #[error("hardware does not support {0:?} arithmetic")]
    UnsupportedPrecision(Precision),
    #[error("hardware does not expose memory capacity")]
    MissingHardwareCapacity,
    #[error("model needs {weight_bytes} bytes but hardware has {capacity_bytes}")]
    ModelDoesNotFit {
        weight_bytes: u64,
        capacity_bytes: u64,
    },
    #[error("quality target identity failed: {0}")]
    QualityIdentity(String),
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::spec::ModelArchitecture;

    fn qwen() -> ModelSpec {
        ModelSpec {
            model_id: "Qwen/Qwen3-8B".into(),
            model_revision: "reference-fixture-v1".into(),
            architecture: ModelArchitecture::DenseDecoder,
            parameter_count: 8_200_000_000,
            layer_count: 36,
            hidden_size: 4_096,
            intermediate_size: 12_288,
            attention_head_count: 32,
            kv_head_count: 8,
            head_dimension: 128,
            vocabulary_size: 151_936,
            max_sequence_length: 32_768,
            weight_precision: Precision::Bf16,
            quantized_weight_storage: None,
            kv_precision: Precision::Fp16,
        }
    }

    #[test]
    fn qwen_specific_changes_alter_weight_and_kv_cost_geometry() {
        let baseline = qwen();
        let variant = ModelVariant {
            name: "qwen-int4-gqa4".into(),
            changes: vec![
                ModelChange::EquivalentRotation {
                    family: "spin".into(),
                },
                ModelChange::WeightPrecision {
                    precision: Precision::Int4,
                    quantized_storage: Some(QuantizedWeightStorageSpec::grouped_all(
                        128, 4, 16, 16, 0,
                    )),
                },
                ModelChange::KvPrecision {
                    precision: Precision::Fp8,
                },
                ModelChange::KvHeadCount { heads: 4 },
            ],
            quality: QualityEvidence::Unvalidated,
        }
        .apply(&baseline)
        .unwrap();

        assert!(variant.model.weight_bytes().unwrap() < baseline.weight_bytes().unwrap());
        assert!(
            variant.model.kv_bytes_per_token().unwrap() < baseline.kv_bytes_per_token().unwrap()
        );
        assert_eq!(variant.model.kv_head_count, 4);
        let target = QualityTarget::for_model(
            &variant.model,
            "agentic-v1",
            &QualityVariantContext {
                name: variant.name.clone(),
                changes: variant.changes.clone(),
            },
        )
        .unwrap();
        assert_eq!(variant.quality.gate_for(&target), QualityGate::Unvalidated);
    }

    #[test]
    fn ffn_and_sparse_changes_reduce_effective_parameter_work() {
        let baseline = qwen();
        let variant = ModelVariant {
            name: "smaller-ffn-sparse".into(),
            changes: vec![
                ModelChange::IntermediateSize { size: 10_240 },
                ModelChange::StructuredParameterDensity { density: 0.75 },
            ],
            quality: QualityEvidence::Surrogate {
                predicted_delta: -0.01,
                uncertainty: 0.02,
            },
        }
        .apply(&baseline)
        .unwrap();

        assert!(variant.model.parameter_count < baseline.parameter_count);
        assert!(variant.requires_structured_sparse_execution);
        let target = QualityTarget::for_model(
            &variant.model,
            "agentic-v1",
            &QualityVariantContext {
                name: variant.name.clone(),
                changes: variant.changes.clone(),
            },
        )
        .unwrap();
        assert_eq!(variant.quality.gate_for(&target), QualityGate::Surrogate);
    }

    #[test]
    fn only_measured_passing_quality_for_the_exact_target_can_support_the_claim() {
        let target =
            QualityTarget::for_model(&qwen(), "agentic-v1", &QualityVariantContext::baseline())
                .unwrap();
        let measured = QualityEvidence::Measured {
            scope: MeasuredQualityScope {
                target: target.clone(),
                report_id: "quality-123".into(),
            },
            passed: true,
            worst_metric_delta: -0.001,
        };
        let failed = QualityEvidence::Measured {
            scope: MeasuredQualityScope {
                target: target.clone(),
                report_id: "quality-456".into(),
            },
            passed: false,
            worst_metric_delta: -0.1,
        };

        assert_eq!(measured.gate_for(&target), QualityGate::MeasuredPassed);
        assert_eq!(failed.gate_for(&target), QualityGate::ContractFailed);
        assert_eq!(
            QualityEvidence::Unvalidated.gate_for(&target),
            QualityGate::Unvalidated
        );
        let missing_report = QualityEvidence::Measured {
            scope: MeasuredQualityScope {
                target: target.clone(),
                report_id: " ".into(),
            },
            passed: true,
            worst_metric_delta: 0.0,
        };
        assert_eq!(
            missing_report.gate_for(&target),
            QualityGate::InvalidEvidence
        );
    }

    #[test]
    fn passing_evidence_for_another_model_revision_variant_or_suite_is_rejected() {
        let target =
            QualityTarget::for_model(&qwen(), "agentic-v1", &QualityVariantContext::baseline())
                .unwrap();
        let mismatches = [
            QualityTarget {
                model_id: "Qwen/Qwen3-0.6B".into(),
                ..target.clone()
            },
            QualityTarget {
                model_revision: "another-revision".into(),
                ..target.clone()
            },
            QualityTarget {
                model_fingerprint: "0".repeat(64),
                ..target.clone()
            },
            QualityTarget {
                variant_name: "int4".into(),
                ..target.clone()
            },
            QualityTarget {
                change_fingerprint: "1".repeat(64),
                ..target.clone()
            },
            QualityTarget {
                suite_id: "different-suite".into(),
                ..target.clone()
            },
        ];

        for mismatched in mismatches {
            let evidence = QualityEvidence::Measured {
                scope: MeasuredQualityScope {
                    target: mismatched,
                    report_id: "passing-report".into(),
                },
                passed: true,
                worst_metric_delta: 0.0,
            };
            assert_eq!(evidence.gate_for(&target), QualityGate::ScopeMismatch);
        }
    }

    #[test]
    fn weight_only_int4_evidence_does_not_cover_kv_or_ffn_changes() {
        let baseline = qwen();
        let int4_variant = ModelVariant {
            name: "weight-int4".into(),
            changes: vec![ModelChange::WeightPrecision {
                precision: Precision::Int4,
                quantized_storage: Some(QuantizedWeightStorageSpec::grouped_all(128, 4, 16, 16, 0)),
            }],
            quality: QualityEvidence::Unvalidated,
        };
        let int4_model = int4_variant.apply(&baseline).unwrap().model;
        let int4_target = QualityTarget::for_model(
            &int4_model,
            "agentic-v1",
            &QualityVariantContext {
                name: int4_variant.name.clone(),
                changes: int4_variant.changes.clone(),
            },
        )
        .unwrap();
        let evidence = QualityEvidence::Measured {
            scope: MeasuredQualityScope {
                target: int4_target,
                report_id: "weight-int4-report".into(),
            },
            passed: true,
            worst_metric_delta: 0.0,
        };
        let other_variants = [
            ModelVariant {
                name: "kv-int8".into(),
                changes: vec![ModelChange::KvPrecision {
                    precision: Precision::Int8,
                }],
                quality: QualityEvidence::Unvalidated,
            },
            ModelVariant {
                name: "smaller-ffn".into(),
                changes: vec![ModelChange::IntermediateSize { size: 10_240 }],
                quality: QualityEvidence::Unvalidated,
            },
        ];

        for variant in other_variants {
            let effective = variant.apply(&baseline).unwrap();
            let target = QualityTarget::for_model(
                &effective.model,
                "agentic-v1",
                &QualityVariantContext {
                    name: effective.name,
                    changes: effective.changes,
                },
            )
            .unwrap();
            assert_eq!(evidence.gate_for(&target), QualityGate::ScopeMismatch);
        }
    }

    #[test]
    fn quantized_storage_metadata_is_part_of_the_quality_change_fingerprint() {
        let baseline = qwen();
        let target_for = |group_size| {
            let variant = ModelVariant {
                name: format!("weight-int4-g{group_size}"),
                changes: vec![ModelChange::WeightPrecision {
                    precision: Precision::Int4,
                    quantized_storage: Some(QuantizedWeightStorageSpec::grouped_all(
                        group_size, 4, 16, 16, 0,
                    )),
                }],
                quality: QualityEvidence::Unvalidated,
            };
            let effective = variant.apply(&baseline).unwrap();
            QualityTarget::for_model(
                &effective.model,
                "agentic-v1",
                &QualityVariantContext {
                    name: effective.name,
                    changes: effective.changes,
                },
            )
            .unwrap()
        };
        let group_128 = target_for(128);
        let group_64 = target_for(64);
        let evidence = QualityEvidence::Measured {
            scope: MeasuredQualityScope {
                target: group_128.clone(),
                report_id: "group-128-quality".into(),
            },
            passed: true,
            worst_metric_delta: 0.0,
        };

        assert_ne!(group_128.change_fingerprint, group_64.change_fingerprint);
        assert_eq!(evidence.gate_for(&group_64), QualityGate::ScopeMismatch);
    }

    #[test]
    fn legacy_unscoped_measured_evidence_is_rejected_during_import() {
        let legacy = r#"{
            "evidence": "measured",
            "report_artifact": "quality-report",
            "passed": true,
            "worst_metric_delta": 0.0
        }"#;

        assert!(serde_json::from_str::<QualityEvidence>(legacy).is_err());
    }

    #[test]
    fn invalid_kv_geometry_is_rejected() {
        let error = ModelVariant {
            name: "invalid".into(),
            changes: vec![ModelChange::KvHeadCount { heads: 3 }],
            quality: QualityEvidence::Unvalidated,
        }
        .apply(&qwen())
        .unwrap_err();

        assert_eq!(error, CoDesignError::InvalidArchitectureChange);
    }
}
