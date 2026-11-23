use async_trait::async_trait;
use reqwest::{header, Response};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use super::{
    client::{
        next_message, one_shot_body, open_events, read_bounded_body, read_completion_body, send,
        Call, ModelNames, RuntimeEvents,
    },
    ChunkUsage, ProtocolViolation, RuntimeCompletion, RuntimeEventStream, RuntimeFailure,
    RuntimeStreamChunk, RuntimeStreamEvent, SglangClient,
};
use crate::{model::MAX_SAFE_INTEGER, NormalizedUsage};
use std::time::Duration;

const CHAT_COMPLETIONS: &str = "v1/chat/completions";
const MAX_RESPONSE_TEXT_CHARS: usize = 300;
const MAX_FINISH_REASON_CHARS: usize = 100;
const STREAM_ADMISSION_PEEK: Duration = Duration::from_secs(1);

impl SglangClient {
    pub(super) async fn complete_chat(
        &self,
        call: Call<'_>,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        let models = ModelNames::new(&call);
        let response = self.send_chat(call, &models, "application/json").await?;

        let body = read_completion_body(response).await?;
        normalize_completion(&body, &models)
    }

    pub(super) async fn stream_chat(
        &self,
        call: Call<'_>,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        let models = ModelNames::new(&call);
        let response = self.send_chat(call, &models, "text/event-stream").await?;

        let events = open_events(response)?;
        let mut stream = ChatEventStream {
            events,
            normalizer: ChatStreamNormalizer::new(models),
            phase: Phase::Streaming,
            pending: None,
            terminal_diagnostics: 0,
        };
        if let Ok(first) = tokio::time::timeout(STREAM_ADMISSION_PEEK, stream.next_event()).await {
            stream.pending = first?;
        }

        Ok(Box::new(stream))
    }

    async fn send_chat(
        &self,
        call: Call<'_>,
        models: &ModelNames,
        accept: &'static str,
    ) -> Result<Response, RuntimeFailure> {
        let body = call
            .request
            .into_upstream_body_for_model(call.output_tokens, Some(&models.runtime));
        crate::diagnostics::body::record_value("runtime_request", &body, None);
        let body = serde_json::to_vec(&body).map_err(|_| ProtocolViolation::Json)?;

        let upstream = self
            .post(call.deployment, CHAT_COMPLETIONS, one_shot_body(body))
            .header(header::ACCEPT, accept);
        let response = send(upstream).await?;
        if !response.status().is_success() {
            return Err(rejected_with_usage(response, models.cartridge_tokens).await);
        }

        Ok(response)
    }
}

/// A rejected chat request can still report usage the runtime consumed.
async fn rejected_with_usage(response: Response, cartridge_tokens: u64) -> RuntimeFailure {
    let status = response.status();
    let headers = response.headers().clone();
    let usage = match read_bounded_body(response).await {
        Ok(body) => optional_usage(&body, cartridge_tokens).unwrap_or_else(NormalizedUsage::zero),
        Err(_) => NormalizedUsage::zero(),
    };

    RuntimeFailure::rejected(status, usage).with_retry_after(&headers)
}

struct ChatEventStream {
    events: RuntimeEvents,
    normalizer: ChatStreamNormalizer,
    phase: Phase,
    pending: Option<RuntimeStreamEvent>,
    terminal_diagnostics: u8,
}

enum Phase {
    Streaming,
    AwaitingDone,
    Done,
}

#[async_trait]
impl RuntimeEventStream for ChatEventStream {
    async fn next_event(&mut self) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure> {
        if let Some(event) = self.pending.take() {
            return Ok(Some(event));
        }

        if matches!(self.phase, Phase::Done) {
            return Ok(None);
        }

        let data = next_message(&mut self.events)
            .await?
            .ok_or(ProtocolViolation::FrameOrder)?;

        let first = self.normalizer.identity.is_none();
        if first && data != "[DONE]" {
            crate::diagnostics::body::record(
                "runtime_response_first_frame",
                data.as_bytes(),
                Some(200),
            );
        }

        let result = self.observe_data(&data);
        match &result {
            Err(failure) => {
                crate::diagnostics::body::record(
                    "runtime_response_invalid_frame",
                    data.as_bytes(),
                    Some(200),
                );
                crate::diagnostics::limited_warn!(
                    diagnostic_code = failure.diagnostic_code(),
                    phase = "response_frame",
                    "runtime response frame rejected"
                );
            }
            Ok(Some(RuntimeStreamEvent::Chunk(chunk)))
                if (chunk.is_terminal_usage() || chunk.finish_reason().is_some())
                    && self.terminal_diagnostics < 2 =>
            {
                crate::diagnostics::body::record(
                    "runtime_response_terminal_frame",
                    data.as_bytes(),
                    Some(200),
                );
                self.terminal_diagnostics += 1;
            }
            _ => {}
        }

        result
    }
}

