use std::{net::SocketAddr, time::Duration};

use axum::http::{HeaderMap, HeaderName, HeaderValue, StatusCode};
use futures_util::StreamExt;
use tokio::net::TcpListener;

use super::{
    support::{start_provider, TestReply, CUSTOMER_KEY, JSON_REPLY},
    *,
};

fn credential() -> ProviderCredential<'static> {
    ProviderCredential {
        provider: Provider::Anthropic,
        secret: CUSTOMER_KEY,
    }
}

fn limits() -> ProxyLimits {
    crate::GatewayConfig::for_tests().proxy_limits()
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
fn the_customer_credential_is_marked_sensitive() {
    let upstream = upstream_headers(
        &HeaderMap::new(),
        RelayRoute::AnthropicMessages,
        &credential(),
    )
    .unwrap();

    assert!(upstream.get("x-api-key").unwrap().is_sensitive());
}

#[test]
fn relay_failures_map_to_public_errors() {
    for (error, expected) in [
        (RelayError::Unavailable, GatewayError::ProviderUnavailable),
        (RelayError::Timeout, GatewayError::ProviderTimeout),
        (RelayError::Overloaded, GatewayError::ProxyOverloaded),
        (RelayError::RequestTooLarge, GatewayError::PayloadTooLarge),
    ] {
        assert_eq!(GatewayError::from(error), expected, "{error:?}");
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

async fn send(relay: &ProviderRelay, body: &'static [u8]) -> Result<RelayResponse, RelayError> {
    relay
        .send(
            RelayRoute::AnthropicMessages,
            bare_upstream(),
            Bytes::from_static(body),
        )
        .await
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
    assert_eq!(collect(response.body).await.unwrap(), JSON_REPLY.as_bytes());

    let seen = provider.headers().unwrap();
    assert_eq!(seen.get("x-api-key").unwrap(), CUSTOMER_KEY);
    assert!(seen.get("x-gradiated-api-key").is_none());
    assert_eq!(
        provider.body().unwrap(),
        request.to_vec(),
        "the provider must receive the caller's bytes unchanged"
    );
}

#[tokio::test]
async fn a_streaming_relay_preserves_provider_frames() {
    let (address, _) = start_provider(TestReply::Stream).await;

    let response = send(
        &relay_for(address, limits()),
        br#"{"model":"claude-sonnet-5","stream":true}"#,
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

    let response = send(
        &relay_for(address, limits()),
        br#"{"model":"claude-sonnet-5"}"#,
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

    let response = send(
        &relay_for(address, limits()),
        br#"{"model":"claude-sonnet-5"}"#,
    )
    .await
    .unwrap();

    assert_eq!(response.status, StatusCode::TEMPORARY_REDIRECT);
}

#[tokio::test]
async fn an_oversized_request_or_a_full_slot_pool_is_refused_before_dispatch() {
    let (address, _) = start_provider(TestReply::Json).await;
    let mut small = limits();
    small.max_request_bytes = 16;

    assert_eq!(
        send(&relay_for(address, small), &[b'a'; 64]).await.err(),
        Some(RelayError::RequestTooLarge)
    );

    let mut exhausted = limits();
    exhausted.max_in_flight = 0;

    assert_eq!(
        send(&relay_for(address, exhausted), b"{}").await.err(),
        Some(RelayError::Overloaded)
    );
}

#[tokio::test]
async fn an_exhausted_byte_budget_is_refused_before_dispatch() {
    let (address, provider) = start_provider(TestReply::Json).await;
    let mut tight = limits();
    tight.request_buffer_bytes = 8;
    tight.max_request_bytes = 1024;

    assert_eq!(
        send(&relay_for(address, tight), &[b'a'; 64]).await.err(),
        Some(RelayError::Overloaded)
    );
    assert!(provider.headers().is_none());
}

#[tokio::test]
async fn the_byte_budget_is_released_when_the_response_is_dropped() {
    let (address, _) = start_provider(TestReply::Json).await;
    let mut single = limits();
    single.max_in_flight = 1;
    let relay = relay_for(address, single);

    for _ in 0..3 {
        let response = send(&relay, br#"{"model":"claude-sonnet-5"}"#)
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

#[tokio::test]
async fn a_slow_response_header_times_out() {
    let (address, _) = start_provider(TestReply::Delayed(Duration::from_millis(500))).await;
    let mut impatient = limits();
    impatient.response_header_timeout = Duration::from_millis(50);

    assert_eq!(
        send(&relay_for(address, impatient), b"{}").await.err(),
        Some(RelayError::Timeout)
    );
}

#[tokio::test]
async fn a_refused_connection_is_unavailable_and_releases_its_permits() {
    let listener = TcpListener::bind(SocketAddr::from(([127, 0, 0, 1], 0)))
        .await
        .unwrap();
    let address = listener.local_addr().unwrap();
    drop(listener);
    let configured = limits();
    let relay = relay_for(address, configured);

    assert_eq!(
        send(&relay, b"{}").await.err(),
        Some(RelayError::Unavailable)
    );

    assert_eq!(
        relay.slots.available_permits(),
        permit_count(configured.max_in_flight)
    );
    assert_eq!(
        relay.bytes.available_permits(),
        permit_count(configured.request_buffer_bytes)
    );
}

#[tokio::test]
async fn a_stream_that_stalls_mid_response_times_out() {
    let (address, _) = start_provider(TestReply::StallAfterFirstChunk).await;
    let mut idle = limits();
    idle.idle_timeout = Duration::from_millis(100);

    let response = send(&relay_for(address, idle), b"{}").await.unwrap();

    assert_eq!(
        collect(response.body).await.err(),
        Some(RelayError::Timeout)
    );
}
