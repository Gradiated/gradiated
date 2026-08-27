use std::{
    collections::VecDeque, convert::Infallible, fs, path::PathBuf, pin::Pin, sync::Arc,
    time::Duration,
};

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use eventsource_stream::{Event, EventStreamError, Eventsource};
use futures_util::{stream, Stream, StreamExt};
use reqwest::{header, redirect::Policy, Certificate, Identity, StatusCode};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use thiserror::Error;
use uuid::Uuid;

use crate::{
    tokenizer::TokenizerDecodeState, ChatCompletionRequest, GatewayError, GatewayModelDeployment,
    ModelDeploymentRelease, ModelTokenizer, NormalizedUsage,
};

const CONNECT_TIMEOUT: Duration = Duration::from_secs(5);
const RESPONSE_IDLE_TIMEOUT: Duration = Duration::from_secs(30);
const MAX_RESPONSE_BYTES: usize = 8_000_000;
const MAX_STREAM_EVENT_BYTES: usize = 1_000_000;
const MAX_RESPONSE_TEXT_CHARS: usize = 300;
const MAX_JSON_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

#[async_trait]
pub trait ModelRuntime: Send + Sync {
    async fn complete(
        &self,
        deployment: &GatewayModelDeployment,
        request: ChatCompletionRequest,
        effective_output_tokens: u64,
        request_deadline: DateTime<Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure>;

    async fn stream(
        &self,
        _deployment: &GatewayModelDeployment,
        _request: ChatCompletionRequest,
        _effective_output_tokens: u64,
        _request_deadline: DateTime<Utc>,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))
    }
}

#[async_trait]
pub trait RuntimeEventStream: Send {
    async fn next_event(&mut self) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure>;
}

#[derive(Clone, Debug, PartialEq)]
pub enum RuntimeStreamEvent {
    Chunk(RuntimeStreamChunk),
    Done,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RuntimeStreamChunk {
    response: Value,
    usage: Option<NormalizedUsage>,
    finish_reason: Option<String>,
    usable_output: bool,
    terminal_usage: bool,
}

impl RuntimeStreamChunk {
    #[cfg(test)]
    pub(crate) fn from_normalized_parts(
        response: Value,
        usage: Option<NormalizedUsage>,
        finish_reason: Option<String>,
        usable_output: bool,
        terminal_usage: bool,
    ) -> Self {
        Self {
            response,
            usage,
            finish_reason,
            usable_output,
            terminal_usage,
        }
    }

    pub fn into_response(self) -> Value {
        self.response
    }

    pub fn usage(&self) -> Option<NormalizedUsage> {
        self.usage
    }

    pub fn finish_reason(&self) -> Option<&str> {
        self.finish_reason.as_deref()
    }

    pub fn has_usable_output(&self) -> bool {
        self.usable_output
    }

    pub fn is_terminal_usage(&self) -> bool {
        self.terminal_usage
    }
}

#[derive(Clone)]
pub struct SglangClient {
    client: reqwest::Client,
    api_key: Option<Arc<str>>,
    tokenizer: Option<ModelTokenizer>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RuntimeTlsConfig {
    ca_certificate_path: PathBuf,
    client_certificate_path: PathBuf,
    client_key_path: PathBuf,
}

impl RuntimeTlsConfig {
    pub fn from_environment() -> Result<Option<Self>, RuntimeClientError> {
        Self::from_paths(
            environment_path("SGLANG_TLS_CA_CERT_PATH"),
            environment_path("SGLANG_TLS_CLIENT_CERT_PATH"),
            environment_path("SGLANG_TLS_CLIENT_KEY_PATH"),
        )
    }

    fn from_paths(
        ca_certificate_path: Option<PathBuf>,
        client_certificate_path: Option<PathBuf>,
        client_key_path: Option<PathBuf>,
    ) -> Result<Option<Self>, RuntimeClientError> {
        match (
            ca_certificate_path,
            client_certificate_path,
            client_key_path,
        ) {
            (None, None, None) => Ok(None),
            (Some(ca_certificate_path), Some(client_certificate_path), Some(client_key_path)) => {
                Ok(Some(Self {
                    ca_certificate_path,
                    client_certificate_path,
                    client_key_path,
                }))
            }
            _ => Err(RuntimeClientError::IncompleteTlsConfiguration),
        }
    }
}

fn environment_path(name: &str) -> Option<PathBuf> {
    std::env::var_os(name)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
}

impl SglangClient {
    pub fn new(api_key: Option<String>) -> Result<Self, RuntimeClientError> {
        Self::new_with_tls(api_key, None)
    }

    pub fn new_with_tls(
        api_key: Option<String>,
        tls: Option<&RuntimeTlsConfig>,
    ) -> Result<Self, RuntimeClientError> {
        let client = build_http_client(tls)?;

        Ok(Self {
            client,
            api_key: api_key.map(Arc::from),
            tokenizer: None,
        })
    }

    pub fn with_tokenizer(
        api_key: Option<String>,
        tokenizer: ModelTokenizer,
    ) -> Result<Self, RuntimeClientError> {
        Self::with_tokenizer_and_tls(api_key, tokenizer, None)
    }

    pub fn with_tokenizer_and_tls(
        api_key: Option<String>,
        tokenizer: ModelTokenizer,
        tls: Option<&RuntimeTlsConfig>,
    ) -> Result<Self, RuntimeClientError> {
        let mut client = Self::new_with_tls(api_key, tls)?;
        client.tokenizer = Some(tokenizer);
        Ok(client)
    }

    pub async fn check_all(
        &self,
        deployments: &[GatewayModelDeployment],
    ) -> Result<(), RuntimeHealthError> {
        for deployment in deployments {
            let health_url = endpoint(&deployment.service_url, "health");
            let mut request = self.client.get(health_url);
            if let Some(api_key) = &self.api_key {
                request = request.bearer_auth(api_key);
            }
            let response = request.send().await?;
            if !response.status().is_success() {
                return Err(RuntimeHealthError::UnhealthyStatus(response.status()));
            }
        }
        Ok(())
    }

    async fn execute_non_streaming(
        &self,
        deployment: &GatewayModelDeployment,
        request: ChatCompletionRequest,
        effective_output_tokens: u64,
        response_header_timeout: Duration,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        if request.stream || effective_output_tokens == 0 {
            return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
        }

        if deployment.release.runtime_revision.starts_with("native-") {
            return self
                .execute_native(
                    deployment,
                    request,
                    effective_output_tokens,
                    response_header_timeout,
                )
                .await;
        }

        let requested_model = request.model.clone();
        let runtime_model = deployment
            .release
            .runtime_model_name
            .clone()
            .unwrap_or_else(|| requested_model.clone());
        let body = serde_json::to_vec(
            &request.into_upstream_body_for_model(effective_output_tokens, Some(&runtime_model)),
        )
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        let mut upstream = self
            .client
            .post(endpoint(&deployment.service_url, "v1/chat/completions"))
            .header(header::CONTENT_TYPE, "application/json")
            .header(header::ACCEPT, "application/json")
            .body(one_shot_body(body));
        if let Some(api_key) = &self.api_key {
            upstream = upstream.bearer_auth(api_key);
        }

        let response = tokio::time::timeout(response_header_timeout, upstream.send())
            .await
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::Unavailable))?;
        let status = response.status();
        if !status.is_success() {
            let kind = match status {
                StatusCode::BAD_REQUEST | StatusCode::UNPROCESSABLE_ENTITY => {
                    RuntimeFailureKind::InvalidRequest
                }
                StatusCode::TOO_MANY_REQUESTS => RuntimeFailureKind::CapacityExceeded,
                _ => RuntimeFailureKind::Unavailable,
            };
            let usage = match read_bounded_body(response).await {
                Ok(body) => optional_usage(&body).unwrap_or_else(NormalizedUsage::zero),
                Err(_) => NormalizedUsage::zero(),
            };
            return Err(RuntimeFailure { kind, usage });
        }

