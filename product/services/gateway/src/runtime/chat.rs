//! The OpenAI chat completions protocol that ordinary SGLang deployments serve.

use std::time::Duration;

use async_trait::async_trait;
use reqwest::{header, Response};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use super::{
    client::{next_message, one_shot_body, open_events, read_bounded_body, send, RuntimeEvents},
    RuntimeCompletion, RuntimeEventStream, RuntimeFailure, RuntimeStreamChunk, RuntimeStreamEvent,
    SglangClient,
};
use crate::{GatewayModelDeployment, InferenceRequest, NormalizedUsage};

const CHAT_COMPLETIONS: &str = "v1/chat/completions";
const MAX_RESPONSE_TEXT_CHARS: usize = 300;
const MAX_FINISH_REASON_CHARS: usize = 100;
const MAX_JSON_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

impl SglangClient {
    pub(super) async fn complete_chat(
        &self,
        deployment: &GatewayModelDeployment,
        request: InferenceRequest,
        effective_output_tokens: u64,
        response_header_timeout: Duration,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        let models = ModelNames::new(deployment, &request);
        let body = chat_body(request, effective_output_tokens, &models)?;

        let upstream = self
            .post(deployment, CHAT_COMPLETIONS, one_shot_body(body))
            .header(header::ACCEPT, "application/json");
        let response = send(upstream, response_header_timeout).await?;
        if !response.status().is_success() {
            return Err(rejected_with_usage(response).await);
        }

        let body = read_bounded_body(response).await?;
        normalize_completion(&body, &models.requested, &models.runtime)
    }

    pub(super) async fn stream_chat(
        &self,
        deployment: &GatewayModelDeployment,
        request: InferenceRequest,
        effective_output_tokens: u64,
        response_header_timeout: Duration,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        let models = ModelNames::new(deployment, &request);
        let body = chat_body(request, effective_output_tokens, &models)?;

        let upstream = self
            .post(deployment, CHAT_COMPLETIONS, one_shot_body(body))
            .header(header::ACCEPT, "text/event-stream");
        let response = send(upstream, response_header_timeout).await?;
        if !response.status().is_success() {
            return Err(rejected_with_usage(response).await);
        }

        let events = open_events(response)?;
        Ok(Box::new(ChatEventStream {
            events,
            models,
            response_id: None,
            created: None,
            done: false,
        }))
    }
}

/// The name the caller asked for and the name the runtime serves. They differ
/// when a release sets `runtime_model_name`, and responses are renamed back.
struct ModelNames {
    requested: String,
    runtime: String,
}

impl ModelNames {
    fn new(deployment: &GatewayModelDeployment, request: &InferenceRequest) -> Self {
        let requested = request.model.clone();
        let runtime = deployment
            .release
            .runtime_model_name
            .clone()
            .unwrap_or_else(|| requested.clone());

        Self { requested, runtime }
    }
}

fn chat_body(
    request: InferenceRequest,
    effective_output_tokens: u64,
    models: &ModelNames,
) -> Result<Vec<u8>, RuntimeFailure> {
    let body = request.into_upstream_body_for_model(effective_output_tokens, Some(&models.runtime));

    serde_json::to_vec(&body).map_err(|_| RuntimeFailure::protocol_violation())
}

/// A rejected chat request can still report usage the runtime consumed.
async fn rejected_with_usage(response: Response) -> RuntimeFailure {
    let status = response.status();
    let usage = match read_bounded_body(response).await {
        Ok(body) => optional_usage(&body).unwrap_or_else(NormalizedUsage::zero),
        Err(_) => NormalizedUsage::zero(),
    };

    RuntimeFailure::rejected(status, usage)
}

struct ChatEventStream {
    events: RuntimeEvents,
    models: ModelNames,
    response_id: Option<String>,
    created: Option<u64>,
    done: bool,
}

#[async_trait]
impl RuntimeEventStream for ChatEventStream {
    async fn next_event(&mut self) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure> {
        if self.done {
            return Ok(None);
        }

        let Some(data) = next_message(&mut self.events).await? else {
            return Ok(None);
        };

        if data == "[DONE]" {
            self.done = true;
            return Ok(Some(RuntimeStreamEvent::Done));
        }

        let chunk = normalize_stream_chunk(
            data.as_bytes(),
            &self.models.requested,
            &self.models.runtime,
            &mut self.response_id,
            &mut self.created,
        )?;

        Ok(Some(RuntimeStreamEvent::Chunk(chunk)))
    }
}

