use std::{
    collections::VecDeque,
    net::SocketAddr,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Mutex,
    },
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
            collector_discovery_host: None,
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
        hosted: false,
        generation_id: Uuid::now_v7(),
        workspace_id: Uuid::now_v7(),
        task: "support-triage".to_owned(),
        trace_id: Some("trace-1".to_owned()),
        session_id: None,
        provider: Provider::Anthropic,
        path: "/v1/messages".to_owned(),
        retention_days: 90,
        request_content_type: Some("application/json".to_owned()),
        request_content_encoding: None,
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
async fn every_response_format_is_recorded() {
    let harness = harness(FakeCollector::default(), 8192).await;

    for mime in [
        "application/json",
        "application/json; charset=utf-8",
        "text/event-stream",
        "text/plain",
        "application/octet-stream",
        "audio/mpeg",
        "image/png",
    ] {
        assert!(harness.record(b"{}", mime).is_some(), "{mime}");
    }

    assert!(harness
        .capture
        .record(relay(b"{}"), 200, &HeaderMap::new())
        .is_some());
}

#[tokio::test]
async fn a_full_buffer_drops_the_generation_and_releases_its_bytes() {
    // Task, trace, path, request and response content types.
    let metadata = std::mem::size_of::<Queued>() + 64 + 14 + 7 + 12 + 16 + 16;
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
            collector_discovery_host: None,
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
async fn compressed_responses_travel_as_sent_with_their_coding() {
    let harness = harness(FakeCollector::default(), 8192).await;
    let mut headers = content_type("application/json");
    headers.insert(CONTENT_ENCODING, HeaderValue::from_static("gzip"));
    let mut recording = harness.capture.record(relay(b"{}"), 200, &headers).unwrap();
    recording.observe(b"\x1f\x8b\x08\x00\xff");
    recording.finish(Outcome::Complete);
    drop(recording);

    let mut plain = content_type("application/json");
    plain.insert(CONTENT_ENCODING, HeaderValue::from_static("identity"));
    let mut recording = harness.capture.record(relay(b"{}"), 200, &plain).unwrap();
    recording.observe(b"{}");
    recording.finish(Outcome::Complete);
    drop(recording);

    let (collector, metrics) = harness.drain().await;
    let lines = collector.lines();
    assert_eq!(lines[0]["response_content_encoding"], "gzip");
    assert_eq!(lines[0]["response_base64"], "H4sIAP8=");
    assert_eq!(lines[1].get("response_content_encoding"), None);
    assert_eq!(lines[1]["response"], "{}");
    assert_eq!(counted(&metrics, "unsupported"), 0);
}

#[tokio::test]
async fn non_utf8_bodies_travel_as_exact_base64() {
    let harness = harness(FakeCollector::default(), 8192).await;
    let mut request = harness.record(b"\xff", "application/json").unwrap();
    request.finish(Outcome::Complete);
    let mut response = harness.record(b"{}", "audio/mpeg").unwrap();
    response.observe(b"\xff\x00ID3");
    response.finish(Outcome::Complete);

    let (collector, metrics) = harness.drain().await;
    let lines = collector.lines();
    assert_eq!(lines.len(), 2);
    assert_eq!(lines[0]["request_base64"], "/w==");
    assert_eq!(lines[0].get("request"), None);
    assert_eq!(lines[0]["response"], "");
    assert_eq!(lines[1]["request"], "{}");
    assert_eq!(lines[1]["response_content_type"], "audio/mpeg");
    assert_eq!(lines[1]["response_base64"], "/wBJRDM=");
    assert_eq!(lines[1].get("response"), None);
    assert_eq!(counted(&metrics, "unsupported"), 0);
    assert_eq!(counted(&metrics, "sent"), 2);
}

#[tokio::test]
async fn multipart_uploads_and_untyped_responses_are_captured() {
    let harness = harness(FakeCollector::default(), 8192).await;
    let mut upload =
        relay(b"--b\r\nContent-Disposition: form-data; name=\"file\"\r\n\r\n\xff\xd8\r\n--b--\r\n");
    upload.path = "/v1/audio/transcriptions".to_owned();
    upload.request_content_type = Some("multipart/form-data; boundary=b".to_owned());
    let mut recording = harness
        .capture
        .record(upload, 200, &HeaderMap::new())
        .unwrap();
    recording.observe(b"Beep.");
    recording.finish(Outcome::Complete);

    let (collector, _) = harness.drain().await;
    let lines = collector.lines();
    assert_eq!(lines[0]["path"], "/v1/audio/transcriptions");
    assert_eq!(
        lines[0]["request_content_type"],
        "multipart/form-data; boundary=b"
    );
    assert!(lines[0]["request_base64"].as_str().is_some());
    assert_eq!(
        lines[0]["response_content_type"],
        "application/octet-stream"
    );
    assert_eq!(lines[0]["response"], "Beep.");
}

#[tokio::test]
async fn a_compressed_upload_keeps_its_content_encoding() {
    let harness = harness(FakeCollector::default(), 8192).await;
    let mut upload = relay(b"\x1f\x8b\x08\x00");
    upload.request_content_encoding = Some("gzip".to_owned());
    let mut recording = harness
        .capture
        .record(upload, 200, &content_type("application/json"))
        .unwrap();
    recording.observe(b"{}");
    recording.finish(Outcome::Complete);
    drop(recording);
    let mut plain = harness.record(b"{}", "application/json").unwrap();
    plain.finish(Outcome::Complete);

    let (collector, _) = harness.drain().await;
    let lines = collector.lines();
    assert_eq!(lines[0]["request_content_encoding"], "gzip");
    assert_eq!(lines[0]["request_base64"], "H4sIAA==");
    assert_eq!(lines[1].get("request_content_encoding"), None);
}

#[test]
fn large_posts_get_more_time() {
    assert_eq!(post_timeout(1024), Duration::from_secs(5));
    assert_eq!(post_timeout(96 * 1024 * 1024), Duration::from_secs(17));
}

#[tokio::test]
async fn a_line_that_escapes_past_the_collector_limit_is_dropped_whole() {
    let harness = harness(FakeCollector::default(), 128 * 1024 * 1024).await;
    // Each control byte serializes as six (\u0001), so 20 MiB becomes 120 MiB.
    let mut big = harness.record(b"{}", "application/json").unwrap();
    big.observe(&vec![1u8; 20 * 1024 * 1024]);
    big.finish(Outcome::Complete);
    drop(big);
    let mut small = harness.record(b"{}", "application/json").unwrap();
    small.finish(Outcome::Complete);
    drop(small);

    let (collector, metrics) = harness.drain().await;
    assert_eq!(collector.lines().len(), 1);
    assert_eq!(counted(&metrics, "too_large"), 1);
    assert_eq!(counted(&metrics, "sent"), 1);
}

/// A fake collector replica on its own port, optionally slow, that counts the
/// posts it is handling at once.
#[derive(Clone, Default)]
struct Replica {
    collector: FakeCollector,
    delay: Duration,
    active: Arc<AtomicUsize>,
    peak: Arc<AtomicUsize>,
}

async fn replica_receive(
    State(replica): State<Replica>,
    headers: HeaderMap,
    body: Bytes,
) -> StatusCode {
    let now = replica.active.fetch_add(1, Ordering::SeqCst) + 1;
    replica.peak.fetch_max(now, Ordering::SeqCst);
    tokio::time::sleep(replica.delay).await;
    replica.active.fetch_sub(1, Ordering::SeqCst);

    receive(State(replica.collector), headers, body).await
}

async fn serve(replica: Replica) -> SocketAddr {
    let listener = TcpListener::bind(SocketAddr::from(([127, 0, 0, 1], 0)))
        .await
        .unwrap();
    let address = listener.local_addr().unwrap();
    let router = Router::new()
        .route("/v1/contents", post(replica_receive))
        .with_state(replica);
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });

    address
}

