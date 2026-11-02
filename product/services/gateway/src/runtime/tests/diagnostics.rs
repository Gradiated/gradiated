use axum::http::StatusCode;
use serde_json::{json, Value};

use super::support::{client, data, deadline, streaming_request, MockRuntime, CHAT, DONE};
use crate::{
    diagnostics::capture::Logs, runtime::ModelRuntime, InferenceRequest, RuntimeFailureKind,
};

fn body_event(logs: &Logs, stage: &str) -> Value {
    let event = logs
        .events()
        .into_iter()
        .find(|event| {
            event["fields"]["event"] == "inference_body" && event["fields"]["stage"] == stage
        })
        .expect("body diagnostic exists");
    serde_json::from_str(event["fields"]["body"].as_str().unwrap()).unwrap()
}

#[tokio::test]
async fn rejected_requests_keep_effective_settings_and_upstream_validation_metadata() {
    let runtime = MockRuntime::builder().json(CHAT, StatusCode::BAD_REQUEST, json!({
        "error": {"code": 400, "type": "BadRequestError", "param": "temperature",
            "message": "temperature invalid: synthetic private input", "input": "synthetic private echo"}
    })).start().await;
    let request = InferenceRequest::parse(br#"{"model":"model-a","messages":[{"role":"user","content":"synthetic private prompt"}],"temperature":0.25}"#).unwrap();
    let logs = Logs::default();
    let _guard = logs.start();

    let failure = client()
        .complete(&runtime.deployment(), request, 256, deadline(5))
        .await
        .unwrap_err();
    assert_eq!(failure.kind(), RuntimeFailureKind::InvalidRequest);
    let request = body_event(&logs, "runtime_request");
    assert_eq!(request["max_completion_tokens"], 256);
    assert_eq!(request["temperature"], 0.25);
    assert_eq!(request["messages"][0]["content"], "[redacted]");
    let response = body_event(&logs, "runtime_response");
    assert_eq!(response["error"]["code"], 400);
    assert_eq!(response["error"]["param"], "temperature");
    assert_eq!(response["error"]["message"]["reason"], "sampling_parameter");
    let events = json!(logs.events()).to_string();
    assert!(!events.contains("synthetic"));
    assert!(!events.contains("runtime-secret"));
}

#[tokio::test]
async fn malformed_stream_usage_is_logged_before_normalization_rejects_it() {
    let first = json!({"id":"chatcmpl-test", "object":"chat.completion.chunk", "model":"runtime-model", "created":1,
        "choices":[{"index":0,"delta":{"content":"synthetic private output","usage":{"total_tokens":123456789}},"finish_reason":null}]});
    let invalid = json!({"id":"chatcmpl-test", "object":"chat.completion.chunk", "model":"runtime-model", "created":1,
        "choices":[],"item":{"usage":{"total_tokens":123456789}},"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":999}});
    let runtime = MockRuntime::builder()
        .sse(CHAT, &[data(&first), data(&invalid), DONE.into()])
        .start()
        .await;
    let logs = Logs::default();
    let _guard = logs.start();
    let mut stream = client()
        .stream(
            &runtime.renamed_deployment(),
            streaming_request(),
            32,
            deadline(5),
        )
        .await
        .unwrap();
    stream.next_event().await.unwrap();
    let failure = stream.next_event().await.unwrap_err();

    assert_eq!(failure.kind(), RuntimeFailureKind::ProtocolViolation);
    assert_eq!(
        body_event(&logs, "runtime_response_invalid_frame")["usage"]["total_tokens"],
        999
    );
    assert!(logs
        .events()
        .iter()
        .any(|event| event["fields"]["diagnostic_code"] == "usage"));
    assert!(!json!(logs.events()).to_string().contains("synthetic"));
    assert!(!json!(logs.events()).to_string().contains("123456789"));
}

#[tokio::test]
async fn streaming_diagnostics_do_not_emit_a_log_per_token() {
    let chunk = |delta: Value, finish: Option<&str>| {
        json!({"id":"chatcmpl-test", "object":"chat.completion.chunk", "model":"runtime-model", "created":1,
        "choices":[{"index":0,"delta":delta,"finish_reason":finish}]})
    };
    let mut frames = vec![data(&chunk(json!({"content":"synthetic private output"}), None)); 100];
    frames.push(data(&chunk(json!({}), Some("stop"))));
    frames.push(data(&json!({"id":"chatcmpl-test", "object":"chat.completion.chunk", "model":"runtime-model", "created":1,
        "choices":[],"usage":{"prompt_tokens":10,"completion_tokens":100,"total_tokens":110}})));
    frames.push(DONE.into());
    let runtime = MockRuntime::builder().sse(CHAT, &frames).start().await;
    let logs = Logs::default();
    let _guard = logs.start();
    let mut stream = client()
        .stream(
            &runtime.renamed_deployment(),
            streaming_request(),
            256,
            deadline(5),
        )
        .await
        .unwrap();
    while stream.next_event().await.unwrap().is_some() {}

    let events = logs.events();
    assert_eq!(
        events
            .iter()
            .filter(|event| event["fields"]["event"] == "inference_body")
            .count(),
        4
    );
    assert!(!json!(events).to_string().contains("synthetic"));
}

#[tokio::test]
async fn inspecting_an_error_body_cannot_stall_a_capacity_retry() {
    use axum::{body::Body, response::Response, routing::post};
    use futures_util::{stream, StreamExt};

    let runtime = MockRuntime::builder()
        .route(
            CHAT,
            post(|| async {
                let first = stream::once(async { Ok::<_, std::io::Error>("{\"error\":") });
                let body = first.chain(stream::pending());
                Response::builder()
                    .status(StatusCode::SERVICE_UNAVAILABLE)
                    .body(Body::from_stream(body))
                    .unwrap()
            }),
        )
        .start()
        .await;
    let logs = Logs::default();
    let _guard = logs.start();
    assert!(tracing::enabled!(tracing::Level::INFO));
    let response = reqwest::Client::new()
        .post(format!("{}{CHAT}", runtime.url()))
        .body("{}")
        .send()
        .await
        .unwrap();
    let failure = tokio::time::timeout(
        std::time::Duration::from_secs(2),
        crate::runtime::client::rejected_response(response),
    )
    .await
    .expect("diagnostics release the response within 250ms");

    assert_eq!(failure.kind(), RuntimeFailureKind::CapacityExceeded);
    assert_eq!(
        failure.gateway_error().status(),
        StatusCode::TOO_MANY_REQUESTS
    );
}
