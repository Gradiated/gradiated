use std::{collections::VecDeque, sync::Arc, time::Duration};

use async_trait::async_trait;
use reqwest::{header, redirect::Policy, Response, StatusCode};
use serde::Deserialize;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use uuid::Uuid;

use super::{
    chat::{
        valid_finish_reason, valid_response_id, Choice, NormalizedCompletionResponse,
        NormalizedStreamResponse, PublicUsage, StreamChoice,
    },
    client::{
        next_message, one_shot_body, open_events, read_bounded_body, read_completion_body,
        record_rejection, remaining_until, send, within, RuntimeEvents, CONNECT_TIMEOUT,
    },
    progress::ProgressStream,
    ChunkUsage, ExternalCapacity, ExternalModel, ExternalRequest, FailureCause, ProtocolViolation,
    RuntimeClientError, RuntimeCompletion, RuntimeEventStream, RuntimeFailure, RuntimeFailureKind,
    RuntimeStreamChunk, RuntimeStreamEvent,
};
use crate::{config::OpenRouterConfig, model::MAX_SAFE_INTEGER, NormalizedUsage};
use gradiated_credentials::{CredentialLoader, Provider};

const STREAM_ADMISSION_PEEK: Duration = Duration::from_secs(1);
const REJECTION_READ: Duration = Duration::from_millis(250);
const MAX_PROVIDER_NAME_CHARS: usize = 100;

/// Advertised parameters OpenRouter does not understand. It ignores rather than
/// rejects them, so a request carrying one stays on our capacity.
const UNSUPPORTED_PARAMETERS: [&str; 1] = ["chat_template_kwargs"];

pub fn supports_parameter(name: &str) -> bool {
    !UNSUPPORTED_PARAMETERS.contains(&name)
}

#[derive(Clone)]
pub struct OpenRouterClient {
    client: reqwest::Client,
    api_key: ApiKey,
    endpoint: Arc<str>,
}

#[derive(Clone)]
enum ApiKey {
    Fixed(Arc<str>),
    Rotating(Arc<CredentialLoader>),
}

impl OpenRouterClient {
    pub async fn connect(config: &OpenRouterConfig) -> Result<Self, RuntimeClientError> {
        let api_key = match &config.api_key {
            Some(key) => ApiKey::Fixed(Arc::from(key.as_str())),
            None => {
                let aws = aws_config::defaults(aws_config::BehaviorVersion::latest())
                    .region(aws_config::Region::new("us-east-1"))
                    .load()
                    .await;
                ApiKey::Rotating(Arc::new(CredentialLoader::new(
                    aws_sdk_secretsmanager::Client::new(&aws),
                )))
            }
        };

        Self::with_key(&config.base_url, api_key)
    }

    #[cfg(test)]
    pub(crate) fn with_loader(
        base_url: &str,
        loader: CredentialLoader,
    ) -> Result<Self, RuntimeClientError> {
        Self::with_key(base_url, ApiKey::Rotating(Arc::new(loader)))
    }

    fn with_key(base_url: &str, api_key: ApiKey) -> Result<Self, RuntimeClientError> {
        let client = reqwest::Client::builder()
            .connect_timeout(CONNECT_TIMEOUT)
            .redirect(Policy::none())
            .build()?;

        Ok(Self {
            client,
            api_key,
            endpoint: Arc::from(format!("{base_url}/chat/completions")),
        })
    }

    /// The loader returns no detail on failure, so none can reach a log.
    async fn api_key(&self) -> Result<Arc<str>, RuntimeFailure> {
        match &self.api_key {
            ApiKey::Fixed(key) => Ok(key.clone()),
            ApiKey::Rotating(loader) => loader
                .load(Provider::OpenRouter)
                .await
                .map(Arc::from)
                .map_err(|_| {
                    crate::diagnostics::limited_warn!(
                        error_code = "openrouter_credential_unavailable",
                        "OpenRouter credential could not be loaded"
                    );
                    RuntimeFailure::caused(
                        RuntimeFailureKind::Unavailable,
                        FailureCause::Credential,
                    )
                }),
        }
    }

