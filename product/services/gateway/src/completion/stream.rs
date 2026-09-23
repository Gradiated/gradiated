use chrono::{DateTime, Utc};
use tokio::sync::{mpsc, watch};

use super::{
    dispatch::RuntimeCall,
    settlement::{Delivery, GenerationEnd, GenerationTerminal, Unsuccessful},
    tasks::force_shutdown_requested,
};
use crate::{
    generation::FinishReason, protocol::StreamItem, CancellationOwner, GatewayError,
    NormalizedUsage, RuntimeEventStream, RuntimeFailure, RuntimeStreamChunk, RuntimeStreamEvent,
};

pub(super) struct StreamProgress {
    usage: NormalizedUsage,
    finish_reason: Option<String>,
    terminal_usage_seen: bool,
    first_token_at: Option<DateTime<Utc>>,
}

impl StreamProgress {
    pub(super) fn new() -> Self {
        Self {
            usage: NormalizedUsage::zero(),
            finish_reason: None,
            terminal_usage_seen: false,
            first_token_at: None,
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

        Ok(())
    }

    fn observe_failure(&mut self, failure: &RuntimeFailure) {
        let usage = failure.usage();
        if usage != NormalizedUsage::zero() && usage_is_monotonic(self.usage, usage) {
            self.usage = usage;
        }
    }

    fn delivered(&mut self, usable_output: bool) {
        if usable_output {
            self.first_token_at.get_or_insert_with(Utc::now);
        }
    }

    pub(super) fn into_terminal(self, stop: StreamStop) -> GenerationTerminal {
        GenerationTerminal {
            delivery: self.delivery(),
            end: stop.into_end(),
            usage: self.usage,
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
    pub(super) fn warn_if_abnormal(
        &self,
        call: &RuntimeCall,
        progress: &StreamProgress,
        started_at: DateTime<Utc>,
    ) {
        let Some(reason) = self.abnormal_reason() else {
            return;
        };

        let failure = match self {
            Self::RuntimeFailed(failure) => Some(failure),
            _ => None,
        };
        crate::diagnostics::limited_warn!(generation_id = %call.generation_id,
            model_id = %call.request.model, deployment_id = %call.deployment.id,
            phase = "stream", reason,
            failure_kind = ?failure.map(RuntimeFailure::kind),
            transport = failure.and_then(RuntimeFailure::transport_code),
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
