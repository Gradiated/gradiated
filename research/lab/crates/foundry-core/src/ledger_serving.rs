use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::action_ledger::{ActionLedger, InferencePhase};
use crate::ledger_roofline::LedgerRooflineReport;
use crate::workload::{
    AgentTurnClass, CanonicalTraceV2, RequestTimingObservation, TraceObservations,
    WorkloadContractV2, WorkloadError, WorkloadSloReport, evaluate_trace,
};

pub const LEDGER_SERVING_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const LEDGER_SERVING_REPORT_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerServingSimulationRequest {
    pub schema_version: u32,
    pub simulation_id: String,
    pub workload_contract: WorkloadContractV2,
    pub trace: CanonicalTraceV2,
    pub ledger: ActionLedger,
    pub roofline: LedgerRooflineReport,
    pub hardware_id: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum LedgerServingClaimBlocker {
    PrefillNotModeled,
    PrefixCacheRestoreNotModeled,
    SharedResourceContentionNotModeled,
    DecodeQuantumTableNotModeled,
    IntraQuantumTokenTimingNotModeled,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerServingClaimGate {
    pub end_to_end_latency_claim_permitted: bool,
    pub slo_claim_permitted: bool,
    pub cost_per_token_claim_permitted: bool,
    pub blockers: Vec<LedgerServingClaimBlocker>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerDecodeQuantum {
    pub ledger_content_id: String,
    pub roofline_content_id: String,
    pub hardware_id: String,
    pub batch_size: u32,
    pub aggregate_context_tokens: u64,
    pub candidate_tokens: u64,
    pub committed_tokens: u64,
    pub optimistic_critical_path_seconds: f64,
    pub duration_microseconds: u64,
    pub quantum_invocations: u64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerServingRequestResult {
    pub request_id: u64,
    pub class: AgentTurnClass,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub prefix_reused_tokens: u32,
    pub delivered_tokens: u32,
    pub arrival_timestamp_microseconds: u64,
    pub start_timestamp_microseconds: u64,
    pub first_token_timestamp_microseconds: u64,
    pub completion_timestamp_microseconds: u64,
    pub queue_microseconds: u64,
    pub ttft_milliseconds: f64,
    pub tpot_milliseconds: f64,
    pub meets_slo: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerServingAggregate {
    pub request_count: u64,
    pub input_tokens: u64,
    pub delivered_output_tokens: u64,
    pub duration_seconds: f64,
    pub output_tokens_per_second: f64,
    pub goodput_requests_per_second: f64,
    pub goodput_output_tokens_per_second: f64,
    pub mean_queue_milliseconds: f64,
    pub p95_queue_milliseconds: f64,
    pub padded_request_slots: u64,
    pub wasted_committed_token_slots: u64,
    pub uncommitted_candidate_token_slots: u64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerServingResult {
    pub simulation_id: String,
    pub workload_contract_id: String,
    pub trace_id: String,
    pub trace_content_id: String,
    pub quantum: LedgerDecodeQuantum,
    pub aggregate: LedgerServingAggregate,
    pub claims: LedgerServingClaimGate,
    pub slo: WorkloadSloReport,
    pub requests: Vec<LedgerServingRequestResult>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerServingReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: LedgerServingResult,
}

impl LedgerServingReport {
    pub fn verify_content_id(&self) -> Result<bool, LedgerServingError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

pub fn simulate_exact_ledger_serving(
    request: &LedgerServingSimulationRequest,
) -> Result<LedgerServingReport, LedgerServingError> {
    let validated = validate_request(request)?;
    let start_timestamp_microseconds = request
        .trace
        .requests
        .iter()
        .map(|request| request.arrival_timestamp_microseconds)
        .max()
        .ok_or(LedgerServingError::InvalidField("trace.requests"))?;
    let completion_timestamp_microseconds = start_timestamp_microseconds
        .checked_add(validated.duration_microseconds)
        .ok_or(LedgerServingError::ArithmeticOverflow)?;
    let delivered = allocate_committed_tokens(
        &request.trace,
        request.ledger.provenance.phase.committed_tokens,
    )?;
    let timing_observations = request
        .trace
        .requests
        .iter()
        .map(|trace_request| RequestTimingObservation {
            request_id: trace_request.request_id,
            first_token_timestamp_microseconds: completion_timestamp_microseconds,
            completion_timestamp_microseconds,
        })
        .collect();
    let observations = TraceObservations {
        trace_id: request.trace.trace_id.clone(),
        requests: timing_observations,
    };
    let slo = evaluate_trace(&request.workload_contract, &request.trace, &observations)?;
    let slo_by_request = slo
        .requests
        .iter()
        .map(|result| (result.request_id, result))
        .collect::<BTreeMap<_, _>>();
    let requests = request
        .trace
        .requests
        .iter()
        .zip(&delivered)
        .map(|(trace_request, delivered_tokens)| {
            let slo_result = slo_by_request.get(&trace_request.request_id).ok_or(
                LedgerServingError::MissingSloResult {
                    request_id: trace_request.request_id,
                },
            )?;
            Ok::<LedgerServingRequestResult, LedgerServingError>(LedgerServingRequestResult {
                request_id: trace_request.request_id,
                class: trace_request.class,
                input_tokens: trace_request.input_tokens,
                output_tokens: trace_request.output_tokens,
                prefix_reused_tokens: trace_request.prefix_reused_tokens,
                delivered_tokens: *delivered_tokens,
                arrival_timestamp_microseconds: trace_request.arrival_timestamp_microseconds,
                start_timestamp_microseconds,
                first_token_timestamp_microseconds: completion_timestamp_microseconds,
                completion_timestamp_microseconds,
                queue_microseconds: start_timestamp_microseconds
                    .checked_sub(trace_request.arrival_timestamp_microseconds)
                    .ok_or(LedgerServingError::ArithmeticOverflow)?,
                ttft_milliseconds: slo_result.ttft_milliseconds,
                tpot_milliseconds: slo_result.tpot_milliseconds,
                meets_slo: slo_result.meets_objective(),
            })
        })
        .collect::<Result<Vec<_>, _>>()?;
    let aggregate = aggregate(
        &request.trace,
        &requests,
        completion_timestamp_microseconds,
        request.ledger.provenance.phase.candidate_tokens,
        request.ledger.provenance.phase.committed_tokens,
    )?;
    let phase = &request.ledger.provenance.phase;
    let result = LedgerServingResult {
        simulation_id: request.simulation_id.clone(),
        workload_contract_id: request.workload_contract.contract_id.clone(),
        trace_id: request.trace.trace_id.clone(),
        trace_content_id: trace_content_id(&request.trace)?,
        quantum: LedgerDecodeQuantum {
            ledger_content_id: validated.ledger_content_id,
            roofline_content_id: request.roofline.content_id.clone(),
            hardware_id: request.hardware_id.clone(),
            batch_size: phase.batch_size,
            aggregate_context_tokens: phase.context_tokens,
            candidate_tokens: phase.candidate_tokens,
            committed_tokens: phase.committed_tokens,
            optimistic_critical_path_seconds: validated.optimistic_critical_path_seconds,
            duration_microseconds: validated.duration_microseconds,
            quantum_invocations: 1,
        },
        aggregate,
        claims: claim_gate(),
        slo,
        requests,
    };
    let schema_version = LEDGER_SERVING_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(LedgerServingReport {
        schema_version,
        content_id,
        result,
    })
}

struct ValidatedQuantum {
    ledger_content_id: String,
    optimistic_critical_path_seconds: f64,
    duration_microseconds: u64,
}

fn validate_request(
    request: &LedgerServingSimulationRequest,
) -> Result<ValidatedQuantum, LedgerServingError> {
    if request.schema_version != LEDGER_SERVING_REQUEST_SCHEMA_VERSION {
        return Err(LedgerServingError::UnsupportedSchemaVersion {
            expected: LEDGER_SERVING_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    validate_required("simulation_id", &request.simulation_id)?;
    validate_required("hardware_id", &request.hardware_id)?;
    request.workload_contract.validate()?;
    request.trace.validate()?;
    if request.workload_contract.identity != request.trace.identity {
        return Err(LedgerServingError::WorkloadIdentityMismatch);
    }
    request
        .ledger
        .validate()
        .map_err(|error| LedgerServingError::Ledger(error.to_string()))?;
    if request.ledger.provenance.phase.phase != InferencePhase::Decode {
        return Err(LedgerServingError::DecodeLedgerRequired);
    }
    if request.trace.identity.model_id != request.ledger.provenance.model.model_id
        || request.trace.identity.model_revision != request.ledger.provenance.model.model_revision
    {
        return Err(LedgerServingError::LedgerModelIdentityMismatch);
    }
    if !request
        .roofline
        .verify_content_id()
        .map_err(|error| LedgerServingError::Roofline(error.to_string()))?
    {
        return Err(LedgerServingError::InvalidRooflineContentId);
    }
    let ledger_content_id = request
        .ledger
        .content_id()
        .map_err(|error| LedgerServingError::Ledger(error.to_string()))?
        .as_str()
        .to_owned();
    if request.roofline.result.ledger_content_id != ledger_content_id {
        return Err(LedgerServingError::LedgerContentIdMismatch);
    }
    if request.roofline.result.committed_tokens != request.ledger.provenance.phase.committed_tokens
    {
        return Err(LedgerServingError::RooflineQuantumMismatch);
    }
    let hardware = request
        .roofline
        .result
        .hardware
        .iter()
        .find(|hardware| hardware.hardware_id == request.hardware_id)
        .ok_or_else(|| LedgerServingError::MissingHardware(request.hardware_id.clone()))?;
    let duration_microseconds = duration_microseconds(hardware.optimistic_critical_path_seconds)?;
    let actual_batch_size = u32::try_from(request.trace.requests.len())
        .map_err(|_| LedgerServingError::ArithmeticOverflow)?;
    let expected_batch_size = request.ledger.provenance.phase.batch_size;
    if actual_batch_size != expected_batch_size {
        return Err(LedgerServingError::BatchSizeMismatch {
            expected: expected_batch_size,
            actual: actual_batch_size,
        });
    }
    for trace_request in &request.trace.requests {
        if trace_request.prefix_reused_tokens != trace_request.input_tokens {
            return Err(LedgerServingError::UncachedInput {
                request_id: trace_request.request_id,
            });
        }
    }
    let actual_context_tokens =
        request
            .trace
            .requests
            .iter()
            .try_fold(0_u64, |total, trace_request| {
                total
                    .checked_add(u64::from(trace_request.input_tokens))
                    .ok_or(LedgerServingError::ArithmeticOverflow)
            })?;
    let expected_context_tokens = request.ledger.provenance.phase.context_tokens;
    if actual_context_tokens != expected_context_tokens {
        return Err(LedgerServingError::ContextTokensMismatch {
            expected: expected_context_tokens,
            actual: actual_context_tokens,
        });
    }
    let required_output_tokens =
        request
            .trace
            .requests
            .iter()
            .try_fold(0_u64, |total, trace_request| {
                total
                    .checked_add(u64::from(trace_request.output_tokens))
                    .ok_or(LedgerServingError::ArithmeticOverflow)
            })?;
    let available_committed_tokens = request.ledger.provenance.phase.committed_tokens;
    if required_output_tokens > available_committed_tokens {
        return Err(LedgerServingError::AdditionalQuantumRequired {
            available_committed_tokens,
            required_output_tokens,
        });
    }
    Ok(ValidatedQuantum {
        ledger_content_id,
        optimistic_critical_path_seconds: hardware.optimistic_critical_path_seconds,
        duration_microseconds,
    })
}

fn allocate_committed_tokens(
    trace: &CanonicalTraceV2,
    committed_tokens: u64,
) -> Result<Vec<u32>, LedgerServingError> {
    let mut remaining = trace
        .requests
        .iter()
        .map(|request| request.output_tokens)
        .collect::<Vec<_>>();
    let mut delivered = vec![0_u32; remaining.len()];
    let mut cursor = 0_usize;
    for _ in 0..committed_tokens {
        let Some(offset) =
            (0..remaining.len()).find(|offset| remaining[(cursor + offset) % remaining.len()] > 0)
        else {
            break;
        };
        let index = (cursor + offset) % remaining.len();
        remaining[index] -= 1;
        delivered[index] = delivered[index]
            .checked_add(1)
            .ok_or(LedgerServingError::ArithmeticOverflow)?;
        cursor = (index + 1) % remaining.len();
    }
    if remaining.iter().any(|tokens| *tokens > 0) {
        return Err(LedgerServingError::ArithmeticOverflow);
    }
    Ok(delivered)
}

fn aggregate(
    trace: &CanonicalTraceV2,
    requests: &[LedgerServingRequestResult],
    completion_timestamp_microseconds: u64,
    candidate_tokens: u64,
    committed_tokens: u64,
) -> Result<LedgerServingAggregate, LedgerServingError> {
    let first_arrival = trace
        .requests
        .first()
        .map(|request| request.arrival_timestamp_microseconds)
        .ok_or(LedgerServingError::InvalidField("trace.requests"))?;
    let duration_microseconds = completion_timestamp_microseconds
        .checked_sub(first_arrival)
        .ok_or(LedgerServingError::ArithmeticOverflow)?;
    if duration_microseconds == 0 {
        return Err(LedgerServingError::ArithmeticOverflow);
    }
    let duration_seconds = duration_microseconds as f64 / 1_000_000.0;
    let input_tokens = requests.iter().try_fold(0_u64, |total, request| {
        total
            .checked_add(u64::from(request.input_tokens))
            .ok_or(LedgerServingError::ArithmeticOverflow)
    })?;
    let delivered_output_tokens = requests.iter().try_fold(0_u64, |total, request| {
        total
            .checked_add(u64::from(request.delivered_tokens))
            .ok_or(LedgerServingError::ArithmeticOverflow)
    })?;
    let mut good_requests = requests.iter().filter(|request| request.meets_slo);
    let good_request_count = u64::try_from(good_requests.clone().count())
        .map_err(|_| LedgerServingError::ArithmeticOverflow)?;
    let good_output_tokens = good_requests.try_fold(0_u64, |total, request| {
        total
            .checked_add(u64::from(request.delivered_tokens))
            .ok_or(LedgerServingError::ArithmeticOverflow)
    })?;
    let queue_milliseconds = requests
        .iter()
        .map(|request| request.queue_microseconds as f64 / 1_000.0)
        .collect::<Vec<_>>();
    Ok(LedgerServingAggregate {
        request_count: u64::try_from(requests.len())
            .map_err(|_| LedgerServingError::ArithmeticOverflow)?,
        input_tokens,
        delivered_output_tokens,
        duration_seconds,
        output_tokens_per_second: delivered_output_tokens as f64 / duration_seconds,
        goodput_requests_per_second: good_request_count as f64 / duration_seconds,
        goodput_output_tokens_per_second: good_output_tokens as f64 / duration_seconds,
        mean_queue_milliseconds: mean(&queue_milliseconds),
        p95_queue_milliseconds: percentile(&queue_milliseconds, 95.0),
        padded_request_slots: 0,
        wasted_committed_token_slots: committed_tokens
            .checked_sub(delivered_output_tokens)
            .ok_or(LedgerServingError::ArithmeticOverflow)?,
        uncommitted_candidate_token_slots: candidate_tokens
            .checked_sub(committed_tokens)
            .ok_or(LedgerServingError::ArithmeticOverflow)?,
    })
}

fn claim_gate() -> LedgerServingClaimGate {
    LedgerServingClaimGate {
        end_to_end_latency_claim_permitted: false,
        slo_claim_permitted: false,
        cost_per_token_claim_permitted: false,
        blockers: vec![
            LedgerServingClaimBlocker::PrefillNotModeled,
            LedgerServingClaimBlocker::PrefixCacheRestoreNotModeled,
            LedgerServingClaimBlocker::SharedResourceContentionNotModeled,
            LedgerServingClaimBlocker::DecodeQuantumTableNotModeled,
            LedgerServingClaimBlocker::IntraQuantumTokenTimingNotModeled,
        ],
    }
}

fn duration_microseconds(seconds: f64) -> Result<u64, LedgerServingError> {
    let microseconds = seconds * 1_000_000.0;
    if !microseconds.is_finite() || microseconds <= 0.0 || microseconds > u64::MAX as f64 {
        return Err(LedgerServingError::InvalidQuantumDuration);
    }
    let duration = microseconds.ceil() as u64;
    if duration == 0 {
        Err(LedgerServingError::InvalidQuantumDuration)
    } else {
        Ok(duration)
    }
}

fn trace_content_id(trace: &CanonicalTraceV2) -> Result<String, LedgerServingError> {
    let canonical = trace.to_canonical_json()?;
    Ok(blake3::hash(canonical.as_bytes()).to_hex().to_string())
}

fn mean(values: &[f64]) -> f64 {
    values.iter().sum::<f64>() / values.len() as f64
}

fn percentile(values: &[f64], percentile: f64) -> f64 {
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    let index = ((sorted.len() as f64 * percentile / 100.0).ceil() as usize)
        .saturating_sub(1)
        .min(sorted.len().saturating_sub(1));
    sorted[index]
}

fn validate_required(field: &'static str, value: &str) -> Result<(), LedgerServingError> {
    if value.trim().is_empty() {
        Err(LedgerServingError::InvalidField(field))
    } else {
        Ok(())
    }
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a LedgerServingResult,
}

fn report_content_id(
    schema_version: u32,
    result: &LedgerServingResult,
) -> Result<String, LedgerServingError> {
    let canonical = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|error| LedgerServingError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&canonical).to_hex().to_string())
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum LedgerServingError {
    #[error("unsupported ledger serving schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid ledger serving field {0}")]
    InvalidField(&'static str),
    #[error("invalid workload: {0}")]
    Workload(#[from] WorkloadError),
    #[error("the workload contract and trace identities differ")]
    WorkloadIdentityMismatch,
    #[error("the action ledger is invalid: {0}")]
    Ledger(String),
    #[error("the ledger roofline report is invalid: {0}")]
    Roofline(String),
    #[error("the ledger roofline report content identity is invalid")]
    InvalidRooflineContentId,
    #[error("the action ledger content identity differs from the roofline input ledger")]
    LedgerContentIdMismatch,
    #[error("the ledger roofline and action ledger quantum geometry differ")]
    RooflineQuantumMismatch,
    #[error("an exact decode action ledger is required")]
    DecodeLedgerRequired,
    #[error("the workload model identity differs from the action ledger")]
    LedgerModelIdentityMismatch,
    #[error("hardware {0} is absent from the ledger roofline report")]
    MissingHardware(String),
    #[error("request {request_id} contains uncached input but prefill is not modeled")]
    UncachedInput { request_id: u64 },
    #[error("exact batch size is {expected}, but the trace contains {actual} requests")]
    BatchSizeMismatch { expected: u32, actual: u32 },
    #[error("exact aggregate context is {expected} tokens, but the trace contains {actual}")]
    ContextTokensMismatch { expected: u64, actual: u64 },
    #[error(
        "trace requires {required_output_tokens} output tokens, exceeding the single quantum's {available_committed_tokens} committed tokens"
    )]
    AdditionalQuantumRequired {
        available_committed_tokens: u64,
        required_output_tokens: u64,
    },
    #[error("the selected optimistic quantum duration is invalid")]
    InvalidQuantumDuration,
    #[error("SLO evaluation omitted request {request_id}")]
    MissingSloResult { request_id: u64 },
    #[error("ledger serving arithmetic overflowed")]
    ArithmeticOverflow,
    #[error("ledger serving serialization failed: {0}")]
    Serialization(String),
}
