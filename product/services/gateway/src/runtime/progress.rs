use std::time::Duration;

use async_trait::async_trait;
use tokio::time::Instant;

use super::{RuntimeEventStream, RuntimeFailure, RuntimeStreamEvent};
use crate::NormalizedUsage;

pub(super) const RESPONSE_IDLE_TIMEOUT: Duration = Duration::from_secs(30);

pub(super) struct ProgressStream {
    inner: Box<dyn RuntimeEventStream>,
    deadline: Instant,
    output_started: bool,
    usage: NormalizedUsage,
    closed: bool,
}

impl ProgressStream {
    pub(super) fn new(inner: Box<dyn RuntimeEventStream>, deadline: Instant) -> Self {
        Self {
            inner,
            deadline,
            output_started: false,
            usage: NormalizedUsage::zero(),
            closed: false,
        }
    }
}

#[async_trait]
impl RuntimeEventStream for ProgressStream {
    async fn next_event(&mut self) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure> {
        if self.closed {
            return Ok(None);
        }

        if Instant::now() >= self.deadline {
            self.closed = true;

            return Err(RuntimeFailure::deadline().or_usage(self.usage));
        }

        let idle = Instant::now() + RESPONSE_IDLE_TIMEOUT;
        let idle_expires_first = self.output_started && idle < self.deadline;
        let expires = if self.output_started {
            idle.min(self.deadline)
        } else {
            self.deadline
        };
        let event = match tokio::time::timeout_at(expires, self.inner.next_event()).await {
            Ok(event) => event,
            Err(_) => {
                self.closed = true;
                let failure = if idle_expires_first {
                    RuntimeFailure::idle()
                } else {
                    RuntimeFailure::deadline()
                };

                return Err(failure.or_usage(self.usage));
            }
        };

        match &event {
            Ok(Some(RuntimeStreamEvent::Chunk(chunk))) => {
                if let Some(usage) = chunk.usage() {
                    self.usage = usage;
                }
                if chunk.has_usable_output()
                    || chunk.finish_reason().is_some()
                    || chunk.is_terminal_usage()
                {
                    self.output_started = true;
                }
            }
            Ok(Some(RuntimeStreamEvent::Done)) | Ok(None) | Err(_) => self.closed = true,
        }

        event.map_err(|failure| failure.or_usage(self.usage))
    }
}
