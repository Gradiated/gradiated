use std::time::Duration;

use axum::http::{header, StatusCode};
use serde_json::{json, Value};

use super::support::{
    client_with_tokenizer, data, deadline, expect_chunk, streaming_request, MockRuntime, DONE,
};
use crate::{
    runtime::{ModelRuntime, RuntimeFailure, RuntimeFailureKind, RuntimeStreamEvent, SglangClient},
    tokenizer::test_support::{
        byte_fallback, rewriting_prefix, unavailable, Hub, E_ACUTE, TOKEN_H, TOKEN_I,
    },
    GatewayError, GatewayModelDeployment, InferenceRequest, ModelTokenizer,
};

const TOKEN_COMPLETIONS: &str = "/v1/token-completions";
const INPUT_IDS: [u32; 3] = [5, 6, 7];

fn native(runtime: &MockRuntime) -> (GatewayModelDeployment, SglangClient) {
    native_with(runtime, byte_fallback)
}

fn native_with(
    runtime: &MockRuntime,
    tokenizer: impl FnOnce(&crate::ModelDeploymentRelease) -> ModelTokenizer,
) -> (GatewayModelDeployment, SglangClient) {
    let mut deployment = runtime.deployment();
    deployment.release.runtime_revision = "native-test".to_owned();
    let client = client_with_tokenizer(tokenizer(&deployment.release));

    (deployment, client)
}

fn native_request(stream: bool) -> InferenceRequest {
    let mut request = streaming_request();
    request.stream = stream;
    request.encoded_input_ids = Some(INPUT_IDS.to_vec());

    request
}

fn usage(output_tokens: usize) -> Value {
    json!({"input_tokens": 3, "cached_input_tokens": 2, "output_tokens": output_tokens})
}

fn token(token_id: u32, output_tokens: usize) -> String {
    data(&json!({"token_id": token_id, "usage": usage(output_tokens)}))
}

fn terminal(output_tokens: usize) -> String {
    data(&json!({"finish_reason": "stop", "usage": usage(output_tokens)}))
}

fn completion(output_ids: &[u32]) -> Value {
    json!({
        "output_ids": output_ids,
        "usage": usage(output_ids.len()),
        "finish_reason": "stop",
        "timing": {"queue_ms": 1, "decode_ms": 2}
    })
}

#[tokio::test]
async fn decodes_a_token_completion_with_authoritative_usage() {
    let output_ids = [TOKEN_H, TOKEN_I, E_ACUTE[0], E_ACUTE[1]];
    let runtime = MockRuntime::builder()
        .json(TOKEN_COMPLETIONS, StatusCode::OK, completion(&output_ids))
        .start()
        .await;
    let (deployment, client) = native(&runtime);

    let completion = client
        .complete(&deployment, native_request(false), 8, deadline(5))
        .await
        .unwrap();

    assert_eq!(completion.finish_reason(), "stop");
    assert_eq!(completion.usage().input_tokens(), 3);
    assert_eq!(completion.usage().cached_input_tokens(), 2);
    assert_eq!(completion.usage().output_tokens(), 4);
    let response = completion.into_response();
    assert!(response["id"].as_str().unwrap().starts_with("chatcmpl-"));
    assert_eq!(response["model"], "model-a");
    assert_eq!(response["choices"][0]["message"]["role"], "assistant");
    assert_eq!(response["choices"][0]["message"]["content"], "hié");
    assert_eq!(response["usage"]["total_tokens"], 7);
    assert!(response.get("timing").is_none());

    let requests = runtime.requests();
    assert_eq!(requests[0].body["input_ids"], json!(INPUT_IDS));
    assert_eq!(requests[0].body["max_tokens"], 8);
    assert_eq!(requests[0].body["stream"], false);
    assert_eq!(requests[0].body["priority"], 0);
}