        let body = read_bounded_body(response).await?;
        normalize_completion(&body, &requested_model, &runtime_model)
    }

    async fn execute_native(
        &self,
        deployment: &GatewayModelDeployment,
        request: ChatCompletionRequest,
        effective_output_tokens: u64,
        response_header_timeout: Duration,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        validate_native_parameters(&request)?;
        let tokenizer = self
            .tokenizer
            .as_ref()
            .ok_or_else(|| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        let input_ids = request
            .encoded_input_ids
            .clone()
            .ok_or_else(|| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        let max_tokens = usize::try_from(effective_output_tokens)
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::InvalidRequest))?;
        let body = serde_json::to_vec(&NativeTokenRequest {
            input_ids: &input_ids,
            max_tokens,
            stream: false,
        })
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        let mut upstream = self
            .client
            .post(endpoint(&deployment.service_url, "v1/token-completions"))
            .header(header::CONTENT_TYPE, "application/json")
            .header(header::ACCEPT, "application/json")
            // Desmond's deliberately small HTTP/1.1 parser requires a bounded
            // Content-Length body and does not accept chunked request framing.
            .body(body);
        if let Some(api_key) = &self.api_key {
            upstream = upstream.bearer_auth(api_key);
        }
        let response = tokio::time::timeout(response_header_timeout, upstream.send())
            .await
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::Unavailable))?;
        let status = response.status();
        if !status.is_success() {
            return Err(RuntimeFailure::new(match status {
                StatusCode::BAD_REQUEST | StatusCode::UNPROCESSABLE_ENTITY => {
                    RuntimeFailureKind::InvalidRequest
                }
                StatusCode::TOO_MANY_REQUESTS => RuntimeFailureKind::CapacityExceeded,
                _ => RuntimeFailureKind::Unavailable,
            }));
        }
        let body = read_bounded_body(response).await?;
        let native: NativeTokenResponse = serde_json::from_slice(&body)
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        if native.usage.input_tokens != input_ids.len()
            || native.usage.cached_input_tokens > native.usage.input_tokens
            || native.usage.output_tokens != native.output_ids.len()
            || native.output_ids.len() > max_tokens
            || native.finish_reason.is_empty()
        {
            return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
        }
        let content = tokenizer
            .decode(&deployment.release, native.output_ids)
            .await
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::Unavailable))?;
        let usage = NormalizedUsage::new(
            native.usage.input_tokens as u64,
            native.usage.cached_input_tokens as u64,
            0,
            native.usage.output_tokens as u64,
            0,
        )
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        let created = u64::try_from(Utc::now().timestamp())
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        let finish_reason = native.finish_reason;
        let response = serde_json::to_value(NormalizedCompletionResponse {
            id: format!("chatcmpl-{}", Uuid::now_v7()),
            object: "chat.completion".to_owned(),
            created,
            model: request.model,
            choices: vec![NormalizedChoice {
                index: 0,
                message: Map::from_iter([
                    ("role".to_owned(), Value::String("assistant".to_owned())),
                    ("content".to_owned(), Value::String(content)),
                ]),
                logprobs: None,
                finish_reason: finish_reason.clone(),
            }],
            usage: usage.into(),
        })
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        Ok(RuntimeCompletion {
            response,
            finish_reason,
            usage,
        })
    }

    async fn execute_streaming(
        &self,
        deployment: &GatewayModelDeployment,
        request: ChatCompletionRequest,
        effective_output_tokens: u64,
        response_header_timeout: Duration,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        if !request.stream || effective_output_tokens == 0 {
            return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
        }

        if deployment.release.runtime_revision.starts_with("native-") {
            return self
                .execute_native_streaming(
                    deployment,
                    request,
                    effective_output_tokens,
                    response_header_timeout,
                )
                .await;
        }

        let requested_model = request.model.clone();
        let runtime_model = deployment
            .release
            .runtime_model_name
            .clone()
            .unwrap_or_else(|| requested_model.clone());
        let body = serde_json::to_vec(
            &request.into_upstream_body_for_model(effective_output_tokens, Some(&runtime_model)),
        )
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        let mut upstream = self
            .client
            .post(endpoint(&deployment.service_url, "v1/chat/completions"))
            .header(header::CONTENT_TYPE, "application/json")
            .header(header::ACCEPT, "text/event-stream")
            .body(one_shot_body(body));
        if let Some(api_key) = &self.api_key {
            upstream = upstream.bearer_auth(api_key);
        }

        let response = tokio::time::timeout(response_header_timeout, upstream.send())
            .await
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::Unavailable))?;
        let status = response.status();
        if !status.is_success() {
            let kind = match status {
                StatusCode::BAD_REQUEST | StatusCode::UNPROCESSABLE_ENTITY => {
                    RuntimeFailureKind::InvalidRequest
                }
                StatusCode::TOO_MANY_REQUESTS => RuntimeFailureKind::CapacityExceeded,
                _ => RuntimeFailureKind::Unavailable,
            };
            let usage = match read_bounded_body(response).await {
                Ok(body) => optional_usage(&body).unwrap_or_else(NormalizedUsage::zero),
                Err(_) => NormalizedUsage::zero(),
            };
            return Err(RuntimeFailure { kind, usage });
        }
        if response
            .headers()
            .get(header::CONTENT_TYPE)
            .and_then(|value| value.to_str().ok())
            .is_none_or(|value| !value.starts_with("text/event-stream"))
        {
            return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
        }

        let bytes = response
            .bytes_stream()
            .map(|result| result.map_err(|_| RuntimeFailure::new(RuntimeFailureKind::Unavailable)))
            .scan(0_usize, |total, result| {
                let result = result.and_then(|bytes| {
                    *total = total
                        .checked_add(bytes.len())
                        .ok_or_else(|| RuntimeFailure::new(RuntimeFailureKind::ResponseTooLarge))?;
                    if *total > MAX_RESPONSE_BYTES {
                        return Err(RuntimeFailure::new(RuntimeFailureKind::ResponseTooLarge));
                    }
                    Ok(bytes)
                });
                std::future::ready(Some(result))
            })
            .eventsource();
        Ok(Box::new(SglangEventStream::new(
            Box::pin(bytes),
            requested_model,
            runtime_model,
        )))
    }

    async fn execute_native_streaming(
        &self,
        deployment: &GatewayModelDeployment,
        request: ChatCompletionRequest,
        effective_output_tokens: u64,
        response_header_timeout: Duration,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        validate_native_parameters(&request)?;
        let tokenizer = self
            .tokenizer
            .clone()
            .ok_or_else(|| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        let input_ids = request
            .encoded_input_ids
            .clone()
            .ok_or_else(|| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        let max_tokens = usize::try_from(effective_output_tokens)
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::InvalidRequest))?;
        let body = serde_json::to_vec(&NativeTokenRequest {
            input_ids: &input_ids,
            max_tokens,
            stream: true,
        })
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        let mut upstream = self
            .client
            .post(endpoint(&deployment.service_url, "v1/token-completions"))
            .header(header::CONTENT_TYPE, "application/json")
            .header(header::ACCEPT, "text/event-stream")
            // Keep the native C++ boundary length-delimited in both response
            // modes; streaming applies to the response, not the request body.
            .body(body);
        if let Some(api_key) = &self.api_key {
            upstream = upstream.bearer_auth(api_key);
        }
        let response = tokio::time::timeout(response_header_timeout, upstream.send())
            .await
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::Unavailable))?;
        if !response.status().is_success() {
            return Err(RuntimeFailure::new(match response.status() {
                StatusCode::BAD_REQUEST | StatusCode::UNPROCESSABLE_ENTITY => {
                    RuntimeFailureKind::InvalidRequest
                }
                StatusCode::TOO_MANY_REQUESTS => RuntimeFailureKind::CapacityExceeded,
                _ => RuntimeFailureKind::Unavailable,
            }));
        }
        if response
            .headers()
            .get(header::CONTENT_TYPE)
            .and_then(|value| value.to_str().ok())
            .is_none_or(|value| !value.starts_with("text/event-stream"))
        {
            return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
        }
        let bytes = response
            .bytes_stream()
            .map(|result| result.map_err(|_| RuntimeFailure::new(RuntimeFailureKind::Unavailable)))
            .scan(0_usize, |total, result| {
                let result = result.and_then(|bytes| {
                    *total = total
                        .checked_add(bytes.len())
                        .ok_or_else(|| RuntimeFailure::new(RuntimeFailureKind::ResponseTooLarge))?;
                    if *total > MAX_RESPONSE_BYTES {
                        return Err(RuntimeFailure::new(RuntimeFailureKind::ResponseTooLarge));
                    }
                    Ok(bytes)
                });
                std::future::ready(Some(result))
            })
            .eventsource();
        Ok(Box::new(NativeEventStream::new(
            Box::pin(bytes),
            tokenizer,
            deployment.release.clone(),
            request.model,
            input_ids.len(),
            max_tokens,
        )))
    }
}

