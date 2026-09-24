use std::{
    convert::Infallible,
    net::SocketAddr,
    sync::{Arc, Mutex},
};

use axum::{
    body::Body,
    extract::State,
    http::{HeaderMap, Method},
    response::{IntoResponse, Response},
    routing::any,
    Router,
};
use futures_util::StreamExt;
use tokio::net::TcpListener;

use super::*;
use crate::credentials;

#[derive(Clone, Copy)]
enum Reply {
    Json,
    Redirect,
    SetsCookies,
    DelayHeaders(Duration),
    StallAfterFirstChunk,
    SlowChunks(Duration),
}

#[derive(Clone)]
struct Server {
    reply: Reply,
    seen: Arc<Mutex<Vec<(String, HeaderMap)>>>,
}

async fn handle(State(server): State<Server>, request: axum::extract::Request) -> Response {
    server.seen.lock().unwrap().push((
        format!("{} {}", request.method(), request.uri()),
        request.headers().clone(),
    ));

    let chunk = |bytes: &'static [u8]| Ok::<_, Infallible>(Bytes::from_static(bytes));
    match server.reply {
        Reply::Json => ([("content-type", "application/json")], "{}").into_response(),
        Reply::Redirect => (
            StatusCode::TEMPORARY_REDIRECT,
            [("location", "http://127.0.0.1:9/elsewhere")],
        )
            .into_response(),
        Reply::SetsCookies => (
            [
                ("set-cookie", "session=1"),
                ("alt-svc", "h3=\":443\""),
                ("x-request-id", "req_1"),
                ("connection", "keep-alive, x-private"),
                ("x-private", "1"),
            ],
            "{}",
        )
            .into_response(),
        Reply::DelayHeaders(delay) => {
            tokio::time::sleep(delay).await;
            "{}".into_response()
        }
        Reply::StallAfterFirstChunk => Body::from_stream(
            futures_util::stream::iter([chunk(b"data: 1\n\n")])
                .chain(futures_util::stream::pending()),
        )
        .into_response(),
        Reply::SlowChunks(gap) => {
            Body::from_stream(futures_util::stream::unfold(0, move |sent| async move {
                if sent == 3 {
                    return None;
                }

                tokio::time::sleep(gap).await;
                Some((chunk(b"data: x\n\n"), sent + 1))
            }))
            .into_response()
        }
    }
}

async fn serve(reply: Reply) -> (String, Server) {
    let server = Server {
        reply,
        seen: Arc::default(),
    };
    let listener = TcpListener::bind(SocketAddr::from(([127, 0, 0, 1], 0)))
        .await
        .unwrap();
    let origin = format!("http://{}", listener.local_addr().unwrap());
    let router = Router::new()
        .fallback(any(handle))
        .with_state(server.clone());
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });

    (origin, server)
}

fn deadlines(headers: Duration, idle: Duration) -> Deadlines {
    Deadlines {
        connect: Duration::from_secs(1),
        headers,
        idle,
        total: Duration::from_secs(10),
    }
}

fn limits() -> Limits {
    let deadlines = deadlines(Duration::from_secs(2), Duration::from_secs(2));

    Limits {
        max_request_bytes: 1024,
        request_buffer_bytes: 2048,
        max_in_flight: 2,
        body_read: Duration::from_secs(2),
        gateway: deadlines,
        provider: deadlines,
    }
}

fn upstreams(origin: &str, limits: Limits) -> Upstreams {
    Upstreams::new(
        Origins {
            gateway: origin,
            anthropic: origin,
            openai: origin,
        },
        limits,
        Metrics::default(),
    )
    .unwrap()
}

fn headers(pairs: &[(&str, &str)]) -> HeaderMap {
    let mut headers = HeaderMap::new();
    for (name, value) in pairs {
        headers.append(
            HeaderName::from_bytes(name.as_bytes()).unwrap(),
            value.parse().unwrap(),
        );
    }

    headers
}

fn names(headers: &HeaderMap) -> Vec<&str> {
    let mut names: Vec<_> = headers.keys().map(HeaderName::as_str).collect();
    names.sort_unstable();
    names.dedup();

    names
}

