use std::{convert::Infallible, fs, path::PathBuf, pin::Pin, sync::Arc, time::Duration};

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use eventsource_stream::{Event, EventStreamError, Eventsource};
use futures_util::{stream, Stream, StreamExt};
use reqwest::{header, redirect::Policy, Certificate, Identity, RequestBuilder, Response};
use thiserror::Error;

use super::{
    ModelRuntime, RuntimeCompletion, RuntimeEventStream, RuntimeFailure, RuntimeFailureKind,
};
use crate::{GatewayModelDeployment, InferenceRequest, ModelTokenizer, NormalizedUsage};

const CONNECT_TIMEOUT: Duration = Duration::from_secs(5);
const RESPONSE_IDLE_TIMEOUT: Duration = Duration::from_secs(30);
const MAX_RESPONSE_BYTES: usize = 8_000_000;
const MAX_STREAM_EVENT_BYTES: usize = 1_000_000;

/// Server-sent events from a runtime, bounded to `MAX_RESPONSE_BYTES` in total.
pub(super) type RuntimeEvents =
    Pin<Box<dyn Stream<Item = Result<Event, EventStreamError<RuntimeFailure>>> + Send>>;

#[derive(Clone)]
pub struct SglangClient {
    client: reqwest::Client,
    api_key: Option<Arc<str>>,
    tokenizer: Option<ModelTokenizer>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RuntimeTlsConfig {
    pub(super) ca_certificate_path: PathBuf,
    pub(super) client_certificate_path: PathBuf,
    pub(super) client_key_path: PathBuf,
}

impl RuntimeTlsConfig {
    pub fn from_environment() -> Result<Option<Self>, RuntimeClientError> {
        Self::from_paths(
            environment_path("SGLANG_TLS_CA_CERT_PATH"),
            environment_path("SGLANG_TLS_CLIENT_CERT_PATH"),
            environment_path("SGLANG_TLS_CLIENT_KEY_PATH"),
        )
    }

    pub(super) fn from_paths(
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
        Ok(Self {
            client: build_http_client(tls)?,
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
            let request = self.authorized(self.client.get(endpoint(deployment, "health")));
            let response = request.send().await?;
            if !response.status().is_success() {
                return Err(RuntimeHealthError::UnhealthyStatus(response.status()));
            }
        }

        Ok(())
    }

    /// A JSON POST to one of the deployment's endpoints.
    pub(super) fn post(
        &self,
        deployment: &GatewayModelDeployment,
        path: &str,
        body: impl Into<reqwest::Body>,
    ) -> RequestBuilder {
        let request = self
            .client
            .post(endpoint(deployment, path))
            .header(header::CONTENT_TYPE, "application/json")
            .body(body);

        self.authorized(request)
    }

    /// The tokenizer that native token transport depends on. A client built
    /// without one cannot serve those releases.
    pub(super) fn tokenizer(&self) -> Result<&ModelTokenizer, RuntimeFailure> {
        self.tokenizer
            .as_ref()
            .ok_or_else(RuntimeFailure::protocol_violation)
    }

    fn authorized(&self, request: RequestBuilder) -> RequestBuilder {
        match &self.api_key {
            Some(api_key) => request.bearer_auth(api_key),
            None => request,
        }
    }

    /// Each request speaks exactly one protocol. A decision goes to a SystemOne
    /// release; chat goes to native token transport or to the chat endpoint.
    async fn dispatch_complete(
        &self,
        deployment: &GatewayModelDeployment,
        request: InferenceRequest,
        effective_output_tokens: u64,
        response_header_timeout: Duration,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        let system_one = deployment.release.is_system_one();

        if request.decision.is_some() {
            if !system_one || request.stream || effective_output_tokens != 0 {
                return Err(RuntimeFailure::protocol_violation());
            }

            return self
                .complete_system_one(deployment, request, response_header_timeout)
                .await;
        }

        if system_one || request.stream || effective_output_tokens == 0 {
            return Err(RuntimeFailure::protocol_violation());
        }

        if deployment.release.sends_token_ids() {
            self.complete_native(
                deployment,
                request,
                effective_output_tokens,
                response_header_timeout,
            )
            .await
        } else {
            self.complete_chat(
                deployment,
                request,
                effective_output_tokens,
                response_header_timeout,
            )
            .await
        }
    }

    async fn dispatch_stream(
        &self,
        deployment: &GatewayModelDeployment,
        request: InferenceRequest,
        effective_output_tokens: u64,
        response_header_timeout: Duration,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        if request.decision.is_some()
            || deployment.release.is_system_one()
            || !request.stream
            || effective_output_tokens == 0
        {
            return Err(RuntimeFailure::protocol_violation());
        }

        if deployment.release.sends_token_ids() {
            self.stream_native(
                deployment,
                request,
                effective_output_tokens,
                response_header_timeout,
            )
            .await
        } else {
            self.stream_chat(
                deployment,
                request,
                effective_output_tokens,
                response_header_timeout,
            )
            .await
        }
    }

    async fn complete_system_one(
        &self,
        deployment: &GatewayModelDeployment,
        request: InferenceRequest,
        response_header_timeout: Duration,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        let decision = request
            .decision
            .as_ref()
            .ok_or_else(RuntimeFailure::protocol_violation)?;
        let runtime_model = deployment
            .release
            .runtime_model_name
            .as_deref()
            .unwrap_or(&request.model);
        let body = serde_json::to_vec(&serde_json::json!({
            "model": runtime_model,
            "state": decision.state,
            "questions": decision.questions,
            "priority": request.service_tier.runtime_priority(),
        }))
        .map_err(|_| RuntimeFailure::protocol_violation())?;

        let upstream = self.post(deployment, "v1/systemone", body);
        let response = send(upstream, response_header_timeout).await?;
        let status = response.status();
        if !status.is_success() {
            return Err(RuntimeFailure::rejected(status, NormalizedUsage::zero()));
        }

        let body = read_bounded_body(response).await?;
        let (response, usage) =
            crate::systemone::normalize_response(&body, decision, runtime_model)?;

        Ok(RuntimeCompletion {
            response,
            usage,
            finish_reason: "stop".to_owned(),
        })
    }
}

#[async_trait]
impl ModelRuntime for SglangClient {
    async fn complete(
        &self,
        deployment: &GatewayModelDeployment,
        request: InferenceRequest,
        effective_output_tokens: u64,
        request_deadline: DateTime<Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        let remaining = remaining_until(request_deadline)?;
        let dispatch =
            self.dispatch_complete(deployment, request, effective_output_tokens, remaining);

        tokio::time::timeout(remaining, dispatch)
            .await
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?
    }

