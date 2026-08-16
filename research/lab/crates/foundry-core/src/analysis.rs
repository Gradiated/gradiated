use crate::codesign::{QualityEvidence, QualityGate, QualityTarget, QualityVariantContext};
use crate::decision::{DecisionError, OptimizationAxis, OptimizationDecision, OptimizationDossier};
use crate::study::CoDesignStudyReport;
use crate::workload::{
    AgentTurnClass, CanonicalTraceRequest, CanonicalTraceV2, RequestTimingObservation,
    TimestampBasis, TraceObservations, TraceProvenance, WorkloadContractV2, WorkloadSloReport,
    evaluate_trace,
};
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct DecisionMetadata {
    pub axis: OptimizationAxis,
    pub name: String,
    pub model_specific_reason: String,
    pub mechanism: String,
    pub confidence: f64,
    pub evidence_artifacts: Vec<String>,
}

pub fn compare_studies(
    baseline: &CoDesignStudyReport,
    candidate: &CoDesignStudyReport,
    metadata: DecisionMetadata,
) -> Result<OptimizationDecision, StudyAnalysisError> {
    if baseline.candidate_spec.model.model_id != candidate.candidate_spec.model.model_id
        || baseline.candidate_spec.model.model_revision
            != candidate.candidate_spec.model.model_revision
        || baseline.candidate_spec.quality_suite_id != candidate.candidate_spec.quality_suite_id
        || baseline.candidate_spec.quality_constraints
            != candidate.candidate_spec.quality_constraints
        || baseline.candidate_spec.workload != candidate.candidate_spec.workload
        || baseline.candidate_spec.serving.ttft_slo_milliseconds
            != candidate.candidate_spec.serving.ttft_slo_milliseconds
        || baseline.candidate_spec.serving.tpot_slo_milliseconds
            != candidate.candidate_spec.serving.tpot_slo_milliseconds
    {
        return Err(StudyAnalysisError::ComparisonContractMismatch);
    }
    if !metadata.confidence.is_finite() || !(0.0..=1.0).contains(&metadata.confidence) {
        return Err(StudyAnalysisError::InvalidConfidence);
    }
    let baseline_result = baseline
        .capacity
        .selected
        .as_ref()
        .ok_or(StudyAnalysisError::NoFeasibleBaseline)?;
    let candidate_result = candidate
        .capacity
        .selected
        .as_ref()
        .ok_or(StudyAnalysisError::NoFeasibleCandidate)?;
    let candidate_quality_gate = quality_gate(candidate)?;
    Ok(OptimizationDecision {
        axis: metadata.axis,
        name: metadata.name,
        qwen3_specific_reason: metadata.model_specific_reason,
        mechanism: metadata.mechanism,
        baseline_input_cost_per_million: baseline_result.costs.input.cost_per_million_tokens,
        candidate_input_cost_per_million: candidate_result.costs.input.cost_per_million_tokens,
        baseline_output_cost_per_million: baseline_result.costs.output.cost_per_million_tokens,
        candidate_output_cost_per_million: candidate_result.costs.output.cost_per_million_tokens,
        quality_delta: quality_delta(&candidate.quality, candidate_quality_gate),
        ttft_delta_milliseconds: candidate_result.simulation.p95_ttft_milliseconds
            - baseline_result.simulation.p95_ttft_milliseconds,
        tpot_delta_milliseconds: candidate_result.simulation.p95_tpot_milliseconds
            - baseline_result.simulation.p95_tpot_milliseconds,
        energy_delta_joules_per_million_tokens: energy_per_million(candidate_result)
            - energy_per_million(baseline_result),
        fidelity: candidate_result.oracle_fidelity,
        confidence: metadata.confidence,
        evidence_artifacts: metadata.evidence_artifacts,
    })
}

pub fn build_dossier(
    baseline: &CoDesignStudyReport,
    candidate: &CoDesignStudyReport,
    decisions: Vec<OptimizationDecision>,
    conclusion: impl Into<String>,
) -> Result<OptimizationDossier, StudyAnalysisError> {
    let baseline_result = baseline
        .capacity
        .selected
        .as_ref()
        .ok_or(StudyAnalysisError::NoFeasibleBaseline)?;
    let candidate_result = candidate
        .capacity
        .selected
        .as_ref()
        .ok_or(StudyAnalysisError::NoFeasibleCandidate)?;
    let candidate_quality_gate = quality_gate(candidate)?;
    let dossier = OptimizationDossier {
        model_id: candidate.candidate_spec.model.model_id.clone(),
        workload_id: format!("agentic-seed-{}", candidate.candidate_spec.workload.seed),
        baseline_name: baseline.candidate_spec.experiment_name.clone(),
        candidate_name: candidate.candidate_spec.experiment_name.clone(),
        baseline_input_cost_per_million: baseline_result.costs.input.cost_per_million_tokens,
        candidate_input_cost_per_million: candidate_result.costs.input.cost_per_million_tokens,
        baseline_output_cost_per_million: baseline_result.costs.output.cost_per_million_tokens,
        candidate_output_cost_per_million: candidate_result.costs.output.cost_per_million_tokens,
        quality_contract_passed: candidate_quality_gate.permits_economic_conclusion(),
        slo_contract_passed: true,
        decisions,
        conclusion: conclusion.into(),
    };
    dossier.validate()?;
    Ok(dossier)
}