#[tokio::test]
async fn rejects_an_untrustworthy_token_completion() {
    let mut too_many_outputs = completion(&[TOKEN_H; 9]);
    too_many_outputs["usage"]["output_tokens"] = json!(9);
    let mut input_mismatch = completion(&[TOKEN_H]);
    input_mismatch["usage"]["input_tokens"] = json!(4);
    let mut output_mismatch = completion(&[TOKEN_H]);
    output_mismatch["usage"]["output_tokens"] = json!(2);
    let mut cached_over_input = completion(&[TOKEN_H]);
    cached_over_input["usage"]["cached_input_tokens"] = json!(4);
    let mut empty_finish_reason = completion(&[TOKEN_H]);
    empty_finish_reason["finish_reason"] = json!("");
    let mut long_finish_reason = completion(&[TOKEN_H]);
    long_finish_reason["finish_reason"] = json!("x".repeat(101));

    for (case, body) in [
        ("output past max_tokens", too_many_outputs),
        ("input count mismatch", input_mismatch),
        ("output count mismatch", output_mismatch),
        ("cached tokens over input", cached_over_input),
        ("empty finish reason", empty_finish_reason),
        ("finish reason over 100 characters", long_finish_reason),
    ] {
        let runtime = MockRuntime::builder()
            .json(TOKEN_COMPLETIONS, StatusCode::OK, body)
            .start()
            .await;
        let (deployment, client) = native(&runtime);

        let failure = client
            .complete(&deployment, native_request(false), 8, deadline(5))
            .await
            .unwrap_err();

        assert_eq!(
            failure.kind(),
            RuntimeFailureKind::ProtocolViolation,
            "{case}"
        );
    }
}

#[tokio::test]
async fn classifies_rejected_token_requests() {
    for (status, kind) in [
        (StatusCode::BAD_REQUEST, RuntimeFailureKind::InvalidRequest),
        (
            StatusCode::SERVICE_UNAVAILABLE,
            RuntimeFailureKind::CapacityExceeded,
        ),
    ] {
        let runtime = MockRuntime::builder()
            .json(TOKEN_COMPLETIONS, status, json!({"error": "rejected"}))
            .start()
            .await;
        let (deployment, client) = native(&runtime);

        let completion = client
            .complete(&deployment, native_request(false), 8, deadline(5))
            .await
            .unwrap_err();
        let stream = client
            .stream(&deployment, native_request(true), 8, deadline(5))
            .await
            .err()
            .unwrap();

        assert_eq!(completion.kind(), kind, "{status}");
        assert_eq!(stream.kind(), kind, "{status}");
        assert_eq!(completion.upstream_status(), Some(status.as_u16()));
    }
}

#[tokio::test]
async fn token_requests_are_length_delimited_for_the_cpp_runtime() {
    let runtime = MockRuntime::builder()
        .json(TOKEN_COMPLETIONS, StatusCode::BAD_REQUEST, json!({}))
        .start()
        .await;
    let (deployment, client) = native(&runtime);

    let _ = client
        .complete(&deployment, native_request(false), 8, deadline(5))
        .await;
    let _ = client
        .stream(&deployment, native_request(true), 8, deadline(5))
        .await;

    let requests = runtime.requests();
    assert_eq!(requests.len(), 2);
    for request in requests {
        assert!(request.headers.contains_key(header::CONTENT_LENGTH));
        assert!(!request.headers.contains_key(header::TRANSFER_ENCODING));
    }
}

#[tokio::test]
async fn rejects_unimplemented_stochastic_sampling_before_sending() {
    let runtime = MockRuntime::builder().start().await;
    let (deployment, client) = native(&runtime);

    for (parameter, value) in [
        ("temperature", json!(0.25)),
        ("top_p", json!(1)),
        ("seed", json!(7)),
    ] {
        let mut request = native_request(false);
        request.parameters.insert(parameter.to_owned(), value);

        let failure = client
            .complete(&deployment, request, 32, deadline(5))
            .await
            .unwrap_err();

        assert_eq!(failure.kind(), RuntimeFailureKind::InvalidRequest);
        assert_eq!(failure.diagnostic_code(), "parameter");
        assert_eq!(
            failure.gateway_error(),
            GatewayError::invalid_request(Some(parameter))
        );
    }
    assert!(runtime.requests().is_empty());
}