    /// Only opening the stream is bounded here. The caller holds the deadline for
    /// the events that follow.
    async fn stream(
        &self,
        deployment: &GatewayModelDeployment,
        request: InferenceRequest,
        effective_output_tokens: u64,
        request_deadline: DateTime<Utc>,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        let remaining = remaining_until(request_deadline)?;

        self.dispatch_stream(deployment, request, effective_output_tokens, remaining)
            .await
    }
}

fn remaining_until(deadline: DateTime<Utc>) -> Result<Duration, RuntimeFailure> {
    deadline
        .signed_duration_since(Utc::now())
        .to_std()
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))
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

fn endpoint(deployment: &GatewayModelDeployment, path: &str) -> String {
    format!("{}/{}", deployment.service_url.trim_end_matches('/'), path)
}

/// Sends a request body as a single chunk without a `Content-Length`, which
/// SGLang accepts for its chat endpoint.
pub(super) fn one_shot_body(body: Vec<u8>) -> reqwest::Body {
    reqwest::Body::wrap_stream(stream::once(async move {
        Result::<Vec<u8>, Infallible>::Ok(body)
    }))
}

/// Sends a request and waits at most `timeout` for the response headers.
pub(super) async fn send(
    request: RequestBuilder,
    timeout: Duration,
) -> Result<Response, RuntimeFailure> {
    tokio::time::timeout(timeout, request.send())
        .await
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?
        .map_err(RuntimeFailure::from_transport)
}

/// Reads a whole response body, failing past `MAX_RESPONSE_BYTES` or after
/// `RESPONSE_IDLE_TIMEOUT` without a chunk.
pub(super) async fn read_bounded_body(mut response: Response) -> Result<Vec<u8>, RuntimeFailure> {
    let declared = response.content_length();
    if declared.is_some_and(|length| length > MAX_RESPONSE_BYTES as u64) {
        return Err(RuntimeFailure::new(RuntimeFailureKind::ResponseTooLarge));
    }

    let mut body = Vec::with_capacity(declared.unwrap_or(0) as usize);
    loop {
        let chunk = tokio::time::timeout(RESPONSE_IDLE_TIMEOUT, response.chunk())
            .await
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?
            .map_err(RuntimeFailure::from_transport)?;
        let Some(chunk) = chunk else {
            return Ok(body);
        };

        if body.len().saturating_add(chunk.len()) > MAX_RESPONSE_BYTES {
            return Err(RuntimeFailure::new(RuntimeFailureKind::ResponseTooLarge));
        }

        body.extend_from_slice(&chunk);
    }
}

/// Turns a successful streaming response into server-sent events.
pub(super) fn open_events(response: Response) -> Result<RuntimeEvents, RuntimeFailure> {
    let event_stream = response
        .headers()
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .is_some_and(|value| value.starts_with("text/event-stream"));
    if !event_stream {
        return Err(RuntimeFailure::protocol_violation());
    }

    let events = response
        .bytes_stream()
        .map(|result| result.map_err(RuntimeFailure::from_transport))
        .scan(0_usize, |total, result| {
            let result = result.and_then(|bytes| {
                *total = total.saturating_add(bytes.len());
                if *total > MAX_RESPONSE_BYTES {
                    return Err(RuntimeFailure::new(RuntimeFailureKind::ResponseTooLarge));
                }

                Ok(bytes)
            });
            std::future::ready(Some(result))
        })
        .eventsource();

    Ok(Box::pin(events))
}

/// Returns the data of the next event, or `None` when the stream has ended.
/// Runtimes send only unnamed events without IDs or retry hints.
pub(super) async fn next_message(
    events: &mut RuntimeEvents,
) -> Result<Option<String>, RuntimeFailure> {
    let event = tokio::time::timeout(RESPONSE_IDLE_TIMEOUT, events.next())
        .await
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?;
    let Some(event) = event else {
        return Ok(None);
    };

    let event = event.map_err(|error| match error {
        EventStreamError::Transport(failure) => failure,
        EventStreamError::Utf8(_) | EventStreamError::Parser(_) => {
            RuntimeFailure::protocol_violation()
        }
    })?;
    if event.event != "message"
        || !event.id.is_empty()
        || event.retry.is_some()
        || event.data.len() > MAX_STREAM_EVENT_BYTES
    {
        return Err(RuntimeFailure::protocol_violation());
    }

    Ok(Some(event.data))
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
