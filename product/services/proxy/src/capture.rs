use std::{sync::Arc, time::Duration};

use axum::{
    body::Bytes,
    http::{
        header::{CONTENT_ENCODING, CONTENT_TYPE},
        HeaderMap,
    },
};
use bytes::BytesMut;
use chrono::{DateTime, Utc};
use reqwest::Client;
use serde::Serialize;
use tokio::{
    sync::{mpsc, oneshot, OwnedSemaphorePermit, Semaphore},
    task::JoinHandle,
};
use uuid::Uuid;

use crate::{
    credentials::Provider,
    metrics::{CaptureResult, Metrics},
};

const SCHEMA: &str = "gradiated.relay/1";
const CAPTURED_CONTENT_TYPES: &[&str] = &["application/json", "text/event-stream"];
const MAX_GENERATION_BYTES: usize = 16 * 1024 * 1024;
const BATCH_BYTES: usize = 1024 * 1024;
const BATCH_WINDOW: Duration = Duration::from_millis(100);
const CONNECT_TIMEOUT: Duration = Duration::from_secs(1);
const POST_TIMEOUT: Duration = Duration::from_secs(5);
const RETRY_DELAY: Duration = Duration::from_millis(250);

#[derive(Clone, Debug)]
pub struct CaptureSettings {
    pub collector_url: String,
    pub collector_token: String,
    pub buffer_bytes: usize,
}

#[derive(Clone, Default)]
pub struct Capture {
    inner: Option<Arc<Inner>>,
}

struct Inner {
    queue: mpsc::UnboundedSender<Queued>,
    budget: Arc<Semaphore>,
    metrics: Metrics,
}

pub struct Relay {
    pub hosted: bool,
    pub generation_id: Uuid,
    pub workspace_id: Uuid,
    pub task: String,
    pub trace_id: Option<String>,
    pub session_id: Option<String>,
    pub provider: Provider,
    pub path: String,
    pub retention_days: i16,
    pub request: Bytes,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    Complete,
    Error,
    Cancelled,
}

struct Generation {
    relay: Relay,
    status: u16,
    content_type: String,
    response: BytesMut,
    budget: OwnedSemaphorePermit,
}

struct Queued {
    generation: Generation,
    outcome: Outcome,
    completed_at: DateTime<Utc>,
}

pub struct Recording {
    inner: Arc<Inner>,
    generation: Option<Generation>,
}

impl Capture {
    pub fn is_enabled(&self) -> bool {
        self.inner.is_some()
    }

    pub fn start(
        settings: CaptureSettings,
        metrics: Metrics,
    ) -> Result<(Self, Sender), reqwest::Error> {
        let client = Client::builder()
            .connect_timeout(CONNECT_TIMEOUT)
            .timeout(POST_TIMEOUT)
            .build()?;
        let (queue, receiver) = mpsc::unbounded_channel();
        let (stop, stopped) = oneshot::channel();

        let capture = Self {
            inner: Some(Arc::new(Inner {
                queue,
                budget: Arc::new(Semaphore::new(settings.buffer_bytes)),
                metrics: metrics.clone(),
            })),
        };
        let collector = Collector {
            client,
            url: settings.collector_url,
            token: settings.collector_token,
            metrics,
        };
        let task = tokio::spawn(collector.run(receiver, stopped));

        Ok((capture, Sender { stop, task }))
    }

    pub fn record(&self, relay: Relay, status: u16, headers: &HeaderMap) -> Option<Recording> {
        let inner = self.inner.as_ref()?;

        if headers.get_all(CONTENT_ENCODING).iter().any(|value| {
            !value
                .to_str()
                .is_ok_and(|value| value.trim().eq_ignore_ascii_case("identity"))
        }) {
            inner.metrics.record_captures(CaptureResult::Unsupported, 1);
            return None;
        }

        let content_type = headers
            .get(CONTENT_TYPE)
            .and_then(|value| value.to_str().ok())
            .filter(|value| {
                CAPTURED_CONTENT_TYPES
                    .iter()
                    .any(|captured| value.starts_with(captured))
            })?
            .to_owned();

        if relay.request.len() > MAX_GENERATION_BYTES {
            inner.metrics.record_captures(CaptureResult::TooLarge, 1);
            return None;
        }

        let bytes = relay.request.len()
            + std::mem::size_of::<Queued>()
            + 64
            + relay.task.capacity()
            + relay.trace_id.as_ref().map_or(0, String::capacity)
            + relay.session_id.as_ref().map_or(0, String::capacity)
            + relay.path.capacity()
            + content_type.capacity();
        let Ok(bytes) = u32::try_from(bytes) else {
            inner.metrics.record_captures(CaptureResult::Full, 1);
            return None;
        };

        let Ok(budget) = inner.budget.clone().try_acquire_many_owned(bytes) else {
            inner.metrics.record_captures(CaptureResult::Full, 1);
            return None;
        };

        Some(Recording {
            inner: inner.clone(),
            generation: Some(Generation {
                relay,
                status,
                content_type,
                response: BytesMut::new(),
                budget,
            }),
        })
    }
}

