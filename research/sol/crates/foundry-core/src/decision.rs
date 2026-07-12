use crate::performance::OracleFidelity;
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum OptimizationAxis {
    Model,
    Kernel,
    Serving,
    Hardware,
    Mapping,
    Interaction,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct OptimizationDecision {
    pub axis: OptimizationAxis,
    pub name: String,
    pub qwen3_specific_reason: String,
    pub mechanism: String,
    pub baseline_input_cost_per_million: f64,
    pub candidate_input_cost_per_million: f64,
    pub baseline_output_cost_per_million: f64,
    pub candidate_output_cost_per_million: f64,
    pub quality_delta: Option<f64>,
    pub ttft_delta_milliseconds: f64,
    pub tpot_delta_milliseconds: f64,
    pub energy_delta_joules_per_million_tokens: f64,
    pub fidelity: OracleFidelity,
    pub confidence: f64,
    pub evidence_artifacts: Vec<String>,
}

impl OptimizationDecision {
    pub fn input_cost_reduction_fraction(&self) -> f64 {
        reduction_fraction(
            self.baseline_input_cost_per_million,
            self.candidate_input_cost_per_million,
        )
    }

    pub fn output_cost_reduction_fraction(&self) -> f64 {
        reduction_fraction(
            self.baseline_output_cost_per_million,
            self.candidate_output_cost_per_million,
        )
    }

    fn validate(&self) -> Result<(), DecisionError> {
        if self.name.trim().is_empty()
            || self.qwen3_specific_reason.trim().is_empty()
            || self.mechanism.trim().is_empty()
        {
            return Err(DecisionError::MissingDescription(self.name.clone()));
        }
        for value in [
            self.baseline_input_cost_per_million,
            self.candidate_input_cost_per_million,
            self.baseline_output_cost_per_million,
            self.candidate_output_cost_per_million,
        ] {
            if !value.is_finite() || value < 0.0 {
                return Err(DecisionError::InvalidCost(self.name.clone()));
            }
        }
        if self.quality_delta.is_some_and(|value| !value.is_finite())
            || !self.ttft_delta_milliseconds.is_finite()
            || !self.tpot_delta_milliseconds.is_finite()
            || !self.energy_delta_joules_per_million_tokens.is_finite()
            || !self.confidence.is_finite()
            || !(0.0..=1.0).contains(&self.confidence)
        {
            return Err(DecisionError::InvalidMeasurement(self.name.clone()));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct OptimizationDossier {
    pub model_id: String,
    pub workload_id: String,
    pub baseline_name: String,
    pub candidate_name: String,
    pub baseline_input_cost_per_million: f64,
    pub candidate_input_cost_per_million: f64,
    pub baseline_output_cost_per_million: f64,
    pub candidate_output_cost_per_million: f64,
    pub quality_contract_passed: bool,
    pub slo_contract_passed: bool,
    pub decisions: Vec<OptimizationDecision>,
    pub conclusion: String,
}

impl OptimizationDossier {
    pub fn validate(&self) -> Result<(), DecisionError> {
        if self.model_id.trim().is_empty()
            || self.workload_id.trim().is_empty()
            || self.baseline_name.trim().is_empty()
            || self.candidate_name.trim().is_empty()
            || self.conclusion.trim().is_empty()
        {
            return Err(DecisionError::MissingDossierField);
        }
        if self.decisions.is_empty() {
            return Err(DecisionError::EmptyDossier);
        }
        for decision in &self.decisions {
            decision.validate()?;
        }
        Ok(())
    }

    pub fn input_cost_reduction_fraction(&self) -> f64 {
        reduction_fraction(
            self.baseline_input_cost_per_million,
            self.candidate_input_cost_per_million,
        )
    }

    pub fn output_cost_reduction_fraction(&self) -> f64 {
        reduction_fraction(
            self.baseline_output_cost_per_million,
            self.candidate_output_cost_per_million,
        )
    }

    pub fn render_markdown(&self) -> Result<String, DecisionError> {
        self.validate()?;
        let mut output = format!(
            "# {} optimization dossier\n\n## Comparison contract\n\n- Workload: `{}`\n- Baseline: `{}`\n- Candidate: `{}`\n- Quality contract: {}\n- SLO contract: {}\n\n## Economic outcome\n\n| Metric | Baseline | Candidate | Reduction |\n| --- | ---: | ---: | ---: |\n| Input $/1M tokens | ${:.6} | ${:.6} | {:.2}% |\n| Output $/1M tokens | ${:.6} | ${:.6} | {:.2}% |\n\n## Model-specific decisions\n\n",
            self.model_id,
            self.workload_id,
            self.baseline_name,
            self.candidate_name,
            pass_label(self.quality_contract_passed),
            pass_label(self.slo_contract_passed),
            self.baseline_input_cost_per_million,
            self.candidate_input_cost_per_million,
            self.input_cost_reduction_fraction() * 100.0,
            self.baseline_output_cost_per_million,
            self.candidate_output_cost_per_million,
            self.output_cost_reduction_fraction() * 100.0,
        );
        for decision in &self.decisions {
            output.push_str(&format!(
                "### {}: {}\n\n- Qwen3-8B reason: {}\n- Mechanism: {}\n- Isolated input-cost reduction: {:.2}%\n- Isolated output-cost reduction: {:.2}%\n- Quality delta: {}\n- TTFT delta: {:+.3} ms\n- TPOT delta: {:+.3} ms\n- Energy delta: {:+.3} J/1M tokens\n- Fidelity: `{:?}`\n- Confidence: {:.1}%\n- Evidence: {}\n\n",
                axis_name(decision.axis),
                decision.name,
                decision.qwen3_specific_reason,
                decision.mechanism,
                decision.input_cost_reduction_fraction() * 100.0,
                decision.output_cost_reduction_fraction() * 100.0,
                decision
                    .quality_delta
                    .map(|value| format!("{value:+.6}"))
                    .unwrap_or_else(|| "unmeasured".into()),
                decision.ttft_delta_milliseconds,
                decision.tpot_delta_milliseconds,
                decision.energy_delta_joules_per_million_tokens,
                decision.fidelity,
                decision.confidence * 100.0,
                if decision.evidence_artifacts.is_empty() {
                    "none".into()
                } else {
                    decision.evidence_artifacts.join(", ")
                },
            ));
        }
        output.push_str("## Conclusion\n\n");
        output.push_str(&self.conclusion);
        output.push('\n');
        Ok(output)
    }
}

fn reduction_fraction(baseline: f64, candidate: f64) -> f64 {
    if baseline > 0.0 {
        (baseline - candidate) / baseline
    } else {
        0.0
    }
}

fn pass_label(passed: bool) -> &'static str {
    if passed { "passed" } else { "failed" }
}

fn axis_name(axis: OptimizationAxis) -> &'static str {
    match axis {
        OptimizationAxis::Model => "Model",
        OptimizationAxis::Kernel => "Kernel",
        OptimizationAxis::Serving => "Serving",
        OptimizationAxis::Hardware => "Hardware",
        OptimizationAxis::Mapping => "Mapping",
        OptimizationAxis::Interaction => "Interaction",
    }
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum DecisionError {
    #[error("optimization decision {0} is missing its model-specific explanation")]
    MissingDescription(String),
    #[error("optimization decision {0} has invalid cost data")]
    InvalidCost(String),
    #[error("optimization decision {0} has invalid measured data")]
    InvalidMeasurement(String),
    #[error("optimization dossier is missing a required field")]
    MissingDossierField,
    #[error("optimization dossier has no decisions")]
    EmptyDossier,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn decision() -> OptimizationDecision {
        OptimizationDecision {
            axis: OptimizationAxis::Model,
            name: "Qwen-specific mixed precision".into(),
            qwen3_specific_reason: "Qwen3-8B layers have different outlier sensitivity".into(),
            mechanism: "Store insensitive layers at four bits and preserve sensitive channels"
                .into(),
            baseline_input_cost_per_million: 0.2,
            candidate_input_cost_per_million: 0.15,
            baseline_output_cost_per_million: 0.8,
            candidate_output_cost_per_million: 0.4,
            quality_delta: Some(-0.001),
            ttft_delta_milliseconds: -10.0,
            tpot_delta_milliseconds: -5.0,
            energy_delta_joules_per_million_tokens: -100.0,
            fidelity: OracleFidelity::TensorTile,
            confidence: 0.6,
            evidence_artifacts: vec!["abc123".into()],
        }
    }

    #[test]
    fn dossier_documents_cost_mechanism_and_confidence() {
        let dossier = OptimizationDossier {
            model_id: "Qwen/Qwen3-8B".into(),
            workload_id: "agentic-v1".into(),
            baseline_name: "H100-vLLM".into(),
            candidate_name: "qwen-asic-v0".into(),
            baseline_input_cost_per_million: 0.2,
            candidate_input_cost_per_million: 0.15,
            baseline_output_cost_per_million: 0.8,
            candidate_output_cost_per_million: 0.4,
            quality_contract_passed: true,
            slo_contract_passed: true,
            decisions: vec![decision()],
            conclusion: "The simulated result merits higher-fidelity validation.".into(),
        };

        let markdown = dossier.render_markdown().unwrap();

        assert!(markdown.contains("Input $/1M tokens"));
        assert!(markdown.contains("Qwen3-8B reason"));
        assert!(markdown.contains("50.00%"));
        assert!(markdown.contains("TensorTile"));
        assert!(markdown.contains("abc123"));
    }

    #[test]
    fn undocumented_or_unbounded_decisions_are_rejected() {
        let mut invalid = decision();
        invalid.qwen3_specific_reason.clear();
        invalid.confidence = 1.5;

        assert!(matches!(
            invalid.validate(),
            Err(DecisionError::MissingDescription(_))
        ));
    }
}