fn build_http_client(
    tls: Option<&RuntimeTlsConfig>,
) -> Result<reqwest::Client, RuntimeClientError> {
    let mut builder = reqwest::Client::builder()
        .connect_timeout(CONNECT_TIMEOUT)
        .redirect(Policy::none());

    if let Some(tls) = tls {
        let ca_certificate = read_tls_file(&tls.ca_certificate_path)?;
        let client_certificate = read_tls_file(&tls.client_certificate_path)?;
        let client_key = read_tls_file(&tls.client_key_path)?;
        let mut identity = Vec::with_capacity(client_certificate.len() + client_key.len() + 1);
        identity.extend_from_slice(&client_certificate);
        if !identity.ends_with(b"\n") {
            identity.push(b'\n');
        }
        identity.extend_from_slice(&client_key);

        builder = builder
            .add_root_certificate(Certificate::from_pem(&ca_certificate)?)
            .identity(Identity::from_pem(&identity)?);
    }

    Ok(builder.build()?)
}

fn read_tls_file(path: &PathBuf) -> Result<Vec<u8>, RuntimeClientError> {
    fs::read(path).map_err(|source| RuntimeClientError::TlsFile {
        path: path.clone(),
        source,
    })
}

#[async_trait]
impl ModelRuntime for SglangClient {
    async fn complete(
        &self,
        deployment: &GatewayModelDeployment,
        request: ChatCompletionRequest,
        effective_output_tokens: u64,
        request_deadline: DateTime<Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        let remaining = request_deadline
            .signed_duration_since(Utc::now())
            .to_std()
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?;

        tokio::time::timeout(remaining, async {
            self.execute_non_streaming(deployment, request, effective_output_tokens, remaining)
                .await
        })
        .await
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?
    }

    async fn stream(
        &self,
        deployment: &GatewayModelDeployment,
        request: ChatCompletionRequest,
        effective_output_tokens: u64,
        request_deadline: DateTime<Utc>,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        let remaining = request_deadline
            .signed_duration_since(Utc::now())
            .to_std()
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?;
        self.execute_streaming(deployment, request, effective_output_tokens, remaining)
            .await
    }
}

fn one_shot_body(body: Vec<u8>) -> reqwest::Body {
    reqwest::Body::wrap_stream(stream::once(async move {
        Result::<Vec<u8>, Infallible>::Ok(body)
    }))
}

fn endpoint(service_url: &str, path: &str) -> String {
    format!("{}/{}", service_url.trim_end_matches('/'), path)
}

fn validate_native_parameters(request: &ChatCompletionRequest) -> Result<(), RuntimeFailure> {
    if request
        .parameters
        .get("temperature")
        .is_some_and(|value| value.as_f64() != Some(0.0))
        || [
            "top_p",
            "top_k",
            "min_p",
            "seed",
            "frequency_penalty",
            "presence_penalty",
            "repetition_penalty",
        ]
        .iter()
        .any(|name| request.parameters.contains_key(*name))
    {
        return Err(RuntimeFailure::new(RuntimeFailureKind::InvalidRequest));
    }
    Ok(())
}

async fn read_bounded_body(mut response: reqwest::Response) -> Result<Vec<u8>, RuntimeFailure> {
    if response
        .content_length()
        .is_some_and(|length| length > MAX_RESPONSE_BYTES as u64)
    {
        return Err(RuntimeFailure::new(RuntimeFailureKind::ResponseTooLarge));
    }

    let mut body = Vec::with_capacity(
        response
            .content_length()
            .unwrap_or(0)
            .min(MAX_RESPONSE_BYTES as u64) as usize,
    );
    loop {
        let chunk = tokio::time::timeout(RESPONSE_IDLE_TIMEOUT, response.chunk())
            .await
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::Unavailable))?;
        let Some(chunk) = chunk else {
            break;
        };
        if body
            .len()
            .checked_add(chunk.len())
            .is_none_or(|length| length > MAX_RESPONSE_BYTES)
        {
            return Err(RuntimeFailure::new(RuntimeFailureKind::ResponseTooLarge));
        }
        body.extend_from_slice(&chunk);
    }
    Ok(body)
}

struct SglangEventStream {
    events: Pin<Box<dyn Stream<Item = Result<Event, EventStreamError<RuntimeFailure>>> + Send>>,
    requested_model: String,
    runtime_model: String,
    response_id: Option<String>,
    created: Option<u64>,
    done: bool,
}

