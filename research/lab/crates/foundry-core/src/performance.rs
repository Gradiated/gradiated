use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::spec::{HardwareSpec, ModelArchitecture, ModelSpec};

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum InferencePhase {
    Prefill,
    Decode,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct PhaseWork {
    pub phase: InferencePhase,
    pub batch_size: u32,
    pub new_tokens: u64,
    pub attention_token_pairs: u64,
    pub interchip_bytes: u64,
}

impl PhaseWork {
    pub fn prefill(batch_size: u32, new_tokens: u64, attention_token_pairs: u64) -> Self {
        Self {
            phase: InferencePhase::Prefill,
            batch_size,
            new_tokens,
            attention_token_pairs,
            interchip_bytes: 0,
        }
    }

    pub fn decode(batch_size: u32, attention_token_pairs: u64) -> Self {
        Self {
            phase: InferencePhase::Decode,
            batch_size,
            new_tokens: u64::from(batch_size),
            attention_token_pairs,
            interchip_bytes: 0,
        }
    }

    pub fn with_interchip_bytes(mut self, interchip_bytes: u64) -> Self {
        self.interchip_bytes = interchip_bytes;
        self
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum OracleFidelity {
    Roofline,
    TensorTile,
    External,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Bottleneck {
    Compute,
    Sram,
    Hbm,
    OnChipNetwork,
    InterchipLink,
    Launch,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ActionKind {
    Arithmetic,
    SramRead,
    SramWrite,
    HbmRead,
    HbmWrite,
    OnChipTransfer,
    InterchipTransfer,
    KernelLaunch,
    StaticPower,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct PerformanceAction {
    pub kind: ActionKind,
    pub operations: f64,
    pub bytes: u64,
    pub latency_seconds: f64,
    pub energy_joules: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct PhaseResult {
    pub phase: InferencePhase,
    pub fidelity: OracleFidelity,
    pub batch_size: u32,
    pub new_tokens: u64,
    pub flops: f64,
    pub executed_flops: f64,
    pub tile_utilization: f64,
    pub weight_bytes: u64,
    pub activation_bytes: u64,
    pub kv_read_bytes: u64,
    pub kv_write_bytes: u64,
    pub interchip_bytes: u64,
    pub effective_compute_operations_per_second: f64,
    pub effective_memory_bandwidth_bytes_per_second: f64,
    pub compute_seconds: f64,
    pub memory_seconds: f64,
    pub launch_seconds: f64,
    pub latency_seconds: f64,
    pub energy_joules: f64,
    pub bottleneck: Bottleneck,
    pub actions: Vec<PerformanceAction>,
}

impl PhaseResult {
    pub fn total_memory_bytes(&self) -> u64 {
        self.weight_bytes
            .saturating_add(self.activation_bytes)
            .saturating_add(self.kv_read_bytes)
            .saturating_add(self.kv_write_bytes)
    }
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum PerformanceError {
    #[error("model architecture does not have complete performance accounting")]
    UnsupportedModelArchitecture,
    #[error("phase work must contain at least one request and one new token")]
    EmptyWork,
    #[error("{field} must be finite and greater than zero")]
    InvalidHardware { field: &'static str },
    #[error("{field} exceeds the supported numeric range")]
    Overflow { field: &'static str },
    #[error("detailed hardware design is required for this oracle")]
    MissingHardwareDesign,
    #[error("hardware does not define arithmetic for {precision}")]
    UnsupportedArithmetic { precision: String },
    #[error("hardware does not define a usable {resource}")]
    MissingResource { resource: &'static str },
}

pub trait PerformanceOracle {
    fn estimate(
        &self,
        model: &ModelSpec,
        hardware: &HardwareSpec,
        work: &PhaseWork,
    ) -> Result<PhaseResult, PerformanceError>;
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct RooflineOracle {
    pub launch_overhead_seconds: f64,
    pub kernels_per_layer: u32,
}

impl Default for RooflineOracle {
    fn default() -> Self {
        Self {
            launch_overhead_seconds: 4.0e-6,
            kernels_per_layer: 6,
        }
    }
}

impl PerformanceOracle for RooflineOracle {
    fn estimate(
        &self,
        model: &ModelSpec,
        hardware: &HardwareSpec,
        work: &PhaseWork,
    ) -> Result<PhaseResult, PerformanceError> {
        let accounting = account_phase_work(model, work)?;
        let compute_rate = hardware.effective_compute_operations_per_second().ok_or(
            PerformanceError::MissingResource {
                resource: "compute throughput",
            },
        )?;
        let memory_bandwidth = hardware
            .effective_memory_bandwidth_bytes_per_second()
            .ok_or(PerformanceError::MissingResource {
                resource: "memory bandwidth",
            })?;
        validate_positive(compute_rate, "effective compute throughput")?;
        validate_positive(memory_bandwidth, "effective memory bandwidth")?;
        validate_positive(self.launch_overhead_seconds, "launch overhead")?;

        let total_memory_bytes = accounting
            .weight_bytes
            .checked_add(accounting.kv_read_bytes)
            .and_then(|bytes| bytes.checked_add(accounting.kv_write_bytes))
            .ok_or(PerformanceError::Overflow {
                field: "memory traffic",
            })?;

        let compute_seconds = accounting.flops / compute_rate;
        let memory_seconds = total_memory_bytes as f64 / memory_bandwidth;
        let (interchip_seconds, interchip_energy_joules) =
            aggregate_interchip_cost(hardware, work.interchip_bytes)?;
        let launch_count = u64::from(model.layer_count)
            .checked_mul(u64::from(self.kernels_per_layer))
            .and_then(|count| count.checked_add(1))
            .ok_or(PerformanceError::Overflow {
                field: "kernel launches",
            })?;
        let launch_seconds = launch_count as f64 * self.launch_overhead_seconds;
        let active_seconds = compute_seconds.max(memory_seconds).max(interchip_seconds);
        let latency_seconds = active_seconds + launch_seconds;
        let peak_power =
            hardware
                .effective_peak_power_watts()
                .ok_or(PerformanceError::MissingResource {
                    resource: "peak power",
                })?;
        let idle_power =
            hardware
                .effective_idle_power_watts()
                .ok_or(PerformanceError::MissingResource {
                    resource: "idle power",
                })?;
        validate_non_negative(peak_power, "peak power")?;
        validate_non_negative(idle_power, "idle power")?;
        let base_energy_joules = active_seconds * peak_power + launch_seconds * idle_power;
        let energy_joules = base_energy_joules + interchip_energy_joules;
        let bottleneck = if launch_seconds >= active_seconds {
            Bottleneck::Launch
        } else if compute_seconds >= memory_seconds && compute_seconds >= interchip_seconds {
            Bottleneck::Compute
        } else if interchip_seconds >= memory_seconds {
            Bottleneck::InterchipLink
        } else {
            Bottleneck::Hbm
        };
        let weighted_seconds =
            compute_seconds + memory_seconds + interchip_seconds + launch_seconds;
        let action_energy = |seconds: f64| {
            if weighted_seconds > 0.0 {
                base_energy_joules * seconds / weighted_seconds
            } else {
                0.0
            }
        };
        let hbm_read_bytes = accounting
            .weight_bytes
            .checked_add(accounting.kv_read_bytes)
            .ok_or(PerformanceError::Overflow { field: "HBM reads" })?;

        let mut actions = vec![
            PerformanceAction {
                kind: ActionKind::Arithmetic,
                operations: accounting.flops,
                bytes: 0,
                latency_seconds: compute_seconds,
                energy_joules: action_energy(compute_seconds),
            },
            PerformanceAction {
                kind: ActionKind::HbmRead,
                operations: 0.0,
                bytes: hbm_read_bytes,
                latency_seconds: hbm_read_bytes as f64 / memory_bandwidth,
                energy_joules: action_energy(memory_seconds),
            },
            PerformanceAction {
                kind: ActionKind::HbmWrite,
                operations: 0.0,
                bytes: accounting.kv_write_bytes,
                latency_seconds: accounting.kv_write_bytes as f64 / memory_bandwidth,
                energy_joules: 0.0,
            },
            PerformanceAction {
                kind: ActionKind::KernelLaunch,
                operations: launch_count as f64,
                bytes: 0,
                latency_seconds: launch_seconds,
                energy_joules: action_energy(launch_seconds),
            },
        ];
        if work.interchip_bytes > 0 {
            actions.push(PerformanceAction {
                kind: ActionKind::InterchipTransfer,
                operations: 0.0,
                bytes: work.interchip_bytes,
                latency_seconds: interchip_seconds,
                energy_joules: action_energy(interchip_seconds) + interchip_energy_joules,
            });
        }
        Ok(PhaseResult {
            phase: work.phase,
            fidelity: OracleFidelity::Roofline,
            batch_size: work.batch_size,
            new_tokens: work.new_tokens,
            flops: accounting.flops,
            executed_flops: accounting.flops,
            tile_utilization: 1.0,
            weight_bytes: accounting.weight_bytes,
            activation_bytes: 0,
            kv_read_bytes: accounting.kv_read_bytes,
            kv_write_bytes: accounting.kv_write_bytes,
            interchip_bytes: work.interchip_bytes,
            effective_compute_operations_per_second: compute_rate,
            effective_memory_bandwidth_bytes_per_second: memory_bandwidth,
            compute_seconds,
            memory_seconds: memory_seconds.max(interchip_seconds),
            launch_seconds,
            latency_seconds,
            energy_joules,
            bottleneck,
            actions,
        })
    }
}

fn aggregate_interchip_cost(
    hardware: &HardwareSpec,
    bytes: u64,
) -> Result<(f64, f64), PerformanceError> {
    if bytes == 0 {
        return Ok((0.0, 0.0));
    }
    let aggregate = hardware
        .aggregate
        .as_ref()
        .ok_or(PerformanceError::MissingResource {
            resource: "aggregate scale-up interconnect",
        })?;
    validate_positive(
        aggregate.scale_up_bandwidth_bytes_per_second,
        "scale-up interconnect bandwidth",
    )?;
    validate_non_negative(
        aggregate.scale_up_latency_nanoseconds,
        "scale-up interconnect latency",
    )?;
    validate_non_negative(
        aggregate.scale_up_energy_picojoules_per_byte,
        "scale-up interconnect energy",
    )?;
    Ok((
        bytes as f64 / aggregate.scale_up_bandwidth_bytes_per_second
            + aggregate.scale_up_latency_nanoseconds * 1.0e-9,
        bytes as f64 * aggregate.scale_up_energy_picojoules_per_byte * 1.0e-12,
    ))
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct PhaseAccounting {
    pub flops: f64,
    pub weight_bytes: u64,
    pub kv_read_bytes: u64,
    pub kv_write_bytes: u64,
}

pub(crate) fn account_phase_work(
    model: &ModelSpec,
    work: &PhaseWork,
) -> Result<PhaseAccounting, PerformanceError> {
    validate_work(work)?;
    if !matches!(model.architecture, ModelArchitecture::DenseDecoder) {
        return Err(PerformanceError::UnsupportedModelArchitecture);
    }
    let weight_flops = checked_product(
        &[2.0, model.parameter_count as f64, work.new_tokens as f64],
        "weight FLOPs",
    )?;
    let attention_flops = checked_product(
        &[
            4.0,
            model.layer_count as f64,
            model.hidden_size as f64,
            work.attention_token_pairs as f64,
        ],
        "attention FLOPs",
    )?;
    let flops = weight_flops + attention_flops;
    if !flops.is_finite() {
        return Err(PerformanceError::Overflow { field: "FLOPs" });
    }
    let weight_bytes = model.weight_bytes().ok_or(PerformanceError::Overflow {
        field: "model weights",
    })?;
    let kv_bytes_per_token = model
        .kv_bytes_per_token()
        .ok_or(PerformanceError::Overflow {
            field: "KV bytes per token",
        })?;

    Ok(PhaseAccounting {
        flops,
        weight_bytes,
        kv_read_bytes: checked_bytes(kv_bytes_per_token, work.attention_token_pairs, "KV reads")?,
        kv_write_bytes: checked_bytes(kv_bytes_per_token, work.new_tokens, "KV writes")?,
    })
}

fn validate_work(work: &PhaseWork) -> Result<(), PerformanceError> {
    if work.batch_size == 0 || work.new_tokens == 0 {
        return Err(PerformanceError::EmptyWork);
    }
    Ok(())
}

fn validate_positive(value: f64, field: &'static str) -> Result<(), PerformanceError> {
    if !value.is_finite() || value <= 0.0 {
        return Err(PerformanceError::InvalidHardware { field });
    }
    Ok(())
}

fn validate_non_negative(value: f64, field: &'static str) -> Result<(), PerformanceError> {
    if !value.is_finite() || value < 0.0 {
        return Err(PerformanceError::InvalidHardware { field });
    }
    Ok(())
}

fn checked_product(values: &[f64], field: &'static str) -> Result<f64, PerformanceError> {
    let product: f64 = values.iter().product();
    if !product.is_finite() {
        return Err(PerformanceError::Overflow { field });
    }
    Ok(product)
}

fn checked_bytes(left: u64, right: u64, field: &'static str) -> Result<u64, PerformanceError> {
    left.checked_mul(right)
        .ok_or(PerformanceError::Overflow { field })
}

#[cfg(test)]
mod tests {
    use crate::spec::{
        AggregateHardwareSpec, HardwareFidelity, HardwareSpec, ModelArchitecture, ModelSpec,
        Precision, glm_5_2_bf16_reference,
    };

    use super::{
        ActionKind, Bottleneck, PerformanceError, PerformanceOracle, PhaseWork, RooflineOracle,
    };

    fn model() -> ModelSpec {
        ModelSpec {
            model_id: "tiny-decoder".into(),
            model_revision: "test-fixture-v1".into(),
            architecture: ModelArchitecture::DenseDecoder,
            parameter_count: 1_000_000,
            layer_count: 4,
            hidden_size: 256,
            intermediate_size: 1_024,
            attention_head_count: 8,
            kv_head_count: 2,
            head_dimension: 32,
            vocabulary_size: 32_000,
            max_sequence_length: 4_096,
            weight_precision: Precision::Bf16,
            quantized_weight_storage: None,
            kv_precision: Precision::Bf16,
        }
    }

    fn hardware() -> HardwareSpec {
        HardwareSpec {
            name: "test-accelerator".into(),
            fidelity: HardwareFidelity::Analytical,
            physical_device_count: 1,
            aggregate: Some(AggregateHardwareSpec {
                memory_capacity_bytes: 8_000_000_000,
                memory_bandwidth_bytes_per_second: 1.0e12,
                compute_operations_per_second: 1.0e14,
                compute_efficiency: 0.8,
                memory_efficiency: 0.7,
                scale_up_bandwidth_bytes_per_second: 0.0,
                scale_up_latency_nanoseconds: 0.0,
                scale_up_energy_picojoules_per_byte: 0.0,
                idle_power_watts: 50.0,
                peak_power_watts: 400.0,
            }),
            design: None,
            accelerator_hourly_cost_usd: 2.0,
            host_hourly_cost_usd: 0.2,
        }
    }

    #[test]
    fn prefix_reuse_reduces_prefill_work() {
        let oracle = RooflineOracle::default();
        let without_prefix = oracle
            .estimate(&model(), &hardware(), &PhaseWork::prefill(1, 512, 131_328))
            .unwrap();
        let with_prefix = oracle
            .estimate(&model(), &hardware(), &PhaseWork::prefill(1, 256, 98_432))
            .unwrap();

        assert!(with_prefix.flops < without_prefix.flops);
        assert!(with_prefix.kv_write_bytes < without_prefix.kv_write_bytes);
        assert!(with_prefix.latency_seconds < without_prefix.latency_seconds);
    }

    #[test]
    fn batching_amortizes_weight_traffic() {
        let oracle = RooflineOracle::default();
        let one = oracle
            .estimate(&model(), &hardware(), &PhaseWork::prefill(1, 64, 2_080))
            .unwrap();
        let eight = oracle
            .estimate(&model(), &hardware(), &PhaseWork::prefill(8, 512, 16_640))
            .unwrap();

        assert_eq!(one.weight_bytes, eight.weight_bytes);
        assert!(
            eight.weight_bytes as f64 / (eight.new_tokens as f64)
                < one.weight_bytes as f64 / (one.new_tokens as f64)
        );
    }

    #[test]
    fn reports_the_roofline_bottleneck_and_launch_overhead() {
        let oracle = RooflineOracle::default();
        let result = oracle
            .estimate(&model(), &hardware(), &PhaseWork::decode(4, 2_048))
            .unwrap();

        assert_eq!(result.bottleneck, Bottleneck::Launch);
        assert!(result.launch_seconds > 0.0);
        assert!(result.latency_seconds >= result.memory_seconds);
        assert!(result.energy_joules > 0.0);
    }

    #[test]
    fn aggregate_scale_up_link_is_timed_and_energy_accounted() {
        let oracle = RooflineOracle::default();
        let mut hardware = hardware();
        hardware.physical_device_count = 2;
        let aggregate = hardware.aggregate.as_mut().unwrap();
        aggregate.scale_up_bandwidth_bytes_per_second = 1.0e8;
        aggregate.scale_up_latency_nanoseconds = 1_000.0;
        aggregate.scale_up_energy_picojoules_per_byte = 2.0;
        let work = PhaseWork::decode(4, 2_048).with_interchip_bytes(1_000_000_000);

        let result = oracle.estimate(&model(), &hardware, &work).unwrap();

        assert_eq!(result.bottleneck, Bottleneck::InterchipLink);
        assert!(
            result
                .actions
                .iter()
                .any(|action| action.kind == ActionKind::InterchipTransfer)
        );
        assert!(result.energy_joules > 0.0);
    }

    #[test]
    fn hybrid_models_require_architecture_specific_performance_accounting() {
        let result = RooflineOracle::default().estimate(
            &glm_5_2_bf16_reference(),
            &hardware(),
            &PhaseWork::decode(1, 1_024),
        );

        assert!(matches!(
            result,
            Err(PerformanceError::UnsupportedModelArchitecture)
        ));
    }
}
