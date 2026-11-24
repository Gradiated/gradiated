use std::{collections::VecDeque, time::Duration};

use async_trait::async_trait;
use serde::Deserialize;
use serde_json::{Map, Value};
use uuid::Uuid;

use super::{
    chat::{
        valid_finish_reason, valid_response_id, Choice, NormalizedCompletionResponse,
        NormalizedStreamResponse, PublicUsage, StreamChoice,
    },
    client::{next_message, RuntimeEvents},
    fallback::{FallbackVendor, TokenRates},
    ChunkUsage, ExternalRequest, FailureCause, ProtocolViolation, RuntimeCompletion,
    RuntimeEventStream, RuntimeFailure, RuntimeFailureKind, RuntimeStreamChunk, RuntimeStreamEvent,
};
use crate::{model::MAX_SAFE_INTEGER, NormalizedUsage};

const STREAM_ADMISSION_PEEK: Duration = Duration::from_secs(1);

pub(super) struct Names {
    generation_id: Uuid,
    requested: String,
    upstream: String,
    response_model: Option<String>,
    billing: UpstreamBilling,
    response_id: String,
}

impl Names {
    pub(super) fn new(request: &ExternalRequest, upstream: &str, billing: UpstreamBilling) -> Self {
        Self {
            generation_id: request.generation_id,
            requested: request.request.model.clone(),
            upstream: upstream.to_owned(),
            response_model: None,
            billing,
            response_id: format!("chatcmpl-{}", request.generation_id.simple()),
        }
    }

    pub(super) fn with_response_model(mut self, response_model: Option<&str>) -> Self {
        self.response_model = response_model.map(str::to_owned);
        self
    }

    fn check_model(&self, model: &str) -> Result<(), RuntimeFailure> {
        if model != self.upstream && self.response_model.as_deref() != Some(model) {
            return Err(ProtocolViolation::ModelMismatch.into());
        }

        Ok(())
    }
}

#[derive(Clone, Copy)]
pub(super) enum UpstreamBilling {
    OpenRouter,
    Direct(FallbackVendor, TokenRates),
}

fn record_usage(
    names: &Names,
    upstream_id: &str,
    provider: Option<&str>,
    usage: &ChatUsage,
    tokens: NormalizedUsage,
) -> Option<u64> {
    let reported = usage.cost_nano_usd();
    match names.billing {
        UpstreamBilling::OpenRouter => {
            tracing::info!(generation_id = %names.generation_id,
                openrouter_model = names.upstream,
                upstream_generation_id = upstream_id,
                upstream_provider = provider.filter(|name| name.chars().count() <= 100),
                upstream_cost_nano_usd = reported,
                event = "openrouter_usage", "OpenRouter reported usage");

            reported
        }
        UpstreamBilling::Direct(vendor, rates) => {
            let cost = reported.or_else(|| rates.cost(tokens));
            tracing::info!(generation_id = %names.generation_id,
                upstream_model = names.upstream,
                upstream_generation_id = upstream_id,
                upstream_provider = vendor.as_str(),
                upstream_cost_nano_usd = cost,
                event = "external_usage", "External provider reported usage");

            cost
        }
    }
}

pub(super) fn normalize_completion(
    body: &[u8],
    names: &Names,
) -> Result<RuntimeCompletion, RuntimeFailure> {
    let value: Value = serde_json::from_slice(body).map_err(|_| ProtocolViolation::Json)?;
    reject_reported_error(&value)?;

    let completion: ChatCompletion =
        serde_json::from_value(value).map_err(|_| ProtocolViolation::Json)?;
    if completion.object != "chat.completion" || !valid_response_id(&completion.id) {
        return Err(ProtocolViolation::ResponseShape.into());
    }

    names.check_model(&completion.model)?;
    let usage = completion.usage.normalize()?;
    let upstream_cost_nano_usd = record_usage(
        names,
        &completion.id,
        completion.provider.as_deref(),
        &completion.usage,
        usage,
    );

    if completion.choices.is_empty()
        || completion
            .choices
            .iter()
            .any(|choice| choice.index > MAX_SAFE_INTEGER)
    {
        return Err(RuntimeFailure::from(ProtocolViolation::ResponseShape).or_usage(usage));
    }

    let mut choices = Vec::with_capacity(completion.choices.len());
    for choice in completion.choices {
        let finish_reason = choice
            .finish_reason
            .ok_or_else(|| RuntimeFailure::from(ProtocolViolation::FinishReason).or_usage(usage))?;
        check_finish_reason(&finish_reason, usage)?;

        choices.push(Choice {
            index: choice.index,
            message: public_message(choice.message),
            logprobs: choice.logprobs,
            finish_reason,
        });
    }

    let finish_reason = choices[0].finish_reason.clone();
    let response = NormalizedCompletionResponse {
        id: names.response_id.clone(),
        object: completion.object,
        created: completion.created,
        model: names.requested.clone(),
        choices,
        usage: PublicUsage::from(usage),
    };

    Ok(RuntimeCompletion {
        response: serde_json::to_value(response).map_err(|_| ProtocolViolation::Json)?,
        finish_reason,
        usage,
        upstream_cost_nano_usd,
    })
}