pub(super) fn normalize_completion(
    body: &[u8],
    requested_model: &str,
    runtime_model: &str,
) -> Result<RuntimeCompletion, RuntimeFailure> {
    let response: UpstreamCompletion =
        serde_json::from_slice(body).map_err(|_| RuntimeFailure::protocol_violation())?;
    if response.object != "chat.completion"
        || !valid_response_id(&response.id)
        || response.model != runtime_model
        || response.choices.is_empty()
        || response.choices.iter().any(UpstreamChoice::is_invalid)
    {
        return Err(RuntimeFailure::protocol_violation());
    }

    let usage = response.usage.normalize()?;
    let finish_reason = response.choices[0].finish_reason.clone();
    let response = NormalizedCompletionResponse {
        id: response.id,
        object: response.object,
        created: response.created,
        model: requested_model.to_owned(),
        choices: response
            .choices
            .into_iter()
            .map(NormalizedChoice::from)
            .collect(),
        usage: PublicUsage::from(usage),
    };

    Ok(RuntimeCompletion {
        response: serde_json::to_value(response)
            .map_err(|_| RuntimeFailure::protocol_violation())?,
        finish_reason,
        usage,
    })
}

/// Normalizes one stream chunk. Every chunk of a response must carry the ID and
/// creation time of the first one.
pub(super) fn normalize_stream_chunk(
    body: &[u8],
    requested_model: &str,
    runtime_model: &str,
    response_id: &mut Option<String>,
    created: &mut Option<u64>,
) -> Result<RuntimeStreamChunk, RuntimeFailure> {
    let chunk: UpstreamStreamChunk =
        serde_json::from_slice(body).map_err(|_| RuntimeFailure::protocol_violation())?;
    if chunk.object != "chat.completion.chunk"
        || !valid_response_id(&chunk.id)
        || chunk.model != runtime_model
        || chunk.choices.iter().any(UpstreamStreamChoice::is_invalid)
        || response_id.as_ref().is_some_and(|id| id != &chunk.id)
        || created.is_some_and(|value| value != chunk.created)
    {
        return Err(RuntimeFailure::protocol_violation());
    }

    response_id.get_or_insert_with(|| chunk.id.clone());
    created.get_or_insert(chunk.created);

    // A chunk without choices is the terminal usage report.
    let terminal_usage = chunk.choices.is_empty();
    let usage = chunk.usage.map(UpstreamUsage::normalize).transpose()?;
    let public_usage = match (terminal_usage, usage) {
        (true, None) => return Err(RuntimeFailure::protocol_violation()),
        (true, Some(usage)) => Some(PublicUsage::from(usage)),
        (false, _) => None,
    };

    let finish_reason = chunk
        .choices
        .iter()
        .find_map(|choice| choice.finish_reason.clone());
    let usable_output = chunk
        .choices
        .iter()
        .any(UpstreamStreamChoice::has_usable_output);
    let response = NormalizedStreamResponse {
        id: chunk.id,
        object: chunk.object,
        created: chunk.created,
        model: requested_model.to_owned(),
        choices: chunk
            .choices
            .into_iter()
            .map(NormalizedStreamChoice::from)
            .collect(),
        usage: public_usage,
    };

    Ok(RuntimeStreamChunk {
        response: serde_json::to_value(response)
            .map_err(|_| RuntimeFailure::protocol_violation())?,
        usage,
        finish_reason,
        usable_output,
        terminal_usage,
    })
}

fn valid_response_id(id: &str) -> bool {
    !id.is_empty() && id.chars().count() <= MAX_RESPONSE_TEXT_CHARS
}

fn valid_finish_reason(reason: &str) -> bool {
    !reason.is_empty() && reason.chars().count() <= MAX_FINISH_REASON_CHARS
}

fn optional_usage(body: &[u8]) -> Option<NormalizedUsage> {
    #[derive(Deserialize)]
    struct UsageEnvelope {
        usage: Option<UpstreamUsage>,
    }

    serde_json::from_slice::<UsageEnvelope>(body)
        .ok()?
        .usage?
        .normalize()
        .ok()
}

#[derive(Debug, Deserialize)]
struct UpstreamCompletion {
    id: String,
    object: String,
    created: u64,
    model: String,
    choices: Vec<UpstreamChoice>,
    usage: UpstreamUsage,
}

#[derive(Debug, Deserialize)]
struct UpstreamStreamChunk {
    id: String,
    object: String,
    created: u64,
    model: String,
    #[serde(default)]
    choices: Vec<UpstreamStreamChoice>,
    #[serde(default)]
    usage: Option<UpstreamUsage>,
}

#[derive(Debug, Deserialize)]
struct UpstreamStreamChoice {
    index: u64,
    delta: Map<String, Value>,
    #[serde(default)]
    logprobs: Option<Value>,
    #[serde(default)]
    finish_reason: Option<String>,
}