const CUSTOMER_HEADERS: &[(&str, &str)] = &[
    ("content-type", "application/json"),
    ("accept-encoding", "gzip, br"),
    ("anthropic-version", "2023-06-01"),
    ("anthropic-beta", "tools-2024"),
    ("openai-organization", "org_1"),
    ("user-agent", "sdk/1.0"),
    ("x-gradiated-api-key", "grad_customer"),
    ("x-gradiated-service-tier", "flex"),
    ("cookie", "session=1"),
    ("forwarded", "for=1.2.3.4"),
    ("x-forwarded-for", "1.2.3.4"),
    ("x-real-ip", "1.2.3.4"),
    ("x-amzn-trace-id", "Root=1"),
    ("cf-ray", "1"),
    ("host", "api.gradiated.com"),
    ("content-length", "2"),
    ("transfer-encoding", "chunked"),
    ("te", "trailers"),
    ("proxy-authorization", "Basic x"),
    ("connection", "keep-alive, x-hop-named"),
    ("x-hop-named", "1"),
];

#[test]
fn a_provider_receives_only_the_customer_key_and_content_headers() {
    for (header, value, other) in [
        ("x-api-key", "sk-ant-api03-customer", "authorization"),
        ("authorization", "Bearer sk-ant-oat01-customer", "x-api-key"),
        ("authorization", "Bearer sk-proj-customer", "x-api-key"),
        ("x-api-key", "sk-proj-customer", "authorization"),
    ] {
        let mut inbound = headers(CUSTOMER_HEADERS);
        inbound.insert(HeaderName::from_static(header), value.parse().unwrap());
        let credentials = credentials::extract(&inbound).unwrap();

        let outbound = provider_headers(&inbound, credentials.provider.as_ref().unwrap()).unwrap();

        let mut expected = vec![
            "accept-encoding",
            "anthropic-beta",
            "anthropic-version",
            "cf-ray",
            header,
            "content-type",
            "openai-organization",
            "user-agent",
            "x-gradiated-hop",
        ];
        expected.sort_unstable();
        assert_eq!(names(&outbound), expected, "{header}: {value}");
        assert_eq!(outbound[header], value);
        assert!(outbound[header].is_sensitive());
        assert!(!outbound.contains_key(other), "{header}: {value}");
        assert_eq!(outbound["accept-encoding"], "gzip, br");
    }
}

#[test]
fn a_request_that_already_crossed_the_proxy_never_relays_again() {
    let inbound = headers(&[
        ("x-api-key", "sk-ant-api03-customer"),
        ("x-gradiated-api-key", "grad_customer"),
        ("x-gradiated-hop", "1"),
    ]);
    let credentials = credentials::extract(&inbound).unwrap();

    assert_eq!(
        provider_headers(&inbound, credentials.provider.as_ref().unwrap()).err(),
        Some(UpstreamError::Loop)
    );
}

#[test]
fn the_gateway_receives_the_request_with_its_hop_headers_removed() {
    let outbound = gateway_headers(&headers(CUSTOMER_HEADERS));

    for kept in [
        "x-gradiated-api-key",
        "x-gradiated-service-tier",
        "anthropic-version",
        "content-type",
        "cookie",
        "x-forwarded-for",
    ] {
        assert!(outbound.contains_key(kept), "{kept}");
    }
    for hop in [
        "host",
        "content-length",
        "transfer-encoding",
        "te",
        "connection",
        "x-hop-named",
        "proxy-authorization",
    ] {
        assert!(!outbound.contains_key(hop), "{hop}");
    }
}

#[test]
fn only_gradiated_credentials_reach_the_gateway() {
    for (header, value, kept) in [
        ("authorization", "Bearer grad_customer", true),
        ("x-api-key", "grad_customer", true),
        ("authorization", "Bearer sk-proj-customer", false),
        ("authorization", "Bearer sk-ant-customer", false),
        ("x-api-key", "sk-ant-customer", false),
        ("x-api-key", "sk-customer", false),
        ("authorization", "Basic Z3JhZF9hOmI=", false),
        ("authorization", "bearer grad_customer", true),
        ("authorization", "BEARER  grad_customer", true),
        ("authorization", "bearer sk-ant-customer", false),
        ("x-api-key", "unknown-namespace", false),
    ] {
        let outbound = gateway_headers(&headers(&[(header, value)]));

        assert_eq!(outbound.contains_key(header), kept, "{header}: {value}");
    }
}

#[test]
fn a_provider_key_repeated_beside_a_gradiated_key_is_still_removed() {
    let outbound = gateway_headers(&headers(&[
        ("x-api-key", "grad_customer"),
        ("x-api-key", "sk-ant-customer"),
    ]));

    assert!(!outbound.contains_key("x-api-key"));
}

