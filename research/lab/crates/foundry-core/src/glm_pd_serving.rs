use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::glm_storage::{ByteBounds, EnvelopeEvidence};
use crate::ledger_roofline::HardwareTimingEvidence;
use crate::workload::{
    AgentTurnClass, CanonicalTraceV2, RequestTimingObservation, TraceObservations,
    WorkloadContractV2, WorkloadError, WorkloadSloReport, evaluate_trace,
};

pub const GLM_PD_SERVING_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const GLM_PD_SERVING_REPORT_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ServiceStage {
    Prefill,
    KvTransfer,
    Decode,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SchedulingDiscipline {
    Fifo,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SchedulingContract {
    pub discipline: SchedulingDiscipline,
    pub continuous_batching: bool,
    pub prefill_batch_size: u32,
    pub decode_batch_size: u32,
    pub decode_quantum_tokens: u32,
    pub aggregated_stage_priority: Vec<ServiceStage>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FixedFleetBudget {
    pub total_device_slots: u32,
    pub usd_per_device_hour: f64,
    pub evidence: HardwareTimingEvidence,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ContextTokenRateBand {
    pub max_context_tokens_inclusive: u64,
    pub tokens_per_second: u64,
    pub evidence: HardwareTimingEvidence,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TokenStageProfile {
    pub fixed_job_microseconds: u64,
    pub context_bands: Vec<ContextTokenRateBand>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ByteStageProfile {
    pub fixed_job_microseconds: u64,
    pub bytes_per_second: u64,
    pub evidence: HardwareTimingEvidence,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NeutralServiceRateProfile {
    pub prefill: TokenStageProfile,
    pub decode: TokenStageProfile,
    pub kv_transfer: ByteStageProfile,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExplicitRateEffect {
    pub multiplier_basis_points: u32,
    pub evidence: HardwareTimingEvidence,
    pub basis: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct StageRateEffects {
    pub effect_id: String,
    pub aggregated_prefill: ExplicitRateEffect,
    pub aggregated_decode: ExplicitRateEffect,
    pub disaggregated_prefill: ExplicitRateEffect,
    pub disaggregated_transfer: ExplicitRateEffect,
    pub disaggregated_decode: ExplicitRateEffect,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct KvTransferEnvelope {
    pub bytes_per_token: ByteBounds,
    pub evidence: EnvelopeEvidence,
    pub basis: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TransferEndpoint {
    DeltaLower,
    FullUpper,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AggregatedControl {
    pub worker_count: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PdPoolSplit {
    pub split_id: String,
    pub prefill_workers: u32,
    pub transfer_workers: u32,
    pub decode_workers: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DisaggregatedSweep {
    pub splits: Vec<PdPoolSplit>,
    pub transfer_endpoints: Vec<TransferEndpoint>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MechanismTargetRole {
    MechanismOnly,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MechanismTarget {
    pub target_id: String,
    pub source_artifact_id: String,
    pub mechanism: String,
    pub role: MechanismTargetRole,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmPdServingRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub workload_contract: WorkloadContractV2,
    pub trace: CanonicalTraceV2,
    pub budget: FixedFleetBudget,
    pub scheduling: SchedulingContract,
    pub service_rates: NeutralServiceRateProfile,
    pub kv_transfer: KvTransferEnvelope,
    pub aggregated: AggregatedControl,
    pub disaggregated: DisaggregatedSweep,
    pub effect_scenarios: Vec<StageRateEffects>,
    #[serde(default)]
    pub mechanism_targets: Vec<MechanismTarget>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ServingLayout {
    Aggregated,
    Disaggregated,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CasePoolAllocation {
    pub total_device_slots: u32,
    pub aggregated_workers: u32,
    pub prefill_workers: u32,
    pub transfer_workers: u32,
    pub decode_workers: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct StageTiming {
    pub ready_timestamp_microseconds: u64,
    pub start_timestamp_microseconds: u64,
    pub completion_timestamp_microseconds: u64,
    pub queue_microseconds: u64,
    pub service_microseconds: u64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ServingRequestResult {
    pub request_id: u64,
    pub class: AgentTurnClass,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub prefix_reused_tokens: u32,
    pub uncached_input_tokens: u32,
    pub kv_transfer_bytes: u64,
    pub arrival_timestamp_microseconds: u64,
    pub first_token_timestamp_microseconds: u64,
    pub completion_timestamp_microseconds: u64,
    pub ttft_milliseconds: f64,
    pub tpot_milliseconds: f64,
    pub meets_slo: bool,
    pub prefill: Option<StageTiming>,
    pub kv_transfer: Option<StageTiming>,
    pub decode_queue_microseconds: u64,
    pub decode_service_microseconds: u64,
    pub kv_transfer_queue_microseconds: u64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct StageActivity {
    pub stage: ServiceStage,
    pub worker_count: u32,
    pub jobs: u64,
    pub tokens: u64,
    pub bytes: u64,
    pub busy_microseconds: u64,
    pub capacity_microseconds: u64,
    pub utilization: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PoolActivity {
    pub pool_id: String,
    pub worker_count: u32,
    pub busy_microseconds: u64,
    pub capacity_microseconds: u64,
    pub utilization: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ServingCaseAggregate {
    pub request_count: u64,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub duration_microseconds: u64,
    pub output_tokens_per_second: f64,
    pub goodput_requests_per_second: f64,
    pub goodput_output_tokens_per_second: f64,
    pub cost_per_million_output_tokens_usd: f64,
    pub slo_goodput_cost_per_million_output_tokens_usd: Option<f64>,
    pub mean_queue_milliseconds: f64,
    pub p95_queue_milliseconds: f64,
    pub hourly_budget_usd: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ServingCaseReport {
    pub case_id: String,
    pub layout: ServingLayout,
    pub effect_id: String,
    pub split_id: Option<String>,
    pub transfer_endpoint: Option<TransferEndpoint>,
    pub allocation: CasePoolAllocation,
    pub aggregate: ServingCaseAggregate,
    pub stage_activity: Vec<StageActivity>,
    pub pool_activity: Vec<PoolActivity>,
    pub slo: WorkloadSloReport,
    pub requests: Vec<ServingRequestResult>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum GlmPdServingClaimBlocker {
    EndToEndCalibrationMissing,
    KvTransferIsBounded,
    RateEffectsAreUncalibrated,
    ContinuousBatchingExcluded,
    ResidencyAndFailuresExcluded,
    ProviderReportsAreMechanismOnly,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmPdServingClaimGate {
    pub end_to_end_latency_claim_permitted: bool,
    pub slo_claim_permitted: bool,
    pub cost_per_token_claim_permitted: bool,
    pub blockers: Vec<GlmPdServingClaimBlocker>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmPdServingResult {
    pub study_id: String,
    pub workload_contract_id: String,
    pub trace_id: String,
    pub trace_content_id: String,
    pub budget: FixedFleetBudget,
    pub mechanism_targets: Vec<MechanismTarget>,
    pub cases: Vec<ServingCaseReport>,
    pub claims: GlmPdServingClaimGate,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmPdServingReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: GlmPdServingResult,
}

impl GlmPdServingReport {
    pub fn verify_content_id(&self) -> Result<bool, GlmPdServingError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

pub fn evaluate_glm_pd_serving(
    request: &GlmPdServingRequest,
) -> Result<GlmPdServingReport, GlmPdServingError> {
    validate_request(request)?;
    let mut cases = Vec::new();
    for effects in &request.effect_scenarios {
        cases.push(simulate_case(
            request,
            effects,
            CaseConfiguration::Aggregated,
        )?);
        for split in &request.disaggregated.splits {
            for endpoint in &request.disaggregated.transfer_endpoints {
                cases.push(simulate_case(
                    request,
                    effects,
                    CaseConfiguration::Disaggregated {
                        split,
                        endpoint: *endpoint,
                    },
                )?);
            }
        }
    }
    let result = GlmPdServingResult {
        study_id: request.study_id.clone(),
        workload_contract_id: request.workload_contract.contract_id.clone(),
        trace_id: request.trace.trace_id.clone(),
        trace_content_id: trace_content_id(&request.trace)?,
        budget: request.budget.clone(),
        mechanism_targets: request.mechanism_targets.clone(),
        cases,
        claims: claim_gate(),
    };
    let schema_version = GLM_PD_SERVING_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(GlmPdServingReport {
        schema_version,
        content_id,
        result,
    })
}

fn validate_request(request: &GlmPdServingRequest) -> Result<(), GlmPdServingError> {
    if request.schema_version != GLM_PD_SERVING_REQUEST_SCHEMA_VERSION {
        return Err(GlmPdServingError::UnsupportedSchemaVersion {
            expected: GLM_PD_SERVING_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    validate_required("study_id", &request.study_id)?;
    request.workload_contract.validate()?;
    request.trace.validate()?;
    if request.workload_contract.identity != request.trace.identity {
        return Err(GlmPdServingError::WorkloadIdentityMismatch);
    }
    if request.budget.total_device_slots == 0
        || !request.budget.usd_per_device_hour.is_finite()
        || request.budget.usd_per_device_hour <= 0.0
    {
        return Err(GlmPdServingError::InvalidField("budget"));
    }
    validate_hardware_evidence("budget.evidence", &request.budget.evidence)?;
    validate_scheduling(&request.scheduling)?;
    let max_context = request
        .trace
        .requests
        .iter()
        .map(|trace_request| {
            u64::from(trace_request.input_tokens)
                .checked_add(u64::from(trace_request.output_tokens))
                .ok_or(GlmPdServingError::ArithmeticOverflow)
        })
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .max()
        .ok_or(GlmPdServingError::InvalidField("trace.requests"))?;
    validate_token_profile(
        "service_rates.prefill",
        &request.service_rates.prefill,
        max_context,
    )?;
    validate_token_profile(
        "service_rates.decode",
        &request.service_rates.decode,
        max_context,
    )?;
    if request.service_rates.kv_transfer.bytes_per_second == 0 {
        return Err(GlmPdServingError::InvalidField(
            "service_rates.kv_transfer.bytes_per_second",
        ));
    }
    validate_hardware_evidence(
        "service_rates.kv_transfer.evidence",
        &request.service_rates.kv_transfer.evidence,
    )?;
    if request.kv_transfer.bytes_per_token.lower > request.kv_transfer.bytes_per_token.upper
        || request.kv_transfer.bytes_per_token.upper == 0
    {
        return Err(GlmPdServingError::InvalidField(
            "kv_transfer.bytes_per_token",
        ));
    }
    validate_required(
        "kv_transfer.evidence",
        &request.kv_transfer.evidence.source_artifact_id,
    )?;
    validate_required("kv_transfer.basis", &request.kv_transfer.basis)?;
    if request.aggregated.worker_count != request.budget.total_device_slots {
        return Err(GlmPdServingError::FleetBudgetMismatch);
    }
    validate_sweep(request)?;
    validate_effects(&request.effect_scenarios)?;
    validate_mechanism_targets(request)?;
    Ok(())
}

fn validate_scheduling(scheduling: &SchedulingContract) -> Result<(), GlmPdServingError> {
    if scheduling.discipline != SchedulingDiscipline::Fifo
        || scheduling.continuous_batching
        || scheduling.prefill_batch_size != 1
        || scheduling.decode_batch_size != 1
        || scheduling.decode_quantum_tokens != 1
        || scheduling.aggregated_stage_priority.len() != 2
        || !scheduling
            .aggregated_stage_priority
            .contains(&ServiceStage::Prefill)
        || !scheduling
            .aggregated_stage_priority
            .contains(&ServiceStage::Decode)
    {
        return Err(GlmPdServingError::UnsupportedSchedulingContract);
    }
    Ok(())
}

fn validate_token_profile(
    field: &'static str,
    profile: &TokenStageProfile,
    required_context: u64,
) -> Result<(), GlmPdServingError> {
    if profile.context_bands.is_empty() {
        return Err(GlmPdServingError::InvalidField(field));
    }
    let mut previous = 0_u64;
    for band in &profile.context_bands {
        if band.max_context_tokens_inclusive <= previous || band.tokens_per_second == 0 {
            return Err(GlmPdServingError::InvalidField(field));
        }
        validate_hardware_evidence(field, &band.evidence)?;
        previous = band.max_context_tokens_inclusive;
    }
    if previous < required_context {
        return Err(GlmPdServingError::ContextRateCoverageMissing {
            required_context,
            covered_context: previous,
        });
    }
    Ok(())
}

fn validate_sweep(request: &GlmPdServingRequest) -> Result<(), GlmPdServingError> {
    if request.disaggregated.splits.is_empty()
        || request.disaggregated.transfer_endpoints.is_empty()
    {
        return Err(GlmPdServingError::InvalidField("disaggregated"));
    }
    let mut splits = BTreeSet::new();
    for split in &request.disaggregated.splits {
        validate_required("disaggregated.splits.split_id", &split.split_id)?;
        if !splits.insert(split.split_id.as_str())
            || split.prefill_workers == 0
            || split.transfer_workers == 0
            || split.decode_workers == 0
        {
            return Err(GlmPdServingError::InvalidField("disaggregated.splits"));
        }
        let total = split
            .prefill_workers
            .checked_add(split.transfer_workers)
            .and_then(|value| value.checked_add(split.decode_workers))
            .ok_or(GlmPdServingError::ArithmeticOverflow)?;
        if total != request.budget.total_device_slots {
            return Err(GlmPdServingError::FleetBudgetMismatch);
        }
    }
    let mut endpoints = BTreeSet::new();
    for endpoint in &request.disaggregated.transfer_endpoints {
        if !endpoints.insert(*endpoint) {
            return Err(GlmPdServingError::InvalidField(
                "disaggregated.transfer_endpoints",
            ));
        }
    }
    Ok(())
}

fn validate_effects(effects: &[StageRateEffects]) -> Result<(), GlmPdServingError> {
    if effects.is_empty() {
        return Err(GlmPdServingError::InvalidField("effect_scenarios"));
    }
    let mut ids = BTreeSet::new();
    for effect_set in effects {
        validate_required("effect_scenarios.effect_id", &effect_set.effect_id)?;
        if !ids.insert(effect_set.effect_id.as_str()) {
            return Err(GlmPdServingError::InvalidField("effect_scenarios"));
        }
        for effect in [
            &effect_set.aggregated_prefill,
            &effect_set.aggregated_decode,
            &effect_set.disaggregated_prefill,
            &effect_set.disaggregated_transfer,
            &effect_set.disaggregated_decode,
        ] {
            if effect.multiplier_basis_points == 0 {
                return Err(GlmPdServingError::InvalidField(
                    "effect_scenarios.multiplier_basis_points",
                ));
            }
            validate_hardware_evidence("effect_scenarios.evidence", &effect.evidence)?;
            validate_required("effect_scenarios.basis", &effect.basis)?;
        }
    }
    Ok(())
}

fn validate_mechanism_targets(request: &GlmPdServingRequest) -> Result<(), GlmPdServingError> {
    let mut ids = BTreeSet::new();
    let mut sources = BTreeSet::new();
    for target in &request.mechanism_targets {
        for (field, value) in [
            ("mechanism_targets.target_id", target.target_id.as_str()),
            (
                "mechanism_targets.source_artifact_id",
                target.source_artifact_id.as_str(),
            ),
            ("mechanism_targets.mechanism", target.mechanism.as_str()),
        ] {
            validate_required(field, value)?;
        }
        if !ids.insert(target.target_id.as_str())
            || !sources.insert(target.source_artifact_id.as_str())
        {
            return Err(GlmPdServingError::InvalidField("mechanism_targets"));
        }
    }
    for source in rate_evidence_sources(request) {
        if sources.contains(source.as_str()) {
            return Err(GlmPdServingError::MechanismTargetUsedAsCalibration(source));
        }
    }
    Ok(())
}

fn rate_evidence_sources(request: &GlmPdServingRequest) -> Vec<String> {
    let mut sources = vec![
        request.budget.evidence.source_artifact_id.clone(),
        request
            .service_rates
            .kv_transfer
            .evidence
            .source_artifact_id
            .clone(),
        request.kv_transfer.evidence.source_artifact_id.clone(),
    ];
    for profile in [
        &request.service_rates.prefill,
        &request.service_rates.decode,
    ] {
        sources.extend(
            profile
                .context_bands
                .iter()
                .map(|band| band.evidence.source_artifact_id.clone()),
        );
    }
    for effects in &request.effect_scenarios {
        sources.extend(
            [
                &effects.aggregated_prefill,
                &effects.aggregated_decode,
                &effects.disaggregated_prefill,
                &effects.disaggregated_transfer,
                &effects.disaggregated_decode,
            ]
            .into_iter()
            .map(|effect| effect.evidence.source_artifact_id.clone()),
        );
    }
    sources
}

fn validate_hardware_evidence(
    field: &'static str,
    evidence: &HardwareTimingEvidence,
) -> Result<(), GlmPdServingError> {
    validate_required(field, &evidence.source_artifact_id)
}

fn validate_required(field: &'static str, value: &str) -> Result<(), GlmPdServingError> {
    if value.trim().is_empty() {
        Err(GlmPdServingError::InvalidField(field))
    } else {
        Ok(())
    }
}

#[derive(Clone, Copy)]
enum CaseConfiguration<'a> {
    Aggregated,
    Disaggregated {
        split: &'a PdPoolSplit,
        endpoint: TransferEndpoint,
    },
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
enum PoolKind {
    Aggregated,
    Prefill,
    Transfer,
    Decode,
}

#[derive(Clone, Copy, Debug)]
struct ReadyJob {
    ready_microseconds: u64,
    stage: ServiceStage,
    request_index: usize,
    token_ordinal: u32,
}

#[derive(Clone, Copy, Debug)]
struct RunningJob {
    job: ReadyJob,
    start_microseconds: u64,
    completion_microseconds: u64,
    service_microseconds: u64,
}

#[derive(Debug)]
struct WorkerPool {
    kind: PoolKind,
    workers: Vec<Option<RunningJob>>,
    busy_microseconds: u64,
}

impl WorkerPool {
    fn new(kind: PoolKind, worker_count: u32) -> Result<Self, GlmPdServingError> {
        let count = usize::try_from(worker_count).map_err(|_| GlmPdServingError::CountOverflow)?;
        Ok(Self {
            kind,
            workers: vec![None; count],
            busy_microseconds: 0,
        })
    }
}

#[derive(Debug)]
struct RequestSimulation {
    home_worker: Option<usize>,
    uncached_input_tokens: u32,
    kv_transfer_bytes: u64,
    prefill: Option<StageTiming>,
    kv_transfer: Option<StageTiming>,
    decode_queue_microseconds: u64,
    decode_service_microseconds: u64,
    first_token_microseconds: Option<u64>,
    completion_microseconds: Option<u64>,
}

#[derive(Clone, Copy, Debug, Default)]
struct ActivityAccumulator {
    jobs: u64,
    tokens: u64,
    bytes: u64,
    busy_microseconds: u64,
}

fn simulate_case(
    request: &GlmPdServingRequest,
    effects: &StageRateEffects,
    configuration: CaseConfiguration<'_>,
) -> Result<ServingCaseReport, GlmPdServingError> {
    let mut states = initialize_request_states(request, configuration)?;
    let mut pools = initialize_pools(request, configuration)?;
    let mut ready = Vec::new();
    let mut activity = BTreeMap::<ServiceStage, ActivityAccumulator>::new();
    let mut next_arrival = 0_usize;
    let mut current_microseconds = request.trace.requests[0].arrival_timestamp_microseconds;

    loop {
        complete_jobs(
            request,
            configuration,
            &mut pools,
            &mut states,
            &mut ready,
            current_microseconds,
        )?;
        enqueue_arrivals(
            request,
            configuration,
            &states,
            &mut ready,
            &mut next_arrival,
            current_microseconds,
        );
        dispatch_jobs(
            request,
            effects,
            configuration,
            &mut pools,
            &mut states,
            &mut ready,
            &mut activity,
            current_microseconds,
        )?;

        if states
            .iter()
            .all(|state| state.completion_microseconds.is_some())
        {
            break;
        }
        current_microseconds =
            next_event_timestamp(request, &pools, next_arrival, current_microseconds)?;
    }

    build_case_report(request, effects, configuration, states, pools, activity)
}

fn initialize_request_states(
    request: &GlmPdServingRequest,
    configuration: CaseConfiguration<'_>,
) -> Result<Vec<RequestSimulation>, GlmPdServingError> {
    request
        .trace
        .requests
        .iter()
        .map(|trace_request| {
            let uncached_input_tokens = trace_request
                .input_tokens
                .checked_sub(trace_request.prefix_reused_tokens)
                .ok_or(GlmPdServingError::ArithmeticOverflow)?;
            let kv_transfer_bytes = match configuration {
                CaseConfiguration::Aggregated => 0,
                CaseConfiguration::Disaggregated { endpoint, .. } => match endpoint {
                    TransferEndpoint::DeltaLower => u64::from(uncached_input_tokens)
                        .checked_mul(request.kv_transfer.bytes_per_token.lower)
                        .ok_or(GlmPdServingError::ArithmeticOverflow)?,
                    TransferEndpoint::FullUpper => u64::from(trace_request.input_tokens)
                        .checked_mul(request.kv_transfer.bytes_per_token.upper)
                        .ok_or(GlmPdServingError::ArithmeticOverflow)?,
                },
            };
            Ok(RequestSimulation {
                home_worker: None,
                uncached_input_tokens,
                kv_transfer_bytes,
                prefill: None,
                kv_transfer: None,
                decode_queue_microseconds: 0,
                decode_service_microseconds: 0,
                first_token_microseconds: None,
                completion_microseconds: None,
            })
        })
        .collect()
}

fn initialize_pools(
    request: &GlmPdServingRequest,
    configuration: CaseConfiguration<'_>,
) -> Result<Vec<WorkerPool>, GlmPdServingError> {
    match configuration {
        CaseConfiguration::Aggregated => Ok(vec![WorkerPool::new(
            PoolKind::Aggregated,
            request.aggregated.worker_count,
        )?]),
        CaseConfiguration::Disaggregated { split, .. } => Ok(vec![
            WorkerPool::new(PoolKind::Prefill, split.prefill_workers)?,
            WorkerPool::new(PoolKind::Transfer, split.transfer_workers)?,
            WorkerPool::new(PoolKind::Decode, split.decode_workers)?,
        ]),
    }
}

fn enqueue_arrivals(
    request: &GlmPdServingRequest,
    configuration: CaseConfiguration<'_>,
    states: &[RequestSimulation],
    ready: &mut Vec<ReadyJob>,
    next_arrival: &mut usize,
    current_microseconds: u64,
) {
    while request
        .trace
        .requests
        .get(*next_arrival)
        .is_some_and(|trace_request| {
            trace_request.arrival_timestamp_microseconds == current_microseconds
        })
    {
        let request_index = *next_arrival;
        let state = &states[request_index];
        let stage = if state.uncached_input_tokens > 0 {
            ServiceStage::Prefill
        } else if matches!(configuration, CaseConfiguration::Disaggregated { .. })
            && state.kv_transfer_bytes > 0
        {
            ServiceStage::KvTransfer
        } else {
            ServiceStage::Decode
        };
        ready.push(ReadyJob {
            ready_microseconds: current_microseconds,
            stage,
            request_index,
            token_ordinal: 0,
        });
        *next_arrival += 1;
    }
}

fn complete_jobs(
    request: &GlmPdServingRequest,
    configuration: CaseConfiguration<'_>,
    pools: &mut [WorkerPool],
    states: &mut [RequestSimulation],
    ready: &mut Vec<ReadyJob>,
    current_microseconds: u64,
) -> Result<(), GlmPdServingError> {
    let mut completions = Vec::new();
    for pool in pools.iter_mut() {
        for (worker_id, worker) in pool.workers.iter_mut().enumerate() {
            if worker
                .as_ref()
                .is_some_and(|running| running.completion_microseconds == current_microseconds)
            {
                let running = worker.take().ok_or(GlmPdServingError::SimulationStalled)?;
                completions.push((pool.kind, worker_id, running));
            }
        }
    }
    completions.sort_by_key(|(kind, worker_id, _)| (*kind, *worker_id));
    for (_, _, running) in completions {
        complete_job(
            request,
            configuration,
            states,
            ready,
            current_microseconds,
            running,
        )?;
    }
    Ok(())
}

fn complete_job(
    request: &GlmPdServingRequest,
    configuration: CaseConfiguration<'_>,
    states: &mut [RequestSimulation],
    ready: &mut Vec<ReadyJob>,
    current_microseconds: u64,
    running: RunningJob,
) -> Result<(), GlmPdServingError> {
    let state = &mut states[running.job.request_index];
    let timing = StageTiming {
        ready_timestamp_microseconds: running.job.ready_microseconds,
        start_timestamp_microseconds: running.start_microseconds,
        completion_timestamp_microseconds: running.completion_microseconds,
        queue_microseconds: running
            .start_microseconds
            .checked_sub(running.job.ready_microseconds)
            .ok_or(GlmPdServingError::ArithmeticOverflow)?,
        service_microseconds: running.service_microseconds,
    };
    match running.job.stage {
        ServiceStage::Prefill => {
            state.prefill = Some(timing);
            let stage = if matches!(configuration, CaseConfiguration::Disaggregated { .. })
                && state.kv_transfer_bytes > 0
            {
                ServiceStage::KvTransfer
            } else {
                ServiceStage::Decode
            };
            ready.push(ReadyJob {
                ready_microseconds: current_microseconds,
                stage,
                request_index: running.job.request_index,
                token_ordinal: 0,
            });
        }
        ServiceStage::KvTransfer => {
            state.kv_transfer = Some(timing);
            ready.push(ReadyJob {
                ready_microseconds: current_microseconds,
                stage: ServiceStage::Decode,
                request_index: running.job.request_index,
                token_ordinal: 0,
            });
        }
        ServiceStage::Decode => {
            state.decode_queue_microseconds = state
                .decode_queue_microseconds
                .checked_add(timing.queue_microseconds)
                .ok_or(GlmPdServingError::ArithmeticOverflow)?;
            state.decode_service_microseconds = state
                .decode_service_microseconds
                .checked_add(timing.service_microseconds)
                .ok_or(GlmPdServingError::ArithmeticOverflow)?;
            if running.job.token_ordinal == 0 {
                state.first_token_microseconds = Some(current_microseconds);
            }
            let next_ordinal = running
                .job
                .token_ordinal
                .checked_add(1)
                .ok_or(GlmPdServingError::ArithmeticOverflow)?;
            if next_ordinal < request.trace.requests[running.job.request_index].output_tokens {
                ready.push(ReadyJob {
                    ready_microseconds: current_microseconds,
                    stage: ServiceStage::Decode,
                    request_index: running.job.request_index,
                    token_ordinal: next_ordinal,
                });
            } else {
                state.completion_microseconds = Some(current_microseconds);
            }
        }
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn dispatch_jobs(
    request: &GlmPdServingRequest,
    effects: &StageRateEffects,
    configuration: CaseConfiguration<'_>,
    pools: &mut [WorkerPool],
    states: &mut [RequestSimulation],
    ready: &mut Vec<ReadyJob>,
    activity: &mut BTreeMap<ServiceStage, ActivityAccumulator>,
    current_microseconds: u64,
) -> Result<(), GlmPdServingError> {
    for pool in pools.iter_mut() {
        for worker_id in 0..pool.workers.len() {
            if pool.workers[worker_id].is_some() {
                continue;
            }
            let Some(job_index) =
                next_ready_job(request, configuration, pool.kind, worker_id, states, ready)
            else {
                continue;
            };
            let job = ready.remove(job_index);
            if matches!(configuration, CaseConfiguration::Aggregated)
                && states[job.request_index].home_worker.is_none()
            {
                states[job.request_index].home_worker = Some(worker_id);
            }
            let service_microseconds = service_microseconds(
                request,
                effects,
                configuration,
                &states[job.request_index],
                job,
            )?;
            let completion_microseconds = current_microseconds
                .checked_add(service_microseconds)
                .ok_or(GlmPdServingError::ArithmeticOverflow)?;
            pool.busy_microseconds = pool
                .busy_microseconds
                .checked_add(service_microseconds)
                .ok_or(GlmPdServingError::ArithmeticOverflow)?;
            record_activity(
                activity,
                &job,
                &states[job.request_index],
                service_microseconds,
            )?;
            pool.workers[worker_id] = Some(RunningJob {
                job,
                start_microseconds: current_microseconds,
                completion_microseconds,
                service_microseconds,
            });
        }
    }
    Ok(())
}

fn next_ready_job(
    request: &GlmPdServingRequest,
    configuration: CaseConfiguration<'_>,
    pool_kind: PoolKind,
    worker_id: usize,
    states: &[RequestSimulation],
    ready: &[ReadyJob],
) -> Option<usize> {
    ready
        .iter()
        .enumerate()
        .filter(|(_, job)| pool_accepts(pool_kind, job.stage))
        .filter(|(_, job)| {
            !matches!(configuration, CaseConfiguration::Aggregated)
                || states[job.request_index]
                    .home_worker
                    .is_none_or(|home| home == worker_id)
        })
        .min_by_key(|(_, job)| ready_key(request, job))
        .map(|(index, _)| index)
}

fn pool_accepts(pool_kind: PoolKind, stage: ServiceStage) -> bool {
    match pool_kind {
        PoolKind::Aggregated => matches!(stage, ServiceStage::Prefill | ServiceStage::Decode),
        PoolKind::Prefill => stage == ServiceStage::Prefill,
        PoolKind::Transfer => stage == ServiceStage::KvTransfer,
        PoolKind::Decode => stage == ServiceStage::Decode,
    }
}

fn ready_key(request: &GlmPdServingRequest, job: &ReadyJob) -> (u64, usize, u64, u32) {
    let stage_priority = request
        .scheduling
        .aggregated_stage_priority
        .iter()
        .position(|stage| *stage == job.stage)
        .unwrap_or(usize::MAX);
    (
        job.ready_microseconds,
        stage_priority,
        request.trace.requests[job.request_index].request_id,
        job.token_ordinal,
    )
}

fn service_microseconds(
    request: &GlmPdServingRequest,
    effects: &StageRateEffects,
    configuration: CaseConfiguration<'_>,
    state: &RequestSimulation,
    job: ReadyJob,
) -> Result<u64, GlmPdServingError> {
    let trace_request = &request.trace.requests[job.request_index];
    match job.stage {
        ServiceStage::Prefill => token_range_service_microseconds(
            &request.service_rates.prefill,
            u64::from(trace_request.prefix_reused_tokens)
                .checked_add(1)
                .ok_or(GlmPdServingError::ArithmeticOverflow)?,
            u64::from(trace_request.input_tokens),
            effect_basis_points(effects, configuration, ServiceStage::Prefill)?,
        ),
        ServiceStage::KvTransfer => byte_service_microseconds(
            &request.service_rates.kv_transfer,
            state.kv_transfer_bytes,
            effect_basis_points(effects, configuration, ServiceStage::KvTransfer)?,
        ),
        ServiceStage::Decode => {
            let context = u64::from(trace_request.input_tokens)
                .checked_add(u64::from(job.token_ordinal))
                .and_then(|value| value.checked_add(1))
                .ok_or(GlmPdServingError::ArithmeticOverflow)?;
            token_range_service_microseconds(
                &request.service_rates.decode,
                context,
                context,
                effect_basis_points(effects, configuration, ServiceStage::Decode)?,
            )
        }
    }
}

fn token_range_service_microseconds(
    profile: &TokenStageProfile,
    first_context: u64,
    last_context: u64,
    effect_basis_points: u32,
) -> Result<u64, GlmPdServingError> {
    if first_context > last_context {
        return Err(GlmPdServingError::InvalidServiceWork);
    }
    let mut total = profile.fixed_job_microseconds;
    let mut previous_max = 0_u64;
    for band in &profile.context_bands {
        let band_first = previous_max
            .checked_add(1)
            .ok_or(GlmPdServingError::ArithmeticOverflow)?;
        let segment_first = first_context.max(band_first);
        let segment_last = last_context.min(band.max_context_tokens_inclusive);
        if segment_first <= segment_last {
            let tokens = segment_last
                .checked_sub(segment_first)
                .and_then(|value| value.checked_add(1))
                .ok_or(GlmPdServingError::ArithmeticOverflow)?;
            total = total
                .checked_add(rate_duration_microseconds(
                    tokens,
                    band.tokens_per_second,
                    effect_basis_points,
                )?)
                .ok_or(GlmPdServingError::ArithmeticOverflow)?;
        }
        previous_max = band.max_context_tokens_inclusive;
        if previous_max >= last_context {
            break;
        }
    }
    Ok(total)
}

fn byte_service_microseconds(
    profile: &ByteStageProfile,
    bytes: u64,
    effect_basis_points: u32,
) -> Result<u64, GlmPdServingError> {
    if bytes == 0 {
        return Err(GlmPdServingError::InvalidServiceWork);
    }
    profile
        .fixed_job_microseconds
        .checked_add(rate_duration_microseconds(
            bytes,
            profile.bytes_per_second,
            effect_basis_points,
        )?)
        .ok_or(GlmPdServingError::ArithmeticOverflow)
}

fn rate_duration_microseconds(
    work: u64,
    rate_per_second: u64,
    effect_basis_points: u32,
) -> Result<u64, GlmPdServingError> {
    let numerator = u128::from(work)
        .checked_mul(1_000_000)
        .and_then(|value| value.checked_mul(10_000))
        .ok_or(GlmPdServingError::ArithmeticOverflow)?;
    let denominator = u128::from(rate_per_second)
        .checked_mul(u128::from(effect_basis_points))
        .ok_or(GlmPdServingError::ArithmeticOverflow)?;
    let duration = numerator
        .checked_add(
            denominator
                .checked_sub(1)
                .ok_or(GlmPdServingError::ArithmeticOverflow)?,
        )
        .ok_or(GlmPdServingError::ArithmeticOverflow)?
        / denominator;
    u64::try_from(duration).map_err(|_| GlmPdServingError::ArithmeticOverflow)
}

fn effect_basis_points(
    effects: &StageRateEffects,
    configuration: CaseConfiguration<'_>,
    stage: ServiceStage,
) -> Result<u32, GlmPdServingError> {
    match (configuration, stage) {
        (CaseConfiguration::Aggregated, ServiceStage::Prefill) => {
            Ok(effects.aggregated_prefill.multiplier_basis_points)
        }
        (CaseConfiguration::Aggregated, ServiceStage::Decode) => {
            Ok(effects.aggregated_decode.multiplier_basis_points)
        }
        (CaseConfiguration::Disaggregated { .. }, ServiceStage::Prefill) => {
            Ok(effects.disaggregated_prefill.multiplier_basis_points)
        }
        (CaseConfiguration::Disaggregated { .. }, ServiceStage::KvTransfer) => {
            Ok(effects.disaggregated_transfer.multiplier_basis_points)
        }
        (CaseConfiguration::Disaggregated { .. }, ServiceStage::Decode) => {
            Ok(effects.disaggregated_decode.multiplier_basis_points)
        }
        (CaseConfiguration::Aggregated, ServiceStage::KvTransfer) => {
            Err(GlmPdServingError::InvalidServiceWork)
        }
    }
}

fn record_activity(
    activity: &mut BTreeMap<ServiceStage, ActivityAccumulator>,
    job: &ReadyJob,
    state: &RequestSimulation,
    service_microseconds: u64,
) -> Result<(), GlmPdServingError> {
    let entry = activity.entry(job.stage).or_default();
    entry.jobs = entry
        .jobs
        .checked_add(1)
        .ok_or(GlmPdServingError::ArithmeticOverflow)?;
    entry.busy_microseconds = entry
        .busy_microseconds
        .checked_add(service_microseconds)
        .ok_or(GlmPdServingError::ArithmeticOverflow)?;
    match job.stage {
        ServiceStage::Prefill => {
            entry.tokens = entry
                .tokens
                .checked_add(u64::from(state.uncached_input_tokens))
                .ok_or(GlmPdServingError::ArithmeticOverflow)?;
        }
        ServiceStage::KvTransfer => {
            entry.bytes = entry
                .bytes
                .checked_add(state.kv_transfer_bytes)
                .ok_or(GlmPdServingError::ArithmeticOverflow)?;
        }
        ServiceStage::Decode => {
            entry.tokens = entry
                .tokens
                .checked_add(1)
                .ok_or(GlmPdServingError::ArithmeticOverflow)?;
        }
    }
    Ok(())
}

fn next_event_timestamp(
    request: &GlmPdServingRequest,
    pools: &[WorkerPool],
    next_arrival: usize,
    current_microseconds: u64,
) -> Result<u64, GlmPdServingError> {
    let arrival = request
        .trace
        .requests
        .get(next_arrival)
        .map(|trace_request| trace_request.arrival_timestamp_microseconds);
    let completion = pools
        .iter()
        .flat_map(|pool| pool.workers.iter())
        .filter_map(|worker| worker.as_ref())
        .map(|running| running.completion_microseconds)
        .min();
    let next = match (arrival, completion) {
        (Some(arrival), Some(completion)) => arrival.min(completion),
        (Some(arrival), None) => arrival,
        (None, Some(completion)) => completion,
        (None, None) => return Err(GlmPdServingError::SimulationStalled),
    };
    if next <= current_microseconds {
        Err(GlmPdServingError::SimulationStalled)
    } else {
        Ok(next)
    }
}

fn build_case_report(
    request: &GlmPdServingRequest,
    effects: &StageRateEffects,
    configuration: CaseConfiguration<'_>,
    states: Vec<RequestSimulation>,
    pools: Vec<WorkerPool>,
    activity: BTreeMap<ServiceStage, ActivityAccumulator>,
) -> Result<ServingCaseReport, GlmPdServingError> {
    let observations = TraceObservations {
        trace_id: request.trace.trace_id.clone(),
        requests: request
            .trace
            .requests
            .iter()
            .zip(&states)
            .map(|(trace_request, state)| {
                Ok(RequestTimingObservation {
                    request_id: trace_request.request_id,
                    first_token_timestamp_microseconds: state
                        .first_token_microseconds
                        .ok_or(GlmPdServingError::SimulationStalled)?,
                    completion_timestamp_microseconds: state
                        .completion_microseconds
                        .ok_or(GlmPdServingError::SimulationStalled)?,
                })
            })
            .collect::<Result<Vec<_>, GlmPdServingError>>()?,
    };
    let slo = evaluate_trace(&request.workload_contract, &request.trace, &observations)?;
    let slo_by_id = slo
        .requests
        .iter()
        .map(|evaluation| (evaluation.request_id, evaluation))
        .collect::<BTreeMap<_, _>>();
    let mut request_results = Vec::with_capacity(states.len());
    let mut queue_microseconds = Vec::with_capacity(states.len());
    for ((trace_request, state), observation) in request
        .trace
        .requests
        .iter()
        .zip(states)
        .zip(&observations.requests)
    {
        let evaluation = slo_by_id
            .get(&trace_request.request_id)
            .ok_or(GlmPdServingError::SimulationStalled)?;
        let transfer_queue = state
            .kv_transfer
            .as_ref()
            .map_or(0, |timing| timing.queue_microseconds);
        let total_queue = state
            .prefill
            .as_ref()
            .map_or(0, |timing| timing.queue_microseconds)
            .checked_add(transfer_queue)
            .and_then(|value| value.checked_add(state.decode_queue_microseconds))
            .ok_or(GlmPdServingError::ArithmeticOverflow)?;
        queue_microseconds.push(total_queue);
        request_results.push(ServingRequestResult {
            request_id: trace_request.request_id,
            class: trace_request.class,
            input_tokens: trace_request.input_tokens,
            output_tokens: trace_request.output_tokens,
            prefix_reused_tokens: trace_request.prefix_reused_tokens,
            uncached_input_tokens: state.uncached_input_tokens,
            kv_transfer_bytes: state.kv_transfer_bytes,
            arrival_timestamp_microseconds: trace_request.arrival_timestamp_microseconds,
            first_token_timestamp_microseconds: observation.first_token_timestamp_microseconds,
            completion_timestamp_microseconds: observation.completion_timestamp_microseconds,
            ttft_milliseconds: evaluation.ttft_milliseconds,
            tpot_milliseconds: evaluation.tpot_milliseconds,
            meets_slo: evaluation.meets_objective(),
            prefill: state.prefill,
            kv_transfer: state.kv_transfer,
            decode_queue_microseconds: state.decode_queue_microseconds,
            decode_service_microseconds: state.decode_service_microseconds,
            kv_transfer_queue_microseconds: transfer_queue,
        });
    }
    let first_arrival = request.trace.requests[0].arrival_timestamp_microseconds;
    let last_completion = observations
        .requests
        .iter()
        .map(|observation| observation.completion_timestamp_microseconds)
        .max()
        .ok_or(GlmPdServingError::SimulationStalled)?;
    let duration_microseconds = last_completion
        .checked_sub(first_arrival)
        .ok_or(GlmPdServingError::ArithmeticOverflow)?;
    if duration_microseconds == 0 {
        return Err(GlmPdServingError::InvalidServiceWork);
    }
    let input_tokens = request
        .trace
        .requests
        .iter()
        .try_fold(0_u64, |total, trace_request| {
            total
                .checked_add(u64::from(trace_request.input_tokens))
                .ok_or(GlmPdServingError::ArithmeticOverflow)
        })?;
    let output_tokens = request
        .trace
        .requests
        .iter()
        .try_fold(0_u64, |total, trace_request| {
            total
                .checked_add(u64::from(trace_request.output_tokens))
                .ok_or(GlmPdServingError::ArithmeticOverflow)
        })?;
    let good_request_count = request_results
        .iter()
        .filter(|result| result.meets_slo)
        .count();
    let good_output_tokens = request_results
        .iter()
        .filter(|result| result.meets_slo)
        .try_fold(0_u64, |total, result| {
            total
                .checked_add(u64::from(result.output_tokens))
                .ok_or(GlmPdServingError::ArithmeticOverflow)
        })?;
    let request_count =
        u64::try_from(request_results.len()).map_err(|_| GlmPdServingError::CountOverflow)?;
    let good_request_count =
        u64::try_from(good_request_count).map_err(|_| GlmPdServingError::CountOverflow)?;
    let allocation = case_allocation(request, configuration);
    let stage_activity =
        build_stage_activity(configuration, &allocation, duration_microseconds, &activity)?;
    let pool_activity = build_pool_activity(duration_microseconds, pools)?;
    let case_id = case_id(effects, configuration);
    let layout = match configuration {
        CaseConfiguration::Aggregated => ServingLayout::Aggregated,
        CaseConfiguration::Disaggregated { .. } => ServingLayout::Disaggregated,
    };
    let (split_id, transfer_endpoint) = match configuration {
        CaseConfiguration::Aggregated => (None, None),
        CaseConfiguration::Disaggregated { split, endpoint } => {
            (Some(split.split_id.clone()), Some(endpoint))
        }
    };
    let duration_seconds_denominator = duration_microseconds as f64;
    let hourly_budget_usd =
        f64::from(request.budget.total_device_slots) * request.budget.usd_per_device_hour;
    let output_tokens_per_second =
        output_tokens as f64 * 1_000_000.0 / duration_seconds_denominator;
    let goodput_output_tokens_per_second =
        good_output_tokens as f64 * 1_000_000.0 / duration_seconds_denominator;
    Ok(ServingCaseReport {
        case_id,
        layout,
        effect_id: effects.effect_id.clone(),
        split_id,
        transfer_endpoint,
        allocation,
        aggregate: ServingCaseAggregate {
            request_count,
            input_tokens,
            output_tokens,
            duration_microseconds,
            output_tokens_per_second,
            goodput_requests_per_second: good_request_count as f64 * 1_000_000.0
                / duration_seconds_denominator,
            goodput_output_tokens_per_second,
            cost_per_million_output_tokens_usd: cost_per_million_output_tokens(
                hourly_budget_usd,
                output_tokens_per_second,
            ),
            slo_goodput_cost_per_million_output_tokens_usd: (goodput_output_tokens_per_second
                > 0.0)
                .then(|| {
                    cost_per_million_output_tokens(
                        hourly_budget_usd,
                        goodput_output_tokens_per_second,
                    )
                }),
            mean_queue_milliseconds: mean_u64(&queue_microseconds) / 1_000.0,
            p95_queue_milliseconds: percentile_u64(&queue_microseconds, 95.0) as f64 / 1_000.0,
            hourly_budget_usd,
        },
        stage_activity,
        pool_activity,
        slo,
        requests: request_results,
    })
}

fn case_allocation(
    request: &GlmPdServingRequest,
    configuration: CaseConfiguration<'_>,
) -> CasePoolAllocation {
    match configuration {
        CaseConfiguration::Aggregated => CasePoolAllocation {
            total_device_slots: request.budget.total_device_slots,
            aggregated_workers: request.aggregated.worker_count,
            prefill_workers: 0,
            transfer_workers: 0,
            decode_workers: 0,
        },
        CaseConfiguration::Disaggregated { split, .. } => CasePoolAllocation {
            total_device_slots: request.budget.total_device_slots,
            aggregated_workers: 0,
            prefill_workers: split.prefill_workers,
            transfer_workers: split.transfer_workers,
            decode_workers: split.decode_workers,
        },
    }
}

fn build_stage_activity(
    configuration: CaseConfiguration<'_>,
    allocation: &CasePoolAllocation,
    duration_microseconds: u64,
    activity: &BTreeMap<ServiceStage, ActivityAccumulator>,
) -> Result<Vec<StageActivity>, GlmPdServingError> {
    [
        ServiceStage::Prefill,
        ServiceStage::KvTransfer,
        ServiceStage::Decode,
    ]
    .into_iter()
    .map(|stage| {
        let worker_count = match (configuration, stage) {
            (CaseConfiguration::Aggregated, ServiceStage::Prefill | ServiceStage::Decode) => {
                allocation.aggregated_workers
            }
            (CaseConfiguration::Aggregated, ServiceStage::KvTransfer) => 0,
            (CaseConfiguration::Disaggregated { .. }, ServiceStage::Prefill) => {
                allocation.prefill_workers
            }
            (CaseConfiguration::Disaggregated { .. }, ServiceStage::KvTransfer) => {
                allocation.transfer_workers
            }
            (CaseConfiguration::Disaggregated { .. }, ServiceStage::Decode) => {
                allocation.decode_workers
            }
        };
        let accumulated = activity.get(&stage).copied().unwrap_or_default();
        let capacity_microseconds = duration_microseconds
            .checked_mul(u64::from(worker_count))
            .ok_or(GlmPdServingError::ArithmeticOverflow)?;
        Ok(StageActivity {
            stage,
            worker_count,
            jobs: accumulated.jobs,
            tokens: accumulated.tokens,
            bytes: accumulated.bytes,
            busy_microseconds: accumulated.busy_microseconds,
            capacity_microseconds,
            utilization: utilization(accumulated.busy_microseconds, capacity_microseconds),
        })
    })
    .collect()
}

fn build_pool_activity(
    duration_microseconds: u64,
    pools: Vec<WorkerPool>,
) -> Result<Vec<PoolActivity>, GlmPdServingError> {
    pools
        .into_iter()
        .map(|pool| {
            let worker_count =
                u32::try_from(pool.workers.len()).map_err(|_| GlmPdServingError::CountOverflow)?;
            let capacity_microseconds = duration_microseconds
                .checked_mul(u64::from(worker_count))
                .ok_or(GlmPdServingError::ArithmeticOverflow)?;
            Ok(PoolActivity {
                pool_id: pool_id(pool.kind).into(),
                worker_count,
                busy_microseconds: pool.busy_microseconds,
                capacity_microseconds,
                utilization: utilization(pool.busy_microseconds, capacity_microseconds),
            })
        })
        .collect()
}

fn utilization(busy_microseconds: u64, capacity_microseconds: u64) -> f64 {
    if capacity_microseconds == 0 {
        0.0
    } else {
        busy_microseconds as f64 / capacity_microseconds as f64
    }
}

fn cost_per_million_output_tokens(hourly_budget_usd: f64, tokens_per_second: f64) -> f64 {
    hourly_budget_usd * 1_000_000.0 / (tokens_per_second * 3_600.0)
}

fn case_id(effects: &StageRateEffects, configuration: CaseConfiguration<'_>) -> String {
    match configuration {
        CaseConfiguration::Aggregated => format!("aggregated:{}", effects.effect_id),
        CaseConfiguration::Disaggregated { split, endpoint } => format!(
            "pd:{}:{}:{}",
            effects.effect_id,
            split.split_id,
            transfer_endpoint_id(endpoint)
        ),
    }
}

fn transfer_endpoint_id(endpoint: TransferEndpoint) -> &'static str {
    match endpoint {
        TransferEndpoint::DeltaLower => "delta_lower",
        TransferEndpoint::FullUpper => "full_upper",
    }
}

fn pool_id(kind: PoolKind) -> &'static str {
    match kind {
        PoolKind::Aggregated => "aggregated",
        PoolKind::Prefill => "prefill",
        PoolKind::Transfer => "kv_transfer",
        PoolKind::Decode => "decode",
    }
}

fn mean_u64(values: &[u64]) -> f64 {
    values.iter().map(|value| *value as f64).sum::<f64>() / values.len() as f64
}

fn percentile_u64(values: &[u64], percentile: f64) -> u64 {
    let mut sorted = values.to_vec();
    sorted.sort_unstable();
    let index = ((sorted.len() as f64 * percentile / 100.0).ceil() as usize)
        .saturating_sub(1)
        .min(sorted.len().saturating_sub(1));
    sorted[index]
}

fn trace_content_id(trace: &CanonicalTraceV2) -> Result<String, GlmPdServingError> {
    let canonical = trace.to_canonical_json()?;
    Ok(blake3::hash(canonical.as_bytes()).to_hex().to_string())
}

fn claim_gate() -> GlmPdServingClaimGate {
    GlmPdServingClaimGate {
        end_to_end_latency_claim_permitted: false,
        slo_claim_permitted: false,
        cost_per_token_claim_permitted: false,
        blockers: vec![
            GlmPdServingClaimBlocker::EndToEndCalibrationMissing,
            GlmPdServingClaimBlocker::KvTransferIsBounded,
            GlmPdServingClaimBlocker::RateEffectsAreUncalibrated,
            GlmPdServingClaimBlocker::ContinuousBatchingExcluded,
            GlmPdServingClaimBlocker::ResidencyAndFailuresExcluded,
            GlmPdServingClaimBlocker::ProviderReportsAreMechanismOnly,
        ],
    }
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a GlmPdServingResult,
}

fn report_content_id(
    schema_version: u32,
    result: &GlmPdServingResult,
) -> Result<String, GlmPdServingError> {
    let bytes = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|error| GlmPdServingError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum GlmPdServingError {
    #[error("unsupported GLM P/D serving schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid GLM P/D serving field {0}")]
    InvalidField(&'static str),
    #[error("workload contract identity differs from trace identity")]
    WorkloadIdentityMismatch,
    #[error("aggregate and P/D cases do not use the same fixed fleet budget")]
    FleetBudgetMismatch,
    #[error("unsupported scheduling contract")]
    UnsupportedSchedulingContract,
    #[error(
        "context-banded service rates cover {covered_context} tokens but {required_context} are required"
    )]
    ContextRateCoverageMissing {
        required_context: u64,
        covered_context: u64,
    },
    #[error("mechanism-only source {0} was used as calibration evidence")]
    MechanismTargetUsedAsCalibration(String),
    #[error("simulation arithmetic overflowed")]
    ArithmeticOverflow,
    #[error("simulation count exceeds the supported numeric range")]
    CountOverflow,
    #[error("simulation encountered an invalid zero-work service job")]
    InvalidServiceWork,
    #[error("simulation made no forward progress")]
    SimulationStalled,
    #[error("GLM P/D serving serialization failed: {0}")]
    Serialization(String),
    #[error(transparent)]
    Workload(#[from] WorkloadError),
}