impl Recording {
    pub fn observe(&mut self, chunk: &[u8]) {
        let Some(generation) = &mut self.generation else {
            return;
        };

        let size = generation.relay.request.len() + generation.response.len() + chunk.len();
        if size > MAX_GENERATION_BYTES {
            self.abandon(CaptureResult::TooLarge);
            return;
        }

        let Ok(permit) = self
            .inner
            .budget
            .clone()
            .try_acquire_many_owned(chunk.len() as u32)
        else {
            self.abandon(CaptureResult::Full);
            return;
        };

        generation.budget.merge(permit);
        generation.response.extend_from_slice(chunk);
    }

    pub fn finish(&mut self, outcome: Outcome) {
        let Some(generation) = self.generation.take() else {
            return;
        };

        let queued = Queued {
            generation,
            outcome,
            completed_at: Utc::now(),
        };

        if self.inner.queue.send(queued).is_err() {
            self.inner.metrics.record_captures(CaptureResult::Closed, 1);
        }
    }

    fn abandon(&mut self, result: CaptureResult) {
        self.generation = None;
        self.inner.metrics.record_captures(result, 1);
    }
}

impl Drop for Recording {
    fn drop(&mut self) {
        self.finish(Outcome::Cancelled);
    }
}

pub struct Sender {
    stop: oneshot::Sender<()>,
    task: JoinHandle<()>,
}

impl Sender {
    pub async fn drain(self, timeout: Duration) -> bool {
        let _ = self.stop.send(());

        tokio::time::timeout(timeout, self.task).await.is_ok()
    }
}

struct Collector {
    client: Client,
    url: String,
    token: String,
    metrics: Metrics,
}

#[derive(Serialize)]
struct Line<'a> {
    schema: &'static str,
    generation_id: Uuid,
    workspace_id: Uuid,
    task: &'a str,
    trace_id: Option<&'a str>,
    session_id: Option<&'a str>,
    provider: &'static str,
    path: &'a str,
    retention_days: i16,
    status: u16,
    outcome: Outcome,
    completed_at: DateTime<Utc>,
    request: &'a str,
    response_content_type: &'a str,
    response: &'a str,
}

#[derive(Default)]
struct Batch {
    body: Vec<u8>,
    budget: Vec<OwnedSemaphorePermit>,
}

impl Collector {
    async fn run(
        self,
        mut receiver: mpsc::UnboundedReceiver<Queued>,
        mut stopped: oneshot::Receiver<()>,
    ) {
        loop {
            let first = tokio::select! {
                queued = receiver.recv() => queued,
                _ = &mut stopped, if !receiver.is_closed() => {
                    receiver.close();
                    continue;
                }
            };
            let Some(first) = first else {
                break;
            };

            let mut batch = Batch::default();
            self.append(&mut batch, first);

            let window = tokio::time::sleep(BATCH_WINDOW);
            tokio::pin!(window);
            while batch.body.len() < BATCH_BYTES {
                tokio::select! {
                    Some(queued) = receiver.recv() => self.append(&mut batch, queued),
                    _ = &mut window => break,
                    else => break,
                }
            }

            self.post(batch).await;
        }
    }

    fn append(&self, batch: &mut Batch, queued: Queued) {
        let generation = queued.generation;
        let relay = &generation.relay;

        let (Ok(request), Ok(response)) = (
            std::str::from_utf8(&relay.request),
            std::str::from_utf8(&generation.response),
        ) else {
            self.metrics.record_captures(CaptureResult::Unsupported, 1);
            return;
        };

        let line = Line {
            schema: if relay.hosted {
                "gradiated.hosted/1"
            } else {
                SCHEMA
            },
            generation_id: relay.generation_id,
            workspace_id: relay.workspace_id,
            task: &relay.task,
            trace_id: relay.trace_id.as_deref(),
            session_id: relay.session_id.as_deref(),
            provider: relay.provider.as_str(),
            path: &relay.path,
            retention_days: relay.retention_days,
            status: generation.status,
            outcome: queued.outcome,
            completed_at: queued.completed_at,
            request,
            response_content_type: &generation.content_type,
            response,
        };
        serde_json::to_writer(&mut batch.body, &line).expect("a relay line always serializes");
        batch.body.push(b'\n');
        batch.budget.push(generation.budget);
    }

    async fn post(&self, batch: Batch) {
        if batch.budget.is_empty() {
            return;
        }

        let count = batch.budget.len() as u64;
        let body = Bytes::from(batch.body);
        let send = || {
            self.client
                .post(&self.url)
                .bearer_auth(&self.token)
                .header(CONTENT_TYPE, "application/x-ndjson")
                .body(body.clone())
                .send()
        };

        let mut result = send()
            .await
            .and_then(|response| response.error_for_status());
        if result.is_err() {
            tokio::time::sleep(RETRY_DELAY).await;
            result = send()
                .await
                .and_then(|response| response.error_for_status());
        }

        match result {
            Ok(_) => self.metrics.record_captures(CaptureResult::Sent, count),
            Err(error) => {
                tracing::warn!(%error, count, "captured generations dropped");
                self.metrics
                    .record_captures(CaptureResult::Collector, count);
            }
        }
    }
}

#[cfg(test)]
#[path = "capture_tests.rs"]
mod tests;
