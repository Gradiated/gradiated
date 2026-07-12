use crate::artifact::ArtifactId;
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct QualityRequest {
    pub baseline_model: ArtifactId,
    pub candidate_model: ArtifactId,
    pub suite: String,
    pub seed: u64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct MetricResult {
    pub name: String,
    pub baseline: f64,
    pub candidate: f64,
    pub allowed_regression: f64,
    pub higher_is_better: bool,
}

impl MetricResult {
    pub fn regression(&self) -> f64 {
        if self.higher_is_better {
            self.baseline - self.candidate
        } else {
            self.candidate - self.baseline
        }
    }

    pub fn passes(&self) -> bool {
        self.regression() <= self.allowed_regression
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct QualityReport {
    pub suite: String,
    pub metrics: Vec<MetricResult>,
    pub passed: bool,
}

impl QualityReport {
    pub fn from_metrics(suite: impl Into<String>, metrics: Vec<MetricResult>) -> Self {
        let passed = !metrics.is_empty() && metrics.iter().all(MetricResult::passes);
        Self {
            suite: suite.into(),
            metrics,
            passed,
        }
    }

    pub fn validate(&self) -> Result<(), QualityError> {
        if self.metrics.is_empty() {
            return Err(QualityError::EmptySuite);
        }
        for metric in &self.metrics {
            if metric.name.trim().is_empty() {
                return Err(QualityError::UnnamedMetric);
            }
            if !metric.baseline.is_finite()
                || !metric.candidate.is_finite()
                || !metric.allowed_regression.is_finite()
                || metric.allowed_regression < 0.0
            {
                return Err(QualityError::InvalidMetric(metric.name.clone()));
            }
        }
        if self.passed != self.metrics.iter().all(MetricResult::passes) {
            return Err(QualityError::InconsistentPassState);
        }
        Ok(())
    }
}

pub trait QualityOracle {
    fn evaluate(&self, request: &QualityRequest) -> Result<QualityReport, QualityError>;
}

#[derive(Debug, Error)]
pub enum QualityError {
    #[error("quality suite must contain at least one metric")]
    EmptySuite,
    #[error("quality metric must have a name")]
    UnnamedMetric,
    #[error("quality metric {0} contains an invalid value")]
    InvalidMetric(String),
    #[error("quality report pass state does not match its metrics")]
    InconsistentPassState,
    #[error("quality backend failed: {0}")]
    Backend(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn evaluates_higher_and_lower_is_better_non_inferiority() {
        let report = QualityReport::from_metrics(
            "agentic-v1",
            vec![
                MetricResult {
                    name: "task_success".into(),
                    baseline: 0.80,
                    candidate: 0.795,
                    allowed_regression: 0.01,
                    higher_is_better: true,
                },
                MetricResult {
                    name: "perplexity".into(),
                    baseline: 8.0,
                    candidate: 8.05,
                    allowed_regression: 0.1,
                    higher_is_better: false,
                },
            ],
        );

        assert!(report.passed);
        assert!(report.validate().is_ok());
    }

    #[test]
    fn one_regressed_metric_rejects_the_candidate() {
        let report = QualityReport::from_metrics(
            "agentic-v1",
            vec![MetricResult {
                name: "task_success".into(),
                baseline: 0.80,
                candidate: 0.75,
                allowed_regression: 0.01,
                higher_is_better: true,
            }],
        );

        assert!(!report.passed);
        assert!(report.validate().is_ok());
    }

    #[test]
    fn rejects_forged_pass_state() {
        let report = QualityReport {
            suite: "agentic-v1".into(),
            metrics: vec![MetricResult {
                name: "task_success".into(),
                baseline: 0.80,
                candidate: 0.70,
                allowed_regression: 0.01,
                higher_is_better: true,
            }],
            passed: true,
        };

        assert!(matches!(
            report.validate(),
            Err(QualityError::InconsistentPassState)
        ));
    }
}
