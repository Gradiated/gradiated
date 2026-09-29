mod chat;
mod client;
mod native;
mod systemone;

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use reqwest::StatusCode;
use serde_json::Value;
use thiserror::Error;
use uuid::Uuid;

use crate::{GatewayError, GatewayModelDeployment, InferenceRequest, NormalizedUsage};

pub use client::{RuntimeClientError, RuntimeTlsConfig, SglangClient};

#[async_trait]
pub trait ModelRuntime: Send + Sync {
    async fn complete(
        &self,
        deployment: &GatewayModelDeployment,
        request: InferenceRequest,
        effective_output_tokens: u64,
        request_deadline: DateTime<Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure>;

    async fn stream(
        &self,
        _deployment: &GatewayModelDeployment,
        _request: InferenceRequest,
        _effective_output_tokens: u64,
        _request_deadline: DateTime<Utc>,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        Err(ProtocolViolation::Dispatch.into())
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
    finish_reason: Option<String>,
    usable_output: bool,
    usage: Option<ChunkUsage>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum ChunkUsage {
    Running(NormalizedUsage),
    Terminal(NormalizedUsage),
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
        debug_assert!(usage.is_some() || !terminal_usage);

        Self {
            response,
            finish_reason,
            usable_output,
            usage: usage.map(if terminal_usage {
                ChunkUsage::Terminal
            } else {
                ChunkUsage::Running
            }),
        }
    }

    pub fn into_response(self) -> Value {
        self.response
    }

    pub fn usage(&self) -> Option<NormalizedUsage> {
        match self.usage? {
            ChunkUsage::Running(usage) | ChunkUsage::Terminal(usage) => Some(usage),
        }
    }

    pub fn finish_reason(&self) -> Option<&str> {
        self.finish_reason.as_deref()
    }

    pub fn has_usable_output(&self) -> bool {
        self.usable_output
    }

    pub fn is_terminal_usage(&self) -> bool {
        matches!(self.usage, Some(ChunkUsage::Terminal(_)))
    }
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

    #[cfg(test)]
    pub(crate) fn response(&self) -> &Value {
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
    Interrupted,
}

#[derive(Clone, Debug, Error, Eq, PartialEq)]
#[error("model runtime failed: {kind:?}")]
pub struct RuntimeFailure {
    kind: RuntimeFailureKind,
    usage: NormalizedUsage,
    cause: FailureCause,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum FailureCause {
    Status(u16),
    Transport(TransportError),
    Protocol(ProtocolViolation),
    Tokenizer,
    Deadline,
    IdleTimeout,
    DeclaredTooLarge,
    StreamedTooLarge,
    Parameter(&'static str),
    #[cfg(test)]
    Scripted,
}

impl FailureCause {
    fn as_str(self) -> &'static str {
        match self {
            Self::Status(_) => "upstream_status",
            Self::Transport(error) => error.as_str(),
            Self::Protocol(violation) => violation.as_str(),
            Self::Tokenizer => "tokenizer",
            Self::Deadline => "deadline",
            Self::IdleTimeout => "idle_timeout",
            Self::DeclaredTooLarge => "declared_too_large",
            Self::StreamedTooLarge => "streamed_too_large",
            Self::Parameter(_) => "parameter",
            #[cfg(test)]
            Self::Scripted => "scripted",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum TransportError {
    Timeout,
    Connect,
    Body,
    Decode,
    Builder,
    IncompleteResponse,
    InvalidResponse,
    ConnectionClosed,
    ConnectionReset,
    Canceled,
    Http2GoAway,
    Http2Reset,
    Http2,
    Other,
}

impl TransportError {
    // Never retain the error: its display/debug representation may include a private URL.
    fn classify(error: &reqwest::Error) -> Self {
        if error.is_timeout() {
            return Self::Timeout;
        }
        if error.is_connect() {
            return Self::Connect;
        }

        let fallback = if error.is_body() {
            Self::Body
        } else if error.is_decode() {
            Self::Decode
        } else if error.is_builder() {
            Self::Builder
        } else {
            Self::Other
        };

        match Self::classify_source(error) {
            Self::Other => fallback,
            cause => cause,
        }
    }

    fn classify_source(error: &(dyn std::error::Error + 'static)) -> Self {
        let mut source = error.source();
        while let Some(error) = source {
            if let Some(error) = error.downcast_ref::<hyper::Error>() {
                if error.is_incomplete_message() {
                    return Self::IncompleteResponse;
                }
                if error.is_parse() {
                    return Self::InvalidResponse;
                }
                if error.is_canceled() {
                    return Self::Canceled;
                }
                if error.is_closed() {
                    return Self::ConnectionClosed;
                }
            }
            if let Some(error) = error.downcast_ref::<std::io::Error>() {
                match error.kind() {
                    std::io::ErrorKind::ConnectionReset => return Self::ConnectionReset,
                    std::io::ErrorKind::BrokenPipe | std::io::ErrorKind::UnexpectedEof => {
                        return Self::ConnectionClosed;
                    }
                    _ => {}
                }
            }
            if let Some(error) = error.downcast_ref::<h2::Error>() {
                if error.is_go_away() {
                    return Self::Http2GoAway;
                }
                if error.is_reset() {
                    return Self::Http2Reset;
                }
                if !error.is_io() {
                    return Self::Http2;
                }
            }

            source = error.source();
        }

        Self::Other
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Timeout => "timeout",
            Self::Connect => "connect",
            Self::Body => "body",
            Self::Decode => "decode",
            Self::Builder => "request_build",
            Self::IncompleteResponse => "incomplete_response",
            Self::InvalidResponse => "invalid_http_response",
            Self::ConnectionClosed => "connection_closed",
            Self::ConnectionReset => "connection_reset",
            Self::Canceled => "transport_canceled",
            Self::Http2GoAway => "http2_goaway",
            Self::Http2Reset => "http2_reset",
            Self::Http2 => "http2",
            Self::Other => "transport",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ProtocolViolation {
    Json,
    ResponseShape,
    ModelMismatch,
    Usage,
    StreamIdentity,
    FinishReason,
    TokenBounds,
    FrameOrder,
    SseFraming,
    ContentType,
    Dispatch,
    DecisionAnswer,
}

impl ProtocolViolation {
    fn as_str(self) -> &'static str {
        match self {
            Self::Json => "json",
            Self::ResponseShape => "response_shape",
            Self::ModelMismatch => "model_mismatch",
            Self::Usage => "usage",
            Self::StreamIdentity => "stream_identity",
            Self::FinishReason => "finish_reason",
            Self::TokenBounds => "token_bounds",
            Self::FrameOrder => "frame_order",
            Self::SseFraming => "sse_framing",
            Self::ContentType => "content_type",
            Self::Dispatch => "dispatch",
            Self::DecisionAnswer => "decision_answer",
        }
    }
}

impl From<ProtocolViolation> for RuntimeFailure {
    fn from(violation: ProtocolViolation) -> Self {
        Self::caused(
            RuntimeFailureKind::ProtocolViolation,
            FailureCause::Protocol(violation),
        )
    }
}

impl RuntimeFailure {
    #[cfg(test)]
    pub(crate) fn new(kind: RuntimeFailureKind) -> Self {
        Self::caused(kind, FailureCause::Scripted)
    }

    #[cfg(test)]
    pub(crate) fn protocol_violation() -> Self {
        ProtocolViolation::Dispatch.into()
    }

    #[cfg(test)]
    pub(crate) fn with_usage(kind: RuntimeFailureKind, usage: NormalizedUsage) -> Self {
        Self::new(kind).or_usage(usage)
    }

    fn caused(kind: RuntimeFailureKind, cause: FailureCause) -> Self {
        Self {
            kind,
            usage: NormalizedUsage::zero(),
            cause,
        }
    }

    fn rejected(status: StatusCode, usage: NormalizedUsage) -> Self {
        Self::caused(
            failure_kind_for_status(status),
            FailureCause::Status(status.as_u16()),
        )
        .or_usage(usage)
    }

    fn from_transport(error: reqwest::Error) -> Self {
        Self::transport(RuntimeFailureKind::Unavailable, &error)
    }

    fn interrupted(error: reqwest::Error) -> Self {
        Self::transport(RuntimeFailureKind::Interrupted, &error)
    }

    fn transport(kind: RuntimeFailureKind, error: &reqwest::Error) -> Self {
        Self::caused(
            kind,
            FailureCause::Transport(TransportError::classify(error)),
        )
    }

    fn tokenizer(kind: RuntimeFailureKind) -> Self {
        Self::caused(kind, FailureCause::Tokenizer)
    }

    fn deadline() -> Self {
        Self::caused(RuntimeFailureKind::TimedOut, FailureCause::Deadline)
    }

    fn idle() -> Self {
        Self::caused(RuntimeFailureKind::TimedOut, FailureCause::IdleTimeout)
    }

    fn too_large(cause: FailureCause) -> Self {
        Self::caused(RuntimeFailureKind::ResponseTooLarge, cause)
    }

    fn invalid_parameter(name: &'static str) -> Self {
        Self::caused(
            RuntimeFailureKind::InvalidRequest,
            FailureCause::Parameter(name),
        )
    }

    fn or_usage(mut self, usage: NormalizedUsage) -> Self {
        if self.usage == NormalizedUsage::zero() {
            self.usage = usage;
        }

        self
    }

    pub(crate) fn log_attempt(
        &self,
        generation_id: Uuid,
        model_id: &str,
        deployment_id: Uuid,
        attempt: u8,
        elapsed_ms: u64,
        retry_selected: bool,
    ) {
        crate::diagnostics::limited_warn!(%generation_id, model_id, %deployment_id, attempt, phase = "dispatch",
            elapsed_ms, retry_selected, failure_kind = ?self.kind,
            upstream_status = self.upstream_status(), diagnostic_code = self.diagnostic_code(),
            "runtime attempt failed");
    }

    pub(crate) fn diagnostic_code(&self) -> &'static str {
        self.cause.as_str()
    }

    pub(crate) fn transport_code(&self) -> Option<&'static str> {
        match self.cause {
            FailureCause::Transport(error) => Some(error.as_str()),
            _ => None,
        }
    }

    fn parameter(&self) -> Option<&'static str> {
        match self.cause {
            FailureCause::Parameter(name) => Some(name),
            _ => None,
        }
    }

    fn upstream_status(&self) -> Option<u16> {
        match self.cause {
            FailureCause::Status(status) => Some(status),
            _ => None,
        }
    }

    pub fn kind(&self) -> RuntimeFailureKind {
        self.kind
    }

    pub fn usage(&self) -> NormalizedUsage {
        self.usage
    }

    pub fn gateway_error(&self) -> GatewayError {
        match self.kind {
            RuntimeFailureKind::InvalidRequest => GatewayError::invalid_request(self.parameter()),
            RuntimeFailureKind::CapacityExceeded => GatewayError::CapacityExceeded,
            RuntimeFailureKind::Unavailable
            | RuntimeFailureKind::TimedOut
            | RuntimeFailureKind::ResponseTooLarge
            | RuntimeFailureKind::ProtocolViolation
            | RuntimeFailureKind::Interrupted => GatewayError::RuntimeUnavailable,
        }
    }
}

/// A vLLM `QueueOverflowError` or `MaxQueuedTokensError` rejects with HTTP 503
/// when the engine queue reaches `max_num_queued_reqs` or `max_num_queued_tokens`.
/// That rejection is admission backpressure, not an outage, so it must stay
/// retryable and must not surface as `runtime_unavailable`. Include 429 for
/// runtimes that reject excess load with `Too Many Requests`.
fn failure_kind_for_status(status: StatusCode) -> RuntimeFailureKind {
    match status {
        StatusCode::BAD_REQUEST | StatusCode::UNPROCESSABLE_ENTITY => {
            RuntimeFailureKind::InvalidRequest
        }
        StatusCode::TOO_MANY_REQUESTS | StatusCode::SERVICE_UNAVAILABLE => {
            RuntimeFailureKind::CapacityExceeded
        }
        _ => RuntimeFailureKind::Unavailable,
    }
}

#[cfg(test)]
mod tests;
