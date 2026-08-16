use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::action_ledger::{
    Action, ActionId, ActionLedger, ActionWork, CacheKeySpace, ComputeClass, EvidenceKind,
    LedgerError, MemoryTier, SchedulerDecision, SynchronizationKind,
};

pub const LEDGER_ROOFLINE_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const LEDGER_ROOFLINE_REPORT_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum HardwareTimingEvidenceKind {
    PublishedSpecification,
    MeasuredMicrobenchmark,
    ModeledAssumption,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HardwareTimingEvidence {
    pub kind: HardwareTimingEvidenceKind,
    pub source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ComputeEngineSpec {
    pub class: ComputeClass,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub action_ids: Option<Vec<String>>,
    pub flops_per_second: f64,
    pub non_flop_operations_per_second: f64,
    pub fixed_latency_seconds: f64,
    pub evidence: HardwareTimingEvidence,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ModelFormatContract {
    SelectiveExpertNvfp4,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelFormatSupportSpec {
    pub format: ModelFormatContract,
    pub native: bool,
    pub evidence: HardwareTimingEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MemoryPathTimingSpec {
    pub source: MemoryTier,
    pub destination: MemoryTier,
    pub bandwidth_bytes_per_second: f64,
    pub fixed_latency_seconds: f64,
    pub evidence: HardwareTimingEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CacheTimingSpec {
    pub tier: MemoryTier,
    pub key_space: Option<CacheKeySpace>,
    pub bandwidth_bytes_per_second: f64,
    pub fixed_latency_seconds: f64,
    pub evidence: HardwareTimingEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NetworkTimingSpec {
    pub aggregate_bandwidth_bytes_per_second: f64,
    pub fixed_latency_seconds: f64,
    pub latency_seconds_per_message: f64,
    pub evidence: HardwareTimingEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SynchronizationTimingSpec {
    pub fixed_latency_seconds: f64,
    pub latency_seconds_per_participant: f64,
    pub supported_kinds: Vec<SynchronizationKind>,
    pub evidence: HardwareTimingEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SchedulerTimingSpec {
    pub fixed_latency_seconds: f64,
    pub latency_seconds_per_request: f64,
    pub latency_seconds_per_token: f64,
    pub supported_decisions: Vec<SchedulerDecision>,
    pub evidence: HardwareTimingEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerHardwareTimingSpec {
    pub hardware_id: String,
    pub evidence: HardwareTimingEvidence,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub model_format_support: Vec<ModelFormatSupportSpec>,
    pub compute_engines: Vec<ComputeEngineSpec>,
    pub memory_paths: Vec<MemoryPathTimingSpec>,
    pub cache_tiers: Vec<CacheTimingSpec>,
    pub network: NetworkTimingSpec,
    pub synchronization: SynchronizationTimingSpec,
    pub scheduler: SchedulerTimingSpec,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerRooflineHardwarePlan {
    pub schema_version: u32,
    pub study_id: String,
    pub baseline_hardware_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub required_model_format: Option<ModelFormatContract>,
    pub hardware: Vec<LedgerHardwareTimingSpec>,
}

impl LedgerRooflineHardwarePlan {
    pub fn into_request(self, ledger: ActionLedger) -> LedgerRooflineRequest {
        LedgerRooflineRequest {
            schema_version: self.schema_version,
            study_id: self.study_id,
            baseline_hardware_id: self.baseline_hardware_id,
            required_model_format: self.required_model_format,
            ledger,
            hardware: self.hardware,
        }
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerRooflineRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub baseline_hardware_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub required_model_format: Option<ModelFormatContract>,
    pub ledger: ActionLedger,
    pub hardware: Vec<LedgerHardwareTimingSpec>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ActionRooflineTiming {
    pub action_id: String,
    pub fixed_component_seconds: f64,
    pub throughput_component_seconds: f64,
    pub coordination_component_seconds: f64,
    pub modeled_duration_seconds: f64,
    pub earliest_start_seconds: f64,
    pub earliest_finish_seconds: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HardwareRooflineReport {
    pub hardware_id: String,
    pub evidence: HardwareTimingEvidence,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub required_model_format_support: Option<ModelFormatSupportSpec>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub execution_blockers: Vec<HardwareExecutionBlocker>,
    pub action_timings: Vec<ActionRooflineTiming>,
    pub optimistic_critical_path_seconds: f64,
    pub serial_action_seconds: f64,
    pub optimistic_committed_tokens_per_second: f64,
    pub relative_ideal_speedup_vs_baseline: f64,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum HardwareExecutionBlocker {
    RequiredModelFormatNotNativelySupported,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum LedgerRooflineClaimBlocker {
    LedgerContainsAssumptions,
    HardwareTimingIsNotCalibrated,
    HardwareExecutionUnsupported,
    SharedResourceContentionIsNotModeled,
    ServingAndQueueingAreNotModeled,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerRooflineClaimGate {
    pub end_to_end_latency_claim_permitted: bool,
    pub energy_claim_permitted: bool,
    pub cost_per_token_claim_permitted: bool,
    pub blockers: Vec<LedgerRooflineClaimBlocker>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerRooflineResult {
    pub study_id: String,
    pub ledger_content_id: String,
    pub baseline_hardware_id: String,
    pub committed_tokens: u64,
    pub hardware: Vec<HardwareRooflineReport>,
    pub claims: LedgerRooflineClaimGate,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerRooflineReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: LedgerRooflineResult,
}

impl LedgerRooflineReport {
    pub fn verify_content_id(&self) -> Result<bool, LedgerRooflineError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

pub fn evaluate_ledger_roofline(
    request: &LedgerRooflineRequest,
) -> Result<LedgerRooflineReport, LedgerRooflineError> {
    validate_request(request)?;
    let ledger_content_id = request.ledger.content_id()?.as_str().to_owned();
    let mut hardware = request
        .hardware
        .iter()
        .map(|spec| evaluate_hardware(&request.ledger, spec, request.required_model_format))
        .collect::<Result<Vec<_>, _>>()?;
    let baseline_seconds = hardware
        .iter()
        .find(|report| report.hardware_id == request.baseline_hardware_id)
        .ok_or(LedgerRooflineError::MissingBaselineHardware)?
        .optimistic_critical_path_seconds;
    for report in &mut hardware {
        report.relative_ideal_speedup_vs_baseline =
            baseline_seconds / report.optimistic_critical_path_seconds;
    }
    let result = LedgerRooflineResult {
        study_id: request.study_id.clone(),
        ledger_content_id,
        baseline_hardware_id: request.baseline_hardware_id.clone(),
        committed_tokens: request.ledger.provenance.phase.committed_tokens,
        hardware,
        claims: claim_gate(request),
    };
    let schema_version = LEDGER_ROOFLINE_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(LedgerRooflineReport {
        schema_version,
        content_id,
        result,
    })
}

fn validate_request(request: &LedgerRooflineRequest) -> Result<(), LedgerRooflineError> {
    if request.schema_version != LEDGER_ROOFLINE_REQUEST_SCHEMA_VERSION {
        return Err(LedgerRooflineError::UnsupportedSchemaVersion {
            expected: LEDGER_ROOFLINE_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    validate_required("study_id", &request.study_id)?;
    validate_required("baseline_hardware_id", &request.baseline_hardware_id)?;
    request.ledger.validate()?;
    if request.hardware.is_empty() {
        return Err(LedgerRooflineError::InvalidField("hardware"));
    }
    let mut ids = BTreeSet::new();
    for hardware in &request.hardware {
        if !ids.insert(hardware.hardware_id.as_str()) {
            return Err(LedgerRooflineError::DuplicateHardware(
                hardware.hardware_id.clone(),
            ));
        }
        validate_hardware(hardware)?;
        validate_compute_coverage(&request.ledger, hardware)?;
    }
    if !ids.contains(request.baseline_hardware_id.as_str()) {
        return Err(LedgerRooflineError::MissingBaselineHardware);
    }
    if let Some(required) = request.required_model_format {
        for hardware in &request.hardware {
            if hardware
                .model_format_support
                .iter()
                .all(|support| support.format != required)
            {
                return Err(LedgerRooflineError::MissingModelFormatSupport {
                    hardware_id: hardware.hardware_id.clone(),
                    format: required,
                });
            }
        }
        let baseline = request
            .hardware
            .iter()
            .find(|hardware| hardware.hardware_id == request.baseline_hardware_id)
            .ok_or(LedgerRooflineError::MissingBaselineHardware)?;
        if !baseline
            .model_format_support
            .iter()
            .any(|support| support.format == required && support.native)
        {
            return Err(LedgerRooflineError::UnsupportedBaselineModelFormat(
                required,
            ));
        }
    }
    Ok(())
}

fn validate_hardware(hardware: &LedgerHardwareTimingSpec) -> Result<(), LedgerRooflineError> {
    validate_required("hardware.hardware_id", &hardware.hardware_id)?;
    validate_evidence("hardware.evidence", &hardware.evidence)?;
    if hardware.compute_engines.is_empty() {
        return Err(LedgerRooflineError::InvalidField(
            "hardware.compute_engines",
        ));
    }
    let mut formats = BTreeSet::new();
    for support in &hardware.model_format_support {
        if !formats.insert(support.format) {
            return Err(LedgerRooflineError::InvalidField(
                "hardware.model_format_support",
            ));
        }
        validate_evidence("hardware.model_format_support.evidence", &support.evidence)?;
    }
    for (index, engine) in hardware.compute_engines.iter().enumerate() {
        if let Some(action_ids) = &engine.action_ids {
            if action_ids.is_empty()
                || action_ids
                    .iter()
                    .any(|action_id| action_id.trim().is_empty())
                || action_ids.iter().enumerate().any(|(position, action_id)| {
                    action_ids[..position].iter().any(|seen| seen == action_id)
                })
            {
                return Err(LedgerRooflineError::InvalidField(
                    "hardware.compute_engines.action_ids",
                ));
            }
        }
        for seen in &hardware.compute_engines[..index] {
            if seen.class != engine.class {
                continue;
            }
            let disjoint = match (&seen.action_ids, &engine.action_ids) {
                (Some(left), Some(right)) => {
                    left.iter().all(|action_id| !right.contains(action_id))
                }
                _ => false,
            };
            if !disjoint {
                return Err(LedgerRooflineError::InvalidField(
                    "hardware.compute_engines",
                ));
            }
        }
        validate_positive(
            "hardware.compute_engines.flops_per_second",
            engine.flops_per_second,
        )?;
        validate_positive(
            "hardware.compute_engines.non_flop_operations_per_second",
            engine.non_flop_operations_per_second,
        )?;
        validate_nonnegative(
            "hardware.compute_engines.fixed_latency_seconds",
            engine.fixed_latency_seconds,
        )?;
        validate_evidence("hardware.compute_engines.evidence", &engine.evidence)?;
    }
    for (index, path) in hardware.memory_paths.iter().enumerate() {
        if hardware.memory_paths[..index]
            .iter()
            .any(|seen| seen.source == path.source && seen.destination == path.destination)
        {
            return Err(LedgerRooflineError::InvalidField("hardware.memory_paths"));
        }
        validate_positive(
            "hardware.memory_paths.bandwidth_bytes_per_second",
            path.bandwidth_bytes_per_second,
        )?;
        validate_nonnegative(
            "hardware.memory_paths.fixed_latency_seconds",
            path.fixed_latency_seconds,
        )?;
        validate_evidence("hardware.memory_paths.evidence", &path.evidence)?;
    }
    for (index, cache) in hardware.cache_tiers.iter().enumerate() {
        if hardware.cache_tiers[..index]
            .iter()
            .any(|seen| seen.tier == cache.tier && seen.key_space == cache.key_space)
        {
            return Err(LedgerRooflineError::InvalidField("hardware.cache_tiers"));
        }
        validate_positive(
            "hardware.cache_tiers.bandwidth_bytes_per_second",
            cache.bandwidth_bytes_per_second,
        )?;
        validate_nonnegative(
            "hardware.cache_tiers.fixed_latency_seconds",
            cache.fixed_latency_seconds,
        )?;
        validate_evidence("hardware.cache_tiers.evidence", &cache.evidence)?;
    }
    validate_positive(
        "hardware.network.aggregate_bandwidth_bytes_per_second",
        hardware.network.aggregate_bandwidth_bytes_per_second,
    )?;
    validate_nonnegative(
        "hardware.network.fixed_latency_seconds",
        hardware.network.fixed_latency_seconds,
    )?;
    validate_nonnegative(
        "hardware.network.latency_seconds_per_message",
        hardware.network.latency_seconds_per_message,
    )?;
    validate_evidence("hardware.network.evidence", &hardware.network.evidence)?;
    if hardware.synchronization.supported_kinds.is_empty() {
        return Err(LedgerRooflineError::InvalidField(
            "hardware.synchronization.supported_kinds",
        ));
    }
    validate_nonnegative(
        "hardware.synchronization.fixed_latency_seconds",
        hardware.synchronization.fixed_latency_seconds,
    )?;
    validate_nonnegative(
        "hardware.synchronization.latency_seconds_per_participant",
        hardware.synchronization.latency_seconds_per_participant,
    )?;
    validate_evidence(
        "hardware.synchronization.evidence",
        &hardware.synchronization.evidence,
    )?;
    if hardware.scheduler.supported_decisions.is_empty() {
        return Err(LedgerRooflineError::InvalidField(
            "hardware.scheduler.supported_decisions",
        ));
    }
    for (field, value) in [
        (
            "hardware.scheduler.fixed_latency_seconds",
            hardware.scheduler.fixed_latency_seconds,
        ),
        (
            "hardware.scheduler.latency_seconds_per_request",
            hardware.scheduler.latency_seconds_per_request,
        ),
        (
            "hardware.scheduler.latency_seconds_per_token",
            hardware.scheduler.latency_seconds_per_token,
        ),
    ] {
        validate_nonnegative(field, value)?;
    }
    validate_evidence("hardware.scheduler.evidence", &hardware.scheduler.evidence)
}

fn validate_compute_coverage(
    ledger: &ActionLedger,
    hardware: &LedgerHardwareTimingSpec,
) -> Result<(), LedgerRooflineError> {
    let compute_actions = ledger
        .actions
        .iter()
        .filter_map(|action| match &action.work {
            ActionWork::Compute(work) => Some((action, work)),
            _ => None,
        })
        .collect::<Vec<_>>();
    for engine in &hardware.compute_engines {
        if let Some(action_ids) = &engine.action_ids {
            for action_id in action_ids {
                if compute_actions
                    .iter()
                    .find(|(action, _)| action.id.as_str() == action_id)
                    .is_some_and(|(_, work)| work.class != engine.class)
                {
                    return Err(LedgerRooflineError::InvalidField(
                        "hardware.compute_engines.action_ids",
                    ));
                }
            }
        }
    }
    for (action, work) in compute_actions {
        let matches = hardware
            .compute_engines
            .iter()
            .filter(|engine| compute_engine_matches(engine, action.id.as_str(), work.class))
            .count();
        match matches {
            1 => {}
            0 => {
                return Err(LedgerRooflineError::MissingComputeEngineForAction(
                    action.id.as_str().to_owned(),
                ));
            }
            _ => {
                return Err(LedgerRooflineError::AmbiguousComputeEngineForAction(
                    action.id.as_str().to_owned(),
                ));
            }
        }
    }
    Ok(())
}

fn compute_engine_matches(
    engine: &ComputeEngineSpec,
    action_id: &str,
    class: ComputeClass,
) -> bool {
    engine.class == class
        && engine
            .action_ids
            .as_ref()
            .is_none_or(|action_ids| action_ids.iter().any(|candidate| candidate == action_id))
}

fn evaluate_hardware(
    ledger: &ActionLedger,
    hardware: &LedgerHardwareTimingSpec,
    required_model_format: Option<ModelFormatContract>,
) -> Result<HardwareRooflineReport, LedgerRooflineError> {
    let actions = ledger
        .actions
        .iter()
        .map(|action| (action.id.clone(), action))
        .collect::<BTreeMap<_, _>>();
    let mut finishes = BTreeMap::<ActionId, f64>::new();
    let mut action_timings = Vec::with_capacity(ledger.actions.len());
    let mut serial_action_seconds = 0.0;
    for action_id in ledger.topological_action_ids()? {
        let action = actions
            .get(&action_id)
            .ok_or(LedgerRooflineError::ArithmeticOverflow)?;
        let components = action_components(action, hardware)?;
        let earliest_start = action
            .dependencies
            .iter()
            .map(|dependency| {
                finishes
                    .get(dependency)
                    .copied()
                    .ok_or(LedgerRooflineError::ArithmeticOverflow)
            })
            .collect::<Result<Vec<_>, _>>()?
            .into_iter()
            .fold(0.0, f64::max);
        let duration = components.fixed + components.throughput + components.coordination;
        let earliest_finish = earliest_start + duration;
        if !duration.is_finite() || duration <= 0.0 || !earliest_finish.is_finite() {
            return Err(LedgerRooflineError::ArithmeticOverflow);
        }
        serial_action_seconds += duration;
        if !serial_action_seconds.is_finite() {
            return Err(LedgerRooflineError::ArithmeticOverflow);
        }
        finishes.insert(action_id.clone(), earliest_finish);
        action_timings.push(ActionRooflineTiming {
            action_id: action_id.as_str().to_owned(),
            fixed_component_seconds: components.fixed,
            throughput_component_seconds: components.throughput,
            coordination_component_seconds: components.coordination,
            modeled_duration_seconds: duration,
            earliest_start_seconds: earliest_start,
            earliest_finish_seconds: earliest_finish,
        });
    }
    let optimistic_critical_path_seconds = finishes.values().copied().fold(0.0, f64::max);
    if optimistic_critical_path_seconds <= 0.0 || !optimistic_critical_path_seconds.is_finite() {
        return Err(LedgerRooflineError::ArithmeticOverflow);
    }
    let required_model_format_support = required_model_format.and_then(|required| {
        hardware
            .model_format_support
            .iter()
            .find(|support| support.format == required)
            .cloned()
    });
    let execution_blockers = required_model_format_support
        .as_ref()
        .is_some_and(|support| !support.native)
        .then_some(HardwareExecutionBlocker::RequiredModelFormatNotNativelySupported)
        .into_iter()
        .collect();
    Ok(HardwareRooflineReport {
        hardware_id: hardware.hardware_id.clone(),
        evidence: hardware.evidence.clone(),
        required_model_format_support,
        execution_blockers,
        action_timings,
        optimistic_critical_path_seconds,
        serial_action_seconds,
        optimistic_committed_tokens_per_second: ledger.provenance.phase.committed_tokens as f64
            / optimistic_critical_path_seconds,
        relative_ideal_speedup_vs_baseline: 0.0,
    })
}

struct TimingComponents {
    fixed: f64,
    throughput: f64,
    coordination: f64,
}

fn action_components(
    action: &Action,
    hardware: &LedgerHardwareTimingSpec,
) -> Result<TimingComponents, LedgerRooflineError> {
    match &action.work {
        ActionWork::Compute(work) => {
            let engine = hardware
                .compute_engines
                .iter()
                .find(|engine| compute_engine_matches(engine, action.id.as_str(), work.class))
                .ok_or_else(|| {
                    LedgerRooflineError::MissingComputeEngineForAction(
                        action.id.as_str().to_owned(),
                    )
                })?;
            Ok(TimingComponents {
                fixed: engine.fixed_latency_seconds,
                throughput: (work.flops.get() as f64 / engine.flops_per_second).max(
                    work.non_flop_operations.get() as f64 / engine.non_flop_operations_per_second,
                ),
                coordination: 0.0,
            })
        }
        ActionWork::Memory(work) => {
            let path = hardware
                .memory_paths
                .iter()
                .find(|path| path.source == work.source && path.destination == work.destination)
                .ok_or(LedgerRooflineError::MissingMemoryPath {
                    source_tier: work.source,
                    destination_tier: work.destination,
                })?;
            Ok(TimingComponents {
                fixed: path.fixed_latency_seconds,
                throughput: work.bytes.get() as f64 / path.bandwidth_bytes_per_second,
                coordination: 0.0,
            })
        }
        ActionWork::Cache(work) => {
            let timing = hardware
                .cache_tiers
                .iter()
                .find(|timing| timing.tier == work.tier && timing.key_space == Some(work.key_space))
                .or_else(|| {
                    hardware
                        .cache_tiers
                        .iter()
                        .find(|timing| timing.tier == work.tier && timing.key_space.is_none())
                })
                .ok_or(LedgerRooflineError::MissingCacheTiming {
                    tier: work.tier,
                    key_space: work.key_space,
                })?;
            Ok(TimingComponents {
                fixed: timing.fixed_latency_seconds,
                throughput: work.bytes.get() as f64 / timing.bandwidth_bytes_per_second,
                coordination: 0.0,
            })
        }
        ActionWork::Network(work) => Ok(TimingComponents {
            fixed: hardware.network.fixed_latency_seconds,
            throughput: work.aggregate_bytes.get() as f64
                / hardware.network.aggregate_bandwidth_bytes_per_second,
            coordination: work.messages.get() as f64 * hardware.network.latency_seconds_per_message,
        }),
        ActionWork::Synchronization(work) => {
            if !hardware
                .synchronization
                .supported_kinds
                .contains(&work.kind)
            {
                return Err(LedgerRooflineError::UnsupportedSynchronization(work.kind));
            }
            Ok(TimingComponents {
                fixed: hardware.synchronization.fixed_latency_seconds,
                throughput: 0.0,
                coordination: f64::from(work.participants)
                    * hardware.synchronization.latency_seconds_per_participant,
            })
        }
        ActionWork::Scheduler(work) => {
            if !hardware
                .scheduler
                .supported_decisions
                .contains(&work.decision)
            {
                return Err(LedgerRooflineError::UnsupportedSchedulerDecision(
                    work.decision,
                ));
            }
            Ok(TimingComponents {
                fixed: hardware.scheduler.fixed_latency_seconds,
                throughput: 0.0,
                coordination: f64::from(work.requests)
                    * hardware.scheduler.latency_seconds_per_request
                    + work.tokens as f64 * hardware.scheduler.latency_seconds_per_token,
            })
        }
    }
}

fn claim_gate(request: &LedgerRooflineRequest) -> LedgerRooflineClaimGate {
    let mut blockers = Vec::new();
    if request
        .ledger
        .actions
        .iter()
        .any(|action| action.evidence.kind == EvidenceKind::Assumption)
    {
        blockers.push(LedgerRooflineClaimBlocker::LedgerContainsAssumptions);
    }
    if request.hardware.iter().any(|hardware| {
        hardware.evidence.kind != HardwareTimingEvidenceKind::MeasuredMicrobenchmark
            || hardware.compute_engines.iter().any(|value| {
                value.evidence.kind != HardwareTimingEvidenceKind::MeasuredMicrobenchmark
            })
            || hardware.memory_paths.iter().any(|value| {
                value.evidence.kind != HardwareTimingEvidenceKind::MeasuredMicrobenchmark
            })
            || hardware.cache_tiers.iter().any(|value| {
                value.evidence.kind != HardwareTimingEvidenceKind::MeasuredMicrobenchmark
            })
            || hardware.network.evidence.kind != HardwareTimingEvidenceKind::MeasuredMicrobenchmark
            || hardware.synchronization.evidence.kind
                != HardwareTimingEvidenceKind::MeasuredMicrobenchmark
            || hardware.scheduler.evidence.kind
                != HardwareTimingEvidenceKind::MeasuredMicrobenchmark
    }) {
        blockers.push(LedgerRooflineClaimBlocker::HardwareTimingIsNotCalibrated);
    }
    if request.required_model_format.is_some_and(|required| {
        request.hardware.iter().any(|hardware| {
            hardware
                .model_format_support
                .iter()
                .any(|support| support.format == required && !support.native)
        })
    }) {
        blockers.push(LedgerRooflineClaimBlocker::HardwareExecutionUnsupported);
    }
    blockers.push(LedgerRooflineClaimBlocker::SharedResourceContentionIsNotModeled);
    blockers.push(LedgerRooflineClaimBlocker::ServingAndQueueingAreNotModeled);
    LedgerRooflineClaimGate {
        end_to_end_latency_claim_permitted: false,
        energy_claim_permitted: false,
        cost_per_token_claim_permitted: false,
        blockers,
    }
}

fn validate_evidence(
    field: &'static str,
    evidence: &HardwareTimingEvidence,
) -> Result<(), LedgerRooflineError> {
    validate_required(field, &evidence.source_artifact_id)
}

fn validate_required(field: &'static str, value: &str) -> Result<(), LedgerRooflineError> {
    if value.trim().is_empty() {
        Err(LedgerRooflineError::InvalidField(field))
    } else {
        Ok(())
    }
}

fn validate_positive(field: &'static str, value: f64) -> Result<(), LedgerRooflineError> {
    if value.is_finite() && value > 0.0 {
        Ok(())
    } else {
        Err(LedgerRooflineError::InvalidField(field))
    }
}

fn validate_nonnegative(field: &'static str, value: f64) -> Result<(), LedgerRooflineError> {
    if value.is_finite() && value >= 0.0 {
        Ok(())
    } else {
        Err(LedgerRooflineError::InvalidField(field))
    }
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a LedgerRooflineResult,
}

fn report_content_id(
    schema_version: u32,
    result: &LedgerRooflineResult,
) -> Result<String, LedgerRooflineError> {
    let bytes = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|error| LedgerRooflineError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Debug, Error)]
pub enum LedgerRooflineError {
    #[error("unsupported ledger roofline schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid ledger roofline field {0}")]
    InvalidField(&'static str),
    #[error("duplicate hardware timing specification {0}")]
    DuplicateHardware(String),
    #[error("the baseline hardware timing specification is missing")]
    MissingBaselineHardware,
    #[error("hardware {hardware_id} has no support declaration for {format:?}")]
    MissingModelFormatSupport {
        hardware_id: String,
        format: ModelFormatContract,
    },
    #[error("baseline hardware does not natively support {0:?}")]
    UnsupportedBaselineModelFormat(ModelFormatContract),
    #[error("hardware has no compute engine for action {0}")]
    MissingComputeEngineForAction(String),
    #[error("hardware has multiple compute engines for action {0}")]
    AmbiguousComputeEngineForAction(String),
    #[error("hardware has no memory path from {source_tier:?} to {destination_tier:?}")]
    MissingMemoryPath {
        source_tier: MemoryTier,
        destination_tier: MemoryTier,
    },
    #[error("hardware has no cache timing for {tier:?} and {key_space:?}")]
    MissingCacheTiming {
        tier: MemoryTier,
        key_space: CacheKeySpace,
    },
    #[error("hardware does not support synchronization kind {0:?}")]
    UnsupportedSynchronization(SynchronizationKind),
    #[error("hardware does not support scheduler decision {0:?}")]
    UnsupportedSchedulerDecision(SchedulerDecision),
    #[error("ledger roofline arithmetic overflowed")]
    ArithmeticOverflow,
    #[error("action ledger is invalid: {0}")]
    Ledger(#[from] LedgerError),
    #[error("ledger roofline serialization failed: {0}")]
    Serialization(String),
}