    async fn send(
        &self,
        request: ExternalRequest,
        accept: &str,
    ) -> Result<Response, RuntimeFailure> {
        let api_key = self.api_key().await?;
        let model = request.model.clone();
        let body = self.body(request);
        crate::diagnostics::body::record_value("runtime_request", &body, None);
        let body = serde_json::to_vec(&body).map_err(|_| ProtocolViolation::Json)?;

        let upstream = self
            .client
            .post(&*self.endpoint)
            .bearer_auth(&api_key)
            .header(header::CONTENT_TYPE, "application/json")
            .header(header::ACCEPT, accept)
            .body(one_shot_body(body));
        let response = send(upstream).await?;
        let status = response.status();
        if status.is_success() {
            return Ok(response);
        }

        if status != StatusCode::BAD_REQUEST {
            let status = record_rejection(response).await.as_u16();
            return Err(failure_for_code(status, NormalizedUsage::zero()));
        }

        if !rejects_model(response, &model).await {
            return Err(failure_for_code(400, NormalizedUsage::zero()));
        }

        crate::diagnostics::limited_warn!(
            error_code = "openrouter_model_rejected",
            openrouter_model = model.id(),
            "OpenRouter does not recognise the mapped model"
        );
        Err(RuntimeFailure::caused(
            RuntimeFailureKind::Unavailable,
            FailureCause::Status(400),
        ))
    }

    fn body(&self, request: ExternalRequest) -> Value {
        let ExternalRequest {
            workspace_id,
            model,
            request,
            output_tokens,
            price_cap,
            ..
        } = request;
        let session = request
            .session_id
            .as_deref()
            .map(|session| scoped_hash(workspace_id, session));

        let mut body = request.into_external_body(output_tokens, model.id());
        // Every request routes only to zero-retention endpoints that collect no data
        // and charge no more than the caller pays us.
        body.insert(
            "provider".to_owned(),
            json!({
                "data_collection": "deny",
                "require_parameters": true,
                "zdr": true,
                "max_price": {
                    "prompt": usd_per_million(price_cap.prompt),
                    "completion": usd_per_million(price_cap.completion),
                },
            }),
        );
        // Context compression is on by default for small-context endpoints and
        // would silently drop the middle of a prompt.
        body.insert(
            "plugins".to_owned(),
            json!([{"id": "context-compression", "enabled": false}]),
        );
        body.insert(
            "user".to_owned(),
            Value::String(scoped_hash(workspace_id, "")),
        );
        if let Some(session) = session {
            body.insert("session_id".to_owned(), Value::String(session));
        }

        Value::Object(body)
    }
}

fn usd_per_million(nano_usd_per_token: u64) -> f64 {
    nano_usd_per_token as f64 / 1_000.0
}

/// An opaque per-workspace value: OpenRouter isolates abuse controls by `user`
/// and keeps provider cache affinity by `session_id`, but neither needs our IDs.
fn scoped_hash(workspace_id: Uuid, value: &str) -> String {
    let mut hash = Sha256::new();
    hash.update(workspace_id.as_bytes());
    hash.update(value.as_bytes());

    format!("{:x}", hash.finalize())
}

#[async_trait]
impl ExternalCapacity for OpenRouterClient {
    async fn complete(
        &self,
        request: ExternalRequest,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        let remaining = remaining_until(request.deadline)?;
        let names = Names::new(&request);

        within(remaining, async move {
            let response = self.send(request, "application/json").await?;
            let body = read_completion_body(response).await?;

            normalize_completion(&body, &names)
        })
        .await
    }

    async fn stream(
        &self,
        request: ExternalRequest,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        let remaining = remaining_until(request.deadline)?;
        let deadline = tokio::time::Instant::now() + remaining;
        let names = Names::new(&request);

        let stream = within(remaining, async move {
            let response = self.send(request, "text/event-stream").await?;
            let mut stream = OpenRouterStream {
                events: open_events(response)?,
                normalizer: StreamNormalizer::new(names),
                pending: VecDeque::new(),
                phase: Phase::Streaming,
            };
            // An error OpenRouter reports in its first event fails the request
            // before the gateway commits its own response.
            if let Ok(first) =
                tokio::time::timeout(STREAM_ADMISSION_PEEK, stream.next_event()).await
            {
                stream.pending.extend(first?);
            }

            Ok(stream)
        })
        .await?;

        Ok(Box::new(ProgressStream::new(Box::new(stream), deadline)))
    }
}

