use std::{
    net::SocketAddr,
    sync::{Arc, Mutex},
    time::Duration,
};

use axum::{
    body::Body,
    extract::State,
    http::{HeaderMap, HeaderName, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    routing::post,
    Router,
};
use futures_util::StreamExt;
use tokio::net::TcpListener;

use super::*;

const CUSTOMER_KEY: &str = "sk-ant-customer";

fn credential() -> ProviderCredential<'static> {
    ProviderCredential {
        provider: Provider::Anthropic,
        secret: CUSTOMER_KEY,
    }
}

fn limits() -> ProxyLimits {
    ProxyLimits {
        connect_timeout: Duration::from_secs(10),
        response_header_timeout: Duration::from_secs(120),
        idle_timeout: Duration::from_secs(120),
        total_timeout: Duration::from_secs(900),
        max_request_bytes: 8 * 1024 * 1024,
        request_buffer_bytes: 64 * 1024 * 1024,
        max_in_flight: 2_000,
    }
}

fn header_map(values: &[(&str, &str)]) -> HeaderMap {
    let mut headers = HeaderMap::new();
    for (name, value) in values {
        headers.append(
            HeaderName::from_bytes(name.as_bytes()).unwrap(),
            HeaderValue::from_str(value).unwrap(),
        );
    }

    headers
}

