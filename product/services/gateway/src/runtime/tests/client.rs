use std::{path::PathBuf, time::Duration};

use axum::{
    body::Body,
    http::{header, StatusCode},
    response::Response,
    routing::post,
};
use futures_util::{stream, StreamExt};
use serde_json::json;
use uuid::Uuid;

use super::support::{
    chat_request, client, data, deadline, decision_request, streaming_request, MockRuntime, CHAT,
    DONE, SYSTEMONE,
};
use crate::{
    runtime::{
        client::one_shot_body, ModelRuntime, RuntimeClientError, RuntimeFailure,
        RuntimeFailureKind, RuntimeStreamEvent, RuntimeTlsConfig, SglangClient,
    },
    GatewayError, ModelTokenizer, NormalizedUsage,
};

#[test]
fn runtime_tls_paths_are_optional_as_one_group() {
    assert_eq!(
        RuntimeTlsConfig::from_paths(None, None, None).unwrap(),
        None
    );

    let config = RuntimeTlsConfig::from_paths(
        Some(PathBuf::from("ca.crt")),
        Some(PathBuf::from("client.crt")),
        Some(PathBuf::from("client.key")),
    )
    .unwrap()
    .unwrap();
    assert_eq!(config.ca_certificate_path, PathBuf::from("ca.crt"));
    assert_eq!(config.client_certificate_path, PathBuf::from("client.crt"));
    assert_eq!(config.client_key_path, PathBuf::from("client.key"));
}

#[test]
fn runtime_tls_rejects_partial_path_groups() {
    for paths in [
        (Some(PathBuf::from("ca.crt")), None, None),
        (
            Some(PathBuf::from("ca.crt")),
            Some(PathBuf::from("client.crt")),
            None,
        ),
        (None, None, Some(PathBuf::from("client.key"))),
    ] {
        assert!(matches!(
            RuntimeTlsConfig::from_paths(paths.0, paths.1, paths.2),
            Err(RuntimeClientError::IncompleteTlsConfiguration)
        ));
    }
}

fn tls_config(directory: &std::path::Path) -> RuntimeTlsConfig {
    RuntimeTlsConfig::from_paths(
        Some(directory.join("ca.crt")),
        Some(directory.join("client.crt")),
        Some(directory.join("client.key")),
    )
    .unwrap()
    .unwrap()
}

#[test]
fn runtime_tls_reports_an_unreadable_file_by_path() {
    let directory = std::env::temp_dir().join(format!("gateway-tls-{}", Uuid::now_v7()));

    let error = SglangClient::with_tokenizer_and_tls(
        None,
        ModelTokenizer::new().unwrap(),
        Some(&tls_config(&directory)),
    )
    .err()
    .unwrap();

    assert!(
        matches!(error, RuntimeClientError::TlsFile { path, .. } if path == directory.join("ca.crt"))
    );
}

#[test]
fn runtime_tls_rejects_invalid_pem() {
    let directory = std::env::temp_dir().join(format!("gateway-tls-{}", Uuid::now_v7()));
    std::fs::create_dir(&directory).unwrap();
    for file in ["ca.crt", "client.crt", "client.key"] {
        std::fs::write(directory.join(file), "not a pem file").unwrap();
    }

    let error = SglangClient::with_tokenizer_and_tls(
        None,
        ModelTokenizer::new().unwrap(),
        Some(&tls_config(&directory)),
    )
    .err()
    .unwrap();
    std::fs::remove_dir_all(&directory).unwrap();

    assert!(matches!(error, RuntimeClientError::Request(_)));
}