struct Names {
    generation_id: Uuid,
    requested: String,
    upstream: ExternalModel,
    response_id: String,
}

impl Names {
    fn new(request: &ExternalRequest) -> Self {
        Self {
            generation_id: request.generation_id,
            requested: request.request.model.clone(),
            upstream: request.model.clone(),
            response_id: format!("chatcmpl-{}", request.generation_id.simple()),
        }
    }

    fn check_model(&self, model: &str) -> Result<(), RuntimeFailure> {
        if model != self.upstream.id() {
            return Err(ProtocolViolation::ModelMismatch.into());
        }

        Ok(())
    }
}

/// OpenRouter's own generation ID, provider and cost, kept for reconciliation.
fn log_usage(names: &Names, upstream_id: &str, provider: Option<&str>, usage: &OpenRouterUsage) {
    tracing::info!(generation_id = %names.generation_id,
        openrouter_model = names.upstream.id(),
        upstream_generation_id = upstream_id,
        upstream_provider = provider.filter(|name| name.chars().count() <= MAX_PROVIDER_NAME_CHARS),
        upstream_cost_nano_usd = usage.cost_nano_usd(),
        event = "openrouter_usage", "OpenRouter reported usage");
}

fn normalize_completion(body: &[u8], names: &Names) -> Result<RuntimeCompletion, RuntimeFailure> {
    let value: Value = serde_json::from_slice(body).map_err(|_| ProtocolViolation::Json)?;
    reject_reported_error(&value)?;

    let completion: OpenRouterCompletion =
        serde_json::from_value(value).map_err(|_| ProtocolViolation::Json)?;
    if completion.object != "chat.completion"
        || !valid_response_id(&completion.id)
        || completion.choices.is_empty()
        || completion
            .choices
            .iter()
            .any(|choice| choice.index > MAX_SAFE_INTEGER)
    {
        return Err(ProtocolViolation::ResponseShape.into());
    }

    names.check_model(&completion.model)?;
    let usage = completion.usage.normalize()?;
    log_usage(
        names,
        &completion.id,
        completion.provider.as_deref(),
        &completion.usage,
    );

    let mut choices = Vec::with_capacity(completion.choices.len());
    for choice in completion.choices {
        let finish_reason = choice
            .finish_reason
            .ok_or(ProtocolViolation::FinishReason)?;
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
        upstream_cost_nano_usd: completion.usage.cost_nano_usd(),
    })
}

/// OpenRouter reports a failure that follows committed headers inside a 200
/// response, as a top-level `error` object.
fn reject_reported_error(value: &Value) -> Result<(), RuntimeFailure> {
    let Some(error) = value.get("error").filter(|error| !error.is_null()) else {
        return Ok(());
    };

    let usage = value
        .get("usage")
        .and_then(|usage| OpenRouterUsage::deserialize(usage).ok())
        .and_then(|usage| usage.normalize().ok())
        .unwrap_or_else(NormalizedUsage::zero);
    let code = error
        .get("code")
        .and_then(Value::as_u64)
        .and_then(|code| u16::try_from(code).ok())
        .unwrap_or(500);

    Err(failure_for_code(code, usage))
}

/// A choice that OpenRouter ended with `error` failed upstream after it began.
fn check_finish_reason(reason: &str, usage: NormalizedUsage) -> Result<(), RuntimeFailure> {
    if reason == "error" {
        return Err(RuntimeFailure::caused(
            RuntimeFailureKind::Interrupted,
            FailureCause::Protocol(ProtocolViolation::FinishReason),
        )
        .or_usage(usage));
    }

    if !valid_finish_reason(reason) {
        return Err(ProtocolViolation::FinishReason.into());
    }

    Ok(())
}

