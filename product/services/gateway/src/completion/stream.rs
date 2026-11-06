use std::time::Duration;

use chrono::{DateTime, Utc};
use tokio::sync::{mpsc, watch};

use super::{
    dispatch::{RuntimeCall, Target},
    settlement::{Delivery, GenerationEnd, GenerationTerminal, Unsuccessful},
    tasks::force_shutdown_requested,
};
use crate::{
    generation::FinishReason, metrics::Capacity, protocol::StreamItem, CancellationOwner,
    GatewayError, NormalizedUsage, RuntimeEventStream, RuntimeFailure, RuntimeFailureKind,
    RuntimeStreamChunk, RuntimeStreamEvent,
};

/// OpenRouter sends its usage frame right after the finish reason.
const FINAL_USAGE_GRACE: Duration = Duration::from_secs(2);

pub(super) struct StreamProgress {
    usage: NormalizedUsage,
    finish_reason: Option<String>,
    terminal_usage_seen: bool,
    pub(super) terminal_response: Option<serde_json::Value>,
    first_token_at: Option<DateTime<Utc>>,
    frame_delivered: bool,
    upstream_cost_nano_usd: Option<u64>,
}

impl StreamProgress {
    pub(super) fn new() -> Self {
        Self {
            usage: NormalizedUsage::zero(),
            finish_reason: None,
            terminal_usage_seen: false,
            terminal_response: None,
            first_token_at: None,
            frame_delivered: false,
            upstream_cost_nano_usd: None,
        }
    }

    pub(super) async fn relay(
        &mut self,
        runtime_stream: &mut Box<dyn RuntimeEventStream>,
        events: &mpsc::Sender<StreamItem>,
        shutdown: &mut watch::Receiver<bool>,
        deadline: DateTime<Utc>,
    ) -> StreamStop {
        let deadline = tokio::time::sleep_until(tokio_instant(deadline));
        tokio::pin!(deadline);

        loop {
            let event = tokio::select! {
                _ = events.closed() => return StreamStop::ClientGone,
                _ = &mut deadline => return StreamStop::Deadline,
                _ = force_shutdown_requested(shutdown) => return StreamStop::Shutdown,
                event = runtime_stream.next_event() => event,
            };

            let chunk = match event {
                Ok(Some(RuntimeStreamEvent::Chunk(chunk))) => chunk,
                Ok(Some(RuntimeStreamEvent::Done)) => return self.finish(),
                Ok(None) => return StreamStop::Incomplete,
                Err(failure) => {
                    self.observe_failure(&failure);
                    return StreamStop::RuntimeFailed(failure);
                }
            };

            if let Err(stop) = self.observe(&chunk) {
                return stop;
            }

            if chunk.is_terminal_usage() {
                self.terminal_response = Some(chunk.into_response());
                continue;
            }

            let usable_output = chunk.has_usable_output();
            tokio::select! {
                result = events.send(StreamItem::Chunk(chunk.into_response())) => {
                    if result.is_err() {
                        return StreamStop::ClientGone;
                    }
                }
                _ = &mut deadline => return StreamStop::Deadline,
                _ = force_shutdown_requested(shutdown) => return StreamStop::Shutdown,
            }

            self.delivered(usable_output);
        }
    }

    /// Billing takes the last reported usage, so usage must never move backwards.
    fn observe(&mut self, chunk: &RuntimeStreamChunk) -> Result<(), StreamStop> {
        if let Some(usage) = chunk.usage() {
            if !usage_is_monotonic(self.usage, usage) {
                return Err(StreamStop::InvalidUsage);
            }

            self.usage = usage;
        }

        if let Some(reason) = chunk.finish_reason() {
            self.finish_reason = Some(reason.to_owned());
        }

        self.terminal_usage_seen |= chunk.is_terminal_usage();
        if let Some(cost) = chunk.upstream_cost_nano_usd() {
            self.upstream_cost_nano_usd = Some(cost);
        }

        Ok(())
    }

    /// OpenRouter reports usage only in its final frame, so a caller that leaves
    /// after the finish reason, holding its answer, is still billed for it.
    pub(super) async fn collect_final_usage(
        &mut self,
        runtime_stream: &mut Box<dyn RuntimeEventStream>,
    ) {
        if self.finish_reason.is_none() || self.terminal_usage_seen {
            return;
        }

        let collect = async {
            while let Ok(Some(RuntimeStreamEvent::Chunk(chunk))) = runtime_stream.next_event().await
            {
                if self.observe(&chunk).is_err() || chunk.is_terminal_usage() {
                    return;
                }
            }
        };
        let _ = tokio::time::timeout(FINAL_USAGE_GRACE, collect).await;
    }

    fn observe_failure(&mut self, failure: &RuntimeFailure) {
        let usage = failure.usage();
        if usage != NormalizedUsage::zero() && usage_is_monotonic(self.usage, usage) {
            self.usage = usage;
        }
    }

    fn delivered(&mut self, usable_output: bool) {
        self.frame_delivered = true;
        if usable_output {
            self.first_token_at.get_or_insert_with(Utc::now);
        }
    }

    pub(super) fn can_retry_before_any_frame(&self) -> bool {
        !self.frame_delivered
            && self.usage == NormalizedUsage::zero()
            && self.finish_reason.is_none()
            && !self.terminal_usage_seen
    }

    pub(super) fn into_terminal(self, stop: StreamStop) -> GenerationTerminal {
        GenerationTerminal {
            delivery: self.delivery(),
            end: stop.into_end(),
            usage: self.usage,
            upstream_cost_nano_usd: self.upstream_cost_nano_usd,
        }
    }