#[tokio::test]
async fn dispatch_rejects_a_request_the_release_cannot_serve_before_sending() {
    let runtime = MockRuntime::builder()
        .json(CHAT, StatusCode::OK, json!({}))
        .json(SYSTEMONE, StatusCode::OK, json!({}))
        .start()
        .await;
    let chat = runtime.deployment();
    let system_one = runtime.system_one_deployment();
    let client = client();

    let completions = [
        ("decision to a chat release", &chat, decision_request(), 0),
        (
            "chat to a SystemOne release",
            &system_one,
            chat_request(),
            8,
        ),
        ("stream to complete", &chat, streaming_request(), 8),
        ("chat without output tokens", &chat, chat_request(), 0),
        (
            "decision with output tokens",
            &system_one,
            decision_request(),
            8,
        ),
    ];
    for (case, deployment, request, output_tokens) in completions {
        let failure = client
            .complete(deployment, request, output_tokens, deadline(5))
            .await
            .unwrap_err();

        assert_eq!(
            failure.kind(),
            RuntimeFailureKind::ProtocolViolation,
            "{case}"
        );
    }

    let streams = [
        ("non-streaming request to stream", &chat, chat_request(), 8),
        (
            "stream without output tokens",
            &chat,
            streaming_request(),
            0,
        ),
        ("decision to stream", &system_one, decision_request(), 0),
    ];
    for (case, deployment, request, output_tokens) in streams {
        let failure = client
            .stream(deployment, request, output_tokens, deadline(5))
            .await
            .err()
            .unwrap();

        assert_eq!(
            failure.kind(),
            RuntimeFailureKind::ProtocolViolation,
            "{case}"
        );
    }

    assert!(runtime.requests().is_empty());
}

#[tokio::test]
async fn classifies_rejected_statuses_and_retains_valid_usage() {
    let body = json!({
        "error": {"message": "queue full"},
        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}
    });

    for (status, kind, gateway_error) in [
        (
            StatusCode::BAD_REQUEST,
            RuntimeFailureKind::InvalidRequest,
            GatewayError::invalid_request(None),
        ),
        (
            StatusCode::UNPROCESSABLE_ENTITY,
            RuntimeFailureKind::InvalidRequest,
            GatewayError::invalid_request(None),
        ),
        (
            StatusCode::TOO_MANY_REQUESTS,
            RuntimeFailureKind::CapacityExceeded,
            GatewayError::CapacityExceeded,
        ),
        (
            StatusCode::SERVICE_UNAVAILABLE,
            RuntimeFailureKind::CapacityExceeded,
            GatewayError::CapacityExceeded,
        ),
        (
            StatusCode::BAD_GATEWAY,
            RuntimeFailureKind::Unavailable,
            GatewayError::RuntimeUnavailable,
        ),
    ] {
        let runtime = MockRuntime::builder()
            .json(CHAT, status, body.clone())
            .start()
            .await;

        let failure = client()
            .complete(&runtime.deployment(), chat_request(), 1_024, deadline(5))
            .await
            .unwrap_err();

        assert_eq!(failure.kind(), kind, "{status}");
        assert_eq!(failure.gateway_error(), gateway_error);
        assert_eq!(failure.upstream_status(), Some(status.as_u16()));
        assert_eq!(failure.usage().input_tokens(), 2);
        assert_eq!(failure.usage().output_tokens(), 1);
        assert_eq!(runtime.requests().len(), 1);
    }
}

#[tokio::test]
async fn rejection_without_valid_usage_keeps_zero_usage_and_the_status() {
    let unreadable = MockRuntime::builder()
        .truncated(
            CHAT,
            StatusCode::TOO_MANY_REQUESTS,
            "application/json",
            "{\"usage\"".to_owned(),
        )
        .start()
        .await;
    let invalid = MockRuntime::builder()
        .json(
            CHAT,
            StatusCode::TOO_MANY_REQUESTS,
            json!({"usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 9}}),
        )
        .start()
        .await;

    for runtime in [unreadable, invalid] {
        let failure = client()
            .complete(&runtime.deployment(), chat_request(), 1_024, deadline(5))
            .await
            .unwrap_err();

        assert_eq!(failure.kind(), RuntimeFailureKind::CapacityExceeded);
        assert_eq!(failure.upstream_status(), Some(429));
        assert_eq!(failure.usage(), NormalizedUsage::zero());
    }
}

fn declared_oversized_body() -> Response {
    Response::builder()
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::CONTENT_LENGTH, "8000001")
        .body(Body::from_stream(stream::pending::<
            Result<Vec<u8>, std::io::Error>,
        >()))
        .unwrap()
}

fn undeclared_oversized_body() -> Response {
    let chunks = stream::iter((0..9).map(|_| Ok::<_, std::io::Error>(vec![b' '; 1_000_000])));

    Response::builder()
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from_stream(chunks))
        .unwrap()
}