impl ChatEventStream {
    fn observe_data(&mut self, data: &str) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure> {
        match (&self.phase, data == "[DONE]") {
            (Phase::AwaitingDone, true) => {
                self.phase = Phase::Done;
                Ok(Some(RuntimeStreamEvent::Done))
            }
            (Phase::Streaming, false) => {
                if self.normalizer.identity.is_none() {
                    if let Ok(rejection) = serde_json::from_str::<StreamRejection>(data) {
                        if rejection.error.code == 503
                            && rejection.error.kind == "SERVICE_UNAVAILABLE"
                        {
                            let cartridge_tokens = self.normalizer.models.cartridge_tokens;
                            let usage = rejection
                                .usage
                                .map(|usage| usage.normalize(cartridge_tokens))
                                .transpose()?
                                .unwrap_or_else(NormalizedUsage::zero);

                            // SGLang reports queue admission rejection inside an HTTP 200 stream.
                            return Err(RuntimeFailure::rejected(
                                reqwest::StatusCode::SERVICE_UNAVAILABLE,
                                usage,
                            ));
                        }
                    }
                }

                let chunk = self.normalizer.normalize(data.as_bytes())?;
                if chunk.is_terminal_usage() {
                    self.phase = Phase::AwaitingDone;
                }

                Ok(Some(RuntimeStreamEvent::Chunk(chunk)))
            }
            _ => Err(ProtocolViolation::FrameOrder.into()),
        }
    }
}

#[derive(Deserialize)]
struct StreamRejection {
    error: StreamRejectionError,
    #[serde(default)]
    usage: Option<UpstreamUsage>,
}

#[derive(Deserialize)]
struct StreamRejectionError {
    code: u16,
    #[serde(rename = "type")]
    kind: String,
}

pub(super) fn normalize_completion(
    body: &[u8],
    models: &ModelNames,
) -> Result<RuntimeCompletion, RuntimeFailure> {
    let response: UpstreamCompletion =
        serde_json::from_slice(body).map_err(|_| ProtocolViolation::Json)?;
    if response.object != "chat.completion"
        || !valid_response_id(&response.id)
        || response.choices.is_empty()
        || response
            .choices
            .iter()
            .any(|choice| choice.index > MAX_SAFE_INTEGER)
    {
        return Err(ProtocolViolation::ResponseShape.into());
    }

    if response.model != models.runtime {
        return Err(ProtocolViolation::ModelMismatch.into());
    }

    if response
        .choices
        .iter()
        .any(|choice| !valid_finish_reason(&choice.finish_reason))
    {
        return Err(ProtocolViolation::FinishReason.into());
    }

    let usage = response.usage.normalize(models.cartridge_tokens)?;
    let finish_reason = response.choices[0].finish_reason.clone();
    let response = NormalizedCompletionResponse {
        id: response.id,
        object: response.object,
        created: response.created,
        model: models.requested.clone(),
        choices: response.choices,
        usage: PublicUsage::from(usage),
    };

    Ok(RuntimeCompletion {
        response: serde_json::to_value(response).map_err(|_| ProtocolViolation::Json)?,
        finish_reason,
        usage,
        upstream_cost_nano_usd: None,
    })
}

pub(super) struct ChatStreamNormalizer {
    models: ModelNames,
    identity: Option<(String, u64)>,
}

impl ChatStreamNormalizer {
    pub(super) fn new(models: ModelNames) -> Self {
        Self {
            models,
            identity: None,
        }
    }

