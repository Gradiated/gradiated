use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::capacity::{CapacityError, CapacityPlan, plan_capacity};
use crate::codesign::{
    CoDesignError, ModelChange, ModelVariant, QualityEvidence, QualityTarget, QualityVariantContext,
};
use crate::experiment::{CostChoice, RunOptions};
use crate::sizing::{
    ConstraintViolation, HardwareSizer, HardwareSizingConstraints, HardwareSizingReport,
    SizingError,
};
use crate::spec::{ExperimentSpec, KernelSpec};

const HARDWARE_THROUGHPUT_FACTORS: [f64; 7] = [0.5, 0.75, 1.0, 1.5, 2.0, 4.0, 8.0];

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct HardwareTrialSummary {
    pub target_output_tokens_per_second: f64,
    pub physical_devices_per_replica: u32,
    pub hbm_capacity_bytes: u64,
    pub hbm_bandwidth_bytes_per_second: f64,
    pub required_replicas: Option<u32>,
    pub input_cost_per_million_tokens: Option<f64>,
    pub output_cost_per_million_tokens: Option<f64>,
    pub p95_ttft_milliseconds: f64,
    pub p95_tpot_milliseconds: f64,
    pub slo_passed: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct RejectedHardwareTrial {
    pub target_output_tokens_per_second: f64,
    pub physical_devices_provisioned: u32,
    pub minimum_required_device_count: u32,
    pub violations: Vec<ConstraintViolation>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Serialize)]