#[tokio::test]
async fn streams_decoded_text_then_finish_then_usage() {
    let runtime = MockRuntime::builder()
        .sse(
            TOKEN_COMPLETIONS,
            &[
                token(TOKEN_H, 1),
                token(TOKEN_I, 2),
                token(E_ACUTE[0], 3),
                token(E_ACUTE[1], 4),
                terminal(4),
                DONE.to_owned(),
            ],
        )
        .start()
        .await;
    let (deployment, client) = native(&runtime);

    let mut events = client
        .stream(&deployment, native_request(true), 8, deadline(5))
        .await
        .unwrap();

    let mut deltas = Vec::new();
    for _ in 0..3 {
        let chunk = expect_chunk(events.next_event().await.unwrap());
        assert!(chunk.has_usable_output());
        deltas.push(chunk.into_response()["choices"][0]["delta"].clone());
    }
    assert_eq!(
        deltas,
        [
            json!({"role": "assistant", "content": "h"}),
            json!({"content": "i"}),
            json!({"content": "é"}),
        ]
    );

    let finish = expect_chunk(events.next_event().await.unwrap());
    assert_eq!(finish.finish_reason(), Some("stop"));
    assert!(!finish.has_usable_output());
    assert!(!finish.is_terminal_usage());

    let usage = expect_chunk(events.next_event().await.unwrap());
    assert!(usage.is_terminal_usage());
    assert_eq!(usage.usage().unwrap().output_tokens(), 4);
    assert_eq!(usage.usage().unwrap().cached_input_tokens(), 2);

    assert_eq!(
        events.next_event().await.unwrap(),
        Some(RuntimeStreamEvent::Done)
    );
    assert_eq!(events.next_event().await.unwrap(), None);
    assert_eq!(runtime.requests()[0].body["stream"], true);
}

async fn drain_stream(frames: &[String], max_tokens: u64) -> Result<(), RuntimeFailure> {
    let runtime = MockRuntime::builder()
        .sse(TOKEN_COMPLETIONS, frames)
        .start()
        .await;
    let (deployment, client) = native(&runtime);

    let mut events = client
        .stream(&deployment, native_request(true), max_tokens, deadline(5))
        .await?;
    while events.next_event().await?.is_some() {}

    Ok(())
}

#[tokio::test]
async fn rejects_an_untrustworthy_token_stream() {
    let unknown_field = data(&json!({"token_id": TOKEN_H, "usage": usage(1), "logprob": -0.1}));
    let token_and_finish =
        data(&json!({"token_id": TOKEN_H, "finish_reason": "stop", "usage": usage(1)}));
    let long_finish = data(&json!({"finish_reason": "x".repeat(101), "usage": usage(1)}));

    for (case, frames, max_tokens) in [
        (
            "token after the terminal frame",
            vec![
                token(TOKEN_H, 1),
                terminal(1),
                token(TOKEN_I, 2),
                DONE.to_owned(),
            ],
            8,
        ),
        (
            "second terminal frame",
            vec![token(TOKEN_H, 1), terminal(1), terminal(1), DONE.to_owned()],
            8,
        ),
        (
            "done before the terminal frame",
            vec![token(TOKEN_H, 1), DONE.to_owned()],
            8,
        ),
        (
            "end of stream before done",
            vec![token(TOKEN_H, 1), terminal(1)],
            8,
        ),
        (
            "unknown token field",
            vec![unknown_field, terminal(1), DONE.to_owned()],
            8,
        ),
        (
            "token and finish reason in one frame",
            vec![token_and_finish, terminal(1), DONE.to_owned()],
            8,
        ),
        (
            "finish reason over 100 characters",
            vec![token(TOKEN_H, 1), long_finish, DONE.to_owned()],
            8,
        ),
        (
            "token count past max_tokens",
            vec![
                token(TOKEN_H, 1),
                token(TOKEN_I, 2),
                terminal(2),
                DONE.to_owned(),
            ],
            1,
        ),
        (
            "terminal usage mismatch",
            vec![token(TOKEN_H, 1), terminal(2), DONE.to_owned()],
            8,
        ),
    ] {
        let failure = drain_stream(&frames, max_tokens).await.unwrap_err();

        assert_eq!(
            failure.kind(),
            RuntimeFailureKind::ProtocolViolation,
            "{case}"
        );
    }
}

