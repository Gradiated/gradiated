use std::{
    convert::Infallible,
    fs,
    future::Future,
    path::{Path, PathBuf},
    pin::Pin,
    sync::Arc,
    time::Duration,
};

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use eventsource_stream::{Event, EventStreamError, Eventsource};
use futures_util::{stream, Stream, StreamExt};
use reqwest::{header, redirect::Policy, Certificate, Identity, RequestBuilder, Response};
use thiserror::Error;

use super::{
    progress::{ProgressStream, RESPONSE_IDLE_TIMEOUT},
    FailureCause, ModelRuntime, ProtocolViolation, RuntimeCompletion, RuntimeEventStream,
    RuntimeFailure,
};
use crate::{
    systemone::SystemOneRequest, GatewayModelDeployment, InferenceRequest, ModelDeploymentRelease,
    ModelTokenizer,
};

pub(super) const CONNECT_TIMEOUT: Duration = Duration::from_secs(5);
const MAX_RESPONSE_BYTES: usize = 8_000_000;
const MAX_STREAM_EVENT_BYTES: usize = 1_000_000;

pub(super) type RuntimeEvents =
    Pin<Box<dyn Stream<Item = Result<Event, EventStreamError<RuntimeFailure>>> + Send>>;

#[derive(Clone)]
pub struct SglangClient {
    client: reqwest::Client,
    api_key: Option<Arc<str>>,
    pub(super) tokenizer: ModelTokenizer,
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
    pub fn with_tokenizer_and_tls(
        api_key: Option<String>,
        tokenizer: ModelTokenizer,
        tls: Option<&RuntimeTlsConfig>,
    ) -> Result<Self, RuntimeClientError> {
        Ok(Self {
            client: build_http_client(tls)?,
            api_key: api_key.map(Arc::from),
            tokenizer,
        })
    }

    pub(super) fn post(
        &self,
        deployment: &GatewayModelDeployment,
        path: &str,
        body: impl Into<reqwest::Body>,
    ) -> RequestBuilder {
        let body = body.into();
        if let Some(bytes) = body.as_bytes() {
            crate::diagnostics::body::record("runtime_request", bytes, None);
        }

        let request = self
            .client
            .post(endpoint(deployment, path))
            .header(header::CONTENT_TYPE, "application/json")
            .body(body);

        self.authorized(request)
    }

    fn authorized(&self, request: RequestBuilder) -> RequestBuilder {
        match &self.api_key {
            Some(api_key) => request.bearer_auth(api_key),
            None => request,
        }
    }
}

/// Kimi releases built before the runtime capped output with
/// `SGLANG_MAX_NEW_TOKENS_LIMIT`. Without a limit they would decode toward the
/// whole remaining context, so they keep receiving the explicit default.
const UNCAPPED_RUNTIME_REVISIONS: [&str; 1] = ["kimi-k31-d25d7c28cd76"];

pub(super) struct Call<'a> {
    pub(super) deployment: &'a GatewayModelDeployment,
    pub(super) request: InferenceRequest,
    pub(super) output_tokens: u64,
}

enum Transport {
    Chat,
    Native(Vec<u32>),
    SystemOne(Box<SystemOneRequest>),
}

impl<'a> Call<'a> {
    fn route(
        deployment: &'a GatewayModelDeployment,
        mut request: InferenceRequest,
        output_tokens: u64,
        streaming: bool,
    ) -> Result<(Transport, Self), RuntimeFailure> {
        let transport = Transport::select(&deployment.release, &mut request, output_tokens)?;
        if UNCAPPED_RUNTIME_REVISIONS.contains(&deployment.release.runtime_revision.as_str()) {
            request.open_output_limit = false;
        }
        if request.stream != streaming {
            return Err(ProtocolViolation::Dispatch.into());
        }

        let call = Self {
            deployment,
            request,
            output_tokens,
        };

        Ok((transport, call))
    }
}

impl Transport {
    fn select(
        release: &ModelDeploymentRelease,
        request: &mut InferenceRequest,
        output_tokens: u64,
    ) -> Result<Self, RuntimeFailure> {
        match request.decision.take() {
            Some(decision) if release.is_system_one() && output_tokens == 0 => {
                Ok(Self::SystemOne(Box::new(decision)))
            }
            None if !release.is_system_one() && output_tokens > 0 => {
                if !release.sends_token_ids() {
                    return Ok(Self::Chat);
                }

                request
                    .encoded_input_ids
                    .take()
                    .map(Self::Native)
                    .ok_or_else(|| ProtocolViolation::Dispatch.into())
            }
            _ => Err(ProtocolViolation::Dispatch.into()),
        }
    }
}

pub(super) struct ModelNames {
    pub(super) requested: String,
    pub(super) runtime: String,
}

impl ModelNames {
    pub(super) fn new(call: &Call<'_>) -> Self {
        let requested = call.request.model.clone();
        let runtime = call
            .request
            .runtime_model_name
            .clone()
            .or_else(|| call.deployment.release.runtime_model_name.clone())
            .unwrap_or_else(|| requested.clone());

        Self { requested, runtime }
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
        let (transport, call) = Call::route(deployment, request, effective_output_tokens, false)?;

        within(remaining, async move {
            match transport {
                Transport::Chat => self.complete_chat(call).await,
                Transport::Native(input_ids) => self.complete_native(call, &input_ids).await,
                Transport::SystemOne(decision) => self.complete_system_one(call, &decision).await,
            }
        })
        .await
    }