/// Our credential, credit and routing problems are ours, not the caller's, so
/// only a malformed request is reported as one.
/// OpenRouter answers 400 for a model it does not list, which is our mapping's fault.
async fn rejects_model(response: Response, model: &ExternalModel) -> bool {
    let Ok(Ok(body)) = tokio::time::timeout(REJECTION_READ, read_bounded_body(response)).await
    else {
        return false;
    };

    serde_json::from_slice::<Value>(&body)
        .ok()
        .and_then(|value| {
            Some(
                value
                    .pointer("/error/message")?
                    .as_str()?
                    .contains(model.id()),
            )
        })
        .unwrap_or(false)
}

fn failure_for_code(code: u16, usage: NormalizedUsage) -> RuntimeFailure {
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
struct OpenRouterCompletion {
    id: String,
    object: String,
    created: u64,
    model: String,
    #[serde(default)]
    provider: Option<String>,
    choices: Vec<OpenRouterChoice>,
    usage: OpenRouterUsage,
}

#[derive(Deserialize)]
struct OpenRouterChoice {
    index: u64,
    message: Map<String, Value>,
    #[serde(default)]
    logprobs: Option<Value>,
    #[serde(default)]
    finish_reason: Option<String>,
}

#[derive(Deserialize)]
struct OpenRouterUsage {
    prompt_tokens: u64,
    completion_tokens: u64,
    total_tokens: u64,
    #[serde(default)]
    prompt_tokens_details: Option<PromptDetails>,
    #[serde(default)]
    completion_tokens_details: Option<CompletionDetails>,
    #[serde(default)]
    cost: Option<f64>,
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

impl OpenRouterUsage {
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

    /// OpenRouter's charge to Gradiated. It is recorded, never billed to the caller.
    fn cost_nano_usd(&self) -> Option<u64> {
        let nano_usd = (self.cost? * 1e9).round();

        (nano_usd.is_finite() && nano_usd >= 0.0 && nano_usd <= MAX_SAFE_INTEGER as f64)
            .then_some(nano_usd as u64)
    }
}

enum Phase {
    Streaming,
    AwaitingDone,
    Done,
}

struct OpenRouterStream {
    events: RuntimeEvents,
    normalizer: StreamNormalizer,
    pending: VecDeque<RuntimeStreamEvent>,
    phase: Phase,
}

#[async_trait]
impl RuntimeEventStream for OpenRouterStream {
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
                            "OpenRouter response frame rejected"
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
struct OpenRouterChunk {
    id: String,
    object: String,
    created: u64,
    model: String,
    #[serde(default)]
    provider: Option<String>,
    #[serde(default)]
    choices: Vec<OpenRouterDelta>,
    #[serde(default)]
    usage: Option<OpenRouterUsage>,
}

#[derive(Deserialize)]
struct OpenRouterDelta {
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

        let chunk: OpenRouterChunk =
            serde_json::from_value(value).map_err(|_| ProtocolViolation::Json)?;
        if chunk.object != "chat.completion.chunk"
            || !valid_response_id(&chunk.id)
            || chunk
                .choices
                .iter()
                .any(|choice| choice.index > MAX_SAFE_INTEGER)
        {
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

        let usage = chunk
            .usage
            .as_ref()
            .map(OpenRouterUsage::normalize)
            .transpose()?;
        let mut choices = Vec::with_capacity(chunk.choices.len());
        for choice in chunk.choices {
            if let Some(reason) = &choice.finish_reason {
                check_finish_reason(reason, usage.unwrap_or_else(NormalizedUsage::zero))?;
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

        if let (Some(usage), Some(upstream)) = (usage, &chunk.usage) {
            log_usage(&self.names, &chunk.id, chunk.provider.as_deref(), upstream);
            normalized.push(self.usage_chunk(created, usage, upstream.cost_nano_usd())?);
        }

        Ok(normalized)
    }

    /// The usage frame repeats the last finish reason in an otherwise empty choice.
    fn adds_to_stream(&self, choice: &StreamChoice) -> bool {
        choice.has_usable_output() || (choice.finish_reason.is_some() && !self.finished)
    }

    fn public_choice(&mut self, choice: OpenRouterDelta) -> StreamChoice {
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