#[tokio::test]
async fn response_headers_drop_hop_headers_and_provider_cookies_only() {
    let (origin, _) = serve(Reply::SetsCookies).await;
    let upstreams = upstreams(&origin, limits());

    let provider = upstreams
        .to_provider(
            Provider::Anthropic,
            Method::POST,
            "/v1/messages",
            HeaderMap::new(),
            Bytes::new(),
            upstreams.admit().unwrap(),
        )
        .await
        .unwrap();
    let gateway = upstreams
        .to_gateway(
            Method::POST,
            "/v1/messages",
            HeaderMap::new(),
            Bytes::new(),
            upstreams.admit().unwrap(),
        )
        .await
        .unwrap();

    for (response, cookies_kept) in [(&provider, false), (&gateway, true)] {
        assert_eq!(response.headers["x-request-id"], "req_1");
        assert!(!response.headers.contains_key("connection"));
        assert!(!response.headers.contains_key("x-private"));
        assert_eq!(response.headers.contains_key("set-cookie"), cookies_kept);
        assert_eq!(response.headers.contains_key("alt-svc"), cookies_kept);
    }
}

#[tokio::test]
async fn a_provider_receives_the_method_path_and_query_the_client_used() {
    let (origin, server) = serve(Reply::Json).await;
    let upstreams = upstreams(&origin, limits());
    let requests = [
        (Provider::Anthropic, Method::POST, "/v1/messages?beta=true"),
        (
            Provider::Anthropic,
            Method::GET,
            "/v1/messages/batches?limit=2",
        ),
        (Provider::OpenAi, Method::POST, "/v1/audio/transcriptions"),
        (Provider::OpenAi, Method::DELETE, "/v1/files/file_1"),
        (Provider::OpenAi, Method::GET, "/v1/models"),
    ];

    for (provider, method, path) in &requests {
        upstreams
            .to_provider(
                *provider,
                method.clone(),
                path,
                HeaderMap::new(),
                Bytes::new(),
                upstreams.admit().unwrap(),
            )
            .await
            .unwrap();
    }

    let seen: Vec<_> = server
        .seen
        .lock()
        .unwrap()
        .iter()
        .map(|(request, _)| request.clone())
        .collect();
    let sent: Vec<_> = requests
        .iter()
        .map(|(_, method, path)| format!("{method} {path}"))
        .collect();
    assert_eq!(seen, sent);
}