    async fn stream(
        &self,
        deployment: &GatewayModelDeployment,
        request: InferenceRequest,
        effective_output_tokens: u64,
        request_deadline: DateTime<Utc>,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        let remaining = remaining_until(request_deadline)?;
        let deadline = tokio::time::Instant::now() + remaining;
        let (transport, call) = Call::route(deployment, request, effective_output_tokens, true)?;

        within(remaining, async move {
            match transport {
                Transport::Chat => self.stream_chat(call).await,
                Transport::Native(input_ids) => self.stream_native(call, &input_ids).await,
                Transport::SystemOne(_) => Err(ProtocolViolation::Dispatch.into()),
            }
        })
        .await
        .map(|inner| {
            Box::new(ProgressStream::new(inner, deadline)) as Box<dyn super::RuntimeEventStream>
        })
    }
}

pub(super) fn remaining_until(deadline: DateTime<Utc>) -> Result<Duration, RuntimeFailure> {
    deadline
        .signed_duration_since(Utc::now())
        .to_std()
        .map_err(|_| RuntimeFailure::deadline())
}

pub(super) async fn within<T>(
    remaining: Duration,
    dispatch: impl Future<Output = Result<T, RuntimeFailure>>,
) -> Result<T, RuntimeFailure> {
    tokio::time::timeout(remaining, dispatch)
        .await
        .map_err(|_| RuntimeFailure::deadline())?
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

fn read_tls_file(path: &Path) -> Result<Vec<u8>, RuntimeClientError> {
    fs::read(path).map_err(|source| RuntimeClientError::TlsFile {
        path: path.to_owned(),
        source,
    })
}

fn endpoint(deployment: &GatewayModelDeployment, path: &str) -> String {
    format!("{}/{}", deployment.service_url.trim_end_matches('/'), path)
}

/// A streamed body has no bytes the HTTP client could replay, so the client
/// never sends a prompt twice.
pub(super) fn one_shot_body(body: Vec<u8>) -> reqwest::Body {
    reqwest::Body::wrap_stream(stream::once(async move {
        Result::<Vec<u8>, Infallible>::Ok(body)
    }))
}

pub(super) async fn send(request: RequestBuilder) -> Result<Response, RuntimeFailure> {
    request.send().await.map_err(RuntimeFailure::from_transport)
}

pub(super) async fn rejected_response(response: Response) -> RuntimeFailure {
    let status = record_rejection(response).await;

    RuntimeFailure::rejected(status, crate::NormalizedUsage::zero())
}

pub(super) async fn record_rejection(mut response: Response) -> reqwest::StatusCode {
    let status = response.status();
    if tracing::enabled!(tracing::Level::INFO) {
        let read = async {
            let mut body = Vec::new();
            while let Ok(Some(chunk)) = response.chunk().await {
                if body.len() + chunk.len() > 65_536 {
                    return;
                }

                body.extend_from_slice(&chunk);
            }
            crate::diagnostics::body::record("runtime_response", &body, Some(status.as_u16()));
        };
        // Diagnostics must not hold up a capacity retry for an unresponsive error body.
        let _ = tokio::time::timeout(Duration::from_millis(250), read).await;
    }

    status
}

pub(super) async fn read_bounded_body(response: Response) -> Result<Vec<u8>, RuntimeFailure> {
    read_body(response, false).await
}

pub(super) async fn read_completion_body(response: Response) -> Result<Vec<u8>, RuntimeFailure> {
    read_body(response, true).await
}

async fn read_body(mut response: Response, allow_prefill: bool) -> Result<Vec<u8>, RuntimeFailure> {
    let status = response.status().as_u16();
    let declared = response.content_length();
    if declared.is_some_and(|length| length > MAX_RESPONSE_BYTES as u64) {
        return Err(RuntimeFailure::too_large(FailureCause::DeclaredTooLarge));
    }

    let mut body = Vec::with_capacity(declared.unwrap_or(0) as usize);
    loop {
        // OpenRouter pads a buffered response with whitespace while it waits for
        // the model, so the response is still in prefill until its first JSON byte.
        let chunk = if allow_prefill && body.iter().all(u8::is_ascii_whitespace) {
            response.chunk().await
        } else {
            tokio::time::timeout(RESPONSE_IDLE_TIMEOUT, response.chunk())
                .await
                .map_err(|_| RuntimeFailure::idle())?
        }
        .map_err(RuntimeFailure::interrupted)?;
        let Some(chunk) = chunk else {
            crate::diagnostics::body::record("runtime_response", &body, Some(status));
            return Ok(body);
        };

        if body.len().saturating_add(chunk.len()) > MAX_RESPONSE_BYTES {
            return Err(RuntimeFailure::too_large(FailureCause::StreamedTooLarge));
        }

        body.extend_from_slice(&chunk);
    }
}

pub(super) fn open_events(response: Response) -> Result<RuntimeEvents, RuntimeFailure> {
    let event_stream = response
        .headers()
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .is_some_and(|value| value.starts_with("text/event-stream"));
    if !event_stream {
        return Err(ProtocolViolation::ContentType.into());
    }

    let events = response
        .bytes_stream()
        .map(|result| result.map_err(RuntimeFailure::interrupted))
        .eventsource();

    Ok(Box::pin(events))
}

/// Runtimes send only unnamed events without IDs or retry hints.
pub(super) async fn next_message(
    events: &mut RuntimeEvents,
) -> Result<Option<String>, RuntimeFailure> {
    let event = events.next().await;
    let Some(event) = event else {
        return Ok(None);
    };

    let event = event.map_err(|error| match error {
        EventStreamError::Transport(failure) => failure,
        EventStreamError::Utf8(_) | EventStreamError::Parser(_) => {
            ProtocolViolation::SseFraming.into()
        }
    })?;
    if event.event != "message"
        || !event.id.is_empty()
        || event.retry.is_some()
        || event.data.len() > MAX_STREAM_EVENT_BYTES
    {
        return Err(ProtocolViolation::SseFraming.into());
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