#[tokio::test]
async fn a_failed_stream_bills_tokens_still_pending_in_the_decoder() {
    let cut = MockRuntime::builder()
        .truncated(
            TOKEN_COMPLETIONS,
            StatusCode::OK,
            "text/event-stream",
            token(E_ACUTE[0], 1),
        )
        .start()
        .await;
    let ended = MockRuntime::builder()
        .sse(TOKEN_COMPLETIONS, &[token(E_ACUTE[0], 1)])
        .start()
        .await;

    for (runtime, kind) in [
        (cut, RuntimeFailureKind::Interrupted),
        (ended, RuntimeFailureKind::ProtocolViolation),
    ] {
        let (deployment, client) = native(&runtime);
        let mut events = client
            .stream(&deployment, native_request(true), 8, deadline(5))
            .await
            .unwrap();

        let failure = events.next_event().await.unwrap_err();

        assert_eq!(failure.kind(), kind);
        assert_eq!(failure.usage().input_tokens(), 3);
        assert_eq!(failure.usage().output_tokens(), 1);
    }
}

#[tokio::test]
async fn a_native_release_without_encoded_input_is_a_dispatch_violation() {
    let runtime = MockRuntime::builder().start().await;
    let (deployment, client) = native(&runtime);
    let mut request = native_request(false);
    request.encoded_input_ids = None;

    let failure = client
        .complete(&deployment, request, 8, deadline(5))
        .await
        .unwrap_err();

    assert_eq!(failure.kind(), RuntimeFailureKind::ProtocolViolation);
    assert_eq!(failure.diagnostic_code(), "dispatch");
    assert!(runtime.requests().is_empty());
}

#[tokio::test]
async fn an_unavailable_decoder_fails_before_sending() {
    let runtime = MockRuntime::builder().start().await;
    let (deployment, client) = native_with(&runtime, |_| unavailable());

    let completion = client
        .complete(&deployment, native_request(false), 8, deadline(5))
        .await
        .unwrap_err();
    let stream = client
        .stream(&deployment, native_request(true), 8, deadline(5))
        .await
        .err()
        .unwrap();

    for failure in [completion, stream] {
        assert_eq!(failure.kind(), RuntimeFailureKind::Unavailable);
        assert_eq!(failure.diagnostic_code(), "tokenizer");
    }
    assert!(runtime.requests().is_empty());
}

#[tokio::test]
async fn a_slow_tokenizer_load_cannot_hold_a_stream_open_past_the_deadline() {
    let runtime = MockRuntime::builder().start().await;
    let hub = Hub::silent().await;
    let (deployment, client) = native_with(&runtime, |_| hub.tokenizer.clone());

    let opened = tokio::time::timeout(
        Duration::from_secs(5),
        client.stream(&deployment, native_request(true), 8, deadline(1)),
    )
    .await
    .expect("opening the stream overran the request deadline");
    let failure = opened.err().unwrap();

    assert_eq!(failure.kind(), RuntimeFailureKind::TimedOut);
    assert_eq!(failure.diagnostic_code(), "deadline");
    assert!(runtime.requests().is_empty());
}

#[tokio::test]
async fn a_stream_decode_failure_interrupts_and_bills_the_decoded_tokens() {
    let runtime = MockRuntime::builder()
        .sse(
            TOKEN_COMPLETIONS,
            &[token(0, 1), token(1, 2), terminal(2), DONE.to_owned()],
        )
        .start()
        .await;
    let (deployment, client) = native_with(&runtime, rewriting_prefix);

    let mut events = client
        .stream(&deployment, native_request(true), 8, deadline(5))
        .await
        .unwrap();
    expect_chunk(events.next_event().await.unwrap());
    let failure = events.next_event().await.unwrap_err();

    assert_eq!(failure.kind(), RuntimeFailureKind::Interrupted);
    assert_eq!(failure.diagnostic_code(), "tokenizer");
    assert_eq!(failure.usage().input_tokens(), 3);
    assert_eq!(failure.usage().output_tokens(), 2);
}
