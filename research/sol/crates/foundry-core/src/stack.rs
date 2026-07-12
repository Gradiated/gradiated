use crate::kernel::KernelOperation;
use crate::model::ModelProgram;
use crate::performance::{
    ActionKind, Bottleneck, OracleFidelity, PerformanceAction, PerformanceError, PerformanceOracle,
    PhaseResult, PhaseWork,
};
use crate::spec::{FusionPolicy, HardwareSpec, KernelSpec, ModelSpec};

#[derive(Clone, Debug)]
pub struct StackOracle<O> {
    inner: O,
    kernel: KernelSpec,
}

impl<O> StackOracle<O> {
    pub fn new(inner: O, kernel: &KernelSpec) -> Self {
        Self {
            inner,
            kernel: kernel.clone(),
        }
    }
}

impl<O: PerformanceOracle> PerformanceOracle for StackOracle<O> {
    fn estimate(
        &self,
        model: &ModelSpec,
        hardware: &HardwareSpec,
        work: &PhaseWork,
    ) -> Result<PhaseResult, PerformanceError> {
        let mut result = self.inner.estimate(model, hardware, work)?;
        let program = ModelProgram::new(model).map_err(|_| PerformanceError::InvalidHardware {
            field: "model program",
        })?;
        let invocations = program
            .lower(work)
            .map_err(|_| PerformanceError::InvalidHardware {
                field: "model lowering",
            })?;
        let tile_utilization = tile_utilization(
            &invocations,
            self.kernel.tile_rows,
            self.kernel.tile_columns,
        )?;
        let original_latency = result.latency_seconds;
        result.tile_utilization = tile_utilization;
        result.executed_flops = result.flops / tile_utilization;
        result.compute_seconds /= tile_utilization;

        let activation_bytes = invocations.iter().try_fold(0_u64, |total, invocation| {
            total
                .checked_add(invocation.activation_read_bytes)
                .and_then(|value| value.checked_add(invocation.activation_write_bytes))
                .ok_or(PerformanceError::Overflow {
                    field: "activation traffic",
                })
        })?;
        let materialized_activation_bytes = if result.fidelity == OracleFidelity::Roofline {
            activation_bytes
                .checked_mul(materialization_percent(self.kernel.fusion))
                .and_then(|value| value.checked_div(100))
                .ok_or(PerformanceError::Overflow {
                    field: "materialized activation traffic",
                })?
        } else {
            result.activation_bytes
        };
        if result.fidelity == OracleFidelity::Roofline {
            result.activation_bytes = materialized_activation_bytes;
            result.memory_seconds += materialized_activation_bytes as f64
                / result.effective_memory_bandwidth_bytes_per_second;
            if materialized_activation_bytes > 0 {
                result.actions.push(PerformanceAction {
                    kind: ActionKind::HbmRead,
                    operations: 0.0,
                    bytes: materialized_activation_bytes,
                    latency_seconds: materialized_activation_bytes as f64
                        / result.effective_memory_bandwidth_bytes_per_second,
                    energy_joules: 0.0,
                });
            }
        }

        let base_launches = result
            .actions
            .iter()
            .filter(|action| action.kind == ActionKind::KernelLaunch)
            .map(|action| action.operations)
            .sum::<f64>();
        if base_launches > 0.0 {
            let launch_overhead = result.launch_seconds / base_launches;
            let launches = f64::from(model.layer_count)
                * f64::from(kernels_per_layer(self.kernel.fusion))
                + 1.0;
            result.launch_seconds = launches * launch_overhead;
            for action in &mut result.actions {
                if action.kind == ActionKind::KernelLaunch {
                    action.operations = launches;
                    action.latency_seconds = result.launch_seconds;
                }
            }
        }
        for action in &mut result.actions {
            if action.kind == ActionKind::Arithmetic {
                action.operations = result.executed_flops;
                action.latency_seconds = result.compute_seconds;
            }
        }
        let active_seconds = result.compute_seconds.max(result.memory_seconds);
        result.latency_seconds = active_seconds + result.launch_seconds;
        result.bottleneck = bottleneck(&result, active_seconds);
        if original_latency > 0.0 {
            result.energy_joules *= result.latency_seconds / original_latency;
        }
        Ok(result)
    }
}

fn tile_utilization(
    invocations: &[crate::model::KernelInvocation],
    tile_rows: u32,
    tile_columns: u32,
) -> Result<f64, PerformanceError> {
    if tile_rows == 0 || tile_columns == 0 {
        return Err(PerformanceError::InvalidHardware {
            field: "kernel tile",
        });
    }
    let mut useful = 0_u128;
    let mut executed = 0_u128;
    for invocation in invocations {
        if invocation.problem.operation != KernelOperation::Gemm {
            continue;
        }
        useful = useful
            .checked_add(invocation.operations)
            .ok_or(PerformanceError::Overflow {
                field: "useful kernel operations",
            })?;
        let m = round_up(invocation.problem.m, u64::from(tile_rows))?;
        let n = round_up(invocation.problem.n, u64::from(tile_columns))?;
        let k = round_up(invocation.problem.k, u64::from(tile_columns))?;
        let padded = u128::from(2_u8)
            .checked_mul(u128::from(m))
            .and_then(|value| value.checked_mul(u128::from(n)))
            .and_then(|value| value.checked_mul(u128::from(k)))
            .and_then(|value| value.checked_mul(u128::from(invocation.problem.batch)))
            .and_then(|value| value.checked_mul(u128::from(invocation.repetitions)))
            .ok_or(PerformanceError::Overflow {
                field: "padded kernel operations",
            })?;
        executed = executed
            .checked_add(padded.max(invocation.operations))
            .ok_or(PerformanceError::Overflow {
                field: "executed kernel operations",
            })?;
    }
    if useful == 0 || executed == 0 {
        return Ok(1.0);
    }
    let utilization = useful as f64 / executed as f64;
    if utilization.is_finite() && utilization > 0.0 && utilization <= 1.0 {
        Ok(utilization)
    } else {
        Err(PerformanceError::InvalidHardware {
            field: "tile utilization",
        })
    }
}