fn spread(addresses: Vec<SocketAddr>) -> (Collector, Metrics) {
    let metrics = Metrics::default();
    let collector = Collector {
        client: Client::new(),
        targets: Targets::fixed(
            Url::parse("http://collector-headless.invalid:3004/v1/contents").unwrap(),
            addresses,
        ),
        token: "collector-token".to_owned(),
        metrics: metrics.clone(),
    };

    (collector, metrics)
}

fn one_line_batch() -> Batch {
    let budget = Arc::new(Semaphore::new(1));
    Batch {
        body: b"{}\n".to_vec(),
        budget: vec![budget.try_acquire_owned().unwrap()],
    }
}

#[tokio::test]
async fn posts_rotate_across_every_collector_replica() {
    let replicas: Vec<Replica> = (0..3).map(|_| Replica::default()).collect();
    let mut addresses = Vec::new();
    for replica in &replicas {
        addresses.push(serve(replica.clone()).await);
    }
    let (collector, metrics) = spread(addresses);

    for _ in 0..9 {
        collector.post(one_line_batch()).await;
    }

    for replica in &replicas {
        assert_eq!(replica.collector.posts().len(), 3);
    }
    assert_eq!(counted(&metrics, "sent"), 9);
}

#[tokio::test]
async fn a_refused_post_is_retried_on_other_replicas() {
    let busy = Replica {
        collector: FakeCollector::answering(&[StatusCode::SERVICE_UNAVAILABLE]),
        ..Replica::default()
    };
    let down = Replica {
        collector: FakeCollector::answering(&[StatusCode::SERVICE_UNAVAILABLE]),
        ..Replica::default()
    };
    let healthy = Replica::default();
    let addresses = vec![
        serve(busy.clone()).await,
        serve(down.clone()).await,
        serve(healthy.clone()).await,
    ];
    let (collector, metrics) = spread(addresses);

    collector.post(one_line_batch()).await;

    assert_eq!(busy.collector.posts().len(), 1);
    assert_eq!(down.collector.posts().len(), 1);
    assert_eq!(healthy.collector.posts().len(), 1);
    assert_eq!(counted(&metrics, "sent"), 1);
}