/// Some upstreams report errors inside a successful HTTP response.
fn reject_reported_error(value: &Value) -> Result<(), RuntimeFailure> {
    let Some(error) = value.get("error").filter(|error| !error.is_null()) else {
        return Ok(());
    };

    let usage = value
        .get("usage")
        .and_then(|usage| ChatUsage::deserialize(usage).ok())
        .and_then(|usage| usage.normalize().ok())
        .unwrap_or_else(NormalizedUsage::zero);
    let code = error
        .get("code")
        .and_then(Value::as_u64)
        .and_then(|code| u16::try_from(code).ok())
        .unwrap_or(500);

    Err(failure_for_code(code, usage))
}

fn check_finish_reason(reason: &str, usage: NormalizedUsage) -> Result<(), RuntimeFailure> {
    if reason == "error" {
        return Err(RuntimeFailure::caused(
            RuntimeFailureKind::Interrupted,
            FailureCause::Protocol(ProtocolViolation::FinishReason),
        )
        .or_usage(usage));
    }

    if !valid_finish_reason(reason) {
        return Err(RuntimeFailure::from(ProtocolViolation::FinishReason).or_usage(usage));
    }

    Ok(())
}

pub(super) fn failure_for_code(code: u16, usage: NormalizedUsage) -> RuntimeFailure {
    let kind = match code {
        400 | 422 => RuntimeFailureKind::InvalidRequest,
        429 | 503 | 529 => RuntimeFailureKind::CapacityExceeded,
        _ => RuntimeFailureKind::Unavailable,
    };

    RuntimeFailure::caused(kind, FailureCause::Status(code)).or_usage(usage)
}

/// Only standard fields reach the caller. OpenRouter's `reasoning` becomes the
/// `reasoning_content` our runtimes return; `reasoning_details` and provider
/// annotations are dropped.
fn public_message(mut upstream: Map<String, Value>) -> Map<String, Value> {
    let mut message = Map::new();
    for field in ["role", "content", "refusal", "tool_calls"] {
        if let Some(value) = upstream.remove(field) {
            message.insert(field.to_owned(), value);
        }
    }

    let reasoning = ["reasoning", "reasoning_content"]
        .into_iter()
        .find_map(|field| upstream.remove(field).filter(Value::is_string));
    if let Some(reasoning) = reasoning {
        message.insert("reasoning_content".to_owned(), reasoning);
    }

    message
}

#[derive(Deserialize)]
struct ChatCompletion {
    id: String,
    object: String,
    created: u64,
    model: String,
    #[serde(default)]
    provider: Option<String>,
    choices: Vec<ChatChoice>,
    usage: ChatUsage,
}

#[derive(Deserialize)]
struct ChatChoice {
    index: u64,
    message: Map<String, Value>,
    #[serde(default)]
    logprobs: Option<Value>,
    #[serde(default)]
    finish_reason: Option<String>,
}

#[derive(Deserialize)]
struct ChatUsage {
    prompt_tokens: u64,
    completion_tokens: u64,
    total_tokens: u64,
    #[serde(default)]
    prompt_tokens_details: Option<PromptDetails>,
    #[serde(default)]
    completion_tokens_details: Option<CompletionDetails>,
    #[serde(default)]
    cost: Option<Value>,
}

#[derive(Deserialize)]
struct PromptDetails {
    #[serde(default)]
    cached_tokens: Option<u64>,
    #[serde(default)]
    cache_write_tokens: Option<u64>,
}

#[derive(Deserialize)]
struct CompletionDetails {
    #[serde(default)]
    reasoning_tokens: Option<u64>,
}

