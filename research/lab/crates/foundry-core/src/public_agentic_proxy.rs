use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::workload::{
    AgentTurnClass, CanonicalTraceRequest, CanonicalTraceV2, ClassSloObjective,
    ModelTokenizerIdentity, PercentileSloObjective, TimestampBasis, TraceProvenance,
    WORKLOAD_SCHEMA_VERSION, WorkloadContractV2, WorkloadError,
};

pub const PUBLIC_AGENTIC_PROXY_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const PUBLIC_AGENTIC_PROXY_REPORT_SCHEMA_VERSION: u32 = 1;
pub const PUBLIC_AGENTIC_PROXY_GENERATOR_ID: &str = "foundry-public-agentic-proxy-v1";
pub const PUBLIC_AGENTIC_PROXY_DISCLAIMER: &str = "Synthetic proxy based only on AA-AgentPerf's public workload geometry; it is not AA-AgentPerf's private test set and does not reproduce benchmark prompts, outputs, scoring, or measured results.";
pub const PUBLIC_AGENTIC_PROXY_ASSUMPTION_NOTICE: &str = "Session count, turn mix, output lengths, prefix-reuse ratios, arrival stagger, delay distribution beyond its public median, and SLO tiers are synthetic controls rather than AA-AgentPerf specifications.";