#[test]
fn a_relayed_body_names_exactly_one_model() {
    let target = parse_target(br#"{"model":"claude-sonnet-5","max_tokens":16}"#).unwrap();
    assert_eq!(target.model, "claude-sonnet-5");
    assert_eq!(target.request["max_tokens"], 16);

    for body in [
        &br#"{"max_tokens":16}"#[..],
        &br#"{"model":""}"#[..],
        &br#"{"model":null}"#[..],
        &br#"{"model":["claude-sonnet-5"]}"#[..],
        &br#"{"model":"claude-sonnet-5","model":"claude-opus-5"}"#[..],
        &br#"not json"#[..],
    ] {
        assert!(
            parse_target(body).is_err(),
            "expected a local rejection for {}",
            String::from_utf8_lossy(body)
        );
    }
}

#[test]
fn upstream_headers_carry_only_the_customer_credential() {
    let inbound = header_map(&[
        ("content-type", "application/json"),
        ("anthropic-version", "2023-06-01"),
        ("authorization", "Bearer grad_test"),
        ("x-api-key", CUSTOMER_KEY),
        ("x-gradiated-api-key", "grad_test"),
        ("x-gradiated-session-id", "session"),
        ("cookie", "session=1"),
        ("host", "api.gradiated.com"),
        ("content-length", "128"),
        ("transfer-encoding", "chunked"),
        ("x-forwarded-for", "203.0.113.7"),
        ("cf-connecting-ip", "203.0.113.7"),
        ("connection", "keep-alive, x-trace-hint"),
        ("x-trace-hint", "drop me"),
    ]);

    let upstream =
        upstream_headers(&inbound, RelayRoute::AnthropicMessages, &credential()).unwrap();

    assert_eq!(upstream.get("x-api-key").unwrap(), CUSTOMER_KEY);
    assert_eq!(upstream.get("anthropic-version").unwrap(), "2023-06-01");
    assert_eq!(upstream.get("content-type").unwrap(), "application/json");
    assert_eq!(upstream.get("x-gradiated-hop").unwrap(), "1");
    assert_eq!(upstream.get("accept-encoding").unwrap(), "identity");

    for absent in [
        "authorization",
        "x-gradiated-api-key",
        "x-gradiated-session-id",
        "cookie",
        "host",
        "content-length",
        "transfer-encoding",
        "x-forwarded-for",
        "cf-connecting-ip",
        "connection",
        "x-trace-hint",
    ] {
        assert!(
            upstream.get(absent).is_none(),
            "{absent} must not reach the provider"
        );
    }
}

#[test]
fn an_inbound_hop_header_is_rejected() {
    let inbound = header_map(&[("x-gradiated-hop", "1")]);
    assert!(upstream_headers(&inbound, RelayRoute::AnthropicMessages, &credential()).is_err());
}

#[test]
fn downstream_headers_keep_provider_content_and_drop_the_connection() {
    let upstream = header_map(&[
        ("content-type", "text/event-stream"),
        ("content-encoding", "gzip"),
        ("request-id", "req_123"),
        ("content-length", "64"),
        ("transfer-encoding", "chunked"),
        ("set-cookie", "a=1"),
        ("alt-svc", "h3=\":443\""),
        ("connection", "keep-alive, x-provider-hint"),
        ("x-provider-hint", "drop me"),
    ]);

    let downstream = downstream_headers(&upstream);

    assert_eq!(downstream.get("content-type").unwrap(), "text/event-stream");
    assert_eq!(downstream.get("content-encoding").unwrap(), "gzip");
    assert_eq!(downstream.get("request-id").unwrap(), "req_123");

    for absent in [
        "content-length",
        "transfer-encoding",
        "set-cookie",
        "alt-svc",
        "connection",
        "x-provider-hint",
    ] {
        assert!(
            downstream.get(absent).is_none(),
            "{absent} must be stripped"
        );
    }
}

#[derive(Clone)]
struct TestProvider {
    seen: Arc<Mutex<Option<HeaderMap>>>,
    body: Arc<Mutex<Option<Vec<u8>>>>,
    reply: TestReply,
}

#[derive(Clone, Copy)]
enum TestReply {
    Json,
    Stream,
    RateLimited,
    Redirect,
}

async fn provider_handler(
    State(provider): State<TestProvider>,
    headers: HeaderMap,
    body: axum::body::Bytes,
) -> Response {
    *provider.seen.lock().unwrap() = Some(headers);
    *provider.body.lock().unwrap() = Some(body.to_vec());

    match provider.reply {
        TestReply::Json => (
            StatusCode::OK,
            [("content-type", "application/json"), ("set-cookie", "a=1")],
            r#"{"id":"msg_1","model":"claude-sonnet-5"}"#,
        )
            .into_response(),
        TestReply::Stream => {
            let frames = futures_util::stream::iter(vec![
                Ok::<_, std::io::Error>(Bytes::from_static(b"event: message_start\n\n")),
                Ok(Bytes::from_static(b"event: message_stop\n\n")),
            ]);
            (
                StatusCode::OK,
                [("content-type", "text/event-stream")],
                Body::from_stream(frames),
            )
                .into_response()
        }
        TestReply::RateLimited => (
            StatusCode::TOO_MANY_REQUESTS,
            [("content-type", "application/json"), ("retry-after", "7")],
            r#"{"type":"error","error":{"type":"rate_limit_error"}}"#,
        )
            .into_response(),
        TestReply::Redirect => (
            StatusCode::TEMPORARY_REDIRECT,
            [("location", "https://example.invalid/v1/messages")],
            "",
        )
            .into_response(),
    }
}

async fn start_provider(reply: TestReply) -> (SocketAddr, TestProvider) {
    let provider = TestProvider {
        seen: Arc::new(Mutex::new(None)),
        body: Arc::new(Mutex::new(None)),
        reply,
    };
    let router = Router::new()
        .route("/v1/messages", post(provider_handler))
        .with_state(provider.clone());
    let listener = TcpListener::bind(SocketAddr::from(([127, 0, 0, 1], 0)))
        .await
        .unwrap();
    let address = listener.local_addr().unwrap();
    tokio::spawn(async move {
        axum::serve(listener, router).await.unwrap();
    });

    (address, provider)
}

/// The sanitized header set for a request that carries no caller headers.
fn bare_upstream() -> UpstreamHeaders {
    upstream_headers(
        &HeaderMap::new(),
        RelayRoute::AnthropicMessages,
        &credential(),
    )
    .unwrap()
}

fn relay_for(address: SocketAddr, limits: ProxyLimits) -> ProviderRelay {
    ProviderRelay::new(&format!("http://{address}"), limits).unwrap()
}

async fn collect(body: RelayBody) -> Result<Vec<u8>, RelayError> {
    let mut collected = Vec::new();
    let mut body = Box::pin(body);
    while let Some(chunk) = body.next().await {
        collected.extend_from_slice(&chunk?);
    }

    Ok(collected)
}

#[tokio::test]
async fn a_non_streaming_relay_passes_bytes_and_isolates_credentials() {
    let (address, provider) = start_provider(TestReply::Json).await;
    let inbound = header_map(&[
        ("content-type", "application/json"),
        ("anthropic-version", "2023-06-01"),
        ("x-gradiated-api-key", "grad_test"),
    ]);
    let request = Bytes::from_static(br#"{"model":"claude-sonnet-5","max_tokens":16}"#);

    let upstream =
        upstream_headers(&inbound, RelayRoute::AnthropicMessages, &credential()).unwrap();
    let response = relay_for(address, limits())
        .send(RelayRoute::AnthropicMessages, upstream, request.clone())
        .await
        .unwrap();

    assert_eq!(response.status, StatusCode::OK);
    assert_eq!(
        response.headers.get("content-type").unwrap(),
        "application/json"
    );
    assert!(response.headers.get("set-cookie").is_none());
    assert_eq!(
        collect(response.body).await.unwrap(),
        br#"{"id":"msg_1","model":"claude-sonnet-5"}"#
    );

    let seen = provider.seen.lock().unwrap().clone().unwrap();
    assert_eq!(seen.get("x-api-key").unwrap(), CUSTOMER_KEY);
    assert!(seen.get("x-gradiated-api-key").is_none());
    assert_eq!(
        provider.body.lock().unwrap().clone().unwrap(),
        request.to_vec(),
        "the provider must receive the caller's bytes unchanged"
    );
}

#[tokio::test]
async fn a_streaming_relay_preserves_provider_frames() {
    let (address, _) = start_provider(TestReply::Stream).await;
    let upstream = upstream_headers(
        &header_map(&[("content-type", "application/json")]),
        RelayRoute::AnthropicMessages,
        &credential(),
    )
    .unwrap();

    let response = relay_for(address, limits())
        .send(
            RelayRoute::AnthropicMessages,
            upstream,
            Bytes::from_static(br#"{"model":"claude-sonnet-5","stream":true}"#),
        )
        .await
        .unwrap();

    assert_eq!(
        response.headers.get("content-type").unwrap(),
        "text/event-stream"
    );
    assert_eq!(
        collect(response.body).await.unwrap(),
        b"event: message_start\n\nevent: message_stop\n\n"
    );
}

#[tokio::test]
async fn a_provider_rate_limit_reaches_the_caller_unchanged() {
    let (address, _) = start_provider(TestReply::RateLimited).await;
    let upstream = upstream_headers(
        &header_map(&[("content-type", "application/json")]),
        RelayRoute::AnthropicMessages,
        &credential(),
    )
    .unwrap();

    let response = relay_for(address, limits())
        .send(
            RelayRoute::AnthropicMessages,
            upstream,
            Bytes::from_static(br#"{"model":"claude-sonnet-5"}"#),
        )
        .await
        .unwrap();

    assert_eq!(response.status, StatusCode::TOO_MANY_REQUESTS);
    assert_eq!(response.headers.get("retry-after").unwrap(), "7");
    assert_eq!(
        collect(response.body).await.unwrap(),
        br#"{"type":"error","error":{"type":"rate_limit_error"}}"#
    );
}

#[tokio::test]
async fn a_provider_redirect_is_never_followed() {
    let (address, _) = start_provider(TestReply::Redirect).await;
    let upstream = upstream_headers(
        &header_map(&[("content-type", "application/json")]),
        RelayRoute::AnthropicMessages,
        &credential(),
    )
    .unwrap();

    let response = relay_for(address, limits())
        .send(
            RelayRoute::AnthropicMessages,
            upstream,
            Bytes::from_static(br#"{"model":"claude-sonnet-5"}"#),
        )
        .await
        .unwrap();

    assert_eq!(response.status, StatusCode::TEMPORARY_REDIRECT);
}

#[tokio::test]
async fn an_oversized_request_and_an_exhausted_budget_are_refused_before_dispatch() {
    let (address, _) = start_provider(TestReply::Json).await;
    let mut small = limits();
    small.max_request_bytes = 16;
    let relay = relay_for(address, small);

    assert_eq!(
        relay
            .send(
                RelayRoute::AnthropicMessages,
                bare_upstream(),
                Bytes::from(vec![b'a'; 64]),
            )
            .await
            .err(),
        Some(RelayError::RequestTooLarge)
    );

    let mut exhausted = limits();
    exhausted.max_in_flight = 0;
    assert_eq!(
        relay_for(address, exhausted)
            .send(
                RelayRoute::AnthropicMessages,
                bare_upstream(),
                Bytes::from_static(b"{}"),
            )
            .await
            .err(),
        Some(RelayError::Overloaded)
    );
}

#[tokio::test]
async fn the_byte_budget_is_released_when_the_response_is_dropped() {
    let (address, _) = start_provider(TestReply::Json).await;
    let mut single = limits();
    single.max_in_flight = 1;
    let relay = relay_for(address, single);
    let body = Bytes::from_static(br#"{"model":"claude-sonnet-5"}"#);

    for _ in 0..3 {
        let response = relay
            .send(RelayRoute::AnthropicMessages, bare_upstream(), body.clone())
            .await
            .expect("each relay reuses the released slot");
        collect(response.body).await.unwrap();
    }

    assert_eq!(relay.slots.available_permits(), 1);
    assert_eq!(
        relay.bytes.available_permits(),
        permit_count(single.request_buffer_bytes)
    );
}