#[tokio::test]
async fn the_gateway_receives_the_customer_path_and_query() {
    let (origin, server) = serve(Reply::Json).await;
    let upstreams = upstreams(&origin, limits());

    upstreams
        .to_gateway(
            Method::GET,
            "/v1/models?limit=5",
            HeaderMap::new(),
            Bytes::new(),
            upstreams.admit().unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(server.seen.lock().unwrap()[0].0, "GET /v1/models?limit=5");
}

#[tokio::test]
async fn a_redirect_is_returned_not_followed() {
    let (origin, server) = serve(Reply::Redirect).await;
    let upstreams = upstreams(&origin, limits());

    let response = upstreams
        .to_provider(
            Provider::Anthropic,
            Method::POST,
            "/v1/messages",
            HeaderMap::new(),
            Bytes::new(),
            upstreams.admit().unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status, StatusCode::TEMPORARY_REDIRECT);
    assert_eq!(server.seen.lock().unwrap().len(), 1);
}

#[tokio::test]
async fn upstream_failures_are_classified() {
    let (slow, _) = serve(Reply::DelayHeaders(Duration::from_secs(5))).await;
    let closed = {
        let listener = TcpListener::bind(SocketAddr::from(([127, 0, 0, 1], 0)))
            .await
            .unwrap();
        format!("http://{}", listener.local_addr().unwrap())
    };
    let mut quick_headers = limits();
    quick_headers.provider = deadlines(Duration::from_millis(200), Duration::from_secs(2));
    quick_headers.gateway = quick_headers.provider;

    for (origin, expected) in [
        (closed, UpstreamError::Unavailable),
        (slow, UpstreamError::Timeout),
    ] {
        let upstreams = upstreams(&origin, quick_headers);

        let provider = upstreams
            .to_provider(
                Provider::OpenAi,
                Method::POST,
                "/v1/responses",
                HeaderMap::new(),
                Bytes::new(),
                upstreams.admit().unwrap(),
            )
            .await;
        let gateway = upstreams
            .to_gateway(
                Method::POST,
                "/v1/chat/completions",
                HeaderMap::new(),
                Bytes::new(),
                upstreams.admit().unwrap(),
            )
            .await;

        assert_eq!(provider.err(), Some(expected), "{origin}");
        assert_eq!(gateway.err(), Some(expected), "{origin}");
    }
}

#[tokio::test]
async fn the_total_deadline_counts_from_admission() {
    let (origin, _) = serve(Reply::DelayHeaders(Duration::from_millis(500))).await;
    let mut short_total = limits();
    short_total.gateway.total = Duration::from_secs(1);
    let upstreams = upstreams(&origin, short_total);

    let send = |admission| {
        upstreams.to_gateway(
            Method::POST,
            "/v1/chat/completions",
            HeaderMap::new(),
            Bytes::new(),
            admission,
        )
    };

    assert!(send(upstreams.admit().unwrap()).await.is_ok());

    let uploaded_slowly = upstreams.admit().unwrap();
    tokio::time::sleep(Duration::from_millis(800)).await;
    assert_eq!(
        send(uploaded_slowly).await.err(),
        Some(UpstreamError::Timeout)
    );
}

async fn drain(mut body: UpstreamBody) -> (usize, Option<UpstreamError>) {
    let mut chunks = 0;
    while let Some(item) = body.next().await {
        match item {
            Ok(_) => chunks += 1,
            Err(error) => return (chunks, Some(error)),
        }
    }

    (chunks, None)
}

#[tokio::test]
async fn a_silent_stream_fails_after_the_idle_deadline() {
    let (origin, _) = serve(Reply::StallAfterFirstChunk).await;
    let mut short_idle = limits();
    short_idle.provider = deadlines(Duration::from_secs(2), Duration::from_millis(200));
    let upstreams = upstreams(&origin, short_idle);

    let response = upstreams
        .to_provider(
            Provider::Anthropic,
            Method::POST,
            "/v1/messages",
            HeaderMap::new(),
            Bytes::new(),
            upstreams.admit().unwrap(),
        )
        .await
        .unwrap();
    let started = Instant::now();

    assert_eq!(
        drain(response.body).await,
        (1, Some(UpstreamError::Timeout))
    );
    assert!(started.elapsed() < Duration::from_secs(2));
}

#[tokio::test]
async fn each_chunk_resets_the_idle_deadline() {
    let (origin, _) = serve(Reply::SlowChunks(Duration::from_millis(150))).await;
    let mut idle = limits();
    idle.provider = deadlines(Duration::from_secs(2), Duration::from_millis(300));
    let upstreams = upstreams(&origin, idle);

    let response = upstreams
        .to_provider(
            Provider::Anthropic,
            Method::POST,
            "/v1/messages",
            HeaderMap::new(),
            Bytes::new(),
            upstreams.admit().unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(drain(response.body).await, (3, None));
}

#[tokio::test]
async fn the_in_flight_slots_are_held_until_the_response_body_is_dropped() {
    let (origin, _) = serve(Reply::StallAfterFirstChunk).await;
    let upstreams = upstreams(&origin, limits());

    let first = upstreams
        .to_provider(
            Provider::Anthropic,
            Method::POST,
            "/v1/messages",
            HeaderMap::new(),
            Bytes::new(),
            upstreams.admit().unwrap(),
        )
        .await
        .unwrap();
    let second = upstreams.admit().unwrap();

    assert_eq!(upstreams.admit().err(), Some(UpstreamError::Overloaded));

    drop(first);
    let third = upstreams.admit().unwrap();

    drop((second, third));
    assert!(upstreams.admit().is_ok());
}

#[test]
fn the_body_budget_bounds_buffered_bytes_across_requests() {
    let mut roomy = limits();
    roomy.max_in_flight = 10;
    let upstreams = upstreams("http://127.0.0.1:9", roomy);
    let reserve = |length| {
        let mut admission = upstreams.admit()?;
        admission.reserve(length)?;
        Ok::<_, UpstreamError>(admission)
    };

    let first = reserve(1024).unwrap();
    let mut second = reserve(512).unwrap();
    second.reserve(512).unwrap();
    assert_eq!(reserve(1).err(), Some(UpstreamError::Overloaded));
    assert!(reserve(0).is_ok());

    drop(first);
    let third = reserve(1024).unwrap();

    drop((second, third));
    assert!(reserve(2048).is_ok());
}
