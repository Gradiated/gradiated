use crate::economics::{CostBreakdown, CostReport, PhaseEconomics};
use crate::spec::HardwareFidelity;
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use thiserror::Error;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ComparisonContract {
    pub model_id: String,
    pub model_revision: String,
    pub tokenizer_id: String,
    pub tokenizer_revision: String,
    pub quality: QualityContract,
    pub slo: SloContract,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct QualityContract {
    pub suite: String,
    pub seed: u64,
    pub requirements: Vec<QualityRequirement>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct QualityRequirement {
    pub metric: String,
    pub threshold: f64,
    pub direction: MetricDirection,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum MetricDirection {
    HigherIsBetter,
    LowerIsBetter,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct SloContract {
    pub ttft: LatencyObjective,
    pub tpot: LatencyObjective,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct LatencyObjective {
    pub percentile: f64,
    pub maximum_milliseconds: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProviderBaseline {
    pub provider_name: String,
    pub contract: ComparisonContract,
    pub observables: ObservableSummary,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CandidateResult {
    pub candidate_name: String,
    pub contract: ComparisonContract,
    pub observables: ObservableSummary,
    pub ablations: Vec<AblationObservation>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ObservableSummary {
    pub costs: CostReport,
    pub quality: Vec<QualityMeasurement>,
    pub ttft_milliseconds: f64,
    pub tpot_milliseconds: f64,
    pub input_energy_joules_per_million_tokens: f64,
    pub output_energy_joules_per_million_tokens: f64,
    pub hardware_fidelity: HardwareFidelity,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct QualityMeasurement {
    pub metric: String,
    pub score: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AblationObservation {
    pub axis: OptimizationAxis,
    pub without_axis: ObservableSummary,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum OptimizationAxis {
    Model,
    Kernel,
    Mapping,
    Serving,
    Hardware,
    Other(String),
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct MaterialityThresholds {
    pub cost_relative: f64,
    pub price_relative: f64,
    pub quality_absolute: f64,
    pub latency_relative: f64,
    pub energy_relative: f64,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Materiality {
    Improvement,
    Neutral,
    Regression,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct MetricChange {
    pub baseline: f64,
    pub candidate: f64,
    pub absolute_improvement: f64,
    pub relative_improvement: Option<f64>,
    pub materiality: Materiality,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct PhaseComparison {
    pub cost: MetricChange,
    pub minimum_sustainable_price: MetricChange,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct QualityComparison {
    pub metric: String,
    pub threshold: f64,
    pub direction: MetricDirection,
    pub baseline_passes: bool,
    pub candidate_passes: bool,
    pub change: MetricChange,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct LatencyComparison {
    pub ttft: MetricChange,
    pub tpot: MetricChange,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct EnergyComparison {
    pub input: MetricChange,
    pub output: MetricChange,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum FidelityChange {
    LowerConfidence,
    Same,
    HigherConfidence,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub struct HardwareFidelityComparison {
    pub baseline: HardwareFidelity,
    pub candidate: HardwareFidelity,
    pub change: FidelityChange,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub struct ComparisonCompliance {
    pub baseline_quality: bool,
    pub candidate_quality: bool,
    pub baseline_slo: bool,
    pub candidate_slo: bool,
}

impl ComparisonCompliance {
    pub const fn baseline_meets_contract(&self) -> bool {
        self.baseline_quality && self.baseline_slo
    }

    pub const fn candidate_meets_contract(&self) -> bool {
        self.candidate_quality && self.candidate_slo
    }
}

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq)]
pub struct EconomicGain {
    pub input_cost: f64,
    pub output_cost: f64,
    pub input_minimum_price: f64,
    pub output_minimum_price: f64,
}

impl EconomicGain {
    fn add(self, other: Self) -> Self {
        Self {
            input_cost: self.input_cost + other.input_cost,
            output_cost: self.output_cost + other.output_cost,
            input_minimum_price: self.input_minimum_price + other.input_minimum_price,
            output_minimum_price: self.output_minimum_price + other.output_minimum_price,
        }
    }

    fn subtract(self, other: Self) -> Self {
        Self {
            input_cost: self.input_cost - other.input_cost,
            output_cost: self.output_cost - other.output_cost,
            input_minimum_price: self.input_minimum_price - other.input_minimum_price,
            output_minimum_price: self.output_minimum_price - other.output_minimum_price,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AxisContribution {
    pub axis: OptimizationAxis,
    pub gain: EconomicGain,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AttributionReport {
    pub total_gain: EconomicGain,
    pub contributions: Vec<AxisContribution>,
    pub interaction_residual: EconomicGain,
}

impl AttributionReport {
    pub fn reconciles(&self, tolerance: f64) -> bool {
        if !tolerance.is_finite() || tolerance < 0.0 {
            return false;
        }
        let explained = self
            .contributions
            .iter()
            .fold(self.interaction_residual, |sum, contribution| {
                sum.add(contribution.gain)
            });
        close(explained.input_cost, self.total_gain.input_cost, tolerance)
            && close(
                explained.output_cost,
                self.total_gain.output_cost,
                tolerance,
            )
            && close(
                explained.input_minimum_price,
                self.total_gain.input_minimum_price,
                tolerance,
            )
            && close(
                explained.output_minimum_price,
                self.total_gain.output_minimum_price,
                tolerance,
            )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CausalComparisonReport {
    pub baseline_provider: String,
    pub candidate_name: String,
    pub contract: ComparisonContract,
    pub input: PhaseComparison,
    pub output: PhaseComparison,
    pub quality: Vec<QualityComparison>,
    pub latency: LatencyComparison,
    pub energy: EnergyComparison,
    pub hardware_fidelity: HardwareFidelityComparison,
    pub compliance: ComparisonCompliance,
    pub attribution: AttributionReport,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ContractDimension {
    Model,
    Tokenizer,
    Quality,
    Slo,
    GrossMargin,
}

#[derive(Debug, Clone, Error, PartialEq)]
pub enum ComparisonError {
    #[error("invalid comparison contract field {0}")]
    InvalidContract(&'static str),
    #[error("comparison contracts differ in {0:?}")]
    ContractMismatch(ContractDimension),
    #[error("invalid materiality threshold {0}")]
    InvalidThreshold(&'static str),
    #[error("{run} contains an invalid observable field {field}")]
    InvalidObservable { run: String, field: &'static str },
    #[error("{run} quality metrics do not match the quality contract")]
    QualityMetricsMismatch { run: String },
    #[error("duplicate ablation axis {0:?}")]
    DuplicateAblationAxis(OptimizationAxis),
    #[error("ablation {0:?} uses a different gross margin")]
    AblationGrossMarginMismatch(OptimizationAxis),
}

pub fn compare(
    baseline: &ProviderBaseline,
    candidate: &CandidateResult,
    thresholds: MaterialityThresholds,
) -> Result<CausalComparisonReport, ComparisonError> {
    baseline.contract.validate()?;
    candidate.contract.validate()?;
    ensure_compatible_contracts(&baseline.contract, &candidate.contract)?;
    thresholds.validate()?;
    validate_name("provider_name", &baseline.provider_name)?;
    validate_name("candidate_name", &candidate.candidate_name)?;
    baseline
        .observables
        .validate_against(&baseline.contract, &baseline.provider_name)?;
    candidate
        .observables
        .validate_against(&candidate.contract, &candidate.candidate_name)?;
    if baseline.observables.costs.target_gross_margin
        != candidate.observables.costs.target_gross_margin
    {
        return Err(ComparisonError::ContractMismatch(
            ContractDimension::GrossMargin,
        ));
    }
    validate_ablations(candidate)?;

    let input = phase_comparison(
        &baseline.observables.costs.input,
        &candidate.observables.costs.input,
        thresholds,
    );
    let output = phase_comparison(
        &baseline.observables.costs.output,
        &candidate.observables.costs.output,
        thresholds,
    );
    let quality = quality_comparisons(
        &baseline.contract.quality,
        &baseline.observables,
        &candidate.observables,
        thresholds.quality_absolute,
    );
    let compliance = ComparisonCompliance {
        baseline_quality: quality.iter().all(|metric| metric.baseline_passes),
        candidate_quality: quality.iter().all(|metric| metric.candidate_passes),
        baseline_slo: meets_slo(&baseline.contract.slo, &baseline.observables),
        candidate_slo: meets_slo(&candidate.contract.slo, &candidate.observables),
    };

    Ok(CausalComparisonReport {
        baseline_provider: baseline.provider_name.clone(),
        candidate_name: candidate.candidate_name.clone(),
        contract: baseline.contract.clone(),
        input,
        output,
        quality,
        latency: LatencyComparison {
            ttft: lower_is_better(
                baseline.observables.ttft_milliseconds,
                candidate.observables.ttft_milliseconds,
                thresholds.latency_relative,
            ),
            tpot: lower_is_better(
                baseline.observables.tpot_milliseconds,
                candidate.observables.tpot_milliseconds,
                thresholds.latency_relative,
            ),
        },
        energy: EnergyComparison {
            input: lower_is_better(
                baseline.observables.input_energy_joules_per_million_tokens,
                candidate.observables.input_energy_joules_per_million_tokens,
                thresholds.energy_relative,
            ),
            output: lower_is_better(
                baseline.observables.output_energy_joules_per_million_tokens,
                candidate
                    .observables
                    .output_energy_joules_per_million_tokens,
                thresholds.energy_relative,
            ),
        },
        hardware_fidelity: compare_fidelity(
            baseline.observables.hardware_fidelity,
            candidate.observables.hardware_fidelity,
        ),
        compliance,
        attribution: attribution(baseline, candidate),
    })
}

impl ComparisonContract {
    pub fn validate(&self) -> Result<(), ComparisonError> {
        validate_name("model_id", &self.model_id)?;
        validate_name("model_revision", &self.model_revision)?;
        validate_name("tokenizer_id", &self.tokenizer_id)?;
        validate_name("tokenizer_revision", &self.tokenizer_revision)?;
        validate_name("quality.suite", &self.quality.suite)?;
        if self.quality.requirements.is_empty() {
            return Err(ComparisonError::InvalidContract("quality.requirements"));
        }
        let mut metrics = BTreeSet::new();
        for requirement in &self.quality.requirements {
            validate_name("quality.requirements.metric", &requirement.metric)?;
            if !requirement.threshold.is_finite() {
                return Err(ComparisonError::InvalidContract(
                    "quality.requirements.threshold",
                ));
            }
            if !metrics.insert(requirement.metric.as_str()) {
                return Err(ComparisonError::InvalidContract(
                    "quality.requirements.metric",
                ));
            }
        }
        validate_latency_objective("slo.ttft", self.slo.ttft)?;
        validate_latency_objective("slo.tpot", self.slo.tpot)
    }
}

impl MaterialityThresholds {
    pub fn validate(&self) -> Result<(), ComparisonError> {
        for (field, value) in [
            ("cost_relative", self.cost_relative),
            ("price_relative", self.price_relative),
            ("quality_absolute", self.quality_absolute),
            ("latency_relative", self.latency_relative),
            ("energy_relative", self.energy_relative),
        ] {
            if !value.is_finite() || value < 0.0 {
                return Err(ComparisonError::InvalidThreshold(field));
            }
        }
        Ok(())
    }
}

impl ObservableSummary {
    pub fn validate_against(
        &self,
        contract: &ComparisonContract,
        run: &str,
    ) -> Result<(), ComparisonError> {
        validate_cost_report(&self.costs, run)?;
        validate_positive_observable(run, "ttft_milliseconds", self.ttft_milliseconds)?;
        validate_positive_observable(run, "tpot_milliseconds", self.tpot_milliseconds)?;
        validate_non_negative_observable(
            run,
            "input_energy_joules_per_million_tokens",
            self.input_energy_joules_per_million_tokens,
        )?;
        validate_non_negative_observable(
            run,
            "output_energy_joules_per_million_tokens",
            self.output_energy_joules_per_million_tokens,
        )?;
        let mut metrics = BTreeSet::new();
        for measurement in &self.quality {
            if measurement.metric.trim().is_empty()
                || !measurement.score.is_finite()
                || !metrics.insert(measurement.metric.as_str())
            {
                return Err(ComparisonError::QualityMetricsMismatch { run: run.into() });
            }
        }
        if metrics.len() != contract.quality.requirements.len()
            || contract
                .quality
                .requirements
                .iter()
                .any(|requirement| !metrics.contains(requirement.metric.as_str()))
        {
            return Err(ComparisonError::QualityMetricsMismatch { run: run.into() });
        }
        Ok(())
    }
}

fn ensure_compatible_contracts(
    baseline: &ComparisonContract,
    candidate: &ComparisonContract,
) -> Result<(), ComparisonError> {
    if baseline.model_id != candidate.model_id
        || baseline.model_revision != candidate.model_revision
    {
        return Err(ComparisonError::ContractMismatch(ContractDimension::Model));
    }
    if baseline.tokenizer_id != candidate.tokenizer_id
        || baseline.tokenizer_revision != candidate.tokenizer_revision
    {
        return Err(ComparisonError::ContractMismatch(
            ContractDimension::Tokenizer,
        ));
    }
    if !quality_contracts_match(&baseline.quality, &candidate.quality) {
        return Err(ComparisonError::ContractMismatch(
            ContractDimension::Quality,
        ));
    }
    if baseline.slo != candidate.slo {
        return Err(ComparisonError::ContractMismatch(ContractDimension::Slo));
    }
    Ok(())
}

fn quality_contracts_match(baseline: &QualityContract, candidate: &QualityContract) -> bool {
    baseline.suite == candidate.suite
        && baseline.seed == candidate.seed
        && baseline.requirements.len() == candidate.requirements.len()
        && baseline.requirements.iter().all(|baseline_requirement| {
            candidate
                .requirements
                .iter()
                .any(|candidate_requirement| baseline_requirement == candidate_requirement)
        })
}

fn validate_name(field: &'static str, value: &str) -> Result<(), ComparisonError> {
    if value.trim().is_empty() {
        Err(ComparisonError::InvalidContract(field))
    } else {
        Ok(())
    }
}

fn validate_latency_objective(
    field: &'static str,
    objective: LatencyObjective,
) -> Result<(), ComparisonError> {
    if !objective.percentile.is_finite()
        || objective.percentile <= 0.0
        || objective.percentile > 100.0
        || !objective.maximum_milliseconds.is_finite()
        || objective.maximum_milliseconds <= 0.0
    {
        Err(ComparisonError::InvalidContract(field))
    } else {
        Ok(())
    }
}

fn validate_cost_report(report: &CostReport, run: &str) -> Result<(), ComparisonError> {
    if !report.target_gross_margin.is_finite() || !(0.0..1.0).contains(&report.target_gross_margin)
    {
        return invalid_observable(run, "costs.target_gross_margin");
    }
    validate_phase(
        &report.input,
        report.target_gross_margin,
        run,
        "costs.input",
    )?;
    validate_phase(
        &report.output,
        report.target_gross_margin,
        run,
        "costs.output",
    )?;
    for (field, value) in [
        ("costs.total_cost_usd", report.total_cost_usd),
        ("costs.allocated_cost_usd", report.allocated_cost_usd),
        (
            "costs.reconciliation_delta_usd",
            report.reconciliation_delta_usd,
        ),
    ] {
        if !value.is_finite() {
            return invalid_observable(run, field);
        }
    }
    if report.total_cost_usd < 0.0 || report.allocated_cost_usd < 0.0 {
        return invalid_observable(run, "costs.total_cost_usd");
    }
    let allocated = report.input.costs.total_usd() + report.output.costs.total_usd();
    if !relative_close(allocated, report.allocated_cost_usd)
        || !relative_close(
            report.allocated_cost_usd - report.total_cost_usd,
            report.reconciliation_delta_usd,
        )
    {
        return invalid_observable(run, "costs.reconciliation");
    }
    Ok(())
}

fn validate_phase(
    phase: &PhaseEconomics,
    gross_margin: f64,
    run: &str,
    field: &'static str,
) -> Result<(), ComparisonError> {
    if phase.tokens == 0
        || !valid_breakdown(&phase.costs)
        || !phase.cost_per_million_tokens.is_finite()
        || phase.cost_per_million_tokens < 0.0
        || !phase.minimum_price_per_million_tokens.is_finite()
        || phase.minimum_price_per_million_tokens < 0.0
    {
        return invalid_observable(run, field);
    }
    let expected_cost = phase.costs.total_usd() * 1_000_000.0 / phase.tokens as f64;
    let expected_price = expected_cost / (1.0 - gross_margin);
    if !relative_close(expected_cost, phase.cost_per_million_tokens)
        || !relative_close(expected_price, phase.minimum_price_per_million_tokens)
    {
        return invalid_observable(run, field);
    }
    Ok(())
}

fn valid_breakdown(costs: &CostBreakdown) -> bool {
    [
        costs.hardware_usd,
        costs.host_usd,
        costs.network_rack_usd,
        costs.nre_usd,
        costs.provider_usd,
        costs.energy_usd,
    ]
    .iter()
    .all(|value| value.is_finite() && *value >= 0.0)
}

fn validate_positive_observable(
    run: &str,
    field: &'static str,
    value: f64,
) -> Result<(), ComparisonError> {
    if value.is_finite() && value > 0.0 {
        Ok(())
    } else {
        invalid_observable(run, field)
    }
}

fn validate_non_negative_observable(
    run: &str,
    field: &'static str,
    value: f64,
) -> Result<(), ComparisonError> {
    if value.is_finite() && value >= 0.0 {
        Ok(())
    } else {
        invalid_observable(run, field)
    }
}

fn invalid_observable<T>(run: &str, field: &'static str) -> Result<T, ComparisonError> {
    Err(ComparisonError::InvalidObservable {
        run: run.into(),
        field,
    })
}

fn validate_ablations(candidate: &CandidateResult) -> Result<(), ComparisonError> {
    let mut axes = BTreeSet::new();
    for ablation in &candidate.ablations {
        if !axes.insert(ablation.axis.clone()) {
            return Err(ComparisonError::DuplicateAblationAxis(
                ablation.axis.clone(),
            ));
        }
        let run = format!("{} without {:?}", candidate.candidate_name, ablation.axis);
        ablation
            .without_axis
            .validate_against(&candidate.contract, &run)?;
        if ablation.without_axis.costs.target_gross_margin
            != candidate.observables.costs.target_gross_margin
        {
            return Err(ComparisonError::AblationGrossMarginMismatch(
                ablation.axis.clone(),
            ));
        }
    }
    Ok(())
}

fn phase_comparison(
    baseline: &PhaseEconomics,
    candidate: &PhaseEconomics,
    thresholds: MaterialityThresholds,
) -> PhaseComparison {
    PhaseComparison {
        cost: lower_is_better(
            baseline.cost_per_million_tokens,
            candidate.cost_per_million_tokens,
            thresholds.cost_relative,
        ),
        minimum_sustainable_price: lower_is_better(
            baseline.minimum_price_per_million_tokens,
            candidate.minimum_price_per_million_tokens,
            thresholds.price_relative,
        ),
    }
}

fn quality_comparisons(
    contract: &QualityContract,
    baseline: &ObservableSummary,
    candidate: &ObservableSummary,
    threshold: f64,
) -> Vec<QualityComparison> {
    contract
        .requirements
        .iter()
        .map(|requirement| {
            let baseline_score = quality_score(baseline, &requirement.metric);
            let candidate_score = quality_score(candidate, &requirement.metric);
            QualityComparison {
                metric: requirement.metric.clone(),
                threshold: requirement.threshold,
                direction: requirement.direction,
                baseline_passes: passes_quality(requirement, baseline_score),
                candidate_passes: passes_quality(requirement, candidate_score),
                change: directed_change(
                    baseline_score,
                    candidate_score,
                    threshold,
                    requirement.direction,
                ),
            }
        })
        .collect()
}

fn quality_score(observables: &ObservableSummary, metric: &str) -> f64 {
    observables
        .quality
        .iter()
        .find(|measurement| measurement.metric == metric)
        .map_or(0.0, |measurement| measurement.score)
}

fn passes_quality(requirement: &QualityRequirement, score: f64) -> bool {
    match requirement.direction {
        MetricDirection::HigherIsBetter => score >= requirement.threshold,
        MetricDirection::LowerIsBetter => score <= requirement.threshold,
    }
}

fn meets_slo(contract: &SloContract, observables: &ObservableSummary) -> bool {
    observables.ttft_milliseconds <= contract.ttft.maximum_milliseconds
        && observables.tpot_milliseconds <= contract.tpot.maximum_milliseconds
}

fn lower_is_better(baseline: f64, candidate: f64, threshold: f64) -> MetricChange {
    directed_change(
        baseline,
        candidate,
        threshold,
        MetricDirection::LowerIsBetter,
    )
}

fn directed_change(
    baseline: f64,
    candidate: f64,
    threshold: f64,
    direction: MetricDirection,
) -> MetricChange {
    let absolute_improvement = match direction {
        MetricDirection::HigherIsBetter => candidate - baseline,
        MetricDirection::LowerIsBetter => baseline - candidate,
    };
    let relative_improvement = if baseline == 0.0 {
        None
    } else {
        Some(absolute_improvement / baseline.abs())
    };
    let materiality = if matches!(direction, MetricDirection::HigherIsBetter) {
        classify_absolute(absolute_improvement, threshold)
    } else {
        classify_relative(absolute_improvement, relative_improvement, threshold)
    };
    MetricChange {
        baseline,
        candidate,
        absolute_improvement,
        relative_improvement,
        materiality,
    }
}

fn classify_absolute(improvement: f64, threshold: f64) -> Materiality {
    if improvement > 0.0 && improvement >= threshold {
        Materiality::Improvement
    } else if improvement < 0.0 && -improvement >= threshold {
        Materiality::Regression
    } else {
        Materiality::Neutral
    }
}

fn classify_relative(
    absolute_improvement: f64,
    relative_improvement: Option<f64>,
    threshold: f64,
) -> Materiality {
    match relative_improvement {
        Some(improvement) => classify_absolute(improvement, threshold),
        None if absolute_improvement > 0.0 => Materiality::Improvement,
        None if absolute_improvement < 0.0 => Materiality::Regression,
        None => Materiality::Neutral,
    }
}

fn compare_fidelity(
    baseline: HardwareFidelity,
    candidate: HardwareFidelity,
) -> HardwareFidelityComparison {
    let change = match fidelity_rank(candidate).cmp(&fidelity_rank(baseline)) {
        std::cmp::Ordering::Less => FidelityChange::LowerConfidence,
        std::cmp::Ordering::Equal => FidelityChange::Same,
        std::cmp::Ordering::Greater => FidelityChange::HigherConfidence,
    };
    HardwareFidelityComparison {
        baseline,
        candidate,
        change,
    }
}

const fn fidelity_rank(fidelity: HardwareFidelity) -> u8 {
    match fidelity {
        HardwareFidelity::Analytical => 0,
        HardwareFidelity::Architecture => 1,
        HardwareFidelity::Rtl => 2,
        HardwareFidelity::Measured => 3,
    }
}

fn attribution(baseline: &ProviderBaseline, candidate: &CandidateResult) -> AttributionReport {
    let candidate_economics = economics_values(&candidate.observables.costs);
    let total_gain = economics_values(&baseline.observables.costs).subtract(candidate_economics);
    let contributions: Vec<_> = candidate
        .ablations
        .iter()
        .map(|ablation| AxisContribution {
            axis: ablation.axis.clone(),
            gain: economics_values(&ablation.without_axis.costs).subtract(candidate_economics),
        })
        .collect();
    let explained = contributions
        .iter()
        .fold(EconomicGain::default(), |sum, contribution| {
            sum.add(contribution.gain)
        });
    AttributionReport {
        total_gain,
        contributions,
        interaction_residual: total_gain.subtract(explained),
    }
}

fn economics_values(report: &CostReport) -> EconomicGain {
    EconomicGain {
        input_cost: report.input.cost_per_million_tokens,
        output_cost: report.output.cost_per_million_tokens,
        input_minimum_price: report.input.minimum_price_per_million_tokens,
        output_minimum_price: report.output.minimum_price_per_million_tokens,
    }
}

fn relative_close(left: f64, right: f64) -> bool {
    close(left, right, 1e-9 * left.abs().max(right.abs()).max(1.0))
}

fn close(left: f64, right: f64, tolerance: f64) -> bool {
    (left - right).abs() <= tolerance
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::economics::{CostBreakdown, PhaseEconomics};

    #[test]
    fn compares_provider_economics_quality_latency_energy_and_fidelity() {
        let baseline = baseline();
        let candidate = candidate();

        let report = compare(&baseline, &candidate, thresholds()).unwrap();

        assert_eq!(report.input.cost.materiality, Materiality::Improvement);
        assert_eq!(
            report.output.minimum_sustainable_price.materiality,
            Materiality::Improvement
        );
        assert_eq!(report.quality[0].change.materiality, Materiality::Neutral);
        assert_eq!(report.latency.ttft.materiality, Materiality::Improvement);
        assert_eq!(report.latency.tpot.materiality, Materiality::Neutral);
        assert_eq!(report.energy.input.materiality, Materiality::Improvement);
        assert_eq!(
            report.hardware_fidelity.change,
            FidelityChange::HigherConfidence
        );
        assert!(report.compliance.baseline_meets_contract());
        assert!(report.compliance.candidate_meets_contract());
    }

    #[test]
    fn rejects_incompatible_model_tokenizer_quality_and_slo_contracts() {
        let baseline = baseline();

        let mut different_model = candidate();
        different_model.contract.model_revision = "other".into();
        assert_mismatch(&baseline, &different_model, ContractDimension::Model);

        let mut different_tokenizer = candidate();
        different_tokenizer.contract.tokenizer_id = "other".into();
        assert_mismatch(
            &baseline,
            &different_tokenizer,
            ContractDimension::Tokenizer,
        );

        let mut different_quality = candidate();
        different_quality.contract.quality.requirements[0].threshold = 0.8;
        assert_mismatch(&baseline, &different_quality, ContractDimension::Quality);

        let mut different_slo = candidate();
        different_slo.contract.slo.ttft.maximum_milliseconds = 90.0;
        assert_mismatch(&baseline, &different_slo, ContractDimension::Slo);
    }

    #[test]
    fn configurable_thresholds_classify_improvements_and_regressions() {
        let baseline = baseline();
        let mut candidate = candidate();
        candidate.observables.costs.input = phase(1.85);
        candidate.observables.costs.total_cost_usd = 4.35;
        candidate.observables.costs.allocated_cost_usd = 4.35;

        let report = compare(&baseline, &candidate, thresholds()).unwrap();
        assert_eq!(report.input.cost.materiality, Materiality::Neutral);

        let mut strict = thresholds();
        strict.cost_relative = 0.05;
        let report = compare(&baseline, &candidate, strict).unwrap();
        assert_eq!(report.input.cost.materiality, Materiality::Improvement);

        candidate.observables.ttft_milliseconds = 120.0;
        let report = compare(&baseline, &candidate, strict).unwrap();
        assert_eq!(report.latency.ttft.materiality, Materiality::Regression);
    }

    #[test]
    fn ablations_and_interaction_residual_reconcile_to_total_gain() {
        let report = compare(&baseline(), &candidate(), thresholds()).unwrap();

        assert_eq!(report.attribution.contributions.len(), 2);
        assert!((report.attribution.contributions[0].gain.input_cost - 0.4).abs() < 1e-12);
        assert!((report.attribution.contributions[1].gain.input_cost - 0.3).abs() < 1e-12);
        assert!((report.attribution.interaction_residual.input_cost - 0.3).abs() < 1e-12);
        assert!((report.attribution.interaction_residual.output_cost - 0.7).abs() < 1e-12);
        assert!(report.attribution.reconciles(1e-12));
    }

    #[test]
    fn duplicate_ablation_axes_are_rejected() {
        let mut candidate = candidate();
        candidate.ablations[1].axis = OptimizationAxis::Model;

        assert!(matches!(
            compare(&baseline(), &candidate, thresholds()),
            Err(ComparisonError::DuplicateAblationAxis(
                OptimizationAxis::Model
            ))
        ));
    }

    fn assert_mismatch(
        baseline: &ProviderBaseline,
        candidate: &CandidateResult,
        expected: ContractDimension,
    ) {
        assert_eq!(
            compare(baseline, candidate, thresholds()).unwrap_err(),
            ComparisonError::ContractMismatch(expected)
        );
    }

    fn baseline() -> ProviderBaseline {
        ProviderBaseline {
            provider_name: "tuned-vllm".into(),
            contract: contract(),
            observables: observables(2.0, 4.0, 0.8, 100.0, 50.0, 1_000.0, 2_000.0),
        }
    }

    fn candidate() -> CandidateResult {
        CandidateResult {
            candidate_name: "foundry-int4".into(),
            contract: contract(),
            observables: ObservableSummary {
                hardware_fidelity: HardwareFidelity::Measured,
                ..observables(1.0, 2.5, 0.805, 80.0, 48.0, 700.0, 1_400.0)
            },
            ablations: vec![
                AblationObservation {
                    axis: OptimizationAxis::Model,
                    without_axis: observables(1.4, 3.0, 0.8, 88.0, 49.0, 800.0, 1_600.0),
                },
                AblationObservation {
                    axis: OptimizationAxis::Kernel,
                    without_axis: observables(1.3, 2.8, 0.805, 86.0, 48.5, 760.0, 1_500.0),
                },
            ],
        }
    }

    fn contract() -> ComparisonContract {
        ComparisonContract {
            model_id: "Qwen/Qwen3-8B".into(),
            model_revision: "frozen-v1".into(),
            tokenizer_id: "Qwen/Qwen3-8B".into(),
            tokenizer_revision: "frozen-v1".into(),
            quality: QualityContract {
                suite: "agentic-v1".into(),
                seed: 11,
                requirements: vec![QualityRequirement {
                    metric: "task_success".into(),
                    threshold: 0.79,
                    direction: MetricDirection::HigherIsBetter,
                }],
            },
            slo: SloContract {
                ttft: LatencyObjective {
                    percentile: 99.0,
                    maximum_milliseconds: 120.0,
                },
                tpot: LatencyObjective {
                    percentile: 99.0,
                    maximum_milliseconds: 55.0,
                },
            },
        }
    }

    fn observables(
        input_cost: f64,
        output_cost: f64,
        quality_score: f64,
        ttft_milliseconds: f64,
        tpot_milliseconds: f64,
        input_energy: f64,
        output_energy: f64,
    ) -> ObservableSummary {
        ObservableSummary {
            costs: CostReport {
                input: phase(input_cost),
                output: phase(output_cost),
                target_gross_margin: 0.6,
                total_cost_usd: input_cost + output_cost,
                allocated_cost_usd: input_cost + output_cost,
                reconciliation_delta_usd: 0.0,
            },
            quality: vec![QualityMeasurement {
                metric: "task_success".into(),
                score: quality_score,
            }],
            ttft_milliseconds,
            tpot_milliseconds,
            input_energy_joules_per_million_tokens: input_energy,
            output_energy_joules_per_million_tokens: output_energy,
            hardware_fidelity: HardwareFidelity::Analytical,
        }
    }

    fn phase(cost: f64) -> PhaseEconomics {
        PhaseEconomics {
            tokens: 1_000_000,
            costs: CostBreakdown {
                hardware_usd: cost,
                ..CostBreakdown::default()
            },
            cost_per_million_tokens: cost,
            minimum_price_per_million_tokens: cost / 0.4,
        }
    }

    fn thresholds() -> MaterialityThresholds {
        MaterialityThresholds {
            cost_relative: 0.1,
            price_relative: 0.1,
            quality_absolute: 0.01,
            latency_relative: 0.1,
            energy_relative: 0.1,
        }
    }
}