#[tokio::test]
async fn refuses_a_response_body_over_the_limit() {
    for (respond, code) in [
        (
            declared_oversized_body as fn() -> Response,
            "declared_too_large",
        ),
        (undeclared_oversized_body, "streamed_too_large"),
    ] {
        let runtime = MockRuntime::builder()
            .route(CHAT, post(move || async move { respond() }))
            .start()
            .await;

        let failure = client()
            .complete(&runtime.deployment(), chat_request(), 1_024, deadline(5))
            .await
            .unwrap_err();

        assert_eq!(failure.kind(), RuntimeFailureKind::ResponseTooLarge);
        assert_eq!(failure.diagnostic_code(), code);
    }
}

#[tokio::test]
async fn streams_past_the_buffered_response_limit() {
    let chunk = |delta: serde_json::Value, finish_reason: Option<&str>| {
        data(&json!({
            "id": "chatcmpl-1", "object": "chat.completion.chunk", "created": 1, "model": "model-a",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]
        }))
    };
    let mut frames = vec![chunk(json!({"content": "x".repeat(990_000)}), None); 9];
    frames.push(chunk(json!({}), Some("stop")));
    frames.push(data(&json!({
        "id": "chatcmpl-1", "object": "chat.completion.chunk", "created": 1, "model": "model-a",
        "choices": [],
        "usage": {"prompt_tokens": 1, "completion_tokens": 9, "total_tokens": 10}
    })));
    frames.push(DONE.to_owned());
    let runtime = MockRuntime::builder().sse(CHAT, &frames).start().await;

    let mut events = client()
        .stream(
            &runtime.deployment(),
            streaming_request(),
            1_024,
            deadline(5),
        )
        .await
        .unwrap();
    let mut chunks = 0;
    while let Some(event) = events.next_event().await.unwrap() {
        match event {
            RuntimeStreamEvent::Chunk(_) => chunks += 1,
            RuntimeStreamEvent::Done => break,
        }
    }

    assert_eq!(chunks, 11);
}

#[tokio::test]
async fn a_body_cut_after_acceptance_is_an_interruption_without_retry() {
    let chat = MockRuntime::builder()
        .truncated(
            CHAT,
            StatusCode::OK,
            "application/json",
            "{\"id\":\"x\",".to_owned(),
        )
        .start()
        .await;
    let system_one = MockRuntime::builder()
        .truncated(
            SYSTEMONE,
            StatusCode::OK,
            "application/json",
            "{\"model\":".to_owned(),
        )
        .start()
        .await;
    let client = client();

    for (case, deployment, request, output_tokens) in [
        ("chat", chat.deployment(), chat_request(), 1_024),
        (
            "SystemOne",
            system_one.system_one_deployment(),
            decision_request(),
            0,
        ),
    ] {
        let failure = client
            .complete(&deployment, request, output_tokens, deadline(5))
            .await
            .unwrap_err();

        assert_eq!(failure.kind(), RuntimeFailureKind::Interrupted, "{case}");
        assert_eq!(failure.diagnostic_code(), "connection_closed", "{case}");
        assert_eq!(failure.usage(), NormalizedUsage::zero(), "{case}");
        assert_eq!(failure.gateway_error(), GatewayError::RuntimeUnavailable);
    }
}

#[tokio::test]
async fn refuses_execution_after_the_deadline_without_sending() {
    let runtime = MockRuntime::builder()
        .json(CHAT, StatusCode::OK, json!({}))
        .start()
        .await;
    let client = client();

    let completion = client
        .complete(&runtime.deployment(), chat_request(), 1_024, deadline(-1))
        .await
        .unwrap_err();
    let stream = client
        .stream(
            &runtime.deployment(),
            streaming_request(),
            1_024,
            deadline(-1),
        )
        .await
        .err()
        .unwrap();

    for failure in [completion, stream] {
        assert_eq!(failure.kind(), RuntimeFailureKind::TimedOut);
        assert_eq!(failure.diagnostic_code(), "deadline");
    }
    assert!(runtime.requests().is_empty());
}

#[tokio::test]
async fn times_out_when_the_runtime_never_answers() {
    let runtime = MockRuntime::builder()
        .route(CHAT, post(std::future::pending::<Response>))
        .start()
        .await;
    let client = client();

    let completion = client
        .complete(&runtime.deployment(), chat_request(), 1_024, deadline(1))
        .await
        .unwrap_err();
    let stream = client
        .stream(
            &runtime.deployment(),
            streaming_request(),
            1_024,
            deadline(1),
        )
        .await
        .err()
        .unwrap();

    for failure in [completion, stream] {
        assert_eq!(failure.kind(), RuntimeFailureKind::TimedOut);
        assert_eq!(failure.diagnostic_code(), "deadline");
    }
}