impl ChatUsage {
    fn normalize(&self) -> Result<NormalizedUsage, RuntimeFailure> {
        let expected_total = self
            .prompt_tokens
            .checked_add(self.completion_tokens)
            .ok_or(ProtocolViolation::Usage)?;
        if expected_total != self.total_tokens || self.total_tokens > MAX_SAFE_INTEGER {
            return Err(ProtocolViolation::Usage.into());
        }

        let prompt = self.prompt_tokens_details.as_ref();
        let reasoning = self
            .completion_tokens_details
            .as_ref()
            .and_then(|details| details.reasoning_tokens)
            .unwrap_or(0);

        // Providers can report more reasoning tokens than completion tokens;
        // `completion_tokens` is the total OpenRouter bills, so reasoning is capped there.
        NormalizedUsage::new(
            self.prompt_tokens,
            prompt
                .and_then(|details| details.cached_tokens)
                .unwrap_or(0),
            prompt
                .and_then(|details| details.cache_write_tokens)
                .unwrap_or(0),
            self.completion_tokens,
            reasoning.min(self.completion_tokens),
        )
        .map_err(|_| ProtocolViolation::Usage.into())
    }

    fn cost_nano_usd(&self) -> Option<u64> {
        let usd = self.cost.as_ref()?.as_f64()?;
        let nano_usd = (usd * 1e9).round();

        (usd >= 0.0 && nano_usd <= MAX_SAFE_INTEGER as f64).then_some(nano_usd as u64)
    }
}

enum Phase {
    Streaming,
    AwaitingDone,
    Done,
}

pub(super) struct ChatStream {
    events: RuntimeEvents,
    normalizer: StreamNormalizer,
    pending: VecDeque<RuntimeStreamEvent>,
    phase: Phase,
}

impl ChatStream {
    pub(super) fn new(events: RuntimeEvents, names: Names) -> Self {
        Self {
            events,
            normalizer: StreamNormalizer::new(names),
            pending: VecDeque::new(),
            phase: Phase::Streaming,
        }
    }

    pub(super) async fn peek(&mut self, frame_limit: usize) -> Result<(), RuntimeFailure> {
        let mut prefix = VecDeque::new();
        let read = async {
            for _ in 0..frame_limit {
                let event = self
                    .next_event()
                    .await?
                    .ok_or(ProtocolViolation::FrameOrder)?;
                let started = match &event {
                    RuntimeStreamEvent::Chunk(chunk) => {
                        chunk.has_usable_output()
                            || chunk.finish_reason().is_some()
                            || chunk.is_terminal_usage()
                    }
                    RuntimeStreamEvent::Done => true,
                };

                prefix.push_back(event);
                if started {
                    break;
                }
            }

            Ok::<_, RuntimeFailure>(())
        };

        if let Ok(result) = tokio::time::timeout(STREAM_ADMISSION_PEEK, read).await {
            result?;
        }

        prefix.append(&mut self.pending);
        self.pending = prefix;

        Ok(())
    }
}

#[async_trait]
impl RuntimeEventStream for ChatStream {
    async fn next_event(&mut self) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure> {
        loop {
            if let Some(event) = self.pending.pop_front() {
                return Ok(Some(event));
            }

            if matches!(self.phase, Phase::Done) {
                return Ok(None);
            }

            let data = next_message(&mut self.events)
                .await?
                .ok_or(ProtocolViolation::FrameOrder)?;

            match (&self.phase, data == "[DONE]") {
                (Phase::AwaitingDone, true) => {
                    self.phase = Phase::Done;
                    return Ok(Some(RuntimeStreamEvent::Done));
                }
                (Phase::Streaming, false) => {
                    let normalized = self.normalizer.normalize(&data).inspect_err(|failure| {
                        crate::diagnostics::limited_warn!(
                            diagnostic_code = failure.diagnostic_code(),
                            phase = "response_frame",
                            "External response frame rejected"
                        );
                    })?;
                    for chunk in normalized {
                        if chunk.is_terminal_usage() {
                            self.phase = Phase::AwaitingDone;
                        }
                        self.pending.push_back(RuntimeStreamEvent::Chunk(chunk));
                    }
                }
                _ => return Err(ProtocolViolation::FrameOrder.into()),
            }
        }
    }
}

#[derive(Deserialize)]
struct ChatChunk {
    id: String,
    object: String,
    created: u64,
    model: String,
    #[serde(default)]
    provider: Option<String>,
    #[serde(default)]
    choices: Vec<ChatDelta>,
    #[serde(default)]
    usage: Option<ChatUsage>,
}

#[derive(Deserialize)]
struct ChatDelta {
    index: u64,
    #[serde(default)]
    delta: Map<String, Value>,
    #[serde(default)]
    logprobs: Option<Value>,
    #[serde(default)]
    finish_reason: Option<String>,
}

struct StreamNormalizer {
    names: Names,
    identity: Option<(String, u64)>,
    role_sent: bool,
    finished: bool,
}

impl StreamNormalizer {
    fn new(names: Names) -> Self {
        Self {
            names,
            identity: None,
            role_sent: false,
            finished: false,
        }
    }

