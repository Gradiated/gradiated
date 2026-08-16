use crate::workload::{
    AgentTurnClass, CanonicalTraceRequest, CanonicalTraceV2, ClassSloObjective, WorkloadContractV2,
    WorkloadError,
};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use thiserror::Error;

pub const SERVING_BENCHMARK_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const SERVING_BENCHMARK_REPORT_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ServingModelIdentity {
    pub model_id: String,
    pub model_revision: String,
    pub checkpoint_id: String,
    pub checkpoint_revision: String,
    pub tokenizer_id: String,
    pub tokenizer_revision: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ServingEngineIdentity {
    pub name: String,
    pub version: String,
    pub build_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ServingHardwareTopology {
    pub device_model: String,
    pub device_count: u32,
    pub topology: String,
    pub interconnect: String,
    pub device_set_hash: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ServingEvidenceKind {
    MeasuredHardware,
    Simulated,
    Analytical,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ServingMeasurementProvenance {
    pub evidence_kind: ServingEvidenceKind,
    pub run_id: String,
    pub source_artifact_id: String,
    pub engine: ServingEngineIdentity,
    pub hardware: ServingHardwareTopology,
    pub measurement_tool: String,
    pub software_revision: String,
    pub captured_at_unix_milliseconds: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MeasuredServingRequestObservation {
    pub request_id: u64,
    pub model: ServingModelIdentity,
    pub provenance: ServingMeasurementProvenance,
    pub trace_id: String,
    pub trace_content_id: String,
    pub class: AgentTurnClass,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub prefix_reused_tokens: u32,
    pub arrival_timestamp_microseconds: u64,
    pub start_timestamp_microseconds: u64,
    pub first_token_timestamp_microseconds: Option<u64>,
    pub end_timestamp_microseconds: u64,
    pub success: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MeasuredServingBenchmarkRequest {
    pub schema_version: u32,
    pub benchmark_id: String,
    pub workload_contract: WorkloadContractV2,
    pub trace: CanonicalTraceV2,
    pub observations: Vec<MeasuredServingRequestObservation>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RequestServingBenchmarkResult {
    pub request_id: u64,
    pub class: AgentTurnClass,
    pub success: bool,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub prefix_reused_tokens: u32,
    pub queue_milliseconds: f64,
    pub ttft_milliseconds: Option<f64>,
    pub tpot_milliseconds: Option<f64>,
    pub ttft_objective_met: bool,
    pub tpot_objective_met: bool,
}

impl RequestServingBenchmarkResult {
    pub const fn meets_objective(&self) -> bool {
        self.success && self.ttft_objective_met && self.tpot_objective_met
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ClassServingBenchmarkResult {
    pub class: AgentTurnClass,
    pub objective: ClassSloObjective,
    pub request_count: u64,
    pub successful_requests: u64,
    pub failed_requests: u64,
    pub measured_ttft_milliseconds: Option<f64>,
    pub measured_tpot_milliseconds: Option<f64>,
    pub ttft_slo_met_requests: u64,
    pub tpot_slo_met_requests: u64,
    pub slo_met_requests: u64,
    pub ttft_compliant_fraction: f64,
    pub tpot_compliant_fraction: f64,
    pub ttft_objective_met: bool,
    pub tpot_objective_met: bool,
    pub goodput_requests_per_second: f64,
    pub goodput_output_tokens_per_second: f64,
}

impl ClassServingBenchmarkResult {
    pub const fn meets_objective(&self) -> bool {
        self.ttft_objective_met && self.tpot_objective_met
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AggregateServingBenchmarkResult {
    pub request_count: u64,
    pub successful_requests: u64,
    pub failed_requests: u64,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub prefix_reused_tokens: u64,
    pub duration_seconds: f64,
    pub throughput_requests_per_second: f64,
    pub successful_requests_per_second: f64,
    pub p95_ttft_milliseconds: Option<f64>,
    pub p95_tpot_milliseconds: Option<f64>,
    pub slo_met_requests: u64,
    pub goodput_requests_per_second: f64,
    pub goodput_output_tokens_per_second: f64,
    pub class_objective_count: u64,
    pub class_objectives_met: u64,
    pub all_class_objectives_met: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ServingBenchmarkResult {
    pub benchmark_id: String,
    pub workload_contract_id: String,
    pub trace_id: String,
    pub trace_content_id: String,
    pub model: ServingModelIdentity,
    pub evidence_kind: ServingEvidenceKind,
    pub run_id: String,
    pub source_artifact_id: String,
    pub engine: ServingEngineIdentity,
    pub hardware: ServingHardwareTopology,
    pub measurement_tool: String,
    pub software_revision: String,
    pub captured_at_unix_milliseconds: u64,
    pub by_class: Vec<ClassServingBenchmarkResult>,
    pub aggregate: AggregateServingBenchmarkResult,
    pub requests: Vec<RequestServingBenchmarkResult>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ServingBenchmarkReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: ServingBenchmarkResult,
}

impl ServingBenchmarkReport {
    pub fn verify_content_id(&self) -> Result<bool, ServingBenchmarkError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

pub fn canonical_trace_content_id(
    trace: &CanonicalTraceV2,
) -> Result<String, ServingBenchmarkError> {
    let canonical = trace
        .to_canonical_json()
        .map_err(ServingBenchmarkError::Workload)?;
    Ok(blake3::hash(canonical.as_bytes()).to_hex().to_string())
}

pub fn evaluate_measured_serving_benchmark(
    request: &MeasuredServingBenchmarkRequest,
) -> Result<ServingBenchmarkReport, ServingBenchmarkError> {
    let validated = validate_request(request)?;
    let result = evaluate(request, &validated)?;
    let schema_version = SERVING_BENCHMARK_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(ServingBenchmarkReport {
        schema_version,
        content_id,
        result,
    })
}

struct ValidatedRun<'a> {
    trace_content_id: String,
    model: &'a ServingModelIdentity,
    provenance: &'a ServingMeasurementProvenance,
    observations: BTreeMap<u64, &'a MeasuredServingRequestObservation>,
}

fn validate_request(
    request: &MeasuredServingBenchmarkRequest,
) -> Result<ValidatedRun<'_>, ServingBenchmarkError> {
    if request.schema_version != SERVING_BENCHMARK_REQUEST_SCHEMA_VERSION {
        return Err(ServingBenchmarkError::UnsupportedSchemaVersion {
            expected: SERVING_BENCHMARK_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    validate_required("benchmark_id", &request.benchmark_id)?;
    request
        .workload_contract
        .validate()
        .map_err(ServingBenchmarkError::Workload)?;
    request
        .trace
        .validate()
        .map_err(ServingBenchmarkError::Workload)?;
    if request.workload_contract.identity != request.trace.identity {
        return Err(ServingBenchmarkError::TraceModelIdentityMismatch);
    }
    if request.observations.is_empty() {
        return Err(ServingBenchmarkError::InvalidField("observations"));
    }
    let trace_content_id = canonical_trace_content_id(&request.trace)?;
    let mut observations = BTreeMap::new();
    for observation in &request.observations {
        if observations
            .insert(observation.request_id, observation)
            .is_some()
        {
            return Err(ServingBenchmarkError::DuplicateObservation {
                request_id: observation.request_id,
            });
        }
    }
    let first_request = request
        .trace
        .requests
        .first()
        .ok_or(ServingBenchmarkError::InvalidField("trace.requests"))?;
    let first = observations.get(&first_request.request_id).ok_or(
        ServingBenchmarkError::MissingObservation {
            request_id: first_request.request_id,
        },
    )?;
    for trace_request in &request.trace.requests {
        let observation = observations.get(&trace_request.request_id).ok_or(
            ServingBenchmarkError::MissingObservation {
                request_id: trace_request.request_id,
            },
        )?;
        validate_observation(
            observation,
            trace_request,
            &request.workload_contract,
            &request.trace.trace_id,
            &trace_content_id,
        )?;
        if observation.model != first.model {
            return Err(ServingBenchmarkError::RunModelIdentityMismatch {
                request_id: observation.request_id,
            });
        }
        if observation.provenance != first.provenance {
            return Err(ServingBenchmarkError::RunProvenanceMismatch {
                request_id: observation.request_id,
            });
        }
    }
    let trace_ids = request
        .trace
        .requests
        .iter()
        .map(|trace_request| trace_request.request_id)
        .collect::<BTreeSet<_>>();
    if let Some(request_id) = observations
        .keys()
        .find(|request_id| !trace_ids.contains(request_id))
    {
        return Err(ServingBenchmarkError::UnexpectedObservation {
            request_id: *request_id,
        });
    }
    Ok(ValidatedRun {
        trace_content_id,
        model: &first.model,
        provenance: &first.provenance,
        observations,
    })
}

fn validate_observation(
    observation: &MeasuredServingRequestObservation,
    trace_request: &CanonicalTraceRequest,
    workload_contract: &WorkloadContractV2,
    trace_id: &str,
    trace_content_id: &str,
) -> Result<(), ServingBenchmarkError> {
    observation.provenance.validate(observation.request_id)?;
    observation.model.validate(observation.request_id)?;
    if observation.model.model_id != workload_contract.identity.model_id
        || observation.model.model_revision != workload_contract.identity.model_revision
        || observation.model.tokenizer_id != workload_contract.identity.tokenizer_id
        || observation.model.tokenizer_revision != workload_contract.identity.tokenizer_revision
    {
        return Err(ServingBenchmarkError::WorkloadModelIdentityMismatch {
            request_id: observation.request_id,
        });
    }
    if observation.trace_id != trace_id {
        return Err(ServingBenchmarkError::TraceIdMismatch {
            request_id: observation.request_id,
        });
    }
    if observation.trace_content_id != trace_content_id {
        return Err(ServingBenchmarkError::TraceContentIdentityMismatch {
            request_id: observation.request_id,
        });
    }
    check_trace_field(
        observation.request_id,
        "class",
        observation.class == trace_request.class,
    )?;
    check_trace_field(
        observation.request_id,
        "input_tokens",
        observation.input_tokens == trace_request.input_tokens,
    )?;
    check_trace_field(
        observation.request_id,
        "prefix_reused_tokens",
        observation.prefix_reused_tokens == trace_request.prefix_reused_tokens,
    )?;
    check_trace_field(
        observation.request_id,
        "arrival_timestamp_microseconds",
        observation.arrival_timestamp_microseconds == trace_request.arrival_timestamp_microseconds,
    )?;
    let output_matches = if observation.success {
        observation.output_tokens == trace_request.output_tokens
    } else {
        observation.output_tokens <= trace_request.output_tokens
    };
    check_trace_field(observation.request_id, "output_tokens", output_matches)?;
    observation.validate_timestamps()
}

impl ServingModelIdentity {
    fn validate(&self, request_id: u64) -> Result<(), ServingBenchmarkError> {
        for value in [
            self.model_id.as_str(),
            self.model_revision.as_str(),
            self.checkpoint_id.as_str(),
            self.checkpoint_revision.as_str(),
            self.tokenizer_id.as_str(),
            self.tokenizer_revision.as_str(),
        ] {
            if value.trim().is_empty() {
                return Err(ServingBenchmarkError::InvalidModelIdentity { request_id });
            }
        }
        Ok(())
    }
}

impl ServingMeasurementProvenance {
    fn validate(&self, request_id: u64) -> Result<(), ServingBenchmarkError> {
        if self.evidence_kind != ServingEvidenceKind::MeasuredHardware {
            return Err(ServingBenchmarkError::ObservationIsNotMeasured {
                request_id,
                evidence_kind: self.evidence_kind,
            });
        }
        for value in [
            self.run_id.as_str(),
            self.source_artifact_id.as_str(),
            self.engine.name.as_str(),
            self.engine.version.as_str(),
            self.engine.build_id.as_str(),
            self.hardware.device_model.as_str(),
            self.hardware.topology.as_str(),
            self.hardware.interconnect.as_str(),
            self.hardware.device_set_hash.as_str(),
            self.measurement_tool.as_str(),
            self.software_revision.as_str(),
        ] {
            if value.trim().is_empty() {
                return Err(ServingBenchmarkError::InvalidProvenance { request_id });
            }
        }
        if self.hardware.device_count == 0 || self.captured_at_unix_milliseconds == 0 {
            return Err(ServingBenchmarkError::InvalidProvenance { request_id });
        }
        Ok(())
    }
}

impl MeasuredServingRequestObservation {
    fn validate_timestamps(&self) -> Result<(), ServingBenchmarkError> {
        if self.start_timestamp_microseconds < self.arrival_timestamp_microseconds
            || self.end_timestamp_microseconds < self.start_timestamp_microseconds
        {
            return Err(ServingBenchmarkError::InvalidTimestamps {
                request_id: self.request_id,
            });
        }
        match self.first_token_timestamp_microseconds {
            Some(first_token)
                if first_token >= self.start_timestamp_microseconds
                    && first_token <= self.end_timestamp_microseconds => {}
            None if !self.success => {}
            _ => {
                return Err(ServingBenchmarkError::InvalidTimestamps {
                    request_id: self.request_id,
                });
            }
        }
        Ok(())
    }
}

fn evaluate(
    request: &MeasuredServingBenchmarkRequest,
    validated: &ValidatedRun<'_>,
) -> Result<ServingBenchmarkResult, ServingBenchmarkError> {
    let objectives = request
        .workload_contract
        .class_objectives
        .iter()
        .map(|objective| (objective.class, objective))
        .collect::<BTreeMap<_, _>>();
    let mut request_results = Vec::with_capacity(request.trace.requests.len());
    for trace_request in &request.trace.requests {
        let observation = validated
            .observations
            .get(&trace_request.request_id)
            .ok_or(ServingBenchmarkError::MissingObservation {
                request_id: trace_request.request_id,
            })?;
        let objective = objectives.get(&observation.class).ok_or(
            ServingBenchmarkError::MissingClassObjective(observation.class),
        )?;
        request_results.push(evaluate_request(observation, objective));
    }
    let first_arrival = request_results
        .iter()
        .filter_map(|result| {
            validated
                .observations
                .get(&result.request_id)
                .map(|observation| observation.arrival_timestamp_microseconds)
        })
        .min()
        .ok_or(ServingBenchmarkError::InvalidField("observations"))?;
    let last_end = request_results
        .iter()
        .filter_map(|result| {
            validated
                .observations
                .get(&result.request_id)
                .map(|observation| observation.end_timestamp_microseconds)
        })
        .max()
        .ok_or(ServingBenchmarkError::InvalidField("observations"))?;
    if last_end <= first_arrival {
        return Err(ServingBenchmarkError::InvalidRunDuration);
    }
    let duration_seconds = (last_end - first_arrival) as f64 / 1_000_000.0;
    let by_class = request
        .workload_contract
        .class_objectives
        .iter()
        .map(|objective| class_result(objective, &request_results, duration_seconds))
        .collect::<Result<Vec<_>, _>>()?;
    let aggregate = aggregate_result(&request_results, &by_class, duration_seconds)?;
    let provenance = validated.provenance;
    Ok(ServingBenchmarkResult {
        benchmark_id: request.benchmark_id.clone(),
        workload_contract_id: request.workload_contract.contract_id.clone(),
        trace_id: request.trace.trace_id.clone(),
        trace_content_id: validated.trace_content_id.clone(),
        model: validated.model.clone(),
        evidence_kind: provenance.evidence_kind,
        run_id: provenance.run_id.clone(),
        source_artifact_id: provenance.source_artifact_id.clone(),
        engine: provenance.engine.clone(),
        hardware: provenance.hardware.clone(),
        measurement_tool: provenance.measurement_tool.clone(),
        software_revision: provenance.software_revision.clone(),
        captured_at_unix_milliseconds: provenance.captured_at_unix_milliseconds,
        by_class,
        aggregate,
        requests: request_results,
    })
}

fn evaluate_request(
    observation: &MeasuredServingRequestObservation,
    objective: &ClassSloObjective,
) -> RequestServingBenchmarkResult {
    let queue_milliseconds = (observation.start_timestamp_microseconds
        - observation.arrival_timestamp_microseconds) as f64
        / 1_000.0;
    let ttft_milliseconds = observation
        .first_token_timestamp_microseconds
        .map(|first_token| {
            (first_token - observation.arrival_timestamp_microseconds) as f64 / 1_000.0
        });
    let tpot_milliseconds = observation
        .first_token_timestamp_microseconds
        .map(|first_token| {
            let inter_token_count = observation.output_tokens.saturating_sub(1);
            if inter_token_count == 0 {
                0.0
            } else {
                (observation.end_timestamp_microseconds - first_token) as f64
                    / f64::from(inter_token_count)
                    / 1_000.0
            }
        });
    RequestServingBenchmarkResult {
        request_id: observation.request_id,
        class: observation.class,
        success: observation.success,
        input_tokens: observation.input_tokens,
        output_tokens: observation.output_tokens,
        prefix_reused_tokens: observation.prefix_reused_tokens,
        queue_milliseconds,
        ttft_milliseconds,
        tpot_milliseconds,
        ttft_objective_met: observation.success
            && ttft_milliseconds.is_some_and(|value| value <= objective.ttft.maximum_milliseconds),
        tpot_objective_met: observation.success
            && tpot_milliseconds.is_some_and(|value| value <= objective.tpot.maximum_milliseconds),
    }
}

fn class_result(
    objective: &ClassSloObjective,
    requests: &[RequestServingBenchmarkResult],
    duration_seconds: f64,
) -> Result<ClassServingBenchmarkResult, ServingBenchmarkError> {
    let class_requests = requests
        .iter()
        .filter(|request| request.class == objective.class)
        .collect::<Vec<_>>();
    if class_requests.is_empty() {
        return Err(ServingBenchmarkError::MissingRequestsForClass(
            objective.class,
        ));
    }
    let request_count = usize_to_u64(class_requests.len())?;
    let successful_requests = usize_to_u64(
        class_requests
            .iter()
            .filter(|request| request.success)
            .count(),
    )?;
    let ttft_slo_met_requests = usize_to_u64(
        class_requests
            .iter()
            .filter(|request| request.ttft_objective_met)
            .count(),
    )?;
    let tpot_slo_met_requests = usize_to_u64(
        class_requests
            .iter()
            .filter(|request| request.tpot_objective_met)
            .count(),
    )?;
    let slo_met_requests = usize_to_u64(
        class_requests
            .iter()
            .filter(|request| request.meets_objective())
            .count(),
    )?;
    let ttfts = class_requests
        .iter()
        .filter_map(|request| request.ttft_milliseconds)
        .collect::<Vec<_>>();
    let tpots = class_requests
        .iter()
        .filter_map(|request| request.tpot_milliseconds)
        .collect::<Vec<_>>();
    let good_output_tokens = class_requests
        .iter()
        .filter(|request| request.meets_objective())
        .map(|request| u64::from(request.output_tokens))
        .sum::<u64>();
    let ttft_compliant_fraction = ttft_slo_met_requests as f64 / request_count as f64;
    let tpot_compliant_fraction = tpot_slo_met_requests as f64 / request_count as f64;
    Ok(ClassServingBenchmarkResult {
        class: objective.class,
        objective: objective.clone(),
        request_count,
        successful_requests,
        failed_requests: request_count - successful_requests,
        measured_ttft_milliseconds: percentile(&ttfts, objective.ttft.percentile),
        measured_tpot_milliseconds: percentile(&tpots, objective.tpot.percentile),
        ttft_slo_met_requests,
        tpot_slo_met_requests,
        slo_met_requests,
        ttft_compliant_fraction,
        tpot_compliant_fraction,
        ttft_objective_met: ttft_compliant_fraction >= objective.ttft.percentile / 100.0,
        tpot_objective_met: tpot_compliant_fraction >= objective.tpot.percentile / 100.0,
        goodput_requests_per_second: slo_met_requests as f64 / duration_seconds,
        goodput_output_tokens_per_second: good_output_tokens as f64 / duration_seconds,
    })
}

fn aggregate_result(
    requests: &[RequestServingBenchmarkResult],
    by_class: &[ClassServingBenchmarkResult],
    duration_seconds: f64,
) -> Result<AggregateServingBenchmarkResult, ServingBenchmarkError> {
    let request_count = usize_to_u64(requests.len())?;
    let successful_requests =
        usize_to_u64(requests.iter().filter(|request| request.success).count())?;
    let slo_met_requests = usize_to_u64(
        requests
            .iter()
            .filter(|request| request.meets_objective())
            .count(),
    )?;
    let input_tokens = requests
        .iter()
        .map(|request| u64::from(request.input_tokens))
        .sum();
    let output_tokens = requests
        .iter()
        .map(|request| u64::from(request.output_tokens))
        .sum();
    let prefix_reused_tokens = requests
        .iter()
        .map(|request| u64::from(request.prefix_reused_tokens))
        .sum();
    let good_output_tokens = requests
        .iter()
        .filter(|request| request.meets_objective())
        .map(|request| u64::from(request.output_tokens))
        .sum::<u64>();
    let ttfts = requests
        .iter()
        .filter_map(|request| request.ttft_milliseconds)
        .collect::<Vec<_>>();
    let tpots = requests
        .iter()
        .filter_map(|request| request.tpot_milliseconds)
        .collect::<Vec<_>>();
    let class_objective_count = usize_to_u64(by_class.len())?;
    let class_objectives_met = usize_to_u64(
        by_class
            .iter()
            .filter(|class| class.meets_objective())
            .count(),
    )?;
    Ok(AggregateServingBenchmarkResult {
        request_count,
        successful_requests,
        failed_requests: request_count - successful_requests,
        input_tokens,
        output_tokens,
        prefix_reused_tokens,
        duration_seconds,
        throughput_requests_per_second: request_count as f64 / duration_seconds,
        successful_requests_per_second: successful_requests as f64 / duration_seconds,
        p95_ttft_milliseconds: percentile(&ttfts, 95.0),
        p95_tpot_milliseconds: percentile(&tpots, 95.0),
        slo_met_requests,
        goodput_requests_per_second: slo_met_requests as f64 / duration_seconds,
        goodput_output_tokens_per_second: good_output_tokens as f64 / duration_seconds,
        class_objective_count,
        class_objectives_met,
        all_class_objectives_met: class_objective_count == class_objectives_met,
    })
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a ServingBenchmarkResult,
}

fn report_content_id(
    schema_version: u32,
    result: &ServingBenchmarkResult,
) -> Result<String, ServingBenchmarkError> {
    let bytes = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|error| ServingBenchmarkError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

fn check_trace_field(
    request_id: u64,
    field: &'static str,
    matches: bool,
) -> Result<(), ServingBenchmarkError> {
    if matches {
        Ok(())
    } else {
        Err(ServingBenchmarkError::TraceRequestMismatch { request_id, field })
    }
}

fn validate_required(field: &'static str, value: &str) -> Result<(), ServingBenchmarkError> {
    if value.trim().is_empty() {
        Err(ServingBenchmarkError::InvalidField(field))
    } else {
        Ok(())
    }
}

fn percentile(values: &[f64], percentile: f64) -> Option<f64> {
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    let index = ((sorted.len() as f64 * percentile / 100.0).ceil() as usize)
        .saturating_sub(1)
        .min(sorted.len().saturating_sub(1));
    sorted.get(index).copied()
}

fn usize_to_u64(value: usize) -> Result<u64, ServingBenchmarkError> {
    u64::try_from(value).map_err(|_| ServingBenchmarkError::CountOverflow)
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum ServingBenchmarkError {
    #[error("unsupported serving benchmark schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid serving benchmark field {0}")]
    InvalidField(&'static str),
    #[error("workload contract or trace is invalid: {0}")]
    Workload(WorkloadError),
    #[error("canonical trace identity differs from the workload contract")]
    TraceModelIdentityMismatch,
    #[error("duplicate observation for request {request_id}")]
    DuplicateObservation { request_id: u64 },
    #[error("missing observation for request {request_id}")]
    MissingObservation { request_id: u64 },
    #[error("observation references unknown request {request_id}")]
    UnexpectedObservation { request_id: u64 },
    #[error("request {request_id} observation is {evidence_kind:?}, not measured hardware")]
    ObservationIsNotMeasured {
        request_id: u64,
        evidence_kind: ServingEvidenceKind,
    },
    #[error("request {request_id} has invalid model identity")]
    InvalidModelIdentity { request_id: u64 },
    #[error("request {request_id} has invalid measurement provenance")]
    InvalidProvenance { request_id: u64 },
    #[error("request {request_id} model or tokenizer differs from the workload contract")]
    WorkloadModelIdentityMismatch { request_id: u64 },
    #[error("request {request_id} model or checkpoint differs within the measured run")]
    RunModelIdentityMismatch { request_id: u64 },
    #[error("request {request_id} provenance differs within the measured run")]
    RunProvenanceMismatch { request_id: u64 },
    #[error("request {request_id} trace id differs from the canonical trace")]
    TraceIdMismatch { request_id: u64 },
    #[error("request {request_id} trace content identity is invalid")]
    TraceContentIdentityMismatch { request_id: u64 },
    #[error("request {request_id} differs from canonical trace field {field}")]
    TraceRequestMismatch {
        request_id: u64,
        field: &'static str,
    },
    #[error("request {request_id} timestamps are invalid")]
    InvalidTimestamps { request_id: u64 },
    #[error("missing SLO objective for request class {0:?}")]
    MissingClassObjective(AgentTurnClass),
    #[error("trace contains no requests for class {0:?}")]
    MissingRequestsForClass(AgentTurnClass),
    #[error("serving benchmark has an invalid run duration")]
    InvalidRunDuration,
    #[error("serving benchmark count exceeds the supported numeric range")]
    CountOverflow,
    #[error("serving benchmark serialization failed: {0}")]
    Serialization(String),
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::workload::privacy_safe_synthetic_agent_fixture;

    #[test]
    fn measured_run_evaluates_classes_goodput_and_stable_content_identity() {
        let request = benchmark_request();

        let report = evaluate_measured_serving_benchmark(&request).unwrap();
        let same = evaluate_measured_serving_benchmark(&request).unwrap();

        assert_eq!(
            report.schema_version,
            SERVING_BENCHMARK_REPORT_SCHEMA_VERSION
        );
        assert_eq!(report.content_id, same.content_id);
        assert!(report.verify_content_id().unwrap());
        assert_eq!(report.result.by_class.len(), 3);
        assert!(
            report
                .result
                .by_class
                .iter()
                .all(ClassServingBenchmarkResult::meets_objective)
        );
        assert_eq!(report.result.aggregate.request_count, 6);
        assert_eq!(report.result.aggregate.successful_requests, 6);
        assert_eq!(report.result.aggregate.slo_met_requests, 6);
        assert!(report.result.aggregate.goodput_requests_per_second > 0.0);
        assert!(report.result.aggregate.all_class_objectives_met);
        assert_eq!(report.result.engine.name, "vllm");
        assert_eq!(report.result.hardware.device_count, 1);

        let json = serde_json::to_string(&report).unwrap();
        assert!(!json.contains("prompt"));
        assert!(!json.contains("_usd"));
    }

    #[test]
    fn simulated_or_analytical_observations_are_rejected() {
        for evidence_kind in [
            ServingEvidenceKind::Simulated,
            ServingEvidenceKind::Analytical,
        ] {
            let mut request = benchmark_request();
            request.observations[0].provenance.evidence_kind = evidence_kind;

            assert_eq!(
                evaluate_measured_serving_benchmark(&request),
                Err(ServingBenchmarkError::ObservationIsNotMeasured {
                    request_id: 1,
                    evidence_kind,
                })
            );
        }
    }

    #[test]
    fn trace_content_and_model_identity_mismatches_are_rejected() {
        let mut request = benchmark_request();
        request.observations[0].trace_content_id = "wrong".into();
        assert_eq!(
            evaluate_measured_serving_benchmark(&request),
            Err(ServingBenchmarkError::TraceContentIdentityMismatch { request_id: 1 })
        );

        let mut request = benchmark_request();
        request.observations[0].model.checkpoint_revision = "other".into();
        assert_eq!(
            evaluate_measured_serving_benchmark(&request),
            Err(ServingBenchmarkError::RunModelIdentityMismatch { request_id: 2 })
        );

        let mut request = benchmark_request();
        request.observations[0].model.model_revision = "other".into();
        assert_eq!(
            evaluate_measured_serving_benchmark(&request),
            Err(ServingBenchmarkError::WorkloadModelIdentityMismatch { request_id: 1 })
        );
    }

    #[test]
    fn request_geometry_and_timestamp_mismatches_are_rejected() {
        let mut request = benchmark_request();
        request.observations[0].prefix_reused_tokens += 1;
        assert_eq!(
            evaluate_measured_serving_benchmark(&request),
            Err(ServingBenchmarkError::TraceRequestMismatch {
                request_id: 1,
                field: "prefix_reused_tokens",
            })
        );

        let mut request = benchmark_request();
        request.observations[0].start_timestamp_microseconds = 1;
        request.observations[0].first_token_timestamp_microseconds = Some(0);
        assert_eq!(
            evaluate_measured_serving_benchmark(&request),
            Err(ServingBenchmarkError::InvalidTimestamps { request_id: 1 })
        );
    }

    #[test]
    fn failed_requests_reduce_class_slo_compliance_and_goodput() {
        let mut request = benchmark_request();
        let tool = &mut request.observations[0];
        tool.success = false;
        tool.output_tokens = 0;
        tool.first_token_timestamp_microseconds = None;
        tool.end_timestamp_microseconds = tool.start_timestamp_microseconds + 10_000;

        let report = evaluate_measured_serving_benchmark(&request).unwrap();
        let tool = report
            .result
            .by_class
            .iter()
            .find(|result| result.class == AgentTurnClass::Tool)
            .unwrap();

        assert_eq!(tool.failed_requests, 1);
        assert!(!tool.meets_objective());
        assert_eq!(report.result.aggregate.successful_requests, 5);
        assert_eq!(report.result.aggregate.slo_met_requests, 5);
        assert!(!report.result.aggregate.all_class_objectives_met);
    }

    fn benchmark_request() -> MeasuredServingBenchmarkRequest {
        let fixture = privacy_safe_synthetic_agent_fixture();
        let trace_content_id = canonical_trace_content_id(&fixture.trace).unwrap();
        let model = ServingModelIdentity {
            model_id: fixture.trace.identity.model_id.clone(),
            model_revision: fixture.trace.identity.model_revision.clone(),
            checkpoint_id: "qwen3-8b-bf16".into(),
            checkpoint_revision: "checkpoint-sha256".into(),
            tokenizer_id: fixture.trace.identity.tokenizer_id.clone(),
            tokenizer_revision: fixture.trace.identity.tokenizer_revision.clone(),
        };
        let provenance = ServingMeasurementProvenance {
            evidence_kind: ServingEvidenceKind::MeasuredHardware,
            run_id: "vllm-run-1".into(),
            source_artifact_id: "benchmark-artifact-1".into(),
            engine: ServingEngineIdentity {
                name: "vllm".into(),
                version: "0.10.0".into(),
                build_id: "container-digest".into(),
            },
            hardware: ServingHardwareTopology {
                device_model: "H100 SXM".into(),
                device_count: 1,
                topology: "single_device".into(),
                interconnect: "none".into(),
                device_set_hash: "device-set-hash".into(),
            },
            measurement_tool: "foundry-serving-harness".into(),
            software_revision: "harness-revision".into(),
            captured_at_unix_milliseconds: 1_750_000_000_000,
        };
        let timings = fixture
            .observations
            .requests
            .iter()
            .map(|timing| (timing.request_id, timing))
            .collect::<std::collections::BTreeMap<_, _>>();
        let observations = fixture
            .trace
            .requests
            .iter()
            .map(|request| {
                let timing = timings.get(&request.request_id).unwrap();
                MeasuredServingRequestObservation {
                    request_id: request.request_id,
                    model: model.clone(),
                    provenance: provenance.clone(),
                    trace_id: fixture.trace.trace_id.clone(),
                    trace_content_id: trace_content_id.clone(),
                    class: request.class,
                    input_tokens: request.input_tokens,
                    output_tokens: request.output_tokens,
                    prefix_reused_tokens: request.prefix_reused_tokens,
                    arrival_timestamp_microseconds: request.arrival_timestamp_microseconds,
                    start_timestamp_microseconds: request.arrival_timestamp_microseconds + 1_000,
                    first_token_timestamp_microseconds: Some(
                        timing.first_token_timestamp_microseconds,
                    ),
                    end_timestamp_microseconds: timing.completion_timestamp_microseconds,
                    success: true,
                }
            })
            .collect();
        MeasuredServingBenchmarkRequest {
            schema_version: SERVING_BENCHMARK_REQUEST_SCHEMA_VERSION,
            benchmark_id: "vllm-qwen-agentic-1".into(),
            workload_contract: fixture.contract,
            trace: fixture.trace,
            observations,
        }
    }
}