fn dripping_rejection() -> Response {
    let first = stream::iter([Ok::<_, std::io::Error>(b"{".to_vec())]);

    Response::builder()
        .status(StatusCode::BAD_REQUEST)
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from_stream(first.chain(stream::pending())))
        .unwrap()
}

#[tokio::test]
async fn a_slow_rejected_body_cannot_hold_a_stream_open_past_the_deadline() {
    let runtime = MockRuntime::builder()
        .route(CHAT, post(|| async { dripping_rejection() }))
        .start()
        .await;

    let opened = tokio::time::timeout(
        Duration::from_secs(5),
        client().stream(
            &runtime.deployment(),
            streaming_request(),
            1_024,
            deadline(1),
        ),
    )
    .await
    .expect("opening the stream overran the request deadline");
    let failure = opened.err().unwrap();

    assert_eq!(failure.kind(), RuntimeFailureKind::TimedOut);
    assert_eq!(failure.diagnostic_code(), "deadline");
}

#[tokio::test]
async fn does_not_follow_a_runtime_redirect() {
    let runtime = MockRuntime::builder()
        .redirect(CHAT, "/redirected")
        .json("/redirected", StatusCode::OK, json!({}))
        .start()
        .await;

    let failure = client()
        .complete(&runtime.deployment(), chat_request(), 1_024, deadline(5))
        .await
        .unwrap_err();

    assert_eq!(failure.kind(), RuntimeFailureKind::Unavailable);
    let paths: Vec<_> = runtime
        .requests()
        .into_iter()
        .map(|request| request.path)
        .collect();
    assert_eq!(paths, [CHAT]);
}

fn logged_attempt(failure: &RuntimeFailure) -> serde_json::Value {
    let logs = crate::diagnostics::capture::Logs::default();
    let _guard = logs.start();

    failure.log_attempt(
        Uuid::from_u128(1),
        "hosted-model",
        Some(Uuid::from_u128(2)),
        "local",
        1,
        20,
        None,
    );

    let events = logs.events();
    assert_eq!(events.len(), 1);
    events[0].clone()
}

async fn closed_port_url() -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    drop(listener);

    format!("http://{address}/private-path")
}

