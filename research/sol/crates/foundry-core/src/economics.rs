use serde::{Deserialize, Serialize};
use std::f64::consts::PI;
use thiserror::Error;

use crate::performance::{InferencePhase, PhaseResult};
use crate::simulation::SimulationReport;
use crate::spec::{EconomicsSpec, HardwareSpec};

const SECONDS_PER_HOUR: f64 = 3_600.0;
const JOULES_PER_KILOWATT_HOUR: f64 = 3_600_000.0;

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct KnownHourlyCost {
    pub hardware_usd_per_hour: f64,
    pub host_usd_per_hour: f64,
    pub network_rack_usd_per_hour: f64,
    pub provider_usd_per_hour: f64,
    pub electricity_usd_per_kwh: f64,
    pub power_usage_effectiveness: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct SiliconCostInputs {
    pub wafer_cost_usd: f64,
    pub wafer_diameter_mm: f64,
    pub die_area_mm2: f64,
    pub die_yield: f64,
    pub dies_per_accelerator: u32,
}

impl SiliconCostInputs {
    pub fn gross_dies_per_wafer(&self) -> Result<u64, EconomicsError> {
        validate_positive("wafer_diameter_mm", self.wafer_diameter_mm)?;
        validate_positive("die_area_mm2", self.die_area_mm2)?;
        let wafer_area_term = PI * (self.wafer_diameter_mm / 2.0).powi(2) / self.die_area_mm2;
        let edge_loss_term = PI * self.wafer_diameter_mm / (2.0 * self.die_area_mm2).sqrt();
        let gross_dies = (wafer_area_term - edge_loss_term).floor();
        if !gross_dies.is_finite() || gross_dies < 1.0 {
            return Err(EconomicsError::InvalidSiliconGeometry);
        }
        Ok(gross_dies as u64)
    }

    pub fn known_good_die_cost_usd(&self) -> Result<f64, EconomicsError> {
        validate_non_negative("wafer_cost_usd", self.wafer_cost_usd)?;
        validate_fraction_exclusive_zero("die_yield", self.die_yield)?;
        if self.dies_per_accelerator == 0 {
            return Err(EconomicsError::InvalidCount("dies_per_accelerator"));
        }
        Ok(self.wafer_cost_usd / (self.gross_dies_per_wafer()? as f64 * self.die_yield))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct CustomSiliconTco {
    pub silicon: SiliconCostInputs,
    pub accelerators_per_server: u32,
    pub package_usd_per_accelerator: f64,
    pub memory_usd_per_accelerator: f64,
    pub board_usd_per_server: f64,
    pub host_usd_per_server: f64,
    pub network_usd_per_server: f64,
    pub rack_usd_per_server: f64,
    pub nre_usd: f64,
    pub nre_amortization_servers: u64,
    pub lifetime_hours: f64,
    pub target_utilization: f64,
    pub provider_usd_per_active_hour: f64,
    pub electricity_usd_per_kwh: f64,
    pub power_usage_effectiveness: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct ServerTcoInputs {
    pub accelerators_per_server: u32,
    pub memory_usd_per_accelerator: f64,
    pub board_usd_per_server: f64,
    pub host_usd_per_server: f64,
    pub network_usd_per_server: f64,
    pub rack_usd_per_server: f64,
    pub lifetime_hours: f64,
    pub target_utilization: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(tag = "cost_model", rename_all = "snake_case")]
pub enum CostModel {
    KnownHourly(KnownHourlyCost),
    CustomSilicon(CustomSiliconTco),
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct ServerCapitalBreakdown {
    pub silicon_usd: f64,
    pub package_usd: f64,
    pub memory_usd: f64,
    pub board_usd: f64,
    pub host_usd: f64,
    pub network_usd: f64,
    pub rack_usd: f64,
    pub nre_usd: f64,
}

impl ServerCapitalBreakdown {
    pub fn total_usd(&self) -> f64 {
        self.silicon_usd
            + self.package_usd
            + self.memory_usd
            + self.board_usd
            + self.host_usd
            + self.network_usd
            + self.rack_usd
            + self.nre_usd
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct LevelizedCostRates {
    pub hardware_usd_per_active_hour: f64,
    pub host_usd_per_active_hour: f64,
    pub network_rack_usd_per_active_hour: f64,
    pub nre_usd_per_active_hour: f64,
    pub provider_usd_per_active_hour: f64,
    pub electricity_usd_per_kwh: f64,
    pub power_usage_effectiveness: f64,
}

impl CostModel {
    pub fn known_hourly_from_spec(hardware: &HardwareSpec, economics: &EconomicsSpec) -> Self {
        Self::KnownHourly(KnownHourlyCost {
            hardware_usd_per_hour: hardware.accelerator_hourly_cost_usd,
            host_usd_per_hour: hardware.host_hourly_cost_usd,
            network_rack_usd_per_hour: 0.0,
            provider_usd_per_hour: economics.provider_overhead_usd_per_hour.unwrap_or(0.0),
            electricity_usd_per_kwh: economics.electricity_usd_per_kwh,
            power_usage_effectiveness: economics.power_usage_effectiveness,
        })
    }

    pub fn custom_silicon_from_spec(
        hardware: &HardwareSpec,
        economics: &EconomicsSpec,
        server: ServerTcoInputs,
    ) -> Result<Self, EconomicsError> {
        if server.accelerators_per_server == 0 {
            return Err(EconomicsError::InvalidCount("accelerators_per_server"));
        }
        let design = hardware
            .design
            .as_ref()
            .ok_or(EconomicsError::MissingHardwareDesign)?;
        validate_fraction_exclusive_zero(
            "hardware.design.manufacturing.package_yield",
            design.manufacturing.package_yield,
        )?;
        let combined_die_and_package_yield =
            design.manufacturing.die_yield * design.manufacturing.package_yield;
        let amortization_servers = design
            .manufacturing
            .amortization_units
            .div_ceil(u64::from(server.accelerators_per_server));
        let model = Self::CustomSilicon(CustomSiliconTco {
            silicon: SiliconCostInputs {
                wafer_cost_usd: design.process.wafer_cost_usd,
                wafer_diameter_mm: design.process.wafer_diameter_millimeters,
                die_area_mm2: design.die.area_square_millimeters,
                die_yield: combined_die_and_package_yield,
                dies_per_accelerator: design.die.die_count,
            },
            accelerators_per_server: server.accelerators_per_server,
            package_usd_per_accelerator: (design.package.package_cost_usd
                + design.manufacturing.assembly_cost_usd
                + design.manufacturing.test_cost_usd)
                / design.manufacturing.package_yield,
            memory_usd_per_accelerator: server.memory_usd_per_accelerator
                / design.manufacturing.package_yield,
            board_usd_per_server: server.board_usd_per_server,
            host_usd_per_server: server.host_usd_per_server,
            network_usd_per_server: server.network_usd_per_server,
            rack_usd_per_server: server.rack_usd_per_server,
            nre_usd: design.manufacturing.non_recurring_engineering_cost_usd,
            nre_amortization_servers: amortization_servers,
            lifetime_hours: server.lifetime_hours,
            target_utilization: server.target_utilization,
            provider_usd_per_active_hour: economics.provider_overhead_usd_per_hour.unwrap_or(0.0),
            electricity_usd_per_kwh: economics.electricity_usd_per_kwh,
            power_usage_effectiveness: economics.power_usage_effectiveness,
        });
        model.levelized_rates()?;
        Ok(model)
    }

    pub fn server_capital_breakdown(
        &self,
    ) -> Result<Option<ServerCapitalBreakdown>, EconomicsError> {
        match self {
            Self::KnownHourly(cost) => {
                cost.validate()?;
                Ok(None)
            }
            Self::CustomSilicon(cost) => Ok(Some(cost.server_capital_breakdown()?)),
        }
    }

    pub fn levelized_rates(&self) -> Result<LevelizedCostRates, EconomicsError> {
        match self {
            Self::KnownHourly(cost) => cost.levelized_rates(),
            Self::CustomSilicon(cost) => cost.levelized_rates(),
        }
    }
}

impl KnownHourlyCost {
    fn validate(&self) -> Result<(), EconomicsError> {
        validate_non_negative("hardware_usd_per_hour", self.hardware_usd_per_hour)?;
        validate_non_negative("host_usd_per_hour", self.host_usd_per_hour)?;
        validate_non_negative("network_rack_usd_per_hour", self.network_rack_usd_per_hour)?;
        validate_non_negative("provider_usd_per_hour", self.provider_usd_per_hour)?;
        validate_non_negative("electricity_usd_per_kwh", self.electricity_usd_per_kwh)?;
        validate_at_least_one("power_usage_effectiveness", self.power_usage_effectiveness)
    }

    fn levelized_rates(&self) -> Result<LevelizedCostRates, EconomicsError> {
        self.validate()?;
        Ok(LevelizedCostRates {
            hardware_usd_per_active_hour: self.hardware_usd_per_hour,
            host_usd_per_active_hour: self.host_usd_per_hour,
            network_rack_usd_per_active_hour: self.network_rack_usd_per_hour,
            nre_usd_per_active_hour: 0.0,
            provider_usd_per_active_hour: self.provider_usd_per_hour,
            electricity_usd_per_kwh: self.electricity_usd_per_kwh,
            power_usage_effectiveness: self.power_usage_effectiveness,
        })
    }
}

impl CustomSiliconTco {
    fn validate(&self) -> Result<(), EconomicsError> {
        self.silicon.known_good_die_cost_usd()?;
        if self.accelerators_per_server == 0 {
            return Err(EconomicsError::InvalidCount("accelerators_per_server"));
        }
        if self.nre_amortization_servers == 0 {
            return Err(EconomicsError::InvalidCount("nre_amortization_servers"));
        }
        validate_non_negative(
            "package_usd_per_accelerator",
            self.package_usd_per_accelerator,
        )?;
        validate_non_negative(
            "memory_usd_per_accelerator",
            self.memory_usd_per_accelerator,
        )?;
        validate_non_negative("board_usd_per_server", self.board_usd_per_server)?;
        validate_non_negative("host_usd_per_server", self.host_usd_per_server)?;
        validate_non_negative("network_usd_per_server", self.network_usd_per_server)?;
        validate_non_negative("rack_usd_per_server", self.rack_usd_per_server)?;
        validate_non_negative("nre_usd", self.nre_usd)?;
        validate_positive("lifetime_hours", self.lifetime_hours)?;
        validate_fraction_exclusive_zero("target_utilization", self.target_utilization)?;
        validate_non_negative(
            "provider_usd_per_active_hour",
            self.provider_usd_per_active_hour,
        )?;
        validate_non_negative("electricity_usd_per_kwh", self.electricity_usd_per_kwh)?;
        validate_at_least_one("power_usage_effectiveness", self.power_usage_effectiveness)
    }

    fn server_capital_breakdown(&self) -> Result<ServerCapitalBreakdown, EconomicsError> {
        self.validate()?;
        let accelerators = f64::from(self.accelerators_per_server);
        Ok(ServerCapitalBreakdown {
            silicon_usd: self.silicon.known_good_die_cost_usd()?
                * f64::from(self.silicon.dies_per_accelerator)
                * accelerators,
            package_usd: self.package_usd_per_accelerator * accelerators,
            memory_usd: self.memory_usd_per_accelerator * accelerators,
            board_usd: self.board_usd_per_server,
            host_usd: self.host_usd_per_server,
            network_usd: self.network_usd_per_server,
            rack_usd: self.rack_usd_per_server,
            nre_usd: self.nre_usd / self.nre_amortization_servers as f64,
        })
    }

    fn levelized_rates(&self) -> Result<LevelizedCostRates, EconomicsError> {
        let capital = self.server_capital_breakdown()?;
        let active_lifetime_hours = self.lifetime_hours * self.target_utilization;
        Ok(LevelizedCostRates {
            hardware_usd_per_active_hour: (capital.silicon_usd
                + capital.package_usd
                + capital.memory_usd
                + capital.board_usd)
                / active_lifetime_hours,
            host_usd_per_active_hour: capital.host_usd / active_lifetime_hours,
            network_rack_usd_per_active_hour: (capital.network_usd + capital.rack_usd)
                / active_lifetime_hours,
            nre_usd_per_active_hour: capital.nre_usd / active_lifetime_hours,
            provider_usd_per_active_hour: self.provider_usd_per_active_hour,
            electricity_usd_per_kwh: self.electricity_usd_per_kwh,
            power_usage_effectiveness: self.power_usage_effectiveness,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct PhaseActivity {
    pub tokens: u64,
    pub accelerator_seconds: f64,
    pub host_seconds: f64,
    pub provider_seconds: f64,
    pub energy_joules: f64,
}

impl PhaseActivity {
    pub fn uniform(tokens: u64, busy_seconds: f64, energy_joules: f64) -> Self {
        Self {
            tokens,
            accelerator_seconds: busy_seconds,
            host_seconds: busy_seconds,
            provider_seconds: busy_seconds,
            energy_joules,
        }
    }

    fn validate(&self, phase: &'static str) -> Result<(), EconomicsError> {
        if self.tokens == 0 {
            return Err(EconomicsError::ZeroTokens(phase));
        }
        validate_non_negative("accelerator_seconds", self.accelerator_seconds)?;
        validate_non_negative("host_seconds", self.host_seconds)?;
        validate_non_negative("provider_seconds", self.provider_seconds)?;
        validate_non_negative("energy_joules", self.energy_joules)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct InferenceActivity {
    pub input: PhaseActivity,
    pub output: PhaseActivity,
}

impl InferenceActivity {
    pub fn from_simulation_report(report: &SimulationReport) -> Self {
        let (input_seconds, output_seconds) = allocate_elapsed_seconds(
            report.duration_seconds,
            report.prefill.busy_seconds,
            report.decode.busy_seconds,
        );
        Self {
            input: PhaseActivity::uniform(
                report.input_tokens,
                input_seconds,
                report.prefill.energy_joules,
            ),
            output: PhaseActivity::uniform(
                report.output_tokens,
                output_seconds,
                report.decode.energy_joules,
            ),
        }
    }

    pub fn from_phase_results(
        input_tokens: u64,
        output_tokens: u64,
        results: &[PhaseResult],
    ) -> Self {
        let mut input_seconds = 0.0;
        let mut input_energy_joules = 0.0;
        let mut output_seconds = 0.0;
        let mut output_energy_joules = 0.0;
        for result in results {
            match result.phase {
                InferencePhase::Prefill => {
                    input_seconds += result.latency_seconds;
                    input_energy_joules += result.energy_joules;
                }
                InferencePhase::Decode => {
                    output_seconds += result.latency_seconds;
                    output_energy_joules += result.energy_joules;
                }
            }
        }
        Self {
            input: PhaseActivity::uniform(input_tokens, input_seconds, input_energy_joules),
            output: PhaseActivity::uniform(output_tokens, output_seconds, output_energy_joules),
        }
    }
}

fn allocate_elapsed_seconds(
    elapsed_seconds: f64,
    input_busy_seconds: f64,
    output_busy_seconds: f64,
) -> (f64, f64) {
    let total_busy_seconds = input_busy_seconds + output_busy_seconds;
    if total_busy_seconds > 0.0 {
        let input_seconds = elapsed_seconds * input_busy_seconds / total_busy_seconds;
        (input_seconds, elapsed_seconds - input_seconds)
    } else {
        (elapsed_seconds / 2.0, elapsed_seconds / 2.0)
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Serialize, Deserialize)]
pub struct CostBreakdown {
    pub hardware_usd: f64,
    pub host_usd: f64,
    pub network_rack_usd: f64,
    pub nre_usd: f64,
    pub provider_usd: f64,
    pub energy_usd: f64,
}

impl CostBreakdown {
    pub fn total_usd(&self) -> f64 {
        self.hardware_usd
            + self.host_usd
            + self.network_rack_usd
            + self.nre_usd
            + self.provider_usd
            + self.energy_usd
    }

    fn for_activity(rates: &LevelizedCostRates, activity: &PhaseActivity) -> Self {
        let accelerator_hours = activity.accelerator_seconds / SECONDS_PER_HOUR;
        Self {
            hardware_usd: rates.hardware_usd_per_active_hour * accelerator_hours,
            host_usd: rates.host_usd_per_active_hour * activity.host_seconds / SECONDS_PER_HOUR,
            network_rack_usd: rates.network_rack_usd_per_active_hour * accelerator_hours,
            nre_usd: rates.nre_usd_per_active_hour * accelerator_hours,
            provider_usd: rates.provider_usd_per_active_hour * activity.provider_seconds
                / SECONDS_PER_HOUR,
            energy_usd: activity.energy_joules / JOULES_PER_KILOWATT_HOUR
                * rates.power_usage_effectiveness
                * rates.electricity_usd_per_kwh,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct PhaseEconomics {
    pub tokens: u64,
    pub costs: CostBreakdown,
    pub cost_per_million_tokens: f64,
    pub minimum_price_per_million_tokens: f64,
}

impl PhaseEconomics {
    pub fn gross_margin_at_minimum_price(&self) -> f64 {
        if self.minimum_price_per_million_tokens == 0.0 {
            0.0
        } else {
            1.0 - self.cost_per_million_tokens / self.minimum_price_per_million_tokens
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct CostReport {
    pub input: PhaseEconomics,
    pub output: PhaseEconomics,
    pub target_gross_margin: f64,
    pub total_cost_usd: f64,
    pub allocated_cost_usd: f64,
    pub reconciliation_delta_usd: f64,
}

impl CostReport {
    pub fn reconciles(&self, tolerance_usd: f64) -> bool {
        self.reconciliation_delta_usd.abs() <= tolerance_usd
    }
}

pub fn calculate_cost_report(
    model: &CostModel,
    activity: &InferenceActivity,
    target_gross_margin: f64,
) -> Result<CostReport, EconomicsError> {
    validate_gross_margin(target_gross_margin)?;
    activity.input.validate("input")?;
    activity.output.validate("output")?;
    let rates = model.levelized_rates()?;
    let input = phase_economics(&rates, &activity.input, target_gross_margin);
    let output = phase_economics(&rates, &activity.output, target_gross_margin);
    let aggregate = PhaseActivity {
        tokens: activity.input.tokens + activity.output.tokens,
        accelerator_seconds: activity.input.accelerator_seconds
            + activity.output.accelerator_seconds,
        host_seconds: activity.input.host_seconds + activity.output.host_seconds,
        provider_seconds: activity.input.provider_seconds + activity.output.provider_seconds,
        energy_joules: activity.input.energy_joules + activity.output.energy_joules,
    };
    let total_cost_usd = CostBreakdown::for_activity(&rates, &aggregate).total_usd();
    let allocated_cost_usd = input.costs.total_usd() + output.costs.total_usd();
    Ok(CostReport {
        input,
        output,
        target_gross_margin,
        total_cost_usd,
        allocated_cost_usd,
        reconciliation_delta_usd: allocated_cost_usd - total_cost_usd,
    })
}

pub fn calculate_cost_report_from_spec(
    model: &CostModel,
    activity: &InferenceActivity,
    economics: &EconomicsSpec,
) -> Result<CostReport, EconomicsError> {
    calculate_cost_report(model, activity, economics.target_gross_margin)
}

fn phase_economics(
    rates: &LevelizedCostRates,
    activity: &PhaseActivity,
    target_gross_margin: f64,
) -> PhaseEconomics {
    let costs = CostBreakdown::for_activity(rates, activity);
    let cost_per_million_tokens = costs.total_usd() * 1_000_000.0 / activity.tokens as f64;
    PhaseEconomics {
        tokens: activity.tokens,
        costs,
        cost_per_million_tokens,
        minimum_price_per_million_tokens: cost_per_million_tokens / (1.0 - target_gross_margin),
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Error)]
pub enum EconomicsError {
    #[error("{0} must be finite and non-negative, got {1}")]
    InvalidValue(&'static str, f64),
    #[error("{0} must be greater than zero")]
    InvalidCount(&'static str),
    #[error("gross margin must be finite and in [0, 1), got {0}")]
    InvalidGrossMargin(f64),
    #[error("{0} tokens must be greater than zero")]
    ZeroTokens(&'static str),
    #[error("wafer and die geometry produces no gross dies")]
    InvalidSiliconGeometry,
    #[error("detailed hardware design is required for custom silicon TCO")]
    MissingHardwareDesign,
}

fn validate_non_negative(field: &'static str, value: f64) -> Result<(), EconomicsError> {
    if value.is_finite() && value >= 0.0 {
        Ok(())
    } else {
        Err(EconomicsError::InvalidValue(field, value))
    }
}

fn validate_positive(field: &'static str, value: f64) -> Result<(), EconomicsError> {
    if value.is_finite() && value > 0.0 {
        Ok(())
    } else {
        Err(EconomicsError::InvalidValue(field, value))
    }
}

fn validate_fraction_exclusive_zero(field: &'static str, value: f64) -> Result<(), EconomicsError> {
    if value.is_finite() && value > 0.0 && value <= 1.0 {
        Ok(())
    } else {
        Err(EconomicsError::InvalidValue(field, value))
    }
}

fn validate_at_least_one(field: &'static str, value: f64) -> Result<(), EconomicsError> {
    if value.is_finite() && value >= 1.0 {
        Ok(())
    } else {
        Err(EconomicsError::InvalidValue(field, value))
    }
}

fn validate_gross_margin(value: f64) -> Result<(), EconomicsError> {
    if value.is_finite() && (0.0..1.0).contains(&value) {
        Ok(())
    } else {
        Err(EconomicsError::InvalidGrossMargin(value))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn activity() -> InferenceActivity {
        InferenceActivity {
            input: PhaseActivity::uniform(2_000_000, 900.0, 72_000_000.0),
            output: PhaseActivity::uniform(1_000_000, 2_700.0, 216_000_000.0),
        }
    }

    #[test]
    fn allocated_phase_costs_reconcile_to_total_cost() {
        let model = CostModel::KnownHourly(KnownHourlyCost {
            hardware_usd_per_hour: 8.0,
            host_usd_per_hour: 1.0,
            network_rack_usd_per_hour: 0.5,
            provider_usd_per_hour: 0.5,
            electricity_usd_per_kwh: 0.10,
            power_usage_effectiveness: 1.2,
        });

        let report = calculate_cost_report(&model, &activity(), 0.5).unwrap();

        assert!(report.reconciles(1e-12));
        assert!((report.allocated_cost_usd - report.total_cost_usd).abs() < 1e-12);
        assert!(
            (report.input.costs.total_usd() + report.output.costs.total_usd()
                - report.total_cost_usd)
                .abs()
                < 1e-12
        );
    }

    #[test]
    fn minimum_prices_achieve_the_target_gross_margin() {
        let model = CostModel::KnownHourly(KnownHourlyCost {
            hardware_usd_per_hour: 8.0,
            host_usd_per_hour: 1.0,
            network_rack_usd_per_hour: 0.5,
            provider_usd_per_hour: 0.5,
            electricity_usd_per_kwh: 0.10,
            power_usage_effectiveness: 1.2,
        });

        let report = calculate_cost_report(&model, &activity(), 0.6).unwrap();

        assert!(
            (report.input.minimum_price_per_million_tokens
                - report.input.cost_per_million_tokens / 0.4)
                .abs()
                < 1e-12
        );
        assert!(
            (report.output.minimum_price_per_million_tokens
                - report.output.cost_per_million_tokens / 0.4)
                .abs()
                < 1e-12
        );
        assert!((report.input.gross_margin_at_minimum_price() - 0.6).abs() < 1e-12);
        assert!((report.output.gross_margin_at_minimum_price() - 0.6).abs() < 1e-12);
    }

    #[test]
    fn custom_silicon_tco_levelizes_all_server_costs() {
        let model = CostModel::CustomSilicon(CustomSiliconTco {
            silicon: SiliconCostInputs {
                wafer_cost_usd: 20_000.0,
                wafer_diameter_mm: 300.0,
                die_area_mm2: 600.0,
                die_yield: 0.75,
                dies_per_accelerator: 2,
            },
            accelerators_per_server: 8,
            package_usd_per_accelerator: 2_000.0,
            memory_usd_per_accelerator: 8_000.0,
            board_usd_per_server: 10_000.0,
            host_usd_per_server: 15_000.0,
            network_usd_per_server: 20_000.0,
            rack_usd_per_server: 5_000.0,
            nre_usd: 100_000_000.0,
            nre_amortization_servers: 10_000,
            lifetime_hours: 26_280.0,
            target_utilization: 0.70,
            provider_usd_per_active_hour: 0.25,
            electricity_usd_per_kwh: 0.10,
            power_usage_effectiveness: 1.2,
        });

        let rates = model.levelized_rates().unwrap();
        let capital = model.server_capital_breakdown().unwrap().unwrap();

        assert!(capital.silicon_usd > 0.0);
        assert_eq!(capital.package_usd, 16_000.0);
        assert_eq!(capital.memory_usd, 64_000.0);
        assert_eq!(capital.nre_usd, 10_000.0);
        assert!(rates.hardware_usd_per_active_hour > 0.0);
        assert!(rates.host_usd_per_active_hour > 0.0);
        assert!(rates.network_rack_usd_per_active_hour > 0.0);
        assert!(rates.nre_usd_per_active_hour > 0.0);
    }

    #[test]
    fn rejects_an_invalid_gross_margin() {
        let model = CostModel::KnownHourly(KnownHourlyCost {
            hardware_usd_per_hour: 1.0,
            host_usd_per_hour: 0.0,
            network_rack_usd_per_hour: 0.0,
            provider_usd_per_hour: 0.0,
            electricity_usd_per_kwh: 0.0,
            power_usage_effectiveness: 1.0,
        });

        let error = calculate_cost_report(&model, &activity(), 1.0).unwrap_err();

        assert_eq!(error, EconomicsError::InvalidGrossMargin(1.0));
    }

    #[test]
    fn wall_clock_cost_is_allocated_across_input_and_output_activity() {
        let (input, output) = allocate_elapsed_seconds(1_000.0, 100.0, 300.0);

        assert_eq!(input, 250.0);
        assert_eq!(output, 750.0);
        assert_eq!(input + output, 1_000.0);
    }
}