impl UpstreamStreamChoice {
    fn is_invalid(&self) -> bool {
        self.index > MAX_JSON_SAFE_INTEGER
            || self
                .finish_reason
                .as_deref()
                .is_some_and(|reason| !valid_finish_reason(reason))
    }

    /// Text, reasoning or a tool call. Role-only and empty deltas are not output.
    fn has_usable_output(&self) -> bool {
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

#[derive(Debug, Deserialize)]
struct UpstreamChoice {
    index: u64,
    message: Map<String, Value>,
    #[serde(default)]
    logprobs: Option<Value>,
    finish_reason: String,
}

impl UpstreamChoice {
    fn is_invalid(&self) -> bool {
        self.index > MAX_JSON_SAFE_INTEGER || !valid_finish_reason(&self.finish_reason)
    }
}

#[derive(Debug, Deserialize)]
struct UpstreamUsage {
    prompt_tokens: u64,
    completion_tokens: u64,
    total_tokens: u64,
    #[serde(default)]
    prompt_tokens_details: Option<PromptTokenDetails>,
    #[serde(default)]
    reasoning_tokens: Option<u64>,
    #[serde(default)]
    cache_write_tokens: Option<u64>,
}

impl UpstreamUsage {
    fn normalize(self) -> Result<NormalizedUsage, RuntimeFailure> {
        let expected_total = self
            .prompt_tokens
            .checked_add(self.completion_tokens)
            .ok_or_else(RuntimeFailure::protocol_violation)?;
        if expected_total != self.total_tokens || self.total_tokens > MAX_JSON_SAFE_INTEGER {
            return Err(RuntimeFailure::protocol_violation());
        }

        NormalizedUsage::new(
            self.prompt_tokens,
            self.prompt_tokens_details
                .map_or(0, |details| details.cached_tokens),
            self.cache_write_tokens.unwrap_or(0),
            self.completion_tokens,
            self.reasoning_tokens.unwrap_or(0),
        )
        .map_err(|_| RuntimeFailure::protocol_violation())
    }
}

#[derive(Debug, Deserialize)]
struct PromptTokenDetails {
    #[serde(default)]
    cached_tokens: u64,
}

#[derive(Serialize)]
pub(super) struct NormalizedCompletionResponse {
    pub(super) id: String,
    pub(super) object: String,
    pub(super) created: u64,
    pub(super) model: String,
    pub(super) choices: Vec<NormalizedChoice>,
    pub(super) usage: PublicUsage,
}

#[derive(Serialize)]
pub(super) struct NormalizedStreamResponse {
    pub(super) id: String,
    pub(super) object: String,
    pub(super) created: u64,
    pub(super) model: String,
    pub(super) choices: Vec<NormalizedStreamChoice>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) usage: Option<PublicUsage>,
}

#[derive(Serialize)]
pub(super) struct NormalizedStreamChoice {
    pub(super) index: u64,
    pub(super) delta: Map<String, Value>,
    pub(super) logprobs: Option<Value>,
    pub(super) finish_reason: Option<String>,
}

impl From<UpstreamStreamChoice> for NormalizedStreamChoice {
    fn from(choice: UpstreamStreamChoice) -> Self {
        Self {
            index: choice.index,
            delta: choice.delta,
            logprobs: choice.logprobs,
            finish_reason: choice.finish_reason,
        }
    }
}

#[derive(Serialize)]
pub(super) struct NormalizedChoice {
    pub(super) index: u64,
    pub(super) message: Map<String, Value>,
    pub(super) logprobs: Option<Value>,
    pub(super) finish_reason: String,
}

impl From<UpstreamChoice> for NormalizedChoice {
    fn from(choice: UpstreamChoice) -> Self {
        Self {
            index: choice.index,
            message: choice.message,
            logprobs: choice.logprobs,
            finish_reason: choice.finish_reason,
        }
    }
}

#[derive(Serialize)]
pub(super) struct PublicUsage {
    prompt_tokens: u64,
    completion_tokens: u64,
    total_tokens: u64,
    prompt_tokens_details: PublicPromptTokenDetails,
    completion_tokens_details: PublicCompletionTokenDetails,
}

impl From<NormalizedUsage> for PublicUsage {
    fn from(usage: NormalizedUsage) -> Self {
        Self {
            prompt_tokens: usage.input_tokens(),
            completion_tokens: usage.output_tokens(),
            total_tokens: usage.input_tokens() + usage.output_tokens(),
            prompt_tokens_details: PublicPromptTokenDetails {
                cached_tokens: usage.cached_input_tokens(),
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
}

#[derive(Serialize)]
struct PublicCompletionTokenDetails {
    reasoning_tokens: u64,
}
