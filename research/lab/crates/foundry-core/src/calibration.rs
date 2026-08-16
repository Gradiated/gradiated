use crate::performance::{InferencePhase, PhaseResult, PhaseWork};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use thiserror::Error;

pub const CALIBRATION_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const CALIBRATION_REPORT_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Copy, Debug, Deserialize, Eq, Hash, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalibrationMetric {
    LatencySeconds,
    EnergyJoules,
    WeightBytes,
    ActivationBytes,
    KvReadBytes,
    KvWriteBytes,
    InterchipBytes,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalibrationEvidenceKind {
    MeasuredHardware,
    Analytical,
    Simulated,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MeasurementProvenance {
    pub evidence_kind: CalibrationEvidenceKind,
    pub source_artifact_id: String,
    pub run_id: String,
    pub hardware_configuration_id: String,
    pub device_id_hash: String,
    pub measurement_tool: String,
    pub software_revision: String,
    pub captured_at_unix_milliseconds: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PredictorProvenance {
    pub predictor_id: String,
    pub predictor_version: String,
    pub configuration_id: String,
    pub generated_at_unix_milliseconds: u64,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PhaseMetricValues {
    pub latency_seconds: f64,
    pub energy_joules: Option<f64>,
    pub weight_bytes: Option<u64>,
    pub activation_bytes: Option<u64>,
    pub kv_read_bytes: Option<u64>,
    pub kv_write_bytes: Option<u64>,
    pub interchip_bytes: Option<u64>,
}

impl PhaseMetricValues {
    pub fn from_phase_result(result: &PhaseResult) -> Self {
        Self {
            latency_seconds: result.latency_seconds,
            energy_joules: Some(result.energy_joules),
            weight_bytes: Some(result.weight_bytes),
            activation_bytes: Some(result.activation_bytes),
            kv_read_bytes: Some(result.kv_read_bytes),
            kv_write_bytes: Some(result.kv_write_bytes),
            interchip_bytes: Some(result.interchip_bytes),
        }
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalibrationSample {
    pub sample_id: String,
    pub phase: InferencePhase,
    pub work: PhaseWork,
    pub measurement_provenance: MeasurementProvenance,
    pub measured: PhaseMetricValues,
    pub predicted: PhaseMetricValues,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MetricAcceptanceThreshold {
    pub metric: CalibrationMetric,
    pub minimum_sample_count: u64,
    pub maximum_p50_absolute_relative_error: f64,
    pub maximum_p95_absolute_relative_error: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalibrationRequest {
    pub schema_version: u32,
    pub calibration_id: String,
    pub model_id: String,
    pub hardware_configuration_id: String,
    pub predictor: PredictorProvenance,
    pub thresholds: Vec<MetricAcceptanceThreshold>,
    pub samples: Vec<CalibrationSample>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RelativeErrorConvention {
    PredictedMinusMeasuredOverMeasured,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SampleMetricError {
    pub sample_id: String,
    pub phase: InferencePhase,
    pub metric: CalibrationMetric,
    pub measured_value: f64,
    pub predicted_value: f64,
    pub signed_relative_error: Option<f64>,
    pub absolute_relative_error: Option<f64>,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RobustQuantiles {
    pub p05: f64,
    pub p50: f64,
    pub p90: f64,
    pub p95: f64,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MetricCalibrationSummary {
    pub metric: CalibrationMetric,
    pub sample_count: u64,
    pub relative_error_count: u64,
    pub undefined_relative_error_count: u64,
    pub signed_relative_error: Option<RobustQuantiles>,
    pub absolute_relative_error: Option<RobustQuantiles>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum AcceptanceFailureReason {
    MissingThreshold,
    MissingMetricSamples,
    InsufficientSamples,
    UndefinedRelativeErrors,
    P50ThresholdExceeded,
    P95ThresholdExceeded,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MetricAcceptanceResult {
    pub metric: CalibrationMetric,
    pub threshold: Option<MetricAcceptanceThreshold>,
    pub summary: Option<MetricCalibrationSummary>,
    pub failures: Vec<AcceptanceFailureReason>,
    pub passed: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalibrationAcceptance {
    pub metric_results: Vec<MetricAcceptanceResult>,
    pub passed: bool,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalibrationStatus {
    Passed,
    Failed,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalibrationReport {
    pub schema_version: u32,
    pub calibration_id: String,
    pub model_id: String,
    pub hardware_configuration_id: String,
    pub predictor: PredictorProvenance,
    pub relative_error_convention: RelativeErrorConvention,
    pub sample_count: u64,
    pub sample_errors: Vec<SampleMetricError>,
    pub metric_summaries: Vec<MetricCalibrationSummary>,
    pub acceptance: CalibrationAcceptance,
    pub status: CalibrationStatus,
}

impl CalibrationReport {
    pub const fn passed(&self) -> bool {
        matches!(self.status, CalibrationStatus::Passed)
    }
}

pub fn calibrate(request: &CalibrationRequest) -> Result<CalibrationReport, CalibrationError> {
    request.validate()?;
    let mut sample_errors = Vec::new();
    for sample in &request.samples {
        for (metric, measured, predicted) in metric_pairs(sample)? {
            let signed_relative_error = relative_error(measured, predicted);
            sample_errors.push(SampleMetricError {
                sample_id: sample.sample_id.clone(),
                phase: sample.phase,
                metric,
                measured_value: measured,
                predicted_value: predicted,
                signed_relative_error,
                absolute_relative_error: signed_relative_error.map(f64::abs),
            });
        }
    }
    let metric_summaries = summarize_errors(&sample_errors)?;
    let acceptance = evaluate_acceptance(&request.thresholds, &metric_summaries);
    let status = if acceptance.passed {
        CalibrationStatus::Passed
    } else {
        CalibrationStatus::Failed
    };
    Ok(CalibrationReport {
        schema_version: CALIBRATION_REPORT_SCHEMA_VERSION,
        calibration_id: request.calibration_id.clone(),
        model_id: request.model_id.clone(),
        hardware_configuration_id: request.hardware_configuration_id.clone(),
        predictor: request.predictor.clone(),
        relative_error_convention: RelativeErrorConvention::PredictedMinusMeasuredOverMeasured,
        sample_count: usize_to_u64(request.samples.len())?,
        sample_errors,
        metric_summaries,
        acceptance,
        status,
    })
}

impl CalibrationRequest {
    pub fn validate(&self) -> Result<(), CalibrationError> {
        if self.schema_version != CALIBRATION_REQUEST_SCHEMA_VERSION {
            return Err(CalibrationError::UnsupportedSchemaVersion {
                expected: CALIBRATION_REQUEST_SCHEMA_VERSION,
                actual: self.schema_version,
            });
        }
        for (field, value) in [
            ("calibration_id", self.calibration_id.as_str()),
            ("model_id", self.model_id.as_str()),
            (
                "hardware_configuration_id",
                self.hardware_configuration_id.as_str(),
            ),
            (
                "predictor.predictor_id",
                self.predictor.predictor_id.as_str(),
            ),
            (
                "predictor.predictor_version",
                self.predictor.predictor_version.as_str(),
            ),
            (
                "predictor.configuration_id",
                self.predictor.configuration_id.as_str(),
            ),
        ] {
            validate_required(field, value)?;
        }
        if self.predictor.generated_at_unix_milliseconds == 0 {
            return Err(CalibrationError::InvalidField(
                "predictor.generated_at_unix_milliseconds",
            ));
        }
        if self.thresholds.is_empty() {
            return Err(CalibrationError::InvalidField("thresholds"));
        }
        let mut threshold_metrics = BTreeSet::new();
        for threshold in &self.thresholds {
            if !threshold_metrics.insert(threshold.metric) {
                return Err(CalibrationError::DuplicateThreshold(threshold.metric));
            }
            threshold.validate()?;
        }
        if self.samples.is_empty() {
            return Err(CalibrationError::InvalidField("samples"));
        }
        let mut sample_ids = BTreeSet::new();
        for sample in &self.samples {
            if !sample_ids.insert(sample.sample_id.as_str()) {
                return Err(CalibrationError::DuplicateSample(sample.sample_id.clone()));
            }
            sample.validate(&self.hardware_configuration_id)?;
        }
        Ok(())
    }
}

impl MetricAcceptanceThreshold {
    fn validate(&self) -> Result<(), CalibrationError> {
        if self.minimum_sample_count == 0 {
            return Err(CalibrationError::InvalidThreshold(self.metric));
        }
        if !self.maximum_p50_absolute_relative_error.is_finite()
            || self.maximum_p50_absolute_relative_error < 0.0
            || !self.maximum_p95_absolute_relative_error.is_finite()
            || self.maximum_p95_absolute_relative_error < 0.0
            || self.maximum_p50_absolute_relative_error > self.maximum_p95_absolute_relative_error
        {
            return Err(CalibrationError::InvalidThreshold(self.metric));
        }
        Ok(())
    }
}

impl CalibrationSample {
    fn validate(&self, hardware_configuration_id: &str) -> Result<(), CalibrationError> {
        validate_required("samples.sample_id", &self.sample_id)?;
        if self.phase != self.work.phase {
            return Err(CalibrationError::PhaseMismatch {
                sample_id: self.sample_id.clone(),
            });
        }
        if self.work.batch_size == 0 || self.work.new_tokens == 0 {
            return Err(CalibrationError::InvalidSampleMetric {
                sample_id: self.sample_id.clone(),
                metric: CalibrationMetric::LatencySeconds,
            });
        }
        self.measurement_provenance
            .validate(&self.sample_id, hardware_configuration_id)?;
        validate_positive_metric(
            &self.sample_id,
            CalibrationMetric::LatencySeconds,
            self.measured.latency_seconds,
        )?;
        validate_positive_metric(
            &self.sample_id,
            CalibrationMetric::LatencySeconds,
            self.predicted.latency_seconds,
        )?;
        if let Some(measured) = self.measured.energy_joules {
            validate_non_negative_metric(
                &self.sample_id,
                CalibrationMetric::EnergyJoules,
                measured,
            )?;
            let predicted = self.predicted.energy_joules.ok_or_else(|| {
                CalibrationError::MissingPredictedMetric {
                    sample_id: self.sample_id.clone(),
                    metric: CalibrationMetric::EnergyJoules,
                }
            })?;
            validate_non_negative_metric(
                &self.sample_id,
                CalibrationMetric::EnergyJoules,
                predicted,
            )?;
        }
        validate_byte_prediction(self, CalibrationMetric::WeightBytes)?;
        validate_byte_prediction(self, CalibrationMetric::ActivationBytes)?;
        validate_byte_prediction(self, CalibrationMetric::KvReadBytes)?;
        validate_byte_prediction(self, CalibrationMetric::KvWriteBytes)?;
        validate_byte_prediction(self, CalibrationMetric::InterchipBytes)
    }
}

impl MeasurementProvenance {
    fn validate(
        &self,
        sample_id: &str,
        expected_hardware_configuration_id: &str,
    ) -> Result<(), CalibrationError> {
        if self.evidence_kind != CalibrationEvidenceKind::MeasuredHardware {
            return Err(CalibrationError::ReferenceIsNotMeasured {
                sample_id: sample_id.into(),
                evidence_kind: self.evidence_kind,
            });
        }
        for (field, value) in [
            ("source_artifact_id", self.source_artifact_id.as_str()),
            ("run_id", self.run_id.as_str()),
            (
                "hardware_configuration_id",
                self.hardware_configuration_id.as_str(),
            ),
            ("device_id_hash", self.device_id_hash.as_str()),
            ("measurement_tool", self.measurement_tool.as_str()),
            ("software_revision", self.software_revision.as_str()),
        ] {
            validate_required(field, value)?;
        }
        if self.hardware_configuration_id != expected_hardware_configuration_id {
            return Err(CalibrationError::HardwareConfigurationMismatch {
                sample_id: sample_id.into(),
            });
        }
        if self.captured_at_unix_milliseconds == 0 {
            return Err(CalibrationError::InvalidField(
                "captured_at_unix_milliseconds",
            ));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum CalibrationError {
    #[error("unsupported calibration request schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid calibration field {0}")]
    InvalidField(&'static str),
    #[error("duplicate calibration sample {0}")]
    DuplicateSample(String),
    #[error("duplicate acceptance threshold for {0:?}")]
    DuplicateThreshold(CalibrationMetric),
    #[error("invalid acceptance threshold for {0:?}")]
    InvalidThreshold(CalibrationMetric),
    #[error("sample {sample_id} uses {evidence_kind:?} rather than measured hardware evidence")]
    ReferenceIsNotMeasured {
        sample_id: String,
        evidence_kind: CalibrationEvidenceKind,
    },
    #[error("sample {sample_id} belongs to a different hardware configuration")]
    HardwareConfigurationMismatch { sample_id: String },
    #[error("sample {sample_id} phase differs from its phase work")]
    PhaseMismatch { sample_id: String },
    #[error("sample {sample_id} has invalid {metric:?}")]
    InvalidSampleMetric {
        sample_id: String,
        metric: CalibrationMetric,
    },
    #[error("sample {sample_id} lacks predicted {metric:?}")]
    MissingPredictedMetric {
        sample_id: String,
        metric: CalibrationMetric,
    },
    #[error("calibration sample count exceeds the supported numeric range")]
    CountOverflow,
}

fn metric_pairs(
    sample: &CalibrationSample,
) -> Result<Vec<(CalibrationMetric, f64, f64)>, CalibrationError> {
    let mut pairs = vec![(
        CalibrationMetric::LatencySeconds,
        sample.measured.latency_seconds,
        sample.predicted.latency_seconds,
    )];
    push_optional_f64(
        &mut pairs,
        sample,
        CalibrationMetric::EnergyJoules,
        sample.measured.energy_joules,
        sample.predicted.energy_joules,
    )?;
    push_optional_u64(
        &mut pairs,
        sample,
        CalibrationMetric::WeightBytes,
        sample.measured.weight_bytes,
        sample.predicted.weight_bytes,
    )?;
    push_optional_u64(
        &mut pairs,
        sample,
        CalibrationMetric::ActivationBytes,
        sample.measured.activation_bytes,
        sample.predicted.activation_bytes,
    )?;
    push_optional_u64(
        &mut pairs,
        sample,
        CalibrationMetric::KvReadBytes,
        sample.measured.kv_read_bytes,
        sample.predicted.kv_read_bytes,
    )?;
    push_optional_u64(
        &mut pairs,
        sample,
        CalibrationMetric::KvWriteBytes,
        sample.measured.kv_write_bytes,
        sample.predicted.kv_write_bytes,
    )?;
    push_optional_u64(
        &mut pairs,
        sample,
        CalibrationMetric::InterchipBytes,
        sample.measured.interchip_bytes,
        sample.predicted.interchip_bytes,
    )?;
    Ok(pairs)
}

fn push_optional_f64(
    pairs: &mut Vec<(CalibrationMetric, f64, f64)>,
    sample: &CalibrationSample,
    metric: CalibrationMetric,
    measured: Option<f64>,
    predicted: Option<f64>,
) -> Result<(), CalibrationError> {
    if let Some(measured) = measured {
        let predicted = predicted.ok_or_else(|| CalibrationError::MissingPredictedMetric {
            sample_id: sample.sample_id.clone(),
            metric,
        })?;
        pairs.push((metric, measured, predicted));
    }
    Ok(())
}

fn push_optional_u64(
    pairs: &mut Vec<(CalibrationMetric, f64, f64)>,
    sample: &CalibrationSample,
    metric: CalibrationMetric,
    measured: Option<u64>,
    predicted: Option<u64>,
) -> Result<(), CalibrationError> {
    if let Some(measured) = measured {
        let predicted = predicted.ok_or_else(|| CalibrationError::MissingPredictedMetric {
            sample_id: sample.sample_id.clone(),
            metric,
        })?;
        pairs.push((metric, measured as f64, predicted as f64));
    }
    Ok(())
}

fn validate_byte_prediction(
    sample: &CalibrationSample,
    metric: CalibrationMetric,
) -> Result<(), CalibrationError> {
    let (measured, predicted) = match metric {
        CalibrationMetric::WeightBytes => {
            (sample.measured.weight_bytes, sample.predicted.weight_bytes)
        }
        CalibrationMetric::ActivationBytes => (
            sample.measured.activation_bytes,
            sample.predicted.activation_bytes,
        ),
        CalibrationMetric::KvReadBytes => (
            sample.measured.kv_read_bytes,
            sample.predicted.kv_read_bytes,
        ),
        CalibrationMetric::KvWriteBytes => (
            sample.measured.kv_write_bytes,
            sample.predicted.kv_write_bytes,
        ),
        CalibrationMetric::InterchipBytes => (
            sample.measured.interchip_bytes,
            sample.predicted.interchip_bytes,
        ),
        CalibrationMetric::LatencySeconds | CalibrationMetric::EnergyJoules => return Ok(()),
    };
    if measured.is_some() && predicted.is_none() {
        return Err(CalibrationError::MissingPredictedMetric {
            sample_id: sample.sample_id.clone(),
            metric,
        });
    }
    Ok(())
}

fn relative_error(measured: f64, predicted: f64) -> Option<f64> {
    if measured == 0.0 {
        if predicted == 0.0 { Some(0.0) } else { None }
    } else {
        Some((predicted - measured) / measured)
    }
}

fn summarize_errors(
    errors: &[SampleMetricError],
) -> Result<Vec<MetricCalibrationSummary>, CalibrationError> {
    let mut grouped = BTreeMap::<CalibrationMetric, Vec<&SampleMetricError>>::new();
    for error in errors {
        grouped.entry(error.metric).or_default().push(error);
    }
    grouped
        .into_iter()
        .map(|(metric, errors)| {
            let signed = errors
                .iter()
                .filter_map(|error| error.signed_relative_error)
                .collect::<Vec<_>>();
            let absolute = errors
                .iter()
                .filter_map(|error| error.absolute_relative_error)
                .collect::<Vec<_>>();
            let sample_count = usize_to_u64(errors.len())?;
            let relative_error_count = usize_to_u64(signed.len())?;
            Ok(MetricCalibrationSummary {
                metric,
                sample_count,
                relative_error_count,
                undefined_relative_error_count: sample_count - relative_error_count,
                signed_relative_error: robust_quantiles(&signed),
                absolute_relative_error: robust_quantiles(&absolute),
            })
        })
        .collect()
}

fn evaluate_acceptance(
    thresholds: &[MetricAcceptanceThreshold],
    summaries: &[MetricCalibrationSummary],
) -> CalibrationAcceptance {
    let threshold_map = thresholds
        .iter()
        .map(|threshold| (threshold.metric, *threshold))
        .collect::<BTreeMap<_, _>>();
    let summary_map = summaries
        .iter()
        .map(|summary| (summary.metric, *summary))
        .collect::<BTreeMap<_, _>>();
    let metrics = threshold_map
        .keys()
        .chain(summary_map.keys())
        .copied()
        .collect::<BTreeSet<_>>();
    let metric_results = metrics
        .into_iter()
        .map(|metric| {
            let threshold = threshold_map.get(&metric).copied();
            let summary = summary_map.get(&metric).copied();
            let mut failures = Vec::new();
            if threshold.is_none() {
                failures.push(AcceptanceFailureReason::MissingThreshold);
            }
            if summary.is_none() {
                failures.push(AcceptanceFailureReason::MissingMetricSamples);
            }
            if let (Some(threshold), Some(summary)) = (threshold, summary) {
                if summary.sample_count < threshold.minimum_sample_count {
                    failures.push(AcceptanceFailureReason::InsufficientSamples);
                }
                if summary.undefined_relative_error_count > 0 {
                    failures.push(AcceptanceFailureReason::UndefinedRelativeErrors);
                }
                if summary.absolute_relative_error.is_some_and(|quantiles| {
                    quantiles.p50 > threshold.maximum_p50_absolute_relative_error
                }) {
                    failures.push(AcceptanceFailureReason::P50ThresholdExceeded);
                }
                if summary.absolute_relative_error.is_some_and(|quantiles| {
                    quantiles.p95 > threshold.maximum_p95_absolute_relative_error
                }) {
                    failures.push(AcceptanceFailureReason::P95ThresholdExceeded);
                }
            }
            MetricAcceptanceResult {
                metric,
                threshold,
                summary,
                passed: failures.is_empty(),
                failures,
            }
        })
        .collect::<Vec<_>>();
    CalibrationAcceptance {
        passed: metric_results.iter().all(|result| result.passed),
        metric_results,
    }
}

fn robust_quantiles(values: &[f64]) -> Option<RobustQuantiles> {
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    Some(RobustQuantiles {
        p05: quantile(&sorted, 0.05)?,
        p50: quantile(&sorted, 0.50)?,
        p90: quantile(&sorted, 0.90)?,
        p95: quantile(&sorted, 0.95)?,
    })
}

fn quantile(sorted: &[f64], quantile: f64) -> Option<f64> {
    let index = ((sorted.len() as f64 * quantile).ceil() as usize)
        .saturating_sub(1)
        .min(sorted.len().saturating_sub(1));
    sorted.get(index).copied()
}

fn validate_required(field: &'static str, value: &str) -> Result<(), CalibrationError> {
    if value.trim().is_empty() {
        Err(CalibrationError::InvalidField(field))
    } else {
        Ok(())
    }
}

fn validate_positive_metric(
    sample_id: &str,
    metric: CalibrationMetric,
    value: f64,
) -> Result<(), CalibrationError> {
    if value.is_finite() && value > 0.0 {
        Ok(())
    } else {
        Err(CalibrationError::InvalidSampleMetric {
            sample_id: sample_id.into(),
            metric,
        })
    }
}

fn validate_non_negative_metric(
    sample_id: &str,
    metric: CalibrationMetric,
    value: f64,
) -> Result<(), CalibrationError> {
    if value.is_finite() && value >= 0.0 {
        Ok(())
    } else {
        Err(CalibrationError::InvalidSampleMetric {
            sample_id: sample_id.into(),
            metric,
        })
    }
}

fn usize_to_u64(value: usize) -> Result<u64, CalibrationError> {
    u64::try_from(value).map_err(|_| CalibrationError::CountOverflow)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn computes_metric_errors_robust_quantiles_and_an_explicit_pass() {
        let report = calibrate(&request()).unwrap();

        assert_eq!(report.status, CalibrationStatus::Passed);
        assert!(report.passed());
        assert_eq!(report.sample_count, 3);
        assert_eq!(report.sample_errors.len(), 9);

        let latency = report
            .metric_summaries
            .iter()
            .find(|summary| summary.metric == CalibrationMetric::LatencySeconds)
            .unwrap();
        let signed = latency.signed_relative_error.unwrap();
        let absolute = latency.absolute_relative_error.unwrap();
        assert!((signed.p05 + 0.1).abs() < 1e-12);
        assert!((signed.p50 - 0.1).abs() < 1e-12);
        assert!((signed.p95 - 0.2).abs() < 1e-12);
        assert!((absolute.p50 - 0.1).abs() < 1e-12);
        assert!((absolute.p95 - 0.2).abs() < 1e-12);
        assert!(
            report
                .metric_summaries
                .iter()
                .any(|summary| summary.metric == CalibrationMetric::EnergyJoules)
        );
        assert!(
            report
                .metric_summaries
                .iter()
                .any(|summary| summary.metric == CalibrationMetric::WeightBytes)
        );
        assert!(
            report
                .acceptance
                .metric_results
                .iter()
                .all(|result| result.passed)
        );
    }

    #[test]
    fn a_threshold_violation_produces_a_versioned_failed_report() {
        let mut request = request();
        request
            .thresholds
            .iter_mut()
            .find(|threshold| threshold.metric == CalibrationMetric::LatencySeconds)
            .unwrap()
            .maximum_p95_absolute_relative_error = 0.15;

        let report = calibrate(&request).unwrap();

        assert_eq!(report.schema_version, CALIBRATION_REPORT_SCHEMA_VERSION);
        assert_eq!(report.status, CalibrationStatus::Failed);
        assert!(!report.passed());
        let latency = report
            .acceptance
            .metric_results
            .iter()
            .find(|result| result.metric == CalibrationMetric::LatencySeconds)
            .unwrap();
        assert!(!latency.passed);
    }

    #[test]
    fn analytical_or_simulated_reference_samples_are_rejected() {
        for evidence_kind in [
            CalibrationEvidenceKind::Analytical,
            CalibrationEvidenceKind::Simulated,
        ] {
            let mut request = request();
            request.samples[0].measurement_provenance.evidence_kind = evidence_kind;

            assert_eq!(
                calibrate(&request),
                Err(CalibrationError::ReferenceIsNotMeasured {
                    sample_id: "sample-1".into(),
                    evidence_kind,
                })
            );
        }
    }

    #[test]
    fn undefined_zero_reference_error_is_visible_and_fails_acceptance() {
        let mut request = request();
        for sample in &mut request.samples {
            sample.measured.activation_bytes = Some(0);
            sample.predicted.activation_bytes = Some(1);
        }
        request.thresholds.push(MetricAcceptanceThreshold {
            metric: CalibrationMetric::ActivationBytes,
            minimum_sample_count: 3,
            maximum_p50_absolute_relative_error: 0.1,
            maximum_p95_absolute_relative_error: 0.2,
        });

        let report = calibrate(&request).unwrap();
        let activation = report
            .metric_summaries
            .iter()
            .find(|summary| summary.metric == CalibrationMetric::ActivationBytes)
            .unwrap();

        assert_eq!(activation.undefined_relative_error_count, 3);
        assert!(activation.absolute_relative_error.is_none());
        assert_eq!(report.status, CalibrationStatus::Failed);
    }

    #[test]
    fn missing_corresponding_prediction_and_phase_mismatch_are_rejected() {
        let mut missing = request();
        missing.samples[0].predicted.energy_joules = None;
        assert_eq!(
            calibrate(&missing),
            Err(CalibrationError::MissingPredictedMetric {
                sample_id: "sample-1".into(),
                metric: CalibrationMetric::EnergyJoules,
            })
        );

        let mut mismatch = request();
        mismatch.samples[0].work.phase = InferencePhase::Decode;
        assert_eq!(
            calibrate(&mismatch),
            Err(CalibrationError::PhaseMismatch {
                sample_id: "sample-1".into(),
            })
        );
    }

    fn request() -> CalibrationRequest {
        CalibrationRequest {
            schema_version: CALIBRATION_REQUEST_SCHEMA_VERSION,
            calibration_id: "qwen-h100-v1".into(),
            model_id: "Qwen/Qwen3-8B".into(),
            hardware_configuration_id: "h100-sxm-testbed".into(),
            predictor: PredictorProvenance {
                predictor_id: "foundry-tensor-tile".into(),
                predictor_version: "0.1.0".into(),
                configuration_id: "predictor-config-1".into(),
                generated_at_unix_milliseconds: 1_750_000_000_000,
            },
            thresholds: vec![
                threshold(CalibrationMetric::LatencySeconds, 0.15, 0.25),
                threshold(CalibrationMetric::EnergyJoules, 0.15, 0.25),
                threshold(CalibrationMetric::WeightBytes, 0.15, 0.25),
            ],
            samples: vec![
                sample("sample-1", 1.0, 1.1),
                sample("sample-2", 1.0, 0.9),
                sample("sample-3", 1.0, 1.2),
            ],
        }
    }

    fn threshold(
        metric: CalibrationMetric,
        maximum_p50_absolute_relative_error: f64,
        maximum_p95_absolute_relative_error: f64,
    ) -> MetricAcceptanceThreshold {
        MetricAcceptanceThreshold {
            metric,
            minimum_sample_count: 3,
            maximum_p50_absolute_relative_error,
            maximum_p95_absolute_relative_error,
        }
    }

    fn sample(sample_id: &str, measured_latency: f64, predicted_latency: f64) -> CalibrationSample {
        CalibrationSample {
            sample_id: sample_id.into(),
            phase: InferencePhase::Prefill,
            work: PhaseWork::prefill(1, 1_024, 524_800),
            measurement_provenance: MeasurementProvenance {
                evidence_kind: CalibrationEvidenceKind::MeasuredHardware,
                source_artifact_id: format!("artifact-{sample_id}"),
                run_id: format!("run-{sample_id}"),
                hardware_configuration_id: "h100-sxm-testbed".into(),
                device_id_hash: "device-hash".into(),
                measurement_tool: "internal-benchmark-harness".into(),
                software_revision: "runtime-revision".into(),
                captured_at_unix_milliseconds: 1_750_000_000_000,
            },
            measured: PhaseMetricValues {
                latency_seconds: measured_latency,
                energy_joules: Some(10.0),
                weight_bytes: Some(1_000),
                activation_bytes: None,
                kv_read_bytes: None,
                kv_write_bytes: None,
                interchip_bytes: None,
            },
            predicted: PhaseMetricValues {
                latency_seconds: predicted_latency,
                energy_joules: Some(11.0),
                weight_bytes: Some(1_100),
                activation_bytes: None,
                kv_read_bytes: None,
                kv_write_bytes: None,
                interchip_bytes: None,
            },
        }
    }
}
