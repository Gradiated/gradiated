use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::codesign::{CoDesignError, EffectiveModelVariant, ModelVariant};
use crate::economics::{EconomicsError, SiliconCostInputs};
use crate::spec::{
    AggregateHardwareSpec, ArithmeticSpec, ComputeArraySpec, ComputeSpec, DieSpec,
    HardwareDesignSpec, HardwareFidelity, HardwareSpec, InterconnectSpec, LinkSpec,
    ManufacturingSpec, ModelArchitecture, ModelSpec, NetworkTopology, OffChipMemoryKind,
    OffChipMemoryTierSpec, OnChipMemoryKind, OnChipMemoryTierSpec, OnDieNetworkSpec, PackageSpec,
    PowerThermalSpec, ProcessSpec,
};

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct ServingDesignPoint {
    pub max_concurrent_requests: u32,
    pub reserved_sequence_tokens_per_request: u32,
    pub decode_batch_size: u32,
    pub average_decode_context_tokens: u32,
    pub target_output_tokens_per_second: f64,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct MemoryTechnology {
    pub hbm_stack_capacity_bytes: u64,
    pub hbm_stack_bandwidth_bytes_per_second: f64,
    pub hbm_stack_power_watts: f64,
    pub hbm_stack_cost_usd: f64,
    pub hbm_stack_area_square_millimeters: f64,
    pub max_hbm_stacks_per_device: u32,
    pub bandwidth_efficiency: f64,
    pub runtime_fixed_bytes: u64,
    pub runtime_headroom_fraction: f64,
    pub minimum_tile_tokens: u32,
    pub minimum_sram_bytes_per_array: u64,
    pub maximum_sram_bytes_per_device: u64,
    pub sram_bandwidth_bytes_per_second_per_array: f64,
    pub sram_energy_picojoules_per_byte: f64,
    pub sram_area_square_millimeters_per_megabyte: f64,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct ComputeTechnology {
    pub array_rows: u32,
    pub array_columns: u32,
    pub frequency_hz: f64,
    pub operations_per_cycle_per_element: f64,
    pub compute_efficiency: f64,
    pub energy_picojoules_per_operation: f64,
    pub area_square_millimeters_per_array: f64,
    pub power_watts_per_array: f64,
    pub max_arrays_per_chiplet: u32,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub enum YieldModel {
    Fixed { die_yield: f64 },
    Poisson,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct PhysicalConstraints {
    pub max_devices: u32,
    pub max_chiplets_per_device: u32,
    pub maximum_die_area_square_millimeters: f64,
    pub fixed_die_area_square_millimeters: f64,
    pub maximum_device_tdp_watts: f64,
    pub base_device_power_watts: f64,
    pub cooling_headroom_fraction: f64,
    pub node_nanometers: f64,
    pub transistor_density_million_per_square_millimeter: f64,
    pub wafer_diameter_millimeters: f64,
    pub wafer_cost_usd: f64,
    pub defect_density_per_square_centimeter: f64,
    pub yield_model: YieldModel,
    pub package_yield: f64,
    pub package_cost_usd_per_device: f64,
    pub package_area_square_millimeters_per_device: f64,
    pub assembly_cost_usd_per_device: f64,
    pub test_cost_usd_per_device: f64,
    pub non_recurring_engineering_cost_usd: f64,
    pub amortization_units: u64,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct InterconnectTechnology {
    pub bandwidth_bytes_per_second_per_link: f64,
    pub link_efficiency: f64,
    pub max_links_per_device: u32,
    pub latency_nanoseconds: f64,
    pub energy_picojoules_per_byte: f64,
    pub power_watts_per_link: f64,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct CostAssumptions {
    pub active_lifetime_hours: f64,
    pub target_utilization: f64,
    pub host_hourly_cost_usd: f64,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct HardwareSizingConstraints {
    pub serving: ServingDesignPoint,
    pub memory: MemoryTechnology,
    pub compute: ComputeTechnology,
    pub physical: PhysicalConstraints,
    pub interconnect: InterconnectTechnology,
    pub cost: CostAssumptions,
}

impl Default for HardwareSizingConstraints {
    fn default() -> Self {
        Self {
            serving: ServingDesignPoint {
                max_concurrent_requests: 32,
                reserved_sequence_tokens_per_request: 8_192,
                decode_batch_size: 32,
                average_decode_context_tokens: 4_096,
                target_output_tokens_per_second: 2_000.0,
            },
            memory: MemoryTechnology {
                hbm_stack_capacity_bytes: 24_000_000_000,
                hbm_stack_bandwidth_bytes_per_second: 800_000_000_000.0,
                hbm_stack_power_watts: 20.0,
                hbm_stack_cost_usd: 300.0,
                hbm_stack_area_square_millimeters: 110.0,
                max_hbm_stacks_per_device: 4,
                bandwidth_efficiency: 0.8,
                runtime_fixed_bytes: 2_000_000_000,
                runtime_headroom_fraction: 0.15,
                minimum_tile_tokens: 128,
                minimum_sram_bytes_per_array: 1_048_576,
                maximum_sram_bytes_per_device: 67_108_864,
                sram_bandwidth_bytes_per_second_per_array: 2_000_000_000_000.0,
                sram_energy_picojoules_per_byte: 0.5,
                sram_area_square_millimeters_per_megabyte: 0.4,
            },
            compute: ComputeTechnology {
                array_rows: 128,
                array_columns: 128,
                frequency_hz: 1_500_000_000.0,
                operations_per_cycle_per_element: 2.0,
                compute_efficiency: 0.7,
                energy_picojoules_per_operation: 0.2,
                area_square_millimeters_per_array: 12.0,
                power_watts_per_array: 25.0,
                max_arrays_per_chiplet: 4,
            },
            physical: PhysicalConstraints {
                max_devices: 8,
                max_chiplets_per_device: 4,
                maximum_die_area_square_millimeters: 600.0,
                fixed_die_area_square_millimeters: 60.0,
                maximum_device_tdp_watts: 450.0,
                base_device_power_watts: 50.0,
                cooling_headroom_fraction: 0.1,
                node_nanometers: 4.0,
                transistor_density_million_per_square_millimeter: 200.0,
                wafer_diameter_millimeters: 300.0,
                wafer_cost_usd: 20_000.0,
                defect_density_per_square_centimeter: 0.1,
                yield_model: YieldModel::Poisson,
                package_yield: 0.95,
                package_cost_usd_per_device: 500.0,
                package_area_square_millimeters_per_device: 1_200.0,
                assembly_cost_usd_per_device: 100.0,
                test_cost_usd_per_device: 50.0,
                non_recurring_engineering_cost_usd: 20_000_000.0,
                amortization_units: 100_000,
            },
            interconnect: InterconnectTechnology {
                bandwidth_bytes_per_second_per_link: 200_000_000_000.0,
                link_efficiency: 0.8,
                max_links_per_device: 8,
                latency_nanoseconds: 100.0,
                energy_picojoules_per_byte: 2.0,
                power_watts_per_link: 5.0,
            },
            cost: CostAssumptions {
                active_lifetime_hours: 26_280.0,
                target_utilization: 0.7,
                host_hourly_cost_usd: 0.25,
            },
        }
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct SizingRequirements {
    pub weight_bytes: u64,
    pub kv_cache_bytes: u64,
    pub runtime_fixed_bytes: u64,
    pub runtime_headroom_bytes: u64,
    pub total_hbm_bytes: u64,
    pub memory_bandwidth_bytes_per_second: f64,
    pub compute_operations_per_second: f64,
    pub interconnect_bandwidth_bytes_per_second: f64,
    pub sram_bytes_per_array: u64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ProvisionedResources {
    pub hbm_capacity_bytes: u64,
    pub hbm_bandwidth_bytes_per_second: f64,
    pub compute_operations_per_second: f64,
    pub interconnect_bandwidth_bytes_per_second: f64,
    pub sram_capacity_bytes: u64,
    pub thermal_design_power_watts: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct HardwareMapping {
    pub device_count: u32,
    pub minimum_required_device_count: u32,
    pub hbm_stacks_per_device: u32,
    pub tensor_arrays_per_device: u32,
    pub tensor_array_rows: u32,
    pub tensor_array_columns: u32,
    pub chiplets_per_device: u32,
    pub links_per_device: u32,
    pub tensor_parallelism: u32,
    pub die_area_square_millimeters: f64,
    pub tile_token_capacity: u64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct CostImplications {
    pub die_yield: f64,
    pub gross_dies_per_wafer: u64,
    pub known_good_silicon_cost_usd: f64,
    pub hbm_cost_usd: f64,
    pub package_and_test_cost_usd: f64,
    pub nre_cost_usd_per_unit: f64,
    pub estimated_system_capital_usd: f64,
    pub estimated_accelerator_usd_per_active_hour: f64,
    pub excluded_costs: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct SizingAssumption {
    pub name: String,
    pub value: String,
    pub consequence: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ConstraintKind {
    HbmCapacity,
    HbmBandwidth,
    ComputeThroughput,
    SramCapacity,
    DeviceCount,
    HbmStacksPerDevice,
    TensorArraysPerChiplet,
    ChipletsPerDevice,
    DieArea,
    DevicePower,
    InterconnectBandwidth,
    ArithmeticPrecision,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ConstraintViolation {
    pub constraint: ConstraintKind,
    pub required: f64,
    pub available: f64,
    pub unit: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SizingSource {
    Synthesized,
    Validated,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct HardwareSizingReport {
    pub source: SizingSource,
    pub model_id: String,
    pub hardware: HardwareSpec,
    pub requirements: SizingRequirements,
    pub provisioned: ProvisionedResources,
    pub mapping: HardwareMapping,
    pub cost: CostImplications,
    pub assumptions: Vec<SizingAssumption>,
    pub violations: Vec<ConstraintViolation>,
}

impl HardwareSizingReport {
    pub fn is_feasible(&self) -> bool {
        self.violations.is_empty()
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct HardwareSizer;

impl HardwareSizer {
    pub fn synthesize(
        &self,
        model: &ModelSpec,
        constraints: &HardwareSizingConstraints,
    ) -> Result<HardwareSizingReport, SizingError> {
        validate_constraints(constraints)?;
        let requirements = derive_requirements(model, constraints)?;
        let total_hbm_stacks = required_hbm_stacks(&requirements, constraints)?;
        let total_tensor_arrays = required_tensor_arrays(&requirements, constraints)?;
        let mapping = select_mapping(
            total_hbm_stacks,
            total_tensor_arrays,
            &requirements,
            constraints,
        )?;
        let provisioned = provisioned_resources(&mapping, &requirements, constraints)?;
        let cost = derive_cost(&mapping, constraints)?;
        let hardware = build_hardware(model, &mapping, &provisioned, &cost, constraints)?;
        let violations =
            assess_constraints(&requirements, &provisioned, &mapping, constraints, true);

        Ok(HardwareSizingReport {
            source: SizingSource::Synthesized,
            model_id: model.model_id.clone(),
            hardware,
            requirements,
            provisioned,
            mapping,
            cost,
            assumptions: sizing_assumptions(constraints),
            violations,
        })
    }

    pub fn synthesize_variant(
        &self,
        base: &ModelSpec,
        variant: &ModelVariant,
        constraints: &HardwareSizingConstraints,
    ) -> Result<HardwareSizingReport, SizingError> {
        let effective = variant.apply(base)?;
        self.synthesize_effective_variant(&effective, constraints)
    }

    pub fn synthesize_effective_variant(
        &self,
        variant: &EffectiveModelVariant,
        constraints: &HardwareSizingConstraints,
    ) -> Result<HardwareSizingReport, SizingError> {
        let mut report = self.synthesize(&variant.model, constraints)?;
        report.assumptions.push(SizingAssumption {
            name: "model_quality".into(),
            value: "not inferred by hardware sizing".into(),
            consequence: format!(
                "variant {} requires separate quality evidence before an economic conclusion",
                variant.name
            ),
        });
        if variant.requires_structured_sparse_execution {
            report.assumptions.push(SizingAssumption {
                name: "structured_sparse_execution".into(),
                value: "required".into(),
                consequence:
                    "provisioned throughput assumes the declared parameter reduction is executable"
                        .into(),
            });
        }
        Ok(report)
    }

    pub fn validate_hardware(
        &self,
        model: &ModelSpec,
        hardware: &HardwareSpec,
        constraints: &HardwareSizingConstraints,
    ) -> Result<HardwareSizingReport, SizingError> {
        validate_constraints(constraints)?;
        let device_count = hardware.physical_device_count;
        if device_count == 0 {
            return Err(SizingError::InvalidConstraint {
                field: "device_count",
            });
        }
        let requirements = derive_requirements(model, constraints)?;
        let capacity = hardware.effective_memory_capacity_bytes().ok_or(
            SizingError::MissingHardwareInformation {
                field: "memory capacity",
            },
        )?;
        let bandwidth = hardware
            .effective_memory_bandwidth_bytes_per_second()
            .ok_or(SizingError::MissingHardwareInformation {
                field: "memory bandwidth",
            })?;
        let compute = hardware.effective_compute_operations_per_second().ok_or(
            SizingError::MissingHardwareInformation {
                field: "compute throughput",
            },
        )?;
        let peak_power = hardware.effective_peak_power_watts().ok_or(
            SizingError::MissingHardwareInformation {
                field: "peak power",
            },
        )?;
        let design = hardware.design.as_ref();
        let total_arrays = design
            .map(|value| value.compute.array_count)
            .unwrap_or_else(|| {
                ceil_u32(
                    compute / raw_array_operations_per_second(constraints).unwrap_or(f64::INFINITY),
                )
                .unwrap_or(1)
            })
            .max(1);
        let total_hbm_stacks = ceil_div_u64(capacity, constraints.memory.hbm_stack_capacity_bytes)?;
        let total_hbm_stacks =
            u32::try_from(total_hbm_stacks).map_err(|_| SizingError::Overflow)?;
        let total_chiplets = design
            .map(|value| value.die.die_count)
            .unwrap_or(device_count);
        let chiplets_per_device = total_chiplets.div_ceil(device_count).max(1);
        let tensor_arrays_per_device = total_arrays.div_ceil(device_count).max(1);
        let hbm_stacks_per_device = total_hbm_stacks.div_ceil(device_count).max(1);
        let sram_capacity = design
            .map(|value| {
                value
                    .on_chip_memory
                    .iter()
                    .map(|tier| tier.capacity_bytes)
                    .try_fold(0_u64, u64::checked_add)
                    .ok_or(SizingError::Overflow)
            })
            .transpose()?
            .unwrap_or(0);
        let links = design
            .map(|value| {
                value
                    .interconnect
                    .scale_up
                    .iter()
                    .map(|link| link.link_count)
                    .try_fold(0_u32, u32::checked_add)
                    .ok_or(SizingError::Overflow)
            })
            .transpose()?
            .unwrap_or(0);
        let links_per_device = if device_count > 1 {
            links.div_ceil(device_count)
        } else {
            0
        };
        let interconnect_bandwidth = design
            .map(|value| {
                value
                    .interconnect
                    .scale_up
                    .iter()
                    .map(|link| {
                        f64::from(link.link_count)
                            * link.bandwidth_bytes_per_second_per_link
                            * constraints.interconnect.link_efficiency
                    })
                    .sum()
            })
            .unwrap_or(0.0);
        let die_area = design
            .map(|value| value.die.area_square_millimeters)
            .unwrap_or(constraints.physical.maximum_die_area_square_millimeters);
        let tile_token_capacity = if total_arrays == 0 {
            0
        } else {
            sram_capacity
                .checked_div(u64::from(total_arrays))
                .unwrap_or(0)
                .checked_div(tile_working_set_bytes(model)?)
                .unwrap_or(0)
        };
        let minimum_required_device_count = minimum_device_count(
            required_hbm_stacks(&requirements, constraints)?,
            required_tensor_arrays(&requirements, constraints)?,
            &requirements,
            constraints,
        )?;
        let mapping = HardwareMapping {
            device_count,
            minimum_required_device_count,
            hbm_stacks_per_device,
            tensor_arrays_per_device,
            tensor_array_rows: design
                .map(|value| value.compute.array.rows)
                .unwrap_or(constraints.compute.array_rows),
            tensor_array_columns: design
                .map(|value| value.compute.array.columns)
                .unwrap_or(constraints.compute.array_columns),
            chiplets_per_device,
            links_per_device,
            tensor_parallelism: device_count,
            die_area_square_millimeters: die_area,
            tile_token_capacity,
        };
        let provisioned = ProvisionedResources {
            hbm_capacity_bytes: capacity,
            hbm_bandwidth_bytes_per_second: bandwidth,
            compute_operations_per_second: compute,
            interconnect_bandwidth_bytes_per_second: interconnect_bandwidth,
            sram_capacity_bytes: sram_capacity,
            thermal_design_power_watts: peak_power,
        };
        let arithmetic_supported = design.is_none_or(|value| {
            value
                .compute
                .arithmetic
                .iter()
                .any(|arithmetic| arithmetic.precision == model.weight_precision)
        });
        let cost = derive_cost(&mapping, constraints)?;
        let violations = assess_constraints(
            &requirements,
            &provisioned,
            &mapping,
            constraints,
            arithmetic_supported,
        );
        let mut assumptions = sizing_assumptions(constraints);
        assumptions.push(SizingAssumption {
            name: "validation_scope".into(),
            value: "declared hardware fields".into(),
            consequence: "validation does not independently verify silicon measurements".into(),
        });
        assumptions.push(SizingAssumption {
            name: "validation_cost_model".into(),
            value: "sizing cost assumptions".into(),
            consequence:
                "cost implications are recomputed from sizing inputs rather than audited invoices"
                    .into(),
        });

        Ok(HardwareSizingReport {
            source: SizingSource::Validated,
            model_id: model.model_id.clone(),
            hardware: hardware.clone(),
            requirements,
            provisioned,
            mapping,
            cost,
            assumptions,
            violations,
        })
    }
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum SizingError {
    #[error("model architecture does not have complete performance and cache accounting")]
    UnsupportedModelArchitecture,
    #[error("invalid sizing constraint: {field}")]
    InvalidConstraint { field: &'static str },
    #[error("model or sizing arithmetic exceeded numeric limits")]
    Overflow,
    #[error("model variant is invalid: {0}")]
    ModelVariant(#[from] CoDesignError),
    #[error("cost implication could not be evaluated: {0}")]
    Economics(#[from] EconomicsError),
    #[error("hardware does not expose enough information for validation: {field}")]
    MissingHardwareInformation { field: &'static str },
}

fn derive_requirements(
    model: &ModelSpec,
    constraints: &HardwareSizingConstraints,
) -> Result<SizingRequirements, SizingError> {
    if !matches!(model.architecture, ModelArchitecture::DenseDecoder) {
        return Err(SizingError::UnsupportedModelArchitecture);
    }
    let weight_bytes = model.weight_bytes().ok_or(SizingError::Overflow)?;
    let kv_bytes_per_token = model.kv_bytes_per_token().ok_or(SizingError::Overflow)?;
    let reserved_tokens = u64::from(constraints.serving.max_concurrent_requests)
        .checked_mul(u64::from(
            constraints.serving.reserved_sequence_tokens_per_request,
        ))
        .ok_or(SizingError::Overflow)?;
    let kv_cache_bytes = kv_bytes_per_token
        .checked_mul(reserved_tokens)
        .ok_or(SizingError::Overflow)?;
    let base_memory = weight_bytes
        .checked_add(kv_cache_bytes)
        .and_then(|value| value.checked_add(constraints.memory.runtime_fixed_bytes))
        .ok_or(SizingError::Overflow)?;
    let runtime_headroom_bytes =
        ceil_u64(base_memory as f64 * constraints.memory.runtime_headroom_fraction)?;
    let total_hbm_bytes = base_memory
        .checked_add(runtime_headroom_bytes)
        .ok_or(SizingError::Overflow)?;

    let weight_bytes_per_output =
        weight_bytes as f64 / f64::from(constraints.serving.decode_batch_size);
    let kv_read_bytes_per_output =
        kv_bytes_per_token as f64 * f64::from(constraints.serving.average_decode_context_tokens);
    let kv_write_bytes_per_output = kv_bytes_per_token as f64;
    let memory_bandwidth_bytes_per_second = checked_f64(
        (weight_bytes_per_output + kv_read_bytes_per_output + kv_write_bytes_per_output)
            * constraints.serving.target_output_tokens_per_second,
    )?;
    let operations_per_output = checked_f64(
        2.0 * model.parameter_count as f64
            + 4.0
                * f64::from(model.layer_count)
                * f64::from(model.hidden_size)
                * (f64::from(constraints.serving.average_decode_context_tokens) + 1.0),
    )?;
    let compute_operations_per_second =
        checked_f64(operations_per_output * constraints.serving.target_output_tokens_per_second)?;
    let interconnect_bytes_per_output =
        checked_f64(4.0 * f64::from(model.layer_count) * f64::from(model.hidden_size))?;
    let interconnect_bandwidth_bytes_per_second = checked_f64(
        interconnect_bytes_per_output * constraints.serving.target_output_tokens_per_second,
    )?;
    let tile_working_set = tile_working_set_bytes(model)?;
    let tile_sram = tile_working_set
        .checked_mul(u64::from(constraints.memory.minimum_tile_tokens))
        .ok_or(SizingError::Overflow)?;

    Ok(SizingRequirements {
        weight_bytes,
        kv_cache_bytes,
        runtime_fixed_bytes: constraints.memory.runtime_fixed_bytes,
        runtime_headroom_bytes,
        total_hbm_bytes,
        memory_bandwidth_bytes_per_second,
        compute_operations_per_second,
        interconnect_bandwidth_bytes_per_second,
        sram_bytes_per_array: tile_sram.max(constraints.memory.minimum_sram_bytes_per_array),
    })
}

fn tile_working_set_bytes(model: &ModelSpec) -> Result<u64, SizingError> {
    let activations = u64::from(model.hidden_size)
        .checked_mul(8)
        .ok_or(SizingError::Overflow)?;
    let layer_kv = model
        .kv_bytes_per_token()
        .ok_or(SizingError::Overflow)?
        .checked_div(u64::from(model.layer_count))
        .ok_or(SizingError::Overflow)?;
    activations
        .checked_add(layer_kv)
        .ok_or(SizingError::Overflow)
}

fn required_hbm_stacks(
    requirements: &SizingRequirements,
    constraints: &HardwareSizingConstraints,
) -> Result<u32, SizingError> {
    let capacity_stacks = ceil_div_u64(
        requirements.total_hbm_bytes,
        constraints.memory.hbm_stack_capacity_bytes,
    )?;
    let bandwidth_per_stack = constraints.memory.hbm_stack_bandwidth_bytes_per_second
        * constraints.memory.bandwidth_efficiency;
    let bandwidth_stacks =
        ceil_u64(requirements.memory_bandwidth_bytes_per_second / bandwidth_per_stack)?;
    u32::try_from(capacity_stacks.max(bandwidth_stacks).max(1)).map_err(|_| SizingError::Overflow)
}

fn required_tensor_arrays(
    requirements: &SizingRequirements,
    constraints: &HardwareSizingConstraints,
) -> Result<u32, SizingError> {
    let effective_array =
        raw_array_operations_per_second(constraints)? * constraints.compute.compute_efficiency;
    ceil_u32(requirements.compute_operations_per_second / effective_array).map(|value| value.max(1))
}

fn raw_array_operations_per_second(
    constraints: &HardwareSizingConstraints,
) -> Result<f64, SizingError> {
    checked_f64(
        f64::from(constraints.compute.array_rows)
            * f64::from(constraints.compute.array_columns)
            * constraints.compute.frequency_hz
            * constraints.compute.operations_per_cycle_per_element,
    )
}

fn select_mapping(
    total_hbm_stacks: u32,
    total_tensor_arrays: u32,
    requirements: &SizingRequirements,
    constraints: &HardwareSizingConstraints,
) -> Result<HardwareMapping, SizingError> {
    let minimum_required_device_count = minimum_device_count(
        total_hbm_stacks,
        total_tensor_arrays,
        requirements,
        constraints,
    )?;
    mapping_candidate(
        minimum_required_device_count.min(constraints.physical.max_devices),
        minimum_required_device_count,
        total_hbm_stacks,
        total_tensor_arrays,
        requirements,
        constraints,
    )
}

fn mapping_candidate(
    device_count: u32,
    minimum_required_device_count: u32,
    total_hbm_stacks: u32,
    total_tensor_arrays: u32,
    requirements: &SizingRequirements,
    constraints: &HardwareSizingConstraints,
) -> Result<HardwareMapping, SizingError> {
    let hbm_stacks_per_device = total_hbm_stacks.div_ceil(device_count);
    let tensor_arrays_per_device = total_tensor_arrays.div_ceil(device_count);
    let sram_per_device = requirements
        .sram_bytes_per_array
        .checked_mul(u64::from(tensor_arrays_per_device))
        .ok_or(SizingError::Overflow)?;
    let compute_area =
        f64::from(tensor_arrays_per_device) * constraints.compute.area_square_millimeters_per_array;
    let sram_area = sram_per_device as f64 / 1_048_576.0
        * constraints.memory.sram_area_square_millimeters_per_megabyte;
    let variable_area = checked_f64(compute_area + sram_area)?;
    let usable_die_area = constraints.physical.maximum_die_area_square_millimeters
        - constraints.physical.fixed_die_area_square_millimeters;
    let area_chiplets = ceil_u32(variable_area / usable_die_area)?.max(1);
    let array_chiplets = tensor_arrays_per_device
        .div_ceil(constraints.compute.max_arrays_per_chiplet)
        .max(1);
    let chiplets_per_device = area_chiplets.max(array_chiplets);
    let die_area_square_millimeters = constraints.physical.fixed_die_area_square_millimeters
        + variable_area / f64::from(chiplets_per_device);
    let links_per_device = if device_count > 1 {
        let effective_link = constraints.interconnect.bandwidth_bytes_per_second_per_link
            * constraints.interconnect.link_efficiency;
        ceil_u32(
            requirements.interconnect_bandwidth_bytes_per_second
                / (effective_link * f64::from(device_count)),
        )?
        .max(1)
    } else {
        0
    };
    let tile_token_capacity = sram_per_device
        .checked_div(u64::from(tensor_arrays_per_device))
        .unwrap_or(0)
        .checked_div(
            requirements
                .sram_bytes_per_array
                .checked_div(u64::from(constraints.memory.minimum_tile_tokens))
                .unwrap_or(1)
                .max(1),
        )
        .unwrap_or(0);
    Ok(HardwareMapping {
        device_count,
        minimum_required_device_count,
        hbm_stacks_per_device,
        tensor_arrays_per_device,
        tensor_array_rows: constraints.compute.array_rows,
        tensor_array_columns: constraints.compute.array_columns,
        chiplets_per_device,
        links_per_device,
        tensor_parallelism: device_count,
        die_area_square_millimeters,
        tile_token_capacity,
    })
}

fn minimum_device_count(
    total_hbm_stacks: u32,
    total_tensor_arrays: u32,
    requirements: &SizingRequirements,
    constraints: &HardwareSizingConstraints,
) -> Result<u32, SizingError> {
    let hbm_devices = total_hbm_stacks
        .div_ceil(constraints.memory.max_hbm_stacks_per_device)
        .max(1);
    let arrays_per_device = constraints
        .compute
        .max_arrays_per_chiplet
        .checked_mul(constraints.physical.max_chiplets_per_device)
        .ok_or(SizingError::Overflow)?;
    let compute_devices = total_tensor_arrays.div_ceil(arrays_per_device).max(1);
    let total_sram = requirements
        .sram_bytes_per_array
        .checked_mul(u64::from(total_tensor_arrays))
        .ok_or(SizingError::Overflow)?;
    let sram_devices = ceil_div_u64(total_sram, constraints.memory.maximum_sram_bytes_per_device)?;
    let sram_devices = u32::try_from(sram_devices).map_err(|_| SizingError::Overflow)?;
    let total_variable_area = f64::from(total_tensor_arrays)
        * constraints.compute.area_square_millimeters_per_array
        + total_sram as f64 / 1_048_576.0
            * constraints.memory.sram_area_square_millimeters_per_megabyte;
    let variable_area_per_device = (constraints.physical.maximum_die_area_square_millimeters
        - constraints.physical.fixed_die_area_square_millimeters)
        * f64::from(constraints.physical.max_chiplets_per_device);
    let area_devices = ceil_u32(total_variable_area / variable_area_per_device)?.max(1);
    let resource_devices = hbm_devices
        .max(compute_devices)
        .max(sram_devices)
        .max(area_devices);
    let variable_power_per_device = constraints.physical.maximum_device_tdp_watts
        - constraints.physical.base_device_power_watts;
    let resource_power = f64::from(total_hbm_stacks) * constraints.memory.hbm_stack_power_watts
        + f64::from(total_tensor_arrays) * constraints.compute.power_watts_per_array;
    let preliminary_power_devices = if variable_power_per_device > 0.0 {
        ceil_u32(resource_power / variable_power_per_device)?.max(1)
    } else {
        u32::MAX
    };
    let total_links = if resource_devices.max(preliminary_power_devices) > 1 {
        ceil_u32(
            requirements.interconnect_bandwidth_bytes_per_second
                / (constraints.interconnect.bandwidth_bytes_per_second_per_link
                    * constraints.interconnect.link_efficiency),
        )?
    } else {
        0
    };
    let link_devices = if total_links == 0 {
        1
    } else {
        total_links
            .div_ceil(constraints.interconnect.max_links_per_device)
            .max(1)
    };
    let variable_power =
        resource_power + f64::from(total_links) * constraints.interconnect.power_watts_per_link;
    let power_devices = if variable_power_per_device > 0.0 {
        ceil_u32(variable_power / variable_power_per_device)?.max(1)
    } else {
        u32::MAX
    };
    Ok(resource_devices.max(link_devices).max(power_devices))
}

fn provisioned_resources(
    mapping: &HardwareMapping,
    requirements: &SizingRequirements,
    constraints: &HardwareSizingConstraints,
) -> Result<ProvisionedResources, SizingError> {
    let total_stacks = mapping
        .hbm_stacks_per_device
        .checked_mul(mapping.device_count)
        .ok_or(SizingError::Overflow)?;
    let total_arrays = mapping
        .tensor_arrays_per_device
        .checked_mul(mapping.device_count)
        .ok_or(SizingError::Overflow)?;
    let total_links = mapping
        .links_per_device
        .checked_mul(mapping.device_count)
        .ok_or(SizingError::Overflow)?;
    let hbm_capacity_bytes = constraints
        .memory
        .hbm_stack_capacity_bytes
        .checked_mul(u64::from(total_stacks))
        .ok_or(SizingError::Overflow)?;
    let sram_capacity_bytes = requirements
        .sram_bytes_per_array
        .checked_mul(u64::from(total_arrays))
        .ok_or(SizingError::Overflow)?;
    let device_power = constraints.physical.base_device_power_watts
        + f64::from(mapping.hbm_stacks_per_device) * constraints.memory.hbm_stack_power_watts
        + f64::from(mapping.tensor_arrays_per_device) * constraints.compute.power_watts_per_array
        + f64::from(mapping.links_per_device) * constraints.interconnect.power_watts_per_link;
    Ok(ProvisionedResources {
        hbm_capacity_bytes,
        hbm_bandwidth_bytes_per_second: checked_f64(
            f64::from(total_stacks)
                * constraints.memory.hbm_stack_bandwidth_bytes_per_second
                * constraints.memory.bandwidth_efficiency,
        )?,
        compute_operations_per_second: checked_f64(
            f64::from(total_arrays)
                * raw_array_operations_per_second(constraints)?
                * constraints.compute.compute_efficiency,
        )?,
        interconnect_bandwidth_bytes_per_second: checked_f64(
            f64::from(total_links)
                * constraints.interconnect.bandwidth_bytes_per_second_per_link
                * constraints.interconnect.link_efficiency,
        )?,
        sram_capacity_bytes,
        thermal_design_power_watts: checked_f64(device_power * f64::from(mapping.device_count))?,
    })
}

fn assess_constraints(
    requirements: &SizingRequirements,
    provisioned: &ProvisionedResources,
    mapping: &HardwareMapping,
    constraints: &HardwareSizingConstraints,
    arithmetic_supported: bool,
) -> Vec<ConstraintViolation> {
    let mut violations = Vec::new();
    compare(
        &mut violations,
        ConstraintKind::HbmCapacity,
        requirements.total_hbm_bytes as f64,
        provisioned.hbm_capacity_bytes as f64,
        "bytes",
    );
    compare(
        &mut violations,
        ConstraintKind::HbmBandwidth,
        requirements.memory_bandwidth_bytes_per_second,
        provisioned.hbm_bandwidth_bytes_per_second,
        "bytes/second",
    );
    compare(
        &mut violations,
        ConstraintKind::ComputeThroughput,
        requirements.compute_operations_per_second,
        provisioned.compute_operations_per_second,
        "operations/second",
    );
    let required_sram_per_device = requirements
        .sram_bytes_per_array
        .saturating_mul(u64::from(mapping.tensor_arrays_per_device));
    let required_sram = required_sram_per_device.saturating_mul(u64::from(mapping.device_count));
    compare(
        &mut violations,
        ConstraintKind::SramCapacity,
        required_sram as f64,
        provisioned.sram_capacity_bytes as f64,
        "bytes",
    );
    compare(
        &mut violations,
        ConstraintKind::SramCapacity,
        required_sram_per_device as f64,
        constraints.memory.maximum_sram_bytes_per_device as f64,
        "bytes/device",
    );
    compare(
        &mut violations,
        ConstraintKind::DeviceCount,
        f64::from(mapping.minimum_required_device_count),
        f64::from(mapping.device_count.min(constraints.physical.max_devices)),
        "devices",
    );
    compare(
        &mut violations,
        ConstraintKind::HbmStacksPerDevice,
        f64::from(mapping.hbm_stacks_per_device),
        f64::from(constraints.memory.max_hbm_stacks_per_device),
        "stacks/device",
    );
    let arrays_per_chiplet = mapping
        .tensor_arrays_per_device
        .div_ceil(mapping.chiplets_per_device.max(1));
    compare(
        &mut violations,
        ConstraintKind::TensorArraysPerChiplet,
        f64::from(arrays_per_chiplet),
        f64::from(constraints.compute.max_arrays_per_chiplet),
        "arrays/chiplet",
    );
    compare(
        &mut violations,
        ConstraintKind::ChipletsPerDevice,
        f64::from(mapping.chiplets_per_device),
        f64::from(constraints.physical.max_chiplets_per_device),
        "chiplets/device",
    );
    compare(
        &mut violations,
        ConstraintKind::DieArea,
        mapping.die_area_square_millimeters,
        constraints.physical.maximum_die_area_square_millimeters,
        "mm2",
    );
    compare(
        &mut violations,
        ConstraintKind::DevicePower,
        provisioned.thermal_design_power_watts / f64::from(mapping.device_count),
        constraints.physical.maximum_device_tdp_watts,
        "watts/device",
    );
    if mapping.device_count > 1 {
        compare(
            &mut violations,
            ConstraintKind::InterconnectBandwidth,
            requirements.interconnect_bandwidth_bytes_per_second,
            provisioned.interconnect_bandwidth_bytes_per_second,
            "bytes/second",
        );
        compare(
            &mut violations,
            ConstraintKind::InterconnectBandwidth,
            f64::from(mapping.links_per_device),
            f64::from(constraints.interconnect.max_links_per_device),
            "links/device",
        );
    }
    if !arithmetic_supported {
        violations.push(ConstraintViolation {
            constraint: ConstraintKind::ArithmeticPrecision,
            required: 1.0,
            available: 0.0,
            unit: "supported format".into(),
        });
    }
    violations
}

fn compare(
    violations: &mut Vec<ConstraintViolation>,
    constraint: ConstraintKind,
    required: f64,
    available: f64,
    unit: &str,
) {
    if required > available * (1.0 + 1.0e-12) {
        violations.push(ConstraintViolation {
            constraint,
            required,
            available,
            unit: unit.into(),
        });
    }
}

fn build_hardware(
    model: &ModelSpec,
    mapping: &HardwareMapping,
    provisioned: &ProvisionedResources,
    cost: &CostImplications,
    constraints: &HardwareSizingConstraints,
) -> Result<HardwareSpec, SizingError> {
    let total_arrays = mapping
        .tensor_arrays_per_device
        .checked_mul(mapping.device_count)
        .ok_or(SizingError::Overflow)?;
    let total_chiplets = mapping
        .chiplets_per_device
        .checked_mul(mapping.device_count)
        .ok_or(SizingError::Overflow)?;
    let total_stacks = mapping
        .hbm_stacks_per_device
        .checked_mul(mapping.device_count)
        .ok_or(SizingError::Overflow)?;
    let total_links = mapping
        .links_per_device
        .checked_mul(mapping.device_count)
        .ok_or(SizingError::Overflow)?;
    let raw_compute =
        checked_f64(f64::from(total_arrays) * raw_array_operations_per_second(constraints)?)?;
    let raw_hbm_bandwidth = checked_f64(
        f64::from(total_stacks) * constraints.memory.hbm_stack_bandwidth_bytes_per_second,
    )?;
    let sram_area = provisioned.sram_capacity_bytes as f64 / 1_048_576.0
        * constraints.memory.sram_area_square_millimeters_per_megabyte;
    let die_yield = die_yield(mapping.die_area_square_millimeters, constraints)?;
    let total_peak_power = provisioned.thermal_design_power_watts;
    let total_idle_power =
        constraints.physical.base_device_power_watts * f64::from(mapping.device_count);
    let scale_up = if total_links == 0 {
        Vec::new()
    } else {
        vec![LinkSpec {
            name: "sized-scale-up".into(),
            link_count: total_links,
            bandwidth_bytes_per_second_per_link: constraints
                .interconnect
                .bandwidth_bytes_per_second_per_link,
            latency_nanoseconds: constraints.interconnect.latency_nanoseconds,
            energy_picojoules_per_byte: constraints.interconnect.energy_picojoules_per_byte,
        }]
    };
    let package_cost =
        constraints.physical.package_cost_usd_per_device * f64::from(mapping.device_count);

    Ok(HardwareSpec {
        name: format!("sized-{}", model.model_id),
        fidelity: HardwareFidelity::Architecture,
        physical_device_count: mapping.device_count,
        aggregate: Some(AggregateHardwareSpec {
            memory_capacity_bytes: provisioned.hbm_capacity_bytes,
            memory_bandwidth_bytes_per_second: raw_hbm_bandwidth,
            compute_operations_per_second: raw_compute,
            compute_efficiency: constraints.compute.compute_efficiency,
            memory_efficiency: constraints.memory.bandwidth_efficiency,
            scale_up_bandwidth_bytes_per_second: provisioned
                .interconnect_bandwidth_bytes_per_second,
            scale_up_latency_nanoseconds: constraints.interconnect.latency_nanoseconds,
            scale_up_energy_picojoules_per_byte: constraints
                .interconnect
                .energy_picojoules_per_byte,
            idle_power_watts: total_idle_power,
            peak_power_watts: total_peak_power,
        }),
        design: Some(HardwareDesignSpec {
            process: ProcessSpec {
                node_nanometers: constraints.physical.node_nanometers,
                transistor_density_million_per_square_millimeter: constraints
                    .physical
                    .transistor_density_million_per_square_millimeter,
                wafer_diameter_millimeters: constraints.physical.wafer_diameter_millimeters,
                wafer_cost_usd: constraints.physical.wafer_cost_usd,
            },
            die: DieSpec {
                die_count: total_chiplets,
                area_square_millimeters: mapping.die_area_square_millimeters,
            },
            package: PackageSpec {
                package_type: if mapping.chiplets_per_device > 1 {
                    "analytical-chiplet-package".into()
                } else {
                    "analytical-single-die-package".into()
                },
                interposer_area_square_millimeters: constraints
                    .physical
                    .package_area_square_millimeters_per_device
                    * f64::from(mapping.device_count),
                package_cost_usd: package_cost,
            },
            compute: ComputeSpec {
                array_count: total_arrays,
                array: ComputeArraySpec {
                    rows: constraints.compute.array_rows,
                    columns: constraints.compute.array_columns,
                },
                frequency_hz: constraints.compute.frequency_hz,
                arithmetic: vec![ArithmeticSpec {
                    precision: model.weight_precision,
                    operations_per_cycle_per_element: constraints
                        .compute
                        .operations_per_cycle_per_element,
                    energy_picojoules_per_operation: constraints
                        .compute
                        .energy_picojoules_per_operation,
                }],
            },
            on_chip_memory: vec![OnChipMemoryTierSpec {
                name: "sized-sram".into(),
                kind: OnChipMemoryKind::Sram,
                capacity_bytes: provisioned.sram_capacity_bytes,
                bandwidth_bytes_per_second: checked_f64(
                    f64::from(total_arrays)
                        * constraints.memory.sram_bandwidth_bytes_per_second_per_array,
                )?,
                energy_picojoules_per_byte: constraints.memory.sram_energy_picojoules_per_byte,
                area_square_millimeters: sram_area,
            }],
            off_chip_memory: vec![OffChipMemoryTierSpec {
                name: "sized-hbm".into(),
                kind: OffChipMemoryKind::Hbm,
                capacity_bytes: provisioned.hbm_capacity_bytes,
                bandwidth_bytes_per_second: raw_hbm_bandwidth,
                energy_picojoules_per_byte: 5.0,
                area_square_millimeters: f64::from(total_stacks)
                    * constraints.memory.hbm_stack_area_square_millimeters,
                controller_latency_nanoseconds: 50.0,
            }],
            network: OnDieNetworkSpec {
                topology: NetworkTopology::Mesh,
                bisection_bandwidth_bytes_per_second: checked_f64(
                    f64::from(total_arrays)
                        * constraints.memory.sram_bandwidth_bytes_per_second_per_array
                        / 2.0,
                )?,
                hop_latency_nanoseconds: 2.0,
                energy_picojoules_per_byte_per_hop: 0.1,
                area_square_millimeters: f64::from(total_arrays).max(1.0),
            },
            interconnect: InterconnectSpec {
                scale_up,
                scale_out: Vec::new(),
            },
            power_thermal: PowerThermalSpec {
                idle_power_watts: total_idle_power,
                thermal_design_power_watts: total_peak_power,
                cooling_capacity_watts: total_peak_power
                    * (1.0 + constraints.physical.cooling_headroom_fraction),
                maximum_junction_temperature_celsius: 95.0,
            },
            manufacturing: ManufacturingSpec {
                defect_density_per_square_centimeter: constraints
                    .physical
                    .defect_density_per_square_centimeter,
                die_yield,
                package_yield: constraints.physical.package_yield,
                assembly_cost_usd: constraints.physical.assembly_cost_usd_per_device
                    * f64::from(mapping.device_count),
                test_cost_usd: constraints.physical.test_cost_usd_per_device
                    * f64::from(mapping.device_count),
                non_recurring_engineering_cost_usd: constraints
                    .physical
                    .non_recurring_engineering_cost_usd,
                amortization_units: constraints.physical.amortization_units,
            },
        }),
        accelerator_hourly_cost_usd: cost.estimated_accelerator_usd_per_active_hour,
        host_hourly_cost_usd: constraints.cost.host_hourly_cost_usd,
    })
}

fn derive_cost(
    mapping: &HardwareMapping,
    constraints: &HardwareSizingConstraints,
) -> Result<CostImplications, SizingError> {
    let total_chiplets = mapping
        .chiplets_per_device
        .checked_mul(mapping.device_count)
        .ok_or(SizingError::Overflow)?;
    let total_stacks = mapping
        .hbm_stacks_per_device
        .checked_mul(mapping.device_count)
        .ok_or(SizingError::Overflow)?;
    let yield_fraction = die_yield(mapping.die_area_square_millimeters, constraints)?;
    let silicon = SiliconCostInputs {
        wafer_cost_usd: constraints.physical.wafer_cost_usd,
        wafer_diameter_mm: constraints.physical.wafer_diameter_millimeters,
        die_area_mm2: mapping.die_area_square_millimeters,
        die_yield: yield_fraction,
        dies_per_accelerator: total_chiplets,
    };
    let gross_dies_per_wafer = silicon.gross_dies_per_wafer()?;
    let known_good_silicon_cost_usd = checked_f64(
        silicon.known_good_die_cost_usd()? * f64::from(total_chiplets)
            / constraints.physical.package_yield,
    )?;
    let hbm_cost_usd = checked_f64(
        f64::from(total_stacks) * constraints.memory.hbm_stack_cost_usd
            / constraints.physical.package_yield,
    )?;
    let package_and_test_cost_usd = checked_f64(
        f64::from(mapping.device_count)
            * (constraints.physical.package_cost_usd_per_device
                + constraints.physical.assembly_cost_usd_per_device
                + constraints.physical.test_cost_usd_per_device)
            / constraints.physical.package_yield,
    )?;
    let nre_cost_usd_per_unit = constraints.physical.non_recurring_engineering_cost_usd
        / constraints.physical.amortization_units as f64;
    let estimated_system_capital_usd = checked_f64(
        known_good_silicon_cost_usd
            + hbm_cost_usd
            + package_and_test_cost_usd
            + nre_cost_usd_per_unit,
    )?;
    let active_hours = constraints.cost.active_lifetime_hours * constraints.cost.target_utilization;
    let estimated_accelerator_usd_per_active_hour = estimated_system_capital_usd / active_hours;
    Ok(CostImplications {
        die_yield: yield_fraction,
        gross_dies_per_wafer,
        known_good_silicon_cost_usd,
        hbm_cost_usd,
        package_and_test_cost_usd,
        nre_cost_usd_per_unit,
        estimated_system_capital_usd,
        estimated_accelerator_usd_per_active_hour,
        excluded_costs: vec![
            "board and voltage regulation".into(),
            "host CPU and DRAM capital".into(),
            "rack network and cooling infrastructure".into(),
            "financing, operations, redundancy, and failures".into(),
        ],
    })
}

fn die_yield(
    die_area_square_millimeters: f64,
    constraints: &HardwareSizingConstraints,
) -> Result<f64, SizingError> {
    let value = match constraints.physical.yield_model {
        YieldModel::Fixed { die_yield } => die_yield,
        YieldModel::Poisson => (-constraints.physical.defect_density_per_square_centimeter
            * die_area_square_millimeters
            / 100.0)
            .exp(),
    };
    if !value.is_finite() || value <= 0.0 || value > 1.0 {
        return Err(SizingError::InvalidConstraint {
            field: "physical.yield_model",
        });
    }
    Ok(value)
}

fn sizing_assumptions(constraints: &HardwareSizingConstraints) -> Vec<SizingAssumption> {
    vec![
        SizingAssumption {
            name: "fidelity".into(),
            value: "analytical sizing".into(),
            consequence:
                "results are hypotheses for higher-fidelity simulation, not silicon measurements"
                    .into(),
        },
        SizingAssumption {
            name: "decode_memory_traffic".into(),
            value: "one sharded weight pass per decode batch plus full-context KV reads".into(),
            consequence: "kernel fusion, caching, and contention require later calibration".into(),
        },
        SizingAssumption {
            name: "activation_format".into(),
            value: "16-bit activations".into(),
            consequence: "SRAM and interconnect requirements change with activation format".into(),
        },
        SizingAssumption {
            name: "resource_scaling".into(),
            value:
                "uniform tensor, memory, and request sharding across a logical accelerator group"
                    .into(),
            consequence:
                "load imbalance, pipeline bubbles, and per-device tile timing are not included"
                    .into(),
        },
        SizingAssumption {
            name: "memory_action_model".into(),
            value: "5 pJ/byte HBM and 50 ns controller-latency placeholders".into(),
            consequence: "energy and latency require memory-vendor or calibrated simulator data"
                .into(),
        },
        SizingAssumption {
            name: "on_die_network_model".into(),
            value: "mesh with half aggregate SRAM bandwidth, 2 ns hops, and 0.1 pJ/byte-hop".into(),
            consequence: "NoC area, congestion, latency, and energy are exploratory estimates"
                .into(),
        },
        SizingAssumption {
            name: "yield_model".into(),
            value: match constraints.physical.yield_model {
                YieldModel::Fixed { .. } => "user-supplied fixed yield".into(),
                YieldModel::Poisson => "Poisson defect-density estimate".into(),
            },
            consequence: "yield and cost must be replaced with foundry and packaging data".into(),
        },
        SizingAssumption {
            name: "cost_scope".into(),
            value: "silicon, HBM, package/test, and amortized NRE".into(),
            consequence: "the listed excluded costs prevent treating this as complete TCO".into(),
        },
    ]
}

fn validate_constraints(constraints: &HardwareSizingConstraints) -> Result<(), SizingError> {
    positive_u32(
        constraints.serving.max_concurrent_requests,
        "serving.max_concurrent_requests",
    )?;
    positive_u32(
        constraints.serving.reserved_sequence_tokens_per_request,
        "serving.reserved_sequence_tokens_per_request",
    )?;
    positive_u32(
        constraints.serving.decode_batch_size,
        "serving.decode_batch_size",
    )?;
    positive_u32(
        constraints.serving.average_decode_context_tokens,
        "serving.average_decode_context_tokens",
    )?;
    positive(
        constraints.serving.target_output_tokens_per_second,
        "serving.target_output_tokens_per_second",
    )?;
    positive_u64(
        constraints.memory.hbm_stack_capacity_bytes,
        "memory.hbm_stack_capacity_bytes",
    )?;
    positive(
        constraints.memory.hbm_stack_bandwidth_bytes_per_second,
        "memory.hbm_stack_bandwidth_bytes_per_second",
    )?;
    non_negative(
        constraints.memory.hbm_stack_power_watts,
        "memory.hbm_stack_power_watts",
    )?;
    non_negative(
        constraints.memory.hbm_stack_cost_usd,
        "memory.hbm_stack_cost_usd",
    )?;
    positive(
        constraints.memory.hbm_stack_area_square_millimeters,
        "memory.hbm_stack_area_square_millimeters",
    )?;
    positive_u32(
        constraints.memory.max_hbm_stacks_per_device,
        "memory.max_hbm_stacks_per_device",
    )?;
    fraction(
        constraints.memory.bandwidth_efficiency,
        "memory.bandwidth_efficiency",
    )?;
    non_negative(
        constraints.memory.runtime_headroom_fraction,
        "memory.runtime_headroom_fraction",
    )?;
    positive_u32(
        constraints.memory.minimum_tile_tokens,
        "memory.minimum_tile_tokens",
    )?;
    positive_u64(
        constraints.memory.minimum_sram_bytes_per_array,
        "memory.minimum_sram_bytes_per_array",
    )?;
    positive_u64(
        constraints.memory.maximum_sram_bytes_per_device,
        "memory.maximum_sram_bytes_per_device",
    )?;
    positive(
        constraints.memory.sram_bandwidth_bytes_per_second_per_array,
        "memory.sram_bandwidth_bytes_per_second_per_array",
    )?;
    positive(
        constraints.memory.sram_energy_picojoules_per_byte,
        "memory.sram_energy_picojoules_per_byte",
    )?;
    positive(
        constraints.memory.sram_area_square_millimeters_per_megabyte,
        "memory.sram_area_square_millimeters_per_megabyte",
    )?;
    positive_u32(constraints.compute.array_rows, "compute.array_rows")?;
    positive_u32(constraints.compute.array_columns, "compute.array_columns")?;
    positive(constraints.compute.frequency_hz, "compute.frequency_hz")?;
    positive(
        constraints.compute.operations_per_cycle_per_element,
        "compute.operations_per_cycle_per_element",
    )?;
    fraction(
        constraints.compute.compute_efficiency,
        "compute.compute_efficiency",
    )?;
    positive(
        constraints.compute.energy_picojoules_per_operation,
        "compute.energy_picojoules_per_operation",
    )?;
    positive(
        constraints.compute.area_square_millimeters_per_array,
        "compute.area_square_millimeters_per_array",
    )?;
    positive(
        constraints.compute.power_watts_per_array,
        "compute.power_watts_per_array",
    )?;
    positive_u32(
        constraints.compute.max_arrays_per_chiplet,
        "compute.max_arrays_per_chiplet",
    )?;
    positive_u32(constraints.physical.max_devices, "physical.max_devices")?;
    positive_u32(
        constraints.physical.max_chiplets_per_device,
        "physical.max_chiplets_per_device",
    )?;
    positive(
        constraints.physical.maximum_die_area_square_millimeters,
        "physical.maximum_die_area_square_millimeters",
    )?;
    non_negative(
        constraints.physical.fixed_die_area_square_millimeters,
        "physical.fixed_die_area_square_millimeters",
    )?;
    if constraints.physical.fixed_die_area_square_millimeters
        >= constraints.physical.maximum_die_area_square_millimeters
    {
        return Err(SizingError::InvalidConstraint {
            field: "physical.fixed_die_area_square_millimeters",
        });
    }
    positive(
        constraints.physical.maximum_device_tdp_watts,
        "physical.maximum_device_tdp_watts",
    )?;
    non_negative(
        constraints.physical.base_device_power_watts,
        "physical.base_device_power_watts",
    )?;
    non_negative(
        constraints.physical.cooling_headroom_fraction,
        "physical.cooling_headroom_fraction",
    )?;
    positive(
        constraints.physical.node_nanometers,
        "physical.node_nanometers",
    )?;
    positive(
        constraints
            .physical
            .transistor_density_million_per_square_millimeter,
        "physical.transistor_density_million_per_square_millimeter",
    )?;
    positive(
        constraints.physical.wafer_diameter_millimeters,
        "physical.wafer_diameter_millimeters",
    )?;
    positive(
        constraints.physical.wafer_cost_usd,
        "physical.wafer_cost_usd",
    )?;
    non_negative(
        constraints.physical.defect_density_per_square_centimeter,
        "physical.defect_density_per_square_centimeter",
    )?;
    fraction(constraints.physical.package_yield, "physical.package_yield")?;
    non_negative(
        constraints.physical.package_cost_usd_per_device,
        "physical.package_cost_usd_per_device",
    )?;
    positive(
        constraints
            .physical
            .package_area_square_millimeters_per_device,
        "physical.package_area_square_millimeters_per_device",
    )?;
    non_negative(
        constraints.physical.assembly_cost_usd_per_device,
        "physical.assembly_cost_usd_per_device",
    )?;
    non_negative(
        constraints.physical.test_cost_usd_per_device,
        "physical.test_cost_usd_per_device",
    )?;
    non_negative(
        constraints.physical.non_recurring_engineering_cost_usd,
        "physical.non_recurring_engineering_cost_usd",
    )?;
    positive_u64(
        constraints.physical.amortization_units,
        "physical.amortization_units",
    )?;
    positive(
        constraints.interconnect.bandwidth_bytes_per_second_per_link,
        "interconnect.bandwidth_bytes_per_second_per_link",
    )?;
    fraction(
        constraints.interconnect.link_efficiency,
        "interconnect.link_efficiency",
    )?;
    positive_u32(
        constraints.interconnect.max_links_per_device,
        "interconnect.max_links_per_device",
    )?;
    positive(
        constraints.interconnect.latency_nanoseconds,
        "interconnect.latency_nanoseconds",
    )?;
    positive(
        constraints.interconnect.energy_picojoules_per_byte,
        "interconnect.energy_picojoules_per_byte",
    )?;
    non_negative(
        constraints.interconnect.power_watts_per_link,
        "interconnect.power_watts_per_link",
    )?;
    positive(
        constraints.cost.active_lifetime_hours,
        "cost.active_lifetime_hours",
    )?;
    fraction(
        constraints.cost.target_utilization,
        "cost.target_utilization",
    )?;
    non_negative(
        constraints.cost.host_hourly_cost_usd,
        "cost.host_hourly_cost_usd",
    )?;
    die_yield(1.0, constraints)?;
    Ok(())
}

fn positive(value: f64, field: &'static str) -> Result<(), SizingError> {
    if !value.is_finite() || value <= 0.0 {
        return Err(SizingError::InvalidConstraint { field });
    }
    Ok(())
}

fn non_negative(value: f64, field: &'static str) -> Result<(), SizingError> {
    if !value.is_finite() || value < 0.0 {
        return Err(SizingError::InvalidConstraint { field });
    }
    Ok(())
}

fn fraction(value: f64, field: &'static str) -> Result<(), SizingError> {
    if !value.is_finite() || value <= 0.0 || value > 1.0 {
        return Err(SizingError::InvalidConstraint { field });
    }
    Ok(())
}

fn positive_u32(value: u32, field: &'static str) -> Result<(), SizingError> {
    if value == 0 {
        return Err(SizingError::InvalidConstraint { field });
    }
    Ok(())
}

fn positive_u64(value: u64, field: &'static str) -> Result<(), SizingError> {
    if value == 0 {
        return Err(SizingError::InvalidConstraint { field });
    }
    Ok(())
}

fn checked_f64(value: f64) -> Result<f64, SizingError> {
    if !value.is_finite() || value < 0.0 {
        return Err(SizingError::Overflow);
    }
    Ok(value)
}

fn ceil_u64(value: f64) -> Result<u64, SizingError> {
    if !value.is_finite() || value < 0.0 || value.ceil() > u64::MAX as f64 {
        return Err(SizingError::Overflow);
    }
    Ok(value.ceil() as u64)
}

fn ceil_u32(value: f64) -> Result<u32, SizingError> {
    if !value.is_finite() || value < 0.0 || value.ceil() > f64::from(u32::MAX) {
        return Err(SizingError::Overflow);
    }
    Ok(value.ceil() as u32)
}

fn ceil_div_u64(numerator: u64, denominator: u64) -> Result<u64, SizingError> {
    numerator
        .checked_add(denominator.saturating_sub(1))
        .and_then(|value| value.checked_div(denominator))
        .ok_or(SizingError::Overflow)
}

#[cfg(test)]
mod tests {
    use crate::codesign::{ModelChange, ModelVariant, QualityEvidence};
    use crate::spec::{ModelArchitecture, Precision};

    use super::*;

    fn qwen() -> ModelSpec {
        ModelSpec {
            model_id: "Qwen/Qwen3-8B".into(),
            model_revision: "reference-fixture-v1".into(),
            architecture: ModelArchitecture::DenseDecoder,
            parameter_count: 8_200_000_000,
            layer_count: 36,
            hidden_size: 4_096,
            intermediate_size: 12_288,
            attention_head_count: 32,
            kv_head_count: 8,
            head_dimension: 128,
            vocabulary_size: 151_936,
            max_sequence_length: 32_768,
            weight_precision: Precision::Int4,
            quantized_weight_storage: Some(crate::spec::QuantizedWeightStorageSpec::grouped_all(
                128, 4, 16, 16, 0,
            )),
            kv_precision: Precision::Fp16,
        }
    }

    fn glm_scale() -> ModelSpec {
        ModelSpec {
            model_id: "synthetic/glm-scale-100b".into(),
            model_revision: "synthetic-projection-v1".into(),
            architecture: ModelArchitecture::DenseDecoder,
            parameter_count: 100_000_000_000,
            layer_count: 80,
            hidden_size: 8_192,
            intermediate_size: 28_672,
            attention_head_count: 64,
            kv_head_count: 8,
            head_dimension: 128,
            vocabulary_size: 150_000,
            max_sequence_length: 65_536,
            weight_precision: Precision::Int4,
            quantized_weight_storage: Some(crate::spec::QuantizedWeightStorageSpec::grouped_all(
                128, 4, 16, 16, 0,
            )),
            kv_precision: Precision::Fp16,
        }
    }

    #[test]
    fn model_scale_materially_changes_the_synthesized_system() {
        let constraints = HardwareSizingConstraints::default();
        let sizer = HardwareSizer;

        let qwen = sizer.synthesize(&qwen(), &constraints).unwrap();
        let glm = sizer.synthesize(&glm_scale(), &constraints).unwrap();

        assert!(qwen.is_feasible());
        assert!(glm.is_feasible());
        assert!(glm.requirements.total_hbm_bytes > qwen.requirements.total_hbm_bytes * 3);
        assert!(glm.mapping.device_count > qwen.mapping.device_count);
        assert!(glm.mapping.tensor_arrays_per_device > qwen.mapping.tensor_arrays_per_device);
        assert!(glm.mapping.chiplets_per_device > qwen.mapping.chiplets_per_device);
        assert!(glm.cost.estimated_system_capital_usd > qwen.cost.estimated_system_capital_usd);
        assert!(!glm.assumptions.is_empty());
    }

    #[test]
    fn model_variant_precision_resizes_memory_and_hardware() {
        let mut baseline = qwen();
        baseline.weight_precision = Precision::Bf16;
        baseline.quantized_weight_storage = None;
        let variant = ModelVariant {
            name: "qwen-int4".into(),
            changes: vec![ModelChange::WeightPrecision {
                precision: Precision::Int4,
                quantized_storage: Some(crate::spec::QuantizedWeightStorageSpec::grouped_all(
                    128, 4, 16, 16, 0,
                )),
            }],
            quality: QualityEvidence::Unvalidated,
        };
        let constraints = HardwareSizingConstraints::default();
        let sizer = HardwareSizer;

        let bf16 = sizer.synthesize(&baseline, &constraints).unwrap();
        let int4 = sizer
            .synthesize_variant(&baseline, &variant, &constraints)
            .unwrap();

        assert!(int4.requirements.weight_bytes < bf16.requirements.weight_bytes);
        assert!(int4.requirements.total_hbm_bytes < bf16.requirements.total_hbm_bytes);
        assert!(
            int4.assumptions
                .iter()
                .any(|item| item.name == "model_quality")
        );
    }

    #[test]
    fn quantized_storage_metadata_increases_hbm_and_bandwidth_requirements() {
        let compact = qwen();
        let mut metadata_heavy = compact.clone();
        metadata_heavy
            .quantized_weight_storage
            .as_mut()
            .unwrap()
            .fixed_metadata_bytes = 2_000_000_000;
        let constraints = HardwareSizingConstraints::default();

        let compact = HardwareSizer.synthesize(&compact, &constraints).unwrap();
        let metadata_heavy = HardwareSizer
            .synthesize(&metadata_heavy, &constraints)
            .unwrap();

        assert!(metadata_heavy.requirements.weight_bytes > compact.requirements.weight_bytes);
        assert!(metadata_heavy.requirements.total_hbm_bytes > compact.requirements.total_hbm_bytes);
        assert!(
            metadata_heavy
                .requirements
                .memory_bandwidth_bytes_per_second
                > compact.requirements.memory_bandwidth_bytes_per_second
        );
    }

    #[test]
    fn infeasible_packaging_limits_are_reported_not_hidden() {
        let mut constraints = HardwareSizingConstraints::default();
        constraints.physical.max_devices = 1;
        constraints.memory.max_hbm_stacks_per_device = 2;
        constraints.physical.max_chiplets_per_device = 1;

        let report = HardwareSizer
            .synthesize(&glm_scale(), &constraints)
            .unwrap();

        assert!(!report.is_feasible());
        assert!(report.violations.iter().any(|violation| {
            matches!(
                violation.constraint,
                ConstraintKind::HbmStacksPerDevice | ConstraintKind::ChipletsPerDevice
            )
        }));
    }

    #[test]
    fn validation_identifies_an_undersized_existing_design() {
        let constraints = HardwareSizingConstraints::default();
        let sizer = HardwareSizer;
        let synthesized = sizer.synthesize(&qwen(), &constraints).unwrap();
        let mut undersized = synthesized.hardware;
        undersized.aggregate.as_mut().unwrap().memory_capacity_bytes = 1_000_000_000;
        undersized.design.as_mut().unwrap().off_chip_memory[0].capacity_bytes = 1_000_000_000;

        let report = sizer
            .validate_hardware(&qwen(), &undersized, &constraints)
            .unwrap();

        assert_eq!(report.source, SizingSource::Validated);
        assert!(
            report
                .violations
                .iter()
                .any(|violation| violation.constraint == ConstraintKind::HbmCapacity)
        );
    }

    #[test]
    fn invalid_technology_inputs_return_a_typed_error() {
        let mut constraints = HardwareSizingConstraints::default();
        constraints.memory.bandwidth_efficiency = f64::NAN;

        let error = HardwareSizer.synthesize(&qwen(), &constraints).unwrap_err();

        assert_eq!(
            error,
            SizingError::InvalidConstraint {
                field: "memory.bandwidth_efficiency"
            }
        );
    }
}