    /// One OpenRouter frame becomes zero, one or two chunks. Its final frame
    /// carries usage beside a choice that repeats the finish reason, which our
    /// stream contract splits into a choice chunk and a choiceless usage chunk.
    fn normalize(&mut self, data: &str) -> Result<Vec<RuntimeStreamChunk>, RuntimeFailure> {
        let value: Value = serde_json::from_str(data).map_err(|_| ProtocolViolation::Json)?;
        reject_reported_error(&value)?;

        let chunk: ChatChunk =
            serde_json::from_value(value).map_err(|_| ProtocolViolation::Json)?;
        if chunk.object != "chat.completion.chunk" || !valid_response_id(&chunk.id) {
            return Err(ProtocolViolation::ResponseShape.into());
        }

        self.names.check_model(&chunk.model)?;
        let (id, created) = self
            .identity
            .get_or_insert_with(|| (chunk.id.clone(), chunk.created));
        if *id != chunk.id {
            return Err(ProtocolViolation::StreamIdentity.into());
        }
        let created = *created;

        let usage = chunk.usage.as_ref().map(ChatUsage::normalize).transpose()?;
        let cost = chunk
            .usage
            .as_ref()
            .zip(usage)
            .and_then(|(upstream, tokens)| {
                record_usage(
                    &self.names,
                    &chunk.id,
                    chunk.provider.as_deref(),
                    upstream,
                    tokens,
                )
            });
        let verified_usage = usage.unwrap_or_else(NormalizedUsage::zero);
        if chunk
            .choices
            .iter()
            .any(|choice| choice.index > MAX_SAFE_INTEGER)
        {
            return Err(
                RuntimeFailure::from(ProtocolViolation::ResponseShape).or_usage(verified_usage)
            );
        }

        let mut choices = Vec::with_capacity(chunk.choices.len());
        for choice in chunk.choices {
            if let Some(reason) = &choice.finish_reason {
                check_finish_reason(reason, verified_usage)?;
            }

            let choice = self.public_choice(choice);
            if usage.is_none() || self.adds_to_stream(&choice) {
                choices.push(choice);
            }
        }

        let mut normalized = Vec::with_capacity(2);
        if !choices.is_empty() {
            normalized.push(self.choice_chunk(created, choices)?);
        }

        if let Some(usage) = usage {
            normalized.push(self.usage_chunk(created, usage, cost)?);
        }

        Ok(normalized)
    }

    /// The usage frame repeats the last finish reason in an otherwise empty choice.
    fn adds_to_stream(&self, choice: &StreamChoice) -> bool {
        choice.has_usable_output() || (choice.finish_reason.is_some() && !self.finished)
    }

    fn public_choice(&mut self, choice: ChatDelta) -> StreamChoice {
        let mut delta = public_message(choice.delta);
        if self.role_sent {
            delta.remove("role");
        }
        self.role_sent |= delta.contains_key("role");

        StreamChoice {
            index: choice.index,
            delta,
            logprobs: choice.logprobs,
            finish_reason: choice.finish_reason,
        }
    }

    fn choice_chunk(
        &mut self,
        created: u64,
        choices: Vec<StreamChoice>,
    ) -> Result<RuntimeStreamChunk, RuntimeFailure> {
        let finish_reason = choices
            .iter()
            .find_map(|choice| choice.finish_reason.clone());
        self.finished |= finish_reason.is_some();
        let usable_output = choices.iter().any(StreamChoice::has_usable_output);

        Ok(RuntimeStreamChunk {
            response: self.envelope(created, choices, None)?,
            finish_reason,
            usable_output,
            usage: None,
            upstream_cost_nano_usd: None,
        })
    }

    fn usage_chunk(
        &self,
        created: u64,
        usage: NormalizedUsage,
        upstream_cost_nano_usd: Option<u64>,
    ) -> Result<RuntimeStreamChunk, RuntimeFailure> {
        Ok(RuntimeStreamChunk {
            response: self.envelope(created, Vec::new(), Some(PublicUsage::from(usage)))?,
            finish_reason: None,
            usable_output: false,
            usage: Some(ChunkUsage::Terminal(usage)),
            upstream_cost_nano_usd,
        })
    }

    fn envelope(
        &self,
        created: u64,
        choices: Vec<StreamChoice>,
        usage: Option<PublicUsage>,
    ) -> Result<Value, RuntimeFailure> {
        serde_json::to_value(NormalizedStreamResponse {
            id: self.names.response_id.clone(),
            object: "chat.completion.chunk".to_owned(),
            created,
            model: self.names.requested.clone(),
            choices,
            usage,
        })
        .map_err(|_| ProtocolViolation::Json.into())
    }
}
