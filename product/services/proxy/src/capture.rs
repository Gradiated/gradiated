use std::{
    net::SocketAddr,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Mutex,
    },
    time::{Duration, Instant},
};

use axum::{
    body::Bytes,
    http::{
        header::{CONTENT_ENCODING, CONTENT_TYPE},
        HeaderMap,
    },
};
use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use bytes::BytesMut;
use chrono::{DateTime, Utc};
use reqwest::{Client, Url};
use serde::Serialize;
use tokio::{
    sync::{mpsc, oneshot, OwnedSemaphorePermit, Semaphore},
    task::{JoinHandle, JoinSet},
};
use uuid::Uuid;

use crate::{
    credentials::Provider,
    metrics::{CaptureResult, Metrics},
};

const SCHEMA: &str = "gradiated.relay/1";
/// A response without a content type is stored as opaque bytes.
const UNTYPED: &str = "application/octet-stream";
/// A request at the 32 MB body limit plus a response of up to 32 MiB.
const MAX_GENERATION_BYTES: usize = 64 * 1024 * 1024;
const BATCH_BYTES: usize = 1024 * 1024;
/// A batch below `BATCH_BYTES` plus one line fits the collector's 96 MiB body limit.
const MAX_LINE_BYTES: usize = 96 * 1024 * 1024 - BATCH_BYTES;
const BATCH_WINDOW: Duration = Duration::from_millis(100);
const CONNECT_TIMEOUT: Duration = Duration::from_secs(1);
const POST_TIMEOUT: Duration = Duration::from_secs(5);
/// A large batch gets one more second for each 8 MiB, at in-cluster speeds.
const POST_BYTES_PER_SECOND: usize = 8 * 1024 * 1024;
const RETRY_DELAY: Duration = Duration::from_millis(250);
/// Posts in flight at once, so more collector replicas mean more throughput.
const MAX_POSTS_IN_FLIGHT: usize = 8;
/// How long a resolved set of collector replicas is used before resolving again.
const RESOLVE_INTERVAL: Duration = Duration::from_secs(5);

