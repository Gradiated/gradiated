use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::codesign::{QualityGate, QualityTarget, QualityVariantContext};
use crate::economics::{LevelizedCostRates, ServerCapitalBreakdown};
use crate::performance::OracleFidelity;
use crate::sizing::SizingSource;
use crate::study::CoDesignStudyReport;

const SECONDS_PER_HOUR: f64 = 3_600.0;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceKind {
    Measured,
    VendorQuote,
    FoundryModel,
    PublicPricing,
    Contract,
    InternalEstimate,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct AssumptionProvenance {
    pub kind: EvidenceKind,
    pub source: String,
    pub artifact: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ValueRange {
    pub lower: f64,
    pub nominal: f64,
    pub upper: f64,
    pub provenance: AssumptionProvenance,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct CountRange {
    pub lower: u64,
    pub nominal: u64,
    pub upper: u64,
    pub provenance: AssumptionProvenance,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct CustomSiliconSensitivity {
    pub nre_amortization_units: CountRange,
    pub utilization: ValueRange,
    pub hbm_stack_cost_usd: ValueRange,
    pub wafer_cost_usd: ValueRange,
    pub effective_silicon_yield: ValueRange,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct KnownHourlySensitivity {
    pub fleet_hardware_usd_per_hour: ValueRange,
    pub host_usd_per_hour: ValueRange,
    pub network_rack_usd_per_hour: ValueRange,
    pub provider_overhead_usd_per_hour: ValueRange,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(tag = "cost_basis", content = "ranges", rename_all = "snake_case")]
pub enum SensitivityAssumptions {
    CustomSilicon(CustomSiliconSensitivity),
    KnownHourly(KnownHourlySensitivity),
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ProviderBaseline {
    pub name: String,
    pub input_usd_per_million_tokens: f64,
    pub output_usd_per_million_tokens: f64,
    pub provenance: AssumptionProvenance,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct SensitivityRequest {
    pub assumptions: SensitivityAssumptions,
    pub provider_baseline: ProviderBaseline,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TimingSource {
    ReusedCoDesignStudySelection,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct FixedTimingBasis {
    pub source: TimingSource,
    pub experiment_spec_id: String,
    pub oracle_fidelity: OracleFidelity,
    pub simulation_duration_seconds: f64,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub data_parallel_replicas: u32,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(tag = "cost_basis", rename_all = "snake_case")]
pub enum ScenarioAssumptions {
    CustomSilicon {
        nre_amortization_units: u64,
        utilization: f64,
        hbm_stack_cost_usd: f64,
        wafer_cost_usd: f64,
        effective_silicon_yield: f64,
    },
    KnownHourly {
        fleet_hardware_usd_per_hour: f64,
        host_usd_per_hour: f64,
        network_rack_usd_per_hour: f64,
        provider_overhead_usd_per_hour: f64,
    },
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct SensitivityScenario {
    pub assumptions: ScenarioAssumptions,
    pub input_cost_per_million_tokens: f64,
    pub output_cost_per_million_tokens: f64,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct PhaseCostRange {
    pub lower: f64,
    pub nominal: f64,
    pub upper: f64,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BreakEvenStatus {
    AllScenarios,
    SomeScenarios,
    NoScenarios,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub struct BreakEvenAssessment {
    pub provider_price_per_million_tokens: f64,
    pub status: BreakEvenStatus,
    pub scenarios_at_or_below_baseline: usize,
    pub scenario_count: usize,
    pub worst_case_advantage_fraction: f64,
    pub best_case_advantage_fraction: f64,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ConclusionBlocker {
    QualityUnmeasured,
    QualityContractFailed,
    QualityEvidenceScopeMismatch,
    QualityEvidenceInvalid,
    PerformanceFidelityNotExternal,
    HardwareSizingNotValidated,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct EconomicConclusionGate {
    pub permitted: bool,
    pub blockers: Vec<ConclusionBlocker>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct EconomicSensitivityReport {
    pub study_baseline_spec_id: String,
    pub timing_basis: FixedTimingBasis,
    pub assumptions: SensitivityAssumptions,
    pub provider_baseline: ProviderBaseline,
    pub scenarios: Vec<SensitivityScenario>,
    pub input_cost_per_million_tokens: PhaseCostRange,
    pub output_cost_per_million_tokens: PhaseCostRange,
    pub input_break_even: BreakEvenAssessment,
    pub output_break_even: BreakEvenAssessment,
    pub conclusion_gate: EconomicConclusionGate,
}

pub fn analyze_codesign_sensitivity(
    study: &CoDesignStudyReport,
    request: &SensitivityRequest,
) -> Result<EconomicSensitivityReport, SensitivityError> {
    let selected = study
        .capacity
        .selected
        .as_ref()
        .ok_or(SensitivityError::NoSloCompliantSelection)?;
    validate_study(study)?;
    validate_provider_baseline(&request.provider_baseline)?;
    let activity = FixedActivity::from_study(study)?;
    let scenarios = match &request.assumptions {
        SensitivityAssumptions::CustomSilicon(assumptions) => {
            custom_silicon_scenarios(study, assumptions, &activity)?
        }
        SensitivityAssumptions::KnownHourly(assumptions) => {
            known_hourly_scenarios(study, assumptions, &activity)?
        }
    };
    let nominal = nominal_scenario(&scenarios, &request.assumptions)
        .ok_or(SensitivityError::NominalScenarioMissing)?;
    validate_nominal(
        "nominal.input_cost_per_million_tokens",
        nominal.input_cost_per_million_tokens,
        selected.costs.input.cost_per_million_tokens,
    )?;
    validate_nominal(
        "nominal.output_cost_per_million_tokens",
        nominal.output_cost_per_million_tokens,
        selected.costs.output.cost_per_million_tokens,
    )?;
    let input_cost_per_million_tokens = phase_range(
        &scenarios,
        nominal.input_cost_per_million_tokens,
        |scenario| scenario.input_cost_per_million_tokens,
    )?;
    let output_cost_per_million_tokens = phase_range(
        &scenarios,
        nominal.output_cost_per_million_tokens,
        |scenario| scenario.output_cost_per_million_tokens,
    )?;
    let input_break_even = break_even(
        &scenarios,
        input_cost_per_million_tokens,
        request.provider_baseline.input_usd_per_million_tokens,
        |scenario| scenario.input_cost_per_million_tokens,
    );
    let output_break_even = break_even(
        &scenarios,
        output_cost_per_million_tokens,
        request.provider_baseline.output_usd_per_million_tokens,
        |scenario| scenario.output_cost_per_million_tokens,
    );
    Ok(EconomicSensitivityReport {
        study_baseline_spec_id: study.baseline_spec_id.clone(),
        timing_basis: FixedTimingBasis {
            source: TimingSource::ReusedCoDesignStudySelection,
            experiment_spec_id: selected.spec_id.clone(),
            oracle_fidelity: selected.oracle_fidelity,
            simulation_duration_seconds: selected.simulation.duration_seconds,
            input_tokens: selected.costs.input.tokens,
            output_tokens: selected.costs.output.tokens,
            data_parallel_replicas: selected.data_parallel_replicas,
        },
        assumptions: request.assumptions.clone(),
        provider_baseline: request.provider_baseline.clone(),
        scenarios,
        input_cost_per_million_tokens,
        output_cost_per_million_tokens,
        input_break_even,
        output_break_even,
        conclusion_gate: conclusion_gate(study, selected.oracle_fidelity),
    })
}

#[derive(Clone, Copy)]
struct FixedActivity {
    input_seconds: f64,
    output_seconds: f64,
    input_tokens: u64,
    output_tokens: u64,
    input_energy_usd: f64,
    output_energy_usd: f64,
}

impl FixedActivity {
    fn from_study(study: &CoDesignStudyReport) -> Result<Self, SensitivityError> {
        let selected = study
            .capacity
            .selected
            .as_ref()
            .ok_or(SensitivityError::NoSloCompliantSelection)?;
        let simulation = &selected.simulation;
        for (field, value) in [
            ("simulation.duration_seconds", simulation.duration_seconds),
            (
                "simulation.prefill.busy_seconds",
                simulation.prefill.busy_seconds,
            ),
            (
                "simulation.decode.busy_seconds",
                simulation.decode.busy_seconds,
            ),
        ] {
            if !value.is_finite() || value < 0.0 {
                return Err(SensitivityError::InvalidTimingBasis(field));
            }
        }
        if simulation.duration_seconds == 0.0 {
            return Err(SensitivityError::InvalidTimingBasis(
                "simulation.duration_seconds",
            ));
        }
        if selected.costs.input.tokens == 0 || selected.costs.output.tokens == 0 {
            return Err(SensitivityError::InvalidTimingBasis("phase.tokens"));
        }
        let total_busy_seconds = simulation.prefill.busy_seconds + simulation.decode.busy_seconds;
        if !total_busy_seconds.is_finite() {
            return Err(SensitivityError::InvalidTimingBasis(
                "simulation.total_busy_seconds",
            ));
        }
        let input_seconds = if total_busy_seconds > 0.0 {
            simulation.duration_seconds * simulation.prefill.busy_seconds / total_busy_seconds
        } else {
            simulation.duration_seconds / 2.0
        };
        let output_seconds = simulation.duration_seconds - input_seconds;
        let input_energy_usd = selected.costs.input.costs.energy_usd;
        let output_energy_usd = selected.costs.output.costs.energy_usd;
        if !input_energy_usd.is_finite()
            || input_energy_usd < 0.0
            || !output_energy_usd.is_finite()
            || output_energy_usd < 0.0
        {
            return Err(SensitivityError::InvalidCostBasis);
        }
        Ok(Self {
            input_seconds,
            output_seconds,
            input_tokens: selected.costs.input.tokens,
            output_tokens: selected.costs.output.tokens,
            input_energy_usd,
            output_energy_usd,
        })
    }

    fn costs(&self, rates: ScenarioRates) -> Result<(f64, f64), SensitivityError> {
        let hourly = rates.total();
        if !hourly.is_finite() || hourly < 0.0 {
            return Err(SensitivityError::InvalidCostBasis);
        }
        let input = (hourly * self.input_seconds / SECONDS_PER_HOUR + self.input_energy_usd)
            * 1_000_000.0
            / self.input_tokens as f64;
        let output = (hourly * self.output_seconds / SECONDS_PER_HOUR + self.output_energy_usd)
            * 1_000_000.0
            / self.output_tokens as f64;
        if !input.is_finite() || input < 0.0 || !output.is_finite() || output < 0.0 {
            return Err(SensitivityError::InvalidCostBasis);
        }
        Ok((input, output))
    }
}

#[derive(Clone, Copy)]
struct ScenarioRates {
    hardware: f64,
    host: f64,
    network_rack: f64,
    nre: f64,
    provider: f64,
}

impl ScenarioRates {
    fn total(self) -> f64 {
        self.hardware + self.host + self.network_rack + self.nre + self.provider
    }
}

fn custom_silicon_scenarios(
    study: &CoDesignStudyReport,
    assumptions: &CustomSiliconSensitivity,
    activity: &FixedActivity,
) -> Result<Vec<SensitivityScenario>, SensitivityError> {
    validate_custom_assumptions(study, assumptions)?;
    let selected = study
        .capacity
        .selected
        .as_ref()
        .ok_or(SensitivityError::NoSloCompliantSelection)?;
    let capital = selected
        .server_capital
        .as_ref()
        .ok_or(SensitivityError::CostModelMismatch {
            expected: "custom_silicon",
        })?;
    let hardware_capital = hardware_capital(capital)?;
    let base_rates = selected.levelized_cost_rates;
    let accelerators_per_server = u64::from(selected.data_parallel_replicas);
    let nominal_servers = assumptions
        .nre_amortization_units
        .nominal
        .div_ceil(accelerators_per_server);
    let mut scenarios = Vec::new();
    for nre_units in assumptions.nre_amortization_units.values() {
        let scenario_servers = nre_units.div_ceil(accelerators_per_server);
        let nre_scale = nominal_servers as f64 / scenario_servers as f64;
        for utilization in assumptions.utilization.values() {
            let utilization_scale = assumptions.utilization.nominal / utilization;
            for hbm_cost in assumptions.hbm_stack_cost_usd.values() {
                let hbm_scale = hbm_cost / assumptions.hbm_stack_cost_usd.nominal;
                for wafer_cost in assumptions.wafer_cost_usd.values() {
                    for silicon_yield in assumptions.effective_silicon_yield.values() {
                        let silicon_scale = wafer_cost / assumptions.wafer_cost_usd.nominal
                            * assumptions.effective_silicon_yield.nominal
                            / silicon_yield;
                        let scenario_hardware_capital = capital.silicon_usd * silicon_scale
                            + capital.package_usd
                            + capital.memory_usd * hbm_scale
                            + capital.board_usd;
                        let rates = ScenarioRates {
                            hardware: base_rates.hardware_usd_per_active_hour
                                * scenario_hardware_capital
                                / hardware_capital
                                * utilization_scale,
                            host: base_rates.host_usd_per_active_hour * utilization_scale,
                            network_rack: base_rates.network_rack_usd_per_active_hour
                                * utilization_scale,
                            nre: base_rates.nre_usd_per_active_hour * nre_scale * utilization_scale,
                            provider: base_rates.provider_usd_per_active_hour,
                        };
                        let (input, output) = activity.costs(rates)?;
                        scenarios.push(SensitivityScenario {
                            assumptions: ScenarioAssumptions::CustomSilicon {
                                nre_amortization_units: nre_units,
                                utilization,
                                hbm_stack_cost_usd: hbm_cost,
                                wafer_cost_usd: wafer_cost,
                                effective_silicon_yield: silicon_yield,
                            },
                            input_cost_per_million_tokens: input,
                            output_cost_per_million_tokens: output,
                        });
                    }
                }
            }
        }
    }
    Ok(scenarios)
}

fn known_hourly_scenarios(
    study: &CoDesignStudyReport,
    assumptions: &KnownHourlySensitivity,
    activity: &FixedActivity,
) -> Result<Vec<SensitivityScenario>, SensitivityError> {
    validate_known_hourly_assumptions(study, assumptions)?;
    let mut scenarios = Vec::new();
    for hardware in assumptions.fleet_hardware_usd_per_hour.values() {
        for host in assumptions.host_usd_per_hour.values() {
            for network in assumptions.network_rack_usd_per_hour.values() {
                for provider in assumptions.provider_overhead_usd_per_hour.values() {
                    let (input, output) = activity.costs(ScenarioRates {
                        hardware,
                        host,
                        network_rack: network,
                        nre: 0.0,
                        provider,
                    })?;
                    scenarios.push(SensitivityScenario {
                        assumptions: ScenarioAssumptions::KnownHourly {
                            fleet_hardware_usd_per_hour: hardware,
                            host_usd_per_hour: host,
                            network_rack_usd_per_hour: network,
                            provider_overhead_usd_per_hour: provider,
                        },
                        input_cost_per_million_tokens: input,
                        output_cost_per_million_tokens: output,
                    });
                }
            }
        }
    }
    Ok(scenarios)
}

fn validate_custom_assumptions(
    study: &CoDesignStudyReport,
    assumptions: &CustomSiliconSensitivity,
) -> Result<(), SensitivityError> {
    assumptions
        .nre_amortization_units
        .validate("custom_silicon.nre_amortization_units")?;
    assumptions
        .utilization
        .validate_fraction("custom_silicon.utilization")?;
    assumptions
        .hbm_stack_cost_usd
        .validate_positive("custom_silicon.hbm_stack_cost_usd")?;
    assumptions
        .wafer_cost_usd
        .validate_positive("custom_silicon.wafer_cost_usd")?;
    assumptions
        .effective_silicon_yield
        .validate_fraction("custom_silicon.effective_silicon_yield")?;
    let selected = study
        .capacity
        .selected
        .as_ref()
        .ok_or(SensitivityError::NoSloCompliantSelection)?;
    let capital = selected
        .server_capital
        .as_ref()
        .ok_or(SensitivityError::CostModelMismatch {
            expected: "custom_silicon",
        })?;
    hardware_capital(capital)?;
    let design = study
        .candidate_spec
        .hardware
        .design
        .as_ref()
        .ok_or(SensitivityError::MissingHardwareDesign)?;
    if assumptions.nre_amortization_units.nominal != design.manufacturing.amortization_units {
        return Err(SensitivityError::NominalCountMismatch {
            field: "custom_silicon.nre_amortization_units",
            expected: design.manufacturing.amortization_units,
            actual: assumptions.nre_amortization_units.nominal,
        });
    }
    validate_nominal(
        "custom_silicon.wafer_cost_usd",
        assumptions.wafer_cost_usd.nominal,
        design.process.wafer_cost_usd,
    )?;
    validate_nominal(
        "custom_silicon.effective_silicon_yield",
        assumptions.effective_silicon_yield.nominal,
        design.manufacturing.die_yield * design.manufacturing.package_yield,
    )?;
    let total_stacks = study
        .hardware_sizing
        .mapping
        .device_count
        .checked_mul(study.hardware_sizing.mapping.hbm_stacks_per_device)
        .ok_or(SensitivityError::HardwareCountOverflow)?;
    if total_stacks == 0 {
        return Err(SensitivityError::InvalidCostBasis);
    }
    let reference_hbm_stack_cost = study.hardware_sizing.cost.hbm_cost_usd
        * design.manufacturing.package_yield
        / f64::from(total_stacks);
    validate_nominal(
        "custom_silicon.hbm_stack_cost_usd",
        assumptions.hbm_stack_cost_usd.nominal,
        reference_hbm_stack_cost,
    )
}

fn validate_known_hourly_assumptions(
    study: &CoDesignStudyReport,
    assumptions: &KnownHourlySensitivity,
) -> Result<(), SensitivityError> {
    let selected = study
        .capacity
        .selected
        .as_ref()
        .ok_or(SensitivityError::NoSloCompliantSelection)?;
    if selected.server_capital.is_some() {
        return Err(SensitivityError::CostModelMismatch {
            expected: "known_hourly",
        });
    }
    for (field, range) in [
        (
            "known_hourly.fleet_hardware_usd_per_hour",
            &assumptions.fleet_hardware_usd_per_hour,
        ),
        (
            "known_hourly.host_usd_per_hour",
            &assumptions.host_usd_per_hour,
        ),
        (
            "known_hourly.network_rack_usd_per_hour",
            &assumptions.network_rack_usd_per_hour,
        ),
        (
            "known_hourly.provider_overhead_usd_per_hour",
            &assumptions.provider_overhead_usd_per_hour,
        ),
    ] {
        range.validate_non_negative(field)?;
    }
    let rates = selected.levelized_cost_rates;
    for (field, actual, expected) in [
        (
            "known_hourly.fleet_hardware_usd_per_hour",
            assumptions.fleet_hardware_usd_per_hour.nominal,
            rates.hardware_usd_per_active_hour,
        ),
        (
            "known_hourly.host_usd_per_hour",
            assumptions.host_usd_per_hour.nominal,
            rates.host_usd_per_active_hour,
        ),
        (
            "known_hourly.network_rack_usd_per_hour",
            assumptions.network_rack_usd_per_hour.nominal,
            rates.network_rack_usd_per_active_hour,
        ),
        (
            "known_hourly.provider_overhead_usd_per_hour",
            assumptions.provider_overhead_usd_per_hour.nominal,
            rates.provider_usd_per_active_hour,
        ),
    ] {
        validate_nominal(field, actual, expected)?;
    }
    Ok(())
}

impl ValueRange {
    fn validate_non_negative(&self, field: &'static str) -> Result<(), SensitivityError> {
        self.validate_order(field)?;
        if self.lower < 0.0 {
            return Err(SensitivityError::InvalidRange(field));
        }
        Ok(())
    }

    fn validate_fraction(&self, field: &'static str) -> Result<(), SensitivityError> {
        self.validate_order(field)?;
        if self.lower <= 0.0 || self.upper > 1.0 {
            return Err(SensitivityError::InvalidRange(field));
        }
        Ok(())
    }

    fn validate_positive(&self, field: &'static str) -> Result<(), SensitivityError> {
        self.validate_order(field)?;
        if self.lower <= 0.0 {
            return Err(SensitivityError::InvalidRange(field));
        }
        Ok(())
    }

    fn validate_order(&self, field: &'static str) -> Result<(), SensitivityError> {
        if !self.lower.is_finite()
            || !self.nominal.is_finite()
            || !self.upper.is_finite()
            || self.lower > self.nominal
            || self.nominal > self.upper
        {
            return Err(SensitivityError::InvalidRange(field));
        }
        self.provenance.validate(field)
    }

    fn values(&self) -> Vec<f64> {
        unique_values([self.lower, self.nominal, self.upper])
    }
}

impl CountRange {
    fn validate(&self, field: &'static str) -> Result<(), SensitivityError> {
        if self.lower == 0 || self.lower > self.nominal || self.nominal > self.upper {
            return Err(SensitivityError::InvalidCountRange(field));
        }
        self.provenance.validate(field)
    }

    fn values(&self) -> Vec<u64> {
        let mut values = vec![self.lower];
        if self.nominal != self.lower {
            values.push(self.nominal);
        }
        if self.upper != self.nominal {
            values.push(self.upper);
        }
        values
    }
}

impl AssumptionProvenance {
    fn validate(&self, field: &'static str) -> Result<(), SensitivityError> {
        if self.source.trim().is_empty() || self.artifact.trim().is_empty() {
            Err(SensitivityError::InvalidProvenance(field))
        } else {
            Ok(())
        }
    }
}

fn validate_provider_baseline(baseline: &ProviderBaseline) -> Result<(), SensitivityError> {
    if baseline.name.trim().is_empty()
        || !baseline.input_usd_per_million_tokens.is_finite()
        || baseline.input_usd_per_million_tokens <= 0.0
        || !baseline.output_usd_per_million_tokens.is_finite()
        || baseline.output_usd_per_million_tokens <= 0.0
    {
        return Err(SensitivityError::InvalidProviderBaseline);
    }
    baseline.provenance.validate("provider_baseline")
}

fn validate_study(study: &CoDesignStudyReport) -> Result<(), SensitivityError> {
    let selected = study
        .capacity
        .selected
        .as_ref()
        .ok_or(SensitivityError::NoSloCompliantSelection)?;
    if study.baseline_spec_id.trim().is_empty() || selected.spec_id.trim().is_empty() {
        return Err(SensitivityError::InvalidStudyProvenance);
    }
    if selected.data_parallel_replicas == 0 {
        return Err(SensitivityError::InvalidTimingBasis(
            "data_parallel_replicas",
        ));
    }
    if study.quality != selected.quality {
        return Err(SensitivityError::QualityEvidenceMismatch);
    }
    let expected_target = expected_quality_target(study)?;
    if study.quality_target != expected_target || selected.quality_target != expected_target {
        return Err(SensitivityError::QualityTargetMismatch);
    }
    for value in [
        selected.costs.input.cost_per_million_tokens,
        selected.costs.output.cost_per_million_tokens,
    ] {
        if !value.is_finite() || value < 0.0 {
            return Err(SensitivityError::InvalidCostBasis);
        }
    }
    validate_rates(selected.levelized_cost_rates)
}

fn validate_rates(rates: LevelizedCostRates) -> Result<(), SensitivityError> {
    for value in [
        rates.hardware_usd_per_active_hour,
        rates.host_usd_per_active_hour,
        rates.network_rack_usd_per_active_hour,
        rates.nre_usd_per_active_hour,
        rates.provider_usd_per_active_hour,
        rates.electricity_usd_per_kwh,
        rates.power_usage_effectiveness,
    ] {
        if !value.is_finite() || value < 0.0 {
            return Err(SensitivityError::InvalidCostBasis);
        }
    }
    Ok(())
}

fn hardware_capital(capital: &ServerCapitalBreakdown) -> Result<f64, SensitivityError> {
    let components = [
        capital.silicon_usd,
        capital.package_usd,
        capital.memory_usd,
        capital.board_usd,
    ];
    if components
        .iter()
        .any(|value| !value.is_finite() || *value < 0.0)
    {
        return Err(SensitivityError::InvalidCostBasis);
    }
    let total = components.into_iter().sum::<f64>();
    if total <= 0.0 || !total.is_finite() {
        Err(SensitivityError::InvalidCostBasis)
    } else {
        Ok(total)
    }
}

fn validate_nominal(
    field: &'static str,
    actual: f64,
    expected: f64,
) -> Result<(), SensitivityError> {
    let tolerance = expected.abs().max(1.0) * 1e-9;
    if (actual - expected).abs() > tolerance {
        Err(SensitivityError::NominalValueMismatch {
            field,
            expected,
            actual,
        })
    } else {
        Ok(())
    }
}

fn unique_values(values: [f64; 3]) -> Vec<f64> {
    let mut unique = vec![values[0]];
    for value in values.into_iter().skip(1) {
        if unique.last().copied() != Some(value) {
            unique.push(value);
        }
    }
    unique
}

fn nominal_scenario<'a>(
    scenarios: &'a [SensitivityScenario],
    assumptions: &SensitivityAssumptions,
) -> Option<&'a SensitivityScenario> {
    scenarios
        .iter()
        .find(|scenario| match (assumptions, &scenario.assumptions) {
            (
                SensitivityAssumptions::CustomSilicon(ranges),
                ScenarioAssumptions::CustomSilicon {
                    nre_amortization_units,
                    utilization,
                    hbm_stack_cost_usd,
                    wafer_cost_usd,
                    effective_silicon_yield,
                },
            ) => {
                *nre_amortization_units == ranges.nre_amortization_units.nominal
                    && *utilization == ranges.utilization.nominal
                    && *hbm_stack_cost_usd == ranges.hbm_stack_cost_usd.nominal
                    && *wafer_cost_usd == ranges.wafer_cost_usd.nominal
                    && *effective_silicon_yield == ranges.effective_silicon_yield.nominal
            }
            (
                SensitivityAssumptions::KnownHourly(ranges),
                ScenarioAssumptions::KnownHourly {
                    fleet_hardware_usd_per_hour,
                    host_usd_per_hour,
                    network_rack_usd_per_hour,
                    provider_overhead_usd_per_hour,
                },
            ) => {
                *fleet_hardware_usd_per_hour == ranges.fleet_hardware_usd_per_hour.nominal
                    && *host_usd_per_hour == ranges.host_usd_per_hour.nominal
                    && *network_rack_usd_per_hour == ranges.network_rack_usd_per_hour.nominal
                    && *provider_overhead_usd_per_hour
                        == ranges.provider_overhead_usd_per_hour.nominal
            }
            _ => false,
        })
}

fn phase_range(
    scenarios: &[SensitivityScenario],
    nominal: f64,
    value: impl Fn(&SensitivityScenario) -> f64,
) -> Result<PhaseCostRange, SensitivityError> {
    let lower = scenarios
        .iter()
        .map(&value)
        .min_by(f64::total_cmp)
        .ok_or(SensitivityError::NominalScenarioMissing)?;
    let upper = scenarios
        .iter()
        .map(value)
        .max_by(f64::total_cmp)
        .ok_or(SensitivityError::NominalScenarioMissing)?;
    Ok(PhaseCostRange {
        lower,
        nominal,
        upper,
    })
}

fn break_even(
    scenarios: &[SensitivityScenario],
    range: PhaseCostRange,
    baseline: f64,
    value: impl Fn(&SensitivityScenario) -> f64,
) -> BreakEvenAssessment {
    let scenarios_at_or_below_baseline = scenarios
        .iter()
        .filter(|scenario| value(scenario) <= baseline)
        .count();
    let status = if scenarios_at_or_below_baseline == scenarios.len() {
        BreakEvenStatus::AllScenarios
    } else if scenarios_at_or_below_baseline == 0 {
        BreakEvenStatus::NoScenarios
    } else {
        BreakEvenStatus::SomeScenarios
    };
    BreakEvenAssessment {
        provider_price_per_million_tokens: baseline,
        status,
        scenarios_at_or_below_baseline,
        scenario_count: scenarios.len(),
        worst_case_advantage_fraction: (baseline - range.upper) / baseline,
        best_case_advantage_fraction: (baseline - range.lower) / baseline,
    }
}

fn conclusion_gate(
    study: &CoDesignStudyReport,
    oracle_fidelity: OracleFidelity,
) -> EconomicConclusionGate {
    let mut blockers = Vec::new();
    match study.quality.gate_for(&study.quality_target) {
        QualityGate::MeasuredPassed => {}
        QualityGate::ContractFailed => blockers.push(ConclusionBlocker::QualityContractFailed),
        QualityGate::ScopeMismatch => {
            blockers.push(ConclusionBlocker::QualityEvidenceScopeMismatch);
        }
        QualityGate::InvalidEvidence => {
            blockers.push(ConclusionBlocker::QualityEvidenceInvalid);
        }
        QualityGate::Unvalidated | QualityGate::Surrogate => {
            blockers.push(ConclusionBlocker::QualityUnmeasured);
        }
    }
    if oracle_fidelity != OracleFidelity::External {
        blockers.push(ConclusionBlocker::PerformanceFidelityNotExternal);
    }
    if study.hardware_sizing.source != SizingSource::Validated {
        blockers.push(ConclusionBlocker::HardwareSizingNotValidated);
    }
    EconomicConclusionGate {
        permitted: blockers.is_empty(),
        blockers,
    }
}

fn expected_quality_target(study: &CoDesignStudyReport) -> Result<QualityTarget, SensitivityError> {
    QualityTarget::for_model(
        &study.candidate_spec.model,
        &study.candidate_spec.quality_suite_id,
        &QualityVariantContext {
            name: study.variant_name.clone(),
            changes: study.variant_changes.clone(),
        },
    )
    .map_err(|error| SensitivityError::QualityIdentity(error.to_string()))
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum SensitivityError {
    #[error("co-design study has no SLO-compliant selected timing result")]
    NoSloCompliantSelection,
    #[error("study or selected experiment provenance is missing")]
    InvalidStudyProvenance,
    #[error("study and selected experiment quality evidence differ")]
    QualityEvidenceMismatch,
    #[error("study quality target does not match its model, variant, suite, or selected run")]
    QualityTargetMismatch,
    #[error("quality target identity failed: {0}")]
    QualityIdentity(String),
    #[error("invalid fixed timing basis field {0}")]
    InvalidTimingBasis(&'static str),
    #[error("invalid sensitivity range {0}")]
    InvalidRange(&'static str),
    #[error("invalid count sensitivity range {0}")]
    InvalidCountRange(&'static str),
    #[error("missing provenance for sensitivity assumption {0}")]
    InvalidProvenance(&'static str),
    #[error("provider baseline must have a name, positive prices, and provenance")]
    InvalidProviderBaseline,
    #[error(
        "nominal value for {field} differs from study basis: expected {expected}, got {actual}"
    )]
    NominalValueMismatch {
        field: &'static str,
        expected: f64,
        actual: f64,
    },
    #[error(
        "nominal count for {field} differs from study basis: expected {expected}, got {actual}"
    )]
    NominalCountMismatch {
        field: &'static str,
        expected: u64,
        actual: u64,
    },
    #[error("sensitivity assumptions require the {expected} cost model")]
    CostModelMismatch { expected: &'static str },
    #[error("custom-silicon sensitivity requires a detailed hardware design")]
    MissingHardwareDesign,
    #[error("invalid or unrecoverable economic cost basis")]
    InvalidCostBasis,
    #[error("hardware component count overflow")]
    HardwareCountOverflow,
    #[error("nominal sensitivity scenario is missing")]
    NominalScenarioMissing,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::codesign::{MeasuredQualityScope, QualityEvidence};
    use crate::economics::ServerTcoInputs;
    use crate::experiment::{CostChoice, OracleChoice, RunOptions};
    use crate::performance::OracleFidelity;
    use crate::sizing::{HardwareSizingConstraints, SizingSource};
    use crate::spec::ExperimentSpec;
    use crate::study::{CoDesignStudyReport, run_codesign_study};

    #[test]
    fn custom_silicon_sweep_reuses_timing_and_reports_phase_cost_ranges() {
        let study = custom_study(measured_quality());
        let selected = study.capacity.selected.as_ref().unwrap();
        let request = SensitivityRequest {
            assumptions: SensitivityAssumptions::CustomSilicon(custom_assumptions(&study)),
            provider_baseline: provider_baseline(
                selected.costs.input.cost_per_million_tokens,
                selected.costs.output.cost_per_million_tokens,
            ),
        };

        let report = analyze_codesign_sensitivity(&study, &request).unwrap();

        assert_eq!(report.scenarios.len(), 243);
        assert!(
            report.input_cost_per_million_tokens.lower < report.input_cost_per_million_tokens.upper
        );
        assert!(
            report.output_cost_per_million_tokens.lower
                < report.output_cost_per_million_tokens.upper
        );
        assert_close(
            report.input_cost_per_million_tokens.nominal,
            selected.costs.input.cost_per_million_tokens,
        );
        assert_close(
            report.output_cost_per_million_tokens.nominal,
            selected.costs.output.cost_per_million_tokens,
        );
        assert_eq!(report.timing_basis.experiment_spec_id, selected.spec_id);
        assert_eq!(
            report.timing_basis.simulation_duration_seconds,
            selected.simulation.duration_seconds
        );
        assert_eq!(
            report.timing_basis.source,
            TimingSource::ReusedCoDesignStudySelection
        );
    }

    #[test]
    fn pessimistic_custom_silicon_assumptions_cost_more_than_optimistic_ones() {
        let study = custom_study(measured_quality());
        let assumptions = custom_assumptions(&study);
        let request = SensitivityRequest {
            assumptions: SensitivityAssumptions::CustomSilicon(assumptions.clone()),
            provider_baseline: provider_baseline(10.0, 10.0),
        };

        let report = analyze_codesign_sensitivity(&study, &request).unwrap();
        let optimistic = report
            .scenarios
            .iter()
            .find(|scenario| {
                scenario.assumptions
                    == ScenarioAssumptions::CustomSilicon {
                        nre_amortization_units: assumptions.nre_amortization_units.upper,
                        utilization: assumptions.utilization.upper,
                        hbm_stack_cost_usd: assumptions.hbm_stack_cost_usd.lower,
                        wafer_cost_usd: assumptions.wafer_cost_usd.lower,
                        effective_silicon_yield: assumptions.effective_silicon_yield.upper,
                    }
            })
            .unwrap();
        let pessimistic = report
            .scenarios
            .iter()
            .find(|scenario| {
                scenario.assumptions
                    == ScenarioAssumptions::CustomSilicon {
                        nre_amortization_units: assumptions.nre_amortization_units.lower,
                        utilization: assumptions.utilization.lower,
                        hbm_stack_cost_usd: assumptions.hbm_stack_cost_usd.upper,
                        wafer_cost_usd: assumptions.wafer_cost_usd.upper,
                        effective_silicon_yield: assumptions.effective_silicon_yield.lower,
                    }
            })
            .unwrap();

        assert!(
            pessimistic.input_cost_per_million_tokens > optimistic.input_cost_per_million_tokens
        );
        assert!(
            pessimistic.output_cost_per_million_tokens > optimistic.output_cost_per_million_tokens
        );
    }

    #[test]
    fn known_hourly_sweep_uses_the_selected_activity_without_custom_capital() {
        let study = known_hourly_study(measured_quality());
        let selected = study.capacity.selected.as_ref().unwrap();
        let request = SensitivityRequest {
            assumptions: SensitivityAssumptions::KnownHourly(known_hourly_assumptions(&study)),
            provider_baseline: provider_baseline(
                selected.costs.input.cost_per_million_tokens,
                selected.costs.output.cost_per_million_tokens,
            ),
        };

        let report = analyze_codesign_sensitivity(&study, &request).unwrap();

        assert!(selected.server_capital.is_none());
        assert!(report.scenarios.len() > 1);
        assert_close(
            report.input_cost_per_million_tokens.nominal,
            selected.costs.input.cost_per_million_tokens,
        );
        assert_close(
            report.output_cost_per_million_tokens.nominal,
            selected.costs.output.cost_per_million_tokens,
        );
    }

    #[test]
    fn break_even_reports_how_many_scenarios_beat_provider_prices() {
        let study = custom_study(measured_quality());
        let selected = study.capacity.selected.as_ref().unwrap();
        let request = SensitivityRequest {
            assumptions: SensitivityAssumptions::CustomSilicon(custom_assumptions(&study)),
            provider_baseline: provider_baseline(
                selected.costs.input.cost_per_million_tokens,
                selected.costs.output.cost_per_million_tokens,
            ),
        };

        let report = analyze_codesign_sensitivity(&study, &request).unwrap();

        assert_eq!(
            report.input_break_even.status,
            BreakEvenStatus::SomeScenarios
        );
        assert_eq!(
            report.output_break_even.status,
            BreakEvenStatus::SomeScenarios
        );
        assert!(report.input_break_even.scenarios_at_or_below_baseline > 0);
        assert!(report.input_break_even.scenarios_at_or_below_baseline < report.scenarios.len());
        assert!(report.input_break_even.worst_case_advantage_fraction < 0.0);
        assert!(report.input_break_even.best_case_advantage_fraction > 0.0);
    }

    #[test]
    fn economic_conclusion_requires_measured_quality_and_validated_external_fidelity() {
        let study = custom_study(QualityEvidence::Unvalidated);
        let request = SensitivityRequest {
            assumptions: SensitivityAssumptions::CustomSilicon(custom_assumptions(&study)),
            provider_baseline: provider_baseline(10.0, 10.0),
        };

        let report = analyze_codesign_sensitivity(&study, &request).unwrap();

        assert_eq!(
            report.conclusion_gate.blockers,
            vec![
                ConclusionBlocker::QualityUnmeasured,
                ConclusionBlocker::PerformanceFidelityNotExternal,
                ConclusionBlocker::HardwareSizingNotValidated,
            ]
        );
        assert!(!report.conclusion_gate.permitted);

        let mut validated = study;
        validated.quality = measured_quality();
        validated.hardware_sizing.source = SizingSource::Validated;
        let selected = validated.capacity.selected.as_mut().unwrap();
        selected.quality = measured_quality();
        selected.oracle_fidelity = OracleFidelity::External;
        let request = SensitivityRequest {
            assumptions: SensitivityAssumptions::CustomSilicon(custom_assumptions(&validated)),
            provider_baseline: provider_baseline(10.0, 10.0),
        };

        let report = analyze_codesign_sensitivity(&validated, &request).unwrap();

        assert!(report.conclusion_gate.permitted);
        assert!(report.conclusion_gate.blockers.is_empty());
    }

    #[test]
    fn economic_conclusion_reports_wrong_model_quality_as_a_scope_mismatch() {
        let mut study = custom_study(QualityEvidence::Unvalidated);
        let mut wrong_target = study.quality_target.clone();
        wrong_target.model_id = "Qwen/Qwen3-0.6B".into();
        let wrong_quality = QualityEvidence::Measured {
            scope: MeasuredQualityScope {
                target: wrong_target,
                report_id: "small-model-quality".into(),
            },
            passed: true,
            worst_metric_delta: 0.0,
        };
        study.quality = wrong_quality.clone();
        study.capacity.selected.as_mut().unwrap().quality = wrong_quality;
        let request = SensitivityRequest {
            assumptions: SensitivityAssumptions::CustomSilicon(custom_assumptions(&study)),
            provider_baseline: provider_baseline(10.0, 10.0),
        };

        let report = analyze_codesign_sensitivity(&study, &request).unwrap();

        assert!(
            report
                .conclusion_gate
                .blockers
                .contains(&ConclusionBlocker::QualityEvidenceScopeMismatch)
        );
        assert!(!report.conclusion_gate.permitted);
    }

    #[test]
    fn invalid_assumption_provenance_is_rejected() {
        let study = custom_study(measured_quality());
        let mut assumptions = custom_assumptions(&study);
        assumptions.hbm_stack_cost_usd.provenance.source.clear();
        let request = SensitivityRequest {
            assumptions: SensitivityAssumptions::CustomSilicon(assumptions),
            provider_baseline: provider_baseline(10.0, 10.0),
        };

        assert_eq!(
            analyze_codesign_sensitivity(&study, &request),
            Err(SensitivityError::InvalidProvenance(
                "custom_silicon.hbm_stack_cost_usd"
            ))
        );
    }

    fn custom_study(quality: QualityEvidence) -> CoDesignStudyReport {
        let options = RunOptions {
            oracle: OracleChoice::Auto,
            cost: CostChoice::CustomSilicon(ServerTcoInputs {
                accelerators_per_server: 1,
                memory_usd_per_accelerator: 1.0,
                board_usd_per_server: 5_000.0,
                host_usd_per_server: 8_000.0,
                network_usd_per_server: 3_000.0,
                rack_usd_per_server: 2_000.0,
                lifetime_hours: 26_280.0,
                target_utilization: 0.7,
            }),
            quality,
            quality_variant: None,
        };
        run_codesign_study(&baseline(), None, &constraints(), &options, 64).unwrap()
    }

    fn known_hourly_study(quality: QualityEvidence) -> CoDesignStudyReport {
        let options = RunOptions {
            quality,
            ..RunOptions::default()
        };
        run_codesign_study(&baseline(), None, &constraints(), &options, 64).unwrap()
    }

    fn baseline() -> ExperimentSpec {
        let mut spec: ExperimentSpec =
            serde_json::from_str(include_str!("../../../configs/qwen3-8b-agentic-h100.json"))
                .unwrap();
        spec.workload.request_count = 16;
        spec.serving.ttft_slo_milliseconds = 60_000.0;
        spec.serving.tpot_slo_milliseconds = 200.0;
        spec
    }

    fn constraints() -> HardwareSizingConstraints {
        let mut constraints = HardwareSizingConstraints::default();
        constraints.serving.max_concurrent_requests = 8;
        constraints.serving.reserved_sequence_tokens_per_request = 32_768;
        constraints.serving.decode_batch_size = 8;
        constraints.serving.target_output_tokens_per_second = 500.0;
        constraints
    }

    fn custom_assumptions(study: &CoDesignStudyReport) -> CustomSiliconSensitivity {
        let design = study.candidate_spec.hardware.design.as_ref().unwrap();
        let nominal_volume = design.manufacturing.amortization_units;
        let nominal_hbm = study.hardware_sizing.cost.hbm_cost_usd
            * design.manufacturing.package_yield
            / f64::from(
                study.hardware_sizing.mapping.device_count
                    * study.hardware_sizing.mapping.hbm_stacks_per_device,
            );
        let nominal_yield = design.manufacturing.die_yield * design.manufacturing.package_yield;
        CustomSiliconSensitivity {
            nre_amortization_units: CountRange {
                lower: nominal_volume / 10,
                nominal: nominal_volume,
                upper: nominal_volume * 10,
                provenance: provenance(EvidenceKind::InternalEstimate),
            },
            utilization: ValueRange {
                lower: 0.4,
                nominal: 0.7,
                upper: 0.9,
                provenance: provenance(EvidenceKind::InternalEstimate),
            },
            hbm_stack_cost_usd: ValueRange {
                lower: nominal_hbm * 0.5,
                nominal: nominal_hbm,
                upper: nominal_hbm * 1.5,
                provenance: provenance(EvidenceKind::VendorQuote),
            },
            wafer_cost_usd: ValueRange {
                lower: design.process.wafer_cost_usd * 0.75,
                nominal: design.process.wafer_cost_usd,
                upper: design.process.wafer_cost_usd * 1.25,
                provenance: provenance(EvidenceKind::VendorQuote),
            },
            effective_silicon_yield: ValueRange {
                lower: nominal_yield * 0.7,
                nominal: nominal_yield,
                upper: (nominal_yield * 1.1).min(1.0),
                provenance: provenance(EvidenceKind::FoundryModel),
            },
        }
    }

    fn known_hourly_assumptions(study: &CoDesignStudyReport) -> KnownHourlySensitivity {
        let rates = study
            .capacity
            .selected
            .as_ref()
            .unwrap()
            .levelized_cost_rates;
        KnownHourlySensitivity {
            fleet_hardware_usd_per_hour: around(rates.hardware_usd_per_active_hour),
            host_usd_per_hour: around(rates.host_usd_per_active_hour),
            network_rack_usd_per_hour: around(rates.network_rack_usd_per_active_hour),
            provider_overhead_usd_per_hour: around(rates.provider_usd_per_active_hour),
        }
    }

    fn around(nominal: f64) -> ValueRange {
        ValueRange {
            lower: nominal * 0.5,
            nominal,
            upper: nominal * 1.5,
            provenance: provenance(EvidenceKind::PublicPricing),
        }
    }

    fn provider_baseline(input: f64, output: f64) -> ProviderBaseline {
        ProviderBaseline {
            name: "tuned-provider-baseline".into(),
            input_usd_per_million_tokens: input,
            output_usd_per_million_tokens: output,
            provenance: provenance(EvidenceKind::PublicPricing),
        }
    }

    fn provenance(kind: EvidenceKind) -> AssumptionProvenance {
        AssumptionProvenance {
            kind,
            source: "evidence source".into(),
            artifact: "artifact-id".into(),
        }
    }

    fn measured_quality() -> QualityEvidence {
        let target =
            QualityTarget::for_experiment(&baseline(), &QualityVariantContext::baseline()).unwrap();
        QualityEvidence::Measured {
            scope: MeasuredQualityScope {
                target,
                report_id: "quality-report".into(),
            },
            passed: true,
            worst_metric_delta: -0.001,
        }
    }

    fn assert_close(left: f64, right: f64) {
        assert!((left - right).abs() <= right.abs().max(1.0) * 1e-9);
    }
}