fn round_up(value: u64, multiple: u64) -> Result<u64, PerformanceError> {
    value
        .checked_add(multiple - 1)
        .and_then(|rounded| rounded.checked_div(multiple))
        .and_then(|tiles| tiles.checked_mul(multiple))
        .ok_or(PerformanceError::Overflow {
            field: "kernel tile rounding",
        })
}

fn kernels_per_layer(fusion: FusionPolicy) -> u32 {
    match fusion {
        FusionPolicy::None => 8,
        FusionPolicy::Attention | FusionPolicy::Mlp => 6,
        FusionPolicy::AttentionAndMlp => 4,
        FusionPolicy::FullLayer => 1,
    }
}

fn materialization_percent(fusion: FusionPolicy) -> u64 {
    match fusion {
        FusionPolicy::None => 100,
        FusionPolicy::Attention => 75,
        FusionPolicy::Mlp => 60,
        FusionPolicy::AttentionAndMlp => 40,
        FusionPolicy::FullLayer => 15,
    }
}

fn bottleneck(result: &PhaseResult, active_seconds: f64) -> Bottleneck {
    if result.launch_seconds >= active_seconds {
        Bottleneck::Launch
    } else if result.compute_seconds >= result.memory_seconds {
        Bottleneck::Compute
    } else if result
        .actions
        .iter()
        .filter(|action| action.kind == ActionKind::InterchipTransfer)
        .any(|action| action.latency_seconds >= result.compute_seconds)
    {
        Bottleneck::InterchipLink
    } else {
        Bottleneck::Hbm
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hardware::HardwareOracle;
    use crate::performance::RooflineOracle;
    use crate::spec::{AttentionKernel, FusionPolicy, KernelBackend};

    fn spec() -> ExperimentSpec {
        serde_json::from_str(include_str!("../../../configs/qwen3-8b-agentic-h100.json")).unwrap()
    }

    use crate::spec::ExperimentSpec;

    #[test]
    fn fusion_reduces_launches_and_materialized_activations() {
        let spec = spec();
        let mut none = spec.kernel.clone();
        none.fusion = FusionPolicy::None;
        let mut full = spec.kernel.clone();
        full.fusion = FusionPolicy::FullLayer;
        let work = PhaseWork::prefill(4, 512, 131_328);
        let none = StackOracle::new(HardwareOracle::Roofline(RooflineOracle::default()), &none)
            .estimate(&spec.model, &spec.hardware, &work)
            .unwrap();
        let full = StackOracle::new(HardwareOracle::Roofline(RooflineOracle::default()), &full)
            .estimate(&spec.model, &spec.hardware, &work)
            .unwrap();

        assert!(full.launch_seconds < none.launch_seconds);
        assert!(full.activation_bytes < none.activation_bytes);
        assert!(full.latency_seconds < none.latency_seconds);
    }

    #[test]
    fn model_aligned_tiles_execute_less_padding() {
        let spec = spec();
        let mut aligned = spec.kernel.clone();
        aligned.tile_rows = 64;
        aligned.tile_columns = 128;
        let mut misaligned = aligned.clone();
        misaligned.tile_columns = 192;
        let work = PhaseWork::decode(64, 64 * 8_192);
        let aligned = StackOracle::new(RooflineOracle::default(), &aligned)
            .estimate(&spec.model, &spec.hardware, &work)
            .unwrap();
        let misaligned = StackOracle::new(RooflineOracle::default(), &misaligned)
            .estimate(&spec.model, &spec.hardware, &work)
            .unwrap();

        assert!(aligned.tile_utilization > misaligned.tile_utilization);
        assert!(aligned.executed_flops < misaligned.executed_flops);
    }

    #[test]
    fn analytical_results_do_not_invent_a_backend_language_speedup() {
        let spec = spec();
        let rust = KernelSpec {
            backend: KernelBackend::Rust,
            attention: AttentionKernel::Paged,
            ..spec.kernel.clone()
        };
        let cuda = KernelSpec {
            backend: KernelBackend::Cuda,
            ..rust.clone()
        };
        let work = PhaseWork::decode(16, 16 * 4_096);
        let rust = StackOracle::new(RooflineOracle::default(), &rust)
            .estimate(&spec.model, &spec.hardware, &work)
            .unwrap();
        let cuda = StackOracle::new(RooflineOracle::default(), &cuda)
            .estimate(&spec.model, &spec.hardware, &work)
            .unwrap();

        assert_eq!(rust, cuda);
    }
}
