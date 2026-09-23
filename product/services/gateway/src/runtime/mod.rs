//! The boundary between the gateway and a model runtime. `SglangClient` is the
//! production implementation; tests replace it through `ModelRuntime`.

mod chat;
mod client;
mod native;

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use reqwest::StatusCode;
use serde_json::Value;
use thiserror::Error;
use uuid::Uuid;

use crate::{GatewayError, GatewayModelDeployment, InferenceRequest, NormalizedUsage};

pub use client::{RuntimeClientError, RuntimeHealthError, RuntimeTlsConfig, SglangClient};

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
        Err(RuntimeFailure::protocol_violation())
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

/// One normalized chunk and the counters the gateway settles from.
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
    upstream_status: Option<u16>,
    transport: Option<&'static str>,
}

impl RuntimeFailure {
    pub fn new(kind: RuntimeFailureKind) -> Self {
        Self {
            kind,
            usage: NormalizedUsage::zero(),
            upstream_status: None,
            transport: None,
        }
    }

    /// The runtime answered with something the gateway cannot trust.
    pub fn protocol_violation() -> Self {
        Self::new(RuntimeFailureKind::ProtocolViolation)
    }

    pub(crate) fn with_usage(kind: RuntimeFailureKind, usage: NormalizedUsage) -> Self {
        Self {
            usage,
            ..Self::new(kind)
        }
    }

    /// A non-success upstream status, classified by `failure_kind_for_status`.
    fn rejected(status: StatusCode, usage: NormalizedUsage) -> Self {
        Self {
            upstream_status: Some(status.as_u16()),
            ..Self::with_usage(failure_kind_for_status(status), usage)
        }
    }

    fn from_transport(error: reqwest::Error) -> Self {
        // Never retain the error: its display/debug representation may include a private URL.
        let transport = if error.is_timeout() {
            "timeout"
        } else if error.is_connect() {
            "connect"
        } else if error.is_body() {
            "body"
        } else if error.is_decode() {
            "decode"
        } else {
            "transport"
        };

        Self {
            transport: Some(transport),
            ..Self::new(RuntimeFailureKind::Unavailable)
        }
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
            upstream_status = self.upstream_status, transport = self.transport,
            "runtime attempt failed");
    }

    pub(crate) fn transport_code(&self) -> Option<&'static str> {
        self.transport
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

/// Maps an upstream status to a failure kind.
///
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