    pub(super) fn normalize(&mut self, body: &[u8]) -> Result<RuntimeStreamChunk, RuntimeFailure> {
        let chunk: UpstreamStreamChunk =
            serde_json::from_slice(body).map_err(|_| ProtocolViolation::Json)?;
        if chunk.object != "chat.completion.chunk"
            || !valid_response_id(&chunk.id)
            || chunk
                .choices
                .iter()
                .any(|choice| choice.index > MAX_SAFE_INTEGER)
        {
            return Err(ProtocolViolation::ResponseShape.into());
        }

        if chunk.model != self.models.runtime {
            return Err(ProtocolViolation::ModelMismatch.into());
        }

        if chunk.choices.iter().any(|choice| {
            choice
                .finish_reason
                .as_deref()
                .is_some_and(|reason| !valid_finish_reason(reason))
        }) {
            return Err(ProtocolViolation::FinishReason.into());
        }

        let (id, created) = self
            .identity
            .get_or_insert_with(|| (chunk.id.clone(), chunk.created));
        if *id != chunk.id || *created != chunk.created {
            return Err(ProtocolViolation::StreamIdentity.into());
        }

        // A chunk without choices is the terminal usage report.
        let cartridge_tokens = self.models.cartridge_tokens;
        let usage = if chunk.choices.is_empty() {
            let usage = chunk.usage.ok_or(ProtocolViolation::Usage)?;
            Some(ChunkUsage::Terminal(usage.normalize(cartridge_tokens)?))
        } else {
            let usage = chunk
                .usage
                .map(|usage| usage.normalize(cartridge_tokens))
                .transpose()?;
            usage.map(ChunkUsage::Running)
        };
        let public_usage = match usage {
            Some(ChunkUsage::Terminal(usage)) => Some(PublicUsage::from(usage)),
            _ => None,
        };

        let finish_reason = chunk
            .choices
            .iter()
            .find_map(|choice| choice.finish_reason.clone());
        let usable_output = chunk.choices.iter().any(StreamChoice::has_usable_output);
        let response = NormalizedStreamResponse {
            id: chunk.id,
            object: chunk.object,
            created: chunk.created,
            model: self.models.requested.clone(),
            choices: chunk.choices,
            usage: public_usage,
        };

        Ok(RuntimeStreamChunk {
            response: serde_json::to_value(response).map_err(|_| ProtocolViolation::Json)?,
            finish_reason,
            usable_output,
            usage,
            upstream_cost_nano_usd: None,
        })
    }
}

pub(super) fn valid_response_id(id: &str) -> bool {
    !id.is_empty() && id.chars().count() <= MAX_RESPONSE_TEXT_CHARS
}

pub(super) fn valid_finish_reason(reason: &str) -> bool {
    !reason.is_empty() && reason.chars().count() <= MAX_FINISH_REASON_CHARS
}

fn optional_usage(body: &[u8], cartridge_tokens: u64) -> Option<NormalizedUsage> {
    #[derive(Deserialize)]
    struct UsageEnvelope {
        usage: Option<UpstreamUsage>,
    }

    serde_json::from_slice::<UsageEnvelope>(body)
        .ok()?
        .usage?
        .normalize(cartridge_tokens)
        .ok()
}

#[derive(Debug, Deserialize)]
struct UpstreamCompletion {
    id: String,
    object: String,
    created: u64,
    model: String,
    choices: Vec<Choice>,
    usage: UpstreamUsage,
}

#[derive(Debug, Deserialize)]
struct UpstreamStreamChunk {
    id: String,
    object: String,
    created: u64,
    model: String,
    #[serde(default)]
    choices: Vec<StreamChoice>,
    #[serde(default)]
    usage: Option<UpstreamUsage>,
}

#[derive(Debug, Deserialize, Serialize)]
pub(super) struct StreamChoice {
    pub(super) index: u64,
    pub(super) delta: Map<String, Value>,
    #[serde(default)]
    pub(super) logprobs: Option<Value>,
    #[serde(default)]
    pub(super) finish_reason: Option<String>,
}

impl StreamChoice {
    /// Text, reasoning or a tool call. Role-only and empty deltas are not output.
    pub(super) fn has_usable_output(&self) -> bool {
        let text = |name: &str| {
            self.delta
                .get(name)
                .and_then(Value::as_str)
                .is_some_and(|text| !text.is_empty())
        };
        let tool_calls = self
            .delta
            .get("tool_calls")
            .and_then(Value::as_array)
            .is_some_and(|calls| !calls.is_empty());
        let function_call = self
            .delta
            .get("function_call")
            .is_some_and(|value| !value.is_null());

        text("content")
            || text("reasoning_content")
            || text("reasoning")
            || tool_calls
            || function_call
    }
}

#[derive(Debug, Deserialize, Serialize)]
pub(super) struct Choice {
    pub(super) index: u64,
    pub(super) message: Map<String, Value>,
    #[serde(default)]
    pub(super) logprobs: Option<Value>,
    pub(super) finish_reason: String,
}

