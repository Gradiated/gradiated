use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use thiserror::Error;

pub const WORKLOAD_SCHEMA_VERSION: u32 = 2;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelTokenizerIdentity {
    pub model_id: String,
    pub model_revision: String,
    pub tokenizer_id: String,
    pub tokenizer_revision: String,
}

impl ModelTokenizerIdentity {
    pub fn validate(&self) -> Result<(), WorkloadError> {
        for (field, value) in [
            ("identity.model_id", self.model_id.as_str()),
            ("identity.model_revision", self.model_revision.as_str()),
            ("identity.tokenizer_id", self.tokenizer_id.as_str()),
            (
                "identity.tokenizer_revision",
                self.tokenizer_revision.as_str(),
            ),
        ] {
            if value.trim().is_empty() {
                return Err(WorkloadError::InvalidField(field));
            }
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Hash, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentTurnClass {
    Tool,
    Coding,
    LongAgent,
}

impl AgentTurnClass {
    pub const ALL: [Self; 3] = [Self::Tool, Self::Coding, Self::LongAgent];
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PercentileSloObjective {
    pub percentile: f64,
    pub maximum_milliseconds: f64,
}

impl PercentileSloObjective {
    fn validate(&self, field: &'static str) -> Result<(), WorkloadError> {
        if !self.percentile.is_finite() || self.percentile <= 0.0 || self.percentile > 100.0 {
            return Err(WorkloadError::InvalidField(field));
        }
        if !self.maximum_milliseconds.is_finite() || self.maximum_milliseconds <= 0.0 {
            return Err(WorkloadError::InvalidField(field));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ClassSloObjective {
    pub class: AgentTurnClass,
    pub ttft: PercentileSloObjective,
    pub tpot: PercentileSloObjective,
}

impl ClassSloObjective {
    fn validate(&self) -> Result<(), WorkloadError> {
        self.ttft.validate("class_objectives.ttft")?;
        self.tpot.validate("class_objectives.tpot")
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WorkloadContractV2 {
    pub schema_version: u32,
    pub contract_id: String,
    pub identity: ModelTokenizerIdentity,
    pub class_objectives: Vec<ClassSloObjective>,
}

impl WorkloadContractV2 {
    pub fn validate(&self) -> Result<(), WorkloadError> {
        validate_version("workload_contract", self.schema_version)?;
        if self.contract_id.trim().is_empty() {
            return Err(WorkloadError::InvalidField("contract_id"));
        }
        self.identity.validate()?;
        let mut classes = BTreeSet::new();
        for objective in &self.class_objectives {
            objective.validate()?;
            if !classes.insert(objective.class) {
                return Err(WorkloadError::DuplicateClassObjective(objective.class));
            }
        }
        for class in AgentTurnClass::ALL {
            if !classes.contains(&class) {
                return Err(WorkloadError::MissingClassObjective(class));
            }
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TimestampBasis {
    RelativeMicroseconds,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "provenance", rename_all = "snake_case")]
pub enum TraceProvenance {
    Synthetic {
        generator_id: String,
        seed: u64,
    },
    AnonymizedImport {
        source_label: String,
        privacy_review_id: String,
    },
}

impl TraceProvenance {
    fn validate(&self) -> Result<(), WorkloadError> {
        match self {
            Self::Synthetic { generator_id, .. } => {
                if generator_id.trim().is_empty() {
                    return Err(WorkloadError::InvalidField("provenance.generator_id"));
                }
            }
            Self::AnonymizedImport {
                source_label,
                privacy_review_id,
            } => {
                if source_label.trim().is_empty() {
                    return Err(WorkloadError::InvalidField("provenance.source_label"));
                }
                if privacy_review_id.trim().is_empty() {
                    return Err(WorkloadError::InvalidField("provenance.privacy_review_id"));
                }
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CanonicalTraceRequest {
    pub request_id: u64,
    pub class: AgentTurnClass,
    pub arrival_timestamp_microseconds: u64,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub prefix_reused_tokens: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CanonicalTraceV2 {
    pub schema_version: u32,
    pub trace_id: String,
    pub provenance: TraceProvenance,
    pub timestamp_basis: TimestampBasis,
    pub identity: ModelTokenizerIdentity,
    pub requests: Vec<CanonicalTraceRequest>,
}

impl CanonicalTraceV2 {
    pub fn validate(&self) -> Result<(), WorkloadError> {
        validate_version("canonical_trace", self.schema_version)?;
        if self.trace_id.trim().is_empty() {
            return Err(WorkloadError::InvalidField("trace_id"));
        }
        self.provenance.validate()?;
        self.identity.validate()?;
        if self.requests.is_empty() {
            return Err(WorkloadError::InvalidField("requests"));
        }
        let mut request_ids = BTreeSet::new();
        let mut previous_key = None;
        for request in &self.requests {
            if !request_ids.insert(request.request_id) {
                return Err(WorkloadError::DuplicateRequestId {
                    request_id: request.request_id,
                });
            }
            if request.input_tokens == 0 {
                return Err(WorkloadError::InvalidRequestField {
                    request_id: request.request_id,
                    field: "input_tokens",
                });
            }
            if request.output_tokens == 0 {
                return Err(WorkloadError::InvalidRequestField {
                    request_id: request.request_id,
                    field: "output_tokens",
                });
            }
            if request.prefix_reused_tokens > request.input_tokens {
                return Err(WorkloadError::PrefixExceedsInput {
                    request_id: request.request_id,
                });
            }
            let key = (request.arrival_timestamp_microseconds, request.request_id);
            if previous_key.is_some_and(|previous| key < previous) {
                return Err(WorkloadError::NonCanonicalRequestOrder);
            }
            previous_key = Some(key);
        }
        Ok(())
    }

    pub fn to_canonical_json(&self) -> Result<String, WorkloadError> {
        self.validate()?;
        serde_json::to_string(self).map_err(|error| WorkloadError::Serialization(error.to_string()))
    }

    pub fn from_canonical_json(json: &str) -> Result<Self, WorkloadError> {
        let trace: Self = serde_json::from_str(json)
            .map_err(|error| WorkloadError::Serialization(error.to_string()))?;
        trace.validate()?;
        Ok(trace)
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RequestTimingObservation {
    pub request_id: u64,
    pub first_token_timestamp_microseconds: u64,
    pub completion_timestamp_microseconds: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TraceObservations {
    pub trace_id: String,
    pub requests: Vec<RequestTimingObservation>,
}

impl TraceObservations {
    fn validate_against(&self, trace: &CanonicalTraceV2) -> Result<(), WorkloadError> {
        if self.trace_id != trace.trace_id {
            return Err(WorkloadError::TraceIdMismatch);
        }
        let trace_requests = trace
            .requests
            .iter()
            .map(|request| (request.request_id, request))
            .collect::<BTreeMap<_, _>>();
        let mut observed_ids = BTreeSet::new();
        for observation in &self.requests {
            if !observed_ids.insert(observation.request_id) {
                return Err(WorkloadError::DuplicateObservation {
                    request_id: observation.request_id,
                });
            }
            let request = trace_requests.get(&observation.request_id).ok_or(
                WorkloadError::UnexpectedObservation {
                    request_id: observation.request_id,
                },
            )?;
            if observation.first_token_timestamp_microseconds
                < request.arrival_timestamp_microseconds
                || observation.completion_timestamp_microseconds
                    < observation.first_token_timestamp_microseconds
            {
                return Err(WorkloadError::InvalidObservationTimestamps {
                    request_id: observation.request_id,
                });
            }
        }
        for request in &trace.requests {
            if !observed_ids.contains(&request.request_id) {
                return Err(WorkloadError::MissingObservation {
                    request_id: request.request_id,
                });
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RequestSloEvaluation {
    pub request_id: u64,
    pub class: AgentTurnClass,
    pub ttft_milliseconds: f64,
    pub tpot_milliseconds: f64,
    pub ttft_objective_met: bool,
    pub tpot_objective_met: bool,
}

impl RequestSloEvaluation {
    pub const fn meets_objective(&self) -> bool {
        self.ttft_objective_met && self.tpot_objective_met
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ClassSloEvaluation {
    pub class: AgentTurnClass,
    pub request_count: u64,
    pub objective: ClassSloObjective,
    pub measured_ttft_milliseconds: f64,
    pub measured_tpot_milliseconds: f64,
    pub ttft_objective_met: bool,
    pub tpot_objective_met: bool,
    pub slo_met_requests: u64,
    pub slo_met_fraction: f64,
}

impl ClassSloEvaluation {
    pub const fn meets_objective(&self) -> bool {
        self.ttft_objective_met && self.tpot_objective_met
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AggregateSloEvaluation {
    pub request_count: u64,
    pub mean_ttft_milliseconds: f64,
    pub p95_ttft_milliseconds: f64,
    pub mean_tpot_milliseconds: f64,
    pub p95_tpot_milliseconds: f64,
    pub ttft_slo_met_requests: u64,
    pub tpot_slo_met_requests: u64,
    pub slo_met_requests: u64,
    pub slo_met_fraction: f64,
    pub class_objective_count: u64,
    pub class_objectives_met: u64,
    pub all_class_objectives_met: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WorkloadSloReport {
    pub contract_id: String,
    pub trace_id: String,
    pub by_class: Vec<ClassSloEvaluation>,
    pub aggregate: AggregateSloEvaluation,
    pub requests: Vec<RequestSloEvaluation>,
}

impl WorkloadSloReport {
    pub const fn meets_contract(&self) -> bool {
        self.aggregate.all_class_objectives_met
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SyntheticAgentFixture {
    pub contract: WorkloadContractV2,
    pub trace: CanonicalTraceV2,
    pub observations: TraceObservations,
}

pub fn evaluate_trace(
    contract: &WorkloadContractV2,
    trace: &CanonicalTraceV2,
    observations: &TraceObservations,
) -> Result<WorkloadSloReport, WorkloadError> {
    contract.validate()?;
    trace.validate()?;
    if contract.identity != trace.identity {
        return Err(WorkloadError::IdentityMismatch);
    }
    observations.validate_against(trace)?;
    let objectives = contract
        .class_objectives
        .iter()
        .map(|objective| (objective.class, objective))
        .collect::<BTreeMap<_, _>>();
    let timings = observations
        .requests
        .iter()
        .map(|observation| (observation.request_id, observation))
        .collect::<BTreeMap<_, _>>();
    let mut requests = Vec::with_capacity(trace.requests.len());
    for request in &trace.requests {
        let objective = objectives
            .get(&request.class)
            .ok_or(WorkloadError::MissingClassObjective(request.class))?;
        let timing = timings
            .get(&request.request_id)
            .ok_or(WorkloadError::MissingObservation {
                request_id: request.request_id,
            })?;
        let ttft_milliseconds = (timing.first_token_timestamp_microseconds
            - request.arrival_timestamp_microseconds) as f64
            / 1_000.0;
        let inter_token_count = request.output_tokens.saturating_sub(1);
        let tpot_milliseconds = if inter_token_count == 0 {
            0.0
        } else {
            (timing.completion_timestamp_microseconds - timing.first_token_timestamp_microseconds)
                as f64
                / f64::from(inter_token_count)
                / 1_000.0
        };
        requests.push(RequestSloEvaluation {
            request_id: request.request_id,
            class: request.class,
            ttft_milliseconds,
            tpot_milliseconds,
            ttft_objective_met: ttft_milliseconds <= objective.ttft.maximum_milliseconds,
            tpot_objective_met: tpot_milliseconds <= objective.tpot.maximum_milliseconds,
        });
    }
    let mut by_class = Vec::with_capacity(contract.class_objectives.len());
    for objective in &contract.class_objectives {
        let class_requests = requests
            .iter()
            .filter(|request| request.class == objective.class)
            .collect::<Vec<_>>();
        if class_requests.is_empty() {
            return Err(WorkloadError::MissingRequestsForClass(objective.class));
        }
        let ttfts = class_requests
            .iter()
            .map(|request| request.ttft_milliseconds)
            .collect::<Vec<_>>();
        let tpots = class_requests
            .iter()
            .map(|request| request.tpot_milliseconds)
            .collect::<Vec<_>>();
        let measured_ttft_milliseconds = percentile(&ttfts, objective.ttft.percentile);
        let measured_tpot_milliseconds = percentile(&tpots, objective.tpot.percentile);
        let request_count = usize_to_u64(class_requests.len())?;
        let slo_met_requests = usize_to_u64(
            class_requests
                .iter()
                .filter(|request| request.meets_objective())
                .count(),
        )?;
        by_class.push(ClassSloEvaluation {
            class: objective.class,
            request_count,
            objective: objective.clone(),
            measured_ttft_milliseconds,
            measured_tpot_milliseconds,
            ttft_objective_met: measured_ttft_milliseconds <= objective.ttft.maximum_milliseconds,
            tpot_objective_met: measured_tpot_milliseconds <= objective.tpot.maximum_milliseconds,
            slo_met_requests,
            slo_met_fraction: slo_met_requests as f64 / request_count as f64,
        });
    }
    let ttfts = requests
        .iter()
        .map(|request| request.ttft_milliseconds)
        .collect::<Vec<_>>();
    let tpots = requests
        .iter()
        .map(|request| request.tpot_milliseconds)
        .collect::<Vec<_>>();
    let request_count = usize_to_u64(requests.len())?;
    let ttft_slo_met_requests = usize_to_u64(
        requests
            .iter()
            .filter(|request| request.ttft_objective_met)
            .count(),
    )?;
    let tpot_slo_met_requests = usize_to_u64(
        requests
            .iter()
            .filter(|request| request.tpot_objective_met)
            .count(),
    )?;
    let slo_met_requests = usize_to_u64(
        requests
            .iter()
            .filter(|request| request.meets_objective())
            .count(),
    )?;
    let class_objective_count = usize_to_u64(by_class.len())?;
    let class_objectives_met = usize_to_u64(
        by_class
            .iter()
            .filter(|class| class.meets_objective())
            .count(),
    )?;
    Ok(WorkloadSloReport {
        contract_id: contract.contract_id.clone(),
        trace_id: trace.trace_id.clone(),
        by_class,
        aggregate: AggregateSloEvaluation {
            request_count,
            mean_ttft_milliseconds: mean(&ttfts),
            p95_ttft_milliseconds: percentile(&ttfts, 95.0),
            mean_tpot_milliseconds: mean(&tpots),
            p95_tpot_milliseconds: percentile(&tpots, 95.0),
            ttft_slo_met_requests,
            tpot_slo_met_requests,
            slo_met_requests,
            slo_met_fraction: slo_met_requests as f64 / request_count as f64,
            class_objective_count,
            class_objectives_met,
            all_class_objectives_met: class_objective_count == class_objectives_met,
        },
        requests,
    })
}

pub fn privacy_safe_synthetic_agent_fixture() -> SyntheticAgentFixture {
    let identity = ModelTokenizerIdentity {
        model_id: "Qwen/Qwen3-8B".into(),
        model_revision: "synthetic-workload-reference-v2".into(),
        tokenizer_id: "Qwen/Qwen3-8B".into(),
        tokenizer_revision: "synthetic-workload-reference-v2".into(),
    };
    SyntheticAgentFixture {
        contract: WorkloadContractV2 {
            schema_version: WORKLOAD_SCHEMA_VERSION,
            contract_id: "synthetic-agent-slo-v2".into(),
            identity: identity.clone(),
            class_objectives: vec![
                class_objective(AgentTurnClass::Tool, 100.0, 25.0),
                class_objective(AgentTurnClass::Coding, 500.0, 50.0),
                class_objective(AgentTurnClass::LongAgent, 1_500.0, 70.0),
            ],
        },
        trace: CanonicalTraceV2 {
            schema_version: WORKLOAD_SCHEMA_VERSION,
            trace_id: "privacy-safe-synthetic-agent-trace-v2".into(),
            provenance: TraceProvenance::Synthetic {
                generator_id: "foundry-built-in-agent-generator-v2".into(),
                seed: 20_260_711,
            },
            timestamp_basis: TimestampBasis::RelativeMicroseconds,
            identity,
            requests: vec![
                trace_request(1, AgentTurnClass::Tool, 0, 256, 16, 128),
                trace_request(2, AgentTurnClass::Tool, 1_000_000, 512, 32, 400),
                trace_request(3, AgentTurnClass::Coding, 2_000_000, 4_096, 128, 2_048),
                trace_request(4, AgentTurnClass::Coding, 3_000_000, 8_192, 256, 6_144),
                trace_request(5, AgentTurnClass::LongAgent, 4_000_000, 32_768, 256, 24_576),
                trace_request(6, AgentTurnClass::LongAgent, 5_000_000, 65_536, 512, 50_000),
            ],
        },
        observations: TraceObservations {
            trace_id: "privacy-safe-synthetic-agent-trace-v2".into(),
            requests: vec![
                timing(1, 40_000, 265_000),
                timing(2, 1_060_000, 1_680_000),
                timing(3, 2_250_000, 6_695_000),
                timing(4, 3_350_000, 14_825_000),
                timing(5, 4_900_000, 18_925_000),
                timing(6, 6_200_000, 39_415_000),
            ],
        },
    }
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum WorkloadError {
    #[error("unsupported {artifact} schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion {
        artifact: &'static str,
        expected: u32,
        actual: u32,
    },
    #[error("invalid workload field {0}")]
    InvalidField(&'static str),
    #[error("request {request_id} has invalid field {field}")]
    InvalidRequestField {
        request_id: u64,
        field: &'static str,
    },
    #[error("request {request_id} reuses more prefix tokens than it has input tokens")]
    PrefixExceedsInput { request_id: u64 },
    #[error("duplicate request id {request_id}")]
    DuplicateRequestId { request_id: u64 },
    #[error("canonical trace requests are not ordered by arrival timestamp and request id")]
    NonCanonicalRequestOrder,
    #[error("duplicate class objective {0:?}")]
    DuplicateClassObjective(AgentTurnClass),
    #[error("missing class objective {0:?}")]
    MissingClassObjective(AgentTurnClass),
    #[error("trace does not contain requests for class {0:?}")]
    MissingRequestsForClass(AgentTurnClass),
    #[error("model or tokenizer identity differs between workload contract and trace")]
    IdentityMismatch,
    #[error("observation trace id differs from canonical trace")]
    TraceIdMismatch,
    #[error("missing timing observation for request {request_id}")]
    MissingObservation { request_id: u64 },
    #[error("timing observation references unknown request {request_id}")]
    UnexpectedObservation { request_id: u64 },
    #[error("duplicate timing observation for request {request_id}")]
    DuplicateObservation { request_id: u64 },
    #[error("timing observation has invalid timestamps for request {request_id}")]
    InvalidObservationTimestamps { request_id: u64 },
    #[error("workload count exceeds the supported numeric range")]
    CountOverflow,
    #[error("canonical trace serialization failed: {0}")]
    Serialization(String),
}

fn validate_version(artifact: &'static str, actual: u32) -> Result<(), WorkloadError> {
    if actual == WORKLOAD_SCHEMA_VERSION {
        Ok(())
    } else {
        Err(WorkloadError::UnsupportedSchemaVersion {
            artifact,
            expected: WORKLOAD_SCHEMA_VERSION,
            actual,
        })
    }
}

fn class_objective(
    class: AgentTurnClass,
    maximum_ttft_milliseconds: f64,
    maximum_tpot_milliseconds: f64,
) -> ClassSloObjective {
    ClassSloObjective {
        class,
        ttft: PercentileSloObjective {
            percentile: 95.0,
            maximum_milliseconds: maximum_ttft_milliseconds,
        },
        tpot: PercentileSloObjective {
            percentile: 95.0,
            maximum_milliseconds: maximum_tpot_milliseconds,
        },
    }
}

fn trace_request(
    request_id: u64,
    class: AgentTurnClass,
    arrival_timestamp_microseconds: u64,
    input_tokens: u32,
    output_tokens: u32,
    prefix_reused_tokens: u32,
) -> CanonicalTraceRequest {
    CanonicalTraceRequest {
        request_id,
        class,
        arrival_timestamp_microseconds,
        input_tokens,
        output_tokens,
        prefix_reused_tokens,
    }
}

fn timing(
    request_id: u64,
    first_token_timestamp_microseconds: u64,
    completion_timestamp_microseconds: u64,
) -> RequestTimingObservation {
    RequestTimingObservation {
        request_id,
        first_token_timestamp_microseconds,
        completion_timestamp_microseconds,
    }
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

fn usize_to_u64(value: usize) -> Result<u64, WorkloadError> {
    u64::try_from(value).map_err(|_| WorkloadError::CountOverflow)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn synthetic_fixture_is_privacy_safe_and_canonically_round_trips() {
        let fixture = privacy_safe_synthetic_agent_fixture();

        assert!(matches!(
            fixture.trace.provenance,
            TraceProvenance::Synthetic { .. }
        ));
        assert_eq!(fixture.contract.class_objectives.len(), 3);
        assert_eq!(fixture.trace.requests.len(), 6);
        assert!(
            fixture
                .trace
                .requests
                .iter()
                .all(|request| request.prefix_reused_tokens <= request.input_tokens)
        );

        let json = fixture.trace.to_canonical_json().unwrap();
        let imported = CanonicalTraceV2::from_canonical_json(&json).unwrap();

        assert_eq!(imported, fixture.trace);
        assert_eq!(imported.to_canonical_json().unwrap(), json);
        assert!(!json.contains("prompt"));
        assert!(!json.contains("content"));
    }

    #[test]
    fn evaluates_each_agent_class_and_the_aggregate() {
        let fixture = privacy_safe_synthetic_agent_fixture();

        let report =
            evaluate_trace(&fixture.contract, &fixture.trace, &fixture.observations).unwrap();

        assert_eq!(report.by_class.len(), 3);
        assert!(
            report
                .by_class
                .iter()
                .all(ClassSloEvaluation::meets_objective)
        );
        assert_eq!(report.aggregate.request_count, 6);
        assert_eq!(report.aggregate.class_objectives_met, 3);
        assert_eq!(report.aggregate.slo_met_requests, 6);
        assert!(report.aggregate.all_class_objectives_met);
        assert!(report.meets_contract());

        let tool = report
            .by_class
            .iter()
            .find(|class| class.class == AgentTurnClass::Tool)
            .unwrap();
        assert_eq!(tool.measured_ttft_milliseconds, 60.0);
        assert_eq!(tool.measured_tpot_milliseconds, 20.0);
    }

    #[test]
    fn one_class_regression_fails_that_class_and_the_aggregate() {
        let mut fixture = privacy_safe_synthetic_agent_fixture();
        let coding = fixture
            .observations
            .requests
            .iter_mut()
            .find(|request| request.request_id == 3)
            .unwrap();
        coding.first_token_timestamp_microseconds = 3_000_000;

        let report =
            evaluate_trace(&fixture.contract, &fixture.trace, &fixture.observations).unwrap();
        let coding = report
            .by_class
            .iter()
            .find(|class| class.class == AgentTurnClass::Coding)
            .unwrap();

        assert!(!coding.ttft_objective_met);
        assert!(coding.tpot_objective_met);
        assert!(!report.aggregate.all_class_objectives_met);
        assert_eq!(report.aggregate.class_objectives_met, 2);
        assert!(!report.meets_contract());
    }

    #[test]
    fn rejects_identity_mismatch_and_incomplete_observations() {
        let mut fixture = privacy_safe_synthetic_agent_fixture();
        fixture.trace.identity.tokenizer_revision = "different".into();

        assert_eq!(
            evaluate_trace(&fixture.contract, &fixture.trace, &fixture.observations),
            Err(WorkloadError::IdentityMismatch)
        );

        let mut fixture = privacy_safe_synthetic_agent_fixture();
        fixture.observations.requests.pop();
        assert_eq!(
            evaluate_trace(&fixture.contract, &fixture.trace, &fixture.observations),
            Err(WorkloadError::MissingObservation { request_id: 6 })
        );
    }

    #[test]
    fn rejects_invalid_prefixes_ordering_and_class_objectives() {
        let mut fixture = privacy_safe_synthetic_agent_fixture();
        fixture.trace.requests[0].prefix_reused_tokens = fixture.trace.requests[0].input_tokens + 1;
        assert_eq!(
            fixture.trace.validate(),
            Err(WorkloadError::PrefixExceedsInput { request_id: 1 })
        );

        let mut fixture = privacy_safe_synthetic_agent_fixture();
        fixture.trace.requests.swap(0, 1);
        assert_eq!(
            fixture.trace.validate(),
            Err(WorkloadError::NonCanonicalRequestOrder)
        );

        let mut fixture = privacy_safe_synthetic_agent_fixture();
        fixture.contract.class_objectives[1].class = AgentTurnClass::Tool;
        assert_eq!(
            fixture.contract.validate(),
            Err(WorkloadError::DuplicateClassObjective(AgentTurnClass::Tool))
        );
    }
}