impl SglangEventStream {
    fn new(
        events: Pin<Box<dyn Stream<Item = Result<Event, EventStreamError<RuntimeFailure>>> + Send>>,
        requested_model: String,
        runtime_model: String,
    ) -> Self {
        Self {
            events,
            requested_model,
            runtime_model,
            response_id: None,
            created: None,
            done: false,
        }
    }
}

#[async_trait]
impl RuntimeEventStream for SglangEventStream {
    async fn next_event(&mut self) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure> {
        if self.done {
            return Ok(None);
        }
        let event = tokio::time::timeout(RESPONSE_IDLE_TIMEOUT, self.events.next())
            .await
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?;
        let Some(event) = event else {
            return Ok(None);
        };
        let event = event.map_err(|error| match error {
            EventStreamError::Transport(failure) => failure,
            EventStreamError::Utf8(_) | EventStreamError::Parser(_) => {
                RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation)
            }
        })?;
        if event.event != "message"
            || !event.id.is_empty()
            || event.retry.is_some()
            || event.data.len() > MAX_STREAM_EVENT_BYTES
        {
            return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
        }
        if event.data == "[DONE]" {
            self.done = true;
            return Ok(Some(RuntimeStreamEvent::Done));
        }
        let chunk = normalize_stream_chunk(
            event.data.as_bytes(),
            &self.requested_model,
            &self.runtime_model,
            &mut self.response_id,
            &mut self.created,
        )?;
        Ok(Some(RuntimeStreamEvent::Chunk(chunk)))
    }
}

struct NativeEventStream {
    events: Pin<Box<dyn Stream<Item = Result<Event, EventStreamError<RuntimeFailure>>> + Send>>,
    tokenizer: ModelTokenizer,
    release: ModelDeploymentRelease,
    requested_model: String,
    response_id: String,
    created: u64,
    input_tokens: usize,
    max_tokens: usize,
    output_tokens: usize,
    decode_state: TokenizerDecodeState,
    pending: VecDeque<RuntimeStreamEvent>,
    terminal_received: bool,
    done: bool,
    sent_role: bool,
}

impl NativeEventStream {
    fn new(
        events: Pin<Box<dyn Stream<Item = Result<Event, EventStreamError<RuntimeFailure>>> + Send>>,
        tokenizer: ModelTokenizer,
        release: ModelDeploymentRelease,
        requested_model: String,
        input_tokens: usize,
        max_tokens: usize,
    ) -> Self {
        Self {
            events,
            tokenizer,
            release,
            requested_model,
            response_id: format!("chatcmpl-{}", Uuid::now_v7()),
            created: Utc::now().timestamp().try_into().unwrap_or(0),
            input_tokens,
            max_tokens,
            output_tokens: 0,
            decode_state: TokenizerDecodeState::default(),
            pending: VecDeque::new(),
            terminal_received: false,
            done: false,
            sent_role: false,
        }
    }

    fn response(&self, choices: Vec<NormalizedStreamChoice>, usage: Option<PublicUsage>) -> Value {
        serde_json::to_value(NormalizedStreamResponse {
            id: self.response_id.clone(),
            object: "chat.completion.chunk".to_owned(),
            created: self.created,
            model: self.requested_model.clone(),
            choices,
            usage,
        })
        .expect("normalized native stream response is serializable")
    }
}

#[async_trait]
impl RuntimeEventStream for NativeEventStream {
    async fn next_event(&mut self) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure> {
        if let Some(event) = self.pending.pop_front() {
            return Ok(Some(event));
        }
        if self.done {
            return Ok(None);
        }
        loop {
            let event = tokio::time::timeout(RESPONSE_IDLE_TIMEOUT, self.events.next())
                .await
                .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?;
            let Some(event) = event else {
                return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
            };
            let event = event.map_err(|error| match error {
                EventStreamError::Transport(failure) => failure,
                EventStreamError::Utf8(_) | EventStreamError::Parser(_) => {
                    RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation)
                }
            })?;
            if event.event != "message"
                || !event.id.is_empty()
                || event.retry.is_some()
                || event.data.len() > MAX_STREAM_EVENT_BYTES
            {
                return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
            }
            if event.data == "[DONE]" {
                if !self.terminal_received {
                    return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
                }
                self.done = true;
                return Ok(Some(RuntimeStreamEvent::Done));
            }
            let value: Value = serde_json::from_str(&event.data)
                .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
            if let Some(token_id) = value.get("token_id").and_then(Value::as_u64) {
                let token: NativeStreamToken = serde_json::from_value(value)
                    .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
                if self.terminal_received || token.token_id != token_id {
                    return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
                }
                let token_id = u32::try_from(token_id)
                    .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
                self.output_tokens += 1;
                if self.output_tokens > self.max_tokens {
                    return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
                }
                if token.usage.input_tokens != self.input_tokens
                    || token.usage.cached_input_tokens > token.usage.input_tokens
                    || token.usage.output_tokens != self.output_tokens
                {
                    return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
                }
                let usage = NormalizedUsage::new(
                    self.input_tokens as u64,
                    token.usage.cached_input_tokens as u64,
                    0,
                    self.output_tokens as u64,
                    0,
                )
                .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
                let state = std::mem::take(&mut self.decode_state);
                let (state, decoded) = self
                    .tokenizer
                    .decode_step(&self.release, state, token_id)
                    .await
                    .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::Unavailable))?;
                self.decode_state = state;
                let Some(content) = decoded else {
                    continue;
                };
                let mut delta = Map::new();
                if !self.sent_role {
                    delta.insert("role".to_owned(), Value::String("assistant".to_owned()));
                    self.sent_role = true;
                }
                delta.insert("content".to_owned(), Value::String(content.clone()));
                let response = self.response(
                    vec![NormalizedStreamChoice {
                        index: 0,
                        delta,
                        logprobs: None,
                        finish_reason: None,
                    }],
                    None,
                );
                return Ok(Some(RuntimeStreamEvent::Chunk(RuntimeStreamChunk {
                    response,
                    usage: Some(usage),
                    finish_reason: None,
                    usable_output: !content.is_empty(),
                    terminal_usage: false,
                })));
            }

            let terminal: NativeStreamTerminal = serde_json::from_value(value)
                .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
            if self.terminal_received
                || terminal.finish_reason.is_empty()
                || terminal.usage.input_tokens != self.input_tokens
                || terminal.usage.cached_input_tokens > terminal.usage.input_tokens
                || terminal.usage.output_tokens != self.output_tokens
            {
                return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
            }
            self.terminal_received = true;
            let usage = NormalizedUsage::new(
                self.input_tokens as u64,
                terminal.usage.cached_input_tokens as u64,
                0,
                self.output_tokens as u64,
                0,
            )
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
            let finish_reason = terminal.finish_reason;
            let finish = RuntimeStreamChunk {
                response: self.response(
                    vec![NormalizedStreamChoice {
                        index: 0,
                        delta: Map::new(),
                        logprobs: None,
                        finish_reason: Some(finish_reason.clone()),
                    }],
                    None,
                ),
                usage: None,
                finish_reason: Some(finish_reason.clone()),
                usable_output: false,
                terminal_usage: false,
            };
            let terminal_usage = RuntimeStreamChunk {
                response: self.response(Vec::new(), Some(usage.into())),
                usage: Some(usage),
                finish_reason: None,
                usable_output: false,
                terminal_usage: true,
            };
            self.pending
                .push_back(RuntimeStreamEvent::Chunk(terminal_usage));
            return Ok(Some(RuntimeStreamEvent::Chunk(finish)));
        }
    }
}