pub struct StudyOverrides {
    pub kernel: Option<KernelSpec>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct CoDesignStudyReport {
    pub baseline_spec_id: String,
    pub candidate_spec: ExperimentSpec,
    pub variant_name: String,
    pub variant_changes: Vec<ModelChange>,
    pub quality: QualityEvidence,
    pub quality_target: QualityTarget,
    pub hardware_sizing: HardwareSizingReport,
    pub capacity: CapacityPlan,
    pub hardware_trials: Vec<HardwareTrialSummary>,
    #[serde(default)]
    pub rejected_hardware_trials: Vec<RejectedHardwareTrial>,
    pub selection_score_usd_per_million_tokens: Option<f64>,
    pub production_claim_permitted: bool,
    pub limitations: Vec<String>,
}

pub fn run_codesign_study(
    baseline: &ExperimentSpec,
    variant: Option<&ModelVariant>,
    constraints: &HardwareSizingConstraints,
    options: &RunOptions,
    maximum_replicas: u32,
) -> Result<CoDesignStudyReport, StudyError> {
    run_codesign_study_with_overrides(
        baseline,
        variant,
        constraints,
        options,
        maximum_replicas,
        &StudyOverrides::default(),
    )
}

pub fn run_codesign_study_with_overrides(
    baseline: &ExperimentSpec,
    variant: Option<&ModelVariant>,
    constraints: &HardwareSizingConstraints,
    options: &RunOptions,
    maximum_replicas: u32,
    overrides: &StudyOverrides,
) -> Result<CoDesignStudyReport, StudyError> {
    baseline.validate().map_err(StudyError::InvalidBaseline)?;
    let (variant_name, variant_changes, model, quality) = match variant {
        Some(variant) => {
            let effective = variant.apply(&baseline.model)?;
            (
                effective.name,
                effective.changes,
                effective.model,
                effective.quality,
            )
        }
        None => (
            crate::codesign::BASELINE_VARIANT_NAME.into(),
            Vec::new(),
            baseline.model.clone(),
            options.quality.clone(),
        ),
    };
    let quality_variant = QualityVariantContext {
        name: variant_name.clone(),
        changes: variant_changes.clone(),
    };
    let quality_target =
        QualityTarget::for_model(&model, &baseline.quality_suite_id, &quality_variant)
            .map_err(|error| StudyError::QualityIdentity(error.to_string()))?;
    let mut bundles = Vec::new();
    let mut rejected_hardware_trials = Vec::new();
    for factor in HARDWARE_THROUGHPUT_FACTORS {
        let mut trial_constraints = *constraints;
        trial_constraints.serving.target_output_tokens_per_second =
            constraints.serving.target_output_tokens_per_second * factor;
        let hardware_sizing = HardwareSizer.synthesize(&model, &trial_constraints)?;
        if !hardware_sizing.is_feasible() {
            rejected_hardware_trials.push(rejected_trial(
                &hardware_sizing,
                trial_constraints.serving.target_output_tokens_per_second,
            ));
            continue;
        }
        let candidate_spec = candidate_spec(
            baseline,
            &variant_name,
            &model,
            &hardware_sizing,
            &trial_constraints,
            overrides,
        )?;
        if bundles
            .iter()
            .any(|bundle: &StudyBundle| bundle.hardware_sizing.hardware == hardware_sizing.hardware)
        {
            continue;
        }
        let run_options = run_options(
            options,
            &quality,
            &quality_variant,
            &hardware_sizing,
            &trial_constraints,
        )?;
        let capacity = plan_capacity(&candidate_spec, &run_options, maximum_replicas)?;
        let score = selection_score(baseline, &capacity);
        bundles.push(StudyBundle {
            candidate_spec,
            hardware_sizing,
            capacity,
            score,
            target_output_tokens_per_second: trial_constraints
                .serving
                .target_output_tokens_per_second,
        });
    }
    let selected_index = bundles
        .iter()
        .enumerate()
        .filter_map(|(index, bundle)| bundle.score.map(|score| (index, score)))
        .min_by(|left, right| left.1.total_cmp(&right.1))
        .map(|(index, _)| index)
        .unwrap_or_else(|| {
            bundles
                .iter()
                .enumerate()
                .min_by(|left, right| {
                    slo_violation(&left.1.capacity).total_cmp(&slo_violation(&right.1.capacity))
                })
                .map(|(index, _)| index)
                .unwrap_or(0)
        });
    let hardware_trials = bundles.iter().map(trial_summary).collect::<Vec<_>>();
    let selected = bundles
        .into_iter()
        .nth(selected_index)
        .ok_or(StudyError::NoHardwareCandidates)?;
    let candidate_spec = selected.candidate_spec;
    let hardware_sizing = selected.hardware_sizing;
    let capacity = selected.capacity;
    let selection_score_usd_per_million_tokens = selected.score;
    let production_claim_permitted = false;
    let mut limitations = hardware_sizing
        .assumptions
        .iter()
        .map(|assumption| format!("{}: {}", assumption.name, assumption.consequence))
        .collect::<Vec<_>>();
    let quality_gate = quality.gate_for(&quality_target);
    if !quality_gate.permits_economic_conclusion() {
        limitations.push(format!(
            "candidate quality gate is {quality_gate:?} for the exact model, variant, and suite"
        ));
    }
    if capacity.required_replicas.is_none() {
        limitations.push("no fleet size within the search bound met both latency SLOs".into());
    }
    limitations.push(
        "hardware sizing and tensor-tile timing remain analytical until externally calibrated"
            .into(),
    );
    Ok(CoDesignStudyReport {
        baseline_spec_id: baseline
            .content_id()
            .map_err(|error| StudyError::Identity(error.to_string()))?
            .to_hex(),
        candidate_spec,
        variant_name,
        variant_changes,
        quality,
        quality_target,
        hardware_sizing,
        capacity,
        hardware_trials,
        rejected_hardware_trials,
        selection_score_usd_per_million_tokens,
        production_claim_permitted,
        limitations,
    })
}

fn rejected_trial(
    sizing: &HardwareSizingReport,
    target_output_tokens_per_second: f64,
) -> RejectedHardwareTrial {
    RejectedHardwareTrial {
        target_output_tokens_per_second,
        physical_devices_provisioned: sizing.mapping.device_count,
        minimum_required_device_count: sizing.mapping.minimum_required_device_count,
        violations: sizing.violations.clone(),
    }
}

struct StudyBundle {
    candidate_spec: ExperimentSpec,
    hardware_sizing: HardwareSizingReport,
    capacity: CapacityPlan,
    score: Option<f64>,
    target_output_tokens_per_second: f64,
}

fn candidate_spec(
    baseline: &ExperimentSpec,
    variant_name: &str,
    model: &crate::spec::ModelSpec,
    sizing: &HardwareSizingReport,
    constraints: &HardwareSizingConstraints,
    overrides: &StudyOverrides,
) -> Result<ExperimentSpec, StudyError> {
    let mut candidate = baseline.clone();
    candidate.experiment_name = format!(
        "{}--{}--sized-hardware-{}",
        baseline.experiment_name, variant_name, constraints.serving.target_output_tokens_per_second
    );
    candidate.model = model.clone();
    candidate.hardware = sizing.hardware.clone();
    candidate.mapping.tensor_parallelism = sizing.mapping.tensor_parallelism;
    candidate.mapping.pipeline_parallelism = 1;
    candidate.mapping.data_parallelism = 1;
    candidate.serving.max_concurrent_requests = constraints.serving.max_concurrent_requests;
    candidate.serving.max_batch_size = constraints.serving.decode_batch_size;
    if let Some(kernel) = &overrides.kernel {
        candidate.kernel = kernel.clone();
    }
    candidate.validate().map_err(StudyError::InvalidCandidate)?;
    Ok(candidate)
}

fn run_options(
    options: &RunOptions,
    quality: &QualityEvidence,
    quality_variant: &QualityVariantContext,
    sizing: &HardwareSizingReport,
    constraints: &HardwareSizingConstraints,
) -> Result<RunOptions, StudyError> {
    let mut run_options = options.clone();
    run_options.quality = quality.clone();
    run_options.quality_variant = Some(quality_variant.clone());
    if let CostChoice::CustomSilicon(mut server) = run_options.cost {
        server.memory_usd_per_accelerator = f64::from(
            sizing
                .mapping
                .device_count
                .checked_mul(sizing.mapping.hbm_stacks_per_device)
                .ok_or(StudyError::HardwareCountOverflow)?,
        ) * constraints.memory.hbm_stack_cost_usd;
        run_options.cost = CostChoice::CustomSilicon(server);
    }
    Ok(run_options)
}

fn selection_score(baseline: &ExperimentSpec, capacity: &CapacityPlan) -> Option<f64> {
    let selected = capacity.selected.as_ref()?;
    let input_tokens = baseline
        .workload
        .request_classes
        .iter()
        .map(|class| class.share * f64::from(class.input_tokens))
        .sum::<f64>();
    let output_tokens = baseline
        .workload
        .request_classes
        .iter()
        .map(|class| class.share * f64::from(class.output_tokens))
        .sum::<f64>();
    let total_tokens = input_tokens + output_tokens;
    Some(
        input_tokens / total_tokens * selected.costs.input.cost_per_million_tokens
            + output_tokens / total_tokens * selected.costs.output.cost_per_million_tokens,
    )
}

fn slo_violation(capacity: &CapacityPlan) -> f64 {
    capacity
        .evaluated_points
        .iter()
        .map(|point| point.p95_ttft_milliseconds + point.p95_tpot_milliseconds)
        .reduce(f64::min)
        .unwrap_or(f64::INFINITY)
}

fn trial_summary(bundle: &StudyBundle) -> HardwareTrialSummary {
    let selected = bundle.capacity.selected.as_ref();
    let point = selected
        .map(|report| {
            (
                report.simulation.p95_ttft_milliseconds,
                report.simulation.p95_tpot_milliseconds,
            )
        })
        .or_else(|| {
            bundle
                .capacity
                .evaluated_points
                .iter()
                .min_by(|left, right| {
                    (left.p95_ttft_milliseconds + left.p95_tpot_milliseconds)
                        .total_cmp(&(right.p95_ttft_milliseconds + right.p95_tpot_milliseconds))
                })
                .map(|point| (point.p95_ttft_milliseconds, point.p95_tpot_milliseconds))
        })
        .unwrap_or((f64::INFINITY, f64::INFINITY));
    HardwareTrialSummary {
        target_output_tokens_per_second: bundle.target_output_tokens_per_second,
        physical_devices_per_replica: bundle.hardware_sizing.mapping.device_count,
        hbm_capacity_bytes: bundle.hardware_sizing.provisioned.hbm_capacity_bytes,
        hbm_bandwidth_bytes_per_second: bundle
            .hardware_sizing
            .provisioned
            .hbm_bandwidth_bytes_per_second,
        required_replicas: bundle.capacity.required_replicas,
        input_cost_per_million_tokens: selected
            .map(|report| report.costs.input.cost_per_million_tokens),
        output_cost_per_million_tokens: selected
            .map(|report| report.costs.output.cost_per_million_tokens),
        p95_ttft_milliseconds: point.0,
        p95_tpot_milliseconds: point.1,
        slo_passed: selected.is_some(),
    }
}

#[derive(Debug, Error)]
pub enum StudyError {
    #[error("baseline specification is invalid: {0}")]
    InvalidBaseline(crate::spec::ValidationErrors),
    #[error("generated candidate specification is invalid: {0}")]
    InvalidCandidate(crate::spec::ValidationErrors),
    #[error("model variant failed: {0}")]
    ModelVariant(#[from] CoDesignError),
    #[error("hardware sizing failed: {0}")]
    Sizing(#[from] SizingError),
    #[error("capacity planning failed: {0}")]
    Capacity(#[from] CapacityError),
    #[error("experiment identity failed: {0}")]
    Identity(String),
    #[error("quality target identity failed: {0}")]
    QualityIdentity(String),
    #[error("hardware component count overflow")]
    HardwareCountOverflow,
    #[error("hardware co-design search produced no candidates")]
    NoHardwareCandidates,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::codesign::{MeasuredQualityScope, ModelChange, QualityGate};
    use crate::spec::Precision;

    fn baseline() -> ExperimentSpec {
        let mut spec: ExperimentSpec =
            serde_json::from_str(include_str!("../../../configs/qwen3-8b-agentic-h100.json"))
                .unwrap();
        spec.workload.request_count = 16;
        spec.serving.ttft_slo_milliseconds = 60_000.0;
        spec.serving.tpot_slo_milliseconds = 200.0;
        spec
    }

    fn constraints() -> HardwareSizingConstraints {
        let mut constraints = HardwareSizingConstraints::default();
        constraints.serving.max_concurrent_requests = 8;
        constraints.serving.reserved_sequence_tokens_per_request = 32_768;
        constraints.serving.decode_batch_size = 8;
        constraints.serving.target_output_tokens_per_second = 500.0;
        constraints
    }

    #[test]
    fn model_variant_is_resized_remapped_and_capacity_planned_as_one_candidate() {
        let variant = ModelVariant {
            name: "qwen-w4-kv8".into(),
            changes: vec![
                ModelChange::WeightPrecision {
                    precision: Precision::Int4,
                    quantized_storage: Some(crate::spec::QuantizedWeightStorageSpec::grouped_all(
                        128, 4, 16, 16, 0,
                    )),
                },
                ModelChange::KvPrecision {
                    precision: Precision::Fp8,
                },
            ],
            quality: QualityEvidence::Unvalidated,
        };

        let report = run_codesign_study(
            &baseline(),
            Some(&variant),
            &constraints(),
            &RunOptions::default(),
            64,
        )
        .unwrap();

        assert_eq!(
            report.candidate_spec.model.weight_precision,
            Precision::Int4
        );
        assert_eq!(report.candidate_spec.model.kv_precision, Precision::Fp8);
        assert_eq!(
            report.candidate_spec.hardware.physical_device_count,
            report.hardware_sizing.mapping.device_count
        );
        assert_eq!(
            report.candidate_spec.mapping.tensor_parallelism,
            report.hardware_sizing.mapping.tensor_parallelism
        );
        assert!(report.capacity.required_replicas.is_some());
        assert!(!report.production_claim_permitted);
    }

    #[test]
    fn exact_variant_quality_scope_propagates_to_the_selected_experiment() {
        let baseline = baseline();
        let name = "qwen-weight-int4";
        let changes = vec![ModelChange::WeightPrecision {
            precision: Precision::Int4,
            quantized_storage: Some(crate::spec::QuantizedWeightStorageSpec::grouped_all(
                128, 4, 16, 16, 0,
            )),
        }];
        let effective = ModelVariant {
            name: name.into(),
            changes: changes.clone(),
            quality: QualityEvidence::Unvalidated,
        }
        .apply(&baseline.model)
        .unwrap();
        let target = QualityTarget::for_model(
            &effective.model,
            &baseline.quality_suite_id,
            &QualityVariantContext {
                name: name.into(),
                changes: changes.clone(),
            },
        )
        .unwrap();
        let variant = ModelVariant {
            name: name.into(),
            changes,
            quality: QualityEvidence::Measured {
                scope: MeasuredQualityScope {
                    target: target.clone(),
                    report_id: "qwen-weight-int4-quality".into(),
                },
                passed: true,
                worst_metric_delta: 0.0,
            },
        };

        let report = run_codesign_study(
            &baseline,
            Some(&variant),
            &constraints(),
            &RunOptions::default(),
            64,
        )
        .unwrap();

        assert_eq!(report.quality_target, target);
        assert_eq!(
            report.quality.gate_for(&target),
            QualityGate::MeasuredPassed
        );
        assert!(
            report
                .capacity
                .selected
                .as_ref()
                .unwrap()
                .quality_gated_comparison_permitted
        );
    }

    #[test]
    fn weight_and_kv_changes_materially_resize_the_hardware_envelope() {
        let variant = ModelVariant {
            name: "compressed".into(),
            changes: vec![
                ModelChange::WeightPrecision {
                    precision: Precision::Int4,
                    quantized_storage: Some(crate::spec::QuantizedWeightStorageSpec::grouped_all(
                        128, 4, 16, 16, 0,
                    )),
                },
                ModelChange::KvPrecision {
                    precision: Precision::Fp8,
                },
            ],
            quality: QualityEvidence::Unvalidated,
        };
        let baseline = baseline();
        let baseline_sizing = HardwareSizer
            .synthesize(&baseline.model, &constraints())
            .unwrap();
        let candidate = variant.apply(&baseline.model).unwrap();
        let candidate_sizing = HardwareSizer
            .synthesize(&candidate.model, &constraints())
            .unwrap();

        assert!(
            candidate_sizing.requirements.total_hbm_bytes
                < baseline_sizing.requirements.total_hbm_bytes
        );
        assert!(
            candidate_sizing
                .requirements
                .memory_bandwidth_bytes_per_second
                < baseline_sizing
                    .requirements
                    .memory_bandwidth_bytes_per_second
        );
    }

    #[test]
    fn infeasible_hardware_trials_are_rejected_before_simulation() {
        let mut constraints = constraints();
        constraints.physical.max_devices = 4;

        let report =
            run_codesign_study(&baseline(), None, &constraints, &RunOptions::default(), 64)
                .unwrap();

        assert!(report.hardware_sizing.is_feasible());
        assert!(!report.rejected_hardware_trials.is_empty());
        assert!(
            report
                .rejected_hardware_trials
                .iter()
                .all(|trial| !trial.violations.is_empty())
        );
        assert!(report.hardware_trials.iter().all(|trial| {
            !report.rejected_hardware_trials.iter().any(|rejected| {
                rejected.target_output_tokens_per_second == trial.target_output_tokens_per_second
            })
        }));
    }
}