#[tokio::test]
async fn each_failure_logs_one_bounded_diagnostic_code() {
    let mismatch = MockRuntime::builder()
        .json(
            CHAT,
            StatusCode::OK,
            json!({
                "id": "chatcmpl-1", "object": "chat.completion", "created": 1,
                "model": "private-runtime-model",
                "choices": [{"index": 0, "message": {"content": "private text"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
            }),
        )
        .start()
        .await;
    let framing = MockRuntime::builder()
        .sse(CHAT, &["event: private-name\ndata: {}\n\n".to_owned()])
        .start()
        .await;
    let busy = MockRuntime::builder()
        .json(
            CHAT,
            StatusCode::SERVICE_UNAVAILABLE,
            json!({"error": "private queue full"}),
        )
        .start()
        .await;
    let client = client();

    let model_mismatch = client
        .complete(&mismatch.deployment(), chat_request(), 1_024, deadline(5))
        .await
        .unwrap_err();
    let sse_framing = match client
        .stream(
            &framing.deployment(),
            streaming_request(),
            1_024,
            deadline(5),
        )
        .await
    {
        Ok(mut events) => events.next_event().await.unwrap_err(),
        Err(failure) => failure,
    };
    let status = client
        .complete(&busy.deployment(), chat_request(), 1_024, deadline(5))
        .await
        .unwrap_err();
    let connect = client
        .complete(
            &super::support::deployment(closed_port_url().await),
            chat_request(),
            1_024,
            deadline(5),
        )
        .await
        .unwrap_err();

    for (failure, diagnostic_code, upstream_status) in [
        (model_mismatch, "model_mismatch", json!(null)),
        (sse_framing, "sse_framing", json!(null)),
        (status, "upstream_status", json!(503)),
        (connect, "connect", json!(null)),
    ] {
        let event = logged_attempt(&failure);
        let text = event.to_string();

        assert_eq!(event["fields"]["diagnostic_code"], diagnostic_code);
        assert_eq!(
            event["fields"]
                .get("upstream_status")
                .cloned()
                .unwrap_or_default(),
            upstream_status,
            "{diagnostic_code}"
        );
        assert!(!text.contains("private"), "{diagnostic_code}: {text}");
    }
}

#[tokio::test]
async fn transport_diagnostic_drops_private_url_and_correlates_attempt() {
    // Keep a local TCP listener open without responding: DNS failures must not
    // race the timeout, and proxy settings must not route this fixture elsewhere.
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let error = reqwest::Client::builder()
        .no_proxy()
        .resolve("private-runtime.invalid", address)
        .build()
        .unwrap()
        .get(format!(
            "http://private-runtime.invalid:{}/secret-path",
            address.port()
        ))
        .timeout(Duration::from_millis(50))
        .send()
        .await
        .unwrap_err();
    let failure = RuntimeFailure::from_transport(error);

    let event = logged_attempt(&failure);

    assert_eq!(
        event["fields"]["generation_id"],
        Uuid::from_u128(1).to_string()
    );
    assert_eq!(event["fields"]["diagnostic_code"], "timeout");
    assert_eq!(failure.diagnostic_code(), "timeout");
    assert!(!event.to_string().contains("private-runtime"));
    assert!(!format!("{failure:?}").contains("secret-path"));
}

#[test]
fn request_body_is_not_replayable() {
    assert!(one_shot_body(b"private prompt".to_vec())
        .as_bytes()
        .is_none());
}

#[tokio::test]
async fn broken_http_responses_have_safe_specific_diagnostics() {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    for (response, expected) in [
        ("HTTP/1.1 200 OK\r\nContent-Length:", "incomplete_response"),
        ("private-invalid-status\r\n\r\n", "invalid_http_response"),
    ] {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut request = [0; 4096];
            assert!(socket.read(&mut request).await.unwrap() > 0);
            socket.write_all(response.as_bytes()).await.unwrap();
            socket.shutdown().await.unwrap();
        });
        let error = reqwest::Client::new()
            .get(format!("http://{address}/private-path"))
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .unwrap_err();
        server.await.unwrap();
        let failure = RuntimeFailure::from_transport(error);

        assert_eq!(failure.diagnostic_code(), expected);
        assert!(!format!("{failure:?}").contains("private"));
    }
}

#[tokio::test]
async fn http2_reset_has_a_safe_specific_diagnostic() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let server = tokio::spawn(async move {
        let (socket, _) = listener.accept().await.unwrap();
        let mut connection = h2::server::handshake(socket).await.unwrap();
        let (_, mut response) = connection.accept().await.unwrap().unwrap();
        response.send_reset(h2::Reason::PROTOCOL_ERROR);
        while connection.accept().await.is_some() {}
    });
    let error = reqwest::Client::builder()
        .http2_prior_knowledge()
        .build()
        .unwrap()
        .get(format!("http://{address}/private-path"))
        .timeout(Duration::from_secs(5))
        .send()
        .await
        .unwrap_err();
    server.abort();
    let failure = RuntimeFailure::from_transport(error);

    assert_eq!(failure.diagnostic_code(), "http2_reset");
    assert!(!format!("{failure:?}").contains("private"));
}

#[tokio::test]
async fn a_truncated_body_preserves_its_connection_diagnostic() {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let server = tokio::spawn(async move {
        let (mut socket, _) = listener.accept().await.unwrap();
        let mut request = [0; 4096];
        assert!(socket.read(&mut request).await.unwrap() > 0);
        socket
            .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nprivate")
            .await
            .unwrap();
        socket.shutdown().await.unwrap();
    });
    let response = reqwest::Client::new()
        .get(format!("http://{address}/private-path"))
        .timeout(Duration::from_secs(5))
        .send()
        .await
        .unwrap();
    let error = response.bytes().await.unwrap_err();
    server.await.unwrap();
    let failure = RuntimeFailure::interrupted(error);

    assert_eq!(failure.kind(), RuntimeFailureKind::Interrupted);
    assert_eq!(failure.diagnostic_code(), "connection_closed");
    assert!(!format!("{failure:?}").contains("private"));
}