#[tokio::test]
async fn a_slow_collector_does_not_serialize_posts() {
    let slow = Replica {
        delay: Duration::from_millis(300),
        ..Replica::default()
    };
    let address = serve(slow.clone()).await;
    let metrics = Metrics::default();
    let (capture, sender) = Capture::start_with(
        CaptureSettings {
            collector_url: format!("http://{address}/v1/contents"),
            collector_discovery_host: None,
            collector_token: "collector-token".to_owned(),
            buffer_bytes: 1 << 20,
        },
        Targets::fixed(
            Url::parse("http://collector.invalid/v1/contents").unwrap(),
            vec![address],
        ),
        metrics.clone(),
    )
    .unwrap();

    for _ in 0..4 {
        let mut recording = capture
            .record(relay(b"{}"), 200, &content_type("application/json"))
            .unwrap();
        recording.finish(Outcome::Complete);
        drop(recording);
        tokio::time::sleep(BATCH_WINDOW + Duration::from_millis(30)).await;
    }
    assert!(sender.drain(Duration::from_secs(5)).await);

    assert_eq!(slow.collector.posts().len(), 4);
    assert!(
        slow.peak.load(Ordering::SeqCst) >= 2,
        "posts ran one at a time"
    );
    assert_eq!(counted(&metrics, "sent"), 4);
}

#[tokio::test]
async fn an_unresolvable_discovery_host_falls_back_to_the_collector_url() {
    let url = Url::parse("http://collector.gradiated.svc:3004/v1/contents").unwrap();
    let targets = Targets::resolved(url.clone(), Some("collector-headless.invalid".to_owned()));

    assert_eq!(targets.attempts().await, vec![url; 2]);
}

#[tokio::test]
async fn a_discovery_host_resolves_to_replicas_on_the_url_port() {
    let url = Url::parse("http://collector.gradiated.svc:3004/v1/contents").unwrap();
    let targets = Targets::resolved(url, Some("localhost".to_owned()));
    let attempts = targets.attempts().await;

    assert!(attempts.len() >= 2);
    for attempt in attempts {
        assert_ne!(attempt.host_str(), Some("collector.gradiated.svc"));
        assert_eq!(attempt.port(), Some(3004));
        assert_eq!(attempt.path(), "/v1/contents");
    }
}

#[tokio::test]
async fn without_a_discovery_host_the_url_is_used_as_given() {
    let url = Url::parse("http://collector.gradiated.svc:3004/v1/contents").unwrap();
    let targets = Targets::resolved(url.clone(), None);

    assert_eq!(targets.attempts().await, vec![url; 2]);
}

#[tokio::test]
async fn https_collector_urls_are_never_spread() {
    for url in ["https://collector.example/v1/contents"] {
        let targets = Targets::resolved(Url::parse(url).unwrap(), Some("localhost".to_owned()));
        assert_eq!(targets.attempts().await, vec![Url::parse(url).unwrap(); 2]);
    }
}