pub fn evaluate_study_slos(
    study: &CoDesignStudyReport,
    contract: &WorkloadContractV2,
) -> Result<WorkloadSloReport, StudyAnalysisError> {
    let selected = study
        .capacity
        .selected
        .as_ref()
        .ok_or(StudyAnalysisError::NoFeasibleCandidate)?;
    let trace_id = format!("simulation-{}", selected.spec_id);
    let mut trace_requests = Vec::with_capacity(selected.simulation.requests.len());
    let mut observations = Vec::with_capacity(selected.simulation.requests.len());
    for request in &selected.simulation.requests {
        trace_requests.push(CanonicalTraceRequest {
            request_id: request.request_id,
            class: agent_turn_class(&request.class_name)?,
            arrival_timestamp_microseconds: seconds_to_microseconds(request.arrival_seconds)?,
            input_tokens: request.input_tokens,
            output_tokens: request.output_tokens,
            prefix_reused_tokens: request.cached_prefix_tokens,
        });
        observations.push(RequestTimingObservation {
            request_id: request.request_id,
            first_token_timestamp_microseconds: seconds_to_microseconds(
                request.first_token_seconds,
            )?,
            completion_timestamp_microseconds: seconds_to_microseconds(request.completion_seconds)?,
        });
    }
    let trace = CanonicalTraceV2 {
        schema_version: crate::workload::WORKLOAD_SCHEMA_VERSION,
        trace_id: trace_id.clone(),
        provenance: TraceProvenance::Synthetic {
            generator_id: "foundry-serving-simulation".into(),
            seed: study.candidate_spec.workload.seed,
        },
        timestamp_basis: TimestampBasis::RelativeMicroseconds,
        identity: contract.identity.clone(),
        requests: trace_requests,
    };
    let observations = TraceObservations {
        trace_id,
        requests: observations,
    };
    evaluate_trace(contract, &trace, &observations)
        .map_err(|error| StudyAnalysisError::Workload(error.to_string()))
}

fn agent_turn_class(name: &str) -> Result<AgentTurnClass, StudyAnalysisError> {
    match name {
        "tool_turn" => Ok(AgentTurnClass::Tool),
        "coding_turn" => Ok(AgentTurnClass::Coding),
        "long_agent_turn" => Ok(AgentTurnClass::LongAgent),
        _ => Err(StudyAnalysisError::UnknownRequestClass(name.into())),
    }
}

fn seconds_to_microseconds(seconds: f64) -> Result<u64, StudyAnalysisError> {
    let microseconds = seconds * 1_000_000.0;
    if microseconds.is_finite() && microseconds >= 0.0 && microseconds <= u64::MAX as f64 {
        Ok(microseconds.round() as u64)
    } else {
        Err(StudyAnalysisError::InvalidTimestamp)
    }
}

fn quality_delta(evidence: &QualityEvidence, gate: QualityGate) -> Option<f64> {
    match evidence {
        QualityEvidence::Unvalidated => None,
        QualityEvidence::Surrogate {
            predicted_delta, ..
        } => Some(*predicted_delta),
        QualityEvidence::Measured {
            worst_metric_delta, ..
        } if matches!(
            gate,
            QualityGate::MeasuredPassed | QualityGate::ContractFailed
        ) =>
        {
            Some(*worst_metric_delta)
        }
        QualityEvidence::Measured { .. } => None,
    }
}

fn quality_gate(study: &CoDesignStudyReport) -> Result<QualityGate, StudyAnalysisError> {
    let expected = QualityTarget::for_model(
        &study.candidate_spec.model,
        &study.candidate_spec.quality_suite_id,
        &QualityVariantContext {
            name: study.variant_name.clone(),
            changes: study.variant_changes.clone(),
        },
    )
    .map_err(|error| StudyAnalysisError::QualityIdentity(error.to_string()))?;
    if expected != study.quality_target {
        return Err(StudyAnalysisError::QualityTargetMismatch);
    }
    let selected = study
        .capacity
        .selected
        .as_ref()
        .ok_or(StudyAnalysisError::NoFeasibleCandidate)?;
    if selected.quality != study.quality || selected.quality_target != expected {
        return Err(StudyAnalysisError::QualityEvidenceMismatch);
    }
    Ok(study.quality.gate_for(&expected))
}

fn energy_per_million(report: &crate::experiment::ExperimentReport) -> f64 {
    let tokens = report.simulation.input_tokens + report.simulation.output_tokens;
    if tokens == 0 {
        0.0
    } else {
        report.simulation.total_energy_joules * 1_000_000.0 / tokens as f64
    }
}