    fn delivery(&self) -> Delivery {
        match self.first_token_at {
            Some(first_token_at) => Delivery::Streamed { first_token_at },
            None => Delivery::NoOutput,
        }
    }

    fn finish(&mut self) -> StreamStop {
        match self.finish_reason.take() {
            Some(reason) if self.terminal_usage_seen => FinishReason::parse(reason)
                .map_or(StreamStop::InvalidFinishReason, StreamStop::Finished),
            _ => StreamStop::Incomplete,
        }
    }
}

pub(super) enum StreamStop {
    Finished(FinishReason),
    ClientGone,
    Deadline,
    Shutdown,
    InvalidUsage,
    InvalidFinishReason,
    Incomplete,
    RuntimeFailed(RuntimeFailure),
    Panicked,
}

impl StreamStop {
    /// Moves the call to its next capacity, logging the failed attempt, unless a
    /// frame already reached the caller.
    pub(super) fn fall_back(
        &self,
        call: &mut RuntimeCall,
        progress: &StreamProgress,
        attempt_started: std::time::Instant,
        started_at: DateTime<Utc>,
    ) -> bool {
        let Some(kind) = self.failure_kind() else {
            return false;
        };
        if progress.frame_delivered {
            return false;
        }

        let failed = call.plan.target.clone();
        let refused =
            kind == RuntimeFailureKind::CapacityExceeded && progress.can_retry_before_any_frame();
        let Some(next) = call.fall_back(kind, refused) else {
            return false;
        };

        match self {
            Self::RuntimeFailed(failure) => failure.log_attempt(
                call.generation_id,
                &call.request.model,
                failed.deployment_id(),
                failed.capacity().as_str(),
                call.attempts,
                attempt_started.elapsed().as_millis() as u64,
                Some(next.as_str()),
            ),
            _ => self.warn_if_abnormal(call, &failed, progress, started_at, Some(next)),
        }

        true
    }

    fn failure_kind(&self) -> Option<RuntimeFailureKind> {
        match self {
            Self::RuntimeFailed(failure) => Some(failure.kind()),
            Self::InvalidUsage | Self::InvalidFinishReason | Self::Incomplete | Self::Panicked => {
                Some(RuntimeFailureKind::ProtocolViolation)
            }
            Self::Finished(_) | Self::ClientGone | Self::Deadline | Self::Shutdown => None,
        }
    }

    pub(super) fn warn_if_abnormal(
        &self,
        call: &RuntimeCall,
        target: &Target,
        progress: &StreamProgress,
        started_at: DateTime<Utc>,
        next: Option<Capacity>,
    ) {
        let Some(reason) = self.abnormal_reason() else {
            return;
        };

        let failure = match self {
            Self::RuntimeFailed(failure) => Some(failure),
            _ => None,
        };
        crate::diagnostics::limited_warn!(generation_id = %call.generation_id,
            model_id = %call.request.model,
            deployment_id = target.deployment_id().map(tracing::field::display),
            capacity = target.capacity().as_str(),
            next_capacity = next.map(Capacity::as_str),
            phase = "stream", reason,
            failure_kind = ?failure.map(RuntimeFailure::kind),
            transport = failure.and_then(RuntimeFailure::transport_code),
            diagnostic_code = failure.map(RuntimeFailure::diagnostic_code),
            usable_output_delivered = progress.first_token_at.is_some(),
            elapsed_ms = (Utc::now() - started_at).num_milliseconds().max(0),
            "generation stream terminated abnormally");
    }

    fn abnormal_reason(&self) -> Option<&'static str> {
        match self {
            // The panic boundary logs a panic where it catches it.
            Self::Finished(_) | Self::ClientGone | Self::Panicked => None,
            Self::Deadline => Some("deadline"),
            Self::Shutdown => Some("shutdown"),
            Self::InvalidUsage => Some("invalid_usage"),
            Self::InvalidFinishReason => Some("invalid_finish_reason"),
            Self::Incomplete => Some("incomplete_stream"),
            Self::RuntimeFailed(_) => Some("runtime_failure"),
        }
    }

    fn into_end(self) -> GenerationEnd {
        match self {
            Self::Finished(reason) => GenerationEnd::Succeeded(reason),
            Self::ClientGone => GenerationEnd::cancelled(CancellationOwner::Client),
            Self::Deadline | Self::Shutdown => GenerationEnd::cancelled(CancellationOwner::Server),
            Self::InvalidUsage | Self::InvalidFinishReason | Self::Incomplete | Self::Panicked => {
                GenerationEnd::failed(GatewayError::RuntimeUnavailable)
            }
            Self::RuntimeFailed(failure) => {
                GenerationEnd::Unsuccessful(Unsuccessful::from_runtime_failure(&failure))
            }
        }
    }
}

fn tokio_instant(deadline: DateTime<Utc>) -> tokio::time::Instant {
    let remaining = deadline
        .signed_duration_since(Utc::now())
        .to_std()
        .unwrap_or_default();

    tokio::time::Instant::now() + remaining
}

fn usage_is_monotonic(previous: NormalizedUsage, next: NormalizedUsage) -> bool {
    (previous == NormalizedUsage::zero() || previous.input_tokens() == next.input_tokens())
        && previous.cached_input_tokens() <= next.cached_input_tokens()
        && previous.cache_write_tokens() <= next.cache_write_tokens()
        && previous.output_tokens() <= next.output_tokens()
        && previous.reasoning_tokens() <= next.reasoning_tokens()
}