#[derive(Clone, Debug)]
pub struct CaptureSettings {
    pub collector_url: String,
    /// A headless Service name that resolves to every collector replica. Posts
    /// rotate across them; without it, or when it resolves to nothing, every
    /// post uses `collector_url`.
    pub collector_discovery_host: Option<String>,
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
    pub request_content_type: Option<String>,
    /// A compressed upload is captured as sent, so readers need its coding.
    pub request_content_encoding: Option<String>,
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
    content_encoding: Option<String>,
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
    ) -> Result<(Self, Sender), CaptureError> {
        let url = Url::parse(&settings.collector_url)?;
        let targets = Targets::resolved(url, settings.collector_discovery_host.clone());
        Self::start_with(settings, targets, metrics)
    }

    fn start_with(
        settings: CaptureSettings,
        targets: Targets,
        metrics: Metrics,
    ) -> Result<(Self, Sender), CaptureError> {
        let client = Client::builder().connect_timeout(CONNECT_TIMEOUT).build()?;
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
            targets,
            token: settings.collector_token,
            metrics,
        };
        let task = tokio::spawn(collector.run(receiver, stopped));

        Ok((capture, Sender { stop, task }))
    }

    pub fn record(&self, relay: Relay, status: u16, headers: &HeaderMap) -> Option<Recording> {
        let inner = self.inner.as_ref()?;

        // A compressed response reaches the client unchanged; the collector
        // decodes the captured copy, so it travels with its coding.
        let Ok(codings) = headers
            .get_all(CONTENT_ENCODING)
            .iter()
            .map(|value| value.to_str().map(str::trim))
            .collect::<Result<Vec<_>, _>>()
        else {
            inner.metrics.record_captures(CaptureResult::Unsupported, 1);
            return None;
        };
        let content_encoding = Some(codings.join(", ")).filter(|codings| {
            codings.split(',').any(|coding| {
                !coding.trim().is_empty() && !coding.trim().eq_ignore_ascii_case("identity")
            })
        });

        // Any format is kept: the collector stores bodies it cannot parse as raw HTTP.
        let content_type = headers
            .get(CONTENT_TYPE)
            .and_then(|value| value.to_str().ok())
            .unwrap_or(UNTYPED)
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
            + relay
                .request_content_type
                .as_ref()
                .map_or(0, String::capacity)
            + relay
                .request_content_encoding
                .as_ref()
                .map_or(0, String::capacity)
            + content_type.capacity()
            + content_encoding.as_ref().map_or(0, String::capacity);
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
                content_encoding,
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

#[derive(Debug, thiserror::Error)]
pub enum CaptureError {
    #[error("PROXY_COLLECTOR_URL is not a URL: {0}")]
    Url(#[from] url::ParseError),
    #[error(transparent)]
    Client(#[from] reqwest::Error),
}

struct Collector {
    client: Client,
    targets: Targets,
    token: String,
    metrics: Metrics,
}

/// The collector replicas to post to. A Kubernetes Service keeps one TCP
/// connection on one pod, so the discovery host (a headless Service) is
/// resolved to every replica and posts rotate across them. A retry goes to the
/// next replica, so one busy or failing pod does not drop the batch.
struct Targets {
    url: Url,
    host: Option<(String, u16)>,
    fixed: Option<Vec<SocketAddr>>,
    resolved: Mutex<Option<(Instant, Vec<SocketAddr>)>>,
    next: AtomicUsize,
}

impl Targets {
    fn resolved(url: Url, discovery: Option<String>) -> Self {
        // Replica addresses replace the host, which TLS certificates would refuse.
        let host = discovery
            .filter(|_| url.scheme() == "http")
            .zip(url.port_or_known_default());

        Self {
            url,
            host,
            fixed: None,
            resolved: Mutex::new(None),
            next: AtomicUsize::new(0),
        }
    }

    #[cfg(test)]
    fn fixed(url: Url, addresses: Vec<SocketAddr>) -> Self {
        Self {
            fixed: Some(addresses),
            ..Self::resolved(url, None)
        }
    }

    async fn addresses(&self) -> Vec<SocketAddr> {
        if let Some(fixed) = &self.fixed {
            return fixed.clone();
        }
        let Some((host, port)) = &self.host else {
            return Vec::new();
        };

        let cached = self.resolved.lock().unwrap().clone();
        if let Some((at, addresses)) = &cached {
            if at.elapsed() < RESOLVE_INTERVAL {
                return addresses.clone();
            }
        }

        match tokio::net::lookup_host((host.as_str(), *port)).await {
            Ok(found) => {
                let mut addresses: Vec<_> = found.collect();
                addresses.sort();
                addresses.dedup();
                if !addresses.is_empty() {
                    *self.resolved.lock().unwrap() = Some((Instant::now(), addresses.clone()));
                    return addresses;
                }
            }
            Err(error) => tracing::warn!(%error, "collector addresses could not be resolved"),
        }

        // Keep the last good set; with none, the collector URL is used.
        cached.map(|(_, addresses)| addresses).unwrap_or_default()
    }

    /// The URLs of one post's attempts: the next replica in rotation, then
    /// different replicas for retries when there are any.
    async fn attempts(&self) -> Vec<Url> {
        let addresses = self.addresses().await;
        if addresses.is_empty() {
            return vec![self.url.clone(); 2];
        }

        let count = if addresses.len() >= 3 { 3 } else { 2 };
        let start = self.next.fetch_add(1, Ordering::Relaxed);
        (0..count)
            .map(|attempt| {
                let address = addresses[(start + attempt) % addresses.len()];
                let mut url = self.url.clone();
                url.set_ip_host(address.ip())
                    .expect("an http URL takes an IP host");
                url.set_port(Some(address.port()))
                    .expect("an http URL takes a port");
                url
            })
            .collect()
    }
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
    request_content_type: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    request_content_encoding: Option<&'a str>,
    #[serde(flatten)]
    request: Body<'a, RequestField>,
    response_content_type: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    response_content_encoding: Option<&'a str>,
    #[serde(flatten)]
    response: Body<'a, ResponseField>,
}

/// UTF-8 bodies travel as text; any other bytes, such as multipart uploads or
/// audio, travel as base64 under the `_base64` name.
enum Body<'a, F> {
    Text(&'a str, F),
    Binary(String, F),
}

trait Field {
    const TEXT: &'static str;
    const BINARY: &'static str;
}

#[derive(Clone, Copy)]
struct RequestField;
#[derive(Clone, Copy)]
struct ResponseField;

impl Field for RequestField {
    const TEXT: &'static str = "request";
    const BINARY: &'static str = "request_base64";
}

impl Field for ResponseField {
    const TEXT: &'static str = "response";
    const BINARY: &'static str = "response_base64";
}

impl<'a, F: Field + Copy> Body<'a, F> {
    fn new(bytes: &'a [u8], field: F) -> Self {
        match std::str::from_utf8(bytes) {
            Ok(text) => Self::Text(text, field),
            Err(_) => Self::Binary(BASE64.encode(bytes), field),
        }
    }
}

impl<F: Field> Serialize for Body<'_, F> {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeMap;

        let mut map = serializer.serialize_map(Some(1))?;
        match self {
            Self::Text(text, _) => map.serialize_entry(F::TEXT, text)?,
            Self::Binary(encoded, _) => map.serialize_entry(F::BINARY, encoded)?,
        }
        map.end()
    }
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
        let collector = Arc::new(self);
        let slots = Arc::new(Semaphore::new(MAX_POSTS_IN_FLIGHT));
        let mut posts = JoinSet::new();

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
            collector.append(&mut batch, first);

            let window = tokio::time::sleep(BATCH_WINDOW);
            tokio::pin!(window);
            while batch.body.len() < BATCH_BYTES {
                tokio::select! {
                    Some(queued) = receiver.recv() => collector.append(&mut batch, queued),
                    _ = &mut window => break,
                    else => break,
                }
            }

            let slot = slots
                .clone()
                .acquire_owned()
                .await
                .expect("the post slots are never closed");
            let poster = collector.clone();
            posts.spawn(async move {
                poster.post(batch).await;
                drop(slot);
            });
            while posts.try_join_next().is_some() {}
        }

        while posts.join_next().await.is_some() {}
    }

    fn append(&self, batch: &mut Batch, queued: Queued) {
        let generation = queued.generation;
        let relay = &generation.relay;

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
            request_content_type: relay.request_content_type.as_deref(),
            request_content_encoding: relay.request_content_encoding.as_deref(),
            request: Body::new(&relay.request, RequestField),
            response_content_type: &generation.content_type,
            response_content_encoding: generation.content_encoding.as_deref(),
            response: Body::new(&generation.response, ResponseField),
        };
        let start = batch.body.len();
        serde_json::to_writer(&mut batch.body, &line).expect("a relay line always serializes");
        batch.body.push(b'\n');
        // JSON escaping and base64 can grow a body past the collector's limit;
        // the bound is on the line as sent.
        if batch.body.len() - start > MAX_LINE_BYTES {
            batch.body.truncate(start);
            self.metrics.record_captures(CaptureResult::TooLarge, 1);
            return;
        }
        batch.budget.push(generation.budget);
    }

    async fn post(&self, batch: Batch) {
        if batch.budget.is_empty() {
            return;
        }

        let count = batch.budget.len() as u64;
        let body = Bytes::from(batch.body);
        let timeout = post_timeout(body.len());
        let send = |url: Url| {
            self.client
                .post(url)
                .timeout(timeout)
                .bearer_auth(&self.token)
                .header(CONTENT_TYPE, "application/x-ndjson")
                .body(body.clone())
                .send()
        };

        let mut result = None;
        for (attempt, url) in self.targets.attempts().await.into_iter().enumerate() {
            if attempt > 0 {
                tokio::time::sleep(RETRY_DELAY).await;
            }
            let outcome = send(url)
                .await
                .and_then(|response| response.error_for_status());
            let done = outcome.is_ok();
            result = Some(outcome);
            if done {
                break;
            }
        }
        let result = result.expect("a post makes at least one attempt");

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

fn post_timeout(bytes: usize) -> Duration {
    POST_TIMEOUT + Duration::from_secs((bytes / POST_BYTES_PER_SECOND) as u64)
}

#[cfg(test)]
#[path = "capture_tests.rs"]
mod tests;
