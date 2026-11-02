use axum::{body::to_bytes, http::StatusCode};
use serde_json::{json, Value};
use tower::ServiceExt;

use super::*;
use crate::diagnostics::{capture::Logs, request_span};

#[tokio::test]
async fn rejected_http_requests_log_redacted_settings_without_credentials_or_input() {
    let application = support::router_for(
        true,
        Arc::new(crate::test_support::TestServingState::unknown_credential()),
    );
    let logs = Logs::default();
    let _guard = logs.start();
    let response = application.oneshot(support::json_request("/v1/chat/completions",
        &[("authorization", "Bearer synthetic-credential")],
        r#"{"model":"test/model","messages":[{"role":"user","content":"synthetic private input"}],"temperature":0.7,"max_tokens":128}"#,
    )).await.unwrap();

    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    let events = logs.events();
    let request = events
        .iter()
        .find(|e| e["fields"]["stage"] == "client_request")
        .unwrap();
    let body: Value = serde_json::from_str(request["fields"]["body"].as_str().unwrap()).unwrap();
    assert_eq!(body["temperature"], 0.7);
    assert_eq!(body["max_tokens"], 128);
    assert_eq!(body["messages"][0]["content"], "[redacted]");
    assert!(events
        .iter()
        .any(|e| e["fields"]["stage"] == "client_error" && e["fields"]["http_status"] == 401));
    assert!(!json!(events).to_string().contains("synthetic"));
}

#[tokio::test]
async fn streamed_body_logs_keep_request_correlation_when_polled_after_the_handler_returns() {
    let logs = Logs::default();
    let _guard = logs.start();
    let id = uuid::Uuid::from_u128(10);
    let span = request_span(id, &HeaderMap::new());
    let chunk = StreamItem::Chunk(json!({"id":"chatcmpl-1", "object":"chat.completion.chunk",
        "created":1,"model":"test/model", "choices":[{"index":0,
        "delta":{"role":"assistant","content":"synthetic private output"}, "finish_reason":null}]}));
    let response = span.in_scope(|| {
        sse_response(
            Protocol::OpenAiChat,
            futures_util::stream::iter(vec![chunk, StreamItem::Done]),
        )
    });
    let wire = to_bytes(response.into_body(), 16_384).await.unwrap();

    assert!(String::from_utf8(wire.to_vec())
        .unwrap()
        .contains("synthetic private output"));
    let events = logs.events();
    let body = events
        .iter()
        .find(|e| e["fields"]["stage"] == "client_response_frame")
        .unwrap();
    assert_eq!(body["span"]["generation_id"], id.to_string());
    assert!(!json!(events).to_string().contains("synthetic"));
}

#[tokio::test]
async fn client_body_diagnostics_include_identity_when_authorization_resolves_it() {
    let mut state = crate::test_support::TestServingState::ready();
    state.workspace.as_mut().unwrap().archived_at = Some(chrono::Utc::now());
    let app = support::router_for(true, Arc::new(state));
    let logs = Logs::default();
    let _guard = logs.start();
    app.oneshot(support::json_request(
        "/v1/chat/completions",
        &[("authorization", "Bearer grad_DO_NOT_LOG_THIS")],
        r#"{"model":"model-a","messages":[{"role":"user","content":"synthetic private input"}]}"#,
    ))
    .await
    .unwrap();
    let events = logs.events();
    let request = events
        .iter()
        .find(|e| e["fields"]["stage"] == "client_request")
        .unwrap();
    assert_eq!(
        request["span"]["organization_id"],
        crate::test_support::ORGANIZATION_ID.to_string()
    );
    assert!(!json!(events).to_string().contains("synthetic"));
}
