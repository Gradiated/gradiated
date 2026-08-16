use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::experiment::{
    CostChoice, ExperimentError, ExperimentReport, ExperimentRunner, RunOptions,
};
use crate::spec::ExperimentSpec;

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct CapacityPoint {
    pub replicas: u32,
    pub p95_ttft_milliseconds: f64,
    pub p95_tpot_milliseconds: f64,
    pub input_cost_per_million_tokens: f64,
    pub output_cost_per_million_tokens: f64,
    pub input_price_per_million_tokens: f64,
    pub output_price_per_million_tokens: f64,
    pub aggregate_goodput_output_tokens_per_second: f64,
    pub slo_passed: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct CapacityPlan {
    pub workload_arrival_rate_per_second: f64,
    pub maximum_replicas: u32,
    pub required_replicas: Option<u32>,
    pub selected: Option<ExperimentReport>,
    pub evaluated_points: Vec<CapacityPoint>,
}

pub fn plan_capacity(
    spec: &ExperimentSpec,
    options: &RunOptions,
    maximum_replicas: u32,
) -> Result<CapacityPlan, CapacityError> {
    if maximum_replicas == 0 {
        return Err(CapacityError::ZeroMaximumReplicas);
    }
    let mut reports = BTreeMap::new();
    let mut failing = 0_u32;
    let mut candidate = 1_u32;
    let passing = loop {
        let report = evaluate(spec, options, candidate)?;
        let passed = meets_slos(spec, &report);
        reports.insert(candidate, report);
        if passed {
            break Some(candidate);
        }
        failing = candidate;
        if candidate == maximum_replicas {
            break None;
        }
        candidate = candidate.saturating_mul(2).min(maximum_replicas);
    };
    let required_replicas = if let Some(mut upper) = passing {
        let mut lower = failing.saturating_add(1);
        while lower < upper {
            let middle = lower + (upper - lower) / 2;
            let report = evaluate(spec, options, middle)?;
            let passed = meets_slos(spec, &report);
            reports.insert(middle, report);
            if passed {
                upper = middle;
            } else {
                lower = middle + 1;
            }
        }
        Some(upper)
    } else {
        None
    };
    if let Some(replicas) = required_replicas {
        if let std::collections::btree_map::Entry::Vacant(entry) = reports.entry(replicas) {
            entry.insert(evaluate(spec, options, replicas)?);
        }
    }
    let selected = required_replicas.and_then(|replicas| reports.get(&replicas).cloned());
    let evaluated_points = reports
        .values()
        .map(|report| CapacityPoint::from_report(spec, report))
        .collect();
    Ok(CapacityPlan {
        workload_arrival_rate_per_second: spec.workload.arrival_rate_per_second,
        maximum_replicas,
        required_replicas,
        selected,
        evaluated_points,
    })
}

fn evaluate(
    spec: &ExperimentSpec,
    options: &RunOptions,
    replicas: u32,
) -> Result<ExperimentReport, CapacityError> {
    let mut candidate = spec.clone();
    candidate.mapping.data_parallelism = replicas;
    let mut run_options = options.clone();
    if let CostChoice::CustomSilicon(mut server) = run_options.cost {
        server.accelerators_per_server = replicas;
        run_options.cost = CostChoice::CustomSilicon(server);
    }
    Ok(ExperimentRunner.run(&candidate, &run_options)?)
}

fn meets_slos(spec: &ExperimentSpec, report: &ExperimentReport) -> bool {
    report.simulation.p95_ttft_milliseconds <= spec.serving.ttft_slo_milliseconds
        && report.simulation.p95_tpot_milliseconds <= spec.serving.tpot_slo_milliseconds
}

impl CapacityPoint {
    fn from_report(spec: &ExperimentSpec, report: &ExperimentReport) -> Self {
        Self {
            replicas: report.data_parallel_replicas,
            p95_ttft_milliseconds: report.simulation.p95_ttft_milliseconds,
            p95_tpot_milliseconds: report.simulation.p95_tpot_milliseconds,
            input_cost_per_million_tokens: report.costs.input.cost_per_million_tokens,
            output_cost_per_million_tokens: report.costs.output.cost_per_million_tokens,
            input_price_per_million_tokens: report.costs.input.minimum_price_per_million_tokens,
            output_price_per_million_tokens: report.costs.output.minimum_price_per_million_tokens,
            aggregate_goodput_output_tokens_per_second: report
                .aggregate_goodput_output_tokens_per_second,
            slo_passed: meets_slos(spec, report),
        }
    }
}

#[derive(Debug, Error)]
pub enum CapacityError {
    #[error("maximum replicas must be greater than zero")]
    ZeroMaximumReplicas,
    #[error("accelerator count overflow")]
    AcceleratorCountOverflow,
    #[error("capacity candidate failed: {0}")]
    Experiment(#[from] ExperimentError),
}

#[cfg(test)]
mod tests {
    use super::*;

    fn qwen() -> ExperimentSpec {
        let mut spec: ExperimentSpec =
            serde_json::from_str(include_str!("../../../configs/qwen3-8b-agentic-h100.json"))
                .unwrap();
        spec.workload.request_count = 32;
        spec
    }

    #[test]
    fn finds_the_smallest_replica_count_that_meets_both_slos() {
        let plan = plan_capacity(&qwen(), &RunOptions::default(), 64).unwrap();
        let required = plan.required_replicas.unwrap();
        let selected = plan.selected.as_ref().unwrap();

        assert!(required > 1);
        assert!(selected.simulation.p95_ttft_milliseconds <= qwen().serving.ttft_slo_milliseconds);
        assert!(selected.simulation.p95_tpot_milliseconds <= qwen().serving.tpot_slo_milliseconds);
        assert!(plan.evaluated_points.iter().any(|point| !point.slo_passed));
        assert!(plan.evaluated_points.iter().any(|point| point.slo_passed));
    }

    #[test]
    fn returns_no_selection_when_the_fleet_limit_is_insufficient() {
        let plan = plan_capacity(&qwen(), &RunOptions::default(), 1).unwrap();

        assert_eq!(plan.required_replicas, None);
        assert_eq!(plan.selected, None);
        assert_eq!(plan.evaluated_points.len(), 1);
    }
}
