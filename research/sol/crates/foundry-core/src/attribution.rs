use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::study::CoDesignStudyReport;

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct FactorialObservation {
    pub enabled_axes: BTreeSet<String>,
    pub input_cost_per_million_tokens: f64,
    pub output_cost_per_million_tokens: f64,
    pub workload_weighted_cost_per_million_tokens: f64,
}

impl FactorialObservation {
    pub fn from_study(
        enabled_axes: BTreeSet<String>,
        study: &CoDesignStudyReport,
    ) -> Result<Self, AttributionError> {
        let report =
            study
                .capacity
                .selected
                .as_ref()
                .ok_or(AttributionError::InfeasibleObservation(
                    enabled_axes.clone(),
                ))?;
        let (input_fraction, output_fraction) = token_fractions(study);
        Ok(Self {
            enabled_axes,
            input_cost_per_million_tokens: report.costs.input.cost_per_million_tokens,
            output_cost_per_million_tokens: report.costs.output.cost_per_million_tokens,
            workload_weighted_cost_per_million_tokens: input_fraction
                * report.costs.input.cost_per_million_tokens
                + output_fraction * report.costs.output.cost_per_million_tokens,
        })
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct MetricAttribution {
    pub baseline_cost_per_million_tokens: f64,
    pub full_stack_cost_per_million_tokens: f64,
    pub total_savings_per_million_tokens: f64,
    pub shapley_savings_per_million_tokens: f64,
    pub shapley_savings_fraction_of_baseline: f64,
    pub standalone_savings_per_million_tokens: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct AxisAttribution {
    pub axis: String,
    pub input: MetricAttribution,
    pub output: MetricAttribution,
    pub workload_weighted: MetricAttribution,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ShapleyAttributionReport {
    pub axes: Vec<String>,
    pub baseline: FactorialObservation,
    pub full_stack: FactorialObservation,
    pub attributions: Vec<AxisAttribution>,
    pub input_reconciliation_delta: f64,
    pub output_reconciliation_delta: f64,
    pub workload_weighted_reconciliation_delta: f64,
}

pub fn shapley_attribution(
    axes: &[String],
    observations: Vec<FactorialObservation>,
) -> Result<ShapleyAttributionReport, AttributionError> {
    validate_axes(axes)?;
    let axis_set = axes.iter().cloned().collect::<BTreeSet<_>>();
    let expected = 1_usize
        .checked_shl(u32::try_from(axes.len()).map_err(|_| AttributionError::TooManyAxes)?)
        .ok_or(AttributionError::TooManyAxes)?;
    let mut by_axes = BTreeMap::new();
    for observation in observations {
        validate_observation(&observation, &axis_set)?;
        if by_axes
            .insert(observation.enabled_axes.clone(), observation)
            .is_some()
        {
            return Err(AttributionError::DuplicateObservation);
        }
    }
    if by_axes.len() != expected {
        return Err(AttributionError::IncompleteFactorial {
            expected,
            actual: by_axes.len(),
        });
    }
    let baseline = by_axes
        .get(&BTreeSet::new())
        .cloned()
        .ok_or(AttributionError::MissingBaseline)?;
    let full_stack = by_axes
        .get(&axis_set)
        .cloned()
        .ok_or(AttributionError::MissingFullStack)?;
    let mut attributions = Vec::new();
    for axis in axes {
        let input = metric_attribution(axis, axes.len(), &by_axes, |observation| {
            observation.input_cost_per_million_tokens
        })?;
        let output = metric_attribution(axis, axes.len(), &by_axes, |observation| {
            observation.output_cost_per_million_tokens
        })?;
        let workload_weighted = metric_attribution(axis, axes.len(), &by_axes, |observation| {
            observation.workload_weighted_cost_per_million_tokens
        })?;
        attributions.push(AxisAttribution {
            axis: axis.clone(),
            input,
            output,
            workload_weighted,
        });
    }
    Ok(ShapleyAttributionReport {
        axes: axes.to_vec(),
        input_reconciliation_delta: reconciliation(
            &attributions,
            baseline.input_cost_per_million_tokens - full_stack.input_cost_per_million_tokens,
            |axis| axis.input.shapley_savings_per_million_tokens,
        ),
        output_reconciliation_delta: reconciliation(
            &attributions,
            baseline.output_cost_per_million_tokens - full_stack.output_cost_per_million_tokens,
            |axis| axis.output.shapley_savings_per_million_tokens,
        ),
        workload_weighted_reconciliation_delta: reconciliation(
            &attributions,
            baseline.workload_weighted_cost_per_million_tokens
                - full_stack.workload_weighted_cost_per_million_tokens,
            |axis| axis.workload_weighted.shapley_savings_per_million_tokens,
        ),
        baseline,
        full_stack,
        attributions,
    })
}

fn metric_attribution<F>(
    axis: &str,
    axis_count: usize,
    observations: &BTreeMap<BTreeSet<String>, FactorialObservation>,
    metric: F,
) -> Result<MetricAttribution, AttributionError>
where
    F: Fn(&FactorialObservation) -> f64,
{
    let baseline = observations
        .get(&BTreeSet::new())
        .ok_or(AttributionError::MissingBaseline)?;
    let full_axes = observations
        .keys()
        .max_by_key(|axes| axes.len())
        .ok_or(AttributionError::MissingFullStack)?;
    let full = observations
        .get(full_axes)
        .ok_or(AttributionError::MissingFullStack)?;
    let mut shapley = 0.0;
    for (subset, without_axis) in observations {
        if subset.contains(axis) {
            continue;
        }
        let mut with_axis = subset.clone();
        with_axis.insert(axis.to_owned());
        let with_axis =
            observations
                .get(&with_axis)
                .ok_or(AttributionError::IncompleteFactorial {
                    expected: 1_usize << axis_count,
                    actual: observations.len(),
                })?;
        let subset_size = subset.len();
        let weight = factorial(subset_size) * factorial(axis_count - subset_size - 1)
            / factorial(axis_count);
        shapley += weight * (metric(without_axis) - metric(with_axis));
    }
    let singleton = observations
        .iter()
        .find(|(enabled, _)| enabled.len() == 1 && enabled.contains(axis))
        .map(|(_, observation)| observation)
        .ok_or(AttributionError::IncompleteFactorial {
            expected: 1_usize << axis_count,
            actual: observations.len(),
        })?;
    let baseline_cost = metric(baseline);
    let full_cost = metric(full);
    Ok(MetricAttribution {
        baseline_cost_per_million_tokens: baseline_cost,
        full_stack_cost_per_million_tokens: full_cost,
        total_savings_per_million_tokens: baseline_cost - full_cost,
        shapley_savings_per_million_tokens: shapley,
        shapley_savings_fraction_of_baseline: if baseline_cost == 0.0 {
            0.0
        } else {
            shapley / baseline_cost
        },
        standalone_savings_per_million_tokens: baseline_cost - metric(singleton),
    })
}

fn token_fractions(study: &CoDesignStudyReport) -> (f64, f64) {
    let input = study
        .candidate_spec
        .workload
        .request_classes
        .iter()
        .map(|class| class.share * f64::from(class.input_tokens))
        .sum::<f64>();
    let output = study
        .candidate_spec
        .workload
        .request_classes
        .iter()
        .map(|class| class.share * f64::from(class.output_tokens))
        .sum::<f64>();
    (input / (input + output), output / (input + output))
}

fn validate_axes(axes: &[String]) -> Result<(), AttributionError> {
    if axes.is_empty() || axes.len() > 16 || axes.iter().any(|axis| axis.trim().is_empty()) {
        return Err(AttributionError::InvalidAxes);
    }
    if axes.iter().collect::<BTreeSet<_>>().len() != axes.len() {
        return Err(AttributionError::InvalidAxes);
    }
    Ok(())
}

fn validate_observation(
    observation: &FactorialObservation,
    axes: &BTreeSet<String>,
) -> Result<(), AttributionError> {
    if !observation.enabled_axes.is_subset(axes) {
        return Err(AttributionError::UnknownAxis);
    }
    for value in [
        observation.input_cost_per_million_tokens,
        observation.output_cost_per_million_tokens,
        observation.workload_weighted_cost_per_million_tokens,
    ] {
        if !value.is_finite() || value < 0.0 {
            return Err(AttributionError::InvalidCost);
        }
    }
    Ok(())
}

fn factorial(value: usize) -> f64 {
    (1..=value).map(|item| item as f64).product()
}

fn reconciliation<F>(axes: &[AxisAttribution], total: f64, contribution: F) -> f64
where
    F: Fn(&AxisAttribution) -> f64,
{
    axes.iter().map(contribution).sum::<f64>() - total
}

#[derive(Debug, Error)]
pub enum AttributionError {
    #[error("attribution axes must be unique, nonempty, and no more than sixteen")]
    InvalidAxes,
    #[error("factorial attribution contains too many axes")]
    TooManyAxes,
    #[error("observation contains an unknown axis")]
    UnknownAxis,
    #[error("factorial observation has invalid cost")]
    InvalidCost,
    #[error("duplicate factorial observation")]
    DuplicateObservation,
    #[error("incomplete factorial: expected {expected} observations, found {actual}")]
    IncompleteFactorial { expected: usize, actual: usize },
    #[error("factorial baseline is missing")]
    MissingBaseline,
    #[error("full-stack factorial observation is missing")]
    MissingFullStack,
    #[error("study for axes {0:?} has no SLO-feasible result")]
    InfeasibleObservation(BTreeSet<String>),
}

#[cfg(test)]
mod tests {
    use super::*;

    fn observation(axes: &[&str], input: f64, output: f64) -> FactorialObservation {
        FactorialObservation {
            enabled_axes: axes.iter().map(|axis| (*axis).to_owned()).collect(),
            input_cost_per_million_tokens: input,
            output_cost_per_million_tokens: output,
            workload_weighted_cost_per_million_tokens: input * 0.8 + output * 0.2,
        }
    }

    #[test]
    fn shapley_values_allocate_interactions_and_reconcile_to_total_savings() {
        let axes = vec!["model".into(), "kernel".into()];
        let report = shapley_attribution(
            &axes,
            vec![
                observation(&[], 10.0, 20.0),
                observation(&["model"], 8.0, 15.0),
                observation(&["kernel"], 7.0, 18.0),
                observation(&["model", "kernel"], 4.0, 10.0),
            ],
        )
        .unwrap();

        assert_eq!(
            report.attributions[0]
                .input
                .shapley_savings_per_million_tokens,
            2.5
        );
        assert_eq!(
            report.attributions[1]
                .input
                .shapley_savings_per_million_tokens,
            3.5
        );
        assert!(report.input_reconciliation_delta.abs() < 1e-12);
        assert!(report.output_reconciliation_delta.abs() < 1e-12);
    }

    #[test]
    fn incomplete_factorials_are_rejected() {
        let error = shapley_attribution(
            &["model".into(), "kernel".into()],
            vec![observation(&[], 10.0, 20.0)],
        )
        .unwrap_err();

        assert!(matches!(
            error,
            AttributionError::IncompleteFactorial { .. }
        ));
    }
}