fn normalize_completion(
    body: &[u8],
    requested_model: &str,
    runtime_model: &str,
) -> Result<RuntimeCompletion, RuntimeFailure> {
    let response: UpstreamCompletion = serde_json::from_slice(body)
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
    if response.object != "chat.completion"
        || response.id.is_empty()
        || response.id.chars().count() > MAX_RESPONSE_TEXT_CHARS
        || response.model != runtime_model
        || response.choices.is_empty()
        || response.choices.iter().any(UpstreamChoice::is_invalid)
    {
        return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
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
    let response = serde_json::to_value(response)
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;

    Ok(RuntimeCompletion {
        response,
        finish_reason,
        usage,
    })
}

fn normalize_stream_chunk(
    body: &[u8],
    requested_model: &str,
    runtime_model: &str,
    response_id: &mut Option<String>,
    created: &mut Option<u64>,
) -> Result<RuntimeStreamChunk, RuntimeFailure> {
    let chunk: UpstreamStreamChunk = serde_json::from_slice(body)
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
    if chunk.object != "chat.completion.chunk"
        || chunk.id.is_empty()
        || chunk.id.chars().count() > MAX_RESPONSE_TEXT_CHARS
        || chunk.model != runtime_model
        || chunk.choices.iter().any(UpstreamStreamChoice::is_invalid)
        || response_id.as_ref().is_some_and(|id| id != &chunk.id)
        || created.is_some_and(|value| value != chunk.created)
    {
        return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
    }
    response_id.get_or_insert_with(|| chunk.id.clone());
    created.get_or_insert(chunk.created);

    let usage = chunk.usage.map(UpstreamUsage::normalize).transpose()?;
    let terminal_usage = chunk.choices.is_empty();
    if terminal_usage && usage.is_none() {
        return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
    }
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
        usage: terminal_usage.then(|| PublicUsage::from(usage.expect("validated usage"))),
    };
    let response = serde_json::to_value(response)
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
    Ok(RuntimeStreamChunk {
        response,
        usage,
        finish_reason,
        usable_output,
        terminal_usage,
    })
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

#[derive(Serialize)]
struct NativeTokenRequest<'a> {
    input_ids: &'a [u32],
    max_tokens: usize,
    stream: bool,
}

#[derive(Deserialize)]
struct NativeTokenResponse {
    output_ids: Vec<u32>,
    usage: NativeTokenUsage,
    finish_reason: String,
}

#[derive(Deserialize)]
struct NativeTokenUsage {
    input_tokens: usize,
    cached_input_tokens: usize,
    output_tokens: usize,
}

#[derive(Deserialize)]
struct NativeStreamTerminal {
    finish_reason: String,
    usage: NativeTokenUsage,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct NativeStreamToken {
    token_id: u64,
    usage: NativeTokenUsage,
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
                .as_ref()
                .is_some_and(|reason| reason.is_empty() || reason.chars().count() > 100)
    }

    fn has_usable_output(&self) -> bool {
        self.delta
            .get("content")
            .and_then(Value::as_str)
            .is_some_and(|content| !content.is_empty())
            || self
                .delta
                .get("reasoning_content")
                .and_then(Value::as_str)
                .is_some_and(|content| !content.is_empty())
            || self
                .delta
                .get("tool_calls")
                .and_then(Value::as_array)
                .is_some_and(|calls| !calls.is_empty())
            || self
                .delta
                .get("function_call")
                .is_some_and(|value| !value.is_null())
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
        self.index > MAX_JSON_SAFE_INTEGER
            || self.finish_reason.is_empty()
            || self.finish_reason.chars().count() > 100
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
            .ok_or_else(|| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        if expected_total != self.total_tokens || self.total_tokens > MAX_JSON_SAFE_INTEGER {
            return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
        }
        NormalizedUsage::new(
            self.prompt_tokens,
            self.prompt_tokens_details
                .map_or(0, |details| details.cached_tokens),
            self.cache_write_tokens.unwrap_or(0),
            self.completion_tokens,
            self.reasoning_tokens.unwrap_or(0),
        )
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))
    }
}

#[derive(Debug, Deserialize)]
struct PromptTokenDetails {
    #[serde(default)]
    cached_tokens: u64,
}

#[derive(Serialize)]
struct NormalizedCompletionResponse {
    id: String,
    object: String,
    created: u64,
    model: String,
    choices: Vec<NormalizedChoice>,
    usage: PublicUsage,
}

#[derive(Serialize)]
struct NormalizedStreamResponse {
    id: String,
    object: String,
    created: u64,
    model: String,
    choices: Vec<NormalizedStreamChoice>,
    #[serde(skip_serializing_if = "Option::is_none")]
    usage: Option<PublicUsage>,
}

#[derive(Serialize)]
struct NormalizedStreamChoice {
    index: u64,
    delta: Map<String, Value>,
    logprobs: Option<Value>,
    finish_reason: Option<String>,
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
struct NormalizedChoice {
    index: u64,
    message: Map<String, Value>,
    logprobs: Option<Value>,
    finish_reason: String,
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
struct PublicUsage {
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

#[derive(Clone, Debug, PartialEq)]
pub struct RuntimeCompletion {
    response: Value,
    finish_reason: String,
    usage: NormalizedUsage,
}

impl RuntimeCompletion {
    #[cfg(test)]
    pub(crate) fn from_normalized_parts(
        response: Value,
        finish_reason: String,
        usage: NormalizedUsage,
    ) -> Self {
        Self {
            response,
            finish_reason,
            usage,
        }
    }

    pub fn response(&self) -> &Value {
        &self.response
    }

    pub fn into_response(self) -> Value {
        self.response
    }

    pub fn finish_reason(&self) -> &str {
        &self.finish_reason
    }

