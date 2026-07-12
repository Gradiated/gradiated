use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::codesign::{QualityEvidence, QualityGate, QualityTarget, QualityVariantContext};
use crate::economics::{
    CostModel, CostReport, EconomicsError, InferenceActivity, LevelizedCostRates,
    ServerCapitalBreakdown, ServerTcoInputs, calculate_cost_report_from_spec,
};
use crate::hardware::{HardwareOracle, TensorTileOracle};
use crate::performance::{OracleFidelity, RooflineOracle};
use crate::simulation::{ServingSimulator, SimulationError, SimulationReport};
use crate::spec::{ExperimentSpec, HardwareFidelity};
use crate::stack::StackOracle;

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum OracleChoice {
    #[default]
    Auto,
    Roofline,
    TensorTile,
}

#[derive(Clone, Copy, Debug, Default, Deserialize, PartialEq, Serialize)]
#[serde(tag = "cost", content = "server", rename_all = "snake_case")]
pub enum CostChoice {
    #[default]
    KnownHourly,
    CustomSilicon(ServerTcoInputs),
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct RunOptions {
    pub oracle: OracleChoice,
    pub cost: CostChoice,
    pub quality: QualityEvidence,
    pub quality_variant: Option<QualityVariantContext>,
}

impl Default for RunOptions {
    fn default() -> Self {
        Self {
            oracle: OracleChoice::Auto,
            cost: CostChoice::KnownHourly,
            quality: QualityEvidence::Unvalidated,
            quality_variant: None,
        }
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ExperimentReport {
    pub spec_id: String,
    pub experiment_name: String,
    pub model_id: String,
    pub hardware_name: String,
    pub declared_hardware_fidelity: HardwareFidelity,
    pub oracle_fidelity: OracleFidelity,
    pub data_parallel_replicas: u32,
    pub model_parallel_devices_per_replica: u32,
    pub deployed_accelerators: u32,
    pub aggregate_input_tokens: u64,
    pub aggregate_output_tokens: u64,
    pub aggregate_goodput_output_tokens_per_second: f64,
    pub simulation: SimulationReport,
    pub costs: CostReport,
    pub levelized_cost_rates: LevelizedCostRates,
    pub server_capital: Option<ServerCapitalBreakdown>,
    pub quality: QualityEvidence,
    pub quality_target: QualityTarget,
    pub quality_gate: QualityGate,
    pub quality_gated_comparison_permitted: bool,
    pub production_claim_permitted: bool,
    pub billed_accelerator_seconds: f64,
    pub limitations: Vec<String>,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct ExperimentRunner;

impl ExperimentRunner {
    pub fn run(
        &self,
        spec: &ExperimentSpec,
        options: &RunOptions,
    ) -> Result<ExperimentReport, ExperimentError> {
        let quality_variant = options
            .quality_variant
            .clone()
            .unwrap_or_else(QualityVariantContext::baseline);
        let quality_target = QualityTarget::for_experiment(spec, &quality_variant)
            .map_err(|error| ExperimentError::QualityIdentity(error.to_string()))?;
        let quality_gate = options.quality.gate_for(&quality_target);
        let model_parallel_accelerators = spec
            .mapping
            .tensor_parallelism
            .checked_mul(spec.mapping.pipeline_parallelism)
            .ok_or(ExperimentError::AcceleratorCountOverflow)?;
        if model_parallel_accelerators != spec.hardware.physical_device_count {
            return Err(ExperimentError::HardwareMappingMismatch {
                mapped: model_parallel_accelerators,
                provisioned: spec.hardware.physical_device_count,
            });
        }
        let data_parallel_replicas = spec.mapping.data_parallelism;
        let deployed_accelerators = model_parallel_accelerators
            .checked_mul(data_parallel_replicas)
            .ok_or(ExperimentError::AcceleratorCountOverflow)?;
        let mut simulation_spec = spec.clone();
        simulation_spec.workload.arrival_rate_per_second /= f64::from(data_parallel_replicas);
        let choice = resolve_oracle(spec.hardware.fidelity, options.oracle)?;
        let (simulation, oracle_fidelity) = match choice {
            OracleChoice::Auto => unreachable!(),
            OracleChoice::Roofline => (
                ServingSimulator.run(
                    &simulation_spec,
                    &StackOracle::new(
                        HardwareOracle::Roofline(RooflineOracle::default()),
                        &simulation_spec.kernel,
                    ),
                )?,
                OracleFidelity::Roofline,
            ),
            OracleChoice::TensorTile => (
                ServingSimulator.run(
                    &simulation_spec,
                    &StackOracle::new(
                        HardwareOracle::TensorTile(TensorTileOracle::default()),
                        &simulation_spec.kernel,
                    ),
                )?,
                OracleFidelity::TensorTile,
            ),
        };
        let mut activity = InferenceActivity::from_simulation_report(&simulation);
        allocate_idle_energy(spec, &simulation, &mut activity)?;
        scale_replica_activity(&mut activity, data_parallel_replicas)?;
        let cost_model = match options.cost {
            CostChoice::KnownHourly => {
                let mut fleet = spec.hardware.clone();
                fleet.accelerator_hourly_cost_usd *= f64::from(data_parallel_replicas);
                CostModel::known_hourly_from_spec(&fleet, &spec.economics)
            }
            CostChoice::CustomSilicon(server) => {
                if server.accelerators_per_server != data_parallel_replicas {
                    return Err(ExperimentError::ServerAcceleratorCountMismatch {
                        mapped: data_parallel_replicas,
                        costed: server.accelerators_per_server,
                    });
                }
                CostModel::custom_silicon_from_spec(&spec.hardware, &spec.economics, server)?
            }
        };
        let costs = calculate_cost_report_from_spec(&cost_model, &activity, &spec.economics)?;
        let levelized_cost_rates = cost_model.levelized_rates()?;
        let server_capital = cost_model.server_capital_breakdown()?;
        let quality_gated_comparison_permitted = quality_gate.permits_economic_conclusion();
        let production_claim_permitted = false;
        let mut limitations = vec![format!(
            "performance is simulated with the {oracle_fidelity:?} oracle"
        )];
        if !quality_gated_comparison_permitted {
            limitations.push(format!(
                "model quality gate is {quality_gate:?} for the exact model, variant, and suite"
            ));
        }
        limitations.push(
            "production claims require calibrated external kernel, serving, power, and hardware measurements"
                .into(),
        );
        Ok(ExperimentReport {
            spec_id: spec
                .content_id()
                .map_err(|error| ExperimentError::SpecIdentity(error.to_string()))?
                .to_hex(),
            experiment_name: spec.experiment_name.clone(),
            model_id: spec.model.model_id.clone(),
            hardware_name: spec.hardware.name.clone(),
            declared_hardware_fidelity: spec.hardware.fidelity,
            oracle_fidelity,
            data_parallel_replicas,
            model_parallel_devices_per_replica: model_parallel_accelerators,
            deployed_accelerators,
            aggregate_input_tokens: activity.input.tokens,
            aggregate_output_tokens: activity.output.tokens,
            aggregate_goodput_output_tokens_per_second: simulation.goodput_output_tokens_per_second
                * f64::from(data_parallel_replicas),
            simulation,
            costs,
            levelized_cost_rates,
            server_capital,
            quality: options.quality.clone(),
            quality_target,
            quality_gate,
            quality_gated_comparison_permitted,
            production_claim_permitted,
            billed_accelerator_seconds: (activity.input.accelerator_seconds
                + activity.output.accelerator_seconds)
                * f64::from(deployed_accelerators),
            limitations,
        })
    }
}

fn scale_replica_activity(
    activity: &mut InferenceActivity,
    replicas: u32,
) -> Result<(), ExperimentError> {
    let replicas_u64 = u64::from(replicas);
    activity.input.tokens = activity
        .input
        .tokens
        .checked_mul(replicas_u64)
        .ok_or(ExperimentError::ActivityOverflow)?;
    activity.output.tokens = activity
        .output
        .tokens
        .checked_mul(replicas_u64)
        .ok_or(ExperimentError::ActivityOverflow)?;
    activity.input.energy_joules *= f64::from(replicas);
    activity.output.energy_joules *= f64::from(replicas);
    if !activity.input.energy_joules.is_finite() || !activity.output.energy_joules.is_finite() {
        return Err(ExperimentError::ActivityOverflow);
    }
    Ok(())
}

fn resolve_oracle(
    fidelity: HardwareFidelity,
    choice: OracleChoice,
) -> Result<OracleChoice, ExperimentError> {
    match choice {
        OracleChoice::Roofline | OracleChoice::TensorTile => Ok(choice),
        OracleChoice::Auto => match fidelity {
            HardwareFidelity::Analytical => Ok(OracleChoice::Roofline),
            HardwareFidelity::Architecture => Ok(OracleChoice::TensorTile),
            HardwareFidelity::Rtl | HardwareFidelity::Measured => {
                Err(ExperimentError::ExternalOracleRequired(fidelity))
            }
        },
    }
}

fn allocate_idle_energy(
    spec: &ExperimentSpec,
    simulation: &SimulationReport,
    activity: &mut InferenceActivity,
) -> Result<(), ExperimentError> {
    let idle_seconds = (simulation.duration_seconds - simulation.total_busy_seconds).max(0.0);
    let idle_watts = spec
        .hardware
        .effective_idle_power_watts()
        .ok_or(ExperimentError::MissingIdlePower)?;
    if !idle_watts.is_finite() || idle_watts < 0.0 {
        return Err(ExperimentError::MissingIdlePower);
    }
    let billed_seconds = activity.input.accelerator_seconds + activity.output.accelerator_seconds;
    let input_share = if billed_seconds > 0.0 {
        activity.input.accelerator_seconds / billed_seconds
    } else {
        0.5
    };
    let idle_energy = idle_seconds * idle_watts;
    activity.input.energy_joules += idle_energy * input_share;
    activity.output.energy_joules += idle_energy * (1.0 - input_share);
    Ok(())
}

#[derive(Debug, Error, PartialEq)]
pub enum ExperimentError {
    #[error("simulation failed: {0}")]
    Simulation(#[from] SimulationError),
    #[error("economics failed: {0}")]
    Economics(#[from] EconomicsError),
    #[error("failed to identify the experiment: {0}")]
    SpecIdentity(String),
    #[error("failed to identify the quality target: {0}")]
    QualityIdentity(String),
    #[error("{0:?} hardware requires an external calibrated performance oracle")]
    ExternalOracleRequired(HardwareFidelity),
    #[error("execution maps across {mapped} devices but hardware provisions {provisioned}")]
    HardwareMappingMismatch { mapped: u32, provisioned: u32 },
    #[error("accelerator count overflow")]
    AcceleratorCountOverflow,
    #[error("replica activity overflow")]
    ActivityOverflow,
    #[error("mapped accelerator count {mapped} does not match costed server count {costed}")]
    ServerAcceleratorCountMismatch { mapped: u32, costed: u32 },
    #[error("hardware idle power is missing or invalid")]
    MissingIdlePower,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::codesign::{MeasuredQualityScope, QualityEvidence};
    use crate::economics::ServerTcoInputs;
    use crate::performance::OracleFidelity;
    use crate::spec::ExperimentSpec;

    fn spec(path: &str) -> ExperimentSpec {
        serde_json::from_str(path).unwrap()
    }

    #[test]
    fn analytical_hardware_runs_end_to_end_with_wall_clock_economics() {
        let experiment = spec(include_str!("../../../configs/qwen3-8b-agentic-h100.json"));

        let report = ExperimentRunner
            .run(&experiment, &RunOptions::default())
            .unwrap();

        assert_eq!(report.oracle_fidelity, OracleFidelity::Roofline);
        assert_eq!(report.spec_id, experiment.content_id().unwrap().to_hex());
        assert!(report.costs.input.cost_per_million_tokens > 0.0);
        assert!(report.costs.output.cost_per_million_tokens > 0.0);
        assert!(
            (report.billed_accelerator_seconds - report.simulation.duration_seconds).abs() < 1e-9
        );
        assert!(!report.quality_gated_comparison_permitted);
        assert!(!report.production_claim_permitted);
    }

    #[test]
    fn architecture_hardware_uses_tensor_tile_and_custom_silicon_tco() {
        let experiment = spec(include_str!(
            "../../../configs/qwen3-8b-agentic-custom-asic.json"
        ));
        let quality_target =
            QualityTarget::for_experiment(&experiment, &QualityVariantContext::baseline()).unwrap();
        let options = RunOptions {
            oracle: OracleChoice::Auto,
            cost: CostChoice::CustomSilicon(ServerTcoInputs {
                accelerators_per_server: 1,
                memory_usd_per_accelerator: 8_000.0,
                board_usd_per_server: 5_000.0,
                host_usd_per_server: 8_000.0,
                network_usd_per_server: 3_000.0,
                rack_usd_per_server: 2_000.0,
                lifetime_hours: 26_280.0,
                target_utilization: 0.7,
            }),
            quality: QualityEvidence::Measured {
                scope: MeasuredQualityScope {
                    target: quality_target,
                    report_id: "quality-report".into(),
                },
                passed: true,
                worst_metric_delta: -0.001,
            },
            quality_variant: None,
        };

        let report = ExperimentRunner.run(&experiment, &options).unwrap();

        assert_eq!(report.oracle_fidelity, OracleFidelity::TensorTile);
        assert!(report.levelized_cost_rates.nre_usd_per_active_hour > 0.0);
        assert!(report.quality_gated_comparison_permitted);
        assert!(!report.production_claim_permitted);
    }

    #[test]
    fn passing_quality_for_qwen_point_six_does_not_unlock_qwen_eight_economics() {
        let experiment = spec(include_str!("../../../configs/qwen3-8b-agentic-h100.json"));
        let mut wrong_model = experiment.clone();
        wrong_model.model.model_id = "Qwen/Qwen3-0.6B".into();
        wrong_model.model.model_revision = "small-model-revision".into();
        wrong_model.model.parameter_count = 600_000_000;
        let wrong_target =
            QualityTarget::for_experiment(&wrong_model, &QualityVariantContext::baseline())
                .unwrap();
        let options = RunOptions {
            quality: QualityEvidence::Measured {
                scope: MeasuredQualityScope {
                    target: wrong_target,
                    report_id: "qwen3-0.6b-int4-quality".into(),
                },
                passed: true,
                worst_metric_delta: 0.0,
            },
            ..RunOptions::default()
        };

        let report = ExperimentRunner.run(&experiment, &options).unwrap();

        assert_eq!(report.quality_gate, QualityGate::ScopeMismatch);
        assert!(!report.quality_gated_comparison_permitted);
    }

    #[test]
    fn auto_mode_rejects_claiming_rtl_or_measured_fidelity_with_builtin_oracles() {
        let mut experiment = spec(include_str!(
            "../../../configs/qwen3-8b-agentic-custom-asic.json"
        ));
        experiment.hardware.fidelity = crate::spec::HardwareFidelity::Rtl;

        let error = ExperimentRunner
            .run(&experiment, &RunOptions::default())
            .unwrap_err();

        assert_eq!(
            error,
            ExperimentError::ExternalOracleRequired(crate::spec::HardwareFidelity::Rtl)
        );
    }

    #[test]
    fn data_parallel_replicas_partition_arrivals_and_reconcile_fleet_activity() {
        let mut single = spec(include_str!("../../../configs/qwen3-8b-agentic-h100.json"));
        single.workload.request_count = 32;
        let single_report = ExperimentRunner
            .run(&single, &RunOptions::default())
            .unwrap();
        let mut fleet = single;
        fleet.mapping.data_parallelism = 16;

        let fleet_report = ExperimentRunner
            .run(&fleet, &RunOptions::default())
            .unwrap();

        assert_eq!(fleet_report.deployed_accelerators, 16);
        assert_eq!(
            fleet_report.aggregate_input_tokens,
            fleet_report.simulation.input_tokens * 16
        );
        assert_eq!(
            fleet_report.aggregate_output_tokens,
            fleet_report.simulation.output_tokens * 16
        );
        assert!(
            fleet_report.simulation.p95_ttft_milliseconds
                < single_report.simulation.p95_ttft_milliseconds
        );
        assert!(
            (fleet_report.billed_accelerator_seconds
                - fleet_report.simulation.duration_seconds * 16.0)
                .abs()
                < 1e-8
        );
    }
}