const PUBLIC_MINIMUM_INPUT_TOKENS: u32 = 5_000;
const PUBLIC_MAXIMUM_INPUT_TOKENS: u32 = 131_000;
const PUBLIC_APPROXIMATE_MEAN_INPUT_TOKENS: u32 = 27_000;
const PUBLIC_MEDIAN_TOOL_DELAY_MILLISECONDS: u64 = 1_000;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PublicAgenticBasis {
    pub source_label: String,
    pub minimum_input_tokens: u32,
    pub maximum_input_tokens: u32,
    pub approximate_mean_input_tokens: u32,
    pub median_tool_delay_milliseconds: u64,
    pub dynamic_prefixes: bool,
    pub concurrent_sessions: bool,
    pub private_test_set_used: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct InputLengthBucket {
    pub input_tokens: u32,
    pub count: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ClassOutputTokens {
    pub class: AgentTurnClass,
    pub output_tokens: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SyntheticAgenticDesign {
    pub session_count: u32,
    pub turns_per_session: u32,
    pub session_start_stagger_milliseconds: u64,
    pub tool_delay_milliseconds_by_turn: Vec<u64>,
    pub prefix_reuse_basis_points_by_turn: Vec<u32>,
    pub class_by_turn: Vec<AgentTurnClass>,
    pub input_length_histogram: Vec<InputLengthBucket>,
    pub output_tokens_by_class: Vec<ClassOutputTokens>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgenticSloTier {
    pub tier_id: String,
    pub class: AgentTurnClass,
    pub percentile: f64,
    pub maximum_ttft_milliseconds: f64,
    pub minimum_output_tokens_per_second: f64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgenticProxyClaimGates {
    pub aa_agentperf_score_claim_permitted: bool,
    pub measured_performance_claim_permitted: bool,
    pub nvidia_performance_claim_permitted: bool,
    pub provider_performance_claim_permitted: bool,
    pub cost_claim_permitted: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PublicAgenticProxyRequest {
    pub schema_version: u32,
    pub proxy_id: String,
    pub seed: u64,
    pub identity: ModelTokenizerIdentity,
    pub public_basis: PublicAgenticBasis,
    pub synthetic_design: SyntheticAgenticDesign,
    pub slo_tiers: Vec<AgenticSloTier>,
    pub claim_gates: AgenticProxyClaimGates,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ResolvedAgenticSloTier {
    pub tier_id: String,
    pub class: AgentTurnClass,
    pub percentile: f64,
    pub maximum_ttft_milliseconds: f64,
    pub minimum_output_tokens_per_second: f64,
    pub maximum_tpot_milliseconds: f64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgenticSessionTurn {
    pub request_id: u64,
    pub turn_index: u32,
    pub class: AgentTurnClass,
    pub arrival_timestamp_microseconds: u64,
    pub preceding_tool_delay_milliseconds: Option<u64>,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub prefix_reused_tokens: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgenticSession {
    pub session_id: String,
    pub start_timestamp_microseconds: u64,
    pub end_timestamp_microseconds: u64,
    pub turns: Vec<AgenticSessionTurn>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PublicAgenticProxySummary {
    pub session_count: u64,
    pub request_count: u64,
    pub minimum_input_tokens: u32,
    pub maximum_input_tokens: u32,
    pub mean_input_tokens: f64,
    pub total_input_tokens: u64,
    pub total_output_tokens: u64,
    pub tool_call_count: u64,
    pub median_tool_delay_milliseconds: u64,
    pub peak_active_session_windows: u64,
    pub dynamic_prefix_session_count: u64,
    pub interleaved_session_switch_count: u64,
    pub trace_duration_milliseconds: u64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PublicAgenticProxyResult {
    pub proxy_id: String,
    pub disclaimer: String,
    pub synthetic_assumption_notice: String,
    pub request_content_id: String,
    pub trace_content_id: String,
    pub workload_contract_content_id: String,
    pub public_basis: PublicAgenticBasis,
    pub synthetic_design: SyntheticAgenticDesign,
    pub slo_tiers: Vec<ResolvedAgenticSloTier>,
    pub workload_contract: WorkloadContractV2,
    pub trace: CanonicalTraceV2,
    pub sessions: Vec<AgenticSession>,
    pub summary: PublicAgenticProxySummary,
    pub claim_gates: AgenticProxyClaimGates,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PublicAgenticProxyReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: PublicAgenticProxyResult,
}

impl PublicAgenticProxyReport {
    pub fn verify_content_id(&self) -> Result<bool, PublicAgenticProxyError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

#[derive(Clone, Debug)]
struct PendingTurn {
    session_index: u32,
    turn_index: u32,
    class: AgentTurnClass,
    arrival_timestamp_microseconds: u64,
    preceding_tool_delay_milliseconds: Option<u64>,
    input_tokens: u32,
    output_tokens: u32,
    prefix_reused_tokens: u32,
}

pub fn generate_public_agentic_proxy(
    request: &PublicAgenticProxyRequest,
) -> Result<PublicAgenticProxyReport, PublicAgenticProxyError> {
    validate_request(request)?;
    let design = &request.synthetic_design;
    let session_count = usize::try_from(design.session_count)
        .map_err(|_| PublicAgenticProxyError::CountOverflow)?;
    let turns_per_session = usize::try_from(design.turns_per_session)
        .map_err(|_| PublicAgenticProxyError::CountOverflow)?;
    let mut input_lengths = expand_input_lengths(&design.input_length_histogram)?;
    deterministic_shuffle(&mut input_lengths, request.seed);
    let output_tokens = design
        .output_tokens_by_class
        .iter()
        .map(|value| (value.class, value.output_tokens))
        .collect::<BTreeMap<_, _>>();
    let mut pending = Vec::with_capacity(input_lengths.len());
    for session_index in 0..session_count {
        let session_index_u64 =
            u64::try_from(session_index).map_err(|_| PublicAgenticProxyError::CountOverflow)?;
        let mut arrival_milliseconds = session_index_u64
            .checked_mul(design.session_start_stagger_milliseconds)
            .ok_or(PublicAgenticProxyError::ArithmeticOverflow)?;
        for turn_index in 0..turns_per_session {
            let preceding_tool_delay_milliseconds = if turn_index == 0 {
                None
            } else {
                let delay = design.tool_delay_milliseconds_by_turn[turn_index - 1];
                arrival_milliseconds = arrival_milliseconds
                    .checked_add(delay)
                    .ok_or(PublicAgenticProxyError::ArithmeticOverflow)?;
                Some(delay)
            };
            let index = session_index
                .checked_mul(turns_per_session)
                .and_then(|base| base.checked_add(turn_index))
                .ok_or(PublicAgenticProxyError::ArithmeticOverflow)?;
            let input_tokens = input_lengths[index];
            let prefix_reused_tokens = u32::try_from(
                u64::from(input_tokens)
                    * u64::from(design.prefix_reuse_basis_points_by_turn[turn_index])
                    / 10_000,
            )
            .map_err(|_| PublicAgenticProxyError::ArithmeticOverflow)?;
            let class = design.class_by_turn[turn_index];
            pending.push(PendingTurn {
                session_index: u32::try_from(session_index)
                    .map_err(|_| PublicAgenticProxyError::CountOverflow)?,
                turn_index: u32::try_from(turn_index)
                    .map_err(|_| PublicAgenticProxyError::CountOverflow)?,
                class,
                arrival_timestamp_microseconds: arrival_milliseconds
                    .checked_mul(1_000)
                    .ok_or(PublicAgenticProxyError::ArithmeticOverflow)?,
                preceding_tool_delay_milliseconds,
                input_tokens,
                output_tokens: output_tokens[&class],
                prefix_reused_tokens,
            });
        }
    }
    pending.sort_by_key(|turn| {
        (
            turn.arrival_timestamp_microseconds,
            turn.session_index,
            turn.turn_index,
        )
    });
    let mut session_turns = vec![Vec::with_capacity(turns_per_session); session_count];
    let mut trace_requests = Vec::with_capacity(pending.len());
    let mut ordered_session_indices = Vec::with_capacity(pending.len());
    for (index, turn) in pending.into_iter().enumerate() {
        let request_id =
            u64::try_from(index + 1).map_err(|_| PublicAgenticProxyError::CountOverflow)?;
        trace_requests.push(CanonicalTraceRequest {
            request_id,
            class: turn.class,
            arrival_timestamp_microseconds: turn.arrival_timestamp_microseconds,
            input_tokens: turn.input_tokens,
            output_tokens: turn.output_tokens,
            prefix_reused_tokens: turn.prefix_reused_tokens,
        });
        ordered_session_indices.push(turn.session_index);
        session_turns[usize::try_from(turn.session_index)
            .map_err(|_| PublicAgenticProxyError::CountOverflow)?]
        .push(AgenticSessionTurn {
            request_id,
            turn_index: turn.turn_index,
            class: turn.class,
            arrival_timestamp_microseconds: turn.arrival_timestamp_microseconds,
            preceding_tool_delay_milliseconds: turn.preceding_tool_delay_milliseconds,
            input_tokens: turn.input_tokens,
            output_tokens: turn.output_tokens,
            prefix_reused_tokens: turn.prefix_reused_tokens,
        });
    }
    let sessions = build_sessions(session_turns)?;
    let trace = CanonicalTraceV2 {
        schema_version: WORKLOAD_SCHEMA_VERSION,
        trace_id: format!("{}-trace", request.proxy_id),
        provenance: TraceProvenance::Synthetic {
            generator_id: PUBLIC_AGENTIC_PROXY_GENERATOR_ID.into(),
            seed: request.seed,
        },
        timestamp_basis: TimestampBasis::RelativeMicroseconds,
        identity: request.identity.clone(),
        requests: trace_requests,
    };
    trace.validate()?;
    let (slo_tiers, workload_contract) = build_slo_contract(request)?;
    workload_contract.validate()?;
    let summary = summarize(&trace, &sessions, &ordered_session_indices)?;
    let request_content_id = request_content_id(request)?;
    let trace_content_id = trace_content_id(&trace)?;
    let workload_contract_content_id = workload_contract_content_id(&workload_contract)?;
    let result = PublicAgenticProxyResult {
        proxy_id: request.proxy_id.clone(),
        disclaimer: PUBLIC_AGENTIC_PROXY_DISCLAIMER.into(),
        synthetic_assumption_notice: PUBLIC_AGENTIC_PROXY_ASSUMPTION_NOTICE.into(),
        request_content_id,
        trace_content_id,
        workload_contract_content_id,
        public_basis: request.public_basis.clone(),
        synthetic_design: request.synthetic_design.clone(),
        slo_tiers,
        workload_contract,
        trace,
        sessions,
        summary,
        claim_gates: request.claim_gates.clone(),
    };
    let schema_version = PUBLIC_AGENTIC_PROXY_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(PublicAgenticProxyReport {
        schema_version,
        content_id,
        result,
    })
}

fn validate_request(request: &PublicAgenticProxyRequest) -> Result<(), PublicAgenticProxyError> {
    if request.schema_version != PUBLIC_AGENTIC_PROXY_REQUEST_SCHEMA_VERSION {
        return Err(PublicAgenticProxyError::UnsupportedSchemaVersion {
            expected: PUBLIC_AGENTIC_PROXY_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    validate_text("proxy_id", &request.proxy_id)?;
    if request.seed == 0 {
        return Err(PublicAgenticProxyError::InvalidField("seed"));
    }
    request.identity.validate()?;
    validate_public_basis(&request.public_basis)?;
    validate_design(&request.synthetic_design, &request.public_basis)?;
    validate_slo_tiers(&request.slo_tiers)?;
    if request.claim_gates.aa_agentperf_score_claim_permitted
        || request.claim_gates.measured_performance_claim_permitted
        || request.claim_gates.nvidia_performance_claim_permitted
        || request.claim_gates.provider_performance_claim_permitted
        || request.claim_gates.cost_claim_permitted
    {
        return Err(PublicAgenticProxyError::ClaimGatePromoted);
    }
    Ok(())
}

fn validate_public_basis(basis: &PublicAgenticBasis) -> Result<(), PublicAgenticProxyError> {
    validate_text("public_basis.source_label", &basis.source_label)?;
    if basis.minimum_input_tokens != PUBLIC_MINIMUM_INPUT_TOKENS
        || basis.maximum_input_tokens != PUBLIC_MAXIMUM_INPUT_TOKENS
        || basis.approximate_mean_input_tokens != PUBLIC_APPROXIMATE_MEAN_INPUT_TOKENS
        || basis.median_tool_delay_milliseconds != PUBLIC_MEDIAN_TOOL_DELAY_MILLISECONDS
        || !basis.dynamic_prefixes
        || !basis.concurrent_sessions
        || basis.private_test_set_used
    {
        return Err(PublicAgenticProxyError::PublicGeometryDrift);
    }
    Ok(())
}

fn validate_design(
    design: &SyntheticAgenticDesign,
    basis: &PublicAgenticBasis,
) -> Result<(), PublicAgenticProxyError> {
    if design.session_count < 2
        || design.turns_per_session < 2
        || design.session_start_stagger_milliseconds == 0
    {
        return Err(PublicAgenticProxyError::InvalidField("synthetic_design"));
    }
    let turns = usize::try_from(design.turns_per_session)
        .map_err(|_| PublicAgenticProxyError::CountOverflow)?;
    if design.tool_delay_milliseconds_by_turn.len() != turns - 1
        || design.class_by_turn.len() != turns
        || design.prefix_reuse_basis_points_by_turn.len() != turns
    {
        return Err(PublicAgenticProxyError::InvalidField(
            "synthetic_design.turn_vectors",
        ));
    }
    if design.tool_delay_milliseconds_by_turn.contains(&0)
        || median_u64(&design.tool_delay_milliseconds_by_turn)
            != basis.median_tool_delay_milliseconds
    {
        return Err(PublicAgenticProxyError::InvalidField(
            "synthetic_design.tool_delay_milliseconds_by_turn",
        ));
    }
    let prefix_values = design
        .prefix_reuse_basis_points_by_turn
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    if design.prefix_reuse_basis_points_by_turn[0] != 0
        || prefix_values.len() < 2
        || prefix_values.iter().any(|value| *value > 10_000)
    {
        return Err(PublicAgenticProxyError::InvalidField(
            "synthetic_design.prefix_reuse_basis_points_by_turn",
        ));
    }
    let classes = design
        .class_by_turn
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    if AgentTurnClass::ALL
        .iter()
        .any(|class| !classes.contains(class))
    {
        return Err(PublicAgenticProxyError::InvalidField(
            "synthetic_design.class_by_turn",
        ));
    }
    validate_output_tokens(&design.output_tokens_by_class)?;
    validate_histogram(design, basis)
}

fn validate_output_tokens(values: &[ClassOutputTokens]) -> Result<(), PublicAgenticProxyError> {
    let mut classes = BTreeSet::new();
    for value in values {
        if value.output_tokens == 0 || !classes.insert(value.class) {
            return Err(PublicAgenticProxyError::InvalidField(
                "synthetic_design.output_tokens_by_class",
            ));
        }
    }
    if AgentTurnClass::ALL
        .iter()
        .any(|class| !classes.contains(class))
        || classes.len() != AgentTurnClass::ALL.len()
    {
        return Err(PublicAgenticProxyError::InvalidField(
            "synthetic_design.output_tokens_by_class",
        ));
    }
    Ok(())
}

fn validate_histogram(
    design: &SyntheticAgenticDesign,
    basis: &PublicAgenticBasis,
) -> Result<(), PublicAgenticProxyError> {
    if design.input_length_histogram.is_empty() {
        return Err(PublicAgenticProxyError::InvalidField(
            "synthetic_design.input_length_histogram",
        ));
    }
    let expected_count = u64::from(design.session_count)
        .checked_mul(u64::from(design.turns_per_session))
        .ok_or(PublicAgenticProxyError::ArithmeticOverflow)?;
    let mut count = 0_u64;
    let mut total = 0_u64;
    let mut minimum = u32::MAX;
    let mut maximum = 0_u32;
    for bucket in &design.input_length_histogram {
        if bucket.count == 0
            || bucket.input_tokens < basis.minimum_input_tokens
            || bucket.input_tokens > basis.maximum_input_tokens
        {
            return Err(PublicAgenticProxyError::InvalidField(
                "synthetic_design.input_length_histogram",
            ));
        }
        count = count
            .checked_add(u64::from(bucket.count))
            .ok_or(PublicAgenticProxyError::ArithmeticOverflow)?;
        total = total
            .checked_add(u64::from(bucket.input_tokens) * u64::from(bucket.count))
            .ok_or(PublicAgenticProxyError::ArithmeticOverflow)?;
        minimum = minimum.min(bucket.input_tokens);
        maximum = maximum.max(bucket.input_tokens);
    }
    let expected_total = u64::from(basis.approximate_mean_input_tokens)
        .checked_mul(expected_count)
        .ok_or(PublicAgenticProxyError::ArithmeticOverflow)?;
    if count != expected_count
        || total != expected_total
        || minimum != basis.minimum_input_tokens
        || maximum != basis.maximum_input_tokens
    {
        return Err(PublicAgenticProxyError::InvalidField(
            "synthetic_design.input_length_histogram",
        ));
    }
    Ok(())
}

fn validate_slo_tiers(tiers: &[AgenticSloTier]) -> Result<(), PublicAgenticProxyError> {
    let mut classes = BTreeSet::new();
    let mut tier_ids = BTreeSet::new();
    for tier in tiers {
        validate_text("slo_tiers.tier_id", &tier.tier_id)?;
        if !classes.insert(tier.class)
            || !tier_ids.insert(tier.tier_id.as_str())
            || !tier.percentile.is_finite()
            || tier.percentile <= 0.0
            || tier.percentile > 100.0
            || !tier.maximum_ttft_milliseconds.is_finite()
            || tier.maximum_ttft_milliseconds <= 0.0
            || !tier.minimum_output_tokens_per_second.is_finite()
            || tier.minimum_output_tokens_per_second <= 0.0
        {
            return Err(PublicAgenticProxyError::InvalidField("slo_tiers"));
        }
    }
    if classes.len() != AgentTurnClass::ALL.len()
        || AgentTurnClass::ALL
            .iter()
            .any(|class| !classes.contains(class))
    {
        return Err(PublicAgenticProxyError::InvalidField("slo_tiers"));
    }
    Ok(())
}

fn build_slo_contract(
    request: &PublicAgenticProxyRequest,
) -> Result<(Vec<ResolvedAgenticSloTier>, WorkloadContractV2), PublicAgenticProxyError> {
    let by_class = request
        .slo_tiers
        .iter()
        .map(|tier| (tier.class, tier))
        .collect::<BTreeMap<_, _>>();
    let mut resolved = Vec::with_capacity(AgentTurnClass::ALL.len());
    let mut class_objectives = Vec::with_capacity(AgentTurnClass::ALL.len());
    for class in AgentTurnClass::ALL {
        let tier = by_class[&class];
        let maximum_tpot_milliseconds = 1_000.0 / tier.minimum_output_tokens_per_second;
        resolved.push(ResolvedAgenticSloTier {
            tier_id: tier.tier_id.clone(),
            class,
            percentile: tier.percentile,
            maximum_ttft_milliseconds: tier.maximum_ttft_milliseconds,
            minimum_output_tokens_per_second: tier.minimum_output_tokens_per_second,
            maximum_tpot_milliseconds,
        });
        class_objectives.push(ClassSloObjective {
            class,
            ttft: PercentileSloObjective {
                percentile: tier.percentile,
                maximum_milliseconds: tier.maximum_ttft_milliseconds,
            },
            tpot: PercentileSloObjective {
                percentile: tier.percentile,
                maximum_milliseconds: maximum_tpot_milliseconds,
            },
        });
    }
    Ok((
        resolved,
        WorkloadContractV2 {
            schema_version: WORKLOAD_SCHEMA_VERSION,
            contract_id: format!("{}-slo", request.proxy_id),
            identity: request.identity.clone(),
            class_objectives,
        },
    ))
}

fn expand_input_lengths(
    histogram: &[InputLengthBucket],
) -> Result<Vec<u32>, PublicAgenticProxyError> {
    let count = histogram.iter().try_fold(0_usize, |total, bucket| {
        total
            .checked_add(
                usize::try_from(bucket.count)
                    .map_err(|_| PublicAgenticProxyError::CountOverflow)?,
            )
            .ok_or(PublicAgenticProxyError::ArithmeticOverflow)
    })?;
    let mut values = Vec::with_capacity(count);
    for bucket in histogram {
        let bucket_count =
            usize::try_from(bucket.count).map_err(|_| PublicAgenticProxyError::CountOverflow)?;
        values.extend(std::iter::repeat_n(bucket.input_tokens, bucket_count));
    }
    Ok(values)
}

fn deterministic_shuffle(values: &mut [u32], seed: u64) {
    let mut state = seed;
    for index in (1..values.len()).rev() {
        state = state
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        let swap_index = (state % u64::try_from(index + 1).unwrap()) as usize;
        values.swap(index, swap_index);
    }
}

fn build_sessions(
    mut session_turns: Vec<Vec<AgenticSessionTurn>>,
) -> Result<Vec<AgenticSession>, PublicAgenticProxyError> {
    session_turns
        .iter_mut()
        .for_each(|turns| turns.sort_by_key(|turn| turn.turn_index));
    session_turns
        .into_iter()
        .enumerate()
        .map(|(index, turns)| {
            let start = turns
                .first()
                .ok_or(PublicAgenticProxyError::InvalidField("sessions"))?
                .arrival_timestamp_microseconds;
            let end = turns
                .last()
                .ok_or(PublicAgenticProxyError::InvalidField("sessions"))?
                .arrival_timestamp_microseconds;
            Ok(AgenticSession {
                session_id: format!("session-{index:02}"),
                start_timestamp_microseconds: start,
                end_timestamp_microseconds: end,
                turns,
            })
        })
        .collect()
}

fn summarize(
    trace: &CanonicalTraceV2,
    sessions: &[AgenticSession],
    ordered_session_indices: &[u32],
) -> Result<PublicAgenticProxySummary, PublicAgenticProxyError> {
    let request_count =
        u64::try_from(trace.requests.len()).map_err(|_| PublicAgenticProxyError::CountOverflow)?;
    let session_count =
        u64::try_from(sessions.len()).map_err(|_| PublicAgenticProxyError::CountOverflow)?;
    let total_input_tokens = trace
        .requests
        .iter()
        .map(|request| u64::from(request.input_tokens))
        .sum::<u64>();
    let total_output_tokens = trace
        .requests
        .iter()
        .map(|request| u64::from(request.output_tokens))
        .sum::<u64>();
    let minimum_input_tokens = trace
        .requests
        .iter()
        .map(|request| request.input_tokens)
        .min()
        .ok_or(PublicAgenticProxyError::InvalidField("trace.requests"))?;
    let maximum_input_tokens = trace
        .requests
        .iter()
        .map(|request| request.input_tokens)
        .max()
        .ok_or(PublicAgenticProxyError::InvalidField("trace.requests"))?;
    let tool_delays = sessions
        .iter()
        .flat_map(|session| session.turns.iter())
        .filter_map(|turn| turn.preceding_tool_delay_milliseconds)
        .collect::<Vec<_>>();
    let dynamic_prefix_session_count = u64::try_from(
        sessions
            .iter()
            .filter(|session| {
                session
                    .turns
                    .iter()
                    .map(|turn| turn.prefix_reused_tokens)
                    .collect::<BTreeSet<_>>()
                    .len()
                    > 1
            })
            .count(),
    )
    .map_err(|_| PublicAgenticProxyError::CountOverflow)?;
    let peak_active_session_windows = sessions
        .iter()
        .flat_map(|session| session.turns.iter())
        .map(|turn| {
            sessions
                .iter()
                .filter(|session| {
                    session.start_timestamp_microseconds <= turn.arrival_timestamp_microseconds
                        && session.end_timestamp_microseconds >= turn.arrival_timestamp_microseconds
                })
                .count()
        })
        .max()
        .unwrap_or(0);
    let interleaved_session_switch_count = ordered_session_indices
        .windows(2)
        .filter(|pair| pair[0] != pair[1])
        .count();
    let first_arrival = trace.requests[0].arrival_timestamp_microseconds;
    let last_arrival = trace.requests[trace.requests.len() - 1].arrival_timestamp_microseconds;
    Ok(PublicAgenticProxySummary {
        session_count,
        request_count,
        minimum_input_tokens,
        maximum_input_tokens,
        mean_input_tokens: total_input_tokens as f64 / request_count as f64,
        total_input_tokens,
        total_output_tokens,
        tool_call_count: u64::try_from(tool_delays.len())
            .map_err(|_| PublicAgenticProxyError::CountOverflow)?,
        median_tool_delay_milliseconds: median_u64(&tool_delays),
        peak_active_session_windows: u64::try_from(peak_active_session_windows)
            .map_err(|_| PublicAgenticProxyError::CountOverflow)?,
        dynamic_prefix_session_count,
        interleaved_session_switch_count: u64::try_from(interleaved_session_switch_count)
            .map_err(|_| PublicAgenticProxyError::CountOverflow)?,
        trace_duration_milliseconds: (last_arrival - first_arrival) / 1_000,
    })
}

fn median_u64(values: &[u64]) -> u64 {
    let mut sorted = values.to_vec();
    sorted.sort_unstable();
    sorted[sorted.len() / 2]
}

fn validate_text(field: &'static str, value: &str) -> Result<(), PublicAgenticProxyError> {
    if value.trim().is_empty() {
        Err(PublicAgenticProxyError::InvalidField(field))
    } else {
        Ok(())
    }
}

fn request_content_id(
    request: &PublicAgenticProxyRequest,
) -> Result<String, PublicAgenticProxyError> {
    Ok(blake3::hash(&serde_json::to_vec(request)?)
        .to_hex()
        .to_string())
}

fn trace_content_id(trace: &CanonicalTraceV2) -> Result<String, PublicAgenticProxyError> {
    Ok(blake3::hash(trace.to_canonical_json()?.as_bytes())
        .to_hex()
        .to_string())
}

fn workload_contract_content_id(
    contract: &WorkloadContractV2,
) -> Result<String, PublicAgenticProxyError> {
    contract.validate()?;
    Ok(blake3::hash(&serde_json::to_vec(contract)?)
        .to_hex()
        .to_string())
}

fn report_content_id(
    schema_version: u32,
    result: &PublicAgenticProxyResult,
) -> Result<String, PublicAgenticProxyError> {
    Ok(
        blake3::hash(&serde_json::to_vec(&(schema_version, result))?)
            .to_hex()
            .to_string(),
    )
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum PublicAgenticProxyError {
    #[error("unsupported public agentic proxy schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid public agentic proxy field {0}")]
    InvalidField(&'static str),
    #[error("public AA-AgentPerf geometry drifted from the frozen proxy contract")]
    PublicGeometryDrift,
    #[error("a prohibited performance or cost claim gate was promoted")]
    ClaimGatePromoted,
    #[error("public agentic proxy count exceeds the supported range")]
    CountOverflow,
    #[error("public agentic proxy arithmetic overflow")]
    ArithmeticOverflow,
    #[error(transparent)]
    Workload(#[from] WorkloadError),
    #[error("public agentic proxy serialization failed: {0}")]
    Serialization(String),
}

impl From<serde_json::Error> for PublicAgenticProxyError {
    fn from(error: serde_json::Error) -> Self {
        Self::Serialization(error.to_string())
    }
}