    pub fn usage(&self) -> NormalizedUsage {
        self.usage
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RuntimeFailureKind {
    InvalidRequest,
    CapacityExceeded,
    Unavailable,
    TimedOut,
    ResponseTooLarge,
    ProtocolViolation,
}

#[derive(Clone, Debug, Error, Eq, PartialEq)]
#[error("model runtime failed: {kind:?}")]
pub struct RuntimeFailure {
    kind: RuntimeFailureKind,
    usage: NormalizedUsage,
}

impl RuntimeFailure {
    pub fn new(kind: RuntimeFailureKind) -> Self {
        Self {
            kind,
            usage: NormalizedUsage::zero(),
        }
    }

    pub(crate) fn with_usage(kind: RuntimeFailureKind, usage: NormalizedUsage) -> Self {
        Self { kind, usage }
    }

    pub fn kind(&self) -> RuntimeFailureKind {
        self.kind
    }

    pub fn usage(&self) -> NormalizedUsage {
        self.usage
    }

    pub fn gateway_error(&self) -> GatewayError {
        match self.kind {
            RuntimeFailureKind::InvalidRequest => GatewayError::invalid_request(None),
            RuntimeFailureKind::CapacityExceeded => GatewayError::CapacityExceeded,
            RuntimeFailureKind::Unavailable
            | RuntimeFailureKind::TimedOut
            | RuntimeFailureKind::ResponseTooLarge
            | RuntimeFailureKind::ProtocolViolation => GatewayError::RuntimeUnavailable,
        }
    }
}

#[derive(Debug, Error)]
pub enum RuntimeClientError {
    #[error("runtime HTTP client could not be built: {0}")]
    Request(#[from] reqwest::Error),
    #[error(
        "SGLANG_TLS_CA_CERT_PATH, SGLANG_TLS_CLIENT_CERT_PATH, and SGLANG_TLS_CLIENT_KEY_PATH must be set together"
    )]
    IncompleteTlsConfiguration,
    #[error("runtime TLS file {path} could not be read: {source}")]
    TlsFile {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },
}

#[derive(Debug, Error)]
pub enum RuntimeHealthError {
    #[error("SGLang health request failed: {0}")]
    Request(#[from] reqwest::Error),
    #[error("SGLang health endpoint returned {0}")]
    UnhealthyStatus(reqwest::StatusCode),
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Mutex,
    };

    use axum::{
        body::{Body, Bytes},
        extract::State,
        http::{header::LOCATION, HeaderMap, StatusCode},
        response::{IntoResponse, Response},
        routing::post,
        Router,
    };
    use serde_json::json;
    use tokio::task::JoinHandle;
    use uuid::Uuid;

    use super::*;
    use crate::{DeploymentStatus, ModelDeploymentRelease};

    #[test]
    fn runtime_tls_paths_are_optional_as_one_group() {
        assert_eq!(
            RuntimeTlsConfig::from_paths(None, None, None).unwrap(),
            None
        );

        let config = RuntimeTlsConfig::from_paths(
            Some(PathBuf::from("ca.crt")),
            Some(PathBuf::from("client.crt")),
            Some(PathBuf::from("client.key")),
        )
        .unwrap()
        .unwrap();
        assert_eq!(config.ca_certificate_path, PathBuf::from("ca.crt"));
        assert_eq!(config.client_certificate_path, PathBuf::from("client.crt"));
        assert_eq!(config.client_key_path, PathBuf::from("client.key"));
    }

    #[test]
    fn runtime_tls_rejects_partial_path_groups() {
        for paths in [
            (Some(PathBuf::from("ca.crt")), None, None),
            (
                Some(PathBuf::from("ca.crt")),
                Some(PathBuf::from("client.crt")),
                None,
            ),
            (None, None, Some(PathBuf::from("client.key"))),
        ] {
            assert!(matches!(
                RuntimeTlsConfig::from_paths(paths.0, paths.1, paths.2),
                Err(RuntimeClientError::IncompleteTlsConfiguration)
            ));
        }
    }

    #[derive(Clone)]
    struct RecordedRequest {
        headers: HeaderMap,
        body: Value,
    }

    #[derive(Clone)]
    struct TestServerState {
        recorded: Arc<Mutex<Vec<RecordedRequest>>>,
        status: StatusCode,
        response: Value,
    }

    async fn respond(
        State(state): State<TestServerState>,
        headers: HeaderMap,
        body: Bytes,
    ) -> impl IntoResponse {
        state.recorded.lock().unwrap().push(RecordedRequest {
            headers,
            body: serde_json::from_slice(&body).unwrap(),
        });
        (state.status, axum::Json(state.response))
    }

    async fn server(
        status: StatusCode,
        response: Value,
    ) -> (String, Arc<Mutex<Vec<RecordedRequest>>>, JoinHandle<()>) {
        let recorded = Arc::new(Mutex::new(Vec::new()));
        let state = TestServerState {
            recorded: recorded.clone(),
            status,
            response,
        };
        let application = Router::new()
            .route("/v1/chat/completions", post(respond))
            .with_state(state);
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let task = tokio::spawn(async move {
            axum::serve(listener, application).await.unwrap();
        });
        (format!("http://{address}"), recorded, task)
    }

    fn deployment(service_url: String) -> GatewayModelDeployment {
        GatewayModelDeployment {
            id: Uuid::now_v7(),
            status: DeploymentStatus::Available,
            provider: "local".to_owned(),
            region: "local".to_owned(),
            fault_domain: "local:runtime-1".to_owned(),
            service_url,
            release: ModelDeploymentRelease {
                schema_version: 1,
                runtime_revision: "runtime".to_owned(),
                model_path: "model-a".to_owned(),
                model_revision: "model-revision".to_owned(),
                runtime_model_name: None,
                tokenizer_path: "model-a".to_owned(),
                tokenizer_revision: "tokenizer-revision".to_owned(),
                tokenizer_mode: None,
            },
        }
    }

    fn request() -> ChatCompletionRequest {
        ChatCompletionRequest::parse(
            br#"{
                "model":"model-a",
                "messages":[{"role":"user","content":"hello"}],
                "temperature":0.25,
                "tools":[{"type":"function","function":{"name":"weather"}}]
            }"#,
        )
        .unwrap()
    }

    fn streaming_request() -> ChatCompletionRequest {
        ChatCompletionRequest::parse(
            br#"{
                "model":"model-a",
                "messages":[{"role":"user","content":"hello"}],
                "stream":true
            }"#,
        )
        .unwrap()
    }

    fn successful_response() -> Value {
        json!({
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 1_777_000_000,
            "model": "model-a",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "hello",
                    "reasoning_content": null,
                    "tool_calls": null
                },
                "logprobs": null,
                "finish_reason": "stop",
                "matched_stop": 1
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "prompt_tokens_details": {"cached_tokens": 4},
                "reasoning_tokens": 2
            },
            "metadata": {"private_runtime_field": true}
        })
    }

    #[tokio::test]
    async fn sends_one_qualified_request_and_normalizes_the_response() {
        let mut upstream_response = successful_response();
        upstream_response["model"] = json!("runtime-model");
        let (service_url, recorded, task) = server(StatusCode::OK, upstream_response).await;
        let runtime = SglangClient::new(Some("runtime-secret".to_owned())).unwrap();
        let mut deployment = deployment(service_url);
        deployment.release.runtime_model_name = Some("runtime-model".to_owned());

        let completion = runtime
            .complete(
                &deployment,
                request(),
                1_024,
                Utc::now() + chrono::TimeDelta::seconds(5),
            )
            .await
            .unwrap();

        let requests = recorded.lock().unwrap();
        assert_eq!(requests.len(), 1);
        assert_eq!(
            requests[0].headers[header::AUTHORIZATION],
            "Bearer runtime-secret"
        );
        assert_eq!(requests[0].body["model"], "runtime-model");
        assert_eq!(requests[0].body["messages"][0]["content"], "hello");
        assert_eq!(requests[0].body["temperature"], 0.25);
        assert_eq!(requests[0].body["tools"][0]["function"]["name"], "weather");
        assert_eq!(requests[0].body["max_completion_tokens"], 1_024);
        assert_eq!(requests[0].body["stream"], false);

        assert_eq!(completion.finish_reason(), "stop");
        assert_eq!(completion.usage().input_tokens(), 10);
        assert_eq!(completion.usage().cached_input_tokens(), 4);
        assert_eq!(completion.usage().output_tokens(), 5);
        assert_eq!(completion.usage().reasoning_tokens(), 2);
        assert_eq!(completion.response()["usage"]["total_tokens"], 15);
        assert_eq!(completion.response()["model"], "model-a");
        assert!(completion.response().get("metadata").is_none());
        assert!(completion.response()["choices"][0]
            .get("matched_stop")
            .is_none());
        task.abort();
    }