#[derive(Debug, Deserialize)]
struct UpstreamUsage {
    #[serde(default)]
    estimated_joules: Option<Value>,
    prompt_tokens: u64,
    completion_tokens: u64,
    total_tokens: u64,
    #[serde(default)]
    prompt_tokens_details: Option<PromptTokenDetails>,
    #[serde(default)]
    completion_tokens_details: Option<CompletionTokenDetails>,
    #[serde(default)]
    reasoning_tokens: Option<u64>,
    #[serde(default)]
    cache_write_tokens: Option<u64>,
}

impl UpstreamUsage {
    /// `cartridge_tokens` are prompt positions the runtime counts but nobody is billed for.
    fn normalize(self, cartridge_tokens: u64) -> Result<NormalizedUsage, RuntimeFailure> {
        let expected_total = self
            .prompt_tokens
            .checked_add(self.completion_tokens)
            .ok_or(ProtocolViolation::Usage)?;
        if expected_total != self.total_tokens || self.total_tokens > MAX_SAFE_INTEGER {
            return Err(ProtocolViolation::Usage.into());
        }

        let cached = self
            .prompt_tokens_details
            .as_ref()
            .map_or(0, |details| details.cached_tokens);
        // Cartridge positions the cache did not hold were written to it instead.
        let written_cartridge = cartridge_tokens - cached.min(cartridge_tokens);
        NormalizedUsage::new(
            self.prompt_tokens.saturating_sub(cartridge_tokens),
            cached.saturating_sub(cartridge_tokens),
            self.prompt_tokens_details
                .and_then(|details| details.cache_write_tokens)
                .or(self.cache_write_tokens)
                .unwrap_or(0)
                .saturating_sub(written_cartridge),
            self.completion_tokens,
            self.completion_tokens_details
                .and_then(|details| details.reasoning_tokens)
                .or(self.reasoning_tokens)
                .unwrap_or(0),
        )
        .map(|usage| {
            usage.with_estimated_joules(self.estimated_joules.and_then(|value| value.as_f64()))
        })
        .map_err(|_| ProtocolViolation::Usage.into())
    }
}

#[derive(Debug, Deserialize)]
struct PromptTokenDetails {
    #[serde(default)]
    cached_tokens: u64,
    #[serde(default)]
    cache_write_tokens: Option<u64>,
}

#[derive(Debug, Deserialize)]
struct CompletionTokenDetails {
    #[serde(default)]
    reasoning_tokens: Option<u64>,
}

#[derive(Serialize)]
pub(super) struct NormalizedCompletionResponse {
    pub(super) id: String,
    pub(super) object: String,
    pub(super) created: u64,
    pub(super) model: String,
    pub(super) choices: Vec<Choice>,
    pub(super) usage: PublicUsage,
}

#[derive(Serialize)]
pub(super) struct NormalizedStreamResponse {
    pub(super) id: String,
    pub(super) object: String,
    pub(super) created: u64,
    pub(super) model: String,
    pub(super) choices: Vec<StreamChoice>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) usage: Option<PublicUsage>,
}

#[derive(Serialize)]
pub(super) struct PublicUsage {
    #[serde(skip_serializing_if = "Option::is_none")]
    estimated_joules: Option<f64>,
    prompt_tokens: u64,
    completion_tokens: u64,
    total_tokens: u64,
    prompt_tokens_details: PublicPromptTokenDetails,
    completion_tokens_details: PublicCompletionTokenDetails,
}

impl From<NormalizedUsage> for PublicUsage {
    fn from(usage: NormalizedUsage) -> Self {
        Self {
            estimated_joules: usage.estimated_joules(),
            prompt_tokens: usage.input_tokens(),
            completion_tokens: usage.output_tokens(),
            total_tokens: usage.input_tokens() + usage.output_tokens(),
            prompt_tokens_details: PublicPromptTokenDetails {
                cached_tokens: usage.cached_input_tokens(),
                cache_write_tokens: usage.cache_write_tokens(),
            },
            completion_tokens_details: PublicCompletionTokenDetails {
                reasoning_tokens: usage.reasoning_tokens(),
            },
        }
    }
}

#[derive(Serialize)]
struct PublicPromptTokenDetails {
    cached_tokens: u64,
    #[serde(skip_serializing_if = "is_zero")]
    cache_write_tokens: u64,
}

fn is_zero(value: &u64) -> bool {
    *value == 0
}

#[derive(Serialize)]
struct PublicCompletionTokenDetails {
    reasoning_tokens: u64,
}
