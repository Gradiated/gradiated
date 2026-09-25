use std::{
    collections::VecDeque,
    net::SocketAddr,
    sync::{Arc, Mutex},
};

use axum::{
    extract::State,
    http::{header::AUTHORIZATION, HeaderValue, StatusCode},
    routing::post,
    Router,
};
use serde_json::Value;
use tokio::net::TcpListener;

use super::*;

#[derive(Clone, Default)]
struct FakeCollector {
    statuses: Arc<Mutex<VecDeque<StatusCode>>>,
    posts: Arc<Mutex<Vec<(HeaderMap, Bytes)>>>,
}

impl FakeCollector {
    fn answering(statuses: &[StatusCode]) -> Self {
        Self {
            statuses: Arc::new(Mutex::new(statuses.iter().copied().collect())),
            ..Self::default()
        }
    }

    fn posts(&self) -> Vec<(HeaderMap, Bytes)> {
        self.posts.lock().unwrap().clone()
    }

    fn lines(&self) -> Vec<Value> {
        self.posts()
            .iter()
            .flat_map(|(_, body)| {
                body.split(|byte| *byte == b'\n')
                    .filter(|line| !line.is_empty())
            })
            .map(|line| serde_json::from_slice(line).unwrap())
            .collect()
    }
}

async fn receive(
    State(collector): State<FakeCollector>,
    headers: HeaderMap,
    body: Bytes,
) -> StatusCode {
    let status = collector
        .statuses
        .lock()
        .unwrap()
        .pop_front()
        .unwrap_or(StatusCode::ACCEPTED);
    collector.posts.lock().unwrap().push((headers, body));

    status
}

struct Harness {
    capture: Capture,
    sender: Sender,
    collector: FakeCollector,
    metrics: Metrics,
}

async fn harness(collector: FakeCollector, buffer_bytes: usize) -> Harness {
    let listener = TcpListener::bind(SocketAddr::from(([127, 0, 0, 1], 0)))
        .await
        .unwrap();
    let url = format!("http://{}/v1/contents", listener.local_addr().unwrap());
    let router = Router::new()
        .route("/v1/contents", post(receive))
        .with_state(collector.clone());
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });

    let metrics = Metrics::default();
    let (capture, sender) = Capture::start(
        CaptureSettings {
            collector_url: url,
            collector_token: "collector-token".to_owned(),
            buffer_bytes,
        },
        metrics.clone(),
    )
    .unwrap();

    Harness {
        capture,
        sender,
        collector,
        metrics,
    }
}

fn relay(request: &'static [u8]) -> Relay {
    Relay {
        generation_id: Uuid::now_v7(),
        workspace_id: Uuid::now_v7(),
        task: "support-triage".to_owned(),
        trace_id: Some("trace-1".to_owned()),
        session_id: None,
        provider: Provider::Anthropic,
        path: "/v1/messages".to_owned(),
        retention_days: 90,
        request: Bytes::from_static(request),
    }
}

fn content_type(value: &'static str) -> HeaderMap {
    let mut headers = HeaderMap::new();
    headers.insert(CONTENT_TYPE, HeaderValue::from_static(value));

    headers
}

fn counted(metrics: &Metrics, result: &str) -> u64 {
    let prefix = format!("gradiated_proxy_captures_total{{result=\"{result}\"}} ");

    metrics
        .encode()
        .lines()
        .find_map(|line| line.strip_prefix(&prefix))
        .map_or(0, |count| count.parse().unwrap())
}

impl Harness {
    fn record(&self, request: &'static [u8], mime: &'static str) -> Option<Recording> {
        self.capture
            .record(relay(request), 200, &content_type(mime))
    }

    fn available(&self) -> usize {
        self.capture
            .inner
            .as_ref()
            .unwrap()
            .budget
            .available_permits()
    }

    async fn drain(self) -> (FakeCollector, Metrics) {
        assert!(self.sender.drain(Duration::from_secs(5)).await);

        (self.collector, self.metrics)
    }
}