    #[tokio::test]
    async fn parses_and_normalizes_sglang_streaming_events() {
        let recorded = Arc::new(Mutex::new(Vec::new()));
        let captured = recorded.clone();
        let application = Router::new().route(
            "/v1/chat/completions",
            post(move |headers: HeaderMap, body: Bytes| {
                let captured = captured.clone();
                async move {
                    captured.lock().unwrap().push(RecordedRequest {
                        headers,
                        body: serde_json::from_slice(&body).unwrap(),
                    });
                    Response::builder()
                        .header("content-type", "text/event-stream")
                        .body(Body::from(concat!(
                            "data: {\"id\":\"chatcmpl-stream\",\"object\":\"chat.completion.chunk\",\"created\":1,\"model\":\"runtime-model\",\"choices\":[{\"index\":0,\"delta\":{\"content\":\"hello\"},\"finish_reason\":null}],\"usage\":{\"prompt_tokens\":10,\"completion_tokens\":1,\"total_tokens\":11}}\n\n",
                            "data: {\"id\":\"chatcmpl-stream\",\"object\":\"chat.completion.chunk\",\"created\":1,\"model\":\"runtime-model\",\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}]}\n\n",
                            "data: {\"id\":\"chatcmpl-stream\",\"object\":\"chat.completion.chunk\",\"created\":1,\"model\":\"runtime-model\",\"choices\":[],\"usage\":{\"prompt_tokens\":10,\"completion_tokens\":1,\"total_tokens\":11}}\n\n",
                            "data: [DONE]\n\n"
                        )))
                        .unwrap()
                }
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let task = tokio::spawn(async move {
            axum::serve(listener, application).await.unwrap();
        });
        let runtime = SglangClient::new(None).unwrap();
        let mut deployment = deployment(format!("http://{address}"));
        deployment.release.runtime_model_name = Some("runtime-model".to_owned());
        let mut response = runtime
            .stream(
                &deployment,
                streaming_request(),
                32,
                Utc::now() + chrono::TimeDelta::seconds(5),
            )
            .await
            .unwrap();

        let first = response.next_event().await.unwrap().unwrap();
        let RuntimeStreamEvent::Chunk(first) = first else {
            panic!("first event must be a chunk");
        };
        assert!(first.has_usable_output());
        assert_eq!(first.clone().into_response()["model"], "model-a");
        assert_eq!(first.usage().unwrap().output_tokens(), 1);
        assert!(first.clone().into_response().get("usage").is_none());

        let finish = response.next_event().await.unwrap().unwrap();
        let RuntimeStreamEvent::Chunk(finish) = finish else {
            panic!("second event must be a chunk");
        };
        assert_eq!(finish.finish_reason(), Some("stop"));

        let usage = response.next_event().await.unwrap().unwrap();
        let RuntimeStreamEvent::Chunk(usage) = usage else {
            panic!("third event must be a chunk");
        };
        assert!(usage.is_terminal_usage());
        assert_eq!(usage.into_response()["usage"]["total_tokens"], 11);
        assert_eq!(
            response.next_event().await.unwrap(),
            Some(RuntimeStreamEvent::Done)
        );

        let requests = recorded.lock().unwrap();
        assert_eq!(requests[0].body["model"], "runtime-model");
        assert_eq!(requests[0].body["stream"], true);
        assert_eq!(requests[0].body["stream_options"]["include_usage"], true);
        assert_eq!(
            requests[0].body["stream_options"]["continuous_usage_stats"],
            true
        );
        task.abort();
    }

    #[tokio::test]
    #[ignore = "downloads the pinned production Gemma tokenizer from Hugging Face"]
    async fn parses_native_token_streams_with_authoritative_usage() {
        let recorded = Arc::new(Mutex::new(Vec::new()));
        let captured = recorded.clone();
        let application = Router::new().route(
            "/v1/token-completions",
            post(move |headers: HeaderMap, body: Bytes| {
                let captured = captured.clone();
                async move {
                    captured.lock().unwrap().push(RecordedRequest {
                        headers,
                        body: serde_json::from_slice(&body).unwrap(),
                    });
                    Response::builder()
                        .header("content-type", "text/event-stream")
                        .body(Body::from(concat!(
                            "data: {\"token_id\":2021,\"usage\":{\"input_tokens\":3,\"cached_input_tokens\":2,\"output_tokens\":1}}\n\n",
                            "data: {\"token_id\":1586,\"usage\":{\"input_tokens\":3,\"cached_input_tokens\":2,\"output_tokens\":2}}\n\n",
                            "data: {\"finish_reason\":\"length\",\"usage\":{\"input_tokens\":3,\"cached_input_tokens\":2,\"output_tokens\":2}}\n\n",
                            "data: [DONE]\n\n"
                        )))
                        .unwrap()
                }
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let task = tokio::spawn(async move {
            axum::serve(listener, application).await.unwrap();
        });
        let tokenizer = ModelTokenizer::new().unwrap();
        let runtime = SglangClient::with_tokenizer(None, tokenizer).unwrap();
        let mut deployment = deployment(format!("http://{address}"));
        deployment.release.runtime_revision = "native-gemma4-h200-v1".to_owned();
        deployment.release.model_path = "google/gemma-4-31B-it".to_owned();
        deployment.release.model_revision = "b9ea41a2887d8607f594846523f94c6cc75ac8a4".to_owned();
        deployment.release.tokenizer_path = "google/gemma-4-31B-it".to_owned();
        deployment.release.tokenizer_revision =
            "b9ea41a2887d8607f594846523f94c6cc75ac8a4".to_owned();
        let mut request = streaming_request();
        request.encoded_input_ids = Some(vec![2, 3, 4]);
        let mut response = runtime
            .stream(
                &deployment,
                request,
                8,
                Utc::now() + chrono::TimeDelta::seconds(30),
            )
            .await
            .unwrap();

        let mut usable_chunks = 0;
        let mut finish = None;
        let mut terminal_usage = None;
        while let RuntimeStreamEvent::Chunk(chunk) = response.next_event().await.unwrap().unwrap() {
            if chunk.has_usable_output() {
                usable_chunks += 1;
                assert!(chunk.usage().is_some());
            }
            if let Some(reason) = chunk.finish_reason() {
                finish = Some(reason.to_owned());
            }
            if chunk.is_terminal_usage() {
                terminal_usage = chunk.usage();
            }
        }
        assert!(usable_chunks > 0);
        assert_eq!(finish.as_deref(), Some("length"));
        assert_eq!(terminal_usage.unwrap().input_tokens(), 3);
        assert_eq!(terminal_usage.unwrap().cached_input_tokens(), 2);
        assert_eq!(terminal_usage.unwrap().output_tokens(), 2);
        let requests = recorded.lock().unwrap();
        assert_eq!(requests[0].body["input_ids"], json!([2, 3, 4]));
        assert_eq!(requests[0].body["stream"], true);
        task.abort();
    }

    #[tokio::test]
    async fn maps_overload_without_retrying_and_retains_valid_error_usage() {
        let response = json!({
            "error": {"message": "queue full"},
            "usage": {
                "prompt_tokens": 2,
                "completion_tokens": 1,
                "total_tokens": 3,
                "reasoning_tokens": 0
            }
        });
        let (service_url, recorded, task) = server(StatusCode::TOO_MANY_REQUESTS, response).await;
        let runtime = SglangClient::new(None).unwrap();

        let failure = runtime
            .complete(
                &deployment(service_url),
                request(),
                1_024,
                Utc::now() + chrono::TimeDelta::seconds(5),
            )
            .await
            .unwrap_err();

        assert_eq!(failure.kind(), RuntimeFailureKind::CapacityExceeded);
        assert_eq!(failure.gateway_error(), GatewayError::CapacityExceeded);
        assert_eq!(failure.usage().input_tokens(), 2);
        assert_eq!(recorded.lock().unwrap().len(), 1);
        task.abort();
    }

    #[tokio::test]
    async fn rejects_inconsistent_authoritative_usage() {
        let mut response = successful_response();
        response["usage"]["total_tokens"] = json!(16);
        let (service_url, _, task) = server(StatusCode::OK, response).await;
        let runtime = SglangClient::new(None).unwrap();

        let failure = runtime
            .complete(
                &deployment(service_url),
                request(),
                1_024,
                Utc::now() + chrono::TimeDelta::seconds(5),
            )
            .await
            .unwrap_err();

        assert_eq!(failure.kind(), RuntimeFailureKind::ProtocolViolation);
        task.abort();
    }

    #[tokio::test]
    async fn native_requests_are_length_delimited_for_the_cpp_runtime() {
        let recorded = Arc::new(Mutex::new(Vec::new()));
        let captured = recorded.clone();
        let application = Router::new().route(
            "/v1/token-completions",
            post(move |headers: HeaderMap, body: Bytes| {
                let captured = captured.clone();
                async move {
                    captured.lock().unwrap().push(RecordedRequest {
                        headers,
                        body: serde_json::from_slice(&body).unwrap(),
                    });
                    (
                        StatusCode::BAD_REQUEST,
                        axum::Json(json!({"error": "invalid_request"})),
                    )
                }
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let task = tokio::spawn(async move {
            axum::serve(listener, application).await.unwrap();
        });
        let runtime = SglangClient::with_tokenizer(None, ModelTokenizer::new().unwrap()).unwrap();
        let mut deployment = deployment(format!("http://{address}"));
        deployment.release.runtime_revision = "native-gemma4-h200-v1".to_owned();

        let mut non_streaming =
            ChatCompletionRequest::parse(br#"{"model":"model-a","messages":[{}],"temperature":0}"#)
                .unwrap();
        non_streaming.encoded_input_ids = Some(vec![2, 3, 4]);
        let failure = runtime
            .complete(
                &deployment,
                non_streaming,
                8,
                Utc::now() + chrono::TimeDelta::seconds(5),
            )
            .await
            .unwrap_err();
        assert_eq!(failure.kind(), RuntimeFailureKind::InvalidRequest);

        let mut streaming = streaming_request();
        streaming.encoded_input_ids = Some(vec![2, 3, 4]);
        let failure = runtime
            .stream(
                &deployment,
                streaming,
                8,
                Utc::now() + chrono::TimeDelta::seconds(5),
            )
            .await
            .err()
            .expect("native request should preserve the upstream rejection");
        assert_eq!(failure.kind(), RuntimeFailureKind::InvalidRequest);

        let requests = recorded.lock().unwrap();
        assert_eq!(requests.len(), 2);
        for request in requests.iter() {
            assert!(request.headers.contains_key(header::CONTENT_LENGTH));
            assert!(!request.headers.contains_key(header::TRANSFER_ENCODING));
            assert_eq!(request.body["input_ids"], json!([2, 3, 4]));
        }
        task.abort();
    }

    #[tokio::test]
    async fn native_runtime_rejects_unimplemented_stochastic_sampling() {
        let runtime = SglangClient::new(None).unwrap();
        let mut deployment = deployment("http://127.0.0.1:1".to_owned());
        deployment.release.runtime_revision = "native-gemma4-h200-v1".to_owned();
        let failure = runtime
            .complete(
                &deployment,
                request(),
                32,
                Utc::now() + chrono::TimeDelta::seconds(5),
            )
            .await
            .unwrap_err();
        assert_eq!(failure.kind(), RuntimeFailureKind::InvalidRequest);
    }

    #[tokio::test]
    async fn refuses_non_streaming_execution_after_the_deadline() {
        let runtime = SglangClient::new(None).unwrap();

        let failure = runtime
            .complete(
                &deployment("http://127.0.0.1:1".to_owned()),
                request(),
                1_024,
                Utc::now() - chrono::TimeDelta::seconds(1),
            )
            .await
            .unwrap_err();

        assert_eq!(failure.kind(), RuntimeFailureKind::TimedOut);
    }

    #[test]
    fn request_body_is_not_replayable() {
        assert!(one_shot_body(b"private prompt".to_vec())
            .as_bytes()
            .is_none());
    }

    #[tokio::test]
    async fn does_not_follow_a_runtime_redirect() {
        let initial_requests = Arc::new(AtomicUsize::new(0));
        let redirected_requests = Arc::new(AtomicUsize::new(0));
        let initial_counter = initial_requests.clone();
        let redirected_counter = redirected_requests.clone();
        let application = Router::new()
            .route(
                "/v1/chat/completions",
                post(move || {
                    let counter = initial_counter.clone();
                    async move {
                        counter.fetch_add(1, Ordering::SeqCst);
                        (StatusCode::TEMPORARY_REDIRECT, [(LOCATION, "/redirected")])
                    }
                }),
            )
            .route(
                "/redirected",
                post(move || {
                    let counter = redirected_counter.clone();
                    async move {
                        counter.fetch_add(1, Ordering::SeqCst);
                        axum::Json(successful_response())
                    }
                }),
            );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let task = tokio::spawn(async move {
            axum::serve(listener, application).await.unwrap();
        });
        let runtime = SglangClient::new(None).unwrap();

        let failure = runtime
            .complete(
                &deployment(format!("http://{address}")),
                request(),
                1_024,
                Utc::now() + chrono::TimeDelta::seconds(5),
            )
            .await
            .unwrap_err();

        assert_eq!(failure.kind(), RuntimeFailureKind::Unavailable);
        assert_eq!(initial_requests.load(Ordering::SeqCst), 1);
        assert_eq!(redirected_requests.load(Ordering::SeqCst), 0);
        task.abort();
    }
}
