use serde::{Deserialize, Serialize};

use crate::performance::{
    ActionKind, Bottleneck, OracleFidelity, PerformanceAction, PerformanceError, PerformanceOracle,
    PhaseResult, PhaseWork, RooflineOracle, account_phase_work,
};
use crate::spec::{
    HardwareDesignSpec, HardwareSpec, ModelSpec, NetworkTopology, OffChipMemoryTierSpec,
    OnChipMemoryTierSpec,
};

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct TensorTileOracle {
    pub launch_overhead_seconds: f64,
    pub kernels_per_layer: u32,
}

impl Default for TensorTileOracle {
    fn default() -> Self {
        Self {
            launch_overhead_seconds: 2.0e-6,
            kernels_per_layer: 6,
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(tag = "fidelity", content = "config", rename_all = "snake_case")]
pub enum HardwareOracle {
    Roofline(RooflineOracle),
    TensorTile(TensorTileOracle),
}

impl PerformanceOracle for HardwareOracle {
    fn estimate(
        &self,
        model: &ModelSpec,
        hardware: &HardwareSpec,
        work: &PhaseWork,
    ) -> Result<PhaseResult, PerformanceError> {
        match self {
            Self::Roofline(oracle) => oracle.estimate(model, hardware, work),
            Self::TensorTile(oracle) => oracle.estimate(model, hardware, work),
        }
    }
}

impl PerformanceOracle for TensorTileOracle {
    fn estimate(
        &self,
        model: &ModelSpec,
        hardware: &HardwareSpec,
        work: &PhaseWork,
    ) -> Result<PhaseResult, PerformanceError> {
        let accounting = account_phase_work(model, work)?;
        let design = hardware
            .design
            .as_ref()
            .ok_or(PerformanceError::MissingHardwareDesign)?;
        let arithmetic = design
            .compute
            .arithmetic
            .iter()
            .find(|entry| entry.precision == model.weight_precision)
            .ok_or_else(|| PerformanceError::UnsupportedArithmetic {
                precision: format!("{:?}", model.weight_precision),
            })?;
        let compute_rate = compute_rate(design, arithmetic.operations_per_cycle_per_element)?;
        let sram = memory_summary(&design.on_chip_memory, "on-chip memory")?;
        let hbm = off_chip_memory_summary(&design.off_chip_memory)?;
        let launch_count = u64::from(model.layer_count)
            .checked_mul(u64::from(self.kernels_per_layer))
            .and_then(|count| count.checked_add(1))
            .ok_or(PerformanceError::Overflow {
                field: "kernel launches",
            })?;
        let launch_seconds = launch_count as f64 * self.launch_overhead_seconds;
        validate_positive(launch_seconds, "launch overhead")?;

        let layer_kv_bytes = accounting
            .kv_write_bytes
            .checked_div(u64::from(model.layer_count))
            .unwrap_or(accounting.kv_write_bytes)
            .checked_div(work.new_tokens)
            .unwrap_or(0);
        let activation_bytes = bits_to_bytes(
            u64::from(model.hidden_size)
                .checked_mul(u64::from(model.weight_precision.bits()))
                .and_then(|bits| bits.checked_mul(4))
                .ok_or(PerformanceError::Overflow {
                    field: "activation tile",
                })?,
        );
        let tile_bytes_per_token = activation_bytes
            .checked_add(layer_kv_bytes)
            .ok_or(PerformanceError::Overflow {
                field: "tile working set",
            })?
            .max(1);
        let tile_token_capacity = (sram.capacity_bytes / tile_bytes_per_token).max(1);
        let weight_passes = work.new_tokens.div_ceil(tile_token_capacity);
        let weight_bytes = accounting.weight_bytes.checked_mul(weight_passes).ok_or(
            PerformanceError::Overflow {
                field: "tiled weight traffic",
            },
        )?;
        let hbm_read_bytes = weight_bytes.checked_add(accounting.kv_read_bytes).ok_or(
            PerformanceError::Overflow {
                field: "off-chip reads",
            },
        )?;
        let hbm_total_bytes = hbm_read_bytes
            .checked_add(accounting.kv_write_bytes)
            .ok_or(PerformanceError::Overflow {
                field: "off-chip traffic",
            })?;
        let activation_traffic =
            activation_bytes
                .checked_mul(work.new_tokens)
                .ok_or(PerformanceError::Overflow {
                    field: "activation traffic",
                })?;
        let sram_read_bytes =
            hbm_total_bytes
                .checked_add(activation_traffic)
                .ok_or(PerformanceError::Overflow {
                    field: "SRAM reads",
                })?;
        let sram_write_bytes = accounting
            .kv_write_bytes
            .checked_add(activation_traffic)
            .ok_or(PerformanceError::Overflow {
                field: "SRAM writes",
            })?;
        let on_chip_bytes =
            sram_read_bytes
                .checked_add(sram_write_bytes)
                .ok_or(PerformanceError::Overflow {
                    field: "on-chip traffic",
                })?;

        let compute_seconds = accounting.flops / compute_rate;
        let sram_seconds = on_chip_bytes as f64 / sram.bandwidth_bytes_per_second;
        let hbm_transactions = weight_passes
            .checked_mul(u64::from(model.layer_count))
            .and_then(|count| count.checked_add(2))
            .ok_or(PerformanceError::Overflow {
                field: "off-chip transactions",
            })?;
        let hbm_seconds = hbm_total_bytes as f64 / hbm.bandwidth_bytes_per_second
            + hbm_transactions as f64 * hbm.fixed_latency_seconds;
        let hops = topology_hops(&design.network.topology, design.compute.array_count);
        validate_positive(
            design.network.bisection_bandwidth_bytes_per_second,
            "on-chip network bandwidth",
        )?;
        let noc_seconds = on_chip_bytes as f64
            / design.network.bisection_bandwidth_bytes_per_second
            + launch_count as f64 * hops * design.network.hop_latency_nanoseconds * 1.0e-9;
        let (link_seconds, link_energy) = interchip_cost(design, work.interchip_bytes)?;

        let resources = [
            (Bottleneck::Compute, compute_seconds),
            (Bottleneck::Sram, sram_seconds),
            (Bottleneck::Hbm, hbm_seconds),
            (Bottleneck::OnChipNetwork, noc_seconds),
            (Bottleneck::InterchipLink, link_seconds),
        ];
        let (resource_bottleneck, active_seconds) = resources
            .into_iter()
            .max_by(|left, right| left.1.total_cmp(&right.1))
            .ok_or(PerformanceError::InvalidHardware {
                field: "resource latency",
            })?;
        let bottleneck = if launch_seconds >= active_seconds {
            Bottleneck::Launch
        } else {
            resource_bottleneck
        };
        let latency_seconds = active_seconds + launch_seconds;

        let arithmetic_energy =
            accounting.flops * arithmetic.energy_picojoules_per_operation * 1.0e-12;
        let sram_read_energy = sram_read_bytes as f64 * sram.energy_picojoules_per_byte * 1.0e-12;
        let sram_write_energy = sram_write_bytes as f64 * sram.energy_picojoules_per_byte * 1.0e-12;
        let hbm_read_energy = hbm_read_bytes as f64 * hbm.energy_picojoules_per_byte * 1.0e-12;
        let hbm_write_energy =
            accounting.kv_write_bytes as f64 * hbm.energy_picojoules_per_byte * 1.0e-12;
        let noc_energy = on_chip_bytes as f64
            * hops
            * design.network.energy_picojoules_per_byte_per_hop
            * 1.0e-12;
        let static_energy = design.power_thermal.idle_power_watts * latency_seconds;
        let energy_joules = arithmetic_energy
            + sram_read_energy
            + sram_write_energy
            + hbm_read_energy
            + hbm_write_energy
            + noc_energy
            + link_energy
            + static_energy;

        Ok(PhaseResult {
            phase: work.phase,
            fidelity: OracleFidelity::TensorTile,
            batch_size: work.batch_size,
            new_tokens: work.new_tokens,
            flops: accounting.flops,
            executed_flops: accounting.flops,
            tile_utilization: 1.0,
            weight_bytes,
            activation_bytes: activation_traffic.saturating_mul(2),
            kv_read_bytes: accounting.kv_read_bytes,
            kv_write_bytes: accounting.kv_write_bytes,
            interchip_bytes: work.interchip_bytes,
            effective_compute_operations_per_second: compute_rate,
            effective_memory_bandwidth_bytes_per_second: hbm.bandwidth_bytes_per_second,
            compute_seconds,
            memory_seconds: sram_seconds
                .max(hbm_seconds)
                .max(noc_seconds)
                .max(link_seconds),
            launch_seconds,
            latency_seconds,
            energy_joules,
            bottleneck,
            actions: vec![
                action(
                    ActionKind::Arithmetic,
                    accounting.flops,
                    0,
                    compute_seconds,
                    arithmetic_energy,
                ),
                action(
                    ActionKind::SramRead,
                    0.0,
                    sram_read_bytes,
                    sram_read_bytes as f64 / sram.bandwidth_bytes_per_second,
                    sram_read_energy,
                ),
                action(
                    ActionKind::SramWrite,
                    0.0,
                    sram_write_bytes,
                    sram_write_bytes as f64 / sram.bandwidth_bytes_per_second,
                    sram_write_energy,
                ),
                action(
                    ActionKind::HbmRead,
                    0.0,
                    hbm_read_bytes,
                    hbm_read_bytes as f64 / hbm.bandwidth_bytes_per_second,
                    hbm_read_energy,
                ),
                action(
                    ActionKind::HbmWrite,
                    0.0,
                    accounting.kv_write_bytes,
                    accounting.kv_write_bytes as f64 / hbm.bandwidth_bytes_per_second,
                    hbm_write_energy,
                ),
                action(
                    ActionKind::OnChipTransfer,
                    0.0,
                    on_chip_bytes,
                    noc_seconds,
                    noc_energy,
                ),
                action(
                    ActionKind::InterchipTransfer,
                    0.0,
                    work.interchip_bytes,
                    link_seconds,
                    link_energy,
                ),
                action(
                    ActionKind::KernelLaunch,
                    launch_count as f64,
                    0,
                    launch_seconds,
                    0.0,
                ),
                action(
                    ActionKind::StaticPower,
                    0.0,
                    0,
                    latency_seconds,
                    static_energy,
                ),
            ],
        })
    }
}

#[derive(Clone, Copy)]
struct MemorySummary {
    capacity_bytes: u64,
    bandwidth_bytes_per_second: f64,
    energy_picojoules_per_byte: f64,
    fixed_latency_seconds: f64,
}

fn compute_rate(
    design: &HardwareDesignSpec,
    operations_per_cycle_per_element: f64,
) -> Result<f64, PerformanceError> {
    let elements = f64::from(design.compute.array_count)
        * f64::from(design.compute.array.rows)
        * f64::from(design.compute.array.columns);
    let rate = elements * design.compute.frequency_hz * operations_per_cycle_per_element;
    validate_positive(rate, "arithmetic throughput")?;
    Ok(rate)
}

fn memory_summary(
    tiers: &[OnChipMemoryTierSpec],
    resource: &'static str,
) -> Result<MemorySummary, PerformanceError> {
    if tiers.is_empty() {
        return Err(PerformanceError::MissingResource { resource });
    }
    let capacity_bytes = tiers.iter().try_fold(0_u64, |total, tier| {
        total
            .checked_add(tier.capacity_bytes)
            .ok_or(PerformanceError::Overflow { field: resource })
    })?;
    let bandwidth_bytes_per_second = tiers
        .iter()
        .map(|tier| tier.bandwidth_bytes_per_second)
        .sum::<f64>();
    validate_positive(bandwidth_bytes_per_second, resource)?;
    let energy_picojoules_per_byte = tiers
        .iter()
        .map(|tier| tier.energy_picojoules_per_byte * tier.bandwidth_bytes_per_second)
        .sum::<f64>()
        / bandwidth_bytes_per_second;
    validate_non_negative(energy_picojoules_per_byte, resource)?;
    Ok(MemorySummary {
        capacity_bytes,
        bandwidth_bytes_per_second,
        energy_picojoules_per_byte,
        fixed_latency_seconds: 0.0,
    })
}

fn off_chip_memory_summary(
    tiers: &[OffChipMemoryTierSpec],
) -> Result<MemorySummary, PerformanceError> {
    if tiers.is_empty() {
        return Err(PerformanceError::MissingResource {
            resource: "off-chip memory",
        });
    }
    let capacity_bytes = tiers.iter().try_fold(0_u64, |total, tier| {
        total
            .checked_add(tier.capacity_bytes)
            .ok_or(PerformanceError::Overflow {
                field: "off-chip memory",
            })
    })?;
    let bandwidth_bytes_per_second = tiers
        .iter()
        .map(|tier| tier.bandwidth_bytes_per_second)
        .sum::<f64>();
    validate_positive(bandwidth_bytes_per_second, "off-chip memory bandwidth")?;
    let energy_picojoules_per_byte = tiers
        .iter()
        .map(|tier| tier.energy_picojoules_per_byte * tier.bandwidth_bytes_per_second)
        .sum::<f64>()
        / bandwidth_bytes_per_second;
    let fixed_latency_seconds = tiers
        .iter()
        .map(|tier| tier.controller_latency_nanoseconds)
        .fold(0.0_f64, f64::max)
        * 1.0e-9;
    validate_non_negative(energy_picojoules_per_byte, "off-chip memory energy")?;
    Ok(MemorySummary {
        capacity_bytes,
        bandwidth_bytes_per_second,
        energy_picojoules_per_byte,
        fixed_latency_seconds,
    })
}

fn topology_hops(topology: &NetworkTopology, endpoint_count: u32) -> f64 {
    let endpoints = f64::from(endpoint_count.max(1));
    match topology {
        NetworkTopology::Crossbar => 1.0,
        NetworkTopology::Mesh => endpoints.sqrt().ceil(),
        NetworkTopology::Ring => (endpoints / 2.0).ceil(),
        NetworkTopology::Tree => endpoints.log2().ceil().max(1.0),
        NetworkTopology::Custom => 2.0,
    }
}

fn interchip_cost(design: &HardwareDesignSpec, bytes: u64) -> Result<(f64, f64), PerformanceError> {
    if bytes == 0 {
        return Ok((0.0, 0.0));
    }
    let links = &design.interconnect.scale_up;
    if links.is_empty() {
        return Err(PerformanceError::MissingResource {
            resource: "scale-up interconnect",
        });
    }
    let bandwidth = links
        .iter()
        .map(|link| f64::from(link.link_count) * link.bandwidth_bytes_per_second_per_link)
        .sum::<f64>();
    validate_positive(bandwidth, "scale-up interconnect bandwidth")?;
    let latency = links
        .iter()
        .map(|link| link.latency_nanoseconds)
        .fold(0.0_f64, f64::max)
        * 1.0e-9;
    let energy_per_byte = links
        .iter()
        .map(|link| link.energy_picojoules_per_byte)
        .sum::<f64>()
        / links.len() as f64;
    Ok((
        bytes as f64 / bandwidth + latency,
        bytes as f64 * energy_per_byte * 1.0e-12,
    ))
}

fn action(
    kind: ActionKind,
    operations: f64,
    bytes: u64,
    latency_seconds: f64,
    energy_joules: f64,
) -> PerformanceAction {
    PerformanceAction {
        kind,
        operations,
        bytes,
        latency_seconds,
        energy_joules,
    }
}

fn bits_to_bytes(bits: u64) -> u64 {
    bits.div_ceil(8)
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

#[cfg(test)]
mod tests {
    use crate::performance::{ActionKind, PerformanceOracle, PhaseWork};
    use crate::spec::{
        ArithmeticSpec, ComputeArraySpec, ComputeSpec, DieSpec, HardwareDesignSpec,
        HardwareFidelity, HardwareSpec, InterconnectSpec, LinkSpec, ManufacturingSpec,
        ModelArchitecture, ModelSpec, NetworkTopology, OffChipMemoryKind, OffChipMemoryTierSpec,
        OnChipMemoryKind, OnChipMemoryTierSpec, OnDieNetworkSpec, PackageSpec, PowerThermalSpec,
        Precision, ProcessSpec,
    };

    use super::TensorTileOracle;

    fn model(precision: Precision) -> ModelSpec {
        ModelSpec {
            model_id: "tile-test".into(),
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
            weight_precision: precision,
            quantized_weight_storage: (precision.bits() < 8)
                .then(|| crate::spec::QuantizedWeightStorageSpec::grouped_all(128, 4, 16, 16, 0)),
            kv_precision: Precision::Fp16,
        }
    }

    fn hardware() -> HardwareSpec {
        HardwareSpec {
            name: "tile-accelerator".into(),
            fidelity: HardwareFidelity::Architecture,
            physical_device_count: 1,
            aggregate: None,
            design: Some(HardwareDesignSpec {
                process: ProcessSpec {
                    node_nanometers: 4.0,
                    transistor_density_million_per_square_millimeter: 200.0,
                    wafer_diameter_millimeters: 300.0,
                    wafer_cost_usd: 20_000.0,
                },
                die: DieSpec {
                    die_count: 1,
                    area_square_millimeters: 400.0,
                },
                package: PackageSpec {
                    package_type: "2.5D".into(),
                    interposer_area_square_millimeters: 800.0,
                    package_cost_usd: 400.0,
                },
                compute: ComputeSpec {
                    array_count: 16,
                    array: ComputeArraySpec {
                        rows: 64,
                        columns: 64,
                    },
                    frequency_hz: 1.0e9,
                    arithmetic: vec![
                        ArithmeticSpec {
                            precision: Precision::Bf16,
                            operations_per_cycle_per_element: 1.0,
                            energy_picojoules_per_operation: 0.8,
                        },
                        ArithmeticSpec {
                            precision: Precision::Int8,
                            operations_per_cycle_per_element: 4.0,
                            energy_picojoules_per_operation: 0.1,
                        },
                    ],
                },
                on_chip_memory: vec![OnChipMemoryTierSpec {
                    name: "sram".into(),
                    kind: OnChipMemoryKind::Sram,
                    capacity_bytes: 16_384,
                    bandwidth_bytes_per_second: 20.0e12,
                    energy_picojoules_per_byte: 0.5,
                    area_square_millimeters: 50.0,
                }],
                off_chip_memory: vec![OffChipMemoryTierSpec {
                    name: "hbm".into(),
                    kind: OffChipMemoryKind::Hbm,
                    capacity_bytes: 16_000_000_000,
                    bandwidth_bytes_per_second: 200.0e9,
                    energy_picojoules_per_byte: 5.0,
                    area_square_millimeters: 100.0,
                    controller_latency_nanoseconds: 50.0,
                }],
                network: OnDieNetworkSpec {
                    topology: NetworkTopology::Crossbar,
                    bisection_bandwidth_bytes_per_second: 20.0e12,
                    hop_latency_nanoseconds: 2.0,
                    energy_picojoules_per_byte_per_hop: 0.1,
                    area_square_millimeters: 20.0,
                },
                interconnect: InterconnectSpec {
                    scale_up: vec![LinkSpec {
                        name: "die-link".into(),
                        link_count: 4,
                        bandwidth_bytes_per_second_per_link: 100.0e9,
                        latency_nanoseconds: 100.0,
                        energy_picojoules_per_byte: 2.0,
                    }],
                    scale_out: vec![],
                },
                power_thermal: PowerThermalSpec {
                    idle_power_watts: 20.0,
                    thermal_design_power_watts: 300.0,
                    cooling_capacity_watts: 350.0,
                    maximum_junction_temperature_celsius: 95.0,
                },
                manufacturing: ManufacturingSpec {
                    defect_density_per_square_centimeter: 0.1,
                    die_yield: 0.8,
                    package_yield: 0.95,
                    assembly_cost_usd: 100.0,
                    test_cost_usd: 50.0,
                    non_recurring_engineering_cost_usd: 10_000_000.0,
                    amortization_units: 100_000,
                },
            }),
            accelerator_hourly_cost_usd: 0.8,
            host_hourly_cost_usd: 0.2,
        }
    }

    fn action_bytes(result: &crate::performance::PhaseResult, kind: ActionKind) -> u64 {
        result
            .actions
            .iter()
            .find(|action| action.kind == kind)
            .unwrap()
            .bytes
    }

    #[test]
    fn larger_sram_reduces_weight_reload_latency_and_energy() {
        let oracle = TensorTileOracle::default();
        let small = hardware();
        let mut large = small.clone();
        large.design.as_mut().unwrap().on_chip_memory[0].capacity_bytes = 4_000_000;
        let work = PhaseWork::prefill(8, 512, 20_000);

        let small_result = oracle
            .estimate(&model(Precision::Bf16), &small, &work)
            .unwrap();
        let large_result = oracle
            .estimate(&model(Precision::Bf16), &large, &work)
            .unwrap();

        assert!(
            action_bytes(&large_result, ActionKind::HbmRead)
                < action_bytes(&small_result, ActionKind::HbmRead)
        );
        assert!(large_result.latency_seconds < small_result.latency_seconds);
        assert!(large_result.energy_joules < small_result.energy_joules);
    }

    #[test]
    fn higher_hbm_bandwidth_reduces_memory_bound_latency() {
        let oracle = TensorTileOracle::default();
        let slow = hardware();
        let mut fast = slow.clone();
        fast.design.as_mut().unwrap().off_chip_memory[0].bandwidth_bytes_per_second *= 8.0;
        let work = PhaseWork::decode(8, 8_192);

        let slow_result = oracle
            .estimate(&model(Precision::Bf16), &slow, &work)
            .unwrap();
        let fast_result = oracle
            .estimate(&model(Precision::Bf16), &fast, &work)
            .unwrap();

        assert!(fast_result.memory_seconds < slow_result.memory_seconds);
        assert!(fast_result.latency_seconds < slow_result.latency_seconds);
    }

    #[test]
    fn lower_precision_arithmetic_improves_throughput_and_energy() {
        let oracle = TensorTileOracle::default();
        let hardware = hardware();
        let work = PhaseWork::prefill(4, 128, 8_256);

        let bf16 = oracle
            .estimate(&model(Precision::Bf16), &hardware, &work)
            .unwrap();
        let int8 = oracle
            .estimate(&model(Precision::Int8), &hardware, &work)
            .unwrap();

        assert!(int8.compute_seconds < bf16.compute_seconds);
        assert!(int8.weight_bytes < bf16.weight_bytes);
        assert!(int8.energy_joules < bf16.energy_joules);
    }

    #[test]
    fn lower_hop_topology_reduces_noc_latency_and_energy() {
        let oracle = TensorTileOracle::default();
        let crossbar = hardware();
        let mut ring = crossbar.clone();
        ring.design.as_mut().unwrap().network.topology = NetworkTopology::Ring;
        let work = PhaseWork::prefill(8, 256, 16_000);

        let crossbar_result = oracle
            .estimate(&model(Precision::Bf16), &crossbar, &work)
            .unwrap();
        let ring_result = oracle
            .estimate(&model(Precision::Bf16), &ring, &work)
            .unwrap();
        let crossbar_noc = crossbar_result
            .actions
            .iter()
            .find(|action| action.kind == ActionKind::OnChipTransfer)
            .unwrap();
        let ring_noc = ring_result
            .actions
            .iter()
            .find(|action| action.kind == ActionKind::OnChipTransfer)
            .unwrap();

        assert!(crossbar_noc.latency_seconds < ring_noc.latency_seconds);
        assert!(crossbar_noc.energy_joules < ring_noc.energy_joules);
    }
}
