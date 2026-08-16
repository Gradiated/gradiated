use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::spec::ExperimentSpec;

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct HardwareGroupSpec {
    pub name: String,
    pub physical_device_count: u32,
    pub tensor_parallelism: u32,
    pub pipeline_parallelism: u32,
    pub scale_up_bandwidth_bytes_per_second: f64,
    pub scale_up_latency_nanoseconds: f64,
    pub scale_up_energy_picojoules_per_byte: f64,
    pub accelerator_group_hourly_cost_usd: f64,
    pub host_hourly_cost_usd: f64,
    pub cost_basis: String,
    pub evidence_artifacts: Vec<String>,
}

impl HardwareGroupSpec {
    pub fn apply(&self, baseline: &ExperimentSpec) -> Result<ExperimentSpec, HardwareGroupError> {
        self.validate()?;
        let mapped = self
            .tensor_parallelism
            .checked_mul(self.pipeline_parallelism)
            .ok_or(HardwareGroupError::Overflow)?;
        if mapped != self.physical_device_count {
            return Err(HardwareGroupError::MappingDeviceMismatch {
                mapped,
                physical: self.physical_device_count,
            });
        }
        let mut candidate = baseline.clone();
        let aggregate = candidate
            .hardware
            .aggregate
            .as_mut()
            .ok_or(HardwareGroupError::AggregateHardwareRequired)?;
        aggregate.memory_capacity_bytes = aggregate
            .memory_capacity_bytes
            .checked_mul(u64::from(self.physical_device_count))
            .ok_or(HardwareGroupError::Overflow)?;
        let devices = f64::from(self.physical_device_count);
        aggregate.memory_bandwidth_bytes_per_second =
            checked_scale(aggregate.memory_bandwidth_bytes_per_second, devices)?;
        aggregate.compute_operations_per_second =
            checked_scale(aggregate.compute_operations_per_second, devices)?;
        aggregate.idle_power_watts = checked_scale(aggregate.idle_power_watts, devices)?;
        aggregate.peak_power_watts = checked_scale(aggregate.peak_power_watts, devices)?;
        aggregate.scale_up_bandwidth_bytes_per_second = self.scale_up_bandwidth_bytes_per_second;
        aggregate.scale_up_latency_nanoseconds = self.scale_up_latency_nanoseconds;
        aggregate.scale_up_energy_picojoules_per_byte = self.scale_up_energy_picojoules_per_byte;
        candidate.experiment_name = format!("{}--{}", baseline.experiment_name, self.name);
        candidate.hardware.name = self.name.clone();
        candidate.hardware.physical_device_count = self.physical_device_count;
        candidate.hardware.accelerator_hourly_cost_usd = self.accelerator_group_hourly_cost_usd;
        candidate.hardware.host_hourly_cost_usd = self.host_hourly_cost_usd;
        candidate.mapping.tensor_parallelism = self.tensor_parallelism;
        candidate.mapping.pipeline_parallelism = self.pipeline_parallelism;
        candidate.mapping.data_parallelism = 1;
        candidate
            .validate()
            .map_err(HardwareGroupError::InvalidCandidate)?;
        Ok(candidate)
    }

    fn validate(&self) -> Result<(), HardwareGroupError> {
        if self.name.trim().is_empty() || self.cost_basis.trim().is_empty() {
            return Err(HardwareGroupError::MissingDescription);
        }
        if self.physical_device_count == 0
            || self.tensor_parallelism == 0
            || self.pipeline_parallelism == 0
        {
            return Err(HardwareGroupError::ZeroDeviceCount);
        }
        for value in [
            self.scale_up_bandwidth_bytes_per_second,
            self.scale_up_latency_nanoseconds,
            self.scale_up_energy_picojoules_per_byte,
            self.accelerator_group_hourly_cost_usd,
            self.host_hourly_cost_usd,
        ] {
            if !value.is_finite() || value < 0.0 {
                return Err(HardwareGroupError::InvalidValue);
            }
        }
        if self.physical_device_count > 1 && self.scale_up_bandwidth_bytes_per_second == 0.0 {
            return Err(HardwareGroupError::MissingScaleUpBandwidth);
        }
        Ok(())
    }
}

fn checked_scale(value: f64, factor: f64) -> Result<f64, HardwareGroupError> {
    let scaled = value * factor;
    if scaled.is_finite() && scaled > 0.0 {
        Ok(scaled)
    } else {
        Err(HardwareGroupError::Overflow)
    }
}

#[derive(Debug, Error)]
pub enum HardwareGroupError {
    #[error("hardware group is missing its name or cost basis")]
    MissingDescription,
    #[error("hardware group device and mapping counts must be nonzero")]
    ZeroDeviceCount,
    #[error("hardware group contains an invalid numeric value")]
    InvalidValue,
    #[error("multi-device groups require scale-up bandwidth")]
    MissingScaleUpBandwidth,
    #[error("mapping uses {mapped} devices but the group declares {physical}")]
    MappingDeviceMismatch { mapped: u32, physical: u32 },
    #[error("hardware group scaling requires aggregate hardware")]
    AggregateHardwareRequired,
    #[error("hardware group arithmetic overflow")]
    Overflow,
    #[error("scaled experiment is invalid: {0}")]
    InvalidCandidate(crate::spec::ValidationErrors),
}

#[cfg(test)]
mod tests {
    use super::*;

    fn baseline() -> ExperimentSpec {
        serde_json::from_str(include_str!("../../../configs/qwen3-8b-agentic-h100.json")).unwrap()
    }

    fn group() -> HardwareGroupSpec {
        HardwareGroupSpec {
            name: "4xh100".into(),
            physical_device_count: 4,
            tensor_parallelism: 4,
            pipeline_parallelism: 1,
            scale_up_bandwidth_bytes_per_second: 3.6e12,
            scale_up_latency_nanoseconds: 1_000.0,
            scale_up_energy_picojoules_per_byte: 2.0,
            accelerator_group_hourly_cost_usd: 28.0,
            host_hourly_cost_usd: 0.5,
            cost_basis: "public rental sensitivity".into(),
            evidence_artifacts: vec!["source".into()],
        }
    }

    #[test]
    fn aggregate_group_scales_resources_cost_and_mapping_together() {
        let baseline = baseline();

        let candidate = group().apply(&baseline).unwrap();

        assert_eq!(candidate.hardware.physical_device_count, 4);
        assert_eq!(candidate.mapping.tensor_parallelism, 4);
        assert_eq!(
            candidate
                .hardware
                .aggregate
                .as_ref()
                .unwrap()
                .memory_capacity_bytes,
            baseline
                .hardware
                .aggregate
                .as_ref()
                .unwrap()
                .memory_capacity_bytes
                * 4
        );
        assert_eq!(candidate.hardware.accelerator_hourly_cost_usd, 28.0);
    }

    #[test]
    fn mismatched_mapping_and_missing_link_are_rejected() {
        let baseline = baseline();
        let mut mismatched = group();
        mismatched.tensor_parallelism = 2;
        assert!(matches!(
            mismatched.apply(&baseline),
            Err(HardwareGroupError::MappingDeviceMismatch { .. })
        ));
        let mut missing_link = group();
        missing_link.scale_up_bandwidth_bytes_per_second = 0.0;
        assert!(matches!(
            missing_link.apply(&baseline),
            Err(HardwareGroupError::MissingScaleUpBandwidth)
        ));
    }
}