#[tokio::test]
async fn a_finished_stream_reaches_the_collector_as_one_relay_line() {
    let harness = harness(FakeCollector::default(), 8192).await;

    let mut recording = harness
        .record(
            br#"{"model":"claude","stream":true}"#,
            "text/event-stream; charset=utf-8",
        )
        .unwrap();
    recording.observe(b"event: message_start\n");
    recording.observe(b"data: {}\n\n");
    recording.finish(Outcome::Complete);
    drop(recording);

    let (collector, metrics) = harness.drain().await;
    let posts = collector.posts();
    let lines = collector.lines();

    assert_eq!(posts.len(), 1);
    assert_eq!(posts[0].0[AUTHORIZATION], "Bearer collector-token");
    assert_eq!(posts[0].0[CONTENT_TYPE], "application/x-ndjson");
    assert_eq!(lines.len(), 1);
    assert_eq!(lines[0]["schema"], "gradiated.relay/1");
    assert_eq!(lines[0]["task"], "support-triage");
    assert_eq!(lines[0]["trace_id"], "trace-1");
    assert_eq!(lines[0]["session_id"], Value::Null);
    assert_eq!(lines[0]["provider"], "anthropic");
    assert_eq!(lines[0]["path"], "/v1/messages");
    assert_eq!(lines[0]["retention_days"], 90);
    assert_eq!(lines[0]["status"], 200);
    assert_eq!(lines[0]["outcome"], "complete");
    assert_eq!(lines[0]["request"], r#"{"model":"claude","stream":true}"#);
    assert_eq!(
        lines[0]["response_content_type"],
        "text/event-stream; charset=utf-8"
    );
    assert_eq!(lines[0]["response"], "event: message_start\ndata: {}\n\n");
    assert_eq!(counted(&metrics, "sent"), 1);
}

#[tokio::test]
async fn generations_that_finish_together_share_one_post() {
    let harness = harness(FakeCollector::default(), 8192).await;

    for _ in 0..3 {
        let mut recording = harness.record(b"{}", "application/json").unwrap();
        recording.observe(b"{}");
        recording.finish(Outcome::Complete);
    }

    let (collector, metrics) = harness.drain().await;

    assert_eq!(collector.posts().len(), 1);
    assert_eq!(collector.lines().len(), 3);
    assert_eq!(counted(&metrics, "sent"), 3);
}

#[tokio::test]
async fn a_dropped_stream_is_sent_as_cancelled_and_a_failed_one_as_an_error() {
    let harness = harness(FakeCollector::default(), 8192).await;

    let mut cancelled = harness.record(b"{}", "text/event-stream").unwrap();
    cancelled.observe(b"data: partial\n\n");
    drop(cancelled);

    let mut failed = harness.record(b"{}", "text/event-stream").unwrap();
    failed.finish(Outcome::Error);
    failed.finish(Outcome::Complete);
    drop(failed);

    let (collector, _) = harness.drain().await;
    let outcomes: Vec<Value> = collector
        .lines()
        .iter()
        .map(|line| line["outcome"].clone())
        .collect();

    assert_eq!(outcomes, ["cancelled", "error"]);
    assert_eq!(collector.lines()[0]["response"], "data: partial\n\n");
}

#[tokio::test]
async fn only_json_and_event_stream_responses_are_recorded() {
    let harness = harness(FakeCollector::default(), 8192).await;

    for mime in [
        "application/json",
        "application/json; charset=utf-8",
        "text/event-stream",
    ] {
        assert!(harness.record(b"{}", mime).is_some(), "{mime}");
    }

    for mime in ["text/html", "application/octet-stream", "audio/mpeg"] {
        assert!(harness.record(b"{}", mime).is_none(), "{mime}");
    }

    assert!(harness
        .capture
        .record(relay(b"{}"), 200, &HeaderMap::new())
        .is_none());
}

#[tokio::test]
async fn a_full_buffer_drops_the_generation_and_releases_its_bytes() {
    let metadata = std::mem::size_of::<Queued>() + 64 + 14 + 7 + 12 + 16;
    let harness = harness(FakeCollector::default(), metadata + 16).await;

    let mut recording = harness.record(b"0123456789", "application/json").unwrap();
    assert_eq!(harness.available(), 6);

    recording.observe(b"too many bytes");
    assert_eq!(harness.available(), metadata + 16);

    recording.finish(Outcome::Complete);
    assert!(harness.record(&[b'x'; 17], "application/json").is_none());

    let (collector, metrics) = harness.drain().await;

    assert!(collector.posts().is_empty());
    assert_eq!(counted(&metrics, "full"), 2);
}

#[tokio::test]
async fn sent_generations_return_their_bytes_to_the_buffer() {
    let harness = harness(FakeCollector::default(), 8192).await;

    let mut recording = harness.record(b"{}", "application/json").unwrap();
    recording.observe(b"{}");
    recording.finish(Outcome::Complete);

    let capture = harness.capture.clone();
    let (collector, _) = harness.drain().await;

    assert_eq!(collector.lines().len(), 1);
    assert_eq!(
        capture.inner.as_ref().unwrap().budget.available_permits(),
        8192
    );
}

#[tokio::test]
async fn a_generation_over_the_size_cap_is_dropped() {
    let harness = harness(FakeCollector::default(), Semaphore::MAX_PERMITS).await;

    let mut recording = harness.record(b"{}", "application/json").unwrap();
    recording.observe(&vec![b'x'; MAX_GENERATION_BYTES]);
    recording.finish(Outcome::Complete);

    let (collector, metrics) = harness.drain().await;

    assert!(collector.posts().is_empty());
    assert_eq!(counted(&metrics, "too_large"), 1);
}

#[tokio::test]
async fn a_failed_post_is_retried_once() {
    for (statuses, posts, sent, dropped) in [
        (&[StatusCode::SERVICE_UNAVAILABLE][..], 2, 1, 0),
        (&[StatusCode::SERVICE_UNAVAILABLE; 2][..], 2, 0, 1),
        (&[StatusCode::BAD_REQUEST; 2][..], 2, 0, 1),
    ] {
        let harness = harness(FakeCollector::answering(statuses), 1024).await;

        let mut recording = harness.record(b"{}", "application/json").unwrap();
        recording.finish(Outcome::Complete);

        let (collector, metrics) = harness.drain().await;

        assert_eq!(collector.posts().len(), posts, "{statuses:?}");
        assert_eq!(counted(&metrics, "sent"), sent, "{statuses:?}");
        assert_eq!(counted(&metrics, "collector"), dropped, "{statuses:?}");
    }
}

#[tokio::test]
async fn an_unreachable_collector_drops_the_batch() {
    let listener = TcpListener::bind(SocketAddr::from(([127, 0, 0, 1], 0)))
        .await
        .unwrap();
    let url = format!("http://{}/v1/contents", listener.local_addr().unwrap());
    drop(listener);

    let metrics = Metrics::default();
    let (capture, sender) = Capture::start(
        CaptureSettings {
            collector_url: url,
            collector_token: "collector-token".to_owned(),
            buffer_bytes: 1024,
        },
        metrics.clone(),
    )
    .unwrap();

    let mut recording = capture
        .record(relay(b"{}"), 200, &content_type("application/json"))
        .unwrap();
    recording.finish(Outcome::Complete);

    assert!(sender.drain(Duration::from_secs(5)).await);
    assert_eq!(counted(&metrics, "collector"), 1);
}

#[tokio::test]
async fn generations_that_finish_after_the_drain_are_counted_as_closed() {
    let harness = harness(FakeCollector::default(), 8192).await;

    let mut late = harness.record(b"{}", "application/json").unwrap();
    let (collector, metrics) = harness.drain().await;

    late.finish(Outcome::Complete);

    assert!(collector.posts().is_empty());
    assert_eq!(counted(&metrics, "closed"), 1);
}

#[tokio::test]
async fn a_disabled_capture_records_nothing() {
    let capture = Capture::default();

    assert!(capture
        .record(relay(b"{}"), 200, &content_type("application/json"))
        .is_none());
}

#[tokio::test]
async fn queued_empty_generations_and_metadata_exhaust_the_budget() {
    let harness = harness(FakeCollector::default(), 8192).await;
    let mut accepted = 0;

    while let Some(mut recording) = harness.record(b"", "application/json") {
        recording.finish(Outcome::Complete);
        accepted += 1;
        assert!(accepted < 64);
    }

    assert!(accepted > 0);
    assert_eq!(counted(&harness.metrics, "full"), 1);
    let (collector, _) = harness.drain().await;
    assert_eq!(collector.lines().len(), accepted);
}

#[tokio::test]
async fn customer_metadata_is_charged_before_recording() {
    let harness = harness(FakeCollector::default(), 8192).await;
    let mut request = relay(b"{}");
    request.session_id = Some("x".repeat(8192));

    assert!(harness
        .capture
        .record(request, 200, &content_type("application/json"))
        .is_none());
    assert_eq!(harness.available(), 8192);
    assert_eq!(counted(&harness.metrics, "full"), 1);
}

#[tokio::test]
async fn encoded_responses_are_skipped_without_recording_corrupt_text() {
    let harness = harness(FakeCollector::default(), 8192).await;
    let mut headers = content_type("application/json");
    headers.insert(CONTENT_ENCODING, HeaderValue::from_static("gzip"));

    assert!(harness
        .capture
        .record(relay(b"{}"), 200, &headers)
        .is_none());
    assert_eq!(harness.available(), 8192);
    assert_eq!(counted(&harness.metrics, "unsupported"), 1);
}

#[tokio::test]
async fn non_utf8_bodies_are_dropped_without_lossy_conversion() {
    let harness = harness(FakeCollector::default(), 8192).await;
    let mut request = harness.record(b"\xff", "application/json").unwrap();
    request.finish(Outcome::Complete);
    let mut response = harness.record(b"{}", "application/json").unwrap();
    response.observe(b"\xff");
    response.finish(Outcome::Complete);

    let (collector, metrics) = harness.drain().await;
    assert!(collector.posts().is_empty());
    assert_eq!(counted(&metrics, "unsupported"), 2);
}