#[derive(Debug, Error)]
pub enum StudyAnalysisError {
    #[error("study comparison contracts do not match")]
    ComparisonContractMismatch,
    #[error("decision confidence must be in [0, 1]")]
    InvalidConfidence,
    #[error("baseline study has no SLO-feasible result")]
    NoFeasibleBaseline,
    #[error("candidate study has no SLO-feasible result")]
    NoFeasibleCandidate,
    #[error("dossier is invalid: {0}")]
    Decision(#[from] DecisionError),
    #[error("unknown canonical request class {0}")]
    UnknownRequestClass(String),
    #[error("simulation timestamp cannot be represented as microseconds")]
    InvalidTimestamp,
    #[error("workload evaluation failed: {0}")]
    Workload(String),
    #[error("quality target identity failed: {0}")]
    QualityIdentity(String),
    #[error("study quality target does not match its candidate model and variant")]
    QualityTargetMismatch,
    #[error("study and selected experiment quality evidence differ")]
    QualityEvidenceMismatch,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::codesign::{MeasuredQualityScope, ModelChange, ModelVariant};
    use crate::experiment::RunOptions;
    use crate::sizing::HardwareSizingConstraints;
    use crate::spec::{ExperimentSpec, Precision};
    use crate::study::run_codesign_study;

    fn study(variant: Option<&ModelVariant>) -> CoDesignStudyReport {
        let mut spec: ExperimentSpec =
            serde_json::from_str(include_str!("../../../configs/qwen3-8b-agentic-h100.json"))
                .unwrap();
        spec.workload.request_count = 8;
        spec.serving.ttft_slo_milliseconds = 60_000.0;
        spec.serving.tpot_slo_milliseconds = 200.0;
        let mut constraints = HardwareSizingConstraints::default();
        constraints.serving.max_concurrent_requests = 4;
        constraints.serving.decode_batch_size = 4;
        run_codesign_study(&spec, variant, &constraints, &RunOptions::default(), 16).unwrap()
    }

    #[test]
    fn unvalidated_model_changes_render_as_unmeasured_not_zero_quality_loss() {
        let baseline = study(None);
        let variant = ModelVariant {
            name: "kv8".into(),
            changes: vec![ModelChange::KvPrecision {
                precision: Precision::Fp8,
            }],
            quality: QualityEvidence::Unvalidated,
        };
        let candidate = study(Some(&variant));
        let decision = compare_studies(
            &baseline,
            &candidate,
            DecisionMetadata {
                axis: OptimizationAxis::Model,
                name: "FP8 KV".into(),
                model_specific_reason: "Qwen uses grouped-query attention".into(),
                mechanism: "halves KV bytes".into(),
                confidence: 0.25,
                evidence_artifacts: vec!["simulation".into()],
            },
        )
        .unwrap();
        let dossier = build_dossier(
            &baseline,
            &candidate,
            vec![decision],
            "Simulation only; quality validation remains open.",
        )
        .unwrap();

        assert!(!dossier.quality_contract_passed);
        assert!(dossier.render_markdown().unwrap().contains("unmeasured"));
    }

    #[test]
    fn passing_quality_for_another_model_does_not_pass_the_dossier_gate() {
        let baseline = study(None);
        let mut candidate = study(None);
        let mut wrong_model = candidate.candidate_spec.model.clone();
        wrong_model.model_id = "Qwen/Qwen3-0.6B".into();
        wrong_model.model_revision = "small-model-revision".into();
        wrong_model.parameter_count = 600_000_000;
        let wrong_target = QualityTarget::for_model(
            &wrong_model,
            &candidate.candidate_spec.quality_suite_id,
            &QualityVariantContext::baseline(),
        )
        .unwrap();
        candidate.quality = QualityEvidence::Measured {
            scope: MeasuredQualityScope {
                target: wrong_target,
                report_id: "qwen3-0.6b-int4".into(),
            },
            passed: true,
            worst_metric_delta: 0.0,
        };
        candidate.capacity.selected.as_mut().unwrap().quality = candidate.quality.clone();
        let decision = compare_studies(
            &baseline,
            &candidate,
            DecisionMetadata {
                axis: OptimizationAxis::Model,
                name: "wrong-model-evidence-check".into(),
                model_specific_reason: "quality evidence must match the exact model".into(),
                mechanism: "scope compatibility gate".into(),
                confidence: 1.0,
                evidence_artifacts: vec!["qwen3-0.6b-int4".into()],
            },
        )
        .unwrap();
        assert_eq!(decision.quality_delta, None);

        let dossier = build_dossier(
            &baseline,
            &candidate,
            vec![decision],
            "Wrong-model quality must remain blocked.",
        )
        .unwrap();

        assert!(!dossier.quality_contract_passed);
    }
}
